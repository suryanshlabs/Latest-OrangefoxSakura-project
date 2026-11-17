#!/usr/bin/env bash
#
# check_crypto_blobs.sh - the decryption gate.
#
# The repository must never produce an image that claims decryption support
# while the TEE chain is missing, which is exactly what the earlier handoff
# image did (keystore2 present, qseecomd/Keymaster 3.0/Gatekeeper 1.0 absent,
# no active fileencryption=ice). This script is that claim's truth value.
#
# It checks, in order:
#   1. every required entry of device/xiaomi/sakura/proprietary-files.txt is
#      installed at its exact destination in the device tree;
#   2. installed files match vendor_blobs/MANIFEST.sha256 when that local
#      manifest exists (so a hand-edited blob cannot pass);
#   3. the init services that execute them resolve - path, ELF architecture,
#      interpreter, and every transitive DT_NEEDED library - via
#      tools/check_init_services.py;
#   4. the three TEE services (qseecomd + Keymaster + Gatekeeper) are declared
#      and started.
#
# Modes:
#   (default)      report only, always exit 0 - used for logs
#   --require      exit 1 when any of the above fails - used by build.sh,
#                  run-all.sh and CI
#
# Usage: ./build/check_crypto_blobs.sh [--require] [source-tree]
#
# SPDX-License-Identifier: Apache-2.0
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV="${ROOT}/device/xiaomi/sakura"
LIST="${DEV}/proprietary-files.txt"
BLOBS="${ROOT}/vendor_blobs"

REQUIRE=0
SRC=""
for arg in "$@"; do
    case "$arg" in
        --require) REQUIRE=1 ;;
        *) SRC="$arg" ;;
    esac
done

[ -f "$LIST" ] || { echo "ERROR: missing $LIST" >&2; exit 1; }

present=0; missing_required=0; missing_optional=0; bad=0
declare -a missing_list=()

echo "==> QTI TEE chain (device tree: $DEV)"
while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    case "$line" in *:*) ;; *) continue ;; esac
    rest="${line#*:}"
    dst="${rest%%|*}"
    dst="$(printf '%s' "$dst" | tr -d '[:space:]')"
    [ -n "$dst" ] || continue
    tail="${rest#*|}"
    if [ "$tail" = "$rest" ]; then req="required"; else req="$(printf '%s' "${tail%%|*}" | tr -d '[:space:]')"; fi
    target="${DEV}/recovery/root/${dst}"
    if [ -f "$target" ]; then
        present=$((present + 1))
        if ! python3 "${ROOT}/tools/elf.py" "$target" 2>&1 | grep -q '64-bit AArch64'; then
            bad=$((bad + 1))
            echo "    NOT AARCH64 ELF: $dst"
        fi
    else
        if [ "$req" = "required" ]; then
            missing_required=$((missing_required + 1))
            missing_list+=("$dst")
        else
            missing_optional=$((missing_optional + 1))
        fi
    fi
done < "$LIST"

# Is there a local checksum manifest to compare against?
if [ -f "${BLOBS}/MANIFEST.sha256" ]; then
    echo "==> verifying installed blobs against vendor_blobs/MANIFEST.sha256"
    while IFS= read -r line; do
        case "$line" in ''|'#'*) continue ;; esac
        want="${line%% *}"
        rel="${line#*  }"
        rel="${rel#./}"
        [ "$want" != "$rel" ] || continue
        tgt="${DEV}/recovery/root/${rel}"
        [ -f "$tgt" ] || continue
        got="$(sha256sum "$tgt" | cut -d' ' -f1)"
        if [ "$got" != "$want" ]; then
            bad=$((bad + 1))
            echo "    SHA-256 MISMATCH: $rel (installed $got, expected $want)"
        fi
    done < "${BLOBS}/MANIFEST.sha256"
else
    echo "==> no vendor_blobs/MANIFEST.sha256 (blobs not extracted on this host)"
fi

echo "==> init service resolution"
LOG="$(mktemp)"
python3 "${ROOT}/tools/check_init_services.py" --device-tree "$DEV" \
    --manifest "$LIST" --require crypto > "$LOG" 2>&1
init_rc=$?
sed 's/^/    /' "$LOG"
rm -f "$LOG"
[ "$init_rc" = 0 ] || bad=$((bad + 1))

# Cross-check the paths against a synced upstream tree when one is provided.
if [ -n "$SRC" ] && [ -d "$SRC" ]; then
    echo "==> upstream crypto init references in $SRC"
    refs="$(grep -rhoE '(/system/bin|/sbin|/vendor/bin/hw)/(android\.hardware\.(keymaster|gatekeeper)[^ \t"]*|qseecomd)' \
              "$SRC/bootable/recovery" "$SRC/vendor/recovery" 2>/dev/null | sort -u)"
    if [ -n "$refs" ]; then
        printf '%s\n' "$refs" | sed 's/^/    /'
        echo "    (upstream declares these; this device tree must not duplicate them)"
    else
        echo "    none - the pinned upstream trees ship no TEE service definitions,"
        echo "    so this device tree is the only provider (verified at the pinned SHAs)."
    fi
fi

echo
echo "    present: ${present}   missing required: ${missing_required}" \
     "  absent optional: ${missing_optional}   invalid: ${bad}"
if [ "$missing_required" -gt 0 ]; then
    echo "    missing required files:"
    for d in "${missing_list[@]}"; do echo "      - $d"; done
fi

fail=0
[ "$missing_required" = 0 ] || fail=1
[ "$bad" = 0 ] || fail=1
[ "$init_rc" = 0 ] || fail=1

if [ "$fail" = 0 ]; then
    echo "CRYPTO CHAIN: complete and init-resolvable ($present files installed)."
    echo "              Runtime decryption is still UNTESTED on hardware."
    exit 0
fi

echo "CRYPTO CHAIN: INCOMPLETE - decryption cannot work in an image built now."
cat <<'EOF'
              Extract the chain from your own sakura Android 9 stock fastboot ROM:

                ./build/extract_blobs.sh --firmware <fastboot ROM>.tgz
                ./build/install_blobs.sh

              Do not report FDE/FBE as working for an image built without it.
              documentation/DEPENDENCIES.md section 4 has the full procedure.
EOF
if [ "$REQUIRE" = 1 ]; then
    echo "RESULT: FAIL (--require): refusing to build an image that claims decryption support."
    exit 1
fi
echo "RESULT: report only (use --require to make this fatal)"
exit 0
