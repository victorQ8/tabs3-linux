#!/usr/bin/env python3
"""Stream a 2048x1536 XRGB8888 test pattern to the tablet framebuffer.

Patterns: red green blue white black q4 (TL red, TR green, BL blue,
BR white) stripes (R/G/B/W in the left half only) greys (16 grey steps,
black at the left to white at the right)."""
import pathlib
import subprocess
import sys

W, H = 2048, 1536
TSSH = str(pathlib.Path(__file__).with_name('tssh'))


def px(r, g, b):
    return bytes((b, g, r, 0))


def frame(name):
    solid = {'red': (255, 0, 0), 'green': (0, 255, 0), 'blue': (0, 0, 255),
             'white': (255, 255, 255), 'black': (0, 0, 0)}
    if name in solid:
        return px(*solid[name]) * (W * H)
    if name == 'q4':
        top = px(255, 0, 0) * (W // 2) + px(0, 255, 0) * (W // 2)
        bottom = px(0, 0, 255) * (W // 2) + px(255, 255, 255) * (W // 2)
        return top * (H // 2) + bottom * (H // 2)
    if name == 'stripes':
        left = b''.join(px(*c) * 256 for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)))
        return (left + px(0, 0, 0) * (W // 2)) * H
    if name == 'greys':
        return b''.join(px(v, v, v) * (W // 16) for v in range(0, 256, 17)) * H
    raise SystemExit(__doc__)


data = frame(sys.argv[1] if len(sys.argv) > 1 else 'q4')
subprocess.run([TSSH, 'sudo -n sh -c "echo 0 > /sys/class/vtconsole/vtcon1/bind 2>/dev/null; true"'], check=True)
subprocess.run([TSSH, 'sudo -n dd of=/dev/fb0 bs=1M status=none'], input=data, check=True)
