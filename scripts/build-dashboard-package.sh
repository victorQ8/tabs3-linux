#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
version=$DASHBOARD_VERSION
grep -qx "Version: $version" packages/tabs3-dashboard/DEBIAN/control
mkdir -p artifacts
docker run --rm --user "$(id -u):$(id -g)" -e "DASHBOARD_VERSION=$version" \
    -v "$PWD:/project:ro" -v "$PWD/artifacts:/out" tabs3-builder:trixie bash -euc '
      stage=$(mktemp -d)
      trap '\''rm -rf "$stage"'\'' EXIT
      cp -a /project/packages/tabs3-dashboard/. "$stage/"
      python3 -m py_compile "$stage/usr/libexec/tabs3-dashboard" "$stage/usr/libexec/tabs3_dashboard_themes.py" "$stage/usr/libexec/tabs3_dashboard_silicon.py" "$stage/usr/libexec/tabs3_dashboard_power.py" "$stage/usr/bin/tabs3-dashboard-theme"
      find "$stage" -type d -name __pycache__ -prune -exec rm -rf {} +
      chmod 755 "$stage/usr/libexec/tabs3-dashboard" "$stage/DEBIAN/postinst" "$stage/DEBIAN/prerm" "$stage/DEBIAN/postrm"
      chmod 755 "$stage/usr/bin/tabs3-dashboard-theme"
      install -D -m 644 /project/LICENSE "$stage/usr/share/doc/tabs3-dashboard/copyright"
      find "$stage/etc" -type f -printf "/etc/%P\n" | sort > "$stage/DEBIAN/conffiles"
      dpkg-deb --root-owner-group --build "$stage" "/out/tabs3-dashboard_${DASHBOARD_VERSION}_all.deb"
    '
