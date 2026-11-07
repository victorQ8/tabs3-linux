"""Exercise shutdown decisions; never issue a real poweroff."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('power_guard', str(
    ROOT / 'packages/tabs3-base/usr/libexec/tabs3-power-guard'))
spec = importlib.util.spec_from_loader(loader.name, loader)
guard = importlib.util.module_from_spec(spec)
loader.exec_module(guard)


def sample(**changes):
    return dict(dict(boot_id='boot-a', uptime_s=100, capacity=5,
                     voltage_uv=3500000, current_ua=-200000, charger_online=0), **changes)


class PowerGuardTests(unittest.TestCase):
    def timeline(self, samples):
        result = None
        for row in samples:
            result = guard.decide(row, result)
        return result

    def test_low_battery_requires_full_confirmed_minute(self):
        rows = [sample(uptime_s=t) for t in range(100, 161, 15)]
        self.assertEqual(self.timeline(rows[:-1])['action'], 'none')
        self.assertEqual(self.timeline(rows)['action'], 'poweroff')

    def test_critical_battery_confirms_for_thirty_seconds(self):
        rows = [sample(uptime_s=t, capacity=2) for t in (100, 115, 130)]
        self.assertEqual(self.timeline(rows[:-1])['action'], 'none')
        self.assertEqual(self.timeline(rows)['action'], 'poweroff')

    def test_online_but_inadequate_supply_still_protects_the_battery(self):
        rows = [sample(uptime_s=t, charger_online=1) for t in range(100, 161, 15)]
        self.assertEqual(self.timeline(rows)['action'], 'poweroff')

    def test_charging_at_one_percent_may_boot_and_recover(self):
        rows = [sample(uptime_s=t, capacity=1, charger_online=1, current_ua=100000)
                for t in range(100, 301, 15)]
        result = self.timeline(rows)
        self.assertEqual(result['action'], 'none')
        self.assertIsNone(result['low_since_s'])

    def test_replug_or_capacity_recovery_cancels_confirmation(self):
        previous = self.timeline([sample(uptime_s=t) for t in (100, 115, 130, 145)])
        for changes in ({'charger_online': 1, 'current_ua': 100000}, {'capacity': 6}):
            reset = guard.decide(sample(uptime_s=160, **changes), previous)
            next_row = guard.decide(sample(uptime_s=175), reset)
            self.assertEqual(next_row['action'], 'none')
            self.assertEqual(next_row['low_since_s'], 175)

    def test_gap_reboot_and_clock_regression_restart_confirmation(self):
        previous = self.timeline([sample(uptime_s=t) for t in (100, 115, 130, 145)])
        for changes in ({'uptime_s': 210}, {'boot_id': 'boot-b', 'uptime_s': 160},
                        {'uptime_s': 10}):
            row = sample(**changes)
            result = guard.decide(row, previous)
            self.assertEqual(result['action'], 'none')
            self.assertEqual(result['low_since_s'], row['uptime_s'])

    def test_bad_telemetry_never_requests_shutdown(self):
        for field, value in [('capacity', None), ('capacity', -1), ('capacity', 101),
                             ('voltage_uv', None), ('voltage_uv', 999),
                             ('boot_id', None), ('uptime_s', float('nan'))]:
            with self.subTest(field=field, value=value):
                self.assertEqual(guard.decide(sample(**{field: value}))['action'], 'none')
        row = sample(charger_online=None, current_ua=None)
        self.assertEqual(guard.decide(row)['reason'], 'drain_telemetry_unavailable')
        for current in (-2147483648, 2147483647, None, 'bad'):
            row = sample(charger_online=1, current_ua=current)
            self.assertEqual(guard.decide(row)['reason'], 'drain_telemetry_unavailable')

    def test_bad_state_restarts_confirmation(self):
        for previous in ([], 'bad', {'boot_id': 'boot-a', 'uptime_s': 'bad'},
                         {'boot_id': 'boot-a', 'uptime_s': 90, 'low_since_s': 'bad'}):
            self.assertEqual(guard.decide(sample(), previous)['action'], 'none')

    def test_wrong_device_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'SM-T825'):
                guard.collect(Path(directory))


if __name__ == '__main__':
    unittest.main()
