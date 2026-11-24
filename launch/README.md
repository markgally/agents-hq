# Windows launch helpers

| File | Purpose |
|---|---|
| `../AGENTS HQ.vbs` | Double-click to start AGENTS HQ like an app (no console) |
| `run-app.ps1` | Hidden supervisor: starts the server, opens the app window, stops when the window closes |
| `Create Desktop Shortcut.ps1` | Creates a Desktop icon pointing at the VBS |
| `open-app.cmd` | Opens Edge/Chrome in `--app` mode (used by `start.bat`) |
| `open-app-delayed.cmd` | Waits briefly for the server, then opens the app window |

**Desktop shortcut / VBS:** close the Edge/Chrome app window to stop the server (schedules stop too).

**`start.bat`:** keeps a visible console for debugging — close that window to stop.
