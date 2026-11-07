/* SPDX-License-Identifier: MIT */
/* SM-T825 recovery only. Never interpret Samsung's misc/param contents here. */
#include <debug.h>
#include <fastboot.h>
#include <kernel/thread.h>
#include <partition_parser.h>
#include <platform.h>
#include <stdlib.h>
#include <string.h>
#include <target.h>
#include <lk2nd/recovery-fastboot.h>

static bool requested, busy, expired;
static unsigned last_activity;

/* This copy splits recovery, not boot. Generic partition writes would have
 * different offsets from the normal lk2nd and could overwrite its wrapper. */
bool tabs3_fastboot_command_allowed(const char *command)
{
    return !strncmp(command, "getvar:", 7) ||
           !strncmp(command, "download:", 9) ||
           !strcmp(command, "boot") || !strcmp(command, "continue") ||
           !strcmp(command, "reboot") || !strcmp(command, "oem log") ||
           !strcmp(command, "upload");
}

static void publish_mode(void)
{
    fastboot_publish("tabs3-recovery-fastboot", "1");
    fastboot_publish("tabs3-idle-timeout", "120");
}
FASTBOOT_INIT(publish_mode);

bool tabs3_fastboot_consume(void)
{
    struct partition_info wrapper = partition_get_info("lk2nd");
    struct partition_info recovery = partition_get_info("recovery");
    unsigned char *buffer;
    const unsigned char capability[TABS3_FB_RECORD_SIZE] = TABS3_FB_CAPABILITY;
    const unsigned char request[TABS3_FB_RECORD_SIZE] = TABS3_FB_ONESHOT;
    const unsigned char empty[TABS3_FB_RECORD_SIZE] = {0};
    bool result = false;

    /* lk2nd has already split recovery into its wrapper and Linux payload. */
    if (!target_is_emmc_boot() || mmc_get_device_blocksize() != 512 ||
        !wrapper.offset || wrapper.size != TABS3_FB_RESERVATION ||
        recovery.offset != wrapper.offset + wrapper.size)
        return false;
    buffer = memalign(CACHE_LINE, TABS3_FB_RECORD_SIZE);
    if (!buffer)
        return false;
    if (mmc_read(wrapper.offset + TABS3_FB_DESCRIPTOR, (void *)buffer, sizeof(capability)) ||
        memcmp(buffer, capability, sizeof(capability)))
        goto out;
    if (mmc_read(wrapper.offset + TABS3_FB_REQUEST, (void *)buffer, sizeof(request)) ||
        memcmp(buffer, request, sizeof(request)))
        goto out;

    /* Consume BEFORE entering fastboot. Failed writes/readback boot recovery. */
    memset(buffer, 0, TABS3_FB_RECORD_SIZE);
    if (mmc_write(wrapper.offset + TABS3_FB_REQUEST, TABS3_FB_RECORD_SIZE, buffer) ||
        mmc_read(wrapper.offset + TABS3_FB_REQUEST, (void *)buffer, TABS3_FB_RECORD_SIZE) ||
        memcmp(buffer, empty, sizeof(empty))) {
        dprintf(CRITICAL, "tabS3: cannot consume fastboot request; booting recovery\n");
        goto out;
    }
    requested = result = true;
    dprintf(INFO, "tabS3: one-time fastboot request consumed\n");
out:
    free(buffer);
    return result;
}

/* Serialize the timeout decision with command dispatch on LK's single CPU. */
bool tabs3_fastboot_begin_command(void)
{
    bool accept;
    enter_critical_section();
    accept = !expired && !busy;
    if (accept)
        busy = true;
    exit_critical_section();
    return accept;
}

void tabs3_fastboot_end_command(void)
{
    enter_critical_section();
    last_activity = current_time();
    busy = false;
    exit_critical_section();
}

void tabs3_fastboot_stop(void)
{
    enter_critical_section();
    requested = false;
    exit_critical_section();
}

static bool timeout_expired(void)
{
    bool leave;
    enter_critical_section();
    leave = requested && !busy &&
        (unsigned)(current_time() - last_activity) >= TABS3_FB_TIMEOUT_MS;
    if (leave)
        expired = true; /* No new commands can start after this decision. */
    exit_critical_section();
    return leave;
}

static int idle_monitor(void *arg)
{
    (void)arg;
    for (;;) {
        thread_sleep(250);
        if (timeout_expired()) {
            dprintf(INFO, "tabS3: fastboot idle timeout; rebooting recovery\n");
            reboot_device(RECOVERY_MODE);
            return 0;
        }
    }
}

void tabs3_fastboot_start(void)
{
    thread_t *thread;
    if (!requested)
        return; /* Physical-key fastboot keeps its existing behavior. */
    last_activity = current_time();
    thread = thread_create("recovery-fb-timeout", idle_monitor, NULL,
                           DEFAULT_PRIORITY, DEFAULT_STACK_SIZE);
    if (!thread) {
        expired = true;
        reboot_device(RECOVERY_MODE);
        return;
    }
    thread_resume(thread);
}
