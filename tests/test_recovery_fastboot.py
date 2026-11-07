"""Exercise the actual bootloader/request code against simulated storage and time."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('recovery_fastboot', ROOT / 'scripts/pack-recovery-fastboot.py')
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


class RecoveryRequestTests(unittest.TestCase):
    def run_request(self, directory, operation):
        path = Path(directory)
        source = (ROOT / 'initramfs/fastboot-request.sh').read_text()
        source = source.replace('/run/tabs3-fastboot', str(path / 'tabs3-fastboot'))
        source += '\ntabs3_fastboot_device() { echo ' + shlex.quote(str(path / 'partition')) + '; }\n'
        source += 'tabs3_fastboot_request "$1"\n'
        script = path / 'helper.sh'
        script.write_text(source)
        return subprocess.run(['sh', str(script), operation], capture_output=True, text=True)

    def fixture(self, directory, cap=pack.CAPABILITY, request=bytes(512)):
        data = bytearray(b'K' * pack.CAP_OFFSET + bytes(8192) + b'LINUX-UNCHANGED')
        data[pack.CAP_OFFSET:pack.CAP_OFFSET+512] = cap
        data[pack.REQUEST_OFFSET:pack.REQUEST_OFFSET+512] = request
        file = Path(directory) / 'partition'
        file.write_bytes(data)
        return file, bytes(data)

    def test_arm_cancel_only_change_the_request_sector(self):
        with tempfile.TemporaryDirectory() as directory:
            file, original = self.fixture(directory)
            result = self.run_request(directory, 'arm')
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = bytearray(original)
            expected[pack.REQUEST_OFFSET:pack.REQUEST_OFFSET+512] = pack.REQUEST
            self.assertEqual(file.read_bytes(), bytes(expected))
            self.assertEqual(self.run_request(directory, 'status').stdout.strip(), 'armed')
            self.assertEqual(self.run_request(directory, 'cancel').returncode, 0)
            self.assertEqual(file.read_bytes(), original)
            self.assertEqual(self.run_request(directory, 'status').stdout.strip(), 'clear')

    def test_old_recovery_and_unknown_request_are_never_written(self):
        for changes in ({'cap': bytes(512)}, {'request': b'?' * 512},
                        {'cap': pack.CAPABILITY[:-1] + b'?' }):
            with self.subTest(changes=list(changes)), tempfile.TemporaryDirectory() as directory:
                file, original = self.fixture(directory, **changes)
                result = self.run_request(directory, 'arm')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(file.read_bytes(), original)

    def test_concurrent_request_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            file, original = self.fixture(directory)
            (Path(directory) / 'tabs3-fastboot.lock').mkdir()
            self.assertNotEqual(self.run_request(directory, 'arm').returncode, 0)
            self.assertEqual(file.read_bytes(), original)


class RecoveryBootloaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        (root / 'kernel').mkdir()
        stubs = {
            'fastboot.h': '''static void fastboot_publish(const char *n, const char *v) { (void)n; (void)v; }
#define FASTBOOT_INIT(f) static void (*const init_hook)(void) __attribute__((unused)) = f
''',
            'debug.h': '#define INFO 1\n#define CRITICAL 2\n#define dprintf(...) ((void)0)\n',
            'kernel/thread.h': '''#include <stdint.h>
typedef int thread_t;
#define DEFAULT_PRIORITY 16
#define DEFAULT_STACK_SIZE 12288
static unsigned clock_ms;
static void enter_critical_section(void) {}
static void exit_critical_section(void) {}
static unsigned current_time(void) { return clock_ms; }
static void thread_sleep(unsigned n) { clock_ms += n; }
static thread_t *thread_create(const char *n, int (*f)(void *), void *a, int p, int s)
{ (void)n; (void)f; (void)a; (void)p; (void)s; static thread_t t; return &t; }
static void thread_resume(thread_t *t) { (void)t; }
''',
            'partition_parser.h': '''#include <stdint.h>
struct partition_info { uint64_t offset, size; };
struct partition_info partition_get_info(const char *);
''',
            'platform.h': '''#define RECOVERY_MODE 1
static void reboot_device(unsigned reason) { (void)reason; }
''',
            'target.h': '''#include <stdint.h>
#define CACHE_LINE 64
static int target_is_emmc_boot(void) { return 1; }
static unsigned blocksize = 512;
static unsigned mmc_get_device_blocksize(void) { return blocksize; }
int mmc_read(uint64_t, void *, unsigned);
int mmc_write(uint64_t, unsigned, void *);
''',
        }
        for name, data in stubs.items():
            (root / name).write_text(data)
        source = root / 'test.c'
        source.write_text('''#include <assert.h>
#include <malloc.h>
#include <limits.h>
#include "''' + str(ROOT / 'bootloader/files/lk2nd/recovery-fastboot.c') + '''"
static unsigned char disk[4194304];
static unsigned writes;
static int bad_layout, write_error, stale_write, read_error;
struct partition_info partition_get_info(const char *name) {
    struct partition_info p;
    p.offset = !strcmp(name, "lk2nd") ? 4096 : 4096 + sizeof(disk) + bad_layout;
    p.size = sizeof(disk);
    return p;
}
int mmc_read(uint64_t pos, void *out, unsigned len) {
    assert(pos >= 4096 && pos + len <= 4096 + sizeof(disk));
    if (read_error) return 1;
    memcpy(out, disk + pos - 4096, len); return 0;
}
int mmc_write(uint64_t pos, unsigned len, void *in) {
    assert(pos == 4096 + TABS3_FB_REQUEST && len == 512);
    writes++;
    if (write_error) return 1;
    if (!stale_write) memcpy(disk + pos - 4096, in, len);
    return 0;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    assert(tabs3_fastboot_command_allowed("boot"));
    assert(tabs3_fastboot_command_allowed("getvar:product"));
    assert(tabs3_fastboot_command_allowed("download:00001000"));
    assert(tabs3_fastboot_command_allowed("continue"));
    assert(tabs3_fastboot_command_allowed("oem log"));
    assert(!tabs3_fastboot_command_allowed("flash:boot"));
    assert(!tabs3_fastboot_command_allowed("flash:recovery"));
    assert(!tabs3_fastboot_command_allowed("erase:userdata"));
    assert(!tabs3_fastboot_command_allowed("oem reboot-edl"));
    strcpy((char *)disk + TABS3_FB_DESCRIPTOR, TABS3_FB_CAPABILITY);
    strcpy((char *)disk + TABS3_FB_REQUEST, TABS3_FB_ONESHOT);
    int mode = atoi(argv[1]);
    if (mode == 1) disk[TABS3_FB_DESCRIPTOR] = '?';
    if (mode == 2) disk[TABS3_FB_REQUEST + 511] = '?';
    if (mode == 3) write_error = 1;
    if (mode == 4) stale_write = 1;
    if (mode == 5) bad_layout = 512;
    if (mode == 6) read_error = 1;
    if (mode == 7) blocksize = 4096;
    if (mode >= 1 && mode <= 7) {
        assert(!tabs3_fastboot_consume()); assert(!requested);
        assert(writes == ((mode == 3 || mode == 4) ? 1U : 0U)); return 0;
    }
    assert(tabs3_fastboot_consume()); assert(writes == 1);
    unsigned char zero[512] = {0};
    assert(!memcmp(disk + TABS3_FB_REQUEST, zero, 512));
    assert(!tabs3_fastboot_consume()); assert(writes == 1);
    clock_ms = mode == 9 ? UINT_MAX - 60000 : 1000;
    tabs3_fastboot_start();
    clock_ms += TABS3_FB_TIMEOUT_MS - 1;
    assert(!timeout_expired());
    assert(tabs3_fastboot_begin_command());
    assert(!tabs3_fastboot_begin_command()); /* Menu/USB cannot overlap. */
    clock_ms += TABS3_FB_TIMEOUT_MS * 2;
    assert(!timeout_expired()); /* Never reset during a flash/download. */
    tabs3_fastboot_end_command();
    clock_ms += TABS3_FB_TIMEOUT_MS - 1;
    assert(!timeout_expired());
    if (mode == 10) { tabs3_fastboot_stop(); clock_ms++; assert(!timeout_expired()); }
    else { clock_ms++; assert(timeout_expired()); assert(!tabs3_fastboot_begin_command()); }
    return 0;
}
''')
        cls.binary = root / 'test'
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-DLK2ND_RECOVERY_FASTBOOT=1', '-I', str(root),
                        '-I', str(ROOT / 'bootloader/files/lk2nd/include'),
                        str(source), '-o', str(cls.binary)], check=True)

    def test_consumption_errors_timeout_busy_and_clock_wrap(self):
        for mode in range(11):
            with self.subTest(mode=mode):
                subprocess.run([str(self.binary), str(mode)], check=True)


class RecoveryPackingTests(unittest.TestCase):
    def test_overlay_preserves_other_records_and_rejects_missing_helpers(self):
        fields = [1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        archive = pack.newc_record('usr/sbin/tabs3-recovery', b'old', fields)
        archive += pack.newc_record('usr/bin/tabs3-recovery-ui', b'ui', fields)
        untouched = pack.newc_record('lib/modules/keep', b'unchanged')
        archive += untouched + pack.newc_record('TRAILER!!!', b'')
        result = pack.overlay_cpio(archive, {'usr/sbin/tabs3-recovery': b'new-helper',
                                           'usr/lib/tabs3/fastboot-request.sh': b'library'})
        self.assertIn(untouched, result)
        self.assertIn(b'new-helper', result)
        self.assertIn(b'library', result)
        with self.assertRaises(ValueError):
            pack.overlay_cpio(pack.newc_record('TRAILER!!!', b''), {})

    def test_packer_and_firmware_protocol_match(self):
        header = (ROOT / 'bootloader/files/lk2nd/include/lk2nd/recovery-fastboot.h').read_text()
        self.assertIn(pack.CAPABILITY.rstrip(b'\0').decode(), header)
        self.assertIn(pack.REQUEST.rstrip(b'\0').decode(), header)


if __name__ == '__main__':
    unittest.main()
