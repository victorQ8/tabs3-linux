#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/prepare-lte-kernel.py
source scripts/versions.sh
mkdir -p artifacts
# Objects stay in Docker storage rather than filling the user's home partition.
# TABS3_BUILD_VOLUME lets CI build from scratch without touching this volume.
volume=${TABS3_BUILD_VOLUME:-tabs3-kernel-build-$KERNEL_DIR}
docker volume create "$volume" >/dev/null
docker run --rm --name "$volume" \
    -v "$PWD:/project:ro" -v "$volume:/build" \
    -v "$PWD/artifacts:/out" \
    -e "OUTPUT_UID=$(id -u)" -e "OUTPUT_GID=$(id -g)" \
    -e "JOBS=${JOBS:-4}" -e KERNEL_DIR tabs3-builder:trixie \
    bash /project/build/kernel-container.sh
