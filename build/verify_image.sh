#!/usr/bin/env bash
#
# verify_image.sh - structural checks on a freshly built recovery image.
#
# This proves the image is *built correctly* (right header, cmdline, sakura
# DTB, R12 ramdisk contents). It does NOT prove the recovery boots or that
# decryption works - that needs the device. See documentation/TEST_REPORT.md.
#
# Usage: ./build/verify_image.sh [source-tree] [image]
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC=""
IMG=""
REQUIRE_CRYPTO=0
for arg in "$@"; do
    case "$arg" in
        --require-crypto) REQUIRE_CRYPTO=1 ;;
        -*) echo "ERROR: unknown option $arg" >&2; exit 2 ;;
        *)  if [ -z "$SRC" ]; then SRC="$arg"; else IMG="$arg"; fi ;;
    esac
done

if [ -z "$IMG" ]; then
    [ -n "$SRC" ] || { echo "usage: $0 [source-tree] [image]" >&2; exit 1; }
    for cand in \
        "$SRC/out/target/product/sakura/OrangeFox-unofficial-sakura.img" \
        "$SRC/out/target/product/sakura/recovery.img"; do
        [ -f "$cand" ] && IMG="$cand" && break
    done
fi
[ -n "${IMG:-}" ] && [ -f "$IMG" ] || { echo "ERROR: no recovery image found" >&2; exit 1; }

fail=0
ok()   { echo "  [PASS] $*"; }
bad()  { echo "  [FAIL] $*"; fail=1; }

echo "==> image: $IMG ($(stat -c %s "$IMG") bytes)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 "${ROOT}/tools/bootimg.py" info "$IMG" | tee "$TMP/info.txt" >/dev/null
cat "$TMP/info.txt"

grep -q 'page_size            : 2048' "$TMP/info.txt" \
    && ok "page size 2048" || bad "page size is not 2048"

grep -q 'androidboot.bootdevice=7824900.sdhci' "$TMP/info.txt" \
    && ok "bootdevice cmdline (7824900.sdhci)" || bad "boot cmdline missing bootdevice"

grep -q 'kernel_addr          : 0x80008000' "$TMP/info.txt" \
    && ok "kernel addr 0x80008000" || bad "kernel addr wrong"

grep -q 'ramdisk_addr         : 0x81000000' "$TMP/info.txt" \
    && ok "ramdisk addr 0x81000000" || bad "ramdisk addr wrong"

grep -q 'header_version       : 0' "$TMP/info.txt" \
    && ok "boot image header v0" || bad "unexpected boot header version"

size=$(stat -c %s "$IMG")
[ "$size" -le 67108864 ] \
    && ok "fits the 64 MiB recovery partition ($size bytes)" \
    || bad "image is larger than BOARD_RECOVERYIMAGE_PARTITION_SIZE (64 MiB)"

echo "==> kernel / DTB fingerprint"
if python3 "${ROOT}/tools/verify_dtb.py" "$IMG"; then
    ok "kernel targets sakura (camera/panel nodes + fscrypt)"
else
    bad "kernel/DTB fingerprint check failed"
fi

echo "==> ramdisk contents"
python3 "${ROOT}/tools/bootimg.py" unpack "$IMG" "$TMP/u" >/dev/null
python3 "${ROOT}/tools/bootimg.py" cpiotoc "$TMP/u/ramdisk.cpio" "$TMP/rd" >/dev/null
# --- ramdisk layout, as measured in the pinned bootable/recovery -----------
# fox_12.1 puts binaries in /system/bin, libraries in /system/lib64 and keeps
# only the sh/bash symlinks in /sbin; init exports
# PATH=/sbin:/system/bin and LD_LIBRARY_PATH=/system/lib64:/vendor/lib64/hw.
# A file placed anywhere else is invisible to init and to the linker.
echo "==> ramdisk layout"
for f in system/bin/linker64 system/bin/recovery system/bin/toybox \
         system/etc/init/hwservicemanager.rc system/etc/init/servicemanager.rc \
         init.recovery.qcom.rc init.recovery.qcom_decrypt.rc ; do
    [ -e "$TMP/rd/$f" ] && ok "ramdisk contains /$f" \
        || bad "ramdisk is missing /$f"
done

for f in \
    etc/recovery.fstab \
    system/etc/twrp.flags \
    system/etc/recovery.fstab \
    init.recovery.qcom.rc ; do
    if [ -e "$TMP/rd/$f" ] || [ -e "$TMP/rd/system/$f" ]; then
        ok "ramdisk contains $f"
    else
        echo "  [info] $f not at that exact path (layout can differ)"
    fi
done

# --- fstab fs_mgr flag regression gate ------------------------------------
# AOSP fs_mgr splits the fs_mgr flags column on commas only. A ';' would make
# "encryptable=footer;fileencryption=ice" one malformed token and silently
# disable BOTH mechanisms, which is exactly the defect that shipped in the
# audited image. Check the ramdisk the device will actually parse.
echo "==> installed fstab flags"
FSTABS=$(find "$TMP/rd" -name 'recovery.fstab' 2>/dev/null || true)
if [ -z "$FSTABS" ]; then
    bad "no recovery.fstab found in the ramdisk (TARGET_RECOVERY_FSTAB not installed)"
else
    for f in $FSTABS; do
        echo "    $(echo "$f" | sed "s|$TMP/rd||")"
    done
    # Comments must not be able to satisfy (or trip) these checks: the audited
    # handoff image contained the words "fileencryption=ice" only inside a
    # comment explaining that it had been removed.
    ACTIVE="$TMP/fstab_active"
    cat $FSTABS | sed 's/#.*//' | grep -v '^[[:space:]]*$' > "$ACTIVE"

    if grep -qhE 'encryptable=footer;|;fileencryption=' "$ACTIVE"; then
        bad "semicolon-delimited fs_mgr flags in the installed fstab (must be commas)"
    else
        ok "installed fstab uses comma-separated fs_mgr flags"
    fi
    if grep -qh 'encryptable=footer' "$ACTIVE" && grep -qh 'fileencryption=ice' "$ACTIVE"; then
        ok "installed /data carries both FDE and FBE tokens"
    else
        bad "installed fstab is missing encryptable=footer and/or fileencryption=ice"
    fi
fi

if grep -qhs 'fileencryption=ice' "$TMP/fstab_active" 2>/dev/null; then
    ok "FBE (fileencryption=ice) configured in the installed fstab"
else
    bad "no fileencryption=ice in the installed fstab - FBE cannot work"
fi
if grep -qhs 'encryptable=footer' "$TMP/fstab_active" 2>/dev/null; then
    ok "legacy FDE (encryptable=footer) retained"
else
    echo "  [warn] encryptable=footer not found (Android 9 FDE ROMs unsupported)"
fi

# --- QTI crypto chain presence (reported, not claimed) --------------------
# The blobs are proprietary and are NOT in this repository. Their absence is
# what made the audited handoff image unable to decrypt anything, so report it
# explicitly rather than inferring a working crypto path from the fstab.
echo "==> QTI crypto chain"
crypto_found=0
crypto_missing=""
for b in qseecomd android.hardware.keymaster@3.0-service-qti \
         android.hardware.gatekeeper@1.0-service-qti; do
    if find "$TMP/rd" -name "$b" 2>/dev/null | grep -q .; then
        echo "  [info] present: $b"
        crypto_found=$((crypto_found + 1))
    else
        crypto_missing="$crypto_missing $b"
    fi
done
if [ "$crypto_found" = 3 ]; then
    ok "TEE chain present in the ramdisk"
else
    if [ "$REQUIRE_CRYPTO" = 1 ]; then
        bad "TEE chain incomplete in the built ramdisk: missing${crypto_missing}"
    else
        echo "  [info] missing:$crypto_missing"
        echo "  [info] DECRYPTION: UNVERIFIED - extract the blobs (documentation/DEPENDENCIES.md section 4)"
    fi
fi

# --- init service resolvability, in the ramdisk the device boots ----------
# This is the check the audited handoff image would have failed: it had no
# qseecomd, no QTI Keymaster/Gatekeeper service, and an init fragment whose
# import target did not exist, so nothing ever started the TEE chain.
echo "==> init services resolve in the built ramdisk"
INIT_ARGS=(--ramdisk "$TMP/rd")
if [ "$REQUIRE_CRYPTO" = 1 ]; then
    INIT_ARGS+=(--require crypto)
fi
if python3 "${ROOT}/tools/check_init_services.py" "${INIT_ARGS[@]}" > "$TMP/init.txt" 2>&1; then
    sed 's/^/  /' "$TMP/init.txt"
    ok "every init service executable, interpreter and DT_NEEDED library resolves"
else
    sed 's/^/  /' "$TMP/init.txt"
    bad "init service resolution failed (see above)"
fi
grep -rqs 'metadata_encryption' "$TMP/rd" 2>/dev/null \
    && echo "  [warn] metadata_encryption present - NOT supportable on sakura, remove it"

for b in recovery init busybox magiskboot; do
    [ -e "$TMP/rd/sbin/$b" ] && ok "binary present: /sbin/$b"
done
if grep -rqs 'OrangeFox' "$TMP/rd" 2>/dev/null; then
    ok "OrangeFox branding present (this is a Fox build, not plain TWRP)"
else
    bad "no OrangeFox strings found - vendor/twrp was probably not patched"
fi

echo
if [ "$fail" = 0 ]; then
    echo "RESULT: PASS (structural). Boot/decryption still untested - see testing/."
else
    echo "RESULT: FAIL"
fi
exit "$fail"
