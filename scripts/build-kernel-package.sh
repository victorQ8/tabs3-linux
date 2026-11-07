#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
[[ -f artifacts/kernel-release.txt ]] || { echo 'Build the kernel first' >&2; exit 1; }
volume=${TABS3_BUILD_VOLUME:-tabs3-kernel-build-$KERNEL_DIR}
docker run --rm --name "$volume-package" \
    -v "$PWD:/project:ro" -v "$volume:/build" \
    -v "$PWD/artifacts:/out" \
    -e "OUTPUT_UID=$(id -u)" -e "OUTPUT_GID=$(id -g)" \
    -e "JOBS=${JOBS:-4}" -e KERNEL_PACKAGE_VERSION -e KERNEL_DIR tabs3-builder:trixie \
    bash /project/build/kernel-package-container.sh
