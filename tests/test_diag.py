#!/usr/bin/env python3
"""
test_diag.py - logic tests for the early-boot diagnostic collector.

The collector is a shell script that runs before the GUI, so these tests drive
it with synthetic fixtures (props/dmesg/logcat/mounts files) instead of a
device. That is the only honest way to test it off-device.

    python3 -m unittest discover -s tests -v

Coverage:
  * syntax and executable bit of the shipped script;
  * error counting from dmesg + logcat (threadtime format) + service state;
  * an optional/unknown service being stopped must never become an error;
  * bounded size and rotation (base + N rotations, never unbounded);
  * redaction of passwords, PINs and serial numbers in the report;
  * the report contains the required sections and the real counters;
  * missing log storage fails cleanly instead of hanging;
  * `clear` refuses to run without the confirmation flag;
  * `export` degrades to tmpfs-only when /cache is not writable;
  * the boot supervisor is bounded (WATCH_ITERATIONS=0 returns immediately).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402

REPO = support.REPO
SCRIPT = os.path.join(REPO, "device", "xiaomi", "sakura", "recovery", "root",
                      "system", "bin", "sakura-diag")

PROPS = """\
ro.product.device=sakura
ro.product.model=Redmi 6 Pro
ro.product.manufacturer=Xiaomi
ro.build.display.id=PKQ1.190319.001
ro.crypto.state=encrypted
ro.serialno=abcdef123456
init.svc.qseecomd=running
init.svc.vendor.keymaster-3-0=failed
init.svc.vendor.gatekeeper-1-0=running
init.svc.some-optional-hal=stopped
init.svc.random-other-hal=stopped
"""

DMESG = """\
[    1.0] init: starting service 'qseecomd'
[    2.0] EXT4-fs error (device mmcblk0p49): ext4_lookup: deleted inode referenced
[    3.0] avc: denied { read } for scontext=u:r:recovery:s0
[    4.0] mmc0: error -110 whilst initialising SD card
"""

LOGCAT = """\
01-01 00:00:01.000  1  1 E Keymaster: failed to open qseecom
01-01 00:00:02.000  1  1 W Something: password=hunter2 pin=1234
01-01 00:00:03.000  1  1 I Fine: all good
01-01 00:00:04.000  1  1 F AndroidRuntime: FATAL EXCEPTION: main
"""

MOUNTS = "/dev/block/dm-0 /data f2fs rw,seclabel 0 0\n"


class DiagCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = os.path.join(self.tmp, "fixtures")
        self.root = os.path.join(self.tmp, "root")
        os.makedirs(self.fx)
        os.makedirs(self.root)
        for name, content in (("props.txt", PROPS), ("dmesg.txt", DMESG),
                              ("logcat.txt", LOGCAT), ("mounts.txt", MOUNTS)):
            with open(os.path.join(self.fx, name), "w", encoding="utf-8") as fh:
                fh.write(content)

    def run_diag(self, *args, **extra_env):
        env = {
            "SAKURA_DIAG_FIXTURES": self.fx,
            "SAKURA_DIAG_ROOT": self.root,
            "SAKURA_DIAG_CACHE": os.path.join(self.tmp, "cache"),
            "SAKURA_DIAG_NO_SETPROP": "1",
            "SAKURA_DIAG_NO_MIRROR": "1",
            "SAKURA_DIAG_WATCH_ITERATIONS": "0",
        }
        env.update(extra_env)
        return support.run(["sh", SCRIPT, *args], env=env, timeout=60)

    def read(self, name):
        with open(os.path.join(self.root, name), encoding="utf-8") as fh:
            return fh.read()


class TestScriptShape(unittest.TestCase):
    def test_exists_executable_and_syntax_clean(self):
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "must be executable for init")
        proc = support.run(["sh", "-n", SCRIPT])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("#!/system/bin/sh"))
        # It runs before encryption is resolved; it must never write user data.
        self.assertNotIn("rm -rf /data", text)
        self.assertNotIn(">/data", text)
        self.assertNotIn("mkfs", text)


class TestClassification(DiagCase):
    def test_counts_errors_and_warnings(self):
        proc = self.run_diag("collect")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        errors = self.read("errors.txt")
        # kernel: EXT4-fs error + mmc timeout = 2
        # logcat: E line + FATAL EXCEPTION = 2
        # service: keymaster failed = 1
        self.assertIn("EXT4-fs error", errors)
        self.assertIn("mmc0", errors)
        self.assertIn("[logcat]", errors)
        self.assertIn("vendor.keymaster-3-0", errors)
        self.assertIn("avc: denied", errors)

    def test_optional_service_is_not_an_error(self):
        self.run_diag("collect")
        services = self.read("services.txt")
        self.assertIn("some-optional-hal", services)
        self.assertIn("random-other-hal", services)
        # They are present in services.txt but must not be in errors.txt.
        self.assertNotIn("some-optional-hal", self.read("errors.txt"))
        self.assertNotIn("random-other-hal", self.read("errors.txt"))

    def test_report_has_required_sections(self):
        self.run_diag("collect")
        out = self.run_diag("report").stdout.strip()
        self.assertTrue(os.path.isfile(out), out)
        with open(out, encoding="utf-8") as fh:
            report = fh.read()
        for section in ("device:", "build:", "kernel:", "boot stage:",
                        "errors:", "warnings:", "--- services ---",
                        "--- mounts ---", "--- encryption ---",
                        "--- errors and warnings ---", "--- selected properties ---"):
            self.assertIn(section, report)
        self.assertIn("errors:         5", report)
        self.assertIn("warnings:       1", report)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "report.txt")))

    def test_report_redacts_sensitive_values(self):
        self.run_diag("collect")
        out = self.run_diag("report").stdout.strip()
        with open(out, encoding="utf-8") as fh:
            report = fh.read()
        for secret in ("hunter2", "pin=1234", "abcdef123456"):
            self.assertNotIn(secret, report)
        self.assertIn("<redacted>", report)
        # The GUI viewer reads logcat.txt directly, so it must be redacted at
        # collection time, not only inside the report.
        logcat = self.read("logcat.txt")
        self.assertNotIn("hunter2", logcat)
        self.assertNotIn("1234", logcat)
        self.assertIn("<redacted>", logcat)
        # Device identification is wanted and must survive redaction.
        self.assertIn("Redmi 6 Pro", report)
        self.assertIn("sakura", report)


class TestBoundsAndStorage(DiagCase):
    def test_rotation_is_bounded(self):
        for _ in range(40):
            proc = self.run_diag("collect", SAKURA_DIAG_MAX_BYTES="400",
                                 SAKURA_DIAG_MAX_ROTATIONS="3")
            self.assertEqual(proc.returncode, 0, proc.stderr)
        names = sorted(n for n in os.listdir(self.root) if n.startswith("boot-diag.txt"))
        self.assertEqual(len(names), 4, names)      # base + 3 rotations
        for name in names:
            # Rotation happens when the cap is exceeded, so one record may push
            # a file slightly past it; it must still be tightly bounded.
            self.assertLessEqual(os.path.getsize(os.path.join(self.root, name)), 600)
        total = sum(os.path.getsize(os.path.join(self.root, n)) for n in names)
        self.assertLessEqual(total, 2400)

    def test_missing_storage_fails_cleanly(self):
        proc = support.run(["sh", SCRIPT, "collect"], env={
            "SAKURA_DIAG_ROOT": "/dev/null/sakura-diag",
            "SAKURA_DIAG_NO_SETPROP": "1",
            "SAKURA_DIAG_NO_MIRROR": "1",
            "SAKURA_DIAG_FIXTURES": self.fx,
        }, timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot create", proc.stdout)

    def test_clear_needs_confirmation(self):
        self.run_diag("collect")
        refused = self.run_diag("clear")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("Refusing to clear", refused.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "dmesg.txt")))

        cleared = self.run_diag("clear", "--yes")
        self.assertEqual(cleared.returncode, 0, cleared.stdout)
        self.assertFalse(os.path.isfile(os.path.join(self.root, "dmesg.txt")))

    def test_export_to_writable_cache(self):
        self.run_diag("collect")
        proc = self.run_diag("export", SAKURA_DIAG_NO_MIRROR="0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        cache = os.path.join(self.tmp, "cache")
        self.assertTrue(os.path.isfile(os.path.join(cache, "boot-diag.txt")), proc.stdout)
        self.assertTrue(os.path.isfile(os.path.join(cache, "report.txt")), proc.stdout)

    def test_export_without_cache_does_not_fail(self):
        self.run_diag("collect")
        proc = self.run_diag("export", SAKURA_DIAG_CACHE="/dev/null/nope")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("/tmp", proc.stdout)

    def test_preboot_pending_service_is_not_an_error(self):
        # The first snapshot runs at late-init, before `on boot` starts the TEE
        # services. An unset init.svc.* there must not light the badge.
        with open(os.path.join(self.fx, "props.txt"), "w", encoding="utf-8") as fh:
            fh.write("ro.product.device=sakura\nro.crypto.state=encrypted\n"
                     "init.svc.qseecomd=\n")
        for name in ("dmesg.txt", "logcat.txt"):
            with open(os.path.join(self.fx, name), "w", encoding="utf-8") as fh:
                fh.write("")
        self.run_diag("collect")
        errors = self.read("errors.txt")
        self.assertNotIn("qseecomd state= (required)", errors)
        self.assertIn("pending; first pass", errors)
        self.assertIn("errors=0", self.read("boot-diag.txt"))

    def test_later_pass_reports_missing_service(self):
        with open(os.path.join(self.fx, "props.txt"), "w", encoding="utf-8") as fh:
            fh.write("ro.product.device=sakura\n")
        for name in ("dmesg.txt", "logcat.txt"):
            with open(os.path.join(self.fx, name), "w", encoding="utf-8") as fh:
                fh.write("")
        proc = self.run_diag("boot", SAKURA_DIAG_WATCH_ITERATIONS="1",
                             SAKURA_DIAG_WATCH_INTERVAL="0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        errors = self.read("errors.txt")
        for svc in ("qseecomd", "keymaster-3-0", "gatekeeper-1-0"):
            self.assertIn(svc, errors, errors)

    def test_boot_is_bounded(self):
        proc = self.run_diag("boot")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        diag = self.read("boot-diag.txt")
        self.assertIn("collector started", diag)
        self.assertIn("collector finished", diag)


if __name__ == "__main__":
    unittest.main(verbosity=2)
