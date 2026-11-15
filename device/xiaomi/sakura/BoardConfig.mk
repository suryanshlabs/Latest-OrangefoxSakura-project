#
# BoardConfig.mk — OrangeFox R12.0 (fox_12.1) for Xiaomi Redmi 6 Pro (sakura)
#
# Derived from the R11.0_5 reference recovery (see documentation/REFERENCE_R11_ANALYSIS.md)
# and the public community tree msm8953E/device_xiaomi_sakura_twrp@ofx-12.1,
# with the defects listed in documentation/SOURCE_REFERENCES.md §B1 corrected.
#
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/xiaomi/sakura

# ---------------------------------------------------------------------------
# Architecture (MSM8953: 4x Cortex-A53)
# ---------------------------------------------------------------------------
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_ABI2 :=
TARGET_CPU_VARIANT := cortex-a53

TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv8-a
TARGET_2ND_CPU_ABI := armeabi-v7a
TARGET_2ND_CPU_ABI2 := armeabi
TARGET_2ND_CPU_VARIANT := cortex-a53

# ---------------------------------------------------------------------------
# Platform / bootloader
# ---------------------------------------------------------------------------
TARGET_BOARD_PLATFORM := msm8953
TARGET_BOOTLOADER_BOARD_NAME := MSM8953
TARGET_NO_BOOTLOADER := true

# ---------------------------------------------------------------------------
# Kernel
#
# R11.0_5 shipped Xiaomi's stock 3.18.120 kernel, which has NO fscrypt and NO
# f2fs (measured — documentation/KERNEL_ANALYSIS.md §2). That makes FBE and
# f2fs /data impossible, so R12 uses the 4.9 kernel that adds both.
#
# The prebuilt Image.gz-dtb MUST be gzip Image + appended sakura multi-DTB
# inside the kernel slot (dt_size stays 0), exactly like R11.
# ---------------------------------------------------------------------------
TARGET_PREBUILT_KERNEL := $(DEVICE_PATH)/prebuilt/Image.gz-dtb

BOARD_KERNEL_CMDLINE := androidboot.hardware=qcom msm_rtb.filter=0x237 ehci-hcd.park=3 \
    lpm_levels.sleep_disabled=1 androidboot.bootdevice=7824900.sdhci \
    androidboot.selinux=permissive audit=0
BOARD_KERNEL_BASE := 0x80000000
BOARD_KERNEL_PAGESIZE := 2048
BOARD_KERNEL_TAGS_OFFSET := 0x00000100
# += not := — TWRP adds its own mkbootimg args; := would discard them.
BOARD_RAMDISK_OFFSET := 0x01000000
BOARD_MKBOOTIMG_ARGS += --header_version 0

# ---------------------------------------------------------------------------
# Partitions (fixed layout — sakura has no dynamic/super partition)
# ---------------------------------------------------------------------------
BOARD_FLASH_BLOCK_SIZE := 131072
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 67108864
BOARD_CACHEIMAGE_PARTITION_SIZE := 268435456
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 3221225472
BOARD_VENDORIMAGE_PARTITION_SIZE := 872415232
BOARD_USERDATAIMAGE_PARTITION_SIZE := 25765043200

BOARD_BUILD_SYSTEM_ROOT_IMAGE := true
BOARD_USES_FULL_RECOVERY_IMAGE := true
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := ext4
TARGET_COPY_OUT_VENDOR := vendor
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true
BOARD_SUPPRESS_SECURE_ERASE := true

# R11.0_5 used a legacy v2 fstab in the ramdisk; R12 parses a 5-column AOSP
# fstab for vold/crypto and twrp.flags for the mount list.
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/recovery/root/system/etc/recovery.fstab

# ---------------------------------------------------------------------------
# Crypto
#
# qcom_decrypt      -> FDE (crypto footer), Android 9-era ROMs
# qcom_decrypt_fbe  -> FBE (fileencryption=ice), Android 10+ ROMs
# Keymaster 3.0 is what the sakura Android 9 vendor actually provides.
#
# Metadata encryption (dm-default-key + KM4/KeyMint) is NOT available on this
# device; see documentation/ENCRYPTION.md §4. Do not enable the metadata
# options here — it would silently produce a build that cannot mount the data
# it claims to decrypt.
# ---------------------------------------------------------------------------
TW_INCLUDE_CRYPTO := true
BOARD_USES_QCOM_FBE_DECRYPTION := true
TW_INCLUDE_FBE := true
BOARD_USES_METADATA_PARTITION := false

# ---------------------------------------------------------------------------
# Treble / vintf
#
# PRODUCT_ENFORCE_VINTF_MANIFEST is deliberately NOT set.
# Enforcing the vintf manifest requires DEVICE_MANIFEST_FILE / DEVICE_MATRIX_FILE
# to be provided by the tree; this port ships no such files (R11.0_5 shipped
# none either — its ramdisk had no vendor/etc/vintf/manifest.xml). Turning
# enforcement on without them fails the build or produces a recovery that
# cannot start its HALs. If sakura-correct vintf manifests are later extracted
# from the stock vendor image, set DEVICE_MANIFEST_FILE and then re-enable.
# ---------------------------------------------------------------------------
PRODUCT_FULL_TREBLE_OVERRIDE := true

# ---------------------------------------------------------------------------
# Init
#
# R11.0_5 shipped NO device-side libinit: it configured everything through
# init.recovery.qcom.rc + default.prop. The 2024 community tree added a Soong
# libinit_sakura; that source is not part of this repository and cannot be
# build-verified here, so this port deliberately keeps the R11 approach and
# sets the needed props from product overrides (device.mk). This is a
# reduction in unverifiable surface area, not a lost feature.

# ---------------------------------------------------------------------------
# Recovery / TWRP-OrangeFox display + hardware
# ---------------------------------------------------------------------------
TW_THEME := portrait_hdpi
TW_SCREEN_BLANK_ON_BOOT := true
TW_NO_SCREEN_BLANK := true
TW_BRIGHTNESS_PATH := "/sys/class/leds/lcd-backlight/brightness"
TW_MAX_BRIGHTNESS := 255
TW_DEFAULT_BRIGHTNESS := 150
TW_INPUT_BLACKLIST := "hbtp_vm"
TARGET_RECOVERY_PIXEL_FORMAT := "RGBX_8888"
TARGET_RECOVERY_QCOM_RTC_FIX := true
RECOVERY_SDCARD_ON_DATA := true
TW_USE_LEGACY_BATTERY_SERVICES := true
TW_USE_TOOLBOX := true

# External storage / filesystems
TW_INCLUDE_FUSE_NTFS := true
TW_INCLUDE_NTFS_3G := true
TW_INCLUDE_REPACKTOOLS := true
TW_INCLUDE_LIBRESETPROP := true
TW_INCLUDE_RESETPROP := true

# Debugging
TWRP_INCLUDE_LOGCAT := true
TARGET_USES_LOGD := true
TARGET_RECOVERY_DEVICE_MODULES += debuggerd
RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/debuggerd
TARGET_RECOVERY_DEVICE_MODULES += strace
RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/strace

# Build tolerances for this legacy platform on a 12.1 base.
# (ALLOW_MISSING_DEPENDENCIES is an *environment* variable read by the build
# system, not a make variable — it is exported by build/build.sh. Setting it
# here would have no effect.)
BUILD_BROKEN_ELF_PREBUILT_PRODUCT_COPY_FILES := true
BUILD_BROKEN_DUP_RULES := true

# --- export TWRP variables to Soong -------------------------------------
# vendor/twrp/config/BoardConfigSoong.mk declares the Soong vendor config
# namespace "twrpVarsPlugin" and exports TW_THEME, TW_CUSTOM_THEME,
# TW_EXTRA_LANGUAGES, TW_SCREEN_BLANK_ON_BOOT, TW_NO_SCREEN_BLANK and friends.
# bootable/recovery/gui/libguitwrp_defaults.go reads TW_THEME only through that
# namespace: without this include the theme resolves to "", the theme files are
# copied one level down (twres/portrait_hdpi/... instead of twres/...), and the
# recovery module's post-install sed on twres/splash.xml fails.
# It must come after TW_THEME is set above.
include vendor/twrp/config/BoardConfigSoong.mk
