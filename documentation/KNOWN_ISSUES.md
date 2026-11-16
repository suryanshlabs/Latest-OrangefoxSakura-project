# Known issues and open questions

Severity: **blocker** (cannot ship), **high** (functional gap), **medium**
(needs verification), **info**.

## KI-1 — Metadata encryption is not supportable (high, architectural)

`sakura`'s vendor is Keymaster 3.0 and **neither** available kernel
(stock 3.18.120 nor the 4.9.278 candidate) contains `dm-default-key`
(measured). Metadata-encrypted `/data` therefore cannot be mounted/decrypted by
any single sakura R12 build.

*Impact:* Android 10+ ROMs that encrypt metadata will show an unmountable
`/data` until "Format Data" (data loss) or a first boot without encryption.
*Mitigation:* documented as a limitation; no false advertising.
*Fix path:* requires a `dm-default-key` backport to 4.9 **and** a KM4/KeyMint
storage-key provider on the vendor — not available on this firmware. Research
project, not a build flag.

## KI-2 — Kernel provenance is not attributable (high, release blocker)

The verified 4.9.278 `Image.gz-dtb` came from a public tree whose own README
names a **daisy** kernel source (`TWRP-Mi-A2-Lite/twrp_kernel_xiaomi_daisy`)
and was built in an anonymous container with Eva GCC 12. The resulting DTB is
sakura-correct (verified), but for a release the kernel should be rebuilt from
`msm8953E/kernel_xiaomi_msm8953@lineage-21` (`52b67cb3…`) so the binary has
attributable source. GPL compliance requires offering the corresponding source.

## KI-3 — Proprietary blobs are daisy-derived (high, release blocker)

`device/xiaomi/sakura/proprietary-files.txt` inherits its list from the
community tree, whose header says the blobs come from
`daisy-user 10 QKQ1.191002.002 V11.0.21.0.QDLMIXM`. They are very likely
ABI-compatible but **unproven**. Extract sakura Android 9 blobs
(`V12.0.x.x.PDI*`) and compare SHA-1 (`DEPENDENCIES.md` §4).

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

## KI-11 — QTI crypto chain is absent from the tree (blocker for decryption)

`device/xiaomi/sakura/proprietary-files.txt` lists the `qseecomd`,
Keymaster 3.0 and Gatekeeper 1.0 QTI services plus their library set, but the
binaries are proprietary and are **not** in this repository. The audited
handoff image (`documentation/IMAGE_AUDIT.md`) shipped `keystore2` and none of
the three services, with no active `fileencryption=ice`.

*Impact:* any image built without those blobs cannot decrypt FDE or FBE, and
because the fstab now declares `fileencryption=ice`, an FBE-encrypted `/data`
may hang at the splash rather than report an error.
*Mitigation:* `build/check_crypto_blobs.sh` lists exactly what is missing and
`build/verify_image.sh` prints `DECRYPTION: UNVERIFIED`; no decryption claim is
made anywhere.
*Fix path:* extract the blobs from your own sakura Android 9 stock vendor image
(`DEPENDENCIES.md` §4) and record their SHA-1s.

## KI-12 — sbin vs system/bin destination for the QTI services (medium)

The inherited list maps the three service binaries to `recovery/root/sbin`,
while the Android 12+ recovery layout used by `fox_12.1` expects services under
`/system/bin`. The correct path is whatever the synced
`vendor/recovery`/`init.recovery.qcom_decrypt.rc` actually executes;
`build/check_crypto_blobs.sh` greps that tree and prints the referenced paths
so the mismatch is visible instead of assumed. Do not "fix" this by copying a
binary into both paths without checking its `DT_NEEDED` libraries resolve — a
decrypt service that cannot link is worse than an absent one.

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
