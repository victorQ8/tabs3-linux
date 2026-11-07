# Recovery fastboot on SM-T825

The recovery partition has a separate lk2nd ahead of Linux. The
`--recovery-fastboot` build adds software entry to that copy while retaining
the package-29 recovery kernel, device tree and modules. Debian continues to
use kernel package `6.18.56-55`. This is bootloader fastboot, not Android
fastbootd, so it supports loading a Linux image into RAM.

## Entry and exit

From Debian, as root:

```sh
tabs3-fastboot          # arm one request and reboot into recovery's lk2nd
tabs3-fastboot status   # clear or armed; read-only
tabs3-fastboot cancel   # clear a previously armed request without rebooting
```

From recovery: select **Enter fastboot**, or run `tabs3-recovery fastboot`
over its authenticated USB SSH connection. The recovery helper unmounts the
Debian root, refuses an active USB storage export, then requests a recovery
reboot using `RESTART2`. It does not rely on a leftover Samsung recovery flag.

On the PC, always select this tablet's recorded serial explicitly. The new
mode advertises `getvar:tabs3-recovery-fastboot = 1` and
`getvar:tabs3-idle-timeout = 120`. Check the product and LTE compatibility
before sending an image. `fastboot boot` takes a Linux boot image, **not** a
combined on-disk lk2nd/Linux partition image. `fastboot continue` boots the
installed recovery. Use `tabs3-recovery reboot` from there to return to Debian;
it clears Samsung's persistent recovery flag.

The available fastboot commands are `getvar`, `download`, `boot`, `continue`,
`reboot`, `oem log`, and `upload`. Partition writes and erases are deliberately
unavailable in this recovery build: its partition splitting differs from the
normal boot copy, so a generic `flash boot` could overwrite Debian's lk2nd.
Use recovery's existing checked `flash-boot` helper for persistent updates.
The recovery bootloader menu also omits Download/EDL entry.

A RAM-boot round trip without touching a button (2026-10-14, package 63):
`tabs3-fastboot` on Debian, wait for the serial in `fastboot devices`,
`fastboot -s SERIAL boot private/images/package63/tabs3-installed-gpu.img`,
SSH is back about 20 s later on the installed root. A plain reboot from
the RAM-booted system lands in **recovery**, because Samsung's persistent
recovery flag set on the way in is still there; `tabs3-recovery reboot`
over `tools/recovery-ssh` clears it and returns to Debian. The recovery's
own SSH host key is not stored, so the Debian helpers (which pin the
installed host key) simply fail while the tablet sits in recovery.

## One-time request and timeout

Two full 512-byte records occupy previously zero-filled wrapper padding:

| Record | Offset within recovery | Contents |
| --- | ---: | --- |
| Capability | `0x3fe000` | `TABS3-RFB-CAP-v1:120`, then zero padding |
| Request | `0x3ff000` | `TABS3-RFB-ONCE-v1`, then zero padding, or all zero |

The Linux payload starts at `0x400000`. The packer refuses a wrapper that
overlaps either record or a baseline with nonzero reserved tail bytes.
The Linux helper checks the SM-T825 device-tree identity, recovery partition
name/size, export state, exact capability record and valid existing request
contents. Writes touch only the request sector and are followed by fsync and
readback. A local lock serializes request writers. Old recovery images fail
the capability check before any write.

After lk2nd splits recovery, it validates the resulting partition offsets,
512-byte storage block size and both records. It clears and reads back the
request before entering fastboot. Failed consumption continues into recovery.
No request is stored in Samsung's `misc` or `param` partition.

Only entry through a consumed software request starts the idle timer. After
120 seconds waiting for a new command, lk2nd requests a recovery reboot. The
timer cannot run a reset while a command handler is active. USB command and
physical menu dispatch share the same busy/expiry gate. `fastboot_stop`
disarms the timer before handing off to Linux.

This is an **idle timeout**, not a watchdog. An interrupted transfer that
leaves a command handler blocked, a bootloader failure, or a hung experimental
kernel can still require a physical reset. Hardware watchdog qualification is
a separate server task. USB remains necessary; lk2nd does not provide Wi-Fi.

## Hardening of 2026-10-14

A review by Codex of the helper, the UI and the init found eight weaknesses;
all are fixed in the recovery image installed on 2026-10-14
(`private/recovery-fastboot-2/`, same kernel, device tree and lk2nd as the
2026-10-13 build), with `tests/test_recovery_robustness.py` covering each:

- `flash-boot` validates the image before writing: both Android headers of
  the combined image (page size, payload bounds, legacy DTB area), the Linux
  image's id checksum over kernel and initramfs, no recovery images, nothing
  while storage is exported. A file holding only two `ANDROID!` strings used
  to be written and reported as verified.
- One operation at a time: a lock directory (`/run/tabs3-recovery.lock`)
  serialises mount, umount, fsck, storage, flash-boot, fastboot, reboot and
  poweroff, passes to the detached export worker, and the power-key hold
  respects it. Leaving stops an active export first.
- The export worker rebinds the USB controller on any failure, so a failed
  reconfiguration no longer strands the SSH path.
- The superblock fields fall back to the first backup superblock and fsck
  gets `-b`/`-B` when the primary is unreadable; read-only mounts use
  `noload` and never replay the journal.
- The UI clears "Starting Debian" when the helper refuses or fails, refuses
  to leave while a check runs, reads its status with a 5 s timeout and shows
  "Status unavailable" rather than "No filesystem" on a failed read.
- The init starts the screen before USB and continues without SSH when the
  controller fails.

Checked on a RAM boot before installing and on the installed build: bad and
truncated images refused with the boot partition untouched, a real image
validated and written in 3 s, a reboot during fsck refused, `norecovery`
on the read-only mount, export on and off with the lock released. The
fastboot idle timeout is still not a watchdog (see above).

## Build and rollback

```sh
bash scripts/build-lk2nd.sh --recovery-fastboot
bash scripts/build-recovery-ui.sh --preview work/recovery-fastboot/preview
python3 scripts/pack-recovery-fastboot.py \
  --baseline private/images/tabs3-internal-display-recovery.img \
  --baseline-sha256 b2e4d3d21e6a128a02688d9a27145aecaf1caf27b4d12195b030467294d89c40 \
  --output-dir private/recovery-fastboot
bash scripts/build-package.sh
python3 -m unittest discover -s tests
```

The packer preserves the baseline's Linux kernel, appended DTBs, modules,
SSH credentials, addresses and command line. It replaces lk2nd and the
recovery UI/helper, and adds the request library and small static recovery
reboot helper. It writes separate combined and RAM-boot images and a hash
manifest, with no device access. Images remain private because they include
the authorized SSH key.

The full pre-install recovery partition is saved as
`private/recovery-fastboot/recovery-before.bin`; its hash and the unchanged
boot partition hash are in `pre-install.json` beside it. Keep that backup and
the original RAM-bootable recovery available on the host during testing.
The normal Debian bootloader is not part of this update.

## Validation

Host tests compile the actual bootloader request/timeout implementation with
simulated storage and time. They cover one-time consumption, invalid records,
write/read failures, incorrect partition layouts, unsupported block sizes,
timeout renewal, counter wrap, active commands, overlapping menu/USB actions,
and timer cancellation. Shell tests check exact write boundaries, old-image
refusal and concurrent requests. The UI's hitbox test covers all five tiles;
its rendered preview was inspected for layout and readability.

Hardware results are recorded separately in `recovery-fastboot-20261013.json`.
The build manifest's `hardware_tested: false` describes build-time validation;
it is not overwritten with later test results.
