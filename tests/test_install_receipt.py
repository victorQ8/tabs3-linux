"""Host-only tests: no ADB/SSH calls or device writes."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load('record-storage-probe')
installer = load('install-internal')


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.output = ('userdata_bytes=26226966016\ncid_sha256=' + 'a'*64 +
                       '\nkernel=test\n' + ('read_sha256=' + 'b'*64 + '\n')*3)

    def test_successful_receipt_matches_same_device(self):
        report = probe.parse_report(self.output)
        installer.validate_storage_report(report, 'a'*64, 26226966016)

    def test_wrong_device_refused(self):
        with self.assertRaises(ValueError):
            installer.validate_storage_report(probe.parse_report(self.output), 'c'*64, 26226966016)

    def test_partial_or_inconsistent_reads_refused(self):
        for text in (self.output.rsplit('read_sha256=', 1)[0],
                     self.output.replace('b'*64, 'c'*64, 1),
                     self.output.replace('26226966016', '1024')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                probe.parse_report(text)

    def test_legacy_or_incomplete_receipt_refused(self):
        report = probe.parse_report(self.output)
        for key in ('schema', 'cid_sha256', 'read_sha256', 'read_bytes_each', 'storage_test_verified'):
            changed = copy.deepcopy(report)
            del changed[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                installer.validate_storage_report(changed, 'a'*64, 26226966016)
