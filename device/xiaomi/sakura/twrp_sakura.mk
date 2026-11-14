#
# Plain TWRP product for sakura — build fallback / A-B comparison only.
#
# The OrangeFox target is fox_sakura.mk. This exists so that, if the OrangeFox
# vendor patch is not applied, a stock TWRP recovery can still be produced to
# isolate whether a failure is device-side or OrangeFox-side.
#
# SPDX-License-Identifier: Apache-2.0
#

PRODUCT_RELEASE_NAME := sakura

$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/aosp_base.mk)
$(call inherit-product, device/xiaomi/sakura/device.mk)
$(call inherit-product, vendor/twrp/config/common.mk)

PRODUCT_DEVICE := sakura
PRODUCT_NAME := twrp_sakura
PRODUCT_BRAND := Xiaomi
PRODUCT_MODEL := Redmi 6 Pro
PRODUCT_MANUFACTURER := Xiaomi
