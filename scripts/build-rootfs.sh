#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
key=${1:?Usage: bash scripts/build-rootfs.sh /path/to/ssh-public-key.pub}
key=$(realpath "$key")
ssh-keygen -lf "$key" >/dev/null
[[ "$key" == *.pub ]] || { echo 'Supply a public .pub file, never a private key' >&2; exit 1; }
[[ -f private/dev-password.hash ]] || { echo 'Run scripts/set-dev-password.sh first (console login)' >&2; exit 1; }
[[ -f "artifacts/tabs3-base_${TABS3_BASE_VERSION}_all.deb" ]] || { echo 'Run scripts/build-package.sh first' >&2; exit 1; }
mkdir -p artifacts
# SYS_ADMIN permits mmdebstrap mounts and a temporary, task-specific ARM64
# binfmt entry. The container gets no tablet devices or Docker socket.
docker run --rm --cap-add SYS_ADMIN --security-opt apparmor=unconfined \
    --mount type=bind,src=/proc/sys/fs/binfmt_misc,dst=/binfmt \
    -v "$PWD:/project:ro" -v "$PWD/artifacts:/out" \
    -v "$key:/run/tabs3-authorized-key.pub:ro" \
    -v "$PWD/private/dev-password.hash:/run/tabs3-dev-password.hash:ro" \
    -e "OUTPUT_UID=$(id -u)" -e "OUTPUT_GID=$(id -g)" -e TABS3_BASE_VERSION \
    tabs3-builder:trixie bash /project/build/rootfs-container.sh
