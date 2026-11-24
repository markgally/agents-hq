# AGENTS HQ Implementation Plan

Transformation of the existing 24/7 Bots application into AGENTS HQ. This document records the
repository audit taken before any change, the checkpoint, the decisions, and the phases.

Audit date: 2026-11-24. Host: Windows 10.0.26200.

## 1. Checkpoint

- No Git executable is installed and the project has no `.git` folder, so a Git checkpoint was not possible.
- Checkpoint taken as a full copy: `C:\Users\markg\Downloads\24-7-Bots-backup-20261124`
  (16 files, 5,876,397 bytes, identical file count and byte total to the source at copy time).
- To roll back: stop the server, delete the project folder contents, copy the backup folder back.

## 2. Repository audit (baseline)

### Architecture and entry points

| Item | Baseline |
|---|---|
| Backend | `server.py`, 462 lines, Python standard library only (`http.server.ThreadingHTTPServer`) |
| Frontend | `static/index.html`, 273,697 bytes: one `<style>` block (lines 5-362), body markup (364-428), one inline script in an IIFE (429-1543). No framework, no build step |
| Launchers | `start.bat` (Windows), `start.command` (Mac). Both find Python, copy `.env.example` to `.env`, stop an older copy on the port, open Chrome, run `server.py` |
| Bind | `127.0.0.1`, port `4181` (`PORT` env) |
| Dependencies | None beyond Python 3. `ffmpeg` optional (not installed here). pdf.js loaded from a CDN for training files |
| Database | None. `.env` and `training.txt` only |
| Tests / build scripts | None |

### Baseline API (all retired by this migration)

`GET /brief`, `/api/defaultfolder`, `/api/train`, `/api/status`, `/api/outbox`, `/api/outbox/file`;
`POST /api/savevideo`, `/api/thumb`, `/api/train`, `/api/extract`, `/api/key`, `/api/brief`,
`/api/shopee`, `/api/product`, `/api/thumbpick`, `/api/caption`, `/api/transcribe`.

### Front-end subsystems (line numbers refer to the baseline `static/index.html`)

| Subsystem | Location | Notes |
|---|---|---|
| Bot state | `state()` 479-485 | Derived in the browser from `vids`, `plan`, `packed`, busy flags |
| Bot Log | `log()` 464-467, `#side` | In memory only; lost on refresh |
| Canvas cards, drag, wires | 763-830 | `POS`, `WIRES`, `place()`, `wires()`, `wireState()`, `pulse()`, drag threshold 5 px, positions in `smm-pos12` |
| White panel | `openPanel()` 810-813, `panelHead()` 855-877 | Panel bodies are stashed `<div>`s moved in and out |
| Setup wizard | `renderGuide()` 929-937 | Two steps: Groq key, platforms and checkboxes |
| Tutorial dialog | markup line 394, `openHow()` 947-951 | Four illustrated cards |
| Office engine | 1013-1433 | Described below |
| Video pipeline | 569-674, 1435-1456 | Transcribe, caption, schedule, manager check |
| Thumbnail Bot | 677-762 | Frame scoring and Groq vision pick |
| Affiliate (YB, SHP) | 487-514, 1492-1506 | TikTok product and Shopee link checks |
| Claude hand-off | 469-478, 840-853 | Brief text served at `/brief`, polled through `/api/status` |
| Video Editor / RVS suite | 1483-1540 | Outbox polling, external links |

### Office engine

- Rendering: one `<canvas>`, one render loop (`isoLoop`), about 14 FPS when nothing moves and sound is off.
- Two office drawings: painted plate (`assets/office-plate-door.webp`, magenta keyed out, 672x448 logical)
  or a procedural 25x22 isometric tile office when the plate is missing.
- Sprites, three-level fallback: `assets/bot-<k>.webp` (4 moods x 8 directions) -> `assets/bots-sheet.webp`
  (tinted) -> procedurally drawn box robot. Recolours of `bot-cap.webp` supply the Video Editor (orange),
  RVS (lime), Thumbnail (cyan), YB (yellow) and SHP (red) characters.
- Pathfinding: A* over an 8x4 px lattice inside `NAVW` polygons minus `NAVB` boxes (plate only).
- Idle engine: `idleTick()`; each idle bot leaves its desk every 7-16 s; 45% chance of a pair chat; 45% chance
  of a group activity (arcade 25%, coffee 25%, train 17%, joke 17%, hide and seek 16%).
- Group activities: `groupGo()` (coffee, arcade), `groupFun()` (train, joke, hide and seek), coffee queue,
  mugs, steam, arcade screens. Members carry a cancel token (`tok`), so one member can leave.
- Holograms: `holoDraw()` cyan panel with binary particles, one glyph per job.
- Sound: Web Audio, muted by default, `smm-snd`; spatial pan and zoom-scaled volume; 74 BPM music loop.
- Zoom 1x-4x, wheel zoom, drag pan, reset; reduced-motion and hidden-tab shortcuts in `officeCalm()`.

Baseline limitation found: `idleTick()` sends every bot to its desk whenever any job is active, and idle
activities only run on the painted plate. Both are changed (section 5).

### Assets present

`static/assets/`: `office-plate-door.webp`, `neon-front.webp`, `bot-in.webp`, `bot-cap.webp`, `bot-sch.webp`,
`bot-mgr.webp`, `bot-pack.webp`, `bots-sheet.webp`, plus `static/icon.svg`. All eight referenced images exist.
None are modified by this migration.

### Browser storage keys (baseline, all `smm-*`)

`smm-setup`, `smm-howto`, `smm-plats`, `smm-metaname`, `smm-style`, `smm-rules`, `smm-sched`, `smm-folder`,
`smm-outbox`, `smm-shop`, `smm-pos7/10/12`, `smm-view`, `smm-snd`, `smm-pduser`, `smm-mduser`, `smm-editfirst`,
`smm-examples`. AGENTS HQ uses a new `ahq-*` namespace and never reads the old keys.

### Environment

| Tool | Finding |
|---|---|
| Python | 3.14.6, SQLite 3.50.4. `zoneinfo` has no tz database on this machine |
| Node / npm | 24.19.0 / 11.17.0 (used only for Playwright end-to-end tests) |
| Git, ffmpeg | Not installed |
| Codex | Desktop app `OpenAI.Codex 26.1120.5083.0`; bundled `app\resources\codex.exe` reports `codex-cli 0.171.0-alpha.13.2`; `codex login status` -> "Logged in using ChatGPT" |
| Port 4181 | In use at audit time by the baseline 24/7 Bots server |

## 3. Decisions

1. Keep Python standard library and vanilla JavaScript. No framework, bundler, or Electron. The existing
   architecture supports every requirement: SQLite, threads, subprocess pipes, and Server-Sent Events are all
   in the standard library.
2. Codex integration through the documented Codex App Server over stdio (newline-delimited JSON-RPC),
   spawned by the backend with an argument array. The executable is discovered at runtime.
3. Authentication is whatever the Codex CLI already holds (here: ChatGPT sign-in). AGENTS HQ never reads
   Codex credential files, cookies, or desktop storage; it asks the app server (`account/read`).
4. SQLite database at `data/agent_hq.db` (WAL, foreign keys on, versioned migrations).
5. Server-Sent Events for the real-time channel, with persisted event ids and `Last-Event-ID` replay.
6. Default agent sandbox is Codex `read-only` with approvals on request. `workspace-write` is opt-in per
   agent. Full-access mode is never offered.
7. Default workspace `workspace/`, default outputs `outputs/`, both inside the project and changeable.
8. `Asia/Manila` handled with a built-in fixed UTC+8 rule when the tz database is missing.
9. Port stays 4181.
10. A mock app server exists only for automated tests and is never used by the running application.

## 4. Target architecture

```
Browser (canvas, office, workspace, log)  <--REST + SSE-->  agent_hq.app (HTTP API)
                                                              |-- agents, tasks, schedules (SQLite)
                                                              |-- ExecutionManager (queue, locks, retries)
                                                              |-- Scheduler (backend thread)
                                                              |-- EventBus (persist + fan-out)
                                                              `-- CodexAdapter --JSON-RPC/stdio--> codex app-server
```

Principle: the office is the body, Codex is the brain, AGENTS HQ is the management system. The office keeps
its own cosmetic animation state and reads execution state from the same store as the canvas.

## 5. Reuse and change map

| Baseline piece | Action |
|---|---|
| Office engine (1013-1433) | Moved to `static/js/office.js` unchanged, then edited in place |
| `BT` roster of 5 + suite + 3 affiliate bots | Seven permanent slots: `mgr, cap, in, sch, pack, ved, rvs` -> `agent-01..07` |
| `idleTick()` global "everyone to desks" | Per agent: only an agent with real work walks back |
| Idle activities on plate only | Kept on the plate; simple wander added to the procedural office |
| Job-specific holograms | Generic holograms selected from real Codex item events |
| Video-flavoured dialogue | General office dialogue, still scripted locally |
| Room-click opens a panel | Only characters are clickable; empty floor does nothing |
| Canvas cards and wires | Seven independent cards; wires only for user-configured dependencies |
| White panel | Becomes the agent workspace (Chat, Configure, Tasks, Outputs, History) |
| Setup wizard, tutorial | Same dialog styles, new content |
| Bot Log | Same column, now persisted and filterable |
| `server.py` routes | Replaced by `agent_hq` package; `server.py` stays as the entry point |
| Video, Groq, affiliate, Claude brief, suite | Removed after replacements are verified |

## 6. Phases

1. Backup and baseline (this document).
2. Codex probe: generate the schema for the installed version, verify sign-in, verify transport.
3. Backend core: database, seven agents, settings, security, event bus, state and event endpoints.
4. Front-end split and rebrand.
5. Canvas and office for seven agents.
6. Agent workspace.
7. Codex adapter.
8. Execution manager and Run Everything.
9. Scheduler, outputs, persisted log, Command Center.
10. Dialogs, presets, collaboration, connector status.
11. Removal of the video workflow.
12. Tests, acceptance run, documentation, completion report.

The application is kept runnable between phases.

## 7. Known risks

- The app server is labelled experimental in this Codex version; the adapter follows the generated schema in
  `docs/codex-schema/`, not online documentation.
- Thread sharing with the Codex desktop app is verified separately and only exposed if it works.
- Real acceptance turns consume the ChatGPT plan's Codex allowance, shared by all seven agents.
- Local scheduling only runs while this computer, the AGENTS HQ server, and Codex are running.
