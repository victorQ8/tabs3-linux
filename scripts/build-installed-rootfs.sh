#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
mkdir -p private/images
chmod 700 private private/images
[[ -f "artifacts/linux-tabs3_${KERNEL_PACKAGE_VERSION}_arm64.deb" ]]
[[ -f artifacts/tabs3-trixie-arm64-rootfs.tar.xz ]]
bash scripts/build-package.sh
docker run --rm --name tabs3-installed-rootfs-build \
    --cap-add SYS_ADMIN --security-opt apparmor=unconfined \
    -v /proc/sys/fs/binfmt_misc:/binfmt \
    -v "$PWD:/project:ro" -v "$PWD/private/images:/out" \
    -e "OUTPUT_UID=$(id -u)" -e "OUTPUT_GID=$(id -g)" -e TABS3_BASE_VERSION -e KERNEL_PACKAGE_VERSION \
    tabs3-builder:trixie bash /project/build/installed-rootfs-container.sh
