# OrangeFox R12.0 for Xiaomi Redmi 6 Pro (sakura) — unofficial port

A device-specific port of **OrangeFox Recovery R12.0** to the Xiaomi Redmi 6 Pro
(`sakura`, Qualcomm MSM8953 / Snapdragon 625), built on the official
**`fox_12.1`** manifest, preserving the behaviour of the last official release
(**R11.0_5**) while extending it toward modern ROMs.

> **Status: source fixes applied, tooling tested, NOT built, NOT flashed, NOT
> tested on hardware.** The old ServerHive self-hosted runner has expired and is
> no longer referenced by the workflow. The crypto dependency chain is now
> reproducible (extract → install → gate → verify), but its firmware input has
> never been supplied here, so **no decryption claim is made**. Read
> `documentation/TEST_REPORT.md` before trusting any claim, and do not flash
> anything without your own rollback plan.

---

## What was actually established

| Question | Finding | Where |
|---|---|---|
| Is R11.0_5 authentic? | Yes — MD5 matches the official API record exactly; SHA-256 recorded | `REFERENCE_R11_ANALYSIS.md` §1 |
| What kernel did R11 ship? | Xiaomi stock **3.18.120-perf-gd85b39b**, GCC 4.9.x, built 2020-07-28 on Xiaomi's MIUI OTA builder | `KERNEL_ANALYSIS.md` §1 |
| Can that kernel support modern ROMs? | **No** — measured: no `fscrypt` (so no FBE), no f2fs, no EROFS | `KERNEL_ANALYSIS.md` §2 |
| Which manifest? | **`fox_12.1`** — it *is* R12.0; `fox_14.1` is unnecessary for this device | `SOURCE_AUDIT.md` §2 |
| Is the DTB sakura's? | Yes — 46 FDTs whose camera/panel nodes are sakura-specific (`sakura_imx486_ofilm`, `ili7807`, `nt36672`) | `REFERENCE_R11_ANALYSIS.md` §5 |
| Is the community R12 tree usable as-is? | Partly — it is **daisy-derived** (blobs + kernel) and its OrangeFox product makefile was never wired up | `SOURCE_REFERENCES.md` §B1, `DEVICE_COMPATIBILITY.md` §3 |
| Android 9–17 support? | **Not established as 9–17 decryption support.** Config declares FDE (`encryptable=footer`) + FBE without metadata (`fileencryption=ice`, vendor FSCRYPT_MODE_PRIVATE form); metadata encryption is **off by default** with an explicit opt-in that the shipped kernels cannot use (no `dm-default-key`). Inspected sakura trees show FDE-like (LOS 18.1) or `fileencryption=ice` (LOS 20/21/22.x) with no metadata, but A10/A12 formats and all runtime behaviour are **unverified**. **Android 16/17: no sakura ROM/device-tree evidence.** | `ANDROID_COMPATIBILITY.md`, `ENCRYPTION.md` |
| Boot diagnostics? | **Implemented in source, unit-tested (74 tests), not device-tested.** `sakura-diag` runs from init before the GUI, writes bounded/rotated redacted logs to `/tmp/sakura-diag` (and mirrors to `/cache/recovery` only when `/proc/mounts` proves `/cache` is mounted read-write), classifies critical/recoverable/unclassified, persists its counters across processes, and drives Settings → Error Logs (12 features: viewers, filters, copy, export, clear) plus an `! DIAG` badge via a pinned theme patch. `adb pull /tmp/sakura-diag` works even when the GUI never starts | `DIAGNOSTICS.md` |
| Decryption? | Source config declares FDE + FBE-without-metadata flags and TEE service wiring; metadata decryption is compiled in but **cannot work on this kernel** (`dm-default-key` absent in both available kernels). **0/20** proprietary QTI blobs present, no production image built, no hardware test — **decryption unverified** | `ENCRYPTION.md`, `IMAGE_AUDIT.md` |

## Repository layout

```
device/xiaomi/sakura/     the R12 device tree (the actual port)
  BoardConfig.mk          arch, kernel, partitions, crypto flags
  device.mk               ramdisk file installs + blob fragment include
  fox_sakura.mk           OrangeFox product (was missing upstream)
  twrp_sakura.mk          plain TWRP fallback product
  AndroidProducts.mk      lunch targets
  vendorsetup.sh          FOX_*/OF_* build vars ported from R11
  recovery/root/          fstab, twrp.flags, init.recovery.qcom.rc,
                          init.recovery.qcom_decrypt.rc (TEE services)
  proprietary-files.txt   required QTI crypto blobs + provenance warning
  prebuilt/README.md      kernel provenance and how to supply it
manifest/                 pinned refs + sync recipe
patches/                  pinned upstream theme patch + revision pin
build/                    check_deps, fetch_reference, fetch_kernel, sync,
                          extract_blobs, install_blobs, check_crypto_blobs,
                          build, verify_image, run-all
tools/                    bootimg.py, verify_dtb.py, elf.py, simg2img.py,
                          check_init_services.py, static_checks.py
tests/                    regression tests for the extraction toolchain
documentation/            full audit: sources, kernel, encryption, compatibility,
                          BUILD_FROM_CLEAN_CLONE.md, BUILD_TROUBLESHOOTING.md
testing/android-9..17/    per-ROM-generation test records (empty = untested)
```

`vendor_blobs/`, `device/xiaomi/sakura/blob_install.mk` and the installed
`recovery/root/system/{bin,lib64}` are **gitignored**: they hold proprietary
Xiaomi/Qualcomm binaries that only the user's own firmware can supply.

## Quick start

On a compatible Linux x86_64 host (>=45 GB free, >=8 GB RAM, not root), one
command does everything:

```bash
./build/check_deps.sh                          # optional, seconds: proves the host
./build/extract_blobs.sh --firmware sakura_*_images_*.tgz   # see below
./build/install_blobs.sh
./build/run-all.sh "$HOME/orangefox/fox_12.1"
```

`run-all.sh`, `sync.sh` and `build.sh` also apply the pinned theme patch
(`patches/0001-theme-sakura-diagnostics.patch`) through
`build/apply_patches.sh`. That step fails the build if the pinned upstream
context changed, instead of shipping a Settings page that does not exist.

`run-all.sh` runs the host preflight, static checks, the TEE blob gate, the
pinned sync, the kernel fetch + DTB verification, the single `recoveryimage`
build and the hard structural + init-service verification, then prints the
image path and SHA-256.

**The one input this repository cannot supply** is the vendor TEE chain
(`qseecomd`, QTI Keymaster 3.0, QTI Gatekeeper 1.0 + libraries). It is
proprietary, so `build/extract_blobs.sh` extracts it from *your own* sakura
Android 9 stock **fastboot** ROM (`V12.0.4.0.PDMMIXM` Global/India or
`V12.0.1.0.PDICNXM` China), verifies device identity and ELF architecture, and
records SHA-256 provenance under the gitignored `vendor_blobs/`. Without it the
build stops rather than producing an image that cannot decrypt; to build a
no-decryption image deliberately:

```bash
SAKURA_ALLOW_MISSING_CRYPTO=1 ./build/run-all.sh
```

Full step-by-step: [`documentation/BUILD_FROM_CLEAN_CLONE.md`](documentation/BUILD_FROM_CLEAN_CLONE.md).

Structural checks and the toolchain's own tests, no source needed:

```bash
python3 tools/static_checks.py
python3 -m unittest discover -s tests -v
```

Reference analysis (no root, no extra packages, ~46 MB):

```bash
./build/fetch_reference.sh
python3 tools/bootimg.py info reference/recovery.img
python3 tools/verify_dtb.py reference/unpacked/kernel   # FAILs: stock kernel has no fscrypt
```

Then run the device tests in `testing/android-N/` and fill in real results.

If the first build stops, read `documentation/BUILD_TROUBLESHOOTING.md` before
changing anything — it maps each likely Soong/make error to its actual cause.

## Key design decisions (and why)

1. **`fox_12.1`, not `fox_14.1`.** Sakura has no dynamic partitions, no AVB
   enabled, a real 64 MiB recovery partition and a VNDK 28 vendor. The official
   guide reserves 14.x for devices that *require* it.
2. **A 4.9 kernel, not R11's stock 3.18.** Stock has no `fscrypt`/f2fs, so it
   cannot serve FBE ROMs. This is evidence-driven, not "newer is better".
3. **No metadata encryption claims.** Neither kernel has `dm-default-key` and
   the vendor is Keymaster 3.0. Advertising it would be a lie. The opt-in
   configuration (`SAKURA_METADATA_ENCRYPTION=1`) exists so a future
   `dm-default-key` kernel needs no tree change, and stays off by default
   because a non-empty `keydirectory=` makes recovery treat a plain `/data` as
   encrypted (`ENCRYPTION.md` §6a).
4. **Sakura-only.** `FOX_TARGET_DEVICES="sakura,sakura_india"` is preserved
   (exported from `device/xiaomi/sakura/vendorsetup.sh`; R12 renamed it from
   `OF_TARGET_DEVICES`, which `orangefox.mk` now rejects).
   Daisy (Mi A2 Lite) is a different target and is explicitly excluded.
5. **No proprietary blobs committed.** The tree documents which blobs are
   needed, flags their unverified daisy provenance, and gives a licence-safe
   extraction procedure.

## Upstream

OrangeFox R12.0 sources: <https://gitlab.com/OrangeFox> ·
sync: <https://gitlab.com/OrangeFox/sync> ·
build guide: <https://wiki.orangefox.tech/dev/building>

This is an **unofficial** build. It is not affiliated with or endorsed by the
OrangeFox Recovery Project. OrangeFox is GPL-3.0; the device tree here is
provided under the same terms.
