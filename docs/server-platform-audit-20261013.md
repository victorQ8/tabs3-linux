# SM-T825 server transition and platform audit — 2026-10-13

The owner changed the target to a continuously running Debian server. Desktop
integration and application shortcuts are no longer the active objective.
Claude stopped before these tests. Only the SM-T825 was accessed.

## Installed state and limits

- Normal boot and modules: **6.18.56-55**. Recovery: **6.19.5-29**.
  Both boot partitions were read back and still match their saved images.
- `tabs3-base` **0.1.15** includes `tabs3-server-enable`, the server CPU ceiling,
  factory Wi-Fi MAC restoration, persistent health recording and server
  maintenance policy. The earlier platform/load record used 0.1.13; see the
  subsequent qualification work below for the later changes.
- Console boot, SSH and Wi-Fi survive a normal reboot. Graphical startup and
  desktop audio services are disabled; sleep targets are masked. Closing a
  lid must not suspend the server. The display powers down after 60 seconds.
- Wi-Fi MAC differed from EFS. It now matches EFS after reconnect and reboot.
  Both USB SSH and Wi-Fi SSH were checked. Private addresses/SSID, credentials
  and EFS contents are excluded from the published captures.
- This is **not a completed 24/7 qualification**. The new platform kernel
  reset in RAM tests, and several requested hardware tests remain open.

Run `sudo tabs3-server-enable` to apply the server profile. Optional desktop
packages remain installed. Desktop audio is masked through `/etc/systemd/user/`;
the profile also writes `/etc/systemd/logind.conf.d/70-tabs3-server.conf` and
`/etc/systemd/system/tabs3-screen.service.d/server.conf`. These are deliberate
server settings, not changes to the recovery image.

The Wi-Fi helper uses `/wifi/.mac.info` in EFS and validates a single unicast
address. A `.link` file and NetworkManager connection default set the address.
On the installed IWD backend, the NetworkManager setting alone did **not**
change the address: IWD recreated the interface with the board-data address.
`[DriverQuirks] DefaultInterface=ath10k_pci` preserves the interface configured
by udev. Existing IWD settings are preserved, with an initial local backup.

## Requested hardware, item by item

| Item | Measurement / work completed | Still required |
|---|---|---|
| CPU idle | Package 56 added only `ARM_PSCI_CPUIDLE`. Read-only RAM probe reported `psci_idle`; all four cores accumulated deep-idle residency with zero rejected entries, including after a short four-worker load. Reboot returned to Debian. | Full-system qualification and measured power saving. It is not enabled in installed package 55. WFI is a shallow waiting state, not a software busy loop. |
| eMMC | Normal system remains at the conservative 52 MHz ceiling. Built separate 200 MHz HS200 and HS400 **read-only RAM probes** that preserve the existing probe's initramfs and five-minute reboot limit. | RAM-boot each, verify actual timing, repeated direct reads and matching hashes before any normal-root write test. No speed improvement is claimed. |
| Camera memory | Package 57 removed only the unused `0xc0000000/0x14800000` no-map pool. Its first RAM boot reported 3,702,680 kB MemTotal versus 3,367,480 kB in package 55 (about 327.3 MiB recovered after kernel overhead). | Isolate the subsequent reset, then memory/firmware stress. Removal is not installed. |
| RTC | Confirmed 1970 RTC despite NTP-correct system time. `util-linux-extra` provides `hwclock`. Candidate adds `allow-set-time`. | Write trusted UTC, read back, and verify retention through an offline reboot on a stable candidate. Do not guess coincell charging parameters: the stock node does not specify them. |
| Hall cover | Candidate adds GPIO7 on PM8994 as active-low `EV_SW/SW_LID`, using stock S4/no-pull configuration. Server logind policy ignores lid-triggered suspend. | Physical open/close event and screen policy check. No cover event was claimed. |
| AP/skin thermistor | Candidate raw-IIO driver uses all 111 stock VADC 0x73 calibration points. Host C tests cover units, interpolation, monotonicity and invalid readings. First RAM boot reported 36,344 m°C. The proposed 43°C passive trip links both CPU clusters and GPU. | Stable probing, comparison against raw ADC and an independent thermometer, and cooling response. This is an AP thermistor reading, not a verified surface temperature. |
| RNG | Candidate `qcom_rng` bound and reported `TRNG support not detected`, as expected for `qcom,prng-ee`. | Keep the distinction: this driver deliberately does not expose this older PRNG as a trusted `/dev/hwrng`. Do not substitute the `qcom,trng` compatible to force one. Binding remains a candidate change. |
| Crypto BAM | Candidate disables both unused crypto and remotely controlled BAM nodes; its deferred-probe list was empty. | Isolate/qualify the platform changes. Installed 55 still has the existing crypto deferred probe; CPU cryptography continues to work. No DMA execution-environment values were invented. |
| Grip/SAR | Added both stock bit-banged buses and the existing SX9310 driver to candidate 57. **Both probes returned ENXIO when reading WHOAMI.** The original Android log confirms that the LTE SX9310 initialized and returned register values. | Investigate rail/probe ordering and bus electrical setup. Rebind after shared sensor supplies settle before assuming the devices are absent. Wi-Fi sensor population is not established by the stock DT alone. No Linux RF/SAR policy is implemented. |
| Wi-Fi MAC | **Installed and verified** against read-only EFS after reconnect and reboot; verified SSH via Wi-Fi. | Longer operation/reconnection coverage. |
| USB SuperSpeed | Reviewed stock S2MM005 status-read protocol, QMP PHY and redriver GPIO14 wiring. Current host mode remains USB 2.0. | PHY/redriver/CC integration and a real SuperSpeed peripheral in both cable orientations. Do not assert that an AP-controlled orientation mux is required: the reviewed stock QMP code does not program one. Firmware handling must be established. No PD voltage/current negotiation changes were made. |
| Watchdog | Candidate registered `/dev/watchdog0` using the stock APSS address, KPSS driver, sleep clock and bark interrupt. | Isolate the reset with this node disabled, then prove keepalive, safe disarm and a controlled timeout before enabling systemd hardware-watchdog supervision. |
| Back/Recents | Prior hardware press tests establish input events; the desktop-specific actions were unresolved. | Desktop actions are deferred by the server scope change. No new physical press test was performed. |

## Failed platform RAM boots: do not install package 57

The aggregate platform image booted Debian and exposed recovered RAM,
skin temperature, RTC configuration and the watchdog, but then unexpectedly
reset back to the untouched package-55 boot image. Repeating the RAM boot with
`cpuidle.off=1` also reset. That rules out enabled CPU idle as a necessary
condition for this failure, but does not prove CPU idle is production-ready.

No persistent panic identifying the reset was captured. There were display
clock-update warnings and failed SX9310 probes. Neither is established as
the cause. Systemd `RuntimeWatchdogUSec` was zero. Registering a watchdog is
not the same as testing its timeout or proving that it caused this reset.

Next isolate the watchdog, camera-pool reclamation, and the other platform
changes in separate RAM boots. Capture kernel output continuously on the
host from first SSH availability, plus watchdog state and CPU-idle counters.
Keep the normal boot partition at 55 until a candidate stays up and passes
load/reboot tests. Those RAM boots need physical fastboot entry; the owner
left after the comparisons, so they were not attempted unattended.

The experiment is preserved on branch `platform-audit-57`; the normal
`display-bringup` branch retains the installed kernel configuration. Private
images and full logs are under `private/platform-audit/` and
`private/images/package56/`, `private/images/package57/`.

## Server load measurement

The uncapped kernel-55 run used four verified integer CPU workers plus a
256 MiB memory worker. The independent monitor stopped it after 525 seconds
when a CPU sensor reached **95.1°C**. Stress-ng reported five workers passed
and zero failed, but the requested ten-minute run **did not complete**.
Battery temperature at stop was 28.5°C. This motivated a conservative
supported-frequency ceiling for server mode, while retaining kernel thermal
throttling. See `tools/server/soak.py` and the captures in
`docs/server-measurements-20261013/`.

The repeated runs completed ten minutes each with no verification failures:

| Requested ceiling | Observed CPU maximum | Maximum battery temperature | Result |
|---|---|---|---|
| Uncapped | 95.1°C | 28.5°C | Monitor stopped at 525 s |
| 1.2 GHz | 92.2°C | 28.9°C | Completed 601 s |
| 1.0 GHz | 90.6°C | 29.0°C | Completed 603 s |

These were successive runs with different starting temperatures, not controlled
thermal benchmarks. The final profile selects 960 MHz / 940.8 MHz ceilings
from the two supported frequency tables. This does **not** establish a safe
chassis temperature or remove the need for the skin sensor and further thermal
qualification. Kernel thermal throttling still reduced frequencies during load.

`tabs3-server-cpu-limit.service` selects supported frequencies at or below
`TABS3_CPU_MAX_KHZ`, configured through `/etc/default/tabs3-server`. It changes
no voltage table. Disabling that service and rebooting restores the normal
driver defaults. Both capped repeats and the final reboot check are recorded
in [`server-validation-20261013.json`](server-validation-20261013.json).
A short soak cannot certify 24/7 reliability.

The PC is detected as an SDP and remains capped at 500 mA. During heavy load
the battery current was negative even with the cable attached. Continuous
heavy server workloads therefore still require a suitable wall-powered
setup; USB attachment alone does not prove a sustainable power budget.

The eMMC reports raw lifetime fields `0x01 0x01` and pre-EOL `0x01`; the root
filesystem had 23 GiB free. For the next timing tests,
`tools/platform/read-storage-probe.sh` reads an unchanged portion of **boot**
repeatedly. Do not compare a whole-disk hash across boots: Android-era metadata
and firmware-owned partitions can change even when the RAM probe writes nothing.

The live IIO inventory still exposes VADC and the SMGR accelerometer. Recognition
of gyro, magnetometer or ambient-light firmware services is not equivalent to
a working Linux IIO driver for each; those were not newly implemented here.

## Follow-up: is the installed system ready for unattended 24/7 service?

**Not yet qualified.** A read-only live inspection at 12:11 UTC found kernel
55, working SSH/network services, no failed system services, CPU temperatures
around 39–41°C at idle, and a battery temperature of 28.5°C. The battery was
100%; charger-board temperature was 32.5°C. These are an idle snapshot, not a
sustained-load result. The earlier ten-minute tests and normal reboot checks
do not establish unattended reliability. See the sanitized
[live inventory](server-measurements-20261013/reliability-review.json).

The server-critical work is power, thermal control, storage integrity, network
recovery and recovery from hangs. Missing camera, pen, orientation or audio
features need not block a headless server. Faster eMMC and reclaiming the camera
pool are performance/capacity improvements; preserving working storage and
firmware memory boundaries takes precedence.

Additional gaps beyond the original hardware list:

1. **Power management still has development overrides.** The live command line
   contains `clk_ignore_unused` and `pd_ignore_unused`. They suppress automatic
   gating of unclaimed clocks and power domains left enabled by firmware;
   they do not prove how much power is wasted. The modem, ADSP and SLPI were all
   running, with Bluetooth and sensor services active. Qualify a minimal server
   configuration and removal of the overrides in separate RAM tests. Do not
   blindly switch off shared supplies needed by Wi-Fi or charging. The kernel's
   [parameter reference](https://docs.kernel.org/admin-guide/kernel-parameters.html)
   documents these as development options.
2. **Charging for permanent attachment is not qualified.** The live driver
   reported `Full` while the gauge reported roughly +140–150 mA at 4.37 V.
   This alone proves neither a charging fault nor correct termination: the
   driver's status maps either `DONE` or `TOPOFF` to `Full`. Record a complete
   termination/recharge cycle and check battery-current accuracy. No charge
   percentage ceiling is implemented. Battery capacity/condition, low-battery
   clean shutdown, extended loss of power and restart when power returns still
   need testing. A previous cable-powered reboot after `poweroff` is not proof
   of recovery after an exhausted battery. Test sustainable wall-powered load
   before treating the battery as a UPS.
3. **Wired networking/storage and charging conflict today.** The installed OTG
   path disables charging while the tablet powers a USB host connection. The
   RTL8153 bound in the earlier hub test, but wired traffic and a powered hub
   were not tested. A USB3 speed change alone will not solve simultaneous
   host operation and power input. Use the separate
   [hub evidence](usb-hub-validation-20261013.json) when qualifying this path.
4. **Hang recovery and post-reset evidence are incomplete.** Ramoops is bound,
   persistent journaling is enabled, and older pstore files were archived;
   it would be wrong to call crash logging absent. But one saved console has
   visibly damaged bytes, and no captured panic explains candidate 57. Prove
   retention across the relevant reset paths. Hardware watchdog supervision
   is absent in installed 55, and software soft/hard-lockup and hung-task
   detectors are disabled. `panic=30` only handles an actual panic; it is not
   a general hang-recovery mechanism. The kernel documents
   [watchdog supervision](https://docs.kernel.org/watchdog/watchdog-api.html)
   and [ramoops persistence requirements](https://docs.kernel.org/admin-guide/ramoops.html).
5. **Server maintenance was incomplete at the review snapshot.** `unattended-upgrades` was not
   installed and no APT periodic policy was returned. Define a Debian security
   update process and a separate tested update path for our custom kernel.
   [Debian documents the distinction](https://www.debian.org/doc/manuals/debian-handbook/sect.regular-upgrades.en.html)
   between checking/downloading and applying upgrades. SSH has key access and
   disallows root login, but password authentication remains enabled from
   tablet setup. Review the permanent server login/network policy. Boot and
   firmware backups are not a tested backup/restore plan for future service
   data. No monitoring/backup job was found in the limited local-service search;
   external monitoring or backups were not audited.
6. **Storage and memory failure policy deserves explicit qualification.** Root
   ext4 then reported `Errors behavior: Continue`; select and test the
   intended response to detected corruption. Weekly TRIM is enabled and has
   succeeded. Journals occupy about 388 MiB. There is no active swap; set
   workload memory limits and test recovery from memory pressure rather than
   assuming all containers fit in the available RAM. Check journal retention,
   disk-full behavior, backup restore and checksums under the actual workload.

The kernel still emits four display-clock warnings during boot, despite the
GUI being disabled. VADC uses polling intentionally, Wi-Fi has a board-file
fallback, and crypto BAM remains the known failed/deferred probe. These logs
need classification; a zero failed-service count is not a claim of error-free
driver initialization. No new GPU or filesystem fault was identified in this
inspection. Linux's random generator reported initialization at 5.82 seconds,
so the absent hardware PRNG driver does not mean normal cryptography is broken.

Qualification order: isolate the candidate reset; validate thermal, idle, RTC
and watchdog changes individually; establish sustainable power and automatic
recovery; then run the intended services for multiple days with temperature,
power, network, memory and storage checks. A 48–72 hour run would be an initial
acceptance test, not a guarantee of future uptime. No workload was specified
when this review was recorded. This review changed documentation only, without
rebooting, adding load, or changing the tablet's configuration.

## Qualification work after the review

The owner authorized the work and is away. Software entry into the existing
recovery is verified; it does not require Volume Down. Fastboot RAM entry is
different, and remains dependent on a button in the tested procedure. Kexec
is compiled into Debian, but no hardware handoff through it has been validated.
No speculative fastboot/kexec route was attempted unattended, and no kernel
or recovery image was installed.

Completed independently of physical access:

- **Persistent health recording:** `tabs3-server-health.timer` samples once a
  minute. Root-only JSON records contain temperatures, battery current and
  charge/source state, CPU frequencies, memory/IO pressure, space, link counters
  and boot identity. Records survive reboot. Retention is seven daily files,
  each capped at 8 MiB, plus the latest sample. Missing temperature/battery
  readings produce notices; 15 minutes of reported drain on external power
  also produces a notice. Early warning thresholds are diagnostic, not thermal
  control or a low-battery shutdown implementation. No external alert delivery
  is configured. A live sample took about 0.12 seconds to collect; total process
  CPU time was about 0.7 seconds and peak memory about 6 MiB.
- **CPU governor check:** both clusters already use `schedutil`. Their time-in-
  state counters showed roughly 96% at 307.2 MHz. A sample briefly reading the
  configured frequency ceiling is not proof that the CPU stays there at idle.
  Deep-idle qualification is still separate and unfinished.
- **Configuration/user-file backup:** a private 403,297,071-byte compressed
  snapshot covers `/etc`, `/home/dev` (excluding cache/trash), Wi-Fi state and
  `/var/lib/tabs3`, with a package inventory. Restored in an isolated,
  network-disabled container: 660 regular files matched contents and modes,
  557 symlink targets matched, and 334 directories existed. Numeric ownership
  is recorded in the tar but was not applied in the unprivileged restore test.
  This is a one-time configuration/user-data checkpoint, not a full-system
  image, scheduled backup service, or transaction-consistent database backup.
- **Offline filesystem check:** software recovery entry returned SSH in 15.2
  seconds. Root was unmounted, USB export was off, and all five `e2fsck -fn`
  passes completed with exit 0. No filesystem repairs were needed. The return
  to Debian succeeded; the initiating SSH command timed out during reset,
  so success was established through a new boot ID and fresh connection.
- **Maintenance:** `tabs3-server-maintenance` sets SSH key authentication and
  disallows remote root/password login. Fresh key logins passed over USB and
  Wi-Fi, while a password-only connection was rejected. The console password
  was not changed. Debian `trixie-security` updates are automatic; `linux-tabs3`
  and `tabs3-*` are excluded, automatic reboots and automatic dependency/kernel
  removal are disabled. A dry run selected only `librsvg2-2` and
  `librsvg2-common`; both security updates were then applied successfully.
- **Filesystem error policy:** the validated `tabs3root` ext4 mapping now uses
  `errors=remount-ro`, both in its superblock and active mount. The authoritative
  live option list is `/proc/fs/ext4/dm-0/options`; `findmnt` omits this option
  when it matches the superblock default. Deliberate corruption was not induced.

The failed platform boots' last persisted journal entries are at 23.449863
and 21.985653 seconds. Neither contains an orderly reboot or a captured panic.
These are the times of the last saved entries, not proven reset times. The
watchdog remains a bisection candidate, not a diagnosed cause. Existing pstore
and kernel logs were copied privately before the recovery round trip.

The final normal reboot with base 0.1.15 returned USB SSH in 28.9 seconds.
The automatic health sample, key-authentication policy, factory Wi-Fi address,
CPU ceilings and filesystem error policy survived it, with no failed system
services. Kernel 55 and recovery 29 image prefixes match their saved hashes;
the record explicitly includes their byte lengths, since both images are
shorter than their containing partitions. All 49 host tests pass. The
[stage-1 validation](server-stage1-validation-20261013.json) includes the private
backup's digest/restore results, update policy and a bounded health capture.
The recorder continues on the tablet after this capture ends.

Long-duration workload/power testing, watchdog/RTC/skin/CPU-idle driver testing,
router-outage recovery, battery exhaustion/restart and the remaining hardware
items are still open. There is no claim of completed 24/7 qualification.

## Source and evidence

- Mainline driver sources are pinned to Linux 6.18.56 in `config/sources.json`.
  Relevant files: `drivers/crypto/qcom-rng.c`, `drivers/watchdog/qcom-wdt.c`,
  `drivers/rtc/rtc-pm8xxx.c`, `drivers/thermal/thermal-generic-adc.c` and
  `drivers/iio/proximity/sx9310.c`.
- Samsung source: `awesometic/android_kernel_samsung_msm8996`, commit
  `f48aec90fcebf4615fdee4a8abac7339930db856`; relevant files are
  `drivers/sensors/sx9310.c`, `sx9310_wifi.c`,
  `drivers/soc/qcom/watchdog_v2.c`, `drivers/ccic/s2mm005_cc.c`,
  `drivers/usb/phy/phy-msm-ssusb-qmp.c` and
  `drivers/usb/notify/usb_notifier_qcom.c`.
- Board wiring/calibration: this tablet's backed-up stock live DTB, kept
  private under `private/backups/20261010T094140Z/`.
- Installed IWD documentation describes `DriverQuirks.DefaultInterface`;
  its journal confirmed the quirk was in use. No passphrases are in the record.
