# Debian tablet: production qualification

Status on 2026-11-05: **release candidate, not production qualified**.
The primary workload is Debian plus the AMOLED dashboard. On 2026-11-05 the
owner explicitly expanded acceptance to **all hardware drivers end to end**.
The hardware matrix and remaining work in [todo.md](../todo.md#hardware-functions)
are part of this target, including functions unused by the dashboard.
Emulation is retired. Direct wall power and a powered USB hub are both intended
setups; neither may be assumed equivalent to the PC's 500 mA USB port.

## Installed foundation

- Kernel `6.18.56-80`, base `0.1.35`, dashboard `0.1.9`, desktop package
  `0.1.10`. Desktop sessions are not the default.
- `tabs3-power-guard.timer` checks every 15 seconds. At 5% or below it requests
  an orderly systemd shutdown after 60 seconds of consecutive drain evidence;
  at 2% or below it requires 30 seconds. A gap over 45 seconds, a reboot,
  recovered charging, or recovered capacity resets confirmation. It checks
  signed battery current as well as cable presence. It never issues a forced
  hardware cutoff. Missing/implausible measurements cannot request shutdown.
- The existing 65–80% battery keeper is retained. Invalid configuration and
  capacity readings are now handled before charger arithmetic/writes.
- The health recorder reports read-only root filesystems and telemetry gaps.
  Gaps, reboot, invalid time, and deliberate keeper descent cannot masquerade
  as evidence of sustained external-power drain. Logs remain bounded to
  8 MiB per day and seven files.
- Base 0.1.34 also rejects Venus video-firmware and remote DSP crashes in
  the production checker, even if the firmware recovers. The controlled
  encoder tests exposed such a fault; this boot is not a clean soak.
- Base 0.1.35 reads PID 1's root mount and superblock flags. The health
  service's own `ProtectSystem=strict` namespace is intentionally read-only
  and previously caused false root-read-only alerts. The actual service now
  records schema 3, a writable root and no current notices while retaining
  its sandbox. Missing or malformed mount information fails the health gate.
  Historical false alerts remain in the log; they are not erased to pass a soak.
- SSH remains key-only, root SSH is disabled, Debian security updates are
  automatic, and automatic reboots remain disabled. Local hardware packages
  require the separate validated image/update procedure.
- Refreshed the Debian indexes and installed the available security updates
  for apt, libapt-pkg7.0, libnss3 and linux-libc-dev, plus the stable timezone
  data update. `linux-libc-dev` is userspace development headers; this did not
  replace or reboot the custom running kernel.
- The live audit found ten emulator packages still installed despite the
  2026-10-16 removal record. These were purged again on 2026-11-05, plus the
  remaining manual emulator/test binaries. Shared graphics/audio libraries,
  Debian, the dashboard, user profiles and saves were preserved.

The guard can be inspected without changing anything:

```sh
sudo /usr/libexec/tabs3-power-guard
sudo cat /run/tabs3-power-guard/latest.json
systemctl status tabs3-power-guard.timer
```

`--enforce` is reserved for the installed timer and allows a real shutdown.
The gauge's current accuracy and physical shutdown/restart behavior still
need hardware qualification. Invalid measurements are logged, not interpreted
as proof the battery is safe indefinitely.

## Boot candidate, prepared but not flashed

Private release directory: `private/releases/20261105-rc1/`.
`manifest.json` records SHA-256 hashes and the exact package versions.
The candidate's kernel/DTB payload, command line and first 4 MiB bootloader
region match the current boot partition byte for byte.

The new initramfs runs `e2fsck -p` on the validated, unmounted root mapping
before mounting it. Only status 0 or 1 permits Debian to start. Reboot-required,
uncorrected-error, operational-error and interrupted results enter the recovery
screen and USB rescue instead of mounting the root or entering a reboot loop.
The checker log and numeric status survive into Debian under `/run/log` and
`/run/tabs3-root-fsck.status`. The recovery Fastboot action also works when the
kernel command line still says `installed` after a failed root check.
The rescue USB gadget also applies the installed system's USB 2 speed limit
before binding, so the known USB 3 Rx.Detect problem cannot strand this path
after a host-mode session. This needs the same physical cable-switch test.

This follows [e2fsck's preen and exit-status rules](https://manpages.debian.org/trixie/e2fsprogs/e2fsck.8.en.html).
The initramfs uses `broken_system_clock=true` because this tablet's PMIC clock
offset is applied later in Debian; this avoids treating pre-NTP time as disk
damage. See [e2fsck.conf](https://manpages.debian.org/trixie/e2fsprogs/e2fsck.conf.5.en.html).

Validation already performed: shell exit-status tests, recovery regression
tests, Android boot-container validation, an authenticated ARM64 SSH session
under QEMU, and the actual ARM64 filesystem checker against a healthy ext4
image and an invalid image. The focused host suite passes all 78 tests.
These do not replace a tablet RAM boot.

The checked combined candidate is staged on the tablet at
`/var/lib/tabs3/kernel-candidates/production-rc1/boot.img`. No boot partition
write or reboot has been performed during this preparation.

## Backups and restore

The verified pre-change backup is
`private/backups/production-20261105T093227Z/`. It includes exact 79,691,776-byte
boot and recovery partitions, installed-package inventory, configuration,
home/root files, Wi-Fi/Bluetooth state and appliance state. The archive was
read through completely (17,914 regular files); six configuration files were
restored into an isolated directory and compared with tablet-side hashes.
An earlier interrupted stream was discarded; its separately verified partition
copies remain in `production-20261105T092118Z/`.

The development PC now has `tabs3-appliance-backup.timer`, scheduled daily
with up to 15 minutes of jitter. It retains the seven newest **verified
appliance** backups; the full user backup is never rotated by this job.
It first tries USB, then the configured private Wi-Fi address, always using the same pinned SSH host
key. It compresses on the PC, validates both partition copies, and restores
configuration samples before declaring success. Its first run passed in
about 15 seconds (`private/backups/appliance-20261105T094015Z/`).
An independent Wi-Fi run also passed (`appliance-20261105T095015Z/`).
The job budgets uncompressed source size, both partition copies and 1 GiB of
headroom before copying, so a low-space PC refuses a new backup rather than
depending on optimistic compression or deleting its last successful copies.

```sh
# On the development PC:
systemctl --user status tabs3-appliance-backup.timer
systemctl --user start tabs3-appliance-backup.service
journalctl --user -u tabs3-appliance-backup.service -n 20
```

The PC's user systemd manager must be running and the tablet must be reachable.
A DHCP reservation for the current Wi-Fi address, or updating the timer's
fallback address after a change, remains necessary. Failed connections do not
count as successful backups or trigger retention. No off-device messages are
sent; the owner's panel-only alert preference is unchanged.

Daily backups cover appliance settings and boot images, **not all user files,
arbitrary `/srv` data, or transaction-consistent application databases**. Add
an application-specific backup before putting new workloads on this tablet.
Backups contain SSH/Wi-Fi credentials and stay private (directory 0700,
files 0600). They are not a complete Debian root image or proof of a whole
device restore after storage failure.

Rollback procedure for this candidate:

1. Keep the verified host backup and existing recovery available. Use the
   [recovery workflow](recovery-fastboot.md), with the tablet serial selected
   explicitly. Never use generic fastboot partition writes.
2. If the candidate fails, use recovery's checked `flash-boot` helper with the
   verified pre-change `boot.img`, then `tabs3-recovery reboot`. Leave the
   recovery partition and root partition mapping unchanged.
3. For userspace rollback, disable `tabs3-power-guard.timer` first and install
   `private/releases/20261105-rc1/tabs3-base_0.1.31_all.deb`. Run daemon-reload
   and inspect the dashboard, screen and health timers. Preserve current user
   configuration unless an individual file has been shown to be the problem.
4. Restore specific configuration files from the archive after comparing
   them, with their original ownership/modes. Do not extract the entire live
   backup over a running system.

## Release gates

| Gate | Current evidence | Still required |
|---|---|---|
| Userspace installation | 0.1.35 installed; guard and health jobs succeed; dashboard and screen active | Survive candidate disk boot |
| Offline root check | Host and ARM64/QEMU tests passed | RAM boot, checked flash, disk boot and recovery fallback on tablet |
| Sustainable power | PC port charging at 500 mA input limit during this work | Wall charger and powered hub: screen on/off, load, unplug/replug, 65–80% hold; no unintended sourcing/drain |
| Low battery | Confirmation/recovery/fault tests passed | Observe orderly shutdown and restart when power returns; never deliberately flatten the cell |
| Watchdog/recovery | Hardware watchdog enabled at 20 s; existing recovery backed up | Controlled watchdog recovery and useful retained crash evidence |
| Long operation | Fresh minute-by-minute baseline started | 72 continuous hours on a frozen release, then a longer intended-workload run |
| Storage | Root writable; 32 MiB temporary-file checksums pass on root and SD | Offline check on tablet, isolated disk-full behavior and endurance |
| Backup | Full archive and daily appliance job verified | Whole-device recovery rehearsal and any future application-data backup |
| Network | USB and Wi-Fi SSH work | Router outage/reconnect; stable fallback address |
| Dashboard/input | Running with AMOLED protection retained | Repeated sleep/wake, sensors, touch/buttons, and recovery after service failure |
| Known drivers | Major dashboard hardware works | Display handoff warnings and audio stream-reopen timeout diagnosis; sustained GPU qualification where used |
| Kernel maintenance | Running project baseline is 6.18.56 | Review and qualify the newer 6.18 stable fixes before final release freeze |
| Release provenance | Private artifact hashes and rollback copies recorded | Review/checkpoint the shared working tree and create a reproducible release/tag after hardware qualification |

Do not close a hardware gate merely because a package builds or a service is
active. USB3 SuperSpeed, LTE data, GPS/SMS/voice, fingerprint, keyboard cover,
headset detection and the other incomplete paths remain open acceptance items.
An unavailable peripheral is a blocked physical test, not a pass. Features
whose board wiring is unproven (native video output) must be resolved against
the actual model rather than inferred from shared Samsung device-tree nodes.

The separate audio candidate `6.18.56-81~audio1` contains fixes for late q6asm
responses and a skipped capture flush. It builds and passes the host regression
test, but is not installed. Both its package/modules and boot image are needed
for the next hardware test. Keep the kernel-80 boot-fsck candidate above as the
isolated recovery baseline. See the [hardware record](hardware-sm-t825.md#full-device-qualification-2026-11-05).

The source build version is now `6.18.56-81~drivers2`, so new builds cannot
overwrite the package-80 rollback artifact. The complete build in
`private/releases/20261105-drivers81c/` adds Venus patches 0048–0050 to the
audio fixes. Its packaged video-module build IDs match the temporary modules
that passed the tests below. Its boot images reuse the checked audio-candidate
payload: these additional changes affect modules only. It is **not installed,
flashed or production qualified**. The earlier `81~drivers1` setup-only build
failed encoder testing and is retained separately as negative evidence.
The final package, both boot images and the package-80 module rollback are
also staged and SHA-256 verified on the tablet under
`/var/lib/tabs3/kernel-candidates/drivers81c/`. Staging does not install modules
or write the boot partition. Reboot/flash approval is still pending.

The [video validation record](driver-video-validation-20261105.json) separates
initial firmware crashes from the final candidate's successful hardware
tests. Patches 0049/0050 fix encoder EOS and reject unsupported capture-pool
growth while streaming. H.264 through 1080p, a 300-frame stream, three reopen
cycles, VP8 file/container output and hardware H.264 decoding now reach clean
EOS with no new kernel errors in these runs. Independent decoding confirms
the expected frame counts. Original modules were restored. Complete candidate
boot, audio validation, camera-to-encoder operation and longer operation
remain required; package 80's encoder is still the installed baseline.

The 2026-11-05 data-path check passed a 32 MiB write/fsync/checksum readback on
both root and microSD, and numeric samples from all four SLPI sensors plus the
grip sensor. [Raw results](driver-data-paths-20261105.json) record the limits;
these are not whole-media, calibration, endurance or power-loss tests.

As checked on 2026-11-05, [kernel.org](https://www.kernel.org/?lan=english)
lists 6.18.60 (2026-10-30) for the 6.18 longterm line. The installed custom
kernel is therefore not the latest maintenance release. This is a pending
update review/qualification item, not evidence by itself of a specific
exploitable vulnerability. The first boot-check candidate deliberately keeps
the existing kernel so its storage/recovery behavior can be validated on a
known hardware baseline before combining it with a kernel upgrade.

## Continuous qualification

On the tablet, after the final candidate is booted and all package changes are
finished:

```sh
sudo tabs3-production-check --begin
# Later; read-only, JSON report, nonzero until all automated gates pass:
sudo tabs3-production-check --hours 72
```

The report checks running services, failed units, package consistency, clock
sync, SSH policy, offline fsck status, fresh battery protection, current health,
kernel fault signatures, and a continuous health-log interval. A reboot,
changed hardware package version, missing observations or a gap over three
minutes prevents an automated pass. It deliberately never labels the whole
device production-qualified: the physical gates above need separate evidence.
Restart the interval explicitly after a planned reboot or release change.

For the next controlled boot test: RAM-boot
`private/releases/20261105-rc1/RAM-ONLY-rescue-test.img` first to exercise the
recovery fallback using an intentionally mismatched root UUID, with no root
mount. That image is for RAM only and must never be flashed. Then RAM-boot
`private/releases/20261105-rc1/tabs3-installed-gpu.img`, confirm fsck status,
root mount and core services, return to recovery, flash the staged **combined**
image with the checked helper, and repeat validation from disk. Start the
72-hour interval only after that succeeds and sustainable external power is
connected. Reboot/flash permission is pending from the owner.
