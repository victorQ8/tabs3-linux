# S2MPB02 camera PMIC on the SM-T825: notes

Written from Samsung's GPL-2.0 downstream sources in
`<scratch>/samsung/` (`s2mpb02-regulator.c`,
`s2mpb02-core.c`, `s2mpb02.h`, `s2mpb02-private.h`, `leds-s2mpb02.h`,
`msm8996-s2mpb02_r00.dtsi`, `msm8996-camera-sensor-gts3llte-r00.dtsi`,
`msm8996-pinctrl-sec-gts3llte-r05.dtsi`) and the tablet's stock DT dump
`private/backups/20261010T094140Z/live.dts`. No datasheet was available.

## Headline finding: the stock camera supplies do not come from the S2MPB02

Every camera supply phandle in the stock DT resolves to a PM8994 RPM
regulator, not to the S2MPB02. The S2MPB02 regulator subnodes carry no
`phandle` property at all in `live.dts`, so nothing in the stock tree
references them. Samsung's camera dtsi source confirms it
(`cam_vdig-supply = <&pm8994_s3>` etc.).

| Supply | Phandle | Stock node (`live.dts`) | Regulator | Voltage | Consumers |
|---|---|---|---|---|---|
| `cam_vdig` | `0x15c` | `rpm-regulator-smpa3/regulator-s3` (line 8031) | `pm8994_s3` | 1.3 V fixed | rear camera@0, front camera@2, front OTP |
| `cam_vio` | `0xf3` | `rpm-regulator-vsa1/regulator-lvs1` (line 8755) | `pm8994_lvs1` | 1.8 V (LVS, no min/max in node) | rear, front, rear EEPROM, actuator, front OTP |
| `cam_vana` (rear) | `0x1e1` | `rpm-regulator-ldoa29/regulator-l29` (line 8679) | `pm8994_l29` | 2.8 V fixed | rear camera@0 |
| `cam_vaf` | `0xf4` | `rpm-regulator-ldoa17/regulator-l17` (line 8393) | `pm8994_l17` | 2.8 V fixed | rear camera@0, EEPROM@50, actuator@18 |
| `cam_vana` (front) | `0x1d9` | `rpm-regulator-ldoa23/regulator-l23` (line 8532) | `pm8994_l23` | 2.8 V fixed | front camera@2, front OTP |

Camera node voltage/load requests (`qcom,cam-vreg-*`):

- Rear `qcom,camera@0` (line 12447, IMX258): vana 2.8 V @ 5 mA, vdig 1.3 V @
  5 mA, vaf 2.8 V @ 50 mA, vio 1.8 V @ 5 mA. GPIOs: MCLK0 = TLMM 13,
  CAM_RESET0 = TLMM 30, CAM_CORE_EN = TLMM 9.
- Front `qcom,camera@2` (line 12495, S5K5E3YX): vdig 1.3 V @ 200 mA, vio
  1.8 V @ 200 mA, vana 2.8 V @ 100 mA. GPIOs: MCLK2 = TLMM 15, CAM_RESET2 =
  TLMM 40, CAM_CORE_EN = TLMM 8. The front OTP node's power sequence is
  `cam_vana`, `sensor_gpio_vdig`, `cam_vdig`, `cam_vio`, reset, mclk.
- Rear EEPROM `qcom,eeprom@50` (line 6991) and actuator `qcom,actuator@18`
  (line 7040): `cam_vio` (lvs1) + `cam_vaf` (l17).

In mainline terms these are PM8994 `rpm_requests` regulators. The project's
base `apq8096-samsung-gts3lwifi.dts` already defines `vreg_s3a_1p3: s3`
(1.3 V); `lvs1`, `l17`, `l23` and `l29` are not defined there yet and would
need nodes under `&rpm_requests { regulators-0 { ... } }` (as
`msm8996-samsung-gts3llte-touch.dtsi` does for `l18`), e.g.
`vreg_lvs1a_1p8: lvs1`, `vreg_l17a_2p8: l17`, `vreg_l23a_2p8: l23`,
`vreg_l29a_2p8: l29`.

Flash: the rear camera's `qcom,led-flash-src` (phandle `0x1de`, line 19799)
is a `qcom,camera-flash` whose flash/torch sources are `sm5705-leds1/2`
(SM5705 charger IC, `flash-en-gpio` TLMM 12, `torch-en-gpio` TLMM 11), not
the S2MPB02 flash LED driver. The S2MPB02 `torch` subnode in the stock tree
is unreferenced.

So: the S2MPB02 is present in the stock tree (bus enabled, node
`status = "okay"`), but the only effects the stock kernel's constraints
would have are `buck1` fixed at 1.3 V always-on and `bb` fixed at 3.5 V
always-on. What those two rails feed is unknown (candidates: the sensors'
`CAM_CORE_EN`-gated core supply, or the Wacom/touch digitiser side; nothing in
the DT says). The hardware doc's statement that camera supplies come from the
S2MPB02 is not supported by the stock DT.

Whether the chip is actually fitted is also not proven by the stock tree:
the downstream core driver logs "device not found" when the ID read fails
but still continues (it overwrites `ret` with `mfd_add_devices()`), so a
stock boot would not fail without the chip. The mainline driver here fails
probe with the regmap error if the ID register cannot be read, which gives a
definite answer (`dmesg | grep -i s2mpb02`). Alternatively, with the driver
not bound, `i2cdetect -y <blsp2_i2c6 bus> 0x59 0x59`.

## Stock bus

- Stock node `i2c@75ba000` (line 6700) = BLSP2 QUP6 = mainline `blsp2_i2c6`
  (`arch/arm64/boot/dts/qcom/msm8996.dtsi` line 3436, `status = "disabled"`
  by default). Stock pinctrl `s2mpb02_i2c_active`: `gpio87`, `gpio88`,
  function `blsp_i2c12`, drive-strength 2, bias-disable (mainline
  `blsp2_i2c6_default` uses the same pins/function with drive-strength 16;
  the dtsi overrides it to 2 like the touch dtsi does for `blsp2_i2c3`).
- `qcom,clk-freq-out = <400000>`, `qcom,disable-dma` on the stock bus; the
  dtsi sets `clock-frequency = <400000>` and deletes `dmas`/`dma-names`.
- The stock bus also contains a `synaptics,dsx@20` node (line 6720, IRQ TLMM
  125). That is a stale alternate touch node: the tablet's working
  touchscreen is `synaptics,rmi4@20` on `i2c@75b7000` (`blsp2_i2c3`, line
  19992), which is what the project's touch dtsi uses. Do not add the dsx node.
- The `interrupt-parent = <&tlmm>` in the stock S2MPB02 node has no
  `interrupts`; the downstream core reads an absent `s2mpb02,irq-gpio`. The
  driver uses no interrupt.

## Register map (downstream `enum s2mpb02_reg`, 0-based, contiguous)

| Addr | Name | Notes |
|---|---|---|
| 0x00 | ID | chip ID/revision; expected value unknown, downstream only logs it |
| 0x01 | INT1 | interrupt status (flash LED) |
| 0x02 | INT1M | interrupt mask |
| 0x03 | ST1 | status |
| 0x04 | CTRL | |
| 0x05-0x08 | RSVD5..RSVD8 | reserved (names confirm 0-based numbering) |
| 0x09 | BBEN_DBT | buck-boost enable debounce |
| 0x0a | RSVDA | reserved |
| 0x0b | B1CTRL1 | BUCK1 enable/mode, bits [7:6] |
| 0x0c | B1CTRL2 | BUCK1 voltage selector, bits [7:0] |
| 0x0d | B2CTRL1 | BUCK2 enable/mode |
| 0x0e | B2CTRL2 | BUCK2 voltage selector |
| 0x0f | BB1CTRL1 | buck-boost enable/mode |
| 0x10 | BB1CTRL2 | buck-boost voltage selector |
| 0x11 | BUCK_RAMP | buck ramp rate (not touched) |
| 0x12-0x1b | FLED_CTRL1/2, FLED_CUR1, FLED_TIME1, FLED_CUR2, FLED_TIME2, FLED_IRON1/2, FLED_IRD1/2 | flash LED (out of scope) |
| 0x1c-0x1d | BST_CTRL1/2 | flash boost (out of scope) |
| 0x1e-0x2f | L1CTRL..L18CTRL | LDOn: bit 7 enable, bits [6:0] voltage selector |
| 0x30-0x32 | LDO_DSCH1..3 | LDO discharge control (not touched) |

`regmap_config`: 8-bit reg, 8-bit val, `max_register = 0x32`, no cache.

## Regulators as implemented

| Regulator | DT subnode | enable reg / mask / on value | vsel reg / mask | min, step, n | range | enable_time |
|---|---|---|---|---|---|---|
| LDO1-LDO5 | `ldo1`..`ldo5` | LxCTRL / 0x80 / 0x80 | LxCTRL / 0x7f | 600000 uV, 12500 uV, 128 | 0.6 - 2.1875 V | 180 us |
| LDO6-LDO18 | `ldo6`..`ldo18` | LxCTRL / 0x80 / 0x80 | LxCTRL / 0x7f | 600000 uV, 25000 uV, 128 | 0.6 - 3.775 V | 180 us |
| BUCK1 | `buck1` | B1CTRL1 / 0xc0 / 0xc0 | B1CTRL2 / 0xff | 400000 uV, 6250 uV, 256 | 0.4 - 1.99375 V | 100 us |
| BUCK2 | `buck2` | B2CTRL1 / 0xc0 / 0xc0 | B2CTRL2 / 0xff | 400000 uV, 6250 uV, 256 | 0.4 - 1.99375 V | 100 us |
| BB | `bb` | BB1CTRL1 / 0xc0 / 0xc0 | BB1CTRL2 / 0xff | 2600000 uV, 12500 uV, 256 | 2.6 - 5.7875 V (see below) | 210 us |

All use `ramp_delay = 12000` uV/us (downstream `S2MPB02_RAMP_DELAY`, applied
by the downstream driver to LDOs and bucks alike) with
`regulator_set_voltage_time_sel`. Ops are the stock regmap helpers
(`regulator_{is_enabled,enable,disable}_regmap`,
`regulator_{get,set}_voltage_sel_regmap`, linear list/map).

The 2.1875 V and 3.775 V tops are exactly what the stock DT sets as
`regulator-max-microvolt` for LDO1-5 and LDO6-18, which cross-checks the
step sizes and the 7-bit selector.

Stock constraints copied into `s2mpb02.dtsi`: LDO1-5 0.6-2.1875 V,
LDO6-18 0.6-3.775 V, BUCK1 1.3 V fixed always-on, BUCK2 0.5-1.3 V, BB
3.5 V fixed always-on. (Samsung's reference `msm8996-s2mpb02_r00.dtsi`
differs: BUCK1 0.6-1.6 V not always-on, BB 3.6 V always-on.)

Stock regulator names are kept (`s2mpb02-ldo1` ... `s2mpb02-bb`); the DT
labels are `s2mpb02_ldo1` ... `s2mpb02_ldo18`, `s2mpb02_buck1`,
`s2mpb02_buck2`, `s2mpb02_bb`. No stock camera supply maps to any of them
(see the headline finding), so no camera node should reference these labels
until a real consumer is identified.

## Design choices

- Single self-contained I2C driver, compatible `samsung,s2mpb02`, 6.18
  `probe(struct i2c_client *)`, `devm_regmap_init_i2c`,
  `devm_regulator_register`, `.of_match`/`.regulators_node` matching,
  `MODULE_DEVICE_TABLE(of, ...)` and `(i2c, ...)`. No MFD core, no IRQ, no
  suspend ops, no LED driver.
- Bucks use `enable_val = 0xc0` so `is_enabled` reports true only for the
  full-on mode the downstream driver writes (0b11); the other two mode
  encodings (presumably PWREN-controlled / low-power, as on S2MPS11) are
  reported as disabled and `enable()` always writes 0b11. `disable()` writes
  0b00. LDOs are a single enable bit.
- Probe reads the ID register first and fails cleanly if the chip does not
  answer.
- All 21 regulators are registered whether or not the DT lists them (same as
  `s2mps11.c`); unlisted ones simply get empty constraints.

## Uncertainties

1. Buck-boost range: `2.6 V + 12.5 mV * sel` over a full 8-bit selector gives
   5.7875 V, which is surely above the real ceiling. The downstream driver
   has no tighter limit; keep the DT constraint (3.5 V fixed).
2. Buck mode field: only 0b11 (on) and 0b00 (off) are known from the
   downstream code; the meaning of 0b01/0b10 is assumed.
3. ID register value: unknown; the driver logs it at probe.
4. Whether the chip is fitted and what BUCK1 (1.3 V) and BB (3.5 V) power on
   this board. Nothing in the stock DT references the S2MPB02 rails.
5. `enable_time` and ramp values are the downstream constants, not measured.
6. Standard mainline behaviour: ~30 s after boot the regulator core disables
   any S2MPB02 output that the bootloader left enabled and that has no
   consumer or `regulator-always-on`. If something unexpected turns off,
   compare `/sys/kernel/debug/regulator/regulator_summary` before and after.
7. The dtsi deletes the bus' DMA properties and sets drive-strength 2,
   following the project's touch dtsi pattern; both are optional.

## Validation done (no `make`, nothing written under the kernel trees)

- `s2mpb02-regulator.c`: `clang --target=aarch64-linux-gnu -fsyntax-only
  -std=gnu11 -Wall -Wextra -Wmissing-prototypes -Wstrict-prototypes ...`
  against a scratch harness whose `struct regulator_desc`,
  `regulator_ops`, `regulator_config`, `regmap_config`, `i2c_driver`,
  `device_driver`, `of_device_id` and `i2c_device_id` were copied verbatim
  from the 6.18.56 headers (so every designated initializer name is
  checked against the real structs). Clean.
- `s2mpb02.dtsi`: compiled with a dtc built from the kernel's
  `scripts/dtc` sources, wrapped in a test dts defining `blsp2_i2c6` and
  `blsp2_i2c6_default`; 21 regulators, labels resolve, `/delete-property/`
  and the pinctrl override apply. Clean.
- `kconfig-makefile.diff`: `patch -p1 --dry-run` and apply on copies of the
  6.18.56 `drivers/regulator/Kconfig` and `Makefile`; applies without fuzz.

## Integration

1. Copy `s2mpb02-regulator.c` to `drivers/regulator/`, apply
   `kconfig-makefile.diff`, set `CONFIG_REGULATOR_S2MPB02=y` (or `m`).
2. `#include "s2mpb02.dtsi"` from `kernel/msm8996-samsung-gts3llte.dts`
   (it only needs the `blsp2_i2c6` and `blsp2_i2c6_default` labels from
   `msm8996.dtsi`).
3. Check `dmesg` for `S2MPB02 found, ID register 0x..` and
   `/sys/kernel/debug/regulator/regulator_summary`.
