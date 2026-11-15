# OrangeFox R12.0 for Xiaomi Redmi 6 Pro (sakura) — unofficial port

A device-specific port of **OrangeFox Recovery R12.0** to the Xiaomi Redmi 6 Pro
(`sakura`, Qualcomm MSM8953 / Snapdragon 625), built on the official
**`fox_12.1`** manifest, preserving the behaviour of the last official release
(**R11.0_5**) while extending it toward modern ROMs.

> **Status: design + source audit complete. NOT built, NOT flashed, NOT tested
> on hardware.** Nothing here has been validated on a device. Read
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
| Android 9–17 support? | 9 solid, 10–15 plausible, **16/17 no ROM exists at all** | `ANDROID_COMPATIBILITY.md` |
| Decryption? | FDE + FBE-without-metadata achievable; **metadata encryption impossible** on this vendor/kernel | `ENCRYPTION.md` §4 |

## Repository layout

```
device/xiaomi/sakura/     the R12 device tree (the actual port)
  BoardConfig.mk          arch, kernel, partitions, crypto flags
  device.mk               qcom_decrypt + qcom_decrypt_fbe, recovery modules
  fox_sakura.mk           OrangeFox product (was missing upstream)
  twrp_sakura.mk          plain TWRP fallback product
  AndroidProducts.mk      lunch targets
  vendorsetup.sh          FOX_*/OF_* build vars ported from R11
  recovery/root/          fstab, twrp.flags, init.recovery.qcom.rc
  proprietary-files.txt   required QTI crypto blobs + provenance warning
  prebuilt/README.md      kernel provenance and how to supply it
manifest/                 pinned refs + sync recipe
build/                    fetch_reference, fetch_kernel, sync, build, verify_image
tools/                    bootimg.py, verify_dtb.py (dependency-free)
documentation/            full audit: sources, kernel, encryption, compatibility,
                          plus BUILD_TROUBLESHOOTING.md (the Soong/first-build issues)
testing/android-9..17/    per-ROM-generation test records (empty = untested)
```

## Quick start

```bash
# 1. Reproduce the reference analysis (no root, no extra packages, ~46 MB)
./build/fetch_reference.sh
python3 tools/bootimg.py info reference/recovery.img
python3 tools/verify_dtb.py reference/unpacked/kernel   # FAILs: stock kernel has no fscrypt

# 2. Supply a 4.9 sakura kernel (verified, sha256-pinned)
./build/fetch_kernel.sh

# 3. Sync OrangeFox R12.0 (needs >=45 GB free; hours)
./build/sync.sh "$HOME/fox_12.1"

# 4. Build and structurally verify
./build/build.sh "$HOME/fox_12.1"
./build/verify_image.sh "$HOME/fox_12.1"
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
   the vendor is Keymaster 3.0. Advertising it would be a lie.
4. **Sakura-only.** `OF_TARGET_DEVICES="sakura,sakura_india"` is preserved.
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
