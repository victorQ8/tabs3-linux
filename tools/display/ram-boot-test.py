#!/usr/bin/env python3
"""Reboot the Tab S3 into lk2nd fastboot (Volume Down held), RAM-boot the
display test image with an optional extra cmdline, and collect the panel log."""
import json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
TSSH = str(pathlib.Path(__file__).with_name('tssh'))
label, extra = sys.argv[1], ' '.join(sys.argv[2:])
out = ROOT / 'private/linux-display-test' / f'{label}.txt'
serial = json.loads((ROOT / 'private/fastboot-target.json').read_text())['serial']
fb = ['fastboot', '-s', serial]
image = ROOT / 'private/images/tabs3-installed-display.img'

subprocess.run([TSSH, 'sudo -n systemctl reboot'], timeout=15)
for _ in range(25):
    time.sleep(2)
    devices = subprocess.run(['fastboot', 'devices'], capture_output=True, text=True, timeout=5).stdout
    if any(line.split()[:1] == [serial] for line in devices.splitlines()):
        break
else:
    sys.exit('Fastboot not detected within 50 s (was Volume Down held?)')
ident = subprocess.run(fb + ['getvar', 'lk2nd:compatible'], capture_output=True, text=True, timeout=5)
assert 'samsung,gts3llte' in ident.stdout + ident.stderr, ident
cmd = fb + ['boot', str(image)]
if extra:
    from importlib import util
    spec = util.spec_from_file_location('android_boot', ROOT / 'scripts/android_boot.py')
    ab = util.module_from_spec(spec); spec.loader.exec_module(ab)
    cmd = fb + ['--cmdline', ab.parse_boot(image.read_bytes()).cmdline + ' ' + extra, 'boot', str(image)]
print('fastboot verified; booting', label, extra or '(default cmdline)', flush=True)
subprocess.run(cmd, check=True, timeout=40)
start = time.monotonic()
while time.monotonic() - start < 60:
    time.sleep(3)
    r = subprocess.run([TSSH, 'cat /proc/cmdline; sudo -n dmesg'], capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        out.write_text(r.stdout)
        print(f'SSH back after {time.monotonic() - start:.0f} s; log: {out}')
        keep = ('ams968', 'DCS 0x', 'TCON_RDY', 'panel', 'dsi', 'dpu', 'timed out', 'time out', 'rcg')
        for line in r.stdout.splitlines()[:1] + [l for l in r.stdout.splitlines() if any(k in l for k in keep)
                                                   and 'Fixed dependency' not in l][:60]:
            print(line)
        break
else:
    sys.exit('No SSH within 60 s of RAM boot')
