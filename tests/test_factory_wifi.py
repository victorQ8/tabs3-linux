"""Factory-address validation and preservation of existing IWD policy."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / 'packages/tabs3-base/usr/libexec/tabs3-wifi-address'


class FactoryWifiTests(unittest.TestCase):
    def test_reject_bad_efs_addresses(self):
        source = HELPER.read_text()
        function = source.split('valid_address() {', 1)[1].split('\n}\n', 1)[0]
        function = 'valid_address() {' + function + '\n}\n'
        for address, valid in [('84:38:38:12:34:56', True), ('02:00:00:00:00:01', True),
                               ('00:00:00:00:00:00', False), ('ff:ff:ff:ff:ff:ff', False),
                               ('01:00:5e:00:00:01', False), ('84:38:38:12:34', False),
                               ('84:38:38:12:34:56\nextra', False), ('$(false)', False)]:
            with self.subTest(address=address):
                result = subprocess.run(['sh', '-c', function + 'valid_address "$1"', 'sh', address])
                self.assertEqual(result.returncode == 0, valid)

    def test_iwd_preserves_other_settings_and_is_idempotent(self):
        source = HELPER.read_text().split("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            config = pathlib.Path(directory) / 'main.conf'
            original = ('[General]\nEnableNetworkConfiguration=false\n'
                        '[DriverQuirks]\nDefaultInterface=brcm*,rtw89\nForcePae=old_driver\n'
                        '[Network]\nNameResolvingService=systemd\n')
            config.write_text(original)
            source = source.replace("Path('/etc/iwd/main.conf')", f'Path({str(config)!r})')
            subprocess.run(['python3', '-c', source], check=True)
            changed = config.read_bytes()
            self.assertIn(b'DefaultInterface = brcm*,rtw89,ath10k_pci', changed)
            self.assertIn(b'ForcePae = old_driver', changed)
            self.assertIn(b'EnableNetworkConfiguration = false', changed)
            self.assertIn(b'NameResolvingService = systemd', changed)
            self.assertEqual(config.with_suffix('.conf.pre-tabs3-address').read_text(), original)
            subprocess.run(['python3', '-c', source], check=True)
            self.assertEqual(config.read_bytes(), changed)
            self.assertEqual(config.with_suffix('.conf.pre-tabs3-address').read_text(), original)


if __name__ == '__main__':
    unittest.main()
