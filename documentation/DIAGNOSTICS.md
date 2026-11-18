# Boot diagnostics and Error Logs

Status: **implemented in source, unit-tested off-device, NOT yet seen on a
device.** No production image has been built here and no recovery has been
booted. Everything below describes what the code does; see §9 for what remains
unverified.

## 1. Why this exists

The failure mode that matters most on this port is a recovery that never reaches
the GUI: a missing TEE binary, a bad `on boot` service, an unmountable `/data`.
In that state the only classic evidence was `/tmp/recovery.log`, which a tester
had to know to pull. The diagnostic system records the same boot from init
onwards, tags every line with a timestamp, component and severity, and keeps a
copy where adbd can always reach it.

It is also **not** a decryption feature. It reports; it never changes an
encryption decision.

## 2. Components

| Component | Path | Role |
|---|---|---|
| Collector | `device/xiaomi/sakura/recovery/root/system/bin/sakura-diag` | Shell script: snapshot, classify, report, export, clear |
| Init service | `recovery/root/init.recovery.sakura_diag.rc` | Starts the collector once at `on boot` as a `oneshot` service |
| Import | `recovery/root/init.recovery.qcom.rc` | `import /init.recovery.sakura_diag.rc` |
| GUI patch | `patches/0001-theme-sakura-diagnostics.patch` | Settings → Error Logs, viewer pages, status-bar `! DIAG` badge |
| Applicator | `build/apply_patches.sh` | Applies the pinned patch, fail-closed, idempotent |
| Validator | `tools/check_theme.py` | Pages/actions/strings/targets of the patched theme |
| Tests | `tests/test_diag.py`, `tests/test_patches.py` | Logic, bounds, redaction, patch behaviour |

## 3. Boot ordering (as implemented)

```
early-init -> init -> late-init
                       |-- sakura_diag starts   (device on late-init, queued
                       |                         before init.rc's late-init
                       |                         because the device rc is
                       |                         imported at the top)
                       |-- early-fs
                       |-- fs        (init.recovery.qcom.rc: bootdevice symlink,
                       |              /dev/qseecom permissions)
                       |-- post-fs / post-fs-data
                       |-- early-boot
                       `-- boot      (class_start default -> GUI;
                                      init.recovery.qcom_decrypt.rc:
                                      start qseecomd)
```

`start sakura_diag` is a **service**, not `exec`, so init forks it and continues
immediately. Because the device rc is imported at the top of `init.rc`, its
`on late-init` action is queued before the action that triggers `boot` and
`class_start default`, so the first snapshot and its `setprop` happen before
`gui_init()`. That is what lets the status-bar badge be decided on first paint.
TEE services start later in `on boot`; the watch loop re-samples them.

## 4. Where logs live (and what is never touched)

| Location | When | Survives reboot | Notes |
|---|---|---|---|
| `/tmp/sakura-diag/` | always | no | tmpfs, root-only (`0750`), readable over adbd. Primary store. |
| `/cache/recovery/sakura-diag/` | only when `/cache` is already mounted and writable | yes | `/cache` is `/data/cache`; on an encrypted, undecrypted device it is unavailable. The collector **does not mount it**. |
| `/sdcard/Fox/diag/` | export only, and only if `/sdcard` is already writable | yes | convenience copy; never required |

The collector never mounts, formats or writes to `/data`, `/metadata` or any
other partition. `tests/test_diag.py` asserts the script contains no `/data`
write, no `mkfs`, and no `rm -rf /data`.

Files produced:

```
boot-diag.txt      timestamped collector/init/component trail (rotated)
dmesg.txt          kernel log snapshot (redacted)
logcat.txt         logcat threadtime snapshot (redacted)
services.txt       init.svc.* states + declared-but-missing required services
mounts.txt         /proc/mounts snapshot
props.txt          selected ro.* / init.svc.* / sys.usb.* properties
encryption.txt     crypto properties + /data and dm-crypt/dm-default-key mounts
errors.txt         errors and warnings only, prefixed by component
report.txt         newest redacted diagnostic report (stable name for the GUI)
Sakura-Diagnostic-Report-<timestamp>.txt
```

## 5. Bounds and rotation

* Per-file cap: `SAKURA_DIAG_MAX_BYTES` (default **262144** = 256 KiB).
* Rotations: `SAKURA_DIAG_MAX_ROTATIONS` (default **3**) → at most 4 files per
  log, so roughly 1 MiB per log and a few MiB total.
* A record can push a rotated file slightly past the cap; the test asserts the
  bound stays within one record.
* The GUI viewer (`cat_file`) refuses files over 1.5 MiB, so a 256 KiB cap has
  a 6x margin.
* Watch loop: `SAKURA_DIAG_WATCH_ITERATIONS` × `SAKURA_DIAG_WATCH_INTERVAL`
  (default 18 × 5 s = 90 s), and it exits early when `pidof recovery` shows the
  GUI is up. It never waits indefinitely on a service.

## 6. Severity model (no false alarms)

| Source | ERROR | WARN |
|---|---|---|
| kernel (`dmesg`) | panic, BUG, Oops, call trace, I/O error, EXT4/F2FS errors, mmc error/timeout | `avc: denied` (recovery is permissive, so these are expected) |
| logcat | lines with ` E `/` F ` (threadtime) or `E/`/`F/`, `FATAL EXCEPTION` | none |
| services | `failed`/`crashed`/`restarting`; a **required** service `stopped`, empty or `not-declared` **after the first pass** | — |

`REQUIRED_SERVICES = qseecomd, vendor.keymaster-3-0, vendor.gatekeeper-1-0`.
`OPTIONAL_SERVICES` is empty by design. An unknown or optional HAL that is
stopped is listed in `services.txt` but **never** raises the badge, which is the
rule "do not show a false error just because an optional service is
unavailable". Missing TEE binaries are additionally reported as an explicit
`TEE binaries missing: …` warning, because that is the common real cause.

**First-pass rule (BUG-9).** The first snapshot runs at `late-init`, before
`on boot` starts the TEE chain, so `init.svc.qseecomd` is legitimately empty at
that moment. Such a service is recorded as `pending; first pass` and is *not*
counted; only the second and later classifications treat it as an error.
Without this rule a healthy boot would show a red badge, which is the false
alarm the brief forbids. `failed`/`crashed`/`restarting` are always errors.
Regression tests: `test_preboot_pending_service_is_not_an_error`,
`test_later_pass_reports_missing_service`.

## 7. GUI integration

The feature is a **theme patch against the pinned `bootable/recovery`**, not a
C++ fork. Every action it uses already exists at `8d2aad19`:

* `cmd` — run a shell command in a worker thread;
* `set` — store a GUI variable;
* `page` — switch page;
* `cat_file` — render a file into a scrollable textbox via `of_file_to_read`
  (`gui/listbox.cpp`, 1.5 MiB limit);
* `property.<name>` — `DataManager::GetValue()` resolves Android properties, so
  `<condition var1="property.of.boot_diag_errors" …>` reads what the collector
  sets with `setprop`.

### Settings → Error Logs

Entries: recovery.log, boot/init diagnostics, errors-only, dmesg, logcat,
service status, mounts/encryption, generate report, export, clear (with a
confirmation page). Clearing never deletes `/tmp/recovery.log`; it removes only
the collector's files.

### Status-bar badge

A small `! DIAG` text badge appears only when `of.boot_diag_errors` is non-zero
and opens the Error Logs page. An emoji glyph (🪲) is not used because the
OrangeFox fonts do not guarantee emoji coverage; a missing glyph would render as
a blank box, which is worse than a text badge.

Badge placement is fixed at x=756..926, y=8..72 (1080 px wide). With the sakura
layout (`OF_STATUS_H=95`, `OF_STATUS_INDENT_*` 50) this sits between the centre
clock and the battery. If a future theme moves those, the coordinates must be
adjusted in the patch.

**Refresh semantics (honest limitation):** a `<condition>` is evaluated when the
page renders. The collector sets the property before the GUI starts, so the
badge is correct on first paint. If an error is only discovered later while a
page is already displayed, the badge appears on the next page load; it does not
force a redraw.

## 8. Redaction

Applied by `redact()`:

* `password|passwd|passphrase|pincode|pin|pattern|token|secret|credential|keystore_password`
  followed by `=`/`:` and a value → `<redacted>`;
* `ro.serialno`, `ro.boot.serialno`, `serial`, `imei`, `meid` values;
* MAC addresses, 15-digit IMEIs;
* keymaster/gatekeeper key material.

`logcat.txt` and `dmesg.txt` are redacted **at collection time**, because the
GUI viewer shows them directly. The report is redacted again before writing.
Device identity (model, device, build, crypto state) is intentionally kept.
`/tmp/recovery.log` is TWRP's own log and is not rewritten; it is shown as-is by
the viewer.

## 9. Retrieval when the GUI never starts

This is the case the design is built around. Use adb:

```bash
adb devices
adb shell cat /tmp/sakura-diag/boot-diag.txt
adb shell cat /tmp/sakura-diag/errors.txt
adb pull /tmp/sakura-diag
```

`adbd` starts from `on property:sys.usb.config=adb`; `init.recovery.qcom.rc`
sets that at `on init`, so ADB normally comes up even when the GUI does not. If
ADB is also unavailable, reboot into recovery again and pull the mirror
(`/cache/recovery/sakura-diag/`) **if** `/cache` was writable during the failed
boot; otherwise the tmpfs copy is gone with the reboot — that is stated plainly
rather than papered over.

## 10. Tests and what they do not prove

`python3 -m unittest discover -s tests -v` covers:

* collector syntax/executable bit and the no-`/data` rule;
* error counting from kernel, threadtime logcat and service state;
* optional/unknown stopped services never counted;
* rotation count and size bounds;
* redaction in both the report and the viewer's logcat copy;
* report sections and real counters;
* missing storage failing cleanly;
* `clear` refusing without `--yes`;
* export to a writable cache and graceful tmpfs-only fallback;
* bounded `boot` supervisor;
* patch apply/check/idempotency/context-change/revision-mismatch;
* the patched theme passing `tools/check_theme.py` with strict targets.

They use **synthetic fixtures**, not sakura hardware. They do not prove that
the GUI renders, that the badge is visible, or that `setprop`/`getprop` behave
on the device. Those are hardware-test items (`testing/android-*/TEST_RECORD.md`,
"diagnostics" rows).

## 11. Tester procedure

1. Boot the built recovery with `adb` connected.
2. `adb shell cat /tmp/sakura-diag/boot-diag.txt` — expect
   `diagnostic collector started` and `first snapshot done`.
3. Open Settings → Error Logs; open each viewer once.
4. Generate a report and export; `adb pull /cache/recovery/sakura-diag` if
   `/cache` is mounted.
5. Deliberately test the failure path: boot with encrypted `/data` without the
   TEE blobs and confirm the badge appears and the logs name the missing
   binaries.
6. Record all of it in the generation's `TEST_RECORD.md`. A feature is not
   "tested" until that record contains observed results.
