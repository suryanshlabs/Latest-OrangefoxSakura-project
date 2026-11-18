#!/usr/bin/env bash
#
# run-all.sh - THE one command that builds OrangeFox R12.0 for sakura from a
# fresh clone on a compatible Linux x86_64 host.
#
#   ./build/run-all.sh [SOURCE_DIR]        # SOURCE_DIR defaults to $HOME/orangefox/fox_12.1
#
# No other argument, environment variable or manual step is required.
#
# It performs, in order, and stops at the first failure:
#   1. host preflight (tools, disk, RAM, root)       - build/check_deps.sh
#   2. static regression checks                      - tools/static_checks.py
#   3. TEE blob preparation + decryption gate        - build/install_blobs.sh,
#                                                      build/check_crypto_blobs.sh
#   4. source sync at pinned refs  (skipped if the tree already has .repo)
#   5. device tree + prebuilt kernel + DTB verification
#   6. decryption gate against the synced tree
#   7. one production recoveryimage build            - build/build.sh
#   8. hard structural + init-service verification   - build/verify_image.sh
#
# THE ONE INPUT YOU MUST SUPPLY
# -----------------------------
# Step 3 needs the vendor TEE chain (qseecomd, QTI Keymaster 3.0, QTI
# Gatekeeper 1.0 + libraries). They are Xiaomi/Qualcomm proprietary code and
# are neither committed here nor downloadable by this repository. Extract them
# once from YOUR OWN sakura Android 9 stock fastboot ROM:
#
#   ./build/extract_blobs.sh --firmware <sakura fastboot ROM>.tgz
#   ./build/install_blobs.sh
#
# Without that, step 3 stops with instructions instead of producing an image
# that claims decryption support it does not have. To build an explicitly
# no-decryption image for other work:
#
#   SAKURA_ALLOW_MISSING_CRYPTO=1 ./build/run-all.sh
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

echo "############################################################"
echo "# OrangeFox R12.0 sakura build"
echo "#   repository : $ROOT"
echo "#   source     : $DEST"
echo "#   mode       : $([ "${SAKURA_ALLOW_MISSING_CRYPTO:-0}" = 1 ] \
        && echo 'NO-DECRYPTION (SAKURA_ALLOW_MISSING_CRYPTO=1)' || echo 'full (decryption gate enforced)')"
echo "############################################################"

echo; echo "### 1/8 host preflight"
# Full preflight for a real build; the old inline checks here duplicated it.
"$ROOT/build/check_deps.sh" --dest "$DEST"

echo; echo "### 2/8 static checks"
python3 "$ROOT/tools/static_checks.py"

echo; echo "### 3/8 TEE blobs (proprietary, user-supplied)"
if [ -f "$ROOT/vendor_blobs/MANIFEST.sha256" ]; then
    "$ROOT/build/install_blobs.sh"
else
    echo "no vendor_blobs/ set found in this clone"
fi
if [ "${SAKURA_ALLOW_MISSING_CRYPTO:-0}" = 1 ]; then
    echo "SAKURA_ALLOW_MISSING_CRYPTO=1: decryption gate skipped by request"
    echo "the image from this run cannot decrypt /data"
    "$ROOT/build/check_crypto_blobs.sh" || true
else
    "$ROOT/build/check_crypto_blobs.sh" --require || die \
        "TEE blob gate failed - see the instructions above (documentation/DEPENDENCIES.md section 4)"
fi

echo; echo "### 4/8 source sync"
if [ -d "$DEST/.repo" ]; then
    echo "reusing existing tree at $DEST"
    "$ROOT/build/sync.sh" --relink-only "$DEST"
else
    "$ROOT/build/sync.sh" "$DEST"
fi

echo; echo "### 5/8 device tree + kernel"
mkdir -p "$DEST/device/xiaomi/sakura"
rsync -a --exclude 'prebuilt/Image.gz-dtb' \
      "$ROOT/device/xiaomi/sakura/" "$DEST/device/xiaomi/sakura/"
# Theme patch (Settings -> Error Logs + status-bar badge). Idempotent and
# fail-closed on a changed upstream context.
"$ROOT/build/apply_patches.sh" --src "$DEST"
K="$DEST/device/xiaomi/sakura/prebuilt/Image.gz-dtb"
if [ -f "$K" ]; then
    echo "kernel already present:"; sha256sum "$K"
else
    "$ROOT/build/fetch_kernel.sh"
    install -D -m 0644 "$ROOT/device/xiaomi/sakura/prebuilt/Image.gz-dtb" "$K"
fi
python3 "$ROOT/tools/verify_dtb.py" "$K"

echo; echo "### 6/8 decryption gate on the synced tree"
if [ "${SAKURA_ALLOW_MISSING_CRYPTO:-0}" = 1 ]; then
    "$ROOT/build/check_crypto_blobs.sh" "$DEST" || true
else
    "$ROOT/build/check_crypto_blobs.sh" --require "$DEST"
fi

echo; echo "### 7/8 build"
"$ROOT/build/build.sh" "$DEST"      # includes hard structural verification

echo; echo "### 8/8 done"
IMG="$DEST/out/target/product/sakura/OrangeFox-unofficial-sakura.img"
[ -f "$IMG" ] || IMG="$DEST/out/target/product/sakura/recovery.img"
echo "image : $IMG"
echo "size  : $(stat -c %s "$IMG") bytes"
echo "sha256: $(sha256sum "$IMG" | cut -d' ' -f1)"
echo
if [ "${SAKURA_ALLOW_MISSING_CRYPTO:-0}" = 1 ]; then
    echo "This image was built WITHOUT the TEE chain: it cannot decrypt /data."
fi
echo "Next: flash MANUALLY at your own risk, or run the tests in testing/android-N/."
echo "Nothing here proves a boot or a decryption result."
