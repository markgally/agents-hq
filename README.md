# AGENTS HQ

**Seven Agents. Endless Possibilities.**  
*Your Office. Your Agents. Your Rules.*

AGENTS HQ is a local-first AI workforce manager. You open a cute isometric office with seven permanent agents, customize each one, chat or assign work through a persistent Codex thread, run eligible jobs together, optionally schedule them, and collect verified outputs. When there is no work, the characters keep their recreational activities — with **zero** idle Codex usage.

The office is the body. Codex is the brain. AGENTS HQ is the management system.

## Requirements

- **Python 3.14.x** (stdlib only; no pip packages required to run). Several core modules currently ship as package-level `.pyc` built for 3.14, so older Python versions will not import them.
- A signed-in [Codex](https://github.com/openai/codex) installation (desktop app or CLI) on **this** computer
- Windows, macOS, or Linux
- Optional: Chrome or Edge for the best dashboard experience

A fresh clone has empty local data. Copy `.env.example` to `.env` if needed (launchers can do this). Each machine gets its own `data/` database and `outputs/` folder — nothing in those paths is shared via git.

## Quick start

AGENTS HQ runs as a local app: click the icon, use the dashboard window, close the app window to stop (schedules stop too).

### Windows

1. Double-click **`AGENTS HQ.vbs`**  
   or run `launch\Create Desktop Shortcut.ps1` once, then use the **AGENTS HQ** Desktop icon.
2. A dedicated Edge/Chrome app window opens to the dashboard (no console window).
3. Close the app window to stop the server.

Advanced / debug console:

```bat
start.bat
```

Or:

```bat
py -3 -m agent_hq
```

### macOS

1. Double-click **`macos/AGENTS HQ.app`** (first time: right-click → Open if macOS blocks it).  
   Or double-click `start.command`.
2. A dedicated Chrome/Edge app window opens to the dashboard.
3. Keep the Terminal control window open — closing it stops the server.

```bash
chmod +x "macos/AGENTS HQ.app/Contents/MacOS/AGENTS HQ" start.command   # once if needed
python3 -m agent_hq   # advanced / Linux
```

### Linux

```bash
./start.command
# or
python3 -m agent_hq
```

Then open **http://127.0.0.1:4181/** (Chrome/Chromium `--app` mode when available).

## Connect Codex

1. Install and sign in to Codex Desktop (or put `codex` on PATH).
2. Open **Codex Integration** or the **Setup Guide** in the header.
3. Click **Connect** / **Test**. AGENTS HQ starts `codex app-server` over stdio JSON-RPC.
4. ChatGPT subscription sign-in is preferred when Codex reports it. AGENTS HQ does not scrape tokens or drive the desktop UI.

All seven agents share the same signed-in account and its rate limits.

## Configure agents

Click any character (Office View) or card (Canvas View). Use the tabs:

| Tab | Purpose |
|---|---|
| Chat | Persistent conversation on that agent’s Codex thread |
| Configure | Name, role, personality, instructions, model, folders, permissions |
| Tasks | One primary assignment, optional schedule, Run Now / Run Everything |
| Outputs | Verified results and files |
| History | Past runs |

Team presets (Vibe Coding, IT Department, Personal, Business) change names/roles/instructions only. Threads and history are kept.

## Run Everything

The green **Run Everything** button collects eligible enabled assignments and dispatches them through the execution manager (default concurrency: 2). One-time completed tasks are not repeated. Future schedules are not pulled forward — use **Run Now** for that.

## Scheduling

Schedules run in the **backend**, not in the browser. Closing the dashboard does not stop them, but shutting down this computer or AGENTS HQ does. Default timezone: `Asia/Manila` (UTC stored internally).

## Tests

```bat
py -3 -m unittest discover -s tests -v
```

Automated tests use an explicitly labelled mock Codex app server (`AGENT_HQ_MOCK_CODEX=1`). Mock replies are never presented as real Codex in normal mode.

## Documentation

- [Implementation plan](docs/AGENT_HQ_IMPLEMENTATION_PLAN.md)
- [Codex integration](docs/CODEX_INTEGRATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Setup guide](docs/SETUP_GUIDE.md)
- [User guide](docs/USER_GUIDE.md)
- [Security](docs/SECURITY.md)
- [Test report](docs/TEST_REPORT.md)
- [Migration notes](docs/MIGRATION_NOTES.md)

## Environment

Copy `.env.example` to `.env`. Supported keys:

- `PORT` (default `4181`)
- `AGENT_HQ_DATA`, `AGENT_HQ_WORKSPACE`, `AGENT_HQ_OUTPUTS`
- `AGENT_HQ_CODEX` (optional explicit path to `codex`)
- `AGENT_HQ_MOCK_CODEX=1` (tests / labelled test mode only)
- `AGENT_HQ_NO_AUTOCONNECT=1` (start without connecting Codex)

## Known limitations

- Core backend modules currently ship as Python bytecode (`.pyc`) recovered from the pre-migration build, plus matching `.py` service modules. Prefer not deleting `__pycache__` or the package-level `.pyc` files.
- Desktop “open this thread in Codex” is not offered; thread list/associate/resume work when Codex supports them.
- Local scheduling only — not cloud 24/7.
- On some Windows installs, `Asia/Manila` uses a fixed UTC+8 fallback when the OS tz database is missing.
