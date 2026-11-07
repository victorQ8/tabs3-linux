"""Exercise recovery result reporting without accessing any tablet storage."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RecoveryFsckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = pathlib.Path(cls.temporary.name)
        # Load the real helper functions without running its command dispatcher.
        source = (ROOT / "initramfs/tabs3-recovery").read_text()
        source, separator, _ = source.partition('\ncase "${1:-help}" in')
        if not separator:
            raise AssertionError("Recovery command dispatcher not found")
        source = source.replace(
            ". /usr/lib/tabs3/rootmap.sh",
            ". " + shlex.quote(str(ROOT / "initramfs/rootmap.sh")))
        cls.helper = directory / "check.sh"
        cls.helper.write_text(source + r'''
# Replace only the hardware access and checker; keep the real fsck wrapper.
mounted() { [ "$TEST_MOUNTED" = 1 ]; }
exported() { [ "$TEST_EXPORTED" = 1 ]; }
root_dev() {
    [ "$TEST_ROOT_FAILURE" = 0 ] || return 1
    printf '%s\n' mock-device
}
say() { printf '%s\n' "$*"; }
e2fsck() {
    printf '%s\n' "$*" > "$TEST_TRACE"
    return "$TEST_FSCK_STATUS"
}
fsck_root "$@"
''')
        program = directory / "message.c"
        program.write_text('''
#include <stdio.h>
#include <stdlib.h>
#include "fsck-result.h"
int main(int argc, char **argv) {
    if (argc != 2) return 1;
    puts(fsck_result_message(atoi(argv[1])));
    return 0;
}
''')
        cls.formatter = directory / "message"
        subprocess.run(["cc", "-Wall", "-Wextra", "-Werror",
                        "-I", str(ROOT / "recovery-ui"), str(program),
                        "-o", str(cls.formatter)], check=True)

    def check(self, status=0, *, mounted=False, exported=False,
              root_failure=False, repair=False):
        with tempfile.TemporaryDirectory() as directory:
            trace = pathlib.Path(directory) / "checker-arguments"
            env = dict(os.environ, TEST_FSCK_STATUS=str(status),
                       TEST_MOUNTED=str(int(mounted)),
                       TEST_EXPORTED=str(int(exported)),
                       TEST_ROOT_FAILURE=str(int(root_failure)),
                       TEST_TRACE=str(trace))
            args = ["/bin/sh", str(self.helper)] + (["-y"] if repair else [])
            result = subprocess.run(args, env=env, capture_output=True, text=True)
            invoked = trace.read_text().strip() if trace.exists() else None
        message = self.message(result.returncode)
        return result, invoked, message

    def message(self, status):
        return subprocess.check_output([str(self.formatter), str(status)], text=True).strip()

    def test_checker_status_reaches_the_ui(self):
        cases = {
            0: "no errors", 1: "errors corrected.", 2: "reboot required",
            3: "reboot required", 4: "errors remain", 5: "errors remain",
            6: "errors remain", 7: "errors remain", 8: "check failed",
            12: "check failed", 16: "check failed", 32: "check cancelled",
            36: "check cancelled", 128: "check failed",
            126: "check failed", 127: "check failed", 255: "check failed",
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                result, invoked, message = self.check(status)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(invoked, "-fn mock-device")
                self.assertIn(expected, message)
                if status:
                    self.assertNotIn("no errors", message)

    def test_repair_is_explicit_and_preserves_repaired_status(self):
        result, invoked, message = self.check(1, repair=True)
        self.assertEqual(invoked, "-fy mock-device")
        self.assertEqual(result.returncode, 1)
        self.assertIn("errors corrected", message)

    def test_preflight_refusals_are_not_reported_as_repairs(self):
        for condition in ("mounted", "exported", "root_failure"):
            with self.subTest(condition=condition):
                result, invoked, message = self.check(**{condition: True})
                self.assertEqual(result.returncode, 8, result.stderr)
                self.assertIsNone(invoked)
                self.assertIn("check failed", message)

    def test_signalled_process_is_not_reported_clean(self):
        self.assertIn("interrupted", self.message(-1))


if __name__ == "__main__":
    unittest.main()
