#!/usr/bin/env bash
#
# fetch_kernel.sh - place a verified sakura kernel at
# device/xiaomi/sakura/prebuilt/Image.gz-dtb
#
# The binary is not committed (8.7 MB, third-party compiled artifact). This
# script fetches the verified 4.9.278 candidate, checks its SHA-256 and then
# proves it targets sakura before installing it.
#
# Read device/xiaomi/sakura/prebuilt/README.md first: the provenance of this
# binary is daisy-lineage and should be replaced by a clean rebuild for a
# release-quality build.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${ROOT}/device/xiaomi/sakura/prebuilt/Image.gz-dtb"
TMP="$(mktemp)"

SRC_URL="https://raw.githubusercontent.com/msm8953E/device_xiaomi_sakura_twrp/ofx-12.1/prebuilt/Image.gz-dtb"
EXPECT_SHA256="d12f816aef3572be156596e0b0c5607c56b309eea4b3e06f052d8509b9867764"

echo "==> downloading kernel candidate"
curl -fL --retry 3 --retry-delay 2 -H "User-Agent: fox-port-research/1.0" -o "${TMP}" "${SRC_URL}"

actual=$(sha256sum "${TMP}" | cut -d' ' -f1)
if [ "${actual}" != "${EXPECT_SHA256}" ]; then
    echo "FAIL: SHA-256 mismatch" >&2
    echo "  expected ${EXPECT_SHA256}" >&2
    echo "  actual   ${actual}" >&2
    rm -f "${TMP}"; exit 1
fi
echo "==> SHA-256 OK"

echo "==> verifying sakura DTB fingerprints"
if ! python3 "${ROOT}/tools/verify_dtb.py" "${TMP}"; then
    echo "FAIL: kernel does not look like a sakura kernel; not installing" >&2
    rm -f "${TMP}"; exit 1
fi

install -D -m 0644 "${TMP}" "${DEST}"
rm -f "${TMP}"
echo "==> installed ${DEST}"
sha256sum "${DEST}"
