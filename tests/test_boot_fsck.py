"""Boot must not mount a root that e2fsck cannot safely clear for use."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootFsckTests(unittest.TestCase):
    def test_every_checker_result_preserves_the_recovery_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = (ROOT / 'initramfs/rootcheck.sh').read_text()
            source = source.replace('/run/log/root-fsck.log', shlex.quote(str(work / 'log')))
            source = source.replace('/run/tabs3-root-fsck.status', shlex.quote(str(work / 'status')))
            script = work / 'check.sh'
            script.write_text(source + '''
e2fsck() { echo "$*"; return "$TEST_STATUS"; }
check_root_filesystem /dev/mock
''')
            for code in (0, 1, 2, 3, 4, 5, 6, 8, 12, 16, 32, 128, 127, 255):
                with self.subTest(code=code):
                    result = subprocess.run(['sh', str(script)], capture_output=True, text=True,
                                            env=dict(os.environ, TEST_STATUS=str(code)))
                    self.assertEqual(result.returncode, 0 if code in (0, 1) else 1)
                    self.assertEqual((work / 'status').read_text().strip(), str(code))
                    self.assertEqual((work / 'log').read_text().strip(), '-p /dev/mock')


if __name__ == '__main__':
    unittest.main()
