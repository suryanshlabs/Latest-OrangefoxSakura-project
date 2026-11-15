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
# Decryption: OrangeFox qcom_decrypt (FDE) + qcom_decrypt_fbe (FBE)
# Provided by the vendor/recovery tree.
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    qcom_decrypt \
    qcom_decrypt_fbe

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
