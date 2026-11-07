"""Silicon: a procedural hardware portrait for the AMOLED panel (MIT).

An illustrative exploded view, not a board schematic: the GPU is part of
the SoC and the memory packages stand for aggregate RAM, not measured banks.
The expensive material/PCB artwork is cached; only telemetry redraws.
"""
import math
import time

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from tabs3_dashboard_themes import ThemeRenderer, number, percent


ICE = '#9ae9ee'
VIOLET = '#b7a4ed'
COPPER = '#dcb38c'
INK = '#e0e8ed'
DIM = '#84929e'
RULE = '#1b252c'
WARN = '#ffb16e'


class SiliconRenderer(ThemeRenderer):
    """Dark metal, ceramic packages, copper contacts, and live instrument ink."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.artwork = None

    def path(self, points, color, width=1):
        self.d.line([(self.px(x), self.px(y)) for x, y in points],
                    fill=color, width=max(1, self.px(width)), joint='curve')

    def metal(self, x, y, w, h, top, bottom, radius=8, grain=False):
        """Directional lighting and deterministic brushed grain, built once."""
        size = max(1, self.px(w)), max(1, self.px(h))
        tile = Image.new('RGB', size)
        draw = ImageDraw.Draw(tile)
        for yy in range(size[1]):
            t = yy / max(1, size[1]-1)
            sheen = 10 * math.exp(-((t-.16)/.19)**2)
            brush = ((yy * 17 % 11)-5) * .38 if grain else 0
            rgb = tuple(round(max(0, min(255, a+(b-a)*t+sheen+brush)))
                        for a, b in zip(top, bottom))
            draw.line((0, yy, size[0], yy), fill=rgb)
        mask = Image.new('L', size)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0]-1, size[1]-1),
                                               self.px(radius), fill=255)
        self.img.paste(tile, (self.px(x), self.px(y)), mask)

    def halo(self, box, color, radius=18):
        layer = Image.new('RGB', self.img.size)
        ImageDraw.Draw(layer).rounded_rectangle(tuple(self.px(v) for v in box),
                                                self.px(18), outline=color,
                                                width=max(1, self.px(4)))
        layer = layer.filter(ImageFilter.GaussianBlur(max(1, self.px(radius))))
        # Only static, very dark local edge light; the canvas stays pure black.
        self.img.paste(ImageChops.lighter(self.img, layer))

    def screw(self, x, y):
        self.dot(x, y, 12, '#060809')
        self.dot(x, y-1, 9, '#42484c')
        self.dot(x, y, 6, '#191f23')
        self.line(x-4, y+3, x+4, y-5, '#6c7376', 2)

    def capacitor(self, x, y, vertical=False):
        w, h = (9, 19) if vertical else (19, 9)
        self.rect(x, y+2, w, h, '#030405', radius=2)
        self.rect(x, y, w, h, '#77776c', radius=2)
        self.rect(x+(1 if vertical else 5), y+(5 if vertical else 1),
                  w-(2 if vertical else 10), h-(10 if vertical else 2), '#292b28')

    def package(self, x, y, w, h):
        # Solder lands and chamfered ceramic edge.
        for xx in range(18, int(w)-12, 15):
            self.metal(x+xx, y-12, 6, 14, (100, 95, 78), (31, 33, 31), 1)
            self.metal(x+xx, y+h-2, 6, 14, (66, 67, 59), (29, 31, 29), 1)
        for yy in range(18, int(h)-12, 15):
            self.metal(x-12, y+yy, 14, 6, (81, 83, 76), (32, 35, 33), 1)
            self.metal(x+w-2, y+yy, 14, 6, (68, 71, 66), (29, 31, 29), 1)
        self.rect(x-3, y+3, w+6, h+5, '#030404', radius=10)
        self.metal(x, y, w, h, (38, 45, 50), (10, 13, 17), 9, True)
        self.rect(x+2, y+2, w-4, h-4, outline='#454e53', radius=8, width=1)
        self.line(x+12, y+h-3, x+w-12, y+h-3, '#06080a', 3)
        self.dot(x+16, y+16, 3, '#777b76')

    def memory_board(self, y):
        x, w = 1122, 802
        self.rect(x+3, y+8, w, 140, '#020404', radius=8)
        self.metal(x, y, w, 130, (15, 29, 29), (5, 12, 14), 7)
        self.rect(x, y, w, 130, outline='#324849', radius=7, width=1)
        for i in range(74):
            xx = x+28+i*10
            if 31 <= i <= 33:
                continue
            self.metal(xx, y+115, 6, 24, (144, 118, 69), (63, 55, 34), 1)
        for i in range(4):
            xx = x+43+i*184
            for j in range(5):
                self.path([(xx+15+j*13, y+111), (xx+15+j*13, y+103),
                           (xx+24+j*13, y+94)], '#24423c')
            self.package(xx, y+23, 142, 72)
            self.text(xx+13, y+38, 'LPDDR4', 17, '#7b8789', 'mono')
            self.text(xx+13, y+66, 'MEMORY', 13, '#4e5e63', 'mono')
            self.capacitor(xx+151, y+29, True)
            self.capacitor(xx+151, y+69, True)
        self.screw(x+14, y+64)
        self.screw(x+w-14, y+64)

    def build_artwork(self):
        self.img = Image.new('RGB', (self.px(2048), self.px(1536)), '#000000')
        self.d = ImageDraw.Draw(self.img)

        # Fine board traces connect the exploded components. No full-screen fill.
        for i in range(10):
            y = 422+i*17
            self.path([(833, y), (906+i*8, y), (1004+i*8, y-98),
                       (1083, y-98), (1122, y-137)], '#142d32' if i%3 else '#274b50')
        for i in range(7):
            self.path([(832, 830+i*14), (940+i*12, 830+i*14),
                       (1000+i*12, 890+i*14), (1119, 890+i*14)], '#202333')
        for i in range(6):
            self.path([(832, 990+i*14), (880+i*12, 990+i*14),
                       (972+i*12, 1082+i*14), (972+i*12, 1214)], '#15262c')
        for x, y in [(937, 317), (984, 780), (1032, 1060), (170, 1108), (1904, 642)]:
            self.dot(x, y, 5, '#31484b')
            self.dot(x, y, 2, '#000000')

        # Compute socket: layered PCB, retaining frame, capacitors, brushed lid.
        self.halo((145, 305, 835, 1063), '#256773', 23)
        self.metal(141, 306, 694, 758, (19, 32, 35), (6, 13, 16), 18)
        self.rect(141, 306, 694, 758, outline='#34474c', radius=18)
        for x in (160, 816):
            for y in (326, 1044):
                self.screw(x, y)
        for i in range(22):
            self.capacitor(191+i*27, 329)
            self.capacitor(191+i*27, 1025)
        for i in range(24):
            self.capacitor(165, 362+i*28, True)
            self.capacitor(801, 362+i*28, True)
        self.package(205, 363, 565, 637)
        self.metal(222, 379, 531, 604, (76, 86, 94), (24, 30, 37), 21, True)
        self.metal(230, 387, 515, 588, (43, 52, 62), (13, 19, 26), 15, True)
        self.line(247, 388, 725, 388, '#9aa5ac', 1)
        self.line(231, 406, 231, 950, '#53626e', 1)
        self.line(249, 975, 728, 975, '#0a1016', 2)
        self.text(267, 422, 'QUALCOMM', 22, '#aab9c5', 'mono')
        self.text(267, 464, 'Snapdragon 820', 39, INK, 'status')
        self.text(268, 925, 'MSM8996  /  KRYO CPU', 19, '#6e8794', 'mono')
        # Laser-etched orientation triangle.
        self.d.polygon([(self.px(x), self.px(y)) for x, y in
                        [(719, 399), (731, 399), (731, 411)]], fill='#909da6')

        self.memory_board(292)
        self.memory_board(480)

        # GPU package with a visibly patterned silicon die and violet edge light.
        self.halo((1120, 885, 1460, 1169), '#463066', 18)
        self.metal(1122, 889, 338, 276, (20, 27, 28), (8, 13, 15), 8)
        self.rect(1122, 889, 338, 276, outline='#384343', radius=8)
        for i in range(10):
            self.capacitor(1143+i*29, 904)
            self.capacitor(1143+i*29, 1144)
        for i in range(6):
            self.capacitor(1136, 943+i*30, True)
            self.capacitor(1435, 943+i*30, True)
        self.package(1170, 927, 240, 199)
        self.metal(1184, 940, 212, 173, (54, 47, 81), (13, 23, 32), 3)
        self.rect(1184, 940, 212, 173, outline='#6e6293', width=1)
        for i in range(12):
            for j in range(9):
                self.rect(1190+i*17, 947+j*18, 12, 12,
                          outline=('#394359' if (i+j)%3 else '#52506a'), width=1)
        # Dark central engraving area keeps the sensor figure legible.
        self.metal(1196, 978, 188, 87, (26, 29, 44), (13, 19, 30), 2)

        # Small physical battery and eMMC illustrations in the service rail.
        self.metal(83, 1286, 74, 82, (48, 53, 48), (16, 23, 22), 9)
        self.rect(105, 1277, 28, 8, '#69736a', radius=2)
        self.package(688, 1283, 94, 86)
        self.text(701, 1299, 'eMMC', 19, '#788793', 'mono')
        self.text(701, 1336, 'FLASH', 14, '#4f626c', 'mono')
        self.artwork = self.img.copy()

    def silicon(self, m, reason):
        # render() in the base class supplies centering and AMOLED pixel shift.
        if self.artwork is None:
            self.build_artwork()
        self.img.paste(self.artwork)
        self.d = ImageDraw.Draw(self.img)
        th, b = m['thermal'], m['battery']
        ram, disk = percent(m['memory']), percent(m['storage'])
        status, warn = self.state(m)
        cpu_color = WARN if th['cpu'] is not None and th['cpu'] >= 70 else ICE
        ram_color = WARN if ram is not None and ram >= 90 else ICE
        gpu_color = VIOLET
        power_color = WARN if b['capacity'] is not None and b['capacity'] < 20 else ICE
        disk_color = WARN if disk is not None and disk > 92 else COPPER
        t = time.localtime(m['now'])

        self.text(76, 58, 'Silicon', 62, INK, 'status')
        self.dot(342, 72, 4, ICE)
        self.label(365, 61, f'{m["hostname"]} / hardware telemetry', DIM, 21, width=650)
        self.text(365, 108, 'UP ' + self.duration(m['uptime']), 20, DIM, 'mono', width=650)
        self.text(1560, 58, status.upper(), 22, WARN if warn else ICE, 'mono', anchor='rt', width=510)
        self.text(1560, 106, time.strftime('%a %d %b', t).upper(), 20, DIM, 'mono', anchor='rt')
        self.text(1968, 48, time.strftime('%H:%M', t), 82, INK, 'clock', anchor='rt')
        self.line(80, 168, 1968, 168, RULE)

        self.label(80, 205, '01 / Compute', ICE, 23)
        self.text(836, 207, '4 × KRYO', 20, DIM, 'mono', anchor='rt')
        self.label(1122, 205, '02 / Memory', ICE, 23)
        self.text(1968, 193, number(ram, 1, '%'), 45, ram_color, 'figures', anchor='rt')
        self.text(1122, 248, 'LPDDR4  /  SYSTEM RAM', 19, DIM, 'mono')

        # The values sit in the packages, not in separate dashboard cards.
        self.text(487, 600, number(m['cpu'], 1), 142, cpu_color, 'figures', anchor='mt', width=470)
        self.text(708, 763, '%', 35, '#8cabb9', 'mono', anchor='rt')
        self.label(269, 775, 'CPU utilization', '#8ba1af', 20)
        self.line(269, 866, 704, 866, '#2d3c48')
        self.text(269, 887, 'TEMP', 20, '#8ba1af', 'mono')
        self.text(707, 880, number(th['cpu'], 1, ' °C'), 32, cpu_color, 'figures', anchor='rt')
        # History floats beside the socket like an oscilloscope probe.
        self.label(80, 252, 'Activity', DIM, 18)
        self.chart(245, 244, 590, 35, m['hist']['cpu'], cpu_color, fill=False)

        for i in range(4):
            x = 142+i*178
            freq = m['freqs'][i] if i < len(m['freqs']) else None
            self.text(x, 1101, f'CPU {i}', 18, DIM, 'mono')
            self.text(x, 1137, number(freq, suffix=' MHz'), 25, INK, 'mono', width=174)
        self.text(142, 1190, 'LOAD  ' + ' / '.join(m['load']), 20, DIM, 'mono', width=692)

        # One continuous aggregate occupancy meter across all eight memory chips.
        for i in range(8):
            xx, yy = 1165+(i%4)*184, 292+(i//4)*188
            for j in range(10):
                lit = ram is not None and (i*10+j+.5)/80 <= max(0, min(1, ram/100))
                self.rect(xx+9+j*12.5, yy+102, 8, 3,
                          ram_color if lit else '#263938', radius=1)
        self.text(1122, 656, self.human_bytes(m['memory']['used']) + ' occupied',
                  27, INK, 'mono', width=470)
        self.text(1968, 656, self.human_bytes(m['memory']['total']) + ' usable',
                  25, DIM, 'mono', anchor='rt', width=360)
        self.label(1122, 714, 'Memory history', DIM, 18)
        self.text(1968, 714, '0–100 %', 18, DIM, 'mono', anchor='rt')
        self.chart(1122, 754, 846, 48, m['hist']['memory'], ICE, fill=False)
        self.line(1122, 839, 1968, 839, RULE)

        self.label(1532, 887, '03 / Graphics', VIOLET, 22)
        self.text(1530, 939, 'Adreno 530', 48, INK, 'status', width=438)
        self.text(1290, 991, number(th['gpu'], 1) + '°', 48, VIOLET, 'figures', anchor='mt')
        self.text(1290, 1081, 'GPU / °C', 18, '#b3a7cb', 'mono', anchor='mt')
        self.label(1532, 1011, 'Die temperature', DIM, 19)
        self.dot(1537, 1068, 4, gpu_color if th['gpu'] is not None else WARN)
        self.text(1555, 1057, 'Sensor online' if th['gpu'] is not None else 'Sensor unavailable',
                  23, DIM, width=413)
        self.text(1532, 1110, 'Integrated in Snapdragon', 21, DIM, width=436)
        self.text(1122, 1190, 'BOARD ' + number(th['ap'], 1, ' °C'), 20, DIM, 'mono')
        self.text(1968, 1190, 'ILLUSTRATIVE COMPONENT VIEW', 17, '#64727c', 'mono', anchor='rt')

        self.line(80, 1245, 1968, 1245, RULE)
        self.label(189, 1273, '04 / Power', COPPER, 20)
        self.text(185, 1312, number(b['capacity'], suffix='%'), 51, power_color, 'figures')
        self.text(607, 1318, self.battery_status(b), 25, INK, anchor='rt', width=270)
        self.text(607, 1357, number(b['voltage'], 2, ' V') + ' / ' + number(b['current'], suffix=' mA'),
                  20, DIM, 'mono', anchor='rt', width=408)
        self.meter(94, 1300, 53, b['capacity'], power_color, segments=5, h=53, track='#242e2b')
        self.text(83, 1403, self.power(b) + '  ·  ' + number(b['temp'], 1, ' °C'),
                  21, DIM, width=540)

        self.line(647, 1280, 647, 1422, RULE)
        self.label(814, 1273, '05 / Storage', COPPER, 20)
        self.text(810, 1312, number(disk, suffix='%'), 51, disk_color, 'figures')
        self.text(1258, 1325, self.human_bytes(m['storage']['used']) + ' used',
                  26, INK, 'mono', anchor='rt', width=260)
        self.meter(814, 1380, 444, disk, disk_color, segments=37, h=5, track='#30291f')
        self.text(688, 1403, 'ROOT / ' + self.human_bytes(m['storage']['total']), 21, DIM, 'mono')

        self.line(1300, 1280, 1300, 1422, RULE)
        self.label(1340, 1273, '06 / Network', ICE, 20)
        nets = self.networks(m)
        for i, (name, v) in enumerate(nets[:2]):
            yy = 1320+i*47
            self.dot(1345, yy+10, 4, ICE if v.get('up') else WARN)
            self.text(1363, yy, name, 23, INK, 'mono', width=130)
            self.text(1968, yy, v.get('addr', 'no address'), 24, DIM, 'mono', anchor='rt', width=460)
        if not nets:
            self.text(1340, 1320, 'No active network', 26, WARN)
        else:
            rx, tx = (sum(v[k] for _, v in nets) for k in ('rx', 'tx'))
            self.text(1340, 1411, '↓ ' + self.human_bytes(rx) + '/s   ↑ ' + self.human_bytes(tx) + '/s',
                      21, ICE, 'mono', width=628)

        self.line(80, 1460, 1968, 1460, RULE)
        self.text(80, 1484, m['release'] + ' / ' + m['kernel'], 18, DIM, 'mono', width=850)
        self.text(1968, 1484, number(m['lux'], suffix=' lx') + '  ·  wake ' + reason,
                  18, DIM, 'mono', anchor='rt', width=1000)
