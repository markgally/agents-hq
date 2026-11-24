# AGENTS HQ — Setup

**Seven Agents. Endless Possibilities.**

AGENTS HQ is a local-first AI workforce manager. Seven permanent agents live in a cute office; each one chats and works through your signed-in Codex account. Idle recreation never spends Codex tokens.

## Requirements

- Python 3.10+ (stdlib only; no pip packages required to run)
- A signed-in Codex Desktop app or CLI
- Windows, macOS, or Linux

## Start the app

### Windows

1. Double-click **`AGENTS HQ.vbs`**, or run `launch\Create Desktop Shortcut.ps1` once and use the Desktop icon.
2. A dedicated Edge/Chrome app window opens the dashboard (no console).
3. Close the app window to stop the server (and schedules). For a visible debug console, use `start.bat`.

### macOS

1. Double-click **`macos/AGENTS HQ.app`** (or `start.command`).
2. A dedicated Chrome/Edge app window opens the dashboard.
3. Keep the Terminal control window open — closing it stops the server.

### Terminal (any OS)

```bat
py -3 -m agent_hq
```

```bash
python3 -m agent_hq
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
