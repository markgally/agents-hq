# AGENTS HQ Security

## Defaults

- Server binds to **localhost only** (`127.0.0.1`)
- Mutating API calls require the session write token (`X-AHQ-Token`)
- Host / Origin checks reject non-local browsers
- Default agent sandbox: `read-only`; approval preference: `on-request`
- `danger-full-access` is never accepted

## Filesystem

`PathPolicy` allowlists working and output roots. Private roots (AGENTS HQ data directory, `~/.codex`) are denied even if nested under an allowlisted path. Symlink / traversal escapes are rejected.

## Secrets

Logs, events, speech bubbles, and API errors run through redaction. Authentication material is never stored as ordinary plaintext settings fields by AGENTS HQ; Codex owns its own credential store, which AGENTS HQ does not read.

## Codex

AGENTS HQ uses the official app-server protocol only. It does not scrape ChatGPT, drive the desktop UI, or copy browser cookies. Approvals from Codex are presented to the user; AGENTS HQ may only auto-**refuse** when its own policy forbids an action (for example an integration not on the agent’s allowlist).

## Markdown

Rendered Markdown is sanitized in the frontend (`markdown.js`). Model text never becomes raw HTML.
