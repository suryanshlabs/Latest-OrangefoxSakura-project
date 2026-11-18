# Test report

## Verdict

**No build was produced and no device was touched.** Every claim below is
either a static analysis result on real artifacts or an explicit "not tested".

Per the brief's status vocabulary, the project is at **"Source verified"** for
the device configuration and **"Research only"** for runtime behaviour.

## 1. What was executed (and its result)

| # | Check | Command | Result |
|---|---|---|---|
| 1 | Official artifact integrity | `md5sum` / `sha256sum` on the downloaded ZIP | **PASS** — MD5 `5dff190fe5e86631bd58c049a9b5f924` equals the API value; SHA-256 `461e60c8…`; size 46 500 245 = API `size` |
| 2 | ZIP inventory | `unzip -l`, `find` | **PASS** — 22 files; no script executed |
| 3 | Boot image parse | `tools/bootimg.py info` | **PASS** — v0, page 2048, cmdline recovered, 44 687 360 bytes |
| 4 | Kernel/DTB split | `tools/bootimg.py unpack` | **PASS** — 1 gzip member (9 838 320 → 24 904 192) + 11 561 950 DTB bytes |
| 5 | DTB enumeration | custom scan | **PASS** — 46 FDTs |
| 6 | sakura fingerprint | `tools/verify_dtb.py` | 6/6 sakura camera nodes, ili7807 + nt36672 panels |
| 7 | Ramdisk extract | `tools/bootimg.py cpiotoc` | **PASS** — 2 322 entries (1 836 files, 201 symlinks) |
| 8 | Kernel capability probe | string probe | stock: fscrypt 0, f2fs 0, EROFS 0, dm-crypt yes, ICE yes |
| 9 | Community 4.9 kernel probe | same | fscrypt yes, f2fs yes, EROFS 0, dm-default-key 0 |
| 10 | Verifier regression gate | `verify_dtb.py` on both kernels | **PASS** on 4.9, **correctly FAILs** on stock 3.18 |
| 11 | Build scripts syntax | `bash -n build/*.sh` | **PASS** (all 5) |
| 12 | Upstream refs | `git ls-remote`, GitLab/GitHub API | **PASS** — all SHAs in `SOURCE_AUDIT.md` resolved live |

## 1b. Static checks executed for the current tree (no build)

Run on the committed tree; re-runnable anywhere with `python3` and `bash`. The checks below were **re-executed on the current tree in this audit session** (HEAD `1fb8154…` lineage, before this compatibility-research commit) with the results shown; re-run after doc-only commits to confirm. Synthetic test fixtures are **not** genuine sakura firmware.

```bash
python3 tools/static_checks.py   # PASS (50 checks), expected WARN: 0/20 proprietary blobs present
bash -n build/*.sh               # PASS (11 scripts)
python3 -m unittest discover -s tests -v   # PASS (18 tests, synthetic fixtures)
```

| Check | Result |
|---|---|
| `fstab`: no `;` delimiters in the fs_mgr flags column | PASS (was `encryptable=footer;fileencryption=ice`, now commas) |
| `fstab`: `/data` rows keep `encryptable=footer` and `fileencryption=ice` as separate tokens | PASS (2 rows: f2fs + ext4) |
| `fstab`/`twrp.flags`: no `metadata_encryption` | PASS |
| `BoardConfig.mk`: recovery partition 64 MiB, fstab path exists, `TW_THEME` set, soong theme export included, QCOM FBE enabled, metadata partition disabled | PASS |
| `fox_sakura.mk` inherits `vendor/twrp/config/common.mk`; `fox_sakura-eng` is a lunch target | PASS |
| `vendorsetup.sh`: sakura device guard, FBE not skipped, keymaster 3.0 pinned | PASS |
| workflow: manual only, runner selectable (no ServerHive self-hosted label), verification is a hard gate, artifacts uploaded on failure, stale image removed, static checks wired in | PASS |
| all `build/*.sh` pass `bash -n` and are executable; all `tools/*.py` compile | PASS |
| `device.mk` installs every `recovery/root` file via `PRODUCT_COPY_FILES` | PASS (previously only the fstab was installed, so the init fragments and `twrp.flags` never reached the ramdisk) |
| `BoardConfig.mk` uses the variables the pinned tree reads (`TW_INCLUDE_CRYPTO`, `TW_INCLUDE_CRYPTO_FBE`) and no dead ones | PASS (removed `BOARD_USES_QCOM_FBE_DECRYPTION`, `TW_INCLUDE_FBE`) |
| `device.mk` no longer requests the nonexistent `qcom_decrypt`/`qcom_decrypt_fbe` modules | PASS |
| init: every import target exists, every service executable path is absolute, matches the manifest destination and (once installed) resolves its libraries | PASS via `tools/check_init_services.py` |
| QTI crypto blob availability | **all required blobs absent** (no firmware supplied) — `DECRYPTION: UNVERIFIED`, and `build.sh` refuses to build unless `SAKURA_ALLOW_MISSING_CRYPTO=1` |
| workflow: decryption gate + explicit `allow_missing_crypto` opt-out | PASS |

What this does **not** prove: that the source syncs, that Soong builds, that the
image boots, or that any decryption works.

## 1c. Toolchain tests executed (new extraction workflow)

```bash
python3 -m unittest discover -s tests -v      # 18 tests
```

| Area | What is exercised | Result |
|---|---|---|
| `tools/elf.py` | AArch64 header, `PT_INTERP`, `DT_NEEDED`, `DT_SONAME`; 32-bit and non-ELF rejection | PASS |
| `tools/simg2img.py` | Android sparse → raw roundtrip, raw passthrough, `--info` | PASS |
| `tools/check_init_services.py` | resolvable ramdisk; missing library; dangling import; missing interpreter; crypto requirement | PASS |
| `build/extract_blobs.sh` | end-to-end against a real ext4 `vendor.img` read via `debugfs`: extraction of required + optional files, checksum manifest (`sha256sum -c`), report contents, `--dry-run`, wrong-device refusal (daisy), missing required file, wrong architecture | PASS |
| `build/install_blobs.sh` | install modes (0755/0644), generated `PRODUCT_COPY_FILES`, `--clean`, refusal without blobs | PASS |
| committed device tree | init scan clean; manifest destinations equal the exec'd service paths | PASS |

The firmware used for the end-to-end tests is **synthetic** (ELF/`build.prop`
fixtures built by `tests/support.py`), because no genuine sakura ROM is
available here. That proves the workflow's logic, not sakura's actual blobs.

## 2. What was NOT executed

| Not done | Why |
|---|---|
| `repo sync` of `fox_12.1` | needs ≥45 GB; sandbox has 9.5 GB |
| Kernel build | no toolchain (aarch64 GCC/clang), no 20+ GB build dir |
| OrangeFox build (`mka recoveryimage`) | needs the synced tree; also no `java` |
| Booting the recovery | no hardware — the phone is not connected |
| Any decryption test | requires hardware + an encrypted `/data` |
| ADB / MTP / OTG / touch / display | requires hardware |
| Flashing anything | **explicitly not authorized** |

Consequence: **no feature may be reported as working.** In particular
"decryption works", "MTP works", "boots on Android 15" are all unsupported
statements for this project today.

## 3. Feature preservation: R11 → R12 (config-level audit)

This is a *configuration* comparison, not a functional test. R11 values come
from `META-INF/debug/fox_build_vars.txt` in the official ZIP.

| Feature | R11.0_5 | R12 port | State |
|---|---|---|---|
| Fox Dark / Fox White themes | default R11 set | R12 upstream themes (SVG) | inherited from upstream Recovery tree |
| SVG rendering / new icon system | R11 icon set | R12 upstream | inherited |
| Gesture navigation | R12-only feature | enabled by R12 | inherited |
| File manager, Terminal | present | present | inherited |
| Password protection | present | present | inherited |
| ZIP / ROM install | present | present | inherited |
| Magisk install & patching | `OF_USE_MAGISKBOOT=1`, `OF_USE_NEW_MAGISKBOOT=1`, Magisk.zip in FoxFiles | same vars preserved | preserved in config |
| ADB / ADB sideload | present | present | untested |
| MTP | present | present | untested |
| USB OTG | `/usb_otg` + `/usb_otg` storage flag | preserved in twrp.flags | untested |
| Internal storage mount | `/data` | f2fs + ext4 rows | untested |
| External storage | `/sdcard1`, `/external_sd` | preserved | untested |
| Backup / restore | `OF_QUICK_BACKUP_LIST` | preserved | untested |
| Partition mount/format | ext4 + emmc | + f2fs | untested |
| Encryption | FDE footer only (`OF_SKIP_FBE_DECRYPTION=1`) | Source config declares FDE footer + FBE (`fileencryption=ice`) flags and TEE service wiring; no metadata encryption declared | **unverified** (0/20 blobs, no built image, no hardware test) |
| Recovery logs | present | present | untested |
| Reboot options | present | present | untested |
| OTA-related | `OF_OTA_RES_DECRYPT`, MIUI OTA vars | preserved | untested |
| App manager | not in R11 | `FOX_ENABLE_APP_MANAGER=1` | added (R12 feature) |
| LP tools | not in R11 | `OF_ENABLE_LPTOOLS=1` | added (R12 feature) |
| AromaFM | `FOX_DELETE_AROMAFM=1` | preserved | preserved |

No OrangeFox feature was disabled to make the build succeed — no build exists
yet, so there was nothing to work around.

## 4. How to complete this report

1. Build on a qualifying host (`BUILD_INSTRUCTIONS.md`).
2. `./build/verify_image.sh` → must PASS structurally.
3. Back up the current working recovery (rollback path) — e.g. dump
   `/dev/block/bootdevice/by-name/recovery` from a working recovery.
4. For each Android generation, fill `testing/android-N/TEST_RECORD.md` with
   observed results only.
5. Update the matrix in `ANDROID_COMPATIBILITY.md` with the achieved status.

Only after that may this file claim anything beyond "Source verified".
