# Encryption analysis (current source configuration, evidence-based)

This document describes the **current** sakura OrangeFox R12.0 (`fox_12.1`) source configuration, inspected upstream/device-tree evidence, and what remains unverified. **No recovery image from this tree has been built here, no hardware boot has been performed, and no decryption has been tested on a device.**

## 1. Encryption types (kept distinct)

| Mechanism | What it is | How it appears in this tree | Status |
|---|---|---|---|
| **FDE (Full-Disk Encryption, legacy)** | Block-device encryption (dm-crypt) for `/data` using a crypto footer. User credential is verified via Gatekeeper/Keymaster to unwrap the disk key. | `encryptable=footer` is present as a separate fs_mgr flag token on both `/data` rows in `device/xiaomi/sakura/recovery/root/system/etc/recovery.fstab`. | **Configured/intended** for FDE-capable layouts; **not build-tested and not hardware-tested**. |
| **FBE (File-Based Encryption)** | Per-file encryption (fscrypt) on `/data`; keys protected via Keymaster/Gatekeeper-backed mechanisms. | `fileencryption=ice` is present on both `/data` rows. `TW_INCLUDE_CRYPTO := true`, `TW_INCLUDE_CRYPTO_FBE := true` in `BoardConfig.mk`. 4.9 prebuilt kernel (fscrypt/f2fs capable per project analysis). No `metadata_encryption=` and no `keydirectory=` declared. | **Configured/intended** for **FBE without metadata encryption**, only where the on-disk format matches (see §3–§5); **not build-tested and not hardware-tested**. |
| **Metadata encryption (FBEv2)** | Separate metadata layer (commonly `metadata_encryption=` / `dm-default-key`, often with `keydirectory=`). Not the same as `fileencryption=...`. | **Off by default** in fstab/twrp.flags; `BOARD_USES_METADATA_PARTITION := false`. The pinned recovery's metadata path *is* compiled in (`-DTW_INCLUDE_FBE_METADATA_DECRYPT`, `libvold`). Opt-in configuration exists (`SAKURA_METADATA_ENCRYPTION=1` → `tools/configure_metadata.py`), see §6. | **Wired, not functional on this kernel**: neither available kernel has `dm-default-key` and the vendor is Keymaster 3.0 (no KeyMint). Do not claim decryption support. |

## 2. Current source configuration (actual)

- **`/data` fstab entries** (`device/xiaomi/sakura/recovery/root/system/etc/recovery.fstab`): f2fs then ext4, both with fs_mgr flags `wait,check,encryptable=footer,fileencryption=ice,quota,formattable` (comma-separated). No `metadata_encryption=`, no `keydirectory=` (deliberate; §6 explains why a non-empty key directory is dangerous here and how to opt in).
- **Crypto build flags** (`device/xiaomi/sakura/BoardConfig.mk`): `TW_INCLUDE_CRYPTO := true`, `TW_INCLUDE_CRYPTO_FBE := true`, `BOARD_USES_METADATA_PARTITION := false`.
- **TEE/init integration** (`init.recovery.qcom.rc`, `init.recovery.qcom_decrypt.rc`, `device.mk`): device init fragments installed into recovery ramdisk; decryption rc defines/starts `qseecomd` → QTI Keymaster 3.0 → QTI Gatekeeper 1.0 (paths under `/system/bin`, destinations per manifest; `tools/check_init_services.py` enforces consistency). No nonexistent upstream `qcom_decrypt`/`qcom_decrypt_fbe` product modules.
- **Vendor blobs** (`proprietary-files.txt`, `build/extract_blobs.sh`, `build/install_blobs.sh`, `build/check_crypto_blobs.sh`): **20** proprietary entries total (7 required, 13 optional). **0/20 present** in this workspace. Extraction is read-only from a user-supplied sakura Android 9 fastboot ROM with provenance/hashes recorded locally under gitignored `vendor_blobs/`. `check_crypto_blobs.sh --require` refuses crypto-gated builds by default; `SAKURA_ALLOW_MISSING_CRYPTO=1` is an explicit non-decryption opt-out only.
- **Boot/kernel/partitions**: unchanged by this audit (no boot parameters, kernel, DTB, addresses, bootdevice command line, or partition size modified).

## 3. `fileencryption=ice` checked against pinned recovery and android-12.1

### 3.1 Pinned recovery parser — `bootable/recovery` @ `8d2aad19deb158e935d70ca5b648162c2b2831ee` (`fox_12.1`)

Read from that commit's `partition.cpp` / `partitionmanager.cpp`:

| Code path | Behaviour |
|---|---|
| `TWPartition::Process_Fstab_Line()` | `/dev/` line → AOSP 5-column format (`fstab_version = 2`); column 4 → `Process_FS_Flags()`, column 5 → TWRP flags. |
| `TWPartition::Process_FS_Flags()` | Tokenises mount options with `strtok_r(..., ",", ...)` (commas only). |
| `TWPartition::Process_TW_Flags()` | `source_separator = ','` when `fstab_ver == 2`; `encryptable=footer;fileencryption=ice` would be one malformed token (both lost). |
| `TWFLAG_ENCRYPTABLE` | `Crypto_Key_Location = str` (footer/key location retained). |
| `TWFLAG_FILEENCRYPTION` | Sets `fbe.contents` / `fbe.filenames` from argument. For this fstab → `fbe.contents=ice`, empty `fbe.filenames`. Source comment references "fileencryption=ice:aes-256-heh". |
| FBE build/runtime | FBE code under `TW_INCLUDE_FBE` (enabled by `TW_INCLUDE_CRYPTO_FBE`). Runtime detection via `/data/unencrypted/key/version` in `Decrypt_FBE_DE()`; skippable via `OF_SKIP_FBE_DECRYPTION[_SDKVERSION]`. |
| Metadata decryption | `partitionmanager.cpp` compiles metadata path only under `TW_INCLUDE_FBE_METADATA_DECRYPT` and needs `metadata_encryption=`/`keydirectory=` fstab data. **Neither macro nor flags enabled here.** |

### 3.2 Android 12.1 fs_mgr / libfscrypt

| Code | Behaviour |
|---|---|
| `system/core/fs_mgr/fs_mgr_fstab.cpp` (android-12.1) | fs_mgr flag column split on `,`. `encryptable=` sets `crypt=true` + `key_loc`; `fileencryption=` parses via `ParseFileEncryption()`. No voldmanaged-only rejection of `encryptable` in 12.1. |
| `system/extras/libfscrypt/fscrypt.cpp` (android12-release) | `ParseOptionsForApiLevel()` maps `"ice"` → **`FSCRYPT_MODE_PRIVATE` (127)** (vendor on-disk contents format), not the `inlinecrypt` mount option. Default filenames `aes-256-cts`; policy version `1` when `ro.product.first_api_level <= 29` (sakura first API level < 29). |

### 3.3 Established vs not established

- **Established:** comma-separated tokens parsed as intended by pinned recovery; `encryptable=footer` retained; `fileencryption=ice` yields `fbe.contents=ice`; FBE path enabled, metadata path not enabled.
- **Caveat (not changed):** `ice` = vendor `FSCRYPT_MODE_PRIVATE` contents format (historical for sakura/Android 9 launch). A `/data` formatted with standard `aes-256-xts` (or other contents/filenames/policy/metadata variants) will not match this declaration. Flag left unchanged; compatibility is per-ROM and unverified.
- **Not established:** that FBE/FDE decryption succeeds (needs genuine blobs, built/verified image, matching on-disk format, and device testing — none present).

## 4. TEE / crypto integration (intended, not runtime-proven)

- **Platform:** 4.9 prebuilt kernel (fscrypt/f2fs capability per project analysis); Qualcomm TEE `/dev/qseecom`.
- **Userspace:** `qseecomd`.
- **HALs:** QTI **Keymaster 3.0** (`android.hardware.keymaster@3.0-service-qti`) and QTI **Gatekeeper 1.0** (`android.hardware.gatekeeper@1.0-service-qti`) with vendor libraries listed in `proprietary-files.txt` (20 entries total).
- **Recovery crypto:** `TW_INCLUDE_CRYPTO`, `TW_INCLUDE_CRYPTO_FBE` (pinned upstream trees).

**Runtime compatibility unverified.** **0/20** blobs present, no production image built/verified, no device testing. Do not claim KM/GK/QSEECom startup or decryption without genuine firmware blobs and on-device evidence.

## 5. Per-ROM / per-generation evidence (inspected sources)

Sakura (Redmi 6 Pro) launched on Android 8.1 (API 27), official end state MIUI 12 Android 9 (`V12.0.4.0.PDMMIXM` / `V12.0.1.0.PDICNXM`). Inspected public sakura/daisy/msm8953-common fstabs:

| Source (branch) | Android era | `/data` encryption flags observed | Metadata |
|---|---|---|---|
| `TeamWin/android_device_xiaomi_sakura` `android-8.1` (`twrp.fstab`) | 8.1/9 stock-era | `encryptable=footer;length=-16384` | none |
| `xiaomi-msm8953-devs/msm8953-common` `lineage-18.1` | A11 era (LOS 18.1) | `encryptable=footer,quota` | none |
| `xiaomi-msm8953-devs/msm8953-common` `lineage-20` | A13 era (LOS 20) | `fileencryption=ice,quota` | none |
| `xiaomi-msm8953-devs/msm8953-common` `lineage-21` | A14 era (LOS 21) | `fileencryption=ice,quota` | none |
| `xiaomi-msm8953-devs/android_device_xiaomi_daisy` `lineage-22.0/22.1/22.2` (sakura unified) | A15 era (LOS 22.x) | `fileencryption=ice,quota` (+formattable on ext4) | none |

**No genuine sakura Android 16/17 ROM or device tree found** in sources checked. Exact userdata format (contents/filenames modes, policy v1/v2, metadata, Adiantum, wrapped-key variants) is **ROM-specific** and cannot be inferred from Android version alone; uninspected ROMs (e.g. A10, A12, some A14 builds) remain **unknown**.

## 6. Intended / unsupported / unknown configurations

| Configuration | Intended by current config? | Notes |
|---|---|---|
| Android 9 stock-era, unencrypted `/data` | Yes (mount/use) | Not a decryption case. |
| Android 9 legacy FDE (`encryptable=footer`) | **Intended** | Footer flag + TEE chain configured; **unverified**. |
| FBE without metadata encryption, userdata formatted with vendor `ice` (`FSCRYPT_MODE_PRIVATE`, v1-default context) | **Intended (best-effort target)** | Declared flags match inspected LOS 20/21/22.x sakura-unified fstabs; **unverified**, blobs/build/tests missing. |
| FBE with standard `aes-256-xts` contents, different filenames/policy (e.g. v2), Adiantum, or other non-`ice` formats | **Unknown / likely mismatch** | Fstab declares `fbe.contents=ice`; no proof of match. Not changed. |
| FBE with metadata encryption (`metadata_encryption=`, `keydirectory=`, dm-default-key) | **Off by default; opt-in wired (§6a)** | Not declared in the committed tree. The recovery's metadata path is compiled in; enabling it needs `SAKURA_METADATA_ENCRYPTION=1` **and** a kernel with `dm-default-key`, which neither available kernel has — so it is not usable on this device today. |
| Android 16 / 17 on sakura | **Unknown / not applicable** | No sakura ROM/device-tree evidence. |

## 6a. Metadata encryption (FBEv2): what is implemented, and the hard blocker

**Implemented and shipped (opt-in, default off).** The expensive half of
metadata decryption lives in the recovery, not in this device tree. Against the
pinned `bootable/recovery` @ `8d2aad19deb158e935d70ca5b648162c2b2831ee`:

| Evidence | Location |
|---|---|
| Metadata decryption is compiled whenever crypto is on | `Android.mk:360` adds `-DTW_INCLUDE_FBE_METADATA_DECRYPT` |
| `libvold` / `MetadataCrypt` are linked | `Android.mk:139` |
| fstab tokens are parsed (both spellings) | `partition.cpp:193` (`metadata_encryption=`), `partition.cpp:220` (`keydirectory=`) |
| Decryption path uses them | `partitionmanager.cpp:677-700` |

So the userspace path is already in the image; no device-tree flag is needed to
compile it. What *is* needed is the fstab declaration, and that is the dangerous
part:

`Setup_Data_Partition()` treats **any non-empty key directory** as "this `/data`
is encrypted". Declaring `keydirectory=` on a ROM that does not use a metadata
layer therefore produces a **false encryption state**: recovery asks for a
credential for a plain `/data`, and a tester reads that as "decryption is
broken". Every inspected sakura fstab (`LOS 18.1`, `20`, `21`, `22.x`)
declares `fileencryption=ice` and no metadata layer. Consequently metadata stays
**off by default** and cannot be enabled by accident.

**Enabling it (explicit, reversible):**

```bash
# adds metadata_encryption=aes-256-xts:wrappedkey_v0 and
# keydirectory=/metadata/vold/metadata_encryption to both /data rows, plus a
# /metadata partition row in recovery.fstab and twrp.flags
python3 tools/configure_metadata.py --enable --confirm-rom-uses-metadata

# or through the build entry point (also writes metadata_encryption.mk)
SAKURA_METADATA_ENCRYPTION=1 ./build/build.sh --no-sync

# inspect / revert (byte-exact)
python3 tools/configure_metadata.py --check
python3 tools/configure_metadata.py --disable
```

`--enable` refuses to run without `--confirm-rom-uses-metadata`; `--check`
fails on a half-applied tree (tokens without a `/metadata` row, or the reverse);
`--disable` restores the committed files byte-for-byte (regression-tested).
`build/build.sh` refuses `SAKURA_METADATA_ENCRYPTION=1` together with
`SAKURA_ALLOW_MISSING_CRYPTO=1`, because a metadata image without the TEE chain
can never decrypt anything, and `build/verify_image.sh` cross-checks the tokens
against the recorded mode.

**The blocker that no device-tree change can fix:** metadata encryption needs
`dm-default-key` in the kernel to map the metadata device, and a Keymaster that
supports the wrapped-key format. Documented measurements of both kernels
available here (`documentation/KERNEL_ANALYSIS.md` §2, §3 and §5, plus
`REFERENCE_R11_ANALYSIS.md` §… "dm-default-key: no"): `dm-default-key` is **absent** from the stock 3.18.120 kernel and from the
4.9.278 community candidate; sakura's vendor is Keymaster **3.0** (no KeyMint).
Therefore:

* metadata-encrypted `/data` **cannot be decrypted by this recovery on this
  device** today, whatever the fstab says;
* the opt-in exists so that a future `dm-default-key` kernel can be used without
  touching the device tree again, and so the configuration can be validated on
  hardware that does support it;
* no sakura ROM inspected uses metadata encryption, so the default build loses
  nothing.

This is deliberately stated as **implemented-but-blocked**, not as working
support. Claiming otherwise would be the exact failure mode this audit exists to
prevent.

## 7. Verification status (executed checks only)

| Item | Status | Evidence |
|---|---|---|
| Source fstab/config consistency (comma tokens, no metadata flags, crypto flags/init wiring) | **PASS (executed)** | `python3 tools/static_checks.py` → **PASS (all checks)**; WARN `0/20` proprietary blobs. |
| Tooling/unit regression tests | **PASS (executed)** | `python3 -m unittest discover -s tests` → **74 tests, OK** (synthetic fixtures; **not** genuine sakura firmware). Includes the metadata tool: enable requires confirmation, `--disable` is byte-exact, half-applied trees fail `--check`. |
| Pinned recovery parsing of fstab/flags | **Verified by source inspection** | `bootable/recovery@8d2aad19` `partition.cpp`: comma separator for `fstab_ver==2`, `encryptable` key location, `fileencryption` → `fbe.contents/filenames`. Runtime unverified. |
| `ice` meaning in android-12.1 | **Verified by source inspection** | `system/extras/libfscrypt/fscrypt.cpp` (android12-release): `"ice"` → `FSCRYPT_MODE_PRIVATE`. |
| Genuine firmware blob extraction/integration | **Not completed** | No genuine sakura A9 fastboot ROM; `0/20` blobs. |
| Blob-dependent crypto gates with real blobs | **Not executed** | No blobs. |
| Production recovery image build/verification | **Not done** | No compatible build host/image. |
| Boot, service startup, FDE/FBE decryption on hardware | **Not tested** | No device testing. |

## 8. Operational cautions

- FBE flags without a working TEE/Keymaster/Gatekeeper chain can hang on encrypted `/data`. Do not infer working decryption from flags or `keystore2` presence.
- `SAKURA_ALLOW_MISSING_CRYPTO=1` produces (if built) a **non-decrypting** artifact choice; never label it decryption-capable.
- Never claim decryption works without a real build, verified image, and on-device evidence recorded in `testing/android-*/TEST_RECORD.md`.
