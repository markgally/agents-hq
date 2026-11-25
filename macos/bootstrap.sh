#!/bin/bash
# Private CPython for the bundled Python 3.14 bytecode. Never changes system Python.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime"
PYTHON="$RUNTIME/python/bin/python3"
compatible() {
  [ -x "$PYTHON" ] && "$PYTHON" -I -c 'import sys; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 14)' >/dev/null 2>&1
}
if compatible; then exit 0; fi
mkdir -p "$RUNTIME"
LOCK="$RUNTIME/bootstrap.lock"
LOCKED=0
STAGE=""
cleanup() {
  if [ -n "$STAGE" ]; then rm -rf "$STAGE"; fi
  if [ "$LOCKED" = 1 ]; then rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for attempt in {1..120}; do
  if mkdir "$LOCK" 2>/dev/null; then
    LOCKED=1
    echo "$$" > "$LOCK/pid"
    break
  fi
  if compatible; then exit 0; fi
  if [ -f "$LOCK/pid" ]; then
    owner=$(cat "$LOCK/pid")
    if [[ "$owner" =~ ^[0-9]+$ ]] && ! kill -0 "$owner" 2>/dev/null; then
      rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null || true
    fi
  fi
  sleep 1
done
if [ "$LOCKED" != 1 ]; then echo "Python setup is already running. Please try again shortly." >&2; exit 1; fi
if compatible; then exit 0; fi
case "$(uname -m)" in
  arm64)
    ARCH=aarch64
    SHA256=4fc4f7f83df874d623ae6aa700d6024a10bc7c401ef35df8b1117778616ec420
    ;;
  x86_64)
    ARCH=x86_64
    SHA256=2a0d2817398655c545e0e1005f18b41c7909822a8638d8ccef03f10430cc220c
    ;;
  *) echo "This installer supports Apple Silicon and Intel Macs." >&2; exit 1 ;;
esac
STAGE=$(mktemp -d "$RUNTIME/install.XXXXXX")
ASSET="cpython-3.14.10%2B20261124-${ARCH}-apple-darwin-install_only.tar.gz"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261124/$ASSET"
echo "Installing private Python 3.14.10 for $ARCH..."
/usr/bin/curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 20 --max-time 600 --retry 2 "$URL" -o "$STAGE/python.tar.gz"
ACTUAL=$(/usr/bin/shasum -a 256 "$STAGE/python.tar.gz")
if [ "${ACTUAL%% *}" != "$SHA256" ]; then echo "Python download checksum did not match. Nothing was installed." >&2; exit 1; fi
/usr/bin/tar -xzf "$STAGE/python.tar.gz" -C "$STAGE"
"$STAGE/python/bin/python3" -I -c 'import sys; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 14)'
if [ -e "$RUNTIME/python" ]; then
  mv "$RUNTIME/python" "$RUNTIME/python.previous.$(date +%Y%m%d%H%M%S).$$"
fi
mv "$STAGE/python" "$RUNTIME/python"
echo "Private Python 3.14 is ready."
