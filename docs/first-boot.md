# SM-T825 first boot and restore plan

Status: **RAM-only Linux boot, USB SSH, eMMC reads and TWRP recovery verified**.
This is the original plan. TWRP was later replaced by the tabS3 Linux recovery
(see "Recovery (replaces TWRP)" in `docs/hardware-sm-t825.md`); the TWRP image
remains backed up privately.
The initial diagnostic test replaced boot temporarily and restored its full
original hash; Android return was confirmed. The user subsequently chose a
persistent internal Debian installation and authorized erasing Android data.
That installation has now booted Debian from userdata with USB SSH and a
24 GiB root filesystem; its boot and rootfs writes passed complete readback
hash checks, and recovery remained unchanged.

## What the first test changes

Samsung's normal Android interface cannot RAM-boot this mainline image.
The proposed first persistent change is installing our 2.3 MiB lk2nd wrapper
in the **boot partition**. It does not replace Samsung's primary bootloader.
This build deliberately stops in fastboot. Android will not start normally
until its saved boot partition is restored.

Once lk2nd is running, the 19 MiB diagnostic image can be loaded with fastboot's
RAM-boot operation. The Linux device tree disables internal storage. The
initramfs mounts only RAM/virtual filesystems, configures USB networking,
starts public-key SSH and requests a reboot after 300 seconds. A panic asks
for a reboot after 30 seconds. Neither timer guarantees recovery from a
firmware hang; physical recovery access must be available.

Display/touch, charging, Wi-Fi, GPU and LTE modem support are not established.
The screen may retain the Samsung/lk2nd splash throughout the diagnostic boot.
After the timed reboot the tablet returns to lk2nd, not Android.

## Prerequisites before writing boot

1. Charging to **at least 50%** is recommended. Check the level again in
   Android before leaving it. Do not rely on mainline Linux to charge it.
2. Verify that the installed TWRP actually boots, exposes ADB, reports the
   correct model and can read the named boot partition. Offline inspection
   found a TWRP recovery ramdisk; subsequent hardware boots verified TWRP 3.5.2_9-0.
3. Keep the current boot/recovery backups and their manifest on this PC and
   another safe storage location if available. Preserve important user data
   separately. The current backup is rooted firmware, not a factory package.
4. Check the image hashes in `private/images/boot-images.json` against the
   files immediately before use. Recheck tablet identity, root access, named
   partition resolution and partition size in the current recovery session.
5. Review that installing lk2nd temporarily replaces Android's normal boot
   path. This preparation does not authorize erasing userdata, repartitioning,
   replacing recovery or touching modem/calibration partitions.

## Target selection and test sequence

The PC can have other phones connected. Every ADB/fastboot command must specify
the verified tablet serial. Recovery or lk2nd can report different metadata
from Android; do not carry a guessed target forward or use an implicit default.

After the prerequisites are met:

- Enter and verify TWRP, leaving recovery installed.
- Stage `private/images/lk2nd-sm-t825.img` in recovery's temporary RAM directory
  and compare its SHA-256 with the PC copy.
- Write that verified image only to the freshly resolved named **boot**
  partition. Flush writes and read back exactly the image length to verify it.
- Reboot, identify the tablet's lk2nd fastboot device and collect its log.
- Use fastboot **boot**, with an explicit tablet serial, to load
  `private/images/tabs3-diagnostic.img` into RAM. No OS image is flashed during
  this first diagnostic test.
- Identify the newly appeared USB network interface by its host MAC
  `02:54:53:33:00:01`. Assign only that interface `172.16.42.1/30`.
- Connect with the project development key to `root@172.16.42.2`. Host keys
  are regenerated for each diagnostic boot; use a separate known-hosts file
  for these tests without weakening global SSH settings.
- Save kernel version, device-tree identity and `dmesg` to private logs.
  Check USB stability. An SSH login is the first hardware milestone.
- Restore Android's original boot image at the end of the initial test unless
  keeping lk2nd installed has been explicitly chosen.

The initial diagnostic flash sequence is manual. The source port's Wi-Fi
commands and default lk2nd offsets must not be copied onto this LTE tablet
without the checks above. The internal installer now automates a separate,
explicitly destructive userdata/boot installation after these hardware checks.

## Restore Android

Primary restore image:
`private/backups/20261010T094140Z/boot.img` (79,691,776 bytes).
Its SHA-256 is recorded in that directory's `manifest.json`.

Use the hardware recovery combination described in the
[source port's recovery notes](https://github.com/wh1ter0z3/gts3lwifi-mainline/blob/97e9c58c29bc34c4776ca47ee147226464120cda/docs/lk2nd.md):
Power + Volume Up + Home. Those notes report that lk2nd's Recovery menu entry
can merely reboot; do not depend on that menu entry. This behavior was also
observed on SM-T825. Holding Home + Volume Up during a targeted reboot reached
TWRP successfully on this tablet.

In verified TWRP, copy the saved boot image into its temporary RAM directory,
verify the transfer hash, restore the complete image to the discovered named
boot partition, flush, and verify the full partition hash before rebooting.
Do not write the original image using lk2nd's ordinary `flash boot` operation:
that operation applies lk2nd's reserved offset and would not restore the
original layout.

This boot-only restore returns the original Android installation only while
Android userdata is still intact. Once Debian replaces userdata, restoring
Android also requires a suitable Android data filesystem; the boot backup does
not recover erased files or apps.

Samsung Download mode is a secondary possible restore route. Matching factory
firmware has not been downloaded, and a Download-mode restore has not been
tested. This is why a working TWRP path is required before the first write.

Calibration backups are in `private/backups/20261010T103054Z/` (EFS, modemst1,
modemst2 and persist). They are for device-specific recovery, not part of the
normal boot test or restore procedure. Never publish or transplant them.

## Internal-install checks learned on this recovery

Allowing modifications in the TWRP UI can mount the newly written userdata
filesystem. The installer pauses the verified `/sbin/recovery` UI/MTP
processes and unmounts userdata before rewriting it. ADB remains available;
TWRP stays paused until the separately requested reboot.

This TWRP's Toybox `head -c 4294967296` wraps to zero bytes. A four-GiB
readback must use `dd bs=1048576 count=4096`, followed by SHA-256. The installer
uses that bounded read and compares the entire image before writing boot.
The smaller boot-image readback remains below the affected size.
