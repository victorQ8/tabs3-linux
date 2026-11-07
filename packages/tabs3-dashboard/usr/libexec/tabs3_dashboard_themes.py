"""Optional Pillow layouts for the panel dashboard (SPDX-License-Identifier: MIT).

All coordinates use a 2048 x 1536 design space. This module only renders
samples supplied by the dashboard; it never reads hardware or changes state.
"""
import math
import time

from PIL import Image, ImageDraw, ImageFont


THEMES = ('original', 'observatory', 'folio', 'terminal', 'silicon')
BLACK = '#000000'
WHITE = '#e8efed'
MUTED = '#8caaa4'
GRID = '#1b302c'
GREEN = '#8ae8bd'
CYAN = '#79d7e8'
AMBER = '#efb46e'
PURPLE = '#b6a4ed'


def number(value, digits=0, suffix=''):
    return '—' if value is None else f'{value:.{digits}f}{suffix}'


def percent(item):
    return 100 * item['used'] / item['total'] if item['total'] else None


class ThemeRenderer:
    """Shared drawing primitives, with deliberately different compositions."""

    def __init__(self, width, height, theme, font_dir, roles, fallback,
                 human_bytes, duration, status_of):
        self.w, self.h, self.theme = width, height, theme
        self.s = min(width / 2048, height / 1536)
        self.font_dir, self.roles, self.fallback = font_dir, roles, fallback
        self.human_bytes, self.duration, self.status_of = human_bytes, duration, status_of
        self.fonts, self.tiles = {}, {}

    def px(self, value):
        return round(value * self.s)

    def font(self, size, role='text'):
        key = size, role
        if key not in self.fonts:
            if role == 'serif':
                paths = ['truetype/dejavu/DejaVuSerif.ttf'] + self.fallback['text']
            else:
                paths = self.roles.get(role, []) + self.fallback[role]
            for path in paths:
                try:
                    self.fonts[key] = ImageFont.truetype(f'{self.font_dir}/{path}', max(1, self.px(size)))
                    break
                except OSError:
                    continue
            else:
                self.fonts[key] = ImageFont.load_default(max(1, self.px(size)))
        return self.fonts[key]

    def text(self, x, y, value, size=32, color=WHITE, role='text', anchor='lt', width=None):
        value = str(value)
        font = self.font(size, role)
        if width is not None and font.getlength(value) > self.px(width):
            while value and font.getlength(value + '…') > self.px(width):
                value = value[:-1]
            value += '…'
        key = value, size, role, color, anchor
        cached = self.tiles.get(key)
        if cached is None:
            l, t, r, b = font.getbbox(value, anchor=anchor)
            tile = Image.new('RGBA', (max(1, r - l), max(1, b - t)))
            ImageDraw.Draw(tile).text((-l, -t), value, font=font, fill=color, anchor=anchor)
            cached = tile, l, t
            if len(self.tiles) >= 400:
                self.tiles.clear()
            self.tiles[key] = cached
        tile, l, t = cached
        self.img.paste(tile, (self.px(x) + l, self.px(y) + t), tile)

    def label(self, x, y, text, color=MUTED, size=23, width=None):
        self.text(x, y, text.upper(), size, color, 'mono', width=width)

    def line(self, x1, y1, x2, y2, color=GRID, width=2):
        self.d.line(tuple(self.px(v) for v in (x1, y1, x2, y2)),
                    fill=color, width=max(1, self.px(width)))

    def rect(self, x, y, w, h, fill=None, outline=None, radius=0, width=2):
        box = tuple(self.px(v) for v in (x, y, x + w, y + h))
        self.d.rounded_rectangle(box, radius=self.px(radius), fill=fill,
                                 outline=outline, width=max(1, self.px(width)))

    def dot(self, x, y, r=5, color=GREEN):
        self.d.ellipse(tuple(self.px(v) for v in (x-r, y-r, x+r, y+r)), fill=color)

    def chart(self, x, y, w, h, series, color=GREEN, lo=0, hi=100, fill=True, bars=False):
        # Keep missing readings as gaps, and only draw as many points as pixels.
        values = list(series)
        if not values:
            self.text(x + w / 2, y + h / 2, 'Awaiting samples', 25, MUTED, anchor='mm')
            return
        step = max(1, math.ceil(len(values) / max(1, self.px(w / (8 if bars else 1)))))
        groups, points = [], []
        indices = list(range(0, len(values), step))
        if indices[-1] != len(values)-1:
            indices.append(len(values)-1)
        for i in indices:
            value = values[i]
            if value is None:
                if points:
                    groups.append(points)
                    points = []
                continue
            xx = x + w * i / max(1, len(values)-1)
            yy = y + h * (1 - (max(lo, min(hi, value)) - lo) / (hi-lo))
            points.append((xx, yy))
        if points:
            groups.append(points)
        if not groups:
            self.text(x + w / 2, y + h / 2, 'No sensor samples', 23, MUTED, anchor='mm')
            return
        rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        dark = tuple(round(v * 0.10) for v in rgb)
        for points in groups:
            scaled = [(self.px(a), self.px(b)) for a, b in points]
            if bars:
                for xx, yy in points:
                    self.line(xx, yy, xx, y+h, color, 4)
            else:
                if fill and len(points) > 1:
                    polygon = [(scaled[0][0], self.px(y+h))] + scaled + [(scaled[-1][0], self.px(y+h))]
                    self.d.polygon(polygon, fill=dark)
                if len(points) > 1:
                    self.d.line(scaled, fill=color, width=max(1, self.px(3)), joint='curve')
                self.dot(*points[-1], r=4, color=color)

    def meter(self, x, y, w, value, color=GREEN, segments=40, h=12, track=GRID):
        for i in range(segments):
            active = value is not None and (i + 0.5) / segments <= max(0, min(1, value / 100))
            self.rect(x + i * w / segments, y, w / segments - 4, h,
                      fill=color if active else track)

    def ring(self, cx, cy, r, value, color=GREEN):
        for i in range(61):
            angle = math.radians(135 + i * 4.5)
            inner = r - (20 if i % 5 == 0 else 10)
            on = value is not None and i / 60 <= value / 100
            self.line(cx + inner * math.cos(angle), cy + inner * math.sin(angle),
                      cx + r * math.cos(angle), cy + r * math.sin(angle), color if on else GRID, 3)
        box = tuple(self.px(v) for v in (cx-r+40, cy-r+40, cx+r-40, cy+r-40))
        self.d.arc(box, 135, 405, fill=GRID, width=max(1, self.px(9)))
        if value is not None and value > 0:
            self.d.arc(box, 135, 135 + 270 * min(100, value) / 100,
                       fill=color, width=max(1, self.px(9)))

    def state(self, m):
        status, warn = self.status_of(m)
        if status in ('Normal', 'On battery') and any(v is None for v in (
                m['thermal']['cpu'], m['battery']['capacity'], m['battery']['charger'],
                percent(m['memory']), percent(m['storage']))):
            return 'Telemetry incomplete', True
        return status, warn

    @staticmethod
    def power(battery):
        from tabs3_dashboard_power import power_source
        return power_source(battery)

    @staticmethod
    def battery_status(battery):
        from tabs3_dashboard_power import battery_status
        return battery_status(battery)

    @staticmethod
    def networks(m):
        return [(n, v) for n, v in sorted(m['network'].items()) if v.get('up') or v.get('addr')]

    @staticmethod
    def processors(m):
        names = {'mss': 'modem', 'adsp': 'audio DSP', 'slpi': 'sensor DSP'}
        return [(names.get(k, k), v) for k, v in sorted(m['remoteprocs'].items())]

    def firmware_line(self, m, x, y, width=1888, color=MUTED):
        states = self.processors(m)
        text = '   /   '.join(f'{name} · {state}' for name, state in states) or 'Firmware state unavailable'
        self.text(x, y, text, 25, color, 'mono', width=width)

    def footer(self, m, reason, color=MUTED, rule=GRID):
        self.line(80, 1430, 1968, 1430, rule)
        self.text(80, 1460, f'{m["release"]}  /  {m["kernel"]}', 23, color, 'mono', width=880)
        self.text(1968, 1460, f'{number(m["lux"], suffix=" lx")}  ·  wake {reason}',
                  23, color, 'mono', anchor='rt', width=960)

    def render(self, m, reason, shift=(0, 0)):
        self.img = Image.new('RGB', (self.px(2048), self.px(1536)), BLACK)
        self.d = ImageDraw.Draw(self.img)
        getattr(self, self.theme)(m, reason)
        canvas = Image.new('RGB', (self.w, self.h), BLACK)
        canvas.paste(self.img, ((self.w-self.img.width)//2 + shift[0],
                                (self.h-self.img.height)//2 + shift[1]))
        return canvas

    def observatory(self, m, reason):
        t = time.localtime(m['now'])
        b, th, hist = m['battery'], m['thermal'], m['hist']
        status, warn = self.state(m)
        accent = AMBER if warn else GREEN
        self.rect(80, 70, 10, 34, fill=GREEN)
        self.label(112, 75, f'{m["hostname"]} / observatory', width=1100)
        self.text(80, 155, status, 66, accent, 'status', width=1100)
        self.text(82, 252, f'UP {self.duration(m["uptime"])}   /   {m["sessions"]} SESSIONS', 27, MUTED, 'mono')
        self.text(1968, 62, time.strftime('%H:%M', t), 140, WHITE, 'clock', anchor='rt')
        self.text(1968, 226, time.strftime('%A, %d %B', t), 29, MUTED, anchor='rt')
        self.line(80, 322, 1968, 322)

        self.ring(401, 608, 238, m['cpu'])
        self.text(401, 551, number(m['cpu'], 1), 130, WHITE, 'figures', anchor='mt')
        self.label(335, 706, 'CPU / %', GREEN)
        self.text(401, 834, 'PROCESSOR UTILIZATION', 23, MUTED, 'mono', anchor='mt')
        self.label(820, 380, 'Processor history', GREEN)
        self.text(1968, 380, '0–100 %', 25, MUTED, 'mono', anchor='rt')
        for i in range(4):
            yy = 448 + i * 100
            self.line(820, yy, 1968, yy)
        self.chart(820, 448, 1148, 300, hist['cpu'])
        self.label(820, 778, 'oldest sample')
        self.text(1968, 778, 'NOW', 23, GREEN, 'mono', anchor='rt')
        self.text(820, 842, 'LOAD  ' + '  '.join(m['load']), 29, WHITE, 'mono')
        self.text(1968, 842, 'CPU ' + number(th['cpu'], 1, ' °C'), 29, AMBER, 'mono', anchor='rt')

        blocks = [
            ('BATTERY', b['capacity'], self.battery_status(b),
             f'{number(b["current"], suffix=" mA")} / {number(b["voltage"], 2, " V")}', GREEN),
            ('MEMORY', percent(m['memory']), self.human_bytes(m['memory']['used']) + ' in use',
             self.human_bytes(m['memory']['total']) + ' total', CYAN),
            ('STORAGE', percent(m['storage']), self.human_bytes(m['storage']['used']) + ' used',
             self.human_bytes(m['storage']['total']) + ' total', PURPLE),
        ]
        for i, (name, value, detail, sub, color) in enumerate(blocks):
            x = 80 + i * 650
            if value is not None and ((name=='BATTERY' and value<20) or (name=='STORAGE' and value>92)):
                color = AMBER
            self.line(x, 930, x+588, 930)
            self.label(x, 962, name, color)
            self.text(x, 1012, number(value, suffix='%'), 92, AMBER if color==AMBER else WHITE, 'figures')
            self.text(x+588, 1037, detail, 27, MUTED, anchor='rt', width=270)
            self.text(x+588, 1082, sub, 24, MUTED, anchor='rt', width=270)
            self.meter(x, 1146, 588, value, color)

        self.label(80, 1220, 'Connections')
        nets = self.networks(m)
        for i, (name, v) in enumerate(nets[:2]):
            y = 1274 + i*54
            self.dot(88, y+14, color=GREEN if v.get('up') else AMBER)
            self.text(112, y, f'{name}  {v.get("addr", "no address")}', 29, WHITE, 'mono', width=500)
            self.text(1120, y, f'↓ {self.human_bytes(v["rx"])}/s  ↑ {self.human_bytes(v["tx"])}/s',
                      25, MUTED, 'mono', anchor='rt', width=500)
        if not nets:
            self.text(80, 1274, 'No active network', 30, AMBER)
        self.label(1250, 1220, 'Thermal / °C')
        self.text(1250, 1274, 'BOARD ' + number(th['ap'], 1), 30, MUTED, 'mono')
        self.text(1968, 1274, 'GPU ' + number(th['gpu'], 1), 30, MUTED, 'mono', anchor='rt')
        self.text(1250, 1328, 'BATTERY ' + number(b['temp'], 1), 30, MUTED, 'mono')
        self.text(1968, 1328, self.power(b).upper(),
                  24, accent, 'mono', anchor='rt', width=460)
        self.firmware_line(m, 80, 1385)
        self.footer(m, reason)

    def folio(self, m, reason):
        cream, faded, rust, rule = '#eee4d2', '#aa9f8c', '#e7a179', '#3c352c'
        t = time.localtime(m['now'])
        b, th, hist = m['battery'], m['thermal'], m['hist']
        status, warn = self.state(m)
        self.rect(80, 70, 36, 36, fill=rust)
        self.label(140, 77, f'{m["hostname"]}  /  the daily reading', faded, width=1400)
        self.text(1968, 77, time.strftime('%d . %m . %Y', t), 26, faded, 'mono', anchor='rt')
        self.line(80, 138, 1968, 138, rule)
        self.text(64, 214, time.strftime('%H:%M', t), 310, cream, 'serif')
        self.text(82, 556, time.strftime('%A', t), 53, faded)
        self.text(1240, 220, '01 / SYSTEM STATUS', 23, rust, 'mono')
        self.text(1240, 277, status, 66, rust if warn else cream, 'status', width=728)
        self.line(1240, 382, 1968, 382, rule)
        for i, (label, value) in enumerate([
            ('UPTIME', self.duration(m['uptime'])),
            ('POWER', self.power(b)),
            ('SESSIONS', str(m['sessions'])),
        ]):
            yy = 420 + i*60
            self.label(1240, yy, label, faded)
            self.text(1968, yy, value, 30, cream, anchor='rt', width=470)
        self.line(80, 664, 1968, 664, cream, 3)
        columns = [
            ('02 / PROCESSOR', m['cpu'], '%', hist['cpu'], 100,
             'Load  ' + ' / '.join(m['load'])),
            ('03 / TEMPERATURE', th['cpu'], '°C', hist['temp'], 100,
             'Board ' + number(th['ap'], 1, '°') + '  ·  GPU ' + number(th['gpu'], 1, '°')),
            ('04 / BATTERY', b['capacity'], '%', hist['battery'], 100,
             f'{self.battery_status(b)}  ·  {number(b["temp"], 1, "°C")}'),
        ]
        for i, (label, value, unit, series, high, detail) in enumerate(columns):
            x = 80 + i*650
            self.label(x, 709, label, rust)
            self.text(x-4, 779 if value is not None else 839,
                      number(value, 1 if i==1 else 0), 156, cream, 'serif')
            self.text(x+570, 865, unit, 48, faded, anchor='rt')
            self.chart(x, 984, 570, 80, series, rust, hi=high, fill=False)
            self.text(x, 1100, detail, 28, faded, width=570)
        self.line(80, 1174, 1968, 1174, rule)
        for x, title, item in [(80, 'MEMORY', m['memory']), (1060, 'STORAGE', m['storage'])]:
            self.label(x, 1214, title, faded)
            self.text(x+870, 1208, f'{self.human_bytes(item["used"])} / {self.human_bytes(item["total"])}',
                      35, cream, 'mono', anchor='rt')
            self.meter(x, 1270, 870, percent(item), rust, segments=60, h=5, track='#2a2520')
        nets = self.networks(m)
        for i, (name, v) in enumerate(nets[:2]):
            x = 80 + i*980
            self.text(x, 1325, f'{name}  {v.get("addr", "no address")}', 28, cream, 'mono', width=870)
            self.text(x, 1372, f'↓ {self.human_bytes(v["rx"])}/s    ↑ {self.human_bytes(v["tx"])}/s',
                      25, faded, 'mono', width=870)
        if not nets:
            self.text(80, 1325, 'No active network', 28, rust)
        self.footer(m, reason, faded, rule)

    def box(self, x, y, w, h, title, color):
        self.rect(x, y, w, h, outline=color, radius=16)
        length = self.font(26, 'mono').getlength(title) / self.s
        self.rect(x+24, y-15, length+32, 34, fill=BLACK)
        self.text(x+40, y-13, title, 26, color, 'mono')

    def terminal(self, m, reason):
        t = time.localtime(m['now'])
        b, th, hist = m['battery'], m['thermal'], m['hist']
        status, warn = self.state(m)
        self.text(52, 48, 'tabS3', 48, GREEN, 'mono')
        self.text(250, 62, ':: terminal', 28, MUTED, 'mono')
        self.text(1024, 62, f'{m["hostname"]} / {status.lower()}', 28, AMBER if warn else GREEN,
                  'mono', anchor='mt', width=700)
        self.text(1996, 47, time.strftime('%H:%M:%S', t), 48, WHITE, 'mono', anchor='rt')

        self.box(48, 154, 1952, 470, '1 cpu', GREEN)
        self.label(88, 206, 'aggregate utilization', MUTED)
        for i in range(5):
            y = 277 + i*60
            self.line(88, y, 1330, y)
        self.chart(88, 277, 1242, 240, hist['cpu'], GREEN, bars=True)
        self.text(88, 564, 'oldest', 23, MUTED, 'mono')
        self.text(1330, 564, 'now', 23, GREEN, 'mono', anchor='rt')
        self.line(1380, 196, 1380, 582, GRID)
        self.text(1440, 218, number(m['cpu'], 1, '%'), 94, GREEN, 'mono')
        for i, freq in enumerate(m['freqs'][:4]):
            self.text(1440, 350+i*47, f'core {i}', 26, MUTED, 'mono')
            self.text(1958, 350+i*47, number(freq, suffix=' MHz'), 26, WHITE, 'mono', anchor='rt')
        if not m['freqs']:
            self.text(1440, 350, 'Clocks unavailable', 26, MUTED, 'mono')
        self.text(1440, 564, 'load ' + ' '.join(m['load']), 24, MUTED, 'mono', width=518)

        self.box(48, 666, 860, 334, '2 memory / disk', CYAN)
        for y, label, item, color in [(716, 'mem', m['memory'], CYAN), (858, 'disk', m['storage'], PURPLE)]:
            if label=='disk' and percent(item) is not None and percent(item)>92:
                color = AMBER
            self.text(88, y, label, 32, color, 'mono')
            self.text(866, y, f'{self.human_bytes(item["used"])} / {self.human_bytes(item["total"])}',
                      29, WHITE, 'mono', anchor='rt')
            self.meter(88, y+54, 610, percent(item), color, segments=38, h=20)
            self.text(866, y+50, number(percent(item), suffix='%'), 28, color, 'mono', anchor='rt')
            if label == 'mem':
                self.chart(88, y+92, 610, 26, hist['memory'], CYAN, fill=False)

        self.box(948, 666, 1052, 334, '3 thermal / power', AMBER)
        for i, (label, value) in enumerate([('CPU', th['cpu']), ('BOARD', th['ap']), ('GPU', th['gpu'])]):
            x = 990 + i*320
            self.label(x, 713, label, MUTED)
            self.text(x, 763, number(value, 1, '°'), 66, AMBER, 'mono')
        self.line(990, 854, 1958, 854)
        battery_color = AMBER if b['capacity'] is not None and b['capacity']<20 else GREEN
        self.text(990, 885, 'BAT ' + number(b['capacity'], suffix='%'), 30, battery_color, 'mono')
        self.meter(1260, 892, 368, b['capacity'], battery_color, segments=23, h=18)
        self.text(1958, 885, self.battery_status(b), 26, WHITE, 'mono', anchor='rt', width=290)
        self.text(990, 945, f'{number(b["voltage"], 2, " V")}  {number(b["current"], suffix=" mA")}  '
                  f'{number(b["temp"], 1, "°C")}', 26, MUTED, 'mono')
        self.text(1958, 945, self.power(b).lower(), 25,
                  MUTED if b['charger'] else AMBER, 'mono', anchor='rt', width=400)

        self.box(48, 1042, 860, 360, '4 network', PURPLE)
        nets = self.networks(m)
        for i, (name, v) in enumerate(nets[:2]):
            y = 1092 + i*140
            self.text(88, y, name, 30, PURPLE, 'mono', width=220)
            self.text(866, y, v.get('addr', 'no address'), 28, WHITE, 'mono', anchor='rt', width=520)
            self.text(88, y+53, '↓ ' + self.human_bytes(v['rx']) + '/s', 30, CYAN, 'mono')
            self.text(866, y+53, '↑ ' + self.human_bytes(v['tx']) + '/s', 30, GREEN, 'mono', anchor='rt')
            if not i:
                self.line(88, y+107, 866, y+107)
        if not nets:
            self.text(88, 1110, 'No active network', 30, AMBER, 'mono')

        self.box(948, 1042, 1052, 360, '5 remote processors', CYAN)
        self.label(990, 1092, 'name', MUTED)
        self.text(1958, 1092, 'state', 23, MUTED, 'mono', anchor='rt')
        self.line(990, 1136, 1958, 1136)
        procs = self.processors(m)
        for i, (name, state) in enumerate(procs[:3]):
            yy = 1165 + i*52
            self.text(990, yy, name, 30, WHITE, 'mono', width=550)
            self.text(1958, yy, '● ' + state, 28, GREEN if state=='running' else AMBER,
                      'mono', anchor='rt', width=350)
        if not procs:
            self.text(990, 1170, 'State unavailable', 28, AMBER, 'mono')
        self.text(990, 1338, 'up ' + self.duration(m['uptime']), 25, MUTED, 'mono')
        self.text(1958, 1338, f'{m["sessions"]} sessions', 25, MUTED, 'mono', anchor='rt')
        self.footer(m, reason)
