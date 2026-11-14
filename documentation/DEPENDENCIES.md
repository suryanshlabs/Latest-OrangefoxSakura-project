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

`repo` must be the Google launcher (`https://storage.googleapis.com/git-repo-downloads/repo`).

### This analysis environment (for reproducibility of the report)

The Cloud workspace used to produce this documentation has **9.5 GB free,
3.8 GB RAM, 2 vCPU, no root** and no `cpio`/`lz4`/`java` binaries. That is
**sufficient** for reference analysis (which is dependency-free Python) and
**not sufficient** to sync or build OrangeFox. See `BUILD_INSTRUCTIONS.md` §6.

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
| `qcom_decrypt`, `qcom_decrypt_fbe` | `vendor/recovery` (OrangeFox) | R12 decryption framework, declared in `device.mk` |
| `libinit_sakura` | `device/xiaomi/sakura/init` (Soong) | sets `ro.hardware.keystore=msm8953`-era init props |
| `android.hardware.keymaster@3.0-service-qti` | prebuilt in `recovery/root/sbin` | vendor KM 3.0 HAL |
| `android.hardware.gatekeeper@1.0-service-qti` | prebuilt in `recovery/root/sbin` | vendor gatekeeper HAL |
| `qseecomd` | prebuilt in `recovery/root/sbin` | QSEECom daemon (TEE channel) |
| `keystore.msm8953.so`, `gatekeeper.msm8953.so` | prebuilt `recovery/root/vendor/lib64/hw/` | TEE-backed key/gatekeeper impls |
| `libQSEEComAPI.so`, `librpmb.so`, `libdiag.so`, `libssd.so`, `libdrmfs.so`, `libdrmtime.so`, `libtime_genoff.so`, `libqisl.so`, `libStDrvInt.so`, `libSecureUILib.so`, `libGPreqcancel*.so`, `libkeymasterdeviceutils.so` | prebuilt | QTI crypto/TEE support chain |
| `health@2.0` HAL + VINTF manifests | prebuilt `recovery/root/**/vintf/manifest.xml` | required by R12 `PRODUCT_ENFORCE_VINTF_MANIFEST := true` |
| `libdrm`, `libion`, `libxml2`, `libicuuc`, `vendor.display.config@1.0/2.0` | `device.mk` recovery modules | display/graphics + XML parsing for vintf |

### Provenance warning

The prebuilts in the community tree are **daisy-derived** (see
`DEVICE_COMPATIBILITY.md` §3: header says blobs from
`daisy-user 10 QKQ1.191002.002 V11.0.21.0.QDLMIXM`). They are recorded here as
*unverified for sakura*.

## 4. Regenerating the proprietary set from your own sakura (licence-safe)

The blobs are Xiaomi/Qualcomm proprietary and are **not** republished in this
repository. To obtain sakura-correct copies:

```bash
# 1. Fetch a sakura stock image for the exact vendor you target (Android 9):
#    V12.0.1.0.PDICNXM (China) or V12.0.4.0.PDMMIXM (Global, sakura_india)
#    from the official MIUI fastboot package (tgz) — unpack:
tar -xzf sakura_*_images_*.tgz
# 2. Extract the vendor image (sparse -> raw)
simg2img vendor.img vendor.raw      # from android-sdk-libsparse-utils
mkdir -p vendor_tree && sudo mount -o loop,ro vendor.raw vendor_tree
# 3. Pull the files listed in device/proprietary-files.txt
while IFS=':' read -r src dst _rest; do
  case "$src" in \#*|"") continue;; esac
  install -D "$vendor_tree/$src" "device/xiaomi/sakura/${dst:-recovery/root/$src}"
done < device/proprietary-files.txt
# 4. Record hashes for the audit
sha1sum device/xiaomi/sakura/recovery/root/vendor/lib64/hw/keystore.msm8953.so
```

Then replace the "unverified (daisy-derived)" note in
`device/proprietary-files.txt` with the actual sakura source + SHA-1, and update
`documentation/SOURCE_REFERENCES.md` §D.

### Cross-check list (sakura vs the daisy-derived set)

Compare SHA-1 of these before trusting the inherited blobs — if they differ,
the sakura copies must be used:

```
vendor/bin/hw/android.hardware.gatekeeper@1.0-service-qti
vendor/bin/hw/android.hardware.keymaster@3.0-service-qti
vendor/bin/qseecomd
vendor/lib64/libQSEEComAPI.so
vendor/lib64/hw/keystore.msm8953.so
vendor/lib64/hw/gatekeeper.msm8953.so
vendor/lib64/libkeymasterdeviceutils.so
```

## 5. Not required (deliberately excluded)

* Full ROM vendor trees (`vendor_xiaomi_sakura`, `vendor_xiaomi_msm8953-common`)
  — these are ROM makefiles, not recovery inputs.
* `proprietary_vendor_xiaomi_msm8953-common` — a *blob source* for ROM builds;
  recovery only needs the crypto subset, and pulling the whole tree would drag
  in hundreds of megabytes of irrelevant blobs.
* `se_omapi` (14.x only), `XiaomiParts`/overlays (ROM-only), `daisy` anything.
