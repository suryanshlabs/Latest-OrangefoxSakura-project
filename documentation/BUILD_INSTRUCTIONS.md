# Build instructions (reproducible)

## 1. Host requirements

* Ubuntu 20.04/22.04 (or equivalent), x86_64
* **≥45 GB free** for `fox_12.1` (60 GB comfortable with output)
* 8 GB RAM minimum, 16 GB recommended
* not root
* packages: see `DEPENDENCIES.md` §1
* `repo` from `https://storage.googleapis.com/git-repo-downloads/repo`

## 2. Reference analysis first (cheap, 2 minutes)

```bash
./build/fetch_reference.sh
```

Downloads the official R11.0_5 ZIP, verifies MD5 `5dff190f…` and SHA-256
`461e60c8…`, unpacks `recovery.img`, the ramdisk, and the original build
variables into `reference/` (git-ignored). Nothing from the archive is executed.

## 3. Kernel

Either reuse the verified 4.9 binary:

```bash
./build/fetch_kernel.sh          # sha256 d12f816a…, DTB/version verified
```

or rebuild from source (preferred for a release-quality, attributable build):

```bash
git clone https://github.com/msm8953E/kernel_xiaomi_msm8953 -b lineage-21
cd kernel_xiaomi_msm8953 && git checkout 52b67cb32ac009d366b632221d5fd381b6b7b55c
make O=out ARCH=arm64 msm8953-perf_defconfig xiaomi/xiaomi.config xiaomi/sakura.config
make O=out ARCH=arm64 -j"$(nproc)" Image.gz dtbs
# append the sakura DTBs, keep the R11 boot header layout, then:
python3 ../tools/verify_dtb.py out/arch/arm64/boot/Image.gz-dtb
```

The verifier must PASS before you use the kernel.

## 4. Sync

```bash
./build/sync.sh "$HOME/fox_12.1"
```

This pins and verifies:

| Item | Ref |
|---|---|
| OrangeFox sync script | `73d4d94e…` (SCRIPT_VERSION 20261107, R12.0) |
| Minimal manifest | `platform_manifest_twrp_aosp` @ `twrp-12.1` `6dc117d9…` |
| Recovery | `OrangeFox/bootable/Recovery@fox_12.1` `8d2aad19…` |
| Vendor | `OrangeFox/vendor/recovery@main` `1998cfca…` |

It then symlinks `device/xiaomi/sakura` into the tree.

## 5. Build

```bash
./build/build.sh "$HOME/fox_12.1"
```

which runs:

```bash
. build/envsetup.sh
export ALLOW_MISSING_DEPENDENCIES=true
lunch fox_sakura-eng
mka recoveryimage | tee build.log
```

Output: `out/target/product/sakura/OrangeFox-unofficial-sakura.img`
(this is the filename the official guide documents).

If `lunch fox_sakura-eng` is not accepted, the vendor patch did not apply —
build `twrp_sakura-eng` instead to isolate the cause (that yields stock TWRP,
not OrangeFox).

## 6. Structural verification

```bash
./build/verify_image.sh "$HOME/fox_12.1"
```

Checks: header v0, page size 2048, `kernel_addr 0x80008000`,
`ramdisk_addr 0x81000000`, `androidboot.bootdevice=7824900.sdhci`, image
fits 64 MiB, sakura DTB fingerprint, `fscrypt`, `fileencryption=ice` present,
`encryptable=footer` retained, no `metadata_encryption`, OrangeFox branding in
the ramdisk (i.e. the vendor patch applied).

A PASS here means **structurally correct**, not bootable.

## 7. Why this environment cannot build it

The Cloud workspace used for this analysis has **9.5 GB free, 3.8 GB RAM,
2 vCPU, no root, and no `java`/`cpio`/`lz4`**, versus the ≥45 GB and 8–16 GB
RAM the build needs, and `repo sync` alone is documented as taking hours.
Therefore: **no build was attempted here and none is claimed.** What this
environment *can* do — and did — is the full reference reverse-engineering,
source audit, device-tree development and structural verification tooling,
all of which are dependency-free.

To build, run steps 1–6 on a machine meeting §1.

## 8. Reproducing a signed official-style release

Official releases must be **signed** (maintainer guidelines). Unsigned zips are
not permitted for release. Signing keys are the maintainer's own and must never
be committed. See <https://wiki.orangefox.tech/dev/maintainers_guidelines>.
