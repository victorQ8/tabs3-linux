#!/usr/bin/env python3
"""Check tracked public source for accidental credentials and private artifacts.

Reports locations only, never matched secret values. This catches common
mistakes; human review is still needed for logs and device-specific data.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private key': rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',
    'password hash': rb'\$6\$[./A-Za-z0-9]+\$[./A-Za-z0-9]{70,}',
    'GitHub token': rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
    'AWS access key': rb'\bAKIA[A-Z0-9]{16}\b',
}
BLOCKED_SUFFIXES = ('.deb', '.img', '.ext4', '.tar', '.tar.gz', '.tar.xz', '.img.zst', '.cpio.gz')


def findings(name, content):
    result = []
    parts = Path(name).parts
    if parts[0] in ('private', 'artifacts', 'work') or '.ssh' in parts:
        result.append('private/build directory')
    if name.endswith(BLOCKED_SUFFIXES):
        result.append('image, package or archive should not be tracked')
    if Path(name).name in ('id_ed25519', 'id_rsa', 'dev-password.hash', 'authorized_keys'):
        result.append('personal authentication file')
    for label, pattern in PATTERNS.items():
        for match in re.finditer(pattern, content):
            result.append(f'{label} at line {content[:match.start()].count(bytes([10])) + 1}')
    return result


def main():
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    failures, checked = [], 0
    for name in filter(None, names):
        path = ROOT / name
        if not path.is_file():  # pinned submodule gitlinks are audited upstream
            continue
        checked += 1
        failures.extend(f'{name}: {reason}' for reason in findings(name, path.read_bytes()))
    if failures:
        print('\n'.join(failures), file=sys.stderr)
        return 1
    print(f'Publication check passed: {checked} tracked files; no matching private artifacts or credentials.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
