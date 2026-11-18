#!/usr/bin/env python3
"""
test_diag.py - logic tests for the early-boot diagnostic collector.

The collector is a shell script that runs before the GUI, so these tests drive
it with synthetic fixtures (props/dmesg/logcat/mounts files) instead of a
device. That is the only honest way to test it off-device; they do not prove
that the GUI renders or that init/setprop behave on sakura.

Coverage (one class per defect class found in the audit):
  * real `[key]: [value]` getprop output, not only the `key=value` fixture form;
  * redaction of credentials, serial numbers, IMEI and MAC addresses, and the
    rule that props.txt never contains a sensitive value in the first place;
  * privacy of every exported file (cache and "sdcard" copies included);
  * /cache detection: unmounted, read-only, read-write, and ramdisk-backed
    (a directory in tmpfs is never treated as persistent);
  * report correctness in a *fresh* shell: counters, boot stage and the
    service-classification pass count are persisted, not recomputed;
  * service grace period, crypto-disabled builds and required-TEE failures;
  * benign vs fatal logcat lines (triage instead of a false badge);
  * bounded boot monitor, rotation, missing storage, clear and copy.
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

SERIAL = "ABCDEF123456"
IMEI = "123456789012345"
MAC = "aa:bb:cc:dd:ee:ff"

# Deliberately the real getprop output shape.
PROPS = f"""\
[ro.product.device]: [sakura]
[ro.product.model]: [Redmi 6 Pro]
[ro.product.manufacturer]: [Xiaomi]
[ro.build.display.id]: [PKQ1.190319.001]
[ro.crypto.state]: [encrypted]
[ro.sakura.crypto.mode]: [full]
[ro.boot.serialno]: [{SERIAL}]
[ro.serialno]: [{SERIAL}]
[ro.product.imei]: [{IMEI}]
[ro.boot.wifimacaddr]: [{MAC}]
[persist.sys.timezone]: [UTC]
[init.svc.qseecomd]: [running]
[init.svc.vendor.keymaster-3-0]: [failed]
[init.svc.vendor.gatekeeper-1-0]: [running]
[init.svc.some-optional-hal]: [stopped]
[init.svc.random-other-hal]: [stopped]
"""

DMESG = """\
[    1.0] init: starting service 'qseecomd'
[    2.0] EXT4-fs error (device mmcblk0p49): ext4_lookup: deleted inode referenced
[    3.0] avc: denied { read } for scontext=u:r:recovery:s0
[    4.0] mmc0: error -110 whilst initialising SD card
[    5.0] healthd: battery voltage 4100
"""

LOGCAT = f"""\
01-01 00:00:01.000  1  1 E Keymaster: failed to open qseecom ({SERIAL})
01-01 00:00:02.000  1  1 W Something: password=hunter2 pin=1234
01-01 00:00:03.000  1  1 I Fine: all good mac {MAC}
01-01 00:00:04.000  1  1 F AndroidRuntime: FATAL EXCEPTION: main
01-01 00:00:05.000  1  1 E AudioFlinger: minor audio failure
01-01 00:00:06.000  1  1 E SomeVendorHal: unknown but probably harmless
01-01 00:00:07.000  1  1 E RIL: imei {IMEI} rejected
"""

MOUNTS_NO_DATA = """/dev/root / ext4 rw,seclabel 0 0
tmpfs /tmp tmpfs rw,seclabel 0 0
"""


class DiagCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = os.path.join(self.tmp, "fixtures")
        self.root = os.path.join(self.tmp, "root")
        self.sdroot = os.path.join(self.tmp, "sdcard")
        os.makedirs(self.fx)
        os.makedirs(self.root)
        os.makedirs(self.sdroot)
        self.write_fixtures(PROPS, DMESG, LOGCAT, MOUNTS_NO_DATA)

    def write_fixtures(self, props, dmesg, logcat, mounts):
        for name, content in (("props.txt", props), ("dmesg.txt", dmesg),
                              ("logcat.txt", logcat), ("mounts.txt", mounts)):
            with open(os.path.join(self.fx, name), "w", encoding="utf-8") as fh:
                fh.write(content)

    def env(self, **extra):
        env = {
            "SAKURA_DIAG_FIXTURES": self.fx,
            "SAKURA_DIAG_ROOT": self.root,
            "SAKURA_DIAG_CACHE": os.path.join(self.tmp, "cache"),
            "SAKURA_DIAG_SDCARD": os.path.join(self.tmp, "sdcard", "Fox/diag"),
            "SAKURA_DIAG_SDCARD_ROOT": self.sdroot,
            "SAKURA_DIAG_MOUNTS": os.path.join(self.fx, "mounts.txt"),
            "SAKURA_DIAG_NO_SETPROP": "1",
            "SAKURA_DIAG_NO_MIRROR": "1",
            "SAKURA_DIAG_WATCH_ITERATIONS": "0",
        }
        env.update(extra)
        return env

    def run_diag(self, *args, **extra_env):
        return support.run(["sh", SCRIPT, *args], env=self.env(**extra_env),
                           timeout=60)

    def read(self, name):
        with open(os.path.join(self.root, name), encoding="utf-8") as fh:
            return fh.read()

    def exists(self, name):
        return os.path.isfile(os.path.join(self.root, name))

    # -- helpers for mount-state tests -------------------------------------
    def mount_cache(self, fstype="ext4", options="rw,seclabel"):
        """Create a fake mounted /cache and return the diagnostics dir on it."""
        mnt = os.path.join(self.tmp, "cache_mnt")
        os.makedirs(mnt, exist_ok=True)
        cache_dir = os.path.join(mnt, "recovery", "sakura-diag")
        with open(os.path.join(self.fx, "mounts.txt"), "w", encoding="utf-8") as fh:
            fh.write("/dev/root / ext4 rw,seclabel 0 0\n")
            fh.write("tmpfs /tmp tmpfs rw,seclabel 0 0\n")
            fh.write(f"/dev/block/mmcblk0p49 {mnt} {fstype} {options} 0 0\n")
        return cache_dir

    def status(self, **extra):
        out = self.run_diag("status", **extra).stdout
        fields = {}
        for token in out.split():
            if "=" in token:
                key, value = token.split("=", 1)
                fields[key] = value
        return fields


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
        # The old documentation claimed /cache is /data/cache.
        self.assertNotIn("/data/cache", text)

    def test_cache_persistence_requires_a_real_mount(self):
        with open(SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("mount_lookup", text)
        self.assertIn("not-persistent", text)
        self.assertIn("/proc/mounts", text)


class TestClassification(DiagCase):
    def test_real_getprop_bracket_syntax_is_parsed(self):
        proc = self.run_diag("collect")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        services = self.read("services.txt")
        self.assertIn("qseecomd", services)
        self.assertIn("running", services)
        # Model/device come from the bracketed fixture values.
        report = self.run_diag("report").stdout.strip()
        with open(report, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("Redmi 6 Pro", body)
        self.assertIn("sakura", body)

    def test_severity_split(self):
        self.run_diag("collect")
        errors = self.read("errors.txt")
        warnings = self.read("warnings.txt")
        triage = self.read("triage.txt")

        # critical: kernel EXT4 error, FATAL EXCEPTION, failed required service
        self.assertIn("EXT4-fs error", errors)
        self.assertIn("FATAL EXCEPTION", errors)
        self.assertIn("vendor.keymaster-3-0", errors)
        # recoverable: avc, mmc timeout, benign-tagged logcat E
        self.assertIn("avc: denied", warnings)
        self.assertIn("mmc0", warnings)
        self.assertIn("AudioFlinger", warnings)
        # unknown E lines stay visible but are not confirmed failures
        self.assertIn("SomeVendorHal", triage)
        self.assertNotIn("SomeVendorHal", errors)
        self.assertTrue(self.exists("boot-diag.txt"))

    def test_missing_tee_service_is_an_error_after_the_grace_period(self):
        props = ("[ro.product.device]: [sakura]\n"
                 "[ro.crypto.state]: [encrypted]\n"
                 "[init.svc.qseecomd]: []\n"
                 "[init.svc.vendor.keymaster-3-0]: [running]\n"
                 "[init.svc.vendor.gatekeeper-1-0]: [running]\n")
        self.write_fixtures(props, "", "", MOUNTS_NO_DATA)
        # Pass 1 (late-init): not started yet, must not be an error.
        self.run_diag("collect")
        self.assertNotIn("qseecomd", self.read("errors.txt"))
        self.assertIn("qseecomd", self.read("triage.txt"))
        self.assertIn("errors=0", self.read("boot-diag.txt"))
        # Pass 2 (after `on boot`): still absent -> required failure.
        self.run_diag("collect")
        self.assertIn("qseecomd", self.read("errors.txt"))

    def test_crypto_disabled_build_does_not_report_tee_failures(self):
        props = PROPS.replace("[ro.sakura.crypto.mode]: [full]",
                              "[ro.sakura.crypto.mode]: [none]")
        props = props.replace("[init.svc.qseecomd]: [running]", "[init.svc.qseecomd]: []")
        self.write_fixtures(props, DMESG, "", MOUNTS_NO_DATA)
        for _ in range(3):
            self.run_diag("collect", SAKURA_DIAG_CRYPTO_MODE="none")
        self.assertNotIn("qseecomd", self.read("errors.txt"))
        self.assertIn("crypto mode none", self.read("triage.txt"))
        self.assertEqual(self.status(SAKURA_DIAG_CRYPTO_MODE="none")["crypto"], "none")

    def test_optional_service_is_not_an_error(self):
        self.run_diag("collect")
        self.assertIn("some-optional-hal", self.read("services.txt"))
        self.assertNotIn("some-optional-hal", self.read("errors.txt"))
        self.assertNotIn("random-other-hal", self.read("errors.txt"))


class TestPrivacy(DiagCase):
    def test_report_redacts_credentials_and_identifiers(self):
        self.run_diag("collect")
        out = self.run_diag("report").stdout.strip()
        with open(out, encoding="utf-8") as fh:
            report = fh.read()
        for secret in ("hunter2", "pin=1234", SERIAL, IMEI, MAC):
            self.assertNotIn(secret, report)
        self.assertIn("<redacted", report)
        # Identification that is safe must survive.
        self.assertIn("Redmi 6 Pro", report)
        self.assertIn("sakura", report)

    def test_props_file_never_contains_sensitive_values(self):
        self.run_diag("collect")
        props = self.read("props.txt")
        for secret in (SERIAL, IMEI, MAC):
            self.assertNotIn(secret, props)
        # Sensitive *names* are dropped entirely, not merely redacted.
        self.assertNotIn("serialno", props)
        self.assertNotIn("imei", props)
        self.assertNotIn("timezone", props)  # outside the allow-list
        self.assertIn("ro.product.device", props)

    def test_viewer_files_are_redacted_at_collection_time(self):
        self.run_diag("collect")
        for name in ("logcat.txt", "dmesg.txt", "recovery-log.txt"):
            if not self.exists(name):
                continue
            body = self.read(name)
            for secret in ("hunter2", SERIAL, IMEI, MAC):
                self.assertNotIn(secret, body, f"{name} leaked {secret}")

    def test_sanitized_recovery_log_is_a_copy(self):
        raw = os.path.join(self.tmp, "recovery.log")
        with open(raw, "w", encoding="utf-8") as fh:
            fh.write(f"I:Starting TWRP\nI:serial={SERIAL}\n"
                     f"I:password=hunter2\nI:done\n")
        self.run_diag("collect", SAKURA_DIAG_RECOVERY_LOG=raw)
        copy = self.read("recovery-log.txt")
        self.assertIn("Starting TWRP", copy)
        self.assertNotIn(SERIAL, copy)
        self.assertNotIn("hunter2", copy)
        # The original must be untouched.
        with open(raw, encoding="utf-8") as fh:
            self.assertIn("hunter2", fh.read())

    def test_exported_copies_contain_no_secrets(self):
        cache = self.mount_cache()
        self.run_diag("collect")
        proc = self.run_diag("export", SAKURA_DIAG_CACHE=cache,
                             SAKURA_DIAG_NO_MIRROR="0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for base in (cache, os.path.join(self.sdroot, "Fox/diag")):
            if not os.path.isdir(base):
                continue
            for name in os.listdir(base):
                path = os.path.join(base, name)
                if not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8", errors="replace") as fh:
                    body = fh.read()
                for secret in ("hunter2", SERIAL, IMEI, MAC):
                    self.assertNotIn(secret, body, f"{path} leaked {secret}")


class TestCachePersistence(DiagCase):
    def test_unmounted_cache_is_reported_and_not_written(self):
        # Only the root filesystem is mounted: /cache has no partition of its own.
        with open(os.path.join(self.fx, "mounts.txt"), "w", encoding="utf-8") as fh:
            fh.write("/dev/root / ext4 rw,seclabel 0 0\n")
        self.assertIn("cache=unmounted",
                      self.run_diag("status", SAKURA_DIAG_NO_MIRROR="0").stdout)
        shutil.rmtree(self.sdroot)   # no internal storage either
        proc = self.run_diag("export", SAKURA_DIAG_NO_MIRROR="0")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("tmpfs", proc.stdout)
        self.assertIn("/cache is not mounted", proc.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "cache")))

    def test_read_only_cache_is_not_written(self):
        cache = self.mount_cache(options="ro,seclabel")
        state = self.run_diag("status", SAKURA_DIAG_CACHE=cache,
                              SAKURA_DIAG_NO_MIRROR="0").stdout
        self.assertIn("cache=read-only", state)
        self.run_diag("collect", SAKURA_DIAG_CACHE=cache, SAKURA_DIAG_NO_MIRROR="0")
        self.assertFalse(os.path.exists(cache), "nothing may be created on a ro /cache")

    def test_read_write_cache_is_mirrored(self):
        cache = self.mount_cache()
        self.run_diag("collect", SAKURA_DIAG_CACHE=cache, SAKURA_DIAG_NO_MIRROR="0")
        self.assertTrue(os.path.isfile(os.path.join(cache, "boot-diag.txt")))
        self.assertTrue(os.path.isfile(os.path.join(cache, "README.txt")))
        with open(os.path.join(cache, "README.txt"), encoding="utf-8") as fh:
            self.assertIn("redacted", fh.read().lower())

    def test_ramdisk_backed_cache_is_never_persistent(self):
        cache = self.mount_cache(fstype="tmpfs")
        state = self.run_diag("status", SAKURA_DIAG_CACHE=cache,
                              SAKURA_DIAG_NO_MIRROR="0").stdout
        self.assertIn("cache=not-persistent", state)
        self.run_diag("collect", SAKURA_DIAG_CACHE=cache, SAKURA_DIAG_NO_MIRROR="0")
        self.assertFalse(os.path.exists(cache))


class TestReportState(DiagCase):
    def test_report_in_a_fresh_process_keeps_counters(self):
        self.run_diag("collect")
        out = self.run_diag("report").stdout.strip()
        with open(out, encoding="utf-8") as fh:
            report = fh.read()
        # 1 kernel + 1 fatal + 1 failed service
        self.assertIn("errors:         3", report)
        self.assertIn("warnings:       3", report)
        # Keymaster / SomeVendorHal / RIL E lines are triage, not failures.
        self.assertIn("triage:         3", report)
        self.assertIn("service errors: 1", report)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "report.txt")))

    def test_report_does_not_reclassify_or_reset(self):
        self.run_diag("collect")
        self.run_diag("report")
        state_after_first = self.read("state")
        self.run_diag("report")
        self.assertIn("classify_pass=1", self.read("state"))
        self.assertEqual(state_after_first, self.read("state"))

    def test_boot_stage_is_persisted_for_the_report(self):
        proc = self.run_diag("boot", SAKURA_DIAG_WATCH_ITERATIONS="2",
                             SAKURA_DIAG_WATCH_INTERVAL="0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = self.run_diag("report").stdout.strip()
        with open(out, encoding="utf-8") as fh:
            report = fh.read()
        self.assertNotIn("boot stage:     unknown", report)
        stage = [ln.split("=", 1)[1] for ln in self.read("state").splitlines()
                 if ln.startswith("boot_stage=")][0]
        self.assertIn(stage, report)
        self.assertIn(f"stage: {stage}", self.read("boot-diag.txt"))
        self.assertIn(stage, ("monitor-timeout", "gui-process-up", "decrypt-pending"))

    def test_status_survives_a_new_process(self):
        self.run_diag("collect")
        self.assertIn("errors=3", self.run_diag("status").stdout)


class TestBoundsAndStorage(DiagCase):
    def test_rotation_is_bounded(self):
        for _ in range(40):
            proc = self.run_diag("collect", SAKURA_DIAG_MAX_BYTES="400",
                                 SAKURA_DIAG_MAX_ROTATIONS="3")
            self.assertEqual(proc.returncode, 0, proc.stderr)
        names = sorted(n for n in os.listdir(self.root) if n.startswith("boot-diag.txt"))
        self.assertEqual(len(names), 4, names)      # base + 3 rotations
        for name in names:
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

    def test_boot_is_bounded_and_records_stages(self):
        proc = self.run_diag("boot", SAKURA_DIAG_WATCH_ITERATIONS="3",
                             SAKURA_DIAG_WATCH_INTERVAL="0")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        diag = self.read("boot-diag.txt")
        self.assertIn("collector started", diag)
        self.assertIn("collector finished", diag)
        self.assertIn("stage:", diag)


class TestClearAndCopy(DiagCase):
    def test_clear_needs_confirmation_and_keeps_logs(self):
        self.run_diag("collect")
        refused = self.run_diag("clear")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("Refusing to clear", refused.stdout)
        self.assertTrue(self.exists("dmesg.txt"))

    def test_clear_removes_session_and_persistent_copies_only(self):
        cache = self.mount_cache()
        self.run_diag("collect", SAKURA_DIAG_CACHE=cache, SAKURA_DIAG_NO_MIRROR="0")
        self.run_diag("export", SAKURA_DIAG_CACHE=cache, SAKURA_DIAG_NO_MIRROR="0")
        sd = os.path.join(self.sdroot, "Fox/diag")
        self.assertTrue(os.path.isfile(os.path.join(cache, "boot-diag.txt")))
        self.assertTrue(os.path.isfile(os.path.join(sd, "boot-diag.txt")))
        # A file that is not ours must survive.
        keep = os.path.join(os.path.dirname(cache), "user-file.txt")
        with open(keep, "w", encoding="utf-8") as fh:
            fh.write("keep me\n")

        cleared = self.run_diag("clear", "--yes", SAKURA_DIAG_CACHE=cache,
                                SAKURA_DIAG_NO_MIRROR="0")
        self.assertEqual(cleared.returncode, 0, cleared.stdout)
        self.assertFalse(self.exists("dmesg.txt"))
        self.assertFalse(os.path.exists(os.path.join(cache, "boot-diag.txt")))
        self.assertFalse(os.path.exists(os.path.join(sd, "boot-diag.txt")))
        self.assertTrue(os.path.isfile(keep))

    def test_copy_selected_log_to_writable_storage(self):
        self.run_diag("collect")
        proc = self.run_diag("copy", "mounts")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        sd = os.path.join(self.sdroot, "Fox/diag")
        self.assertTrue(os.path.isfile(os.path.join(sd, "mounts.txt")))
        with open(os.path.join(sd, "mounts.txt"), encoding="utf-8") as fh:
            self.assertIn("/tmp", fh.read())

    def test_copy_without_writable_storage_is_not_a_failure(self):
        self.run_diag("collect")
        # /sdcard root removed; /cache unmounted (NO_MIRROR=0 but no mount)
        shutil.rmtree(self.sdroot)
        proc = self.run_diag("copy", "mounts", SAKURA_DIAG_NO_MIRROR="0")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Neither /sdcard nor /cache", proc.stdout)

    def test_unknown_copy_target_is_refused(self):
        proc = self.run_diag("copy", "everything")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
