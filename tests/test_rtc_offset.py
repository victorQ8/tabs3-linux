import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'packages/tabs3-base/usr/libexec/tabs3-rtc-offset'
loader = importlib.machinery.SourceFileLoader('rtc_offset', str(PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
rtc = importlib.util.module_from_spec(spec)
loader.exec_module(rtc)


class RTCOffsetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'offset'
        self.counter = Path(self.tmp.name) / 'counter'
        self.counter.write_text('1200\n')
        for name, value in [('STATE', self.state), ('RTC', self.counter)]:
            p = patch.object(rtc, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_unsynchronized_first_boot_does_not_create_offset(self):
        result = subprocess.CompletedProcess([], 0, 'no\n', '')
        with patch.object(rtc.subprocess, 'run', return_value=result):
            rtc.save()
        self.assertFalse(self.state.exists())

    def test_unsynchronized_clock_preserves_existing_record(self):
        self.state.write_text('previous record')
        result = subprocess.CompletedProcess([], 0, 'no\n', '')
        with patch.object(rtc.subprocess, 'run', return_value=result):
            rtc.save()
        self.assertEqual(self.state.read_text(), 'previous record')

    def test_saved_offset_advances_offline_boot_and_keeps_permissions(self):
        synced = subprocess.CompletedProcess([], 0, 'yes\n', '')
        with patch.object(rtc.subprocess, 'run', return_value=synced), \
             patch.object(rtc.time, 'time', return_value=1800000000):
            rtc.save()
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.counter.write_text('1800\n')
        with patch.object(rtc.subprocess, 'run') as run, \
             patch.object(rtc.time, 'time', return_value=1800000000):
            rtc.restore()
        self.assertEqual(run.call_args.args[0], ['date', '-s', '@1800000600'])

    def test_older_estimate_never_moves_clock_back(self):
        record = {'version': 1, 'utc': 1800000000, 'rtc': 1200}
        self.assertIsNone(rtc.restore_target(record, 1800, 1800001000))

    def test_battery_disconnect_invalidates_old_offset(self):
        record = {'version': 1, 'utc': 1800000000, 'rtc': 1200}
        with self.assertRaisesRegex(ValueError, 'went backwards'):
            rtc.restore_target(record, 10, 1800000000)

    def test_malformed_and_legacy_state_cannot_set_time(self):
        for data in ('---', '1777777777', '{"version":1,"rtc":true,"utc":1800000000}'):
            with self.subTest(data=data):
                self.state.write_text(data)
                with patch.object(rtc.subprocess, 'run') as run:
                    rtc.restore()
                run.assert_not_called()
