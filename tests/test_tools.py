#!/usr/bin/env python3
"""
test_tools.py - regression tests for the sakura crypto-extraction toolchain.

These tests exist because the port's central defect was workflow-shaped: the
repository *documented* a decryption path that no script could produce and no
init file could start. Everything here runs on a clean host with python3 and
e2fsprogs - no cross-compiler, no Android SDK, no device, no proprietary blob.

    python3 -m unittest discover -s tests -v

Coverage:
  * tools/elf.py       - class/machine/interp/DT_NEEDED parsing, bad input
  * tools/simg2img.py  - sparse -> raw, raw passthrough, --info
  * tools/check_init_services.py - service paths, dangling import, missing
                         interpreter, unresolved DT_NEEDED, crypto requirement
  * build/extract_blobs.sh - end-to-end on a synthetic ext4 vendor.img:
                         identity gate (sakura vs another device), required vs
                         optional entries, ELF validation, checksum manifest
  * build/install_blobs.sh - install modes, generated PRODUCT_COPY_FILES
                         fragment, and --clean
  * the committed device tree - its manifest destinations must equal the
                         executable paths of its init services
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import support  # noqa: E402
import elf as elfmod  # noqa: E402
import simg2img  # noqa: E402

REPO = support.REPO
DEVICE = os.path.join(REPO, "device", "xiaomi", "sakura")

BUILD_PROP = "\n".join([
    "ro.product.device=sakura",
    "ro.product.name=sakura",
    "ro.build.version.release=9",
    "ro.build.version.security_patch=2020-10-05",
    "ro.vendor.build.fingerprint=Xiaomi/sakura/sakura:9/PKQ1.190319.001/V12.0.4.0.PDMMIXM:user/release-keys",
    "",
])

# The seven entries the manifest marks "required".
REQUIRED_FILES = {
    "bin/qseecomd": dict(interp="/system/bin/linker64",
                         needed=["libQSEEComAPI.so", "libc.so"]),
    "bin/hw/android.hardware.keymaster@3.0-service-qti": dict(
        interp="/system/bin/linker64",
        needed=["libkeymasterdeviceutils.so", "libQSEEComAPI.so"]),
    "bin/hw/android.hardware.gatekeeper@1.0-service-qti": dict(
        interp="/system/bin/linker64", needed=["libQSEEComAPI.so"]),
    "lib64/hw/android.hardware.keymaster@3.0-impl-qti.so": dict(
        soname="android.hardware.keymaster@3.0-impl-qti.so", needed=["libc.so"]),
    "lib64/hw/android.hardware.gatekeeper@1.0-impl-qti.so": dict(
        soname="android.hardware.gatekeeper@1.0-impl-qti.so", needed=["libc.so"]),
    "lib64/libQSEEComAPI.so": dict(soname="libQSEEComAPI.so", needed=["libc.so"]),
    "lib64/libkeymasterdeviceutils.so": dict(
        soname="libkeymasterdeviceutils.so", needed=["libc.so"]),
}
OPTIONAL_FILES = {
    "lib64/libdiag.so": dict(soname="libdiag.so", needed=["libc.so"]),
    "lib64/libqisl.so": dict(soname="libqisl.so", needed=["libc.so"]),
}


def vendor_tree(build_prop=BUILD_PROP, files=None):
    tree = {"build.prop": build_prop}
    default = list(REQUIRED_FILES) + list(OPTIONAL_FILES)
    for rel in (default if files is None else files):
        spec = (REQUIRED_FILES | OPTIONAL_FILES)[rel]
        tree[rel] = support.make_elf(**spec)
    return tree


def manifest_entries():
    """(source path in vendor.img, ramdisk destination, requirement)"""
    entries = []
    with open(os.path.join(DEVICE, "proprietary-files.txt"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            src, rest = line.split(":", 1)
            fields = rest.split("|")
            entries.append((src, fields[0].strip(),
                            fields[1].strip() if len(fields) > 1 else "required"))
    return entries


class TestElf(unittest.TestCase):
    def test_parses_aarch64_with_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "svc")
            with open(path, "wb") as fh:
                fh.write(support.make_elf(interp="/system/bin/linker64",
                                          needed=["libfoo.so", "libc.so"],
                                          soname="libsvc.so"))
            got = elfmod.inspect(path)
            self.assertTrue(got.is64)
            self.assertEqual(got.machine, elfmod.EM_AARCH64)
            self.assertEqual(got.interp, "/system/bin/linker64")
            self.assertEqual(got.needed, ["libfoo.so", "libc.so"])
            self.assertEqual(got.soname, "libsvc.so")
            self.assertIn("64-bit AArch64", got.summary())

    def test_rejects_32bit_and_non_elf(self):
        with tempfile.TemporaryDirectory() as tmp:
            x86 = os.path.join(tmp, "x86")
            with open(x86, "wb") as fh:
                fh.write(support.make_elf(bits=32, machine=support.EM_386))
            got = elfmod.inspect(x86)
            self.assertFalse(got.is64)
            self.assertEqual(got.machine_name, "x86")

            junk = os.path.join(tmp, "junk")
            with open(junk, "wb") as fh:
                fh.write(b"not an elf at all")
            with self.assertRaises(elfmod.ElfError):
                elfmod.inspect(junk)


class TestSimg2Img(unittest.TestCase):
    def test_sparse_roundtrip(self):
        payload = bytes(range(256)) * 64        # 16384 bytes = 4 x 4096
        sparse = support.make_sparse(payload)
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "vendor.img")
            dst = os.path.join(tmp, "vendor.raw")
            with open(src, "wb") as fh:
                fh.write(sparse)
            self.assertTrue(simg2img.is_sparse(src))
            written = simg2img.convert(src, dst)
            self.assertEqual(written, len(payload))
            with open(dst, "rb") as fh:
                self.assertEqual(fh.read(), payload)
            info = simg2img.info(src)
            self.assertEqual(info["blk_sz"], 4096)
            self.assertEqual(info["raw_size"], len(payload))

    def test_raw_passthrough(self):
        payload = b"raw ext4 image bytes" * 100
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "vendor.img")
            dst = os.path.join(tmp, "vendor.raw")
            with open(src, "wb") as fh:
                fh.write(payload)
            self.assertFalse(simg2img.is_sparse(src))
            simg2img.convert(src, dst)
            with open(dst, "rb") as fh:
                self.assertEqual(fh.read(), payload)


class TestInitServices(unittest.TestCase):
    def _root(self, tmp):
        root = os.path.join(tmp, "rd")
        os.makedirs(os.path.join(root, "system/bin"))
        os.makedirs(os.path.join(root, "system/lib64"))
        files = {
            "init.rc": "import /init.recovery.${ro.hardware}.rc\n",
            "init.recovery.qcom.rc": "import /init.recovery.qcom_decrypt.rc\n",
            "init.recovery.qcom_decrypt.rc": (
                "on boot\n"
                "    start qseecomd\n"
                "on property:init.svc.qseecomd=running\n"
                "    start vendor.keymaster-3-0\n"
                "service qseecomd /system/bin/qseecomd\n"
                "    class core\n"
                "service vendor.keymaster-3-0 /system/bin/android.hardware.keymaster@3.0-service-qti\n"
                "    class hal\n"
                "service vendor.gatekeeper-1-0 /system/bin/android.hardware.gatekeeper@1.0-service-qti\n"
                "    class hal\n"
            ),
            "system/bin/linker64": support.make_elf(soname="linker64"),
            "system/bin/qseecomd": support.make_elf(
                interp="/system/bin/linker64", needed=["libQSEEComAPI.so", "libc.so"]),
            "system/bin/android.hardware.keymaster@3.0-service-qti": support.make_elf(
                interp="/system/bin/linker64", needed=["libQSEEComAPI.so"]),
            "system/bin/android.hardware.gatekeeper@1.0-service-qti": support.make_elf(
                interp="/system/bin/linker64", needed=["libQSEEComAPI.so"]),
            "system/lib64/libQSEEComAPI.so": support.make_elf(
                soname="libQSEEComAPI.so", needed=["libc.so"]),
        }
        for rel, content in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = content.encode() if isinstance(content, str) else content
            with open(path, "wb") as fh:
                fh.write(data)
        return root

    def test_resolvable_ramdisk_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            proc = support.run_tool("check_init_services.py",
                                    ["--ramdisk", root, "--require", "crypto"])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("crypto requirement SATISFIED", proc.stdout)

    def test_unresolved_library_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            os.remove(os.path.join(root, "system/lib64/libQSEEComAPI.so"))
            proc = support.run_tool("check_init_services.py",
                                    ["--ramdisk", root, "--require", "crypto"])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("needs libQSEEComAPI.so", proc.stdout)

    def test_dangling_import_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            os.remove(os.path.join(root, "init.recovery.qcom_decrypt.rc"))
            proc = support.run_tool("check_init_services.py", ["--ramdisk", root])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("imports /init.recovery.qcom_decrypt.rc", proc.stdout)

    def test_missing_interpreter_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            os.remove(os.path.join(root, "system/bin/linker64"))
            proc = support.run_tool("check_init_services.py", ["--ramdisk", root])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("interpreter /system/bin/linker64", proc.stdout)

    def test_crypto_requirement_detects_absent_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            rc = os.path.join(root, "init.recovery.qcom_decrypt.rc")
            with open(rc, "w", encoding="utf-8") as fh:
                fh.write("on boot\n    start nothing\n")
            proc = support.run_tool("check_init_services.py",
                                    ["--ramdisk", root, "--require", "crypto"])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("crypto chain incomplete", proc.stdout)


class TestCommittedDeviceTree(unittest.TestCase):
    def test_device_tree_scan_is_clean(self):
        proc = support.run_tool("check_init_services.py",
                                ["--device-tree", DEVICE, "--require", "crypto"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_manifest_destinations_match_init_services(self):
        """The installed destination IS the path init execs - not a convention."""
        manifest = {}
        with open(os.path.join(DEVICE, "proprietary-files.txt"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                src, rest = line.split(":", 1)
                dest = rest.split("|", 1)[0].strip()
                manifest[dest] = src

        rc = os.path.join(DEVICE, "recovery", "root", "init.recovery.qcom_decrypt.rc")
        execs = []
        with open(rc, encoding="utf-8") as fh:
            for line in fh:
                fields = line.split()
                if len(fields) >= 3 and fields[0] == "service":
                    execs.append(fields[2])
        self.assertGreaterEqual(len(execs), 3)
        for exe in execs:
            dest = exe.lstrip("/")
            self.assertIn(dest, manifest,
                          f"{exe} is exec'd by init but not installed by the manifest")


class TestExtractionEndToEnd(unittest.TestCase):
    """build/extract_blobs.sh against a real ext4 image read via debugfs."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.img = os.path.join(self.tmp, "vendor.img")
        support.make_ext4(self.img, vendor_tree())
        self.out = os.path.join(self.tmp, "blobs")

    def _extract(self, *extra):
        return support.run(["bash", "build/extract_blobs.sh",
                            "--vendor-img", self.img, "--out", self.out, *extra])

    def test_extracts_required_and_optional_files(self):
        proc = self._extract()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # Only the entries this fixture image actually contains.
        fixture_sources = {"bin/" + rel for rel in REQUIRED_FILES}
        fixture_sources |= {"lib64/" + rel for rel in REQUIRED_FILES}
        fixture_names = {os.path.basename(s) for s in fixture_sources}
        fixture_names |= {os.path.basename(p) for p in OPTIONAL_FILES}
        for src, dest, _req in manifest_entries():
            if os.path.basename(src) not in fixture_names:
                continue
            installed = os.path.join(self.out, dest)
            self.assertTrue(os.path.isfile(installed), dest)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "MANIFEST.sha256")))
        self.assertTrue(os.path.isfile(os.path.join(self.out, "EXTRACTION_REPORT.md")))

        with open(os.path.join(self.out, "EXTRACTION_REPORT.md"),
                  encoding="utf-8") as fh:
            report = fh.read()
        self.assertIn("sakura", report)
        self.assertIn("PDMMIXM", report)
        self.assertIn("runtime-tested on hardware: **NO**", report)

        # The generated checksum manifest must actually verify.
        check = support.run(["sha256sum", "-c", "--quiet", "MANIFEST.sha256"],
                            cwd=self.out)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_rejects_another_devices_firmware(self):
        support.make_ext4(self.img,
                          vendor_tree(build_prop="ro.product.device=daisy\n"
                                                  "ro.build.version.release=10\n"))
        proc = self._extract()
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("daisy", combined)
        self.assertIn("not 'sakura'", combined)

    def test_missing_required_file_is_fatal(self):
        files = dict(vendor_tree())
        del files["lib64/libkeymasterdeviceutils.so"]
        support.make_ext4(self.img, files)
        proc = self._extract()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("MISSING (required)", proc.stdout)

    def test_dry_run_writes_nothing(self):
        proc = self._extract("--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(self.out))
        self.assertIn("would extract", proc.stdout)

    def test_wrong_architecture_is_fatal(self):
        # A 32-bit ARM library is what a wrong-architecture blob set looks like
        # (Mi A2 Lite firmware for an arm64-only recovery ramdisk).
        files = dict(vendor_tree())
        files["lib64/libdiag.so"] = support.make_elf(bits=32, machine=40)
        support.make_ext4(self.img, files)
        proc = self._extract()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("wrong architecture", proc.stdout + proc.stderr)

    def test_install_then_clean(self):
        extract = self._extract()
        self.assertEqual(extract.returncode, 0, extract.stdout + extract.stderr)

        dev = os.path.join(self.tmp, "device")
        shutil.copytree(os.path.join(DEVICE), dev,
                        ignore=shutil.ignore_patterns("prebuilt"))
        proc = support.run(["bash", "build/install_blobs.sh",
                            "--device-tree", dev, "--blobs", self.out])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        gen = os.path.join(dev, "blob_install.mk")
        self.assertTrue(os.path.isfile(gen))
        with open(gen, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("PRODUCT_COPY_FILES", text)
        self.assertIn("recovery/root/system/bin", text)

        exe = os.path.join(dev, "recovery/root/system/bin/qseecomd")
        lib = os.path.join(dev, "recovery/root/system/lib64/libQSEEComAPI.so")
        self.assertTrue(os.path.isfile(exe))
        self.assertEqual(os.stat(exe).st_mode & 0o777, 0o755)
        self.assertEqual(os.stat(lib).st_mode & 0o777, 0o644)

        clean = support.run(["bash", "build/install_blobs.sh",
                             "--device-tree", dev, "--clean"])
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertFalse(os.path.exists(exe))
        self.assertFalse(os.path.exists(gen))

    def test_install_refuses_without_blobs(self):
        dev = os.path.join(self.tmp, "device")
        shutil.copytree(os.path.join(DEVICE), dev,
                        ignore=shutil.ignore_patterns("prebuilt"))
        proc = support.run(["bash", "build/install_blobs.sh",
                            "--device-tree", dev, "--blobs",
                            os.path.join(self.tmp, "nope")])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("extract_blobs.sh", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
