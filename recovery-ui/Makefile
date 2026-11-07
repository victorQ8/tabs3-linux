# Build the recovery screen. TARGET=arm64 for the tablet, TARGET=preview for
# the build host. OUT must be writable; sources may be read-only.
TARGET ?= arm64
OUT ?= build/$(TARGET)
LVGL_PATH ?= $(abspath ../upstream/lvgl)

ifeq ($(TARGET),arm64)
CC := aarch64-linux-gnu-gcc
STRIP := aarch64-linux-gnu-strip
DEFS :=
else
CC := gcc
STRIP := strip
DEFS := -DTABS3_PREVIEW
endif

CFLAGS := -Os -ffunction-sections -fdata-sections -I$(CURDIR) -I$(LVGL_PATH) \
	-DLV_CONF_INCLUDE_SIMPLE $(DEFS)
LVGL_SRCS := $(shell find $(LVGL_PATH)/src -name '*.c')
OBJS := $(patsubst $(LVGL_PATH)/%.c,$(OUT)/lvgl/%.o,$(LVGL_SRCS)) $(OUT)/main.o

$(OUT)/tabs3-recovery-ui: $(OBJS)
	$(CC) -Wl,--gc-sections -o $@ $^ -lm
	$(STRIP) $@

$(OUT)/lvgl/%.o: $(LVGL_PATH)/%.c lv_conf.h
	@mkdir -p $(dir $@)
	@$(CC) $(CFLAGS) -w -c $< -o $@

$(OUT)/main.o: main.c lv_conf.h fsck-result.h
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -Wall -Wextra -c $< -o $@
