#!/usr/bin/env bash
#
# apply_patches.sh - apply this repository's pinned upstream patches.
#
#   ./build/apply_patches.sh --src /path/to/fox_12.1
#   ./build/apply_patches.sh --src /path/to/fox_12.1 --check
#
# Contract
# --------
# * The patch series is patches/series, applied with `git apply` inside
#   $SRC/bootable/recovery.
# * The upstream checkout MUST be the revision recorded in
#   patches/PINNED_REVISIONS. A different revision is refused by default
#   (--allow-revision-mismatch overrides, but the context check still applies).
# * `git apply --check` runs first. If any hunk no longer matches, NOTHING is
#   written and the build stops. A silently-skipped UI patch is worse than a
#   failed build: the image would ship without Error Logs while the docs claim
#   otherwise.
# * Re-running is idempotent. A patch whose reverse check succeeds is already
#   applied and is skipped.
# * --check validates everything and writes nothing.
#
# Exit codes: 0 success / nothing to do, 1 usage or patch failure.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC=""
CHECK_ONLY=0
ALLOW_MISMATCH=0

die() { echo "ERROR: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --src) SRC="${2:-}"; shift 2 ;;
        --src=*) SRC="${1#--src=}"; shift ;;
        --check) CHECK_ONLY=1; shift ;;
        --allow-revision-mismatch) ALLOW_MISMATCH=1; shift ;;
        -h|--help)
            sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) die "unknown argument: $1 (see --help)" ;;
    esac
done

[ -n "$SRC" ] || die "usage: $0 --src /absolute/path/to/fox_12.1 [--check]"
[ -d "$SRC" ] || die "$SRC does not exist"

REC="$SRC/bootable/recovery"
# repo may materialise .git as a directory, a file or a symlink, so ask git
# rather than testing for a directory.
git -C "$REC" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die \
    "$REC is missing or not a git checkout.
       Sync the pinned sources first: ./build/sync.sh $SRC"

SERIES="$ROOT/patches/series"
PINS="$ROOT/patches/PINNED_REVISIONS"
[ -f "$SERIES" ] || die "missing $SERIES"
[ -f "$PINS" ] || die "missing $PINS"

EXPECTED="$(sed -n 's/^bootable_recovery=//p' "$PINS" | head -n 1)"
[ -n "$EXPECTED" ] || die "$PINS has no bootable_recovery pin"
HAVE="$(git -C "$REC" rev-parse HEAD)"

echo "==> theme patches: $REC"
echo "    expected upstream: $EXPECTED"
echo "    checkout upstream: $HAVE"

if [ "$HAVE" != "$EXPECTED" ]; then
    if [ "$ALLOW_MISMATCH" = 0 ]; then
        die "upstream revision mismatch.
       The patches are verified against $EXPECTED.
       Re-sync/checkout that revision, or pass --allow-revision-mismatch and
       accept that a changed theme context will fail the context check."
    fi
    echo "    WARNING: revision mismatch allowed by --allow-revision-mismatch"
fi

APPLIED=0
SKIPPED=0
WOULD=0

while IFS= read -r entry || [ -n "$entry" ]; do
    case "$entry" in
        ""|\#*) continue ;;
    esac
    PATCH="$ROOT/patches/$entry"
    [ -f "$PATCH" ] || die "patches/series lists '$entry', but $PATCH does not exist"

    if git -C "$REC" apply --reverse --check "$PATCH" >/dev/null 2>&1; then
        echo "    = already applied: $entry"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    if ! git -C "$REC" apply --check "$PATCH" >/dev/null 2>&1; then
        echo "ERROR: '$entry' no longer applies to the theme in $REC" >&2
        echo "       git apply --check said:" >&2
        git -C "$REC" apply --check "$PATCH" >&2 || true
        die "upstream theme context changed; regenerate the patch (patches/README.md)"
    fi

    if [ "$CHECK_ONLY" = 1 ]; then
        echo "    + would apply: $entry"
        WOULD=$((WOULD + 1))
        continue
    fi

    git -C "$REC" apply "$PATCH"
    echo "    + applied: $entry"
    APPLIED=$((APPLIED + 1))
done < "$SERIES"

if [ "$CHECK_ONLY" = 1 ]; then
    echo "==> patch check OK ($WOULD to apply, $SKIPPED already applied)"
else
    if [ "$APPLIED" -gt 0 ]; then
        # Local record, never committed: which patches are in this checkout.
        ( cd "$ROOT/patches" && sha256sum ./*.patch 2>/dev/null ) \
            > "$REC/.sakura-theme-patches" 2>/dev/null || true
    fi
    echo "==> theme patches OK ($APPLIED applied, $SKIPPED already applied)"
fi
exit 0
