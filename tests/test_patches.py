#!/usr/bin/env python3
"""
test_patches.py - patch application, idempotency and fail-closed behaviour.

The Error Logs UI lives in a patch against the pinned OrangeFox theme. A patch
that silently stops applying would ship an image whose Settings page is missing
while the documentation says it exists. These tests make that impossible:

  * apply against a fixture built from the patch's own pre-image;
  * `--check` writes nothing;
  * a second apply is detected as already applied (idempotent);
  * changed upstream context is a hard failure;
  * an unexpected upstream revision is refused unless explicitly allowed;
  * the patched theme passes tools/check_theme.py with strict page targets and
    string resources;
  * patches/PINNED_REVISIONS agrees with build/sync.sh.

The fixture is derived from the patch itself (context + removed lines). It
proves the patch is self-consistent and that the applicator behaves; the patch
is additionally verified against the real pinned upstream checkout during
release verification (see documentation/BUILD_FROM_CLEAN_CLONE.md).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: E402

REPO = support.REPO
PATCHES = os.path.join(REPO, "patches")
APPLY = os.path.join(REPO, "build", "apply_patches.sh")
CHECK_THEME = os.path.join(REPO, "tools", "check_theme.py")


def parse_patch(path):
    """Return {repo-relative path: pre-image text} for every modified file."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    files = {}
    current = None
    new_file = False
    hunks = 0
    body = []

    def flush():
        if current and not new_file:
            files[current] = "\n".join(body) + "\n"

    for line in lines:
        if line.startswith("diff --git "):
            flush()
            current = None
            new_file = False
            hunks = 0
            body = []
            match = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            if match:
                current = match.group(2)
        elif line.startswith("--- "):
            new_file = line.strip() == "--- /dev/null"
        elif line.startswith("@@"):
            hunks += 1
        elif current and not new_file:
            if line.startswith(" ") or line.startswith("-"):
                body.append(line[1:])
            elif line.startswith("\\"):
                continue
    flush()

    if hunks > 1:
        raise AssertionError(
            "this helper only reconstructs single-hunk files; extend it before "
            "adding a multi-hunk patch")
    return files


class PatchRepo:
    """A minimal `$SRC` tree with bootable/recovery at the patched paths."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        self.rec = os.path.join(self.src, "bootable", "recovery")
        os.makedirs(self.rec)
        self.git("init", "-q")

    def git(self, *args, check=True):
        return subprocess.run(
            ["git", "-c", "user.email=test@example.invalid",
             "-c", "user.name=patch-test", *args],
            cwd=self.rec, capture_output=True, text=True, check=check)

    def write(self, rel, text):
        path = os.path.join(self.rec, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, message="fixture"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def cleanup(self):
        shutil.rmtree(self.tmp, True)


def build_fixture():
    repo = PatchRepo()
    for rel, text in parse_patch(os.path.join(
            PATCHES, "0001-theme-sakura-diagnostics.patch")).items():
        repo.write(rel, text)
    repo.commit()
    return repo


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.repo = build_fixture()
        self.addCleanup(self.repo.cleanup)

    def apply(self, *args, allow_mismatch=True):
        extra = ["--allow-revision-mismatch"] if allow_mismatch else []
        return subprocess.run(
            [APPLY, "--src", self.repo.src, *extra, *args],
            capture_output=True, text=True, timeout=120)

    def status(self):
        return self.repo.git("status", "--porcelain").stdout

    def test_check_writes_nothing(self):
        before = self.status()
        proc = self.apply("--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("would apply", proc.stdout)
        self.assertEqual(before, self.status())

    def test_apply_and_second_apply_is_idempotent(self):
        first = self.apply()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("applied:", first.stdout)
        self.assertIn("M gui/theme/portrait_hdpi/ui.xml", self.status())

        second = self.apply()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("already applied", second.stdout)

    def test_changed_context_fails(self):
        path = os.path.join(self.repo.rec, "gui/theme/portrait_hdpi/pages/settings.xml")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("{@about_hdr}", "{@about_header}"))
        self.repo.commit("break context")

        proc = self.apply("--check")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no longer applies", proc.stderr + proc.stdout)

        # And an actual apply must not write a partial tree.
        before = self.status()
        proc = self.apply()
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(before, self.status())

    def test_unexpected_revision_is_refused(self):
        self.repo.write("README.extra", "revision drift\n")
        self.repo.commit("unexpected revision")
        proc = self.apply("--check", allow_mismatch=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("revision mismatch", proc.stderr + proc.stdout)

        allowed = self.apply("--check")
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

    def test_patched_theme_is_structurally_valid(self):
        proc = self.apply()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # The apply fixture is only the patch's context, not a whole theme, so
        # validate the complete file the patch adds (diag.xml) inside a stub
        # theme that supplies the pages and strings it references. The other
        # edited files are validated against the real pinned upstream in
        # release verification; here their applicability is what matters.
        theme = os.path.join(self.repo.tmp, "theme")
        pages = os.path.join(theme, "pages")
        os.makedirs(pages)
        shutil.copy(os.path.join(self.repo.rec, "gui/theme/portrait_hdpi/pages/diag.xml"),
                    os.path.join(pages, "diag.xml"))
        with open(os.path.join(theme, "ui.xml"), "w", encoding="utf-8") as fh:
            fh.write('<?xml version="1.0"?>\n<recovery><include>'
                     '<xml name="/twres/pages/diag.xml"/>'
                     '</include></recovery>\n')
        for name, page in (("main.xml", "main"), ("settings.xml", "settings"),
                           ("files.xml", "cat_file")):
            with open(os.path.join(pages, name), "w", encoding="utf-8") as fh:
                fh.write('<?xml version="1.0"?>\n<recovery><pages>'
                         f'<page name="{page}"/></pages></recovery>\n')

        with open(os.path.join(self.repo.rec, "gui/theme/common/languages/en.xml"),
                  encoding="utf-8") as fh:
            patched = fh.read()
        strings = re.findall(r"<string name=\"[^\"]+\">.*?</string>", patched, re.S)
        self.assertTrue(strings, "patched en.xml should contain strings")
        strings_file = os.path.join(theme, "en.xml")
        with open(strings_file, "w", encoding="utf-8") as fh:
            fh.write("<?xml version=\"1.0\"?>\n<language><resources>\n")
            fh.write("\n".join(strings))
            fh.write("\n</resources></language>\n")

        check = support.run([
            sys.executable, CHECK_THEME,
            "--theme", theme,
            "--strings", strings_file,
            "--strict-targets",
        ])
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("RESULT: PASS", check.stdout)
        # 5 diagnostics pages (hub, viewer, report, copy, clear) + the stubs
        pages = int([ln.split(":")[1] for ln in check.stdout.splitlines()
                     if ln.strip().startswith("pages")][0])
        self.assertGreaterEqual(pages, 8)


class PinConsistency(unittest.TestCase):
    def test_pinned_revision_matches_sync_script(self):
        pins = {}
        with open(os.path.join(PATCHES, "PINNED_REVISIONS"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                pins[key] = value

        with open(os.path.join(REPO, "build", "sync.sh"), encoding="utf-8") as fh:
            sync = fh.read()
        self.assertIn(f'RECOVERY_SHA="{pins["bootable_recovery"]}"', sync)
        self.assertIn(f'VENDOR_SHA="{pins["vendor_recovery"]}"', sync)

    def test_series_lists_existing_patches(self):
        with open(os.path.join(PATCHES, "series"), encoding="utf-8") as fh:
            entries = [ln.strip() for ln in fh
                       if ln.strip() and not ln.strip().startswith("#")]
        self.assertTrue(entries)
        for entry in entries:
            self.assertTrue(os.path.isfile(os.path.join(PATCHES, entry)), entry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
