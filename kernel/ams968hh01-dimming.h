/* SPDX-License-Identifier: GPL-2.0-only */
/* Copyright (C) 2012 Samsung Electronics. All rights reserved.
 * Normal-brightness smart dimming, adapted from Samsung's
 * ss_dsi_smart_dimming_ANA38401_AMS968HH01.c at f48aec90.
 * Explicit unsigned bytes reproduce the downstream ARM64 char semantics.
 * Caller allocates the workspace off stack and holds its panel mutex.
 */
#ifndef AMS968HH01_DIMMING_H
#define AMS968HH01_DIMMING_H

#include "ams968hh01-dimming-data.h"

#define AMS_GAMMA_LEVELS 65
#define AMS_GAMMA_BYTES 33

struct ams_dimming_work {
	s32 gray[3][256];
	s32 vt[3];
};

static int ams_signed_offset(u8 value)
{
	return value & 0x80 ? -(value & 0x7f) : value;
}

static int ams_gray_index(s64 candela)
{
	int i;

	for (i = 0; i < 255; i++) {
		s64 d1 = candela - ams_curve_360[i];
		s64 d2 = candela - ams_curve_360[i + 1];

		if (d2 < 0)
			return d1 + d2 <= 0 ? i : i + 1;
		if (!d1)
			return i;
		if (!d2)
			return i + 1;
	}
	return -EINVAL;
}

static int ams_generate_gamma(const u8 raw[33], u8 out[65][33],
			      struct ams_dimming_work *work)
{
	static const u8 infl[] = { 0, 1, 3, 11, 23, 35, 51, 87, 151, 203, 255 };
	static const u8 sorting[] = {
		9, 7, 6, 5, 4, 3, 2, 1, 0, 8, 10,
		20, 18, 17, 16, 15, 14, 13, 12, 11, 19, 21,
		31, 29, 28, 27, 26, 25, 24, 23, 22, 30, 32,
	};
	static const u8 post[] = {
		24, 21, 18, 15, 12, 9, 6, 1, 27, 0, 30,
		25, 22, 19, 16, 13, 10, 7, 3, 28, 2, 31,
		26, 23, 20, 17, 14, 11, 8, 5, 29, 4, 32,
	};
	static const u8 vt_coeff[] = {
		0, 12, 24, 36, 48, 60, 72, 84, 96, 108, 138, 148, 158, 168, 178, 186,
	};
	static const u8 ref[] = { 128, 128, 128, 128, 128, 128, 128, 0, 128, 1, 0 };
	const u64 ref_l = 28521267, ref_h = 6291456;
	u8 mtp[33];
	int c, i, row;

	memset(work, 0, sizeof(*work));
	for (i = 0; i < 33; i++)
		mtp[i] = raw[sorting[i]];
	for (c = 0; c < 3; c++) {
		u8 *m = mtp + c * 11;
		s32 *g = work->gray[c];
		u64 value, ratio, delta;
		int vt = ams_signed_offset(m[10]);
		int v255 = m[0] ? -m[1] : m[1];

		if (vt < 0 || vt >= 16)
			return -EINVAL;
		ratio = ((u64)(129 + 256 + v255) << 22) / 640;
		g[255] = ref_l - (((ref_l - ref_h) * ratio) >> 22);
		g[0] = ref_l;
		ratio = ((u64)vt_coeff[vt] << 22) / 600;
		work->vt[c] = ref_l - ((ref_l * ratio) >> 22);
		for (i = 9; i >= 3; i--) {
			value = work->vt[c];
			if ((s64)value <= g[infl[i + 1]])
				return -EINVAL;
			delta = value - g[infl[i + 1]];
			ratio = ((u64)(64 + 128 + ams_signed_offset(m[11 - i])) << 22) / 320;
			g[infl[i]] = value - ((delta * ratio) >> 22);
		}
		delta = ref_l - g[11];
		ratio = ((u64)(64 + 128 + ams_signed_offset(m[9])) << 22) / 320;
		g[3] = ref_l - ((delta * ratio) >> 22);
		/* V1 is interpolated between V0 and V3, as in Samsung's code. */
		for (i = 2; i < 11; i++) {
			int low = i == 2 ? 0 : infl[i - 1];
			int high = infl[i], x;
			u64 den = high - low;

			if (g[low] < g[high])
				return -EINVAL;
			for (x = low + 1; x < high; x++) {
				delta = (u64)(g[low] - g[high]) * (high - x);
				g[x] = g[high] + (((delta << 22) / den) >> 22);
			}
		}
	}

	for (row = 0; row < 64; row++) {
		int index[10], adjusted[33];
		u8 gamma[33] = { 0 };

		for (i = 0; i < 10; i++) {
			index[i] = ams_gray_index((s64)ams_coeff_215[infl[i + 1]] * ams_base_luminance[row]);
			if (index[i] < 0)
				return -EINVAL;
		}
		for (i = 1; i < 10; i++) {
			index[10 - i] += ams_gradation[row][i - 1];
			if (!index[10 - i])
				index[10 - i] = 1;
			if (index[10 - i] < 0 || index[10 - i] > 255)
				return -EINVAL;
		}
		for (c = 0; c < 3; c++) {
			s32 *g = work->gray[c];
			u64 value;
			int j;

			value = (ref_l - g[index[9]]) * 640 / (ref_l - ref_h) - 129;
			gamma[c * 2] = value >> 8;
			gamma[c * 2 + 1] = value;
			for (j = 0; j < 8; j++) {
				int lo = 8 - j, hi = 9 - j;
				s64 reference = j == 7 ? (s64)ref_l : work->vt[c];
				s64 den = reference - g[index[hi]];
				s64 num = reference - g[index[lo]];

				if (den <= 0 || num < 0)
					return -EINVAL;
				gamma[6 + j * 3 + c] = (u64)num * 320 / den - 64;
			}
		}
		for (i = 0; i < 33; i++)
			adjusted[i] = gamma[i];
		for (i = 0; i < 24; i++) {
			if (i < 3) {
				int value = ((gamma[2 * i] << 8) | gamma[2 * i + 1]) + ams_rgb_offset[row][i];

				adjusted[2 * i] = (value / 256) & 0xff;
				adjusted[2 * i + 1] = value & 0xff;
			} else {
				adjusted[i + 3] += ams_rgb_offset[row][i];
			}
		}
		for (i = 0; i < 33; i++)
			out[row][i] = adjusted[post[i]];
		for (c = 0; c < 3; c++)
			if (out[row][c * 11 + 9] == 1)
				out[row][c * 11 + 9] = 0x80;
	}
	/* Stock overrides the top level with center-cell gamma plus raw MTP. */
	for (i = 0; i < 33; i++) {
		int value = ref[i % 11] + raw[i] + (ref[i % 11] == 1 ? 127 : 0);

		out[64][i] = value > 255 ? 0x80 : value;
	}
	for (c = 0; c < 3; c++)
		if (out[64][c * 11 + 9] == 1)
			out[64][c * 11 + 9] = 0x80;
	return 0;
}
#endif
