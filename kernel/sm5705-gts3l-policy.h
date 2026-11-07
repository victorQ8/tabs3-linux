/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SM5705_GTS3L_POLICY_H
#define SM5705_GTS3L_POLICY_H

/* SM-T825 rev05 only. Raw ADC tables and temperature thresholds come from
 * this tablet's saved Android DTB, also present in Samsung's GPL source:
 * awesometic/android_kernel_samsung_msm8996 @ f48aec90fcebf4615fdee4a8abac7339930db856
 * arch/arm64/boot/dts/samsung/msm8996-sec-gts3llte-common-battery.dtsi
 * These are raw VADC codes, NOT the generic Qualcomm thermistor conversion.
 */
static const int sm5705_battery_adc[] = {
	25990, 26364, 26586, 26852, 27234, 27669, 28157, 28722,
	29385, 30145, 31002, 31886, 32810, 33900, 35109, 36041,
	37075, 38044, 38876, 39669, 40359, 40936, 41366,
};
static const int sm5705_charger_adc[] = {
	26206, 26298, 26569, 26888, 27291, 27620, 28146, 28725,
	29375, 30179, 31036, 31721, 32982, 34048, 35118, 36013,
	37021, 37831, 38856, 39629, 40307, 40938, 41425,
};

/* Output is deci-Celsius. Reject open/short/out-of-table samples. */
static inline bool sm5705_temperature(int raw, bool charger, int *temp)
{
	const int *adc = charger ? sm5705_charger_adc : sm5705_battery_adc;
	unsigned int i;

	if (raw < adc[0] || raw > adc[22])
		return false;
	for (i = 1; i < 23; i++) {
		if (raw <= adc[i]) {
			*temp = 900 - (int)(i - 1) * 50 -
				(raw - adc[i - 1]) * 50 / (adc[i] - adc[i - 1]);
			return true;
		}
	}
	return false;
}

struct sm5705_safety {
	bool blocked;
	bool cool;
	bool charger_hot;
};

struct sm5705_limits {
	int input_ua;
	int charge_ua;
	bool enable;
};

/* Conservative subset of Samsung's swelling policy: stop outside 5..41 C,
 * recover at 10..39 C. Samsung additionally lowers the float voltage outside
 * its normal range; this port stops instead and never raises float voltage.
 * Cool batteries are limited to 900 mA until 20 C. Charger-board heat at
 * 50 C caps input at 500 mA until 47 C, below Samsung's 1400 mA derating.
 * Battery inhibit does not shut down the system's input supply. A sensor
 * failure inhibits battery charging and caps system input at 500 mA.
 * The caller supplies 500 mA for valid but unclassified VBUS, and the minimum
 * for disconnected sources; hardware/control faults bypass this policy.
 */
static inline struct sm5705_limits
sm5705_choose_limits(struct sm5705_safety *s, bool valid, int battery_temp,
		     int charger_temp, int source_ua, int user_ua,
		     bool automatic, bool inhibit)
{
	struct sm5705_limits out = { 100000, 100000, false };

	if (!valid || battery_temp <= 50 || battery_temp >= 410)
		s->blocked = true;
	else if (battery_temp >= 100 && battery_temp <= 390)
		s->blocked = false;
	if (battery_temp < 150)
		s->cool = true;
	else if (battery_temp >= 200)
		s->cool = false;
	if (charger_temp >= 500)
		s->charger_hot = true;
	else if (charger_temp <= 470)
		s->charger_hot = false;

	if (source_ua < 500000)
		return out;
	out.input_ua = source_ua > 1500000 ? 1500000 : source_ua;
	if ((!valid || !automatic || s->charger_hot) && out.input_ua > 500000)
		out.input_ua = 500000;
	if (out.input_ua > user_ua)
		out.input_ua = user_ua;
	if (!valid || s->blocked || inhibit)
		return out;
	out.charge_ua = s->cool || battery_temp >= 390 ? 900000 : 1500000;
	out.enable = true;
	return out;
}
#endif
