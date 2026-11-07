#!/usr/bin/env python3
"""Install prepared Debian images to SM-T825 userdata/boot from verified TWRP.

Defaults to inspection only. --apply erases Android userdata and replaces boot.
Recovery, GPT, system and modem/calibration partitions are never written.
"""
import argparse
import datetime
import gzip
import hashlib
import json
import pathlib
import re
import shlex
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def validate_storage_report(report, cid_sha256, userdata_bytes):
    """Bind the hardware receipt to the eMMC being installed, not just its model."""
    hashes = report.get('read_sha256', [])
    if not (report.get('schema') == 1 and report.get('model') == 'SM-T825'
            and report.get('storage_test_verified') is True
            and report.get('userdata_bytes') == userdata_bytes == 26226966016
            and re.fullmatch('[0-9a-f]{64}', cid_sha256)
            and report.get('cid_sha256') == cid_sha256
            and report.get('read_bytes_each') == 79691776
            and len(hashes) == 3 and len(set(hashes)) == 1
            and re.fullmatch('[0-9a-f]{64}', hashes[0])):
        raise ValueError('A successful storage-probe receipt for this eMMC is required')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--adb-port', type=int, default=5037)
    parser.add_argument('--variant', choices=('headless', 'display'), default='display',
                        help='First install uses display by default; GPU firmware is provisioned afterward')
    parser.add_argument('--storage-report', type=pathlib.Path,
                        default=ROOT / 'private/linux-storage-test/report.json')
    parser.add_argument('--apply', action='store_true', help='Erase userdata and install the reviewed images')
    args = parser.parse_args()
    adb = ['adb', '-P', str(args.adb_port), '-s', args.serial]

    def run(command, timeout=60):
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()

    def shell(command, timeout=60):
        return run(adb + ['shell', command], timeout)

    def require(condition, message):
        if not condition:
            raise SystemExit(message)

    def verify_file(name, report):
        path = ROOT / 'private/images' / name
        require(path.stat().st_size == report['bytes'] and sha(path) == report['sha256'],
                f'Local image verification failed: {name}')
        return path

    storage = json.loads(args.storage_report.read_text())
    rootfs = json.loads((ROOT / 'private/images/installed-rootfs.json').read_text())
    suffix = '' if args.variant == 'headless' else '-' + args.variant
    boot = json.loads((ROOT / f'private/images/installed{suffix}-images.json').read_text())
    require(storage['storage_test_verified'] and storage['model'] == 'SM-T825', 'Storage test required')
    require(rootfs['model'] == boot['model'] == 'SM-T825', 'Wrong image model')
    require(boot['mode'] == 'installed' and not boot['lk2nd_force_fastboot'], 'Expected installed/autoboot image')
    require(boot.get('variant') == args.variant and not boot.get('root_extend'),
            'First install requires the selected variant and a single-partition root')
    require(rootfs['root_uuid'] == boot['root_uuid'], 'Root UUID does not match boot image')
    require(shell('getprop ro.product.model') == 'SM-T825', 'Wrong target model')
    require(shell('getprop ro.twrp.version') == '3.5.2_9-0', 'Expected verified TWRP version')
    require(shell('id -u') == '0', 'Recovery root access required')
    paths = {}
    for name, expected in [('boot', 'mmcblk0p28'), ('recovery', 'mmcblk0p29'), ('userdata', 'mmcblk0p47')]:
        path = shell(f'readlink -f /dev/block/bootdevice/by-name/{name}')
        require(path == '/dev/block/' + expected, f'Unexpected {name} partition mapping')
        paths[name] = path
    size = int(shell('blockdev --getsize64 ' + paths['userdata']))
    cid = shell('cat /sys/block/mmcblk0/device/cid')
    require(bool(re.fullmatch('[0-9a-fA-F]{32}', cid)), 'Unexpected eMMC identity')
    validate_storage_report(storage, hashlib.sha256(cid.encode()).hexdigest(), size)
    require(size == storage['userdata_bytes'] == 26226966016, 'Unexpected userdata size')
    require(int(shell('blockdev --getsize64 ' + paths['boot'])) == 79691776, 'Unexpected boot size')
    recovery_hash = shell('sha256sum ' + paths['recovery']).split()[0]
    require(recovery_hash == '4bfffec62f55ba3e178165844697c1bb7a844c42ce5f132bf26a0737fe3a58dc',
            'Recovery no longer matches the tested backup')
    # Validate every local artifact before --apply pauses the recovery UI.
    compressed_name = 'tabs3-debian-rootfs.ext4.gz'
    root_name = 'tabs3-debian-rootfs.ext4'
    boot_name = f'tabs3-internal{suffix}-boot.img'
    compressed = verify_file(compressed_name, rootfs['images'][compressed_name])
    verify_file(root_name, rootfs['images'][root_name])
    boot_image = verify_file(boot_name, boot['images'][boot_name])
    require(rootfs['images'][root_name]['bytes'] < size, 'Root filesystem exceeds userdata')
    require(rootfs['images'][root_name]['bytes'] % 1048576 == 0,
            'Root image must have a whole-MiB length')
    require(boot_image.stat().st_size <= 79691776, 'Boot image exceeds partition')
    with gzip.open(compressed, 'rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(digest == rootfs['images'][root_name]['sha256'], 'Compressed rootfs content mismatch')
    if args.apply:
        # TWRP can mount /data when the user allows modifications. Pause its
        # verified UI/MTP processes so nothing remounts a filesystem mid-write.
        # adbd is a separate process and remains available for reboot/recovery.
        pids = shell('pidof recovery').split()
        require(bool(pids) and len(pids) <= 4, 'Unexpected recovery process list')
        for pid in pids:
            require(pid.isdigit() and shell(f'readlink /proc/{pid}/exe') == '/sbin/recovery',
                    'Unexpected recovery executable')
        for pid in pids:
            shell('kill -STOP ' + pid)
        (ROOT / 'private/twrp-paused-pids.json').write_text(json.dumps(pids) + '\n')
        shell('sync')
        mounted = []
        for line in shell('cat /proc/mounts').splitlines():
            source, mountpoint = line.split()[:2]
            if source.startswith('/dev/') and shell('readlink -f ' + shlex.quote(source)) == paths['userdata']:
                mounted.append(mountpoint)
        for mountpoint in sorted(mounted, key=lambda x: (x.count('/'), x), reverse=True):
            shell('umount ' + shlex.quote(mountpoint))
        print('Recovery interface paused; userdata unmounted for installation.', flush=True)
    # Refuse to overwrite mounted userdata or an active encrypted mapping.
    require(not shell('ls -A /sys/class/block/mmcblk0p47/holders'), 'Userdata still has an active device mapping')
    mounts = shell('cat /proc/mounts')
    for line in mounts.splitlines():
        source, mountpoint = line.split()[:2]
        if source.startswith('/dev/'):
            resolved = shell('readlink -f ' + shlex.quote(source))
            require(resolved not in (paths['userdata'], paths['boot']), 'Target partition is mounted')
        require(mountpoint != '/data' and not mountpoint.startswith('/data/'), 'Android data is mounted')
    print('Verified SM-T825, TWRP, untouched recovery, storage test and image hashes.', flush=True)
    print('Install target: existing userdata (26,226,966,016 bytes) and boot; Android data will be erased.', flush=True)
    if not args.apply:
        print('Inspection only; no writes requested.')
        return

    session_path = ROOT / 'private/internal-install-session.json'
    session = {'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'model': 'SM-T825', 'root_uuid': rootfs['root_uuid'],
               'userdata_complete': False, 'boot_complete': False,
               'android_userdata_erased': False}

    def save():
        session_path.write_text(json.dumps(session, indent=2) + '\n')
        session_path.chmod(0o600)

    save()
    # Stage and verify both compressed artifacts in recovery RAM before writing.
    for path, name, report in [(compressed, '/tmp/tabs3-rootfs.ext4.gz', rootfs['images'][compressed_name]),
                               (boot_image, '/tmp/tabs3-internal-boot.img', boot['images'][boot_name])]:
        run(adb + ['push', str(path), name], 180)
        require(shell('sha256sum ' + name).split()[0] == report['sha256'], 'Transfer hash mismatch')
    print('Both transfers verified. Writing Debian root filesystem to userdata.', flush=True)
    session['android_userdata_erased'] = True  # A failed/partial write is also destructive.
    save()
    shell('gzip -dc /tmp/tabs3-rootfs.ext4.gz | dd of=' + paths['userdata'] + ' bs=1048576', 600)
    shell('sync', 120)
    length = rootfs['images'][root_name]['bytes']
    require(length % 1048576 == 0, 'Root image must have a whole-MiB length')
    # This recovery's 32-bit toybox head wraps a 4 GiB byte count to zero.
    # dd with a bounded block count correctly reads the complete image.
    require(shell(f'dd if={paths["userdata"]} bs=1048576 count={length // 1048576} | sha256sum', 600).split()[0]
            == rootfs['images'][root_name]['sha256'], 'Rootfs readback hash mismatch; boot was not changed')
    session['userdata_complete'] = True
    session['userdata_sha256'] = rootfs['images'][root_name]['sha256']
    save()
    print('Debian rootfs readback verified. Writing combined lk2nd/Linux boot image.', flush=True)
    shell('dd if=/tmp/tabs3-internal-boot.img of=' + paths['boot'] + ' bs=4096', 120)
    shell('sync', 120)
    length = boot['images'][boot_name]['bytes']
    require(shell(f'head -c {length} {paths["boot"]} | sha256sum', 120).split()[0]
            == boot['images'][boot_name]['sha256'], 'Boot readback hash mismatch')
    require(shell('sha256sum ' + paths['recovery']).split()[0] == recovery_hash, 'Recovery changed unexpectedly')
    session['boot_complete'] = True
    session['boot_sha256'] = boot['images'][boot_name]['sha256']
    session['recovery_unchanged'] = True
    save()
    print('Boot and rootfs verified; recovery unchanged. Installation complete; reboot separately.', flush=True)
    print('The TWRP interface remains paused until reboot to prevent remounting userdata.', flush=True)


if __name__ == '__main__':
    main()
