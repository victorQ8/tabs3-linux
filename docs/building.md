# Build from source

Run commands from the repository root on a Linux workstation. Building does
not access or flash a tablet.

## Requirements

- Git, Python 3.11+, `patch`, OpenSSH tools, and Docker Engine.
- ADB and fastboot for later device work; Pillow for dashboard previews.
- Space for Linux source, container layers, build objects, and images. The
  installed rootfs image alone is 4 GiB before compression; Android system
  backup extraction needs another approximately 4.2 GB.

The ARM64 rootfs builder uses a temporary QEMU/binfmt handler and `SYS_ADMIN`
inside its container; the handler is removed on exit. Containers do not receive
tablet USB devices or the Docker socket. Host kernel/GPU drivers are unchanged.

```sh
git clone --recurse-submodules https://github.com/victorQ8/tabs3-linux.git
cd tabs3-linux
git submodule update --init --recursive
bash scripts/build-env.sh
```

Source pins and hashes: [sources.json](../config/sources.json). Package
versions: [device.json](../config/device.json). Recorded device facts describe
the development tablet, not yours. Debian package repositories are live;
these steps are not a claim of bit-for-bit reproducibility.

## Kernel, packages, and bootloader

```sh
python3 scripts/prepare-lte-kernel.py
bash scripts/build-kernel.sh
bash scripts/build-kernel-package.sh
bash scripts/build-package.sh
bash scripts/build-dashboard-package.sh
bash scripts/build-sensors-package.sh
bash scripts/build-lk2nd.sh
bash scripts/build-lk2nd.sh --autoboot
bash scripts/build-recovery-ui.sh
```

The first lk2nd variant stops in fastboot; `--autoboot` builds the variant for
installed Debian. Both are needed for initial installation. Artifacts go to
`artifacts/`; no package or image is installed automatically.

Kernel objects default to Docker volume `tabs3-kernel-build-$KERNEL_DIR`, with
the directory from the source manifest. `TABS3_BUILD_VOLUME` overrides it.
lk2nd and recovery UI use separate volumes. The optional baseline check in
`scripts/check-kernel-baseline.sh` compiles the Wi-Fi reference DTB only.

## Personalized filesystem and initramfs

Complete [account setup](accounts.md), then:

```sh
bash scripts/build-rootfs.sh private/id_ed25519.pub
bash scripts/build-installed-rootfs.sh
bash scripts/build-initramfs.sh private/id_ed25519.pub
```

The builder tests ARM64 SSH under QEMU using a disposable key, restores your
authorized public key, and removes temporary host keys and the machine ID.

| Output | Purpose |
| --- | --- |
| `artifacts/tabs3-trixie-arm64-rootfs.tar.xz` | Personalized userspace, not independently bootable |
| `private/images/tabs3-debian-rootfs.ext4.gz` | Initial-install filesystem |
| `private/images/installed-rootfs.json` | Root UUID, sizes and hashes |
| `private/images/diagnostic-initramfs.cpio.gz` | Personalized initramfs |

Never rerun initial rootfs installation to update an existing system.

## Pack boot images

Use `boot.img` and its adjacent `manifest.json` from your own verified Android
backup. `YOUR_BACKUP` below is a placeholder:

```sh
DONOR="$PWD/private/backups/YOUR_BACKUP/boot.img"
bash scripts/pack-images.sh --donor "$DONOR"
bash scripts/pack-images.sh --mode storage-probe --donor "$DONOR"
ROOT_UUID=$(python3 -c 'import json; print(json.load(open("private/images/installed-rootfs.json"))["root_uuid"])')
bash scripts/pack-images.sh --mode installed --variant display \
    --root-uuid "$ROOT_UUID" --donor "$DONOR"
```

Packing checks the backup hash, Samsung boot header, board IDs, load-address
bounds, sizes, and root UUID. Output manifests contain SHA-256 values. First
installation uses `display`, which does not need Adreno firmware.

**Plain images** (for example `tabs3-storage-probe.img`) are for `fastboot boot`.
**Combined images** (`tabs3-internal-display-boot.img`) contain lk2nd plus Linux
at the reserved 4 MiB offset and are for the checked partition writer. They
are not interchangeable. Follow [installation](installation.md).

## Preview and test

On Debian, install `python3-pil`, `fonts-b612`, and `fonts-dejavu-core` for
matching previews. On other distributions, use their Pillow package and set
`TABS3_FONT_DIR` to an extracted Debian `/usr/share/fonts` tree if needed.

```sh
python3 tools/dashboard-preview
python3 -m unittest discover -s tests
```

Host tests do not prove driver behavior on hardware. For a committed revision:

```sh
bash scripts/ci.sh HEAD
```

This longer check clones the committed source, applies patches without fuzz,
compiles kernel/modules/DTBs, runs guards, and builds packages. Uncommitted
changes are excluded. `TABS3_CI_DIR` and `TABS3_CI_VOLUME` must be dedicated
disposable locations: the script recreates them. It never flashes hardware.
