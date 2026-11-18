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
**Check:** `tests/test_diag.py::TestClassification::test_severity_split` (a required TEE
service that is already `failed` is still an error) and
`::test_optional_service_is_not_an_error`.


### BUG-10 — kernel warnings were counted but never written (HIGH, found by test)

`append_matches()` built its prefix with `sed "s/^/[$prefix] /"`. The prefix for
kernel security lines is `selinux/warn`, and the `/` **ends the `s///` command**,
so sed failed, printed nothing, and `2>/dev/null` hid it. The counters still
included those lines, so `warnings: 3` could appear with a `warnings.txt` holding
one entry — a report that contradicts itself and a GUI filter that shows nothing
for an AVC denial.
**Fix:** use `|` as the sed delimiter. **Check:**
`tests/test_diag.py::TestClassification::test_severity_split` asserts the AVC and
mmc lines are present in `warnings.txt`, not just counted.

### BUG-11 — real getprop output leaked serials and mangles credential lines (HIGH, privacy)

Two defects in one function:

* The parser only understood `key=value`. Android's real output is
  `[ro.boot.serialno]: [ABC123]`, so **no** serial, IMEI or MAC in a bracket line
  was ever redacted — they went straight into `dmesg.txt`, `logcat.txt`,
  `recovery-log.txt`, the report and every export.
* The name-based replacement used `\1\2`, but the sensitive-name expression is an
  inner capture group, so the key was written twice
  (`passwordpassword<redacted>`) and the line no longer matched the documented
  shape.

**Fix:** the redactor accepts `[key]: [value]` in addition to `key=value`, uses
`\1\3<redacted>` for the three-group expression, and additionally redacts the
device's own serial/IMEI **by value** (read from `ro.serialno`,
`ro.boot.serialno`, `ro.imei`, `ro.meid`) so a bare occurrence with no key name
is still removed. **Check:** `TestPrivacy` (bracket syntax, IMEI/serial, MAC),
`test_report_redacts_credentials_and_identifiers`,
`test_exported_copies_contain_no_secrets`.

### BUG-12 — `props.txt` was copied raw into every shareable bundle (HIGH, privacy)

The export step copied `*.txt`, including a property dump. Even with redaction,
the safest property is the one that was never written: `props.txt` is now built
from an allow-list of prefixes **and** a block-list of sensitive names, and
exported copies are re-redacted on the way out. A raw secret therefore cannot
reach `/cache`, `/sdcard`, a GUI viewer or a report bundle.
**Check:** `test_props_file_never_contains_sensitive_values`,
`test_exported_copies_contain_no_secrets`.

### BUG-13 — `/cache` handling was guesswork, and the docs contradicted the fstab (MEDIUM)

`cache_writable()` created the directory and ran a write test without proving
that `/cache` was a mount point, so a directory in the ramdisk could be treated
as a persistent copy. The docs simultaneously claimed `/cache` was `/data/cache`,
while `recovery.fstab` maps a **separate** `by-name/cache` ext4 partition.
Worse, a path that resolved only to `/` (i.e. `/cache` not mounted at all) was
reported as `not-persistent` instead of `unmounted`.
**Fix:** `mount_lookup()` resolves the longest containing mount point from
`/proc/mounts` (decoding `\040`) and `cache_state()` returns
`unmounted|not-persistent|read-only|unwritable|rw|disabled`; nothing is created
unless the state is `rw` on a real filesystem. Every `/data/cache` claim was
removed and `tools/static_checks.py` fails if it comes back.
**Check:** the four `/cache` tests in `TestCachePersistence`, plus the docs gate.

### BUG-14 — a no-decryption build reported its own TEE services as failures (MEDIUM)

`SAKURA_ALLOW_MISSING_CRYPTO=1` builds intentionally ship no qseecomd/Keymaster.
The collector's hardcoded required-service list still flagged them, so an
intentional build produced a permanent red badge.
**Fix:** the build writes `ro.sakura.crypto.mode=full|none`; in `none` mode those
services are listed in `triage.txt` as `(not required: crypto mode none)` and
never counted. Full mode is unchanged and still fails loudly; the production
blob gate (`check_crypto_blobs.sh --require`) is untouched.
**Check:** `test_crypto_disabled_build_does_not_report_tee_failures`,
and `test_severity_split` for full mode.

### BUG-15 — the mounts entry opened `encryption.txt`, with no mounts viewer (MEDIUM, GUI)

Part 3 requires a real mount-status viewer, and the old patch's only mount-ish
entry displayed `encryption.txt`. There was no `mounts.txt` page at all.
**Fix:** the regenerated patch adds `mounts.txt` and `crypto-errors.txt` viewers,
an unclassified (`triage.txt`) view, a copy page with 11 targets, a clear
confirmation page and a `diag_view` page that returns to Error Logs.
**Check:** `test_patches.py` (pages, actions, back targets, `fileexists` gate) and
`static_checks.py` (feature matrix).

### BUG-16 — a metadata typo and a misleading "unsupportable" comment (MEDIUM)

`BoardConfig.mk` documented the metadata decision as `DI[disabled]` (truncated
text) and stated flatly that metadata decryption was unsupportable, while the
pinned tree compiles `-DTW_INCLUDE_FBE_METADATA_DECRYPT` and parses
`metadata_encryption=`/`keydirectory=` whenever crypto is on. The real problem is
narrower and more dangerous than "unsupported": a non-empty key directory makes
`Setup_Data_Partition()` believe `/data` is encrypted. That is now documented as
the reason for the default, and `tools/configure_metadata.py` makes enabling it
explicit (`--confirm-rom-uses-metadata`), reversible (byte-exact `--disable`) and
validated (`--check` fails on half-applied trees).
**Check:** `tests/test_metadata.py` (10 tests).


### BUG-17 — the theme could not be selected, killing the build inside Soong (HIGH, observed in CI)

Four CI runs (`43724180838`, `43724709164`, `43726944108`, `43727215787`,
`43727418831`) stopped at the first Soong invocation with

```
Could not find ui.xml for TW_THEME: not set
(theme selection failed; exiting)
```

`gui/libguitwrp_defaults.go` reads `TW_THEME` **only** through Soong's vendor
config namespace `twrpVarsPlugin`, which `vendor/twrp/config/BoardConfigSoong.mk`
fills from `EXPORT_TO_SOONG`. When the device `BoardConfig.mk` does not include
that file — or when an include lands where it cannot take effect — make still sees
`TW_THEME` but Soong sees `""`, the plugin calls `os.Exit(-1)`, and the build dies
before compiling anything. The message names none of the four possible causes, so
each CI run cost minutes to diagnose and the retries changed nothing.

**Fix:** two layers.

1. `BoardConfig.mk` now declares `TARGET_SCREEN_WIDTH := 1080` /
   `TARGET_SCREEN_HEIGHT := 2280` (the panel resolution already documented in
   `DEVICE_COMPATIBILITY.md` and `vendorsetup.sh`). `determineTheme()` derives
   `portrait_hdpi` from the resolution when `TW_THEME` is empty, so an export
   regression degrades to a working theme instead of a dead build.
2. `build/check_theme_inputs.sh` — run by `build/build.sh` *before* envsetup —
   checks the whole chain in seconds: `TW_THEME`/resolution in the device tree,
   `gui/theme/<theme>/ui.xml` in the pinned recovery, the `twrpVarsPlugin`
   namespace and `TW_THEME` in `EXPORT_TO_SOONG`, the include in `BoardConfig.mk`,
   and the OrangeFox `orangefox_soong.mk` ordering (it must precede the export
   loop or `OF_LANDSCAPE_MODE` is silently dropped).

**Check:** `tests/test_theme_inputs.py` (11 tests, one per failure mode).

**Not established:** whether the include was already present-but-ineffective in
those runs. The preflight proves the inputs; only a completed build proves that
`soong.variables` carries them. That is recorded as OPEN-8 rather than claimed as
fixed.

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
| OPEN-4 | MEDIUM | Persistent `/cache` mirror needs the cache partition mounted | `/cache` is its own ext4 partition; if it is absent or read-only the mirror is skipped by design. tmpfs + ADB is the guaranteed path |
| OPEN-5 | MEDIUM | Badge does not force a redraw when an error appears after first paint | theme conditions are evaluated per render; documented, not hidden |
| OPEN-6 | MEDIUM | Metadata decryption is configured but not usable | userspace path compiled + opt-in wiring shipped; neither kernel has `dm-default-key` and the vendor is KM 3.0 (`ENCRYPTION.md` §6a) |
| OPEN-7 | LOW | Kernel provenance is not attributable | `KNOWN_ISSUES.md` KI-2 |
| OPEN-8 | HIGH | No build has ever completed: theme selection died inside Soong in all five CI runs | root cause narrowed and preflighted (`BUG-17`), not proven fixed without a completed build |

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
