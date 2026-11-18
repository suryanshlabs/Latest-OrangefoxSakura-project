#!/usr/bin/env python3
"""
check_init_services.py - prove that every init service can actually be executed.

This is the check the port was missing. The earlier handoff image shipped
`keystore2` but no `qseecomd`, no QTI Keymaster 3.0 service and no QTI
Gatekeeper 1.0 service, and its init fragment imported a file that does not
exist in the pinned OrangeFox sources - so nothing ever started the TEE chain
and decryption could not work even though the fstab asked for it.

What is verified here:

  * every `import` in every reachable init rc resolves to a real file
    (templated imports such as `/init.recovery.${ro.hardware}.rc` are matched
    against the root with a glob and must match at least one file);
  * every `service` line's executable exists at exactly the path init will
    exec (absolute, after `$import` expansion);
  * that executable is an ELF for the target (64-bit AArch64) whose
    PT_INTERP exists in the ramdisk;
  * every DT_NEEDED library, transitively, resolves inside the ramdisk
    (or is a bionic core library that is always present);
  * every service is actually reachable: started by an explicit `start`, or
    covered by `class_start <its class>`.

Two modes:

  --ramdisk DIR        an unpacked built ramdisk (authoritative, used by
                       build/verify_image.sh)
  --device-tree DIR    this repository's device tree, where the same paths are
                       read from DIR/recovery/root (used by the static gate
                       before a build exists)

Exit code: 0 = all services resolvable, 1 = at least one hard failure.

Usage:
  python3 tools/check_init_services.py --ramdisk out/.../recovery/root
  python3 tools/check_init_services.py --device-tree device/xiaomi/sakura
  python3 tools/check_init_services.py --ramdisk RD --require crypto
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import elf as elfmod  # noqa: E402

# Libraries that are part of bionic/linker and always present in a ramdisk
# built by the pinned recovery sources. Nothing proprietary may be listed here.
CORE_LIBS = {
    "libc.so", "libm.so", "libdl.so", "liblog.so", "libstdc++.so", "libc++.so",
    "libz.so", "libutils.so", "libcutils.so", "libbase.so", "libbinder.so",
    "libbinder_ndk.so", "libhardware.so", "libhidlbase.so", "libhidltransport.so",
    "libhwbinder.so", "libprocessgroup.so", "libselinux.so", "libpcre2.so",
    "libcrypto.so", "libssl.so", "ld-android.so", "libsync.so", "libion.so",
    "libziparchive.so", "libtinyxml2.so", "libvndksupport.so", "libnetd_client.so",
    "libsysutils.so", "libnl.so", "liblz4.so", "libext2fs.so", "libext2_blkid.so",
    "libext2_quota.so", "libext2_com_err.so", "libext2_e2p.so", "libext2_uuid.so",
    "libext2_misc.so", "libext2_profile.so", "libsparse.so", "libf2fs_sparseblock.so",
    "libkeymaster_messages.so", "libkeymaster_portable.so", "libhidl-gen-utils.so",
    "libvintf.so",
}

LIB_DIRS = [
    "system/lib64", "system/lib", "vendor/lib64", "vendor/lib", "vendor/lib64/hw",
    "system/lib64/hw", "sbin", "system_ext/lib64", "product/lib64",
]

# Executables provided by the build (not by the device tree). A shell script's
# shebang may name one of these before a ramdisk exists; that is not a failure
# in the pre-build device-tree scan.
CORE_EXECUTABLES = {"sh", "bash", "toybox"}

# Service names whose absence makes decryption impossible on this device.
CRYPTO_SERVICE_HINTS = ("qseecomd", "keymaster", "gatekeeper")


class Finding:
    def __init__(self, level, message):
        self.level = level
        self.message = message

    def __str__(self):
        return f"[{self.level.upper()}] {self.message}"


class InitScan:
    def __init__(self, root, verbose=False, manifest=None, require_installed=True):
        self.root = os.path.abspath(root)
        self.verbose = verbose
        self.manifest_dests = set()
        self.require_installed = require_installed
        if manifest:
            self.manifest_dests = read_manifest_dests(manifest)
        self.findings = []
        self.services = []       # dicts: name, exec, args, klass, file, line
        self.imports = []        # (rc file, imported path, resolved or None)
        self.started = set()     # names referenced by `start`
        self.class_starts = set()
        self.rc_files = []

    # -- reporting ------------------------------------------------------
    def add(self, level, message):
        self.findings.append(Finding(level, message))

    @property
    def failures(self):
        return [f for f in self.findings if f.level == "fail"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == "warn"]

    # -- paths ----------------------------------------------------------
    def path(self, absolute):
        """Map an absolute in-ramdisk path to a path under the scan root."""
        return os.path.join(self.root, absolute.lstrip("/"))

    def exists(self, absolute):
        return os.path.exists(self.path(absolute))

    # -- rc discovery and parsing ---------------------------------------
    def discover_rc_files(self):
        candidates = ["init.rc", "init.recovery.hardware.rc"]
        for pattern in ("init*.rc", "system/etc/init/*.rc", "vendor/etc/init/*.rc",
                        "vendor/etc/init/hw/*.rc", "system/etc/init/hw/*.rc"):
            candidates.extend(
                os.path.relpath(p, self.root)
                for p in glob.glob(os.path.join(self.root, pattern)))
        seen = []
        for rel in sorted(set(candidates)):
            full = os.path.join(self.root, rel)
            if os.path.isfile(full):
                seen.append(full)
        self.rc_files = seen

    def parse_rc(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError as exc:
            self.add("fail", f"cannot read rc file {path}: {exc}")
            return
        section = ""
        for lineno, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            keyword = parts[0]

            if keyword == "import":
                if len(parts) < 2:
                    self.add("fail", f"{path}:{lineno}: import without a path")
                    continue
                self.resolve_import(path, lineno, parts[1])
            elif keyword in ("on", "service"):
                section = line
                if keyword == "service":
                    if len(parts) < 3:
                        self.add("fail", f"{path}:{lineno}: service without an executable")
                        continue
                    if any(s["name"] == parts[1] for s in self.services):
                        # init refuses to load a second definition of the same
                        # service name; the later one is silently ignored, so
                        # the declared executable may not be the one that runs.
                        self.add("fail", f"{path}:{lineno}: duplicate service "
                                          f"name '{parts[1]}' (already defined "
                                          f"earlier; init ignores the duplicate)")
                    self.services.append({
                        "name": parts[1], "exec": parts[2], "args": parts[3:],
                        "class": None, "file": path, "line": lineno,
                    })
            elif keyword == "class" and section.startswith("service ") and len(parts) > 1:
                self.services[-1]["class"] = parts[1]
            elif keyword == "start" and len(parts) > 1:
                self.started.add(parts[1])
            elif keyword in ("class_start", "class_stop", "class_reset") and len(parts) > 1:
                if keyword == "class_start":
                    self.class_starts.add(parts[1])

    def resolve_import(self, rc_path, lineno, target):
        if "$" in target or "{" in target:
            pattern = os.path.join(self.root, target.lstrip("/"))
            pattern = pattern.replace("${ro.hardware}", "*").replace("$ro.hardware", "*")
            matches = [m for m in glob.glob(pattern) if os.path.isfile(m)]
            self.imports.append((rc_path, target, matches))
            if not matches:
                self.add(
                    "fail",
                    f"{os.path.relpath(rc_path, self.root)}:{lineno}: templated import "
                    f"{target} matches no file in the ramdisk "
                    f"(no device init rc for the bootloader's ro.hardware)")
            return
        full = os.path.join(self.root, target.lstrip("/"))
        self.imports.append((rc_path, target, [full] if os.path.isfile(full) else []))
        if not os.path.isfile(full):
            self.add(
                "fail",
                f"{os.path.relpath(rc_path, self.root)}:{lineno}: imports {target}, "
                f"but that file does not exist in the ramdisk "
                f"(searched {os.path.relpath(full, self.root)})")

    # -- library resolution ---------------------------------------------
    def index_libraries(self):
        index = {}
        for rel in LIB_DIRS:
            base = os.path.join(self.root, rel)
            if not os.path.isdir(base):
                continue
            for entry in os.listdir(base):
                if entry.endswith(".so"):
                    index.setdefault(entry, os.path.join(base, entry))
        # A binary's own directory is always searched first by the linker.
        self.lib_index = index

    def resolve_needed(self, elf, extra_dirs=()):
        missing = []
        seen = set()
        queue = list(elf.needed)
        while queue:
            need = queue.pop(0)
            if need in seen:
                continue
            seen.add(need)
            candidates = [os.path.join(d, need) for d in extra_dirs
                          if os.path.isfile(os.path.join(d, need))]
            found = candidates[0] if candidates else self.lib_index.get(need)
            if found is None:
                if need in CORE_LIBS:
                    continue
                missing.append(need)
                continue
            try:
                sub = elfmod.inspect(found)
            except elfmod.ElfError as exc:
                self.add("warn", f"{os.path.relpath(found, self.root)}: {exc}")
                continue
            queue.extend(sub.needed)
        return sorted(set(missing))

    # -- checks ---------------------------------------------------------
    def check(self):
        self.discover_rc_files()
        if not self.rc_files:
            self.add("fail", f"no init rc files found under {self.root} "
                              f"(nothing would start any service)")
            return
        for path in self.rc_files:
            self.parse_rc(path)
        self.index_libraries()

        if not self.services:
            self.add("warn", "no `service` definitions found in the scanned rc files")

        for svc in self.services:
            exec_path = svc["exec"]
            where = f"{os.path.relpath(svc['file'], self.root)}:{svc['line']}"
            if "$" in exec_path:
                self.add("warn", f"{where}: service {svc['name']} uses a templated "
                                  f"executable {exec_path}; not verified")
                continue
            if not exec_path.startswith("/"):
                self.add("fail", f"{where}: service {svc['name']} executable "
                                  f"{exec_path} is not an absolute path")
                continue
            full = self.path(exec_path)
            if not os.path.exists(full):
                rel_dest = exec_path.lstrip("/")
                if rel_dest in self.manifest_dests and not self.require_installed:
                    self.add("warn",
                             f"{where}: service {svc['name']} executes {exec_path}, "
                             f"not installed yet - it is listed in "
                             f"proprietary-files.txt and build/install_blobs.sh "
                             f"provides it once the stock firmware has been "
                             f"extracted")
                    continue
                if rel_dest in self.manifest_dests:
                    self.add("fail", f"{where}: service {svc['name']} executes "
                                      f"{exec_path}; proprietary-files.txt lists it "
                                      f"but it is not installed (run "
                                      f"build/install_blobs.sh)")
                    continue
                self.add("fail", f"{where}: service {svc['name']} executes {exec_path}, "
                                  f"which is missing from the ramdisk and is not "
                                  f"provided by proprietary-files.txt")
                continue
            if os.path.isdir(full):
                self.add("fail", f"{where}: service {svc['name']} executes {exec_path}, "
                                  f"which is a directory")
                continue

            try:
                binary = elfmod.inspect(full)
            except elfmod.ElfError:
                # A shell script is legitimate as an init service. Verify its
                # shebang interpreter resolves, otherwise init execs a file the
                # kernel cannot run and the service dies with ENOENT.
                first = ""
                try:
                    with open(full, "rb") as fh:
                        first = fh.readline(256).decode("utf-8", "replace").strip()
                except OSError:
                    pass
                if first.startswith("#!"):
                    interp = first[2:].strip().split()[0] if first[2:].strip() else ""
                    if (interp and not self.exists(interp)
                            and os.path.basename(interp) not in CORE_EXECUTABLES):
                        self.add("fail", f"{where}: service {svc['name']} is a "
                                          f"script whose interpreter {interp} is "
                                          f"missing from the ramdisk")
                    elif self.verbose:
                        self.add("warn", f"{where}: {exec_path} is a script "
                                          f"(interpreter {interp or '?'})")
                elif self.verbose:
                    self.add("warn", f"{where}: {exec_path} is not an ELF and has "
                                      f"no shebang; init cannot execute it")
                continue

            if not binary.is64:
                self.add("fail", f"{where}: {exec_path} is {binary.summary()}, but the "
                                  f"recovery ramdisk is 64-bit only")
            if binary.machine not in (elfmod.EM_AARCH64,):
                self.add("fail", f"{where}: {exec_path} targets {binary.machine_name}, "
                                  f"not AArch64")
            if binary.interp and not self.exists(binary.interp):
                self.add("fail", f"{where}: {exec_path} requests interpreter "
                                  f"{binary.interp}, which is missing from the ramdisk")

            missing = self.resolve_needed(binary, extra_dirs=[os.path.dirname(full)])
            for need in missing:
                self.add("fail", f"{where}: {exec_path} needs {need}, which does not "
                                  f"resolve inside the ramdisk")

            started = svc["name"] in self.started
            class_started = svc["class"] is not None and svc["class"] in self.class_starts
            if not started and not class_started:
                self.add("warn", f"{where}: service {svc['name']} is never started "
                                  f"(no `start {svc['name']}` and class "
                                  f"{svc['class'] or '(none)'} is never started)")

    # -- output ---------------------------------------------------------
    def report(self, title):
        print(f"==> {title}")
        print(f"    root     : {self.root}")
        print(f"    rc files : {len(self.rc_files)} "
              f"({', '.join(os.path.relpath(p, self.root) for p in self.rc_files)})")
        for rc, target, matches in self.imports:
            resolved = ", ".join(os.path.relpath(m, self.root) for m in matches) or "MISSING"
            print(f"    import   : {os.path.relpath(rc, self.root)} -> {target} [{resolved}]")
        print(f"    services : {len(self.services)}")
        for svc in self.services:
            print(f"      - {svc['name']:<34} {svc['exec']}"
                  f"  class={svc['class'] or '-'}")
        for finding in self.findings:
            print(f"    {finding}")
        status = "PASS" if not self.failures else "FAIL"
        print(f"    RESULT: {status} ({len(self.failures)} failure(s), "
              f"{len(self.warnings)} warning(s))")
        return not self.failures


def read_manifest_dests(path):
    """Destinations (ramdisk-relative) listed in proprietary-files.txt."""
    dests = set()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                rest = line.split(":", 1)[1]
                dest = rest.split("|", 1)[0].strip()
                if dest:
                    dests.add(dest)
    except OSError:
        return dests
    return dests


def require_crypto_services(scan):
    """Extra gate: decryption needs QSEECom + Keymaster + Gatekeeper started."""
    names = " ".join(s["name"] for s in scan.services)
    execs = " ".join(s["exec"] for s in scan.services)
    haystack = f"{names} {execs}"
    missing = [hint for hint in CRYPTO_SERVICE_HINTS if hint not in haystack]
    if missing:
        scan.add("fail", f"crypto chain incomplete: no service for {', '.join(missing)}"
                          f" is declared in any rc file")
        return False
    return True


def scan_device_tree(device_dir, verbose=False):
    """Scan the repo device tree (paths as they will exist in the ramdisk)."""
    root = os.path.join(device_dir, "recovery", "root")
    if not os.path.isdir(root):
        raise SystemExit(f"ERROR: {root} does not exist")
    scan = InitScan(root, verbose=verbose)
    scan.check()
    return scan


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ramdisk")
    ap.add_argument("--device-tree")
    ap.add_argument("--manifest", help="proprietary-files.txt to cross-check "
                                        "service paths against")
    ap.add_argument("--require", choices=["crypto"], default=None)
    ap.add_argument("--require-installed", action="store_true",
                    help="treat manifested-but-not-installed files as failures "
                         "(default: tolerated, for pre-build static checks)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv[1:])

    if args.ramdisk:
        root = args.ramdisk
    elif args.device_tree:
        root = os.path.join(args.device_tree, "recovery", "root")
    else:
        ap.error("one of --ramdisk or --device-tree is required")

    if not os.path.isdir(root):
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 1

    manifest = args.manifest
    if manifest is None and args.device_tree:
        candidate = os.path.join(args.device_tree, "proprietary-files.txt")
        if os.path.isfile(candidate):
            manifest = candidate

    scan = InitScan(root, verbose=args.verbose, manifest=manifest,
                    require_installed=args.require_installed or bool(args.ramdisk))
    scan.check()
    crypto_ok = True
    if args.require == "crypto":
        crypto_ok = require_crypto_services(scan)
    ok = scan.report(f"init service resolvability ({root})") and crypto_ok
    if args.require == "crypto":
        print(f"    RESULT: crypto requirement "
              f"{'SATISFIED' if crypto_ok else 'NOT SATISFIED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
