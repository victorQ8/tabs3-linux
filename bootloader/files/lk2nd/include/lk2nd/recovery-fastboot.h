/* SPDX-License-Identifier: MIT */
#ifndef TABS3_RECOVERY_FASTBOOT_H
#define TABS3_RECOVERY_FASTBOOT_H
#include <stdbool.h>

/* Two 512-byte records in the otherwise unused end of the 4 MiB wrapper. */
#define TABS3_FB_RESERVATION 4194304U
#define TABS3_FB_DESCRIPTOR (TABS3_FB_RESERVATION - 8192U)
#define TABS3_FB_REQUEST (TABS3_FB_RESERVATION - 4096U)
#define TABS3_FB_RECORD_SIZE 512U
#define TABS3_FB_CAPABILITY "TABS3-RFB-CAP-v1:120"
#define TABS3_FB_ONESHOT "TABS3-RFB-ONCE-v1"
#define TABS3_FB_TIMEOUT_MS 120000U

#if LK2ND_RECOVERY_FASTBOOT
bool tabs3_fastboot_consume(void);
void tabs3_fastboot_start(void);
bool tabs3_fastboot_begin_command(void);
bool tabs3_fastboot_command_allowed(const char *command);
void tabs3_fastboot_end_command(void);
void tabs3_fastboot_stop(void);
#else
static inline bool tabs3_fastboot_consume(void) { return false; }
static inline void tabs3_fastboot_start(void) { }
static inline bool tabs3_fastboot_begin_command(void) { return true; }
static inline bool tabs3_fastboot_command_allowed(const char *command) { (void)command; return true; }
static inline void tabs3_fastboot_end_command(void) { }
static inline void tabs3_fastboot_stop(void) { }
#endif
#endif
