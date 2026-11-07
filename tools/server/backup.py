#!/usr/bin/env python3
"""Private off-device configuration/user backup plus exact boot/recovery images.

No tablet writes. This is not a full root image or a transactional database
backup. Every archive member is read back, selected configuration files are
restored into an isolated directory and compared to the device's hashes.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ['etc', 'home', 'root', 'var/lib/tabs3', 'var/lib/tabs3-dashboard',
          'var/lib/iwd', 'var/lib/bluetooth', 'var/lib/alsa',
          'srv/games/Saves', 'srv/games/States', 'srv/games/BIOS']
APPLIANCE_SCOPES = ['etc', 'home/dev/.ssh', 'root/.ssh', 'var/lib/tabs3',
                    'var/lib/tabs3-dashboard', 'var/lib/iwd', 'var/lib/bluetooth',
                    'var/lib/alsa']
RESTORE_FILES = ['etc/fstab', 'etc/tabs3-release', 'etc/tabs3/dashboard.conf',
                 'etc/tabs3/battery.conf', 'etc/ssh/sshd_config',
                 'etc/ssh/sshd_config.d/00-tabs3-server.conf']
PREFLIGHT = r'''
import hashlib, json, os, pathlib, subprocess
root = pathlib.Path('/')
compatible = pathlib.Path('/proc/device-tree/compatible').read_bytes().split(b'\0')
assert b'samsung,gts3llte' in compatible, 'wrong board'
partitions = {}
for label in ('boot', 'recovery'):
    path = pathlib.Path('/dev/disk/by-partlabel') / label
    device = path.resolve(strict=True)
    assert device.is_block_device(), 'not a block device'
    fields = dict(line.split('=', 1) for line in (pathlib.Path('/sys/class/block') / device.name / 'uevent').read_text().splitlines() if '=' in line)
    assert fields['PARTNAME'] == label, 'partition identity mismatch'
    size = int((pathlib.Path('/sys/class/block') / device.name / 'size').read_text()) * 512
    assert size == 79691776, 'unexpected partition size'
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    partitions[label] = dict(bytes=size, sha256=digest)
files = {}
for name in RESTORE_FILES:
    path = root / name
    if path.is_file(): files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
scopes = [p for p in SCOPES if (root / p).exists()]
sizes = subprocess.check_output(['du', '--summarize', '--apparent-size', '--block-size=1',
    '--one-file-system', *('/' + p for p in scopes)], text=True)
estimated_source_bytes = sum(int(line.split()[0]) for line in sizes.splitlines())
print(json.dumps(dict(partitions=partitions, restore_files=files, scopes=scopes,
    estimated_source_bytes=estimated_source_bytes,
    boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    packages=subprocess.check_output(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\t${db:Status-Status}\n'], text=True),
    kernel=subprocess.check_output(['uname', '-a'], text=True).strip())))
'''


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def check_space(metadata, available):
    # Budget the uncompressed source plus exact partition copies and 1 GiB
    # headroom. Never assume a large archive will compress well.
    needed = metadata['estimated_source_bytes'] + sum(p['bytes'] for p in metadata['partitions'].values())
    if available < needed + 1024 ** 3:
        raise RuntimeError(f'Insufficient backup space: need {needed + 1024 ** 3} bytes including headroom; have {available}')


def verify_archive(path, expected):
    restored, count, total = {}, 0, 0
    with tempfile.TemporaryDirectory(prefix='tabs3-restore-', dir=path.parent) as directory:
        with tarfile.open(path, 'r|gz') as archive:
            for member in archive:
                # Never extract archive paths, devices or links onto the host.
                if not member.isfile():
                    continue
                source = archive.extractfile(member)
                target = None
                if member.name in expected:
                    target = (Path(directory) / str(len(restored))).open('wb')
                try:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        total += len(block)
                        if target:
                            target.write(block)
                finally:
                    if target:
                        target.close()
                if member.name in expected:
                    restored[member.name] = digest(Path(target.name))
                count += 1
    if restored != expected:
        raise RuntimeError('Restored configuration does not match the device snapshot')
    return dict(files_read=count, uncompressed_file_bytes=total,
                configuration_files_restored=len(restored))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='dev@172.16.42.2')
    parser.add_argument('--fallback-host', help='alternate address for the same pinned device key')
    parser.add_argument('--identity', type=Path, default=ROOT / 'private/id_ed25519')
    parser.add_argument('--known-hosts', type=Path, default=ROOT / 'private/installed-known-hosts')
    parser.add_argument('--host-key-alias', default='172.16.42.2')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profile', choices=('full-users', 'appliance'), default='full-users')
    parser.add_argument('--keep', type=int, help='keep this many verified appliance backups (minimum 2)')
    args = parser.parse_args()
    if args.keep is not None and (args.keep < 2 or args.profile != 'appliance'):
        parser.error('--keep requires --profile appliance and a value of at least 2')
    os.umask(0o077)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    prefix = 'appliance-' if args.profile == 'appliance' else 'production-'
    output = args.output or ROOT / 'private/backups' / (prefix + timestamp)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    ssh = ['ssh', '-i', str(args.identity), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5',
           '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
           '-o', f'HostKeyAlias={args.host_key_alias}',
           '-o', f'UserKnownHostsFile={args.known_hosts}', args.host]
    scopes = APPLIANCE_SCOPES if args.profile == 'appliance' else SCOPES
    script = 'SCOPES = ' + repr(scopes) + '\nRESTORE_FILES = ' + repr(RESTORE_FILES) + '\n' + PREFLIGHT
    try:
        metadata = json.loads(subprocess.check_output(ssh + ['sudo -n python3 -'], input=script.encode(), timeout=90))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if not args.fallback_host:
            raise
        ssh[-1] = args.fallback_host
        metadata = json.loads(subprocess.check_output(ssh + ['sudo -n python3 -'], input=script.encode(), timeout=90))
    check_space(metadata, shutil.disk_usage(output).free)
    (output / 'snapshot.json').write_text(json.dumps(metadata, indent=2) + '\n')

    def fetch(name, command, timeout, compress=False):
        partial = output / (name + '.partial')
        with partial.open('xb') as out, (output / (name + '.stderr')).open('xb') as err:
            if not compress:
                subprocess.run(ssh + [command], stdout=out, stderr=err, check=True, timeout=timeout)
            else:
                # Compress on the PC. Already-compressed artwork made gzip on
                # the tablet slow and needlessly loaded its battery/CPU.
                source = subprocess.Popen(ssh + [command], stdout=subprocess.PIPE, stderr=err)
                compressor = subprocess.Popen(['gzip', '-1'], stdin=source.stdout, stdout=out, stderr=err)
                source.stdout.close()
                try:
                    status = source.wait(timeout=timeout)
                    compressed = compressor.wait(timeout=60)
                    if status or compressed:
                        raise RuntimeError(f'Backup stream failed: ssh={status}, gzip={compressed}')
                finally:
                    for process in (source, compressor):
                        if process.poll() is None:
                            process.kill()
                            process.wait()
            out.flush()
            os.fsync(out.fileno())
        path = output / name
        partial.rename(path)
        return path

    images = {}
    for label, expected in metadata['partitions'].items():
        path = fetch(label + '.img', f'sudo -n dd if=/dev/disk/by-partlabel/{label} bs=1048576 status=none', 180)
        actual = dict(bytes=path.stat().st_size, sha256=digest(path))
        if actual != expected:
            raise RuntimeError(label + ' backup differs from tablet')
        images[path.name] = actual
        print(f'{label}: exact partition backup verified', flush=True)
    command = ['sudo', '-n', 'nice', '-n', '15', 'tar', '--create', '--file=-',
               '--numeric-owner', '--acls', '--xattrs', '--one-file-system', '--directory=/',
               '--exclude=home/*/.cache', '--exclude=root/.cache',
               '--exclude=var/lib/tabs3/rtc-offset', *metadata['scopes']]
    archive = fetch('configuration-users.tar.gz', shlex.join(command), 1800, compress=True)
    verification = verify_archive(archive, metadata['restore_files'])
    images[archive.name] = dict(bytes=archive.stat().st_size, sha256=digest(archive))
    result = dict(created_utc=timestamp, status='verified', profile=args.profile, artifacts=images,
                  archive_verification=verification, scopes=metadata['scopes'],
                  exclusions=['home/*/.cache', 'root/.cache', 'var/lib/tabs3/rtc-offset'],
                  limitations=['Live file copy; not transaction-consistent application data',
                               'Not a full Debian root filesystem image',
                               'Power-off recovery/whole-device restore not exercised'])
    (output / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    if args.keep:
        # Rotate only our verified appliance backups, after the new one passes.
        # Full user backups, partial runs and all unrelated directories stay.
        verified = []
        for path in output.parent.glob('appliance-*'):
            if path.is_symlink() or not path.is_dir():
                continue
            try:
                record = json.loads((path / 'manifest.json').read_text())
                if record.get('status') == 'verified' and record.get('profile') == 'appliance':
                    verified.append(path)
            except (OSError, ValueError):
                pass
        for expired in sorted(verified, reverse=True)[args.keep:]:
            shutil.rmtree(expired)
    print(f'Backup verified: {output}', flush=True)


if __name__ == '__main__':
    main()
