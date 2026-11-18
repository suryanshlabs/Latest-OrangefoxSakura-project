# Android 13 — test record

> **Untested.** This file records research context only. Until it is filled with
> **observed** device results, Android 13 is **not** supported/tested by this
> port. Do not copy it into a release note as if it were a pass. Synthetic
> fixtures used in unit tests are **not** real sakura firmware tests.

## ROM under test (research context — not a tested run)

| Field | Value |
|---|---|
| ROM name (representative) | LineageOS 20-era sakura/daisy builds (representative) — not tested |
| ROM source / evidence URL | xiaomi-msm8953-devs/android_device_xiaomi_msm8953-common@lineage-20 rootdir/etc/fstab.qcom; xiaomi-msm8953-devs/android_device_xiaomi_sakura (unified with daisy) |
| Android version / build id | Android 13 / LOS 20 (exact build not tested) |
| Device tree + commit | msm8953-common lineage-20 (inspected) |
| Kernel + commit | Not inspected here |
| Encryption method (observed/expected) | fileencryption=ice,quota (f2fs+ext4), no metadata_encryption/keydirectory observed |
| Vendor/firmware base | Per-ROM; genuine sakura blobs not supplied (0/20) |

**Research note:** Research/source: fstab declares ice (vendor FSCRYPT_MODE_PRIVATE, v1-default context for first_api_level<=29). Match with actual userdata unproven; runtime unverified.

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
