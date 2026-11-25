# AGENTS HQ — Setup

**Seven Agents. Endless Possibilities.**

AGENTS HQ is a local-first AI workforce manager. Seven permanent agents live in a cute office; each one chats and works through your signed-in Codex account. Idle recreation never spends Codex tokens.

## Requirements

- Python 3.14.x (stdlib only; no pip packages required to run). The Mac installer downloads its own private runtime; older Python versions cannot load the recovered backend bytecode.
- A signed-in Codex Desktop app or CLI
- Windows, macOS, or Linux

## Start the app

### Windows

1. Double-click **`AGENTS HQ.vbs`**, or run `launch\Create Desktop Shortcut.ps1` once and use the Desktop icon.
2. A dedicated Edge/Chrome app window opens the dashboard (no console).
3. Close the app window to stop the server (and schedules). For a visible debug console, use `start.bat`.

### macOS

1. Double-click **`macos/Install AGENTS HQ.command`** once. It installs private Python 3.14, repairs app permissions, and creates Applications, Desktop and Dock entries.
2. Click **AGENTS HQ in the Dock**. The dashboard opens with no Terminal window, and the server runs in the background.
3. Use **`macos/Stop AGENTS HQ.command`** to stop it and its schedules. Closing the browser does not stop the Mac server.

To restore a missing Dock icon, run **`macos/Add to Dock.command`**. If a downloaded ZIP lost executable permissions, run `bash "macos/Install AGENTS HQ.command"` from its project folder. Keep the project folder in place; the installed app uses it. See [the Mac guide](macos/README.md).

### Terminal (any OS)

```bat
py -3.14 -m agent_hq
```

```bash
python3.14 -m agent_hq
```

Dashboard: **http://127.0.0.1:4181/**

## First-time setup

1. Sign in to Codex on this computer.
2. In AGENTS HQ, open **Setup Guide** or **Codex Integration** and connect.
3. Customize agents, assign tasks, then use **Run Everything** when ready.

## More docs

- [README.md](README.md) — overview and quick start
- [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) — detailed setup
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — how to use the office and agents
- [docs/CODEX_INTEGRATION.md](docs/CODEX_INTEGRATION.md) — Codex App Server details
