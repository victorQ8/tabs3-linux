"""Guard the button device tree and the TC305K key decoding."""
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DISPLAY_DTS = ROOT / "kernel/msm8996-samsung-gts3llte-display.dts"
GPU_DTS = ROOT / "kernel/msm8996-samsung-gts3llte-gpu.dts"
PATCH = ROOT / "kernel/patches/0015-input-tm2-touchkey-coreriver-tc305k.patch"
# Samsung TrustZone owns these; Linux touching them resets the tablet.
SECURE_PINS = set(range(25, 29)) | set(range(58, 62))


def tlmm_blocks(text):
    """Yield the bodies of every top-level '&tlmm { ... }' override."""
    for match in re.finditer(r"^&tlmm\s*\{", text, re.MULTILINE):
        depth, start = 0, match.end() - 1
        for pos in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[pos], 0)
            if depth == 0:
                yield text[start:pos]
                break


def expand(path, seen=None):
    """A board DTS with its local "#include"s inlined (the tree's own
    includes, e.g. the sibling port's DTS, are outside kernel/ and skipped)."""
    seen = set() if seen is None else seen
    out = []
    for line in path.read_text().splitlines(keepends=True):
        match = re.match(r'#include "([^"]+)"', line)
        child = path.parent / match.group(1) if match else None
        if child is not None and child.exists() and child not in seen:
            seen.add(child)
            out.append(expand(child, seen))
        elif child is None:
            out.append(line)
    return "".join(out)


def tlmm_pins(path):
    """Reserved TLMM pins (the last list in the include chain wins) and the
    pins used by a board variant."""
    text = expand(path)
    blocks = list(tlmm_blocks(text))
    ranges = [b for b in blocks if "gpio-reserved-ranges" in b]
    assert ranges, path
    pairs = re.findall(r"<(\d+) (\d+)>", ranges[-1])
    reserved = {pin for start, count in pairs
                for pin in range(int(start), int(start) + int(count))}
    used = {int(n) for n in re.findall(r"&tlmm (\d+)", text)}
    for block in blocks:
        used |= {int(n) for n in re.findall(r'"gpio(\d+)"', block)}
    return reserved, used


class ButtonTreeTests(unittest.TestCase):
    def setUp(self):
        self.text = expand(DISPLAY_DTS)
        self.variants = {
            "display": tlmm_pins(DISPLAY_DTS),
            "gpu": tlmm_pins(GPU_DTS),
        }

    def test_secure_pins_stay_reserved(self):
        for name, (reserved, _) in self.variants.items():
            self.assertTrue(SECURE_PINS <= reserved, name)

    def test_every_used_pin_is_unreserved(self):
        for name, (reserved, used) in self.variants.items():
            self.assertEqual(used & reserved, set(), name)
        self.assertTrue({21, 22, 64, 118} <= self.variants["display"][1])
        self.assertTrue({74, 79} <= self.variants["gpu"][1])
        for name in self.variants:
            self.assertIn(95, self.variants[name][1], name)  # microSD card detect

    def test_keycodes(self):
        self.assertIn("linux,keycodes = <KEY_APPSELECT KEY_BACK>;", self.text)
        for code in ("KEY_HOMEPAGE", "KEY_VOLUMEUP", "KEY_VOLUMEDOWN"):
            self.assertIn(f"linux,code = <{code}>;", self.text)


class TouchkeyBitmapTests(unittest.TestCase):
    def test_decode(self):
        added = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        start = added.index("static void tm2_touchkey_report_bitmap(")
        function = added[start:added.index("\n}", start) + 2]
        source = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char u8;
#define BIT(n) (1U << (n))
#define EV_MSC 4
#define MSC_SCAN 4
struct input_dev { int unused; };
struct tm2_touchkey_data {
    struct input_dev *input_dev;
    unsigned int keycodes[4];
    int num_keycodes;
};
static char out[256];
static void input_event(struct input_dev *d, int type, int code, int value) {
    char b[16]; (void)d; (void)type; (void)code;
    snprintf(b, sizeof b, "S%d ", value); strcat(out, b);
}
static void input_report_key(struct input_dev *d, unsigned int code, int value) {
    char b[16]; (void)d;
    snprintf(b, sizeof b, "K%u=%d ", code, value); strcat(out, b);
}
static void input_sync(struct input_dev *d) { (void)d; strcat(out, "| "); }
''' + function + r'''
int main(int argc, char **argv) {
    struct input_dev dev;
    struct tm2_touchkey_data key = { &dev, { 580, 158 }, 2 };
    for (int i = 1; i < argc; i++) {
        out[0] = 0;
        tm2_touchkey_report_bitmap(&key, (u8)strtol(argv[i], NULL, 0));
        printf("%s\n", out);
    }
    return 0;
}
'''
        expected = {
            "0x01": "S0 K580=1 | | ",            # Recent down
            "0x10": "| S0 K580=0 | ",            # Recent up
            "0x02": "S1 K158=1 | | ",            # Back down
            "0x20": "| S1 K158=0 | ",            # Back up
            "0x11": "S0 K580=1 | S0 K580=0 | ",  # quick tap: press first
            "0x44": "| | ",                      # grip bits are not keys
        }
        with tempfile.TemporaryDirectory() as tmp:
            program = pathlib.Path(tmp) / "bitmap.c"
            program.write_text(source)
            binary = pathlib.Path(tmp) / "bitmap"
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(program), "-o", str(binary)], check=True)
            result = subprocess.run([str(binary), *expected], check=True,
                                    capture_output=True, text=True)
        self.assertEqual(result.stdout.splitlines(), list(expected.values()))


if __name__ == "__main__":
    unittest.main()
