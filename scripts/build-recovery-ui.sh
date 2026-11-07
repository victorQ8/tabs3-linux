#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Build the recovery screen for the tablet (artifacts/tabs3-recovery-ui).
# With --preview DIR, also render its screens on this PC as PNG files.
expected=c016f72d4c125098287be5e83c0f1abed4706ee5
[[ $(git -C upstream/lvgl rev-parse HEAD) == "$expected" ]]
[[ -z $(git -C upstream/lvgl status --porcelain) ]]
preview=
if [[ ${1:-} == --preview && $# -eq 2 ]]; then
    preview=$(realpath "$2")
    mkdir -p "$preview"
elif [[ $# -ne 0 ]]; then
    echo "Usage: $0 [--preview DIR]" >&2
    exit 1
fi
docker build -q -t tabs3-ui-builder:trixie -f build/ui-builder.Dockerfile build >/dev/null
docker volume create tabs3-ui-build >/dev/null
mkdir -p artifacts
run=(docker run --rm -v "$PWD:/project:ro" -v tabs3-ui-build:/build -v "$PWD/artifacts:/out"
     -e "OUTPUT_UID=$(id -u)" -e "OUTPUT_GID=$(id -g)")
# shellcheck disable=SC2016 # expanded inside the container
"${run[@]}" tabs3-ui-builder:trixie bash -euc '
    make -s -C /project/recovery-ui -j"$(nproc)" TARGET=arm64 OUT=/build/arm64 LVGL_PATH=/project/upstream/lvgl
    make -s -C /project/recovery-ui -j"$(nproc)" TARGET=preview OUT=/build/preview LVGL_PATH=/project/upstream/lvgl
    /build/preview/tabs3-recovery-ui --test-hitboxes
    install -m 755 /build/arm64/tabs3-recovery-ui /out/tabs3-recovery-ui
    aarch64-linux-gnu-gcc -Os -Wall -Wextra -Werror -static \
        /project/recovery-ui/reboot-recovery.c -o /out/tabs3-reboot-recovery
    aarch64-linux-gnu-strip /out/tabs3-reboot-recovery
    chown "$OUTPUT_UID:$OUTPUT_GID" /out/tabs3-recovery-ui /out/tabs3-reboot-recovery'
ls -l artifacts/tabs3-recovery-ui
if [[ -n $preview ]]; then
    # shellcheck disable=SC2016 # expanded inside the container
    "${run[@]}" -v "$preview:/preview" tabs3-ui-builder:trixie bash -euc '
        make -s -C /project/recovery-ui -j"$(nproc)" TARGET=preview OUT=/build/preview LVGL_PATH=/project/upstream/lvgl
        /build/preview/tabs3-recovery-ui /preview
        chown "$OUTPUT_UID:$OUTPUT_GID" /preview/*.ppm'
    python3 - "$preview" <<'PY'
import pathlib, sys
from PIL import Image
for ppm in sorted(pathlib.Path(sys.argv[1]).glob('*.ppm')):
    Image.open(ppm).save(ppm.with_suffix('.png'))
    ppm.unlink()
    print(ppm.with_suffix('.png'))
PY
fi
