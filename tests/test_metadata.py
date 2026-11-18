#!/usr/bin/env python3
"""
test_metadata.py - opt-in metadata-encryption (FBEv2) configuration and the
build-time crypto-mode wiring.

Metadata decryption is implemented by the pinned recovery itself
(-DTW_INCLUDE_FBE_METADATA_DECRYPT + libvold/MetadataCrypt, partition.cpp
`metadata_encryption=`/`keydirectory=`). What must be right is the
configuration around it:

  * the default tree must NOT declare a metadata key directory, because
    partition.cpp Setup_Data_Partition() treats a non-empty Key_Directory as
    "this /data is encrypted" and would then demand a credential on a ROM that
    is not metadata-encrypted;
  * enabling must be explicit (a confirmation flag), deterministic, idempotent
    and reversible byte-for-byte;
  * the generated fragment must only ever be a build artifact;
  * the no-decryption mode must be recorded in ro.sakura.crypto.mode so the
    diagnostics do not treat an intentional build as broken.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402

REPO = support.REPO
DEVICE = os.path.join(REPO, "device", "xiaomi", "sakura")
TOOL = os.path.join(REPO, "tools", "configure_metadata.py")


def run_tool(*args):
    return support.run([sys.executable, TOOL, *args])


class MetadataTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dev = os.path.join(self.tmp, "sakura")
        shutil.copytree(DEVICE, self.dev,
                        ignore=shutil.ignore_patterns("prebuilt", "*.mk"))
        self.fstab = os.path.join(self.dev, "recovery/root/system/etc/recovery.fstab")
        self.flags = os.path.join(self.dev, "recovery/root/system/etc/twrp.flags")
        self.mk = os.path.join(self.dev, "metadata_encryption.mk")

    def read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def snapshot(self):
        return self.read(self.fstab), self.read(self.flags)

    def test_default_tree_is_disabled(self):
        proc = run_tool("--device-tree", self.dev, "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("disabled", proc.stdout)
        self.assertFalse(os.path.exists(self.mk))
        active = "\n".join(ln for ln in self.read(self.fstab).splitlines()
                           if ln.strip() and not ln.lstrip().startswith("#"))
        self.assertNotIn("metadata_encryption=", active)
        self.assertNotIn("keydirectory=", active)
        self.assertNotIn("/metadata ", active)

    def test_enable_requires_explicit_confirmation(self):
        before = self.snapshot()
        proc = run_tool("--device-tree", self.dev, "--enable")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--confirm-rom-uses-metadata", proc.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(os.path.exists(self.mk))

    def test_enable_then_disable_restores_the_original_bytes(self):
        before = self.snapshot()
        enable = run_tool("--device-tree", self.dev, "--enable",
                          "--confirm-rom-uses-metadata")
        self.assertEqual(enable.returncode, 0, enable.stdout + enable.stderr)

        fstab, flags = self.snapshot()
        rows = [ln for ln in fstab.splitlines()
                if not ln.lstrip().startswith("#") and ln.split()
                and len(ln.split()) >= 5 and ln.split()[1] == "/data"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            tokens = row.split()[4].split(",")
            self.assertIn("metadata_encryption=aes-256-xts:wrappedkey_v0", tokens)
            self.assertIn("keydirectory=/metadata/vold/metadata_encryption", tokens)
        self.assertTrue(any(ln.split() and not ln.lstrip().startswith("#")
                            and ln.split()[1] == "/metadata"
                            for ln in fstab.splitlines()))
        self.assertTrue(any(ln.split() and not ln.lstrip().startswith("#")
                            and ln.split()[0] == "/metadata"
                            for ln in flags.splitlines()))
        with open(self.mk, encoding="utf-8") as fh:
            mk = fh.read()
        self.assertIn("BOARD_USES_METADATA_PARTITION := true", mk)
        self.assertIn("ro.sakura.metadata_encryption=enabled", mk)

        # Check agrees, and a second enable is a no-op.
        self.assertEqual(run_tool("--device-tree", self.dev, "--check").returncode, 0)
        second = run_tool("--device-tree", self.dev, "--enable",
                          "--confirm-rom-uses-metadata")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual((fstab, flags), self.snapshot())

        disable = run_tool("--device-tree", self.dev, "--disable")
        self.assertEqual(disable.returncode, 0, disable.stdout + disable.stderr)
        self.assertEqual(before, self.snapshot(), "disable must be byte-exact")
        self.assertFalse(os.path.exists(self.mk))

    def test_check_detects_a_half_applied_configuration(self):
        run_tool("--device-tree", self.dev, "--enable", "--confirm-rom-uses-metadata")
        # Simulate a hand-edited tree: tokens present, /metadata row removed.
        text = "\n".join(ln for ln in self.read(self.fstab).splitlines()
                         if not (ln.split() and not ln.lstrip().startswith("#")
                                 and len(ln.split()) >= 5
                                 and ln.split()[1] == "/metadata")) + "\n"
        with open(self.fstab, "w", encoding="utf-8") as fh:
            fh.write(text)
        proc = run_tool("--device-tree", self.dev, "--check")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("disagree", proc.stdout)

    def test_committed_tree_has_no_generated_fragments(self):
        self.assertFalse(os.path.exists(os.path.join(DEVICE, "metadata_encryption.mk")))
        self.assertFalse(os.path.exists(os.path.join(DEVICE, "crypto_mode.mk")))


class BuildWiring(unittest.TestCase):
    """The build must record its crypto mode and reset the metadata opt-in."""

    def read(self, rel):
        with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_device_mk_includes_both_generated_fragments(self):
        device = self.read("device/xiaomi/sakura/device.mk")
        self.assertIn("crypto_mode.mk", device)
        self.assertIn("ro.sakura.crypto.mode=full", device)
        self.assertIn("-include $(DEVICE_PATH)/metadata_encryption.mk", device)

    def test_build_script_writes_the_mode_and_resets_metadata(self):
        build = self.read("build/build.sh")
        self.assertIn("crypto_mode.mk", build)
        self.assertIn("ro.sakura.crypto.mode", build)
        self.assertIn("configure_metadata.py", build)
        self.assertIn("--disable", build)
        self.assertIn("SAKURA_METADATA_ENCRYPTION", build)
        # metadata without the TEE chain must be refused, not silently built
        self.assertIn('CRYPTO_MODE" = "full"', build)

    def test_generated_fragments_are_gitignored(self):
        gi = self.read(".gitignore")
        self.assertIn("device/xiaomi/sakura/crypto_mode.mk", gi)
        self.assertIn("device/xiaomi/sakura/metadata_encryption.mk", gi)

    def test_verify_image_checks_the_recorded_mode(self):
        verify = self.read("build/verify_image.sh")
        self.assertIn("ro.sakura.crypto.mode", verify)
        self.assertIn("metadata_encryption=aes-256-xts", verify)
        self.assertIn("keydirectory=", verify)

    def test_workflow_exposes_both_switches(self):
        wf = self.read(".github/workflows/orangefox-sakura.yml")
        self.assertIn("metadata_encryption:", wf)
        self.assertIn("SAKURA_METADATA_ENCRYPTION=1", wf)
        self.assertIn("SAKURA_ALLOW_MISSING_CRYPTO=1", wf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
