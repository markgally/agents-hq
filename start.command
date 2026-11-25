#!/bin/bash
# CLI convenience: hand off to the app; the server is never tied to this shell.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ "$(uname -s)" != "Darwin" ]; then
  cd "$ROOT"
  exec python3 -m agent_hq
fi
exec /usr/bin/open "$ROOT/macos/AGENTS HQ.app"
