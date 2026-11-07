#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
force_fastboot=1
force_recovery=0
recovery_fastboot=0
base=boot
suffix=
if [[ ${1:-} == --autoboot && $# -eq 1 ]]; then
    force_fastboot=0
    suffix=-auto
elif [[ ( ${1:-} == --recovery || ${1:-} == --recovery-fastboot ) && $# -eq 1 ]]; then
    # Second copy for the recovery partition: it reserves the start of
    # recovery instead of boot and always boots the image after it.
    force_fastboot=0
    force_recovery=1
    base=recovery
    suffix=-recovery
    if [[ $1 == --recovery-fastboot ]]; then
        recovery_fastboot=1
        suffix=-recovery-fastboot
    fi
elif [[ $# -ne 0 ]]; then
    echo "Usage: $0 [--autoboot|--recovery|--recovery-fastboot]" >&2
    exit 1
fi
expected=8b46487c4c76776c4f2f61468d44a74c69e6b9ea
[[ $(git -C upstream/lk2nd rev-parse HEAD) == "$expected" ]]
[[ -z $(git -C upstream/lk2nd status --porcelain) ]]
mkdir -p artifacts
docker volume create tabs3-lk2nd-build >/dev/null
docker run --rm --name tabs3-lk2nd-build \
    -v "$PWD:/project:ro" -v tabs3-lk2nd-build:/build \
    -v "$PWD/artifacts:/out" \
    -e "OUTPUT_UID=$(id -u)" -e "OUTPUT_GID=$(id -g)" \
    -e "FORCE_FASTBOOT=$force_fastboot" -e "FORCE_RECOVERY=$force_recovery" \
    -e "PARTITION_BASE=$base" -e "OUTPUT_SUFFIX=$suffix" \
    -e "RECOVERY_FASTBOOT=$recovery_fastboot" \
    tabs3-builder:trixie bash -euc '
      mkdir -p /build/src
      rsync -a --delete --exclude=.git /project/upstream/lk2nd/ /build/src/
      cp -a /project/bootloader/files/. /build/src/
      cp /project/bootloader/msm8996-samsung-gts3llte.dts /build/src/lk2nd/device/dts/msm8996/
      for p in /project/bootloader/patches/*.patch; do patch -s -p1 -d /build/src < "$p"; done
      make -C /build/src BOOTLOADER_OUT="/build/out$OUTPUT_SUFFIX" TOOLCHAIN_PREFIX=arm-none-eabi- \
        LK2ND_VERSION="tabs3-0.1.0-8b46487$OUTPUT_SUFFIX" LK2ND_PARTITION_SIZE=4194304 \
        LK2ND_FORCE_FASTBOOT="$FORCE_FASTBOOT" LK2ND_FORCE_RECOVERY="$FORCE_RECOVERY" \
        LK2ND_RECOVERY_FASTBOOT="$RECOVERY_FASTBOOT" \
        LK2ND_PARTITION_BASE="$PARTITION_BASE" LK2ND_ADTBS=msm8996-samsung-gts3llte.dtb \
        lk2nd-msm8996 -j2
      install -m 644 "/build/out$OUTPUT_SUFFIX/build-lk2nd-msm8996/lk.bin" "/out/lk2nd-sm-t825$OUTPUT_SUFFIX.bin"
      install -m 644 "/build/out$OUTPUT_SUFFIX/build-lk2nd-msm8996/lk2nd/device/dts/msm8996/msm8996-samsung-gts3llte.dtb" "/out/lk2nd-sm-t825$OUTPUT_SUFFIX.dtb"
      chown "$OUTPUT_UID:$OUTPUT_GID" "/out/lk2nd-sm-t825$OUTPUT_SUFFIX.bin" "/out/lk2nd-sm-t825$OUTPUT_SUFFIX.dtb"
    '
