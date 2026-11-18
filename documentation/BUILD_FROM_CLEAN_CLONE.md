# Build OrangeFox R12.0 for sakura from a clean clone

This is the shortest complete path from `git clone` to a structurally verified
`recovery.img`, plus the one input the repository cannot supply (the vendor TEE
blobs) and exactly how to supply it.

Everything below is executed by scripts in this repository. There is no manual
make invocation, no `repo init` by hand and no SDK requirement.

---

## 1. What you need

| Requirement | Detail |
| --- | --- |
| Host | Linux x86_64, **not root** |
| Disk | **>= 45 GB** free where the source tree lives (~60 GB comfortable) |
| RAM | **>= 8 GB** (16 GB recommended) |
| Tools | see `documentation/DEPENDENCIES.md` §1 — `build/check_deps.sh` checks all of them and prints the `apt-get` line for anything missing |
| JDK | none needed up front: `build/setup_jdk11.sh` fetches a portable Temurin 11 into the workspace if the host has no JDK 11 |
| **Firmware** | a **sakura Android 9 stock fastboot ROM** (see §3). This is the one user-supplied input. |

A GitHub `ubuntu-latest` runner is **not** sufficient (~14 GB free, and the
build is refused by design rather than half-run). See
`documentation/DEPENDENCIES.md` §2.

## 2. Clone and build

```bash
git clone https://github.com/suryanshlabs/Latest-OrangefoxSakura-project.git
cd Latest-OrangefoxSakura-project

# Optional but recommended: prove the host can do this at all (seconds)
./build/check_deps.sh

# One command: preflight, static checks, blob gate, pinned sync,
# device tree + kernel, single recoveryimage build, hard verification
./build/run-all.sh "$HOME/orangefox/fox_12.1"
```

The build applies `patches/0001-theme-sakura-diagnostics.patch` through
`build/apply_patches.sh`. It is pinned to the upstream revision in
`patches/PINNED_REVISIONS` and fails the build if that context changed.
Do not edit the theme inside the source tree; regenerate the patch
(see `patches/README.md`).

`run-all.sh` needs no arguments; the tree location above is its default. It
stops at the first failure and prints the reason.

Steps it performs:

| # | Step | Script |
| --- | --- | --- |
| 1 | Host preflight (tools, disk, RAM, root) | `build/check_deps.sh` |
| 2 | Static regression checks (config, fstab, init paths, manifest, workflow) | `tools/static_checks.py` |
| 3 | TEE blob install + decryption gate | `build/install_blobs.sh`, `build/check_crypto_blobs.sh --require` |
| 4 | Pinned source sync (`fox_12.1` @ `73d4d94e…`, `bootable/recovery` @ `8d2aad19…`, `vendor/recovery` @ `1998cfca…`) | `build/sync.sh` |
| 5 | Device tree install + prebuilt kernel + DTB fingerprint check | `rsync`, `build/fetch_kernel.sh`, `tools/verify_dtb.py` |
| 6 | Decryption gate against the synced tree | `build/check_crypto_blobs.sh --require` |
| 7 | The single production build | `build/build.sh` |
| 8 | Structural + init-service verification | `build/verify_image.sh --require-crypto` |

## 3. The one input you must supply: vendor TEE blobs

Decryption on sakura needs the vendor's TEE chain — `qseecomd`, QTI Keymaster
3.0, QTI Gatekeeper 1.0, their HAL implementations and the QSEECom libraries.
They are Xiaomi/Qualcomm proprietary code, so this repository neither contains
nor downloads them.

Extract them once from **your own** stock firmware:

```bash
./build/extract_blobs.sh --firmware sakura_india_global_images_V12.0.4.0.PDMMIXM_20201104.0000.00_9.0_global_396957553f.tgz
./build/install_blobs.sh
./build/check_crypto_blobs.sh --require
```

* Accepted firmware: sakura Android 9 fastboot ROM (Global/India
  `V12.0.4.0.PDMMIXM`, China `V12.0.1.0.PDICNXM`), as `.tgz`, a directory, or a
  bare `vendor.img`. A *recovery* ROM zip has no `vendor.img` and cannot work.
* The extractor reads the image **read-only** with `debugfs` (no root, no loop
  mount), converts sparse to raw itself, and refuses any image whose
  `ro.product.device` is not `sakura`.
* It writes `vendor_blobs/` plus `MANIFEST.sha256` and `EXTRACTION_REPORT.md`
  (firmware SHA-256, `vendor.img` SHA-256, vendor fingerprint, per-file
  SHA-256). All of that is gitignored.
* To build *without* decryption for unrelated work:
  `SAKURA_ALLOW_MISSING_CRYPTO=1 ./build/run-all.sh` — the resulting image
  cannot decrypt `/data` and must not be reported as doing so. The script
  records `ro.sakura.crypto.mode=none` so the boot diagnostics do not report the
  absent TEE services as faults; a normal build records `full`.
* To declare metadata encryption (FBEv2) — only meaningful on a ROM that
  actually uses it, and **not usable on this kernel** (no `dm-default-key`, see
  `ENCRYPTION.md` §6a):
  `SAKURA_METADATA_ENCRYPTION=1 ./build/build.sh` adds
  `metadata_encryption=`/`keydirectory=` to both `/data` rows and a `/metadata`
  row. It is refused together with `SAKURA_ALLOW_MISSING_CRYPTO=1`. Inspect or
  revert with `python3 tools/configure_metadata.py --check|--disable`.

## 4. What a PASS means — and what it does not

Verified automatically:

* the image header (v0, 2048-byte pages, `0x80008000`/`0x81000000`), the
  `androidboot.bootdevice=7824900.sdhci` cmdline and the 64 MiB partition fit;
* the kernel/DTB is the sakura one and has `fscrypt` symbols;
* the ramdisk contains `system/bin/linker64`, `system/bin/recovery`, the init
  fragments, `twrp.flags` and the fstab, with comma-separated fs_mgr flags
  (`encryptable=footer,fileencryption=ice`) on both `/data` rows;
* **every init service** resolves: executable present at the exec'd path, ELF
  class/machine correct, `PT_INTERP` present in the ramdisk, and every
  transitive `DT_NEEDED` library resolvable;
* the TEE chain (`qseecomd` + QTI Keymaster 3.0 + QTI Gatekeeper 1.0) is present
  and started when the blob gate is enforced.

**Not** verified by any of this:

* that the recovery boots (needs the device);
* that `/data` actually decrypts (needs the device, an encrypted `/data` and the
  tests in `testing/android-*/`);
* that the image flashes safely.

`build/verify_image.sh` and CI both print that distinction; keep it.

## 5. If something fails

| Symptom | Cause / fix |
| --- | --- |
| `check_deps.sh` FAIL on a tool | run the printed `apt-get install` line (needs root once) |
| `need >=45 GB free` | use a bigger volume; `ccache` does not shrink `out/` |
| `TEE blob gate failed` | §3 above; read `vendor_blobs/EXTRACTION_REPORT.md` for what was missing |
| `vendor image is for 'daisy'` | wrong firmware; use a sakura Android 9 fastboot ROM |
| `service … executes /system/bin/…, which is missing` | `install_blobs.sh` not run, or a manifest destination disagrees with the init rc |
| `needs lib…, which does not resolve inside the ramdisk` | a required support library is absent from the image — usually an incomplete extraction |
| Soong/make errors during step 7 | `documentation/BUILD_TROUBLESHOOTING.md` maps each one to its cause |

## 6. Reproducing without the network twice

`build/sync.sh` pins every upstream revision; re-running it with
`--relink-only` reuses an existing tree. Keep the synced tree between builds
and only `vendor_blobs/` + this repository change.
