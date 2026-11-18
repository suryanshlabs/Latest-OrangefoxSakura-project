# Android 14 — test record

> **Untested.** This file records research context only. Until it is filled with
> **observed** device results, Android 14 is **not** supported/tested by this
> port. Do not copy it into a release note as if it were a pass. Synthetic
> fixtures used in unit tests are **not** real sakura firmware tests.

## ROM under test (research context — not a tested run)

| Field | Value |
|---|---|
| ROM name (representative) | LineageOS 21-era / A14 sakura builds (representative; some A14 ROMs reported historically) — not tested |
| ROM source / evidence URL | xiaomi-msm8953-devs/android_device_xiaomi_msm8953-common@lineage-21 rootdir/etc/fstab.qcom inspected; other A14 sakura ROM fstabs not fetched here |
| Android version / build id | Android 14 (unknown/representative) |
| Device tree + commit | msm8953-common lineage-21 (inspected) |
| Kernel + commit | Not inspected here |
| Encryption method (observed/expected) | Common LOS21 fstab: fileencryption=ice,quota, no metadata_encryption/keydirectory. Other A14 ROM formats unconfirmed. |
| Vendor/firmware base | Per-ROM; genuine sakura blobs not supplied (0/20) |

**Research note:** Research/source for common tree; per-ROM format/runtime unverified.

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
