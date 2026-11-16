#!/usr/bin/env bash
#
# check_crypto_blobs.sh - report whether this build can actually attempt
# FDE/FBE decryption, and say so loudly instead of guessing.
#
# The QTI crypto chain (qseecomd + Keymaster 3.0 + Gatekeeper 1.0 services and
# their library set) is proprietary Xiaomi/Qualcomm code. It is NOT committed
# to this repository; device/xiaomi/sakura/proprietary-files.txt lists what is
# needed and where it must land. Without those files present at the paths the
# recovery init rc actually executes, decryption cannot work - the previous
# handoff image proved that: it shipped keystore2 but no qseecomd, keymaster or
# gatekeeper service, and its fstab had no active fileencryption=ice.
#
# This script never fails a build. It exists so the log states the truth:
#   * every listed blob present  -> "chain present (still untested on hardware)"
#   * any blob missing           -> "DECRYPTION: UNVERIFIED"
#
# Usage: ./build/check_crypto_blobs.sh [source-tree]
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-}"
LIST="${ROOT}/device/xiaomi/sakura/proprietary-files.txt"
DEV="${ROOT}/device/xiaomi/sakura"

[ -f "$LIST" ] || { echo "ERROR: missing $LIST" >&2; exit 1; }

missing=0
present=0
echo "==> QTI crypto chain check (device tree: $DEV)"
while IFS= read -r line; do
    case "$line" in ''|\#*) continue;; esac
    src="${line%%:*}"
    dst="${line#*:}"
    dst="${dst%%|*}"
    dst="$(printf '%s' "$dst" | tr -d '[:space:]')"
    [ -n "$dst" ] || continue
    # Some entries point at recovery-root paths, some at vendor library paths.
    cand="$DEV/$dst"
    if [ -e "$cand" ]; then
        present=$((present + 1))
    else
        missing=$((missing + 1))
        [ "$missing" -le 8 ] && echo "    missing: $dst"
    fi
done < "$LIST"
[ "$missing" -gt 8 ] && echo "    ... and $((missing - 8)) more missing"

# Cross-check against the paths the *synced* recovery init actually executes:
# fox_12.1 puts the recovery root at /system/bin for Android 12+ services, and
# legacy imports additionally look at /sbin. Report both so a path mismatch is
# visible rather than assumed away.
if [ -n "$SRC" ] && [ -d "$SRC" ]; then
    echo "==> init rc references in the synced tree"
    refs=$(grep -rhoE '(/system/bin|/sbin)/(android\.hardware\.(keymaster|gatekeeper)[^ 	"]*|qseecomd)' \
             "$SRC/vendor/recovery" "$SRC/bootable/recovery" 2>/dev/null | sort -u)
    if [ -n "$refs" ]; then
        printf '%s\n' "$refs" | sed 's/^/    /'
    else
        echo "    (no keymaster/gatekeeper/qseecomd service references found)"
    fi
fi

echo
if [ "$missing" -eq 0 ]; then
    echo "CRYPTO CHAIN: all $present listed blobs present."
    echo "              Decryption is still UNTESTED on hardware."
    exit 0
fi
echo "DECRYPTION: UNVERIFIED - $missing of $((present + missing)) listed blobs are absent."
echo "            Extract them from YOUR OWN sakura Android 9 stock vendor image:"
echo "            documentation/DEPENDENCIES.md section 4."
echo "            Do not report FDE/FBE as working for an image built without them."
exit 0
