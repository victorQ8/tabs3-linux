// SPDX-License-Identifier: MIT
/*
 * tabS3 recovery screen: status of the Debian root, boot image and USB, and
 * touch actions that run tabs3-recovery. Built for the tablet (framebuffer,
 * evdev) or, with TABS3_PREVIEW, for the build host, where it renders the
 * screens to PPM images for design review.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "lvgl.h"
#include "fsck-result.h"

#define W 2048
#define H 1536
#define MARGIN 72

#define C_BG 0x000000
#define C_CARD 0x0e0f12
#define C_BORDER 0x1c1e23
#define C_RAISED 0x1a1c21
#define C_TILE 0x131519
#define C_TILE_PRESSED 0x1f2228
#define C_TEXT 0xf3f4f6
#define C_TEXT2 0x9aa0aa
#define C_TEXT3 0x656b76
#define C_ACCENT 0xd70a53
#define C_ACCENT_PRESSED 0xa80843
#define C_OK 0x34d399
#define C_OK_BG 0x0c2a1f
#define C_WARN 0xfbbf24
#define C_WARN_BG 0x2e2408
#define C_ERR 0xf87171
#define C_ERR_BG 0x301214

#define HELPER "/usr/sbin/tabs3-recovery"

enum action { ACT_BOOT, ACT_FSCK, ACT_USB, ACT_POWEROFF, ACT_FASTBOOT, ACT_COUNT };

struct rec_status {
    bool valid;
    unsigned long long root_bytes, root_free_bytes;
    char root_state[40];
    char root_layout[40];
    bool boot_ok;
    char boot_desc[64];
    char usb_export[8];
    bool usb_host;
};

/* ------------------------------------------------------------------ */
/* Small UI helpers                                                    */

static lv_color_t hex(uint32_t c) { return lv_color_hex(c); }

static lv_obj_t *box(lv_obj_t *parent)
{
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    /* Layout and decoration must not intercept their button's touches.
     * Modal backdrops opt back into click handling explicitly. */
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    return o;
}

static lv_obj_t *text(lv_obj_t *parent, const lv_font_t *font, uint32_t color, const char *s)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, hex(color), 0);
    lv_label_set_text(l, s);
    return l;
}

static lv_obj_t *column(lv_obj_t *parent, int gap)
{
    lv_obj_t *o = box(parent);
    lv_obj_set_size(o, LV_PCT(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(o, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(o, gap, 0);
    return o;
}

static lv_obj_t *row(lv_obj_t *parent, int gap)
{
    lv_obj_t *o = box(parent);
    lv_obj_set_size(o, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(o, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(o, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(o, gap, 0);
    return o;
}

static void card_style(lv_obj_t *o, uint32_t bg, int radius)
{
    lv_obj_set_style_bg_color(o, hex(bg), 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(o, radius, 0);
    lv_obj_set_style_border_color(o, hex(C_BORDER), 0);
    lv_obj_set_style_border_width(o, 2, 0);
}

static lv_obj_t *section_label(lv_obj_t *parent, const char *s)
{
    lv_obj_t *l = text(parent, &lv_font_montserrat_24, C_TEXT3, s);
    lv_obj_set_style_text_letter_space(l, 3, 0);
    return l;
}

struct pill { lv_obj_t *obj, *label; };

static struct pill pill_create(lv_obj_t *parent)
{
    struct pill p;
    p.obj = box(parent);
    lv_obj_set_size(p.obj, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_style_radius(p.obj, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(p.obj, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_hor(p.obj, 24, 0);
    lv_obj_set_style_pad_ver(p.obj, 8, 0);
    p.label = text(p.obj, &lv_font_montserrat_24, C_TEXT, "");
    return p;
}

static void pill_set(struct pill *p, const char *s, uint32_t fg, uint32_t bg)
{
    lv_label_set_text(p->label, s);
    lv_obj_set_style_text_color(p->label, hex(fg), 0);
    lv_obj_set_style_bg_color(p->obj, hex(bg), 0);
}

/* ------------------------------------------------------------------ */
/* Screen layout                                                       */

struct status_card {
    lv_obj_t *value, *sub;
    struct pill pill;
};

struct tile {
    lv_obj_t *btn, *icon, *spinner, *title, *desc;
    const char *title_idle, *desc_idle;
    bool primary;
};

#define LOG_LINES 4

static struct {
    lv_obj_t *conn_dot, *conn_label, *conn_ssh;
    struct status_card root, boot, usb;
    lv_obj_t *root_bar;
    struct tile tiles[ACT_COUNT];
    lv_obj_t *log_time[LOG_LINES], *log_text[LOG_LINES];
    int log_count;
    lv_obj_t *modal;
    lv_obj_t *overlay;
    lv_obj_t *hold, *hold_bar;
    struct rec_status st;
    int busy;
    enum action pending;
} ui = { .busy = -1 };

static void on_tile(lv_event_t *e);

static void status_card_create(struct status_card *c, lv_obj_t *parent, const char *symbol,
                               const char *title, int height, bool with_bar)
{
    lv_obj_t *card = box(parent);
    lv_obj_set_size(card, LV_PCT(100), height);
    card_style(card, C_CARD, 28);
    lv_obj_set_style_pad_all(card, 36, 0);

    lv_obj_t *icon = box(card);
    lv_obj_set_size(icon, 80, 80);
    lv_obj_set_style_radius(icon, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(icon, hex(C_RAISED), 0);
    lv_obj_set_style_bg_opa(icon, LV_OPA_COVER, 0);
    lv_obj_center(text(icon, &lv_font_montserrat_32, C_TEXT2, symbol));
    lv_obj_align(icon, LV_ALIGN_LEFT_MID, 0, 0);

    lv_obj_t *col = column(card, 6);
    lv_obj_set_width(col, 800 - 72 - 4 - 80 - 32);
    lv_obj_align(col, LV_ALIGN_LEFT_MID, 80 + 32, 0);
    text(col, &lv_font_montserrat_24, C_TEXT2, title);
    c->value = text(col, &lv_font_montserrat_32, C_TEXT, "");
    if (with_bar) {
        ui.root_bar = lv_bar_create(col);
        lv_obj_set_size(ui.root_bar, LV_PCT(100), 12);
        lv_obj_set_style_margin_top(ui.root_bar, 16, 0);
        lv_obj_set_style_margin_bottom(ui.root_bar, 8, 0);
        lv_obj_set_style_bg_color(ui.root_bar, hex(0x24272d), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(ui.root_bar, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_radius(ui.root_bar, 6, LV_PART_MAIN);
        lv_obj_set_style_bg_color(ui.root_bar, hex(C_ACCENT), LV_PART_INDICATOR);
        lv_obj_set_style_radius(ui.root_bar, 6, LV_PART_INDICATOR);
        lv_bar_set_range(ui.root_bar, 0, 1000);
    }
    c->sub = text(col, &lv_font_montserrat_24, C_TEXT3, "");

    c->pill = pill_create(card);
    lv_obj_align(c->pill.obj, LV_ALIGN_TOP_RIGHT, 0, 0);
}

static void tile_create(enum action a, lv_obj_t *parent, const char *symbol, const char *title,
                        const char *desc, bool primary)
{
    struct tile *t = &ui.tiles[a];
    t->primary = primary;
    t->title_idle = title;
    t->desc_idle = desc;
    t->btn = lv_button_create(parent);
    lv_obj_remove_style_all(t->btn);
    lv_obj_set_size(t->btn, 508, 224);
    lv_obj_set_style_radius(t->btn, 32, 0);
    lv_obj_set_style_bg_opa(t->btn, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(t->btn, 24, 0);
    if (primary) {
        lv_obj_set_style_bg_color(t->btn, hex(C_ACCENT), 0);
        lv_obj_set_style_bg_color(t->btn, hex(C_ACCENT_PRESSED), LV_STATE_PRESSED);
    } else {
        card_style(t->btn, C_TILE, 32);
        lv_obj_set_style_bg_color(t->btn, hex(C_TILE_PRESSED), LV_STATE_PRESSED);
    }
    lv_obj_set_style_opa(t->btn, LV_OPA_30, LV_STATE_DISABLED);
    lv_obj_add_event_cb(t->btn, on_tile, LV_EVENT_CLICKED, (void *)(intptr_t)a);

    lv_obj_t *col = column(t->btn, 10);
    lv_obj_t *icon = box(col);
    lv_obj_set_size(icon, 56, 56);
    lv_obj_set_style_radius(icon, 28, 0);
    lv_obj_set_style_bg_color(icon, primary ? hex(0xffffff) : hex(C_RAISED), 0);
    lv_obj_set_style_bg_opa(icon, primary ? LV_OPA_20 : LV_OPA_COVER, 0);
    lv_obj_set_style_margin_bottom(icon, 0, 0);
    t->icon = text(icon, &lv_font_montserrat_40, primary ? 0xffffff : C_TEXT, symbol);
    lv_obj_center(t->icon);
    t->spinner = lv_spinner_create(icon);
    lv_obj_set_size(t->spinner, 44, 44);
    lv_obj_center(t->spinner);
    lv_obj_set_style_arc_width(t->spinner, 7, LV_PART_MAIN);
    lv_obj_set_style_arc_width(t->spinner, 7, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(t->spinner, hex(0x2c2f36), LV_PART_MAIN);
    lv_obj_set_style_arc_color(t->spinner, primary ? hex(0xffffff) : hex(C_ACCENT), LV_PART_INDICATOR);
    lv_obj_add_flag(t->spinner, LV_OBJ_FLAG_HIDDEN);

    t->title = text(col, &lv_font_montserrat_32, primary ? 0xffffff : C_TEXT, title);
    t->desc = text(col, &lv_font_montserrat_24, primary ? 0xf6d7e2 : C_TEXT2, desc);
    lv_label_set_long_mode(t->desc, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(t->desc, LV_PCT(100));
}

static void ui_create(void)
{
    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, hex(C_BG), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    /* Header */
    lv_obj_t *badge = box(scr);
    lv_obj_set_size(badge, 104, 104);
    lv_obj_set_pos(badge, MARGIN, 56);
    lv_obj_set_style_radius(badge, 30, 0);
    lv_obj_set_style_bg_color(badge, hex(C_ACCENT), 0);
    lv_obj_set_style_bg_opa(badge, LV_OPA_COVER, 0);
    lv_obj_center(text(badge, &lv_font_montserrat_40, 0xffffff, "S3"));

    lv_obj_t *title = text(scr, &lv_font_montserrat_48, C_TEXT, "Recovery");
    lv_obj_set_pos(title, MARGIN + 104 + 32, 54);
    lv_obj_t *sub = text(scr, &lv_font_montserrat_24, C_TEXT2,
                         "Galaxy Tab S3 LTE   " LV_SYMBOL_BULLET "   SM-T825   " LV_SYMBOL_BULLET "   Debian 13");
    lv_obj_set_pos(sub, MARGIN + 104 + 32, 122);

    lv_obj_t *chip = row(scr, 16);
    card_style(chip, C_CARD, LV_RADIUS_CIRCLE);
    lv_obj_set_style_pad_hor(chip, 30, 0);
    lv_obj_set_style_pad_ver(chip, 16, 0);
    lv_obj_align(chip, LV_ALIGN_TOP_RIGHT, -MARGIN, 76);
    ui.conn_dot = box(chip);
    lv_obj_set_size(ui.conn_dot, 16, 16);
    lv_obj_set_style_radius(ui.conn_dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(ui.conn_dot, LV_OPA_COVER, 0);
    ui.conn_label = text(chip, &lv_font_montserrat_24, C_TEXT, "");
    ui.conn_ssh = row(chip, 16);
    lv_obj_t *sep = box(ui.conn_ssh);
    lv_obj_set_size(sep, 2, 28);
    lv_obj_set_style_bg_color(sep, hex(0x30333a), 0);
    lv_obj_set_style_bg_opa(sep, LV_OPA_COVER, 0);
    lv_obj_set_style_margin_hor(sep, 6, 0);
    text(ui.conn_ssh, &lv_font_montserrat_24, C_TEXT2, "ssh root@172.16.42.2");

    /* Status column and action grid share one height. */
    const int top = 236;
    const int left_w = 800;
    lv_obj_t *left = column(scr, 28);
    lv_obj_set_width(left, left_w);
    lv_obj_set_pos(left, MARGIN, top);
    section_label(left, "STATUS");
    status_card_create(&ui.root, left, LV_SYMBOL_DRIVE, "Debian root", 248, true);
    status_card_create(&ui.boot, left, LV_SYMBOL_FILE, "Boot partition", 204, false);
    status_card_create(&ui.usb, left, LV_SYMBOL_USB, "USB storage", 204, false);

    const int right_x = MARGIN + left_w + 56;
    lv_obj_t *right = column(scr, 28);
    lv_obj_set_width(right, W - MARGIN - right_x);
    lv_obj_set_pos(right, right_x, top);
    section_label(right, "ACTIONS");
    lv_obj_t *grid = box(right);
    lv_obj_set_size(grid, LV_PCT(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(grid, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_style_pad_row(grid, 32, 0);
    lv_obj_set_style_pad_column(grid, 32, 0);
    tile_create(ACT_BOOT, grid, LV_SYMBOL_PLAY, "Boot Debian",
                "Leave recovery and start the installed system", true);
    tile_create(ACT_FSCK, grid, LV_SYMBOL_OK, "Check filesystem",
                "Read-only check of the Debian root", false);
    tile_create(ACT_USB, grid, LV_SYMBOL_USB, "Share storage",
                "Show the internal storage on a PC, read-only", false);
    tile_create(ACT_POWEROFF, grid, LV_SYMBOL_POWER, "Power off", "Switch the tablet off", false);
    tile_create(ACT_FASTBOOT, grid, LV_SYMBOL_UPLOAD, "Enter fastboot",
                "Connect to a PC to boot a test image", false);

    /* Activity */
    lv_obj_t *activity = box(scr);
    lv_obj_set_size(activity, W - 2 * MARGIN, LV_SIZE_CONTENT);
    lv_obj_set_pos(activity, MARGIN, 1066);
    card_style(activity, C_CARD, 28);
    lv_obj_set_style_pad_hor(activity, 40, 0);
    lv_obj_set_style_pad_ver(activity, 32, 0);
    lv_obj_t *acol = column(activity, 14);
    section_label(acol, "ACTIVITY");
    for (int i = 0; i < LOG_LINES; i++) {
        lv_obj_t *r = row(acol, 28);
        ui.log_time[i] = text(r, &lv_font_montserrat_24, C_TEXT3, "");
        lv_obj_set_width(ui.log_time[i], 90);
        ui.log_text[i] = text(r, &lv_font_montserrat_24, C_TEXT2, "");
    }

    /* Hints */
    lv_obj_t *hints = row(scr, 64);
    lv_obj_align(hints, LV_ALIGN_BOTTOM_LEFT, MARGIN, -58);
    text(hints, &lv_font_montserrat_24, C_TEXT3, LV_SYMBOL_POWER "   Hold Power 3 s to boot Debian");
    text(hints, &lv_font_montserrat_24, C_TEXT3, LV_SYMBOL_POWER "   Press Power to turn the screen off");
    text(hints, &lv_font_montserrat_24, C_TEXT3, "More over SSH:  tabs3-recovery help");
}

/* Newest line last; lines fill from the top. Times are since recovery started. */
static void ui_log(const char *line)
{
    while (*line == ' ')
        line++;
    if (!*line)
        return;
    if (ui.log_count == LOG_LINES) {
        for (int i = 0; i < LOG_LINES - 1; i++) {
            lv_label_set_text(ui.log_time[i], lv_label_get_text(ui.log_time[i + 1]));
            lv_label_set_text(ui.log_text[i], lv_label_get_text(ui.log_text[i + 1]));
        }
        ui.log_count--;
    }
    uint32_t s = lv_tick_get() / 1000;
    lv_label_set_text_fmt(ui.log_time[ui.log_count], "%u:%02u", (unsigned)(s / 60), (unsigned)(s % 60));
    lv_label_set_text(ui.log_text[ui.log_count], line);
    ui.log_count++;
    for (int i = 0; i < ui.log_count; i++)
        lv_obj_set_style_text_color(ui.log_text[i], hex(i == ui.log_count - 1 ? C_TEXT : C_TEXT2), 0);
}

static void size_text(char *buf, size_t n, unsigned long long bytes)
{
    snprintf(buf, n, "%.1f GB", bytes / 1073741824.0);
}

static void ui_set_status(const struct rec_status *s)
{
    char a[32], b[32], line[160];
    static bool was_valid = true;
    if (!s->valid) {
        /* A failed or timed-out status read is shown as such, never as a
         * missing filesystem; the other cards keep their last values. */
        ui.st.valid = false;
        lv_label_set_text(ui.root.value, "Status unavailable");
        lv_label_set_text(ui.root.sub, "the recovery helper did not answer");
        pill_set(&ui.root.pill, "Unknown", C_WARN, C_WARN_BG);
        if (was_valid)
            ui_log("Status check failed or timed out; storage may be slow.");
        was_valid = false;
        return;
    }
    was_valid = true;
    ui.st = *s;
    bool usb_on = strcmp(s->usb_export, "off") != 0;
    bool usb_rw = !strcmp(s->usb_export, "rw");

    lv_obj_set_style_bg_color(ui.conn_dot, hex(s->usb_host ? C_OK : C_TEXT3), 0);
    lv_label_set_text(ui.conn_label, s->usb_host ? "PC connected" : "No PC connected");
    if (s->usb_host)
        lv_obj_remove_flag(ui.conn_ssh, LV_OBJ_FLAG_HIDDEN);
    else
        lv_obj_add_flag(ui.conn_ssh, LV_OBJ_FLAG_HIDDEN);

    if (s->root_bytes) {
        size_text(a, sizeof a, s->root_bytes);
        size_text(b, sizeof b, s->root_free_bytes);
        snprintf(line, sizeof line, "%s  " LV_SYMBOL_BULLET "  ext4", a);
        lv_label_set_text(ui.root.value, line);
        snprintf(line, sizeof line, "%s free  " LV_SYMBOL_BULLET "  %s", b, s->root_layout);
        lv_label_set_text(ui.root.sub, line);
        lv_bar_set_value(ui.root_bar, (int)((s->root_bytes - s->root_free_bytes) * 1000 / s->root_bytes),
                         LV_ANIM_OFF);
        if (!strcmp(s->root_state, "clean"))
            pill_set(&ui.root.pill, "Clean", C_OK, C_OK_BG);
        else
            pill_set(&ui.root.pill, "Needs check", C_WARN, C_WARN_BG);
    } else {
        lv_label_set_text(ui.root.value, "No filesystem");
        lv_label_set_text(ui.root.sub, "userdata has no ext4 filesystem");
        lv_bar_set_value(ui.root_bar, 0, LV_ANIM_OFF);
        pill_set(&ui.root.pill, "Missing", C_ERR, C_ERR_BG);
    }

    lv_label_set_text(ui.boot.value, s->boot_desc);
    lv_label_set_text(ui.boot.sub, s->boot_ok ? "lk2nd + Linux, starts automatically"
                                              : "No lk2nd/Linux image found");
    if (s->boot_ok)
        pill_set(&ui.boot.pill, "Ready", C_OK, C_OK_BG);
    else
        pill_set(&ui.boot.pill, "Problem", C_ERR, C_ERR_BG);

    if (!usb_on) {
        lv_label_set_text(ui.usb.value, "Not shared");
        lv_label_set_text(ui.usb.sub, "The PC gets network and SSH only");
        pill_set(&ui.usb.pill, "Off", C_TEXT2, C_RAISED);
    } else {
        lv_label_set_text(ui.usb.value, usb_rw ? "Shared, writable" : "Shared, read-only");
        lv_label_set_text(ui.usb.sub, usb_rw ? "The PC can change every partition"
                                             : "The PC sees every partition");
        pill_set(&ui.usb.pill, usb_rw ? "Writable" : "Read-only", usb_rw ? C_ERR : C_WARN,
                 usb_rw ? C_ERR_BG : C_WARN_BG);
    }

    struct tile *t = &ui.tiles[ACT_USB];
    if (ui.busy != ACT_USB) {
        lv_label_set_text(t->title, usb_on ? "Stop sharing" : t->title_idle);
        lv_label_set_text(t->desc, usb_on ? "Hide the internal storage from the PC" : t->desc_idle);
    }
}

static void ui_set_busy(int action, const char *desc)
{
    ui.busy = action;
    for (int i = 0; i < ACT_COUNT; i++) {
        struct tile *t = &ui.tiles[i];
        bool mine = i == action;
        if (mine) {
            lv_obj_add_flag(t->icon, LV_OBJ_FLAG_HIDDEN);
            lv_obj_remove_flag(t->spinner, LV_OBJ_FLAG_HIDDEN);
            lv_label_set_text(t->desc, desc);
            lv_obj_add_state(t->btn, LV_STATE_DISABLED);
            lv_obj_set_style_opa(t->btn, LV_OPA_COVER, LV_STATE_DISABLED);
            continue;
        }
        lv_obj_remove_flag(t->icon, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(t->spinner, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_style_opa(t->btn, LV_OPA_30, LV_STATE_DISABLED);
        if (action >= 0) {
            lv_obj_add_state(t->btn, LV_STATE_DISABLED);
        } else {
            lv_obj_remove_state(t->btn, LV_STATE_DISABLED);
            lv_label_set_text(t->title, t->title_idle);
            lv_label_set_text(t->desc, t->desc_idle);
        }
    }
    if (action < 0)
        ui_set_status(&ui.st);
}

static lv_obj_t *backdrop(lv_opa_t opa)
{
    lv_obj_t *o = box(lv_layer_top());
    lv_obj_set_size(o, W, H);
    lv_obj_set_style_bg_color(o, hex(C_BG), 0);
    lv_obj_set_style_bg_opa(o, opa, 0);
    lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
    return o;
}

/* Full-screen message while the tablet restarts or powers off. */
static void ui_overlay(const char *title, const char *body)
{
    if (ui.modal) {
        lv_obj_delete(ui.modal);
        ui.modal = NULL;
    }
    ui.overlay = backdrop(LV_OPA_COVER);
    lv_obj_t *col = column(ui.overlay, 28);
    lv_obj_set_width(col, 1200);
    lv_obj_set_flex_align(col, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_center(col);
    lv_obj_t *sp = lv_spinner_create(col);
    lv_obj_set_size(sp, 120, 120);
    lv_obj_set_style_arc_width(sp, 10, LV_PART_MAIN);
    lv_obj_set_style_arc_width(sp, 10, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(sp, hex(0x2c2f36), LV_PART_MAIN);
    lv_obj_set_style_arc_color(sp, hex(C_ACCENT), LV_PART_INDICATOR);
    lv_obj_set_style_margin_bottom(sp, 24, 0);
    text(col, &lv_font_montserrat_48, C_TEXT, title);
    text(col, &lv_font_montserrat_32, C_TEXT2, body);
}

static void ui_overlay_clear(void)
{
    if (ui.overlay) {
        lv_obj_delete(ui.overlay);
        ui.overlay = NULL;
    }
}

static void modal_close(lv_event_t *e)
{
    (void)e;
    if (ui.modal) {
        lv_obj_delete(ui.modal);
        ui.modal = NULL;
    }
}

static void start_action(enum action a);

static void modal_confirm(lv_event_t *e)
{
    (void)e;
    enum action a = ui.pending;
    modal_close(NULL);
    start_action(a);
}

static lv_obj_t *modal_button(lv_obj_t *parent, const char *label, bool primary, lv_event_cb_t cb)
{
    lv_obj_t *b = lv_button_create(parent);
    lv_obj_remove_style_all(b);
    lv_obj_set_size(b, 340, 112);
    lv_obj_set_style_radius(b, 26, 0);
    lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(b, hex(primary ? C_ACCENT : 0x24272d), 0);
    lv_obj_set_style_bg_color(b, hex(primary ? C_ACCENT_PRESSED : 0x30343b), LV_STATE_PRESSED);
    lv_obj_center(text(b, &lv_font_montserrat_32, primary ? 0xffffff : C_TEXT, label));
    lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, NULL);
    return b;
}

static lv_obj_t *dialog_card(lv_obj_t *parent, int width)
{
    lv_obj_t *card = box(parent);
    lv_obj_set_size(card, width, LV_SIZE_CONTENT);
    card_style(card, 0x15171b, 40);
    lv_obj_set_style_pad_all(card, 64, 0);
    lv_obj_center(card);
    return card;
}

static void ui_confirm(enum action a, const char *symbol, uint32_t tint, const char *title,
                       const char *body, const char *confirm)
{
    ui.pending = a;
    ui.modal = backdrop(LV_OPA_80);
    lv_obj_t *col = column(dialog_card(ui.modal, 1040), 24);

    lv_obj_t *icon = box(col);
    lv_obj_set_size(icon, 104, 104);
    lv_obj_set_style_radius(icon, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(icon, hex(tint), 0);
    lv_obj_set_style_bg_opa(icon, LV_OPA_20, 0);
    lv_obj_center(text(icon, &lv_font_montserrat_48, tint, symbol));
    lv_obj_set_style_margin_bottom(icon, 12, 0);

    text(col, &lv_font_montserrat_48, C_TEXT, title);
    lv_obj_t *b = text(col, &lv_font_montserrat_32, C_TEXT2, body);
    lv_label_set_long_mode(b, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(b, LV_PCT(100));

    lv_obj_t *buttons = row(col, 24);
    lv_obj_set_width(buttons, LV_PCT(100));
    lv_obj_set_flex_align(buttons, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_margin_top(buttons, 32, 0);
    modal_button(buttons, "Cancel", false, modal_close);
    modal_button(buttons, confirm, true, modal_confirm);
}

/* Progress shown while the power key is held. */
static void ui_hold(int permille)
{
    if (permille < 0) {
        if (ui.hold) {
            lv_obj_delete(ui.hold);
            ui.hold = NULL;
        }
        return;
    }
    if (!ui.hold) {
        ui.hold = backdrop(LV_OPA_80);
        lv_obj_t *col = column(dialog_card(ui.hold, 960), 24);
        lv_obj_t *icon = box(col);
        lv_obj_set_size(icon, 104, 104);
        lv_obj_set_style_radius(icon, LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_bg_color(icon, hex(C_ACCENT), 0);
        lv_obj_set_style_bg_opa(icon, LV_OPA_20, 0);
        lv_obj_center(text(icon, &lv_font_montserrat_48, C_ACCENT, LV_SYMBOL_PLAY));
        lv_obj_set_style_margin_bottom(icon, 12, 0);
        text(col, &lv_font_montserrat_48, C_TEXT, "Keep holding Power");
        text(col, &lv_font_montserrat_32, C_TEXT2, "Debian starts when the bar is full.");
        ui.hold_bar = lv_bar_create(col);
        lv_obj_set_size(ui.hold_bar, LV_PCT(100), 16);
        lv_obj_set_style_margin_top(ui.hold_bar, 24, 0);
        lv_obj_set_style_bg_color(ui.hold_bar, hex(0x24272d), LV_PART_MAIN);
        lv_obj_set_style_bg_color(ui.hold_bar, hex(C_ACCENT), LV_PART_INDICATOR);
        lv_bar_set_range(ui.hold_bar, 0, 1000);
    }
    lv_bar_set_value(ui.hold_bar, permille, LV_ANIM_OFF);
}

/* ------------------------------------------------------------------ */
/* Platform: preview renderer on the build host                        */

#ifdef TABS3_PREVIEW

static uint32_t *frame;

static void flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px)
{
    int w = lv_area_get_width(area);
    for (int y = area->y1; y <= area->y2; y++)
        memcpy(&frame[y * W + area->x1], px + (size_t)(y - area->y1) * w * 4, (size_t)w * 4);
    lv_display_flush_ready(disp);
}

static uint32_t tick_cb(void)
{
    static uint32_t t;
    return t += 40;
}

static void start_action(enum action a) { (void)a; }

static void on_tile(lv_event_t *e) { (void)e; }

static void save(const char *dir, const char *name)
{
    char path[512];
    for (int i = 0; i < 8; i++)
        lv_timer_handler();
    lv_refr_now(NULL);
    snprintf(path, sizeof path, "%s/%s.ppm", dir, name);
    FILE *f = fopen(path, "wb");
    if (!f) {
        perror(path);
        exit(1);
    }
    fprintf(f, "P6\n%d %d\n255\n", W, H);
    for (int i = 0; i < W * H; i++) {
        uint32_t p = frame[i];
        unsigned char rgb[3] = { (p >> 16) & 0xff, (p >> 8) & 0xff, p & 0xff };
        fwrite(rgb, 1, 3, f);
    }
    fclose(f);
}

int main(int argc, char **argv)
{
    const char *dir = argc > 1 ? argv[1] : ".";
    static uint8_t buf[W * 256 * 4];
    frame = calloc((size_t)W * H, 4);
    lv_init();
    lv_tick_set_cb(tick_cb);
    lv_display_t *disp = lv_display_create(W, H);
    lv_display_set_color_format(disp, LV_COLOR_FORMAT_XRGB8888);
    lv_display_set_buffers(disp, buf, NULL, sizeof buf, LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_flush_cb(disp, flush_cb);
    lv_display_set_dpi(disp, 264);

    ui_create();
    struct rec_status s = { .valid = true, .root_bytes = 30421266432ULL, .root_free_bytes = 28797947904ULL,
                            .boot_ok = true, .usb_host = true };
    strcpy(s.root_state, "clean");
    strcpy(s.root_layout, "userdata + system");
    strcpy(s.boot_desc, "Debian, extended root");
    strcpy(s.usb_export, "off");
    ui_set_status(&s);
    if (argc > 1 && !strcmp(argv[1], "--test-hitboxes")) {
        lv_obj_update_layout(lv_screen_active());
        for (int a = 0; a < ACT_COUNT; a++) {
            lv_obj_t *objects[] = { ui.tiles[a].icon, ui.tiles[a].title,
                                    ui.tiles[a].desc, ui.tiles[a].btn };
            for (unsigned j = 0; j < sizeof(objects) / sizeof(objects[0]); j++) {
                lv_area_t area;
                lv_obj_get_coords(objects[j], &area);
                lv_point_t p = { (area.x1 + area.x2) / 2, (area.y1 + area.y2) / 2 };
                if (lv_indev_search_obj(lv_screen_active(), &p) != ui.tiles[a].btn) {
                    fprintf(stderr, "Tile %d child %u intercepts touches\n", a, j);
                    return 1;
                }
            }
        }
        puts("All recovery buttons accept touches on their icons, titles, descriptions and centres");
        return 0;
    }
    ui_log("Recovery started");
    ui_log("Debian root: 28.3 GB ext4, clean");
    save(dir, "1-home");

    ui_set_busy(ACT_FSCK, "Checking the Debian root...");
    ui_log("Checking /dev/mapper/tabs3root ...");
    ui_log("Pass 1: Checking inodes, blocks, and sizes");
    save(dir, "2-checking");
    ui_set_busy(-1, "");

    ui_confirm(ACT_POWEROFF, LV_SYMBOL_POWER, C_ACCENT, "Power off the tablet?",
               "Debian stays untouched. Press Power to switch the tablet on again.", "Power off");
    save(dir, "3-confirm");
    modal_close(NULL);

    strcpy(s.usb_export, "ro");
    ui_set_status(&s);
    ui_log("e2fsck finished with exit code 0");
    ui_log("Filesystem check finished: no errors");
    ui_log("Whole eMMC exported to the PC over USB (ro)");
    save(dir, "4-usb");
    ui_hold(450);
    save(dir, "5-hold");
    ui_hold(-1);

    ui_overlay("Starting Debian", "The tablet restarts now.");
    save(dir, "6-boot");
    return 0;
}

#else /* ------------------------------------------------------------ */
/* Platform: the tablet                                                */

#include <dirent.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <linux/kd.h>
#include <poll.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/wait.h>

#define PANEL_BLANK "/sys/class/graphics/fb0/blank"
#define IDLE_MS (10 * 60 * 1000)
#define HOLD_MS 3000

static int fb_fd = -1, tty_fd = -1, key_fd = -1;
static long fb_stride;
static lv_indev_t *touch;
static lv_indev_read_cb_t touch_read_original;
static bool screen_on = true;
static bool consuming_wake_touch;
static uint32_t power_down_ms;
static bool power_down, power_fired;

static uint32_t now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

/* Writes go through the fbdev write path, which tells DRM what changed;
 * this command-mode panel only updates for such damage. */
static void flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px)
{
    int w = lv_area_get_width(area);
    size_t len = (size_t)w * 4;
    if (area->x1 == 0 && w == W && fb_stride == W * 4) {
        size_t total = len * lv_area_get_height(area);
        if (pwrite(fb_fd, px, total, (off_t)area->y1 * fb_stride) < 0)
            perror("fb");
    } else {
        for (int y = area->y1; y <= area->y2; y++)
            if (pwrite(fb_fd, px + (size_t)(y - area->y1) * len, len,
                       (off_t)y * fb_stride + area->x1 * 4) < 0)
                perror("fb");
    }
    lv_display_flush_ready(disp);
}

static void set_screen(bool on)
{
    if (on == screen_on)
        return;
    int fd = open(PANEL_BLANK, O_WRONLY);
    if (fd < 0) {
        perror(PANEL_BLANK);
        return;
    }
    ssize_t written = write(fd, on ? "0" : "4", 1);
    close(fd);
    if (written != 1) {
        perror(PANEL_BLANK);
        return;
    }
    screen_on = on;
    fprintf(stderr, "Screen %s requested\n", on ? "on" : "off");
    if (touch)
        lv_indev_wait_release(touch);
    if (on) {
        lv_display_trigger_activity(NULL);
        lv_obj_invalidate(lv_screen_active());
    }
}

/* Keep draining LVGL's own evdev queue while dark. Disabling the device
 * and watching a second fd left old presses queued; waking replayed them
 * against buttons the user could not see. Consume the wake gesture through
 * its release, so it never also selects an action.
 */
static void touch_read_cb(lv_indev_t *indev, lv_indev_data_t *data)
{
    bool was_off = !screen_on;
    touch_read_original(indev, data);
    if (was_off && data->state == LV_INDEV_STATE_PRESSED) {
        consuming_wake_touch = true;
        if (!screen_on)
            set_screen(true);
    }
    if (was_off || consuming_wake_touch) {
        if (data->state == LV_INDEV_STATE_RELEASED)
            consuming_wake_touch = false;
        data->state = LV_INDEV_STATE_RELEASED;
    }
}

/* Opt-in hardware check using the same LVGL input mapping as the menu. */
static const lv_point_t touch_targets[] = {
    {128, 128}, {W - 129, 128}, {W / 2, H / 2},
    {128, H - 129}, {W - 129, H - 129},
};
static lv_obj_t *touch_test_overlay, *touch_test_target;
static unsigned touch_test_step;

static void touch_test_click(lv_event_t *e)
{
    (void)e;
    lv_point_t p;
    lv_indev_t *input = lv_indev_active();
    if (!input)
        return;
    lv_indev_get_point(input, &p);
    lv_point_t target = touch_targets[touch_test_step];
    int dx = p.x - target.x, dy = p.y - target.y;
    bool pass = dx * dx + dy * dy <= 90 * 90;
    fprintf(stderr, "Touch test %u: target=%d,%d actual=%d,%d %s\n",
            touch_test_step + 1, (int)target.x, (int)target.y,
            (int)p.x, (int)p.y, pass ? "PASS" : "MISS");
    if (!pass)
        return;
    if (++touch_test_step == sizeof(touch_targets) / sizeof(touch_targets[0])) {
        lv_obj_delete(touch_test_overlay);
        touch_test_overlay = NULL;
        fprintf(stderr, "Touch test: all five points passed\n");
        ui_log("Touch test passed: corners and centre");
        return;
    }
    target = touch_targets[touch_test_step];
    lv_obj_set_pos(touch_test_target, target.x - 50, target.y - 50);
}

static void touch_test_start(void)
{
    touch_test_overlay = backdrop(LV_OPA_COVER);
    lv_obj_add_event_cb(touch_test_overlay, touch_test_click, LV_EVENT_CLICKED, NULL);
    lv_obj_t *hint = text(touch_test_overlay, &lv_font_montserrat_48,
                          C_TEXT, "Tap the centre of each pink circle");
    lv_obj_align(hint, LV_ALIGN_CENTER, 0, -180);
    touch_test_target = box(touch_test_overlay);
    lv_obj_set_size(touch_test_target, 100, 100);
    lv_obj_set_style_radius(touch_test_target, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(touch_test_target, hex(C_ACCENT), 0);
    lv_obj_set_style_bg_opa(touch_test_target, LV_OPA_COVER, 0);
    lv_obj_remove_flag(touch_test_target, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_pos(touch_test_target, touch_targets[0].x - 50, touch_targets[0].y - 50);
    fprintf(stderr, "Touch test: ready for five points\n");
}

static int find_input(const char *name_part)
{
    char path[300], name[128];
    DIR *d = opendir("/sys/class/input");
    struct dirent *e;
    int found = -1;
    while (d && (e = readdir(d))) {
        if (strncmp(e->d_name, "event", 5))
            continue;
        snprintf(path, sizeof path, "/sys/class/input/%s/device/name", e->d_name);
        FILE *f = fopen(path, "r");
        if (!f)
            continue;
        if (fgets(name, sizeof name, f) && strstr(name, name_part))
            found = atoi(e->d_name + 5);
        fclose(f);
    }
    if (d)
        closedir(d);
    return found;
}

/* --- tabs3-recovery child processes ------------------------------- */

static pid_t child = -1;
static int child_fd = -1;
static char child_line[512];
static size_t child_len;
static void (*child_done)(int status);

static bool run_async(const char *const argv[], void (*done)(int))
{
    int fds[2];
    if (child > 0 || pipe2(fds, O_CLOEXEC) < 0)
        return false;
    pid_t pid = fork();
    if (pid < 0)
        return false;
    if (pid == 0) {
        dup2(fds[1], 1);
        dup2(fds[1], 2);
        execv(argv[0], (char *const *)argv);
        _exit(127);
    }
    close(fds[1]);
    fcntl(fds[0], F_SETFL, O_NONBLOCK);
    child = pid;
    child_fd = fds[0];
    child_len = 0;
    child_done = done;
    return true;
}

static void child_poll(lv_timer_t *t)
{
    (void)t;
    if (child < 0)
        return;
    char buf[256];
    ssize_t n;
    while ((n = read(child_fd, buf, sizeof buf)) > 0) {
        for (ssize_t i = 0; i < n; i++) {
            if (buf[i] == '\n' || child_len == sizeof child_line - 1) {
                child_line[child_len] = 0;
                ui_log(child_line);
                child_len = 0;
            } else if (buf[i] != '\r') {
                child_line[child_len++] = buf[i];
            }
        }
    }
    int status;
    if (waitpid(child, &status, WNOHANG) == child) {
        close(child_fd);
        child = -1;
        if (child_len) {
            child_line[child_len] = 0;
            ui_log(child_line);
        }
        if (child_done)
            child_done(WIFEXITED(status) ? WEXITSTATUS(status) : -1);
    }
}

static void read_status(void)
{
    /* The helper reads storage; a stalled card must not freeze the screen. */
    FILE *f = popen("timeout 5 " HELPER " _status 2>/dev/null", "r");
    if (!f)
        return;
    struct rec_status s = { .valid = true };
    strcpy(s.usb_export, "off");
    char line[256];
    int lines = 0;
    while (fgets(line, sizeof line, f)) {
        lines++;
        line[strcspn(line, "\n")] = 0;
        char *v = strchr(line, '=');
        if (!v)
            continue;
        *v++ = 0;
        if (!strcmp(line, "root_bytes"))
            s.root_bytes = strtoull(v, NULL, 10);
        else if (!strcmp(line, "root_free_bytes"))
            s.root_free_bytes = strtoull(v, NULL, 10);
        else if (!strcmp(line, "root_state"))
            snprintf(s.root_state, sizeof s.root_state, "%s", v);
        else if (!strcmp(line, "root_layout"))
            snprintf(s.root_layout, sizeof s.root_layout, "%s", v);
        else if (!strcmp(line, "boot_ok"))
            s.boot_ok = !strcmp(v, "1");
        else if (!strcmp(line, "boot_desc"))
            snprintf(s.boot_desc, sizeof s.boot_desc, "%s", v);
        else if (!strcmp(line, "usb_export"))
            snprintf(s.usb_export, sizeof s.usb_export, "%s", v);
        else if (!strcmp(line, "usb_host"))
            s.usb_host = !strcmp(v, "1");
    }
    if (pclose(f) != 0 || lines == 0)
        s.valid = false;
    ui_set_status(&s);
}

static void status_timer(lv_timer_t *t)
{
    (void)t;
    if (child < 0 && !ui.modal && !ui.overlay)
        read_status();
}

static void action_done(int status)
{
    enum action a = (enum action)ui.busy;
    ui_set_busy(-1, "");
    if (a == ACT_FSCK)
        ui_log(fsck_result_message(status));
    if (a == ACT_FASTBOOT && status != 0)
        ui_log("Fastboot entry failed; see the activity log.");
    read_status();
}

static void leave_done(int status)
{
    if (status == 0)
        return;
    /* The helper refused (another operation runs) or failed: do not leave
     * the "Starting Debian" overlay on a tablet that is not restarting. */
    ui_overlay_clear();
    ui_log("Could not leave recovery; see the activity log.");
    read_status();
}

static void start_action(enum action a)
{
    fprintf(stderr, "Recovery action: %s\n", ui.tiles[a].title_idle);
    static const char *const boot[] = { HELPER, "reboot", NULL };
    static const char *const off[] = { HELPER, "poweroff", NULL };
    static const char *const fastboot[] = { HELPER, "fastboot", NULL };
    static const char *const fsck[] = { HELPER, "fsck", NULL };
    static const char *const usb_on[] = { HELPER, "storage", "ro", NULL };
    static const char *const usb_off[] = { HELPER, "storage", "off", NULL };
    switch (a) {
    case ACT_BOOT:
    case ACT_POWEROFF:
        if (child > 0) {
            ui_log("Wait for the running operation to finish before leaving.");
            break;
        }
        if (a == ACT_BOOT)
            ui_overlay("Starting Debian", "The tablet restarts now.");
        else
            ui_overlay("Powering off", "Press Power to switch the tablet on again.");
        lv_refr_now(NULL);
        if (!run_async(a == ACT_BOOT ? boot : off, leave_done))
            ui_overlay_clear();
        break;
    case ACT_FSCK:
        if (run_async(fsck, action_done))
            ui_set_busy(ACT_FSCK, "Checking the Debian root...");
        break;
    case ACT_FASTBOOT:
        if (run_async(fastboot, action_done))
            ui_set_busy(ACT_FASTBOOT, "Entering fastboot...");
        break;
    case ACT_USB: {
        bool on = strcmp(ui.st.usb_export, "off") != 0;
        if (run_async(on ? usb_off : usb_on, action_done))
            ui_set_busy(ACT_USB, "The USB connection restarts...");
        break;
    }
    default:
        break;
    }
}

static void on_tile(lv_event_t *e)
{
    enum action a = (enum action)(intptr_t)lv_event_get_user_data(e);
    if (ui.busy >= 0 || ui.modal || ui.overlay)
        return;
    if (a == ACT_POWEROFF)
        ui_confirm(a, LV_SYMBOL_POWER, C_ACCENT, "Power off the tablet?",
                   "Debian stays untouched. Press Power to switch the tablet on again.", "Power off");
    else if (a == ACT_FASTBOOT)
        ui_confirm(a, LV_SYMBOL_UPLOAD, C_ACCENT, "Enter fastboot?",
                   "The USB connection restarts. Connect to the PC to load a test image. "
                   "After two minutes without commands, the tablet returns to recovery.", "Enter fastboot");
    else if (a == ACT_USB && !strcmp(ui.st.usb_export, "off"))
        ui_confirm(a, LV_SYMBOL_USB, C_WARN, "Show storage on the PC?",
                   "All partitions appear on the computer, read-only. The USB link drops for a "
                   "moment, so SSH sessions reconnect.", "Show on PC");
    else
        start_action(a);
}

/* --- power key, touch wake, idle ----------------------------------- */

static void input_timer(lv_timer_t *t)
{
    (void)t;
    struct input_event ev;
    while (key_fd >= 0 && read(key_fd, &ev, sizeof ev) == sizeof ev) {
        if (ev.type != EV_KEY || ev.code != KEY_POWER)
            continue;
        if (ev.value == 1) {
            power_down = true;
            power_fired = false;
            power_down_ms = now_ms();
        } else if (ev.value == 0 && power_down) {
            power_down = false;
            ui_hold(-1);
            if (!power_fired && now_ms() - power_down_ms < 600)
                set_screen(!screen_on);
        }
    }
    if (power_down && !power_fired) {
        uint32_t held = now_ms() - power_down_ms;
        if (held >= 600 && !ui.overlay) {
            set_screen(true);
            ui_hold((int)((held - 600) * 1000 / (HOLD_MS - 600)));
        }
        if (held >= HOLD_MS && !ui.overlay) {
            power_fired = true;
            ui_hold(-1);
            start_action(ACT_BOOT);
        }
    }
    if (screen_on && !ui.overlay && lv_display_get_inactive_time(NULL) > IDLE_MS)
        set_screen(false);
}

static void restore_console(void)
{
    if (tty_fd >= 0)
        ioctl(tty_fd, KDSETMODE, KD_TEXT);
}

static void on_signal(int sig)
{
    restore_console();
    signal(sig, SIG_DFL);
    raise(sig);
}

int main(void)
{
    struct fb_var_screeninfo var;
    struct fb_fix_screeninfo fix;
    fb_fd = open("/dev/fb0", O_RDWR | O_CLOEXEC);
    if (fb_fd < 0 || ioctl(fb_fd, FBIOGET_VSCREENINFO, &var) || ioctl(fb_fd, FBIOGET_FSCREENINFO, &fix)) {
        perror("/dev/fb0");
        return 1;
    }
    if (var.xres != W || var.yres != H || var.bits_per_pixel != 32) {
        fprintf(stderr, "unexpected framebuffer %ux%u %u bpp\n", var.xres, var.yres, var.bits_per_pixel);
        return 1;
    }
    fb_stride = fix.line_length;

    /* Stop the text console from drawing over the screen. */
    tty_fd = open("/dev/tty1", O_RDWR | O_CLOEXEC);
    if (tty_fd >= 0)
        ioctl(tty_fd, KDSETMODE, KD_GRAPHICS);
    atexit(restore_console);
    signal(SIGTERM, on_signal);
    signal(SIGINT, on_signal);

    static uint8_t buf1[W * 192 * 4], buf2[W * 192 * 4];
    lv_init();
    lv_tick_set_cb(now_ms);
    lv_display_t *disp = lv_display_create(W, H);
    lv_display_set_color_format(disp, LV_COLOR_FORMAT_XRGB8888);
    lv_display_set_buffers(disp, buf1, buf2, sizeof buf1, LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_flush_cb(disp, flush_cb);
    lv_display_set_dpi(disp, 264);

    char path[64];
    int ev = find_input("s5807");
    if (ev >= 0) {
        snprintf(path, sizeof path, "/dev/input/event%d", ev);
        touch = lv_evdev_create(LV_INDEV_TYPE_POINTER, path);
        if (touch) {
            touch_read_original = lv_indev_get_read_cb(touch);
            lv_indev_set_read_cb(touch, touch_read_cb);
            /* The controller reports portrait coordinates (x 0-1535, y 0-2047)
             * for this landscape panel. TABS3_TOUCH=cw selects the other
             * rotation if taps land mirrored. */
            const char *rot = getenv("TABS3_TOUCH");
            lv_evdev_set_swap_axes(touch, true);
            if (rot && !strcmp(rot, "cw"))
                lv_evdev_set_calibration(touch, 2047, 0, 0, 1535);
            else
                lv_evdev_set_calibration(touch, 0, 1535, 2047, 0);
        }
    }
    ev = find_input("pwrkey");
    if (ev >= 0) {
        snprintf(path, sizeof path, "/dev/input/event%d", ev);
        key_fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    }

    ui_create();
    ui_log("Recovery started");
    if (getenv("TABS3_TOUCH_TEST"))
        touch_test_start();
    read_status();
    lv_timer_create(child_poll, 100, NULL);
    lv_timer_create(input_timer, 40, NULL);
    lv_timer_create(status_timer, 4000, NULL);

    for (;;) {
        uint32_t wait = lv_timer_handler();
        if (wait > 40)
            wait = 40;
        usleep(wait * 1000);
    }
}

#endif
