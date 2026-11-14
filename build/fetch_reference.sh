#!/usr/bin/env bash
#
# fetch_reference.sh - download and verify the official R11.0_5 recovery ZIP,
# then unpack it for analysis.
#
# The 46.5 MB ZIP is NEVER committed to this repository. This script reproduces
# it from the official OrangeFox mirror and refuses to continue on a checksum
# mismatch, so the analysis cannot silently run against a different artifact.
#
set -euo pipefail

RELEASE_ID="6056efa3ee1435a74b093dd6"
URL="https://dl.orangefox.download/${RELEASE_ID}"
ZIP_NAME="OrangeFox-sakura-stable@R11.0_5.zip"
EXPECT_MD5="5dff190fe5e86631bd58c049a9b5f924"
EXPECT_SHA256="461e60c823bdc29343a0686ba774f62a775979e920676354d08e0c1735ae92e8"
EXPECT_SIZE=46500245

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF_DIR="${REF_DIR:-${ROOT}/reference}"
mkdir -p "${REF_DIR}"

echo "==> reference dir: ${REF_DIR}"

if [ ! -f "${REF_DIR}/${ZIP_NAME}" ]; then
    echo "==> downloading ${ZIP_NAME}"
    curl -fL --retry 3 --retry-delay 2 \
         -H "User-Agent: fox-port-research/1.0" \
         -o "${REF_DIR}/${ZIP_NAME}.part" "${URL}"
    mv "${REF_DIR}/${ZIP_NAME}.part" "${REF_DIR}/${ZIP_NAME}"
else
    echo "==> already present, verifying"
fi

actual_size=$(stat -c %s "${REF_DIR}/${ZIP_NAME}")
[ "${actual_size}" = "${EXPECT_SIZE}" ] || {
    echo "FAIL: size ${actual_size} != ${EXPECT_SIZE}" >&2; exit 1; }

echo "${EXPECT_MD5}  ${REF_DIR}/${ZIP_NAME}" | md5sum -c - || {
    echo "FAIL: MD5 mismatch - refusing to use this artifact" >&2; exit 1; }
echo "${EXPECT_SHA256}  ${REF_DIR}/${ZIP_NAME}" | sha256sum -c - || {
    echo "FAIL: SHA-256 mismatch" >&2; exit 1; }

# Extract without executing anything from the archive.
if [ ! -f "${REF_DIR}/recovery.img" ]; then
    echo "==> extracting recovery.img + metadata"
    tmp="$(mktemp -d)"
    unzip -q -o "${REF_DIR}/${ZIP_NAME}" -d "${tmp}"
    cp "${tmp}/recovery.img" "${REF_DIR}/recovery.img"
    # keep the small metadata files: they document the original build config
    mkdir -p "${REF_DIR}/meta"
    cp -r "${tmp}/META-INF/debug/." "${REF_DIR}/meta/" 2>/dev/null || true
    cp "${tmp}/META-INF/com/google/android/update-binary" "${REF_DIR}/meta/" 2>/dev/null || true
    rm -rf "${tmp}"
fi

echo "==> unpacking boot image and ramdisk"
python3 "${ROOT}/tools/bootimg.py" unpack "${REF_DIR}/recovery.img" "${REF_DIR}/unpacked"
python3 "${ROOT}/tools/bootimg.py" cpiotoc "${REF_DIR}/unpacked/ramdisk.cpio" "${REF_DIR}/ramdisk"

echo "==> verifying the packaged kernel really is sakura's"
python3 "${ROOT}/tools/verify_dtb.py" "${REF_DIR}/unpacked/kernel" || true

cat <<EOF

Done. Reference artifacts in ${REF_DIR} (git-ignored):
  ${ZIP_NAME}
  recovery.img          (44 687 360 bytes)
  unpacked/{kernel,ramdisk.cpio,kernel.uncompressed}
  ramdisk/              (2 322 entries)
  meta/                 (fox_build_vars.txt, default.prop, update-binary)
EOF
