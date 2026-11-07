"""Run the actual charging policy and verified-write helper on fake hardware."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ChargingSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        directory = pathlib.Path(cls.tmp.name)
        patch = (ROOT / "kernel/patches/0011-power-supply-sm5705-temperature-protection.patch").read_text()
        added = "\n".join(line[1:] for line in patch.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        start = added.index("static int sm5705_update_verified(")
        end = added.index("\n}", start) + 2
        write_helper = added[start:end]
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include "sm5705-gts3l-policy.h"
typedef unsigned char u8;
struct sm5705_chg { int client; };
static u8 reg_value;
static int read_error, write_error, ignore_write, writes;
static int sm5705_chg_read(struct sm5705_chg *c, u8 r, u8 *v) {
    (void)c; (void)r;
    if (read_error) return -EIO;
    *v = reg_value;
    return 0;
}
static int i2c_smbus_write_byte_data(int client, u8 r, u8 value) {
    (void)client; (void)r;
    writes++;
    if (write_error) return -EIO;
    if (!ignore_write) reg_value = value;
    return 0;
}
''' + write_helper + r'''
#define CHOOSE(valid, bt, ct, src) sm5705_choose_limits(&s, valid, bt, ct, src, 1500000, true, false)
int main(int argc, char **argv) {
    assert(argc == 2);
    struct sm5705_safety s = { .blocked = true, .cool = true };
    struct sm5705_limits out;
    int temp;
    switch (atoi(argv[1])) {
    case 0:
        /* Raw units, interpolation, and disconnected/shorted sensor values. */
        assert(sm5705_temperature(33900, false, &temp) && temp == 250);
        assert(sm5705_temperature(34400, false, &temp) && temp == 230);
        assert(sm5705_temperature(34048, true, &temp) && temp == 250);
        assert(sm5705_temperature(41366, false, &temp) && temp == -200);
        assert(sm5705_temperature(25990, false, &temp) && temp == 900);
        assert(!sm5705_temperature(0x6000, false, &temp));
        assert(!sm5705_temperature(0xa800, false, &temp));
        assert(!sm5705_temperature(-1, true, &temp));
        break;
    case 1:
        out = CHOOSE(true, 250, 300, 500000);
        assert(out.enable && out.input_ua == 500000);
        out = CHOOSE(true, 250, 300, 1800000);
        assert(out.enable && out.input_ua == 1500000 && out.charge_ua == 1500000);
        out = CHOOSE(true, 250, 300, 100000);
        assert(!out.enable && out.input_ua == 100000);
        out = sm5705_choose_limits(&s, true, 250, 300, 1500000, 250000, true, false);
        assert(out.input_ua == 250000);
        out = sm5705_choose_limits(&s, true, 250, 300, 1500000, 1500000, false, false);
        assert(out.input_ua == 500000);
        out = sm5705_choose_limits(&s, true, 250, 300, 1500000, 1500000, true, true);
        assert(!out.enable && out.input_ua == 1500000);
        out = sm5705_choose_limits(&s, true, 250, 300, 500000, 1500000, true, true);
        assert(!out.enable && out.input_ua == 500000);
        break;
    case 2:
        out = CHOOSE(true, 50, 300, 1500000); assert(!out.enable && out.input_ua == 1500000);
        out = CHOOSE(true, 75, 300, 1500000); assert(!out.enable);
        out = CHOOSE(true, 100, 300, 1500000); assert(out.enable && out.charge_ua == 900000);
        out = CHOOSE(true, 190, 300, 1500000); assert(out.charge_ua == 900000);
        out = CHOOSE(true, 200, 300, 1500000); assert(out.charge_ua == 1500000);
        out = CHOOSE(true, 410, 300, 1500000); assert(!out.enable && out.input_ua == 1500000);
        out = CHOOSE(true, 400, 300, 1500000); assert(!out.enable);
        out = CHOOSE(true, 390, 300, 1500000); assert(out.enable && out.charge_ua == 900000);
        out = CHOOSE(false, 250, 300, 1500000);
        assert(!out.enable && s.blocked && out.input_ua == 500000);
        out = sm5705_choose_limits(&s, false, 250, 300, 1500000, 250000, true, false);
        assert(!out.enable && out.input_ua == 250000);
        out = CHOOSE(true, 395, 300, 1500000); assert(!out.enable);
        out = CHOOSE(true, 250, 500, 1500000); assert(out.enable && out.input_ua == 500000);
        out = CHOOSE(true, 250, 490, 1500000); assert(out.input_ua == 500000);
        out = CHOOSE(true, 250, 470, 1500000); assert(out.input_ua == 1500000);
        out = CHOOSE(true, 410, 500, 1500000);
        assert(!out.enable && out.input_ua == 500000);
        break;
    case 3: {
        struct sm5705_chg chg = {0};
        /* Start at a higher limit, simulate a failed reduction, then retry. */
        reg_value = 0x80 | 56;
        write_error = 1;
        assert(sm5705_update_verified(&chg, 0x0d, 0x7f, 16) == -EIO);
        assert(reg_value == (0x80 | 56));
        write_error = 0;
        assert(sm5705_update_verified(&chg, 0x0d, 0x7f, 16) == 0);
        assert(reg_value == (0x80 | 16) && writes == 2);
        assert(sm5705_update_verified(&chg, 0x0d, 0x7f, 16) == 0 && writes == 2);
        ignore_write = 1;
        assert(sm5705_update_verified(&chg, 0x0d, 0x7f, 0) == -EIO);
        read_error = 1;
        assert(sm5705_update_verified(&chg, 0x0d, 0x7f, 0) == -EIO);
        assert(writes == 3);
        break;
    }
    default: assert(0);
    }
    return 0;
}
'''
        program = directory / "policy.c"
        program.write_text(source)
        cls.binary = directory / "policy"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-I", str(ROOT / "kernel"), str(program),
                        "-o", str(cls.binary)], check=True)

    def test_stock_temperature_conversion_and_sensor_faults(self):
        subprocess.run([str(self.binary), "0"], check=True)

    def test_source_limits_unknown_ports_and_manual_controls(self):
        subprocess.run([str(self.binary), "1"], check=True)

    def test_temperature_cutoffs_hysteresis_and_missing_readings(self):
        subprocess.run([str(self.binary), "2"], check=True)

    def test_failed_writes_retry_and_require_correct_readback(self):
        subprocess.run([str(self.binary), "3"], check=True)


if __name__ == "__main__":
    unittest.main()
