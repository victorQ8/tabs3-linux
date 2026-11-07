import contextlib
import importlib.util
import io
import pathlib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "inspector", pathlib.Path(__file__).resolve().parents[1] / "scripts/inspect-device.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class DeviceSelectionTests(unittest.TestCase):
    def invoke(self, listing, model="SM-T825"):
        calls = []

        def fake_run(*args):
            calls.append(args)
            if args == ("adb", "devices", "-l"):
                return listing
            if args[-2:] == ("getprop", "ro.product.model"):
                return model
            return "test-value"

        with patch.object(inspector, "run", side_effect=fake_run), patch("sys.argv", ["inspect-device"]):
            with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
                result = inspector.main()
        return result, calls, output.getvalue()

    def test_unrelated_phone_receives_no_shell_commands(self):
        result, calls, _ = self.invoke("List of devices attached\nPHONE device model:SM_S926B device:e2s\n")
        self.assertEqual(result, 2)
        self.assertEqual(calls, [("adb", "devices", "-l")])

    def test_unauthorized_tablet_is_not_inspected(self):
        result, calls, _ = self.invoke("List of devices attached\nTABLET unauthorized\n")
        self.assertEqual(result, 2)
        self.assertEqual(len(calls), 1)

    def test_multiple_tablets_are_ambiguous(self):
        result, calls, _ = self.invoke("List of devices attached\nONE device model:SM_T825\nTWO device model:SM_T825\n")
        self.assertEqual(result, 2)
        self.assertEqual(len(calls), 1)

    def test_only_tablet_is_inspected_when_phone_also_connected(self):
        result, calls, output = self.invoke("List of devices attached\nPHONE device model:SM_S926B device:e2s\nTABLET device model:SM_T825 device:gts3llte\n")
        self.assertEqual(result, 0)
        self.assertTrue(all(call[1:3] == ("-s", "TABLET") for call in calls[1:]))
        self.assertNotIn("TABLET", output)
        self.assertIn('"ro.product.model": "SM-T825"', output)

    def test_wifi_model_is_not_accepted_as_lte(self):
        result, calls, _ = self.invoke("List of devices attached\nTABLET device model:SM_T820 device:gts3lwifi\n")
        self.assertEqual(result, 2)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
