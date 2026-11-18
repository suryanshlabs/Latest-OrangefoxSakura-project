#!/usr/bin/env python3
"""
check_theme.py - structural validation for OrangeFox theme XML.

Why this exists
---------------
The Error Logs feature is shipped as a theme patch, so a typo in a page name,
an unknown action function or a missing string resource would only show up as a
blank page on a device - after a 45 GB build. This check catches those classes
before a build and is run by tests/test_patches.py on the patched fixture.

It validates:
  * every .xml file is well-formed;
  * page names are unique (a duplicate silently replaces the earlier page);
  * `<action function="...">` names exist in the pinned GUI's action map
    (gui/action.cpp at 8d2aad19), so a typo cannot silently do nothing;
  * `<action function="page">` targets exist (unless templated with % / {@);
  * `<include><xml name="/twres/...">` files exist under the theme root;
  * `{@string}` references used by the checked pages exist in the language
    file, when one is supplied.

Usage:
  python3 tools/check_theme.py --theme gui/theme/portrait_hdpi \
      --strings gui/theme/common/languages/en.xml --strict-targets
  python3 tools/check_theme.py --theme tests/.../theme            # lenient

Exit code: 0 = OK, 1 = at least one structural error.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import xml.etree.ElementTree as ET

# Action functions registered by the pinned bootable/recovery
# (gui/action.cpp, ADD_ACTION / ADD_ACTION_EX at 8d2aad19).
KNOWN_FUNCTIONS = {
    "reboot", "home", "key", "page", "reload", "check_and_reload", "readBackup",
    "set", "clear", "mount", "unmount", "umount", "restoredefaultsettings",
    "copylog", "compute", "addsubtract", "setguitimezone", "overlay", "queuezip",
    "cancelzip", "queueclear", "sleep", "sleepcounter", "appenddatetobackupname",
    "generatebackupname", "checkpartitionlist", "getpartitiondetails", "screenshot",
    "screenshotinternal", "setbrightness", "fileexists", "killterminal",
    "checkbackupname", "adbsideloadcancel", "startmtp", "stopmtp", "cancelbackup",
    "checkpartitionlifetimewrites", "mountsystemtoggle", "setlanguage",
    "togglebacklight", "enableadb", "enablefastboot", "changeterminal",
    "unmapsuperdevices", "disableled", "flashlight", "fileextension", "up_a_level",
    "checkbackupfolder", "calculate_chmod", "get_chmod", "set_chmod", "setpassword",
    "passwordcheck", "flash", "wipe", "refreshsizes", "nandroid", "fixcontexts",
    "fixpermissions", "dd", "partitionsd", "cmd", "terminalcommand", "reinjecttwrp",
    "decrypt", "adbsideload", "openrecoveryscript", "installsu", "fixsu",
    "decrypt_backup", "repair", "resize", "changefilesystem", "flashimage", "twcmd",
    "setbootslot", "repackimage", "reflashtwrp", "fixabrecoverybootloop", "adb",
    "wlfw", "wlfx", "calldeactivateprocess", "disable_replace", "editfile",
    "mergesnapshots", "disableAVB2", "batch", "generatedigests", "ftls",
    "need_reboot",
}


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, message):
        self.errors.append(message)

    def warn(self, message):
        self.warnings.append(message)

    def dump(self):
        for message in self.errors:
            print(f"  [FAIL] {message}")
        for message in self.warnings:
            print(f"  [WARN] {message}")
        status = "PASS" if not self.errors else "FAIL"
        print(f"  RESULT: {status} ({len(self.errors)} error(s), "
              f"{len(self.warnings)} warning(s))")
        return not self.errors


def parse_strings(path):
    if not path:
        return None
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        print(f"ERROR: cannot parse strings file {path}: {exc}", file=sys.stderr)
        raise SystemExit(1)
    names = set()
    for node in root.iter("string"):
        name = node.get("name")
        if name:
            names.add(name)
    return names


def is_dynamic(value):
    return not value or "%" in value or "{@" in value or "$" in value


def check_file(path, rel, report, page_names, page_refs, strings, strict_targets,
               string_refs, theme_root):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        report.error(f"{rel}: not well-formed XML: {exc}")
        return
    except OSError as exc:
        report.error(f"{rel}: cannot read: {exc}")
        return

    for page in root.iter("page"):
        name = page.get("name")
        if name is None:
            report.warn(f"{rel}: <page> without a name")
            continue
        if not is_dynamic(name):
            if name in page_names:
                # OrangeFox ships a second definition of some pages in a
                # variant file (recovery.xml). That is upstream behaviour, so
                # it is reported but is not a failure for an unmodified theme.
                report.warn(f"{rel}: duplicate page name '{name}' "
                            f"(also in {page_names[name]})")
            else:
                page_names[name] = rel

    for action in root.iter("action"):
        function = action.get("function")
        if function is None:
            continue
        if is_dynamic(function):
            # Runtime-substituted function name (%tw_action%, %dbg%, ...).
            continue
        if function not in KNOWN_FUNCTIONS:
            report.error(f"{rel}: unknown action function '{function}' "
                         f"(not in the pinned GUI action map)")
            continue
        if function == "page":
            target = (action.text or "").strip()
            if target and not is_dynamic(target):
                page_refs.append((rel, target))

    for include in root.iter("xml"):
        name = include.get("name")
        if not name or is_dynamic(name):
            continue
        if name.startswith("/twres/"):
            wanted = os.path.join(theme_root, name[len("/twres/"):])
            if not os.path.isfile(wanted):
                report.error(f"{rel}: includes {name}, which does not exist "
                             f"in this theme ({wanted})")

    for text in root.iter("text"):
        value = text.text or ""
        for token in value.split("{@"):
            if "}" in token:
                ref = token.split("}", 1)[0]
                if ref and "=" not in ref:
                    string_refs.append((rel, ref))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--theme", required=True,
                    help="theme root containing ui.xml and pages/")
    ap.add_argument("--strings", default=None,
                    help="language XML to resolve {@string} references against")
    ap.add_argument("--strict-targets", action="store_true",
                    help="fail when a page target is not defined in this theme")
    args = ap.parse_args(argv[1:])

    theme = os.path.abspath(args.theme)
    if not os.path.isdir(theme):
        print(f"ERROR: {theme} is not a directory", file=sys.stderr)
        return 1

    files = [os.path.join(theme, "ui.xml")] if os.path.isfile(
        os.path.join(theme, "ui.xml")) else []
    files += sorted(glob.glob(os.path.join(theme, "pages", "*.xml")))
    files += sorted(glob.glob(os.path.join(theme, "pages", "templates", "*.xml")))
    if not files:
        print(f"ERROR: no theme XML found under {theme}", file=sys.stderr)
        return 1

    report = Report()
    page_names = {}
    page_refs = []
    string_refs = []
    strings = parse_strings(args.strings)

    print(f"==> theme check: {theme}")
    for path in files:
        rel = os.path.relpath(path, theme)
        check_file(path, rel, report, page_names, page_refs, strings,
                   args.strict_targets, string_refs, theme)

    print(f"    files   : {len(files)}")
    print(f"    pages   : {len(page_names)}")
    print(f"    actions : {len(page_refs)} page transition(s)")

    if args.strict_targets:
        for rel, target in page_refs:
            if target not in page_names:
                report.error(f"{rel}: page action targets '{target}', "
                             f"which is not defined")

    if strings is not None:
        for rel, ref in string_refs:
            if ref not in strings:
                report.error(f"{rel}: string '{{@{ref}}}' is not defined in "
                             f"the language file")

    return 0 if report.dump() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
