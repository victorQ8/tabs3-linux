"""Loss of telemetry, resets and bounded storage must not look like success."""
import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('server_health', str(
    ROOT / 'packages/tabs3-base/usr/libexec/tabs3-server-health'))
spec = importlib.util.spec_from_loader(loader.name, loader)
health = importlib.util.module_from_spec(spec)
loader.exec_module(health)


def sample():
    return {'boot_id': 'boot-a', 'uptime_s': 10, 'root_read_only': False,
            'battery': {'capacity': 90, 'temp': 280, 'current_now': 0},
            'charger': {'online': 1}, 'charger_health': 'Good',
            'temperatures_mc': {'cpu0-thermal': 40000},
            'memory_bytes': {'MemTotal': 1000, 'MemAvailable': 800},
            'root_bytes': {'total': 1000, 'available': 800},
            'network': {'wlan0': {'operstate': 'up'}}}


class ServerHealthTests(unittest.TestCase):
    def test_missing_measurements_do_not_appear_healthy(self):
        row = sample()
        row['battery']['temp'] = None
        row['temperatures_mc'] = {'cpu0-thermal': None}
        self.assertEqual(set(health.assess(row)['notices']),
                         {'battery_read_failed', 'cpu_temperature_unavailable'})

    def test_sustained_drain_and_reboot_reset(self):
        first = sample()
        first['battery']['current_now'] = -200000
        health.assess(first)
        later = first
        for uptime in range(70, 971, 60):
            previous = later
            later = copy.deepcopy(previous)
            later['uptime_s'] = uptime
            health.assess(later, previous)
        self.assertIn('battery_draining_on_external_power', later['notices'])
        reboot = copy.deepcopy(later)
        reboot.update(boot_id='boot-b', uptime_s=20)
        health.assess(reboot, later)
        self.assertTrue(reboot['new_boot_since_previous_sample'])
        self.assertNotIn('battery_draining_on_external_power', reboot['notices'])
        self.assertEqual(reboot['drain_started_uptime_s'], 20)

    def test_gap_or_bad_previous_timestamp_cannot_prove_sustained_drain(self):
        first = sample()
        first['battery']['current_now'] = -200000
        health.assess(first)
        for last_time in (10, 2010, None, 'invalid', float('nan')):
            with self.subTest(last_time=last_time):
                previous = dict(first, uptime_s=last_time)
                later = copy.deepcopy(first)
                later['uptime_s'] = 2000
                health.assess(later, previous)
                self.assertIn('telemetry_gap', later['notices'])
                self.assertNotIn('battery_draining_on_external_power', later['notices'])
                self.assertEqual(later['drain_started_uptime_s'], 2000)

    def test_read_only_root_is_reported(self):
        row = dict(sample(), root_read_only=True)
        self.assertIn('root_read_only', health.assess(row)['notices'])

    def test_host_mount_and_superblock_read_only_states(self):
        for mount, superblock, expected in (('rw', 'rw', False), ('ro', 'rw', True),
                                             ('rw', 'ro', True), ('ro', 'ro', True)):
            with self.subTest(mount=mount, superblock=superblock):
                line = f'36 25 253:0 / / {mount},noatime shared:1 - ext4 /dev/dm-0 {superblock},errors=remount-ro'
                self.assertIs(health.root_read_only(line), expected)
        for text in (None, '', 'malformed',
                     '36 25 253:0 / / rw - ext4 /dev/dm-0',
                     '36 25 253:0 / / rw,ro - ext4 /dev/dm-0 rw',
                     '36 25 253:0 / / rw - ext4 /dev/dm-0 unknown',
                     '36 25 253:0 / /mnt rw - ext4 /dev/dm-0 rw'):
            self.assertIsNone(health.root_read_only(text))
        self.assertIn('root_mount_read_failed', health.assess(dict(sample(), root_read_only=None))['notices'])

    def test_collection_uses_pid1_mount_view_inside_read_only_sandbox(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ('sys/firmware/devicetree/base/compatible', 'samsung,gts3llte\0'),
                ('proc/1/mountinfo', '36 25 253:0 / / rw,noatime - ext4 /dev/dm-0 rw'),
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)
            usage = SimpleNamespace(f_flag=health.os.ST_RDONLY, f_blocks=1000,
                                    f_bavail=500, f_frsize=4096)
            with patch.object(health.os, 'statvfs', return_value=usage):
                self.assertIs(health.collect(root)['root_read_only'], False)
            (root/'proc/1/mountinfo').unlink()
            self.assertIsNone(health.collect(root)['root_read_only'])

    def test_recovery_interrupts_drain_interval(self):
        first = sample()
        first['battery']['current_now'] = -200000
        health.assess(first)
        recovered = sample()
        recovered['uptime_s'] = 1000
        health.assess(recovered, first)
        self.assertIsNone(recovered['drain_started_uptime_s'])
        self.assertNotIn('battery_draining_on_external_power', recovered['notices'])

    def test_keepers_forced_discharge_is_not_a_drain(self):
        first = sample()
        first['battery']['current_now'] = -500000
        first['charger_behaviour'] = 'force-discharge'
        health.assess(first)
        later = copy.deepcopy(first)
        later['uptime_s'] = 2000
        health.assess(later, first)
        self.assertIsNone(later['drain_started_uptime_s'])
        self.assertNotIn('battery_draining_on_external_power', later['notices'])

    def test_retention_does_not_delete_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keep = root / 'backup.json'
            keep.write_text('keep')
            for day in range(1, 11):
                health.save({'recorded_utc': f'2026-10-{day:02d}T12:00:00Z'}, root)
            self.assertEqual(len(list(root.glob('????-??-??.jsonl'))), 7)
            self.assertEqual(keep.read_text(), 'keep')
            self.assertEqual(json.loads((root / 'latest.json').read_text())['recorded_utc'],
                             '2026-10-10T12:00:00Z')

    def test_reject_unrelated_device(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'SM-T825'):
                health.collect(Path(directory))

    def test_thermal_and_capacity_notices(self):
        row = sample()
        row['battery'].update(capacity=15, temp=390)
        row['temperatures_mc']['cpu0-thermal'] = 90000
        self.assertEqual(set(health.assess(row)['notices']),
                         {'battery_low', 'battery_warm', 'cpu_hot'})


if __name__ == '__main__':
    unittest.main()
