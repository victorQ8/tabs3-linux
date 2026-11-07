# shellcheck shell=sh
# SPDX-License-Identifier: MIT
# Shared by init and tabs3-recovery. tabs3.root_extend=system appends
# Android's unused system partition to the root filesystem with a linear
# device-mapper table. Userdata comes first so the ext4 filesystem keeps its
# offsets; both lengths are whole 4 KiB blocks.
map_root_system() {
    grep -qx PARTNAME=userdata /sys/class/block/mmcblk0p47/uevent || return 1
    grep -qx PARTNAME=system /sys/class/block/mmcblk0p44/uevent || return 1
    data_len=$(( $(cat /sys/class/block/mmcblk0p47/size) / 8 * 8 ))
    system_len=$(( $(cat /sys/class/block/mmcblk0p44/size) / 8 * 8 ))
    printf '0 %s linear /dev/mmcblk0p47 0\n%s %s linear /dev/mmcblk0p44 0\n' \
        "$data_len" "$data_len" "$system_len" |
        DM_DISABLE_UDEV=1 /usr/sbin/dmsetup create tabs3root
}
