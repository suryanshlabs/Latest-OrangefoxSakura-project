# Android 15 — test record

> **Untested.** This file records research context only. Until it is filled with
> **observed** device results, Android 15 is **not** supported/tested by this
> port. Do not copy it into a release note as if it were a pass. Synthetic
> fixtures used in unit tests are **not** real sakura firmware tests.

## ROM under test (research context — not a tested run)

| Field | Value |
|---|---|
| ROM name (representative) | LineageOS 22.2 for sakura (XDA, unified with daisy) — representative, not tested |
| ROM source / evidence URL | xiaomi-msm8953-devs/android_device_xiaomi_daisy@lineage-22.0/22.1/22.2 rootdir/etc/fstab.qcom (sakura unified); XDA lineage-22.2 thread notes "FBE build, don't use twrp for these builds" |
| Android version / build id | Android 15 / LOS 22.x (exact build not tested) |
| Device tree + commit | daisy lineage-22.x (inspected, sakura partitions conditional) |
| Kernel + commit | Not inspected here |
| Encryption method (observed/expected) | fileencryption=ice,quota (f2fs) / fileencryption=ice,quota,formattable (ext4), no metadata_encryption/keydirectory observed |
| Vendor/firmware base | Per-ROM; genuine sakura blobs not supplied (0/20) |

**Research note:** Research/source: fstab flags match ice form; ROM upstream discourages TWRP. Runtime unverified.

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
