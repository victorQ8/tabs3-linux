> Historical development notes. For current installation and hardware status, start with [README.md](README.md). Earlier entries may describe limitations fixed later.

# tabS3 — Debian for Galaxy Tab S3 LTE

An experimental Debian 13 (`trixie`, `arm64`) derivative for the Galaxy Tab S3
LTE. The connected tablet is verified as **SM-T825**, originally running Android
9 with bootloader `T825JXU3CTE1`. The target codename is `gts3llte`; SoC ID is
246, revision 3.1. Android reported an unlocked bootloader.

## Current scope

The primary workload is an **always-on Debian dashboard appliance**, with
**all tablet hardware drivers working end to end** as the acceptance target.
As of 2026-11-05, kernel package `6.18.56-80`, `tabs3-base` 0.1.35 and dashboard
0.1.9 are installed. Production qualification remains open; the current
[release gates, backups and rollback procedure](docs/production-readiness.md)
record the tested foundation and the pending boot/power/soak checks.
Emulation is retired.

`tabs3-base`
provides `sudo tabs3-server-enable`: console boot, no system suspend,
screen timeout, desktop audio disabled and a conservative CPU ceiling.
It also selects SSH key authentication, Debian security updates without
automatic reboots (custom hardware packages excluded), and an ext4 error
policy that remounts the validated root filesystem read-only. A one-minute
health recorder retains seven daily logs under `/var/log/tabs3-server/`;
it observes and logs, without changing charging limits or shutting down.
Factory Wi-Fi identity is restored from this tablet's read-only EFS and was
verified across reboot. See the [server/platform audit](docs/server-platform-audit-20261013.md)
for the earlier measurements. The [platform continuation](docs/platform-handoff-20261013.md)
records the package-56 reset isolation, RTC workaround, HS400 tests, recovered
sensor drivers and CPU-idle/watchdog interaction. Earlier package 61/base
0.1.19 passed RAM, storage, memory, thermal and watchdog tests. CPU0 stays in WFI for watchdog reliability; three cores use
deeper idle. Full Debian uses HS400 at 192 MHz; recovery retains its old cap.
Continuous-service qualification is unfinished.

This repository builds Debian userspace, Linux `6.18.56-gts3l1` (kernel.org 6.18
LTS; packages up to 41 used 6.19.5), an experimental
LTE device tree, a Samsung-packed lk2nd bootloader and a RAM-only diagnostic
boot image. **Debian 13 now boots directly from this SM-T825's internal storage.**
USB/Wi-Fi SSH, sudo, eMMC access and a 28 GiB root filesystem spanning
userdata and Android system are verified. Normal Debian uses kernel package
`6.18.56-80`; recovery retains the verified display-only package `6.19.5-29`.
The installed display stack provides a clean console
from the first frame, correct recovery colours, and full panel power-off/wake.
The clock-order fix removes the five-second garbled startup and timed fixup.
Three immediate off/on cycles also passed register checks after fixing the
case where the DSI hosts have not yet powered down.
See the [measured panel results](docs/panel-lp11-validation-20261011.json).
The rootfs tarball alone cannot boot it.

Normal software reboot is now verified: `systemctl reboot` returned to Debian
and USB SSH in about 16 seconds with a new boot ID and no failed services.
The initial kernel halted after firmware's PSCI reset call returned. Package
`linux-tabs3_6.19.5-3_arm64.deb` adds the stock-address PS_HOLD reset controller
to the device tree, enabling the existing kernel driver's reset fallback.
Battery/charger reporting, calibrated thermistor readings, conservative
temperature cutoffs and physical charge inhibition/resumption are verified
in the installed recovery. They are also included in normal Debian.
The wall-charger test passed at a 1.5 A input limit, delivering about
1.2 A into the battery. Ordinary PC ports remain capped at 500 mA. See the
[hardware record](docs/hardware-sm-t825.md#battery-and-charging-sm5705)
for thresholds, test evidence and remaining limitations.

The diagnostic image disables internal storage, exposes public-key SSH over
USB, and requests a reboot after five minutes. See
[the hardware-test and restore plan](docs/first-boot.md) before changing the
tablet's boot partition. The first test temporarily installs lk2nd into boot
and restores the saved Android boot image afterward; that restore was verified.
The storage test also successfully rebooted from Linux into TWRP with Home +
Volume Up held. The first timed reboot was inconclusive. TWRP has since been
replaced by the project's Linux recovery; do not format userdata alone now
that root spans two partitions. The installed image has no five-minute reboot
timer.

Wi-Fi and Bluetooth scanning work. Recovery's Check filesystem touch action
and five-point touch alignment passed physical checks. Power/touch wake
keeps correct colours and consumes the waking tap; the 3-second Power hold
boots Debian. Brightness now uses Samsung's complete calibrated dimming
tables, with a lower default. Adreno 530 hardware rendering and Phosh are now
installed; see the [GPU/desktop measurements](docs/gpu-desktop-20261011.json)
for test results and remaining qualification. The repeatable `phoc` GPU
translation faults were a kernel bug: closing a client's buffer unmapped it for
the compositor too, since Adreno 5xx shares one GPU address space. The first
fix (package 32) prevented that early removal but retained old buffers:
about 1.93 GB remained allocated after the desktop stopped. Package
`6.19.5-33` adds cleanup at the final external reference, after
outstanding GPU work completes; both are now kernel patch `0014`. In two
12-cycle editor sessions, no GPU
faults were logged and memory returned to the original 13 MB baseline after
each session ended. Physical confirmation and a longer soak remain before
the desktop is the default.
Package `6.19.5-34` and later add the hardware buttons (Home, Volume,
and the Recent/Back touch keys). Package `6.19.5-39` with `tabs3-desktop`
0.1.8 adds headphone and microphone audio through the audio DSP, using the
tablet's own signed firmware; the four speakers' amplifiers are not
supported yet. The modem also boots: rmtfs serves its EFS read-only, so the
IMEI/calibration partitions are never written, and `sudo tabs3-modem-status`
reports SIM, network and signal. Mobile data is not possible yet: the
MSM8996 data engine (IPA v2.5) has no mainline driver, so ModemManager does
not set up the modem. See `docs/audio-modem-20261011.json`.
Package `6.19.5-40` adds the microSD slot and USB host mode for USB-C
Ethernet adapters (`sudo tabs3-usb-host host`, on battery only at the
time; since kernel package 72 the USB-C controller's driver sets the role
itself and a hub with its own charger powers the tablet while it hosts,
see `docs/hardware-sm-t825.md`). Package `6.19.5-41` is the same
kernel built from the cleaned patch stack described in `kernel/PATCHES.md`:
bring-up instruments are removed, and the display clock fix and Wi-Fi PHY
tuning now apply only to this tablet. Package 41 is installed and passed the
remote checks in `docs/kernel41-validation-20261012.json`; the microSD, USB
Ethernet and on-screen checks need someone at the tablet.
Package `6.19.5-43` enables the SoC temperature sensors: until then nothing
throttled the CPU or GPU. Under sustained full load the CPUs now hold at
88-91 C instead of running unthrottled (`docs/hardware-sm-t825.md`).
Package `6.18.56-44` moves to kernel.org's 6.18 LTS series (security fixes
until about December 2028) and passed the same checks after a RAM boot test
(`docs/kernel44-validation-20261013.json`).
Package `6.18.56-45` runs the microSD slot in High Speed mode (3.3 V, about
22 MB/s): UHS-I fails after the 1.8 V switch. Package `6.18.56-46` retries a
card that gets stuck during hot insertion; if a card still does not appear,
reinsert it (`docs/sdcard-validation-20261013.json`).
Package `6.18.56-51` drives the four speakers (RT5508 amplifiers on primary
TDM), and `tabs3-desktop` 0.1.10 adds them to the audio profile as the
default output, in stereo for portrait use and with a -10 dB amplifier
ceiling (`docs/speakers-validation-20261013.json`).
Package `6.18.56-55` with `tabs3-sensors` 0.1.0 adds automatic screen
rotation: the sensor DSP runs with Samsung's own sensor registry, which
`tools/sensor-registry/` rebuilds from your tablet's Android backup (it is
Samsung-derived and never shipped), and iio-sensor-proxy gets the
accelerometer's mounting from a udev rule
(`docs/rotation-validation-20261013.json`).
`tabs3-dashboard` 0.1.0 draws the server's state (load, temperatures,
battery, memory, storage, network, firmware) straight into the panel's
framebuffer and wakes the screen when the light sensor or the
accelerometer notice someone at the tablet (`docs/dashboard.md`; not yet
checked on the hardware).
Panel error-line recovery, mobile data and reliable suspend remain
unfinished.

## Screen brightness

The panel exposes levels `0..255` through
`/sys/class/backlight/ams968hh01/brightness`. Level `86`, the default,
targets 111 nit; the full range targets 2–360 nit. These are Samsung's
table values, not measurements with a luminance meter. Each update sends
matching gamma, AID, ACL, ELVSS and CAPS settings using this panel's factory
calibration. High-brightness mode and cold-temperature voltage selection
are not implemented.

For example, restore the default with:

```sh
echo 86 | sudo tee /sys/class/backlight/ams968hh01/brightness
```

Level `0` is the minimum lit setting. Use the Power key or DRM/fbdev
blanking to turn the screen off completely; manual `bl_power` blanking is
unsupported. Requests made while the panel is off apply before it lights
on the next wake. The existing systemd service saves and restores brightness.
When upgrading from the old binary backlight interface, this tablet's saved
value was migrated to `86` once.

See the [brightness implementation and measurements](docs/panel-brightness-20261011.json).

## GPU and Phosh desktop

This optional desktop work predates the server decision. The installed server
profile disables graphical startup and desktop audio; the instructions below
are historical/optional, not the current server setup path.

The `gpu` boot variant adds Adreno 530 and its real PM8004 S2 supply to the
display tree. The MMCC `vdd-gfx-supply` connection is necessary: enabling the
GPU without it left the GX power domain off. The rail retains its boot voltage
(1000 mV measured); stock CPR voltage tuning has not been ported. The separate
recovery image does not depend on GPU firmware.

Before first boot with this variant, install Debian's `firmware-qcom-soc` on
the tablet and run `tools/install-gpu-firmware` there with sudo. The latter
copies this tablet's signed ZAP files from its read-only `apnhlos` partition.
For audio and the modem, also run `tools/install-dsp-firmware` (installed by
`tabs3-base` as `/usr/libexec/tabs3-install-dsp-firmware`): it copies the
signed ADSP, MBA and modem images from the read-only `modem` partition.
Those vendor binaries remain private and are not included in Git.

Build the kernel normally, then pack the GPU variant for this tablet's
existing extended root:

```sh
bash scripts/build-kernel.sh
bash scripts/build-kernel-package.sh
bash scripts/build-initramfs.sh private/id_ed25519.pub
bash scripts/pack-images.sh --mode installed --variant gpu \
    --root-uuid ROOTFS_UUID --extend-root system \
    --donor private/backups/20261010T094140Z/boot.img
bash scripts/build-desktop-package.sh
```

`ROOTFS_UUID` must be the installed filesystem's UUID. The GPU image is
`private/images/tabs3-internal-gpu-boot.img`. Installing a kernel `.deb` does
not flash it: use the same board, partition, backup and readback checks as
for the display image. Do not recreate or overwrite the existing rootfs.

After the GPU image is booted, copy the built desktop `.deb` and
`tools/install-desktop` to the tablet, then run:

```sh
sudo sh ./install-desktop ./tabs3-desktop_VERSION_all.deb
```

The installer preserves IWD profiles privately before installing dependencies.
It installs the Mesa libraries from official `trixie-backports`
(`26.1.6-1~bpo13+1`). Use kernel package `6.19.5-33` or later to include
both shared-buffer lifetime fixes. Other packages remain on trixie. Activation
restarts the graphical login service, so save any open documents first.
It migrates personal WPA-PSK networks to persistent NetworkManager profiles,
keeps IWD as the Wi-Fi backend, and leaves USB networking with systemd-networkd.
Enterprise Wi-Fi needs separate configuration. It starts the Phrog login screen
for a Phosh test session. Console boot is the current server default.
Run activation over USB SSH because
restarting IWD interrupts Wi-Fi SSH. Log in as `dev` using the tablet password. The keyboard
icon on the number pad exposes the alphabetic on-screen keyboard.

After a console boot, start another test session with
`sudo systemctl start greetd`. A correct-looking picture does not rule out
GPU faults: check `sudo dmesg | grep 'gpu fault'`, since the service-failure
fallback does not detect them. Qualification also checks buffer cleanup:
fault-free rendering alone did not reveal package 32's memory retention.

The desktop package sets 2x display scaling and libinput's touch transform
`x=y, y=1-x`, matching the physically checked recovery orientation. Phosh owns
screen blanking while it runs. Automatic whole-system suspend is disabled
pending hardware validation. GTK4 uses its OpenGL renderer (`ngl` in GTK 4.18),
since Adreno 530 does not have Mesa Turnip Vulkan support.

To return to the console over SSH:

```sh
sudo systemctl stop greetd phosh
sudo systemctl start tabs3-screen getty@tty1
sudo chvt 1
```

For a persistent console default, also disable `greetd` and set
`multi-user.target` as the default. The console rootfs builder remains separate;
it does not silently include or enable the optional desktop.

## Source baseline

- [Device port](https://github.com/wh1ter0z3/gts3lwifi-mainline), pinned as a
  submodule at `97e9c58c29bc34c4776ca47ee147226464120cda`.
- Linux [6.18.56](https://cdn.kernel.org/pub/linux/kernel/v6.x/) from kernel.org
  (longterm); the archive SHA-512 is recorded in `config/sources.json` and
  checked before extraction. `kernel/base/` carries four commits from the
  [msm8996-mainline](https://gitlab.com/msm8996-mainline/linux) community tree
  and seven upstream backports (`kernel/PATCHES.md`). Packages up to 41 used
  that community tree's `v6.19.5-msm8996` tag.
- The three device-port patches are applied without fuzzy matching.
- The upstream Linux board DTS describes **SM-T820 / APQ8096**. Our tracked
  `kernel/msm8996-samsung-gts3llte.dts` derives from it with verified LTE IDs,
  VDD_MX USB power-domain voting, additional stock memory reservations and
  conservative GPIO/debug/storage exclusions. Compilation and USB SSH boot
  are verified; idle power and other hardware remain untested. Full DT schema
  checking is pending.
- [lk2nd](https://github.com/msm8916-mainline/lk2nd) is pinned as a submodule at
  `8b46487c4c76776c4f2f61468d44a74c69e6b9ea`. Its local LTE entry uses this
  tablet's rev05 IDs. Both builds reserve 4 MiB. The diagnostic build stops in
  fastboot; `--autoboot` builds the variant used for persistent Debian boot.
- Debian container base is pinned by digest. Debian package repositories are
  currently live; exact installed versions are recorded with each build.
  This is a repeatable build procedure, not a bit-for-bit reproducible release.
- Samsung-derived panel dimming code, generated tables, fixtures and tools
  carry their own `GPL-2.0-only` notices; the repository's MIT license does
  not override those notices. The license text is in
  [LICENSES/GPL-2.0-only.txt](LICENSES/GPL-2.0-only.txt).

## Inspect the tablet

Power the tablet on, unlock Android, enable USB debugging in Developer options,
and accept this PC's debugging prompt. If Developer options is hidden, tap
Build number seven times under Settings → About tablet → Software information.
Use a data-capable USB cable.

```sh
python3 scripts/inspect-device.py --output private/device-report.json
```

The inspector reads selected model/software properties and battery status.
It ignores unrelated phones, stops if more than one candidate is present, and
does not record the USB serial, IMEI, user files or a full property dump.

With existing root access, preserve current boot/recovery and the live DTB:

```sh
python3 scripts/backup-device.py
python3 scripts/backup-device.py --calibration-only
```

Grant Shell access in the tablet's existing root manager if prompted. This
script only reads the tablet; it checks partition sizes, image headers and
device/local SHA-256 agreement. Backups are private and ignored by Git. They
are current rooted-device images, not necessarily pristine stock images.
The second command separately preserves sensitive EFS, modemst1/2 and persist
partitions. Neither command backs up user data. Never publish calibration files.

## Build on the workstation

Requires Docker, Git, Python 3.11+, `patch`, and OpenSSH client tools. Builds run
in a Debian container. Host GPU drivers, CUDA and package versions are not
changed. Kernel preparation currently occupies about 2 GiB in `work/`; builds
also use Docker storage and write release artifacts under `artifacts/`.

```sh
git submodule update --init
bash scripts/build-env.sh
python3 scripts/prepare-kernel.py
bash scripts/check-kernel-baseline.sh
bash scripts/build-package.sh
```

The baseline check compiles the **Wi-Fi reference DTB only**. Build our LTE
kernel and bootloader with:

```sh
bash scripts/build-kernel.sh
bash scripts/build-kernel-package.sh
bash scripts/build-lk2nd.sh
```

Kernel objects and modules use the Docker volume `tabs3-kernel-build`; lk2nd
uses `tabs3-lk2nd-build`. Builds copy artifacts out without exposing USB
devices to containers. The Debian kernel package copies kernel/modules/DTB
files only; it has no flashing or boot-image update hooks.

For the ARM64 rootfs, choose a console login password for `dev` and supply
an SSH **public** key:

```sh
bash scripts/set-dev-password.sh
bash scripts/build-rootfs.sh private/id_ed25519.pub
```

Only a SHA-512 crypt hash of the password is kept, in
`private/dev-password.hash`. It is for logging in on the tablet's screen;
SSH stays key-only.

A development key was generated locally in `private/`; keep its private half
on this PC. For a fresh clone, generate a separate key with `ssh-keygen`, or
pass your existing public `.pub` file. Do not publish a personalized rootfs as
a general release without replacing its authorized key.

Once the rootfs and kernel exist, build the diagnostic image using a verified
backup directory from this exact SM-T825:

```sh
bash scripts/build-initramfs.sh private/id_ed25519.pub
bash scripts/pack-images.sh --donor private/backups/20261010T094140Z/boot.img
```

Replace the donor path for another backup. Packing validates its saved hash,
SoC/PMIC IDs and board revision. This tablet's boot image uses a legacy QCDT
area after the ramdisk; its four stock DTBs are preserved when creating the
Samsung wrapper. Images and hashes go to `private/images/`. Those files
include donor-derived material or a personalized SSH key and remain private.

The initramfs builder tests an actual ARM64 SSH login under QEMU with a
temporary test key. It briefly registers a dedicated ARM64 binfmt handler,
removes it on exit, and removes test keys before packaging. Diagnostic SSH
uses `root@172.16.42.2`, public-key authentication only. This is separate
from the full rootfs's `dev` account.

The rootfs build temporarily registers one task-specific ARM64 QEMU handler
in `binfmt_misc`, removing it on exit. Its container needs `SYS_ADMIN` for
bootstrap mounts, but receives no tablet devices or Docker socket. Existing
host handlers are preserved. A hard power loss during a build may require
removing a leftover `tabs3-aarch64-*` entry from `binfmt_misc`.

Outputs:

- `artifacts/tabs3-base_VERSION_all.deb`: USB networking, SSH, Wi-Fi/Bluetooth
  setup, screen sleep and power-key defaults.
- `artifacts/tabs3-trixie-arm64-rootfs.tar.xz`: Debian filesystem, without a kernel.
- `artifacts/tabs3-rootfs-packages.tsv`: installed package versions.
- `artifacts/tabs3-SHA256SUMS`: package/rootfs hashes.
- `artifacts/builder-*`: toolchain image identity and package versions.
- `artifacts/Image-RELEASE.gz` and `msm8996-samsung-gts3llte*.dtb`.
- `artifacts/linux-tabs3_VERSION_arm64.deb`: kernel, DTBs and loadable modules.
- `artifacts/tabs3-desktop_VERSION_all.deb`: optional Phosh integration.

Package versions come only from `config/device.json` (`project_version` for
`tabs3-base`, `kernel_package_version` for `linux-tabs3`, `desktop_version`
for `tabs3-desktop`); the build scripts
read them through `scripts/versions.sh`, and `scripts/build-package.sh` stops
if the package's own version files disagree.
- `private/images/lk2nd-sm-t825.img`: Samsung boot wrapper, under 4 MiB.
- `private/images/tabs3-diagnostic.img`: RAM-only Linux/SSH diagnostic image.
- `private/images/boot-images.json`: image sizes, hashes and donor provenance.

The development account is `dev`, with public-key SSH and passwordless sudo.
Password authentication and root SSH login are disabled. SSH host keys and
machine ID are generated for each device on first boot. The USB service only
runs with an exact `samsung,gts3llte` compatible string; its operation is
verified on the installed system. The tablet address is `172.16.42.2/30`;
the PC will need `172.16.42.1/30` on the corresponding USB network interface.

## Next hardware work

Open work, the hardware status table and the sensor inventory are in
[todo.md](todo.md). The milestones below are the project's first steps, all
done.

1. **Done:** verify model, Android build, bootloader properties and root access.
   Current boot/recovery and live DTB are backed up with verified hashes.
   See [the hardware record](docs/hardware-sm-t825.md).
2. **Done:** charge sufficiently (50% recommended), preserve user data and
   verify that TWRP boots and exposes ADB before altering the boot partition.
   TWRP has since been replaced by the tabS3 recovery (see [Recovery](#recovery)).
3. **Done:** compare live LTE IDs, PMICs, memory reservations, eMMC and USB;
   compile the conservative LTE diagnostic DTS and Linux kernel.
4. **Done:** build and validate local lk2nd/Android image containers and an
   early USB SSH initramfs; build the Debian kernel/modules package.
5. **Done:** lk2nd detects the LTE board; RAM-only Linux boots and accepts
   authenticated USB SSH. Recovery entry with hardware keys is verified.
6. **Done:** Linux sees all 47 eMMC partitions. Read-only boot/recovery reads
   match expected hashes. The 52 MHz limit produces a 50 MHz clock with HS200
   timing; removing HS200 DT properties alone does not remove controller caps.
7. **Done:** install Debian on userdata, boot from the combined lk2nd/Linux
   image, log in as `dev` over USB and expand the filesystem. Normal software
   reboot is also verified with the PS_HOLD device-tree fix. Proceed through
   the remaining hardware milestones. The kernel follows kernel.org's 6.18
   longterm series for security fixes (projected end of life December 2028).

The port's Samsung boot packaging and 4 MiB lk2nd reservation are documented
in [its device notes](https://github.com/wh1ter0z3/gts3lwifi-mainline/blob/main/docs/lk2nd.md).
Those hardware tests were on SM-T820. Do not reuse its stock donor images or
partition offsets as SM-T825 facts.

## Internal Debian installation

The user chose internal storage and authorized erasing Android files/apps.
The initial installer overwrites **userdata and boot**, preserving GPT,
recovery, Android system and modem/calibration partitions. The later storage
expansion also uses Android system, and the current installation has the
project's Linux recovery. See Current scope above for hardware status.

```sh
bash scripts/build-kernel.sh
bash scripts/build-kernel-package.sh
bash scripts/build-initramfs.sh private/id_ed25519.pub
bash scripts/build-lk2nd.sh --autoboot
bash scripts/build-installed-rootfs.sh
```

The installed rootfs builder uses the prepared Debian tarball, installs
`linux-tabs3_6.19.5-3_arm64.deb`, tests a real ARM64 login as `dev`, and checks a
4 GiB ext4 filesystem. Its first boot expands the filesystem within userdata,
after checking board identity, partition name and filesystem UUID. The UUID in
`private/images/installed-rootfs.json` must be passed to the boot packer:

```sh
bash scripts/pack-images.sh --mode installed --root-uuid ROOTFS_UUID \
    --donor private/backups/20261010T094140Z/boot.img
```

The resulting `tabs3-internal-boot.img` contains the Samsung lk2nd wrapper,
padding to 4 MiB, then the Linux/initramfs image. The initramfs checks userdata's
filesystem UUID before handing control to Debian systemd. A failed root check
starts key-only USB rescue SSH instead.

Optional, once Android is no longer needed: `--extend-root system` adds
`tabs3.root_extend=system`. The initramfs then joins userdata and Android's
4.2 GB system partition into `/dev/mapper/tabs3root` (linear device-mapper,
userdata first) and mounts that; the grow service fills it. Growing erases
Android's system partition, and afterwards TWRP or an image without the flag
can no longer mount userdata. This tablet runs that way (28 GiB root).

From verified TWRP, `scripts/install-internal.py --serial TABLET_SERIAL` performs
read-only checks. `--apply` writes the prepared images and verifies readback
hashes; it **erases Android userdata**. It requires the saved successful storage
test. `--adb-port` supports a dedicated host ADB server. It pauses TWRP UI/MTP processes and unmounts userdata before writing, then leaves
reboot as a separate step. TWRP remains paused until that reboot. Progress is
recorded under `private/`.

**This tablet no longer has TWRP**: its recovery partition now holds the
tabS3 recovery below, so the TWRP-based installer above needs the saved TWRP
image (`private/backups/20261010T094140Z/recovery.img`) written back first,
until the installer moves to the Linux recovery.

## Recovery

The recovery partition holds a second lk2nd (built with
`LK2ND_PARTITION_BASE=recovery` and `LK2ND_FORCE_RECOVERY=1`, from
`bootloader/patches/`) followed by Linux in `tabs3.mode=recovery`: the same
panel driver and initramfs design as the installed system, with its independent
display-only device tree. Its verified package-29 kernel, DTB and modules are
retained. The recovery fastboot update adds a one-time software entry request,
a 120-second idle return and an **Enter fastboot** touch action.
Nothing is mounted until asked.

See [recovery fastboot](docs/recovery-fastboot.md) for the installed recovery's
build recipe, partition layout, commands, rollback and validation. From Debian,
`sudo tabs3-fastboot` requests this mode; from recovery use
`tabs3-recovery fastboot`. It supports RAM booting and returning to recovery.
Persistent image updates still use the checked recovery helper.

The older recipe below builds recovery using the current kernel artifacts;
it does **not** preserve the installed package-29 kernel or include remote
fastboot. Use the pinned-baseline recipe above for the installed variant.

```sh
bash scripts/build-lk2nd.sh --recovery
bash scripts/build-recovery-ui.sh
bash scripts/build-initramfs.sh private/id_ed25519.pub
bash scripts/pack-images.sh --mode recovery --variant display \
    --donor private/backups/20261010T094140Z/boot.img
```

Write `private/images/tabs3-internal-display-recovery.img` to the partition
named `recovery` and verify it by reading it back. Enter recovery with
`sudo systemctl reboot --reboot-argument=recovery` from Debian, or with
Home + Volume Up + Power. Then, from the PC on USB:

```sh
tools/recovery-ssh tabs3-recovery help
```

It can show the partitions and the root filesystem, mount root (read-only
unless asked, joining userdata and system when needed), run `e2fsck`, export
the whole eMMC to the PC as a USB disk (read-only unless asked), and flash a
combined boot image with readback verification. On the tablet, a touch
screen (`recovery-ui/`, LVGL) shows the root, boot image and USB state and
offers Boot Debian, Check filesystem, Share storage, Power off and Enter fastboot;
`scripts/build-recovery-ui.sh --preview DIR` renders its screens on the PC.
A short Power press switches the screen, touch wakes it, and it switches off
after 10 minutes. Leave with a 3-second Power hold or
`tabs3-recovery reboot`. Samsung's bootloader keeps booting recovery while
the first word of its `param` partition is 2; leaving clears it, but a forced
reset (Power held about 9 seconds) comes back to recovery.

The installed system uses `dev@172.16.42.2`, with the local project key:

```sh
ssh -i private/id_ed25519 -o UserKnownHostsFile=private/installed-known-hosts \
    dev@172.16.42.2
```

The host's `tabs3-diagnostic` NetworkManager profile also serves the installed
system: its match is the tablet gadget's exact host MAC. The installed SSH host
key is persistent; diagnostic initramfs host keys are intentionally ephemeral.

The retained initial rootfs image contains kernel package `6.19.5-2`; the
running tablet was updated to `6.19.5-3` and its combined boot image was written
and readback-verified separately. Installing the kernel package alone does not
update the boot partition. Rootfs builds install the kernel package version
named in `config/device.json`. Retain the
installed filesystem UUID when repacking boot images for an existing system;
building a new rootfs creates a different UUID.

For this workstation, an isolated ADB server on port 5038 with `ADB_LIBUSB=1`
and `--one-device TABLET_SERIAL` recovered a connection missed by the default
native USB backend. Other connected phones are not controlled by this server.

## Checks

```sh
python3 -m unittest discover -s tests -v
docker run --rm -v "$PWD:/project:ro" tabs3-builder:trixie \
  shellcheck scripts/*.sh build/*.sh initramfs/init packages/tabs3-base/usr/libexec/tabs3-usb-gadget
```

The rootfs build checks ARM64 execution, package configuration, sudo syntax and
SSH configuration under QEMU. None of these replace a real tablet boot test.

`scripts/ci.sh [REV]` tests a committed revision (default `HEAD`) from a fresh
clone: it applies the kernel patch stack to the pinned source with `--fuzz=0`,
builds the kernel, device trees, modules and Debian packages from scratch in
the builder container, runs the host tests and `tools/check-dtbs`, and fails on
compiler warnings in patched files; it takes about 11 minutes with 6 jobs. Its
objects use a separate Docker volume, so the development build is untouched. `tools/check-dtbs [DIR]` checks compiled
device trees on their own: board identity, reserved TrustZone pins, and which
hardware each variant enables.

After installing on the tablet, `tools/boot-check --expect-package VERSION`
checks it over USB SSH without changing anything: the running kernel matches
the installed package; no failed units, GPU faults or unexpected kernel
warnings; buttons, panel, Wi-Fi, battery and storage; and on the full variant
the sound card, audio DSP and modem.

Upstream files retain their original licenses. New project code is MIT licensed.
