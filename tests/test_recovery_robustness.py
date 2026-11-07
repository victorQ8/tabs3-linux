"""Recovery helper robustness: image validation before flashing, the operation
lock, USB rollback in the export worker, the backup superblock, read-only
mounts without journal replay and leaving with an export active. The real
helper functions run with the hardware access mocked; no tablet is touched."""
import hashlib
import os
import pathlib
import shlex
import struct
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = 4096
RESERVED = 4 * 1024 * 1024

MOCKS = r'''
part() { case "$1" in boot) printf '%s\n' "$TEST_BOOT_DEV" ;; *) die "no $1 partition" ;; esac; }
sectors() { echo $((TEST_PART_BYTES / 512)); }
exported() { [ "${TEST_EXPORTED:-0}" = 1 ]; }
say() { printf '%s\n' "$*"; }
sync() { :; }
'''


def helper_source():
    source = (ROOT / "initramfs/tabs3-recovery").read_text()
    functions, separator, dispatcher = source.partition('\ncase "${1:-help}" in')
    if not separator:
        raise AssertionError("Recovery command dispatcher not found")
    functions = functions.replace(
        ". /usr/lib/tabs3/rootmap.sh",
        ". " + shlex.quote(str(ROOT / "initramfs/rootmap.sh")))
    return functions, separator + dispatcher


def boot_image(kernel, ramdisk, cmdline, page=PAGE):
    """A v0 Android boot image with the id our packer writes."""
    header = bytearray(1632)
    header[:8] = b'ANDROID!'
    struct.pack_into('<10I', header, 8, len(kernel), 0x80080000, len(ramdisk), 0x82000000,
                     0, 0, 0x80000100, page, 0, 0)
    header[64:64 + len(cmdline)] = cmdline.encode()
    digest = hashlib.sha1()
    for payload in (kernel, ramdisk, b''):
        digest.update(payload)
        digest.update(struct.pack('<I', len(payload)))
    header[576:596] = digest.digest()

    def padded(data):
        return data + bytes((-len(data)) % page)
    return padded(bytes(header)) + padded(kernel) + padded(ramdisk)


def combined_image(cmdline='console=tty0 tabs3.mode=installed tabs3.root_uuid=x'):
    lk = boot_image(b'\x55' * 3000, b'', 'lk2nd').ljust(RESERVED, b'\0')
    return lk + boot_image(bytes(range(256)) * 40, b'\xaa' * 5000, cmdline)


class RecoveryHelperHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.dir = pathlib.Path(cls.temporary.name)
        functions, dispatcher = helper_source()
        # The full helper with mocked hardware: the dispatcher takes the lock.
        cls.full = cls.dir / "full.sh"
        cls.full.write_text(functions + MOCKS + dispatcher)
        cls.functions = functions

    def script(self, name, tail):
        path = self.dir / name
        path.write_text(self.functions + tail)
        return path

    def run_helper(self, path, *args, env=None, lock=None):
        environment = dict(os.environ, TABS3_RECOVERY_LOCK=str(lock or self.dir / "no-lock"))
        environment.update(env or {})
        return subprocess.run(["/bin/sh", str(path)] + list(args), env=environment,
                              capture_output=True, text=True)


class FlashValidationTests(RecoveryHelperHarness):
    def flash(self, image, exported=False, lock=None):
        with tempfile.TemporaryDirectory() as directory:
            d = pathlib.Path(directory)
            (d / "boot.img").write_bytes(image)
            dev = d / "boot-partition"
            dev.write_bytes(bytes(1024))
            result = self.run_helper(self.full, "flash-boot", str(d / "boot.img"), lock=lock,
                                     env={"TEST_BOOT_DEV": str(dev), "TEST_PART_BYTES": str(79691776),
                                          "TEST_EXPORTED": str(int(exported))})
            written = dev.read_bytes()
        return result, written

    def test_magics_alone_are_rejected(self):
        # Codex's reproduction: two ANDROID! signatures and zero padding.
        image = bytearray(RESERVED + 8192)
        image[:8] = b'ANDROID!'
        image[RESERVED:RESERVED + 8] = b'ANDROID!'
        result, written = self.flash(bytes(image))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("no valid lk2nd boot image", result.stderr)
        self.assertEqual(written, bytes(1024), "nothing may be written")

    def test_generated_image_is_written_and_verified(self):
        image = combined_image()
        result, written = self.flash(image)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Image checked: kernel 10240 bytes, initramfs 5000 bytes, tabs3.mode=installed",
                      result.stdout)
        self.assertIn("written and verified", result.stdout)
        self.assertEqual(written, image)

    def test_truncated_image_is_rejected(self):
        image = combined_image()
        result, written = self.flash(image[:-3000])
        self.assertEqual(result.returncode, 1)
        self.assertIn("no valid Linux boot image at 4 MiB", result.stderr)
        self.assertEqual(written, bytes(1024))

    def test_corrupt_payload_is_rejected(self):
        image = bytearray(combined_image())
        image[RESERVED + PAGE + 100] ^= 0xff
        result, written = self.flash(bytes(image))
        self.assertEqual(result.returncode, 1)
        self.assertIn("id checksum mismatch", result.stderr)
        self.assertEqual(written, bytes(1024))

    def test_recovery_image_is_refused(self):
        result, written = self.flash(combined_image('console=tty0 tabs3.mode=recovery'))
        self.assertEqual(result.returncode, 1)
        self.assertIn("recovery image", result.stderr)
        self.assertEqual(written, bytes(1024))

    def test_refused_while_exported(self):
        result, written = self.flash(combined_image(), exported=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("stop the USB export first", result.stderr)
        self.assertEqual(written, bytes(1024))

    def test_lock_held_by_a_live_process_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = pathlib.Path(directory) / "lock"
            lock.mkdir()
            (lock / "pid").write_text(f"{os.getpid()}\n")
            result, written = self.flash(combined_image(), lock=lock)
            self.assertEqual(result.returncode, 1)
            self.assertIn("another operation is running", result.stderr)
            self.assertEqual(written, bytes(1024))
            self.assertTrue(lock.is_dir(), "the other operation's lock stays")

    def test_stale_lock_is_reclaimed_and_released(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = pathlib.Path(directory) / "lock"
            lock.mkdir()
            dead = subprocess.run(["/bin/sh", "-c", "echo $$"], capture_output=True, text=True).stdout.strip()
            (lock / "pid").write_text(dead + "\n")
            result, written = self.flash(combined_image(), lock=lock)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(written, combined_image())
            self.assertFalse(lock.exists(), "the lock is released on exit")


class ExportWorkerTests(RecoveryHelperHarness):
    def run_worker(self, mode, break_file):
        with tempfile.TemporaryDirectory() as directory:
            g = pathlib.Path(directory) / "gadget"
            (g / "configs/c.1").mkdir(parents=True)
            (g / "UDC").write_text("fakeudc\n")
            lun = g / "functions/mass_storage.0/lun.0"
            lun.mkdir(parents=True)
            (lun / "ro").write_text("0\n")
            if break_file:
                (lun / "file").mkdir()
            else:
                (lun / "file").write_text("\n")
            lock = pathlib.Path(directory) / "lock"
            lock.mkdir()
            script = self.script("worker.sh", f'''
g={shlex.quote(str(g))}
lun=$g/functions/mass_storage.0
say() {{ printf '%s\\n' "$*"; }}
sleep() {{ :; }}
storage_apply "$@"
''')
            result = self.run_helper(script, mode, lock=lock)
            return result, (g / "UDC").read_text(), lock.exists(), (g / "configs/c.1/mass_storage.0").exists()

    def test_failure_after_disconnect_rebinds_the_controller(self):
        result, udc, locked, linked = self.run_worker("ro", break_file=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(udc, "fakeudc\n", "USB must come back after a failed export")
        self.assertFalse(locked, "the lock is released")
        self.assertFalse(linked)

    def test_export_succeeds_and_rebinds(self):
        result, udc, locked, linked = self.run_worker("ro", break_file=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(udc, "fakeudc\n")
        self.assertFalse(locked)
        self.assertTrue(linked)


class StorageSafetyTests(RecoveryHelperHarness):
    def test_fastboot_available_in_root_failure_rescue_but_not_normal_debian(self):
        for command_line_recovery, rescue_marker, allowed in ((False, False, False),
                                                             (False, True, True),
                                                             (True, False, True)):
            with self.subTest(cmdline=command_line_recovery, marker=rescue_marker), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                marker = root / 'rescue'
                if rescue_marker:
                    marker.touch()
                source = self.functions.replace('/run/tabs3-recovery-mode', str(marker))
                source = source.replace('. /usr/lib/tabs3/fastboot-request.sh', ':')
                source = source.replace('/usr/sbin/tabs3-reboot-recovery', 'fake_reboot')
                path = root / 'test.sh'
                path.write_text(source + '''
grep() { [ "$TEST_RECOVERY_CMDLINE" = 1 ]; }
exported() { false; }
mounted() { false; }
tabs3_fastboot_request() { echo "request:$1"; }
sync() { :; }
say() { :; }
fake_reboot() { exit 0; }
enter_fastboot
''')
                result = self.run_helper(path, env={'TEST_RECOVERY_CMDLINE': str(int(command_line_recovery))})
                self.assertEqual(result.returncode, 0 if allowed else 1)
                self.assertEqual('request:arm' in result.stdout, allowed)

    def test_backup_superblock_arguments(self):
        script = self.script("sb.sh", '''
dumpe2fs() { case "$*" in *superblock=32768*) echo 'Block count: 10' ;; *) return 1 ;; esac; }
backup_superblock_args /dev/mock
''')
        result = self.run_helper(script)
        self.assertEqual(result.stdout.strip(), "-b 32768 -B 4096")

    def test_healthy_superblock_needs_no_arguments(self):
        script = self.script("sb-ok.sh", '''
dumpe2fs() { echo 'Block count: 10'; }
backup_superblock_args /dev/mock
''')
        self.assertEqual(self.run_helper(script).stdout.strip(), "")

    def test_read_only_mount_does_not_replay_the_journal(self):
        script = self.script("mount.sh", '''
mnt=$(mktemp -d)
mounted() { false; }
exported() { false; }
root_dev() { echo mock-dev; }
fs_field() { echo clean; }
say() { :; }
mount() { printf '%s\\n' "$*"; }
mount_root "$@"
''')
        self.assertIn("-o ro,noload mock-dev", self.run_helper(script).stdout)
        self.assertIn("-o rw mock-dev", self.run_helper(script, "rw").stdout)

    def test_leaving_stops_an_active_export_first(self):
        script = self.script("leave.sh", '''
exported() { true; }
mounted() { false; }
storage_apply() { printf 'storage_apply %s\\n' "$*"; }
clear_recovery_flag() { echo clear; }
reboot() { echo "reboot $*"; }
sync() { :; }
say() { :; }
leave Rebooting
''')
        self.assertEqual(self.run_helper(script).stdout.split("\n")[:3],
                         ["storage_apply off", "clear", "reboot -f"])


if __name__ == "__main__":
    unittest.main()
