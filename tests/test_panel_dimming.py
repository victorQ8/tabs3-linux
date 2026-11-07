"""Compare runtime dimming with independently compiled Samsung C outputs."""
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PanelDimmingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        p = pathlib.Path(cls.temp.name)
        source = p / 'dimming.c'
        source.write_text(r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32; typedef uint64_t u64;
typedef int16_t s16; typedef int32_t s32; typedef int64_t s64;
#include "ams968hh01-dimming.h"
int main(int argc, char **argv) {
    u8 mtp[33], gamma[65][33]; struct ams_dimming_work w;
    if (argc == 2) {
        unsigned level = strtoul(argv[1], 0, 10);
        if (level > 255) return 2;
        const u8 *d = ams_brightness_data[level];
        printf("%u %u %u %u\n", ams_candela[d[0]], (d[1]<<8)|d[2], d[3], d[4]);
        return 0;
    }
    if (argc != 34) return 2;
    for (int i=0;i<33;i++) mtp[i]=strtoul(argv[i+1],0,16);
    if (ams_generate_gamma(mtp,gamma,&w)) return 3;
    return fwrite(gamma,1,sizeof(gamma),stdout)==sizeof(gamma) ? 0 : 4;
}
''')
        cls.exe = p / 'dimming'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined,address', '-I', str(ROOT / 'kernel'),
                        str(source), '-o', str(cls.exe)], check=True)
        cls.fixtures = json.loads((ROOT / 'tests/fixtures/ams968hh01-gamma.json').read_text())['fixtures']

    def test_all_levels_match_original_samsung_code(self):
        for fixture in self.fixtures:
            with self.subTest(calibration=fixture['name']):
                actual = subprocess.check_output([str(self.exe), *fixture['mtp'].split()])
                expected = bytes.fromhex(' '.join(fixture['gamma']))
                self.assertEqual(actual, expected)

    def test_invalid_vt_calibration_is_rejected(self):
        for invalid in (16, 0x81, 255):
            mtp = ['00'] * 33
            mtp[10] = f'{invalid:02x}'
            with self.subTest(value=invalid):
                r = subprocess.run([str(self.exe), *mtp], capture_output=True)
                self.assertEqual(r.returncode, 3, r.stderr)
                self.assertEqual(r.stdout, b'')

    def test_complete_stock_level_mapping(self):
        # Independently cited examples from the pinned stock DT (not generated gamma).
        examples = {0: (2, 0x17f, 0x19, 0x81), 86: (111, 0x99, 0x21, 0x85),
                    255: (360, 0x0e, 0x1b, 0x85)}
        for level, expected in examples.items():
            with self.subTest(level=level):
                values = subprocess.check_output([str(self.exe), str(level)], text=True)
                self.assertEqual(tuple(map(int, values.split())), expected)


if __name__ == '__main__':
    unittest.main()
