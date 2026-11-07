#!/bin/bash
# Clean-room CI for a committed revision: fresh clone, pinned kernel source,
# patches applied with --fuzz=0, host tests, a from-scratch container build of
# the kernel, device trees and modules, the device-tree guards, no new compiler
# warnings in patched files, and the Debian packages.
#
#   scripts/ci.sh [REV]    (default HEAD; uncommitted changes are not tested)
#
# Build objects go to their own Docker volume (TABS3_CI_VOLUME, default
# tabs3-ci-build), recreated every run, so the development build volume is
# never touched. Nothing is flashed or sent to the tablet.
set -euo pipefail
cd "$(dirname "$0")/.."
src=$PWD
rev=$(git rev-parse --verify "${1:-HEAD}^{commit}")
ci=${TABS3_CI_DIR:-$src/work/ci}
volume=${TABS3_CI_VOLUME:-tabs3-ci-build}
jobs=${JOBS:-$(nproc)}
step() { printf '\n== %s\n' "$*"; }

docker image inspect tabs3-builder:trixie >/dev/null 2>&1 || bash scripts/build-env.sh
rm -rf "$ci"
mkdir -p "$ci/logs"

step "clone ${rev:0:12}"
git clone --quiet --no-checkout "$src" "$ci/tree"
git -C "$ci/tree" checkout --quiet --detach "$rev"
# Use local submodule checkouts when they exist, so CI works offline.
while read -r key path; do
    name=${key#submodule.}
    name=${name%.path}
    if [[ -e "$src/$path/.git" ]]; then
        git -C "$ci/tree" config "submodule.$name.url" "$src/$path"
    fi
done < <(git -C "$ci/tree" config -f .gitmodules --get-regexp '^submodule\..*\.path$')
git -C "$ci/tree" -c protocol.file.allow=always submodule --quiet update --init
# The pinned kernel archive is verified by SHA-512 in prepare-kernel.py.
mkdir -p "$ci/tree/work"
archive=$(python3 -c 'import json, posixpath, sys, urllib.parse
print(posixpath.basename(urllib.parse.urlparse(json.load(open(sys.argv[1]))["kernel"]["url"]).path))' \
    "$ci/tree/config/sources.json")
if [[ -f "$src/work/$archive" ]]; then
    ln "$src/work/$archive" "$ci/tree/work/" 2>/dev/null || cp "$src/work/$archive" "$ci/tree/work/"
fi
cd "$ci/tree"
if ! grep -q TABS3_BUILD_VOLUME scripts/build-kernel.sh ||
   ! grep -q TABS3_BUILD_VOLUME scripts/build-kernel-package.sh; then
    echo "${rev:0:12} predates separate CI build volumes; not building it" >&2
    exit 1
fi

step "host tests"
python3 -m unittest discover -s tests 2>&1 | tee "$ci/logs/tests.log" | tail -3

step "kernel source and patch stack (--fuzz=0)"
python3 scripts/prepare-lte-kernel.py > "$ci/logs/prepare.log"
grep -c '^Applying' "$ci/logs/prepare.log" | xargs printf '%s patches applied\n'

step "kernel and device trees, from scratch"
docker volume rm "$volume" >/dev/null 2>&1 || true
TABS3_BUILD_VOLUME=$volume JOBS=$jobs bash scripts/build-kernel.sh > "$ci/logs/kernel.log" 2>&1 ||
    { tail -30 "$ci/logs/kernel.log"; exit 1; }
tail -1 "$ci/logs/kernel.log"

step "modules and kernel package"
TABS3_BUILD_VOLUME=$volume JOBS=$jobs bash scripts/build-kernel-package.sh > "$ci/logs/package.log" 2>&1 ||
    { tail -30 "$ci/logs/package.log"; exit 1; }
tail -1 "$ci/logs/package.log"

step "device-tree guards"
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/project:ro" -w /project \
    tabs3-builder:trixie python3 tools/check-dtbs artifacts

step "compiler warnings in patched files"
patched=$(sed -n 's#^+++ b/\([^[:space:]]*\).*#\1#p' kernel/patches/*.patch | grep -v '\.yaml$' | sort -u)
warnings=$(grep -h -E '(warning|error):' "$ci/logs/kernel.log" "$ci/logs/package.log" |
           grep -F -f <(printf '%s\n' "$patched") || true)
if [[ -n "$warnings" ]]; then
    printf '%s\n' "$warnings"
    exit 1
fi
echo "none in $(wc -w <<<"$patched") patched files"

step "Debian packages"
bash scripts/build-package.sh > "$ci/logs/base.log" 2>&1 || { tail -20 "$ci/logs/base.log"; exit 1; }
bash scripts/build-desktop-package.sh > "$ci/logs/desktop.log" 2>&1 || { tail -20 "$ci/logs/desktop.log"; exit 1; }
bash scripts/build-sensors-package.sh > "$ci/logs/sensors.log" 2>&1 || { tail -20 "$ci/logs/sensors.log"; exit 1; }
bash scripts/build-dashboard-package.sh > "$ci/logs/dashboard.log" 2>&1 || { tail -20 "$ci/logs/dashboard.log"; exit 1; }
for deb in artifacts/*.deb; do basename "$deb"; done

docker volume rm "$volume" >/dev/null
step "CI passed for ${rev:0:12}; artifacts in $ci/tree/artifacts, logs in $ci/logs"
