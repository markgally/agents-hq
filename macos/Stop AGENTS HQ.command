#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -x "$ROOT/.runtime/python/bin/python3" ]; then
  echo "This copy of AGENTS HQ has not been installed."
  exit 0
fi
exec "$ROOT/.runtime/python/bin/python3" "$ROOT/macos/launcher.py" --stop
