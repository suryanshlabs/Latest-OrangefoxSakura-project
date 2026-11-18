# Repository audit — defects, severity and status

Scope: the device tree, build scripts, static checks, tests, workflow, docs and
the pinned upstream interaction (`bootable/recovery` @
`8d2aad19deb158e935d70ca5b648162c2b2831ee`, `vendor/recovery` @
`1998cfcaca9bb247ea20d587e565676faa281de9`).

Severity: **CRITICAL** (wrong/bricking/boot-breaking), **HIGH** (feature or
release-blocking), **MEDIUM** (misleading config / missing guard), **LOW**
(cleanup). "Fixed" means the change is in this repository and its check was
executed; it does **not** mean it was exercised on a device.

## Fixed in this round

### BUG-1 — CI discarded the tree-refresh failure (HIGH)

`working tree` workflow step ran

```bash
./build/sync.sh --relink-only "$SRC" 2>/dev/null || true
```

so a failed device-tree refresh — and, after this round, a failed theme-patch
application — was ignored and the build continued from whatever tree was there.
**Fix:** removed `2>/dev/null || true`; `build.sh` also applies the patches as a
hard gate. **Check:** `.github/workflows/orangefox-sakura.yml`; static check
"workflow: tree refresh is not error-suppressed".

### BUG-2 — the static gate could not see new ramdisk binaries (HIGH)

`tools/static_checks.py` skipped every file under `recovery/root/system/bin/`
on the assumption that all of them are proprietary blobs installed by the blob
scripts. Any **non-blob** file added there (the new `sakura-diag`) could be
absent from `PRODUCT_COPY_FILES` and silently never reach the ramdisk — exactly
the defect class that previously kept `twrp.flags` and the init fragments out.
**Fix:** skip only destinations listed in `proprietary-files.txt`; everything
else must be copied explicitly. **Check:** static check "device.mk: every
recovery/root file is in PRODUCT_COPY_FILES" now covers
`system/bin/sakura-diag`.

### BUG-3 — no evidence path for a pre-GUI boot failure (HIGH, feature gap)

The only early-boot evidence was `/tmp/recovery.log`, unreachable unless the
tester knew the path and ADB was up; there was no boot-stage, service or
mount view. **Fix:** `system/bin/sakura-diag` + `init.recovery.sakura_diag.rc`
+ Settings → Error Logs + status-bar badge (see `DIAGNOSTICS.md`).
**Check:** 11 tests in `tests/test_diag.py`; init wiring checked statically.

### BUG-4 — `libpcrecpp.so` was dead configuration (MEDIUM)

`device.mk` requested `$(TARGET_OUT_SHARED_LIBRARIES)/libpcrecpp.so` in
`RECOVERY_LIBRARY_SOURCE_FILES`. AOSP removed `external/pcre` in Android 10;
android-12.1 ships `libpcre2` only. The pinned `prebuilt/relink.sh` does
`[[ -e $src ]] || return 0`, so the file was skipped without a word. It looked
like a dependency that had to exist. **Fix:** line removed with an explanatory
comment. **Check:** pinned `prebuilt/relink.sh`, `prebuilt/Android.mk`; static
checks still pass.

### BUG-5 — duplicate init services and broken shebangs were invisible (MEDIUM)

`tools/check_init_services.py` checked executable paths, ELF class, interpreter
and `DT_NEEDED`, but:

* two `service` blocks with the same name were accepted, although init ignores
  the later definition (the running executable may not be the declared one);
* a non-ELF service was skipped silently, so a shell script with a missing
  shebang interpreter (e.g. `/system/bin/sh` absent) would fail only on device.

**Fix:** duplicate names fail; shell services must have a resolvable
interpreter (with `sh`/`bash`/`toybox` allowed pre-build because the ramdisk
does not exist yet). **Check:** the collector is itself a script service and
the device-tree scan passes.

### BUG-6 — CI never ran the unit tests (MEDIUM)

The preflight ran static checks only. The extraction tooling, the new collector
and the patch applicator are logic; a regression would have been found after a
45 GB sync (or not at all). **Fix:** preflight runs
`python3 -m unittest discover -s tests -v`. **Check:** workflow text; static
check "workflow: unit tests wired into preflight".

### BUG-7 — collector error counting missed threadtime logcat (MEDIUM, found by test)

The first implementation matched `E/` (brief format). Real recovery logs use
`logcat -v threadtime`, where a line is `… E Tag: message`; the fixture test
counted zero logcat errors. **Fix:** match ` E `/` F `, `E/`/`F/` and
`FATAL EXCEPTION`, once per line. **Check:**
`tests/test_diag.py::test_counts_errors_and_warnings`.

### BUG-8 — a report run in a fresh process reported `errors: 0` (MEDIUM, found by test)

Counters are shell variables; `sakura-diag report` did not recompute them, so
the exported report always claimed a clean boot. **Fix:** `cmd_report` runs
`classify` first. **Check:** `test_report_has_required_sections` asserts
`errors: 5`.

### BUG-9 — the badge would have lit up on a healthy boot (HIGH, found by review)

The collector starts at `late-init`, before `on boot` starts `qseecomd`,
Keymaster and Gatekeeper. `getprop init.svc.qseecomd` is empty at that moment,
and the first classifier counted "required service not running" as three
errors — a red `! DIAG` on a perfectly working recovery, i.e. exactly the
"false error" the brief forbids. **Fix:** the first classification records such
services as `pending; first pass` and only the second and later passes count
them; `failed`/`crashed`/`restarting` is still always an error.
**Check:** `tests/test_diag.py::test_preboot_pending_service_is_not_an_error`
and `::test_later_pass_reports_missing_service`.

## Reviewed and deliberately unchanged

| Item | Why it is not a bug / not changed |
|---|---|
| `RECOVERY_LIBRARY_SOURCE_FILES` also lists `libxml2`, `libdrm`, `libion`, `libicuuc` | They exist in android-12.1 and are already listed by the pinned tree; duplicates are harmless and their removal is not evidenced. |
| `on fs` block in `init.recovery.qcom.rc` | Recovery init triggers `late-init -> fs` (`etc/init.rc`), and `on boot` runs after it. The bootdevice symlink and QSEECom permissions are therefore in place before `qseecomd`. |
| `qseecomd` in `class core` with explicit `start` | `class_start core` is not used in recovery init, so the explicit start is the real one; `start` on a running service is a no-op. |
| `sys.usb.config adb` at `on init` | Deliberate: it is what makes ADB (and therefore the pre-GUI log retrieval) available. Changing it would remove the diagnostic path. |
| `/firmware vfat … mounttodecrypt` in `twrp.flags` | Inherited from the R11 mount list; no evidence it is wrong for sakura, and changing mount policy without a device is unsafe. |
| `fileencryption=ice` | No proof of a different on-disk format; changing it cannot convert existing userdata (`ENCRYPTION.md` §3–§4). |
| `BOARD_BUILD_SYSTEM_ROOT_IMAGE`, `TW_INCLUDE_NTFS_3G` | Obsolete/deprecated on 12.1 but harmless; removing them is not required by any failing check. |

## Open (blocked, not fixable in this environment)

| ID | Severity | Item | Blocker |
|---|---|---|---|
| OPEN-1 | HIGH | Decryption is unverified for Android 9–15 | 0/20 genuine sakura vendor blobs, no production build, no device |
| OPEN-2 | HIGH | No build has been performed | needs a ≥45 GB fox_12.1 host; see `BUILD_FROM_CLEAN_CLONE.md` |
| OPEN-3 | MEDIUM | GUI badge/viewer never rendered on hardware | needs a device; the XML is validated, the pixels are not |
| OPEN-4 | MEDIUM | `/cache` persistence depends on `/data` being decrypted/mounted | architectural (cache lives in `/data/cache`); tmpfs + ADB is the guaranteed path |
| OPEN-5 | MEDIUM | Badge does not force a redraw when an error appears after first paint | theme conditions are evaluated per render; documented, not hidden |
| OPEN-6 | MEDIUM | Metadata encryption unsupported | no `dm-default-key`, KM 3.0 vendor (`ENCRYPTION.md` §5) |
| OPEN-7 | LOW | Kernel provenance is not attributable | `KNOWN_ISSUES.md` KI-2 |

## Verification commands used for this audit

```bash
python3 tools/static_checks.py
python3 -m unittest discover -s tests -v
bash -n build/*.sh
git -C <pinned bootable/recovery> apply --check patches/0001-theme-sakura-diagnostics.patch
python3 tools/check_theme.py --theme <patched theme> --strings <en.xml> --strict-targets
```

The patch was also applied to a **clean clone of the real pinned upstream**
(`8d2aad19…`): check → apply → re-apply (idempotent) → theme validation, all
passing. That is source verification, not a device test.
