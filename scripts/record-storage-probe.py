#!/usr/bin/env python3
"""Record read-only eMMC evidence from the RAM storage-probe image over SSH.

Writes a private report on the workstation. Does not flash, mount a filesystem
on the tablet, or invent a successful receipt when a hardware check fails.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
set -eu
test "$(tr -d '\000' </proc/device-tree/model)" = 'Samsung Galaxy Tab S3 LTE (SM-T825)'
grep -qw tabs3.mode=storage-probe /proc/cmdline
for part in 28 29 47; do
    test "$(blockdev --getro /dev/mmcblk0p$part)" = 1
done
grep -qx PARTNAME=boot /sys/class/block/mmcblk0p28/uevent
grep -qx PARTNAME=recovery /sys/class/block/mmcblk0p29/uevent
grep -qx PARTNAME=userdata /sys/class/block/mmcblk0p47/uevent
test "$(blockdev --getsize64 /dev/mmcblk0p28)" = 79691776
printf 'userdata_bytes=%s\n' "$(blockdev --getsize64 /dev/mmcblk0p47)"
cid=$(cat /sys/block/mmcblk0/device/cid)
test -n "$cid"
printf 'cid_sha256=%s\n' "$(printf %s "$cid" | sha256sum | cut -d' ' -f1)"
printf 'kernel=%s\n' "$(uname -r)"
sample=$(mktemp /run/tabs3-storage.XXXXXX)
trap 'rm -f "$sample"' EXIT
for i in 1 2 3; do
    dd if=/dev/mmcblk0p28 of="$sample" bs=1048576 count=76
    test "$(wc -c <"$sample")" = 79691776
    printf 'read_sha256=%s\n' "$(sha256sum "$sample" | cut -d' ' -f1)"
done
if dmesg | grep -iE 'mmc.*(error|timeout|timed out|crc|failed)'; then
    echo 'Storage errors present; report refused.' >&2
    exit 1
fi
'''


def parse_report(output):
    fields = {}
    for line in output.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            fields.setdefault(key, []).append(value)
    hashes = fields.get('read_sha256', [])
    if len(hashes) != 3 or len(set(hashes)) != 1 or not re.fullmatch('[0-9a-f]{64}', hashes[0]):
        raise ValueError('Need three identical, complete boot-partition reads')
    if fields.get('userdata_bytes') != ['26226966016']:
        raise ValueError('Unsupported userdata geometry')
    cid = fields.get('cid_sha256', [])
    if len(cid) != 1 or not re.fullmatch('[0-9a-f]{64}', cid[0]):
        raise ValueError('Missing eMMC identity hash')
    if len(fields.get('kernel', [])) != 1:
        raise ValueError('Missing kernel version')
    return dict(schema=1, model='SM-T825', storage_test_verified=True,
                userdata_bytes=26226966016, cid_sha256=cid[0],
                read_sha256=hashes, read_bytes_each=79691776,
                kernel=fields['kernel'][0],
                timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='root@172.16.42.2')
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--known-hosts', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'private/linux-storage-test/report.json')
    args = parser.parse_args()
    result = subprocess.run(['ssh', '-i', str(args.identity), '-o', 'IdentitiesOnly=yes',
                             '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ConnectTimeout=10',
                             '-o', f'UserKnownHostsFile={args.known_hosts}', args.host, 'sh -s'],
                            input=REMOTE, text=True, capture_output=True, timeout=180, check=True)
    report = parse_report(result.stdout)
    os.umask(0o077)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    args.output.chmod(0o600)
    print(f'Passed three read-only eMMC checks; private receipt: {args.output}')


if __name__ == '__main__':
    main()
