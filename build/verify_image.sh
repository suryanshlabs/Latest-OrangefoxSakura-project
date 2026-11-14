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
SRC="${1:-}"
IMG="${2:-}"

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

if grep -rqs 'fileencryption=ice' "$TMP/rd" 2>/dev/null; then
    ok "FBE (fileencryption=ice) configured"
else
    bad "no fileencryption=ice found - FBE will not work"
fi
if grep -rqs 'encryptable=footer' "$TMP/rd" 2>/dev/null; then
    ok "legacy FDE (encryptable=footer) retained"
else
    echo "  [warn] encryptable=footer not found (Android 9 FDE ROMs unsupported)"
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
