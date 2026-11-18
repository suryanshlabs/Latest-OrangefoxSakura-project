#!/usr/bin/env python3
"""
test_theme_inputs.py - the TW_THEME -> Soong vendor-config preflight.

Four CI runs of this tree stopped inside Soong with

    Could not find ui.xml for TW_THEME: not set
    (theme selection failed; exiting)

which is gui/libguitwrp_defaults.go failing because
`ctx.Config().VendorConfig("twrpVarsPlugin").String("TW_THEME")` was empty. The
message names none of the four things that can cause it, so build/build.sh runs
build/check_theme_inputs.sh first. These tests pin each failure mode.

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
SCRIPT = os.path.join(REPO, "build", "check_theme_inputs.sh")

TWRP_SOONG = """\
EXPORT_TO_SOONG := KERNEL_ARCH TW_THEME TW_CUSTOM_THEME DEVICE_RESOLUTION
SOONG_CONFIG_NAMESPACES += twrpVarsPlugin
SOONG_CONFIG_twrpVarsPlugin :=
define addVar
SOONG_CONFIG_twrpVarsPlugin += $(1)
SOONG_CONFIG_twrpVarsPlugin_$(1) := $$(subst ",",$($1))
endef
$(foreach v,$(EXPORT_TO_SOONG),$(eval $(call addVar,$(v))))
"""

BOARD_OK = """\
DEVICE_PATH := device/xiaomi/sakura
TW_THEME := portrait_hdpi
TARGET_SCREEN_WIDTH := 1080
TARGET_SCREEN_HEIGHT := 2280
include vendor/twrp/config/BoardConfigSoong.mk
"""


class ThemeInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = self.tmp
        self.dev = os.path.join(self.src, "device", "xiaomi", "sakura")
        self.soong_dir = os.path.join(self.src, "vendor", "twrp", "config")
        self.theme = os.path.join(self.src, "bootable", "recovery", "gui",
                                  "theme", "portrait_hdpi")
        for d in (self.dev, self.soong_dir, self.theme):
            os.makedirs(d, exist_ok=True)
        self.write(os.path.join(self.soong_dir, "BoardConfigSoong.mk"), TWRP_SOONG)
        self.write(os.path.join(self.theme, "ui.xml"), "<recovery/>\n")
        self.write(os.path.join(self.dev, "BoardConfig.mk"), BOARD_OK)

    def write(self, path, text):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def run_check(self, *args):
        return support.run(["bash", SCRIPT, self.src, *args])

    def test_complete_tree_passes(self):
        proc = self.run_check()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

    def test_missing_theme_ui_xml_fails(self):
        os.remove(os.path.join(self.theme, "ui.xml"))
        proc = self.run_check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("portrait_hdpi/ui.xml is missing", proc.stdout)

    def test_missing_boardconfig_include_fails(self):
        self.write(os.path.join(self.dev, "BoardConfig.mk"),
                   BOARD_OK.replace("include vendor/twrp/config/BoardConfigSoong.mk\n", ""))
        proc = self.run_check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("never includes vendor/twrp/config/BoardConfigSoong.mk", proc.stdout)

    def test_missing_vendor_twrp_fails(self):
        shutil.rmtree(os.path.join(self.src, "vendor"))
        proc = self.run_check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("vendor/twrp was not synced", proc.stdout)

    def test_namespace_without_tw_theme_fails(self):
        self.write(os.path.join(self.soong_dir, "BoardConfigSoong.mk"),
                   "SOONG_CONFIG_NAMESPACES += twrpVarsPlugin\n"
                   "SOONG_CONFIG_twrpVarsPlugin := KERNEL_ARCH\n")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("does not list TW_THEME", proc.stdout)

    def test_no_theme_and_no_resolution_fails(self):
        self.write(os.path.join(self.dev, "BoardConfig.mk"),
                   "include vendor/twrp/config/BoardConfigSoong.mk\n")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("none of TW_THEME, DEVICE_RESOLUTION or", proc.stdout)

    def test_resolution_only_is_enough_but_warns(self):
        self.write(os.path.join(self.dev, "BoardConfig.mk"),
                   "TARGET_SCREEN_WIDTH := 1080\nTARGET_SCREEN_HEIGHT := 2280\n"
                   "include vendor/twrp/config/BoardConfigSoong.mk\n")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("RESULT: PASS", proc.stdout)

    def test_orangefox_include_after_the_export_loop_is_an_error(self):
        ox = os.path.join(self.src, "bootable", "recovery", "orangefox_soong.mk")
        self.write(ox, "EXPORT_TO_SOONG += OF_LANDSCAPE_MODE\n")
        self.write(os.path.join(self.dev, "BoardConfig.mk"),
                   BOARD_OK + "include bootable/recovery/orangefox_soong.mk\n")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("included after BoardConfigSoong.mk", proc.stdout)

    def test_orangefox_include_before_the_export_loop_passes(self):
        ox = os.path.join(self.src, "bootable", "recovery", "orangefox_soong.mk")
        self.write(ox, "EXPORT_TO_SOONG += OF_LANDSCAPE_MODE\n")
        self.write(os.path.join(self.dev, "BoardConfig.mk"),
                   "TW_THEME := portrait_hdpi\n"
                   "TARGET_SCREEN_WIDTH := 1080\nTARGET_SCREEN_HEIGHT := 2280\n"
                   "include bootable/recovery/orangefox_soong.mk\n"
                   "include vendor/twrp/config/BoardConfigSoong.mk\n")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("included before the twrpVarsPlugin export loop", proc.stdout)

    def test_real_device_tree_declares_theme_and_resolution(self):
        board = os.path.join(REPO, "device", "xiaomi", "sakura", "BoardConfig.mk")
        with open(board, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("TW_THEME := portrait_hdpi", text)
        self.assertIn("TARGET_SCREEN_WIDTH := 1080", text)
        self.assertIn("TARGET_SCREEN_HEIGHT := 2280", text)
        self.assertIn("include vendor/twrp/config/BoardConfigSoong.mk", text)

    def test_build_script_runs_the_preflight(self):
        with open(os.path.join(REPO, "build", "build.sh"), encoding="utf-8") as fh:
            build = fh.read()
        self.assertIn("check_theme_inputs.sh", build)
        # must run before the build starts, i.e. before envsetup is sourced
        self.assertLess(build.index("\"$ROOT/build/check_theme_inputs.sh\""),
                        build.index(". build/envsetup.sh"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
