# shellcheck shell=sh
# SPDX-License-Identifier: MIT
# Called only after board/partition/UUID validation, before the first root
# mount or any USB storage export. No unconditional -y repairs at boot.
check_root_filesystem() {
    root_check_status=0
    e2fsck -p "$1" > /run/log/root-fsck.log 2>&1 || root_check_status=$?
    cat /run/log/root-fsck.log
    printf '%s\n' "$root_check_status" > /run/tabs3-root-fsck.status
    case "$root_check_status" in
        0|1) return 0 ;;
        *)
            echo "Root filesystem check requires recovery (e2fsck status $root_check_status)."
            return 1 ;;
    esac
}
