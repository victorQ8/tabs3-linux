"""Battery labels must reflect the active charger policy, not available modes."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'packages/tabs3-dashboard/usr/libexec/tabs3_dashboard_power.py'
spec = importlib.util.spec_from_file_location('dashboard_power', SOURCE)
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)


class PowerTests(unittest.TestCase):
    def test_only_active_behaviour(self):
        self.assertEqual(power.charge_behaviour('[auto] inhibit-charge force-discharge'), 'auto')
        self.assertEqual(power.charge_behaviour('auto inhibit-charge [force-discharge]'), 'force-discharge')
        for text in ('', 'force-discharge', None):
            self.assertIsNone(power.charge_behaviour(text))

    def test_target_and_keeper_fallback(self):
        self.assertEqual(power.keeper_target('TABS3_BATTERY_HIGH=75'), 75)
        self.assertEqual(power.keeper_target('TABS3_BATTERY_HIGH="90" # custom'), 90)
        for config in ('TABS3_BATTERY_HIGH=101', 'TABS3_BATTERY_LOW=90', 'TABS3_BATTERY_LOW=10', ''):
            self.assertEqual(power.keeper_target(config), 80)

    def test_intentional_descent_and_rest(self):
        battery = {'charger': 1, 'status': 'Discharging', 'charge_behaviour': 'force-discharge', 'keeper_target': 75}
        self.assertEqual(power.battery_status(battery), 'Reducing to 75%')
        self.assertEqual(power.power_source(battery), 'External power connected')
        battery['charge_behaviour'] = 'inhibit-charge'
        self.assertEqual(power.battery_status(battery), 'Battery resting')

    def test_stale_policy_without_power_does_not_claim_descent(self):
        for online in (0, None):
            battery = {'charger': online, 'status': 'Discharging', 'charge_behaviour': 'force-discharge'}
            self.assertEqual(power.battery_status(battery), 'Discharging')
        self.assertEqual(power.power_source({'charger': 0}), 'On battery')
        self.assertEqual(power.power_source({}), 'Power unknown')

    def test_normal_and_missing_readings(self):
        self.assertEqual(power.battery_status({'charger': 1, 'status': 'Charging', 'charge_behaviour': 'auto'}), 'Charging')
        self.assertEqual(power.battery_status({}), 'Unknown')


if __name__ == '__main__':
    unittest.main()
