"""USB SSH must not depend on /lib/modules.

libcomposite and usb_f_ncm are built in. When a kernel package replaced the
running kernel's module directory, `modprobe` failed under `set -e`, the
gadget script stopped and the tablet had no USB network (2026-10-12).
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packages/tabs3-base/usr/libexec/tabs3-usb-gadget"


class UsbGadgetTests(unittest.TestCase):
    def test_gadget_is_usb2_only_before_it_binds(self):
        text = SCRIPT.read_text()
        self.assertIn("echo high-speed > max_speed", text)
        self.assertLess(text.index("echo high-speed > max_speed"), text.index('echo "$udc" > UDC'))

    def test_modprobe_failures_are_not_fatal(self):
        for line in SCRIPT.read_text().splitlines():
            if re.match(r"\s*modprobe\b", line):
                self.assertRegex(line, r"\|\|\s*true\s*$", line)

    def test_initramfs_rescue_has_the_same_speed_limit_before_bind(self):
        text = (ROOT / 'initramfs/init').read_text()
        self.assertLess(text.index('echo high-speed >"$g/max_speed"'),
                        text.index('echo "$udc" >"$g/UDC"'))


if __name__ == "__main__":
    unittest.main()
