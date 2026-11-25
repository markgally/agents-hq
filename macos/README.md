# AGENTS HQ on Mac

## Install once

Double-click **Install AGENTS HQ.command** in this folder. The one-time installer
can show Terminal while it downloads and sets up the app. Subsequent launches
from Applications, Desktop or Dock run without Terminal.

Setup:

- Downloads private CPython **3.14.10** for Apple Silicon or Intel from Astral's
  python-build-standalone release `20261124`, and checks the architecture-specific
  SHA-256 before extraction. No system Python, pip packages or administrator
  privileges are required.
- Repairs executable permissions and copies the app into
  **~/Applications/AGENTS HQ.app**.
- Adds a Desktop shortcut and a **persistent Dock icon**. The pin remains when
  the short-lived launcher exits; it does not depend on the server being a Dock app.
  Existing Dock entries and their order are preserved, and repeated setup does
  not add duplicate AGENTS HQ icons.

You can also open the app in this folder directly; first launch performs the same
setup in the background. The installer is recommended because it shows initial
download progress. An internet connection is required only to obtain the runtime.

If macOS blocks a downloaded copy on first launch, follow
[Apple’s instructions](https://support.apple.com/en-us/102445) for that trusted copy
using **System Settings → Privacy & Security → Open Anyway**. The installer does
not change system security settings. If an extracted ZIP lost executable
permissions, open Terminal in the project folder and run:

```bash
bash "macos/Install AGENTS HQ.command"
```

The installer also accepts `--no-dock` and `--no-desktop` to omit those shortcuts.
It preserves an existing `.env` and copies `.env.example` only when needed.
Keep the project folder in its installed location. If you move it, run the
installer again from its new location to update the installed app's pointer.

## Open and stop

Click **AGENTS HQ in the Dock** or double-click its Applications/Desktop icon.
It opens the dashboard in your default browser and runs the server in the
background. Repeated clicks reopen the existing instance. Neither the browser
nor a Terminal window owns the server's lifetime.

**Closing the browser leaves AGENTS HQ and schedules running.** To stop this
copy, double-click **Stop AGENTS HQ.command**. That helper verifies the saved
PID's exact Python executable, server script and project before signalling it.
An unrelated process is never stopped because it occupies a port.

`start.command` is a CLI convenience that opens the app; it does not run the
server in that shell. For an explicit debug console, use:

```bash
.runtime/python/bin/python3 -m agent_hq
```

## Missing Dock icon

Run **Add to Dock.command** to restore the persistent pin. It can also update an
older AGENTS HQ pin to the installed Applications app. The Dock is refreshed once
when the pin changes; other apps and windows are left running. Normal app launches
do not re-pin an icon that you intentionally removed.

## Configuration and logs

The launcher honors `.env` settings including `PORT` (default **4181**), data,
workspace, output folders and the optional Codex executable path. Finder's limited
PATH is supplemented with the usual user, Cargo and Homebrew executable folders.
Existing Codex authentication remains owned by Codex.

- `.runtime/python/`: private interpreter; excluded from git.
- `.runtime/mac-setup.log`: background first-launch setup log.
- `.runtime/mac-install.json`: local installation pointer; excluded from git.
- `data/mac-server.log`: server output, under the configured data folder.
- `data/mac-server.json`: owned-process metadata, under that same data folder.
- `data/install-backups/`: Dock preference snapshots made before pin changes.

If another app occupies the configured port, AGENTS HQ reports the collision
without killing it. Choose another `PORT` in `.env` and reopen AGENTS HQ. If you
change the data folder, stop the existing instance before making that change.
Keep intentional package-level `.pyc` backend files: they are why this release
requires CPython 3.14. The installer does not recover their missing source.

## Validation and icons

Run the Mac regression checks with the private interpreter:

```bash
.runtime/python/bin/python3 -m unittest tests.test_macos_launcher -v
```

The tests use temporary Applications/Desktop folders and simulated Dock
preferences, plus a real isolated background server. They do not change your
actual Dock or stop existing AGENTS HQ instances. The native checks run on macOS;
other platforms skip this Mac-specific test module.

To rebuild the existing artwork, use `.runtime/python/bin/python3 tools/make_icons.py`.

See [the Mac validation report](../docs/MACOS_TEST_REPORT.md) for the verified installation path and the existing backend test limitation.
