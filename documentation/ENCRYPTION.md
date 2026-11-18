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

## 3. `fileencryption=ice` and fs_mgr flag parsing (pinned recovery implementation)

**What was verified (source/config evidence):**
- The recovery fstab uses **comma-separated** fs_mgr flags: `encryptable=footer,fileencryption=ice,quota,formattable` on both `/data` rows. Repository checks enforce comma separation and reject `;` (`tools/static_checks.py`, and `build/verify_image.sh` for built images).
- Against the pinned OrangeFox recovery source used by this project, **`bootable/recovery` @ `8d2aad19deb158e935d70ca5b648162c2b2831ee`** (`fox_12.1`), `partition.cpp` defines and parses `fileencryption=` as `TWFLAG_FILEENCRYPTION` and `encryptable=` as `TWFLAG_ENCRYPTABLE` (e.g. flag table entries for `encryptable=` / `fileencryption=` and handling that recognizes `fileencryption=...` values such as `ice` forms). This confirms the pinned recovery partition parser recognizes the `fileencryption=` flag token used in the device fstab.

**What this means / does not mean:**
- The fstab flag syntax and tokenization are consistent with the pinned recovery parser and the project's static gates. This is **not** proof that FBE decryption will succeed on any ROM or device.
- `fileencryption=ice` is the inline-crypto/ICE FBE indicator commonly used for Qualcomm legacy devices in recovery fstabs. Its exact runtime behavior depends on the pinned recovery/crypto code paths, installed vendor blobs, kernel crypto/fscrypt/ICE support, and the actual on-disk encryption state of `/data`. No runtime claim is made here.

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
| **Android 10+ FBE without metadata encryption** (`fileencryption=ice`, fscrypt/ICE-capable kernel/ROM layout) | **Intended (best-effort target)** | FBE flag and FBE crypto build flags are configured; metadata encryption not declared. Requires correct blobs, compatible ROM/key state, and device validation. **Unverified.** |
| **FBE with metadata encryption** (`metadata_encryption=`, dm-default-key, etc.) | **No (unsupported)** | Not declared/configured. Sakura vendor/kernel constraints (KM 3.0 vendor, no dm-default-key support in the kernels relied on by this port) make this unsupported here. Do not advertise support. |
| **Other/unknown encryption combinations** (e.g. ROM-specific wrapped-key/metadata variants, adoptable-storage-specific cases, future formats) | **Unknown** | Treat as unsupported until analyzed and device-tested with evidence. |
| **Android 16 / 17 on sakura** | **Unknown / not applicable** | No sakura ROM/device-tree evidence established in this project for those releases; compatibility cannot be claimed. |

## 6. Verification status (executed checks only)

| Item | Status (current) | Evidence |
|---|---|---|
| Source fstab/config consistency (comma-separated `encryptable=footer,fileencryption=ice`, no metadata encryption declared, crypto flags/init wiring/static structure) | **PASS (static/config checks executed)** | `python3 tools/static_checks.py` → **PASS (50 checks)** on this tree in this workspace; expected warning: `0/20` proprietary blobs present, `DECRYPTION IS UNVERIFIED`. |
| Tooling/unit regression tests (extraction/install/init/ELF/sparse helpers, committed device-tree checks) | **PASS (executed)** | `python3 -m unittest discover -s tests -v` → **Ran 18 tests, OK** in this workspace (synthetic fixtures; not a genuine firmware extraction). |
| `fileencryption=ice` and `encryptable=` recognized by pinned recovery parser | **Verified by source inspection of pinned commit** | Checked `bootable/recovery@8d2aad19deb158e935d70ca5b648162c2b2831ee` (`partition.cpp`: `TWFLAG_FILEENCRYPTION` / `TWFLAG_ENCRYPTABLE` parsing). Runtime behavior not verified. |
| Genuine firmware blob extraction/integration | **Not completed** | No genuine sakura Android 9 fastboot ROM available in this environment; `0/20` blobs extracted/installed. |
| Blob-dependent crypto gates with real blobs (`check_crypto_blobs.sh --require`, `check_init_services.py --require crypto`) | **Not executed with real blobs** | Cannot run meaningfully until genuine blobs are extracted/installed. |
| Production recovery image build and image verification | **Not done** | No compatible build host/image build performed. |
| Boot, service startup, FDE/FBE decryption on hardware | **Not tested** | No device testing performed. |

## 7. Operational cautions

- A configuration that declares FBE but lacks a working TEE/Keymaster/Gatekeeper chain can fail badly at runtime (e.g. recovery hanging at splash on encrypted `/data`). Do not infer working decryption from flags or from `keystore2` presence alone.
- `SAKURA_ALLOW_MISSING_CRYPTO=1` / workflow opt-out produces (if built) an explicitly **non-decrypting** artifact choice; it must never be labeled or described as decryption-capable.
- Never claim decryption works until a real build is produced, its image is verified, and on-device results are recorded in `testing/android-*/TEST_RECORD.md`.
