#!/bin/sh
# Run inside the RAM storage-probe image. No partition or filesystem writes.
set -eu
tr '\000' '\n' < /proc/device-tree/compatible | grep -qx samsung,gts3llte
grep -qw tabs3.mode=storage-probe /proc/cmdline || {
    echo 'Use the RAM storage-probe image, not installed Debian.' >&2; exit 1;
}
test "$(blockdev --getro /dev/mmcblk0p28)" = 1
grep -qx PARTNAME=boot /sys/class/block/mmcblk0p28/uevent
mkdir -p /sys/kernel/debug
grep -q ' /sys/kernel/debug debugfs ' /proc/mounts || mount -t debugfs debugfs /sys/kernel/debug
cat /sys/kernel/debug/mmc0/ios
echo 'Eight direct 64 MiB reads from the unchanged normal-boot partition (512 MiB total).'
echo 'Start uptime:'
cat /proc/uptime
for i in 1 2 3 4 5 6 7 8; do
    dd if=/dev/mmcblk0p28 of=/dev/null bs=4M count=16 iflag=direct
done
echo 'End uptime:'
cat /proc/uptime
echo 'Three independent direct-read SHA-256 values for the same 64 MiB:'
sample=$(mktemp /run/tabs3-storage.XXXXXX)
trap 'rm -f "$sample"' EXIT
for i in 1 2 3; do
    dd if=/dev/mmcblk0p28 of="$sample" bs=4M count=16 iflag=direct
    sha256sum "$sample"
done
echo 'MMC kernel log (check tuning, CRC, timeout and reset messages):'
dmesg | grep -i mmc
