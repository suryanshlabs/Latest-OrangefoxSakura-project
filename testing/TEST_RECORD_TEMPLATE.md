# Android N — test record

> **Untested.** This file is a template. Until it is filled with observed
> results, this Android version is **not** supported by this port. Do not copy
> it into a release note as if it were a pass.

## ROM under test

| Field | Value |
|---|---|
| ROM name | _(fill in)_ |
| ROM source URL | _(fill in)_ |
| Android version / build id | _(e.g. 15 / AP4A.…)_ |
| Device tree + commit | _(fill in)_ |
| Kernel + commit | _(fill in)_ |
| Encryption method | _(FDE footer / FBE / FBE+metadata / none)_ |
| Vendor/firmware base | _(e.g. V12.0.1.0.PDICNXM)_ |

## Results

| Test | Result | Notes |
|---|---|---|
| Recovery boots | not tested | |
| Device detection (sakura, not daisy) | not tested | |
| Display / brightness | not tested | |
| Touchscreen | not tested | |
| ADB | not tested | |
| MTP | not tested | |
| USB OTG | not tested | |
| Internal storage mounts | not tested | |
| External storage (microSD) | not tested | |
| Partitions detected correctly | not tested | |
| **Diagnostics** (badge, Error Logs viewers, filters, copy, export, clear) | not tested | requires a booted image; logic is covered by tests/test_diag.py + tests/test_patches.py |
| **Metadata encryption opt-in** (`SAKURA_METADATA_ENCRYPTION=1`) | not tested, and **cannot work on this kernel** | no `dm-default-key` in either kernel; configuration is covered by tests/test_metadata.py |
| **Decryption** | not tested | record the exact prompt or error |
| Backup | not tested | |
| Restore | not tested | |
| ZIP installation | not tested | |
| ADB sideload | not tested | |
| Magisk install / patch | not tested | |
| OrangeFox themes / gestures | not tested | |
| Reboot functions | not tested | |

## Status

**Research only** — no build and no device test has been performed for this
Android version.

Allowed values: Research only · Source verified · Build verified · Boot tested ·
Feature tested · Decryption tested · Fully validated.

## Logs

Attach `recovery.log`, `dmesg` and photos of failures. A claim without a log is
not a test result.
