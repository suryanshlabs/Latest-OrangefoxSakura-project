# Android 9–17 compatibility

## 0. The honest headline

The requested range is Android 9 → 17. What the evidence actually supports:

* **Android 9**: strongly supported (same crypto model as R11; FDE footer).
* **Android 10–15**: *expected* to boot and mount storage; **FBE decryption is
  unproven**, and metadata-encrypted `/data` is **not supportable** (no
  `dm-default-key`, no KM 4.0/KeyMint on this vendor — `ENCRYPTION.md`).
* **Android 16–17**: **no sakura ROM or device tree exists** as of
  November 2026, so compatibility cannot be claimed at all.

Anyone marketing this port as "Android 9–17 fully working" would be making a
claim the evidence does not support. The matrix below uses the brief's status
vocabulary and only records what was actually done.

## 1. Ecosystem reality (checked, not assumed)

| Finding | Evidence |
|---|---|
| No *current* custom ROM ships for sakura | TheCustomRom device page (synced 2026-11-13): "no custom ROM ships a current build for the Xiaomi Redmi 6 Pro (sakura)"; LineageOS does not list `sakura` |
| Newest public sakura device tree | `xiaomi-msm8953-devs/android_device_xiaomi_sakura@lineage-22.2` = **Android 15**; `msm8953E/device_xiaomi_sakura@A15` = Android 15 |
| Newest community ROM thread | XDA "LineageOS 22.2 for sakura" (Android 15), notes: *"FBE build, don't use twrp for these builds"*, SELinux enforcing, custom kernels unsupported |
| Last official-ish ROM build | crDroid 7.9 (Android 11), 2021-08-09 |
| Android 16 trees (LineageOS 23.x) for sakura | **none found** (`lineage-23`/`A16` branches absent from all sakura repos checked) |
| Android 17 trees (LineageOS 24+) for sakura | **none found** |
| Stock end state | MIUI 12, Android 9, `V12.0.1.0.PDICNXM` / `V12.0.4.0.PDMMIXM` |

Branch inventory checked (all heads enumerated): `msm8953E/device_xiaomi_sakura`
{A14, A15, DSP-wip, UDC, dxui-14, lineage-21};
`msm8953E/device_xiaomi_sakura_twrp` {a12, ofx-12.1, ofx-12.1_daisy};
`xiaomi-msm8953-devs/android_device_xiaomi_sakura`
{lineage-20, lineage-21, lineage-22.1, lineage-22.2}.

## 2. Compatibility matrix

Status vocabulary: Research only · Source verified · Build verified ·
Boot tested · Feature tested · Decryption tested · Fully validated.
**No hardware was available for this project**, so no row can exceed
"Source verified".

| Android | Representative ROM | `/data` crypto | Recovery status | Notes |
|---|---|---|---|---|
| 9 | MIUI 12 stock (`V12.0.x.PDI*`), crDroid-era | FDE footer | **Source verified** | Same model as R11.0_5, which shipped; lowest risk |
| 10 | AOSP/Pixel-Experience ports for MSM8953 | FBE(+metadata) | **Source verified** | metadata-encrypted data not mountable |
| 11 | crDroid 7.9 (last A11 build, 2021-08) | FBE(+metadata) | **Source verified** | |
| 12 | LineageOS 19-era community builds | FBE(+metadata) | **Source verified** | |
| 13 | LineageOS 20 (`lineage-20` tree exists) | FBE(+metadata) | **Source verified** | tree exists → ROM plausible |
| 14 | `msm8953E/device_xiaomi_sakura@A14`, `@lineage-21` | FBE(+metadata) | **Source verified** | |
| 15 | LineageOS 22.2 (`lineage-22.2` tree), A15 tree | FBE(+metadata) | **Source verified** | upstream says "don't use twrp" for these builds |
| 16 | — | — | **Research only** | no sakura tree/branch exists |
| 17 | — | — | **Research only** | no sakura tree/branch exists |

Legend for what "Source verified" means here: the ROM's device tree, fstab
naming, kernel config and cmdline were inspected and are consistent with the
planned recovery configuration. It does **not** mean the recovery boots.

## 3. Why one build *should* cover 9–15 (and where it cannot)

A single recovery can cover 9–15 because the differences that matter are
runtime, not build-time:

| Difference | Handled by |
|---|---|
| system-as-root vs system | `/system_root` + `OF_USE_TWRP_SAR_DETECT` |
| ext4 vs f2fs `/data` | both rows in fstab |
| FDE vs FBE | `qcom_decrypt` + `qcom_decrypt_fbe` + `fileencryption=ice` row |
| kernel features | 4.9 kernel (f2fs, fscrypt) |
| Treble/vndk | `OF_NO_TREBLE_COMPATIBILITY_CHECK := 1` (community tree) |

It **cannot** cover metadata-encrypted `/data` because that needs kernel
`dm-default-key` + keymaster 4.0/KeyMint, neither of which exists for sakura
(measured: `KERNEL_ANALYSIS.md` §2; `ENCRYPTION.md` §4). If, during real
testing, a target ROM turns out to be metadata-encrypted, the workaround is
"Format Data / boot ROM once" rather than a second recovery variant; a variant
would not help because the kernel lacks the feature in both cases.

Android 16/17 would need a ROM first. If such a ROM appears, the same recovery
is expected to remain applicable (same crypto model, same partitions), but that
must be re-verified — it is not supported today.

## 4. Per-generation test contract

`testing/android-N/TEST_RECORD.md` exists for N = 9…17. Each file must be filled
only with observed results:

```
ROM name / source URL / device tree ref / kernel ref /
encryption method / recovery boot result / storage result /
decryption result / ZIP install result / backup+restore result /
known issues / status
```

Empty or template-only files mean **not tested** — they must never be reported
as working.
