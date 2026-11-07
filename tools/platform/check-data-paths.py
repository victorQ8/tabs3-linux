#!/usr/bin/env python3
"""Bounded SM-T825 sensor reads and optional root/SD scratch-file checks.

Run on the tablet as root. No raw block writes, driver rebinding, service
stops or camera/audio capture. Storage writes require --storage; only files
created by this process are removed. Output is evidence, not a release pass.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError as error:
        return {'error': str(error)}


def storage(directory, expected_device):
    result = {'directory': directory, 'passed': False}
    try:
        device = subprocess.check_output(
            ['findmnt', '-n', '-o', 'SOURCE', '--target', directory],
            text=True, timeout=5).strip()
        result['source'] = device
        if device != expected_device:
            raise RuntimeError('Unexpected filesystem; scratch test refused')
        fs = os.statvfs(directory)
        if fs.f_bavail * fs.f_frsize < 512 * 1024**2:
            raise RuntimeError('Less than 512 MiB available; scratch test refused')
        start = time.monotonic()
        expected = hashlib.sha256()
        # TemporaryFile is unlinked at creation, including on interruption.
        with tempfile.TemporaryFile(dir=directory, prefix='.tabs3-driver-check-') as f:
            for _ in range(32):
                data = os.urandom(1024**2)
                assert f.write(data) == len(data)
                expected.update(data)
            f.flush()
            os.fsync(f.fileno())
            written = time.monotonic()
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
            f.seek(0)
            actual, count = hashlib.sha256(), 0
            while data := f.read(1024**2):
                actual.update(data)
                count += len(data)
            result.update(bytes=count, expected_sha256=expected.hexdigest(),
                          readback_sha256=actual.hexdigest(),
                          write_fsync_seconds=round(written-start, 3),
                          read_seconds=round(time.monotonic()-written, 3),
                          passed=count == 32*1024**2 and actual.digest() == expected.digest())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        result['error'] = str(error)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', action='store_true', help='write/fsync/read two 32 MiB temporary files')
    args = parser.parse_args()
    if b'samsung,gts3llte\0' not in Path('/proc/device-tree/compatible').read_bytes():
        raise SystemExit('This check is specific to the SM-T825')
    report = {'schema': 1, 'time_utc': datetime.now(timezone.utc).isoformat(),
              'kernel': os.uname().release, 'all_drivers_qualified': False,
              'sensor_readings': {}, 'storage': [],
              'limits': ['Stationary sensor reads do not validate calibration or physical response.',
                         'Scratch checks cover 32 MiB per filesystem, not all media or power-loss recovery.',
                         'DONTNEED requests cache eviction; this is not a direct-I/O or endurance benchmark.']}
    report['remoteproc'] = {read(d/'name'): read(d/'state')
                           for d in Path('/sys/class/remoteproc').glob('remoteproc*')}
    report['deferred_probes'] = read('/sys/kernel/debug/devices_deferred')
    report['failed_services'] = subprocess.check_output(
        ['systemctl', '--failed', '--no-legend', '--plain'], text=True, timeout=10).strip()
    battery = Path('/sys/class/power_supply/sm5705-battery')
    report['battery'] = {n: read(battery/n) for n in ('capacity', 'current_now', 'voltage_now', 'temp')}
    report['thermals_mc'] = {read(d/'type'): read(d/'temp')
                             for d in Path('/sys/class/thermal').glob('thermal_zone*')}
    for d in sorted(Path('/sys/bus/iio/devices').glob('iio:device*')):
        # The PMIC ADC is represented by the thermal readings above. Sample
        # the four SLPI sensors and the LTE proximity device explicitly.
        name = read(d/'name')
        if not isinstance(name, str) or not (name.startswith('qcom-smgr-') or name == 'sx9310'):
            continue
        channels = sorted(d.glob('in_*_raw'))
        samples = []
        for _ in range(3):
            samples.append({p.name: read(p) for p in channels})
            time.sleep(0.25)
        report['sensor_readings'][name] = {
            'scale': {p.name: read(p) for p in d.glob('in_*_scale')}, 'samples': samples,
            'all_reads_numeric': bool(channels) and all(
                isinstance(v, str) and v.lstrip('-').isdigit() for s in samples for v in s.values())}
    if args.storage:
        capacity, temp = report['battery']['capacity'], report['battery']['temp']
        if (not isinstance(capacity, str) or not capacity.isdigit() or int(capacity) < 20
                or not isinstance(temp, str) or not temp.lstrip('-').isdigit()
                or not 0 <= int(temp) < 400):
            report['storage_refused'] = 'Battery telemetry missing, below 20%, or outside 0–40 C'
        else:
            report['storage'] = [storage('/var/tmp', '/dev/mapper/tabs3root'),
                                 storage('/srv', '/dev/mmcblk1p1')]
    expected_sensors = {'qcom-smgr-accel', 'qcom-smgr-gyro', 'qcom-smgr-mag',
                        'qcom-smgr-light', 'sx9310'}
    report['missing_sensors'] = sorted(expected_sensors - report['sensor_readings'].keys())
    print(json.dumps(report, indent=2))
    return int(bool(report['failed_services']) or bool(report.get('storage_refused'))
               or bool(report['missing_sensors'])
               or any(not v['all_reads_numeric'] for v in report['sensor_readings'].values())
               or any(not v['passed'] for v in report['storage']))


if __name__ == '__main__':
    raise SystemExit(main())
