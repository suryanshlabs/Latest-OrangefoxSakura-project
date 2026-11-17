#
# device.mk — recovery-side packages, props and prebuilt modules for sakura
#
# SPDX-License-Identifier: Apache-2.0
#

# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------
PRODUCT_PROPERTY_OVERRIDES += \
    ro.hardware.keystore=msm8953

# NOTE: PRODUCT_SYSTEM_PROPERTY_BLACKLIST (used by the 2024 community tree) is
# obsolete on a 12.1 base and is not used here. The timestamp props are simply
# not referenced anywhere in this tree.

# ---------------------------------------------------------------------------
# Recovery ramdisk files: init fragments and twrp.flags
#
# NOT automatic. The Android build only copies a device tree's recovery/root
# into the ramdisk when the product lists those files explicitly (the standard
# TWRP form is
#   PRODUCT_COPY_FILES += $(call find-copy-subdir-files,*,.../recovery/root,recovery/root)
# and the pinned OrangeFox trees do not add a rule of their own). Before this
# was added, only TARGET_RECOVERY_FSTAB was installed, so init.recovery.qcom.rc,
# init.recovery.qcom_decrypt.rc and twrp.flags never reached the ramdisk: no
# bootdevice symlink, no TEE services, no TWRP flag overrides.
#
# recovery.fstab is installed by TARGET_RECOVERY_FSTAB (BoardConfig.mk) and is
# deliberately not listed here, so two rules never write the same path.
# ---------------------------------------------------------------------------
PRODUCT_COPY_FILES += \
    $(DEVICE_PATH)/recovery/root/init.recovery.qcom.rc:recovery/root/init.recovery.qcom.rc \
    $(DEVICE_PATH)/recovery/root/init.recovery.qcom_decrypt.rc:recovery/root/init.recovery.qcom_decrypt.rc \
    $(DEVICE_PATH)/recovery/root/system/etc/twrp.flags:recovery/root/system/etc/twrp.flags

# ---------------------------------------------------------------------------
# Decryption: TEE-backed FDE + FBE, implemented by bootable/recovery itself
#
# The earlier tree added `PRODUCT_PACKAGES += qcom_decrypt qcom_decrypt_fbe`
# "provided by the vendor/recovery tree". Verified at the pinned revisions
# (vendor/recovery 1998cfc, bootable/recovery 8d2aad19): those modules do not
# exist anywhere upstream - `git grep qcom_decrypt` returns nothing - so the
# argument was false. Decryption support comes from TW_INCLUDE_CRYPTO (which
# sets TW_INCLUDE_CRYPTO_FBE and builds libcryptfsfde/libtwrpfscrypt) plus the
# vendor TEE services that init.recovery.qcom_decrypt.rc starts.
#
# The proprietary TEE files themselves are installed by the generated
# blob_install.mk, written by build/install_blobs.sh from a user-supplied stock
# firmware. -include (not include) keeps a clean clone parseable; the build is
# then refused by build/check_crypto_blobs.sh --require instead of silently
# producing a recovery that cannot decrypt.
# ---------------------------------------------------------------------------
-include $(DEVICE_PATH)/blob_install.mk

# ---------------------------------------------------------------------------
# Recovery modules required by the prebuilt QTI crypto HAL chain and vintf
# ---------------------------------------------------------------------------
TARGET_RECOVERY_DEVICE_MODULES += \
    android.hidl.base@1.0 \
    libdrm \
    libion \
    libxml2 \
    libicuuc \
    vendor.display.config@1.0 \
    vendor.display.config@2.0

RECOVERY_LIBRARY_SOURCE_FILES += \
    $(TARGET_OUT)/lib64/android.hidl.base@1.0.so \
    $(TARGET_OUT_SHARED_LIBRARIES)/libicuuc.so \
    $(TARGET_OUT_SHARED_LIBRARIES)/libpcrecpp.so \
    $(TARGET_OUT_SHARED_LIBRARIES)/libion.so \
    $(TARGET_OUT_SHARED_LIBRARIES)/libxml2.so \
    $(TARGET_OUT_SHARED_LIBRARIES)/libdrm.so \
    $(TARGET_OUT_SYSTEM_EXT_SHARED_LIBRARIES)/vendor.display.config@1.0.so \
    $(TARGET_OUT_SYSTEM_EXT_SHARED_LIBRARIES)/vendor.display.config@2.0.so

# ---------------------------------------------------------------------------
# Battery / health
#
# TW_USE_LEGACY_BATTERY_SERVICES := true in BoardConfig.mk is the R11.0_5
# behaviour in practice: recovery reads the legacy battery sysfs nodes.
# Requiring android.hardware.health@2.0-service here would add a module the
# TWRP minimal manifest does not reliably provide — a build-breaking
# dependency for no benefit. Do not add it back without a health HAL package.
# ---------------------------------------------------------------------------
