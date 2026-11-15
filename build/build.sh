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

# --- populate OrangeFox theme resources into recovery/root/twres ------
# Why this exists: the recovery binary install recipe at 99% runs
#   sed -i "s/{themeversion}//" .../twres/splash.xml
#   sed -i "s/{themeversion}//" .../twres/ui.xml
# so $(TARGET_RECOVERY_ROOT_OUT)/twres MUST contain the selected theme's
# splash.xml + ui.xml (plus fonts/languages) BEFORE that recipe runs.
# The OrangeFox recovery module is the canonical place that does this at
# soong-configure time (bootable/recovery/gui/libguitwrp_defaults.go,
# reading TW_THEME from the twrpVarsPlugin namespace). In the runs so far
# that side effect has not happened (twres/ absent after lunch), so add an
# explicit, deterministic, device-side copy here. It is idempotent, reads the
# real theme source from the recovery source tree, and fails hard (with the
# exact source path) if the theme is genuinely missing, rather than producing
# empty XML files or silently suppressing the sed.
# Source of truth: gui/theme/$(TW_THEME)/{splash.xml,ui.xml,images,pages,
#   resources,themes} + gui/theme/common/{fonts,languages}
# (verified against the pinned recovery source tree, commit 8d2aad19).
echo "=== populating OrangeFox theme into recovery/root/twres ==="
THEME_SRC="bootable/recovery/gui/theme"
if ! command -v get_build_var >/dev/null 2>&1; then
  echo "::warning::get_build_var not available; theme copy skipped (will re-run next build if TW_THEME is later known)"
else
  TW_THEME_VAL="$(get_build_var TW_THEME 2>/dev/null | tail -1 | tr -d '[:space:]' )"
  echo "TW_THEME resolved to: ${TW_THEME_VAL:-<empty>}"
  if [ -n "${TW_THEME_VAL}" ] && [ -d "${THEME_SRC}/${TW_THEME_VAL}" ]; then
    TW_RES="out/target/product/sakura/recovery/root/twres"
    mkdir -p "$TW_RES"

    # Per-theme files: splash.xml, ui.xml and the theme subdirs.
    for sub in "$THEME_SRC/$TW_THEME_VAL"/*; do
      bn="$(basename "$sub")"
      if [ -f "$sub" ]; then
        cp -f "$sub" "$TW_RES/$bn"
      elif [ -d "$sub" ]; then
        cp -a "$sub" "$TW_RES/$bn"
      fi
    done

    # Common theme resources (fonts and languages) that every theme uses.
    for sub in "$THEME_SRC/common"/*; do
      bn="$(basename "$sub")"
      if [ -d "$sub" ]; then
        cp -a "$sub" "$TW_RES/$bn"
      fi
    done

    # Optional extra languages, gated on TW_EXTRA_LANGUAGES (matches the
    # recovery module's own logic).
    if [ "${TW_EXTRA_LANGUAGES}" = "true" ]; then
      for sub in "$THEME_SRC/extra-languages"/*; do
        bn="$(basename "$sub")"
        if [ -d "$sub" ]; then
          cp -a "$sub" "$TW_RES/$bn"
        fi
      done
    fi

    # Verify the two files the recovery install recipe actually touches.
    if [ ! -f "$TW_RES/splash.xml" ] || [ ! -f "$TW_RES/ui.xml" ]; then
      echo "::error::OrangeFox theme copy did not produce the files the recovery install recipe needs"
      echo "      twres/ contents: $(ls -1 "$TW_RES" 2>/dev/null | tr '\n' ' ' )"
      echo "      expected splash.xml + ui.xml under: $TW_RES"
      echo "      theme source dir: $THEME_SRC/$TW_THEME_VAL"
      echo "      files present in source:"
      echo "        $(ls -1 "$THEME_SRC/$TW_THEME_VAL" 2>/dev/null | tr '\n' ' ' )"
      exit 1
    fi
    echo "OrangeFox theme populated into $TW_RES ($(ls -1 "$TW_RES" 2>/dev/null | wc -l) entries)"
  else
    echo "::warning::TW_THEME value '${TW_THEME_VAL}' did not resolve to a theme dir at $THEME_SRC/${TW_THEME_VAL}; theme copy skipped"
    echo "      Tried: $THEME_SRC/${TW_THEME_VAL}"
    echo "      This will re-run on the next build once TW_THEME is known."
  fi
fi


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
