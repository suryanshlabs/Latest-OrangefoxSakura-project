# Android 12 — test record

> **Untested.** This file records research context only. Until it is filled with
> **observed** device results, Android 12 is **not** supported/tested by this
> port. Do not copy it into a release note as if it were a pass. Synthetic
> fixtures used in unit tests are **not** real sakura firmware tests.

## ROM under test (research context — not a tested run)

| Field | Value |
|---|---|
| ROM name (representative) | No confirmed sakura Android 12 ROM/fstab identified in this audit |
| ROM source / evidence URL | lineage-19 branch not present in checked xiaomi-msm8953-devs common/daisy trees |
| Android version / build id | Android 12 (unknown) |
| Device tree + commit | Not found |
| Kernel + commit | Not found |
| Encryption method (observed/expected) | Unknown from inspected sakura sources |
| Vendor/firmware base | Unknown; genuine sakura blobs not supplied (0/20) |

**Research note:** Research only: no sakura A12 fstab evidence located here.

## Results

| Test | Result | Notes |
|---|---|---|
| Recovery boots | not tested |  |
| Device detection (sakura, not daisy) | not tested |  |
| Display / brightness | not tested |  |
| Touchscreen | not tested |  |
| ADB | not tested |  |
| MTP | not tested |  |
| USB OTG | not tested |  |
| Internal storage mounts | not tested |  |
| External storage (microSD) | not tested |  |
| Partitions detected correctly | not tested |  |
| **Diagnostics** (badge, Error Logs viewers, report/export) | not tested | requires a booted image; logic is covered by tests/test_diag.py |
| **Decryption** | not tested | requires genuine sakura blobs (0/20 present), built/verified image, matching on-disk format, and device evidence |
| Backup | not tested |  |
| Restore | not tested |  |
| ZIP installation | not tested |  |
| ADB sideload | not tested |  |
| Magisk install / patch | not tested |  |
| OrangeFox themes / gestures | not tested |  |
| Reboot functions | not tested |  |

## Status

**Research only** — no build and no device test has been performed for this
Android version. Current recovery config: `encryptable=footer,fileencryption=ice`,
no `metadata_encryption`; decryption **unverified**.

Allowed values: Research only · Source verified · Build verified · Boot tested ·
Feature tested · Decryption tested · Fully validated.

## Logs

Attach `recovery.log`, `dmesg` and photos of failures. A claim without a log is
not a test result.
