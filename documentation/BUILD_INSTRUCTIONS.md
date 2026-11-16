# Build instructions (reproducible)

## 1. Host requirements

* Ubuntu 20.04/22.04 (or equivalent), x86_64
* **≥45 GB free** for `fox_12.1` (60 GB comfortable with output)
* 8 GB RAM minimum, 16 GB recommended
* not root
* packages: see `DEPENDENCIES.md` §1
* `repo` from `https://storage.googleapis.com/git-repo-downloads/repo`

## 1b. One command (recommended)

```bash
./build/run-all.sh "$HOME/orangefox/fox_12.1"
```

That is the whole build: static checks → pinned sync (unless the tree already
exists) → kernel fetch + DTB verification → crypto-chain report → one
`recoveryimage` build → hard structural verification. It stops at the first
failure and prints the image path plus SHA-256.

The sections below are the same steps broken out, for debugging or for running
them individually.

### Which runner / machine

The workflow targets whatever `runner_label` you dispatch it with; it no longer
assumes the expired ServerHive self-hosted runner. Standard `ubuntu-latest`
GitHub-hosted runners usually have far less than the 45 GB this sync needs, so
the workflow's preflight measures disk and RAM and **fails immediately with an
actionable message** rather than starting a doomed sync. Point `runner_label` at
any Linux x86_64 machine you register as a self-hosted runner (>=45 GB free,
>=8 GB RAM, packages from `DEPENDENCIES.md` §1).

Android/Termux hosts (including a Poco F1 running Termux) are **not** supported
build environments for this tree and no support is claimed for them.

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
not OrangeFox). For every other first-build failure class (missing modules,
obsolete 12.1 variables, JDK/toolchain, 32/64-bit), see
`BUILD_TROUBLESHOOTING.md`.

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

## 7. Build status and the current environment

**No recovery image has been built from this tree.** The previous builds ran on
the ServerHive self-hosted runner, which has expired; the workflow no longer
references it. The analysis workspace used for these edits is also not a build
host (no 45 GB of volume, and no Android toolchain), so nothing beyond static
checks was executed there.

What *has* been executed and can be re-executed anywhere:

```bash
python3 tools/static_checks.py          # configuration regression gate
bash -n build/*.sh                      # shell syntax
./build/check_crypto_blobs.sh           # which proprietary blobs are missing
```

To build, use `./build/run-all.sh` (§1b) on a machine meeting §1.

## 8. Reproducing a signed official-style release

Official releases must be **signed** (maintainer guidelines). Unsigned zips are
not permitted for release. Signing keys are the maintainer's own and must never
be committed. See <https://wiki.orangefox.tech/dev/maintainers_guidelines>.
