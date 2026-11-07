"""The battery keeper's decisions against a fake sysfs: the window, the
forced descent from a full battery, the fallbacks."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEEPER = ROOT / "packages/tabs3-base/usr/libexec/tabs3-battery-keeper"
BEHAVIOURS = "auto inhibit-charge force-discharge"


def run_keeper(capacity, current, online=1, behaviours=BEHAVIOURS, high=None, low=None):
    with tempfile.TemporaryDirectory() as tmp:
        bat = pathlib.Path(tmp) / "battery"
        chg = pathlib.Path(tmp) / "charger"
        bat.mkdir()
        chg.mkdir()
        (bat / "capacity").write_text(f"{capacity}\n")
        (chg / "online").write_text(f"{online}\n")
        (chg / "charge_behaviour").write_text(
            " ".join(f"[{b}]" if b == current else b for b in behaviours.split()) + "\n")
        env = {"PATH": "/usr/bin:/bin", "TABS3_BATTERY_PSY": str(bat), "TABS3_CHARGER_PSY": str(chg)}
        if high is not None:
            env["TABS3_BATTERY_HIGH"] = str(high)
        if low is not None:
            env["TABS3_BATTERY_LOW"] = str(low)
        done = subprocess.run(["/bin/sh", str(KEEPER)], env=env, capture_output=True, text=True)
        written = (chg / "charge_behaviour").read_text().strip()
        return done.returncode, done.stdout.strip(), written if "[" not in written else current


class KeeperTests(unittest.TestCase):
    def test_full_battery_is_discharged_down_to_the_window(self):
        self.assertEqual(run_keeper(100, "inhibit-charge")[2], "force-discharge")
        self.assertEqual(run_keeper(83, "auto")[2], "force-discharge")

    def test_discharge_ends_at_the_high_mark(self):
        self.assertEqual(run_keeper(80, "force-discharge")[2], "inhibit-charge")
        self.assertEqual(run_keeper(79, "force-discharge")[2], "inhibit-charge")

    def test_just_above_the_high_mark_only_inhibits(self):
        self.assertEqual(run_keeper(82, "auto")[2], "inhibit-charge")
        code, out, written = run_keeper(81, "inhibit-charge")
        self.assertEqual((code, out, written), (0, "", "inhibit-charge"))

    def test_window_holds_and_charges_from_the_low_mark(self):
        self.assertEqual(run_keeper(70, "inhibit-charge")[2], "inhibit-charge")
        self.assertEqual(run_keeper(70, "auto")[2], "auto")
        self.assertEqual(run_keeper(65, "inhibit-charge")[2], "auto")
        self.assertEqual(run_keeper(80, "auto")[2], "inhibit-charge")

    def test_on_battery_nothing_is_held(self):
        self.assertEqual(run_keeper(100, "force-discharge", online=0)[2], "auto")
        self.assertEqual(run_keeper(90, "inhibit-charge", online=0)[2], "auto")

    def test_without_the_kernel_feature_a_full_battery_is_only_inhibited(self):
        self.assertEqual(run_keeper(100, "auto", behaviours="auto inhibit-charge")[2], "inhibit-charge")

    def test_charge_fully_setting_never_discharges(self):
        self.assertEqual(run_keeper(100, "inhibit-charge", high=100, low=100)[2], "inhibit-charge")

    def test_nonsense_window_falls_back_to_defaults(self):
        self.assertEqual(run_keeper(100, "inhibit-charge", high=10, low=90)[2], "force-discharge")
        self.assertEqual(run_keeper(70, "auto", high=10, low=90)[2], "auto")

    def test_change_is_logged(self):
        code, out, _ = run_keeper(100, "inhibit-charge")
        self.assertEqual(code, 0)
        self.assertEqual(out, "battery 100 %: charging force-discharge (was inhibit-charge)")

    def test_bad_configuration_cannot_break_arithmetic(self):
        for high in ('abc', '080', '999999999999999999999', '-1', '80.5'):
            code, _, written = run_keeper(100, 'auto', high=high)
            self.assertEqual((code, written), (0, 'force-discharge'))

    def test_invalid_capacity_is_not_used_for_charger_control(self):
        for capacity in ('', 'unavailable', -1, 101):
            code, _, written = run_keeper(capacity, 'auto')
            self.assertEqual((code, written), (1, 'auto'))


if __name__ == "__main__":
    unittest.main()
