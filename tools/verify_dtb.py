#!/usr/bin/env python3
"""
verify_dtb.py - prove that a kernel blob really targets Xiaomi Redmi 6 Pro.

sakura's kernel is packed as `Image.gz` + an appended multi-DTB, and the DTBs
are generic Qualcomm board files (qcom,msm8953-mtp / -cdp / -qrd-sku3 ...), so
searching for the string "sakura" in the *compatible* list finds nothing. The
real sakura fingerprint is in the camera and panel nodes. This tool checks
those, plus the kernel version banner and the capability strings the R12 port
depends on (fscrypt, f2fs).

Usage:
  verify_dtb.py <Image.gz-dtb | Image | boot.img> [--json]

Exit codes: 0 = all required checks passed, 1 = a required check failed.
"""
import json
import re
import struct
import sys
import zlib

# Camera sensor nodes present in both the R11 stock DTB set and the 4.9
# community DTB set. sakura = IMX486/OV12A10 era; sakura_india variants share
# the OV5675/S5K5E8 front sensors.
REQUIRED_CAMERA = [
    "sakura_imx486_ofilm",
    "sakura_ov12a10_sunny",
    "sakura_ov5675_ofilm",
    "sakura_ov5675_qtech",
    "sakura_s5k5e8_ofilm",
    "sakura_s5k5e8_sunny",
]
# At least one panel family must be present: sakura shipped ili7807 and
# nt36672 FHD+ panels.
REQUIRED_PANEL_ANY = ["mdss_dsi_ili7807_fhdplus_video", "nt36672"]
# Kernel capabilities the R12 port needs (see documentation/ENCRYPTION.md).
REQUIRED_CAPS = {"fscrypt": b"fscrypt_"}
WARN_CAPS = {"f2fs": b"F2FS", "ice": b"ice_", "dm-crypt": b"kcryptd"}


def gunzip_member(data):
    """Decompress the first gzip member; return (payload, bytes_consumed)."""
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(data)
    return out, len(data) - len(d.unused_data)


def split_fdts(blob):
    """Yield (offset, totalsize, payload) for each concatenated FDT."""
    i = 0
    while True:
        i = blob.find(b"\xd0\x0d\xfe\xed", i)
        if i < 0:
            return
        if i + 8 > len(blob):
            return
        (total,) = struct.unpack(">I", blob[i + 4:i + 8])
        if total < 64 or total > len(blob) - i:
            i += 4
            continue
        yield i, total, blob[i:i + total]
        i += total


def analyse(path):
    raw = open(path, "rb").read()
    report = {"path": path, "file_size": len(raw), "checks": {}, "errors": []}

    # boot.img -> keep only the kernel slot
    if raw[:8] == b"ANDROID!":
        (ksize,) = struct.unpack("<I", raw[8:12])
        (psize,) = struct.unpack("<I", raw[36:40])
        report["input"] = "android boot image"
        raw = raw[psize:psize + ksize]
        report["kernel_slot_size"] = len(raw)

    kernel, ramdisk = raw, b""
    if raw[:2] == b"\x1f\x8b":
        kernel, used = gunzip_member(raw)
        ramdisk = raw[used:]
        report["input"] = "gzip Image"
        report["kernel_image_size"] = len(kernel)
        report["appended_dtb_bytes"] = len(ramdisk)
    else:
        report["input"] = "raw Image"

    # ARM64 Image sanity
    report["arm64_magic"] = kernel[0x38:0x3C].decode("latin-1")
    report["checks"]["arm64_image"] = kernel[0x38:0x3C] == b"ARMd"

    m = re.search(rb"Linux version ([^\x00]{0,120})", kernel)
    report["kernel_version"] = m.group(1).decode("latin-1") if m else None
    report["checks"]["version_4_9_or_newer"] = bool(
        m and re.match(rb"4\.(9|1[4-9]|[2-9][0-9])", m.group(1)))

    for name, pat in REQUIRED_CAPS.items():
        report["checks"][f"cap_{name}"] = pat in kernel
    report["warn_caps"] = {k: (p in kernel) for k, p in WARN_CAPS.items()}

    # DTBs
    fdts = list(split_fdts(ramdisk))
    report["dtb_count"] = len(fdts)
    dtb_text = b"".join(p for _, _, p in fdts)
    report["checks"]["has_dtb"] = len(fdts) > 0
    cams = [c for c in REQUIRED_CAMERA if c.encode() in dtb_text]
    report["camera_nodes_found"] = cams
    report["checks"]["sakura_camera_nodes"] = len(cams) >= 3
    panels = [p for p in REQUIRED_PANEL_ANY if p.encode() in dtb_text]
    report["panel_nodes_found"] = panels
    report["checks"]["sakura_panel_nodes"] = len(panels) > 0

    for k, v in report["checks"].items():
        if not v and not k.startswith("version_"):
            report["errors"].append(f"failed check: {k}")
    report["ok"] = all(report["checks"].values())
    return report


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    path = argv[1]
    try:
        r = analyse(path)
    except (OSError, ValueError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if "--json" in argv:
        print(json.dumps(r, indent=2))
    else:
        print(f"file                : {r['path']} ({r['file_size']} bytes)")
        print(f"input               : {r['input']}")
        if "kernel_image_size" in r:
            print(f"kernel (gzip -> raw): {r['kernel_image_size']} bytes")
            print(f"appended DTB region : {r['appended_dtb_bytes']} bytes")
        print(f"arm64 magic         : {r['arm64_magic']!r}")
        print(f"kernel version      : {r['kernel_version']}")
        print(f"DTB count           : {r['dtb_count']}")
        print(f"sakura camera nodes : {len(r['camera_nodes_found'])}/6 -> {r['camera_nodes_found']}")
        print(f"sakura panel nodes  : {r['panel_nodes_found']}")
        print("checks:")
        for k, v in r["checks"].items():
            print(f"  [{'PASS' if v else 'FAIL'}] {k}")
        print("optional capabilities:")
        for k, v in r["warn_caps"].items():
            print(f"  [{'yes' if v else 'no '}] {k}")
        print(f"\nRESULT: {'PASS' if r['ok'] else 'FAIL'}")
        for e in r["errors"]:
            print(f"  - {e}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
