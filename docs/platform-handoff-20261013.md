# Platform handoff and continuation — 2026-10-13

Installed: **linux-tabs3 6.18.56-61**, **tabs3-base 0.1.19**, console/server
profile. The image passed RAM testing, was written to normal boot and read
back with a matching hash. USB and Wi-Fi SSH returned with no failed units.
Recovery remains unchanged on the verified package-29 display kernel with
remote fastboot. See the [validation record](platform-validation-20261013.json).
Long-duration 24/7 qualification is still open.

## Where Claude stopped

Claude built package 56/base 0.1.17, packed the images, installed the modules
and base package, and actually attempted a RAM boot through remote fastboot.
The tablet returned to recovery after a short Debian boot. The handoff was
therefore later than the quoted “packing images” message, but not a successful
platform validation.

The gyro/magnetometer/light, GP-clock and vibrator changes existed only in the
ignored Linux work tree. They are now reproducible patches 0029–0031. Agent
outputs are preserved under [research/platform-20261013](../research/platform-20261013/README.md).
The rear-camera report completed; S Pen left an unfinished driver patch and
DTS; the S2MPB02 draft did not establish chip presence. None is installed.
Samsung's camera supply wiring names PM8994 regulators, not S2MPB02.

## Resets and timekeeping

Controlled package-56 RAM tests established:

| Change from Claude's image | Result |
|---|---|
| Disable only watchdog | Reset; last live sample 37 s |
| Disable watchdog and restore camera memory reservation | Reset; last live sample 47 s |
| Use the previously installed package-55 DT | Survived the 186 s observation |
| Remove only RTC `allow-set-time` | Survived NTP synchronization, the 187 s observation and over ten minutes of subsequent work |

This isolates the writable-RTC property as the trigger in these experiments.
It does not identify the exact firmware failure mechanism or prove the cause
of every earlier package-57 reset. Keep PM8994 RTC writes disabled.

The base package now stores an atomic, root-only UTC/RTC pair only after NTP
synchronization. On offline boot it advances system time using elapsed RTC
seconds. It ignores malformed records and a backwards RTC counter. Package
58 booted with timesyncd masked and its wall clock agreed with the PC within
one second. Battery removal/counter reset requires a new trusted time sync.
Six host tests cover saving/restoring time and bad/stale input.

## Storage and memory

Both RAM-only HS200 and HS400 probes negotiated an actual **192 MHz**, 8-bit,
1.8 V bus. Each read 512 MiB in about 4.74 s (113 MB/s), with three matching
64 MiB hashes and no MMC CRC/tuning/timeout errors. HS400 did not outperform
HS200 in this measurement.

A package-59 HS400 boot then passed four distinct 256 MiB file writes with
fsync and two direct rereads per file: 1 GiB written, 2 GiB verified. The
full Debian DT now permits 200 MHz/HS400. Base diagnostics, initial eMMC and
display/recovery DTs retain the 52 MHz cap; packer and DT guards enforce the
variant distinction. Long write endurance, power-loss behavior and the user's
actual server workload remain unqualified.

Removing the old 328 MiB no-map camera pool gives `MemTotal: 3700632 kB`.
A five-minute 1 GiB memory-verification run passed, with peak CPU 52.3°C and
battery 27.4°C. This is a bounded memory test, not exhaustive RAM testing.

## CPU idle, watchdog and temperatures

The generic watchdog binds and systemd feeds it, but its active status alone
was misleading. In a RAM-only image with storage read-only, it **did not reset
within 90 seconds** after a single keepalive with a 20-second timeout while
all CPUs used standalone power collapse. Samsung's extra watchdog enable bit
(bit 1, `UNMASKED_INT_EN`) did not fix that. No speculative driver patch for
that bit is included.

Disabling deep idle restored watchdog reset/recovery. A second test disabled
only CPU0's deep state, leaving CPU1–3 enabled, and also returned to recovery.
The server CPU policy therefore disables CPU0's deep idle states; CPU0 still
uses WFI and the other three CPUs use `psci_idle`. The exact firmware/register
interaction remains unproven. A watchdog reset is destructive to a live
filesystem, so these deliberate expiry tests mounted no tablet filesystem.
The first installed-Debian test aborted when remount-read-only was refused.

Patch 0034 adds the stock 111-point raw-VADC AP thermistor conversion on
channel 0x73. Its initial reading was 35.7°C. A 43°C passive trip requests
cooling on both CPU clusters and the GPU. This complements existing TSENS,
battery and charger protections. It is an **AP thermistor**, not independently
calibrated chassis surface temperature. Conversion tests exercise every raw
code, negative temperatures, interpolation and invalid sensor readings.

The first full CPU/memory load test stopped after 15.7 s at its conservative
45°C AP guard (46.3°C sampled, CPU 71°C, battery 26.6°C). Cooling requests
had started, but states 1/2 were above the already imposed server frequency
cap and therefore did not yet reduce CPU clocks. Package 61 starts this AP
trip at CPU cooling states 11/20, mapping to 652.8 MHz on the measured 16/25
OPP tables. Those indices must be revalidated if the OPP tables change.
This abort is not counted as a completed soak.

The revised package-61 policy passed 303.6 seconds of four CPU workers plus
256 MiB memory verification, with zero computation errors. Peak readings:
CPU 62.9°C, AP 43.787°C, battery 26.8°C. CPU clocks actually dropped through
652.8/480/307.2 MHz as cooling was requested, and returned to the server's
960/940.8 MHz ceilings after cooling. The supervisor retained independent
85°C CPU, 50°C AP and 38°C battery guards. This five-minute test does not
establish long-term stability or calibrated outer-surface temperature.

## Other drivers

- Gyro and magnetometer return samples. Light initially selected the wrong
  firmware data type (0x501); patch 0032 uses the reported selector (0x28,1).
  Light now returns samples. Physical motion/light response and unit/calibration
  checks are still needed; registration is not complete sensor validation.
- Haptics bind after correcting the GP1 parent to the RPM XO source. Actual
  vibration/strength needs a physical check.
- Cover switch is registered; logind ignores it for server use. A physical
  cover/magnet event test is pending.
- Both SX9310 grip devices still fail WHOAMI with ENXIO. They do not work.
- Disabled unused crypto/BAM nodes remove the deferred probes. This does not
  provide a functioning hardware crypto engine or hardware RNG.
- ADSP, SLPI and modem boot with the revised carve-outs and relocated MBA.
- Venus authenticated its own stock firmware. Before patch 0033, H.264 decode
  produced 173/180 frames and failed at EOS with `deadb000`. The proposed
  [upstream EOS fix](https://lists.openwall.net/linux-kernel/2026/09/28/2956),
  adapted to 6.18, completed two 180-frame DMA-buffer/fakesink runs cleanly.
  A subsequent CPU pixel-conversion/filesink pipeline timed out, including
  with mmap and ordinary NV12 caps requested. It captured 169 complete I420
  frames; every pixel matched software decoding (infinite PSNR). Completing
  that pipeline, usable transcoding and encoding remain **unverified**.
- Cameras, S Pen, fingerprint, USB3/Type-C controller and simultaneous USB
  host/charging remain unfinished. The old RNG is not a supported TRNG.

## Evidence and next checks

Raw captures, rollback images, source snapshots and package/image hashes are
private under `private/claude-handoff-20261013/`. They include local identities
and journals and are not published. The public validation record will contain
selected measurements and hashes. Firmware remains private on this tablet.

The fresh-clone CI applied 44 base/port/local patches with zero fuzz, passed
63 host tests and all four DT guards, and rebuilt the kernel, modules and
packages with no compiler warnings in 64 patched files. All 97 compared
patched/copied source files and all four DTBs match the development build.
An offline `e2fsck -fn` before installation returned 0 (clean). Kernel and base
package versions, normal boot readback, CPU idle policy, active watchdog,
thermal sensor, empty deferred-probe list, server default target and both SSH
paths were checked on two installed boots with different boot IDs. The second
was an ordinary `systemctl reboot`; the persistent health and RTC-offset
timers remain active.

Next: long wall-powered qualification and the actual server workload;
power interruption/router recovery; physical sensor, cover and vibration
checks; remaining driver ports. Camera/S Pen drafts still require review,
builds and hardware tests. GUI work remains retired.
