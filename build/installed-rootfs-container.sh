#!/bin/bash
set -euo pipefail
umask 022
registration="tabs3-installed-$$"
root=/build/rootfs
cleanup() {
    [[ ! -e "/binfmt/$registration" ]] || echo -1 > "/binfmt/$registration"
    if mountpoint -q "$root/proc"; then umount "$root/proc" || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$root"
tar -xJf /project/artifacts/tabs3-trixie-arm64-rootfs.tar.xz -C "$root"
python3 - "$registration" <<'PY'
import pathlib, sys
spec = next(line for line in pathlib.Path('/usr/lib/binfmt.d/qemu-aarch64.conf').read_text().splitlines() if line.startswith(':'))
parts = spec.split(':')
assert len(parts) == 8
parts[1], parts[6], parts[7] = sys.argv[1], '/usr/bin/qemu-aarch64', 'F'
pathlib.Path('/binfmt/register').write_text(':'.join(parts))
PY
mount -t proc proc "$root/proc"
for node in 'null 1 3' 'zero 1 5' 'random 1 8' 'urandom 1 9'; do
    read -r name major minor <<<"$node"
    [[ -e "$root/dev/$name" ]] || mknod -m 666 "$root/dev/$name" c "$major" "$minor"
done
# Prevent maintainer scripts from trying to start daemons in the build chroot.
printf '#!/bin/sh\nexit 101\n' > "$root/usr/sbin/policy-rc.d"
chmod 755 "$root/usr/sbin/policy-rc.d"
rm "$root/etc/resolv.conf"
cp /etc/resolv.conf "$root/etc/resolv.conf"
chroot "$root" apt-get update
chroot "$root" apt-get install -y --no-install-recommends e2fsprogs
install -m 644 "/project/artifacts/tabs3-base_${TABS3_BASE_VERSION:?}_all.deb" "$root/tmp/base.deb"
install -m 644 "/project/artifacts/linux-tabs3_${KERNEL_PACKAGE_VERSION:?}_arm64.deb" "$root/tmp/kernel.deb"
chroot "$root" dpkg -i /tmp/base.deb /tmp/kernel.deb
rm "$root/tmp/base.deb" "$root/tmp/kernel.deb" "$root/usr/sbin/policy-rc.d" "$root/etc/resolv.conf"
ln -s /run/systemd/resolve/stub-resolv.conf "$root/etc/resolv.conf"
uuid=$(python3 -c 'import uuid; print(uuid.uuid4())')
printf 'UUID=%s / ext4 defaults,noatime 0 1\n' "$uuid" > "$root/etc/fstab"
printf '%s\n' "$uuid" > "$root/etc/tabs3-root-uuid"
install -m 755 /project/build/grow-rootfs.sh "$root/usr/libexec/tabs3-grow-rootfs"
install -m 644 /project/build/tabs3-grow-rootfs.service "$root/usr/lib/systemd/system/"
chroot "$root" systemctl enable tabs3-grow-rootfs.service
chroot "$root" systemctl set-default multi-user.target
test "$(chroot "$root" dpkg --print-architecture)" = arm64
test -z "$(chroot "$root" dpkg --audit)"
chroot "$root" visudo -c
mkdir -p "$root/run/sshd"
chroot "$root" ssh-keygen -A
chroot "$root" /usr/sbin/sshd -t
chroot "$root" /usr/sbin/sshd -T > /out/installed-sshd-effective.conf
cp "$root/home/dev/.ssh/authorized_keys" /build/authorized_keys
qemu-aarch64 -L "$root" "$root/usr/bin/ssh-keygen" -q -t ed25519 -N '' -f /build/test-key
install -m 600 -o 1000 -g 1000 /build/test-key.pub "$root/home/dev/.ssh/authorized_keys"
chroot "$root" /usr/sbin/sshd -D -e -p 2223 -o ListenAddress=127.0.0.1 -o PidFile=/run/sshd-build.pid >/build/sshd-test.log 2>&1 &
server_pid=$!
sleep 1
if ! result=$(timeout 30 qemu-aarch64 -L "$root" "$root/usr/bin/ssh" \
    -p 2223 -i /build/test-key -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/build/known_hosts dev@127.0.0.1 id -u); then
    cat /build/sshd-test.log >&2
    exit 1
fi
[[ "$result" == 1000 ]]
kill "$server_pid"
wait "$server_pid" || true
install -m 600 -o 1000 -g 1000 /build/authorized_keys "$root/home/dev/.ssh/authorized_keys"
rm -f "$root"/etc/ssh/ssh_host_* "$root/run/sshd-build.pid"
rm -rf "$root/run/sshd" "$root/var/lib/apt/lists/"* "$root/var/cache/apt/archives/"*.deb
: > "$root/etc/machine-id"
chroot "$root" dpkg-query -W > /out/installed-packages.tsv
umount "$root/proc"
image=/out/tabs3-debian-rootfs.ext4
truncate -s 4G "$image.partial"
# Avoid newer ext4 features unsupported by older recovery tools. Linux itself
# supports them, but recovery must remain able to inspect this filesystem.
mke2fs -q -t ext4 -L tabs3-debian -U "$uuid" -m 1 \
    -O '^orphan_file,^metadata_csum_seed,^64bit' -E nodiscard,lazy_itable_init=0,lazy_journal_init=0 \
    -d "$root" "$image.partial"
e2fsck -fn "$image.partial"
mv "$image.partial" "$image"
gzip -1c "$image" > "$image.gz.partial"
mv "$image.gz.partial" "$image.gz"
python3 - "$uuid" <<'PY'
import hashlib, json, pathlib, sys
out = pathlib.Path('/out')
def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
names = ('tabs3-debian-rootfs.ext4', 'tabs3-debian-rootfs.ext4.gz')
report = {'model': 'SM-T825', 'suite': 'trixie', 'root_uuid': sys.argv[1],
          'target_partition': 'userdata', 'hardware_tested_at_build': False,
          'arm64_dev_ssh_login_verified': True,
          'images': {name: {'bytes': (out/name).stat().st_size, 'sha256': sha(out/name)} for name in names}}
(out/'installed-rootfs.json').write_text(json.dumps(report, indent=2)+'\n')
PY
chmod 600 "$image" "$image.gz" /out/installed-*.json /out/installed-*.tsv /out/installed-*.conf
chown "$OUTPUT_UID:$OUTPUT_GID" "$image" "$image.gz" /out/installed-*.json /out/installed-*.tsv /out/installed-*.conf
echo 'Internal Debian filesystem built; ARM64 dev SSH and ext4 integrity verified.'
