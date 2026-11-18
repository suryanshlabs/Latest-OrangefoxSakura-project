#!/usr/bin/env bash
#
# check_theme_inputs.sh - prove the theme can be selected before make starts.
#
# WHY
#   Four CI runs of this device tree died inside Soong with
#       Could not find ui.xml for TW_THEME: not set
#       (theme selection failed; exiting)
#   long before any recovery code was compiled. That message comes from
#   bootable/recovery/gui/libguitwrp_defaults.go, which reads TW_THEME through
#   Soong's vendor-config namespace "twrpVarsPlugin" (populated by
#   vendor/twrp/config/BoardConfigSoong.mk from EXPORT_TO_SOONG). When anything
#   in that chain is missing the namespace value is empty, the plugin calls
#   os.Exit(-1), and the build stops with a message that names none of the
#   actual causes.
#
#   This script checks the chain directly, from the synced tree, in seconds:
#     1. the device BoardConfig sets TW_THEME (or a resolution to derive it),
#     2. the theme directory it names really contains ui.xml,
#     3. vendor/twrp/config/BoardConfigSoong.mk exists, declares the namespace
#        and exports TW_THEME,
#     4. the device BoardConfig actually includes that file (and, if present,
#        bootable/recovery/orangefox_soong.mk before it).
#
# USAGE
#   build/check_theme_inputs.sh /path/to/fox_12.1
#   build/check_theme_inputs.sh /path/to/fox_12.1 --device-tree device/xiaomi/sakura
#
# EXIT
#   0 all prerequisites present (warnings may still be printed)
#   1 at least one hard prerequisite is missing
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
set -uo pipefail

SRC=""
DEVICE_TREE="device/xiaomi/sakura"

while [ $# -gt 0 ]; do
    case "$1" in
        --device-tree) DEVICE_TREE="${2:?--device-tree needs a path}"; shift 2 ;;
        -h|--help) sed -n '2,40p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) SRC="$1"; shift ;;
    esac
done

[ -n "$SRC" ] || { echo "ERROR: usage: $0 <src-dir> [--device-tree <path>]" >&2; exit 1; }
[ -d "$SRC" ] || { echo "ERROR: $SRC is not a directory" >&2; exit 1; }

BOARD="$SRC/$DEVICE_TREE/BoardConfig.mk"
THEME_ROOT="$SRC/bootable/recovery/gui/theme"
TWRP_SOONG="$SRC/vendor/twrp/config/BoardConfigSoong.mk"

fail=0
warn=0
ok()   { printf '  [ OK ] %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=$((fail + 1)); }
note() { printf '  [WARN] %s\n' "$1"; warn=$((warn + 1)); }

echo "==> theme selection inputs"
echo "    source      : $SRC"
echo "    device tree : $DEVICE_TREE"

[ -f "$BOARD" ] || { bad "$BOARD is missing (the device tree is not in the source tree)"; exit 1; }

# --- 1. what the BoardConfig says -----------------------------------------
theme=$(sed -n 's/^[[:space:]]*TW_THEME[[:space:]]*:=[[:space:]]*\([^#[:space:]]*\).*/\1/p' "$BOARD" | tail -1)
width=$(sed -n 's/^[[:space:]]*TARGET_SCREEN_WIDTH[[:space:]]*:=[[:space:]]*\([0-9]*\).*/\1/p' "$BOARD" | tail -1)
height=$(sed -n 's/^[[:space:]]*TARGET_SCREEN_HEIGHT[[:space:]]*:=[[:space:]]*\([0-9]*\).*/\1/p' "$BOARD" | tail -1)
res=$(sed -n 's/^[[:space:]]*DEVICE_RESOLUTION[[:space:]]*:=[[:space:]]*\([^#[:space:]]*\).*/\1/p' "$BOARD" | tail -1)

if [ -n "$theme" ]; then
    ok "BoardConfig sets TW_THEME := $theme"
elif [ -n "$res" ]; then
    ok "BoardConfig sets DEVICE_RESOLUTION := $res (TW_THEME is derived from it)"
elif [ -n "$width" ] && [ -n "$height" ]; then
    ok "BoardConfig sets TARGET_SCREEN_WIDTH/HEIGHT := ${width}x${height}"
else
    bad "BoardConfig sets none of TW_THEME, DEVICE_RESOLUTION or TARGET_SCREEN_WIDTH/HEIGHT"
    echo "         soong would print: Could not find ui.xml for TW_THEME: not set"
fi

# The resolution is also the fallback the Go plugin uses when TW_THEME is empty,
# so its absence removes the safety net that turns an export bug into a warning.
if [ -z "$width" ] || [ -z "$height" ]; then
    note "TARGET_SCREEN_WIDTH/HEIGHT are not both set: the resolution fallback in"
    note "  gui/libguitwrp_defaults.go (determineTheme) cannot rescue an empty TW_THEME."
fi

# --- 2. the theme really exists in the pinned recovery ---------------------
if [ ! -d "$THEME_ROOT" ]; then
    bad "$THEME_ROOT is missing (bootable/recovery is not synced or the pinned ref changed)"
    exit 1
fi

check_theme_dir() {
    local t="$1"
    if [ -f "$THEME_ROOT/$t/ui.xml" ]; then
        ok "gui/theme/$t/ui.xml exists"
        return 0
    fi
    return 1
}

if [ -n "$theme" ]; then
    check_theme_dir "$theme" || bad "gui/theme/$theme/ui.xml is missing"
else
    for t in portrait_hdpi portrait_mdpi landscape_hdpi landscape_mdpi watch_mdpi; do
        check_theme_dir "$t" && break
    done
fi

# --- 3. the Soong vendor-config chain --------------------------------------
if [ ! -f "$TWRP_SOONG" ]; then
    bad "$TWRP_SOONG is missing: vendor/twrp was not synced, so twrpVarsPlugin never exists"
else
    if grep -q 'SOONG_CONFIG_NAMESPACES.*twrpVarsPlugin' "$TWRP_SOONG"; then
        ok "vendor/twrp declares the twrpVarsPlugin namespace"
    else
        bad "vendor/twrp/config/BoardConfigSoong.mk does not declare twrpVarsPlugin"
    fi
    if grep -q 'EXPORT_TO_SOONG' "$TWRP_SOONG" && grep -q 'TW_THEME' "$TWRP_SOONG"; then
        ok "vendor/twrp exports TW_THEME into that namespace"
    else
        bad "vendor/twrp's EXPORT_TO_SOONG does not list TW_THEME"
    fi
fi

if grep -q '^[[:space:]]*include[[:space:]].*vendor/twrp/config/BoardConfigSoong.mk' "$BOARD"; then
    ok "device BoardConfig includes vendor/twrp/config/BoardConfigSoong.mk"
else
    bad "device BoardConfig never includes vendor/twrp/config/BoardConfigSoong.mk,"
    echo "         so TW_THEME stays empty inside Soong even though make can see it."
    echo "         Add near the end of BoardConfig.mk, after TW_THEME is set:"
    echo "           include vendor/twrp/config/BoardConfigSoong.mk"
fi

# OrangeFox appends OF_LANDSCAPE_MODE to EXPORT_TO_SOONG in this file, and the
# export loop runs inside BoardConfigSoong.mk, so the order matters.
OX_SOONG="$SRC/bootable/recovery/orangefox_soong.mk"
if [ -f "$OX_SOONG" ]; then
    ox_line=$(grep -n 'include[[:space:]].*orangefox_soong.mk' "$BOARD" | head -1 | cut -d: -f1)
    tw_line=$(grep -n 'include[[:space:]].*vendor/twrp/config/BoardConfigSoong.mk' "$BOARD" | head -1 | cut -d: -f1)
    if [ -z "$ox_line" ]; then
        note "bootable/recovery/orangefox_soong.mk is not included (OF_LANDSCAPE_MODE stays"
        note "  unexported; harmless for a portrait theme, so this is not fatal)"
    elif [ -n "$tw_line" ] && [ "$ox_line" -gt "$tw_line" ]; then
        bad "orangefox_soong.mk is included after BoardConfigSoong.mk (line $ox_line > $tw_line);"
        echo "         its EXPORT_TO_SOONG additions are ignored. Move it before that include."
    else
        ok "orangefox_soong.mk is included before the twrpVarsPlugin export loop"
    fi
fi

echo
if [ "$fail" -gt 0 ]; then
    echo "RESULT: FAIL ($fail hard problem(s), $warn warning(s))"
    echo "        make would stop inside Soong with 'theme selection failed; exiting'."
    exit 1
fi
echo "RESULT: PASS ($warn warning(s))"
echo "NOTE: this proves the inputs, not that soong.variables carries them; the build"
echo "      itself is the only proof of that."
exit 0
