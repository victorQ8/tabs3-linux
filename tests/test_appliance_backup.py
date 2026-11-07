"""Restore verification must inspect data, not merely list a tar archive."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('backup', ROOT / 'tools/server/backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def test_free_space_reserves_uncompressed_data_and_headroom(self):
        metadata = dict(estimated_source_bytes=1000, partitions={'boot': {'bytes': 200}})
        with self.assertRaisesRegex(RuntimeError, 'Insufficient backup space'):
            backup.check_space(metadata, 1200 + 1024 ** 3 - 1)
        backup.check_space(metadata, 1200 + 1024 ** 3)

    def archive(self, directory):
        path = directory / 'backup.tar.gz'
        with tarfile.open(path, 'w:gz') as out:
            for name, data in [('etc/fstab', b'root configuration'),
                               ('../never-extract-me', b'escape attempt')]:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                out.addfile(member, io.BytesIO(data))
        return path

    def test_restore_and_hash_comparison_without_path_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.archive(root)
            result = backup.verify_archive(path, {'etc/fstab': hashlib.sha256(b'root configuration').hexdigest()})
            self.assertEqual(result['configuration_files_restored'], 1)
            self.assertEqual(result['files_read'], 2)
            self.assertEqual(list(root.iterdir()), [path])

    def test_wrong_hash_or_missing_file_fails_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.archive(Path(directory))
            for expected in ({'etc/fstab': 'bad-hash'}, {'etc/absent': 'bad-hash'}):
                with self.assertRaisesRegex(RuntimeError, 'does not match'):
                    backup.verify_archive(path, expected)


if __name__ == '__main__':
    unittest.main()
