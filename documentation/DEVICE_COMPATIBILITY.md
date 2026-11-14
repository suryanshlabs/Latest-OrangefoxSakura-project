# Device compatibility — sakura vs daisy, partitions, and what must be proven

## 1. Identity

| Field | Value |
|---|---|
| Marketing name | Xiaomi Redmi 6 Pro |
| Codename | `sakura` |
| Variant codename | `sakura_india` (India; same hardware family, different factory images) |
| SoC | Qualcomm Snapdragon 625, MSM8953 |
| Architecture | arm64 (`arm64-v8a`) primary, `armeabi-v7a` secondary |
| Launch Android | 8.1 → last stock 9 (MIUI 12, `V12.0.x.x.PDI*`) |
| Screen | 1080×2280 (FHD+), hence `OF_SCREEN_H := 2280` |
| Display panels | `ili7807` FHD+, `nt36672` (tianma/csot) FHD+ |
| Cameras | `sakura_imx486_ofilm` / `ov12a10_sunny` (main), `ov5675` / `s5k5e8` (front, ofilm/sunny/qtech variants) |
| Touch | focaltech `ft5435`/`ft5436`, goodix, novatek `nt36672`, synaptics |
| Recovery partition | real, dedicated, 64 MiB (`67108864`) |
| Boot image | Android boot v0, page size 2048, `kernel 0x80008000`, `ramdisk 0x81000000`, tags 0x80000100 |
| Boot device | `7824900.sdhci` (referenced by boot cmdline and `init.recovery.qcom.rc`) |
| OrangeFox install partition (community tree) | `/dev/block/mmcblk0p49` |

## 2. Partition layout as observed

From the R11 fstab and the sakura trees, sakura uses **fixed** partitions via
`/dev/block/bootdevice/by-name/*`:

```
boot, cache, recovery, system, vendor, userdata, cust, misc,
modem, modemst1, modemst2, fsg, fsc, persist, dsp, ...
```

Crucially:

* **No `super` partition, no dynamic partitions.** `BOARD_SUPER_PARTITION_*`
  does not appear in `msm8953E/device_xiaomi_sakura@A15`, and
  `BOARD_AVB_ENABLE := false` there.
* `/data` is `userdata`; `/cache` ext4; `/system` + `/vendor` ext4 mounted
  system-as-root on modern ROMs.
* `BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864`,
  `BOARD_RECOVERYIMAGE_PARTITION_SIZE := 67108864`,
  `BOARD_SYSTEMIMAGE_PARTITION_SIZE := 3221225472`,
  `BOARD_VENDORIMAGE_PARTITION_SIZE := 872415232`,
  `BOARD_USERDATAIMAGE_PARTITION_SIZE := 25765043200`.

This is why `fox_12.1` (non-dynamic-partition era) is sufficient for the
recovery build: there is no `super`/`vbmeta` gymnastics to support.

## 3. Sakura vs daisy — evidence that they must not be merged

`sakura` (Redmi 6 Pro) and `daisy` (Mi A2 Lite) share MSM8953 and look similar
in trees, so the brief's warning is well founded. Concrete evidence found in
this project:

1. The selected recovery tree `msm8953E/device_xiaomi_sakura_twrp` carries a
   **separate `ofx-12.1_daisy` branch** (`2659a2abd3be9c336f61b7d705d09f0bd239daa`)
   — proof the maintainers themselves treat them as distinct ports.
2. That same tree's `proprietary-files.txt` is headed:
   *"Not appended blobs from **daisy**-user 10 QKQ1.191002.002 V11.0.21.0.QDLMIXM release-keys"*.
3. Its `README.md` says the kernel source is
   `TWRP-Mi-A2-Lite/twrp_kernel_xiaomi_daisy`.

So the community sakura R12 tree is **partly derived from daisy**. Its
`proprietary-files.txt` blobs (gatekeeper/keymaster/qseecomd/libQSEEComAPI/
keystore.msm8953/gatekeeper.msm8953 …) are Android 10 daisy vendor blobs, not
sakura Android 9 blobs. They may be ABI-compatible (same SoC family, same
`ro.hardware.keystore=msm8953`), but **that is an assumption, not proof**.

**Policy for this port:**

* The device tree treats those prebuilts as *unverified* and labels them as
  such in `device/proprietary-files.txt`.
* `DEPENDENCIES.md` gives the procedure to replace them with blobs pulled from a
  **sakura** stock image (`V12.0.x.x.PDI*`) and to compare SHA-1s.
* Nothing from `ofx-12.1_daisy` is copied.

## 4. What is proven vs assumed

| Property | Scenario | Status |
|---|---|---|
| Kernel boots sakura | R11.0_5 kernel | **Proven** by shipping 2021 release (indirect) |
| 4.9.278 kernel boots sakura | community ofx-12.1 tree | **Assumed** — no hardware test here; the tree exists and is public |
| `sakura` camera/panel nodes in DTB | extracted from both kernels | **Proven** (strings) |
| Partition names | R11 fstab + trees | **Proven** |
| Recovery install path `mmcblk0p49` | community tree vendosetup | **Assumed** — must be verified on device with `by-name/recovery` |
| Touch works | needs `TW_INPUT_BLACKLIST="hbtp_vm"` | **Assumed**, inherited |
| Display brightness path `/sys/class/leds/lcd-backlight/brightness` | trees | **Assumed** |
| sakura vendor blobs compatible with daisy-derived set | — | **Unproven**, see §3 |

## 5. Device-detection safety

R11 used `OF_TARGET_DEVICES="sakura,sakura_india"`, which prevents flashing the
ZIP on a daisy. This must be preserved in the R12 port (`OF_TARGET_DEVICES` in
`device/fox_sakura.mk`, and `FDEVICE="sakura"` in `vendorsetup.sh`). Never
loosen this to a generic MSM8953 list — that is precisely how a daisy user
bricks a sakura or vice versa.
