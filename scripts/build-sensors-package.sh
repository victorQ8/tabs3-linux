#!/bin/bash
# Build tabs3-sensors: sns-reg from third_party/ with the image-mode patch,
# cross-compiled for ARM64, plus the service unit and the sensor udev rule.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/versions.sh
grep -qx "Version: $SENSORS_VERSION" packages/tabs3-sensors/DEBIAN/control
mkdir -p artifacts
docker build -q -t tabs3-ui-builder:trixie -f build/ui-builder.Dockerfile build >/dev/null
docker build -q -t tabs3-sensors-builder:trixie -f build/sensors-builder.Dockerfile build >/dev/null
docker run --rm --user "$(id -u):$(id -g)" -e SENSORS_VERSION \
    -v "$PWD:/project:ro" -v "$PWD/artifacts:/out" tabs3-sensors-builder:trixie bash -euc '
      work=$(mktemp -d)
      trap '\''rm -rf "$work"'\'' EXIT
      cp -a /project/third_party/sns-reg "$work/src"
      patch -d "$work/src" -p1 --fuzz=0 -s < /project/third_party/sns-reg-image-mode.patch
      cd "$work/src"
      aarch64-linux-gnu-gcc -O2 -Wall -Wno-unused-variable -fstack-protector-strong \
          -D_FORTIFY_SOURCE=2 -fPIE -pie -Wl,-z,relro,-z,now \
          -o sns-reg main.c qmi/sns_reg.c map.c -lqrtr
      aarch64-linux-gnu-strip sns-reg
      stage="$work/stage"
      cp -a /project/packages/tabs3-sensors/. "$stage/"
      install -D -m 755 sns-reg "$stage/usr/libexec/tabs3-sns-reg"
      chmod 755 "$stage/DEBIAN/postinst" "$stage/DEBIAN/prerm"
      install -d "$stage/usr/share/doc/tabs3-sensors"
      {
          echo "/usr/libexec/tabs3-sns-reg is sns-reg by Yassine Oudjana,"
          echo "https://gitlab.com/msm8996-mainline/sns-reg commit"
          echo "4d238e5f0baba3fb77456fe2bffbf8e8f18a71a0, with the tabS3 image-mode patch"
          echo "(third_party/ in the tabS3 repository). License: GPL-3.0-or-later;"
          echo "on Debian systems the full text is /usr/share/common-licenses/GPL-3."
          echo
          echo "The other files are from the tabS3 project:"
          echo
          cat /project/LICENSE
      } > "$stage/usr/share/doc/tabs3-sensors/copyright"
      dpkg-deb --root-owner-group --build "$stage" "/out/tabs3-sensors_${SENSORS_VERSION}_arm64.deb"
    '
