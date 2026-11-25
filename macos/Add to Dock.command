#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
/bin/bash "$ROOT/macos/bootstrap.sh"
exec "$ROOT/.runtime/python/bin/python3" "$ROOT/macos/setup.py" dock
