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

# Do not bake build timestamps into the image: keeps rebuilds reproducible.
PRODUCT_SYSTEM_PROPERTY_BLACKLIST += \
    ro.bootimage.build.date.utc \
    ro.build.date.utc

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
# Full recovery image (dedicated 64 MiB recovery partition, as on R11)
# ---------------------------------------------------------------------------
PRODUCT_PROPERTY_OVERRIDES += \
    ro.twrp.version=3.7.1

# ---------------------------------------------------------------------------
# Health HAL is required by PRODUCT_ENFORCE_VINTF_MANIFEST on 12.1
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.health@2.0-service
