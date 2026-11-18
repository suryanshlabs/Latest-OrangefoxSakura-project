# Android 9–17 compatibility (evidence-based)

## 0. Headline (no unsupported claims)

- **Implemented in this repo's current config (source only):** a single recovery configuration declaring legacy FDE (`encryptable=footer`) and FBE (`fileencryption=ice`) on both `/data` rows, with `TW_INCLUDE_CRYPTO`/`TW_INCLUDE_CRYPTO_FBE` and a device TEE init chain (qseecomd → QTI Keymaster 3.0 → QTI Gatekeeper 1.0). **No metadata encryption flags are declared.** See `ENCRYPTION.md` §2–§4.
- **Not established:** no genuine sakura vendor blobs are present (**0/20**), no production recovery image has been built or verified here, and no boot or decryption test has been performed on any device/ROM. Decryption is **unverified** for every Android version.
- **No evidence for Android 16/17 on sakura:** no genuine sakura ROM or device tree for Android 16 or 17 was found in the sources checked (see §2). Those generations are **Research only / Unknown**.

## 1. Current implementation audit (what is actually implemented)

| Area | Actual state (inspected) | Status |
|---|---|---|
| `device/xiaomi/sakura/recovery/root/system/etc/recovery.fstab` | `/data` f2fs + ext4 rows both carry `wait,check,encryptable=footer,fileencryption=ice,quota,formattable` (commas). No `metadata_encryption=`, no `keydirectory=`. Comments note `ice` ≠ inlinecrypto and that metadata encryption is not declared. | Implemented (config) |
| `device/xiaomi/sakura/BoardConfig.mk` | `TW_INCLUDE_CRYPTO := true`, `TW_INCLUDE_CRYPTO_FBE := true`, `BOARD_USES_METADATA_PARTITION := false`. No `PRODUCT_ENFORCE_VINTF_MANIFEST`. Boot/kernel/partition/addresses unchanged. | Implemented (config) |
| `device/xiaomi/sakura/device.mk` | Installs init fragments and `twrp.flags` via `PRODUCT_COPY_FILES`; includes gitignored `blob_install.mk` with `-include`. No `qcom_decrypt`/`qcom_decrypt_fbe` packages. | Implemented (config) |
| `recovery/root/init.recovery.qcom.rc` | Creates bootdevice symlink, sets QSEE/ion perms, imports `/init.recovery.qcom_decrypt.rc`. | Implemented (config) |
| `recovery/root/init.recovery.qcom_decrypt.rc` | Defines `qseecomd`, `android.hardware.keymaster@3.0-service-qti`, `android.hardware.gatekeeper@1.0-service-qti` (paths under `/system/bin`); starts in dependency order. | Implemented (config) |
| `proprietary-files.txt` / `build/extract_blobs.sh` / `install_blobs.sh` / `check_crypto_blobs.sh` | Manifest lists **20** proprietary entries (7 required, 13 optional) for QSEECom/KM3.0/GK1.0 chain with provenance/destination rules; scripts extract/install/gate blobs. **0/20 present in this workspace.** | Tooling implemented; blobs not supplied |
| `documentation/ENCRYPTION.md` | Distinguishes FDE/FBE/metadata; cites pinned recovery parser and android-12.1 `libfscrypt` (`ice` → `FSCRYPT_MODE_PRIVATE`); states metadata unsupported and decryption unverified. | Documented |
| `testing/android-9..android-17/TEST_RECORD.md` | Template records present for each generation; all **not tested**. | Placeholders present |

## 2. Per-generation research (actual sakura sources inspected where available)

Sakura (Redmi 6 Pro) launched on Android 8.1 (API 27) and received official MIUI 12 on Android 9 (e.g. `V12.0.4.0.PDMMIXM` global / `V12.0.1.0.PDICNXM` China). Custom ROM activity is sparse; modern builds are typically unified with daisy in the `xiaomi-msm8953-devs` trees.

Evidence inspected (fstab userdata flags) — public device/common trees:

| Source (branch) | Android era | `/data` fs_mgr encryption flags observed | Metadata flags |
|---|---|---|---|
| `TeamWin/android_device_xiaomi_sakura` (`android-8.1`, `twrp.fstab`) | 8.1/9 stock-era TWRP | `flags=encryptable=footer;length=-16384` (TWRP syntax) | none |
| `xiaomi-msm8953-devs/android_device_xiaomi_msm8953-common` `lineage-18.1` `rootdir/etc/fstab.qcom` | Android 11 era (LOS 18.1) | `encryptable=footer,quota` (f2fs+ext4) | none declared |
| `xiaomi-msm8953-devs/android_device_xiaomi_msm8953-common` `lineage-20` `rootdir/etc/fstab.qcom` | Android 13 era (LOS 20) | `fileencryption=ice,quota` (f2fs+ext4) | none declared |
| `xiaomi-msm8953-devs/android_device_xiaomi_msm8953-common` `lineage-21` `rootdir/etc/fstab.qcom` | Android 14 era (LOS 21) | `fileencryption=ice,quota` (f2fs+ext4) | none declared |
| `xiaomi-msm8953-devs/android_device_xiaomi_daisy` `lineage-22.0/22.1/22.2` `rootdir/etc/fstab.qcom` (sakura unified with daisy in this org; sakura partitions conditional in BoardConfig) | Android 15 era (LOS 22.x) | `fileencryption=ice,quota` (f2fs) / `fileencryption=ice,quota,formattable` (ext4) | none declared |

Notes: `fileencryption=ice` (shorthand, no explicit filenames mode/version) means contents mode `ice` as parsed by libfscrypt; with sakura `ro.product.first_api_level` <= 29 the default fscrypt policy is v1 and filenames default `aes-256-cts` per AOSP/libfscrypt behaviour. None of the inspected sakura/daisy/msm8953-common fstabs above declare `metadata_encryption=` or `keydirectory=`.

## 3. Compatibility matrix (per Android generation)

Status vocabulary used: **Research only · Source verified · Build verified · Boot tested · Feature tested · Decryption tested · Fully validated.** No row can exceed **Source verified** here because no production image was built and no hardware test was performed.

| Android | Genuine sakura ROM/device-tree evidence (checked) | Encryption observed/configured in sources | Current recovery config relevance | Status | Gaps |
|---|---|---|---|---|---|
| **9** | Stock MIUI 12 (PD* builds) exists; stock-era TWRP uses FDE footer. `sakura-o-oss`/`sakura-p-oss` kernels in Xiaomi Kernel OpenSource. | Legacy FDE (`encryptable=footer` / `encryptable=footer,length=-16384` in TWRP). | `encryptable=footer` declared; TEE chain (KM3.0/GK1.0/qseecomd) configured in source. Matches historical model. | **Source verified** (config/research only for runtime) | 0/20 blobs, no build, no boot/decryption test. |
| **10** | No definitive sakura-specific LOS19/A10 fstab located in this audit; some A10-era msm8953 ports existed historically but exact sakura userdata flags not confirmed from source here. | **Unknown from inspected sakura sources.** FBE without metadata is plausible on this platform; cannot be asserted per-ROM. | `fileencryption=ice` row present; would only apply if ROM formatted with matching `ice`/FSCRYPT_MODE_PRIVATE content format and no metadata encryption. | **Research only** | No per-ROM source proof, 0/20 blobs, no build/test. |
| **11** | crDroid 7.9 (2021, A11) widely cited as last A11 build; `xiaomi-msm8953-devs` `lineage-18.1` common fstab available. | Common LOS18.1 fstab: `encryptable=footer` (no fileencryption). Actual crDroid 7.9 sakura userdata format not re-verified from its exact ROM image here. | Footer/FDE path present in config. | **Research only** (source evidence mixed/indirect) | Exact per-ROM on-disk format unconfirmed; 0/20 blobs, no build/test. |
| **12** | No direct sakura LOS19 fstab evidence located in inspected repos; lineage-19 branch not present in checked xiaomi-msm8953-devs common/daisy trees. | **Unknown from inspected sakura sources.** | FBE row present but on-disk format/metadata per ROM unknown. | **Research only** | No sakura A12 fstab evidence found; no build/test. |
| **13** | `xiaomi-msm8953-devs/android_device_xiaomi_msm8953-common` `lineage-20` fstab (used by sakura/daisy ecosystem). | `fileencryption=ice,quota`, no `metadata_encryption`, no `keydirectory`. | Matches declared `fileencryption=ice` (format caveat: vendor `ice`/FSCRYPT_MODE_PRIVATE, v1 default for first_api_level<=29) **if** ROM uses this format. | **Source verified** (fstab flags) / runtime **unverified** | 0/20 blobs, no build, no boot/decryption test; format match per installed userdata unproven. |
| **14** | `xiaomi-msm8953-devs` common `lineage-21` fstab; sakura A14 ROMs reported historically (e.g. Matrixx/SuperiorExtended) but their exact fstabs not fetched here. | Common LOS21 fstab: `fileencryption=ice,quota`, no metadata encryption. | Same as Android 13. | **Source verified** (common fstab) / runtime **unverified** | Same gaps as 13. |
| **15** | `xiaomi-msm8953-devs/android_device_xiaomi_daisy` `lineage-22.0/22.1/22.2` fstabs (sakura unified); XDA lineage-22.2 sakura notes "FBE build, don't use twrp for these builds". | `fileencryption=ice,quota` (+formattable on ext4), no metadata encryption. | Same declared form; ROM warns TWRP problematic — decryption/compatibility especially uncertain. | **Source verified** (fstab flags) / runtime **unverified** | 0/20 blobs, no build, no boot/decryption test; upstream ROM discourages TWRP. |
| **16** | No sakura ROM or device tree found (checked xiaomi-msm8953-devs branches, web search). | **Unknown / no evidence.** | N/A. | **Research only / Unknown** | No sakura A16 evidence; do not claim support. |
| **17** | No sakura ROM or device tree found. | **Unknown / no evidence.** | N/A. | **Research only / Unknown** | No sakura A17 evidence; do not claim support. |

## 4. FBE format compatibility (critical)

- The fstab declares `fileencryption=ice` (unchanged). Per pinned recovery `partition.cpp` (`8d2aad19`) this sets `fbe.contents=ice`; per android-12.1 `libfscrypt/fscrypt.cpp`, `"ice"` maps to `FSCRYPT_MODE_PRIVATE` (vendor contents format), not "inline crypto" and not standard `aes-256-xts`. Filenames default to `aes-256-cts`; policy defaults to v1 for `ro.product.first_api_level <= 29`.
- **Not proven equivalent to:** standard `aes-256-xts` contents, Adiantum contents, `aes-256-heh`/`aes-256-hctr2` filenames, v2 policy, or any metadata-encrypted layout. A ROM formatted with a different contents/filenames mode, policy version, or metadata encryption will **not** be compatible just because Android version matches.
- **Changing fstab does not convert existing encrypted userdata.** No `ice`→`aes`/other change is made here (no proof). Multiple conflicting `/data` entries or SDK-version-based format guessing are unsafe and not implemented.
- **Single-config conclusion:** one config can declare footer+`ice` FBE, but it cannot be claimed to decrypt every ROM format. Without per-ROM proof and real blobs/tests, safe multi-format/runtime selection is **not implemented**.

## 5. Metadata encryption (reconfirmed)

- Inspected sakura/common fstabs (LOS 18.1/20/21/22.x) declare **no** `metadata_encryption=` / `keydirectory=`. This repo declares none and sets `BOARD_USES_METADATA_PARTITION := false`; the pinned recovery already compiles the metadata path (`-DTW_INCLUDE_FBE_METADATA_DECRYPT` + `libvold`) whenever crypto is on, so what was missing was only fstab data — now an explicit opt-in (`SAKURA_METADATA_ENCRYPTION=1`). Documented vendor/kernel constraints (KM 3.0-era vendor, no `dm-default-key` in either kernel relied on here) mean metadata-encrypted `/data` still **cannot be decrypted on this device**. **Off by default, wired but blocked.**

## 6. TEE dependency chain (sakura Android 9 vendor, intended)

- Manifested services/libraries (20 entries): `qseecomd`, `android.hardware.keymaster@3.0-service-qti`, `android.hardware.gatekeeper@1.0-service-qti`, `android.hardware.keymaster@3.0-impl-qti.so`, `android.hardware.gatekeeper@1.0-impl-qti.so`, `keystore.msm8953.so` (opt), `gatekeeper.msm8953.so` (opt), `libQSEEComAPI.so`, `libkeymasterdeviceutils.so`, plus optional QTI libs (`libGPreqcancel*`, `libSecureUILib`, `libStDrvInt`, `libdiag`, `libdrmfs`, `libdrmtime`, `libqisl`, `librpmb`, `libssd`, `libtime_genoff`).
- **Real blobs present:** **0/20**. No Daisy binaries fabricated/substituted. Genuine sakura Android 9 fastboot firmware not available here → real crypto integration **blocked**.

## 7. Checks executed (this audit session)

- `python3 tools/static_checks.py` → **PASS (all checks)**, expected WARN `0/20` blobs.
- `python3 -m unittest discover -s tests` → **Ran 18 tests, OK** (synthetic fixtures; **not** real sakura firmware tests).
- No production image built; no hardware boot/feature/decryption tests.

## 8. Preserved (unchanged)

Kernel/prebuilt, DTB, boot params, kernel base/pagesize/tags/ramdisk offsets, mkbootimg args, bootdevice cmdline, recovery partition size, and known boot fixes were not modified.
