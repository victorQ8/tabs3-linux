#!/bin/bash
set -euo pipefail
src=/project/work/${KERNEL_DIR:?}
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tabs3 KBUILD_BUILD_HOST=debian-builder
export KBUILD_BUILD_TIMESTAMP='2026-10-10 00:00:00 UTC'
release=$(make -s -C "$src" O=/build kernelrelease)
version=${KERNEL_PACKAGE_VERSION:?}
[[ "$release" == "$(cat /out/kernel-release.txt)" ]]
cmp /build/.config "/out/config-$release"
make -C "$src" O=/build -j"$JOBS" modules
pkg=$(mktemp -d)
trap 'rm -rf "$pkg"' EXIT
make -C "$src" O=/build INSTALL_MOD_PATH="$pkg" INSTALL_MOD_STRIP=1 modules_install
rm -f "$pkg/lib/modules/$release/build" "$pkg/lib/modules/$release/source"
depmod -b "$pkg" "$release"
mkdir -p "$pkg/DEBIAN" "$pkg/boot/dtbs/$release" "$pkg/usr/share/doc/linux-tabs3"
install -m 644 "/out/Image-$release.gz" "$pkg/boot/vmlinuz-$release"
install -m 644 "/out/config-$release" "$pkg/boot/config-$release"
install -m 644 "/out/System.map-$release" "$pkg/boot/System.map-$release"
install -m 644 /out/msm8996-samsung-gts3llte.dtb "$pkg/boot/dtbs/$release/"
install -m 644 /out/msm8996-samsung-gts3llte-emmc.dtb "$pkg/boot/dtbs/$release/"
install -m 644 /out/msm8996-samsung-gts3llte-display.dtb "$pkg/boot/dtbs/$release/"
install -m 644 /out/msm8996-samsung-gts3llte-gpu.dtb "$pkg/boot/dtbs/$release/"
cat > "$pkg/DEBIAN/control" <<EOF
Package: linux-tabs3
Version: ${version}
Architecture: arm64
Maintainer: tabS3 project <noreply@localhost>
Section: kernel
Priority: optional
Depends: kmod
Description: Experimental Galaxy Tab S3 LTE kernel and modules
 Linux ${release} with RAM-only and initial eMMC device trees.
 The full Debian variant uses qualified HS400; recovery and initial eMMC
 variants retain a 52 MHz cap.
 Includes PS_HOLD reboot and an experimental dual-DSI display/touch variant.
 This package does not install a bootloader or flash tablet partitions.
EOF
cat > "$pkg/usr/share/doc/linux-tabs3/README" <<EOF
Experimental SM-T825 kernel. RAM boot and USB SSH were verified on hardware.
The base device tree disables storage; the -emmc/display variants use 52 MHz.
The full -gpu Debian variant supports HS400 at up to 200 MHz (192 MHz measured).
The display variant uses DPU with MSM8996 split CTL capabilities and
SM-T825 LP11 clock ordering. Console, recovery graphics, full panel wake,
touch, Wi-Fi, battery reporting and temperature-controlled charging were
tested on SM-T825 rev05. CPU idle, AP thermistor and watchdog are enabled;
system suspend and complete peripheral/long-duration qualification remain open. Hardware details are in docs/hardware-sm-t825.md.
Installing this package copies files only; it does not generate or flash
Android boot images. Use the project image builder for RAM diagnostics.
Source baseline and patches: config/sources.json, upstream submodules,
kernel/ and scripts/prepare-lte-kernel.py in the tabS3 project.
EOF
cp "$src/COPYING" "$pkg/usr/share/doc/linux-tabs3/copyright"
dpkg-deb --root-owner-group --build "$pkg" "/out/linux-tabs3_${version}_arm64.deb.partial"
mv "/out/linux-tabs3_${version}_arm64.deb.partial" "/out/linux-tabs3_${version}_arm64.deb"
chown "$OUTPUT_UID:$OUTPUT_GID" "/out/linux-tabs3_${version}_arm64.deb"
echo "Built linux-tabs3_${version}_arm64.deb with loadable modules; no flashing hooks."
