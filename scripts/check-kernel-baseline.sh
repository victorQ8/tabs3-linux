#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
[[ -f "work/$KERNEL_DIR/.tabs3-prepared" ]] || {
    echo 'Run python3 scripts/prepare-kernel.py first' >&2; exit 1;
}
mkdir -p work/kernel-check artifacts
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$PWD:/project:ro" -v "$PWD/work/kernel-check:/build" \
    -e KERNEL_DIR tabs3-builder:trixie bash -euc '
      src=/project/work/$KERNEL_DIR
      cp /project/work/kernel.config /build/.config
      make -C "$src" O=/build ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
      make -C "$src" O=/build ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 qcom/apq8096-samsung-gts3lwifi.dtb
    '
echo 'Upstream Wi-Fi reference DTB compiles. LTE DTB remains unimplemented.' > artifacts/kernel-baseline-validation.txt
