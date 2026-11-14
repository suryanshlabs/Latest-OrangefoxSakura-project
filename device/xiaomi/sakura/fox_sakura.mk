#
# OrangeFox product definition for Xiaomi Redmi 6 Pro (sakura)
#
# The community ofx-12.1 tree declared only twrp_sakura.mk while shipping an
# unreferenced fox_sakura.mk, so no OrangeFox product was ever selectable.
# This file fixes that: it is the product you lunch for an OrangeFox build.
#
# SPDX-License-Identifier: Apache-2.0
#

# Release name
PRODUCT_RELEASE_NAME := sakura

# 64-bit-only recovery user space, as measured in R11.0_5
# (ro.product.cpu.abilist64 was empty; abilist = armeabi-v7a,armeabi).
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/aosp_base.mk)

# Hardware-specific part
$(call inherit-product, device/xiaomi/sakura/device.mk)

# TWRP/OrangeFox common configuration.
#
# The OrangeFox sync script patches vendor/twrp ("patch vendor/twrp to pull in
# an OrangeFox makefile", sync v027) so that this inherit yields the OrangeFox
# UI, Fox themes, FoxFiles and the R12 installer. Do not point this at
# vendor/recovery directly: vendor/twrp is the path the script patches.
$(call inherit-product, vendor/twrp/config/common.mk)

# Device identifier — must come after all inclusions
PRODUCT_DEVICE := sakura
PRODUCT_NAME := fox_sakura
PRODUCT_BRAND := Xiaomi
PRODUCT_MODEL := Redmi 6 Pro
PRODUCT_MANUFACTURER := Xiaomi
