"""Exercise the actual raw-ADC conversion compiled from the kernel patch."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SkinTemperatureTests(unittest.TestCase):
    def test_stock_units_interpolation_and_invalid_sensor_values(self):
        patch = (ROOT / "kernel/patches/0034-thermal-sm-t825-raw-ap-thermistor.patch").read_text()
        section = patch.split("+++ b/drivers/thermal/gts3l-skin-table.h\n", 1)[1]
        section = section.split("--- /dev/null", 1)[0]
        header = "\n".join(line[1:] for line in section.splitlines()
                           if line.startswith("+"))
        source = r'''
#include <assert.h>
#include <limits.h>
#include "table.h"
int main(void) {
    int temp, previous = INT_MAX;
    /* Stock raw codes: 90 C, 43 C trip, room temperature, freezing, -20 C. */
    const int vectors[][2] = {
        {25831, 90000}, {29966, 43000}, {33496, 25000},
        {38453, 0}, {41377, -20000},
        /* Halfway between 24/23 C and 0/-1 C, including negative output. */
        {33880, 23500}, {38568, -500}
    };
    for (unsigned int i = 0; i < sizeof(vectors) / sizeof(vectors[0]); i++) {
        assert(!gts3l_skin_convert(vectors[i][0], &temp));
        assert(temp == vectors[i][1]);
    }
    for (int adc = 25831; adc <= 41377; adc++) {
        assert(!gts3l_skin_convert(adc, &temp));
        assert(temp <= previous && temp >= -20000 && temp <= 90000);
        previous = temp;
    }
    const int invalid[] = {INT_MIN, -1, 0, 25830, 41378, 65535, INT_MAX};
    for (unsigned int i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
        temp = 123456;
        assert(gts3l_skin_convert(invalid[i], &temp) != 0);
        assert(temp == 123456); /* A failed read cannot become a valid cold reading. */
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            (path / "table.h").write_text(header)
            (path / "test.c").write_text(source)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(path / "test.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
