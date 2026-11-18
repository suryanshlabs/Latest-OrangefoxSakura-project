# Android 11 — test record

> **Untested.** This file records research context only. Until it is filled with
> **observed** device results, Android 11 is **not** supported/tested by this
> port. Do not copy it into a release note as if it were a pass. Synthetic
> fixtures used in unit tests are **not** real sakura firmware tests.

## ROM under test (research context — not a tested run)

| Field | Value |
|---|---|
| ROM name (representative) | crDroid 7.9 (Android 11, historical, ~2021-08) — representative; not tested |
| ROM source / evidence URL | crDroid/XDA historical; xiaomi-msm8953-devs/android_device_xiaomi_msm8953-common@lineage-18.1 rootdir/etc/fstab.qcom inspected |
| Android version / build id | Android 11 (exact build not re-verified here) |
| Device tree + commit | msm8953-common lineage-18.1 (common tree evidence) |
| Kernel + commit | Not inspected here |
| Encryption method (observed/expected) | Common LOS18.1 fstab shows encryptable=footer,quota (no fileencryption, no metadata flags). Exact crDroid 7.9 sakura on-disk format not re-verified from ROM image. |
| Vendor/firmware base | Unknown per-ROM; genuine sakura blobs not supplied (0/20) |

**Research note:** Research: footer-style evidence in common LOS18.1 fstab; per-ROM format unconfirmed.

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
| **Diagnostics** (badge, Error Logs viewers, filters, copy, export, clear) | not tested | requires a booted image; logic is covered by tests/test_diag.py + tests/test_patches.py |
| **Metadata encryption opt-in** (`SAKURA_METADATA_ENCRYPTION=1`) | not tested, and **cannot work on this kernel** | no `dm-default-key` in either kernel; configuration is covered by tests/test_metadata.py |
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
