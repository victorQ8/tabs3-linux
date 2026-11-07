#!/bin/bash
set -euo pipefail
registration="tabs3-aarch64-$$"
partial=/out/tabs3-trixie-arm64-rootfs.partial.tar.xz
cleanup() {
    if [[ -e "/binfmt/$registration" ]]; then
        echo -1 > "/binfmt/$registration"
    fi
    rm -f "$partial"
    chown "$OUTPUT_UID:$OUTPUT_GID" /out/tabs3-* 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Reuse Debian's maintained ELF magic/mask; register only ARM64 and remove it
# afterwards. Existing host handlers are neither disabled nor overwritten.
python3 - "$registration" <<'PY'
import pathlib, sys
lines = pathlib.Path('/usr/lib/binfmt.d/qemu-aarch64.conf').read_text().splitlines()
spec = next(line for line in lines if line.startswith(':'))
parts = spec.split(':')
assert len(parts) == 8, parts
parts[1] = sys.argv[1]
parts[6] = '/usr/bin/qemu-aarch64'
parts[7] = 'F'
pathlib.Path('/binfmt/register').write_text(':'.join(parts))
PY
packages=systemd-sysv,udev,dbus,systemd-resolved,systemd-timesyncd,openssh-server,sudo,ca-certificates,iproute2,iputils-ping,kmod,less,nano,procps,initramfs-tools,busybox,dmsetup,e2fsprogs,iwd,bluez,firmware-atheros,wireless-regdb,iw,kbd,console-setup-linux
mmdebstrap --mode=root --architectures=arm64 --variant=minbase \
    --include="$packages" \
    --customize-hook=/project/build/customize-rootfs.sh \
    trixie "$partial" \
    'deb https://deb.debian.org/debian trixie main non-free-firmware' \
    'deb https://deb.debian.org/debian trixie-updates main non-free-firmware' \
    'deb https://security.debian.org/debian-security trixie-security main non-free-firmware'
mv "$partial" /out/tabs3-trixie-arm64-rootfs.tar.xz
cd /out
sha256sum tabs3-trixie-arm64-rootfs.tar.xz "tabs3-base_${TABS3_BASE_VERSION:?}_all.deb" > tabs3-SHA256SUMS
