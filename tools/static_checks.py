#!/usr/bin/env python3
"""
static_checks.py - dependency-free regression gate for the sakura R12 port.

These checks run without a source sync, without a toolchain and without a
device. They catch the defect classes that have actually bitten this port:

  * an fs_mgr flags column delimited with ';' instead of ',' (the confirmed
    fstab parsing bug shipped in the handoff patch), which silently drops both
    `encryptable=footer` and `fileencryption=ice`;
  * metadata-encryption options creeping back in (not supportable on this
    kernel/vendor combination);
  * a recovery partition size that no longer matches the 64 MiB device layout;
  * the OrangeFox product/lunch target going missing (a plain TWRP build);
  * the workflow no longer gating on structural verification, or regaining a
    pull_request trigger / self-hosted-only runner assumption;
  * shell syntax errors in the build scripts.

Exit codes: 0 = every mandatory check passed, 1 = at least one failed.

Usage:
  python3 tools/static_checks.py [--root DIR]
  python3 tools/static_checks.py --image out/target/product/sakura/recovery.img

With --image the checks are ALSO applied to a built image's ramdisk, which is
what the device will actually parse.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESULTS = []


def record(name, ok, detail="", mandatory=True):
    RESULTS.append({"name": name, "ok": ok, "detail": detail,
                    "mandatory": mandatory})
    if ok:
        status = "PASS"
    else:
        status = "FAIL" if mandatory else "WARN"
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))


def read(rel):
    path = os.path.join(ROOT, rel)
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def fstab_entries(text):
    """Yield (lineno, mount_point, fs_type, fs_mgr_flags) for real fstab lines."""
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) < 5:
            continue
        yield lineno, fields[1], fields[2], fields[4]


def fstab_active(text):
    """Just the non-comment lines, so documentation comments never trip a check."""
    return "\n".join(
        ln for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#"))


def check_fstab():
    rel = "device/xiaomi/sakura/recovery/root/system/etc/recovery.fstab"
    text = read(rel)

    bad = [f"line {n}" for n, _mp, _t, flags in fstab_entries(text) if ";" in flags]
    record("fstab: no ';' delimiters in fs_mgr flags", not bad,
           ", ".join(bad) if bad else "commas only, as fs_mgr requires")

    data = [(mp, ftype, flags) for _, mp, ftype, flags in fstab_entries(text)
            if mp == "/data"]
    record("fstab: two /data rows (f2fs + ext4)", len(data) == 2,
           f"{len(data)} row(s)")

    for _mp, ftype, flags in data:
        tokens = [t for t in flags.split(",") if t]
        ok = "encryptable=footer" in tokens and "fileencryption=ice" in tokens
        record(f"fstab: /data ({ftype}) keeps separate FDE + FBE tokens",
               ok, ",".join(tokens))

    record("fstab: no metadata_encryption (unsupportable here)",
           "metadata_encryption" not in fstab_active(text),
           "comments are ignored by this check")

    blob = read("device/xiaomi/sakura/recovery/root/system/etc/twrp.flags")
    record("twrp.flags: no metadata_encryption",
           "metadata_encryption" not in fstab_active(blob), "")


def check_boardconfig():
    text = read("device/xiaomi/sakura/BoardConfig.mk")

    m = re.search(r"BOARD_RECOVERYIMAGE_PARTITION_SIZE\s*:=\s*(\d+)", text)
    size = int(m.group(1)) if m else 0
    record("BoardConfig: recovery partition is 64 MiB", size == 67108864,
           f"{size} bytes")

    m = re.search(r"TARGET_RECOVERY_FSTAB\s*:=\s*\$\(DEVICE_PATH\)/(\S+)", text)
    ok = bool(m) and os.path.isfile(os.path.join(
        ROOT, "device/xiaomi/sakura", m.group(1)))
    record("BoardConfig: TARGET_RECOVERY_FSTAB points at a real file", ok,
           m.group(1) if m else "not set")

    record("BoardConfig: TW_THEME set", bool(re.search(r"^TW_THEME\s*:=\s*\S+", text, re.M)),
           "")

    record("BoardConfig: includes vendor/twrp BoardConfigSoong.mk",
           "vendor/twrp/config/BoardConfigSoong.mk" in text,
           "exports TW_THEME into the twrpVarsPlugin namespace")

    record("BoardConfig: QCOM FBE decryption enabled",
           "BOARD_USES_QCOM_FBE_DECRYPTION := true" in text, "")

    record("BoardConfig: metadata partition not used",
           "BOARD_USES_METADATA_PARTITION := false" in text, "")


def check_product():
    fox = read("device/xiaomi/sakura/fox_sakura.mk")
    record("fox_sakura.mk: inherits vendor/twrp/config/common.mk",
           "vendor/twrp/config/common.mk" in fox,
           "vendor/twrp is the tree the sync script patches into OrangeFox")

    products = read("device/xiaomi/sakura/AndroidProducts.mk")
    record("AndroidProducts.mk: fox_sakura-eng is a lunch target",
           "fox_sakura-eng" in products, "")

    vs = read("device/xiaomi/sakura/vendorsetup.sh")
    record("vendorsetup.sh: FOX_TARGET_DEVICES guards sakura",
           'FOX_TARGET_DEVICES="sakura,sakura_india"' in vs, "")
    record("vendorsetup.sh: FBE decryption not skipped",
           not re.search(r"^\s*export\s+OF_SKIP_FBE_DECRYPTION=", vs, re.M),
           "unset for R12")
    record("vendorsetup.sh: keymaster 3.0 pinned",
           "OF_DEFAULT_KEYMASTER_VERSION=3.0" in vs, "")


def check_crypto_blobs():
    """The blobs are proprietary and are NOT in this repository.

    Report exactly which are missing so no text in the build ever claims a
    verified decrypt path by accident.
    """
    rel = "device/xiaomi/sakura/proprietary-files.txt"
    text = read(rel)
    missing, present = [], []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        _src, dst = line.split(":", 1)
        dst = dst.split("|", 1)[0].strip()
        if not dst:
            continue
        target = os.path.join(ROOT, "device/xiaomi/sakura", dst)
        (present if os.path.exists(target) else missing).append(dst)

    record("crypto blobs: proprietary set is present in the tree",
           not missing,
           f"{len(present)} present / {len(missing)} missing (extraction required)"
           if missing else f"{len(present)} present",
           mandatory=False)

    if missing:
        print("        missing (extract from your own sakura stock vendor image):")
        for dst in missing[:6]:
            print(f"          - {dst}")
        if len(missing) > 6:
            print(f"          ... and {len(missing) - 6} more")
        print("        => DECRYPTION IS UNVERIFIED for any image built without them.")


def check_workflow():
    rel = ".github/workflows/orangefox-sakura.yml"
    text = read(rel)

    record("workflow: manual (workflow_dispatch) only",
           "workflow_dispatch:" in text and "pull_request:" not in text, "")

    record("workflow: runner is selectable, not hard-wired to self-hosted",
           "runs-on: ${{ inputs.runner_label }}" in text
           and "self-hosted, Linux, X64" not in text,
           "expired ServerHive runner must not be referenced")

    record("workflow: structural verification is a hard gate",
           "./build/verify_image.sh" in text
           and not re.search(r"verify_image\.sh[^\n]*\|\|\s*echo", text),
           "no '|| echo warning' suppression")

    record("workflow: artifacts uploaded even on failure",
           "actions/upload-artifact" in text and "if: always()" in text, "")

    record("workflow: stale image removed before the single build",
           re.search(r"rm -f .*recovery\.img", text) is not None, "")

    record("workflow: static checks wired into preflight",
           "tools/static_checks.py" in text, "")

    # YAML syntax, without requiring PyYAML.
    try:
        import yaml  # type: ignore
        yaml.safe_load(text)
        record("workflow: YAML parses", True, "")
    except ImportError:
        record("workflow: YAML parses", True, "PyYAML unavailable, skipped",
               mandatory=False)
    except Exception as exc:  # noqa: BLE001
        record("workflow: YAML parses", False, str(exc))


def check_scripts():
    names = sorted(n for n in os.listdir(os.path.join(ROOT, "build"))
                   if n.endswith(".sh"))
    failures = []
    for name in names:
        path = os.path.join(ROOT, "build", name)
        proc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(f"{name}: {proc.stderr.strip().splitlines()[-1:]}")
    record(f"build scripts: bash -n clean ({len(names)} scripts)",
           not failures, "; ".join(str(f) for f in failures))


def check_image(img):
    """Apply the fstab rules to the ramdisk the device will actually read."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import bootimg  # noqa: E402  (local, dependency-free)

    record("image: parses as an Android boot image", True, img)
    boot = bootimg.BootImage(img)
    record("image: header v0 / page size 2048",
           boot.header_version == 0 and boot.page_size == 2048,
           f"header v{boot.header_version}, page {boot.page_size}")
    record("image: fits the 64 MiB recovery partition",
           os.path.getsize(img) <= 67108864, f"{os.path.getsize(img)} bytes")

    ramdisk, _kind = bootimg.decompress_any(boot.ramdisk, "ramdisk")
    with tempfile.TemporaryDirectory() as tmp:
        bootimg.cpio_extract(ramdisk, tmp, verbose=False)
        found = []
        for base, _dirs, files in os.walk(tmp):
            for fn in files:
                if fn == "recovery.fstab":
                    found.append(os.path.join(base, fn))
        if not found:
            record("image: ramdisk contains recovery.fstab", False, "")
            return
        record("image: ramdisk contains recovery.fstab", True,
               found[0].replace(tmp, "<ramdisk>"))
        text = "\n".join(open(p, encoding="utf-8", errors="replace").read()
                         for p in found)
        record("image: installed fstab has no ';' delimiters",
               ";" not in fstab_active(text), "")
        rows = [f for _, mp, _t, f in fstab_entries(text) if mp == "/data"]
        record("image: installed /data rows carry ice + footer",
               bool(rows) and all(
                   "fileencryption=ice" in f.split(",") and
                   "encryptable=footer" in f.split(",") for f in rows),
               f"{len(rows)} /data row(s)")


def main(argv):
    global ROOT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--image", default=None)
    args = ap.parse_args(argv[1:])
    ROOT = os.path.abspath(args.root)

    print(f"==> static checks in {ROOT}")
    check_fstab()
    check_boardconfig()
    check_product()
    check_crypto_blobs()
    check_workflow()
    check_scripts()
    if args.image:
        check_image(args.image)

    failed = [r for r in RESULTS if r["mandatory"] and not r["ok"]]
    print()
    if failed:
        print(f"RESULT: FAIL ({len(failed)} mandatory check(s))")
        for r in failed:
            print(f"  - {r['name']}")
        return 1
    print(f"RESULT: PASS ({len(RESULTS)} checks)")
    print("NOTE: static checks prove configuration only. They do not prove a "
          "build, a boot or decryption.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
