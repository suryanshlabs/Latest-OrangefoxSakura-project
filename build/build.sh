#!/usr/bin/env bash
#
# build.sh - build OrangeFox R12.0 (fox_12.1) for sakura.
#
# Usage: ./build/build.sh /absolute/path/to/fox_12.1 [target]
#        target defaults to recoveryimage
#
# This script is the single source of truth for a build: the GitHub workflow
# calls it too, so a local run and a CI run execute the same commands.
#
# It hard-fails (never warns) when:
#   * the tree is missing, the prebuilt kernel is missing, or disk is short;
#   * build/envsetup.sh cannot be sourced (the failure that produced
#     TARGET_PRODUCT=aosp_arm and the "Could not find ui.xml for TW_THEME"
#     Soong error in earlier runs);
#   * lunch does not select fox_sakura-eng;
#   * no image newer than the build start exists afterwards;
#   * structural verification fails.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-}"
TARGET="${2:-recoveryimage}"

die() { echo "ERROR: $*" >&2; exit 1; }

[ -n "$SRC" ] || die "usage: $0 /absolute/path/to/fox_12.1 [target]"
[ -d "$SRC/build" ] || die "$SRC does not look like an AOSP tree (no build/)"
[ -d "$SRC/.repo" ] || echo "WARNING: $SRC has no .repo; continuing with an existing checkout"
[ -f "$SRC/device/xiaomi/sakura/prebuilt/Image.gz-dtb" ] || {
    echo "ERROR: prebuilt kernel missing. Run ./build/fetch_kernel.sh first." >&2
    echo "       (or rebuild it - device/xiaomi/sakura/prebuilt/README.md)" >&2
    exit 1
}

avail_gb=$(df -BG --output=avail "$SRC" | tail -1 | tr -dc '0-9')
[ "${avail_gb:-0}" -ge 20 ] || die "need >=20 GB free inside $SRC for build output, have ${avail_gb} GB"

# --- host preflight (tools only; disk/RAM are checked above and by run-all) --
"$ROOT/build/check_deps.sh" --quick --dest "$SRC" || die \
    "host is missing required build tooling (output above lists the packages)"

# --- decryption gate --------------------------------------------------------
# An image built without the vendor TEE chain cannot decrypt anything, and
# every previous artefact of this port claimed FDE/FBE support while missing
# that chain. The gate is therefore fatal by default.
#
# SAKURA_ALLOW_MISSING_CRYPTO=1 builds an explicitly no-decryption image for
# other work (UI, partitioning, backup). It does not make decryption work; the
# resulting image must never be reported as decrypting, and the workflow input
# of the same name carries the same restriction.
if [ "${SAKURA_ALLOW_MISSING_CRYPTO:-0}" = 1 ]; then
    echo "==> WARNING: SAKURA_ALLOW_MISSING_CRYPTO=1 - skipping the TEE blob gate"
    echo "    The image produced by this run CANNOT decrypt /data. Do not report"
    echo "    FDE/FBE as working for it."
    "$ROOT/build/check_crypto_blobs.sh" "$SRC" || true
else
    "$ROOT/build/check_crypto_blobs.sh" --require "$SRC" || die \
        "TEE blob gate failed; see documentation/DEPENDENCIES.md section 4"
fi

# --- JDK 11 -----------------------------------------------------------------
# Soong 12.1 requires JDK 11. Prefer an existing JAVA_HOME, otherwise obtain the
# portable Temurin build (no root needed) and make it win in PATH. Exported
# before envsetup because soong_ui reads ANDROID_JAVA_HOME at configure time.
if [ -z "${JAVA_HOME:-}" ] || ! "$JAVA_HOME/bin/java" -version 2>&1 | grep -q 'version "11'; then
    JAVA_HOME="$("$ROOT/build/setup_jdk11.sh")"
fi
export JAVA_HOME
export ANDROID_JAVA_HOME="$JAVA_HOME"
export PATH="$JAVA_HOME/bin:$PATH"
echo "==> JDK: $("$JAVA_HOME/bin/java" -version 2>&1 | head -1) ($JAVA_HOME)"

cd "$SRC"

# --- never let a stale image satisfy the verifier ---------------------------
OUT="out/target/product/sakura"
rm -f "$OUT/OrangeFox-unofficial-sakura.img" "$OUT/recovery.img"
BUILD_START=$(date +%s)

# --- envsetup ---------------------------------------------------------------
LOG="${ROOT}/reference/build-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "${ROOT}/reference"
ENVSETUP_LOG="${ROOT}/reference/envsetup-$(date +%Y%m%d-%H%M%S).log"
echo "==> sourcing build/envsetup.sh (log: $ENVSETUP_LOG)"

# nounset MUST be off while sourcing: envsetup.sh reads unset variables (TOP,
# ZSH_VERSION, ...) and aborts under `set -u` before lunch() is defined.
set +u
. build/envsetup.sh >"$ENVSETUP_LOG" 2>&1
es=$?
set -u
if [ "$es" != 0 ]; then
    echo "==> envsetup.sh failed with status $es; last 80 lines:" >&2
    tail -80 "$ENVSETUP_LOG" >&2 || true
    die "build/envsetup.sh failed; the build cannot select a lunch target"
fi
command -v lunch >/dev/null 2>&1 || {
    tail -80 "$ENVSETUP_LOG" >&2 || true
    die "build/envsetup.sh did not define lunch()"
}

export ALLOW_MISSING_DEPENDENCIES=true
export LC_ALL=C
export JACK_SERVER_VM_ARGUMENTS="-Dfile.encoding=UTF-8"

# --- lunch ------------------------------------------------------------------
echo "==> lunch fox_sakura-eng"
set +e
lunch fox_sakura-eng 2>&1 | tee -a "$LOG"
lunch_status=${PIPESTATUS[0]}
set -e
[ "$lunch_status" = 0 ] || die "lunch fox_sakura-eng failed with status $lunch_status"
[ "${TARGET_PRODUCT:-}" = "fox_sakura" ] || die "lunch selected TARGET_PRODUCT='${TARGET_PRODUCT:-<unset>}', expected fox_sakura"
echo "==> TARGET_PRODUCT=$TARGET_PRODUCT TARGET_BUILD_VARIANT=${TARGET_BUILD_VARIANT:-?} TW_THEME=${TW_THEME:-?}"

# --- OrangeFox theme resources ---------------------------------------------
# The recovery install recipe runs `sed -i s/{themeversion}//` on
# recovery/root/twres/{splash.xml,ui.xml}; those files must exist first.
# Source of truth: gui/theme/<TW_THEME>/ + gui/theme/common/.
echo "=== populating OrangeFox theme into recovery/root/twres ==="
THEME_SRC="bootable/recovery/gui/theme"
TW_THEME_VAL="$(get_build_var TW_THEME 2>/dev/null | tail -1 | tr -d '[:space:]')"
echo "TW_THEME resolved to: ${TW_THEME_VAL:-<empty>}"
[ -n "$TW_THEME_VAL" ] || die "TW_THEME resolved to empty; the theme copy cannot be done (check BoardConfig.mk and vendor/twrp/config/BoardConfigSoong.mk)"
[ -d "$THEME_SRC/$TW_THEME_VAL" ] || die "theme dir missing: $THEME_SRC/$TW_THEME_VAL"

TW_RES="out/target/product/sakura/recovery/root/twres"
mkdir -p "$TW_RES"
for sub in "$THEME_SRC/$TW_THEME_VAL"/*; do
    bn="$(basename "$sub")"
    if [ -f "$sub" ]; then cp -f "$sub" "$TW_RES/$bn"
    elif [ -d "$sub" ]; then cp -a "$sub" "$TW_RES/$bn"; fi
done
for sub in "$THEME_SRC/common"/*; do
    [ -d "$sub" ] && cp -a "$sub" "$TW_RES/$(basename "$sub")"
done
if [ "${TW_EXTRA_LANGUAGES:-}" = "true" ]; then
    for sub in "$THEME_SRC/extra-languages"/*; do
        [ -d "$sub" ] && cp -a "$sub" "$TW_RES/$(basename "$sub")"
    done
fi
for f in splash.xml ui.xml; do
    [ -f "$TW_RES/$f" ] || die "theme copy did not produce $TW_RES/$f (source: $THEME_SRC/$TW_THEME_VAL)"
done
echo "==> theme populated into $TW_RES ($(ls -1 "$TW_RES" | wc -l) entries)"

# --- build ------------------------------------------------------------------
mem_mb=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 ))
J=0
if [ -n "${PARALLEL_JOBS:-}" ] && [ "$PARALLEL_JOBS" != "0" ]; then
    J="$PARALLEL_JOBS"
else
    J=$(( mem_mb / 1800 )); [ "$J" -lt 1 ] && J=1
    [ "$J" -gt "$(nproc)" ] && J="$(nproc)"
    [ "$J" -gt 8 ] && J=8
fi
echo "==> mka -j$J $TARGET  (RAM ${mem_mb} MB, $(nproc) cpus, log: $LOG)"
set +e
mka -j"$J" "$TARGET" 2>&1 | tee -a "$LOG"
status=${PIPESTATUS[0]}
set -e

if [ "$status" != 0 ]; then
    echo "==> build failed with status $status; first errors:" >&2
    grep -nE 'error:|Error [0-9]+|FAILED' "$LOG" | head -40 >&2 || true
    exit "$status"
fi

# --- exactly one image, produced by this run -------------------------------
IMG=""
for cand in "$OUT/OrangeFox-unofficial-sakura.img" "$OUT/recovery.img"; do
    [ -f "$cand" ] && IMG="$cand" && break
done
[ -n "$IMG" ] || die "build reported success but no recovery image exists in $OUT"
mtime=$(stat -c %Y "$IMG")
[ "$mtime" -ge "$BUILD_START" ] || die "$IMG predates this build (stale output); refusing to verify it"
echo "==> image: $IMG ($(stat -c %s "$IMG") bytes, sha256 $(sha256sum "$IMG" | cut -d' ' -f1))"

# --- structural verification is part of a successful build -----------------
if [ "${SAKURA_ALLOW_MISSING_CRYPTO:-0}" = 1 ]; then
    "$ROOT/build/verify_image.sh" "$SRC" "$IMG"
else
    "$ROOT/build/verify_image.sh" "$SRC" "$IMG" --require-crypto
fi
echo
echo "==> build + structural verification complete."
echo "    image : $IMG"
echo "    sha256: $(sha256sum "$IMG" | cut -d' ' -f1)"
echo "    log   : $LOG"
echo "    This is structural evidence only: no boot or decryption test was performed."
