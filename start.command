#!/bin/bash
# AGENTS HQ launcher for Mac: double-click this file (or use AGENTS HQ.app).
cd "$(dirname "$0")"
PORT="${PORT:-4181}"
URL="http://127.0.0.1:${PORT}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/ then double-click this file again."
  read -r -p "Press Enter to close..." _; exit 1
fi
[ -f .env ] || cp .env.example .env

# Close a leftover AGENTS HQ still holding the port.
OLD=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)
if [ -n "$OLD" ]; then
  echo "Closing the previous process on port $PORT..."
  kill $OLD 2>/dev/null; sleep 1
fi

open_app_window() {
  # Dedicated Chromium app window when possible; otherwise a normal browser tab.
  if [ -d "/Applications/Google Chrome.app" ]; then
    open -na "Google Chrome" --args --app="$URL"
    return 0
  fi
  if [ -d "/Applications/Microsoft Edge.app" ]; then
    open -na "Microsoft Edge" --args --app="$URL"
    return 0
  fi
  if [ -d "/Applications/Chromium.app" ]; then
    open -na "Chromium" --args --app="$URL"
    return 0
  fi
  open "$URL"
}

if [ -z "$AHQ_NO_OPEN" ]; then
  (sleep 2; open_app_window) &
fi

echo "AGENTS HQ is running at $URL"
echo "Keep this window open. Close it to stop AGENTS HQ (including schedules)."
echo "Seven Agents. Endless Possibilities."
PORT="$PORT" exec python3 -m agent_hq
