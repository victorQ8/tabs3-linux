#!/usr/bin/env python3
"""Pack verified SM-T825 boot artifacts locally; never access a USB device."""
import argparse
import gzip
import hashlib
import json
import os
import pathlib
import re
import struct
import subprocess
import tempfile
import uuid

from android_boot import appended_dtbs, parse_boot, verify_v0_id

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs).stdout


def prop(path, node, name):
    return run('fdtget', '-t', 'x', str(path), node, name).decode().strip()


def validate_linux_dtb(dtb, mode, variant):
    if prop(dtb, '/', 'qcom,msm-id') != 'f6 30001' or prop(dtb, '/', 'qcom,board-id') != '8 5':
        raise SystemExit('Linux DTB identity mismatch')
    expected_storage = b'disabled' if mode == 'diagnostic' else b'okay'
    if run('fdtget', '-t', 's', str(dtb), '/soc@0/mmc@7464900', 'status').strip() != expected_storage:
        raise SystemExit('Internal storage status does not match the selected mode')
    expected_clock = 'bebc200' if variant == 'gpu' else '3197500'
    if mode != 'diagnostic' and prop(dtb, '/soc@0/mmc@7464900', 'max-frequency') != expected_clock:
        raise SystemExit('eMMC clock does not match the selected variant')
    expected_gpu = b'okay' if variant == 'gpu' else b'disabled'
    if run('fdtget', '-t', 's', str(dtb), '/soc@0/gpu@b00000', 'status').strip() != expected_gpu:
        raise SystemExit('GPU status does not match the selected variant')


def write_boot(work, name, kernel, ramdisk, donor, cmdline):
    kp, rp, out = work / (name + '.kernel'), work / (name + '.ramdisk'), work / (name + '.img')
    kp.write_bytes(kernel)
    rp.write_bytes(ramdisk)
    run('python3', str(ROOT / 'upstream/lk2nd/lk2nd/scripts/mkbootimg'),
        '--kernel', str(kp), '--ramdisk', str(rp), '--cmdline', cmdline,
        '--base', '0x80000000', '--kernel_offset', '0x8000', '--ramdisk_offset', '0x2200000',
        '--tags_offset', '0x2000000', '--pagesize', '4096', '--output', str(out))
    data = bytearray(out.read_bytes())
    struct.pack_into('<I', data, 28, 0)  # Samsung wrapper has no second-stage address.
    struct.pack_into('<I', data, 44, donor.os_version)
    data += b'SEANDROIDENFORCE'
    verify_v0_id(data)
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor', type=pathlib.Path, required=True)
    parser.add_argument('--lk2nd-only', action='store_true')
    parser.add_argument('--mode', choices=('diagnostic', 'storage-probe', 'installed', 'recovery'),
                        default='diagnostic')
    parser.add_argument('--variant', choices=('headless', 'display', 'gpu'), default='headless')
    parser.add_argument('--root-uuid', help='Filesystem UUID required for installed mode')
    parser.add_argument('--extend-root', choices=('system',),
                        help="Append Android's system partition to the installed root")
    args = parser.parse_args()
    if args.variant in ('display', 'gpu') and (args.mode not in ('installed', 'recovery') or args.lk2nd_only):
        parser.error(f'{args.variant} variant requires installed or recovery mode and a full Linux image')
    if args.variant == 'gpu' and args.mode != 'installed':
        parser.error('GPU variant is for installed Debian; recovery stays display-only')
    variant_suffix = '-' + args.variant if args.variant != 'headless' else ''
    if args.mode == 'installed':
        if not args.root_uuid:
            parser.error('--root-uuid is required for installed mode')
        args.root_uuid = str(uuid.UUID(args.root_uuid))
    elif args.root_uuid:
        parser.error('--root-uuid only applies to installed mode')
    if args.extend_root and args.mode != 'installed':
        parser.error('--extend-root only applies to installed mode')
    os.umask(0o077)
    manifest = json.loads(args.donor.with_name('manifest.json').read_text())
    raw = args.donor.read_bytes()
    if manifest['model'] != 'SM-T825' or hashlib.sha256(raw).hexdigest() != manifest['images'][args.donor.name]['sha256']:
        raise SystemExit('Donor model/hash does not match the verified backup manifest')
    donor = parse_boot(raw)
    if (donor.kernel_addr, donor.ramdisk_addr, donor.tags_addr, donor.page_size) != (0x80008000, 0x82200000, 0x82000000, 4096):
        raise SystemExit('Donor addresses differ from the recorded SM-T825 layout')
    out = ROOT / 'private/images'
    out.mkdir(parents=True, exist_ok=True)
    report = {'model': 'SM-T825', 'hardware_tested_at_build': False, 'mode': args.mode,
              'variant': args.variant, 'images': {},
              'donor_sha256': hashlib.sha256(raw).hexdigest(),
              'lk2nd_reserved_bytes': 4194304,
              'lk2nd_force_fastboot': args.mode not in ('installed', 'recovery')}
    # The recovery partition gets its own lk2nd, which reserves the start of
    # recovery instead of boot and always boots the image after it.
    lk_stem = 'lk2nd-sm-t825' + {'installed': '-auto', 'recovery': '-recovery'}.get(args.mode, '')

    def publish(name, data):
        partial = out / (name + '.partial')
        partial.write_bytes(data)
        partial.replace(out / name)
        report['images'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        print(f'{name}: {len(data)} bytes, container validated')

    with tempfile.TemporaryDirectory() as temporary:
        work = pathlib.Path(temporary)
        lk = run('dtc', '-q', '-I', 'dtb', '-O', 'dts', str(ROOT / 'artifacts' / (lk_stem + '.dtb'))).decode()
        nodes = []
        for name in ('lk2nd', 'lk2nd-hw'):
            match = re.search(r'^\t' + name + r' \{\n.*?^\t\};\n', lk, re.S | re.M)
            if not match:
                raise SystemExit(f'No {name} node in compiled LTE bootloader DTB')
            nodes.append(match.group())
        joined = b''
        board_ids = []
        for index, dtb in enumerate(appended_dtbs(donor)):
            path = work / f'stock-{index}.dtb'
            path.write_bytes(dtb)
            ids = {key: prop(path, '/', key) for key in ('qcom,msm-id', 'qcom,board-id', 'qcom,pmic-id')}
            if ids['qcom,msm-id'] != 'f6 30001' or ids['qcom,pmic-id'] != '20009 1000c 0 0':
                raise SystemExit('Donor DTB is not this LTE SoC/PMIC combination')
            board_ids.append(ids['qcom,board-id'])
            source = run('dtc', '-q', '-I', 'dtb', '-O', 'dts', str(path)).decode()
            if re.search(r'^\tlk2nd(?:-hw)? \{', source, re.M):
                raise SystemExit('Donor already includes lk2nd nodes')
            merged = run('dtc', '-q', '-I', 'dts', '-O', 'dtb', '-p', '4096', '-',
                         input=(source + '\n/ {\n' + ''.join(nodes) + '};\n').encode())
            path.write_bytes(merged)
            for key, value in ids.items():
                if prop(path, '/', key) != value:
                    raise SystemExit('Packing changed donor DT selection IDs')
            if run('fdtget', '-t', 's', str(path), '/lk2nd', 'compatible').strip() != b'samsung,gts3llte':
                raise SystemExit('Incorrect lk2nd board identity')
            joined += merged
        if '8 5' not in board_ids:
            raise SystemExit('Donor has no rev05 device tree')
        report['donor_board_ids'] = board_ids
        empty_cpio = run('cpio', '-o', '-H', 'newc', input=b'')
        lkdata = write_boot(work, 'lk2nd', gzip.compress((ROOT / 'artifacts' / (lk_stem + '.bin')).read_bytes(), mtime=0) + joined,
                            gzip.compress(empty_cpio, mtime=0), donor, donor.cmdline)
        if len(lkdata) >= 4194304:
            raise SystemExit('Samsung lk2nd wrapper exceeds its 4 MiB reservation')
        publish(lk_stem + '.img', lkdata)
        if not args.lk2nd_only:
            release = (ROOT / 'artifacts/kernel-release.txt').read_text().strip()
            kernel = (ROOT / 'artifacts' / f'Image-{release}.gz').read_bytes()
            image = gzip.decompress(kernel)
            if image[56:60] != b'ARM\x64':
                raise SystemExit('Kernel lacks ARM64 Image header')
            # lk2nd's msm8996 forced addresses: tags at +37 MiB, initrd +39 MiB.
            offset, image_size = struct.unpack_from('<QQ', image, 8)
            if offset + max(len(image), image_size) >= 0x2500000:
                raise SystemExit('Kernel overlaps lk2nd DTB load address; revise the load layout')
            dtb_name = 'msm8996-samsung-gts3llte' + ('' if args.mode == 'diagnostic' else '-emmc') + '.dtb'
            if args.variant in ('display', 'gpu'):
                dtb_name = f'msm8996-samsung-gts3llte-{args.variant}.dtb'
            dtb = ROOT / 'artifacts' / dtb_name
            validate_linux_dtb(dtb, args.mode, args.variant)
            initrd = (out / 'diagnostic-initramfs.cpio.gz').read_bytes()
            if len(initrd) > 0xb00000:
                raise SystemExit('Initramfs exceeds its reserved 11 MiB boot window')
            cmdline = 'console=tty0 rdinit=/init clk_ignore_unused pd_ignore_unused loglevel=8 ignore_loglevel panic=30'
            cmdline += f' tabs3.mode={args.mode}'
            if args.variant in ('display', 'gpu'):
                cmdline += ' msm.prefer_mdp5=0'
                report['display_driver'] = 'dpu'
            if args.mode == 'installed':
                cmdline += f' tabs3.root_uuid={args.root_uuid}'
                report['root_uuid'] = args.root_uuid
                if args.extend_root:
                    cmdline += f' tabs3.root_extend={args.extend_root}'
                    report['root_extend'] = args.extend_root
            boot = write_boot(work, args.mode, kernel + dtb.read_bytes(), initrd, donor, cmdline)
            publish(f'tabs3-{args.mode}{variant_suffix}.img', boot)
            if args.mode in ('installed', 'recovery'):
                # Boot and recovery are both 79,691,776 bytes on SM-T825, like the donor.
                combined = lkdata.ljust(4194304, b'\0') + boot
                if len(combined) > len(raw):
                    raise SystemExit('Combined lk2nd/Debian image exceeds the original boot partition')
                verify_v0_id(combined[4194304:])
                target = 'boot' if args.mode == 'installed' else 'recovery'
                publish(f'tabs3-internal{variant_suffix}-{target}.img', combined)
            report['kernel_release'] = release
            report['device_tree'] = dtb_name
            report['kernel_uncompressed_bytes'] = len(image)
            report['diagnostic_reboot_seconds'] = None if args.mode in ('installed', 'recovery') else 300
    name = 'boot-images.json' if args.mode == 'diagnostic' else f'{args.mode}{variant_suffix}-images.json'
    (out / name).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
