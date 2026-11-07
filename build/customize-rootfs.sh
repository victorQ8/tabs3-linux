#!/bin/bash
set -euo pipefail
root=${1:?mmdebstrap root directory is required}
install -m 0644 "/out/tabs3-base_${TABS3_BASE_VERSION:?}_all.deb" "$root/tmp/tabs3-base.deb"
chroot "$root" dpkg -i /tmp/tabs3-base.deb
rm "$root/tmp/tabs3-base.deb"
chroot "$root" useradd --uid 1000 --create-home --shell /bin/bash --groups sudo dev
install -d -m 0700 -o 1000 -g 1000 "$root/home/dev/.ssh"
install -m 0600 -o 1000 -g 1000 /run/tabs3-authorized-key.pub "$root/home/dev/.ssh/authorized_keys"
# Console login only; sshd stays key-only (10-tabs3.conf).
hash=$(cat /run/tabs3-dev-password.hash)
[[ "$hash" == "\$6\$"* ]]
chroot "$root" usermod -p "$hash" dev
echo 'dev ALL=(ALL) NOPASSWD: ALL' > "$root/etc/sudoers.d/tabs3-dev"
chmod 0440 "$root/etc/sudoers.d/tabs3-dev"
# iwd does its own DHCP and hands DNS to systemd-resolved; main.conf is
# iwd's conffile, so the image edits it like an administrator would.
install -m 0644 /project/build/iwd-main.conf "$root/etc/iwd/main.conf"
echo tabs3 > "$root/etc/hostname"
printf '127.0.0.1 localhost\n127.0.1.1 tabs3\n::1 localhost ip6-localhost ip6-loopback\n' > "$root/etc/hosts"
chroot "$root" systemctl enable ssh.service tabs3-usb-gadget.service tabs3-wifi-pcie.service tabs3-wifi-board.service tabs3-bt-address.service tabs3-screen.service iwd.service systemd-networkd.service systemd-resolved.service
ln -sf /run/systemd/resolve/stub-resolv.conf "$root/etc/resolv.conf"
chroot "$root" dpkg-query -W > /out/tabs3-rootfs-packages.tsv
test "$(chroot "$root" dpkg --print-architecture)" = arm64
test -z "$(chroot "$root" dpkg --audit)"
chroot "$root" visudo -c
mkdir -p "$root/run/sshd"
chroot "$root" /usr/sbin/sshd -t
chroot "$root" /usr/sbin/sshd -T > /out/tabs3-sshd-effective.conf
# Per-device identities must be generated at first boot, never cloned.
rm -f "$root"/etc/ssh/ssh_host_* "$root/var/lib/dbus/machine-id"
: > "$root/etc/machine-id"
ln -s /etc/machine-id "$root/var/lib/dbus/machine-id"
rm -rf "$root/run/sshd"
echo 'Debian ARM64 userspace validated under QEMU; tablet boot is not yet validated.' > /out/tabs3-rootfs-validation.txt
