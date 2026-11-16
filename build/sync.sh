#!/usr/bin/env bash
#
# sync.sh - sync OrangeFox R12.0 (fox_12.1) sources at pinned revisions and
# graft this repository's device tree into the source tree.
#
# Requirements: >=45 GB free, git, repo (Google launcher), python3.
# Do NOT run as root (official guide).
#
# Usage: ./build/sync.sh /absolute/path/to/fox_12.1
#        ./build/sync.sh --relink-only /absolute/path/to/fox_12.1
#
# --relink-only skips the network sync and only (re)links this repository's
# device tree into an existing checkout. It is what CI uses when the tree is
# reused between runs, so a reused tree never silently keeps an old device
# tree.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELINK_ONLY=0
if [ "${1:-}" = "--relink-only" ]; then
    RELINK_ONLY=1
    shift
fi
DEST="${1:-}"

# ---- pinned revisions ------------------------------------------------------
SYNC_REPO="https://gitlab.com/OrangeFox/sync.git"
SYNC_SHA="73d4d94e0d1b11b9035dea72ee223d25b1fefa7c"
FOX_BRANCH="12.1"                       # produces release R12.0
MIN_MANIFEST_SHA="6dc117d9cbd08430daa16db2013560e1c4017fa8"
RECOVERY_REPO="https://gitlab.com/OrangeFox/bootable/Recovery.git"
RECOVERY_SHA="8d2aad19deb158e935d70ca5b648162c2b2831ee"
VENDOR_REPO="https://gitlab.com/OrangeFox/vendor/recovery.git"
VENDOR_SHA="1998cfcaca9bb247ea20d587e565676faa281de9"

die() { echo "ERROR: $*" >&2; exit 1; }

[ -n "$DEST" ] || die "usage: $0 [--relink-only] /absolute/path/to/fox_12.1"
case "$DEST" in /*) ;; *) die "--path must be absolute (repo requirement)";; esac
[ "$(id -u)" != "0" ] || die "do not run as root"

if [ "$RELINK_ONLY" = 0 ]; then
    avail_gb=$(df -BG --output=avail "$(dirname "$DEST")" | tail -1 | tr -dc '0-9')
    [ "${avail_gb:-0}" -ge 45 ] || die "need >=45 GB free, have ${avail_gb} GB"
    command -v repo >/dev/null || die "repo not found: install the Google repo launcher"
    mkdir -p "$DEST"

    # ---- 1. official sync tooling at the pinned commit ---------------------
    SYNC_DIR="$(mktemp -d)"
    echo "==> fetching OrangeFox sync tooling @ ${SYNC_SHA:0:12}"
    git clone -q "$SYNC_REPO" "$SYNC_DIR/sync"
    git -C "$SYNC_DIR/sync" checkout -q "$SYNC_SHA"

    # ---- 2. sync sources --------------------------------------------------
    echo "==> syncing fox_${FOX_BRANCH} (this takes a long time)"
    echo "    the official script also clones the OrangeFox recovery + vendor trees"
    ( cd "$SYNC_DIR/sync" && ./orangefox_sync.sh --branch "$FOX_BRANCH" --path "$DEST" )

    # ---- 3. report / pin the refs the script produced ---------------------
    pin() { # <name> <dir> <expected>
        local name="$1" dir="$2" want="$3" got
        [ -d "$dir/.git" ] || { echo "  ! $name missing at $dir"; return; }
        got=$(git -C "$dir" rev-parse HEAD)
        if [ "$got" = "$want" ]; then
            echo "  = $name @ ${got:0:12} (pinned)"
        else
            echo "  ~ $name @ ${got:0:12} (pinned ref was ${want:0:12})"
            echo "    re-checkout with: git -C $dir checkout $want"
        fi
    }

    echo "==> upstream revisions in the tree"
    pin "bootable/recovery"    "$DEST/bootable/recovery"    "$RECOVERY_SHA"
    pin "vendor/recovery"      "$DEST/vendor/recovery"      "$VENDOR_SHA"
    if [ -d "$DEST/.repo/manifests/.git" ]; then
        pin "minimal manifest"  "$DEST/.repo/manifests"     "$MIN_MANIFEST_SHA"
    fi
fi

# ---- 4. graft this repository's device tree -------------------------------
# A copy is used (not a symlink into the checkout) so the build runs on the
# exact files committed here and CI can re-copy them on every reuse.
if [ "$RELINK_ONLY" = 1 ]; then
    rsync -a --delete --exclude 'prebuilt/Image.gz-dtb' \
          "${ROOT}/device/xiaomi/sakura/" "$DEST/device/xiaomi/sakura/"
    echo "==> device tree refreshed from this repository"
else
    mkdir -p "$DEST/device/xiaomi"
    if [ -e "$DEST/device/xiaomi/sakura" ] && [ ! -L "$DEST/device/xiaomi/sakura" ]; then
        echo "==> device/xiaomi/sakura already exists and is not a symlink; leaving it alone"
    else
        ln -sfn "${ROOT}/device/xiaomi/sakura" "$DEST/device/xiaomi/sakura"
        echo "==> linked device tree -> $DEST/device/xiaomi/sakura"
    fi
fi

[ "$RELINK_ONLY" = 0 ] && rm -rf "$SYNC_DIR"

cat <<EOF

Sync complete: $DEST

Next, or instead use the one-command driver:
  ./build/run-all.sh $DEST

  (it runs: kernel fetch -> build -> structural verify, and prints the sha256)

Note: the official script patches vendor/twrp so that inheriting
vendor/twrp/config/common.mk yields the OrangeFox UI. Do not skip that step,
or you will get a plain TWRP build.
EOF
