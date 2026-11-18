# Known issues and open questions

Severity: **blocker** (cannot ship), **high** (functional gap), **medium**
(needs verification), **info**.

## KI-1 — Metadata encryption: wired, but not usable on this kernel (high, architectural)

The recovery's metadata path is **already compiled into the image**
(`-DTW_INCLUDE_FBE_METADATA_DECRYPT`, `libvold`/`MetadataCrypt`, and
`partition.cpp` parsing `metadata_encryption=`/`keydirectory=`), and this tree now
ships an explicit, reversible opt-in configuration
(`tools/configure_metadata.py`, `SAKURA_METADATA_ENCRYPTION=1`; see
`ENCRYPTION.md` §6a).

What blocks real support is not configuration: `sakura`'s vendor is Keymaster 3.0
and **neither** available kernel (stock 3.18.120 nor the 4.9.278 candidate)
contains `dm-default-key` (measured — `KERNEL_ANALYSIS.md` §2/§3). Without that
device-mapper target the metadata device cannot be mapped, so a metadata-encrypted
`/data` cannot be decrypted by any build of this tree.

*Impact:* Android 10+ ROMs that encrypt metadata will show an unmountable `/data`
until "Format Data" (data loss). In practice every inspected sakura fstab
(`LOS 18.1/20/21/22.x`) uses `fileencryption=ice` with no metadata layer, and the
default build declares no metadata tokens, so this does not regress those ROMs.
*Mitigation:* default off; the fstab comment explains why a non-empty
`keydirectory=` is dangerous here (it makes recovery treat a plain `/data` as
encrypted); diagnostics report the crypto mode so an intentional no-crypto build
is not mistaken for a fault.
*Fix path:* a `dm-default-key` backport to 4.9 (or a kernel that has it) plus a
KM4/KeyMint storage-key provider on the vendor. Research project, not a build
flag — and any claim of metadata decryption before that is false.

## KI-2 — Kernel provenance is not attributable (high, release blocker)

The verified 4.9.278 `Image.gz-dtb` came from a public tree whose own README
names a **daisy** kernel source (`TWRP-Mi-A2-Lite/twrp_kernel_xiaomi_daisy`)
and was built in an anonymous container with Eva GCC 12. The resulting DTB is
sakura-correct (verified), but for a release the kernel should be rebuilt from
`msm8953E/kernel_xiaomi_msm8953@lineage-21` (`52b67cb3…`) so the binary has
attributable source. GPL compliance requires offering the corresponding source.

## KI-3 — Proprietary blobs are not shipped, and the inherited set was daisy-derived (high, open until you extract your own)

`device/xiaomi/sakura/proprietary-files.txt` inherits its *list* from the
community tree, whose header says the blobs came from
`daisy-user 10 QKQ1.191002.002 V11.0.21.0.QDLMIXM`. Mi A2 Lite binaries are not
sakura binaries; they are likely ABI-compatible but **unproven**.

This is now enforced rather than documented: `build/extract_blobs.sh` reads the
supplied image's `ro.product.device` / `ro.build.version.release` and refuses
anything that is not `sakura` on Android 9, and it records the firmware name,
firmware SHA-256, `vendor.img` SHA-256, vendor fingerprint and per-file SHA-256
in `vendor_blobs/EXTRACTION_REPORT.md` (`DEPENDENCIES.md` §4).

Still open because no genuine sakura firmware was available in this
development environment: the extraction has only been exercised against
synthetic images (see `TEST_REPORT.md` §1c). Run it once against your own
`V12.0.4.0.PDMMIXM` (Global/India) or `V12.0.1.0.PDICNXM` (China) fastboot ROM
before treating the chain as sakura-correct.

## KI-4 — Recovery install partition: hardened, still confirm once (low)

The community tree hard-coded `/dev/block/mmcblk0p49`, a raw partition number
nobody verified for sakura — flashing an image to the wrong partition number is
a reliable way to hard-brick. This port uses the **by-name symlink** instead:

```
FOX_RECOVERY_INSTALL_PARTITION="/dev/block/bootdevice/by-name/recovery"
```

the same path the R11 fstab used, and correct by construction whenever the boot
device is `7824900.sdhci`. Confirm once on device:

```bash
ls -l /dev/block/bootdevice/by-name/recovery
```

If the OrangeFox installer turns out to reject a by-name path (untested), fall
back to the raw number **after** reading it from that symlink — never assume.

## KI-11 — QTI crypto chain: tooling complete, firmware input still required (blocker for decryption)

The `qseecomd`, QTI Keymaster 3.0 and QTI Gatekeeper 1.0 services plus their
library set are proprietary and are **not** in this repository. The audited
handoff image (`documentation/IMAGE_AUDIT.md`) shipped `keystore2` and none of
the three services, with no active `fileencryption=ice`.

What is complete now:

* `build/extract_blobs.sh` — read-only extraction from a stock fastboot ROM,
  identity + architecture gates, local checksum/provenance report;
* `build/install_blobs.sh` — installs to the exact ramdisk paths init execs and
  generates `blob_install.mk` (`PRODUCT_COPY_FILES`);
* `build/check_crypto_blobs.sh --require` — fatal gate used by `build.sh`,
  `run-all.sh` and CI (explicit opt-out: `SAKURA_ALLOW_MISSING_CRYPTO=1`);
* `tools/check_init_services.py` — proves executable path, ELF machine,
  interpreter and transitive `DT_NEEDED` resolution for every init service.

*Still open:* no genuine sakura firmware was supplied, so no real blob has been
extracted, hashed or link-checked here, and decryption remains **UNTESTED** on
hardware. Extract from your own firmware (`DEPENDENCIES.md` §4) and boot the
result on an encrypted `/data` before claiming FDE/FBE works.

## KI-12 — sbin vs system/bin destination for the QTI services (resolved by measurement)

This was previously an unresolved "which path is right?" question. It is now
measured against the pinned sources (`bootable/recovery` @ `8d2aad19`,
`vendor/recovery` @ `1998cfca`):

* `Android.mk:197` installs the recovery binaries to
  `$(TARGET_RECOVERY_ROOT_OUT)/system/bin`;
* `etc/init.rc` sets `PATH=/sbin:/system/bin` and
  `LD_LIBRARY_PATH=/system/lib64:/vendor/lib64/hw`;
* `/sbin` holds only the `sh`/`bash` symlinks, and `prebuilt/relink.sh` in that
tree only copies files (it does not patch a linker path), so the interpreter
  `/system/bin/linker64` is the one that must exist.

Therefore services go to `recovery/root/system/bin/…` and their libraries to
`recovery/root/system/lib64/…`. The manifest and
`init.recovery.qcom_decrypt.rc` use exactly those strings, and
`tools/check_init_services.py` fails the build if they ever diverge.

## KI-5 — No build has been performed (blocker for any release claim)

See `TEST_REPORT.md` §2. Everything in `device/` is reviewed-but-unbuilt.
Expect real Soong/`mka` issues on first build (12.1 base + legacy MSM8953).
`documentation/BUILD_TROUBLESHOOTING.md` lists each known failure class with
its fix — the obsolete-variable, missing-module, VINTF-enforcement and
mkbootimg-args ones are already corrected in this tree. Do not "fix" remaining
errors by disabling OrangeFox features.

## KI-6 — `vendor/twrp` must be patched or you get plain TWRP (medium)

The OrangeFox sync script patches `vendor/twrp` "to pull in an OrangeFox
makefile" (v027). `fox_sakura.mk` inherits `vendor/twrp/config/common.mk`.
If the patch did not apply, `lunch fox_sakura-eng` fails or the build is plain
TWRP. `verify_image.sh` checks for OrangeFox strings to catch this.

## KI-7 — EROFS images cannot be mounted (info)

Neither kernel has EROFS. Current sakura ROM trees build `/system` and
`/vendor` as **ext4** (`BOARD_{CACHE,VENDOR}IMAGE_FILE_SYSTEM_TYPE := ext4`),
so this is not currently a problem. If a future ROM ships an EROFS `/system`,
this recovery cannot mount it. Do not advertise EROFS support.

## KI-8 — Android 16/17 have no sakura ROM (info)

No `lineage-23`/A16/A17 sakura device tree or ROM was found (all branch heads
enumerated). Those rows in `ANDROID_COMPATIBILITY.md` are "Research only".
Support can only be assessed if and when a ROM exists.

## KI-9 — R11 tree itself is not public (info)

The actual R11.0_5 device tree was never published; `Sakura-Devices/…@eleven`
is a LineageOS 18.1 **ROM** tree, not the recovery tree. R11 behaviour was
therefore reconstructed from the released binary + `fox_build_vars.txt`, which
is authoritative for build variables but not for source-level intent.

## KI-10 — DTB count differs between kernels (info)

R11 stock: 46 DTBs; 4.9 candidate: 2 DTBs. Both contain the six sakura camera
nodes and the sakura panels, so 2 is sufficient in practice — but if a
sakura variant (different panel/touch) fails to display, the 2-DTB set is the
first suspect. A from-source build can regenerate all DTBs.

## KI-13 — Boot diagnostics are source-verified, not screen-verified (medium)

`sakura-diag` and the Error Logs theme patch are implemented and unit-tested,
and the patch applies cleanly to the pinned upstream. **No image has been built
and no pixel has been rendered.** The badge position (x=756..926, y=8..72) is
fixed for the 1080 px sakura layout and may need adjustment if the status bar
variables change. The badge is a text `! DIAG`, not an emoji, because the
OrangeFox fonts do not guarantee an emoji glyph. Details:
`DIAGNOSTICS.md` §7.

## KI-14 — Badge refresh is per page render (low)

Theme conditions are evaluated when a page renders. The collector sets
`of.boot_diag_errors` before the GUI starts, so the first paint is correct. An
error discovered later appears on the next page load; there is no forced
redraw. Do not describe the badge as a live indicator.

## KI-15 — `/cache` mirror is best-effort (medium)

`/cache` is a **separate ext4 partition** (`by-name/cache -> /cache` in
`recovery.fstab`), not `/data/cache`; earlier revisions of this document said the
latter, which was wrong and is corrected here.

The collector mirrors diagnostics into `/cache/recovery/sakura-diag` **only** when
`/proc/mounts` proves a real, read-write, non-ramdisk filesystem is mounted at or
above `/cache`. If the partition is absent, read-only or ramdisk-backed, nothing
is written and `cache=` in `status` says why (`unmounted`, `read-only`,
`not-persistent`, `unwritable`). Never mounting `/data` to fake persistence is a
deliberate constraint.

Consequence: after a reboot with no writable `/cache`, the failed-boot logs are
gone. adbd (started early via `sys.usb.config=adb`) is the retrieval path that
works while the device is still in recovery.

## KI-16 — No build has completed end to end (blocker)

Every CI run so far stopped before compiling recovery code: five runs died at
Soong's theme selection (`Could not find ui.xml for TW_THEME: not set`), one later
run died sourcing `build/envsetup.sh` (`exit status: 1`). Both paths are now
guarded (`build/check_theme_inputs.sh`, `BUG-17`; and the envsetup block in
`build/build.sh` runs with `set +u`, keeps the log and dies with the status), but
**no run has yet produced an image**.

What cannot be claimed until one does: that the theme resolves through
`soong.variables`, that the patched theme compiles, that the ramdisk contains the
diagnostics files, and that `verify_image.sh` passes on a real image. This
document and `TEST_REPORT.md` say so explicitly.
