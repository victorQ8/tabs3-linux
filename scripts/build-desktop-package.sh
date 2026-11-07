#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
version=$DESKTOP_VERSION
grep -qx "Version: $version" packages/tabs3-desktop/DEBIAN/control
mkdir -p artifacts
docker run --rm --user "$(id -u):$(id -g)" -e "DESKTOP_VERSION=$version" \
    -v "$PWD:/project:ro" -v "$PWD/artifacts:/out" tabs3-builder:trixie bash -euc '
      stage=$(mktemp -d)
      trap '\''rm -rf "$stage"'\'' EXIT
      cp -a /project/packages/tabs3-desktop/. "$stage/"
      find "$stage" -type d -name __pycache__ -prune -exec rm -rf {} +
      find "$stage" -type f -name "*.py[co]" -delete
      install -D -m 755 /project/tools/install-gpu-firmware "$stage/usr/libexec/tabs3-install-gpu-firmware"
      install -D -m 644 /project/LICENSE "$stage/usr/share/doc/tabs3-desktop/copyright"
      chmod 755 "$stage/usr/sbin/tabs3-desktop-enable"
      chmod 755 "$stage/usr/libexec/tabs3-import-iwd"
      find "$stage/etc" -type f -printf "/etc/%P\n" | sort > "$stage/DEBIAN/conffiles"
      dpkg-deb --root-owner-group --build "$stage" "/out/tabs3-desktop_${DESKTOP_VERSION}_all.deb"
    '
