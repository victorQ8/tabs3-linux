# SM-T825 rear camera (IMX258 + DW9807) - mainline 6.18 DT notes

Deliverable: `camera.dtsi` in this directory. It only references labels that
exist in `msm8996.dtsi` (`camss`, `cci`, `cci_i2c0`, `blsp2_i2c1`, `tlmm`,
`mmcc`) plus the PM8994 regulator labels another agent defines
(`vreg_s3a_1p3`, `vreg_lvs1a_1p8`, `vreg_l29a_2p8`, `vreg_l17a_2p8`,
`vreg_l2a_1p25`, db820c naming). Nothing under `the project root` was
modified; no build or git commands were run.

Paths below: `live.dts` =
`private/backups/20261010T094140Z/live.dts`,
kernel = `work/linux-6.18.56`,
Samsung = `<scratch>/samsung/`.

## 1. Stock supply phandles -> regulators

Rear sensor node `qcom,camera@0` (live.dts 12447-12498), EEPROM
`qcom,eeprom@50` (6991-7038), actuator `qcom,actuator@18` (7040-7064),
CSIPHY/CSID nodes (11920-12005).

| Stock property | phandle | Stock regulator (live.dts line) | Voltage / mode | Mainline label | Used as |
|---|---|---|---|---|---|
| `cam_vana-supply` | 0x1e1 | `pm8994_l29` (8688) | 2.8 V (0x2ab980), op-mode 5 mA | `vreg_l29a_2p8` | imx258 `vana-supply` |
| `cam_vdig-supply` | 0x15c | `pm8994_s3` (8040) | 1.3 V (0x13d620), op-mode 5 mA | `vreg_s3a_1p3` | `vin-supply` of `vreg_cam_core` (CAM_CORE_EN, TLMM 9) -> imx258 `vdig-supply` |
| `cam_vio-supply` | 0xf3 | `pm8994_lvs1` (8761) | 1.8 V load switch (no voltage props, `qcom,set = <3>`) | `vreg_lvs1a_1p8` | imx258 `vif-supply`; VCM/EEPROM bus I/O rail; forced always-on |
| `cam_vaf-supply` | 0xf4 | `pm8994_l17` (8402) | 2.8 V, op-mode 50 mA | `vreg_l17a_2p8` | at24 `vcc-supply`; DW9807 VDD (no binding slot) -> forced always-on |
| `qcom,mipi-csi-vdd-supply` (csiphy/csid) | 0x32 | `pm8994_l2` (8142) | 1.25 V (0x1312d0), `qcom,csi-vdd-voltage = 1250000` | `vreg_l2a_1p25` | camss `vdda-supply` (required by the binding) |
| `qcom,vdd-cx-supply` | 0x107 | `pm8994_s1_corner` (7960) | corner vote | - | handled by mmcc/GDSC power domains in mainline |
| `mmagic-supply` / `gdscr-supply` | 0x5a / 0x5b | `gdsc_mmagic_camss` / `gdsc_camss_top` | - | `MMAGIC_CAMSS_GDSC` / `CAMSS_GDSC` | already in msm8996.dtsi (cci `power-domains`, vfe_smmu) |
| `vfe0-vdd` / `vfe1-vdd` (ispif, vfe) | 0x1cd / 0x1ce | `gdsc_vfe0` / `gdsc_vfe1` | - | `VFE0_GDSC` / `VFE1_GDSC` | camss `power-domains` in msm8996.dtsi |
| front `cam_vana-supply` | 0x1d9 | `pm8994_l23` (8541) | 2.8 V | `vreg_l23a_2p8` | front camera (S5K5E3, CSIPHY2/CCI1) - not described |

Samsung's `msm8996-camera-sensor-gts3llte-r00.dtsi` uses the same rails by
name (`pm8994_s3`, `pm8994_lvs1`, `pm8994_l29`, `pm8994_l17`,
`pm8994_s1_corner`), so the live dump and the downstream source agree.

S2MPB02: present in live.dts at `i2c@75ba000` line 6740 (reg 0x59, same bus
as the Synaptics touch controller; Samsung's r00 dtsi had it on i2c_1).
None of its LDO/buck nodes has a phandle, i.e. no DT consumer references
them, and the rear-camera nodes use PM8994 rails exclusively. The rear
camera therefore gets no `s2mpb02_ldoN` reference. (Samsung drivers can
still fetch regulators by `regulator-name`; nothing in the camera DT nodes
suggests that for the rear module.)

Other stock facts for the sensor node: `qcom,csiphy-sd-index = 0`,
`qcom,csid-sd-index = 0`, `qcom,cci-master = 0`, `qcom,mount-angle = 90`,
`cam,cal_memory = 2` (EEPROM), `cam,companion_chip = 0`, `cam,ois = 0`,
flash source = SM5705 LED driver (phandle 0x1de -> `qcom,camera-flash`
backed by `sm5705-leds1/2`; not modelled here).

## 2. GPIOs and pin states

| Signal | TLMM | Stock active / suspend pinconf (r05 pinctrl) | Mainline |
|---|---|---|---|
| CAMIF_MCLK0 | 13 | `cam_mclk`, 4 mA, no pull / `cam_mclk`, pull-down | `cam_rear_default` `mclk0-pins` (4 mA) |
| CAM_RESET0 (XCLR) | 30 | gpio, 2 mA, no pull / pull-down | `reset-gpios = <&tlmm 30 GPIO_ACTIVE_LOW>` + `reset-pins` parked `output-high` |
| CAM_CORE_EN | 9 | gpio, 2 mA, no pull / pull-down | `vreg_cam_core` enable GPIO, `cam_rear_core_en_default` |
| CCI0 SDA/SCL | 17 / 18 | `cci_i2c`, 2 mA (live has both pull-up and bias-disable) / gpio pull-down | `cci0_default` from msm8996.dtsi (16 mA, already referenced by `&cci`) |
| CCI1 SDA/SCL | 19 / 20 | same | `cci1_default` (kept, front camera) |
| i2c_7 SDA/SCL (BLSP2 QUP1) | 55 / 56 | `i2c_7_active`; actuator node lists them as "I2C_DATA0/I2C_CLK0" | `blsp2_i2c1_default` (`blsp_i2c7`, msm8996.dtsi 1612) |
| front: MCLK2 / reset / core-en(vdig) | 15 / 40 / 8 | - | not included |

Stock pin phandles: 0x1e2 `cam_sensor_mclk0_active`, 0x1e3
`cam_sensor_rear_active`, 0x1e4 `cam_sensor_mclk0_suspend`, 0x1e5
`cam_sensor_rear_suspend`, 0x1d5/0x1d6 `cci0_active`/`cci1_active`,
0x1d7/0x1d8 `cci0_suspend`/`cci1_suspend`.

The SoC-level `camera_rear_default`/`camera0_mclk` state in msm8996.dtsi
(line 1424) is db820c's layout (gpio25/26 for rst/pwdn, 16 mA MCLK); a
board state is used instead so MCLK keeps the stock 4 mA drive. Swap in
`&camera0_mclk` if preferred (Sony Tone overrides it the same way,
`msm8996-sony-xperia-tone.dtsi` 156).

## 3. Clocks

- MCLK0: stock `qcom,clock-rates = <24000000 0>` for `cam_src_clk`
  (`mclk0_clk_src`). mmcc has `F(24000000, P_GPLL0_DIV, 1, 2, 25)`
  (`drivers/clk/qcom/mmcc-msm8996.c` 892) and `camss_mclk0_clk` carries
  `CLK_SET_RATE_PARENT` (2229), so `assigned-clock-rates = <24000000>` on
  `CAMSS_MCLK0_CLK` reaches the RCG. The i2c core applies assigned clocks
  before probe (`drivers/i2c/i2c-core-base.c` 572).
- CCI: msm8996.dtsi assigns `CAMSS_CCI_AHB_CLK` 80 MHz and `CAMSS_CCI_CLK`
  37.5 MHz; stock used cci_src 19.2 MHz with `qcom,cci-clk-src = 37500000`
  for its timing tables. Bus 400 kHz (stock i2c_fast_mode present; the EEPROM
  node uses `qcom,i2c-freq-mode = <1>` = fast).
- CSIPHY0 timer: driver picks 100 / 200 / 266.67 MHz (`camss.c` 319); CSI0
  core clock stock 200 MHz, mainline derives it from the pixel rate.
- Sensor link frequencies (24 MHz INCK table, `imx258.c` 527-530):
  636 MHz (1272 Mbps/lane, 4208x3120@30 on 4 lanes) and 321 MHz
  (642 Mbps/lane, 2104x1560 and 1048x780).

## 4. Lane assignment

Not in the stock DT: CAF sensor nodes take `csi_lane_assign` /
`csi_lane_mask` from the vendor sensor library (not in the repo; no
`libmmcamera_imx258*` blob found under `private/`). Chosen: 4 data lanes,
straight mapping.

- 4208x3120@30 needs 1267 Mbps/lane on 4 lanes; 2 lanes caps at 15 fps
  (`imx258.c` 177-181). A 13 MP phone/tablet module is wired 4-lane.
- MSM8996 CSIPHY0 is a 4-lane D-PHY; the CAF default for 4-lane sensors is
  `csi_lane_assign = 0x4320`, `csi_lane_mask = 0x1f` (logical lanes 0-3 ->
  physical data lanes in order, clock on CAF lane 1).
- Mainline 6.18 drives the 8996 PHY with the 3ph ops (`camss.c` 311-327,
  `csiphy_ops_3ph_1_0`): a `data-lanes` entry `pos` selects register lane
  `pos*2` and enable bit `BIT(pos*2)` (`camss-csiphy-3ph-1-0.c` 813-815,
  940); the clock lane is hard-wired to lane block 7 and the CLK_ENABLE bit
  (806-813, 897). `clock-lanes` is parsed (`camss.c` 3602) but unused by
  this PHY, so `<7>` is documentation only.
- Sensor side: `data-lanes = <1 2 3 4>` (binding enum, driver only counts
  them, `imx258.c` 1426-1437).

Fallback if the module turns out to be 2-lane: sensor `data-lanes = <1 2>`,
camss `data-lanes = <0 1>`; same link-frequencies.

## 5. IMX258 driver facts verified (`drivers/media/i2c/imx258.c`, 6.18.56)

- Compatibles: `sony,imx258` (plain) and `sony,imx258-pdaf` (1533-1534);
  the variants differ only in regs 0x3052/0x4E21/0x7B25 (436-460). Plain
  chosen; use `-pdaf` only if the module is known to be the PDAF part.
- I2C: CCI regmap with 16-bit register addresses (1366); chip ID 0x0258 at
  0x0016 read at probe (25-26, 1172-1189) with the sensor powered. Slave
  address is not hard-coded; 0x1a is the IMX258 address with SLASEL low
  (0x10 with SLASEL high). The stock DT does not reveal it (CCI nodes take
  it from the vendor library).
- Clock: `devm_v4l2_sensor_clk_get_legacy(dev, NULL, false, 0)` (1379);
  `clk_get_rate()` must be exactly 19200000 or 24000000, otherwise probe
  fails with "input clock frequency ... not supported" (1384-1398). The
  helper would also `clk_set_rate()` from a `clock-frequency` property
  (`drivers/media/v4l2-core/v4l2-common.c` 733-752), but
  `sony,imx258.yaml` does not allow that property, hence
  `assigned-clock-rates`.
- Lanes: 2 or 4 only (1426-1437); `link-frequencies` must intersect the
  driver's menu for the INCK in use or probe fails "Link frequency not
  supported" (1414-1423). 24 MHz menu: 636000000, 321000000.
- Supplies: `vana` (2.8 V), `vdig` (1.2 V), `vif` (1.8 V), bulk-enabled in
  parallel, then MCLK enabled; no delays (484-489, 1101-1131).
- Reset: no GPIO handling at all (`grep -i gpio` is empty). Streaming starts
  with a software reset via 0x0103 and a 12 ms wait (1022-1028). The binding
  nevertheless documents `reset-gpios` (XCLR), so the DT carries it.
- Registers as a sensor subdev with `v4l2_async_register_subdev_sensor`
  (1478): `lens-focus` / `flash-leds` phandles become ancillary subdevs.
  Consequence: with `lens-focus` present the CAMSS notifier only completes
  (video nodes appear) once the DW9807 driver has bound. Build
  `CONFIG_VIDEO_DW9807_VCM`, or drop `lens-focus` for a first bring-up.
- Formats: SRGGB10_1X10 (and flipped variants) 4208x3120, 2104x1560,
  1048x780 (469-472, 600-650); default mode is 4208x3120.
- Exposes `V4L2_CID_CAMERA_ORIENTATION/SENSOR_ROTATION` from `orientation`
  / `rotation` (1313-1319; video-interface-devices.yaml).

## 6. DW9807 and EEPROM

- `dongwoon,dw9807-vcm.yaml`: only `compatible` and `reg`,
  `additionalProperties: false` - no supply, clock or GPIO allowed. The
  driver (`drivers/media/i2c/dw9807-vcm.c`) has no regulator code, probe
  does not touch the hardware (178-222), runtime-suspend writes the
  power-down bit (CTL 0x02) and resume clears it (231-292). VDD = L17 is
  therefore marked `regulator-always-on` in the fragment.
- EEPROM: stock name "dw9807" means the EEPROM block of the DW9807 itself.
  Stock node: `qcom,slave-addr = <0xB0>` (8-bit -> 0x58 7-bit), but
  `reg = <0x51 0x00>` under `qcom,eeprom@50`; map `qcom,mem0..7` reads
  0x0000-0x11FF with address type 2 (16-bit), total 0x1200 bytes
  (live.dts 6991-7036). Modelled as `atmel,24c64` (8 KiB, 16-bit address,
  smallest standard size that holds 0x1200 bytes), `read-only`. at24 gets
  `vcc` (`at24.c` 706), enables it at probe (761), does a one-byte test read
  and fails with -ENODEV if the chip does not answer (772-782), then runtime
  suspends, which disables `vcc` again (799, 823-836). So at24 does not keep
  L17 on - hence the always-on - and needs the bus pull-up rail (LVS1 per
  the stock sequences) at probe time.

## 7. CAMSS facts (`drivers/media/platform/qcom/camss/`)

- Binding `qcom,msm8996-camss.yaml`: `vdda-supply` required; `ports/port@N`
  endpoints need `data-lanes`, `bus-type` optional (D-PHY only, `camss.c`
  3594). msm8996.dtsi already provides regs, 36 clocks, 10 IRQs, `iommus`
  (`vfe_smmu`, enabled by default, line 2460) and VFE0/VFE1 GDSC
  power-domains; the node is `status = "disabled"` until enabled here.
- Entity names: `msm_csiphy0..2`, `msm_csid0..3`, `msm_ispif0..3`,
  `msm_vfe{0,1}_rdi{0,1,2}`, `msm_vfe{0,1}_pix`, video devices
  `msm_vfe{0,1}_video0..3` (video index = line, RDI0 = 0; csiphy.c 25/804,
  csid.c 38/1365, ispif.c 26/1392, vfe.c 28/2042-2086).
- Links: sensor -> csiphy is created IMMUTABLE|ENABLED (`camss.c`
  4001-4003); csiphy -> csid, csid -> ispif, ispif -> vfe are created with
  flags 0 (3765-3830) and must be enabled with media-ctl.
- RDI output formats for 8x96 (`camss-vfe.c` 77-125): SRGGB10_1X10 ->
  `V4L2_PIX_FMT_SRGGB10P` ("pRAA", MIPI-packed; 4208 px -> 5260 bytes/line,
  16 411 200 bytes/frame). There is no unpacked 16-bit RGGB variant on this
  path.
- CCI: `qcom,i2c-cci.yaml` (msm8996 needs `power-domains`, present);
  `cci_i2c0` is `i2c-bus@0` with `clock-frequency = <400000>` and address
  cells already set (msm8996.dtsi 2319-2353).

## 8. Design choices and why

1. `vreg_cam_core` (regulator-fixed, TLMM 9, `vin-supply` S3, 1.2 V) as the
   sensor's `vdig-supply`: the stock sequence enables "cam_vana",
   "gpio core/vdig", "cam_vdig", "cam_vio", reset, mclk; the mainline
   driver has no GPIO hook but does bulk-enable its three supplies before
   MCLK, so hanging the enable GPIO off `vdig` reproduces "S3 on, LDO
   enabled, then clock". Chaining via `vin-supply` (rather than making S3
   the vdig and the GPIO a separate always-on switch) keeps S3 requested
   while the core LDO is on, exactly as stock requested `cam_vdig`.
   The alternative reading (TLMM 9 is a load switch passing 1.3 V) would
   violate the IMX258 VDIG spec, so the LDO reading is preferred; set the
   voltage to whatever is measured on the flex if it matters.
2. XCLR: `reset-gpios` is in the binding, so it is declared, but since the
   6.18 driver ignores it the `reset-pins` pinconf parks TLMM 30 high
   whenever the imx258 driver is bound. With LVS1 (VIF) always on this does
   not back-power an unpowered I/O domain. The per-stream software reset
   keeps the register state sane. A 15-line driver patch (section 11)
   gives proper sequencing and will use the same DT.
3. L17 and LVS1 `regulator-always-on`: see section 6. Both are low-current
   rails (stock op-mode 50 mA / 5 mA); the overrides sit at the end of the
   fragment and can move into the PMIC node.
4. `&cci` keeps the SoC pin states for both masters (stock muxes both); only
   master 0 has a child here.
5. MCLK 4 mA instead of the SoC's 16 mA to match the stock pinconf.
6. `lens-focus` is included for libcamera to find the VCM; see the dependency
   note in section 5.
7. `clock-lanes = <7>` kept for documentation; harmless for the binding and
   the driver.

## 9. Remaining uncertainties

- Data-lane count (4 assumed) and lane order (straight assumed); symptom
  of a wrong guess: CSIPHY/CSID errors or no frames at all. Try 2 lanes.
- Sensor I2C address: 0x1a assumed (0x10 if SLASEL is strapped high).
  Symptom: "failed to read chip id" at probe. The CCI adapter supports
  `i2cdetect -r` only while the sensor is powered (driver bound), so test
  the alternative by editing `reg`.
- EEPROM address (0x58 vs 0x51) and size/type (24c64 assumed, could be a
  smaller Dongwoon part with a non-standard page layout). Verify with
  `i2cdetect` on the BLSP2 I2C1 adapter and by dumping the first bytes.
- Rail assumptions: LVS1 as the VCM/EEPROM pull-up rail; the core LDO output
  voltage; whether any S2MPB02 LDO is involved at all (no evidence it is).
- Plain vs PDAF IMX258 variant.
- XCLR timing with the unpatched driver (XCLR high before supplies). Works
  on most Sony parts; if the chip-ID read fails intermittently, apply the
  patch in section 11.
- CSIPHY settle count is computed from the link frequency; if the sensor's
  real rate differs from 1272/642 Mbps the PHY may miss frames.
- Flash (SM5705) and the front camera (S5K5E3 on CSIPHY2/CCI1, EEPROM via
  OTP) are not part of this fragment.

## 10. Kernel configuration

`CONFIG_MEDIA_SUPPORT`, `CONFIG_MEDIA_CONTROLLER`,
`CONFIG_VIDEO_V4L2_SUBDEV_API`, `CONFIG_MEDIA_CAMERA_SUPPORT`,
`CONFIG_MEDIA_PLATFORM_SUPPORT`/`CONFIG_V4L_PLATFORM_DRIVERS`,
`CONFIG_VIDEO_QCOM_CAMSS`, `CONFIG_I2C_QCOM_CCI`, `CONFIG_I2C_QUP`,
`CONFIG_VIDEO_IMX258` (selects `V4L2_CCI_I2C`), `CONFIG_VIDEO_DW9807_VCM`,
`CONFIG_EEPROM_AT24`, `CONFIG_REGULATOR_FIXED_VOLTAGE`,
`CONFIG_MSM_MMCC_8996`, `CONFIG_ARM_SMMU` (vfe_smmu), `CONFIG_PINCTRL_MSM8996`.

## 11. Optional driver patch: honour `reset-gpios` (untested sketch)

```diff
--- a/drivers/media/i2c/imx258.c
+++ b/drivers/media/i2c/imx258.c
@@
 #include <linux/delay.h>
+#include <linux/gpio/consumer.h>
 #include <linux/i2c.h>
@@ struct imx258 {
 	struct clk *clk;
+	struct gpio_desc *reset_gpio;
@@ static int imx258_power_on(struct device *dev)
 	ret = clk_prepare_enable(imx258->clk);
 	if (ret) {
 		dev_err(dev, "failed to enable clock\n");
 		regulator_bulk_disable(IMX258_NUM_SUPPLIES, imx258->supplies);
+		return ret;
 	}
 
-	return ret;
+	/* XCLR high after supplies and INCK, then let the sensor boot. */
+	gpiod_set_value_cansleep(imx258->reset_gpio, 0);
+	usleep_range(12000, 15000);
+
+	return 0;
 }
 
 static int imx258_power_off(struct device *dev)
 {
 	struct v4l2_subdev *sd = dev_get_drvdata(dev);
 	struct imx258 *imx258 = to_imx258(sd);
 
+	gpiod_set_value_cansleep(imx258->reset_gpio, 1);
 	clk_disable_unprepare(imx258->clk);
@@ static int imx258_probe(struct i2c_client *client)
 	ret = imx258_get_regulators(imx258);
 	if (ret)
 		return dev_err_probe(imx258->dev, ret,
 				     "failed to get regulators\n");
 
+	imx258->reset_gpio = devm_gpiod_get_optional(imx258->dev, "reset",
+						     GPIOD_OUT_HIGH);
+	if (IS_ERR(imx258->reset_gpio))
+		return dev_err_probe(imx258->dev, PTR_ERR(imx258->reset_gpio),
+				     "failed to get reset GPIO\n");
+
```

With the patch, drop `output-high` from `reset-pins` so XCLR stays low
until the driver releases it.

## 12. Validation done here

No `make`. `scratch/check.dts` wraps `qcom/msm8996.dtsi` + stub PM8994
labels + `camera.dtsi`; preprocessed with `cpp` using the 6.18.56 include
paths and compiled with the prebuilt
`work/rebase/build/618/scripts/dtc/dtc` (DTC 1.7.2):
exit 0, all labels/macros resolve, no new warnings beyond the SoC dtsi's
own (`graph_child_address` on `camss/ports` is the generic single-`port@0`
notice that the kernel's default `DTC_FLAGS` suppress). dtschema
(`dt-validate`) is not installed on this host, so the fragment was checked
against the YAML bindings by reading them, not by running them:

```sh
K=work/linux-6.18.56; S=<this dir>/scratch
cpp -nostdinc -I$K/include -I$K/arch/arm64/boot/dts -undef -D__DTS__ \
    -x assembler-with-cpp $S/check.dts -o $S/check.pre.dts
work/rebase/build/618/scripts/dtc/dtc -I dts -O dtb \
    -i $K/arch/arm64/boot/dts/qcom -o $S/check.dtb $S/check.pre.dts
```

## 13. Userspace test commands

### 12.1 Probe sanity

```sh
dmesg | grep -iE 'imx258|camss|cci|dw9807|at24|csiphy|csid|vfe'
ls -l /dev/media* /dev/video* /dev/v4l-subdev*
grep -H . /sys/bus/i2c/devices/*/name          # expect imx258, dw9807, 24c64
i2cdetect -l                                  # find the i2c@75b5000 (blsp2_i2c1) adapter N
i2cdetect -y -r N                             # VCM at 0x18; EEPROM expected at 0x58 (else 0x51)
hexdump -C /sys/bus/i2c/devices/N-0058/eeprom | head -40   # calibration dump, read-only
```

Failure signatures: "chip id mismatch"/"failed to read chip id" = power,
MCLK, XCLR or I2C address; "input clock frequency ... not supported" =
MCLK rate; "Link frequency not supported" = `link-frequencies`;
no `/dev/video*` from camss while the sensor probed = notifier not
complete (DW9807 not bound because of `lens-focus`, or sensor probe
deferred on a regulator).

### 12.2 media-ctl / v4l2-ctl raw capture (v4l-utils; RDI path)

```sh
MDEV=/dev/media0
SENSOR=$(media-ctl -d $MDEV -p | sed -n 's/^- entity [0-9]*: \(imx258 [0-9]*-001a\).*/\1/p')
VIDEO=$(media-ctl -d $MDEV -e msm_vfe0_video0)
media-ctl -d $MDEV -p                                        # full graph, link flags

media-ctl -d $MDEV -r                                        # reset mutable links
media-ctl -d $MDEV -l '"msm_csiphy0":1->"msm_csid0":0[1]'
media-ctl -d $MDEV -l '"msm_csid0":1->"msm_ispif0":0[1]'
media-ctl -d $MDEV -l '"msm_ispif0":1->"msm_vfe0_rdi0":0[1]'
# sensor -> msm_csiphy0 is immutable and already enabled

FMT='fmt:SRGGB10_1X10/4208x3120 field:none'                  # or 2104x1560 / 1048x780
media-ctl -d $MDEV -V "\"$SENSOR\":0[$FMT]"
media-ctl -d $MDEV -V "\"msm_csiphy0\":0[$FMT]"
media-ctl -d $MDEV -V "\"msm_csid0\":0[$FMT]"
media-ctl -d $MDEV -V "\"msm_ispif0\":0[$FMT]"
media-ctl -d $MDEV -V "\"msm_vfe0_rdi0\":0[$FMT]"
media-ctl -d $MDEV -p | grep -A3 -E 'imx258|msm_csiphy0|msm_csid0|msm_ispif0|msm_vfe0_rdi0'

v4l2-ctl -d $VIDEO --set-fmt-video=width=4208,height=3120,pixelformat=pRAA
v4l2-ctl -d $VIDEO --get-fmt-video                           # expect SRGGB10P, 5260 bytes/line
v4l2-ctl -d $VIDEO --stream-mmap=4 --stream-count=5 --stream-poll \
        --stream-to=/tmp/imx258-4208x3120-srggb10p.raw --verbose
ls -l /tmp/imx258-4208x3120-srggb10p.raw                     # 5 x 16411200 bytes

# sensor controls, e.g. a colour-bar test pattern
SUBDEV=$(media-ctl -d $MDEV -e "$SENSOR")
v4l2-ctl -d $SUBDEV --list-ctrls
v4l2-ctl -d $SUBDEV --set-ctrl=test_pattern=1
# VCM
v4l2-ctl -d $(media-ctl -d $MDEV -e "$(media-ctl -d $MDEV -p | sed -n 's/^- entity [0-9]*: \(dw9807 [0-9]*-0018\).*/\1/p')") \
        --set-ctrl=focus_absolute=512
```

The raw file is 10-bit MIPI-packed RGGB (4 pixels in 5 bytes); unpack
with numpy or let libcamera's software ISP render it (12.3).

### 12.3 libcamera (`cam`; simple pipeline handler + software ISP for "qcom-camss")

2026-10-14: Debian's 0.4.0 lists and streams both cameras but its
uncalibrated software ISP collapses to near black with a green cast after
the first frame; 0.7.2 built from the git tag (`/srv/build/libcamera` on
the tablet, installed under `/usr/local`) settles at a neutral exposure on
both. `cam -l` numbers the rear 1 and the front 2. Its simple pipeline
resets every link of the media device, so it fails with EBUSY while the
dashboard's presence sampler holds the front path (screen off); run it
with the screen on or the dashboard stopped.

```sh
cam -l                                   # expect one camera: "imx258 N-001a" (or the libcamera id)
cam -c1 -I                               # stream configuration summary
cam -c1 -p                               # properties: Rotation=90, Location=back
cam -c1 --list-controls
cam -c1 --capture=5 --file=/tmp/imx258-#.bin                 # processed (SW ISP) frames
cam -c1 --capture=5 --stream role=raw --file=/tmp/imx258-raw-#.bin
cam -c1 --capture=5 --stream width=2104,height=1560,role=viewfinder --file=/tmp/imx258-2k-#.bin
LIBCAMERA_LOG_LEVELS='*:DEBUG' cam -c1 -C1 2>&1 | tee /tmp/libcamera.log
```

`#` in `--file` expands to stream name and frame number. If `cam -l` shows
nothing, check that the media device driver is reported as `qcom-camss`
(`media-ctl -p | head`) and that the sensor entity is linked to
`msm_csiphy0`; the simple pipeline handler needs a complete graph down to
a video node and uses the `lens-focus` ancillary link for the VCM.

## 15. USB-C controller: S2MM005 facts from Samsung's driver (2026-10-15)

Source: Samsung's `drivers/ccic/s2mm005*.c` and `include/linux/ccic/` in
the public SM-T825 kernel tree (the one the hardware document cites for
the battery), read, not copied. The chip: slave 0x33 on BLSP1 QUP5
(`i2c@7579000`, TLMM 83/84, "blsp_i2c5", 100 kHz), interrupt TLMM 73
(falling edge), 16-bit big-endian register addresses, reads of up to
48 bytes, writes of a few bytes.

- Versions ("flash read"): write 0xAA to 0x0010, then read 4 bytes at
  0x0000 (hardware: boot, main[3]) and at 0x0008 (software). This unit:
  hardware boot 4, software boot 6 main 00.00.d5.
- 0x0020 function state (u32): bits 7:0 policy-engine state, 10:8 CC1
  plug state, 14:12 CC2 plug state, 23:16 next state, 24 attached, 25 the
  tablet is the source, 26 the tablet is the host (DFP), 28:27 Rp level,
  29 VBUS-CC short, 30 VBUS-SBU short, 31 reset. States: 0 detached, 1-14
  source (6 ready, 14 wait new capabilities), 15-25 sink (17 wait for
  capabilities, 21 ready), 26-28 cable identity, 29 error recovery (also
  Samsung's SBU/water check state), 52 power-role swap source to sink
  (turn VBUS off), 64 power-role swap sink to source (turn VBUS on).
- 0x0030, 48 bytes: twelve u32 (sync, control, data and extended message
  status, message interrupt flags, VDM, debug, three more); word 4's bits:
  3 Accept, 4 Reject, 6 PS_RDY, 9 DR_Swap, 10 PR_Swap, 11 VCONN_Swap, 13
  Soft_Reset, 17 Source_Capabilities, 18 Request, 20 Sink_Capabilities.
- 0x0060 low-power state: bit 0 auto low power enable, 1 low power, 2
  forced low power, 3 water detected, 4 jig, 5 run dry, 6 booting run dry.
- 0x0260: the partner's Source_Capabilities message (header, up to seven
  PDOs, little-endian); 0x0240: the request message sent.
- 0x0010 command word: 0x01 (3-byte write) clears the interrupt; 0x03
  0x03 n selects PDO n; 0x03 0x02 state forces a policy-engine state;
  0x02 0x20/0x02 addr... read and write SRAM words (alternate-mode and
  system-reset code).
- Samsung's handler: on the interrupt read 0x20, 0x60 and 0x30, act (VBUS
  on when attached as source, off when the partner sources, state 52 off,
  state 64 on), then clear the interrupt.
- Observed here: with a PC the chip sits in state 29 as sink and device;
  with a hub that has its own charger the hub asks for a power-role swap
  and the chip accepts (state 17 within 4 s of VBUS), after which it
  negotiates 5 V 3 A and a data-role swap makes the tablet the host (state
  21, bits 24 and 26 set, 25 clear). USB data then needs the SM5705
  MUIC's D+/D- switch on USB (MANSW1 0x13 = 0x24, CTRL 0x02 bit 2 off):
  its automatic switching leaves the switch open for a hub.

## 14. Front camera: S5K5E3YX facts from the vendor library (2026-10-14)

Source: `libmmcamera_s5k5e3yx.so` from the Android system image backed up
on 2026-10-10 (`private/backups/20261010T182445Z-system/`), 32-bit ARM,
919036 bytes, sha256 `10893200309ee2b1c9eaf79916733fdcece27ff95f567ab3b32654c16d18f290`.
Nothing from the library is committed; the driver (`kernel/patches/0040-*`)
carries the decoded register values only.

- Sensor descriptor at file offset 0x3008: name `s5k5e3yx`; slave address
  0x20 in the 8-bit form (0x10 for Linux); register addresses 16-bit, data
  8-bit; sensor id register 0x0000, expected 0x5e30 (the driver reads it at
  probe and it matched); analogue rail 2.8 V.
- Register tables are arrays of 12-byte little-endian entries (u16 address,
  u16 value, u32 delay, u32 data type): the init table at descriptor
  + 0x3644 (97 entries, 0x30xx and 0x32xx registers), the 2576x1932 mode at
  descriptor + 0x6f890 (45 entries), the 640x480 mode at descriptor
  + 0x72890 + 16 (45 entries). The driver keeps the init table whole, splits
  each mode table into a shared PLL/MIPI block (23 entries) and the per-mode
  crop and binning (16 entries), and hands frame length, exposure and
  analogue gain (the remaining 6) to V4L2 controls.
- Clocking: 24 MHz MCLK2 / 6 (0x0305) * 224 (0x0306-0x0307) = 896 MHz;
  0x0820-0x0821 request 896 Mbps per lane, 0x0114 = 1 selects two lanes,
  0x0112-0x0113 10-bit output. Link frequency 448 MHz; pixel rate 2 lanes
  * 896 Mbps / 10 bits = 179.2 MHz. Line length 2950 (0x0342-0x0343); frame
  length 2025 lines (full, 30.0 fps) or 506 lines (VGA, 120 fps).
- Full mode: x 0 to 2575, y 2 to 1933 (0x0344-0x034b), output 2576x1932, no
  binning. VGA: crop 8 to 2567 by 8 to 1927, 4x4 binning (0x0900 = 1,
  0x0901 = 0x44, skips 0x0383/0x0387 = 3/7), output 640x480. Table defaults:
  exposure 0x200 lines (full) and 0x1f4 (VGA), analogue gain 0x20 (1x; the
  control's 16x ceiling comes from the register width, not a datasheet).
- Stock device tree (`qcom,camera@2`): CCI master 1, CSIPHY2 and CSID2,
  mount angle 270, position front; rails cam_vdig S3 1.3 V, cam_vio LVS1
  1.8 V, cam_vana L23 2.8 V; GPIOs CAMIF_MCLK2 TLMM 15, CAM_RESET2 TLMM 40,
  CAM_CORE_EN TLMM 8 (the front's own switch, like the rear's TLMM 9); an
  OTP reader at 0x53 (`lsi_s5k5e3yx`), not described.
- Bayer order: the decoded test frame has neutral colours as SGRBG10, the
  driver's default; flips move the origin as on other SMIA-style sensors.
- CAMSS: `vfe_parent_dev_ops_get()` returns -EINVAL for a CSID index at or
  above the VFE count, so on MSM8996 (four CSIDs, two VFEs) only CSID0 and
  CSID1 can be powered; the front uses CSID1 -> ISPIF1 -> VFE0 RDI1. A
  driver-side mapping of CSID2/3 onto a VFE would be an upstream item.
