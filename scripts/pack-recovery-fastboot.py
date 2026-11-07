#!/usr/bin/env python3
"""Build a separate recovery candidate from a hash-pinned, working recovery.

Preserves its Linux kernel, DTBs, modules and SSH key. Never accesses a device.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import zlib

from android_boot import align, verify_v0_id

ROOT = Path(__file__).resolve().parents[1]
RESERVED = 4194304
CAP_OFFSET = RESERVED - 8192
REQUEST_OFFSET = RESERVED - 4096
CAPABILITY = b'TABS3-RFB-CAP-v1:120'.ljust(512, b'\0')
REQUEST = b'TABS3-RFB-ONCE-v1'.ljust(512, b'\0')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def newc_record(name, payload, fields=None):
    fields = list(fields) if fields else [0, stat.S_IFREG | 0o644, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    name = name.encode() + b'\0'
    fields[6], fields[11], fields[12] = len(payload), len(name), 0
    header = b'070701' + ''.join(f'{v:08x}' for v in fields).encode()
    result = (header + name).ljust(align(len(header) + len(name), 4), b'\0')
    return result + payload.ljust(align(len(payload), 4), b'\0')


def overlay_cpio(raw, replacements, executables=()):
    output, pos, seen = bytearray(), 0, set()
    while True:
        header = raw[pos:pos + 110]
        if len(header) != 110 or header[:6] != b'070701':
            raise ValueError('Expected uncompressed newc archive')
        fields = [int(header[i:i+8], 16) for i in range(6, 110, 8)]
        size, namesize = fields[6], fields[11]
        if not 1 <= namesize <= 4096:
            raise ValueError('Invalid archive name size')
        name_end = pos + 110 + namesize
        name_raw = raw[pos+110:name_end]
        if len(name_raw) != namesize or name_raw[-1:] != b'\0':
            raise ValueError('Truncated archive name')
        name = name_raw[:-1].decode()
        data_at = align(name_end, 4)
        payload = raw[data_at:data_at+size]
        if len(payload) != size:
            raise ValueError('Truncated archive payload')
        pos = align(data_at + size, 4)
        if name == 'TRAILER!!!':
            break
        normalized = name.removeprefix('./')
        if normalized in seen:
            raise ValueError('Duplicate archive path')
        seen.add(normalized)
        if normalized in replacements:
            if not stat.S_ISREG(fields[1]) or fields[4] != 1:
                raise ValueError('Replacement is not a single regular file')
            payload = replacements[normalized]
        output += newc_record(name, payload, fields)
    required = {'usr/sbin/tabs3-recovery', 'usr/bin/tabs3-recovery-ui'}
    if not required.issubset(seen):
        raise ValueError('Baseline is missing recovery helpers')
    for name, payload in replacements.items():
        if name not in seen:
            fields = [0, stat.S_IFREG | (0o755 if name in executables else 0o644),
                      0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
            output += newc_record(name, payload, fields)
    output += newc_record('TRAILER!!!', b'')
    return bytes(output).ljust(align(len(output), 512), b'\0')


def replace_payloads(original, kernel, ramdisk):
    image = verify_v0_id(original)
    header = bytearray(original[:image.page_size])
    struct.pack_into('<I', header, 8, len(kernel))
    struct.pack_into('<I', header, 16, len(ramdisk))
    digest = hashlib.sha1()
    for blob in (kernel, ramdisk, b''):
        digest.update(blob)
        digest.update(struct.pack('<I', len(blob)))
    header[576:608] = digest.digest().ljust(32, b'\0')
    result = bytes(header) + kernel.ljust(align(len(kernel), image.page_size), b'\0')
    result += ramdisk.ljust(align(len(ramdisk), image.page_size), b'\0') + b'SEANDROIDENFORCE'
    verify_v0_id(result)
    return result


def build(baseline, lk_binary, replacements):
    outer = verify_v0_id(baseline[:RESERVED])
    inner = verify_v0_id(baseline[RESERVED:])
    if 'tabs3.mode=recovery' not in inner.cmdline.split():
        raise ValueError('Baseline is not a recovery image')
    if any(baseline[CAP_OFFSET:RESERVED]):
        raise ValueError('Baseline reserved tail is not empty')
    if b'TABS3-RFB-CAP-v1:120' not in lk_binary or b'TABS3-RFB-ONCE-v1' not in lk_binary:
        raise ValueError('lk2nd binary lacks the remote-entry protocol')
    decoder = zlib.decompressobj(31)
    decoder.decompress(outer.kernel)
    if not decoder.eof or not decoder.unused_data.startswith(b'\xd0\x0d\xfe\xed'):
        raise ValueError('Expected gzip lk2nd followed by stock DTBs')
    wrapper = replace_payloads(baseline[:RESERVED],
                               gzip.compress(lk_binary, mtime=0) + decoder.unused_data,
                               outer.ramdisk)
    if len(wrapper) > CAP_OFFSET:
        raise ValueError('Bootloader overlaps reserved request records')
    wrapper = bytearray(wrapper.ljust(RESERVED, b'\0'))
    wrapper[CAP_OFFSET:CAP_OFFSET+512] = CAPABILITY
    initrd = gzip.compress(overlay_cpio(gzip.decompress(inner.ramdisk), replacements,
                                      {'usr/sbin/tabs3-reboot-recovery'}), mtime=0)
    if len(initrd) > 0xb00000:
        raise ValueError('Initramfs exceeds its 11 MiB load window')
    linux = replace_payloads(baseline[RESERVED:], inner.kernel, initrd)
    combined = bytes(wrapper) + linux
    if len(combined) > 79691776:
        raise ValueError('Recovery partition too small')
    return combined, linux


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--baseline-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    baseline = args.baseline.read_bytes()
    if sha(baseline) != args.baseline_sha256:
        parser.error('Baseline SHA256 does not match')
    inputs = {
        'usr/sbin/tabs3-recovery': ROOT / 'initramfs/tabs3-recovery',
        'usr/lib/tabs3/fastboot-request.sh': ROOT / 'initramfs/fastboot-request.sh',
        'usr/bin/tabs3-recovery-ui': ROOT / 'artifacts/tabs3-recovery-ui',
        'usr/sbin/tabs3-reboot-recovery': ROOT / 'artifacts/tabs3-reboot-recovery',
    }
    lk_path = ROOT / 'artifacts/lk2nd-sm-t825-recovery-fastboot.bin'
    lk_binary = lk_path.read_bytes()
    replacements = {name: path.read_bytes() for name, path in inputs.items()}
    combined, linux = build(baseline, lk_binary, replacements)
    os.umask(0o077)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {'tabs3-recovery-fastboot-candidate.img': combined,
               'tabs3-recovery-fastboot-linux.img': linux}
    report = {
        'hardware_tested': False, 'installed': False,
        'baseline_sha256': sha(baseline), 'lk2nd_sha256': sha(lk_binary),
        'kernel_and_dtb_unchanged': True,
        'linux_kernel_sha256': sha(verify_v0_id(linux).kernel),
        'request_offset': REQUEST_OFFSET, 'timeout_seconds': 120,
        'inputs': {name: sha(data) for name, data in replacements.items()},
        'images': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in outputs.items()},
    }
    for name, data in outputs.items():
        dest = args.output_dir / name
        if dest.resolve() == args.baseline.resolve():
            parser.error('Cannot overwrite baseline')
        dest.write_bytes(data)
    (args.output_dir / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
