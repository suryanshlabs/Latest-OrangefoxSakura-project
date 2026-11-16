#!/usr/bin/env bash
#
# run-all.sh - THE one command that builds OrangeFox R12.0 for sakura from a
# fresh clone on a compatible Linux x86_64 host.
#
#   ./build/run-all.sh [SOURCE_DIR]        # SOURCE_DIR defaults to $HOME/orangefox/fox_12.1
#
# It performs, in order, and stops at the first failure:
#   1. host preflight (disk, RAM, tools, repo)      - hard gates, no guessing
#   2. static regression checks                      - tools/static_checks.py
#   3. source sync at pinned refs  (skipped if the tree already has .repo)
#   4. prebuilt kernel fetch + DTB verification      (skipped if already present)
#   5. crypto-chain availability report              (never blocks; states the truth)
#   6. one production recoveryimage build            (build/build.sh)
#   7. hard structural verification                  (build/verify_image.sh)
#
# Requirements: Linux x86_64, not root, >=45 GB free (60 GB comfortable),
# >=8 GB RAM (16 GB recommended), and the packages in
# documentation/DEPENDENCIES.md section 1. JDK 11 is obtained automatically by
# build/setup_jdk11.sh if the host has none.
#
# A PASS here means "structurally verified image". It does NOT mean the
# recovery was booted, and it does NOT mean decryption works: those need the
# physical device (testing/android-*/TEST_RECORD.md).
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$HOME/orangefox/fox_12.1}"

die() { echo "ERROR: $*" >&2; exit 1; }

[ "$(id -u)" != "0" ] || die "do not build as root"
command -v repo >/dev/null || die "repo not found: https://storage.googleapis.com/git-repo-downloads/repo"
for t in git curl python3 rsync unzip zip bc bison flex gcc g++ make ccache cpio lz4; do
    command -v "$t" >/dev/null || die "missing build tool '$t' (documentation/DEPENDENCIES.md section 1)"
done

mem_mb=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 ))
[ "$mem_mb" -ge 7000 ] || die "need >=8 GB RAM, this host has ${mem_mb} MB"

mkdir -p "$(dirname "$DEST")"
avail_gb=$(df -BG --output=avail "$(dirname "$DEST")" | tail -1 | tr -dc '0-9')
[ "${avail_gb:-0}" -ge 45 ] || die "need >=45 GB free at $(dirname "$DEST"), have ${avail_gb} GB"

echo "############################################################"
echo "# OrangeFox R12.0 sakura build"
echo "#   source : $DEST"
echo "#   disk   : ${avail_gb} GB free   RAM: ${mem_mb} MB   cpus: $(nproc)"
echo "############################################################"

echo; echo "### 1/7 static checks"
python3 "$ROOT/tools/static_checks.py"

echo; echo "### 2/7 preflight complete"

echo; echo "### 3/7 source sync"
if [ -d "$DEST/.repo" ]; then
    echo "reusing existing tree at $DEST"
    "$ROOT/build/sync.sh" --relink-only "$DEST"
else
    "$ROOT/build/sync.sh" "$DEST"
fi

echo; echo "### 4/7 device tree + kernel"
mkdir -p "$DEST/device/xiaomi/sakura"
rsync -a --exclude 'prebuilt/Image.gz-dtb' \
      "$ROOT/device/xiaomi/sakura/" "$DEST/device/xiaomi/sakura/"
K="$DEST/device/xiaomi/sakura/prebuilt/Image.gz-dtb"
if [ -f "$K" ]; then
    echo "kernel already present:"; sha256sum "$K"
else
    "$ROOT/build/fetch_kernel.sh"
    install -D -m 0644 "$ROOT/device/xiaomi/sakura/prebuilt/Image.gz-dtb" "$K"
fi
python3 "$ROOT/tools/verify_dtb.py" "$K"

echo; echo "### 5/7 crypto chain"
"$ROOT/build/check_crypto_blobs.sh" "$DEST"

echo; echo "### 6/7 build"
"$ROOT/build/build.sh" "$DEST"      # includes hard structural verification

echo; echo "### 7/7 done"
IMG="$DEST/out/target/product/sakura/OrangeFox-unofficial-sakura.img"
[ -f "$IMG" ] || IMG="$DEST/out/target/product/sakura/recovery.img"
echo "image : $IMG"
echo "size  : $(stat -c %s "$IMG") bytes"
echo "sha256: $(sha256sum "$IMG" | cut -d' ' -f1)"
echo
echo "Next: flash MANUALLY at your own risk, or run the tests in testing/android-N/."
echo "Nothing here proves a boot or a decryption result."
