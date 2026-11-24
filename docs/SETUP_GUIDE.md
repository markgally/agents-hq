# AGENTS HQ Setup Guide

## 1. Install Python

Install Python 3.10+ from https://www.python.org/downloads/  
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
macOS: double-click **`macos/AGENTS HQ.app`** (or `start.command`)  
Or: `py -3 -m agent_hq` / `python3 -m agent_hq`

A dedicated browser app window opens to http://127.0.0.1:4181/  
On Windows via the desktop shortcut/VBS, close that app window to stop AGENTS HQ (including schedules).  
`start.bat` and macOS keep a visible control window — close it to stop.

## 4. Finish the in-app Setup Guide

Header → **Setup Guide**:

1. **Codex Connection** — detect executable, version, sign-in, test connection  
2. **Workspace** — default working and output folders (must be writable)  
3. **Agent Threads** — seven local agents; threads created lazily on first use  
4. **Execution Settings** — concurrency, timeouts, timezone  

**Finish Setup** verifies real prerequisites; it does not accept empty checkboxes.

You may explore the office while disconnected. Only AI execution is blocked until Codex is connected.
