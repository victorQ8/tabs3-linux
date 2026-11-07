#!/bin/bash
set -euo pipefail
registration="tabs3-initramfs-$$"
cleanup() {
    [[ ! -e "/binfmt/$registration" ]] || echo -1 > "/binfmt/$registration"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p /build/rootfs /build/initramfs
tar -xJf /project/artifacts/tabs3-trixie-arm64-rootfs.tar.xz -C /build/rootfs
rd=/build/initramfs
mkdir -p "$rd"/{bin,dev,proc,sys,run,tmp,root/.ssh,etc,usr/bin,usr/lib,var/empty}
ln -s usr/lib "$rd/lib"
python3 /project/build/initramfs-files.py
install -m 755 /project/initramfs/init "$rd/init"
install -D -m 644 /project/initramfs/rootmap.sh "$rd/usr/lib/tabs3/rootmap.sh"
install -m 644 /project/initramfs/rootcheck.sh "$rd/usr/lib/tabs3/rootcheck.sh"
install -m 644 /project/initramfs/e2fsck.conf "$rd/etc/e2fsck.conf"
install -m 644 /project/initramfs/fastboot-request.sh "$rd/usr/lib/tabs3/fastboot-request.sh"
install -m 755 /project/initramfs/tabs3-recovery "$rd/usr/sbin/tabs3-recovery"
install -m 755 /project/artifacts/tabs3-reboot-recovery "$rd/usr/sbin/tabs3-reboot-recovery"
mkdir -p "$rd/usr/share/tabs3" "$rd/mnt"
zcat /build/rootfs/usr/share/consolefonts/Uni2-Terminus32x16.psf.gz > "$rd/usr/share/tabs3/console-32x16.psf"
install -m 644 /project/initramfs/sshd_config "$rd/etc/sshd_config"
install -m 600 /authorized_keys "$rd/root/.ssh/authorized_keys"
chmod 700 "$rd/root" "$rd/root/.ssh"
chmod 1777 "$rd/tmp"
printf 'root:x:0:0:root:/root:/bin/sh\nsshd:x:100:100:sshd:/var/empty:/bin/false\n' > "$rd/etc/passwd"
printf 'root:x:0:\nsshd:x:100:\n' > "$rd/etc/group"
# NP is an unmatchable crypt hash, without the account-lock marker that rejects
# public keys when UsePAM=no. All password and interactive auth is disabled.
printf 'root:NP:20000:0:99999:7:::\nsshd:!:20000:0:99999:7:::\n' > "$rd/etc/shadow"
chmod 600 "$rd/etc/shadow"
printf 'passwd: files\ngroup: files\nshadow: files\nhosts: files\n' > "$rd/etc/nsswitch.conf"
printf '127.0.0.1 localhost\n' > "$rd/etc/hosts"
ln -s /usr/bin/busybox "$rd/bin/sh"
ln -s /usr/bin/busybox "$rd/bin/false"
ln -s /proc/mounts "$rd/etc/mtab"
mknod -m 600 "$rd/dev/console" c 5 1
mknod -m 666 "$rd/dev/null" c 1 3
mknod -m 666 "$rd/dev/urandom" c 1 9
qemu-aarch64 -L "$rd" "$rd/usr/bin/busybox" true
python3 - "$registration" <<'PY'
import pathlib, sys
spec = next(line for line in pathlib.Path('/usr/lib/binfmt.d/qemu-aarch64.conf').read_text().splitlines() if line.startswith(':'))
parts = spec.split(':')
assert len(parts) == 8
parts[1], parts[6], parts[7] = sys.argv[1], '/usr/bin/qemu-aarch64', 'F'
pathlib.Path('/binfmt/register').write_text(':'.join(parts))
PY
mkdir -p "$rd/run/sshd"
chroot "$rd" /usr/bin/busybox --install -s /bin
chroot "$rd" /usr/bin/ssh-keygen -q -t ed25519 -N '' -f /run/ssh_host_ed25519_key
chroot "$rd" /usr/sbin/sshd -t -f /etc/sshd_config
chroot "$rd" /usr/sbin/sshd -T -f /etc/sshd_config > /out/diagnostic-sshd-effective.conf
# Real ARM64 SSH login in the container catches missing session helpers,
# account locking and shared libraries. Test keys never enter the final image.
qemu-aarch64 -L /build/rootfs /build/rootfs/usr/bin/ssh-keygen -q -t ed25519 -N '' -f /build/test-user-key
cp /build/test-user-key.pub "$rd/root/.ssh/authorized_keys"
sed -e 's/Port 22/Port 2222/' -e 's/ListenAddress 172.16.42.2/ListenAddress 127.0.0.1/' "$rd/etc/sshd_config" > "$rd/etc/test-sshd_config"
chroot "$rd" /usr/sbin/sshd -D -e -f /etc/test-sshd_config >/build/sshd-test.log 2>&1 &
server_pid=$!
sleep 1
if ! result=$(timeout 20 qemu-aarch64 -L /build/rootfs /build/rootfs/usr/bin/ssh \
    -p 2222 -i /build/test-user-key -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/build/known_hosts root@127.0.0.1 /usr/bin/busybox id -u); then
    cat /build/sshd-test.log >&2
    exit 1
fi
[[ "$result" == 0 ]]
kill "$server_pid"
wait "$server_pid" || true
install -m 600 /authorized_keys "$rd/root/.ssh/authorized_keys"
rm -f "$rd/etc/test-sshd_config" "$rd"/run/ssh_host_ed25519_key* "$rd/run/sshd.pid"
echo 'Authenticated ARM64 SSH session passed in isolated container.'
cd "$rd"
find . -print0 | LC_ALL=C sort -z | cpio --null -o -H newc --owner=0:0 2>/dev/null | gzip -9n > /out/diagnostic-initramfs.cpio.gz.partial
mv /out/diagnostic-initramfs.cpio.gz.partial /out/diagnostic-initramfs.cpio.gz
chmod 600 /out/diagnostic-initramfs.cpio.gz /out/diagnostic-sshd-effective.conf
chown "$OUTPUT_UID:$OUTPUT_GID" /out/diagnostic-initramfs.cpio.gz /out/diagnostic-sshd-effective.conf
echo 'Diagnostic initramfs built; Debian ARM64 binaries and SSH configuration checked under QEMU.'
