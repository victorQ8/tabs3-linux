# Backups, updates, and recovery

## Back up an existing Debian system

From the workstation, with the tablet's installed host key already verified:

```sh
python3 tools/server/backup.py --profile full-users
```

This saves selected configuration/user directories and exact boot/recovery
partition copies under `private/backups/`, reads every archive member back,
and compares selected restored configuration hashes. It is **not a full root
filesystem image or a transactional database backup**. Back up application
data not covered by the chosen profile separately.

For recurring small appliance/configuration backups:

```sh
python3 tools/server/backup.py --profile appliance --keep 7
```

`--keep` prunes older verified appliance backups; it does not apply to the
full-users profile. Review the exact scopes in the script. The appliance
profile does not preserve arbitrary home-directory documents.

Example systemd user units are in `tools/server/systemd/`. Adjust their
`WorkingDirectory` to your checkout and optionally add `--fallback-host
dev@YOUR_WIFI_ADDRESS`; they run on the **computer**, not the tablet.
Store a second copy of verified backups elsewhere. They contain credentials
and device identity: never attach them to GitHub issues.

## Update user-space packages

Build the relevant `.deb`, copy it to the tablet, and use `sudo apt install
./PACKAGE.deb`. Save work first: package installation can restart the
dashboard or services. Review configuration-file merge prompts. Validate
`systemctl --failed` and service logs afterward.

## Kernel updates are a separate operation

Installing `linux-tabs3_*.deb` updates `/boot` files and `/lib/modules`, but it
**does not flash the actual boot partition**. Keep kernel image, modules and
DTB from the same build. A successful `dpkg` command is not a successful boot
update.

Before testing a kernel, preserve the installed `.deb`, the exact boot and
recovery images, root UUID/layout, and image/package hashes. A kernel package
version may change without changing `uname -r`, so version strings alone are
not enough to prove the modules match.

For an existing root, read its UUID from `/etc/tabs3-root-uuid`. Determine
whether it spans `userdata` only or the `userdata`+`system` mapping before
packing. **Do not rebuild or reinstall the rootfs to update the kernel.**

```sh
bash scripts/build-kernel.sh
bash scripts/build-kernel-package.sh
bash scripts/build-initramfs.sh private/id_ed25519.pub
bash scripts/pack-images.sh --mode installed --variant gpu \
    --root-uuid YOUR_EXISTING_ROOT_UUID \
    --donor private/backups/YOUR_BACKUP/boot.img
```

Add `--extend-root system` only for an already verified extended-root layout.
It is not part of a fresh installation and must not be used to silently erase
or repurpose an Android system partition. Keep the previous images outside
the output directory so another build cannot overwrite your rollback copy.

Stage matching modules, RAM-test the **plain** `tabs3-installed-gpu.img`, and
check boot logs/data paths before considering a permanent write. The details
depend on whether the tablet still has TWRP or already has project recovery.
Do not unload active modules or replace them during workload testing without
a deliberate recovery plan.

## With the project's Linux recovery installed

See [recovery-fastboot.md](recovery-fastboot.md) for its one-time handoff:

```sh
sudo tabs3-fastboot status
sudo tabs3-fastboot
```

The second command reboots into recovery's fastboot path. On the workstation,
select the verified fastboot serial and RAM-boot the **plain** test image.
Do not RAM-boot the combined lk2nd image. A reset from a RAM test can return to
recovery; that is not proof that the kernel was permanently installed.

Once a complete candidate passes, the recovery command
`tabs3-recovery flash-boot FILE` checks and writes the **combined** boot image
with readback verification. Transfer/hash verification, correct device,
matching modules and a rollback copy are still required. The recovery
environment's `tabs3-recovery reboot` clears the recovery request before
returning to normal boot.

This public source includes recovery code, but does not ship a preconfigured
recovery image. Keep your proven TWRP until a separately built project recovery
has been tested on your hardware. Replacing recovery is not part of the first
installation guide.

## With TWRP still installed

Use the explicit-device, named-partition and readback procedure from the
[first-boot record](first-boot.md). A generic `fastboot flash boot` is unsuitable
for restoring an entire Samsung partition because lk2nd applies an offset.
Keep userdata unmounted for offline filesystem work. Never use the
initial internal installer for an update; it erases userdata.

## After any boot change

```sh
python3 tools/boot-check --expect-package YOUR_KERNEL_PACKAGE_VERSION
```

Inspect warnings as well as failures. Test the affected real data paths,
panel wake, charging, network, and recovery before treating the change as
accepted. The [production gates](production-readiness.md) additionally require
continuous observation and power/reboot tests; clearing logs cannot turn an
earlier failure into a pass.
