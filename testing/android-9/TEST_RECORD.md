# Android 9 — test record

> **Untested.** This file records research context only. Until it is filled with
> **observed** device results, Android 9 is **not** supported/tested by this
> port. Do not copy it into a release note as if it were a pass. Synthetic
> fixtures used in unit tests are **not** real sakura firmware tests.

## ROM under test (research context — not a tested run)

| Field | Value |
|---|---|
| ROM name (representative) | MIUI 12 Android 9 stock (e.g. V12.0.4.0.PDMMIXM global / V12.0.1.0.PDICNXM China) — representative, not tested here |
| ROM source / evidence URL | Official MIUI fastboot packages (not present in workspace); stock-era TWRP: TeamWin/android_device_xiaomi_sakura@android-8.1 twrp.fstab |
| Android version / build id | Android 9 / MIUI 12 PD* (not verified from image here) |
| Device tree + commit | Stock-era; not fetched for this record |
| Kernel + commit | sakura-o-oss / sakura-p-oss in MiCode Xiaomi_Kernel_OpenSource (not inspected in detail here) |
| Encryption method (observed/expected) | Legacy FDE (encryptable=footer) in stock/TWRP evidence; no metadata encryption declared in inspected sources |
| Vendor/firmware base | sakura Android 9 vendor/firmware (KM3.0/GK1.0 era) — genuine blobs not supplied (0/20) |

**Research note:** Research: config intends footer/FDE path. Runtime unverified (no blobs/build/device test).

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
