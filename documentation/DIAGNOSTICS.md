# Boot diagnostics and Error Logs

Status: **implemented in source, unit-tested off-device (74 tests), NOT
seen on a device.** No production image has been built in this environment and
no recovery has been booted. Everything below describes what the code does; §11
lists exactly what remains unverified.

## 1. Why this exists

The failure mode that matters most on this port is a recovery that never reaches
the GUI: a missing TEE binary, a bad `on boot` service, an unmountable `/data`.
In that state the only classic evidence was `/tmp/recovery.log`, which a tester
had to know to pull. The diagnostic system records the same boot from init
onwards, tags every line with a timestamp, component and severity, and keeps the
result where adbd can always reach it.

It is **not** a decryption feature. It reports; it never changes an encryption
decision.

## 2. Components

| Component | Path | Role |
|---|---|---|
| Collector | `device/xiaomi/sakura/recovery/root/system/bin/sakura-diag` | Shell script: snapshot, classify, report, export, copy, clear, status |
| Init service | `recovery/root/init.recovery.sakura_diag.rc` | Badge defaults + `oneshot` service started at `on late-init` |
| Import | `recovery/root/init.recovery.qcom.rc` | `import /init.recovery.sakura_diag.rc` |
| GUI patch | `patches/0001-theme-sakura-diagnostics.patch` | Settings → Error Logs, viewers/filters, copy, export, clear, `! DIAG` badge |
| Applicator | `build/apply_patches.sh` | Pinned, fail-closed, idempotent |
| Validator | `tools/check_theme.py` | Pages, actions, includes, string references, page targets |
| Tests | `tests/test_diag.py` (28), `tests/test_patches.py` (7), `tests/test_metadata.py` (10) | Logic, privacy, mount states, state persistence, patch behaviour |

## 3. Boot ordering

```
early-init -> init -> late-init
                       |-- sakura_diag starts (device rc `on late-init` is queued
                       |                        before init.rc's own late-init
                       |                        because the device rc is imported
                       |                        at the top of init.rc)
                       |-- early-fs -> fs -> post-fs -> post-fs-data -> early-boot
                       `-- boot   (class_start default -> GUI;
                                   init.recovery.qcom_decrypt.rc: start qseecomd)
```

`start sakura_diag` is a **service**, not `exec`: init forks it and continues
immediately, so a slow collector can never delay the boot. The first snapshot and
its `setprop` therefore happen before `gui_init()`.

The rc also sets the badge defaults with init's own `setprop` builtin
(`of.boot_diag_errors 0`, …) before the service starts, so an unset property can
never be compared as an empty string and show a false badge.

## 4. Where logs live (and what is never touched)

| Location | When | Survives reboot | Notes |
|---|---|---|---|
| `/tmp/sakura-diag/` | always | no | tmpfs, root-only (`0750`), readable over adbd. Primary store. |
| `/cache/recovery/sakura-diag/` | only when `/proc/mounts` proves `/cache` is a mounted, read-write, non-ramdisk filesystem | yes | `/cache` is **its own ext4 partition** (`by-name/cache -> /cache` in `recovery.fstab`), not a directory inside `/data`. The collector never mounts it and writes nothing when it is absent, read-only or ramdisk-backed. |
| `/sdcard/Fox/diag/` | export/copy only, and only when internal storage is already writable | yes | convenience copy; never required |

The collector never mounts, formats or writes to `/data`, `/metadata` or any
other partition. `tests/test_diag.py` asserts the script contains no `/data`
write, no `mkfs` and no `rm -rf /data`, and that the old “cache lives in /data” claim is
gone from both code and documentation.

### 4.1 How the mount question is answered

`mount_lookup()` reads `/proc/mounts` (overridable for tests), decodes `\040`,
and returns the **longest mount point that contains the path**, plus its fstype
and options. `cache_state()` then returns one of:

| State | Meaning | Behaviour |
|---|---|---|
| `unmounted` | only `/` matches, or nothing matches | nothing created |
| `not-persistent` | matches a `tmpfs`/`rootfs`/`ramfs` mount | nothing created (a ramdisk directory is not a persistent copy) |
| `read-only` | mounted but options contain `ro` | nothing created |
| `unwritable` | mounted `rw` but the write test fails | reported |
| `rw` | mounted `rw`, real filesystem, write test passed | mirror/copy allowed |
| `disabled` | `SAKURA_DIAG_NO_MIRROR=1` (tests) | nothing created |

The write test only runs **after** the mount checks, so the collector can never
mistake a directory in the ramdisk for persistent storage.

## 5. Files, bounds and rotation

```
boot-diag.txt          timestamped collector/init/component trail (rotated)
dmesg.txt              kernel log snapshot (redacted)
logcat.txt             logcat threadtime snapshot (redacted)
recovery-log.txt       sanitized, size-capped copy of /tmp/recovery.log
services.txt           init.svc.* states + declared-but-missing required services
mounts.txt             /proc/mounts snapshot
props.txt              allow-listed properties, sensitive names removed
encryption.txt         crypto properties, /data + /metadata + dm mounts, cache state
errors.txt             critical only
warnings.txt           recoverable (avc, mmc timeouts, benign tags)
triage.txt             unclassified logcat E/F lines (kept, not counted)
crypto-errors.txt      TEE / crypto / mount filter across the above
state                  counters, boot stage, classification pass, crypto mode
report.txt             newest redacted report (stable name for the GUI)
Sakura-Diagnostic-Report-<timestamp>.txt
```

* Per-file cap: `SAKURA_DIAG_MAX_BYTES` (default **262144** = 256 KiB).
* Rotations: `SAKURA_DIAG_MAX_ROTATIONS` (default **3**) → at most 4 files per
  log, roughly 1 MiB per log.
* The GUI viewer refuses files over 1.5 MiB, so a 256 KiB cap has a 6× margin.
* Watch loop: `SAKURA_DIAG_WATCH_ITERATIONS` × `SAKURA_DIAG_WATCH_INTERVAL`
  (default 18 × 5 s = 90 s). It never waits on a service without a bound.

## 6. Severity model (actionable errors only)

| Source | errors (critical) | warnings (recoverable) | triage (kept, not counted) |
|---|---|---|---|
| kernel | panic, Oops/BUG, unable-to-handle, call trace, EXT4/F2FS corruption, `blk_update_request`/`Buffer I/O` errors, `I/O error, dev` | `avc: denied`, `mmcN: error/timeout`, soft lockup | — |
| logcat | `FATAL EXCEPTION`, `Fatal signal`, `*** FATAL`, `E AndroidRuntime` | E/F lines whose tag is in `BENIGN_LOGCAT_TAGS` (audio, camera, wifi, thermal, …) | every other E/F line |
| services | required service `failed`/`crashed`; required service absent **after the grace period** | `restarting` | required service absent **within** the grace period; required services in crypto mode `none` |

* `REQUIRED_SERVICES = qseecomd, vendor.keymaster-3-0, vendor.gatekeeper-1-0`.
* `OPTIONAL_SERVICES` is empty by design: an unknown HAL that is stopped is
  listed in `services.txt` and **never** raises the badge.
* **Grace period** (`SAKURA_DIAG_SERVICE_GRACE`, default 2 passes): the first
  snapshot runs at late-init, before `on boot` starts the TEE chain, so an empty
  `init.svc.*` there is "not started yet", not a failure. This removes the false
  badge that BUG-9 described without hiding a real failure: by the second pass a
  missing required service is an error.
* **Unknown messages are never discarded.** They stay in the raw logs and in
  `triage.txt`; they simply do not become confirmed failures, which is what the
  brief requires.
* Missing TEE binaries (full mode) add an explicit warning naming them, because
  that is the most common real cause on a 0/20-blob port.

## 7. Report state survives a new shell

`report` is invoked by the GUI (`cmd /system/bin/sakura-diag report`) as a **new
process**, so shell variables from the boot supervisor do not exist there.
Without help it printed `errors: 0`, reset the service classification to its
first pass and reported `boot stage: unknown` (BUG-8).

The collector therefore writes `state` (`boot_stage`, `classify_pass`,
`errors`, `warnings`, `triage`, `service_errors`, `crypto_mode`, `updated`)
atomically on every classification and stage change. `report` **loads** that
file and never recomputes history; only an empty diagnostic directory triggers a
one-shot collection. Report generation cannot clear or change established
counters (`test_report_does_not_reclassify_or_reset`).

## 8. Crypto build modes

`build/build.sh` writes `device/xiaomi/sakura/crypto_mode.mk` (gitignored) with
`ro.sakura.crypto.mode=full|none` and the fragment is included by `device.mk`.

* `full` (default): the TEE chain is required. Missing/stopped qseecomd,
  Keymaster or Gatekeeper past the grace period is an **error**.
* `none` (`SAKURA_ALLOW_MISSING_CRYPTO=1`): the image has no TEE chain, so those
  services are expected to be absent. They are listed in `triage.txt` as
  `(not required: crypto mode none)` and never raise the badge. The normal
  production gate is untouched: `build/check_crypto_blobs.sh --require` still
  refuses a crypto build without blobs.

`build/verify_image.sh` fails an image with no `ro.sakura.crypto.mode`, and
fails an image that claims `mode=none` while being verified with
`--require-crypto`.

## 9. GUI (Settings → Error Logs)

Pure theme XML; every action exists in the pinned `bootable/recovery`:

* `cmd` — worker thread; `set`; `page`; `reload`;
* `property.<name>` — `DataManager::GetValue()` resolves Android properties
  (`data.cpp:442/523`), so `%property.of.…%` and
  `<condition var1="property.of.…">` read the collector's `setprop` values;
* `fileexists` — stat-based condition (used to hide "View report" until it is
  generated);
* a listbox with `<data name="of_file_to_read"/>` renders a file
  (`gui/listbox.cpp:340`, 1.5 MiB limit).

| # | Required feature | Where |
|---|---|---|
| 1 | recovery log | "Recovery log (sanitized copy)" → `recovery-log.txt` |
| 2 | boot/init log | `boot-diag.txt` |
| 3 | kernel dmesg | `dmesg.txt` |
| 4 | logcat | `logcat.txt` |
| 5 | service status | `services.txt` |
| 6 | mount status | `mounts.txt` (previously missing: the old entry opened `encryption.txt` only) |
| 7 | encryption diagnostics | `encryption.txt` |
| 8 | errors and warnings | `errors.txt` + `warnings.txt` |
| 9 | filter/search | filtered views: errors, warnings, unclassified, TEE/crypto (`crypto-errors.txt`). Free-text search is **not** a theme capability; filters are pre-rendered by the collector |
| 10 | copy selected logs | "Copy logs" page → `sakura-diag copy <log>` (11 targets) |
| 11 | export redacted report | "Generate diagnostic report" + "Export all logs" |
| 12 | clear copies after confirmation | "Clear diagnostic logs" → confirmation page → `clear --yes` |

The viewer is a dedicated page (`diag_view`) with the same textbox mechanism as
the stock `cat_file` page, but back returns to Error Logs and the file variable is
released on exit.

**Clear semantics.** `clear --yes` deletes this session's files in
`/tmp/sakura-diag`, the `/cache/recovery/sakura-diag` mirror and
`/sdcard/Fox/diag` — and nothing else (a test asserts an unrelated file in the
same directory survives). It never touches `/data`, any partition, or
`/tmp/recovery.log`.

### Badge

A `! DIAG` text badge appears only when `of.boot_diag_errors` is non-zero and
opens Error Logs. No emoji glyph is used (the OrangeFox fonts do not guarantee
emoji coverage). Placement is fixed at x=746…926, y=8…72 (1080 px wide).

**Honest limitations:**

* a `<condition>` is evaluated when the page renders; the badge is correct on
  first paint because the collector runs before the GUI, but it is **not a live
  indicator** and does not force a redraw;
* "the badge is visible/tappable" is unverified on hardware — see §11.

## 10. Redaction and privacy

Two independent layers:

1. **Collection-time filtering of properties.** `props.txt` is built from an
   allow-list of prefixes (`ro.product`, `ro.build`, `ro.hardware`, `ro.crypto`,
   `ro.sakura`, `init.svc`, `sys.usb`, `twrp.`, `of.`, `metadata.`, `fbe.`, …)
   *and* a block-list of sensitive names (`serialno|serial|imei|meid|macaddr|
   btmac|wifi*mac|android_id|oem_id|token|secret|password|passwd|pincode|
   pattern|keystore|keymaster|widevine|drm*id`). The raw value never enters the
   diagnostic directory, so it cannot leak through `/cache`, `/sdcard`, the GUI
   viewers or a report bundle. The report no longer prints a serial line at all.
2. **`redact()` on everything shareable.** It handles both `key=value` and the
   real `[ro.boot.serialno]: [value]` getprop shape, credentials
   (password/passwd/passphrase/pin/pincode/pattern/token/secret/credential/
   keystore/keymaster), MAC addresses, 15-digit IMEI/MEID and the device's own
   serial/IMEI **by value** (so a bare occurrence with no key name is still
   removed). Exported files are written by `copy_redacted()`, which re-runs
   `redact()` on the way out.

`dmesg.txt`, `logcat.txt` and `recovery-log.txt` are redacted **at collection
time** because the GUI shows them directly. `/tmp/recovery.log` is never
modified and is never copied verbatim: the GUI shows `recovery-log.txt`, a
sanitized, size-capped copy.

Regression tests: real bracket syntax, credential/serial/IMEI/MAC redaction in
the report, in every viewer file and in every exported copy, props filtering, and
a byte-level check that the original recovery.log is untouched.

## 11. Retrieval when the GUI never starts

```bash
adb devices
adb shell cat /tmp/sakura-diag/boot-diag.txt
adb shell cat /tmp/sakura-diag/errors.txt
adb pull /tmp/sakura-diag
```

`adbd` starts from `on property:sys.usb.config=adb`; `init.recovery.qcom.rc`
sets that at `on init`, so ADB normally comes up even when the GUI does not. If
ADB is unavailable too, the tmpfs copy is gone with the reboot; the `/cache`
mirror survives **only if** `/cache` was mounted read-write during the failed
boot. That is stated plainly rather than papered over.

## 12. Boot monitor (bounded, evidence-based)

The watch loop records stages derived from what exists in the pinned source:

| Stage | Evidence |
|---|---|
| `early-boot` | collector running |
| `services-ready` | every required `init.svc.*` is `running` |
| `decrypt-pending` | `ro.crypto.state=encrypted` and no `/data` mount yet |
| `data-ready` | `/data` appears in `/proc/mounts`, or `twrp.decrypt.done=true` (set by `partitionmanager.cpp:2186` after a successful decrypt) |
| `gui-process-up` | `pidof recovery` succeeds |
| `monitor-timeout` | the bounded watch finished without either settling |

`pidof recovery` only proves the GUI **process** exists: the pinned GUI keeps its
"rendered" state in `DataManager` (`tw_gui_done`), which init cannot read. The
collector therefore reports `gui-process-up`, never "the GUI rendered". The loop
stops early only when the GUI process is up **and** the data/decryption state is
settled; otherwise it stops at the iteration bound. Every transition is written
to `boot-diag.txt` and to `state`.

## 13. Tests and what they do not prove

`python3 -m unittest discover -s tests -v` currently runs **74 tests**, of which
56 cover diagnostics, patches, metadata configuration and theme inputs. They use synthetic
fixtures (props/dmesg/logcat/mounts files, a fake mounted `/cache`, a fake
`sdcard` root), never sakura hardware.

They do **not** prove that: the GUI renders, the badge is visible or tappable,
`setprop`/`getprop` behave on the device, `/proc/mounts` looks like the fixtures,
the /cache partition is formatted/ext4 as assumed, or that ADB comes up. Those are
hardware-test items (`testing/android-*/TEST_RECORD.md`, "Diagnostics" row).

## 14. Tester procedure

1. Boot the built recovery with `adb` connected.
2. `adb shell cat /tmp/sakura-diag/boot-diag.txt` — expect `diagnostic collector
   started`, `first snapshot done` and at least one `stage:` line.
3. `adb shell cat /tmp/sakura-diag/state` — expect a non-empty `boot_stage`.
4. Open Settings → Error Logs; open each viewer once, generate a report, copy one
   log, export, then clear and confirm.
5. Check the badge appears only when `of.boot_diag_errors > 0`.
6. Test the failure path: boot with encrypted `/data` and no TEE blobs; confirm
   the badge appears and `errors.txt`/`warnings.txt` name the missing binaries.
7. Record all of it in the generation's `TEST_RECORD.md`. A feature is not
   "tested" until that record contains observed results.
