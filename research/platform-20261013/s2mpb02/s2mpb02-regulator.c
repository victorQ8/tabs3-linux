// SPDX-License-Identifier: GPL-2.0-only
/*
 * Regulator driver for the Samsung S2MPB02 camera PMIC
 *
 * Copyright (C) 2014 Samsung Electronics
 *
 * Written from Samsung's GPL-2.0 downstream MSM8996 kernel sources
 * (drivers/regulator/s2mpb02-regulator.c, drivers/mfd/s2mpb02-core.c and
 * include/linux/mfd/s2mpb02-private.h), as shipped for the Galaxy Tab S3
 * (SM-T825).  The register map, enable bits and voltage tables below are
 * taken from those sources; no datasheet was available.
 *
 * The S2MPB02 is a single 8-bit-register I2C device (7-bit address 0x59)
 * with two bucks, one buck-boost, eighteen LDOs and a two-channel flash LED
 * driver.  Only the regulators are handled here.  Interrupts, the flash LED
 * driver and suspend modes are not implemented.
 */

#include <linux/array_size.h>
#include <linux/bits.h>
#include <linux/err.h>
#include <linux/i2c.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/regmap.h>
#include <linux/regulator/driver.h>

/*
 * Register map (downstream enum s2mpb02_reg, which starts at 0 and is
 * contiguous; its RSVD5..RSVD8/RSVDA names match their offsets).
 */
#define S2MPB02_REG_ID			0x00
#define S2MPB02_REG_INT1		0x01
#define S2MPB02_REG_INT1M		0x02
#define S2MPB02_REG_ST1			0x03
#define S2MPB02_REG_CTRL		0x04
/* 0x05 - 0x08 reserved */
#define S2MPB02_REG_BBEN_DBT		0x09
/* 0x0a reserved */
#define S2MPB02_REG_B1CTRL1		0x0b	/* BUCK1 enable/mode */
#define S2MPB02_REG_B1CTRL2		0x0c	/* BUCK1 output voltage */
#define S2MPB02_REG_B2CTRL1		0x0d	/* BUCK2 enable/mode */
#define S2MPB02_REG_B2CTRL2		0x0e	/* BUCK2 output voltage */
#define S2MPB02_REG_BB1CTRL1		0x0f	/* Buck-boost enable/mode */
#define S2MPB02_REG_BB1CTRL2		0x10	/* Buck-boost output voltage */
#define S2MPB02_REG_BUCK_RAMP		0x11
#define S2MPB02_REG_FLED_CTRL1		0x12
#define S2MPB02_REG_FLED_CTRL2		0x13
#define S2MPB02_REG_FLED_CUR1		0x14
#define S2MPB02_REG_FLED_TIME1		0x15
#define S2MPB02_REG_FLED_CUR2		0x16
#define S2MPB02_REG_FLED_TIME2		0x17
#define S2MPB02_REG_FLED_IRON1		0x18
#define S2MPB02_REG_FLED_IRON2		0x19
#define S2MPB02_REG_FLED_IRD1		0x1a
#define S2MPB02_REG_FLED_IRD2		0x1b
#define S2MPB02_REG_BST_CTRL1		0x1c
#define S2MPB02_REG_BST_CTRL2		0x1d
#define S2MPB02_REG_L1CTRL		0x1e	/* LDO1 ... LDO18: 0x1e - 0x2f */
#define S2MPB02_REG_L18CTRL		0x2f
#define S2MPB02_REG_LDO_DSCH1		0x30
#define S2MPB02_REG_LDO_DSCH2		0x31
#define S2MPB02_REG_LDO_DSCH3		0x32
#define S2MPB02_MAX_REGISTER		S2MPB02_REG_LDO_DSCH3

/* LDOn control register, n = 1..18 */
#define S2MPB02_REG_LDO_CTRL(n)		(S2MPB02_REG_L1CTRL + (n) - 1)

/*
 * LxCTRL: bit 7 enables the LDO, bits [6:0] select the output voltage.
 * BxCTRL1/BB1CTRL1: bits [7:6] are the enable/mode field; the downstream
 * driver writes 0b11 to enable and 0b00 to disable.  BxCTRL2/BB1CTRL2 hold
 * the full 8-bit output voltage selector.
 */
#define S2MPB02_LDO_ENABLE_MASK		BIT(7)
#define S2MPB02_LDO_VSEL_MASK		GENMASK(6, 0)
#define S2MPB02_BUCK_ENABLE_MASK	GENMASK(7, 6)
#define S2MPB02_BUCK_ENABLE_ON		GENMASK(7, 6)
#define S2MPB02_BUCK_VSEL_MASK		GENMASK(7, 0)

/*
 * Voltage tables (downstream S2MPB02_{LDO,BUCK}_{MIN,STEP}n defines):
 *
 *  LDO1  - LDO5   600000 uV + sel * 12500 uV, sel 0..127 -> 0.6 V .. 2.1875 V
 *  LDO6  - LDO18  600000 uV + sel * 25000 uV, sel 0..127 -> 0.6 V .. 3.775 V
 *  BUCK1, BUCK2   400000 uV + sel *  6250 uV, sel 0..255 -> 0.4 V .. 1.99375 V
 *  BB (buck-boost) 2600000 uV + sel * 12500 uV, sel 0..255 -> 2.6 V .. 5.7875 V
 *
 * The buck-boost top end follows the downstream driver's 8-bit selector; the
 * real output ceiling is almost certainly lower, so always constrain it in
 * the device tree (the SM-T825 stock tree fixes it at 3.5 V).
 */
#define S2MPB02_LDO_MIN_UV		600000
#define S2MPB02_LDO_STEP1_UV		12500	/* LDO1 - LDO5 */
#define S2MPB02_LDO_STEP2_UV		25000	/* LDO6 - LDO18 */
#define S2MPB02_LDO_N_VOLTAGES		128	/* 7-bit selector */
#define S2MPB02_BUCK_MIN_UV		400000
#define S2MPB02_BUCK_STEP_UV		6250
#define S2MPB02_BB_MIN_UV		2600000
#define S2MPB02_BB_STEP_UV		12500
#define S2MPB02_BUCK_N_VOLTAGES		256	/* 8-bit selector */

/* Downstream S2MPB02_RAMP_DELAY (uV/us) and S2MPB02_ENABLE_TIME_* (us) */
#define S2MPB02_RAMP_DELAY_UV_US	12000
#define S2MPB02_ENABLE_TIME_LDO_US	180
#define S2MPB02_ENABLE_TIME_BUCK_US	100
#define S2MPB02_ENABLE_TIME_BB_US	210

enum s2mpb02_regulator_id {
	S2MPB02_LDO1,
	S2MPB02_LDO2,
	S2MPB02_LDO3,
	S2MPB02_LDO4,
	S2MPB02_LDO5,
	S2MPB02_LDO6,
	S2MPB02_LDO7,
	S2MPB02_LDO8,
	S2MPB02_LDO9,
	S2MPB02_LDO10,
	S2MPB02_LDO11,
	S2MPB02_LDO12,
	S2MPB02_LDO13,
	S2MPB02_LDO14,
	S2MPB02_LDO15,
	S2MPB02_LDO16,
	S2MPB02_LDO17,
	S2MPB02_LDO18,
	S2MPB02_BUCK1,
	S2MPB02_BUCK2,
	S2MPB02_BB,
	S2MPB02_NUM_REGULATORS,
};

static const struct regulator_ops s2mpb02_regulator_ops = {
	.list_voltage		= regulator_list_voltage_linear,
	.map_voltage		= regulator_map_voltage_linear,
	.is_enabled		= regulator_is_enabled_regmap,
	.enable			= regulator_enable_regmap,
	.disable		= regulator_disable_regmap,
	.get_voltage_sel	= regulator_get_voltage_sel_regmap,
	.set_voltage_sel	= regulator_set_voltage_sel_regmap,
	.set_voltage_time_sel	= regulator_set_voltage_time_sel,
};

/* Device tree subnodes under "regulators": ldo1 .. ldo18, buck1, buck2, bb */
#define S2MPB02_LDO_DESC(num, _step)					\
{									\
	.name		= "s2mpb02-ldo" #num,				\
	.of_match	= "ldo" #num,					\
	.regulators_node = "regulators",				\
	.id		= S2MPB02_LDO##num,				\
	.ops		= &s2mpb02_regulator_ops,			\
	.type		= REGULATOR_VOLTAGE,				\
	.owner		= THIS_MODULE,					\
	.min_uV		= S2MPB02_LDO_MIN_UV,				\
	.uV_step	= (_step),					\
	.n_voltages	= S2MPB02_LDO_N_VOLTAGES,			\
	.ramp_delay	= S2MPB02_RAMP_DELAY_UV_US,			\
	.enable_time	= S2MPB02_ENABLE_TIME_LDO_US,			\
	.vsel_reg	= S2MPB02_REG_LDO_CTRL(num),			\
	.vsel_mask	= S2MPB02_LDO_VSEL_MASK,			\
	.enable_reg	= S2MPB02_REG_LDO_CTRL(num),			\
	.enable_mask	= S2MPB02_LDO_ENABLE_MASK,			\
}

#define S2MPB02_BUCK_DESC(_name, _match, _id, _min, _step, _ctrl1, _ctrl2, \
			  _enable_time)					\
{									\
	.name		= _name,					\
	.of_match	= _match,					\
	.regulators_node = "regulators",				\
	.id		= _id,						\
	.ops		= &s2mpb02_regulator_ops,			\
	.type		= REGULATOR_VOLTAGE,				\
	.owner		= THIS_MODULE,					\
	.min_uV		= (_min),					\
	.uV_step	= (_step),					\
	.n_voltages	= S2MPB02_BUCK_N_VOLTAGES,			\
	.ramp_delay	= S2MPB02_RAMP_DELAY_UV_US,			\
	.enable_time	= (_enable_time),				\
	.vsel_reg	= (_ctrl2),					\
	.vsel_mask	= S2MPB02_BUCK_VSEL_MASK,			\
	.enable_reg	= (_ctrl1),					\
	.enable_mask	= S2MPB02_BUCK_ENABLE_MASK,			\
	.enable_val	= S2MPB02_BUCK_ENABLE_ON,			\
}

static const struct regulator_desc s2mpb02_regulators[] = {
	S2MPB02_LDO_DESC(1, S2MPB02_LDO_STEP1_UV),
	S2MPB02_LDO_DESC(2, S2MPB02_LDO_STEP1_UV),
	S2MPB02_LDO_DESC(3, S2MPB02_LDO_STEP1_UV),
	S2MPB02_LDO_DESC(4, S2MPB02_LDO_STEP1_UV),
	S2MPB02_LDO_DESC(5, S2MPB02_LDO_STEP1_UV),
	S2MPB02_LDO_DESC(6, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(7, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(8, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(9, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(10, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(11, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(12, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(13, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(14, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(15, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(16, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(17, S2MPB02_LDO_STEP2_UV),
	S2MPB02_LDO_DESC(18, S2MPB02_LDO_STEP2_UV),
	S2MPB02_BUCK_DESC("s2mpb02-buck1", "buck1", S2MPB02_BUCK1,
			  S2MPB02_BUCK_MIN_UV, S2MPB02_BUCK_STEP_UV,
			  S2MPB02_REG_B1CTRL1, S2MPB02_REG_B1CTRL2,
			  S2MPB02_ENABLE_TIME_BUCK_US),
	S2MPB02_BUCK_DESC("s2mpb02-buck2", "buck2", S2MPB02_BUCK2,
			  S2MPB02_BUCK_MIN_UV, S2MPB02_BUCK_STEP_UV,
			  S2MPB02_REG_B2CTRL1, S2MPB02_REG_B2CTRL2,
			  S2MPB02_ENABLE_TIME_BUCK_US),
	S2MPB02_BUCK_DESC("s2mpb02-bb", "bb", S2MPB02_BB,
			  S2MPB02_BB_MIN_UV, S2MPB02_BB_STEP_UV,
			  S2MPB02_REG_BB1CTRL1, S2MPB02_REG_BB1CTRL2,
			  S2MPB02_ENABLE_TIME_BB_US),
};

static_assert(ARRAY_SIZE(s2mpb02_regulators) == S2MPB02_NUM_REGULATORS);

static const struct regmap_config s2mpb02_regmap_config = {
	.reg_bits	= 8,
	.val_bits	= 8,
	.max_register	= S2MPB02_MAX_REGISTER,
};

static int s2mpb02_i2c_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct regulator_config config = { };
	struct regulator_dev *rdev;
	struct regmap *regmap;
	unsigned int id;
	unsigned int i;
	int ret;

	regmap = devm_regmap_init_i2c(client, &s2mpb02_regmap_config);
	if (IS_ERR(regmap))
		return dev_err_probe(dev, PTR_ERR(regmap),
				     "failed to initialise regmap\n");

	/*
	 * Make sure the chip answers before registering anything.  The
	 * expected ID value is unknown; the downstream driver only logs it.
	 */
	ret = regmap_read(regmap, S2MPB02_REG_ID, &id);
	if (ret)
		return dev_err_probe(dev, ret,
				     "failed to read the chip ID register\n");

	dev_info(dev, "S2MPB02 found, ID register 0x%02x\n", id);

	config.dev = dev;
	config.regmap = regmap;

	for (i = 0; i < ARRAY_SIZE(s2mpb02_regulators); i++) {
		rdev = devm_regulator_register(dev, &s2mpb02_regulators[i],
					       &config);
		if (IS_ERR(rdev))
			return dev_err_probe(dev, PTR_ERR(rdev),
					     "failed to register %s\n",
					     s2mpb02_regulators[i].name);
	}

	return 0;
}

static const struct of_device_id s2mpb02_of_match[] = {
	{ .compatible = "samsung,s2mpb02" },
	{ }
};
MODULE_DEVICE_TABLE(of, s2mpb02_of_match);

static const struct i2c_device_id s2mpb02_i2c_id[] = {
	{ "s2mpb02" },
	{ }
};
MODULE_DEVICE_TABLE(i2c, s2mpb02_i2c_id);

static struct i2c_driver s2mpb02_i2c_driver = {
	.driver = {
		.name		= "s2mpb02-regulator",
		.of_match_table	= s2mpb02_of_match,
		.probe_type	= PROBE_PREFER_ASYNCHRONOUS,
	},
	.probe		= s2mpb02_i2c_probe,
	.id_table	= s2mpb02_i2c_id,
};
module_i2c_driver(s2mpb02_i2c_driver);

MODULE_DESCRIPTION("Samsung S2MPB02 camera PMIC regulator driver");
MODULE_LICENSE("GPL");
