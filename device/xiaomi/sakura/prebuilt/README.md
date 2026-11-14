# prebuilt/Image.gz-dtb

`BoardConfig.mk` sets:

```make
TARGET_PREBUILT_KERNEL := $(DEVICE_PATH)/prebuilt/Image.gz-dtb
```

**The binary itself is intentionally not committed here** (8.7 MB, and it is a
third-party compiled artifact). Supply it with `build/fetch_kernel.sh`.

## Why a 4.9 kernel and not R11's stock kernel

R11.0_5 shipped Xiaomi's stock `3.18.120-perf-gd85b39b`. Measured string probe
of that binary: **no `fscrypt`, no f2fs, no EROFS** — only ext4 + dm-crypt. That
makes FBE and f2fs `/data` impossible, so it cannot serve Android 10+ ROMs.
See `documentation/KERNEL_ANALYSIS.md`.

## Expected format

* `Image.gz` (gzip) with an **appended sakura multi-DTB** in the same kernel
  slot; boot header `dt_size` stays 0 (as in R11.0_5).
* Must contain the `sakura_*` camera nodes and the `ili7807` / `nt36672` panel
  nodes in the DTB.
* Must report a `Linux version 4.9.x` banner and contain `fscrypt_`, `F2FS`.

## Candidate (recommended, verified)

```
source: https://github.com/msm8953E/device_xiaomi_sakura_twrp
branch: ofx-12.1   (commit 7fde3f4faa61493b93fe9ade84a5e705d359c8a3)
path:   prebuilt/Image.gz-dtb
size:   8735584
sha256: d12f816aef3572be156596e0b0c5607c56b309eea4b3e06f052d8509b9867764
banner: Linux version 4.9.278-Mystique-Kernel-TWRP (root@83f6362a4550)
        (gcc version 12.0.0 20210729 (experimental) (Eva GCC))
date:   Fri Aug 13 20:29:24 UTC 2021
DTBs:   2 appended, containing sakura camera/panel nodes
```

Provenance caveat: that tree's README names its kernel source as
`TWRP-Mi-A2-Lite/twrp_kernel_xiaomi_daisy`, i.e. the build lineage is
daisy-side. The resulting **DTB is sakura-correct** (verified: all six
`sakura_*` camera nodes present), but the source lineage should be re-derived
from `msm8953E/kernel_xiaomi_msm8953@lineage-21` for a clean, attributable
build (see `documentation/KERNEL_ANALYSIS.md` §5).

## Rebuilding from source instead

```bash
# defconfigs confirmed present on lineage-21:
#   arch/arm64/configs/msm8953-perf_defconfig
#   arch/arm64/configs/xiaomi/sakura.config
make O=out ARCH=arm64 \
     msm8953-perf_defconfig xiaomi/xiaomi.config xiaomi/sakura.config
make O=out ARCH=arm64 -j"$(nproc)" Image.gz dtbs
# then append the sakura DTBs and keep the R11 boot header layout
```

After any replacement, verify before shipping:

```bash
python3 tools/bootimg.py info out/.../recovery.img     # cmdline, page size
python3 tools/verify_dtb.py  path/to/Image.gz-dtb      # sakura nodes present
```
