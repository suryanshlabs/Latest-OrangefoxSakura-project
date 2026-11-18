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

    # The variables the pinned bootable/recovery actually reads (Android.mk
    # 339-342: TW_INCLUDE_CRYPTO implies TW_INCLUDE_CRYPTO_FBE + -DTW_INCLUDE_FBE;
    # prebuilt/Android.mk 194 and libtar/Android.mk 16/86 read
    # TW_INCLUDE_CRYPTO_FBE). BOARD_USES_QCOM_FBE_DECRYPTION and TW_INCLUDE_FBE
    # were dead: nothing in either pinned tree references them.
    record("BoardConfig: TW_INCLUDE_CRYPTO enabled",
           re.search(r"^TW_INCLUDE_CRYPTO\s*:=\s*true", text, re.M) is not None, "")
    record("BoardConfig: TW_INCLUDE_CRYPTO_FBE enabled (the real FBE switch)",
           re.search(r"^TW_INCLUDE_CRYPTO_FBE\s*:=\s*true", text, re.M) is not None, "")
    record("BoardConfig: dead crypto variables removed",
           "BOARD_USES_QCOM_FBE_DECRYPTION" not in fstab_active(text)
           and not re.search(r"^TW_INCLUDE_FBE\s*:", text, re.M),
           "BOARD_USES_QCOM_FBE_DECRYPTION / TW_INCLUDE_FBE are referenced by nothing")

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


def manifest_dests():
    """Ramdisk destinations listed in proprietary-files.txt (installed by the
    blob scripts, so they are not PRODUCT_COPY_FILES entries)."""
    dests = set()
    for line in read("device/xiaomi/sakura/proprietary-files.txt").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        dests.add(line.split(":", 1)[1].split("|", 1)[0].strip())
    return dests


def check_device_mk():
    """Every file of the device tree's recovery/root must actually be installed.

    PRODUCT_COPY_FILES is the only mechanism: the pinned trees do not copy a
    device tree's recovery/root automatically, so init.recovery.qcom.rc and
    twrp.flags silently never reached the ramdisk before this was added.
    """
    text = read("device/xiaomi/sakura/device.mk")
    blob_dests = manifest_dests()

    # Only PRODUCT_PACKAGES lines matter; the rc FILE is legitimately called
    # init.recovery.qcom_decrypt.rc.
    pkg_lines = [ln for ln in fstab_active(text).splitlines() if "PRODUCT_PACKAGES" in ln]
    record("device.mk: no nonexistent qcom_decrypt modules",
           not any("qcom_decrypt" in ln for ln in pkg_lines),
           "neither vendor/recovery 1998cfc nor bootable/recovery 8d2aad19 has them")

    record("device.mk: includes the generated blob fragment with -include",
           "-include $(DEVICE_PATH)/blob_install.mk" in text,
           "a clean clone has no blob_install.mk and must still parse")

    root = os.path.join(ROOT, "device/xiaomi/sakura/recovery/root")
    listed = set(re.findall(r"\)/recovery/root/(\S+?):recovery/root/", text))
    unlisted = []
    for base, _dirs, files in os.walk(root):
        for fn in files:
            full = os.path.join(base, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel == "system/etc/recovery.fstab":
                continue  # installed by TARGET_RECOVERY_FSTAB, not PRODUCT_COPY_FILES
            if rel in blob_dests:
                continue  # installed from the user's firmware by install_blobs.sh
            if rel.endswith("/.gitkeep"):
                continue
            if rel not in listed:
                unlisted.append(rel)
    record("device.mk: every recovery/root file is in PRODUCT_COPY_FILES",
           not unlisted,
           ", ".join(unlisted) if unlisted else f"{len(listed)} entr(y/ies) listed")


def check_init_service_paths():
    """Service executables, imports and library resolution, pre-build."""
    tool = os.path.join(ROOT, "tools/check_init_services.py")
    proc = subprocess.run([sys.executable, tool, "--device-tree",
                           os.path.join(ROOT, "device/xiaomi/sakura"),
                           "--require", "crypto"],
                          capture_output=True, text=True)
    detail = ""
    if proc.returncode != 0:
        fails = [ln.strip() for ln in proc.stdout.splitlines() if "[FAIL]" in ln]
        detail = "; ".join(fails[:3])
    record("init: service exec paths, imports and crypto chain resolve",
           proc.returncode == 0, detail)


def check_manifest():
    """proprietary-files.txt must describe installable, non-conflicting paths."""
    text = read("device/xiaomi/sakura/proprietary-files.txt")
    errors = []
    dests = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            errors.append(f"line {lineno}: no ':'")
            continue
        src, rest = line.split(":", 1)
        dest = rest.split("|", 1)[0].strip()
        fields = rest.split("|")
        if not src.strip():
            errors.append(f"line {lineno}: empty source")
        if not (dest.startswith("system/bin/") or dest.startswith("system/lib64/")):
            errors.append(f"line {lineno}: {dest} is outside the init/linker search paths")
        if len(fields) > 1 and fields[1].strip() not in ("required", "optional"):
            errors.append(f"line {lineno}: bad requirement '{fields[1].strip()}'")
        if len(fields) > 2:
            sha = fields[2].strip()
            if sha not in ("-", "") and not re.fullmatch(r"[0-9a-f]{64}", sha):
                errors.append(f"line {lineno}: bad sha256 '{sha}'")
        dests.append(dest)
    dupes = sorted({d for d in dests if dests.count(d) > 1})
    if dupes:
        errors.append("duplicate destinations: " + ", ".join(dupes))
    record("manifest: paths, requirements and hashes are well formed",
           not errors, "; ".join(errors[:4]))

    record("manifest: every ramdisk destination is a service or library path",
           all(d.startswith(("system/bin/", "system/lib64/")) for d in dests),
           f"{len(dests)} entries")


def check_tooling():
    """The extraction/install workflow must exist and be runnable."""
    for rel in ("build/extract_blobs.sh", "build/install_blobs.sh",
                "build/check_deps.sh", "tools/elf.py", "tools/simg2img.py",
                "tools/check_init_services.py"):
        path = os.path.join(ROOT, rel)
        record(f"tooling: {rel} exists and is executable",
               os.path.isfile(path) and os.access(path, os.X_OK), "")

    run_all = read("build/run-all.sh")
    record("run-all.sh: works with no arguments",
           'DEST="${1:-' in run_all,
           "SOURCE_DIR must default, not be required")
    record("run-all.sh: invokes extraction-install and the crypto gate",
           "install_blobs.sh" in run_all and "check_crypto_blobs.sh" in run_all, "")
    record("run-all.sh: calls the host preflight",
           "check_deps.sh" in run_all, "")

    gitingore = ".gitignore"
    try:
        gi = read(gitingore)
    except OSError:
        gi = ""
    record(".gitignore: proprietary blobs cannot be committed",
           all(p in gi for p in ("vendor_blobs", "blob_install.mk")),
           "vendor_blobs/, blob_install.mk and the installed blob dirs")


def check_diagnostics():
    """The early-boot collector and its GUI patch must be wired end to end."""
    script = "device/xiaomi/sakura/recovery/root/system/bin/sakura-diag"
    rc = "device/xiaomi/sakura/recovery/root/init.recovery.sakura_diag.rc"

    path = os.path.join(ROOT, script)
    record("diag: collector exists and is executable",
           os.path.isfile(path) and os.access(path, os.X_OK), script)
    if os.path.isfile(path):
        proc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        record("diag: collector shell syntax clean", proc.returncode == 0,
               proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "")

    record("diag: init service file exists",
           os.path.isfile(os.path.join(ROOT, rc)), rc)
    if os.path.isfile(os.path.join(ROOT, rc)):
        text = read(rc)
        record("diag: service declared and started on boot",
               "service sakura_diag /system/bin/sakura-diag" in text
               and "start sakura_diag" in text, "")

    qcom = read("device/xiaomi/sakura/recovery/root/init.recovery.qcom.rc")
    record("diag: device init imports the diagnostic fragment",
           "import /init.recovery.sakura_diag.rc" in qcom, "")

    dev = read("device/xiaomi/sakura/device.mk")
    record("diag: collector and rc are in PRODUCT_COPY_FILES",
           "recovery/root/system/bin/sakura-diag:recovery/root/system/bin/sakura-diag" in dev
           and "recovery/root/init.recovery.sakura_diag.rc:recovery/root/init.recovery.sakura_diag.rc" in dev,
           "the pinned trees do not copy recovery/root automatically")

    try:
        patch = read("patches/0001-theme-sakura-diagnostics.patch")
    except OSError:
        patch = ""
    record("diag: theme patch adds the Error Logs page",
           'page name="error_logs"' in patch, "patches/0001-theme-sakura-diagnostics.patch")
    record("diag: theme patch binds the error badge to the collector property",
           "property.of.boot_diag_errors" in patch, "")
    record("diag: theme patch only uses existing GUI actions",
           'function="cmd"' in patch and 'function="page"' in patch
           and 'function="set"' in patch, "cmd/set/page exist in the pinned GUI")


def check_patches():
    """Patch series, pinned revisions and the applicator must agree."""
    series = [ln.strip() for ln in read("patches/series").splitlines()
              if ln.strip() and not ln.strip().startswith("#")]
    record("patches: series is not empty", bool(series), f"{len(series)} entry(ies)")
    for entry in series:
        record(f"patches: {entry} exists",
               os.path.isfile(os.path.join(ROOT, "patches", entry)), "")

    pins = read("patches/PINNED_REVISIONS")
    sync = read("build/sync.sh")
    rec = re.search(r"^bootable_recovery=(\S+)", pins, re.M)
    record("patches: bootable/recovery pin matches build/sync.sh",
           bool(rec) and f'RECOVERY_SHA="{rec.group(1)}"' in sync,
           rec.group(1) if rec else "missing")
    ven = re.search(r"^vendor_recovery=(\S+)", pins, re.M)
    record("patches: vendor/recovery pin matches build/sync.sh",
           bool(ven) and f'VENDOR_SHA="{ven.group(1)}"' in sync,
           ven.group(1) if ven else "missing")

    apply = os.path.join(ROOT, "build/apply_patches.sh")
    record("patches: applicator exists and is executable",
           os.path.isfile(apply) and os.access(apply, os.X_OK), "")
    record("patches: theme validator exists",
           os.path.isfile(os.path.join(ROOT, "tools/check_theme.py")), "")


def check_docs():
    for rel in ("documentation/BUILD_FROM_CLEAN_CLONE.md",
                "documentation/DIAGNOSTICS.md",
                "documentation/BUG_AUDIT.md"):
        record(f"docs: {rel} exists", os.path.isfile(os.path.join(ROOT, rel)), "")
    try:
        readme = read("README.md")
        deps = read("documentation/DEPENDENCIES.md")
    except OSError as exc:
        record("docs: README/DEPENDENCIES readable", False, str(exc))
        return
    record("docs: README documents the blob extraction step",
           "extract_blobs.sh" in readme, "")
    record("docs: DEPENDENCIES documents the blob extraction step",
           "extract_blobs.sh" in deps, "")


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

    record("workflow: unit tests wired into preflight",
           "unittest discover" in text,
           "the patch/diagnostic logic must be tested on every build")

    record("workflow: tree refresh is not error-suppressed",
           "--relink-only" in text and "--relink-only \"$SRC\" 2>/dev/null || true" not in text,
           "a failed relink/patch must stop the build")

    record("workflow: decryption gate present with an explicit opt-out input",
           "check_crypto_blobs.sh" in text
           and "allow_missing_crypto" in text
           and "SAKURA_ALLOW_MISSING_CRYPTO" in text,
           "a build without the TEE chain must be an explicit, recorded choice")

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
    not_exec = []
    for name in names:
        path = os.path.join(ROOT, "build", name)
        proc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(f"{name}: {proc.stderr.strip().splitlines()[-1:]}")
        if not os.access(path, os.X_OK):
            not_exec.append(name)
    record(f"build scripts: bash -n clean ({len(names)} scripts)",
           not failures, "; ".join(str(f) for f in failures))
    record("build scripts: all executable", not not_exec, ", ".join(not_exec))

    py = sorted(n for n in os.listdir(os.path.join(ROOT, "tools"))
                if n.endswith(".py"))
    errors = []
    for name in py:
        path = os.path.join(ROOT, "tools", name)
        proc = subprocess.run([sys.executable, "-m", "py_compile", path],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            errors.append(f"{name}: {proc.stderr.strip().splitlines()[-1:]}")
    record(f"tools: python compiles ({len(py)} modules)", not errors,
           "; ".join(str(e) for e in errors))


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
    check_device_mk()
    check_init_service_paths()
    check_manifest()
    check_tooling()
    check_diagnostics()
    check_patches()
    check_crypto_blobs()
    check_docs()
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
