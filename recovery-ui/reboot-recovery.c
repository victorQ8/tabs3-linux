/* SPDX-License-Identifier: MIT */
/* BusyBox reboot -f has no RESTART2 argument; request Samsung recovery explicitly. */
#define _GNU_SOURCE
#include <linux/reboot.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(void)
{
    sync();
    syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
            LINUX_REBOOT_CMD_RESTART2, "recovery");
    perror("reboot recovery");
    return 1;
}
