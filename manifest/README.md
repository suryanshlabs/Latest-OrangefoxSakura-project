# Pinned manifest and sync recipe

## Why the build uses `fox_12.1`

`R12.0` is the OrangeFox **release** version. `fox_12.1` is the **build
manifest branch**, and syncing `--branch 12.1` is what produces R12.0
(`FOX_BASE_VERSION="R12.0"` in `orangefox_sync.sh`). There is no "R12.0
branch". Rationale for not choosing `fox_14.1`: see
`../documentation/SOURCE_AUDIT.md` §2.

## Pinned refs used by `build/sync.sh`

| Component | Repository | Ref | Commit |
|---|---|---|---|
| Sync tooling | https://gitlab.com/OrangeFox/sync | `master` | `73d4d94e0d1b11b9035dea72ee223d25b1fefa7c` |
| Minimal manifest | https://github.com/minimal-manifest-twrp/platform_manifest_twrp_aosp | `twrp-12.1` | `6dc117d9cbd08430daa16db2013560e1c4017fa8` |
| Recovery | https://gitlab.com/OrangeFox/bootable/Recovery.git | `fox_12.1` | `8d2aad19deb158e935d70ca5b648162c2b2831ee` |
| Vendor | https://gitlab.com/OrangeFox/vendor/recovery.git | `main` | `1998cfcaca9bb247ea20d587e565676faa281de9` |
| Vendor (strict R12 branch) | same | `fox_12.1` | `fbe4d49c96acace3802c53c12cad0a62903c381f` |
| qcom common | https://github.com/TeamWin/android_device_qcom_common | `android-12.1` | (branch of the minimal manifest era) |
| qcom twrp-common | https://github.com/TeamWin/android_device_qcom_twrp-common | `android-12.1` | (same) |

The reference synced by the project to date is the **official script at the
pinned commit**, so the effective vendor branch is `main` — that is the
script's own default since sync v029 ("use the new unified ('main') branch of
the vendor tree"). Both branches are recorded so a strict R12.0 tree can be
reproduced.

## Sync options

**A. Official script (recommended, matches upstream behaviour):**

```bash
mkdir -p ~/OrangeFox_sync && cd ~/OrangeFox_sync
git clone https://gitlab.com/OrangeFox/sync.git
cd sync && git checkout 73d4d94e0d1b11b9035dea72ee223d25b1fefa7c
./orangefox_sync.sh --branch 12.1 --path "$HOME/fox_12.1"
```

**B. This project's wrapper (same thing + pins + device tree):**

```bash
./build/sync.sh "$HOME/fox_12.1"
```

## Disk

`fox_12.1` needs **≥45 GB**. Plan ~60 GB with build output.

## After syncing

`build/sync.sh` links this repository's `device/xiaomi/sakura` into the source
tree. If you sync manually, do it yourself:

```bash
ln -s "$(pwd)/device/xiaomi/sakura" "$HOME/fox_12.1/device/xiaomi/sakura"
```

## Manifest file

`fox_12.1-sakura.xml` is a *local* manifest pinning the device-side projects.
It is kept for reference/reproducibility and for anyone building with
`repo` over an existing tree; `build/sync.sh` performs the equivalent steps
with plain git so it does not depend on `.repo/local_manifests` layout.
