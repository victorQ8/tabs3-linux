"""Raw capture from the Tab S3's cameras with a software exposure loop.

Both cameras (the rear IMX258 and the front S5K5E3YX) deliver 10-bit
packed Bayer frames through the CAMSS RDI path (CSIPHY -> CSID -> ISPIF ->
VFE); nothing in the SoC processes them for Linux, so this module does
the little that a snapshot or a presence detector needs: set up the media
links and formats with media-ctl, grab single frames with v4l2-ctl (the
camera is powered only while a frame is taken), meter the 8-bit view of a
frame without numpy, run a small exposure and gain loop, and decode a frame
into a colour picture when numpy is available (a grey picture otherwise).

The rear camera's lens is a DW9807 voice-coil actuator (a V4L2 lens
subdevice): a contrast autofocus sweeps it for the sharpest frame.

Used by tabs3-snapshot and by tabs3-dashboard (its camera presence wake
samples the front camera at VGA while the screen is off). A lock keeps the
two from using the CAMSS at the same time; the last exposure of each camera
is kept under /var/lib/tabs3-camera so the next use starts close.
"""
import fcntl
import json
import os
import re
import struct
import subprocess
import time

from PIL import Image, ImageChops, ImageFilter, ImageStat

MEDIA = '/dev/media0'
LOCK = '/run/lock/tabs3-camera.lock'
STATE_DIR = '/var/lib/tabs3-camera'
BLACK8 = 16          # the sensors' black level (64 of 1023) in the 8-bit view

CAMERAS = {
    # The CAMSS only powers CSID0 and CSID1 on MSM8996 (one per VFE); the
    # front camera takes the second CSID, ISPIF line and RDI so the two
    # cameras do not share a path. Analogue gain: the S5K5E3 code is the
    # gain times 32; the IMX258 code c gives 512 / (512 - c).
    'front': dict(entity='s5k5e3', phy=2, csid=1, ispif=1, rdi=1,
                  gain=lambda code: code / 32.0,
                  code=lambda gain: int(round(gain * 32))),
    'rear': dict(entity='imx258', phy=0, csid=0, ispif=0, rdi=0, lens='dw9807',
                 gain=lambda code: 512.0 / (512 - code),
                 code=lambda gain: int(round(512 - 512 / gain))),
}
V4L2_CID_FOCUS_ABSOLUTE = 0x009a090a
VIDIOC_S_CTRL = 0xc008561c          # _IOWR('V', 28, struct v4l2_control)
SIZES = {'front': ((2576, 1932), (640, 480)),
         'rear': ((4208, 3120), (2104, 1560), (1048, 780))}


class CameraError(Exception):
    pass


def run(args, timeout=10, data=False):
    """Run a v4l-utils command; its stdout, or raise CameraError."""
    try:
        done = subprocess.run(args, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CameraError(f'{args[0]}: {exc}') from None
    if done.returncode != 0:
        err = done.stderr.decode(errors='replace').strip().split('\n')[-1]
        raise CameraError(f'{" ".join(args[:3])}: {err or done.returncode}')
    return done.stdout if data else done.stdout.decode(errors='replace')


def stride_of(width):
    """Bytes per row of a 10-bit packed frame: the VFE pads rows to 8 bytes."""
    return (width * 10 // 8 + 7) // 8 * 8


class Lock:
    """One user of the CAMSS at a time (the snapshot and the presence wake)."""

    def __init__(self, wait=15.0):
        self.wait = wait
        self.fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        self.fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(self.fd)
                    self.fd = None
                    raise CameraError('the camera is in use')
                time.sleep(0.2)

    def __exit__(self, *exc):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


class Camera:
    """One camera at one size: pipeline setup, exposure and single frames."""

    def __init__(self, name='front', size=None):
        if name not in CAMERAS:
            raise CameraError(f'unknown camera {name!r}')
        self.name = name
        self.spec = CAMERAS[name]
        self.width, self.height = size or SIZES[name][0]
        self.code = None
        self.exposure = self.gain = None
        self.ready = False
        self.entity = None
        self.subdev = self.video = None
        self.range = {}
        self.line_s = None
        self.exposure_offset = 0
        self.find()

    def find(self):
        if not os.path.exists(MEDIA):
            raise CameraError(f'no {MEDIA}: the camera did not probe')
        graph = run(['media-ctl', '-d', MEDIA, '-p'])
        m = re.search(rf'^- entity \d+: ({self.spec["entity"]} \d+-[0-9a-f]+) ', graph, re.M)
        if not m:
            raise CameraError(f'no {self.spec["entity"]} entity in the media graph')
        self.entity = m.group(1)
        self.subdev = run(['media-ctl', '-d', MEDIA, '-e', self.entity]).strip()
        self.video = run(['media-ctl', '-d', MEDIA, '-e', f'msm_vfe0_video{self.spec["rdi"]}']).strip()
        if not self.subdev.startswith('/dev/') or not self.video.startswith('/dev/'):
            raise CameraError('media-ctl did not resolve the device nodes')

    def read_controls(self):
        """Ranges (min, max) and values of the exposure-related controls."""
        text = run(['v4l2-ctl', '-d', self.subdev, '-l'])
        for line in text.splitlines():
            m = re.match(r'\s*(\w+) 0x[0-9a-f]+ \(\w+\)\s*: min=(-?\d+) max=(-?\d+) step=\d+ default=-?\d+ value=(-?\d+)',
                         line)
            if m:
                self.range[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
        for key in ('exposure', 'analogue_gain', 'vertical_blanking', 'horizontal_blanking', 'pixel_rate'):
            if key not in self.range:
                raise CameraError(f'{self.entity} has no {key} control')
        hblank, rate = self.range['horizontal_blanking'][2], self.range['pixel_rate'][2]
        self.line_s = (self.width + hblank) / float(rate)
        # Lines the exposure must stay below the frame length (the driver
        # shortens the exposure range by this much)
        vblank = self.range['vertical_blanking'][2]
        self.exposure_offset = self.height + vblank - self.range['exposure'][1]
        self.gain = self.spec['gain'](self.range['analogue_gain'][2])
        self.exposure = self.range['exposure'][2]

    def setup(self):
        """Links and formats for this camera's path; the other links are reset."""
        s = self.spec
        run(['media-ctl', '-d', MEDIA, '-r'])
        for link in (f'"msm_csiphy{s["phy"]}":1->"msm_csid{s["csid"]}":0[1]',
                     f'"msm_csid{s["csid"]}":1->"msm_ispif{s["ispif"]}":0[1]',
                     f'"msm_ispif{s["ispif"]}":1->"msm_vfe0_rdi{s["rdi"]}":0[1]'):
            run(['media-ctl', '-d', MEDIA, '-l', link])
        # The sensor picks its own Bayer order and the nearest mode
        run(['media-ctl', '-d', MEDIA, '-V',
             f'"{self.entity}":0[fmt:SBGGR10_1X10/{self.width}x{self.height} field:none]'])
        fmt = run(['media-ctl', '-d', MEDIA, '--get-v4l2', f'"{self.entity}":0'])
        m = re.search(r'fmt:(S[A-Z]{4}10_1X10)/(\d+)x(\d+)', fmt)
        if not m:
            raise CameraError(f'unexpected sensor format: {fmt.strip()}')
        self.code, self.width, self.height = m.group(1), int(m.group(2)), int(m.group(3))
        for entity in (f'msm_csiphy{s["phy"]}', f'msm_csid{s["csid"]}', f'msm_ispif{s["ispif"]}',
                       f'msm_vfe0_rdi{s["rdi"]}'):
            run(['media-ctl', '-d', MEDIA, '-V',
                 f'"{entity}":0[fmt:{self.code}/{self.width}x{self.height} field:none]'])
        pix = {'SBGGR10_1X10': 'pBAA', 'SGBRG10_1X10': 'pGAA', 'SGRBG10_1X10': 'pgAA'}.get(self.code, 'pRAA')
        run(['v4l2-ctl', '-d', self.video,
             f'--set-fmt-video=width={self.width},height={self.height},pixelformat={pix}'])
        self.read_controls()
        self.ready = True

    @property
    def order(self):
        return self.code[1:5] if self.code else 'BGGR'

    @property
    def frame_bytes(self):
        return stride_of(self.width) * self.height

    def gain_limits(self):
        lo, hi, _ = self.range['analogue_gain']
        return self.spec['gain'](lo), self.spec['gain'](hi)

    def max_lines(self):
        return self.height + self.range['vertical_blanking'][1] - self.exposure_offset

    def apply(self, exposure, gain):
        """Set the exposure (lines) and analogue gain, lengthening the frame
        when the exposure needs it. The blanking goes first: the exposure
        range follows it."""
        exposure = int(max(self.range['exposure'][0], min(exposure, self.max_lines())))
        lo, hi = self.gain_limits()
        gain = max(lo, min(gain, hi))
        vblank = max(self.range['vertical_blanking'][0], exposure + self.exposure_offset - self.height)
        run(['v4l2-ctl', '-d', self.subdev, '-c', f'vertical_blanking={vblank}'])
        run(['v4l2-ctl', '-d', self.subdev, '-c',
             f'exposure={exposure},analogue_gain={self.spec["code"](gain)}'])
        self.exposure, self.gain = exposure, gain

    def frame_s(self):
        vblank = max(self.range['vertical_blanking'][0],
                     (self.exposure or 0) + self.exposure_offset - self.height)
        return (self.height + vblank) * self.line_s

    def grab(self, skip=2):
        """One raw frame, after the first `skip` frames (the new exposure
        takes a frame or two to show). The camera streams only meanwhile."""
        if not self.ready:
            self.setup()
        timeout = 5 + (skip + 2) * self.frame_s() * 2
        data = run(['v4l2-ctl', '-d', self.video, '--stream-mmap=3', '--stream-count=1',
                    f'--stream-skip={skip}', '--stream-to=-'], timeout=timeout, data=True)
        if len(data) < self.frame_bytes:
            raise CameraError(f'short frame: {len(data)} of {self.frame_bytes} bytes')
        return data[:self.frame_bytes]

    # Exposure state shared between the users of a camera
    def state_path(self):
        return os.path.join(STATE_DIR, f'{self.name}-{self.width}x{self.height}.json')

    def load_state(self):
        try:
            with open(self.state_path()) as f:
                saved = json.load(f)
            return int(saved['exposure']), float(saved['gain'])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save_state(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            tmp = self.state_path() + '.tmp'
            with open(tmp, 'w') as f:
                json.dump({'exposure': self.exposure, 'gain': self.gain, 'time': time.time()}, f)
            os.replace(tmp, self.state_path())
        except OSError:
            pass


class Lens:
    """A V4L2 lens subdevice (the rear camera's DW9807): focus_absolute 0
    (far) to 1023 (near), held while the device stays open; the driver
    powers the coil down when nobody holds it and the lens springs back."""

    def __init__(self, entity='dw9807'):
        graph = run(['media-ctl', '-d', MEDIA, '-p'])
        m = re.search(rf'^- entity \d+: ({entity} \d+-[0-9a-f]+) ', graph, re.M)
        if not m:
            raise CameraError(f'no {entity} lens in the media graph')
        self.entity = m.group(1)
        node = run(['media-ctl', '-d', MEDIA, '-e', self.entity]).strip()
        try:
            self.fd = os.open(node, os.O_RDWR)
        except OSError as exc:
            raise CameraError(f'{self.entity}: {exc}') from None
        self.position = None

    def set(self, position):
        position = int(max(0, min(position, 1023)))
        try:
            fcntl.ioctl(self.fd, VIDIOC_S_CTRL, struct.pack('Ii', V4L2_CID_FOCUS_ABSOLUTE, position))
        except OSError as exc:
            raise CameraError(f'{self.entity}: focus {position}: {exc}') from None
        self.position = position
        time.sleep(0.02)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def sharpness(view):
    """Edge variance of a grey image: the sharper, the higher."""
    return ImageStat.Stat(view.filter(ImageFilter.FIND_EDGES)).var[0]


def autofocus(cam, lens, log=None, grab=None):
    """Contrast autofocus at the current exposure: a coarse sweep of the
    actuator's range, then finer steps around the best position. Returns
    the position and its score; the lens is left there."""
    grab = grab or (lambda: luma8(cam.grab(skip=1), cam.width, cam.height).reduce(4))
    scores = {}

    def measure(position):
        lens.set(position)
        scores[position] = sharpness(grab())
        return scores[position]

    for position in (0, 256, 512, 768, 1023):
        measure(position)
    best = max(scores, key=scores.get)
    step = 128
    while step >= 32:
        for position in (best - step, best + step):
            if 0 <= position <= 1023 and position not in scores:
                measure(position)
        best = max(scores, key=scores.get)
        step //= 2
    lens.set(best)
    if log:
        ranked = sorted(scores.items())
        log(f'{cam.name}: focus {best} (edge variance {scores[best]:.0f}; '
            + ', '.join(f'{p}: {s:.0f}' for p, s in ranked) + ')')
    return best, scores[best]


def luma8(frame, width, height):
    """The 8-bit view of a packed 10-bit frame as a grey PIL image: the four
    high bytes of every five-byte group are the pixels' top bits, so no
    unpacking is needed (the row padding is dropped)."""
    stride, used = stride_of(width), width * 10 // 8
    if stride != used:
        frame = b''.join(frame[r * stride:r * stride + used] for r in range(height))
    else:
        frame = frame[:used * height]
    out = bytearray(len(frame) * 4 // 5)
    for i in range(4):
        out[i::4] = frame[i::5]
    return Image.frombuffer('L', (width, height), bytes(out), 'raw', 'L', 0, 1)


def meter(image):
    """Median, 95th percentile and saturated fraction of a grey image."""
    hist = image.histogram()
    total = sum(hist) or 1
    cum, median, p95 = 0, 0, 0
    for value, count in enumerate(hist):
        if cum < total * 0.5 <= cum + count:
            median = value
        if cum < total * 0.95 <= cum + count:
            p95 = value
        cum += count
    saturated = sum(hist[250:]) / total
    return median, p95, saturated


def exposure_step(cam, median, saturated, target=72, fast_s=1 / 30, max_gain=8.0, max_s=0.5):
    """The next exposure and gain for a frame metered at `median` (8-bit
    luma, black at 16); None when the frame is close enough. Exposure is
    raised first up to `fast_s` seconds, then the gain up to `max_gain`,
    then the exposure again up to `max_s` seconds."""
    level = max(median - BLACK8, 1)
    want = target - BLACK8
    if saturated > 0.04 and median > target * 0.6:
        factor = 0.7                       # bright patches: back off a little
    else:
        factor = want / float(level)
    if 0.87 < factor < 1.15:
        return None
    factor = max(1 / 8.0, min(factor, 8.0))
    ev = cam.exposure * cam.gain * factor   # in line-gains
    lo_gain, hi_gain = cam.gain_limits()
    hi_gain = min(hi_gain, max_gain)
    fast = fast_s / cam.line_s
    longest = min(max_s / cam.line_s, cam.max_lines())
    if ev <= fast * lo_gain:
        return max(ev / lo_gain, 1), lo_gain
    gain = min(ev / fast, hi_gain)
    return min(ev / gain, longest), gain


def auto_expose(cam, steps=6, log=None, **limits):
    """Converge the exposure on a frame; returns the last frame and its stats."""
    saved = cam.load_state()
    if saved and cam.exposure is None or (saved and (cam.exposure, cam.gain) != saved):
        cam.apply(*saved)
    elif cam.exposure is None:
        cam.apply(cam.range['exposure'][1] // 2, 1.0)
    frame = stats = None
    for step in range(steps):
        frame = cam.grab()
        stats = meter(luma8(frame, cam.width, cam.height).reduce(8))
        median, p95, saturated = stats
        nxt = exposure_step(cam, median, saturated, **limits)
        if log:
            log(f'{cam.name} {cam.width}x{cam.height}: exposure {cam.exposure} lines '
                f'({cam.exposure * cam.line_s * 1000:.1f} ms) gain {cam.gain:.2f}x: '
                f'median {median} p95 {p95} saturated {saturated * 100:.1f} %'
                + ('' if nxt else ' (settled)'))
        if nxt is None:
            break
        cam.apply(*nxt)
    cam.save_state()
    return frame, stats


def decode(frame, width, height, order='GRBG', rotate=0):
    """A colour picture at half size: black level, grey-world white balance,
    gamma 2.2. Needs numpy; without it the grey 8-bit view is returned."""
    try:
        import numpy as np
    except ImportError:
        return luma8(frame, width, height).resize((width // 2, height // 2), Image.BOX).rotate(rotate, expand=True)
    stride = stride_of(width)
    rows = np.frombuffer(frame, dtype=np.uint8)[:stride * height].reshape(height, stride)[:, :width * 10 // 8]
    packed = rows.reshape(height, width // 4, 5).astype(np.uint16)
    low = packed[:, :, 4]
    pixels = np.empty((height, width // 4, 4), dtype=np.uint16)
    for i in range(4):
        pixels[:, :, i] = (packed[:, :, i] << 2) | ((low >> (2 * i)) & 3)
    pixels = pixels.reshape(height, width)
    planes = {'R': [], 'G': [], 'B': []}
    cells = [pixels[0::2, 0::2], pixels[0::2, 1::2], pixels[1::2, 0::2], pixels[1::2, 1::2]]
    for colour, cell in zip(order, cells):
        planes[colour].append(cell.astype(np.float32))
    r, g, b = (sum(planes[c]) / len(planes[c]) for c in 'RGB')
    black = 64.0
    median = float(np.median(g))
    r, g, b = (np.clip(plane - black, 0, None) for plane in (r, g, b))
    grey = max(float(g.mean()), 1.0)
    r *= grey / max(float(r.mean()), 1.0)
    b *= grey / max(float(b.mean()), 1.0)
    # White point: the brightest half percent, but lamps in the picture
    # must not push the room into the dark
    white = max(min(float(np.percentile(g, 99.5)), 8 * max(median - black, 8)), 1.0)
    rgb = np.clip(np.stack([r, g, b], axis=2) / white, 0, 1) ** (1 / 2.2)
    return Image.fromarray((rgb * 255).astype(np.uint8), 'RGB').rotate(rotate, expand=True)


def snapshot(name='front', size=None, rotate=0, log=None, steps=6, focus='auto'):
    """A metered colour picture from a camera (the camera is locked
    meanwhile). `focus` is 'auto' (a sweep, when the camera has a lens), a
    position, or None to leave the lens alone."""
    with Lock():
        cam = Camera(name, size)
        cam.setup()
        lens = Lens(cam.spec['lens']) if focus is not None and cam.spec.get('lens') else None
        try:
            frame, stats = auto_expose(cam, steps=steps, log=log)
            if lens is not None:
                if focus == 'auto':
                    autofocus(cam, lens, log)
                else:
                    lens.set(int(focus))
                frame = cam.grab()
            return decode(frame, cam.width, cam.height, cam.order, rotate), cam, stats
        finally:
            if lens is not None:
                lens.close()


class MotionSampler:
    """Presence from the front camera while the screen is off: a VGA frame
    every `interval` seconds, metered to keep its exposure sensible, and
    compared with the previous one on a coarse grid. A change larger than
    `threshold` percent of the picture's level is motion. Frames live only in
    memory."""

    def __init__(self, name='front', interval=4.0, threshold=3.5, log=None):
        self.name = name
        self.interval = interval
        self.threshold = threshold
        self.log = log or (lambda msg: None)
        self.cam = None
        self.reference = None
        self.level = None
        self.next_at = 0.0
        self.failures = 0
        self.last_change = None     # percent, for diagnostics

    def start(self):
        self.cam = None
        self.reference = None
        self.next_at = 0.0
        self.failures = 0

    def stop(self):
        if self.cam is not None and self.cam.exposure is not None:
            self.cam.save_state()
        self.cam = None
        self.reference = None

    def open(self):
        cam = Camera(self.name, SIZES[self.name][-1])
        cam.setup()
        saved = cam.load_state()
        cam.apply(*saved) if saved else cam.apply(cam.range['exposure'][1] // 2, 1.0)
        return cam

    def sample(self, now):
        """A description of the motion, or None. Cheap when it is not time."""
        if now < self.next_at:
            return None
        self.next_at = now + self.interval
        try:
            with Lock(wait=2.0):
                if self.cam is None:
                    self.cam = self.open()
                cam = self.cam
                frame = cam.grab(skip=1)
                view = luma8(frame, cam.width, cam.height).reduce(16)    # 40x30
                median, p95, saturated = meter(view)
                nxt = exposure_step(cam, median, saturated, fast_s=1 / 15, max_gain=8.0, max_s=0.25)
        except CameraError as exc:
            self.failures += 1
            self.reference = None
            self.cam = None         # set the pipeline up again: another user
            if self.failures in (1, 10, 100):   # (a snapshot) may have reset the links
                self.log(f'camera presence: {exc}')
            if self.failures >= 3:
                self.next_at = now + min(self.interval * self.failures, 120)
            return None
        self.failures = 0
        hit = None
        dark = median < BLACK8 + 6 and nxt is not None and nxt[0] >= cam.max_lines() * 0.9
        if self.reference is not None and self.level is not None and not dark:
            # Compare at equal brightness: scale the new view to the old level
            level = max(median - BLACK8, 4)
            scaled = view.point(lambda v: min(255, int(BLACK8 + (v - BLACK8) * self.level / level))) \
                if abs(level - self.level) > 2 else view
            change = ImageStat.Stat(ImageChops.difference(scaled, self.reference)).mean[0]
            percent = 100.0 * change / max(self.level, 4)
            self.last_change = percent
            if percent >= self.threshold:
                hit = f'{percent:.0f} % of the picture changed'
        self.reference, self.level = view, max(median - BLACK8, 4)
        if nxt is not None:
            cam.apply(*nxt)
            self.reference = None       # a new exposure: compare from the next frame
        if dark:
            self.next_at = now + self.interval * 4
        return hit
