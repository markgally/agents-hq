# Migration notes: 24/7 Bots → AGENTS HQ

## Checkpoint

Full copy of the pre-migration tree:

`C:\Users\markg\Downloads\24-7-Bots-backup-20261124`

## Removed / retired

- Video upload, transcription, Groq captioning, SEO training
- Social calendar / platform tiles, affiliate (YB/SHP), Hand to Claude `/brief`
- Thumbnail / Video Editor / RVS suite launch behaviour as product features
- Legacy `smm-*` browser keys (ignored; new keys use `ahq-`)
- Groq / Claude setup wizard and related `.env` keys

Character artwork, office plate, sound, and idle activity engines were **preserved** and remapped to seven generic agents (`mgr`, `cap`, `in`, `sch`, `pack`, `ved`, `rvs`).

## Added

- `agent_hq` Python package, SQLite persistence, Codex App Server adapter
- Seven configurable agents with persistent threads
- Run Everything, scheduler, approvals, outputs, SSE event stream
- AGENTS HQ UI modules under `static/js/` and `static/css/app.css`

## Data

Fresh installs create `data/agent_hq.db`. There is no automatic import of old video batches.

## Bytecode note

Several core modules (`app`, `db`, `events`, `security`, `execution`, `scheduler`, `codex.adapter`, `codex.rpc`, `codex.discovery`) are loaded from package-level `.pyc` files that match the verified pre-migration implementation, after an accidental source overwrite during this session. Do not delete those `.pyc` files. Matching `.py` service modules (`agents`, `threads`, `conversations`, …) remain as source.
