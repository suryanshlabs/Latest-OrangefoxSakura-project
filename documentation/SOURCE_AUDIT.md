# Source audit — OrangeFox R12.0 for sakura

Scope: verify the *actual* upstream refs (not just names), decide the build
manifest, and record what is and is not public. Every commit SHA below was
resolved with `git ls-remote` or the GitLab/GitHub API during this project.

## 1. Release version vs build manifest — resolving the confusion

Two different version numbers exist and they are unrelated:

* **OrangeFox release version** — `R12.0`. It is a string in the sync script:
  `FOX_BASE_VERSION="R12.0"` (in `orangefox_sync.sh`).
* **Build manifest branch** — `fox_12.1`, `fox_14.1`, `fox_16.0`. This selects
  which minimal-AOSP/TWRP base tree and which recovery/vendor sources are synced.

Verified from `orangefox_sync.sh` (SCRIPT_VERSION `20261107`, `FOX_BASE_VERSION="R12.0"`):

```sh
MIN_MANIFEST="https://github.com/minimal-manifest-twrp/platform_manifest_twrp_aosp.git"

do_fox_121() {
    BASE_VER=12;
    FOX_BRANCH="fox_12.1";
    FOX_DEF_BRANCH="fox_12.1";
    TWRP_BRANCH="twrp-12.1";
    DEVICE_BRANCH="android-12.1";
    TW_DEVICE_BRANCH="android-12.1";
    test_build_device="miatoll";
}
```

So syncing `--branch 12.1` **already gives the R12.0 sources**. There is no
separate "R12.0 branch": `fox_12.1` is the manifest, `R12.0` is what it builds.

## 2. Manifest decision: `fox_12.1` (not `fox_14.1`)

The official guide states `fox_14.1` is for devices that *require* a 14.x build
system, "mostly those that launched with Android 14 or higher", and warns
"you really should avoid building the 14.x branch". Sakura launched with
Android 8.1 on MSM8953 with a 64-bit-primary but 32-bit-capable user space and
no 14.x-era requirements:

* no dynamic partitions (`BOARD_SUPER_PARTITION_*` absent in every sakura tree
  examined)
* `BOARD_AVB_ENABLE := false` in the A15 tree
* recovery partition is a real, 64 MiB partition (`BOARD_RECOVERYIMAGE_PARTITION_SIZE := 67108864`)
* VNDK 28 (lite) vendor

Therefore **`fox_12.1` is the correct and sufficient base**. Choosing `fox_14.1`
would add ~40 GB of source and a newer Soong/Bionic for no benefit, and would
increase the risk of 32-bit/legacy-vendor incompatibilities. Android 15/16/17
*ROM* compatibility does not require a 14.x *recovery* build system.

## 3. Pinned upstream refs

| Component | Repository | Branch | Commit | How verified |
|---|---|---|---|---|
| Sync tooling | https://gitlab.com/OrangeFox/sync | `master` | `73d4d94e0d1b11b9035dea72ee223d25b1fefa7c` | `git ls-remote`; script SCRIPT_VERSION 20261107, FOX_BASE_VERSION R12.0 |
| Build manifest | https://github.com/minimal-manifest-twrp/platform_manifest_twrp_aosp | `twrp-12.1` | `6dc117d9cbd08430daa16db2013560e1c4017fa8` | `git ls-remote` |
| Recovery sources | https://gitlab.com/OrangeFox/bootable/Recovery.git | `fox_12.1` | see §4 note | URL read from `clone_fox_recovery()` |
| Vendor tree | https://gitlab.com/OrangeFox/vendor/recovery.git | `main` (script default) | see §4 note | `git ls-remote` |
| Vendor tree (legacy R12 branch) | same | `fox_12.1` | `fbe4d49c96acace3802c53c12cad0a62903c381f` | `git ls-remote` |
| Vendor tree (14.1) | same | `fox_14.1` | `2c20a4a80fdd63c5da53085f1a28cf8499102090` | `git ls-remote` |

### 4. Important subtlety in the current sync script

`clone_fox_vendor()` hard-codes `local BRANCH="main"`, and the script header
records why: *"v029 (20260913) - use the new unified ('main') branch of the
vendor tree"*. So a **fresh** sync of `--branch 12.1` today takes
`vendor/recovery@main` (`1998cfcaca9bb247ea20d587e565676faa281de9`), not
`vendor/recovery@fox_12.1` (`fbe4d49c…`). Both exist. This project pins **the
script's behaviour** (i.e. `main`) so a rebuild matches what a maintainer gets
today, and records `fox_12.1` as the fallback for reproducing a strict
branch-matched R12.0 tree.

`OrangeFox/bootable/Recovery.git` is a GitLab subgroup project; it is cloned
with `-b $FOX_BRANCH` (i.e. `fox_12.1`). It is not in the `OrangeFox` top-level
group listing (`Manifest`, `bionic`, `build-scipts-examples`, `cts`,
`f2fs-tools`, `sync`, `tracker`), which is why a naive group scan misses it.

## 5. Documentation sources

| Purpose | URL |
|---|---|
| Build guide | https://wiki.orangefox.tech/dev/building |
| Maintainer guidelines | https://wiki.orangefox.tech/dev/maintainers_guidelines |
| Sync repo | https://gitlab.com/OrangeFox/sync |
| Fox API (release metadata) | https://api.orangefox.download (docs: `/redoc`, `/docs`) |
| Download site | https://orangefox.download/ |

Key build-guide constraints that drive this project: ≥45 GB disk for
`fox_12.1`, ≥85 GB for `fox_14.1`; syncing "can take hours"; the guide warns
that *"after you finish building, your build may have problems with decryption
... you will need to work on your device tree"* — which is exactly the problem
this port has to solve.

## 6. Release-state facts about sakura upstream

* The device API record reports `supported: false` — sakura is **not** a
  maintained device on orangefox.download; the device page says "This device is
  not currently maintained".
* The last official release is R11.0_5 (2021-03-21); all six releases are
  flagged `archived: true`.
* Therefore R12.0 for sakura can only ever be an **unofficial** port; it cannot
  be published as an official OrangeFox release without the user becoming the
  maintainer (see maintainer guidelines).

## 7. Deliberately *not* used

* `fox_14.1` / `fox_16.0` bases — no evidence sakura needs them (§2).
* Full ROM device trees copied wholesale (e.g. `Sakura-Devices/device_xiaomi_sakura@eleven`,
  a LineageOS 18.1 tree with `XiaomiParts`, overlays and app sources) — a ROM
  tree drags in ROM-only components into recovery.
* The `ofx-12.1_daisy` branch of the recovery tree — **daisy (Mi A2 Lite) is a
  different device** and is excluded by design, see `DEVICE_COMPATIBILITY.md`.
