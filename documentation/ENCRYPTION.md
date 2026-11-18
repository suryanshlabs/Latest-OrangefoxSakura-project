# Encryption analysis (current source configuration)

This document describes the **current** sakura OrangeFox R12.0 (`fox_12.1`) source configuration, what it is intended to handle, and what remains unverified. **No recovery image from this tree has been built here, no hardware boot has been performed, and no decryption has been tested on a device.**

## 1. Encryption types (kept distinct)

| Mechanism | What it is | How it appears in this tree | Status |
|---|---|---|---|
| **FDE (Full-Disk Encryption, legacy)** | Block-device encryption (dm-crypt) for `/data` using a crypto footer. User credential is verified via Gatekeeper/Keymaster to unwrap the disk key. | `encryptable=footer` is present as a separate fs_mgr flag token on both `/data` rows in `device/xiaomi/sakura/recovery/root/system/etc/recovery.fstab`. This matches the legacy footer/FDE model used by sakura Android 9 stock. | **Configured/intended** for FDE-capable ROM layouts; **not build-tested and not hardware-tested**. |
| **FBE (File-Based Encryption)** | Per-file/per-directory encryption (fscrypt) on `/data`. File keys are protected by Keymaster/Gatekeeper-backed credentials (credential-encrypted keys) and/or device-encrypted state depending on ROM. Inline crypto/ICE may be used by the kernel/hardware. | `fileencryption=ice` is present as a separate fs_mgr flag token on both `/data` rows. `TW_INCLUDE_CRYPTO := true` and `TW_INCLUDE_CRYPTO_FBE := true` are set in `device/xiaomi/sakura/BoardConfig.mk`. The 4.9 prebuilt kernel is used (not R11's stock 3.18) because fscrypt/f2fs support is required for FBE scenarios (see measured kernel analysis in repo history/docs). No `metadata_encryption=` and no `keydirectory=` flags are declared for `/data`. | **Configured/intended** for **FBE without metadata encryption** only; **not build-tested and not hardware-tested**. |
| **Metadata encryption** | A separate encryption layer for filesystem metadata (commonly `metadata_encryption=` / `dm-default-key`, often with a `keydirectory=` path and storage-key support in Keymaster/KeyMint). Not the same thing as `fileencryption=...`. | **Not declared** in `recovery.fstab` or `twrp.flags`. `BOARD_USES_METADATA_PARTITION := false`. | **Unsupported** for sakura with the available vendor/kernel constraints documented below. Do not claim support. |

## 2. Current source configuration (actual)

- **`/data` fstab entries** (`device/xiaomi/sakura/recovery/root/system/etc/recovery.fstab`): two rows (f2fs first, ext4 second), both with fs_mgr flags
  `wait,check,encryptable=footer,fileencryption=ice,quota,formattable` (comma-separated). No `metadata_encryption=`, no `keydirectory=`.
- **Crypto build flags** (`device/xiaomi/sakura/BoardConfig.mk`): `TW_INCLUDE_CRYPTO := true`, `TW_INCLUDE_CRYPTO_FBE := true`, `BOARD_USES_METADATA_PARTITION := false`. Dead/unused variables `BOARD_USES_QCOM_FBE_DECRYPTION` and `TW_INCLUDE_FBE` are not used.
- **TEE/init integration** (`device/xiaomi/sakura/recovery/root/init.recovery.qcom.rc`, `device/xiaomi/sakura/recovery/root/init.recovery.qcom_decrypt.rc`, `device/xiaomi/sakura/device.mk`): device-provided init fragments are installed into the recovery ramdisk via `PRODUCT_COPY_FILES`; `init.recovery.qcom.rc` imports `/init.recovery.qcom_decrypt.rc`. The decryption rc starts the vendor TEE chain in order: `qseecomd` → QTI Keymaster 3.0 service → QTI Gatekeeper 1.0 service (exec paths and destinations are defined by the device tree/manifest; `tools/check_init_services.py` enforces path/manifest consistency). This tree does **not** use nonexistent upstream `qcom_decrypt` / `qcom_decrypt_fbe` product modules.
- **Vendor blobs** (`device/xiaomi/sakura/proprietary-files.txt`, `build/extract_blobs.sh`, `build/install_blobs.sh`, `build/check_crypto_blobs.sh`): proprietary TEE/HAL blobs are **not** committed. `0/20` are currently present in this workspace. Extraction is designed to be read-only from a user-supplied sakura Android 9 **fastboot** ROM and to record provenance/hashes locally under gitignored `vendor_blobs/`; installation generates a gitignored `blob_install.mk`. Without the required blobs, crypto-gated builds are refused by default (`build/check_crypto_blobs.sh --require`); `SAKURA_ALLOW_MISSING_CRYPTO=1` is an explicit non-decryption opt-out only.
- **Boot/kernel/partitions**: unchanged by this documentation audit (no boot parameters, kernel, DTB, addresses, bootdevice command line, or partition size modified).

## 3. `fileencryption=ice` checked against the pinned recovery and android-12.1 code

### 3.1 Pinned recovery parser — `bootable/recovery` @ `8d2aad19deb158e935d70ca5b648162c2b2831ee` (`fox_12.1`)

Read directly from that commit's `partition.cpp`:

| Code path | Behaviour |
|---|---|
| `TWPartition::Process_Fstab_Line()` | A line starting with `/dev/` is treated as the AOSP 5-column format (`fstab_version = 2`); column 4 is handed to `Process_FS_Flags()` and column 5 is stored as the TWRP flag string (`twflags`). |
| `TWPartition::Process_FS_Flags()` | Tokenises mount options with `strtok_r(..., ",", ...)` — commas only. |
| `TWPartition::Process_TW_Flags()` | Chooses the separator from the fstab format: `source_separator = ','` when `fstab_ver == 2`. So `encryptable=footer;fileencryption=ice` is **one malformed token** and both options are silently lost; the comma-separated form is what the pinned parser actually reads. |
| `TWFLAG_ENCRYPTABLE` | `case TWFLAG_ENCRYPTABLE: ... Crypto_Key_Location = str;` — the `footer` argument is retained as the crypto key location. |
| `TWFLAG_FILEENCRYPTION` | Sets the runtime props `fbe.contents` / `fbe.filenames` from the `fileencryption=` argument. The in-source comment reads: *"This flag isn't used by TWRP but is needed in 9.0 FBE decrypt — fileencryption=ice:aes-256-heh"*. For this fstab that yields `fbe.contents=ice` and an empty `fbe.filenames`. |
| FBE build gate | The FBE decryption code is compiled only under `TW_INCLUDE_FBE` (set by `TW_INCLUDE_CRYPTO_FBE := true` in this tree). FBE is detected at runtime from `/data/unencrypted/key/version` (`TWPartition::Decrypt_FBE_DE()`), and can be skipped with `OF_SKIP_FBE_DECRYPTION` / `OF_SKIP_FBE_DECRYPTION_SDKVERSION`. |
| Metadata decryption gate | `partitionmanager.cpp` compiles the metadata path only under `TW_INCLUDE_FBE_METADATA_DECRYPT`; it also needs `metadata_encryption=` / `keydirectory=` fstab data. **This tree enables neither the macro nor the flags.** So metadata-encrypted `/data` is not handled by this configuration. |

### 3.2 Android 12.1 fs_mgr / libfscrypt (the base `fox_12.1` is built on)

| Code | Behaviour |
|---|---|
| `system/core/fs_mgr/fs_mgr_fstab.cpp` (android-12.1) | The fs_mgr flag column is split on `,` (`Split(flags, ",")`). `encryptable=` sets `fs_mgr_flags.crypt = true` and `key_loc`; `fileencryption=` calls `ParseFileEncryption()`, setting the `file_encryption` flag and `encryption_options` to the argument. Android 12.1 contains **no** rejection of `encryptable` without `voldmanaged` (that check exists only in later AOSP releases). |
| `system/extras/libfscrypt/fscrypt.cpp` (android12-release) | `ParseOptionsForApiLevel()` maps the contents mode **`"ice"` to `FSCRYPT_MODE_PRIVATE` (127)** — a vendor-specific on-disk contents format, *not* "inline crypto". Inline crypto is requested by the separate `inlinecrypt` **mount** option; `fileencryption=ice` alone does not enable it. Default filenames mode stays `aes-256-cts`, and the policy version is `1` when `ro.product.first_api_level <= 29` (sakura's first API level is well below 29). |

### 3.3 What this establishes, and what it does not

- **Established:** the two `/data` rows use the token separator the pinned parser expects; `encryptable=footer` is retained as the crypto key location; `fileencryption=ice` reaches recovery as `fbe.contents=ice`; the FBE and metadata code paths exist behind build flags, and only the FBE one is enabled here.
- **Caveat, not changed:** `ice` selects the pre-Android-11 vendor `PRIVATE` contents format. It is the correct historical format for sakura (an Android 9 launch device) and for ROMs formatted with that vendor mode, but a ROM that formatted `/data` with the standard `aes-256-xts` format will not match this declaration. AOSP also documents `fileencryption=ice` as valid only for devices launched with Android 10 or lower. The flag is therefore left exactly as it is; which ROMs match is recorded as an unverified per-ROM item instead of being guessed.
- **Not established by any of the above:** that FBE decryption succeeds. That needs genuine vendor blobs, a built and verified image, a matching on-disk format, and device testing — none of which exist here.

## 4. Intended TEE / crypto integration (not runtime-proven)

The intended decryption stack for sakura is:
- **Kernel/platform basis:** 4.9 prebuilt kernel (fscrypt/f2fs capability as documented by project analysis) instead of R11's 3.18 stock kernel; Qualcomm TEE channel `/dev/qseecom`.
- **TEE userspace:** `qseecomd`.
- **HALs:** QTI **Keymaster 3.0** service (`android.hardware.keymaster@3.0-service-qti`) and QTI **Gatekeeper 1.0** service (`android.hardware.gatekeeper@1.0-service-qti`) with their required vendor libraries, as listed in `device/xiaomi/sakura/proprietary-files.txt`.
- **Recovery crypto build features:** `TW_INCLUDE_CRYPTO` and `TW_INCLUDE_CRYPTO_FBE` (OrangeFox/TWRP recovery crypto implementation in the pinned upstream trees).

**Runtime compatibility is unverified.** Required proprietary blobs are not present in this workspace (`0/20` extracted/installed), no production recovery image has been built/verified here, and no device testing has been performed. Do not claim Keymaster/Gatekeeper/QSEECom runtime compatibility, successful service startup, or decryption without genuine firmware blobs and on-device evidence.

## 5. Intended / unsupported / unknown configurations

| Android / ROM encryption configuration | Intended by current config? | Notes |
|---|---|---|
| **Android 9 (sakura stock era, e.g. MIUI 12 PD* builds), unencrypted `/data`** | Yes (mount/use) | Depends on normal mount/format behavior; not a decryption case. |
| **Android 9 legacy FDE (`encryptable=footer`)** | **Intended** | FDE footer flag present; same general mechanism family as R11. Requires correct TEE stack/blobs and device validation. **Unverified.** |
| **Android 10+ FBE without metadata encryption, `/data` formatted with the sakura vendor `ice` (`FSCRYPT_MODE_PRIVATE`) contents mode** | **Intended (best-effort target)** | FBE flag and FBE crypto build flags are configured; metadata encryption not declared. Requires correct blobs, compatible ROM/key state, and device validation. **Unverified.** |
| **FBE where `/data` was formatted with the standard `aes-256-xts` contents mode** | **Unknown / likely mismatch** | The fstab declares `fileencryption=ice`, so `fbe.contents=ice`; a standard-format `/data` would not share that on-disk format. Not changed here (no assumption-based edits); must be confirmed per ROM with a real device and an encrypted `/data`. |
| **FBE with metadata encryption** (`metadata_encryption=`, dm-default-key, etc.) | **No (unsupported)** | Not declared/configured. Sakura vendor/kernel constraints (KM 3.0 vendor, no dm-default-key support in the kernels relied on by this port) make this unsupported here. Do not advertise support. |
| **Other/unknown encryption combinations** (e.g. ROM-specific wrapped-key/metadata variants, adoptable-storage-specific cases, future formats) | **Unknown** | Treat as unsupported until analyzed and device-tested with evidence. |
| **Android 16 / 17 on sakura** | **Unknown / not applicable** | No sakura ROM/device-tree evidence established in this project for those releases; compatibility cannot be claimed. |

## 6. Verification status (executed checks only)

| Item | Status (current) | Evidence |
|---|---|---|
| Source fstab/config consistency (comma-separated `encryptable=footer,fileencryption=ice`, no metadata encryption declared, crypto flags/init wiring/static structure) | **PASS (static/config checks executed)** | `python3 tools/static_checks.py` → **PASS (50 checks)** on this tree in this workspace; expected warning: `0/20` proprietary blobs present, `DECRYPTION IS UNVERIFIED`. |
| Tooling/unit regression tests (extraction/install/init/ELF/sparse helpers, committed device-tree checks) | **PASS (executed)** | `python3 -m unittest discover -s tests -v` → **Ran 18 tests, OK** in this workspace (synthetic fixtures; not a genuine firmware extraction). |
| Parsing of the fstab flag column by the pinned recovery | **Verified by source inspection** | `bootable/recovery@8d2aad19deb158e935d70ca5b648162c2b2831ee` `partition.cpp`: `Process_TW_Flags()` uses `,` as the separator for AOSP-format (`fstab_ver == 2`) lines; `TWFLAG_ENCRYPTABLE` stores the key location; `TWFLAG_FILEENCRYPTION` sets `fbe.contents` / `fbe.filenames`. Runtime behaviour not verified. |
| `ice` meaning in the android-12.1 crypto library | **Verified by source inspection** | `system/extras/libfscrypt/fscrypt.cpp` (android12-release): `{"ice", FSCRYPT_MODE_PRIVATE}`; contents mode `ice` is vendor PRIVATE, not the `inlinecrypt` mount option. |
| Genuine firmware blob extraction/integration | **Not completed** | No genuine sakura Android 9 fastboot ROM available in this environment; `0/20` blobs extracted/installed. |
| Blob-dependent crypto gates with real blobs (`check_crypto_blobs.sh --require`, `check_init_services.py --require crypto`) | **Not executed with real blobs** | Cannot run meaningfully until genuine blobs are extracted/installed. |
| Production recovery image build and image verification | **Not done** | No compatible build host/image build performed. |
| Boot, service startup, FDE/FBE decryption on hardware | **Not tested** | No device testing performed. |

## 7. Operational cautions

- A configuration that declares FBE but lacks a working TEE/Keymaster/Gatekeeper chain can fail badly at runtime (e.g. recovery hanging at splash on encrypted `/data`). Do not infer working decryption from flags or from `keystore2` presence alone.
- `SAKURA_ALLOW_MISSING_CRYPTO=1` / workflow opt-out produces (if built) an explicitly **non-decrypting** artifact choice; it must never be labeled or described as decryption-capable.
- Never claim decryption works until a real build is produced, its image is verified, and on-device results are recorded in `testing/android-*/TEST_RECORD.md`.
