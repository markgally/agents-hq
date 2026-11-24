# macOS launcher

Double-click **`AGENTS HQ.app`** in this folder.

It opens a Terminal control window (close it to stop AGENTS HQ) and a dedicated Chrome/Edge app window for the dashboard.

## Dock

1. Double-click `AGENTS HQ.app` once.
2. Right-click the Dock icon → **Options → Keep in Dock**.

Keep `AGENTS HQ.app` inside this project’s `macos/` folder so it can find `start.command` and Python sources.

## Rebuild icons

From the project root:

```bash
python3 tools/make_icons.py
```
