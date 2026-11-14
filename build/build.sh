#!/usr/bin/env bash
#
# build.sh - build OrangeFox R12.0 for sakura.
#
# Usage: ./build/build.sh /absolute/path/to/fox_12.1 [target]
#        target defaults to recoveryimage
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-}"
TARGET="${2:-recoveryimage}"

[ -n "$SRC" ] || { echo "usage: $0 /absolute/path/to/fox_12.1 [target]" >&2; exit 1; }
[ -d "$SRC/build" ] || { echo "ERROR: $SRC does not look like an AOSP tree" >&2; exit 1; }
[ -f "$SRC/device/xiaomi/sakura/prebuilt/Image.gz-dtb" ] || {
    echo "ERROR: prebuilt kernel missing. Run ./build/fetch_kernel.sh first." >&2
    echo "       (or rebuild it - device/xiaomi/sakura/prebuilt/README.md)" >&2
    exit 1
}

cd "$SRC"
# shellcheck disable=SC1091
. build/envsetup.sh

# OrangeFox needs this on legacy SoC trees; missing repos exist in the minimal
# manifest by design.
export ALLOW_MISSING_DEPENDENCIES=true
export LC_ALL=C

echo "==> lunch fox_sakura-eng"
lunch fox_sakura-eng

echo "==> mka ${TARGET}  (log: ${ROOT}/reference/build-\$(date +%s).log)"
mkdir -p "${ROOT}/reference"
LOG="${ROOT}/reference/build-$(date +%Y%m%d-%H%M%S).log"
set +e
mka "${TARGET}" 2>&1 | tee "${LOG}"
status=${PIPESTATUS[0]}
set -e

echo
echo "==> build finished with status ${status}; full log: ${LOG}"
if [ "$status" != 0 ]; then
    echo "First errors:" >&2
    grep -nE 'error:|Error [0-9]+|FAILED' "$LOG" | head -40 >&2 || true
    exit "$status"
fi

OUT="out/target/product/sakura"
ls -l "$OUT"/*.img 2>/dev/null || true
echo
echo "Expected OrangeFox image: $OUT/OrangeFox-unofficial-sakura.img"
echo "Now run: ./build/verify_image.sh $SRC"
