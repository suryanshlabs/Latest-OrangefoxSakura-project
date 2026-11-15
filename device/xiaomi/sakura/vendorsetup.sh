#
# vendorsetup.sh — OrangeFox build variables for sakura
#
# The FOX_*/OF_* values below are ported from the R11.0_5 reference build
# (META-INF/debug/fox_build_vars.txt, extracted from the official ZIP) so the
# R12 port preserves the behaviour users already had, unless a value had to
# change for R12 and is annotated as such.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#

FDEVICE="sakura"

fox_get_target_device() {
    local chkdev
    chkdev=$(echo "$BASH_SOURCE" | grep -w "$FDEVICE")
    if [ -n "$chkdev" ]; then
        FOX_BUILD_DEVICE="$FDEVICE"
    else
        chkdev=$(set | grep BASH_ARGV | grep -w "$FDEVICE")
        [ -n "$chkdev" ] && FOX_BUILD_DEVICE="$FDEVICE"
    fi
}

if [ -z "$1" ] && [ -z "$FOX_BUILD_DEVICE" ]; then
    fox_get_target_device
fi

if [ "$1" = "$FDEVICE" ] || [ "$FOX_BUILD_DEVICE" = "$FDEVICE" ]; then

    # --- device identity / installer guard -------------------------------
    # R11 used "sakura,sakura_india". Keep it: this is the check that stops a
    # Mi A2 Lite (daisy) user flashing this ZIP. Never widen this list.
    export OF_TARGET_DEVICES="sakura,sakura_india"

    # --- shell & tools (identical to R11.0_5) ----------------------------
    export FOX_USE_BASH_SHELL=1
    export FOX_ASH_IS_BASH=1
    export FOX_USE_TAR_BINARY=1
    export FOX_USE_XZ_UTILS=1
    export FOX_USE_ZIP_BINARY=1
    export FOX_USE_NANO_EDITOR=1
    export FOX_DELETE_AROMAFM=1

    # --- R12 additions (not present in R11) ------------------------------
    # App manager and LP tools exist in R12 and are useful on a stock-kernel
    # era device; both are optional OrangeFox features.
    export FOX_ENABLE_APP_MANAGER=1
    export OF_ENABLE_LPTOOLS=1

    # --- encryption behaviour --------------------------------------------
    # R11: OF_SKIP_FBE_DECRYPTION=1 (its kernel had no fscrypt).
    # R12: the 4.9 kernel HAS fscrypt, so FBE decryption is attempted.
    #      FDE (footer) is still supported by qcom_decrypt for Android 9 ROMs.
    # Metadata encryption is not supportable on this vendor/kernel — see
    # documentation/ENCRYPTION.md §4. Do not set OF_FBE_METADATA_MOUNT_IGNORE
    # to 1: failing loudly is safer than silently mounting nothing.
    unset OF_SKIP_FBE_DECRYPTION
    export OF_DONT_PATCH_ENCRYPTED_DEVICE=1
    export OF_KEEP_FORCED_ENCRYPTION=1

    # --- AVB / verity / MIUI ---------------------------------------------
    export OF_PATCH_AVB20=1
    export OF_FORCE_DISABLE_DM_VERITY=1
    export OF_FORCE_MAGISKBOOT_BOOT_PATCH_MIUI=1
    export OF_USE_MAGISKBOOT=1
    export OF_USE_NEW_MAGISKBOOT=1
    export OF_USE_MAGISKBOOT_FOR_ALL_PATCHES=1
    export OF_NO_MIUI_PATCH_WARNING=1
    export OF_DISABLE_MIUI_OTA_BY_DEFAULT=1
    export OF_SUPPORT_ALL_BLOCK_OTA_UPDATES=1
    export OF_OTA_RES_DECRYPT=1
    export OF_NO_MIUI_OTA_VENDOR_BACKUP=1
    export OF_FIX_OTA_UPDATE_MANUAL_FLASH_ERROR=1

    # --- layout / misc ----------------------------------------------------
    export OF_SCREEN_H=2280
    export OF_STATUS_H=95
    export OF_STATUS_INDENT_LEFT=50
    export OF_STATUS_INDENT_RIGHT=50
    export OF_CLOCK_POS=1
    export OF_ALLOW_DISABLE_NAVBAR=0
    export OF_USE_TWRP_SAR_DETECT=1
    export OF_QUICK_BACKUP_LIST="/boot;/data;/system_image;/vendor_image;"
    export OF_OPTIONS_LIST_NUM=6
    export OF_NO_TREBLE_COMPATIBILITY_CHECK=1
    export OF_UNBIND_SDCARD_F2FS=1

    # Keymaster actually available on the sakura Android 9 vendor.
    export OF_DEFAULT_KEYMASTER_VERSION=3.0

    # Recovery install target.
    # The community tree hard-codes "/dev/block/mmcblk0p49", a raw partition
    # number that nobody verified for sakura. Flashing a recovery image to the
    # wrong partition number is the fastest way to hard-brick a device, so this
    # uses the by-name symlink instead, which is correct by construction as long
    # as the boot device is 7824900.sdhci (it is, per the boot cmdline).
    # Verify once on device: ls -l /dev/block/bootdevice/by-name/recovery
    export FOX_RECOVERY_INSTALL_PARTITION="/dev/block/bootdevice/by-name/recovery"

    # Optional: pin a specific Magisk zip. R11 bundled Magisk.zip from FoxFiles
    # instead, so this stays unset by default.
    # export FOX_USE_SPECIFIC_MAGISK_ZIP="$HOME/Magisk-v27.0.zip"

else
    if [ -z "$FOX_BUILD_DEVICE" ] && [ -z "$BASH_SOURCE" ]; then
        echo "I: This script requires bash. Not processing the $FDEVICE $(basename "$0")"
    fi
fi
