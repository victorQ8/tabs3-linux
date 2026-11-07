"""Credential migration checks using synthetic profiles only (python3-gi)."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import sys

# The script is loaded from the package tree; never add build artifacts there.
sys.dont_write_bytecode = True

SCRIPT = Path(os.environ.get('TABS3_WIFI_IMPORTER',
    Path(__file__).resolve().parents[1] /
    'packages/tabs3-desktop/usr/libexec/tabs3-import-iwd'))
loader = importlib.machinery.SourceFileLoader('tabs3_import_iwd', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class WifiMigrationTests(unittest.TestCase):
    def test_secrets_ssid_permissions_and_repeat(self):
        with tempfile.TemporaryDirectory() as root:
            src, dst = Path(root) / 'iwd', Path(root) / 'nm'
            src.mkdir()
            # Encoded SSID and a passphrase containing characters INI parsers
            # can mistake for interpolation, comments or escapes.
            old = module.GLib.KeyFile()
            secret = 'test%#;\\password'
            old.set_string('Security', 'Passphrase', secret)
            old.set_string('Settings', 'AutoConnect', 'false')
            profile = src / '=546573743b.psk'
            profile.write_text(old.to_data()[0])
            original = profile.read_bytes()
            self.assertEqual(module.migrate(src, dst), 1)
            target, = dst.glob('*.nmconnection')
            new = module.keyfile(target)
            self.assertEqual(new.get_string('wifi-security', 'psk'), secret)
            self.assertEqual(new.get_integer_list('wifi', 'ssid'), list(b'Test;'))
            self.assertFalse(new.get_boolean('connection', 'autoconnect'))
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            saved = target.read_bytes()
            self.assertEqual(module.migrate(src, dst), 0)
            self.assertEqual(target.read_bytes(), saved)
            self.assertEqual(profile.read_bytes(), original)

    def test_existing_profile_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            src, dst = Path(root) / 'iwd', Path(root) / 'nm'
            src.mkdir(); dst.mkdir()
            (src / 'Test.psk').write_text('[Security]\nPreSharedKey=' + '12' * 32 + '\n')
            target = dst / 'existing.nmconnection'
            original = '[wifi]\nssid=Test\n[wifi-security]\npsk=existing-password\n'
            target.write_text(original)
            self.assertEqual(module.migrate(src, dst), 0)
            self.assertEqual(target.read_text(), original)


if __name__ == '__main__':
    unittest.main()
