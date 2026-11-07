import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('publication', Path(__file__).resolve().parents[1] / 'scripts/check-publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationChecks(unittest.TestCase):
    def test_credentials_rejected_without_echoing_value(self):
        token = b'ghp_' + b'A'*36
        results = publication.findings('example.txt', b'line one\n' + token)
        self.assertEqual(results, ['GitHub token at line 2'])
        self.assertNotIn(token.decode(), str(results))

    def test_private_artifact_and_key_rejected(self):
        self.assertTrue(publication.findings('private/backups/boot.img', b''))
        self.assertTrue(publication.findings('config/id_ed25519', b''))
        key = b'-----BEGIN ' + b'OPENSSH PRIVATE KEY-----'
        self.assertTrue(publication.findings('unexpected.txt', key))

    def test_public_documentation_and_screenshot_allowed(self):
        self.assertEqual(publication.findings('docs/accounts.md', b'Use private/id_ed25519.pub'), [])
        self.assertEqual(publication.findings('docs/images/silicon.png', b'PNG'), [])
