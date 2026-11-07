"""Exercise the patched driver's MUIC decoder, including failed reads."""
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DRIVER = "drivers/power/supply/sm5705_charger.c"


class ChargerSourceTests(unittest.TestCase):
    def test_unknown_source_is_distinct_from_i2c_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            for patch in sorted((ROOT / "kernel/patches").glob("*.patch")):
                text = patch.read_text()
                match = re.search(r"^--- a/" + re.escape(DRIVER) +
                                  r"\n.*?(?=^--- |^diff |\Z)", text,
                                  re.MULTILINE | re.DOTALL)
                if match:
                    subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                   input=match.group(), text=True, cwd=directory,
                                   check=True, capture_output=True)
            text = (directory / DRIVER).read_text()
            start = text.index("static int sm5705_chg_usb_type(")
            end = text.index("\n}", start) + 2
            defines = "\n".join(line for line in text.splitlines()
                                if line.startswith("#define SM5705_MUIC_"))
            source = r'''
#include <assert.h>
#include <errno.h>
#define BIT(n) (1U << (n))
enum { POWER_SUPPLY_USB_TYPE_UNKNOWN, POWER_SUPPLY_USB_TYPE_SDP,
       POWER_SUPPLY_USB_TYPE_DCP, POWER_SUPPLY_USB_TYPE_CDP };
struct sm5705_chg { int muic; };
static int value;
static int i2c_smbus_read_byte_data(int client, int reg) {
    (void)client; (void)reg; return value;
}
''' + defines + "\n" + text[start:end] + r'''
int main(void) {
    struct sm5705_chg chg = {0};
    value = -EIO;
    assert(sm5705_chg_usb_type(&chg) == -EIO);
    value = -ENXIO;
    assert(sm5705_chg_usb_type(&chg) == -ENXIO);
    value = 0;
    assert(sm5705_chg_usb_type(&chg) == POWER_SUPPLY_USB_TYPE_UNKNOWN);
    value = SM5705_MUIC_DEVT1_SDP;
    assert(sm5705_chg_usb_type(&chg) == POWER_SUPPLY_USB_TYPE_SDP);
    value = SM5705_MUIC_DEVT1_CDP;
    assert(sm5705_chg_usb_type(&chg) == POWER_SUPPLY_USB_TYPE_CDP);
    value = SM5705_MUIC_DEVT1_DCP;
    assert(sm5705_chg_usb_type(&chg) == POWER_SUPPLY_USB_TYPE_DCP);
    return 0;
}
'''
            program = directory / "source.c"
            program.write_text(source)
            binary = directory / "source-test"
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(program), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
