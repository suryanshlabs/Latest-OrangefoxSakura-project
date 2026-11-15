#!/usr/bin/env bash
#
# setup_jdk11.sh - ensure an OpenJDK 11 is available, without root.
#
# Why: the Android 12.1 Soong bootstrap requires JDK 11. The ServerHive runner
# has JDK 21 and no passwordless sudo, so apt cannot be used. Instead this
# fetches the current Temurin 11 GA build into $HOME/.jdk11 (idempotent) and
# prints the JAVA_HOME to use.
#
# Usage:
#   ./build/setup_jdk11.sh              # ensure + print JAVA_HOME
#   eval "$(./build/setup_jdk11.sh)"    # ensure + export in the current shell
#
# Exit codes: 0 ok, 1 could not obtain a JDK 11.
#
set -euo pipefail

JDK_DIR="${JDK11_DIR:-$HOME/.jdk11}"
ADOPTIUM="https://api.adoptium.net/v3/binary/latest/11/ga/linux/x64/jdk/hotspot/normal/eclipse"

have_jdk11() {
    [ -x "$1/bin/java" ] && "$1/bin/java" -version 2>&1 | grep -q 'version "11'
}

# 1. A JDK 11 we already installed.
if have_jdk11 "$JDK_DIR"; then
    echo "export JAVA_HOME=\"$JDK_DIR\"" >&2
    echo "$JDK_DIR"
    exit 0
fi

# 2. A system JDK 11, if the image happens to provide one.
if command -v java >/dev/null && java -version 2>&1 | grep -q 'version "11'; then
    JH="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")"
    if have_jdk11 "$JH"; then
        echo "export JAVA_HOME=\"$JH\"" >&2
        echo "$JH"
        exit 0
    fi
fi

# 3. Try apt (only works with passwordless sudo).
if sudo -n true 2>/dev/null; then
    echo "trying apt openjdk-11-jdk" >&2
    sudo apt-get update -qq || true
    DEBIAN_FRONTEND=noninteractive sudo apt-get install -y --no-install-recommends \
        openjdk-11-jdk >&2 || true
    if command -v java >/dev/null && java -version 2>&1 | grep -q 'version "11'; then
        JH="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")"
        echo "export JAVA_HOME=\"$JH\"" >&2
        echo "$JH"
        exit 0
    fi
fi

# 4. Portable tarball into $HOME — no root required.
echo "downloading Temurin 11 into $JDK_DIR" >&2
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if ! curl -fL --retry 3 --retry-delay 3 --max-time 900 -o "$tmp/jdk11.tar.gz" "$ADOPTIUM"; then
    echo "ERROR: could not download JDK 11 from Adoptium" >&2
    exit 1
fi

mkdir -p "$JDK_DIR"
tar -xzf "$tmp/jdk11.tar.gz" -C "$JDK_DIR" --strip-components=1

if ! have_jdk11 "$JDK_DIR"; then
    echo "ERROR: extracted JDK at $JDK_DIR is not a working JDK 11" >&2
    "$JDK_DIR/bin/java" -version 2>&1 | head -3 >&2 || true
    exit 1
fi

echo "installed: $("$JDK_DIR/bin/java" -version 2>&1 | head -1)" >&2
echo "export JAVA_HOME=\"$JDK_DIR\"" >&2
echo "$JDK_DIR"
