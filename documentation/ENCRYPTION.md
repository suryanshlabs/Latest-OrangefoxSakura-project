# Encryption analysis

This is the hardest requirement in the brief and the one most likely to be
over-claimed. Everything here is derived from the R11 artifact, the two kernel
binaries, and the device trees. **No decryption has been tested on hardware.**

## 1. What R11.0_5 actually implemented

From the unpacked ramdisk (`REFERENCE_R11_ANALYSIS.md` §4):

```
/data  ext4  /dev/block/bootdevice/by-name/userdata  encryptable=footer;length=-16384
```

and `OF_SKIP_FBE_DECRYPTION="1"`.

That is **legacy full-disk encryption (FDE)** using a footer:
`encryptable=footer` means dm-crypt with a 16 KiB crypto footer
(`length=-16384`), key derived from the user's PIN/password/pattern via
`gatekeeper` + the Qualcomm keymaster, with the disk key wrapped by
`libcryptfs_hw` / `libcryptfsfde` talking to QSEECom.

Crypto components shipped in `/sbin`: `libcryptfsfde.so`, `libcryptfs_hw.so`,
`libe4crypt.so`, `libgatekeeper.so`, `libkeymaster_messages/portable/4support`,
`libkeystore_binder/aidl`, `libsoftkeymasterdevice.so`, `libQSEEComAPI.so`,
`openaes`, `keystore`, `keystore_auth`, `qseecomd`, `prepdecrypt.sh`, plus HIDL
services `keymaster@3.0-service-qti` and `gatekeeper@1.0-service-qti`.

The bring-up sequence in `init.recovery.qcom.rc`:

```
start prepdecrypt, sbinqseecomd, hwservicemanager, boot-1-0
on property:fde.ready=1     -> start keymaster-3-0
on property:crypto.ready=1  -> start sbinqseecomd + keymaster-3-0 + gatekeeper-1-0 + servicemanager
```

So R11 = **QSEECom + Keymaster 3.0 + Gatekeeper 1.0 + dm-crypt footer (FDE)**.
There is no fscrypt, no ICE-based file encryption, no metadata encryption, and
no KeyMint anywhere in the R11 image. This matches the stock kernel, which has
**dm-crypt but no `fscrypt`**.

## 2. The kernel constraint (measured)

| Requirement | stock 3.18.120 | 4.9.278 (ofx-12.1) | Consequence |
|---|---|---|---|
| dm-crypt (FDE) | yes | yes | legacy FDE is possible on both |
| **fscrypt (FBE)** | **no** | **yes** | **FBE impossible on the stock kernel** |
| ICE / inline crypto | yes | yes | hardware key handling for FBE available |
| dm-default-key | no | no | **metadata encryption not supportable** |
| keymaster 4.0 / KeyMint | n/a (vendor HAL) | vendor HAL is 3.0 | storage-key based metadata encryption unavailable |

The device's vendor partition is Android 9, VNDK 28, with
`OF_DEFAULT_KEYMASTER_VERSION := 3.0` in the community R12 tree and
`android.hardware.keymaster@4.0.so` present only as a *library* (R11) — no
Keymaster 4.0 service, no KeyMint, no `weaver` service binding.

## 3. What each Android generation means

| Android | Typical `/data` crypto on sakura | Reachable by an R12 build? |
|---|---|---|
| 9 (MIUI 12 stock, crDroid 7 era) | **FDE footer** (or unencrypted) | Yes — same mechanism as R11 |
| 10 | FBE (ICE), often **with metadata encryption** | FBE credential-encrypted only; metadata encryption **no** |
| 11 (crDroid 7.9, last official) | FBE + metadata | as above |
| 12 / 13 | FBE + metadata, keymaster 4.0 in ROM (not vendor) | as above |
| 14 / 15 (LineageOS 22.x) | FBE + metadata, ROM enforces encryption | as above; upstream maintainer says "FBE build, don't use twrp" |
| 16 / 17 | identical crypto model to 15 | no ROM exists for sakura (see `ANDROID_COMPATIBILITY.md`) |

Three separate mechanisms must not be conflated:

1. **FDE** (`encryptable=footer`) — dm-crypt over the whole block device.
   Supported by the port.
2. **FBE** (`fileencryption=ice`) — per-file keys, `/data` has
   `keydirectory=`; needs kernel `fscrypt` + ICE + keymaster/gatekeeper to
   unwrap keys. Supported **only** with the 4.9 kernel; unverified on device.
3. **Metadata encryption** (`metadata_encryption=` / `dm-default-key`) — needs
   a keymaster that can derive a storage key (KM 4.0/KeyMint) and kernel
   `dm-default-key`. **Not supported by either available kernel**, therefore
   out of scope for any single sakura R12 build.

## 4. Honest conclusion

A **single** R12.0 configuration cannot decrypt every Android 9–17 ROM on this
hardware, and the blocker is architectural, not a build flag:

* Metadata encryption requires `dm-default-key` (absent from both kernels we
  can boot) and a KM4/KeyMint-backed storage key (the sakura vendor is KM3.0).
  A 3.18/4.9 kernel cannot be given this without a kernel backport plus a
  vendor HAL that does not exist on this device. Porting `dm-default-key` to
  4.9 is conceivable but is a kernel research project with no guarantee, and
  cannot be validated without hardware.
* Therefore the achievable target is: **FDE (Android 9) + FBE without metadata
  (Android 10+)**, using the 4.9 kernel and `qcom_decrypt` +
  `qcom_decrypt_fbe`.

### Least-disruptive strategy recommended

1. Build **one** recovery using the 4.9 kernel with `qcom_decrypt` +
   `qcom_decrypt_fbe` and a multi-fstype fstab (`/data` f2fs **and** ext4,
   `fileencryption=ice`, `encryptable=footer` retained for FDE ROMs).
2. **Do not** set `OF_FBE_METADATA_MOUNT_IGNORE` silently; instead document that
   metadata-encrypted `/data` will mount only after "Format Data" or via
   "Decrypt with PIN" where the ROM is FBE-only.
3. If a specific ROM turns out to be metadata-encrypted only, the documented
   fallback is: **mount `/data` as read-only / use `adb push`+sideload and
   `Format Data`**, or boot the ROM once to remove encryption. That is the least
   disruptive alternative to a second build variant.
4. If two variants ever become necessary, they differ *only* in fstab/kernel
   flags, not in the recovery UI — so they can be produced from the same tree by
   a build-time switch (`FOX_SAKURA_LEGACY_FDE=1`), which is already stubbed in
   `device/`.

## 5. What must change vs R11

| Component | R11.0_5 | R12.0 port | Why |
|---|---|---|---|
| `/data` fstab | ext4 + footer | f2fs **and** ext4, `fileencryption=ice`, keep `encryptable=footer` | support both FBE and legacy FDE |
| `/system` | ext4, SAR auto-detect | `/system_root` entries in twrp.flags (as community tree) | modern ROMs are system-as-root |
| kernel | 3.18.120 stock (no fscrypt) | 4.9.278 with fscrypt + f2fs | FBE requires it |
| crypto packages | libcryptfsfde + KM3 | `qcom_decrypt` + `qcom_decrypt_fbe`, KM3.0 HAL | R12's decryption framework |
| metadata encryption | n/a | **not supported — documented** | no dm-default-key / KM4 |
| keymaster version | 3.0 | 3.0 (`OF_DEFAULT_KEYMASTER_VERSION := 3.0`) | vendor reality |

## 6. Verification status

| Item | Status |
|---|---|
| fstab flags parse as separate tokens | **fixed + statically enforced** — comma-separated; `tools/static_checks.py` and `build/verify_image.sh` fail on `;` |
| FDE footer decryption | **not tested** (no hardware); same mechanism as R11 |
| FBE (ICE) decryption | **not tested**; kernel capability verified by string evidence only |
| Metadata encryption | **not supportable** — proven absent from both kernels |
| Keymaster 3.0 / Gatekeeper 1.0 / qseecomd present | **missing in the audited image** — see `IMAGE_AUDIT.md`; blobs are proprietary and not committed |
| Keymaster 3.0 service start in recovery | **not tested** |

Consequence: with the QTI blobs absent, **no decryption capability is claimed
for any image built from this tree**. The fstab declares both mechanisms so a
build that *does* include the extracted blobs can attempt them, and
`build/check_crypto_blobs.sh` / `build/verify_image.sh` state that status
plainly instead of inferring success from a flag.

One further caution, learned from the audited image: FBE without a working
gatekeeper/keymaster chain makes TWRP block on the splash instead of failing
cleanly. If you build without the blobs and `/data` is FBE-encrypted, expect
that behaviour; the documented workaround is `Format Data` (data loss) or
building with `OF_SKIP_FBE_DECRYPTION=1` for that ROM generation.

Never advertise decryption as working until `testing/android-*/` records a real
`Decryption tested` result.
