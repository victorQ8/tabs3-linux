// SPDX-License-Identifier: GPL-2.0-only
/*
 * Samsung AMS968HH01 QXGA (2048x1536) AMOLED panel, Anapass ANA38401 DDI,
 * as used in the Samsung Galaxy Tab S3 (SM-T820 / SM-T825).
 *
 * Dual-link (bonded) MIPI DSI, command mode. The DDI takes DCS commands on
 * the first link only (downstream "qcom,dcs-cmd-by-left"); the second link
 * carries pixel data only.
 *
 * Derived from the downstream Samsung display driver and its device tree
 * (drivers/video/msm/mdss/samsung/ANA38401_AMS968HH01).
 *
 * UNTESTED DRAFT - not yet built or run on hardware.
 */

#include <linux/backlight.h>
#include <linux/debugfs.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_graph.h>
#include <linux/regulator/consumer.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/workqueue.h>

#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>
#include <drm/drm_probe_helper.h>
#include <video/mipi_display.h>

/*
 * Bring-up switches, settable on the kernel command line as
 * panel_samsung_ams968hh01.<name>=0|1.
 */
static bool stock_clock = true;
module_param(stock_clock, bool, 0444);
MODULE_PARM_DESC(stock_clock, "Run the DSI lanes at the stock 893.2 Mbps instead of 760.8 Mbps");

static bool tear_on = true;
module_param(tear_on, bool, 0444);
MODULE_PARM_DESC(tear_on, "Send DCS set_tear_on after display on, as downstream mdss_dsi does");

static bool keep_vdd = true;
module_param(keep_vdd, bool, 0644);
MODULE_PARM_DESC(keep_vdd, "Keep the panel 3.3 V supply on while the display is off");

static bool init_toggle;
module_param(init_toggle, bool, 0644);
MODULE_PARM_DESC(init_toggle, "Toggle compression mode inside the init sequence");

static int fixup = 2;
module_param(fixup, int, 0644);
MODULE_PARM_DESC(fixup, "Re-apply display on and DSI input setup after enable: 0 off, 1 in enable, 2 delayed");

static unsigned int fixup_delay_ms = 5000;
module_param(fixup_delay_ms, uint, 0644);
MODULE_PARM_DESC(fixup_delay_ms, "Delay for fixup=2, after frames have started");

static unsigned int fixup_gap_ms = 600;
module_param(fixup_gap_ms, uint, 0644);
MODULE_PARM_DESC(fixup_gap_ms, "fixup=2: pause between steps so the DDI sees frames in between");

static bool mtp_gamma = true;
module_param(mtp_gamma, bool, 0444);
MODULE_PARM_DESC(mtp_gamma, "Apply the panel's factory MTP calibration to the 360 nit gamma table");

static bool diag;
module_param(diag, bool, 0444);
MODULE_PARM_DESC(diag, "Log DDI power mode and ID registers during power-on");

static bool read_hs = true;
module_param(read_hs, bool, 0444);
MODULE_PARM_DESC(read_hs, "Send diagnostic reads in HS mode, as downstream rx commands default to");

struct ams968hh01 {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi[2];
	struct regulator *vdd;
	struct gpio_desc *reset_gpio;
	struct gpio_desc *tcon_ready_gpio;
	bool vdd_on;
	bool enabled;		/* between enable() and disable() */
	bool screen_off;	/* backlight bl_power requested off */
	struct mutex bl_lock;
	u8 gamma[33];
	bool gamma_valid;
	struct delayed_work fixup_work;
	int fixup_step;
	struct dentry *debugfs;
	struct mutex cmd_lock;
	char cmd_result[128];
};

static inline struct ams968hh01 *to_ams968hh01(struct drm_panel *panel)
{
	return container_of(panel, struct ams968hh01, panel);
}

/*
 * Full-panel mode. The msm DSI host halves the horizontal timings per link
 * in bonded mode, so these are twice the downstream per-link values
 * (1024 active, hfp 212, hpw 16, hbp 108; vfp 10, vpw 2, vbp 6).
 */
static const struct drm_display_mode ams968hh01_mode = {
	.clock = 253613,		/* 2720 * 1554 * 60 Hz / 1000 */
	.hdisplay = 2048,
	.hsync_start = 2048 + 424,
	.hsync_end = 2048 + 424 + 32,
	.htotal = 2048 + 424 + 32 + 216,
	.vdisplay = 1536,
	.vsync_start = 1536 + 10,
	.vsync_end = 1536 + 10 + 2,
	.vtotal = 1536 + 10 + 2 + 6,
	.width_mm = 196,
	.height_mm = 147,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

/*
 * Downstream overrides the bit clock with qcom,mdss-dsi-panel-clockrate =
 * 893.2 MHz. The ANA38401 TCON runs from the continuous DSI HS clock and its
 * UPLL is programmed for that rate. In command mode the porches never reach
 * the wire, so widen the front porch to keep 60 Hz at the higher pixel clock:
 * 297733 kHz / 2 links * 24 bpp / 4 lanes = 893.2 Mbps per lane.
 */
static const struct drm_display_mode ams968hh01_stock_clock_mode = {
	.clock = 297733,		/* 3194 * 1554 * 59.98 Hz / 1000 */
	.hdisplay = 2048,
	.hsync_start = 2048 + 898,
	.hsync_end = 2048 + 898 + 32,
	.htotal = 2048 + 898 + 32 + 216,
	.vdisplay = 1536,
	.vsync_start = 1536 + 10,
	.vsync_end = 1536 + 10 + 2,
	.vtotal = 1536 + 10 + 2 + 6,
	.width_mm = 196,
	.height_mm = 147,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

/* Bring-up diagnostics: is the DDI alive and in the expected power mode? */
static void ams968hh01_report(struct ams968hh01 *ctx, const char *stage)
{
	static const u8 regs[] = { 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0xda, 0xdb, 0xdc };
	struct mipi_dsi_device *dsi = ctx->dsi[0];
	unsigned long mode_flags = dsi->mode_flags;
	ssize_t ret;
	u8 val;
	int i;

	if (read_hs)
		dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;
	ret = mipi_dsi_set_maximum_return_packet_size(dsi, 1);
	if (ret < 0)
		dev_warn(&dsi->dev, "%s: set max return size failed: %zd\n", stage, ret);

	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = mipi_dsi_dcs_read(dsi, regs[i], &val, 1);
		if (ret == 1)
			dev_info(&dsi->dev, "%s: DCS 0x%02x = 0x%02x\n", stage, regs[i], val);
		else
			dev_warn(&dsi->dev, "%s: DCS 0x%02x read failed: %zd\n", stage, regs[i], ret);
	}
	dsi->mode_flags = mode_flags;
	dev_info(&dsi->dev, "%s (%s reads): TCON_RDY=%d\n", stage, read_hs ? "HS" : "LP",
		 gpiod_get_value_cansleep(ctx->tcon_ready_gpio));
}

/* Samsung explicitly uses DCS long packets for B1/B2 register writes,
 * including writes with only one parameter. The generic DCS helper would
 * select a short packet for those two-byte payloads.
 */
static void ams968hh01_write_register(struct mipi_dsi_multi_context *ctx,
				    const void *data, size_t len)
{
	struct mipi_dsi_device *dsi = ctx->dsi;
	struct mipi_dsi_msg msg = {
		.channel = dsi->channel,
		.type = MIPI_DSI_DCS_LONG_WRITE,
		.flags = (dsi->mode_flags & MIPI_DSI_MODE_LPM) ? MIPI_DSI_MSG_USE_LPM : 0,
		.tx_len = len,
		.tx_buf = data,
	};
	ssize_t ret;

	if (ctx->accum_err)
		return;
	if (!dsi->host->ops || !dsi->host->ops->transfer) {
		ctx->accum_err = -ENOSYS;
		return;
	}
	ret = dsi->host->ops->transfer(dsi->host, &msg);
	if (ret < 0) {
		ctx->accum_err = ret;
		dev_err(&dsi->dev, "panel long write failed: %zd\n", ret);
	}
}

#define ams968hh01_register_seq(ctx, seq...) do { \
	static const u8 data[] = { seq }; \
	ams968hh01_write_register(ctx, data, ARRAY_SIZE(data)); \
} while (0)

/*
 * Factory gamma calibration (MTP): 33 bytes in register page D8 at global
 * parameter offsets 0x5a..0x7a, register order per colour V11 V23 V35 V51
 * V87 V151 V203 V255lsb V3 V255msb VT. The DDI answers reads only in HS.
 */
static int ams968hh01_read_mtp_once(struct ams968hh01 *ctx, u8 *mtp)
{
	static const u8 pos[] = { 0x5a, 0x62, 0x6a, 0x72, 0x7a };
	struct mipi_dsi_device *dsi = ctx->dsi[0];
	unsigned long mode_flags = dsi->mode_flags;
	ssize_t ret = 0;
	int i;

	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;
	for (i = 0; i < ARRAY_SIZE(pos); i++) {
		u8 len = i < 4 ? 8 : 1;
		u8 params[2] = { 0xd8, len };

		ret = mipi_dsi_dcs_write(dsi, 0xb0, &pos[i], 1);
		if (ret < 0)
			break;
		ret = mipi_dsi_generic_read(dsi, params, sizeof(params), mtp + i * 8, len);
		if (ret != len) {
			ret = ret < 0 ? ret : -EIO;
			break;
		}
	}
	dsi->mode_flags = mode_flags;
	return ret < 0 ? ret : 0;
}

/*
 * The first read after the init sequence returned zeros on SM-T825, so
 * start with a throwaway ID read (expect DA = 0x42) and accept the MTP only
 * when two consecutive reads agree.
 */
static int ams968hh01_read_mtp(struct ams968hh01 *ctx, u8 *mtp)
{
	struct mipi_dsi_device *dsi = ctx->dsi[0];
	unsigned long mode_flags = dsi->mode_flags;
	u8 check[33], id = 0;
	int tries, ret;

	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;
	mipi_dsi_dcs_read(dsi, 0xda, &id, 1);
	ret = mipi_dsi_dcs_read(dsi, 0xda, &id, 1);
	dsi->mode_flags = mode_flags;
	if (ret != 1 || id != 0x42) {
		dev_warn(&dsi->dev, "unexpected DDI ID read %d: %02x\n", ret, id);
		return ret < 0 ? ret : -ENODEV;
	}

	for (tries = 0; tries < 3; tries++) {
		ret = ams968hh01_read_mtp_once(ctx, mtp);
		if (!ret)
			ret = ams968hh01_read_mtp_once(ctx, check);
		if (!ret && !memcmp(mtp, check, sizeof(check)))
			return 0;
	}
	return ret ? ret : -EIO;
}

/*
 * Top luminance table of the downstream smart dimming
 * (gamma_cell_determine + gamma_command_sorting_post): the reference
 * values (V255 = 0x100, V203..V3 = 0x80, VT = 0) plus the MTP bytes,
 * with its clamping. With an all-zero MTP this is the 80 80 .. table.
 */
static void ams968hh01_gamma_from_mtp(const u8 *mtp, u8 *gamma)
{
	static const u8 ref[11] = { 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x00, 0x80, 0x01, 0x00 };
	int c, k;

	for (c = 0; c < 3; c++) {
		for (k = 0; k < 11; k++) {
			int sum = ref[k] + mtp[c * 11 + k] + (ref[k] == 0x01 ? 0x7f : 0);
			u8 *out = &gamma[c * 11 + k];

			*out = sum < 0 ? 0 : sum > 255 ? 0x80 : sum;
		}
		if (gamma[c * 11 + 9] == 0x01)
			gamma[c * 11 + 9] = 0x80;
	}
}

static void ams968hh01_write_gamma(struct ams968hh01 *ctx, struct mipi_dsi_multi_context *dsi_ctx)
{
	u8 buf[34] = { 0x83 };

	if (!ctx->gamma_valid)
		return;
	memcpy(buf + 1, ctx->gamma, sizeof(ctx->gamma));
	mipi_dsi_dcs_write_buffer_multi(dsi_ctx, buf, sizeof(buf));
	mipi_dsi_dcs_write_seq_multi(dsi_ctx, 0xb0, 0x35);
	ams968hh01_register_seq(dsi_ctx, 0xb2, 0x01);		/* gamma update key */
}

/* Stock ACL-on and smart-ACL ELVSS at 360 nit, temperature above 0 C.
 * The on-command list alone leaves cold-start ELVSS and ACL disabled.
 * Apply normal conditions before bright frames and again after input fixup.
 * Verified on SM-T825: otherwise bright graphics wash out and roll.
 */
static void ams968hh01_normal_conditions(struct mipi_dsi_multi_context *ctx)
{
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x4d);
	ams968hh01_register_seq(ctx, 0xb2, 0x05);
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x49);
	ams968hh01_register_seq(ctx, 0xb2, 0x7f);
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x36);
	ams968hh01_register_seq(ctx, 0xb2, 0x12);
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x67);
	ams968hh01_register_seq(ctx, 0xb2, 0x1b);
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x35);
	ams968hh01_register_seq(ctx, 0xb2, 0x01);
}

/* Downstream qcom,mdss-dsi-on-command. B0 = register offset, B1/B2 = write. */
static void ams968hh01_init(struct mipi_dsi_multi_context *ctx)
{
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x34);
	ams968hh01_register_seq(ctx, 0xb2, 0x64, 0x00);	/* check fail off */
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x75);
	ams968hh01_register_seq(ctx, 0xb2, 0x28);		/* INTR setting */
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x51);
	ams968hh01_register_seq(ctx, 0xb1, 0x06);		/* dual DSI */
	/*
	 * The DDI re-applies its input configuration, including the dual DSI
	 * setting above, only when the compression mode register changes.
	 * Writing the reset value alone leaves it single-link: link 0 lines
	 * are decoded as full 2048-pixel rows and link 1 is ignored. Toggle it.
	 */
	if (init_toggle) {
		mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0xd9);
		ams968hh01_register_seq(ctx, 0xb1, 0x00);
	}
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0xd9);
	ams968hh01_register_seq(ctx, 0xb1, 0x08);		/* Anapass compression mode */
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x7f);
	ams968hh01_register_seq(ctx, 0xb2, 0x15);		/* TSP HTE / VTE */

	mipi_dsi_dcs_set_tear_scanline_multi(ctx, 1526);

	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0xbc);
	ams968hh01_register_seq(ctx, 0xb2, 0x04);		/* gamma offset index */

	/* Brightness condition set: fixed 360 nit gamma for now */
	mipi_dsi_dcs_write_seq_multi(ctx, 0x83,
				     0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x00, 0x80, 0x80, 0x00,
				     0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x00, 0x80, 0x80, 0x00,
				     0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x00, 0x80, 0x80, 0x00);

	mipi_dsi_dcs_write_seq_multi(ctx, 0x90, 0x00, 0x00, 0x0e);	/* AID, 360 nit */
	ams968hh01_normal_conditions(ctx);
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x6d);
	ams968hh01_register_seq(ctx, 0xb2, 0x85);		/* CAPS on */
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0x35);
	ams968hh01_register_seq(ctx, 0xb2, 0x01);		/* gamma update key */
	mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, 0xd0);
	ams968hh01_register_seq(ctx, 0xb1, 0x1d);		/* UPLL_F = 35 */
	mipi_dsi_msleep(ctx, 215);
}

/*
 * With the supply cut, the next power-on left the SM-T825 panel dark: the
 * init sequence does not restore everything the bootloader set up. Unless
 * keep_vdd=0, keep the 3.3 V supply on and only hold the DDI in reset, which
 * matches the state the panel is in at boot.
 */
static void ams968hh01_power_off(struct ams968hh01 *ctx)
{
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	usleep_range(5000, 6000);
	if (keep_vdd)
		return;
	regulator_disable(ctx->vdd);
	ctx->vdd_on = false;
	msleep(10);
}

static int ams968hh01_prepare(struct drm_panel *panel)
{
	struct ams968hh01 *ctx = to_ams968hh01(panel);
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi[0] };
	int val, ret;

	if (!ctx->vdd_on) {
		ret = regulator_enable(ctx->vdd);
		if (ret)
			return ret;
		ctx->vdd_on = true;
		msleep(10);
	}

	/*
	 * The DSI lanes are already in LP11 here (prepare_prev_first). The
	 * DDI wants 70 ms plus margin between LP11 and reset.
	 */
	msleep(75);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);

	/* The DDI raises TCON_RDY once it accepts commands (downstream: up to 1 s) */
	ret = read_poll_timeout(gpiod_get_value_cansleep, val, val,
				1000, 1000000, false, ctx->tcon_ready_gpio);
	if (ret)
		dev_warn(panel->dev, "TCON_RDY not asserted, continuing anyway\n");
	usleep_range(1000, 2000);

	ams968hh01_init(&dsi_ctx);
	if (dsi_ctx.accum_err) {
		ams968hh01_power_off(ctx);
		return dsi_ctx.accum_err;
	}
	if (mtp_gamma && !ctx->gamma_valid) {
		u8 mtp[33];

		ret = ams968hh01_read_mtp(ctx, mtp);
		if (ret) {
			dev_warn(panel->dev, "MTP read failed (%d), using reference gamma\n", ret);
		} else {
			ams968hh01_gamma_from_mtp(mtp, ctx->gamma);
			ctx->gamma_valid = true;
			dev_info(panel->dev, "MTP %*ph\n", 33, mtp);
			dev_info(panel->dev, "360 nit gamma %*ph\n", 33, ctx->gamma);
		}
	}
	ams968hh01_write_gamma(ctx, &dsi_ctx);
	if (diag)
		ams968hh01_report(ctx, "after init");

	return 0;
}

/*
 * On SM-T825 the init sequence alone left the DDI dark or single-link.
 * What worked on hardware, with the panel running: display on in HS mode,
 * then a compression mode change, which makes the DDI re-apply its dual DSI
 * input configuration.
 */
/* Send one fixup step in HS mode; returns the accumulated error. */
static int ams968hh01_fixup_step(struct ams968hh01 *ctx, int step)
{
	struct mipi_dsi_device *dsi = ctx->dsi[0];
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = dsi };
	unsigned long mode_flags = dsi->mode_flags;

	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;
	switch (step) {
	case 0:
		if (!READ_ONCE(ctx->screen_off))
			mipi_dsi_dcs_set_display_on_multi(&dsi_ctx);
		break;
	case 1:
		mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xb0, 0xd9);
		ams968hh01_register_seq(&dsi_ctx, 0xb1, 0x00);
		break;
	case 2:
		mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xb0, 0xd9);
		ams968hh01_register_seq(&dsi_ctx, 0xb1, 0x08);
		mipi_dsi_dcs_write_seq_multi(&dsi_ctx, 0xb0, 0x51);
		ams968hh01_register_seq(&dsi_ctx, 0xb1, 0x06);
		ams968hh01_write_gamma(ctx, &dsi_ctx);
		break;
	case 3:
		/* The DDI must see frames after the compression change before
		 * accepting its normal drive conditions. Same-transfer settings
		 * did not persist; sending them later on the live panel did.
		 */
		ams968hh01_normal_conditions(&dsi_ctx);
		break;
	}
	dsi->mode_flags = mode_flags;
	if (dsi_ctx.accum_err)
		dev_err(&dsi->dev, "DSI input fixup step %d failed: %d\n", step, dsi_ctx.accum_err);
	else
		dev_info(&dsi->dev, "DSI input fixup step %d sent\n", step);
	return dsi_ctx.accum_err;
}

/*
 * On SM-T825 the init sequence alone left the DDI dark or single-link.
 * What worked on hardware, with frames flowing: display on in HS mode,
 * compression mode 00, frames, then compression 08 and dual DSI, which
 * makes the DDI re-apply its dual DSI input configuration.
 */
static void ams968hh01_fixup(struct ams968hh01 *ctx)
{
	int step;

	for (step = 0; step <= 3; step++) {
		if (step)
			msleep(fixup_gap_ms);
		if (ams968hh01_fixup_step(ctx, step))
			return;
	}
}

static void ams968hh01_fixup_work(struct work_struct *work)
{
	struct ams968hh01 *ctx = container_of(to_delayed_work(work), struct ams968hh01, fixup_work);

	if (ams968hh01_fixup_step(ctx, ctx->fixup_step) || ++ctx->fixup_step > 3)
		return;
	schedule_delayed_work(&ctx->fixup_work, msecs_to_jiffies(fixup_gap_ms));
}

static void ams968hh01_start_fixup(struct ams968hh01 *ctx, unsigned int delay_ms)
{
	cancel_delayed_work_sync(&ctx->fixup_work);
	ctx->fixup_step = 0;
	schedule_delayed_work(&ctx->fixup_work, msecs_to_jiffies(delay_ms));
}

static int ams968hh01_enable(struct drm_panel *panel)
{
	struct ams968hh01 *ctx = to_ams968hh01(panel);
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi[0] };

	mipi_dsi_dcs_set_display_on_multi(&dsi_ctx);
	mipi_dsi_msleep(&dsi_ctx, 50);
	if (tear_on)
		mipi_dsi_dcs_set_tear_on_multi(&dsi_ctx, MIPI_DSI_DCS_TEAR_MODE_VBLANK);
	if (diag && !dsi_ctx.accum_err)
		ams968hh01_report(ctx, "after display on");
	if (dsi_ctx.accum_err)
		return dsi_ctx.accum_err;

	if (fixup == 1)
		ams968hh01_fixup(ctx);
	else if (fixup == 2)
		ams968hh01_start_fixup(ctx, fixup_delay_ms);

	mutex_lock(&ctx->bl_lock);
	ctx->enabled = true;
	if (ctx->screen_off)
		mipi_dsi_dcs_set_display_off(ctx->dsi[0]);
	mutex_unlock(&ctx->bl_lock);

	return 0;
}

static int ams968hh01_disable(struct drm_panel *panel)
{
	struct ams968hh01 *ctx = to_ams968hh01(panel);
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi[0] };

	cancel_delayed_work_sync(&ctx->fixup_work);
	mutex_lock(&ctx->bl_lock);
	ctx->enabled = false;
	mutex_unlock(&ctx->bl_lock);
	mipi_dsi_dcs_set_display_off_multi(&dsi_ctx);
	mipi_dsi_msleep(&dsi_ctx, 100);

	return dsi_ctx.accum_err;
}

static int ams968hh01_unprepare(struct drm_panel *panel)
{
	ams968hh01_power_off(to_ams968hh01(panel));
	return 0;
}

static int ams968hh01_get_modes(struct drm_panel *panel,
				struct drm_connector *connector)
{
	return drm_connector_helper_get_modes_fixed(connector, stock_clock ?
						    &ams968hh01_stock_clock_mode :
						    &ams968hh01_mode);
}

/*
 * Bring-up only: send raw DSI packets on link 0 while the display runs.
 *   echo "39 b1 08" > cmd       write, HS; prefix "lp" for LP mode
 *   echo "06 0a 1" > cmd        read 1 byte (DCS read 0x06 or generic 0x14/0x24)
 *   cat cmd                     result of the last transfer
 */
static ssize_t ams968hh01_cmd_write(struct file *file, const char __user *ubuf,
				    size_t count, loff_t *ppos)
{
	struct ams968hh01 *ctx = file->private_data;
	struct mipi_dsi_device *dsi = ctx->dsi[0];
	struct mipi_dsi_msg msg = { .channel = dsi->channel };
	u8 tx[256], rx[16];
	char *buf, *cur, *tok;
	int n = 0, rx_len = 0;
	unsigned int val;
	ssize_t ret;

	if (count > 1024)
		return -E2BIG;
	buf = memdup_user_nul(ubuf, count);
	if (IS_ERR(buf))
		return PTR_ERR(buf);
	cur = buf;

	while ((tok = strsep(&cur, " \t\n"))) {
		if (!*tok)
			continue;
		if (!n && !msg.type && !strcmp(tok, "lp")) {
			msg.flags |= MIPI_DSI_MSG_USE_LPM;
			continue;
		}
		if (kstrtouint(tok, 16, &val) || val > 0xff || n == sizeof(tx)) {
			kfree(buf);
			return -EINVAL;
		}
		if (!msg.type) {
			msg.type = val;
			continue;
		}
		tx[n++] = val;
	}
	kfree(buf);
	if (!msg.type || !n)
		return -EINVAL;

	if (msg.type == MIPI_DSI_DCS_READ ||
	    msg.type == MIPI_DSI_GENERIC_READ_REQUEST_1_PARAM ||
	    msg.type == MIPI_DSI_GENERIC_READ_REQUEST_2_PARAM) {
		rx_len = tx[--n];
		if (!rx_len || rx_len > sizeof(rx) || !n)
			return -EINVAL;
		msg.rx_buf = rx;
		msg.rx_len = rx_len;
	}
	msg.tx_buf = tx;
	msg.tx_len = n;

	mutex_lock(&ctx->cmd_lock);
	ret = dsi->host->ops->transfer(dsi->host, &msg);
	if (ret < 0) {
		snprintf(ctx->cmd_result, sizeof(ctx->cmd_result), "error %zd\n", ret);
	} else if (rx_len) {
		int i, len = 0;

		for (i = 0; i < min_t(int, ret, rx_len); i++)
			len += scnprintf(ctx->cmd_result + len, sizeof(ctx->cmd_result) - len,
					 "%02x ", rx[i]);
		scnprintf(ctx->cmd_result + len, sizeof(ctx->cmd_result) - len, "(%zd bytes)\n", ret);
	} else {
		snprintf(ctx->cmd_result, sizeof(ctx->cmd_result), "ok %zd\n", ret);
	}
	mutex_unlock(&ctx->cmd_lock);

	return ret < 0 ? ret : count;
}

static ssize_t ams968hh01_cmd_read(struct file *file, char __user *ubuf,
				   size_t count, loff_t *ppos)
{
	struct ams968hh01 *ctx = file->private_data;

	return simple_read_from_buffer(ubuf, count, ppos, ctx->cmd_result,
				       strlen(ctx->cmd_result));
}

static ssize_t ams968hh01_fixup_write(struct file *file, const char __user *ubuf,
				      size_t count, loff_t *ppos)
{
	ams968hh01_start_fixup(file->private_data, 0);
	return count;
}

static const struct file_operations ams968hh01_fixup_fops = {
	.owner = THIS_MODULE,
	.open = simple_open,
	.write = ams968hh01_fixup_write,
	.llseek = default_llseek,
};

static const struct file_operations ams968hh01_cmd_fops = {
	.owner = THIS_MODULE,
	.open = simple_open,
	.write = ams968hh01_cmd_write,
	.read = ams968hh01_cmd_read,
	.llseek = default_llseek,
};

/*
 * Screen sleep without re-initialising the panel: a DPMS off/on cycle (full
 * disable/unprepare, then prepare/enable) left the SM-T825 panel dark, but
 * DCS display off/on while the display pipeline keeps running works. Expose
 * that as a backlight device: bl_power 0 = on, anything else = display off.
 * An AMOLED panel emits nothing while its display is off.
 */
static int ams968hh01_bl_update_status(struct backlight_device *bl)
{
	struct ams968hh01 *ctx = bl_get_data(bl);
	struct mipi_dsi_device *dsi = ctx->dsi[0];
	bool off = backlight_is_blank(bl);
	unsigned long mode_flags;
	int ret = 0;

	mutex_lock(&ctx->bl_lock);
	if (off != ctx->screen_off) {
		if (ctx->enabled) {
			mode_flags = dsi->mode_flags;
			dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;
			if (off) {
				ret = mipi_dsi_dcs_set_display_off(dsi);
			} else {
				struct mipi_dsi_multi_context dsi_ctx = { .dsi = dsi };

				mipi_dsi_dcs_set_display_on_multi(&dsi_ctx);
				ams968hh01_normal_conditions(&dsi_ctx);
				ret = dsi_ctx.accum_err;
			}
			dsi->mode_flags = mode_flags;
		}
		if (!ret)
			ctx->screen_off = off;
	}
	mutex_unlock(&ctx->bl_lock);
	return ret;
}

static const struct backlight_ops ams968hh01_bl_ops = {
	.update_status = ams968hh01_bl_update_status,
};

static const struct drm_panel_funcs ams968hh01_panel_funcs = {
	.prepare = ams968hh01_prepare,
	.enable = ams968hh01_enable,
	.disable = ams968hh01_disable,
	.unprepare = ams968hh01_unprepare,
	.get_modes = ams968hh01_get_modes,
};

static int ams968hh01_probe(struct mipi_dsi_device *dsi)
{
	const struct mipi_dsi_device_info info = {
		.type = "ams968hh01",
		.channel = 0,
		.node = NULL,
	};
	struct device *dev = &dsi->dev;
	struct mipi_dsi_host *dsi1_host;
	struct device_node *dsi1;
	struct ams968hh01 *ctx;
	int ret, i;

	ctx = devm_kzalloc(dev, sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return -ENOMEM;

	ctx->vdd = devm_regulator_get(dev, "vdd");
	if (IS_ERR(ctx->vdd))
		return dev_err_probe(dev, PTR_ERR(ctx->vdd), "failed to get vdd\n");

	/* Logical 1 = held in reset (reset-gpios is GPIO_ACTIVE_LOW in DT) */
	ctx->reset_gpio = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(ctx->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->reset_gpio), "failed to get reset gpio\n");

	ctx->tcon_ready_gpio = devm_gpiod_get(dev, "tcon-ready", GPIOD_IN);
	if (IS_ERR(ctx->tcon_ready_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->tcon_ready_gpio), "failed to get tcon-ready gpio\n");

	/*
	 * The panel node sits under the master DSI controller and has a second
	 * input port fed by the other controller. Register a DSI device there.
	 */
	dsi1 = of_graph_get_remote_node(dev->of_node, 1, -1);
	if (!dsi1)
		return dev_err_probe(dev, -ENODEV, "no second DSI port\n");
	dsi1_host = of_find_mipi_dsi_host_by_node(dsi1);
	of_node_put(dsi1);
	if (!dsi1_host)
		return dev_err_probe(dev, -EPROBE_DEFER, "second DSI host not ready\n");

	ctx->dsi[0] = dsi;
	ctx->dsi[1] = mipi_dsi_device_register_full(dsi1_host, &info);
	if (IS_ERR(ctx->dsi[1]))
		return dev_err_probe(dev, PTR_ERR(ctx->dsi[1]), "failed to register second DSI device\n");

	mipi_dsi_set_drvdata(dsi, ctx);
	mutex_init(&ctx->bl_lock);
	{
		const struct backlight_properties props = {
			.type = BACKLIGHT_RAW,
			.max_brightness = 1,
			.brightness = 1,
		};
		struct backlight_device *bl;

		bl = devm_backlight_device_register(dev, "ams968hh01", dev, ctx,
						    &ams968hh01_bl_ops, &props);
		if (IS_ERR(bl))
			return dev_err_probe(dev, PTR_ERR(bl), "failed to register backlight\n");
	}
	mutex_init(&ctx->cmd_lock);
	INIT_DELAYED_WORK(&ctx->fixup_work, ams968hh01_fixup_work);
	ctx->debugfs = debugfs_create_dir("ams968hh01", NULL);
	debugfs_create_file("cmd", 0600, ctx->debugfs, ctx, &ams968hh01_cmd_fops);
	debugfs_create_file("fixup", 0200, ctx->debugfs, ctx, &ams968hh01_fixup_fops);

	drm_panel_init(&ctx->panel, dev, &ams968hh01_panel_funcs,
		       DRM_MODE_CONNECTOR_DSI);
	ctx->panel.prepare_prev_first = true;
	drm_panel_add(&ctx->panel);

	for (i = 0; i < ARRAY_SIZE(ctx->dsi); i++) {
		ctx->dsi[i]->lanes = 4;
		ctx->dsi[i]->format = MIPI_DSI_FMT_RGB888;
		/* command mode, init commands in LP, continuous clock */
		ctx->dsi[i]->mode_flags = MIPI_DSI_MODE_LPM;

		ret = mipi_dsi_attach(ctx->dsi[i]);
		if (ret < 0) {
			dev_err(dev, "dsi%d attach failed: %d\n", i, ret);
			goto err_attach;
		}
	}

	return 0;

err_attach:
	while (--i >= 0)
		mipi_dsi_detach(ctx->dsi[i]);
	drm_panel_remove(&ctx->panel);
	mipi_dsi_device_unregister(ctx->dsi[1]);
	return ret;
}

static void ams968hh01_remove(struct mipi_dsi_device *dsi)
{
	struct ams968hh01 *ctx = mipi_dsi_get_drvdata(dsi);

	cancel_delayed_work_sync(&ctx->fixup_work);
	debugfs_remove_recursive(ctx->debugfs);
	mipi_dsi_detach(ctx->dsi[0]);
	mipi_dsi_detach(ctx->dsi[1]);
	mipi_dsi_device_unregister(ctx->dsi[1]);
	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id ams968hh01_of_match[] = {
	{ .compatible = "samsung,ams968hh01" },
	{ }
};
MODULE_DEVICE_TABLE(of, ams968hh01_of_match);

static struct mipi_dsi_driver ams968hh01_driver = {
	.probe = ams968hh01_probe,
	.remove = ams968hh01_remove,
	.driver = {
		.name = "panel-samsung-ams968hh01",
		.of_match_table = ams968hh01_of_match,
	},
};
module_mipi_dsi_driver(ams968hh01_driver);

MODULE_DESCRIPTION("Samsung AMS968HH01 (ANA38401) dual-DSI command mode panel");
MODULE_LICENSE("GPL");
