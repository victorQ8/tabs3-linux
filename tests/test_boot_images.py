import importlib.util
import pathlib
import struct
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / 'scripts/android_boot.py'
spec = importlib.util.spec_from_file_location('android_boot', PATH)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def fixture(dt_size=0):
    header = bytearray(4096)
    header[:8] = b'ANDROID!'
    struct.pack_into('<10I', header, 8, 7, 0x80008000, 6, 0x82200000,
                     0, 0, 0x82000000, 4096, dt_size, 0)
    header[64:69] = b'test\0'
    return header + b'kernel!'.ljust(4096, b'\0') + b'initrd'.ljust(4096, b'\0')


class BootImageTests(unittest.TestCase):
    def test_page_aligned_payloads(self):
        parsed = module.parse_boot(fixture())
        self.assertEqual(parsed.kernel, b'kernel!')
        self.assertEqual(parsed.ramdisk, b'initrd')
        self.assertEqual(parsed.cmdline, 'test')

    def test_reject_truncated_payload(self):
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            module.parse_boot(fixture()[:8194])

    def test_modern_header_not_mistaken_for_legacy_dt_size(self):
        with self.assertRaisesRegex(ValueError, 'modern'):
            module.parse_boot(fixture(dt_size=2))

    def test_samsung_legacy_dtb_location(self):
        dtb = b'\xd0\x0d\xfe\xed' + struct.pack('>I', 40) + bytes(32)
        table = b'QCDT' + bytes(28) + dtb
        parsed = module.parse_boot(fixture(dt_size=4096) + table.ljust(4096, b'\0'))
        self.assertEqual(module.appended_dtbs(parsed), [dtb])

    def test_reject_missing_legacy_dt_area(self):
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            module.parse_boot(fixture(dt_size=4096))

    def test_bad_id_detected(self):
        with self.assertRaisesRegex(ValueError, 'checksum'):
            module.verify_v0_id(fixture())


if __name__ == '__main__':
    unittest.main()
