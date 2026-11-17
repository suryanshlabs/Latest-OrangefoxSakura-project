#!/usr/bin/env bash
#
# extract_blobs.sh - deterministic QTI TEE/crypto blob extraction from a
# genuine Xiaomi Redmi 6 Pro (sakura) Android 9 stock fastboot ROM.
#
# WHY
# ---
# Decryption in recovery needs the vendor's TEE chain: qseecomd, the QTI
# Keymaster 3.0 and Gatekeeper 1.0 services, their HAL implementations and the
# QSEECom support libraries. They are Xiaomi/Qualcomm proprietary code, so they
# can never be committed here. This script is the reproducible way to get them
# from the user's own firmware, with provenance and checksums recorded.
#
# WHAT IT DOES
# ------------
#   1. unpacks a fastboot ROM (.tgz/.tar.gz/.tar.xz/.zip) or accepts a
#      directory, a vendor.img, or a raw/sparse vendor image;
#   2. converts an Android sparse image to raw (tools/simg2img.py - no SDK);
#   3. reads vendor.img READ-ONLY with e2fsprogs' debugfs (no root, no loop
#      mount). `mount -o loop,ro` is used only if debugfs is unavailable and
#      the caller is root;
#   4. proves the image really is sakura Android 9 by reading its build.prop
#      before extracting anything (a daisy or Mi A2 Lite image is rejected);
#   5. proves every required file exists, is a regular non-empty file, and is
#      64-bit AArch64 ELF (tools/elf.py) - anything else aborts;
#   6. writes vendor_blobs/ with the exact ramdisk layout the device tree wants,
#      plus vendor_blobs/MANIFEST.sha256 and vendor_blobs/EXTRACTION_REPORT.md
#      (firmware name/SHA-256, vendor.img SHA-256, vendor fingerprint,
#      per-file SHA-256, tool versions).
#
# WHAT IT NEVER DOES
# ------------------
#   * no invented hashes, paths or compatibility claims;
#   * no writes into the device tree (build/install_blobs.sh does that, after a
#     separate checksum verification);
#   * no network access, no download of Xiaomi firmware, no redistribution;
#   * no mounting read-write, so the user's firmware is never modified.
#
# USAGE
#   ./build/extract_blobs.sh --firmware sakura_india_global_images_V12.0.4.0.PDMMIXM_....tgz
#   ./build/extract_blobs.sh --vendor-img /path/to/vendor.img
#   ./build/extract_blobs.sh --firmware ROM.tgz --dry-run     # inspect only
#   ./build/extract_blobs.sh --firmware ROM.tgz --out /tmp/blobs
#
# Requirements: python3, tar/unzip, e2fsprogs (debugfs). See
# ../../documentation/DEPENDENCIES.md section 4.
#
# SPDX-License-Identifier: Apache-2.0
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${ROOT}/device/xiaomi/sakura/proprietary-files.txt"
OUT="${ROOT}/vendor_blobs"
FIRMWARE=""
VENDOR_IMG=""
DRY_RUN=0
KEEP_WORK=0
WORK=""

die() { echo "ERROR: $*" >&2; exit 1; }
note() { echo "  $*"; }

usage() {
    sed -n '3,50p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --firmware)   FIRMWARE="${2:-}"; shift 2 ;;
        --vendor-img) VENDOR_IMG="${2:-}"; shift 2 ;;
        --out)        OUT="${2:-}"; shift 2 ;;
        --dry-run)    DRY_RUN=1; shift ;;
        --keep-work)  KEEP_WORK=1; shift ;;
        -h|--help)    usage 0 ;;
        *) die "unknown argument: $1 (see --help)" ;;
    esac
done

[ -n "$FIRMWARE" ] || [ -n "$VENDOR_IMG" ] || die "give --firmware <fastboot-rom> or --vendor-img <vendor.img>"
[ -f "$MANIFEST" ] || die "missing $MANIFEST"
command -v python3 >/dev/null || die "python3 is required"
[ -f "${ROOT}/tools/elf.py" ] || die "missing tools/elf.py"
[ -f "${ROOT}/tools/simg2img.py" ] || die "missing tools/simg2img.py"

# ---------------------------------------------------------------------------
# 0. read and validate the manifest
# ---------------------------------------------------------------------------
SRC_LIST=(); DST_LIST=(); REQ_LIST=(); SHA_LIST=()
while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    case "$line" in
        *:*) ;;
        *) die "malformed manifest line (no ':'): $line" ;;
    esac
    src="${line%%:*}"
    rest="${line#*:}"
    dst="${rest%%|*}"
    tail="${rest#*|}"
    if [ "$tail" = "$rest" ]; then
        req="required"; want="-"
    else
        req="${tail%%|*}"
        if [ "$req" = "$tail" ]; then want="-"; else want="${tail#*|}"; fi
    fi
    req="$(printf '%s' "$req" | tr -d '[:space:]')"
    dst="$(printf '%s' "$dst" | tr -d '[:space:]')"
    case "$req" in required|optional) ;; *) die "bad requirement '$req' in: $line" ;; esac
    case "$dst" in
        system/bin/*|system/lib64/*) ;;
        *) die "destination must be under system/bin or system/lib64 (init search paths): $dst" ;;
    esac
    SRC_LIST+=("$src"); DST_LIST+=("$dst"); REQ_LIST+=("$req")
    SHA_LIST+=("$(printf '%s' "$want" | tr -d '[:space:]')")
done < "$MANIFEST"
[ "${#SRC_LIST[@]}" -gt 0 ] || die "manifest lists no files"

echo "==> manifest: ${#SRC_LIST[@]} files from $(basename "$MANIFEST")"

# ---------------------------------------------------------------------------
# 1. get a raw vendor.img
# ---------------------------------------------------------------------------
if [ "$KEEP_WORK" = 1 ]; then
    WORK="$(mktemp -d)"
else
    WORK="$(mktemp -d)"
fi
cleanup() {
    if [ "$KEEP_WORK" = 1 ]; then
        echo "  work directory kept: $WORK"
    else
        rm -rf "$WORK"
    fi
}
trap cleanup EXIT

find_vendor_img() { # <dir>
    local dir="$1" hit
    for cand in "$dir/images/vendor.img" "$dir/vendor.img" \
                "$dir"/*/images/vendor.img "$dir"/*/*/images/vendor.img; do
        [ -f "$cand" ] && { printf '%s\n' "$cand"; return 0; }
    done
    hit="$(find "$dir" -maxdepth 4 -type f -name 'vendor.img' -print -quit 2>/dev/null || true)"
    [ -n "$hit" ] && { printf '%s\n' "$hit"; return 0; }
    return 1
}

RAW_VENDOR=""
if [ -n "$VENDOR_IMG" ]; then
    [ -f "$VENDOR_IMG" ] || die "no such file: $VENDOR_IMG"
    case "$VENDOR_IMG" in
        *.img) RAW_VENDOR="$VENDOR_IMG" ;;
        *) die "--vendor-img must be an .img file" ;;
    esac
    echo "==> input: vendor image $VENDOR_IMG"
else
    [ -e "$FIRMWARE" ] || die "no such file or directory: $FIRMWARE"
    if [ -d "$FIRMWARE" ]; then
        echo "==> input: directory $FIRMWARE"
        RAW_VENDOR="$(find_vendor_img "$FIRMWARE")" || die \
            "no vendor.img found under $FIRMWARE (expected images/vendor.img)"
    else
        case "$FIRMWARE" in
            *.img) RAW_VENDOR="$FIRMWARE" ;;
            *.zip)
                echo "==> unpacking ZIP $FIRMWARE"
                unzip -q -o "$FIRMWARE" -d "$WORK/rom"
                RAW_VENDOR="$(find_vendor_img "$WORK/rom")" || die "no vendor.img inside $FIRMWARE"
                ;;
            *.tgz|*.tar.gz|*.tar.xz|*.tar)
                echo "==> unpacking archive $FIRMWARE (this can take a few minutes)"
                tar -xf "$FIRMWARE" -C "$WORK" || die "tar failed on $FIRMWARE"
                RAW_VENDOR="$(find_vendor_img "$WORK")" || die "no vendor.img inside $FIRMWARE"
                ;;
            *) die "unsupported input: $FIRMWARE (use .tgz/.tar.gz/.tar.xz/.zip/.img or a directory)" ;;
        esac
    fi
fi
echo "  vendor image: $RAW_VENDOR ($(stat -c %s "$RAW_VENDOR") bytes)"

# ---------------------------------------------------------------------------
# 2. sparse -> raw
# ---------------------------------------------------------------------------
echo "==> normalising vendor image"
CONVERTED="$WORK/vendor.raw.img"
if [ "$DRY_RUN" = 1 ]; then
    python3 "${ROOT}/tools/simg2img.py" --info "$RAW_VENDOR" | sed 's/^/  /'
    IMG_FOR_READ="$RAW_VENDOR"
else
    python3 "${ROOT}/tools/simg2img.py" "$RAW_VENDOR" "$CONVERTED" | sed 's/^/  /'
    IMG_FOR_READ="$CONVERTED"
fi
VENDOR_SHA256="$(sha256sum "$RAW_VENDOR" | cut -d' ' -f1)"
if [ -n "$FIRMWARE" ] && [ -f "$FIRMWARE" ]; then
    FIRMWARE_SHA256="$(sha256sum "$FIRMWARE" | cut -d' ' -f1)"
    FIRMWARE_NAME="$(basename "$FIRMWARE")"
else
    FIRMWARE_SHA256="(none - direct vendor image input)"
    FIRMWARE_NAME="(direct vendor image)"
fi

# ---------------------------------------------------------------------------
# 3. read-only access to the ext4 filesystem
# ---------------------------------------------------------------------------
EXTRACT_CMD=""
if command -v debugfs >/dev/null; then
    EXTRACT_CMD="debugfs"
else
    EXTRACT_CMD=""
fi
MOUNTED=0
if [ -z "$EXTRACT_CMD" ]; then
    if [ "$(id -u)" = 0 ] && command -v mount >/dev/null; then
        mkdir -p "$WORK/mnt"
        mount -o loop,ro "$IMG_FOR_READ" "$WORK/mnt" || die \
            "neither debugfs (e2fsprogs) nor a loop mount is available; install e2fsprogs"
        MOUNTED=1
        EXTRACT_CMD="mount"
        trap 'umount "$WORK/mnt" 2>/dev/null || true; cleanup' EXIT
        echo "==> using read-only loop mount (debugfs not installed)"
    else
        die "debugfs not found (package e2fsprogs). Install it, or run as root with loop-mount support."
    fi
fi
if [ "$EXTRACT_CMD" = "debugfs" ]; then
    echo "==> filesystem: $(dumpe2fs -h "$IMG_FOR_READ" 2>/dev/null | awk -F: '/Filesystem volume name|Filesystem features/{gsub(/^ +/,"",$2); printf "%s; ", $2}' || echo 'unknown')"
fi

# Extract one file; prints nothing on success, the reason on failure.
extract_one() { # <src> <dstabs>
    local src="$1" dst="$2"
    if [ "$EXTRACT_CMD" = "mount" ]; then
        [ -f "$WORK/mnt/$src" ] || return 1
        mkdir -p "$(dirname "$dst")"
        cp -f "$WORK/mnt/$src" "$dst"
        return 0
    fi
    mkdir -p "$(dirname "$dst")"
    local out
    out="$(debugfs -R "dump /${src} ${dst}" "$IMG_FOR_READ" 2>&1 || true)"
    if [ ! -s "$dst" ]; then
        printf '%s' "$out" >&2
        return 1
    fi
    return 0
}

probe_one() { # <src> -> 0 if present
    local src="$1"
    if [ "$EXTRACT_CMD" = "mount" ]; then
        [ -f "$WORK/mnt/$src" ]
        return
    fi
    # debugfs exits 0 even when the file is missing, so inspect its output.
    local out
    out="$(debugfs -R "stat /${src}" "$IMG_FOR_READ" 2>&1 || true)"
    case "$out" in
        *"File not found"*|*"not found"*) return 1 ;;
        *Inode:*) return 0 ;;
        *) return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# 4. prove this is a sakura Android 9 vendor image before extracting
# ---------------------------------------------------------------------------
read_prop() { # <src build.prop> <key>
    local src="$1" key="$2" tmp
    [ -n "$src" ] || return 1
    tmp="$WORK/probe.prop"
    rm -f "$tmp"
    if [ "$EXTRACT_CMD" = "mount" ]; then
        [ -f "$WORK/mnt/$src" ] || return 1
        cp -f "$WORK/mnt/$src" "$tmp"
    else
        debugfs -R "dump /${src} ${tmp}" "$IMG_FOR_READ" >/dev/null 2>&1 || true
        [ -s "$tmp" ] || return 1
    fi
    grep -E "^${key}=" "$tmp" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r'
}

PROP_CANDIDATES=("build.prop" "vendor/build.prop" "etc/build.prop")
BUILD_FINGERPRINT=""
for cand in "${PROP_CANDIDATES[@]}"; do
    val="$(read_prop "$cand" ro.vendor.build.fingerprint || true)"
    [ -n "$val" ] || val="$(read_prop "$cand" ro.build.fingerprint || true)"
    if [ -n "$val" ]; then BUILD_FINGERPRINT="$val"; PROP_FILE="$cand"; break; fi
done
DEVICE_NAME=""
for cand in "${PROP_CANDIDATES[@]}"; do
    val="$(read_prop "$cand" ro.product.device || true)"
    [ -n "$val" ] || val="$(read_prop "$cand" ro.vendor.product.device || true)"
    [ -n "$val" ] && { DEVICE_NAME="$val"; break; }
done
ANDROID_REL=""
for cand in "${PROP_CANDIDATES[@]}"; do
    val="$(read_prop "$cand" ro.build.version.release || true)"
    [ -n "$val" ] || val="$(read_prop "$cand" ro.vendor.build.version.release || true)"
    [ -n "$val" ] && { ANDROID_REL="$val"; break; }
done
SEC_PATCH=""
for cand in "${PROP_CANDIDATES[@]}"; do
    val="$(read_prop "$cand" ro.build.version.security_patch || true)"
    [ -n "$val" ] && { SEC_PATCH="$val"; break; }
done

echo "==> image identity"
note "build fingerprint : ${BUILD_FINGERPRINT:-<not found>}"
note "ro.product.device : ${DEVICE_NAME:-<not found>}"
note "android release   : ${ANDROID_REL:-<not found>}"
note "security patch    : ${SEC_PATCH:-<not found>}"

if [ "$DRY_RUN" = 0 ]; then
    [ -n "$DEVICE_NAME" ] || die "cannot read ro.product.device from the vendor image; refusing to extract blobs from an unidentified image"
    if [ "$DEVICE_NAME" != "sakura" ]; then
        die "vendor image is for '${DEVICE_NAME}', not 'sakura'. Refusing to mix another device's TEE blobs into this port (the Daisy-derived list is exactly the mistake this check exists to prevent)."
    fi
    case "$ANDROID_REL" in
        9|9.0) ;;
        "") note "WARNING: no ro.build.version.release found; expected 9 (Android 9)" ;;
        *) die "vendor image reports Android ${ANDROID_REL}; sakura's supported stock base is Android 9" ;;
    esac
    case "$BUILD_FINGERPRINT" in
        *PDMMIXM*|*PDICNXM*|*PDI*) ;;
        "") note "WARNING: no build fingerprint found; cannot confirm the MIUI build" ;;
        *) note "WARNING: fingerprint '${BUILD_FINGERPRINT}' is not a known sakura Android 9 build (V12.0.4.0.PDMMIXM / V12.0.1.0.PDICNXM)" ;;
    esac
fi

# ---------------------------------------------------------------------------
# 5. extract + validate
# ---------------------------------------------------------------------------
[ "$DRY_RUN" = 1 ] || { mkdir -p "$OUT"; echo "==> extracting into $OUT"; }

REPORT_ROWS=()
MISSING_REQUIRED=0
MISSING_OPTIONAL=0
EXTRACTED=0
HASH_MISMATCH=0

sha256_of() { sha256sum "$1" | cut -d' ' -f1; }

for i in "${!SRC_LIST[@]}"; do
    src="${SRC_LIST[$i]}"
    dst="${DST_LIST[$i]}"
    req="${REQ_LIST[$i]}"
    want="${SHA_LIST[$i]}"
    srcclean="${src#/}"; srcclean="${srcclean#vendor/}"

    found=""
    for cand in "$srcclean" "$src" "vendor/$srcclean"; do
        cand="${cand#/}"
        if probe_one "$cand"; then found="$cand"; break; fi
    done

    if [ -z "$found" ]; then
        if [ "$req" = "required" ]; then
            MISSING_REQUIRED=$((MISSING_REQUIRED + 1))
            note "MISSING (required): $src"
            REPORT_ROWS+=("| $dst | **MISSING (required)** | - | - |")
        else
            MISSING_OPTIONAL=$((MISSING_OPTIONAL + 1))
            note "absent (optional): $src"
            REPORT_ROWS+=("| $dst | absent (optional) | - | - |")
        fi
        continue
    fi

    if [ "$DRY_RUN" = 1 ]; then
        note "would extract: $found -> $dst"
        REPORT_ROWS+=("| $dst | present (dry run) | - | - |")
        continue
    fi

    target="$OUT/$dst"
    if ! extract_one "$found" "$target"; then
        [ "$req" = "required" ] && MISSING_REQUIRED=$((MISSING_REQUIRED + 1)) || MISSING_OPTIONAL=$((MISSING_OPTIONAL + 1))
        note "FAILED to extract: $found -> $dst"
        REPORT_ROWS+=("| $dst | **extraction failed** | - | - |")
        continue
    fi

    size="$(stat -c %s "$target")"
    [ "$size" -gt 0 ] || die "extracted $dst is empty"

    elf_info="$(python3 "${ROOT}/tools/elf.py" "$target" 2>&1 || true)"
    case "$elf_info" in
        *"not an ELF"*|*FAIL*)
            die "$dst is not an ELF file - refusing to install it as a service/library. Output: ${elf_info}"
            ;;
    esac
    case "$elf_info" in
        *"64-bit AArch64"*) ;;
        *) die "$dst has the wrong architecture for this 64-bit only ramdisk: ${elf_info//$'\n'/ }" ;;
    esac

    got="$(sha256_of "$target")"
    if [ "$want" != "-" ] && [ -n "$want" ] && [ "$want" != "$got" ]; then
        HASH_MISMATCH=$((HASH_MISMATCH + 1))
        note "SHA-256 MISMATCH for $dst (manifest $want, file $got)"
    fi
    EXTRACTED=$((EXTRACTED + 1))
    note "ok: $dst  $(numfmt --to=iec "$size" 2>/dev/null || echo "$size B")  sha256 $got"
    REPORT_ROWS+=("| $dst | extracted, ELF ok | $size | \`$got\` |")
done

# ---------------------------------------------------------------------------
# 6. local-only manifest + provenance report
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
    echo
    echo "DRY RUN: nothing was written."
    [ "$MISSING_REQUIRED" = 0 ] || { echo "RESULT: $MISSING_REQUIRED required file(s) absent from this image."; exit 1; }
    echo "RESULT: all required files are present in the supplied image."
    exit 0
fi

{
    echo "# Local-only checksum manifest for the QTI TEE chain."
    echo "# Generated by build/extract_blobs.sh - NOT committed (see .gitignore)."
    echo "# source firmware : $FIRMWARE_NAME"
    echo "# firmware sha256 : $FIRMWARE_SHA256"
    echo "# vendor.img sha256: $VENDOR_SHA256"
    echo "# fingerprint     : ${BUILD_FINGERPRINT:-unknown}"
    echo "# android release : ${ANDROID_REL:-unknown}"
    echo "# security patch  : ${SEC_PATCH:-unknown}"
    echo "# generated (utc) : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "#"
} > "$OUT/MANIFEST.sha256"
# Paths are recorded ramdisk-relative (no leading "./") because
# build/install_blobs.sh and build/check_crypto_blobs.sh consume them directly.
( cd "$OUT" && find . -type f ! -name 'MANIFEST.sha256' ! -name 'EXTRACTION_REPORT.md' \
    -printf '%P\0' | sort -z | xargs -0 -r sha256sum ) >> "$OUT/MANIFEST.sha256"

{
    echo "# QTI TEE blob extraction report"
    echo
    echo "Generated by \`build/extract_blobs.sh\` on $(date -u +%Y-%m-%dT%H:%M:%SZ)."
    echo "This file and the blobs beside it are **local only** and gitignored."
    echo
    echo "## Source provenance"
    echo
    echo "| Field | Value |"
    echo "| --- | --- |"
    echo "| Firmware input | \`$FIRMWARE_NAME\` |"
    echo "| Firmware SHA-256 | \`$FIRMWARE_SHA256\` |"
    echo "| vendor.img SHA-256 | \`$VENDOR_SHA256\` |"
    echo "| Image size | $(stat -c %s "$RAW_VENDOR") bytes |"
    echo "| ro.product.device | \`${DEVICE_NAME:-unknown}\` |"
    echo "| Android release | \`${ANDROID_REL:-unknown}\` |"
    echo "| Security patch | \`${SEC_PATCH:-unknown}\` |"
    echo "| Build fingerprint | \`${BUILD_FINGERPRINT:-unknown}\` |"
    echo "| Extractor | build/extract_blobs.sh @ $(cd "$ROOT" && git rev-parse --short HEAD 2>/dev/null || echo 'no-git') |"
    echo "| e2fsprogs | $(debugfs -V 2>&1 | head -1 | tr -d '\n' || echo unknown) |"
    echo
    echo "## Files"
    echo
    echo "| Ramdisk path | Status | Bytes | SHA-256 |"
    echo "| --- | --- | --- | --- |"
    for row in "${REPORT_ROWS[@]}"; do echo "$row"; done
    echo
    echo "## Status chain"
    echo
    echo "- listed in proprietary-files.txt: yes (${#SRC_LIST[@]} entries)"
    echo "- extracted: $EXTRACTED"
    echo "- ELF-validated (64-bit AArch64): $EXTRACTED"
    echo "- missing required: $MISSING_REQUIRED"
    echo "- absent optional: $MISSING_OPTIONAL"
    echo "- hash mismatches: $HASH_MISMATCH"
    echo "- copied into a ramdisk: NOT YET (run build/install_blobs.sh, then build)"
    echo "- init-referenced: checked by tools/check_init_services.py at build time"
    echo "- runtime-tested on hardware: **NO**"
    echo
    echo "Decryption remains **untested** until the built image is booted on a"
    echo "sakura with encrypted /data. Nothing here proves runtime decryption."
} > "$OUT/EXTRACTION_REPORT.md"

echo
echo "==> extracted $EXTRACTED file(s) into $OUT"
echo "    report   : $OUT/EXTRACTION_REPORT.md"
echo "    checksums: $OUT/MANIFEST.sha256"

if [ "$MISSING_REQUIRED" != 0 ]; then
    echo
    echo "RESULT: FAIL - $MISSING_REQUIRED required file(s) are not in this image."
    echo "        Either the wrong firmware/build was supplied (expected a sakura"
    echo "        Android 9 fastboot ROM) or the manifest needs a correction backed"
    echo "        by evidence. Do not fabricate the missing files."
    exit 1
fi
if [ "$HASH_MISMATCH" != 0 ]; then
    echo "RESULT: FAIL - $HASH_MISMATCH file(s) did not match a recorded SHA-256."
    exit 1
fi
echo "RESULT: PASS (extraction). Next: ./build/install_blobs.sh, then build."
echo "        Runtime decryption is still UNTESTED on hardware."
