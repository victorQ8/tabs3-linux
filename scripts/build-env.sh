#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -t tabs3-builder:trixie build
mkdir -p artifacts
docker image inspect tabs3-builder:trixie --format '{{.Id}}' > artifacts/builder-image-id.txt
docker run --rm tabs3-builder:trixie dpkg-query -W > artifacts/builder-packages.tsv
