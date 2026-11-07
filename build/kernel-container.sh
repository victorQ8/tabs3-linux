#!/bin/bash
set -euo pipefail
src=/project/work/${KERNEL_DIR:?}
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tabs3 KBUILD_BUILD_HOST=debian-builder
export KBUILD_BUILD_TIMESTAMP='2026-10-10 00:00:00 UTC'
export KCONFIG_CONFIG=/build/.config
cd /build
"$src/scripts/kconfig/merge_config.sh" -m -O /build \
    /project/work/kernel.config /project/kernel/bringup.config
make -C "$src" O=/build olddefconfig
for option in USB_CONFIGFS USB_F_NCM USB_DWC3 PHY_QCOM_QUSB2 QCOM_RPMPD DEVTMPFS BLK_DEV_INITRD RD_GZIP; do
    grep -qx "CONFIG_${option}=y" /build/.config || { echo "Missing built-in $option" >&2; exit 1; }
done
make -C "$src" O=/build -j"$JOBS" Image.gz qcom/msm8996-samsung-gts3llte.dtb \
    qcom/msm8996-samsung-gts3llte-emmc.dtb qcom/msm8996-samsung-gts3llte-display.dtb \
    qcom/msm8996-samsung-gts3llte-gpu.dtb
release=$(make -s -C "$src" O=/build kernelrelease)
install -m 644 /build/arch/arm64/boot/Image.gz "/out/Image-$release.gz"
install -m 644 /build/arch/arm64/boot/dts/qcom/msm8996-samsung-gts3llte.dtb /out/
install -m 644 /build/arch/arm64/boot/dts/qcom/msm8996-samsung-gts3llte-emmc.dtb /out/
install -m 644 /build/arch/arm64/boot/dts/qcom/msm8996-samsung-gts3llte-display.dtb /out/
install -m 644 /build/arch/arm64/boot/dts/qcom/msm8996-samsung-gts3llte-gpu.dtb /out/
install -m 644 /build/.config "/out/config-$release"
install -m 644 /build/System.map "/out/System.map-$release"
printf '%s\n' "$release" > /out/kernel-release.txt
chown "$OUTPUT_UID:$OUTPUT_GID" "/out/Image-$release.gz" "/out/config-$release" \
    "/out/System.map-$release" /out/kernel-release.txt /out/msm8996-samsung-gts3llte*.dtb
echo "Kernel and LTE DTBs built: $release. New variants require hardware validation."
