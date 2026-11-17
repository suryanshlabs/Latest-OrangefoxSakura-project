#!/usr/bin/env bash
#
# check_deps.sh - host preflight for an AOSP 12.1 / OrangeFox R12.0 build.
#
# The earlier CI attempts failed on things this script now catches in seconds
# instead of after a 40-minute sync: JDK 11 not on PATH (envsetup exits 1),
# a disk far too small for out/, RAM below what soong/javac need, and missing
# host packages (bc, bison, flex, cpio, lz4, ...).
#
# Usage:
#   ./build/check_deps.sh            # full preflight for a real build
#   ./build/check_deps.sh --quick    # tools only (no disk/RAM requirements)
#   ./build/check_deps.sh --dest DIR # check free space at DIR's filesystem
#
# Exit: 0 = ready, 1 = at least one hard requirement unmet (each printed with
# the exact remediation command for Debian/Ubuntu).
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${HOME}/orangefox/fox_12.1"
QUICK=0
STRICT_DISK_GB=45

while [ $# -gt 0 ]; do
    case "$1" in
        --quick) QUICK=1; shift ;;
        --dest)  DEST="${2:-}"; shift 2 ;;
        -h|--help) sed -n '3,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

fail=0
ok()   { printf '  [PASS] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; fail=1; }
warn() { printf '  [WARN] %s\n' "$*"; }

echo "==> host tools"
# tool:package
TOOLS="
git:git
curl:curl
python3:python3
rsync:rsync
unzip:unzip
zip:zip
bc:bc
bison:bison
flex:flex
gcc:build-essential
g++:g++-multilib
make:make
ccache:ccache
cpio:cpio
lz4:liblz4-tool
patch:patch
perl:perl
openssl:libssl-dev
"
missing_pkgs=""
while IFS=: read -r tool pkg; do
    [ -n "${tool:-}" ] || continue
    if command -v "$tool" >/dev/null 2>&1; then
        continue
    fi
    bad "missing host tool '$tool'"
    missing_pkgs="$missing_pkgs $pkg"
done <<< "$TOOLS"

# Libraries the 12.1 host build needs by header, not by binary.
for hdr in /usr/include/zlib.h /usr/include/openssl/ssl.h /usr/include/libelf.h; do
    case "$hdr" in
        */zlib.h)         pkg=zlib1g-dev ;;
        */ssl.h)          pkg=libssl-dev ;;
        */libelf.h)       pkg=libelf-dev ;;
        *)                pkg="" ;;
    esac
    [ -f "$hdr" ] || { bad "missing development header $hdr"; missing_pkgs="$missing_pkgs $pkg"; }
done

if [ -n "$missing_pkgs" ]; then
    echo "         install them with:"
    echo "           sudo apt-get install -y$(printf ' %s' $missing_pkgs | tr ' ' '\n' | sort -u | tr '\n' ' ')"
    echo "         (see documentation/DEPENDENCIES.md section 1)"
else
    ok "all required host tools present"
fi

echo "==> blob tooling (needed only by build/extract_blobs.sh)"
if command -v debugfs >/dev/null && command -v mke2fs >/dev/null; then
    ok "e2fsprogs present (debugfs $(debugfs -V 2>&1 | awk '{print $2}' | head -1))"
else
    warn "e2fsprogs missing - blob extraction from a stock vendor.img will not work"
    warn "  sudo apt-get install -y e2fsprogs"
fi

echo "==> JDK 11"
jdk_ok=0
if [ -n "${JAVA_HOME:-}" ] && [ -x "${JAVA_HOME}/bin/java" ] \
   && "${JAVA_HOME}/bin/java" -version 2>&1 | grep -q 'version "11'; then
    jdk_ok=1
elif command -v java >/dev/null && java -version 2>&1 | grep -q 'version "11'; then
    jdk_ok=1
fi
if [ "$jdk_ok" = 1 ]; then
    ok "JDK 11 on PATH or in JAVA_HOME"
else
    echo "  [INFO] no JDK 11 found; build/build.sh will fetch a portable Temurin 11"
    echo "         into build tooling via build/setup_jdk11.sh (no root needed)"
fi

echo "==> python modules (dependency-free tooling)"
python3 - <<'PY' || fail=1
import sys
missing = []
for mod in ("argparse", "hashlib", "struct", "subprocess", "tempfile", "unittest"):
    try:
        __import__(mod)
    except Exception:
        missing.append(mod)
if missing:
    print("  [FAIL] python3 missing modules: " + ", ".join(missing))
    sys.exit(1)
print(f"  [PASS] python3 {sys.version.split()[0]}")
PY

if [ "$QUICK" = 1 ]; then
    echo
    echo "RESULT: $([ "$fail" = 0 ] && echo PASS || echo FAIL) (quick mode: disk/RAM/root not checked)"
    exit "$fail"
fi

echo "==> build host limits"
if [ "$(id -u)" = 0 ]; then
    bad "running as root - the AOSP build refuses to run as root (and so does build/run-all.sh)"
else
    ok "not running as root"
fi

mem_mb=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 ))
if [ "$mem_mb" -ge 7000 ]; then
    ok "RAM ${mem_mb} MB (>=8 GB)"
elif [ "$mem_mb" -ge 3500 ]; then
    warn "RAM ${mem_mb} MB - below the 8 GB this tree needs; the build will likely die in javac/soong"
    fail=1
else
    bad "RAM ${mem_mb} MB - far below the 8 GB minimum (Termux/Poco F1 class hosts cannot build this)"
fi

# The build writes out/ next to the source tree.
CHECK_DIR="$DEST"
while [ ! -d "$CHECK_DIR" ] && [ "$CHECK_DIR" != "/" ]; do
    CHECK_DIR="$(dirname "$CHECK_DIR")"
done
avail_gb=$(df -BG --output=avail "$CHECK_DIR" 2>/dev/null | tail -1 | tr -dc '0-9')
avail_gb="${avail_gb:-0}"
if [ "$avail_gb" -ge "$STRICT_DISK_GB" ]; then
    ok "free space ${avail_gb} GB at ${CHECK_DIR} (>=${STRICT_DISK_GB} GB)"
else
    bad "free space ${avail_gb} GB at ${CHECK_DIR} - need >=${STRICT_DISK_GB} GB (out/ alone is ~35-40 GB)"
fi

cpus=$(nproc)
if [ "$cpus" -ge 4 ]; then ok "cpus ${cpus}"; else warn "cpus ${cpus} - a build will take many hours"; fi

echo
echo "NOTE: ubuntu-latest GitHub runners have ~14 GB free and are NOT usable"
echo "      for this build (see documentation/DEPENDENCIES.md section 2)."
echo "RESULT: $([ "$fail" = 0 ] && echo PASS || echo FAIL)"
exit "$fail"
