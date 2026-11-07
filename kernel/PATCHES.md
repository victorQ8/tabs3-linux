# Kernel patch stack

`scripts/prepare-kernel.py` extracts the pinned kernel.org `6.18.56` tarball
(longterm 6.18.y, projected end of life December 2028), applies the base
patches in `kernel/base/` and then the gts3lwifi port's `0001`-`0003`.
`scripts/prepare-lte-kernel.py`
then applies `kernel/patches/0004`+ in order with `--fuzz=0`, records each
patch's name and SHA-256 in `.tabs3-local-patches`, and copies the board
device trees and the `ams968hh01-dimming*.h` and `sm5705-gts3l-policy.h`
headers from `kernel/`. Changing an applied patch requires a fresh work tree.

Scope: **generic** fixes affect every user of the code and are upstream
candidates; **board** changes are only active when the SM-T825 device tree or
panel asks for them; **bring-up** patches are local until reworked.

| Patch | Change | Scope |
|---|---|---|
| 0004 | DPU: MSM8996 split CTL capability; msm fbdev marked `FBINFO_VIRTFB` | generic |
| 0005 | `MIPI_DSI_CLOCK_DEFER_CONTINUOUS`: msm DSI keeps the clock lane in LP-11 until the first transfer | board (set by the panel) |
| 0006 | AMS968HH01 panel: verified init, stock lane rate, MTP-calibrated brightness, full power lifecycle | board |
| 0007 | `qcom,ep-latency` wait after PERST# | bring-up |
| 0008 | Downstream PHY v3 tables behind `qcom,msm8996-v3-qmp-pcie-phy` | board (selected by DT) |
| 0009-0012 | SM5705 fuel gauge and charger, charger-type input limit, temperature protection, inhibit handling | board drivers |
| 0013 | SM5705 USB OTG VBUS regulator (USB host mode) | board driver |
| 0014 | drm/msm: keep shared global-VM mappings until the last user (phoc GPU faults) | generic, `Fixes: 111fdd2198e6` |
| 0015 | tm2-touchkey: Coreriver TC305K variant | generic driver addition |
| 0016 | apq8096: back-end format S16_LE | generic |
| 0017 | dropped on 6.18.56: these q6asm-dai stream close fixes are in 6.18.35 | |
| 0018 | q6asm-dai: pause and flush capture on stop | generic |
| 0019 | mmc core: power cycle and rescan a present card that did not initialise (microSD hot insertion) | bring-up |
| 0020 | ASoC: Richtek RT5508 speaker amplifier driver (playback; ported from Samsung's vendor driver) | generic driver addition |
| 0021 | q6afe: send TDM data out, sync inversion and data delay to the DSP; slot mapping only when a channel map was set | generic |
| 0022 | apq8096: primary TDM speaker back end (4 x 16-bit slots, 3.072 MHz bit clock) | board (selected by DT) |
| 0023-0026 | QRTR as a bus, QMI instance macro, Qualcomm Sensor Manager core and accelerometer (Yassine Oudjana's msm8996-staging-smgr branch, WIP, from 6.14) | community, bring-up |
| 0027 | qcom_smgr: skip sensors of unsupported types instead of registering a device named NULL (kernel crash) | bring-up |
| 0028 | qcom_smgr: raw reads of the latest sample (`in_accel_{x,y,z}_raw`); a stream starts on demand and stops 3 s after the last read | bring-up |
| 0029 | SMGR gyro, magnetometer and light drivers; accelerometer Q16 scale and persistent sampling-rate range | bring-up |
| 0030 | MSM8996 general-purpose clocks: programmable frequency and duty-cycle propagation | bring-up |
| 0031 | PWM vibrator: configurable idle/full-strength duty cycle for bidirectional motor drive | board |
| 0032 | SMGR: use the firmware data-type selector rather than assuming array entry zero is primary | bring-up |
| 0033 | Venus decoder: allocate a mapped EOS buffer (David Heidelberg’s proposed upstream fix, adapted to 6.18) | community backport |
| 0034 | SM-T825 AP thermistor using the stock raw VADC calibration | board |
| 0035 | wacom_i2c: Samsung S Pen firmware protocol ("wacom,w9019": single-byte commands, 14-byte reports, tilt and distance, vdd supply, touchscreen-* orientation) | generic driver addition |
| 0036 | imx258: drive the reset GPIO (XCLR) around the supplies and INCK | generic |
| 0037 | camss vfe: count the users of the VFE power-domain device link (the CSID's and the ISPIF reset's releases cleared the link the VFE held: NULL dereference) | generic |
| 0038 | SMGR light: the Sensor Manager's illuminance is whole lux, not Q16 | bring-up |
| 0039 | camss: MSM8996 interconnect paths (`cam_ahb`, `cam_vfe_mem`), so the VFE votes bandwidth for its path to memory instead of depending on the display's vote (package 63; validated from a RAM boot with the screen off, `docs/kernel63-validation-20261014.json`) | generic |
| 0040 | s5k5e3: a V4L2 driver for the Samsung S5K5E3YX 5 MP sensor (the SM-T825 front camera: CCI, runtime PM, 2576x1932 and 640x480 modes, exposure, gains, blanking, flips, test pattern; register tables from the module's vendor configuration) (package 65) | generic driver addition |
| 0042 | s2mm005: a driver for the USB-C controller (function state, message flags, versions and the partner's capabilities in sysfs, interrupt plus poll) that tells the SM5705 through `sm5705_partner_supply()` when a partner takes over VBUS and with how much current: the boost goes off, D+/D- stay on USB (the MUIC's charger detection had left the data switch open), the hub charges the tablet while it stays the USB host (package 71); the USB role follows the controller's data role through the connector's role switch and the boost is refused below 15 % (package 72); the drop to the device role waits a second because the chip reports a detach as the tablet's VBUS comes on (package 74); a sink attach with the policy engine still detached is the same blip and does not cut the boost (package 75), nor is it logged (package 76); the SuperSpeed redriver (PM8994 GPIO 14, usb3.dtsi) is on while a partner is attached (package 77) | bring-up |
| 0044 | sm5705: the rear flash LED as a LED class flash device (torch in 10 mA steps to 180 mA, flash pulses to 1200 mA ended by the chip's one-shot timer; the charger's flash boost mode when nothing else feeds the LED) from a `led` child of the charger (package 78, flash.dtsi) | bring-up |
| 0045 | sm5705: D+/D- routed to USB by hand for a USB host (SDP or CDP) and the switch given back when VBUS goes, as Samsung's MUIC driver does; the automatic mode had left a PC without the gadget after a host session (package 80) | bring-up |
| 0041 | sm5705 charger: the force-discharge behaviour (operation mode SUSPEND, buck off) runs the tablet from its battery while plugged in, ends itself at 15 %, on VBUS loss, a fault, shutdown or suspend; the battery keeper uses it to bring a full battery down into its window (package 68) | bring-up |
| 0046 | q6asm: discard late READ/WRITE/EOS basic responses instead of overwriting synchronous command acknowledgments; upstream `8a066a81ee0c` follows base patch 0007 | upstream backport; hardware test pending |
| 0047 | q6asm-dai: capture STOP accepts APR's positive packet-length success return before sending FLUSH; corrects local 0018 | generic; hardware test pending |
| 0048 | Venus: serialize the H.264 8x8-transform control on HFI v3 as well as later versions; Vladimir Lypak's `17b07fbf0a7d` | community backport; setup fixed, encoding still fails |
| 0049 | Venus: HFI-v3 encoder EOS uses zero address and length, importing the encoder portion of Vladimir Lypak's `1c6674b9e45d`; decoder 0033 retained | community backport; bounded hardware test passed |
| 0050 | Venus: refuse HFI-v3 encoder capture-pool growth after STREAMON; firmware rejects registering new static buffers in this state | local; bounded hardware test passed |

Local changes have not been submitted upstream. Imported patches retain their
upstream attribution. New submissions need the owner's review and Signed-off-by.

The 2026-11-05 audio candidate is `6.18.56-81~audio1`, built separately under
`private/releases/20261105-drivers81/`. Patches 0046/0047 compile and pass
`tests/test_q6asm_lifecycle.py`: the actual callback and trigger functions
reproduce both failures before the fixes and preserve control acknowledgments,
flush sequencing and error returns afterward. This uses a simulated transport,
not the DSP. The package and boot images are not installed. The changed q6asm
drivers are **modules**; booting its Image with package 80's modules would not
test the fixes. Install the matching package as part of the controlled test,
with package 80 available for rollback.

The separate `6.18.56-81~drivers1` build in
`private/releases/20261105-drivers81b/` adds 0048. The packet regression test
passes, and a temporary module test confirms that H.264 setup succeeds, but
firmware crashes after three frames. Original-package VP8 also crashes.
Original modules were restored; subsequent hardware H.264 decode passes all
60 test frames. The broader build is **not production-qualified or installed**;
see `docs/driver-video-validation-20261105.json`.

The final `6.18.56-81~drivers2` build in
`private/releases/20261105-drivers81c/` adds 0049/0050. A discarded attempt
to register late buffers was rejected by firmware; it is not in this build.
Final host tests compile actual packet/queue code before and after each fix.
Temporary hardware tests passed H.264 through 1080p, a 300-frame stream,
three reopen cycles, VP8 file/container output and H.264 decoding, all with
clean EOS and no new kernel errors. Independent decoding verifies output
frame counts. Packaged module build IDs match the tested modules. Original
modules were restored; full candidate installation, audio testing and longer
qualification remain open.

Candidate under test: `0043` keeps the A5xx ring write-pointer snapshot and
MMIO write inside the same lock in both writers. The deterministic host test
reproduces a stale overwrite without it. Package 73 is a GPU-stability
candidate, not yet hardware-qualified; it preserves hardware acceleration,
preemption, clocks and package 72's USB-C changes.

## Kernel base

Until package 41 the base was the msm8996-mainline community tag
`v6.19.5-msm8996`, which stopped at 6.19.5 (6.19.y reached end of life with
6.19.14). From package 44 the base is kernel.org 6.18.56 plus `kernel/base/`:

| Base patch | Origin | Why this board needs it |
|---|---|---|
| 0001 | community `9825cdf0` (DSI power management) | 0005/0006 send DSI commands outside bridge enable |
| 0002 | community `7bf172f8` (dwc3 VBUS regulator) | `vbus-supply` for USB host mode (0013) |
| 0003 | community `699af099` (MSM8996 CPU cooling) | DT only; keeps the DTBs equal, inert without TSENS |
| 0004 | community `8737f6db` (report the last SSR event) | SLIMbus starts only after an ADSP SSR event |
| 0005 | 6.19 `389597581e3` (dwc3 role switch from userspace) | `tabs3-usb-host` |
| 0006 | 6.19 `2377626fd21`, MSM8996 hunk (`gpu_zap_shader` label) | `adreno.dtsi` |
| 0007-0011 | 6.19 q6asm series | the audio stack was validated with them |

The other 67 community commits cover other boards, the PMI8994 charger,
sensors, camera, haptics and other panels; one was replaced upstream. See
`docs/kernel-rebase-20261012/` for the classification of all 71 community
commits and how each patch applies on 6.19.5, 6.18.56 and 7.2.10.

## Cleanup of 2026-10-12

The bring-up stack (35 patches, `0004`-`0038`) was squashed into the stack
above. The new stack reproduces the verified tree exactly, except for these
intended changes:

- The panel driver lost its bring-up instruments: the `stock_clock`,
  `tear_on`, `mtp_gamma`, `diag` and `read_hs` module parameters (their
  verified defaults are fixed), the debugfs raw DSI command file, DDI register
  dumps and startup checkpoint messages. The MTP dump became `dev_dbg`.
- The DSI LP-11 clock deferral is requested by the panel through a mode flag
  instead of `of_machine_is_compatible("samsung,gts3llte")` in the msm DSI
  host; its "panel LP11" messages were removed.
- The PCIe PHY tuning moved from the shared MSM8996 tables to separate v3
  tables that only the SM-T825 device tree selects.
- A stray blank line in the shared-VM fix.

Documents written before the cleanup cite the old numbers:

| Old | New |
|---|---|
| 0004 | 0004 |
| 0005-0015, 0018, 0019, 0023, 0025-0027, 0031 | 0006 |
| 0016 | 0007 |
| 0017 | 0008 |
| 0020, 0021, 0022, 0024 | 0009, 0010, 0011, 0012 |
| 0028, 0029, 0030 | 0005 (DSI host) and 0006 (panel) |
| 0032, 0033 | 0014 |
| 0034, 0035, 0036, 0037 | 0015, 0016, 0017, 0018 |
| 0038 | 0013 |

The complete old stack is tagged `old-patch-stack` in git. `0034`-`0038`
kept their contents and only changed numbers.
