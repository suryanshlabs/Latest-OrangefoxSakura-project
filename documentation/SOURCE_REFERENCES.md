# Source references

Every entry: repository, selected ref, exact commit, applicability, why chosen,
sakura-compatibility evidence, and required modifications.

Status legend: **VERIFIED** = ref/SHA resolved by me; **INSPECTED** = files read;
**UNPROVEN** = claim not yet validated.

## A. OrangeFox / build system

### A1. Sync tooling — VERIFIED, INSPECTED
* URL: https://gitlab.com/OrangeFox/sync — branch `master`
* Commit: `73d4d94e0d1b11b9035dea72ee223d25b1fefa7c`
* `orangefox_sync.sh` SCRIPT_VERSION `20261107`, `FOX_BASE_VERSION="R12.0"`
* Why: authoritative source of branch names, minimal manifest and patch steps.
* Modification: none (read-only). The script is used unmodified; this project
  only pins it.

### A2. Build manifest — VERIFIED
* URL: https://github.com/minimal-manifest-twrp/platform_manifest_twrp_aosp
* Branch `twrp-12.1`, commit `6dc117d9cbd08430daa16db2013560e1c4017fa8`
* Android applicability: AOSP 12.1 base for TWRP/OrangeFox recovery builds.
* Why: this is exactly what `do_fox_121()` initialises.
* Sakura evidence: n/a (base tree), but it is what the R11 successor builds use.

### A3. OrangeFox recovery sources — VERIFIED
* URL: https://gitlab.com/OrangeFox/bootable/Recovery.git
* Branch `fox_12.1`, commit `8d2aad19deb158e935d70ca5b648162c2b2831ee`
* Why: the R12.0 UI/feature set (Fox themes, SVG icons, gesture nav, file
  manager, terminal, Magisk patching, OTA tooling).
* Note: cloned by `clone_fox_recovery()` with `-b fox_12.1`.

### A4. OrangeFox vendor tree — VERIFIED
* URL: https://gitlab.com/OrangeFox/vendor/recovery.git
* Branch `main`, commit `1998cfcaca9bb247ea20d587e565676faa281de9`
  (script default since sync v029 — "unified main branch")
* Legacy alternative: branch `fox_12.1`, commit
  `fbe4d49c96acace3802c53c12cad0a62903c381f`
* Supplies `vendor/recovery/config/common.mk` behaviour, `qcom_decrypt`,
  `qcom_decrypt_fbe`, MagiskBoot assets and the Fox installer.
* Modification: none, but note that the *device* product makefile must inherit
  the OrangeFox common config supplied by this tree (see `device/`).

## B. Device trees

### B1. `msm8953E/device_xiaomi_sakura_twrp` @ `ofx-12.1` — VERIFIED, INSPECTED, **selected base**
* URL: https://github.com/msm8953E/device_xiaomi_sakura_twrp
* Branch `ofx-12.1`, commit `7fde3f4faa61493b93fe9ade84a5e705d359c8a3`
* 75 entries; includes `BoardConfig.mk`, `device.mk`, `fox_sakura.mk`,
  `twrp_sakura.mk`, `vendorsetup.sh`, `recovery/root/**`, `prebuilt/Image.gz-dtb`,
  `proprietary-files.txt`, `init/init_sakura.cpp` (Soong `libinit_sakura`), CI.
* Why selected: it is the **only** public tree explicitly written for
  **OrangeFox 12.1 on sakura**, it already carries the R12-era crypto stack
  (`qcom_decrypt`, `qcom_decrypt_fbe`, Keymaster 3.0 HIDL + `keystore.msm8953`),
  a working `Image.gz-dtb`, and the correct sakura cmdline.
* Sakura evidence: filenames + `FOX_RECOVERY_INSTALL_PARTITION="/dev/block/mmcblk0p49"`,
  `OF_TARGET_DEVICES`-equivalent `FDEVICE="sakura"`, `BOARD_KERNEL_BASE`
  `0x80000000`, page size 2048, `7824900.sdhci` bootdevice, `OF_DEFAULT_KEYMASTER_VERSION := 3.0`.
* Known defects found (fixed in `device/`):
  1. `AndroidProducts.mk` declares only `twrp_sakura.mk`; `fox_sakura.mk` is
     never referenced, and `twrp_sakura.mk` inherits `vendor/twrp/config/common.mk`
     (TWRP), so an OrangeFox build is not actually wired up.
  2. `OF_FBE_METADATA_MOUNT_IGNORE := 1` silently ignores metadata encryption.
  3. fstab has `/system` ext4 and `/system_root` in `twrp.flags` but no f2fs
     `/data` variant in the R12 fstab (only in twrp.flags' implied auto).
  4. `TARGET_PREBUILT_KERNEL` is an unattributed 2021 binary (see
     `KERNEL_ANALYSIS.md` §3).
* Branch `ofx-12.1_daisy` (`2659a2ab…`) is the **Mi A2 Lite** port and is
  excluded — see `DEVICE_COMPATIBILITY.md`.
* Branch `a12` (`024c8c7a…`) is the non-OrangeFox TWRP variant; superseded.

### B2. `msm8953E/device_xiaomi_sakura` @ `A15` — VERIFIED, INSPECTED (ROM reference)
* Branch `A15`, commit `3b4064b2c12d6fde36ac66179df829073bfd1fce`
  (`lineage-21` shares `3b4064b2…`; `A14` = `b3e1e351…`; `lineage-21`/`dxui-14` same)
* A full **ROM** tree (DroidX/LineageOS 22): `droidx_sakura.mk`, overlays,
  XiaomiParts-free, `BOARD_AVB_ENABLE := false`, `TARGET_KERNEL_SOURCE := kernel/xiaomi/msm8953`,
  `TARGET_KERNEL_CONFIG := msm8953-perf_defconfig xiaomi/xiaomi.config xiaomi/sakura.config`,
  `BOARD_KERNEL_IMAGE_NAME := Image.gz-dtb`, `BOARD_USES_FULL_RECOVERY_IMAGE := true`,
  `TARGET_USERIMAGES_USE_{EXT4,F2FS} := true`,
  `BOARD_{CACHE,VENDOR}IMAGE_FILE_SYSTEM_TYPE := ext4`.
* Why kept: authoritative statement of what sakura ROMs actually ship
  (fstab names, cmdline, kernel config, partition sizes) and evidence that
  **no dynamic partitions / no AVB** are in play.
* Not used directly: ROM-only components (audio HAL flags, overlays, RRO) must
  not be dragged into recovery.

### B3. `xiaomi-msm8953-devs/android_device_xiaomi_sakura` — VERIFIED
* `lineage-20` `07b169924223ee2b1dee44b27dcff029707e2cf7`
* `lineage-21` / `lineage-22.1` `ef872273a1d097893ecdf594cd46367cffbdbeac`
* `lineage-22.2` `d9fba6009b0787ca77f087974cf4e60abc9eada7`
* Newest (Android 15 / LineageOS 22.2) public sakura device tree; useful to
  confirm the *current* partition/encryption reality. Reference only.

### B4. `xiaomi-msm8953-devs/android_device_xiaomi_msm8953-common` — VERIFIED
* `lineage-22.2` `624551371f6d807349d6d013747ade1d9c643a20`
* `lineage-21` `4b27361aa46396fcb7a7ccdd8aab2e68b9d292fa`
* Common MSM8953 HAL/prop definitions. Recovery does not need the whole tree;
  it is a cross-check for vendor/init expectations.

### B5. `Sakura-Devices/device_xiaomi_sakura` @ `eleven` — VERIFIED, INSPECTED (rejected)
* Commit `3039417f8a790f4556fb55330b21e7de720da4eb`, last push 2021-08-10.
* LineageOS 18.1 **ROM** tree with `XiaomiParts` (KCAL, doze, dirac…), 524 entries.
* Rejected as a base: it is a ROM tree, has no `fox_*`/`twrp_*` product, and is
  two Android generations behind the device's current state. Retained as a
  historical reference for R11-era hardware behaviour (panel/touch/camera sets).

## C. Kernel

| URL | Branch | Commit | Decision |
|---|---|---|---|
| https://github.com/msm8953E/kernel_xiaomi_msm8953 | `lineage-21` | `52b67cb32ac009d366b632221d5fd381b6b7b55c` | **preferred source** for a from-source 4.9 build |
| same | `14` | `1e436c417f3e0d6fb32d6cfbc88ff7c3fc4cd7da` | alternative |
| https://github.com/ndrancs/kernel_xiaomi_sakura | `lineage-17.0` | `d452e25d01d7fcf2ba6a9dc3a92fb3fca0dd2503` | sakura-specific fallback |
| same | `lineage-16.0` / `-4.9` | `f069dcfe…` / `3cc13a0b…` | Android 9 era |
| https://github.com/mahajant99/kernel_xiaomi_msm8953 | `lineage-17.1` | `5b5dd1d44c454a5491b42ecff6aae06217c8e738` | alternative |
| https://github.com/MiCode/Xiaomi_Kernel_OpenSource | `sakura-p-oss`, `sakura-o-oss` | branch exists, exact commit **not found** | stock lineage reference only |

Verified defconfig paths on `msm8953E/kernel_xiaomi_msm8953` (both `lineage-21`
and `14`): `arch/arm64/configs/msm8953-perf_defconfig` (200),
`arch/arm64/configs/vendor/msm8953-perf_defconfig` (200),
`arch/arm64/configs/xiaomi/sakura.config` (200),
`arch/arm64/configs/vendor/xiaomi/sakura.config` (**404** — do not use).
`ndrancs/kernel_xiaomi_sakura` uses a single `arch/arm64/configs/sakura_defconfig`.

## D. Vendor / proprietary

| URL | Branch | Commit | Use |
|---|---|---|---|
| https://github.com/msm8953E/vendor_xiaomi_sakura | `14` | `352766707ce2eecccbdbf22e70f4df8dc96c7261` | device vendor makefiles (source-side) |
| https://github.com/msm8953E/vendor_xiaomi_msm8953-common | `14` | `07a8bcb535342abc666a002af88dc3d15b114b89` | common vendor makefiles |
| https://github.com/msm8953E/proprietary_vendor_xiaomi_msm8953-common | `lineage-22.1` | `29e3c1233edfaf048ebb2e772a5f2b6a6df906ce` | blob source for extraction |
| same | `lineage-22.0` | `bd8a4b872cf5cb27c1d5ce1070ea221ed8b19b31` | alternative |
| `lineage-21` | | `2c01c51d0447f2dddf9ae25fe23b0d3eec0d1d31` | alternative |

**Redistribution:** recovery needs only a handful of QTI crypto/keymaster
libraries, which are already committed as `recovery/root/**` prebuilts in the
selected tree. Those blobs remain Xiaomi/Qualcomm proprietary. This repository
does **not** add new proprietary binaries; it references the tree and provides
extraction instructions (`DEPENDENCIES.md`) so anyone can regenerate them from
their own device/dump. Licences are respected by reference, not republication.

## E. Similar-device caution

`daisy` (Mi A2 Lite) trees exist in the same repositories
(`ofx-12.1_daisy` = `2659a2abd3be9c336f61b7d705d09f0bd239daa`). Daisy differs in
partition layout and recovery install path; **nothing** from the daisy branch is
used here. See `DEVICE_COMPATIBILITY.md` §4.
