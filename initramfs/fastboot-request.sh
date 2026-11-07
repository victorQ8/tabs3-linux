#!/bin/sh
# SPDX-License-Identifier: MIT
# Shared by Debian and the recovery initramfs. This only writes a request;
# callers are responsible for a recovery reboot and for unmounting filesystems.
tabs3_fastboot_device() {
    [ "$(id -u)" = 0 ] || { echo 'Run as root' >&2; return 1; }
    tr '\000' '\n' </sys/firmware/devicetree/base/compatible |
        grep -qx 'samsung,gts3llte' || return 1
    set --
    for fb_uevent in /sys/class/block/mmcblk0p*/uevent; do
        if grep -qx PARTNAME=recovery "$fb_uevent"; then
            fb_dev=${fb_uevent%/uevent}
            set -- "$@" "${fb_dev##*/}"
        fi
    done
    [ "$#" = 1 ] || return 1
    [ "$(cat "/sys/class/block/$1/size")" = 155648 ] || return 1
    [ -b "/dev/$1" ] || return 1
    [ ! -L /sys/kernel/config/usb_gadget/tabs3/configs/c.1/mass_storage.0 ] || {
        echo 'Turn off USB storage export first' >&2; return 1;
    }
    printf '/dev/%s\n' "$1"
}

tabs3_fastboot_request() (
    set -eu
    case "${1:-}" in arm|cancel|status) ;; *) return 1 ;; esac
    fb_device=$(tabs3_fastboot_device) || {
        echo 'Not the expected SM-T825 recovery partition, or storage is exported' >&2
        exit 1
    }
    mkdir /run/tabs3-fastboot.lock 2>/dev/null || {
        echo 'Another fastboot request operation is running' >&2; exit 1;
    }
    fb_tmp=
    trap 'test -z "$fb_tmp" || rm -rf "$fb_tmp"; rmdir /run/tabs3-fastboot.lock' EXIT
    fb_tmp=$(mktemp -d /run/tabs3-fastboot.XXXXXX)
    dd if=/dev/zero of="$fb_tmp/cap" bs=512 count=1 2>/dev/null
    printf 'TABS3-RFB-CAP-v1:120' | dd of="$fb_tmp/cap" conv=notrunc 2>/dev/null
    dd if="$fb_device" of="$fb_tmp/read" bs=512 skip=8176 count=1 2>/dev/null
    cmp -s "$fb_tmp/cap" "$fb_tmp/read" || {
        echo 'Recovery does not advertise remote fastboot v1; no write performed' >&2
        exit 1
    }
    dd if=/dev/zero of="$fb_tmp/empty" bs=512 count=1 2>/dev/null
    cp "$fb_tmp/empty" "$fb_tmp/request"
    printf 'TABS3-RFB-ONCE-v1' | dd of="$fb_tmp/request" conv=notrunc 2>/dev/null
    dd if="$fb_device" of="$fb_tmp/read" bs=512 skip=8184 count=1 2>/dev/null
    if cmp -s "$fb_tmp/empty" "$fb_tmp/read"; then
        fb_state=clear
    elif cmp -s "$fb_tmp/request" "$fb_tmp/read"; then
        fb_state=armed
    else
        echo 'Unknown recovery request contents; no write performed' >&2
        exit 1
    fi
    if [ "$1" = status ]; then printf '%s\n' "$fb_state"; exit 0; fi
    fb_record=$fb_tmp/request
    [ "$1" != cancel ] || fb_record=$fb_tmp/empty
    dd if="$fb_record" of="$fb_device" bs=512 seek=8184 count=1 conv=notrunc,fsync 2>/dev/null
    dd if="$fb_device" of="$fb_tmp/read" bs=512 skip=8184 count=1 2>/dev/null
    cmp -s "$fb_record" "$fb_tmp/read" || {
        echo 'Fastboot request readback failed; not rebooting' >&2; exit 1;
    }
    echo "Fastboot request: $1 verified"
)
