# Installation on SM-T825 rev05

This is an advanced, staged installation. **The initial install erases Android
user data and replaces the boot partition.** It has not been qualified on a
second tablet. Do not use these steps to update an existing Debian install,
especially one whose root spans both `userdata` and `system`.

Keep a working recovery, your own verified backups, a charged battery (at least
50%), and a data-capable USB cable available throughout. This repository does
not unlock the Samsung bootloader, install TWRP, or supply stock firmware.

## 1. Confirm the device and preserve Android

The verified target is **SM-T825 / gts3llte / board rev05 / MSM8996**. The
development tablet used Android 9, bootloader `T825JXU3CTE1`, existing root,
and TWRP `3.5.2_9-0`. Model similarity is not sufficient for another variant.

Enable Android USB debugging and authorize your computer, then run:

```sh
python3 scripts/inspect-device.py --output private/device-report.json
python3 scripts/backup-device.py
python3 scripts/backup-device.py --calibration-only
```

The backup commands require existing Android root access. They save boot,
recovery, live DTB, and (separately) EFS/modemst/persist with readback hashes.
**They do not back up your apps, photographs, or Android user data.** Preserve
those separately. Keep a second copy of the backups off this computer.

Retain your original Android `system` image privately if you want the sensor
DSP registry later; it is not included in `backup-device.py`. The
[registry builder](../tools/sensor-registry/README.md) expects a verified raw
system backup compressed as `system.img.zst`, not a TWRP split archive.
Do not erase or repurpose `system`, `apnhlos`, `modem`, or calibration partitions
during this first installation.

Boot TWRP physically before proceeding and check that ADB, root, and the named
partitions work. The supported layout is:

| Name | Recovery block device | Bytes |
| --- | --- | ---: |
| boot | `/dev/block/mmcblk0p28` | 79,691,776 |
| recovery | `/dev/block/mmcblk0p29` | 79,691,776 |
| userdata | `/dev/block/mmcblk0p47` | 26,226,966,016 |

The installer also pins the tested recovery partition SHA-256
`4bfffec62f55ba3e178165844697c1bb7a844c42ce5f132bf26a0737fe3a58dc`.
Another TWRP build, even with the same version string, may not match. A refusal
means additional recovery qualification is needed; do not remove the guard.
No tested TWRP image is redistributed by this project.

## 2. Build your own images

Follow [building.md](building.md) and [accounts.md](accounts.md). Build both
lk2nd variants, the recovery UI, rootfs, initramfs, diagnostic, storage-probe,
and installed **display** images. Use your own donor `boot.img`; do not reuse
another person's personalized images or credentials.

The source currently builds candidate `6.18.56-81~drivers2`. Its complete
cold-boot/audio qualification is pending. Building it successfully does not
make it a production release.

## 3. Bootstrap lk2nd, then test Linux in RAM

This first bootstrap remains a **manual recovery operation**. The
[original first-boot record](first-boot.md) explains its tested mechanics;
historical device paths in that record must be replaced with your own backups.

1. In TWRP, identify the tablet's ADB serial explicitly. Recheck model, root,
   partition mapping/size, and your backup hashes. Do not use an implicit ADB
   target when other devices are connected.
2. Transfer `private/images/lk2nd-sm-t825.img` to recovery RAM. Compare its
   SHA-256 with `private/images/boot-images.json` on the computer.
3. Write only that verified wrapper to the start of the freshly resolved
   **boot** partition, flush, and read back exactly its byte length. Require
   the same hash before rebooting. Leave recovery and all other partitions
   untouched. This temporarily prevents ordinary Android boot.
4. Boot lk2nd and identify its fastboot serial separately. RAM-boot the plain
   diagnostic image:

```sh
fastboot -s YOUR_FASTBOOT_SERIAL boot private/images/tabs3-diagnostic.img
```

The diagnostic image disables internal storage, exposes root SSH over USB,
and requests a reboot after five minutes. It may leave the splash visible.
Configure the [computer's USB address](user-guide.md#usb-ssh), connect with your
key, verify the board and inspect `dmesg`. A timer is not recovery from every
possible hang; keep the physical recovery combination available.

The recovery/diagnostic host key is regenerated each boot. Keep its trust
record separate from installed Debian. On a physically controlled direct USB
link, enroll this ephemeral key into `private/probe-known-hosts` with an initial
interactive SSH connection. Do not reuse this trust-on-first-use procedure
over an untrusted network.

## 4. Test storage without writing it

Return to lk2nd and RAM-boot:

```sh
fastboot -s YOUR_FASTBOOT_SERIAL boot private/images/tabs3-storage-probe.img
```

Reconnect USB networking and enroll this boot's new key in the dedicated
probe known-hosts file. Then, from the computer:

```sh
python3 scripts/record-storage-probe.py \
    --identity private/id_ed25519 \
    --known-hosts private/probe-known-hosts
```

This checks the storage-probe boot mode, read-only block devices and partition
geometry, reads the full boot partition three times, checks equal hashes and
MMC errors, and saves a private receipt. It writes only a temporary RAM file
on the tablet. The installer binds the receipt to this eMMC's identity hash.
Never fabricate a receipt or copy one from another tablet.

The new receipt tool and its installer integration have host regression tests;
they have not yet been exercised through a fresh installation on a second
device. Stop on a failed check and retain the output for diagnosis.

## 5. Install internally from TWRP

Return to the verified TWRP, keeping Home + Volume Up held during a targeted
reboot if needed. Reconfirm the ADB serial in this mode. First inspect:

```sh
python3 scripts/install-internal.py --serial YOUR_ADB_SERIAL --variant display
```

Only after all checks pass, the following command **erases Android userdata
and writes Debian plus the combined boot image**:

```sh
python3 scripts/install-internal.py --serial YOUR_ADB_SERIAL --variant display --apply
```

The writer pauses the verified TWRP UI, unmounts userdata, verifies image
transfers, writes the rootfs, verifies its entire readback, then writes and
verifies boot. Recovery is hashed before and after. It leaves TWRP paused;
reboot separately only after it prints successful completion:

```sh
adb -s YOUR_ADB_SERIAL reboot
```

If it fails, keep the tablet in recovery and inspect
`private/internal-install-session.json`. Do not reboot a partial install or
assume the Android boot backup restores erased user data.

## 6. First login, network, and dashboard

Installed Debian starts with `dev`, your chosen account password, and key-based
SSH. You can also [enable SSH password login](accounts.md#enable-ssh-password-login).
Configure USB networking and [connect](accounts.md#first-ssh-connection), then
connect Wi-Fi using [the user guide](user-guide.md#wi-fi).

On the computer, copy the built dashboard:

```sh
. scripts/versions.sh
scp -i private/id_ed25519 -o UserKnownHostsFile=private/installed-known-hosts \
    "artifacts/tabs3-dashboard_${DASHBOARD_VERSION}_all.deb" dev@172.16.42.2:~/
```

On the tablet (use the actual filename if you built another version):

```sh
sudo apt update
sudo apt install ./tabs3-dashboard_0.1.9_all.deb
sudo tabs3-server-enable
sudo systemctl enable --now tabs3-dashboard.service
sudo tabs3-dashboard-theme silicon
systemctl --failed
```

Initially, disable camera/sound/light presence wake in
`/etc/tabs3/dashboard.conf` until their firmware and sensors are provisioned.
Touch and Power wake remain available. The display-only image provides the
dashboard; absent peripheral readings are shown as unavailable.

## 7. Provision firmware and qualify the full hardware image

From the repository on the tablet, install Adreno firmware **before** the
other extractors create its shared destination directory:

```sh
sudo apt install firmware-qcom-soc
sudo sh tools/install-gpu-firmware
sudo sh tools/install-dsp-firmware
sudo sh tools/install-slpi-firmware
sudo sh tools/install-venus-firmware
```

Copy those scripts from the computer if the repository is not on the tablet.
They read the tablet's own signed stock partitions and copy the needed files
into `/usr/lib/firmware`; they do not download or redistribute Samsung blobs.
If GPU installation reports an incomplete existing directory, stop and inspect
it; do not delete unrelated DSP firmware to work around the error.

Install `tabs3-sensors` and build/install the private
[sensor registry](../tools/sensor-registry/README.md) for motion/light sensing.
That reconstruction is pinned to a particular Samsung binary and will reject
unrecognized firmware. Audio/desktop configuration is in the optional
`tabs3-desktop` package and [historical setup notes](../HISTORY.md#gpu-and-phosh-desktop).

Use the existing root UUID to build the **GPU** installed variant. Do not add
`--extend-root system` for this new single-partition root. Test the plain image
from RAM with matching modules before writing its combined boot image, using
the [maintenance procedure](maintenance.md). The full peripheral configuration
needs its own validation; a successful dashboard is not proof of all drivers.

## Restore or stop an experiment

Before userdata is erased, restoring the complete original boot partition in
verified TWRP can return the unchanged Android install. After userdata is
erased, boot restoration alone is insufficient. You also need your Android
data backup or a separately qualified stock restoration procedure.

Never write another tablet's EFS, modemst, persist, or calibration images.
See [maintenance.md](maintenance.md) for Debian backup and recovery.
