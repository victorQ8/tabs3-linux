#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
[[ -x artifacts/tabs3-recovery-ui ]] || { echo 'Run scripts/build-recovery-ui.sh first' >&2; exit 1; }
[[ $# -eq 1 ]] || { echo "Usage: $0 SSH_PUBLIC_KEY" >&2; exit 1; }
key=$(realpath "$1")
ssh-keygen -lf "$key" >/dev/null
# Keep the entire personalized image private, as well as the source public key.
mkdir -p private/images
chmod 700 private private/images
docker run --rm --name tabs3-initramfs-build \
    --cap-add SYS_ADMIN --security-opt apparmor=unconfined \
    -v /proc/sys/fs/binfmt_misc:/binfmt \
    -v "$PWD:/project:ro" -v "$PWD/private/images:/out" \
    -v "$key:/authorized_keys:ro" \
    -e "OUTPUT_UID=$(id -u)" -e "OUTPUT_GID=$(id -g)" -e KERNEL_PACKAGE_VERSION \
    tabs3-builder:trixie bash /project/build/initramfs-container.sh
