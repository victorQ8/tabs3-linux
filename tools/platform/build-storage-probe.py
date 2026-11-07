#!/usr/bin/env python3
"""Create a RAM-only eMMC speed probe from an existing read-only probe image.

Run in tabs3-builder:trixie (requires fdtget/fdtput). Never flashes a device.
The original kernel, initramfs, five-minute limit and storage-probe mode are
preserved. Only the MMC timing capabilities and maximum clock are changed.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from android_boot import appended_dtbs, verify_v0_id

spec = importlib.util.spec_from_file_location('pack_images', ROOT / 'scripts/pack-images.py')
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_image', type=pathlib.Path)
    parser.add_argument('output', type=pathlib.Path)
    parser.add_argument('--timing', choices=('hs200', 'hs400'), required=True)
    args = parser.parse_args()
    os.umask(0o077)
    raw = args.base_image.read_bytes()
    boot = verify_v0_id(raw)
    modes = [word for word in boot.cmdline.split() if word.startswith('tabs3.mode=')]
    if modes != ['tabs3.mode=storage-probe']:
        parser.error('Base image must be the read-only storage-probe, never installed mode')
    (dtb,) = appended_dtbs(boot)
    decoder = zlib.decompressobj(31)
    decoder.decompress(boot.kernel)
    kernel = boot.kernel[:-len(decoder.unused_data)]
    with tempfile.TemporaryDirectory() as directory:
        work = pathlib.Path(directory)
        path = work / 'probe.dtb'
        path.write_bytes(dtb)
        pack.validate_linux_dtb(path, 'storage-probe', 'headless')
        node = '/soc@0/mmc@7464900'
        subprocess.run(['fdtput', '-t', 'i', str(path), node, 'max-frequency', '200000000'], check=True)
        subprocess.run(['fdtput', str(path), node, 'mmc-hs200-1_8v'], check=True)
        if args.timing == 'hs400':
            subprocess.run(['fdtput', str(path), node, 'mmc-hs400-1_8v'], check=True)
        else:
            subprocess.run(['fdtput', str(path), node, 'no-mmc-hs400'], check=True)
        data = pack.write_boot(work, args.timing, kernel + path.read_bytes(), boot.ramdisk, boot, boot.cmdline)
        checked = verify_v0_id(data)
        assert checked.ramdisk == boot.ramdisk and checked.cmdline == boot.cmdline
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
        args.output.with_suffix('.json').write_text(json.dumps({
            'mode': 'storage-probe', 'requested_timing': args.timing,
            'maximum_clock_hz': 200000000, 'hardware_validated': False,
            'base_sha256': hashlib.sha256(raw).hexdigest(),
            'image_sha256': hashlib.sha256(data).hexdigest(),
            'unchanged_initramfs_sha256': hashlib.sha256(boot.ramdisk).hexdigest(),
            'cmdline': boot.cmdline,
        }, indent=2) + '\n')
        print(f'{args.output}: RAM probe built; no device accessed')


if __name__ == '__main__':
    main()
