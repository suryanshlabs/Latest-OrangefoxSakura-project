# Inspected image audit (handoff artifact)

This file records what was measured on the recovery image supplied with the
project handoff. It is evidence about a **previous** artifact, not about a
build of this tree. No image from this repository has been built yet.

## Artifact

| Field | Value |
|---|---|
| file | `recovery-sakura-fixed.img` |
| size | 36 179 968 bytes |
| SHA-256 | `0a4ae7d20e6dd2232645c794069a121d819e634d070a7452282a6a9642700d33` |
| container | Android boot image v0, page size 2048 |
| kernel addr / ramdisk addr | `0x80008000` / `0x81000000` |

## Measured with this repository's tools

```
python3 tools/bootimg.py unpack recovery-sakura-fixed.img /tmp/img
sha256sum /tmp/img/kernel
  -> d12f816aef3572be156596e0b0c5607c56b309eea4b3e06f052d8509b9867764
python3 tools/bootimg.py cpiotoc /tmp/img/ramdisk.cpio /tmp/img/rd
find /tmp/img/rd -name qseecomd ...
```

| Observation | Result |
|---|---|
| Embedded kernel SHA-256 | `d12f816aef3572be156596e0b0c5607c56b309eea4b3e06f052d8509b9867764` — identical to the documented prebuilt `Image.gz-dtb`, i.e. **not** a fresh kernel compile |
| `system/bin/keystore2` | **present** |
| `qseecomd` | **absent** (neither `/sbin` nor `/system/bin`) |
| `android.hardware.keymaster@3.0-service-qti` | **absent** |
| `android.hardware.gatekeeper@1.0-service-qti` | **absent** |
| Active `fileencryption=ice` in the image fstab | **absent** — fstab carried a comment saying it had been removed |
| In-image fstab `/data` row | `wait,check,encryptable=footer,quota,formattable` (FDE only) |

## What that means

1. The image used the 4.9 prebuilt kernel, so `fscrypt`/f2fs support was present
   — the *kernel* was not the blocker.
2. The QTI crypto chain was incomplete: without `qseecomd`, the Keymaster 3.0
   service and the Gatekeeper 1.0 service, no TEE-backed key unwrap can happen,
   so neither FDE nor FBE can succeed regardless of what the fstab says.
3. The fstab had FBE removed, so FBE was not even attempted.
4. `keystore2` being present proves nothing about keymaster/gatekeeper/qseecomd
   registering or decryption working.

Therefore: **no decryption claim of any kind may be made for that image**, and
no claim is made here. The audit above is static inspection only; nothing was
flashed and no device was booted.

## Consequences for this repository

* The QTI blobs are proprietary and are deliberately not committed. See
  `device/xiaomi/sakura/proprietary-files.txt` and `DEPENDENCIES.md` §4 for the
  licence-safe extraction procedure.
* `build/check_crypto_blobs.sh` reports exactly which listed blobs are missing
  for the current tree.
* `build/verify_image.sh` prints `DECRYPTION: UNVERIFIED` whenever the chain is
  absent from the built ramdisk, instead of implying that FBE works because a
  flag exists.
* The fstab semicolon defect that turned
  `encryptable=footer;fileencryption=ice` into a single malformed token is
  fixed and guarded by `tools/static_checks.py`, so it cannot regress silently.
