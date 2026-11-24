# AGENTS HQ Test Report

Date: 2026-11-24  
Host: Windows 10.0.26200, Python 3.14.6  
Codex: `codex-cli 0.171.0-alpha.13.2` (desktop package), signed in with ChatGPT (`account type: chatgpt`, plan reported as `team`)

## Automated tests

Command:

```bat
py -3 -m unittest discover -s tests -v
```

Result: **111 ran, 0 failed, 1 skipped** (mock Codex app server).

Coverage includes agent configuration, Codex adapter behaviour against the mock, execution/concurrency/idempotency, scheduling, security/path policy, SSE replay, approvals, outputs, and restart recovery helpers.

## Live Codex checks (this machine)

| Step | Result |
|---|---|
| Discover Codex desktop executable | Verified |
| `codex login status` → Logged in using ChatGPT | Verified |
| `POST /api/codex/connect` | `state: connected`, version `0.171.0-alpha.13.2` |
| Rename agent-01 → JARVIS / Personal Assistant | Verified |
| Chat: “Reply with exactly: AGENTS HQ live OK” | Assistant replied `AGENTS HQ live OK` |
| Persistent thread id created | `01a20dcf-3bee-7191-964e-040eaf97b0a2` |
| Idle recreational activities call Codex | Not observed; idle path has no adapter calls (by design + unit coverage) |

## Not fully re-verified in this session

- Full 40-step browser UI walkthrough (Playwright suite not run this session)
- Follow-up turn continuity after the live reply (blocked mid-session by environment review; prior probe docs and unit tests cover resume)
- Long-running schedule fire while leaving the host overnight

## Known limitations

See [README.md](../README.md) and [CODEX_INTEGRATION.md](CODEX_INTEGRATION.md).
