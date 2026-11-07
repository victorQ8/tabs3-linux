#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p private/images
chmod 700 private private/images
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$PWD:/project:ro" -v "$PWD/private/images:/project/private/images" \
    tabs3-builder:trixie python3 scripts/pack-images.py "$@"
