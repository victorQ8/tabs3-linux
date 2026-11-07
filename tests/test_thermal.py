"""Keep the SoC temperature sensors and their throttling enabled.

Without TSENS nothing throttles the CPU or GPU: before package 43 a sustained
four-core load ran at full speed with no software limit. With it, the 85/90 C
passive trips held the CPUs at 88-91 C on the tablet.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ThermalTests(unittest.TestCase):
    def test_tsens_driver_is_built(self):
        config = (ROOT / "kernel/bringup.config").read_text()
        self.assertRegex(config, r"(?m)^CONFIG_QCOM_TSENS=[my]$")

    def test_board_trees_keep_sensors_and_zones(self):
        for path in sorted((ROOT / "kernel").glob("msm8996-samsung-gts3llte*.dts*")):
            text = path.read_text()
            for label in ("tsens0", "tsens1"):
                block = re.search(r"&" + label + r"\s*\{(.*?)\n\};", text, re.S)
                if block:
                    self.assertNotIn('"disabled"', block.group(1), f"{path.name}: {label}")
            self.assertNotRegex(text, r"/delete-node/\s*&?(tsens|thermal)", path.name)


if __name__ == "__main__":
    unittest.main()
