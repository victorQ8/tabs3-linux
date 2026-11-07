"""Prevent packaging a GPU image into an unsupported boot/recovery mode."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('pack_images', SCRIPTS / 'pack-images.py')
packer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packer)
sys.path.pop(0)


class PackVariantTests(unittest.TestCase):
    def reject_arguments(self, arguments, message):
        with patch.object(sys, 'argv', ['pack-images', '--donor', '/nonexistent/donor', *arguments]):
            with contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as result:
                    packer.main()
        self.assertEqual(result.exception.code, 2)
        self.assertIn(message, error.getvalue())

    def test_gpu_cannot_be_recovery(self):
        self.reject_arguments(['--variant', 'gpu', '--mode', 'recovery'],
                              'recovery stays display-only')

    def test_gpu_cannot_be_diagnostic_or_storage_probe(self):
        for mode in ('diagnostic', 'storage-probe'):
            with self.subTest(mode=mode):
                self.reject_arguments(['--variant', 'gpu', '--mode', mode],
                                      'gpu variant requires installed')

    def test_gpu_requires_full_image_and_root_uuid(self):
        self.reject_arguments(['--variant', 'gpu', '--mode', 'installed', '--lk2nd-only'],
                              'a full Linux image')
        self.reject_arguments(['--variant', 'gpu', '--mode', 'installed'],
                              '--root-uuid is required')

    def check_dtb(self, variant, actual_gpu, clock=None):
        def fake_run(*args):
            values = {
                ('/', 'qcom,msm-id'): b'f6 30001',
                ('/', 'qcom,board-id'): b'8 5',
                ('/soc@0/mmc@7464900', 'status'): b'okay',
                ('/soc@0/mmc@7464900', 'max-frequency'): clock or (b'bebc200' if variant == 'gpu' else b'3197500'),
                ('/soc@0/gpu@b00000', 'status'): actual_gpu,
            }
            return values[args[-2:]] + b'\n'
        with patch.object(packer, 'run', side_effect=fake_run):
            packer.validate_linux_dtb(Path('test.dtb'), 'installed', variant)

    def test_gpu_enabled_only_in_gpu_variant(self):
        self.check_dtb('gpu', b'okay')
        for variant in ('display', 'headless'):
            with self.subTest(variant=variant):
                self.check_dtb(variant, b'disabled')
                with self.assertRaisesRegex(SystemExit, 'GPU status'):
                    self.check_dtb(variant, b'okay')

    def test_recovery_cap_and_full_speed_are_not_interchangeable(self):
        for variant, clock in [('display', b'bebc200'), ('gpu', b'3197500')]:
            with self.subTest(variant=variant), self.assertRaisesRegex(SystemExit, 'eMMC clock'):
                self.check_dtb(variant, b'okay' if variant == 'gpu' else b'disabled', clock)

    def test_gpu_variant_rejects_disabled_gpu(self):
        with self.assertRaisesRegex(SystemExit, 'GPU status'):
            self.check_dtb('gpu', b'disabled')


if __name__ == '__main__':
    unittest.main()
