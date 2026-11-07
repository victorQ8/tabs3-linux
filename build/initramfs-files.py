#!/usr/bin/env python3
"""Select Debian ARM64 binaries and recursively copy their ELF dependencies."""
import os
import pathlib
import re
import shutil
import subprocess

source = pathlib.Path('/build/rootfs')
dest = pathlib.Path('/build/initramfs')
copied = set()


def copy_binary(name):
    if name in copied:
        return
    copied.add(name)
    src = source / name.lstrip('/')
    if not src.exists():
        raise SystemExit(f'Missing Debian binary: {name}')
    target = dest / name.lstrip('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, target, follow_symlinks=True)
    target.chmod(src.stat().st_mode & 0o777)
    elf = subprocess.check_output(['aarch64-linux-gnu-readelf', '-l', '-d', str(target)], text=True)
    for interpreter in re.findall(r'Requesting program interpreter: ([^\]]+)', elf):
        copy_binary(interpreter)
    for lib in re.findall(r'\(NEEDED\).*\[([^\]]+)\]', elf):
        for directory in ('usr/lib/aarch64-linux-gnu', 'lib/aarch64-linux-gnu', 'usr/lib', 'lib'):
            candidate = source / directory / lib
            if candidate.exists():
                copy_binary('/' + directory + '/' + lib)
                break
        else:
            raise SystemExit(f'Missing dependency {lib} for {name}')


def copy_modules(roots):
    """Copy display/input modules and their dependencies, uncompressed for busybox."""
    package = pathlib.Path('/project/artifacts') / f"linux-tabs3_{os.environ['KERNEL_PACKAGE_VERSION']}_arm64.deb"
    unpacked = pathlib.Path('/build/kernel-package')
    subprocess.run(['dpkg-deb', '-x', str(package), str(unpacked)], check=True)
    (release,) = [d.name for d in (unpacked / 'lib/modules').iterdir()]
    tree = unpacked / 'lib/modules' / release
    deps = {}
    for line in (tree / 'modules.dep').read_text().splitlines():
        module, _, needed = line.partition(':')
        deps[module] = needed.split()
    names = {pathlib.Path(m).name.split('.ko')[0].replace('-', '_'): m for m in deps}
    todo = [names[r.replace('-', '_')] for r in roots]
    done = set()
    while todo:
        module = todo.pop()
        if module in done:
            continue
        done.add(module)
        todo += deps[module]
        target = dest / 'usr/lib/modules' / release / module.removesuffix('.zst')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('wb') as out:
            subprocess.run(['zstd', '-dc', str(tree / module)], stdout=out, check=True)
    shutil.copy(tree / 'modules.builtin', dest / 'usr/lib/modules' / release)
    shutil.copy(tree / 'modules.order', dest / 'usr/lib/modules' / release)
    subprocess.run(['depmod', '-b', str(dest), release], check=True)
    print(f'Copied {len(done)} display and input modules for {release}')


for binary in ('/usr/bin/busybox', '/usr/bin/ssh-keygen', '/usr/sbin/sshd',
               '/usr/sbin/blkid', '/usr/sbin/dmsetup', '/usr/bin/setfont',
               '/usr/sbin/e2fsck', '/usr/sbin/resize2fs', '/usr/sbin/dumpe2fs', '/usr/sbin/debugfs',
               '/usr/lib/openssh/sshd-session', '/usr/lib/openssh/sshd-auth'):
    copy_binary(binary)
print('Copied Debian ARM64 binaries and dependencies:', len(copied))
copy_modules(['msm', 'panel-samsung-ams968hh01', 'evdev'])

# Recovery touch screen (scripts/build-recovery-ui.sh); libraries come from the rootfs.
ui = pathlib.Path('/project/artifacts/tabs3-recovery-ui')
shutil.copyfile(ui, source / 'usr/bin/tabs3-recovery-ui')
(source / 'usr/bin/tabs3-recovery-ui').chmod(0o755)
copy_binary('/usr/bin/tabs3-recovery-ui')
