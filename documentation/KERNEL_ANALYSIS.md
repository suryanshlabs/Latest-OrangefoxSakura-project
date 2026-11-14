# Kernel analysis — sakura (MSM8953)

## 0. Summary

| Question | Answer | Confidence |
|---|---|---|
| Which kernel is in R11.0_5? | Xiaomi **stock MIUI-OTA** `3.18.120-perf-gd85b39b`, GCC 4.9.x, built 2020-07-28 | **Certain** (version string in the binary) |
| Is that kernel's source recoverable? | Lineage identified (`sakura-p-oss`, 3.18.120); the exact commit `d85b39b` is **not** in the public MiCode mirror | Certain about the negative |
| Can the stock kernel be reused for R12.0? | **No**, not if FBE or f2fs support is required — it has neither | Certain (string evidence, consistent with R11's ext4-only fstab) |
| Which kernel should the port use? | A **4.9.278** MSM8953 kernel built from the LineageOS-lineage source, with sakura defconfig, appended multi-DTB | Recommended, with caveats |
| Does a 4.9 sakura kernel support EROFS? | **No** (neither kernel does) | Certain for the two binaries examined |

## 1. The kernel actually packaged in R11.0_5

```
Linux version 3.18.120-perf-gd85b39b (builder@c3-miui-ota-bd116.bj)
(gcc version 4.9.x 20150123 (prerelease) (GCC) )
#1 SMP PREEMPT Tue Jul 28 12:13:36 CST 2020
```

* `3.18.120` — Xiaomi's MSM8953 line for sakura (Android 8.1 → 9). Note this is
  **3.18, not 4.9**; many sakura recovery guides assume 4.9 and are wrong for
  the stock ROM.
* `builder@c3-miui-ota-bd116.bj` — Xiaomi MIUI OTA build host.
* `gcc 4.9.x 20150123` — pre-clang AArch64 GCC.
* `-perf-gd85b39b` — MIUI's localversion from commit `d85b39b`.
* Build date 2020-07-28 corresponds to the MIUI 12 / Android 9
  (`V12.0.x.x.PDICNXM` / `PDMMIXM`) release line.

Layout inside `recovery.img` (see `REFERENCE_R11_ANALYSIS.md` §5): the boot
header's `dt_size` is **0**, and the DTB is appended *inside* the kernel slot,
after the gzip member: 46 concatenated FDTs, 11 561 950 bytes. This is the
Xiaomi/Qualcomm `Image.gz-dtb` convention and must be reproduced exactly.

### Source linkage attempt

* `MiCode/Xiaomi_Kernel_OpenSource` provides `sakura-o-oss` and `sakura-p-oss`
  (both resolve, HTTP 200 via the GitHub API).
* Querying the API for commit `d85b39b` in that repository returns
  *"No commit found for SHA: d85b39b"*.
* Interpretation: Xiaomi's public OSS drop does not contain the exact MIUI
  release-branch commit that produced this binary. **Do not claim the source
  was recovered.** What *is* established: kernel line (3.18.120), vendor build
  identity, toolchain family, and that the public `sakura-p-oss` branch is the
  nearest available source lineage.

## 2. Capability comparison (measured, not assumed)

Probe method: decompress each `Image` and count subsystem-specific strings.
Strong signal for filesystems; weak for genuinely optional code.

| Capability | stock 3.18.120 | ofx-12.1 prebuilt 4.9.278 |
|---|---|---|
| ext4 | yes | yes |
| **f2fs** | **no** | **yes** |
| EROFS | no | no |
| **fscrypt (FBE)** | **no** | **yes** |
| dm-crypt (FDE) | yes | yes |
| dm-verity | yes | yes |
| dm-default-key (metadata encryption) | no | no |
| ICE (Qualcomm inline crypto) | yes | yes |
| sdcardfs | yes | yes |
| quota | yes | yes |
| zstd | no | yes |

Why this matters, concretely:

* R11's `/data` is `ext4` + `encryptable=footer` **because** the stock kernel
  has no f2fs and no fscrypt. The fstab was not a lazy choice; it is the only
  thing that kernel can do.
* Any ROM that formats `/data` as f2fs, or that uses **FBE**, cannot be handled
  by a recovery built on the stock kernel. FBE is the default for Android 10+
  and the sakura LineageOS 22.2 thread explicitly states *"FBE build, don't use
  twrp for these builds"*.
* Therefore reusing the stock kernel would silently cap the port at legacy
  FDE/FDE-era ROMs — it would fail the "Android 9–17" requirement at the first
  FBE ROM. This is the evidence that justifies a kernel change; it is not a
  "newest is better" choice.

## 3. The kernel used by the 2024 community R12 attempt

`msm8953E/device_xiaomi_sakura_twrp@ofx-12.1` ships
`prebuilt/Image.gz-dtb` (8 735 584 bytes, SHA-256
`d12f816aef3572be156596e0b0c5607c56b309eea4b3e06f052d8509b9867764`):

```
Linux version 4.9.278-Mystique-Kernel-TWRP (root@83f6362a4550)
(gcc version 12.0.0 20210729 (experimental) (Eva GCC) )
#1 SMP PREEMPT Fri Aug 13 20:29:24 UTC 2021
```

* One gzip member (8 154 717 → 21 549 064 bytes) + **2 appended DTBs**
  (580 867 bytes), still containing all six `sakura_*` camera nodes and the
  `ili7807` / `nt36672` panels — i.e. sakura-correct, just a smaller DTB set.
* Built with **Eva GCC 12** in a container (`root@83f6362a4550` → Docker hostname).
* Adds f2fs, fscrypt, zstd, lz4. Still **no EROFS** and **no dm-default-key**.

This is direct evidence that a 4.9 kernel keeps sakura booting while adding the
capabilities R12 needs, and that a **2-DTB** set is sufficient on this device
(a useful size optimisation, but only if those two DTBs are the right ones for
sakura + sakura_india; that is not proven here, so the port prefers the full
proven DTB set — see §5).

## 4. Candidate kernel sources (verified refs)

| Repository | Branch | Commit | Notes |
|---|---|---|---|
| https://github.com/msm8953E/kernel_xiaomi_msm8953 | `lineage-21` | `52b67cb32ac009d366b632221d5fd381b6b7b55c` | 4.9 MSM8953 tree, the one the A14/A15 device trees target |
| same | `14` | `1e436c417f3e0d6fb32d6cfbc88ff7c3fc4cd7da` | A14 branch |
| same | `metadata-wip` | `837245365d14c3518e099fd328a2747d070887a7` | experiment; **not verified**, do not use for a release |
| https://github.com/ndrancs/kernel_xiaomi_sakura | `lineage-17.0` | `d452e25d01d7fcf2ba6a9dc3a92fb3fca0dd2503` | sakura-specific, 4.9 |
| same | `lineage-16.0` | `f069dcfecf1e732f6bf979565ce8e3ef5c24d301` | Android 9 era |
| same | `lineage-16.0-4.9` | `3cc13a0bae322df973eef285f25cbf2bdea9a7b1` | 4.9 on the A9 tree |
| https://github.com/mahajant99/kernel_xiaomi_msm8953 | `lineage-17.1` | `5b5dd1d44c454a5491b42ecff6aae06217c8e738` | alternative 4.9 |
| https://github.com/MiCode/Xiaomi_Kernel_OpenSource | `sakura-p-oss` / `sakura-o-oss` | branch exists; exact commit unknown | reference only — stock source lineage |

The A15 device tree (`msm8953E/device_xiaomi_sakura@A15`) declares:

```make
TARGET_KERNEL_SOURCE := kernel/xiaomi/msm8953
TARGET_KERNEL_CONFIG := msm8953-perf_defconfig xiaomi/xiaomi.config xiaomi/sakura.config
BOARD_KERNEL_IMAGE_NAME := Image.gz-dtb
```

so a ROM-matching kernel build uses `msm8953-perf_defconfig` fragment +
`xiaomi/sakura.config` fragment and produces `Image.gz-dtb`. Those fragment
paths are the contract to satisfy when building from
`kernel_xiaomi_msm8953` (verify presence in the chosen branch before building —
the defconfig layout differs between the `lineage-21` and `14` branches).

## 5. Recommendation for R12.0

**Keep the kernel change minimal and evidence-driven:**

1. **Primary (recommended) — reuse the verified 4.9.278 `Image.gz-dtb`.**
   Pin `ofx-12.1` prebuilt by SHA-256, keep the full proven `Image.gz-dtb`
   packaging, and do **not** rebuild a kernel you cannot validate boot-wise.
   This is the lowest-risk way to gain f2fs + fscrypt. It is a *binary* reuse,
   so record the provenance honestly: built by the community with Eva GCC 12,
   source not published as a matching tag.
2. **Fallback — reproduce from source:** build
   `msm8953E/kernel_xiaomi_msm8953@lineage-21` at `52b67cb3…` with
   `msm8953-perf_defconfig` + sakura fragments, `Image.gz` + appended DTB,
   then verify the version string, the sakura camera nodes in the DTB, and the
   `fscrypt_`/`F2FS` strings before packaging. Never ship a kernel whose DTB
   lacks the `sakura_*` nodes — that is the fastest way to a black screen.
3. **Do not** use the stock 3.18 kernel for the R12 target. It cannot do FBE or
   f2fs, so it would defeat the Android 10+ requirement. Keep it only as the
   known-good rollback reference (`R11.0_5` itself).

### Kernel requirements checklist for the built image

* `Image.gz` (gzip) with **appended multi-DTB**, `BOARD_KERNEL_BASE=0x80000000`,
  `BOARD_KERNEL_PAGESIZE=2048`, `BOARD_RAMDISK_OFFSET=0x01000000`,
  `BOARD_KERNEL_TAGS_OFFSET=0x00000100` (match the R11 header exactly).
* cmdline identical to R11 plus optional `audit=0`
  (`androidboot.bootdevice=7824900.sdhci` is mandatory for
  `init.recovery.qcom.rc` to create `/dev/block/bootdevice`).
* Must retain: ext4, dm-crypt, dm-verity, ICE, quota, sdcardfs.
* Must add: f2fs, fscrypt (FBE).
* Nice to have: zstd, lz4.
* **Not available (do not advertise):** EROFS, dm-default-key / metadata
  encryption, KeyMint.
