# First-build troubleshooting: the actual Soong/make issues

This answers "what are the Soong issues" for a **legacy MSM8953 device tree on an
AOSP 12.1 (TWRP minimal manifest) base**. These are the real failure classes,
each with the fix. Items marked **[fixed]** were already corrected in this tree;
items marked **[expected]** are what you will hit on the first `mka` and how to
decide.

---

## 1. `repo sync` errors that are NOT errors

The official sync guide says so explicitly: *"ignore errors relating to
android_bootable_recovery"*. The minimal manifest does not carry the full AOSP
`bootable/recovery`; OrangeFox replaces it after syncing. Likewise some
`platform/` projects are absent by design. `repo sync` returning non-zero here
is normal — what matters is that `bootable/recovery` and `vendor/recovery`
exist afterwards (the script clones them).

## 2. `lunch: unknown product 'fox_sakura-eng'` — **[fixed]**

Cause (in the 2024 community tree): `AndroidProducts.mk` declared only
`twrp_sakura.mk` while shipping an unreferenced `fox_sakura.mk`, so no
OrangeFox product was selectable.

Fix (in this tree): `AndroidProducts.mk` declares `fox_sakura.mk` first and adds
`COMMON_LUNCH_CHOICES`, so `lunch fox_sakura-eng` resolves.

## 3. `error: "..." depends on undefined module` — missing packages

Soong resolves `PRODUCT_PACKAGES` and `TARGET_RECOVERY_DEVICE_MODULES` against
the synced tree. A minimal manifest does not contain everything a full ROM does.
Order of likelihood for this device:

| Module | Where it must come from | If missing |
|---|---|---|
| ~~`qcom_decrypt`, `qcom_decrypt_fbe`~~ | do not exist at the pinned revisions | **[fixed]** no longer referenced; decryption comes from `TW_INCLUDE_CRYPTO` / `TW_INCLUDE_CRYPTO_FBE` plus the device tree's TEE services |
| `android.hidl.base@1.0` | `hardware/interfaces` | keep; present in 12.1 minimal manifest |
| `libdrm`, `libion`, `libxml2`, `libicuuc` | `external/` + `system/` | present in 12.1 minimal manifest |
| `vendor.display.config@1.0/2.0` | `hardware/interfaces` (system_ext) | **[expected]** if absent: delete those two lines from `device.mk`; only the display-config HAL loses a dependency, nothing else |
| `android.hardware.health@2.0-service` | was required by VINTF enforcement | **[fixed]** removed — `TW_USE_LEGACY_BATTERY_SERVICES := true` is what R11 used |
| `libinit_sakura` | a Soong module in `init/` | **[fixed]** not referenced: R11 had no device libinit, props come from product overrides |

Rule: if a module is genuinely absent, remove the *reference* and say why —
never stub a fake module into the tree.

## 4. VINTF enforcement without a device manifest — **[fixed]**

`PRODUCT_ENFORCE_VINTF_MANIFEST := true` on a 12.1 base makes the build demand
`DEVICE_MANIFEST_FILE` / `DEVICE_MATRIX_FILE` and validates the HAL set. This
tree ships neither (R11.0_5 shipped no `vendor/etc/vintf/manifest.xml` either),
so enforcement was removed rather than faked. To re-enable it later you must
first extract sakura's real manifests from the stock vendor image.

## 5. Obsolete make variables from older trees — **[fixed]**

* `PRODUCT_SYSTEM_PROPERTY_BLACKLIST` — obsolete on 12.x; removed.
* `ALLOW_MISSING_DEPENDENCIES` — an **environment** variable consumed by the
  build system. Setting it inside `BoardConfig.mk` does nothing; it is exported
  by `build/build.sh` where it works.
* `ro.twrp.version` override — removed; TWRP sets its own version strings.

## 6. Toolchain / environment failures (look like Soong errors, aren't)

| Symptom | Cause | Fix |
|---|---|---|
| `UnsupportedClassVersionError` during Soong bootstrap | wrong JDK | install **OpenJDK 11**, `export JAVA_HOME` accordingly |
| `soong_build: cannot execute` / `ninja: build stopped` immediately | missing `bc`, `bison`, `flex`, `libssl-dev`, `zlib1g-dev` | install the package list in `DEPENDENCIES.md` §1 |
| `mka: command not found` | envsetup not sourced | run via `build/build.sh`, which sources it |
| `repo: command not found` | repo launcher missing | install to `~/bin` from Google |
| build dies with OOM on 8 GB | `-j` too high | `mka -j4 recoveryimage`, or add swap |
| silently builds plain TWRP | `vendor/twrp` not patched | must run the official sync script; `verify_image.sh` fails if OrangeFox strings are missing |

## 7. Duplicate-rule and prebuilt-ELF errors — already tolerated

`BUILD_BROKEN_DUP_RULES := true` and
`BUILD_BROKEN_ELF_PREBUILT_PRODUCT_COPY_FILES := true` are set because:

* the QTI HAL prebuilts are copied from `recovery/root/**` while some libraries
  are also built from source (`libcrypto`, `libxml2`), producing duplicate-rule
  reports;
* prebuilt vendor `.so` files are ELF and would otherwise trip the
  ELF-prebuilt copy check.

These are the official escape hatches for legacy trees; they do **not** weaken
the build, and they must not be used to paper over a genuinely missing module.

## 8. 32/64-bit: verified, not assumed

R11.0_5's ramdisk was inspected (ELF headers):

```
init, recovery, adbd, toybox, libc.so, libc++.so,
keystore, qseecomd          -> ELF64 / AArch64
linker, bash, magiskboot    -> ELF32 / ARM  (32-bit prebuilt helpers)
```

So the recovery user space is **64-bit primary with a 32-bit secondary** — hence
`TARGET_ARCH := arm64`, `TARGET_2ND_ARCH := arm`, and
`core_64_bit_only.mk` is **wrong** for this device if it forbids 32-bit
dependencies. This tree inherits `aosp_base.mk` + `device.mk` and keeps the
secondary arch; if Soong complains that the product is 64-bit-only while 32-bit
modules are required, drop the `core_64_bit_only.mk` inherit in
`fox_sakura.mk`/`twrp_sakura.mk` (that inherit is cosmetic for recovery).

Note: R11's `prop.default` had an empty `ro.product.cpu.abilist64`, which looks
like a 32-bit build. It is not — the binaries are ELF64. Do not "fix" the tree
to match that prop.

## 9. `mkbootimg` args — **[fixed]**

`BOARD_MKBOOTIMG_ARGS` is now appended with `+=` instead of assigned with `:=`.
With `:=` the tree discards the args TWRP adds, which can silently change the
boot image header of the produced recovery.

## 10. What "correct" still cannot guarantee

Even with all of the above fixed, a build can fail for reasons only a real
compile reveals (a moved header, a renamed Soong property, a 12.1
`fs_mgr`/`libcryptfs` API change). That is why the port ships:

* `build/build.sh` — isolates the first error from the log;
* `build/verify_image.sh` — proves the produced image is structurally a sakura
  OrangeFox recovery (header, addresses, cmdline, DTB, fstab, branding).

Only a device test can prove it **boots**. See `TEST_REPORT.md`.
