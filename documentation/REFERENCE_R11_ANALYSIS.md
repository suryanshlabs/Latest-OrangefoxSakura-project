# R11.0_5 reference recovery — reverse-engineering report

Analysis of the last official OrangeFox release for Xiaomi Redmi 6 Pro (`sakura`),
performed on the downloaded artifact. Every number below was produced by
inspecting the file, not copied from a changelog.

Tooling: `tools/bootimg.py` (written for this project, pure Python, no root, no
external packages — this environment has no `cpio`, `lz4`, Android Image Kitchen
or `unpackbootimg`).

## 1. Provenance and integrity

| Field | Value |
|---|---|
| Device page | https://orangefox.download/device/5f16bf6f48f6bf03a0fcbf35 |
| Release page | https://orangefox.download/release/6056efa3ee1435a74b093dd6 |
| Release ID | `6056efa3ee1435a74b093dd6` |
| Version / type | R11.0_5 / stable, variant `default` |
| Release date | 2021-03-21 (API `date` 1616310179) |
| Filename | `OrangeFox-sakura-stable@R11.0_5.zip` |
| Download URL | `https://dl.orangefox.download/6056efa3ee1435a74b093dd6` (API `mirrors.AR`) |
| Size | 46 500 245 bytes (API `size` = 46 500 245 — exact match) |
| MD5 (official) | `5dff190fe5e86631bd58c049a9b5f924` |
| MD5 (computed) | `5dff190fe5e86631bd58c049a9b5f924` — **verified match** |
| SHA-256 | `461e60c823bdc29343a0686ba774f62a775979e920676354d08e0c1735ae92e8` |
| Changelog (official) | "Sync with latest sources", "Switch to stock prebuilt kernel" |
| Device status now | "This device is not currently maintained" |
| Total downloads | 69 541 |

The API record also reports `recovery_img.size = 44 687 360` and
`recovery_img.md5 = e122a22c117f06f0e41f3c04d0d4baf2`. The extracted
`recovery.img` is exactly 44 687 360 bytes, so the image inside the ZIP is the
one OrangeFox recorded at release time.

## 2. ZIP structure (22 files, all inspected without executing anything)

```
META-INF/com/google/android/update-binary      18 549   installer (shell script)
META-INF/com/google/android/updater-script         70   stub comment only
META-INF/debug/default.prop                     2 950   build-time props (leak of build info)
META-INF/debug/fox_build_vars.txt               1 196   ** all OrangeFox build variables **
recovery.img                               44 687 360   Android boot image v0
sdcard/Fox/fox.bashrc                             704   shell profile installed to /sdcard/Fox
sdcard/Fox/FoxFiles/Magisk.zip              5 529 417   bundled Magisk
sdcard/Fox/FoxFiles/unrootmagisk.zip        2 694 251
sdcard/Fox/FoxFiles/OF_initd.zip            1 322 015
sdcard/Fox/FoxFiles/GoogleSans.zip          1 342 037   font
sdcard/Fox/FoxFiles/SubstratumRescue.zip      218 839
sdcard/Fox/FoxFiles/SubstratumRescue_Legacy.zip 218 847
sdcard/Fox/FoxFiles/PassReset.zip               3 172
INSTALL.txt                                       294
```

`updater-script` is deliberately empty ("see update-binary, which is a script"),
i.e. the installer is a hand-written shell script, not an edify package. Its
stored (uncompressed) CRC-32 is `04bb4f50`, SHA-256
`3b9bda80029e0b6699d41b47f6612335329aae62e82e9814dc7fdc87d60e246b`.

## 3. Recovered build configuration (`META-INF/debug/fox_build_vars.txt`)

This file is a complete dump of the build variables, so the R12 target can
reproduce the intended behaviour exactly instead of guessing:

```
FOX_DEVICE="sakura"          FOX_VERSION="R11.0_5"    FOX_BUILD_TYPE="Stable"
FOX_OUT_NAME="OrangeFox-R11.0_5-Stable-sakura"
OF_TARGET_DEVICES="sakura,sakura_india"
OF_SCREEN_H="2280"  OF_STATUS_H="90"  OF_STATUS_INDENT_LEFT="50"  RIGHT="50"
OF_USE_MAGISKBOOT="1"  OF_USE_NEW_MAGISKBOOT="1"  OF_USE_MAGISKBOOT_FOR_ALL_PATCHES="1"
OF_FORCE_MAGISKBOOT_BOOT_PATCH_MIUI="1"  OF_PATCH_AVB20="1"
OF_FORCE_DISABLE_DM_VERITY="1"  OF_KEEP_FORCED_ENCRYPTION="1"
OF_DONT_PATCH_ENCRYPTED_DEVICE="1"  OF_SKIP_FBE_DECRYPTION="1"
OF_FBE_METADATA... (absent in R11)   OF_SKIP_MULTIUSER_FOLDERS_BACKUP="1"
OF_USE_TWRP_SAR_DETECT="1"  OF_USE_SYSTEM_FINGERPRINT="1"
OF_QUICK_BACKUP_LIST="/boot;/data;/system_image;/vendor_image;"
FOX_USE_BASH_SHELL="1" FOX_ASH_IS_BASH="1" FOX_USE_NANO_EDITOR="1"
FOX_USE_TAR_BINARY="1" FOX_USE_XZ_UTILS="1" FOX_USE_ZIP_BINARY="1"
FOX_DELETE_AROMAFM="1"  OF_DISABLE_MIUI_OTA_BY_DEFAULT="1"
OF_SUPPORT_ALL_BLOCK_OTA_UPDATES="1"  OF_OTA_RES_DECRYPT="1"
OF_NO_MIUI_PATCH_WARNING="1"  OF_NO_MIUI_OTA_VENDOR_BACKUP="1"
OF_FIX_OTA_UPDATE_MANUAL_FLASH_ERROR="1"
OF_ALLOW_DISABLE_NAVBAR="0"  OF_CLOCK_POS="2"
```

Interpretation of the encryption-related switches — this matters for the port:

* `OF_SKIP_FBE_DECRYPTION=1` — FBE decryption was **not** performed. Consistent
  with a kernel that has no `fscrypt` (see §5).
* `OF_DONT_PATCH_ENCRYPTED_DEVICE=1` — do not patch boot/vbmeta on an encrypted device.
* `OF_KEEP_FORCED_ENCRYPTION=1` — preserve `forceencrypt` rather than remove it.
* `OF_FORCE_DISABLE_DM_VERITY=1` + `OF_PATCH_AVB20=1` — AVB 2.0 patching on.
* No `OF_ENABLE_LPTOOLS` and no `OF_ENABLE_APP_MANAGER` in R11 (both appear in
  the 2024 community R12 tree).

`META-INF/debug/default.prop` additionally leaks the exact build environment:

```
ro.build.flavor=omni_sakura-eng
ro.build.host=cirrus-ci-task-6630990345928704     # OrangeFox Cirrus CI
ro.build.date=Thu Mar 18 22:13:31 GMT 2021
ro.build.version.release=16.1.0                   # OmniROM 16.1 = Android 9 base
ro.build.version.sdk=28
ro.vndk.version=28
ro.vndk.lite=true
ro.product.cpu.abi=arm64-v8a
ro.build.version.security_patch=2099-12-31
```

So R11.0_5 is an **OmniROM 16.1 (Android 9 / SDK 28) eng build**, VNDK 28 lite,
arm64 primary + armeabi-v7a secondary (ABI list `armeabi-v7a,armeabi` — the
64-bit list is empty, i.e. 64-bit-only user space for the recovery binary).

## 4. Boot image and ramdisk

`file`/parser output for `recovery.img`:

| Field | Value |
|---|---|
| Magic | `ANDROID!` (boot image v0; `header_version` field = 0) |
| Size | 44 687 360 |
| Page size | 2048 |
| kernel_size | 21 400 270 (the kernel **slot**, see §5) |
| kernel_addr | 0x80008000 |
| ramdisk_size | 23 282 301 (gzip) |
| ramdisk_addr | 0x81000000 |
| second_size | 0 |
| second_addr | 0x80f00000 |
| tags_addr | 0x80000100 |
| os_version | 0x2004063c |
| dt_size (v0 field) | 0 — **the DTB is *not* in the boot header, it is appended inside the kernel slot** |
| cmdline | `androidboot.hardware=qcom msm_rtb.filter=0x237 ehci-hcd.park=3 lpm_levels.sleep_disabled=1 androidboot.bootdevice=7824900.sdhci androidboot.selinux=permissive buildvariant=eng` |
| id | `5a3956dba6cde0c1387c5e64a3bb36f657d1fda5` |
| SHA-256 (whole image) | `92069146e5db0c6c336d3a1000787920c91a2d832f66e9f3222ad13fde2c2669` |

Note the cmdline is byte-identical in structure to the `BOARD_KERNEL_CMDLINE`
of the 2024 `ofx-12.1` tree except that `audit=0` was added there. This is the
canonical sakura/MSM8953 cmdline and **must be preserved** (`androidboot.bootdevice=7824900.sdhci`
is what `init.recovery.qcom.rc` uses to create `/dev/block/bootdevice`).

Ramdisk: 23 282 301 bytes gzip → 60 861 184 bytes cpio, **2 322 entries**
(1 836 files, 201 symlinks), SHA-256 of the cpio
`9c57e4701a06e51624e8890d1ec4cc72c84e2f7c5ee42d2fd55dee3584724889`.
Contains `init` (2.1 MB), `init.rc`, `init.recovery.qcom.rc`,
`init.recovery.usb.rc`, `init.recovery.vold_decrypt.rc` (imported),
`ueventd.qcom.rc`, `ueventd.rc`, `sepolicy`, `file_contexts{,.bin}`,
`twres/` (theme), `FFiles/` (OrangeFox add-ons), and 1 836 entries in `/sbin`
with the recovery binaries, HIDL libs and tools (`magiskboot`, `busybox`-derived
toybox, `bash`, `nano`, `gnutar`, `xz`, `zip`, `decrypt`, `keystore`,
`keystore_auth`, `qseecomd`, `prepdecrypt.sh`, `findmiui.sh`, `foxstart.sh`).

### Device-critical configuration found in the ramdisk

`etc/recovery.fstab` (R11, **legacy TWRP v2 fstab, 4 columns**):

```
/boot     emmc  /dev/block/bootdevice/by-name/boot      display="Boot"
/cache    ext4  .../cache                                display="Cache";wipeingui
/recovery emmc  .../recovery                             display="Recovery";backup=1
/system   ext4  .../system                               display="System"
/vendor   ext4  .../vendor                               display="Vendor";backup=1;wipeingui
/data     ext4  .../userdata                             **encryptable=footer;length=-16384**
/system_image emmc .../system                            backup=1;flashimg=1
/vendor_image emmc .../vendor                            backup=1;flashimg=1
/cust     ext4  .../cust                                 display="Cust";backup=1;wipeingui
/misc     emmc  .../misc
/modem    vfat  .../modem                                display="Firmware";mounttodecrypt;fsflags=ro
/efs1     emmc  .../modemst1                             backup=1;display="EFS"
/efs2     emmc  .../modemst2                             backup=1;subpartitionof=/efs1
/fsg      emmc  .../fsg                                  backup=1;subpartitionof=/efs1
/fsc      emmc  .../fsc                                  backup=1;subpartitionof=/efs1
/persist  ext4  .../persist                              display="Persist";backup=1
/usb_otg  vfat  /dev/block/sda1  /dev/block/sda         storage;wipeingui;removable
/sdcard1  vfat  /dev/block/mmcblk1p1 /dev/block/mmcblk1  storage;wipeingui;removable
```

Facts that constrain the R12 port:

1. `/data` is declared **ext4 only** — no f2fs row. Consistent with a kernel
   without f2fs (§5). Modern ROMs default to f2fs on many builds.
2. `/data` uses **`encryptable=footer;length=-16384`** → legacy **full-disk
   encryption (FDE) with a crypto footer**, not FBE. There is **no
   `fileencryption=`, no `metadata_encryption=`, no `keydirectory=`**.
3. `/system` is a plain ext4 mount, **not** `/system_root` — so this build
   cannot mount a system-as-root ROM correctly by itself; R11 relied on
   `OF_USE_TWRP_SAR_DETECT=1` to switch at runtime.
4. **No EROFS** anywhere and **no dynamic/super partition** support.
5. `by-name` symlinks come from `init.recovery.qcom.rc`:
   `wait /dev/block/platform/soc/${ro.boot.bootdevice}` then
   `symlink ... /dev/block/bootdevice`. Because `ro.boot.bootdevice=7824900.sdhci`
   is in the boot cmdline, this only works with the correct cmdline.

### Crypto stack actually shipped in the R11 ramdisk

Present in `/sbin`: `libcryptfsfde.so`, `libcryptfs_hw.so`, `libe4crypt.so`,
`libgatekeeper.so`, `libkeymaster_messages.so`, `libkeymaster_portable.so`,
`libkeymaster4support.so`, `libkeystore_binder.so`, `libkeystore_aidl.so`,
`libsoftkeymasterdevice.so`, `libQSEEComAPI.so`, `libdiag.so`, `librpmb.so`,
`libsecureui*.so`, `openaes`, `keystore`, `keystore_auth`, `keystore_cli`,
`qseecomd`, and the HIDL services
`android.hardware.keymaster@3.0-service-qti`,
`android.hardware.gatekeeper@1.0-service-qti`,
`vendor.qti.hardware.qteeconnector@1.0-service`,
`vendor.qti.hardware.tui_comm@1.0-service-qti`.

`init.recovery.qcom.rc` shows the **two-stage crypto bring-up**:

```
service sbinqseecomd /sbin/qseecomd ...      (disabled)
service prepdecrypt /sbin/prepdecrypt.sh ... (disabled)
on property:fde.ready=1        -> start keymaster-3-0
on property:crypto.ready=1     -> start sbinqseecomd, keymaster-3-0, gatekeeper-1-0, servicemanager
on property:crypto.ready=0     -> stop sbinqseecomd, keymaster-3-0, gatekeeper-1-0, servicemanager
```

This is the classic **Qualcomm FDE/footer** flow: QSEECom + Keymaster 3.0 only,
gatekeeper 1.0. There is no KeyMint, no `android.hardware.security.*`, no weaver
*passthrough* wiring beyond `android.hardware.weaver@1.0.so` being present as a
library.

## 5. Kernel and DTB — the central finding

The 21 400 270-byte "kernel" slot is **not** a single kernel. It is:

| Region | Size | Content |
|---|---|---|
| gzip member | 9 838 320 (compressed) | 24 904 192-byte `Image` |
| appended FDT container | 11 561 950 | **46 concatenated DTBs** (`d00dfeed`) |

The `Image` header decodes as `text_offset = 0x80000`,
`image_size = 0x1C44000` (29 638 656), magic `ARMd` at offset 0x38. The stored
file is 24 904 192 bytes, i.e. **smaller than `image_size`**: that is normal and
expected for AArch64 Linux, because `image_size` counts the zero-initialised
`.bss` which is not stored in the file — it is *not* evidence of truncation.
Anyone re-deriving this image must keep `image_size` as-is.

Version string recovered from the binary:

```
Linux version 3.18.120-perf-gd85b39b (builder@c3-miui-ota-bd116.bj)
(gcc version 4.9.x 20150123 (prerelease) (GCC) )
#1 SMP PREEMPT Tue Jul 28 12:13:36 CST 2020
```

This is a **stock Xiaomi MIUI-OTA kernel**:

* `3.18.120` — the MSM8953 kernel line Xiaomi shipped for sakura (not 4.9).
* `builder@c3-miui-ota-bd116.bj` — Xiaomi's internal MIUI OTA build machine.
* `gcc version 4.9.x` — the Android 8.1/9 era AArch64 GCC, not clang.
* built **2020-07-28**, i.e. MIUI 12 / Android 9 (`V12.0.x.x.PDI*`) era.
* localversion `-perf-gd85b39b` → commit `d85b39b` of the MIUI branch.

This confirms the R11.0_5 changelog ("Switch to stock prebuilt kernel"): the
kernel is Xiaomi's Android 9 stock `Image.gz`, repackaged by the maintainer.

**Source-recovery status: partially unresolved, and documented as such.** The
`d85b39b` commit was **not found** in `MiCode/Xiaomi_Kernel_OpenSource` (the
public mirror exposes `sakura-o-oss` and `sakura-p-oss` branches — both
resolve — but no commit with that SHA). Xiaomi's public OSS mirror lags/omits
the exact MIUI release-branch commits, so the binary cannot be matched to a
published source revision. A compiled binary is not source: the correct position
is that the *lineage* is identified (`sakura-p-oss`, 3.18.120) but the *exact
commit* is not recoverable from public sources.

### The 46 appended DTBs

All are generic Qualcomm board DTs (`qcom,msm8953-sim`, `-rumi`, `-mtp`, `-cdp`,
`-qrd-sku3`, plus msm8937/msmcobalt/apq8037 variants), which is why a naive
search finds "no sakura" in the DTB. The **sakura-specific evidence is in the
camera and panel nodes**:

* camera: `sakura_imx486_ofilm`, `sakura_ov12a10_sunny`, `sakura_ov5675_ofilm`,
  `sakura_ov5675_qtech`, `sakura_s5k5e8_ofilm`, `sakura_s5k5e8_sunny`
  (i.e. sakura and sakura_india camera variants)
* panels: `mdss_dsi_ili7807_fhdplus_video`, `mdss_dsi_nt36672_*_fhdplus_video`
* touch: `focaltech`/`ft5435`, `ft5436`, `ft5606`, `goodix`, `nt36672`, `synaptics`

Conclusion: the packaged blob **is** the sakura stock kernel+DTB bundle, and the
DTB is selected by the bootloader from the 46 entries — the recovery does not
choose a DTB. Any replacement kernel must therefore ship an **appended,
sakura-capable multi-DTB** in the same layout, or the device will not boot.

### Kernel capability probe (string evidence, both kernels)

Method: search the decompressed `Image` for subsystem-specific strings. Strong
for filesystems (printk prefixes), weaker for optional code paths — results are
labelled accordingly.

| Capability | stock 3.18.120 | ofx-12.1 prebuilt 4.9.278 |
|---|---|---|
| ext4 | yes (32) | yes (34) |
| **f2fs** | **no (0)** | **yes (8)** |
| EROFS | no (0) | no (0) |
| **fscrypt / FBE** | **no (0 `fscrypt_`)** | **yes (5)** |
| dm-crypt (FDE) | yes (`crypt_ctr`, `kcryptd`) | yes |
| dm-verity | yes | yes |
| dm-default-key (metadata enc.) | no | no |
| ICE (inline crypto engine) | yes | yes |
| sdcardfs | yes | yes |
| quota | yes | yes |
| lz4 / zstd | lz4 only | lz4 + zstd |

This single table explains most of the R11 design: fstab is ext4-only, FBE is
skipped, `/data` uses a footer. It also predicts exactly what will fail on
modern ROMs and is used as the basis for `documentation/ENCRYPTION.md`.

## 5b. Architecture of the shipped user space (verified from ELF headers)

`prop.default` reports an empty `ro.product.cpu.abilist64`, which superficially
suggests a 32-bit build. The binaries say otherwise:

| Binary | Class | Machine |
|---|---|---|
| `init` | ELF64 | AArch64 |
| `sbin/recovery` | ELF64 | AArch64 |
| `sbin/adbd` | ELF64 | AArch64 |
| `sbin/toybox` | ELF64 | AArch64 |
| `sbin/libc.so`, `libc++.so` | ELF64 | AArch64 |
| `sbin/keystore`, `sbin/qseecomd` | ELF64 | AArch64 |
| `sbin/linker64` | ELF64 | AArch64 |
| `sbin/linker`, `sbin/bash`, `sbin/magiskboot` | ELF32 | ARM |

So R11 is a **64-bit primary** recovery with a 32-bit secondary used only for
prebuilt helpers (`bash`, `magiskboot`, `linker`). This settles the
`TARGET_ARCH` question for the port: `arm64` primary + `arm` secondary, and the
empty `abilist64` prop is a build-prop quirk that must not be imitated.

## 6. What the R11 build actually was

* OmniROM 16.1.0 (Android 9, SDK 28) omni_sakura-eng, built on OrangeFox Cirrus CI
  on 2021-03-18, release tagged R11.0_5 on 2021-03-21.
* Stock sakura kernel+DTB, legacy FDE decryption (QSEECom + Keymaster 3.0),
  ext4-only fstab, SAR auto-detect, MagiskBoot v2 by default.
* Maintainer `imzihad21` (from the device API record).

## 7. Reproduction

```bash
build/fetch_reference.sh              # downloads + verifies the ZIP into reference/
python3 tools/bootimg.py info   reference/recovery.img
python3 tools/bootimg.py unpack reference/recovery.img reference/unpacked
python3 tools/bootimg.py cpiotoc reference/unpacked/ramdisk.cpio reference/ramdisk
```

`build/fetch_reference.sh` refuses to continue unless the MD5 matches
`5dff190fe5e86631bd58c049a9b5f924`.
