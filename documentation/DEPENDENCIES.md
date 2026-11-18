# Dependencies

## 1. Build host requirements (from the official guide + measured)

| Item | Requirement | Source |
|---|---|---|
| Disk | **≥ 45 GB** for `fox_12.1` (≥85 GB for `fox_14.1`) | https://wiki.orangefox.tech/dev/building |
| RAM | 8 GB practical minimum; 16 GB recommended (2 jobs/GB rule) | Soong/link steps |
| CPU | 4+ cores recommended | `repo sync -j$(nproc)` + `mka` |
| OS | Ubuntu 20.04/22.04 (or equivalent), 64-bit | guide |
| User | must **not** be root | guide |

Required packages (standard AOSP/TWRP list):

```bash
sudo apt install -y git curl python3 repo zip unzip \
  openjdk-11-jdk bc bison build-essential ccache flex g++-multilib \
  gcc-multilib gnupg gperf imagemagick lib32ncurses5-dev lib32readline-dev \
  lib32z1-dev libelf-dev liblz4-tool libncurses5 libncurses5-dev libsdl1.2-dev \
  libssl-dev libxml2 libxml2-utils lzop pngcrush rsync schedtool \
  squashfs-tools xsltproc zlib1g-dev
```

### Self-hosted runner notes (ServerHive is retired)

The ServerHive runner used for earlier runs has **expired** and the workflow no
longer references it. Any replacement Linux x86_64 host works as a self-hosted
runner; the workflow takes its label from the `runner_label` dispatch input.

On such a host, if the account has **no passwordless sudo**, the apt line above
cannot be run from CI. Note also that distro images may ship **OpenJDK 21**
while the Android 12.1 Soong bootstrap requires **11**.

`build/setup_jdk11.sh` solves the JDK without root - it reuses a system JDK 11
when one exists, otherwise it unpacks the current Temurin 11 GA tarball into
`$HOME/.jdk11` and prints the `JAVA_HOME` to use. The workflow's preflight, the
build job and `build/build.sh` all use it (and prepend `$JAVA_HOME/bin` to
`PATH`), so no apt step is required for the JDK.

Termux / Android-device hosts (for example a Poco F1 running Termux) are not a
supported build environment for this tree and are not claimed to be one.

System packages are different: if the preflight reports missing tools, they must
be installed once by whoever holds root on the host:

```bash
sudo apt install -y bc bison build-essential ccache flex g++-multilib \
  gcc-multilib libelf-dev liblz4-tool libncurses-dev libssl-dev libxml2 \
  libxml2-utils lzop pngcrush rsync schedtool squashfs-tools xsltproc \
  zip zlib1g-dev cpio lz4
```

`repo` must be the Google launcher (`https://storage.googleapis.com/git-repo-downloads/repo`).

### This analysis environment (for reproducibility of the report)

A Cloud analysis workspace is **sufficient** for the dependency-free tooling
here (`tools/bootimg.py`, `tools/verify_dtb.py`, `tools/static_checks.py`,
`build/check_crypto_blobs.sh`) and **not sufficient** to sync or build
OrangeFox. See `BUILD_INSTRUCTIONS.md` §7.

## 2. Source dependencies (pinned in `manifest/`)

1. `minimal-manifest-twrp/platform_manifest_twrp_aosp` @ `twrp-12.1`
   (`6dc117d9cbd08430daa16db2013560e1c4017fa8`)
2. `OrangeFox/bootable/Recovery` @ `fox_12.1` (`8d2aad19…`)
3. `OrangeFox/vendor/recovery` @ `main` (`1998cfca…`, legacy `fox_12.1` `fbe4d49c…`)
4. `OrangeFox/external/se_omapi` — only cloned for `BASE_VER=14`; **not needed**
   for `fox_12.1` (script: `if [ "$BASE_VER" = "14" ... ]`).
5. `TeamWin/android_device_qcom_common` @ `android-12.1` and
   `TeamWin/android_device_qcom_twrp-common` @ `android-12.1` — cloned by the
   sync script (`clone_qcom_common`), required for MSM8953 init/qcom handling.
6. This device tree (`device/xiaomi/sakura`).

## 3. Runtime components the recovery needs (and where they come from)

| Component | Provided by | Notes |
|---|---|---|
| recovery crypto implementation | `bootable/recovery` (`TW_INCLUDE_CRYPTO`, `TW_INCLUDE_CRYPTO_FBE`) | `qcom_decrypt` / `qcom_decrypt_fbe` do **not** exist at the pinned revisions and are not referenced |
| `android.hardware.keymaster@3.0-service-qti` | prebuilt, installed to `recovery/root/system/bin` by `build/install_blobs.sh` | vendor KM 3.0 HAL |
| `android.hardware.gatekeeper@1.0-service-qti` | prebuilt, installed to `recovery/root/system/bin` | vendor gatekeeper HAL |
| `qseecomd` | prebuilt, installed to `recovery/root/system/bin` | QSEECom daemon (TEE channel) |
| `keystore.msm8953.so`, `gatekeeper.msm8953.so` | prebuilt, installed to `recovery/root/system/lib64` (or `lib64/hw` per manifest) | TEE-backed key/gatekeeper impls |
| `libQSEEComAPI.so`, `librpmb.so`, `libdiag.so`, `libssd.so`, `libdrmfs.so`, `libdrmtime.so`, `libtime_genoff.so`, `libqisl.so`, `libStDrvInt.so`, `libSecureUILib.so`, `libGPreqcancel*.so`, `libkeymasterdeviceutils.so` | prebuilt | QTI crypto/TEE support chain |
| VINTF manifests | not shipped | `PRODUCT_ENFORCE_VINTF_MANIFEST` is deliberately **not** set (`BoardConfig.mk`); no health@2.0 service is required |
| `libdrm`, `libion`, `libxml2`, `libicuuc`, `vendor.display.config@1.0/2.0` | `device.mk` recovery modules | display/graphics + XML parsing for vintf |

### Provenance warning

The prebuilts in the community tree are **daisy-derived** (see
`DEVICE_COMPATIBILITY.md` §3: header says blobs from
`daisy-user 10 QKQ1.191002.002 V11.0.21.0.QDLMIXM`). They are recorded here as
*unverified for sakura*.

## 4. Regenerating the proprietary set from your own sakura (licence-safe)

The blobs are Xiaomi/Qualcomm proprietary and are **not** republished in this
repository. The extraction is scripted, not manual:

```bash
# Required input (the one thing this repository cannot supply):
#   a sakura Android 9 stock FASTBOOT ROM (.tgz)
#     Global / sakura_india : V12.0.4.0.PDMMIXM
#       sakura_india_global_images_V12.0.4.0.PDMMIXM_20201104.0000.00_9.0_global_396957553f.tgz
#     China                 : V12.0.1.0.PDICNXM
#   (the fastboot ROM's images/vendor.img is what gets read; a recovery ROM zip
#    will NOT work - it has no vendor.img)

# 1. Extract + validate (read-only, no root, no Android SDK)
./build/extract_blobs.sh --firmware sakura_india_global_images_V12.0.4.0.PDMMIXM_*.tgz

# 2. Install into the device tree + generate the make fragment
./build/install_blobs.sh

# 3. Confirm the chain is complete and init-resolvable
./build/check_crypto_blobs.sh --require
```

What step 1 does, and why each part exists:

| Step | Detail |
| --- | --- |
| unpack | `.tgz` / `.tar.gz` / `.tar.xz` / `.zip`, a directory, or a bare `vendor.img` |
| sparse -> raw | `tools/simg2img.py` (no `android-sdk-libsparse-utils` needed) |
| read the filesystem | `debugfs` (e2fsprogs), read-only; `mount -o loop,ro` only if root and debugfs is absent |
| identity gate | reads `ro.product.device` / `ro.build.version.release` / fingerprint; **refuses any image that is not `sakura` Android 9** |
| ELF gate | every blob must be ELFCLASS64/AArch64 (`tools/elf.py`) |
| manifest | `vendor_blobs/MANIFEST.sha256` + `vendor_blobs/EXTRACTION_REPORT.md` record firmware name, firmware SHA-256, `vendor.img` SHA-256, vendor fingerprint, security patch and each file's SHA-256 |

The daisy (Mi A2 Lite) list this tree inherited is exactly the mistake the
identity gate exists to stop: those binaries are not sakura's.

`vendor_blobs/`, `device/xiaomi/sakura/blob_install.mk` and the installed
`recovery/root/system/{bin,lib64}` contents are gitignored. Nothing proprietary
can be committed by accident, and `build/check_crypto_blobs.sh --require` makes
an image without them impossible to produce silently.

### Cross-check list (sakura vs the daisy-derived set)

`vendor_blobs/EXTRACTION_REPORT.md` lists the SHA-256 of every extracted file
together with the firmware it came from. If you also hold a Daisy-based set,
these seven are the ones to compare before trusting anything:

```
bin/hw/android.hardware.gatekeeper@1.0-service-qti
bin/hw/android.hardware.keymaster@3.0-service-qti
bin/qseecomd
lib64/libQSEEComAPI.so
lib64/hw/keystore.msm8953.so
lib64/hw/gatekeeper.msm8953.so
lib64/libkeymasterdeviceutils.so
```

### Where the files land, and why

`fox_12.1` builds the recovery ramdisk with binaries in `/system/bin`,
libraries in `/system/lib64`, `/sbin` holding only the `sh`/`bash` symlinks,
`PATH=/sbin:/system/bin` and `LD_LIBRARY_PATH=/system/lib64:/vendor/lib64/hw`.
The manifest therefore installs to `system/bin/...` and `system/lib64/...`, and
`recovery/root/init.recovery.qcom_decrypt.rc` execs those exact paths.
`tools/check_init_services.py` fails the build if the two ever disagree.

## 5. Not required (deliberately excluded)

* Full ROM vendor trees (`vendor_xiaomi_sakura`, `vendor_xiaomi_msm8953-common`)
  — these are ROM makefiles, not recovery inputs.
* `proprietary_vendor_xiaomi_msm8953-common` — a *blob source* for ROM builds;
  recovery only needs the crypto subset, and pulling the whole tree would drag
  in hundreds of megabytes of irrelevant blobs.
* `se_omapi` (14.x only), `XiaomiParts`/overlays (ROM-only), `daisy` anything.
