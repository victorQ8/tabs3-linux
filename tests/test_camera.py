"""tabs3_camera: the packed-frame view, metering and the exposure loop's
arithmetic, without a camera (the functions that touch v4l-utils are not
exercised here)."""
import importlib.util
import pathlib
import unittest

from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'tabs3_camera', ROOT / 'packages/tabs3-base/usr/libexec/tabs3_camera.py')
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)


def pack(values):
    """Four 10-bit pixels into five bytes, as the VFE writes them."""
    out = bytearray()
    for i in range(0, len(values), 4):
        group = values[i:i + 4]
        out += bytes(v >> 2 for v in group)
        out.append(sum((v & 3) << (2 * j) for j, v in enumerate(group)))
    return bytes(out)


class FakeCamera:
    def __init__(self, exposure=500, gain=1.0):
        self.exposure, self.gain = exposure, gain
        self.line_s = 16.46e-6
        self.name = 'fake'

    def gain_limits(self):
        return 1.0, 16.0

    def max_lines(self):
        return 60000


class FrameViewTests(unittest.TestCase):
    def test_stride_pads_rows_to_eight_bytes(self):
        self.assertEqual(camera.stride_of(2576), 3224)
        self.assertEqual(camera.stride_of(640), 800)
        self.assertEqual(camera.stride_of(2104), 2632)

    def test_luma8_takes_the_high_bits_and_drops_the_padding(self):
        width, height = 8, 2
        values = [0, 4, 1023, 512, 255, 256, 3, 700, 100, 200, 300, 400, 500, 600, 700, 800]
        rows = [pack(values[:8]), pack(values[8:])]
        stride = camera.stride_of(width)
        frame = b''.join(row + bytes(stride - len(row)) for row in rows)
        image = camera.luma8(frame, width, height)
        self.assertEqual(image.size, (width, height))
        self.assertEqual(list(image.getdata()), [v >> 2 for v in values])

    def test_meter(self):
        image = Image.new('L', (10, 10), 40)
        for x in range(10):
            image.putpixel((x, 0), 255)      # a lamp: 10 % saturated
        median, p95, saturated = camera.meter(image)
        self.assertEqual(median, 40)
        self.assertEqual(p95, 255)
        self.assertAlmostEqual(saturated, 0.1)


class FakeLens:
    def __init__(self):
        self.position = None
        self.moves = []

    def set(self, position):
        self.position = position
        self.moves.append(position)


class AutofocusTests(unittest.TestCase):
    def test_sweep_finds_the_sharpest_position(self):
        lens = FakeLens()
        best_position = 700

        def grab():
            # A checkerboard whose contrast falls off with the distance from
            # the position in focus
            amplitude = max(0, 120 - abs(lens.position - best_position) // 4)
            image = Image.new('L', (16, 8), 100)
            for y in range(8):
                for x in range(16):
                    if (x + y) % 2:
                        image.putpixel((x, y), 100 + amplitude)
            return image

        cam = FakeCamera()
        position, score = camera.autofocus(cam, lens, grab=grab)
        self.assertLessEqual(abs(position - best_position), 32)
        self.assertEqual(lens.position, position)
        self.assertLess(len(lens.moves), 14)

    def test_sharpness_orders_blurred_below_sharp(self):
        sharp = Image.new('L', (16, 16), 0)
        for x in range(8, 16):
            for y in range(16):
                sharp.putpixel((x, y), 200)
        blurred = sharp.filter(ImageFilter.GaussianBlur(3))
        self.assertGreater(camera.sharpness(sharp), camera.sharpness(blurred))


class ExposureStepTests(unittest.TestCase):
    def test_settled_frame_needs_no_change(self):
        self.assertIsNone(camera.exposure_step(FakeCamera(), median=72, saturated=0.0))
        self.assertIsNone(camera.exposure_step(FakeCamera(), median=68, saturated=0.0))

    def test_dark_frame_raises_the_exposure_first(self):
        cam = FakeCamera(exposure=500, gain=1.0)
        exposure, gain = camera.exposure_step(cam, median=30, saturated=0.0)
        self.assertGreater(exposure, 500)
        self.assertEqual(gain, 1.0)
        self.assertLessEqual(exposure, 1 / 30 / cam.line_s + 1)

    def test_very_dark_frame_adds_gain_after_the_fast_exposure(self):
        cam = FakeCamera(exposure=2000, gain=1.0)
        exposure, gain = camera.exposure_step(cam, median=18, saturated=0.0)
        self.assertAlmostEqual(exposure, 1 / 30 / cam.line_s, delta=1)
        self.assertGreater(gain, 1.0)
        self.assertLessEqual(gain, 8.0)

    def test_bright_frame_lowers_the_exposure(self):
        exposure, gain = camera.exposure_step(FakeCamera(exposure=1000, gain=1.0), median=200, saturated=0.0)
        self.assertLess(exposure, 1000)
        self.assertEqual(gain, 1.0)

    def test_lamps_back_off_a_little(self):
        exposure, gain = camera.exposure_step(FakeCamera(exposure=1000, gain=1.0), median=72, saturated=0.1)
        self.assertAlmostEqual(exposure, 700, delta=1)

    def test_gain_is_spent_before_long_exposures(self):
        cam = FakeCamera(exposure=2000, gain=8.0)
        exposure, gain = camera.exposure_step(cam, median=20, saturated=0.0)
        self.assertEqual(gain, 8.0)
        self.assertGreater(exposure, 2000)
        self.assertLessEqual(exposure, 0.5 / cam.line_s + 1)


if __name__ == '__main__':
    unittest.main()
