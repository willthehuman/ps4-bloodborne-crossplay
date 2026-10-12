#!/usr/bin/env bash
# Task 3 — build the PS4 shadNet plugin from pinned sources.
#
# Usage:        scripts/build-plugin.sh
# Env overrides: OO_PS4_TOOLCHAIN, GOLDHEN_SDK, JOBS (default 8)
#
# Verified working 2026-10-12 on Omarchy (see docs/status.md).
# Artifact: vendor/shadNet-PS4/bin/plugins/prx_final/shadNet-PS4.prx
set -euo pipefail

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS="${JOBS:-8}"

OO_PS4_TOOLCHAIN="${OO_PS4_TOOLCHAIN:-$WS/toolchains/extracted/OpenOrbis/PS4Toolchain}"
GOLDHEN_SDK="${GOLDHEN_SDK:-$WS/vendor/GoldHEN_Plugins_SDK}"
PLUGIN_DIR="$WS/vendor/shadNet-PS4"
LLD_BIN="$WS/toolchains/bin"            # user-local ld.lld wrapper (no system lld package)
LLD_LIB="$WS/toolchains/lld-usr/usr/lib"

export OO_PS4_TOOLCHAIN GOLDHEN_SDK
export PATH="$LLD_BIN:$PATH"
export LD_LIBRARY_PATH="$LLD_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

echo "== preflight =="
command -v clang    >/dev/null || { echo "FAIL: clang missing"; exit 1; }
command -v ld.lld   >/dev/null || { echo "FAIL: ld.lld missing (expected wrapper at $LLD_BIN)"; exit 1; }
command -v llvm-ar  >/dev/null || { echo "FAIL: llvm-ar missing"; exit 1; }
[[ -d "$OO_PS4_TOOLCHAIN" ]] || { echo "FAIL: toolchain missing at $OO_PS4_TOOLCHAIN"; exit 1; }
[[ -d "$GOLDHEN_SDK"      ]] || { echo "FAIL: SDK missing at $GOLDHEN_SDK"; exit 1; }
[[ -d "$PLUGIN_DIR"       ]] || { echo "FAIL: plugin sources missing at $PLUGIN_DIR"; exit 1; }
echo "clang:   $(clang --version | head -1)"
echo "ld.lld:  $(ld.lld --version)"
echo "cmake:   $(cmake --version | head -1)"

echo "== 1/3 Build GoldHEN Plugins SDK =="
make -C "$GOLDHEN_SDK" all

echo "== 2/3 Configure plugin =="
cmake -S "$PLUGIN_DIR" -B "$PLUGIN_DIR/build" -DCMAKE_BUILD_TYPE=Release

echo "== 3/3 Build plugin (jobs=$JOBS) =="
cmake --build "$PLUGIN_DIR/build" --parallel "$JOBS"

PRX="$PLUGIN_DIR/bin/plugins/prx_final/shadNet-PS4.prx"
echo "== artifact =="
ls -l "$PRX"
sha256sum "$PRX"
echo "BUILD OK"
