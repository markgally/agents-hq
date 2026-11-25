# AGENTS HQ Setup Guide

## 1. Install Python

On Mac, run **`macos/Install AGENTS HQ.command`**: it supplies a private Python 3.14 runtime without changing system Python. On Windows/Linux, install Python 3.14.x from https://www.python.org/downloads/ — the recovered backend bytecode requires it.
On Windows, tick **Add python.exe to PATH**. If `python` opens the Microsoft Store, disable the `python.exe` / `python3.exe` app execution aliases.

## 2. Install and sign in to Codex

Install the Codex desktop app (or CLI) and complete its official sign-in. Prefer ChatGPT subscription sign-in when available.

Verify:

```bat
codex login status
```

AGENTS HQ can also locate the Codex desktop package on Windows when `codex` is not on PATH.

## 3. Start AGENTS HQ

Windows: double-click **`AGENTS HQ.vbs`** (or create a Desktop shortcut via `launch\Create Desktop Shortcut.ps1`)
macOS: run **`macos/Install AGENTS HQ.command`** once, then click **AGENTS HQ in the Dock**. Setup repairs executable permissions and adds Applications/Desktop/Dock entries. Use **`macos/Add to Dock.command`** to restore a missing Dock icon.
Or: `py -3.14 -m agent_hq` / `python3.14 -m agent_hq`

A dedicated browser app window opens to http://127.0.0.1:4181/
On Windows via the desktop shortcut/VBS, close that app window to stop AGENTS HQ (including schedules).
`start.bat` keeps a visible debug console — close it to stop. Mac launches run in the background without Terminal. Closing the browser leaves the Mac server running; use **`macos/Stop AGENTS HQ.command`** to stop it and schedules. See the [Mac installation guide](../macos/README.md).

## 4. Finish the in-app Setup Guide

Header → **Setup Guide**:

1. **Codex Connection** — detect executable, version, sign-in, test connection
2. **Workspace** — default working and output folders (must be writable)
3. **Agent Threads** — seven local agents; threads created lazily on first use
4. **Execution Settings** — concurrency, timeouts, timezone

**Finish Setup** verifies real prerequisites; it does not accept empty checkboxes.

You may explore the office while disconnected. Only AI execution is blocked until Codex is connected.
