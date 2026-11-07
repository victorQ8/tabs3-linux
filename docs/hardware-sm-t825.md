# SM-T825 hardware record — 2026-10-10

For the 2026-10-13 transition to server use, current installed versions and
the original platform-kernel tests, see the
[server/platform audit](server-platform-audit-20261013.md). The
[continuation report](platform-handoff-20261013.md) records reset isolation,
faster storage and the current driver validation, including remaining failures.

Read from the connected tablet over authorized ADB/root, TWRP, lk2nd and the
project's Linux kernel. The first boot test temporarily replaced boot and then
restored its complete original image, with matching SHA-256 and Android return.

## Device identity

| Field | Observed value |
| --- | --- |
| Model / product | SM-T825 / gts3lltexx |
| Device | gts3llte |
| Android | 9, security patch 2020-03-01 |
| Bootloader | T825JXU3CTE1 |
| Baseband | T825JXU3CTB1 |
| Bootloader properties | `ro.boot.flash.locked=0`, verified boot `orange` |
| Root access | Confirmed through existing `su` |
| Stock DT model | Samsung GTS3L LTE PROJECT Rev05 |
| SoC ID/revision | 246 (MSM8996), 3.1 |
| DT `qcom,msm-id` | `<0xf6 0x30001>` |
| DT `qcom,board-id` | `<0x8 0x5>` |
| DT `qcom,pmic-id` | `<0x20009 0x1000c 0 0>` (PM8994 + PM8004) |

The pinned upstream LTE lk2nd entry uses SoC revision `0x10000`; this tablet's
live DT instead reports `0x30001`. Its stock DTBs should be preserved in any
donor-based packing procedure and the lk2nd entry reviewed for this revision.

## Recovery references

Verified backups are in `private/backups/20261010T094140Z/`:

- `boot.img`: 79,691,776 bytes (76 MiB).
- `recovery.img`: 79,691,776 bytes (76 MiB).
- `live.dtb`: 548,866 bytes, also decompiled locally to `live.dts`.
- `manifest.json`: source paths, sizes and matching device/local SHA-256 hashes.
- `partitions.txt`: observed named partition links.

These are the current rooted device's images. They are not represented as
untouched Samsung firmware, a user-data backup, or EFS/modem calibration backup.
Raw device trees and images stay private because they can include identifiers
and proprietary content.

Observed partition links: boot → `mmcblk0p28`, recovery → `mmcblk0p29`,
EFS → `mmcblk0p27`, modemst1/2 → `mmcblk0p23`/`mmcblk0p24`,
userdata → `mmcblk0p47`. Future write tools must discover these again on the
actual target; this record is not a flashing script.

Both saved Android image headers specify:

| Field | Value |
| --- | --- |
| Kernel address | `0x80008000` |
| Ramdisk address | `0x82200000` |
| Second address | `0x80f00000` (second size is zero) |
| Tags address | `0x82000000` |
| Page size | 4096 |

## Initial device-tree comparison

eMMC is at `0x7464900`, uses an 8-bit bus, and advertises HS400/HS200 at 1.8 V.
Its supply phandles resolve to PM8994 L20 at 2.95 V and S4 at 1.8 V, matching
the pinned Wi-Fi port's mainline eMMC mapping.

USB uses DWC3 at `0x6a00000`, QUSB2 at `0x7411000` and QMP at `0x7410000`.
The stock QUSB2 analogue supply phandles resolve to L12 and L24. Its digital
`vdd-supply`, however, resolves to `pm8994_s2_corner`, using voltage corners.
The Wi-Fi mainline DTS assigns L28 to this property. The pinned mainline
power-domain driver maps MSM8996 VDD_MX to S2 voltage corners. An
[upstream QUSB2 fix](https://lore.kernel.org/all/20260610-topic-8996_61x5_qusb2phy-v1-3-d7135980e78f@oss.qualcomm.com/)
describes the same supply using VDD_MX and `rpmpd_opp4`. Our LTE override
applies that mapping and removes the inherited L28 `vdd-supply`. The current
driver can use a dummy regulator for the absent regulator property; the
power domain supplies the actual digital vote. No voltage-corner values
are converted to microvolts. USB networking and SSH work on hardware; idle power remains untested;
the PHY driver currently forbids runtime suspend by default.

Stock reserved ranges include `0x85800000 + 0x2a00000`,
modem `0x88800000 + 0x6c00000`, peripherals `0x8f400000 + 0x3100000`,
framebuffer `0x9a400000 + 0x1c00000`, Samsung debug/RKP/TIMA regions, and
QSEE `0xfec00000 + 0x1400000`. The peripheral node's *name* says `8ea00000`,
but its actual `reg` says `8f400000`; use the property, not the node name.
The stock tree also has a camera shared pool at `0xc0000000 + 0x14800000`.
The tested LTE DTS preserves these stock reservations.

Fingerprint SPI pinctrl uses GPIOs 25–28. Preserve the Wi-Fi port's conservative
secure-pin exclusions while investigating LTE behavior; successful DTB
compilation does not establish that TrustZone permits access to any GPIO.

## Power and next work

Open work is tracked in `todo.md` at the repository root; this section is the
historical note from the first inspection.

Initial Android inspection happened at 2–5% battery. The user later authorized
short boot tests at 31%; recovery reported 29% before the tests. Charging to 50%
or more is recommended for further development. Charging-controller support
under mainline remains unimplemented in the upstream port.

## Prepared LTE test build

Linux `6.19.5-gts3l1` and `msm8996-samsung-gts3llte.dtb` compile successfully.
The LTE DTS preserves the stock framebuffer and camera reservations,
reserves all TLMM GPIOs, removes the inherited LCD regulator, disables
CoreSight and disables eMMC for the RAM-only diagnostic. The modem and
other unsupported peripherals remain disabled. Full DT schema validation
has not been performed.

The lk2nd build uses the verified LTE rev05 IDs, a 4 MiB boot-partition
reservation and forced fastboot mode. The current boot donor uses the old
Android header's `dt_size` field and a separate QCDT table after the ramdisk,
not appended DTBs after its gzip stream. The packer preserves all four
SM-T825 stock DTBs (board revisions 0, 2, 4 and 5). The generated wrapper is
2,375,696 bytes. The diagnostic Android image is 19,570,704 bytes.

The uncompressed Linux Image is 28,348,928 bytes, below lk2nd's forced DTB
load address at DDR + 37 MiB. Its initramfs also fits below the 50 MiB boot
window end. The initramfs passed an authenticated ARM64 SSH command under
QEMU. Subsequent hardware tests established USB SSH and over 236 seconds of
uptime in the RAM-only image. Its display retained the old bootloader frame.

Additional verified private backups in `private/backups/20261010T103054Z/`:
EFS 20 MiB, modemst1/2 2 MiB each, persist 32 MiB. These contain sensitive
device identity/calibration data. TWRP 3.5.2_9-0 (Omni `gts3llte`, 2021-07-08)
booted successfully with root ADB and restored the boot backup. Holding Home +
Volume Up while sending a targeted reboot reached TWRP from lk2nd and Linux.
The lk2nd Recovery menu itself only returned to fastboot.

## eMMC validation

Update 2026-10-13: the full Debian installation uses HS400 at an actual 192 MHz
following read-only and filesystem write/checksum tests. Recovery retains the
52 MHz cap. See the [continuation report](platform-handoff-20261013.md).
The following paragraphs describe the original conservative bring-up.

The `-emmc.dts` variant enables SDHC1 with stock-verified L20/S4 supplies and a
52 MHz maximum. Linux reports HS200 at an actual 50 MHz, 8 bits, 1.8 V signaling.
The storage-probe initramfs marks all MMC block devices read-only before SSH
and mounts no tablet filesystems. All 47 partitions appeared. Full boot and
recovery hashes matched expected contents. Logs are in
`private/linux-storage-test/`; full DT schema checks remain pending.

The existing userdata partition is 26,226,966,016 bytes; Android used block
encryption and had about 11 GB of data. The user chose an internal Debian
installation and authorized erasing those files/apps. Installation uses the
existing userdata and boot partitions without changing the GPT. See
[the first-boot and restore plan](first-boot.md).

## Installed Debian

The internal installation overwrote userdata and boot with readback-verified
images. TWRP recovery's full SHA-256 remained unchanged. Debian 13, project
version 0.1.0, booted from `/dev/mmcblk0p47`; its root filesystem expanded to
about 24 GiB. Login as `dev`, passwordless sudo and USB networking all worked.
The first installed boot reported zero failed systemd units. Evidence is in
`private/linux-installed/` and `private/internal-install-session.json`.

The first `systemctl reboot` cleanly stopped services and unmounted storage,
then halted: the saved pstore console ended with `Reboot failed -- System
halted`. Firmware's PSCI reset call returned without resetting the tablet.
A physical restart successfully loaded Debian again from internal storage.

Both the stock SM-T825 device tree and lk2nd identify PS_HOLD at `0x004ab000`.
The LTE DTS now describes that register with `compatible = "qcom,pshold"`,
allowing the built-in `msm-poweroff` driver to provide a reset fallback. The
existing PMIC power-key driver configures the primary PMIC's reset type. The
updated DTBs are packaged in `linux-tabs3_6.19.5-3_arm64.deb`; the combined boot
image was separately written and its readback hash verified.

After a physical restart loaded the new DT, Linux bound `4ab000.restart` to
`msm-restart`. A subsequent `systemctl reboot` returned to USB SSH in 15.8
seconds with a new boot ID, systemd reporting `running`, zero failed services,
and the existing 24 GiB root filesystem mounted read/write. No physical keys
were needed for that software reboot. Evidence is in `private/reboot-fix.json`
and `private/linux-installed/`. This validates normal reboot, not power-off or
charging. Earlier recovery entry with hardware keys does not establish that
the old kernel supported normal reboot.

At this early storage-bring-up stage, display/touch, Wi-Fi, GPU, cellular and
Linux charging support had not been validated. Later results are recorded
below and in the [GPU/desktop record](gpu-desktop-20261011.json).
A retained Samsung/lk2nd frame is not a reliable indication of
whether Linux is running; use the USB session and saved logs.

## Display bring-up (AMS968HH01 / ANA38401, dual DSI)

The display variant RAM-boots with `msm.prefer_mdp5=0` (DPU) and the
display DTB; touch (Synaptics S5807) works. Findings from live DDI
register writes on this SM-T825 (`kernel/patches/0004`–`0011`):

- DPU needs the MSM8996 CTL split-display capability (`0004`). Frames then
  complete on both links with no underruns.
- Stock sends B1/B2 register writes as DCS long packets (`0005`), runs the
  lanes at 893.2 Mbps (the TCON is clocked from the continuous HS clock)
  and sends DCS tear-on after the on-command list (`0006`).
- DDI reads only answer in HS mode; LP reads get a bus turnaround with no
  data. A read while both links stream stalled command DMA.
- Panel ID reads `42 40 16`, matching the stock `lcd_id=0x424016`.
- After the stock init, the DDI stayed single-link: each 1024-pixel link 0
  line became a full 2048-pixel row with wrong colours (compressed-input
  decode) and link 1 was ignored. The dual DSI setting (`B0 51 / B1 06`)
  only took effect when the compression register (`B0 D9`) changed while
  the panel was on, with frames between the change. Display on also had
  to arrive after frames started.
- `0011` runs that as a timed fixup after enable: HS display on;
  compression 00; compression 08 plus dual DSI. A fresh boot then showed
  correct colours, geometry and a readable console.
- Tone and white point: the on-command gamma block (`83 80 80 ..`) is the
  downstream reference table. Smart dimming adds the panel's factory MTP
  calibration even at the top luminance level. Without it everything below
  about half grey was black and white looked yellow. `0013`/`0014` read the
  33 MTP bytes (`D8` at `0x5a`..`0x7a`, HS generic reads, after a priming
  ID read) and send the calibrated table; a 16-step grey ramp is now
  smooth and neutral. This panel's MTP:
  `33 51 55 43 3a 53 5b 36 14 00 00 40 51 57 42 3c 53 5b 3c 0c 00 00 38 53 56 47 3d 55 5c 64 82 00 00`.
- AID writes (`90 00 00 xx`, e.g. `0e` 360 nit, `c9` 51 nit) change
  brightness live, so brightness control can follow the downstream
  candela/AID tables. mDNIe (register page `B9`) responds (negative mode
  works); bypass looks identical to the power-on state.

The panel debugfs at `/sys/kernel/debug/ams968hh01/` (`cmd`, `fixup`) is a
bring-up aid. Blank/unblank cycles were not reliable during testing.

The display variant is now the installed boot image:
`private/images/tabs3-internal-display-boot.img` (lk2nd autoboot plus the
RAM-tested display Linux image, SHA-256 `aa65928a…`) was written to
`mmcblk0p28` from Debian and verified by a readback after dropping caches.
A software reboot returned in 25 seconds to a clean console and login
prompt, with no buttons pressed. The log of this boot path shows one DPU
event overflow and one kickoff timeout during the fixup, which the RAM
boots did not show; frames flow normally afterwards. Record:
`private/display-boot-install.json`.

To fall back to the headless image: hold Volume Down during a reboot to
stop in lk2nd fastboot, `fastboot boot private/images/tabs3-installed.img`
for a RAM boot, then write `private/images/tabs3-internal-boot.img` back
to the boot partition the same way.

Booting through lk2nd autoboot exposed a timing dependency: the console
registered 0.9-3.5 s after panel enable, so a fixup on a short timer could
finish before any frame was sent. The DDI then stopped producing TE and
every update logged "vblank wait timed out", hiding the login prompt
behind warning traces. `0015` starts the fixup 5 s after enable with
600 ms between steps; three normal reboots then reached a clean login
prompt. The garbled console visible for those first seconds is expected.
`tabs3-base` 0.1.1 clears `ignore_loglevel` and sets console log level 4
after boot so kernel messages stay off the login screen.

## Wi-Fi (QCA6174 on PCIe0)

Wi-Fi works from a normal boot: `ath10k_pci` finds the QCA6174 hw3.2 at
0000:01:00.0, loads `WLAN.RM.4.4.1` firmware with this tablet's own board
data (`/etc/firmware/bdwlan30.bin` on the Android system partition, installed as
`/lib/firmware/updates/ath10k/QCA6174/hw3.0/board.bin`; ath10k reports its
crc32 `0x579f7063`), and iwd connects with DHCP and systemd-resolved
(about 650 Mbit/s link rate on 5 GHz).
Samsung keeps no other copy of that board file, and Debian cannot ship it.
From `tabs3-base` 0.1.5, `tabs3-wifi-board.service` copies it on first boot
(read-only `debugfs -c`), before the PCIe rescan and before
`tabs3.root_extend=system` lets root grow over the partition. The base
rootfs installs iwd, bluez, firmware-atheros (`non-free-firmware`),
wireless-regdb and iw, and sets iwd's `/etc/iwd/main.conf` from
`build/iwd-main.conf` (iwd's own DHCP, systemd-resolved). What it took:

- Device tree (`kernel/msm8996-samsung-gts3llte-display.dts`): PCIe0 and
  its PHY, TLMM 35-37 unreserved, power chain `rome_vreg` (PM8994 GPIO 9)
  → WLAN_EN (GPIO 8) → BT_EN (GPIO 19) as the PCIe `vddpe-3v3` supply,
  L30 crystal supply always on.
- The decisive pieces: downstream PHY v3 values (`0017`: CLK_SELECT 0x35,
  spread spectrum off, RX/PCS tweaks), and BT_EN rising after WLAN_EN. Before
  either, the root port LTSSM sat in Polling.Compliance; with the PHY values
  but BT_EN left high by the bootloader, the link only came up after the
  Bluetooth driver (or a manual GPIO pulse) toggled BT_EN.
- Bluetooth on BLSP1 UART2 (hci_qca, SoC 0x44 ROM 0x302, rampatch/NVM
  00440302) works. The first attempt let hci_qca own BT_EN, which held it
  low through panel bring-up and left the panel dark; now BT_EN belongs to
  `bt_en_vreg` and the driver runs without power control. The chip has no
  address of its own: `tabs3-base` 0.1.3 reads this tablet's Samsung
  address from EFS (`/bluetooth/bt_addr`, read-only via `debugfs -c`),
  caches it in `/etc/tabs3/bt-address` and sets it with
  `btmgmt public-addr` before bluetoothd starts. btmgmt needs an open stdin
  (it exits at EOF before the kernel replies). BlueZ 5.82 then scans and
  sees nearby devices.
- `tabs3-base` 0.1.2 adds `tabs3-wifi-pcie.service`, a rescan fallback
  ordered before iwd; on the final image the card enumerates without it.

## Network SSH on this tablet

SSH answers on Wi-Fi as well as USB (sshd listens on all addresses). On
this tablet only, password login for `dev` was enabled at the owner's
request with `/etc/ssh/sshd_config.d/05-local-password.conf`
(`PasswordAuthentication yes`, read before the package's key-only
`10-tabs3.conf`). Root login stays disabled; `dev` still has passwordless
sudo. The password is not recorded in the repo. Images built from this
repo remain key-only. Host key: ED25519
`SHA256:zfB4DhEVPLiND6O6RokKoxq9PR9rGoGYJ16XYWxmnaE`.

## Power key, power-off and screen sleep

Update 2026-10-14 (`tabs3-base` 0.1.21): the book cover's magnet (hall switch,
`gpio-keys` SW_LID) switches the screen off when the cover closes over it and
on when it opens; while it is closed, touch and presence wakes are ignored
and only the power key lights the screen. Home and Volume Up now wake the
screen like a touch.

- A short press of the power key toggles the screen (display off/on); a
  touch also wakes it, and it switches off after 5 minutes without input
  (`tabs3-screen.service`, `TABS3_SCREEN_IDLE`). Hold the key for about
  5 seconds to power off (logind `HandlePowerKeyLongPress=poweroff`, from
  `tabs3-base` 0.1.4). The PMIC forces a reset after about 8.7 seconds
  (KPDPWR S1 6.7 s + S2 2 s, read from PON registers).
- Power-off works (clean shutdown, PS_HOLD released). With USB power
  connected, Samsung's bootloader then starts its charging screen and boots
  the boot partition, so Debian comes back up. Unplug USB to stay off.
- Since package 27, screen sleep uses DRM/fbdev blanking
  (`/sys/class/graphics/fb0/blank`, 4 off / 0 on). It lowers reset, cuts
  panel power and repeats LP11 initialization on wake. The earlier
  retained-supply DCS 28/29 backlight API was removed: it failed with
  bright content despite correct register values. Full power cycles and
  recovery Power/touch wake passed on hardware.
- Recent/Back key lights (TC305K LEDs, `/sys/class/leds/tm2-touchkey`):
  since `tabs3-base` 0.1.11 `tabs3-screen` lights them when the screen or the
  keys are touched and switches them off 3 s after the last touch
  (`TABS3_KEYLIGHT_SECONDS`, 0 disables) and whenever the screen is off, as
  on the stock firmware. Confirmed by the owner on 2026-10-13.
- On the text console the kernel's VT layer unblanks the screen on any key
  event, including the power key's own release: a power press that blanked
  the screen woke it again 0.6 s later, and `tabs3-screen` then believed it
  was off. Since 0.1.12 the power key acts on release and every decision
  reads the connector's DPMS state. Home, Volume and the touch keys still wake
  the console screen through the VT; under Phosh the compositor decides.
- Login details for this tablet are kept in `private/ACCESS.md` (ignored
  by Git).

## Storage: root over userdata and Android system

The eMMC holds 31,268,536,320 bytes. Userdata (`mmcblk0p47`, 26.2 GB) was the
whole Debian root; Android's `system` (`mmcblk0p44`, 4,194,304,000 bytes) sat
unused. The two are not adjacent (cache `p45` and hidden `p46` lie between),
there is no free space after userdata, and ext4 cannot span partitions, so
the GPT is left alone and device-mapper joins them instead:

    0        51224536 linear /dev/mmcblk0p47 0
    51224536 8192000  linear /dev/mmcblk0p44 0

`tabs3.root_extend=system` on the kernel command line makes the initramfs
check both partition names, create `/dev/mapper/tabs3root` with `dmsetup`
(no udev), check the root UUID on it and mount it. Userdata comes first, so
the existing ext4 kept its offsets; both lengths are whole 4 KiB blocks (the
filesystem had exactly 6,403,067 blocks, so the 7 trailing userdata sectors
were already unused). Without the option, booting is unchanged.

Before growing, `system` was saved to
`private/backups/20261010T182445Z-system/` (zstd, SHA-256 `cffd371e…`,
checked on the tablet and after decompression). It also holds Android's
vendor firmware for later bring-up. The Wi-Fi board file had already been
copied to `/lib/firmware/updates`; nothing in Debian reads `system`.

Sequence on 2026-10-10: a RAM boot mounted the joined device with the
filesystem still at its old size; the combined image (SHA-256 `189e2dea…`)
was written to `mmcblk0p28` and verified by a readback after dropping
caches; a software reboot came back in 19 s from it. The updated
`tabs3-grow-rootfs` then grew the mounted root online to 7,427,067 blocks
(28 GiB, 30,421,266,432 bytes). A further reboot mounted it cleanly in 16 s with no
failed units, and Wi-Fi, Bluetooth, SSH and screen sleep were active. Record:
`private/root-extend-install.json`.

Consequences: the filesystem is now larger than userdata, so TWRP or any
boot image without `tabs3.root_extend=system` fails to mount it (the
initramfs then starts USB rescue SSH). Never use TWRP's "format data".
`blkid` still reports the root UUID on `mmcblk0p47` as well. With dmsetup's
udev rules installed, the root device made in the initramfs (no udev, no
cookie) was marked `SYSTEMD_READY=0` and `/dev/disk/by-uuid` named
`mmcblk0p47`; a later fsck through fstab would have checked the bare
partition. `54-tabs3-root.rules` (`tabs3-base` 0.1.5) marks `tabs3root` as
activated and gives its by-uuid link priority, so the UUID resolves to
`dm-0` (checked after a reboot and a change event). Cache and hidden stay
untouched (TWRP keeps its logs on cache).

## microSD (SDHC2, packages 45-46)

Update 2026-10-14 (kernel package 64): UHS-I works. With `no-1-8-v` removed
the same Samsung EVO Plus card initialised at SDR104, 200 MHz, 4-bit, 1.8 V
signalling on a RAM boot and on five host re-initialisations in a row (each
one repeats the CMD11 voltage switch) with no error and no register dump;
raw reads run at 58.8 MB/s against 21.6-23.3 MB/s in High Speed. The
2026-10-13 failure described below did not reproduce, and its cause is not
known; the card was inserted before boot this time. Package 64 is a device
tree change only. Hot insertion is unchanged and still needs cards put in by
hand.

The slot is SDHC2 with the stock supplies and pins: L21 (2.95 V) powers the
card, L13 (1.8-2.95 V) the I/O; card detect is GPIO 95 (active low); clock
16 mA, command and data 8 mA with pull-ups. Stock Android runs it up to
SDR104. Tested on 2026-10-13 with a Samsung EVO Plus 128 GB (SDXC, exFAT).

UHS-I does not work yet. After the 1.8 V switch (CMD11) the card answers
commands, and 1-bit data reads (SCR, SD status, switch status) work, but the
first 4-bit transfer, CMD6 selecting SDR104 at 400 kHz, never receives its
data block. The controller waits with all DAT lines high and raises no
interrupt ("Timeout waiting for hardware interrupt", then "error -110 whilst
initialising SD card"). At 3.3 V the same 64-byte CMD6 status read over four
lines works at 400 kHz and at 50 MHz (`tools/sd-switch-status`, read-only),
as do block reads, so DAT1-DAT3 and the controller are fine: the fault is
specific to 1.8 V signalling. Pins and supplies match stock, and the I/O pad
switch reads 1.8 V mode. Package 45 sets `no-1-8-v`: High Speed, 4-bit,
50 MHz, 21.6-23.3 MB/s raw reads; a read-only exFAT mount listed all 5,009
files without errors. udisks reports the card as removable and
auto-mountable.

Hot insertion fails about half the time. The card answers every ACMD41 as
busy for longer than the 2 s the core waits ("Card stuck being busy!
__mmc_poll_for_busy"), and since the card detect line does not change again,
the card stayed undetected until it was reinserted. Cold boots, a reprobe of
the controller and the other insertions initialise it in 0.4 s. L21 and L13
really switch off after a removal: the PMIC's own view, read through the
SPMI registers, shows both disabled, with their discharge pull-downs enabled
(register `0x48` = `0x80`), so the card is not back-powered. Package 46 adds
patch `0019`: a present card that did not initialise is powered off and
scanned again a second later, at most twice. In the test one stuck insertion
recovered on the first retry; another stayed busy through both retries and
needed a reinsertion. The cause is unknown.

Debugging aids: the `qcom-spmi-regulator` instance on `pmic@1` registers
every PM8994 regulator without constraints, so it cannot switch anything
but reports the real state (`/sys/class/regulator/*/state` for `l13` and
`l21`). `mmc_core` dynamic debug (`drivers/mmc/core/core.c`) logs every
command and response; it also logs the eMMC, so keep it short, and the CID
response holds the card's serial number. `/sys/kernel/debug/mmc1/caps`
accepts a cleared UHS mask for one boot, which tests High Speed without a
new device tree. Record: `docs/sdcard-validation-20261013.json`.

## Speakers (RT5508, packages 47-51, desktop 0.1.10)

The speakers are driven by four Richtek RT5508 smart amplifiers on BLSP1 I2C3
(`0x7577000`, GPIO 47/48, 400 kHz, 2 mA, external pull-ups) at 0x34-0x37,
fed by the primary TDM interface (bit clock 65, frame sync 66, data to the
amps 68, from them 67; stock also holds GPIO 63, "qcom,i2s-sw-en", high).
There are no reset, enable or supply lines. Register 0x00 reads 0xE8 on all
four: RT5508 revision 8, newer than the last revision Samsung's driver names
(G = 6), so its revision G paths apply (`tools/rt5508-id`).

Stock runs PRIMARY_TDM_RX_0 with the SoC as clock master: 48 kHz, four
16-bit slots, 3.072 MHz bit clock, long inverted frame sync from an internal
source, data one bit clock after the sync, MSB aligned. Each amp selects its
slot with `chan_sel` (frame half) and its TDM DAC slot bit; the listening test
confirmed this reading of Samsung's names, in portrait with the Home key at
the bottom:

| TDM channel | Speaker | Amp | Stock name |
|---|---|---|---|
| 0 | bottom-left | 0x37 | LL |
| 1 | bottom-right | 0x36 | LR |
| 2 | top-left | 0x35 | UL |
| 3 | top-right | 0x34 | UR |

What it took on mainline:

- Patch `0020`, a playback-only port of the vendor driver: its reset, init
  tables, OTP-based temperature coefficient and the exact clock and boost
  power sequences; no tuning loader, calibration (it programs OTP) or data
  out. Registers only accept writes out of power-down, so format, sample
  settings and volume are applied at power-up. The DAC volume powers up at
  0 dB and stock never changes it; the driver starts at -40 dB.
- Patch `0021`: mainline parsed the TDM sync inversion and data delay but
  never sent them to the DSP, which would have shifted every frame by a bit.
  It also always sent a slot mapping, which this ADSP rejects for a single
  TDM group (`AFE_PORT_CMD_SET_PARAM_V2` returned EBADPARAM, port 0x9000 did
  not start); Samsung's kernel only sends one for several groups.
- Patch `0022`: the apq8096 machine driver now gives a PRIMARY_TDM_RX_0 back
  end four channels in four 16-bit slots and the bit clock while it is open.
- Package 47 enabled the bus but left GPIO 47/48 reserved; 48 released them,
  51 also 63 and 65-68 (TrustZone pins stay reserved; `tools/check-dtbs`).
  Package 49's driver refused register 0x28, which the revision G table sets,
  and the whole sound card failed to probe; 50 allows exactly that register.

On package 51 the amps report EVENTINFO 0xC0 during playback (bit clock and
PLL locked, no fault flags), power up only while a stream runs and power
down after it. The owner heard 1 kHz tones at -60 to -40 dB below full
output, each channel from the expected corner, and their own voice
recording played back without distortion.

The desktop profile (`tabs3-desktop` 0.1.10) adds a UCM "Speaker" device on
MultiMedia1 with four channels and priority 200 (headphones 100; there is no
jack detection), and a -10 dB amplifier ceiling, because there is no speaker
protection algorithm. WirePlumber names the channels FL FR RL RR with the
simple upmix, so stereo plays on both speakers of each side in portrait.
The DSP routes of all three front ends moved into the HiFi verb: PipeWire
opens every PCM before it enables a device, and a front end without a route
cannot be opened, which had dropped the whole HiFi profile. 24-bit (S24_LE)
playback runs but is inaudible, while the same tone in 16-bit plays, so
WirePlumber now opens every PCM of the card as S16LE (the headphones were
affected too). Through PipeWire, a left-only and a right-only tone came from
the left and right side. Record: `docs/speakers-validation-20261013.json`.

## Sensor DSP and auto-rotation (packages 52-55, `tabs3-sensors` 0.1.0)

Auto-rotation works: in all four orientations the picture turns upright and
touch input follows it (owner, 2026-10-13, Phosh). The motion sensors are not
visible to Linux directly: they sit on the SLPI's own buses, and Android read
them through Qualcomm's Sensor Core. Linux talks to the SLPI's Sensor
Manager with the community drivers (patches `0023`-`0026`, from
gitlab.com/msm8996-mainline/linux, branch msm8996-staging-smgr) plus `0027`
and `0028`, and the `tabs3-sensors` package serves the SLPI its registry.

- SLPI firmware: `slpi.mdt` and 15 segments in the read-only apnhlos
  partition (`tools/install-slpi-firmware`); relocatable, span 0xa00000.
  Stock supplies: CX on L26 (the `ssc_cx` domain), PX on LVS2 (proxy) and
  `vdd_sensor` on L17 at 2.8 V, kept on (`sensors.dtsi`).
- TrustZone authenticates the SLPI only inside Samsung's peripheral region:
  at 0x92500000 (RAM after it) the start failed with "failed to authenticate
  image and release reset"; at 0x91600000 (package 53, MBA moved to
  0x92000000, Venus region dropped) it runs. The modem still boots with the
  moved MBA.
- **Registry.** The SLPI waits for the registry service (QMI `SNS_REG`,
  0x10f) before it starts its Sensor Manager, and reads it once per start.
  Samsung's firmware needs Samsung's registry: one assembled from the vendor
  `sensor_def_qcomdev.conf` alone lacks groups 0020, 2691 and 3050 and made
  the SLPI crash about 170 ms after every start (143 restarts a minute).
  Android's `sensors.qti` builds the real one, `sns.reg`: 100 groups at fixed
  offsets in a 25600-byte image, from built-in defaults plus that file.
  `tools/sensor-registry/make-registry.py` rebuilds it from the tablet's own
  system backup by running `sensors.qti`'s `sns_group_data_init()` in an
  ARM64 emulator (table addresses from IDA). The image is Samsung-derived
  and stays in `private/`; see `tools/sensor-registry/README.md`.
- **Server.** `tabs3-sns-reg.service` runs the community `sns-reg`
  (`third_party/`, GPL-3.0-or-later) with an image mode
  (`third_party/sns-reg-image-mode.patch`) that serves each group's bytes
  from `/etc/sns-reg.d/registry.bin`. With it enabled, the Sensor Manager
  registered 0.45 s after the SLPI started at boot (package 55, 2026-10-13).
- The Sensor Manager (service 0x100, version 1, instance 50, QRTR node 9)
  reports four sensors: 0x00 accelerometer and 0x0a gyroscope
  (STMicroelectronics K6DS3TR), 0x14 magnetometer (AKM AK09916) and 0x28
  light (Capella CM3323). In package 55 only the accelerometer had a driver
  (`qcom-smgr-accel`); the others were skipped since `0027` (an unknown type
  used to register a device named NULL: kernel crash, reset after
  `panic=30`). Package 61 adds gyro, magnetometer and light samples, including
  the firmware light data-type selector fix. Their physical response and
  calibration checks are pending; see the continuation report.
- **Units and axes.** Samples are Q16 m/s^2: Samsung's HAL
  (`Accelerometer::processReportInd` in `sensors.ssc.so`) scales them by
  0.000015259 (1/65536), while the community driver's `in_accel_scale`
  estimate (0.000015328) is 0.45 % high. They are in Qualcomm's SAE frame
  for Android's portrait orientation: x towards the top (camera end), y
  towards the right edge, z into the screen (the HAL makes Android's x, y, z
  from sample 1, sample 0 and minus sample 2). The registry's own axis map
  (items 700-702) is applied by the SLPI.
- **Mount matrix.** The panel's native mode is 2048x1536 landscape, with
  the Home key on the right. For iio-sensor-proxy, which drives the
  rotation in Phosh and Plasma (its tests: upright `normal` reads y = -1 g,
  `face-up` reads z > 0), the matrix is `1, 0, 0; 0, -1, 0; 0, 0, -1`.
  `tabs3-sensors` sets it as `ACCEL_MOUNT_MATRIX` in
  `61-tabs3-sensors.rules`, which overrides the driver's `in_mount_matrix`;
  that one is a placeholder from a portrait phone and gave a constant
  90-degree error here (owner check, all four orientations). The same rule
  sets 10 Hz: the driver defaults to the sensor maximum, 416 Hz, which cost
  about 13 % of a CPU core while the proxy streamed.
- **Raw readings** (`0028`): `in_accel_{x,y,z}_raw` start a stream at up to
  10 Hz on the first read and stop it 3 s after the last one, so
  iio-sensor-proxy's polling driver needs no trigger. The proxy prefers the
  triggerless buffer when it works, as it did with package 55; raw reads
  then return EBUSY, as IIO requires.

## Cameras (identified 2026-10-13)

The stock device tree describes the camera power, GPIOs and buses but not
the sensor models; Samsung's camera libraries in the Android system image
name them. Rear (CSIPHY0, CCI master 0, mounted at 90 degrees): Sony IMX258,
13 MP (`libmmcamera_imx258.so`, tuning `W13QS_libchromatix_imx258_*`), with
a DW9807 voice-coil actuator at 0x18 (`libactuator_dw9807.so`), the module
EEPROM behind it and an LED flash. Front (CSIPHY2, CCI master 1, 270
degrees): Samsung S5K5E3YX, 5 MP, with OTP (`libmmcamera_s5k5e3yx.so`,
`libmmcamera_lsi_s5k5e3yx_eeprom.so`). Both use a 24 MHz MCLK. The stock camera supply phandles resolve to PM8994: S3 (digital),
LVS1 (I/O), L29 (rear analogue), L23 (front analogue), and L17 (focus).
The earlier S2MPB02 supply claim was incorrect; its regulator nodes have
no camera consumers in the stock tree. The flash is described by SM5705.

Mainline 6.18 has `imx258`, `dw9807-vcm` and MSM8996 CAMSS; it has no
S5K5E3 driver (patch `0040` adds one, package 65) and needs no S2MPB02
driver, as both sensors run from PM8994 rails. The rear camera was the first
target: verified camera regulator sequencing, CCI and CAMSS device tree,
then libcamera's simple pipeline with the software ISP.

### Rear camera bring-up (package 62, branch `drivers-62`, in progress)

`camera.dtsi` describes the IMX258 at 0x1a on CCI master 0 (MCLK0 24 MHz on
TLMM 13, XCLR on TLMM 30 driven by patch `0036`, VANA L29, VDIG from the
CAM_CORE_EN switch on TLMM 9 fed by S3, VIF LVS1), the DW9807 at 0x18 on
BLSP2 I2C1 as its `lens-focus`, and the CAMSS with CSIPHY0 on four lanes.
On the 2026-10-13 RAM boots the sensor probed (its chip ID read over CCI),
the actuator bound once LVS1 stayed on, and the full media graph appeared
(`/dev/media0`, eight video nodes). Streaming failed twice:

- the CSI PHY's top AHB clock was stuck off because the CAMSS block's own
  power domain is only switched on through the VFE domains, after the PHY
  in the pipeline order; the camera node now lists the CAMSS GDSC as a
  third, last power domain, which the driver attaches to the device;
- link validation then returned EPIPE (a pad-format mismatch; the
  formats are printed by `tools/camera-capture-test` with the kernel's
  debug messages on), and the power-off path crashed: on MSM8996 the CSID
  powers through the VFE, and the ISPIF reset released the VFE's power
  domain device link that the VFE still held, so the VFE's own release
  dereferenced NULL (patch `0037` counts the link's users). That crash left
  the RAM-booted tablet answering ping without any shell; the kernel now
  panics on an oops, a two-minute hung task or a soft lockup, so `panic=30`
  reboots an unattended tablet.

Package 62 then streamed. `tools/camera-capture-test` captures the binned
2104x1560 frames through the RDI path (the sensor chooses the Bayer order
through its flip controls, SBGGR10 here, and the tool follows it; the
packed rows are padded to 2632 bytes), and `tools/camera-frame-to-png`
turns a capture into a picture. The first decoded frames looked like
diagonal bands, which was the decoder shearing the picture with a 2630-byte
stride; decoded with the padded 2632 bytes, the same capture shows the desk
and a monitor, with the edge of the book cover (folded behind the mounted
tablet, partly over the lens) dark across the bottom. Exposure and gain are
set by hand on the sensor subdevice (`analogue_gain`, `exposure`; nothing
adjusts them yet).

Every capture after the first in a session wedged the ISP, and that turned
out to be the display, not the camera. The VFE writes its frames through
the multimedia NOC, a path the RPM only keeps clocked while somebody votes
bandwidth on it, and the MSM8996 camss resources vote for nothing. While
the panel is on, the display's vote keeps the path alive; once
`tabs3-screen` blanks it (60 s idle) the VFE still receives every frame
(its SOF interrupts keep counting) but no write completes, the halt at
stream-off times out ("VFE halt timeout") and the VFE SMMU then reports
"TLB sync timed out -- SMMU may be deadlocked" at every unmap until a
reboot. Reproduced on demand on 2026-10-14: three sessions in a row
succeed with the screen on, the next one fails with it off. Patch `0039`
adds the two interconnect paths (`cam_ahb`, `cam_vfe_mem`, with the
MSM8953 bandwidths) and `camera.dtsi` wires them to the VFE's NOC master
and the camera configuration slave. Kernel package 63 carries it and was
validated from a RAM boot on 2026-10-14 (entered through recovery's
software fastboot, see `docs/recovery-fastboot.md`): with the panel off and
the display voting nothing, the camera's own votes appear in the
interconnect summary while it streams (38400/76800 kB/s on `cam_ahb`,
939524/1342177 on `cam_vfe_mem`), and 30- and 300-frame captures complete
without a halt timeout or an SMMU error. The package 63 image was written to
the boot partition from recovery at 13:02 the same day (readback verified)
and the screen-off capture passed again from disk. The camera was parked at
this point.

The DW9807's refused writes (ENXIO at probe, packages 62 to 65) were an
address: the stock tree's 0x18 is the part's 8-bit write address, and a
probe of the bus on 2026-10-14 found it answering at 0x0c with its EEPROM
block at 0x58 (stock 0xb0). Kernel package 66 (device tree only) moves the
actuator to 0x0c and describes the EEPROM as a read-only 24c64: the driver
probes without an error, `focus_absolute` 0 to 1023 moves the lens, and
the edge variance of rear frames peaks sharply in the middle of the range
(538 at 500 against about 215 at either end, with the folded cover's flap
and a laptop's speaker grille in view), so `tabs3_camera` (`tabs3-base`
0.1.26) got a contrast autofocus: a coarse sweep and finer steps around
the best position, about eleven frames, held while the picture is taken
(the driver powers the coil down when nobody holds the device and the
lens springs back). `tabs3-snapshot --camera rear` focuses by default
(`--focus auto`, a position, or `none`). The EEPROM holds 1908 bytes of
data behind a section map at 0x0000 and names the module `W13QSJI00NM`
(the W13QS of the stock tuning files), but it only answers while the
DW9807 is awake: with the actuator powered down every byte reads 0xff, so
read it with the lens device held open. Automatic exposure is done
(below); libcamera is the remaining question.

### Front camera bring-up (package 65, 2026-10-14)

The S5K5E3YX has no public datasheet; its register tables come from the
vendor library in the Android system image (`libmmcamera_s5k5e3yx.so`, hash
and offsets in `research/platform-20261013/camera/NOTES.md`, section 14): a
97-entry initialisation table and two 45-entry mode tables, 2576x1932 at
30 fps and 640x480 (4x4 binned) at 120 fps, both at 896 Mbps per lane on two
lanes from the 24 MHz MCLK2. Patch `0040` is a driver in the style of
`imx258`: V4L2 CCI, runtime PM over vana (L23 2.8 V), vdig (the front's own
CAM_CORE_EN switch on TLMM 8, fed by S3) and vio (LVS1), the reset GPIO
(TLMM 40), exposure, analogue and digital gain, vertical blanking, flips and
the test pattern; the chip id 0x5e30 is read at probe. `camera.dtsi`
describes it at 0x10 on CCI master 1 and adds the CAMSS CSIPHY2 port.

Two things cost a RAM boot each. The full tree's `gpio-reserved-ranges`
still reserved TLMM 8, 15 and 40, so the core-enable regulator failed to
request its pin ("could not request pin 8") and the sensor waited for that
supplier forever; the three pins are free now. Then CSIPHY2 -> CSID2 failed
at open ("Failed to power up pipeline: -22"): the CAMSS driver powers a
CSID through the VFE of the same index, and MSM8996 has four CSIDs but two
VFEs, so CSID2 and CSID3 cannot be powered at all. The front camera streams
through CSIPHY2 -> CSID1 -> ISPIF1 -> VFE0 RDI1 (`CAM=front
tools/camera-capture-test`), leaving the rear's CSID0, ISPIF0 and RDI0 path
untouched; the two cameras alternate in one boot.

Validated from the RAM boot and again from disk after the flash
(`docs/kernel65-validation-20261014.json`): full-resolution and VGA
captures with the screen on and blanked, the sensor runtime-suspended
between captures, and a frame at exposure 2000 lines and 4x gain decoded
(`tools/camera-frame-to-png`, GRBG) to the room, sharp and with neutral
colours: ceiling lights, a vent, a mirror. In the landscape mount the raw
frame comes out upright. The pictures stay under `private/captures/`. Open:
automatic exposure, a snapshot tool and, since this camera faces the room,
presence detection.

### Cameras in use: exposure loop, snapshots, presence (2026-10-14)

libcamera 0.4 (Debian's `libcamera-tools` and `libcamera-ipa`, installed on
the tablet for the trial) lists both cameras through its simple pipeline
handler and streams them with the software ISP (front 2576x1932 at 30 fps,
rear 2104x1560 at 15 fps), but its uncalibrated processing is unusable
here: after a neutral first frame (mean RGB 67/66/64) the output drops to
near black with a green cast (3/29/1) on both cameras while it drives the
rear sensor to its longest exposure, so the fault is in the ISP's black
level or colour gains, not in the sensors (the simple IPA has no sensor
helper for either and falls back to `uncalibrated.yaml`).

libcamera 0.7.2, built from its git tag on the tablet (`/srv/build/libcamera`,
meson with only the simple pipeline, the simple IPA and `cam`; about
forty minutes on the four cores) behaves: on both cameras the processed
frames start dark and settle within about ten frames at a neutral mean
near 78 of 255 (front 78/78/73, rear 77/78/76 at frame 23), the rear's
lens initialises now that the DW9807 answers, and the output is a crop of
the sensor at the requested size rather than a scaled frame (1288x966 shows
the middle of the front sensor). The software ISP runs at 10 to 15 fps at
those sizes, the simple IPA has no autofocus and still no sensor helper
for the S5K5E3. It is installed under `/usr/local` (`ninja -C build
install`; `/usr/local/bin/cam` shadows Debian's 0.4 one, both libraries
coexist by soname; `ninja -C build uninstall` removes it) for anything
that wants a standard camera stack. The dashboard and `tabs3-snapshot`
keep the raw path: it is cheaper, it focuses, and it needs no ISP running.
libcamera takes no part in their lock: a `cam` run while the dashboard's
presence sampler was streaming reset the sampler's links under it, and
the aborted stream left subdevices marked as streaming in the V4L2 core,
so the next raw capture warned (`v4l2-subdev.c:484 call_s_stream`) and
timed out before everything recovered on its own. Run libcamera with the
screen on, or with `tabs3-dashboard` stopped.

Instead `tabs3_camera.py` (`tabs3-base` 0.1.25, in `/usr/libexec`) drives
the raw path with v4l-utils: the media links and formats for one camera
(the front through CSID1, the rear through CSID0), single frames with
`v4l2-ctl` (the camera is powered only meanwhile), metering on the 8-bit
view of the packed frame (the four high bytes of every five, no unpacking)
and an exposure loop that raises the exposure to 1/30 s, then the analogue
gain to 8x, then the exposure to half a second, backing off when more than
4 % of the picture saturates (the ceiling lamps). The sensors' gain codes
are mapped (S5K5E3: code/32; IMX258: 512/(512-code)), the frame is
lengthened through vertical blanking when the exposure needs it, and the
last exposure of each camera and mode is kept under `/var/lib/tabs3-camera`.
In the lit room the loop settled in three steps on both cameras (front
66 ms at 8x, median 78 of 255; rear 150 ms at 8x behind the folded cover,
which covers that lens in the mount). `decode()` turns a frame into a
half-size colour picture with numpy (black level 64, grey-world white
balance, a white point that lamps cannot drag down, gamma 2.2); without
numpy the grey view is returned.

On top of it: `tabs3-snapshot` (`tabs3-base`) and the dashboard's camera
presence wake (`tabs3-dashboard` 0.1.5, see `docs/dashboard.md`; evidence
in `docs/camera-userspace-20261014.json`; the corner picture that 0.1.5
also showed was removed in 0.1.6, the owner wanting the camera for the
wake only).
The presence sampler takes a 640x480 frame every 4 s while the screen is
off (about 470 ms with the camera on), compares 40x30 grids at equal
brightness and wakes the screen at a 3.5 % change; a still room measures
0.2 to 0.3 %. The two users of the CAMSS take `/run/lock/tabs3-camera.lock`
in turn, and the dashboard's service allows `/dev/media0` and the
video4linux nodes. Still to do by the owner: a wave at the tablet with the
screen off (the journal then shows `presence wake: camera: N % of the
picture changed`).

## S Pen (package 62, branch `drivers-62`, in progress)

The digitizer is a Wacom W9019 EMR controller with Samsung's firmware
(stock `wacom@56`: I2C 0x56 on BLSP2 I2C6 at 400 kHz, interrupt TLMM 34
falling edge, pen-detect output TLMM 117, firmware-write-enable TLMM 24
held low so the application firmware answers, 3.3 V from a fixed regulator
enabled by TLMM 126). Samsung's firmware does not speak the HID-like I2C
protocol of the mainline `wacom_i2c` driver (that only lives in its
bootloader at 0x09): patch `0035` adds a "wacom,w9019" variant with the
single-byte query and survey-exit commands, the 15-byte big-endian query
reply and 14-byte reports with tilt and hover distance, plus the
`touchscreen-*` orientation properties. On the 2026-10-13 RAM boot the
controller answered the query with the stock limits: 19661 x 14746 units
(0.01 mm) and 4095 pressure levels, and "Wacom I2C Digitizer" appeared as
an input device with tilt and distance axes. Pen strokes and the axis
orientation against the landscape panel are not yet checked.

## Grip sensors (package 62, branch `drivers-62`)

The LTE antenna's Semtech SX9310 (stock `sx9310-i2c@28` on a bit-banged bus,
SDA TLMM 81, SCL TLMM 82, interrupt TLMM 132) answers at 0x28 and binds to
the mainline `sx9310` driver (four proximity channels), but its probe at
6.6 s after boot fails with ENXIO even with its rails (L17 and LVS2)
described and enabled by the driver, and the sensor DSP finishes booting
at 7.0 s, and the chip answers a few seconds after that (on 2026-10-14 a
bind at 10.2 s still failed, one at 11.8 s succeeded; by hand, minutes
later, every bind succeeds). What the chip waits for is still not isolated
(the DSP's own supply votes or its pin setup are the candidates). `tabs3-sensors` 0.1.1 therefore binds it from
`tabs3-grip-sensor.service`, which waits for the SLPI to run and retries
for up to a minute; the kernel does not retry a probe that failed with
ENXIO. Nothing answers on the stock Wi-Fi grip bus (TLMM 49/50), so that
node is not described.

## Recovery (replaces TWRP)

Update 2026-10-13: recovery now includes software entry to its lk2nd fastboot,
with a consumed one-time request and 120-second idle timeout. Its Linux kernel,
DTB and modules remain package 29. Details and validation are in
[`recovery-fastboot.md`](recovery-fastboot.md). Generic fastboot partition
writes are blocked in this recovery variant because it splits recovery rather
than boot; persistent boot updates still use the checked recovery helper.

Entering recovery from Linux works without keys: `systemctl reboot
--reboot-argument=recovery` makes the PM8994 PON driver write reason 1 to
`SOFT_RB_SPARE` (`0x88f`), and Samsung's bootloader then boots the recovery
partition with `androidboot.boot_recovery=1` (first seen with TWRP, which
came up in 32 s). lk2nd cannot use that partition as is: it only reserves
its own space in `boot`, and when told to boot recovery it would read the
recovery partition from offset 0. A second lk2nd built with
`LK2ND_PARTITION_BASE=recovery` reserves the start of recovery instead, and
`LK2ND_FORCE_RECOVERY=1` (patch in `bootloader/patches/`) makes it always
boot the image after it, since the PON reason may already be consumed.

The initial recovery Linux was the then-installed kernel and DTB with
`tabs3.mode=recovery`. DRM, the msm display driver, the panel driver and
evdev are modules, so the initramfs carries 15 of them uncompressed for
busybox `modprobe` (about 1 MB compressed); the initramfs is 10.5 MB of its
11 MiB window. `setfont` with Terminus 32x16 (`console-setup-linux`) gives
a 128x48 console; busybox `loadfont` cannot read PSF2.

Leaving recovery needs one more step. After a plain reboot from recovery the
tablet booted recovery again, with the PMIC reason, IMEM `restart_reason`
(`0x066bf65c`) and `misc` all clear. The first word of Samsung's `param`
partition (`mmcblk0p25`) read 2 while in recovery and 0 after TWRP's own
reboot; Samsung's bootloader evidently keeps booting recovery while it is 2.
`tabs3-recovery` resets it from 2 to 0 when leaving, after which Debian
booted (checked twice). A PMIC forced reset does not clear it. Backups:
`private/backups/*-param/` (whole partition) and
`private/backups/20261010T094140Z/recovery.img` (TWRP).

Verified over USB SSH on 2026-10-10: status, read-only mount of the joined
root, `e2fsck -fn` (clean, 1 s), USB mass storage export of the whole eMMC
read-only (seen by the PC, nothing auto-mounted) and back off, display with
the panel fixup, `flash-boot` (boot image written and read back), and exit
to Debian. Framebuffer captures showed the banner and the progress lines;
sshd logs go to `/run/log/sshd.log` so they stay off the screen. Not yet
verified: Home + Volume Up +
Power with this recovery, the power key and touch handling. The boot
partition now uses the same initramfs (normal boot verified in 17 s).
Record: `private/recovery-install.json`.

The recovery screen is an LVGL 9.4 app (`recovery-ui/`, about 530 KB,
built in `tabs3-ui-builder`, a derived image with the ARM64 C library
headers). It writes rendered areas to `/dev/fb0` with `pwrite`: the fbdev
write path reports damage to DRM, which this command-mode panel needs, while
memory-mapped writes would not reach the panel. It sets `tty1` to
`KD_GRAPHICS` so the console does not draw over it, reads status from
`tabs3-recovery _status`, and runs actions through `tabs3-recovery`. The
touch controller reports portrait coordinates (x 0-1535, y 0-2047, from
`EVIOCGABS`) for the landscape panel; the app swaps the axes and inverts y
(`TABS3_TOUCH=cw` selects the other rotation). Framebuffer captures on the
tablet matched the host preview and followed a storage export started over
SSH. Touch and power-key handling were untested at that stage; the later
physical results are recorded in the LP11 validation section below.

On 2026-10-11 the filesystem-check result reporting was fixed: the helper
now preserves e2fsck's exit status, and the screen distinguishes clean,
repaired, reboot-required, unrepaired, cancelled and failed checks. Preflight
refusals (mounted/exported root or a failed root lookup) return operational
error 8 rather than status 1, which means a successful repair to e2fsck.
Previously the helper always returned 0 after e2fsck, so the screen could
claim "no errors" even when errors remained.

The updated recovery was installed with a verified backup and readback;
only its helper and UI binary changed. The boot partition was unchanged.
All 15 host tests passed, including result-bitmask and refusal tests, and
the ARM64 initramfs SSH build check passed. On the tablet, recovery booted,
the real read-only check of the joined root returned 0 (clean), a mounted
root refusal returned 8, and a simulated checker returned 4/8/32 unchanged
through the installed helper. Recovery then returned to Debian with no
failed services. Record: `private/recovery-fsck-fix.json`. Hardware-button
recovery entry remains untested; touch targeting and Power handling passed
the later physical checks below.

## Battery and charging (SM5705)

The SM-T825 has no PMI8994: a Silicon Mitus SM5705 charges the battery and
measures it. The stock kernel reaches it over two bit-banged I2C buses,
which the display DTS now describes: the fuel gauge at 0x71 on TLMM 6 (SDA)
/ 7 (SCL), the charger at 0x49 and its MUIC at 0x25 on TLMM 33 / 32.
Patches `0020`–`0022` and `0024` add drivers with register formats taken from Samsung's
GPL drivers. The calibration and charge-enable wiring are specific to this
SM-T825 rev05; they must not be assumed correct for other SM5705 boards.

- `sm5705-battery`: state of charge, voltage, open-circuit voltage, net
  battery current (positive into the battery), temperature and 6000 mAh
  design capacity. Status follows the charger, so a small net current no
  longer incorrectly reports "Not charging". The gauge retains its stock
  configuration. A lit screen can consume more than a PC port supplies,
  making battery current negative even with the charger active.
- `sm5705-charger`: cable (`online`), charging state, health, `usb_type`,
  input and charge current limits, float voltage and charger-board
  temperature. Limits are 500 mA for SDP and at most 1500 mA for CDP/DCP.
  DCP detection alone does not justify the old 1800 mA setting.
  `sm5705_charger.auto_input_limit=0` now caps input at 500 mA.
  Writable `input_current_limit` adds an upper bound; it cannot override
  source or temperature limits. `charge_behaviour` accepts `auto` or
  `inhibit-charge`.

Before the driver was added, the charger was already enabled (operating mode
`0x0C` = 0x05, charging on, watchdog off) with a 2000 mA charge current and
4.38 V float voltage; only the input limit (475 mA, left by the
bootloader) held it back. On 2026-10-11 on a PC port: 62%, 3.89 V, +83 mA,
MUIC `DEVICETYPE1` 0x04 (SDP), then 500 mA input. This establishes that
charging was active, not that unattended charging without thermal control
was safe.

### The keeper's forced descent (kernel package 68, `tabs3-base` 0.1.27)

The battery keeper of 0.1.22 could only inhibit charging, and inhibit
leaves the charger's buck supplying the system, so a full battery just
rested at 100 %: the owner saw "100 %, Not charging" for a day and asked.
Self-discharge alone would have taken weeks to reach the window. Patch
`0041` adds the `force-discharge` charge behaviour to the SM5705 driver:
operation mode SUSPEND (the stock driver's "buck off", which Samsung uses
for its store mode) switches the buck off, so the tablet runs from its
battery although VBUS is present, with charging disabled through the
enable pin. The driver ends it on its own when the gauge reaches 15 %,
when VBUS goes away, after a control fault, and at shutdown or suspend,
reports the battery as discharging meanwhile, and the keeper sets `auto`
whenever the charger is offline, so a dead script cannot drain the cell.
The keeper now runs the forced discharge from three points above the high
mark (83 % with the defaults) down to the high mark, inhibits there, and
charges again from the low mark; with both marks at 100 it never
discharges. Checked on a RAM boot of package 68 on 2026-10-15: in
force-discharge the status read "Discharging" with the charger online and
the gauge showed 465 to 654 mA out of the battery, inhibit returned to
-4 mA at rest, auto to +128 mA of top-off. Flashed at 09:47; the keeper's
first run set force-discharge at 100 % and the descent started at about
270 mA (`docs/kernel68-validation-20261015.json`).

### Temperature protection (`0022`/`0024`, kernel package 6.19.5-25)

Battery and charger-board thermistors use PM8994 VADC channels 0x74 and
0x77. Conversion uses the raw ADC tables from this tablet's saved Android
DTB, matching [Samsung's GPL board source](https://github.com/awesometic/android_kernel_samsung_msm8996/blob/f48aec90fcebf4615fdee4a8abac7339930db856/arch/arm64/boot/dts/samsung/msm8996-sec-gts3llte-common-battery.dtsi).
Generic Qualcomm temperature conversion is not used. Active-low PM8994
GPIO13 is the stock nCHGEN control; it is unrelated to TLMM GPIO13.

- Stop charging at battery temperature <=5 C or >=41 C; resume only
  between 10 and 39 C. Below 15 C, limit battery charge current to 900 mA
  until 20 C; at >=39 C use 900 mA. Otherwise charge current is at most
  1500 mA. This is a conservative subset of Samsung's swelling policy.
- At charger-board temperature >=50 C, cap input at 500 mA until <=47 C.
- Thermal or manual battery-charge inhibition leaves the source-limited
  system supply available; nCHGEN disables charging separately. Invalid
  thermistor readings inhibit battery charging and cap system input at
  500 mA (or a lower user limit). Valid VBUS with an unclassified MUIC
  result gets a conservative 500 mA limit. MUIC read errors, charger
  faults and failed control operations inhibit charging and request the
  minimum 100 mA input. Unknown-source hardware remains untested.
- Poll every second; preserve unrelated register bits, read back writes
  and retry failures. Never raise float voltage; refuse to enable charging
  if its register exceeds 4.38 V. Suspend/shutdown inhibit charging;
  resume reevaluates temperature and source before enabling it.

The 21 host tests cover calibration, thermal hysteresis, sensor errors,
current limits, failed-write retries, MUIC read errors versus valid unknown
results, recovery wake-gesture suppression, and recovery filesystem-check results.
In the test recovery, real thermistors report plausible values (battery
23.5 C, charger board 29.0 C). A manual inhibit cleared the chip's charging
state. Package 22 also reduced input to 100 mA; package 23 corrected that
and a real inhibit test retained the PC's 500 mA input with charge type N/A.
`auto` restored charging; both battery and charger reported Charging. These checks do not
simulate an actual overheated battery or a stopped kernel: temperature
protection still depends on the kernel polling successfully.

Install/readback records and previous boot/recovery backups are referenced
by `private/charging-safety-install.json`; subsequent package-24 image hashes
and checks are in `private/kernel24-install.json`. Both images and the normal
Debian kernel package are installed. Normal reboot, USB/Wi-Fi SSH and
temperature readings passed (23.8 C battery, 29.1 C charger board), with
no failed systemd units. The user's wall charger was detected as DCP.
A supervised ramp held 500 mA initially, 1000 mA for 30 seconds, then
1500 mA for 60 seconds. At the 1500 mA input limit, net battery current
was 1.17–1.23 A, battery temperature 23.3–23.4 C and charger-board
temperature 30.3–30.8 C; voltage reached 4.04 V and health stayed Good.
Automatic source/temperature limits were enabled after the test. Reconnecting
to the PC then detected SDP and returned the input limit to 500 mA without
manual intervention, with health Good. This is a short functional test,
not a full-charge or thermal-soak qualification.
Interrupt support, AFC 9 V,
gauge reinitialization after battery disconnect and reliable system
suspend remain unverified.

### Recovery display investigation (2026-10-11; historical failures)

The user reports readable geometry with washed colours and moving lines
in the test recovery. A framebuffer capture is correct, and the three
panel fixup steps execute. Replaying the fixup with repeated framebuffer
writes did not clear the physical symptom. The user successfully left
recovery with a 3-second Power hold and reports a correct Debian text
console. Showing the same recovery framebuffer under the old package-21
Debian kernel also reproduced the bad colours/lines, despite confirmed
30 Hz frame updates on both DSI links. Thus this is not isolated to the
new charging kernel. Applying the exact stock ACL-on and normal-temperature
smart-ACL ELVSS (360-nit table entry) over HS DSI before showing that picture
in freshly booted Debian produced correct colours and no moving lines.

Patch `0023` applies those normal operating settings on init, after input
fixup and on wake. The first kernel test still failed: the existing
long-register-write helper hard-coded LP mode, even when its caller selected
HS. Manually sending all ten packets in HS to the running recovery fixed
its colours/lines and changed net battery current from about -1.47 A to
+0.16 A on the same 500 mA PC input. Patch `0025` makes long register writes
honour the selected mode. Applying normal conditions in the same step as
compression still failed in package 24; a live back-to-back HS sequence
again corrected the screen. Package 25 adds a separate final fixup step
(`0026`) and applies normal conditions after display-on during wake (`0027`). That experimental recovery
kept a dark text console updating for 15 seconds before launching graphics.
It still booted black. Package 27 removes both the delay and timed fixup.
The panel still uses the calibrated 360-nit gamma; variable brightness and
temperature-dependent panel dimming are separate unfinished work.

Recovery now drains LVGL's own touch event queue while the screen is off
and consumes the complete wake gesture. Previously it disabled that input
reader and watched a second descriptor, leaving presses queued to activate
buttons after wake. `TABS3_TOUCH_TEST=1` starts an optional five-point check
using the same LVGL calibration as the menu; results go to stderr.
The five physical targets passed at (158,173), (1929,113), (1018,760),
(135,1407) and (1926,1399), for targets (128,128), (1919,128), (1024,768),
(128,1407) and (1919,1407). This confirms orientation and coarse targeting,
not stylus precision or multi-touch.

The real menu initially ignored taps on labels because decorative layout
boxes inherited LVGL's clickable flag. `box()` now clears it, with modal
backdrops explicitly opting back in. The user confirmed that tapping the
Check filesystem label now runs the check and displays a result. Every UI
build also runs native LVGL hit tests against all four tiles' icon, label,
description and centre. Package 25 failed fresh recovery boot and bright wake;
that failure triggered the controlled measurements below.

### Verified LP11 startup and full power wake (packages 27–28)

Evidence: [initialization/retention measurements](panel-lifecycle-measurements-20261011.json)
and [clock-order and physical validation](panel-lp11-validation-20261011.json).
With the fixup disabled in package 25, two boots read dual-link `02`,
compression `e5`, ELVSS `0f`, ACL `10`, averaging `00` and threshold `99`.
On a settled screen both LP and HS writes worked. Compression changes and
raw display off/on did not erase correctly written values. A bright wake
nevertheless stayed black while all checked settings remained correct.

An opt-in experiment (`0028`) deferred continuous clocks on both DSI hosts
until the panel's first command, after reset release and TCON_RDY. Two
boots then showed correct text from the beginning, with no fixup, and read
the intended `06/08/1b/12/05/7f`. A full supply-off/on cycle recovered the
bright recovery image. GPIO readback confirmed supply and reset low while
off. This establishes clock ordering as a corrective cause for the measured
startup failure; it does not decode every internal DDI latch or identify
an analogue protection trip.

Patch `0029` makes that clock order automatic only on `samsung,gts3llte`,
removes the timer/compression workaround and the retained-supply backlight
blanking interface, and serializes driver command lists with one mutex.
A TCON-ready timeout now fails preparation. Disable sends tear-off and
HS display-off, then unprepare lowers reset and cuts the supply, waiting
25 ms. Recovery and Debian use fbdev blanking to request the full lifecycle.
Recovery starts directly, without the old 15-second wait.

Physical checks on the package-27 recovery: correct colours at startup,
Check filesystem label selects the right action, five touch targets pass,
and short Power followed by one touch wakes a steady image without a menu
action. The controlled wake log contains only screen-off/screen-on; an
earlier less constrained trial included a second filesystem action and
was repeated to remove that ambiguity. Five new targets measured
(93,141), (1932,129), (1035,783), (146,1402), (1910,1402).

An immediate off/on test then exposed a separate package-27 race. The DSI
hosts remain powered for a 200 ms runtime-autosuspend delay, so a quick
wake skips `dsi_ctrl_config` and leaves continuous clocks running during
reset. The old bad register values returned (`02/e5/0f/10/00/99`).
Patch `0030`, installed in package 28, rearms LP11 on both hosts during
every bridge pre-enable, before panel preparation. Three immediate cycles
then returned all eight expected link/drive values, each with eight known
calibration controls and no frame kickoffs during the read window. The
clock log confirms both hosts were rearmed before reset release and only
started continuous clocks after TCON_RDY.

Package-28 boot/recovery writes were flushed and hash-verified. Recovery
build #13 booted and subsequently returned to Debian build #13, with
`tabs3-base` 0.1.6, screen service enabled/active and no failed services.
The first package-28 physical colour/wake question was unanswered. On a
subsequent fresh recovery boot the user confirmed correct colours, a steady
picture and stable Power/touch wake. The log contains one filesystem action;
the user clarified that this was a separate intentional tap after waking.
Thus the final run validates the visible wake, while the earlier package-27
controlled single-tap run supplies the unchanged-action-count evidence.
Recovery then returned to Debian on package 28 with the screen service active
and no failed units.
The earlier Debian charging readout was 65%, battery 22.3 C, charger board
26.8 C, health Good, automatic limits enabled, SDP 500 mA and net +33.7 mA
with the console lit.

At package 28, remaining work included variable brightness (completed below), low-temperature panel voltage tables,
error-line monitoring, longer endurance and system suspend. Occasional
pixel-clock RCG update warnings also exist in earlier boots. A full DRM
wake logs an `encoder is disabled` / `-EWOULDBLOCK` wait message; no visible
wake failure accompanied it, but its upstream DPU ordering needs review.
These are not claims of complete hardware support.

### Calibrated brightness (package 29)

Patch `0031` exposes normal levels 0..255, with level 86 as the default
(Samsung's 111-nit target). The range targets 2–360 nit. Runtime C calculates
all 65 normal gamma rows from this panel's factory MTP; each level sends
matching AID, ACL, ELVSS, CAPS and gamma under the panel command mutex.
The complete tuple is also applied before display-on after a full power cycle.
Calibration read or calculation failures now fail panel preparation rather
than displaying content with an uncalibrated fallback.

The gamma port matches independently compiled Samsung C and the Python
reference for all 65 rows with three calibration fixtures. Host tests cover
invalid calibration, command ordering, each transfer failure position and
requests made while the panel is off. Seven live levels returned the expected
ELVSS/CAPS/ACL values, with 35 known calibration controls and no frame
kickoffs during the read windows. A request made while off applied on wake;
an immediate off/on cycle preserved the selected level.

The user confirmed increasing brightness with correct colours in a
seven-step sweep, and steady, correctly coloured wakes at nominal 20 and
360 nit. Recovery build #14 then started at level 86; the user confirmed
correct colours, Power/touch wake and the filesystem button. Its log records
screen-off, screen-on, then the deliberate filesystem action. This combined
check does not independently count actions from an isolated waking tap.

Both installed images were flushed and hash-verified. The previous package-28
images and packages remain in the private rollback archive. This tablet's
old systemd-backlight binary value was migrated once to level 86.

Brightness 0 means the minimum lit setting; full screen-off still uses DRM
blanking. Manual `bl_power` blanking is unsupported. Nominal nits are stock
table targets, not meter measurements. Low-temperature ELVSS selection,
high-brightness mode, ESD recovery and longer endurance remain unimplemented
or unverified. See [the brightness report and evidence](panel-brightness-20261011.json).

## SoC temperature sensors and throttling (package 43)

The MSM8996 has two TSENS controllers (13 + 8 sensors). Until package 41
`CONFIG_QCOM_TSENS` was off, so the 14 thermal zones in `msm8996.dtsi` never
registered and nothing throttled the CPU or GPU. The stock kernel maps the
same registers (`0x4a8000` and `0x4ac000`, 8 KiB each, SROT and TM), so Linux
may access them; TSENS v2 reports calibrated deci-degrees directly.

Package 43 builds it as the module `qcom_tsens`, which loads at boot. Zones:
CPU passive 85 C and 90 C (cpufreq cooling), critical 110 C; GPU passive
90 C (devfreq cooling); the other sensors only notify at 90 C.

Measured on 2026-10-12: idle 35-37 C on the CPUs (PMIC die 26 C, battery
21 C). Four cores at full load reached 73 C in 75 s from cold and 86 C within
20 s when warm; throttling then held the CPUs at 88-91 C for 7 minutes (big
cluster 940-1824 MHz, little cluster 960-1593 MHz), and they cooled to 45 C
30 s after the load stopped. Figures are in
[the validation record](tsens-validation-20261012.json).

If TSENS ever misbehaves (for example, a false critical reading that powers
the tablet off), turn it off without reinstalling the kernel:
`echo 'blacklist qcom_tsens' | sudo tee /etc/modprobe.d/tabs3-no-tsens.conf`
and reboot. `tools/boot-check` reports the zones and fails without them.

### Board thermistors (package 67, 2026-10-14)

The stock tree reads seven thermistors on the PM8994 ADC under Qualcomm's
generic labels; Samsung's own nodes show which they are on this board.
Three were already in use (the skin zone on THM1 with Samsung's calibrated
table, the battery on THM2 and the charger on THM4 through the SM5705
drivers), so package 67 adds the rest as watch-only zones through
`generic-adc-thermal` (the VADC's own 100 k NTC and crystal tables, a
degree or two from the calibrated skin zone): `pa-thermal` (THM3, by the
LTE power amplifier, 28 C idle) and `xo-thermal` (the crystal's buffered
channel, 32 to 34 C). The seventh, `quiet_therm` on THM5, is not
populated: it read the table's floor, -40.0 C, and was left out. Twenty
zones now (`docs/kernel67-validation-20261014.json`).

## USB host with the owner's adapters (2026-10-15)

With the PC cable out, `tabs3-usb-host host` put the port in host mode
(VBUS from the SM5705 boost) and the owner's Ethernet adapter, a Realtek
RTL8156 2.5G part (`0bda:8156`, `r8152`, high speed on this USB 2.0 host),
came up with a DHCP address from the router in 11 s and became the default
route; a 60 MB download from the PC ran at 16.9 MB/s through it against
11.8 MB/s through Wi-Fi, no errors. The battery supplied 800 to 880 mA
with traffic.

The owner's four-port hub (`14cd:8601`, USB 2.0) enumerates with its
billboard device (`343c:0000`, "USB Type-C Digital AV Adapter"): the hub
also carries an HDMI output that needs the DisplayPort alternate mode,
which the s2mm005 USB-C controller would have to negotiate (the large
USB-C video item). With a wall charger in the hub's Type-C power input the
tablet's charger input stayed offline over a five-minute recording and the
tablet kept powering the hub from its battery at 520 to 880 mA: a hub
sends power upstream only after a PD power-role negotiation, which the
same controller would have to do. Host mode therefore runs on the battery
alone; `tabs3-usb-host device` returns the port to USB networking and
charging. The battery keeper treats host mode as offline (no forced
discharge then).

## USB-C controller: a hub that charges the tablet while it hosts (2026-10-15)

The owner's hub (four USB-A ports, HDMI, a Type-C power input) led to the
port's controller, a Samsung S2MM005: stock `usbpd-s2mm005@33` on BLSP1
QUP5 (`i2c@7579000`, TLMM 83/84, 100 kHz, interrupt TLMM 73), a
microcontroller that runs the Type-C and Power Delivery state machines in
its own firmware. Mainline's `msm8996.dtsi` has no node for that QUP;
`usbpd.dtsi` adds it (package 69) and the chip answers: firmware boot 6,
main 0xd5, 16-bit registers (function state at 0x20, message flags in
the 48-byte block at 0x30, low-power state at 0x60, the partner's source
capabilities at 0x0260, a command word at 0x10; `research/.../NOTES.md`
section 15 has the decoding, from Samsung's driver).

What the chip showed, read from userspace first: with the PC cable it sits
attached as sink and device in its error-recovery state (a PC port is not
a PD source). With the hub and its wall charger attached in host mode
(the tablet boosting VBUS), the chip went to "sink, waiting for
capabilities" within four seconds: the hub asked for a power-role swap
and the chip accepted, but nobody cut the tablet's VBUS in time, the swap
failed and the port went through error recovery, after which the hub
attached as the source: the tablet charged from it and the chip reported
"sink, host", yet the hub never presented its USB data lines.

Patch `0042` (package 70) is the driver: it reads the state on the
interrupt and on a poll, logs changes, shows `state`, `version` and
`source_capabilities` in sysfs, and tells the SM5705 charger through
`sm5705_partner_supply()` when a partner takes over VBUS (the
source-to-sink transition, or the partner reported as the source) and
when the tablet is to source again. On the RAM boot of package 70 the
swap went through by itself: 80 ms after the tablet's VBUS the hub took
the source role, the driver dropped the boost ("the partner supplies the
port"), the hub delivered a 5 V 3 A contract and a data-role swap made
the tablet the host, with the charger online. The hub still did not
enumerate, and that turned out to be the SM5705's MUIC: when the boost
goes off the charger driver restored the MUIC's automatic switching,
whose charger detection classifies a hub as unknown and leaves the D+/D-
switch open (register 0x13 read 0x00). Forcing the switch to USB by hand
made the hub enumerate at once, charging and all. The second version of
the patch (package 71) keeps D+/D- on USB whenever the host role is held,
whoever supplies VBUS, releases the switch when the host role ends, and
takes the partner's contract current (3 A here, capped at the charger's
1.5 A) as the input limit instead of the 500 mA of an unknown source;
`tabs3-usb-host host` (`tabs3-base` 0.1.28) accepts a port a partner
already powers when the controller reports the tablet as host.

Package 71 was flashed on 2026-10-15 at 12:12 and tested with the hub
from disk (`docs/kernel71-validation-20261015.json`). Plugged in cold,
the hub waits: the controller reports the tablet as source and host in
"source wait new capabilities", the hub does not answer until it sees
VBUS. `tabs3-usb-host host` turns the boost on, and from there everything
is the controller's and the driver's: 19 ms later the port detaches, at
69 ms it is a sink waiting for capabilities, at 77 ms the charger drops
the boost ("the partner supplies the port", 3 A), at 276 ms the contract
is in place (5 V 3 A, dual-role power and data), at 690 ms the data-role
swap makes the tablet the host, and at 1.2 s the hub and its billboard
device enumerate by themselves. The charger reports online with the
1.5 A limit and 1.0 to 1.1 A went into the battery, until the keeper put
its forced descent back a minute later (the battery was at 94 %). A
reboot with the hub attached keeps the contract: the driver probes into
"attached, sink, host" and the tablet charges at once, but the USB role
was the boot default (device) until the tool was run.

Package 72 (the third version of patch 0042, flashed the same day at
12:53) closes that: `usbpd.dtsi` describes the port as a
`usb-c-connector` under the controller, its high-speed port wired to a
port under the dwc3 node, and the driver takes the USB role switch from
that graph and sets it from the controller's data role on every change
and at probe: host when the tablet is the downstream-facing port, device
otherwise. The hub is now hosted without a command: plugged in, the
controller attaches as a sink (the hub sources at once), the contract is
in place at 250 ms, the data-role swap comes at 670 ms, the driver sets
the host role 4 ms later, the charger sees the partner's VBUS and skips
the boost, and the hub is found at 1.3 s with the charger online at the
1.5 A limit. A reboot with the hub attached probes straight into "sink,
host" and the hub is found at 9.4 s (`docs/kernel72-validation-20261015.json`).
With the PC cable the role stays device and the gadget comes up as
before. The charger also refuses the boost below 15 %, the floor of its
forced discharge. `tabs3-usb-host` remains for status and overrides.

One lesson from the cable swaps on package 71: a cable detected while
the MUIC's data switch is held (the PC cable arriving while the port was
still in host mode after the hub left) reads as an unknown source, and
the switch stays open after the hold ends until the next detection, so
neither Debian's gadget, lk2nd's fastboot nor the recovery is visible to
the PC until the cable is plugged again (the MUIC detects on VBUS).
Package 72 drops the role to device as a partner leaves, so the next
cable is detected with the switch released.

The automatic role then met the chip's blips (packages 74 to 76,
`docs/kernel76-validation-20261015.json`). As the tablet's own VBUS
comes on, the controller reports a detach for a few tens of
milliseconds and then, for about 100 ms, "attached, sink, device" with
its policy engine still detached. The first version acted on both: the
role dropped and the boost went off on the blip, the partner
re-attached, and a hub or an adapter looped four times a second until
the driver was unbound. Package 74 lets the host role go only after a
second of not being host; package 75 ignores a sink attach whose policy
state is still detached (a partner that supplies reaches "sink wait for
capabilities" within 70 ms); package 76 keeps those blips out of the log
and of the fast poll. With that, the adapter is hosted and keeps its
address, and a hub with its charger settled takes over at the first try
(sourced on attach, data-role swap 410 ms later, hub found under a
second). Right after cable moves the same hub needed twelve tries over
12 s before it could source: its charger side was not ready, the tablet
followed the chip correctly each time. With a partner that speaks no PD
the chip cycles its own state every half second while the tablet
sources (source, a short detach, a sink attach, source again); the data
path does not notice, and why it does so is an open question, probably
a dual-role port's Try.SNK seeing the tablet's own VBUS.

Two more findings came from the PC cable after a hub session (packages
80 and `tabs3-base` 0.1.31, `docs/kernel80-validation-20261015.json`).
The SM5705's automatic switching leaves D+/D- open for a PC: Samsung's
MUIC driver always switches by hand on a USB attach (manual mode, D+/D-
to USB) and back to automatic with the lines open on detach, and the
charger driver now does the same while the port is not a host (patch
0045). And since package 77 the controller has its USB 3 PHY, so as a
gadget it tries USB 3 first; after a host session its USB 3 link stayed
in Rx.Detect and it never fell back to USB 2, so the PC saw nothing even
with the lines routed. The USB networking gadget is now USB 2 only
(`max_speed` high-speed in `tabs3-usb-gadget`); it does not need USB 3.
After both, the PC found the tablet one second after the cable went in,
straight after a hub session.

## Rescue through lk2nd fastboot (2026-10-13)

Holding Volume Down while the tablet restarts (a forced restart with Power +
Volume Down works) stops in lk2nd fastboot: USB `18d1:d00d`, `fastboot getvar
product` reports `lk2nd-msm8996`. From the PC, `fastboot boot IMAGE` with the
plain Debian boot image (the combined image without its first 4 MiB of lk2nd,
for example `private/images/package44/tabs3-installed-gpu.img`) runs that
kernel from RAM; the boot partition is untouched, so a failed test needs only
a restart. Package 44 was tested this way before it was written to disk.

This also ended the 2026-10-12 lockout: installing package 44 from the running
6.19.5 system replaced that kernel's `/lib/modules` and stopped at `depmod`
before the boot partition was written; a reboot then ran 6.19.5 with only the
6.18 modules, `tabs3-usb-gadget` failed on `modprobe` and Wi-Fi had no driver.
A RAM boot of the 6.18 image matched the installed modules, after which the
boot partition was written from that system. Since then `tabs3-base` 0.1.9
keeps USB SSH up when the modules do not match, and the installers run
`depmod` for the kernel they install. When a package changes the kernel
release, write the matching boot image in the same step.

The recovered camera/S Pen/regulator research is preserved under
[`research/platform-20261013`](../research/platform-20261013/README.md).
Those drafts are not installed hardware support.

## Full-device qualification, 2026-11-05

The owner requires every hardware function end to end. The current matrix and
work order remain in [todo.md](../todo.md#hardware-functions); dashboard-only
operation does not close unsupported peripheral paths. Acceptance requires a
real consumer, repeat use, relevant power/sleep transitions, and recovery from
errors. A probe message, device node, successful compilation or empty deferred
probe list is insufficient.

The live baseline is kernel package 80 (`6.18.56-gts3l1`, build 26), base
0.1.35 and dashboard 0.1.9. USB and Wi-Fi SSH work. All three remote processors
run and systemd has no failed units. The PC cable advertises a 500 mA input
limit; it is not equivalent to a wall charger or a powered hub. AMOLED
protection remains enabled. Emulation is retired.

### Audio stream lifecycle

Two source defects were isolated:

- Base patch 0007 imports `a354f030dbce` but omitted its upstream follow-up
  [`8a066a81ee0c`](https://github.com/torvalds/linux/commit/8a066a81ee0c1b6cdbd81393536c3b2d19ccef25).
  READ/WRITE/EOS basic responses still overwrite `ac->result` and wake the
  synchronous command waiter. A close acknowledgment can therefore be lost
  before the waiting thread observes it. Local patch 0046 imports the exact
  upstream correction, dropping these responses before updating command state.
- Local 0018 tests `!ret` after `q6asm_cmd_nowait(CMD_PAUSE)`. The function
  returns `apr_send_pkt()` directly, whose success value is the positive packet
  length. The intended capture FLUSH is skipped. Patch 0047 accepts nonnegative
  success and retains negative error propagation and playback EOS behavior.

`tests/test_q6asm_lifecycle.py` compiles the actual callback/trigger code with
a simulated transport. The original code reproduces both failures; the fixed
code preserves CLOSE across late replies, ignores late replies before CLOSE,
still handles control errors, sends FLUSH after successful PAUSE, and does not
send it after a failed PAUSE. It does not model the DSP or prove acoustic input.

The separately built package `6.18.56-81~audio1` and checked RAM/disk images
are in `private/releases/20261105-drivers81/`. Kernel configuration, board DTB,
bootloader and command line match the package-80 baseline. The initramfs is the
already-tested boot-fsck candidate. **Nothing has been flashed or rebooted.**
The q6asm changes are modules: the matching package must accompany a candidate
boot, and package 80 must remain available for module rollback. Actual repeated
capture close/reopen, concurrent playback and sound-wake validation remain open.

### Video codec qualification

Package-80 H.264 encoding rejected buffer setup with EINVAL. A scoped function
trace reached the fifth property in `venc_set_properties()`: the 8x8-transform
control. The HFI packet serializer handled it only for version 4, while MSM8996
uses version 3. Patch 0048 imports Vladimir Lypak's
[`17b07fbf0a7d`](https://github.com/lineage-on-mainline/android_kernel_xiaomi_msm8953/commit/17b07fbf0a7d3afecbda73a5d48c21dd16fb240c)
to put that existing serializer in the version-3 path; later versions inherit
it. The host test compiles the actual packet implementation and checks both
enabled/disabled payloads, packet sizes, version fallbacks and invalid inputs.

With the candidate core module loaded temporarily, H.264 encoding starts and
emits three valid Baseline frames (15,637 bytes), then the firmware reports a
fatal error in `vbuffer.c:1219`. Pacing input at 30 fps fails before the intended
60-frame stream ends, so this cannot be attributed only to end-of-stream.
Original-module VP8 encoding also crashes with the same firmware signature.
This failure predates patch 0048; the setup-only candidate failed qualification.
The original modules were restored, verified by matching the loaded build ID.
The experimental `81~drivers1` package must not be promoted.

Further isolation found two separate failures. GStreamer filesink retains
compressed output and allocates a fifth capture buffer after STREAMON. The
driver submitted that address without registering it, immediately preceding
the firmware fatal error. Registering it during streaming was also rejected
by firmware with incorrect-state error 0x1006; that experimental change was
discarded. Final patch 0050 returns EBUSY for HFI-v3 encoder capture-pool
growth while streaming. Larger pools may be allocated before STREAMON.
GStreamer then copies retained compressed output and recycles registered
buffers. Hardware encoding stays enabled. Input allocation and later HFI
generations are unchanged.

With a non-retaining sink the original encoder instead reached drain and
rejected the synthetic address `0xdeadb000` with error 0x1001. Patch 0049
imports the encoder portion of Vladimir Lypak's
[`1c6674b9e45d`](https://github.com/lineage-on-mainline/android_kernel_xiaomi_msm8953/commit/1c6674b9e45d573ff12fcdfe45d9a9e13c8ec650):
HFI v3 uses zero address and zero length for encoder EOS. Nonempty buffers
still require an address; decoder patch 0033 remains unchanged.

The final `81~drivers2` modules passed temporary hardware tests with no new
kernel errors: H.264 60 frames at 320x240, 300 at 640x480, 60 at 1920x1080,
three additional 60-frame 640x480 open/close cycles, VP8 60 frames to a raw
file and 60 into Matroska, plus two 60-frame hardware decode runs. Every
pipeline reached clean EOS. Independent host decoding confirmed all expected
frames in the six H.264 files and VP8 container, with no errors; the VP8
container duration is 2.000 seconds. A decoded midpoint shows the expected
SMPTE pattern. The VP8 and lower-resolution H.264 file tests exercised the
refused late allocation; the 1080p run did not need to grow its pool.

All three loaded module build IDs were checked against the test artifacts;
the packaged modules match those IDs. Original package-80 modules were
restored afterward. The complete `81~drivers2` package and boot images are in
`private/releases/20261105-drivers81c/`, **not installed or flashed**. These
bounded tests fix the reproduced encoder failures, but do not establish all
profiles/codecs, sustained throughput, camera-to-encoder operation or endurance.

After recovery, the original hardware decoder processed all 60 synthetic
640x480 H.264 Baseline frames and delivered clean EOS with exit status 0.
No camera, microphone or display capture was used. This establishes that
bounded decode path, not every format, resolution, concurrent stream or long
run. Evidence: [video validation](driver-video-validation-20261105.json).

The production checker now treats recovered video-firmware crashes as faults.
The health service also reads PID 1's mount information: its private systemd
read-only sandbox must not be mistaken for a read-only Debian root. Base 0.1.35
was installed and verified through the actual hardened service, with schema 3,
root writable and no notices. Earlier false storage alerts were retained.

### Live data paths

`tools/platform/check-data-paths.py --storage` ran on the tablet. Each of root
and microSD passed a 32 MiB random temporary-file write, fsync and SHA-256
readback after a cache-eviction request. No raw device write or user-file
modification was performed. These bounded checks are not full-media scans,
direct-I/O performance measurements or power-loss tests. The four SLPI sensors
(accelerometer, gyro, magnetometer and light) and SX9310 grip sensor each
returned numeric channel values in three samples. Physical response and
calibration are separate checks. Evidence: [data-path report](driver-data-paths-20261105.json).

### Inventory corrections and remaining hardware limits

The earlier table understated Bluetooth: the owner already paired an Xbox
controller and confirmed input, navigation and wake. It also overstated USB
power reliability: powered-hub charging passed earlier, then failed to take
over VBUS on later insertions. Both power sources and transitions still need
qualification. USB 3 PHY/redriver support is already enabled, but no known
SuperSpeed partner has established a 5000M link in both orientations.

[Samsung's SM-T825 specifications](https://www.samsung.com/es/business/tablets/galaxy-tab-s/galaxy-tab-s3-9-7-t825-sm-t825nzkaphe/)
list USB 3.1, ANT+, fingerprint, an RGB light sensor and the POGO keyboard
accessory, and explicitly list no MHL or NFC. ANT+ and RGB channels were missing
from the previous qualification scope. Native wired display output cannot be
inferred from shared SoC HDMI nodes; the actual board path remains unproven.
The absence of MHL alone does not establish the state of every alternative
video protocol.

QCE remains disabled. The historical BAM probe error was `num-channels
unspecified in dt`; upstream SoC DMA descriptors alone do not prove the
tablet's secure pipe assignment. The stock tree uses a shared crypto block
at 0x660000, different pipe pairs for qcrypto/qcedev and the same BAM at
0x644000. Mainline's 0x67a000 window and pipes 6/7 require reconciliation with
that ownership model before enabling DMA. No register/pipe counts were guessed.
The separate `qcom,prng-ee` compatible deliberately does not register trusted
hardware entropy in this kernel's `qcom-rng.c`; changing it to `qcom,trng`
would be incorrect. Linux's normal random pool and CPU crypto still operate.

LTE data needs the IPA 2.5 path, fingerprint needs a supported secure transport
and userspace matching, GNSS needs real indications and a fix, and keyboard,
headset, SIM-dependent services and ANT+ need their corresponding hardware.
These remain requested work rather than exclusions from the release target.
