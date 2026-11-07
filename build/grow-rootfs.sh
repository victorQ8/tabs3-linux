#!/bin/sh
set -eu
tr '\000' '\n' </sys/firmware/devicetree/base/compatible | grep -qx samsung,gts3llte
grep -qx PARTNAME=userdata /sys/class/block/mmcblk0p47/uevent
expected=$(cat /etc/tabs3-root-uuid)
[ -n "$expected" ]
# Root is userdata itself or, with tabs3.root_extend=system, the initramfs
# device-mapper table that starts with userdata. Grow whichever is mounted.
source=$(findmnt -n -o SOURCE /)
case "$source" in /dev/mmcblk0p47|/dev/mapper/tabs3root) ;; *) exit 1 ;; esac
[ "$(blkid -s UUID -o value "$source")" = "$expected" ]
[ "$(findmnt -n -o UUID /)" = "$expected" ]
resize2fs "$source"
mkdir -p /var/lib/tabs3
touch /var/lib/tabs3/root-expanded
