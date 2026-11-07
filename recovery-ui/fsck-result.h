// SPDX-License-Identifier: MIT
#ifndef TABS3_FSCK_RESULT_H
#define TABS3_FSCK_RESULT_H

/* e2fsck exit codes are a bitmask. Failures take priority over repairs. */
static inline const char *fsck_result_message(int status)
{
    if (status < 0)
        return "Filesystem check interrupted. See the activity log for details.";
    if (status & ~(1 | 2 | 4 | 32))
        return "Filesystem check failed. See the activity log for details.";
    if (status & 32)
        return "Filesystem check cancelled. No clean result is available.";
    if (status & 4)
        return "Filesystem errors remain. Repair over SSH with: tabs3-recovery fsck -y";
    if (status & 2)
        return "Filesystem errors corrected; reboot required.";
    if (status & 1)
        return "Filesystem errors corrected.";
    return "Filesystem check finished: no errors";
}

#endif
