#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-}"
USE_CN_MIRROR="${USE_CN_MIRROR:-0}"
JDK_URL_DEFAULT="https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.14%2B7/OpenJDK17U-jdk_aarch64_mac_hotspot_17.0.14_7.tar.gz"

resolve_root() {
  if [[ -n "$PROJECT_ROOT" && -f "$PROJECT_ROOT/run.py" ]]; then
    echo "$PROJECT_ROOT"
    return
  fi
  if [[ -f "./run.py" ]]; then
    pwd
    return
  fi
  if [[ -f "./OJ_System/run.py" ]]; then
    echo "$(pwd)/OJ_System"
    return
  fi
  echo "Cannot locate OJ_System root. Pass path as first argument." >&2
  exit 1
}

download_with_fallback() {
  local out="$1"; shift
  for url in "$@"; do
    echo "Downloading: $url"
    if curl -fL "$url" -o "$out"; then
      return 0
    fi
    echo "Download failed, trying next source..."
  done
  return 1
}

ROOT="$(resolve_root)"
TOOLCHAIN_DIR="$ROOT/toolchain"
TMP_DIR="$ROOT/.deploy_tmp"
JDK_DIR="$TOOLCHAIN_DIR/jdk"

mkdir -p "$TOOLCHAIN_DIR" "$TMP_DIR"

if ! command -v g++ >/dev/null 2>&1; then
  echo "g++ not found, trying to install via Homebrew..."
  if command -v brew >/dev/null 2>&1; then
    brew install gcc
  else
    echo "Homebrew not found, install g++ manually." >&2
    exit 1
  fi
fi

JDK_ARCHIVE="$TMP_DIR/jdk.tar.gz"
JDK_URLS=()
if [[ "$USE_CN_MIRROR" == "1" ]]; then
  JDK_URLS+=("https://ghfast.top/$JDK_URL_DEFAULT")
  JDK_URLS+=("https://ghproxy.cn/$JDK_URL_DEFAULT")
fi
JDK_URLS+=("$JDK_URL_DEFAULT")

download_with_fallback "$JDK_ARCHIVE" "${JDK_URLS[@]}"

rm -rf "$JDK_DIR"
mkdir -p "$JDK_DIR"
tar -xzf "$JDK_ARCHIVE" -C "$JDK_DIR"

GPP_PATH="$(command -v g++)"
JAVAC_PATH="$(find "$JDK_DIR" -type f -name javac | head -n 1 || true)"

echo
 echo "Toolchain setup finished."
 echo "ProjectRoot : $ROOT"
 echo "g++ path    : $GPP_PATH"
 echo "JDK path    : $JDK_DIR"
 echo "javac exists: $([[ -n "$JAVAC_PATH" ]] && echo true || echo false)"

"$GPP_PATH" --version | head -n 1
if [[ -n "$JAVAC_PATH" ]]; then
  "$JAVAC_PATH" -version
fi

rm -rf "$TMP_DIR"

echo
 echo "Next step:"
 echo "  .venv/bin/python run.py development"
