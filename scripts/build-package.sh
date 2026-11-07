#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
if ! grep -qx "Version: $TABS3_BASE_VERSION" packages/tabs3-base/DEBIAN/control ||
   ! grep -qx "VERSION=$TABS3_BASE_VERSION" packages/tabs3-base/etc/tabs3-release; then
    echo "tabs3-base version files differ from config/device.json ($TABS3_BASE_VERSION)" >&2
    exit 1
fi
mkdir -p artifacts
docker run --rm --user "$(id -u):$(id -g)" -e TABS3_BASE_VERSION \
    -v "$PWD:/project:ro" -v "$PWD/artifacts:/out" \
    tabs3-builder:trixie bash -euc '
      stage=$(mktemp -d)
      trap '\''rm -rf "$stage"'\'' EXIT
      cp -a /project/packages/tabs3-base/. "$stage/"
      install -D -m 644 /project/initramfs/fastboot-request.sh "$stage/usr/lib/tabs3/fastboot-request.sh"
      chmod 0755 "$stage/usr/sbin/tabs3-fastboot"
      python3 -m py_compile "$stage/usr/libexec/tabs3_camera.py" "$stage/usr/bin/tabs3-snapshot"
      find "$stage" -type d -name __pycache__ -prune -exec rm -rf -- {} +
      find "$stage" -type f -name "*.pyc" -delete
      chmod 0755 "$stage/usr/sbin/tabs3-server-enable"
      chmod 0755 "$stage/usr/sbin/tabs3-server-maintenance"
      chmod 0755 "$stage/usr/libexec/tabs3-wifi-address" "$stage/usr/libexec/tabs3-rtc-offset"
      chmod 0755 "$stage/usr/libexec/tabs3-server-cpu-limit"
      chmod 0755 "$stage/usr/libexec/tabs3-server-health" "$stage/usr/libexec/tabs3-battery-keeper"
      chmod 0755 "$stage/usr/libexec/tabs3-power-guard"
      chmod 0755 "$stage/usr/bin/tabs3-production-check"
      chmod 0755 "$stage/usr/libexec/tabs3-usb-gadget" "$stage/usr/libexec/tabs3-wifi-pcie" "$stage/usr/libexec/tabs3-bt-address" "$stage/usr/libexec/tabs3-screen" "$stage/usr/libexec/tabs3-wifi-board" "$stage/usr/libexec/tabs3-install-dsp-firmware" "$stage/usr/bin/tabs3-modem-status" "$stage/usr/bin/tabs3-usb-host" "$stage/usr/bin/tabs3-snapshot"
      find "$stage/etc" -type f -printf "/etc/%P\n" | sort > "$stage/DEBIAN/conffiles"
      dpkg-deb --root-owner-group --build "$stage" "/out/tabs3-base_${TABS3_BASE_VERSION}_all.deb"
    '
