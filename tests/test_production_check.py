"""A long uptime is not proof of uninterrupted observation."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('production', str(
    ROOT / 'packages/tabs3-base/usr/bin/tabs3-production-check'))
spec = importlib.util.spec_from_loader(loader.name, loader)
production = importlib.util.module_from_spec(spec)
loader.exec_module(production)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.baseline = dict(boot_id='one', uptime_s=100)
        self.current = dict(boot_id='one', uptime_s=3700)
        self.rows = [dict(boot_id='one', uptime_s=t, notices=[]) for t in range(100, 3701, 60)]

    def test_continuous_interval_passes(self):
        self.assertTrue(production.soak(self.rows, self.baseline, self.current, 1)['passed'])

    def test_hours_alone_without_logs_do_not_pass(self):
        self.assertFalse(production.soak([], self.baseline, self.current, 1)['passed'])
        self.assertFalse(production.soak(self.rows[10:], self.baseline, self.current, 1)['passed'])
        self.assertFalse(production.soak(self.rows[:-10], self.baseline, self.current, 1)['passed'])

    def test_gap_reboot_notice_and_short_run_fail(self):
        for rows, current, hours in (
                (self.rows[:10] + self.rows[20:], self.current, 1),
                (self.rows, dict(self.current, boot_id='two'), 1),
                (self.rows + [dict(self.rows[-1], notices=['root_read_only'])], self.current, 1),
                (self.rows, self.current, 72)):
            self.assertFalse(production.soak(rows, self.baseline, current, hours)['passed'])

    def test_kernel_fault_match_does_not_mistake_debug_or_ramoops_for_a_crash(self):
        for line in ('printk: debug: enabled', 'ramoops: using 0x200000', 'GPU initialized'):
            self.assertIsNone(production.FAULT.search(line))
        for line in ('BUG: scheduling while atomic', 'Oops: 000000', 'q6asm: CMD 10bcd timeout',
                     'msm: GPU fault', 'EXT4-fs error (device dm-0)'):
            self.assertIsNotNone(production.FAULT.search(line))

    def test_recovered_video_and_remote_firmware_crashes_still_fail_qualification(self):
        for line in (
                'qcom-venus c00000.video-codec: SFR message from FW: VIDEO.VE.4.4 Err_Fatal - vbuffer.c:1219:',
                'qcom-venus c00000.video-codec: system error has occurred (recovered)',
                'qcom-venus-encoder c00000.video-codec:video-encoder: enc: event session error 0',
                'remoteproc remoteproc2: crash detected in adsp: type fatal error',
                'qcom_q6v5_pas 9300000.remoteproc: fatal error received'):
            with self.subTest(line=line):
                self.assertIsNotNone(production.FAULT.search(line))
        for line in ('qcom-venus c00000.video-codec: video decoder registered',
                     'remoteproc remoteproc2: remote processor adsp is now up',
                     'qcom-venus c00000.video-codec: F/W version: VIDEO.VE.4.4'):
            self.assertIsNone(production.FAULT.search(line))


if __name__ == '__main__':
    unittest.main()
