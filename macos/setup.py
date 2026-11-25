"""Install the app, repair executable modes, and persist an ordinary Dock pin."""
import argparse
import fcntl
from pathlib import Path
import plistlib
import random
import shutil
import subprocess
import time

from common import BUNDLE_ID, ROOT, atomic_json, configuration


def bundle_id(path):
    try:
        with (Path(path) / "Contents/Info.plist").open("rb") as stream:
            return plistlib.load(stream).get("CFBundleIdentifier")
    except (OSError, ValueError):
        return None


def dock_tile(app, guid=None):
    return {"GUID": guid or random.randint(1, 2**31 - 1), "tile-type": "file-tile", "tile-data": {
        "file-data": {"_CFURLString": app.as_uri() + "/", "_CFURLStringType": 15},
        "file-label": "AGENTS HQ", "file-type": 41, "bundle-identifier": BUNDLE_ID}}


def update_dock(app, backup_dir, run=subprocess.run):
    result = run(["/usr/bin/defaults", "export", "com.apple.dock", "-"], check=True, capture_output=True)
    preferences = plistlib.loads(result.stdout)
    tiles = preferences.get("persistent-apps", [])
    matches = [i for i, tile in enumerate(tiles) if tile.get("tile-data", {}).get("bundle-identifier") == BUNDLE_ID]
    desired_url = app.as_uri() + "/"
    if len(matches) == 1 and tiles[matches[0]].get("tile-data", {}).get("file-data", {}).get("_CFURLString") == desired_url:
        return False
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / ("dock-" + str(time.time_ns()) + ".plist")).write_bytes(result.stdout)
    if not matches:
        run(["/usr/bin/defaults", "write", "com.apple.dock", "persistent-apps", "-array-add",
             plistlib.dumps(dock_tile(app)).decode()], check=True)
    else:
        first = matches[0]
        updated = [dock_tile(app, tile.get("GUID")) if i == first else tile
                   for i, tile in enumerate(tiles) if i == first or i not in matches]
        run(["/usr/bin/defaults", "write", "com.apple.dock", "persistent-apps", "-array",
             *[plistlib.dumps(tile).decode() for tile in updated]], check=True)
    run(["/usr/bin/killall", "Dock"], check=False, capture_output=True)
    return True


def install(root=ROOT, home=None, pin=True, desktop=True, run=subprocess.run):
    home = Path.home() if home is None else Path(home)
    root = Path(root).resolve()
    (root / ".runtime").mkdir(exist_ok=True)
    if not (root / ".env").exists() and (root / ".env.example").is_file():
        shutil.copy2(root / ".env.example", root / ".env")
    config = configuration(root)
    data = Path(config.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    destination = home / "Applications/AGENTS HQ.app"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and bundle_id(destination) != BUNDLE_ID:
        raise RuntimeError("An unrelated application already exists at " + str(destination))
    source = root / "macos/AGENTS HQ.app"
    source.joinpath("Contents/MacOS/AGENTS HQ").chmod(0o755)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    destination.joinpath("Contents/MacOS/AGENTS HQ").chmod(0o755)
    with destination.joinpath("Contents/Resources/install.plist").open("wb") as stream:
        plistlib.dump({"ProjectRoot": str(root)}, stream)
    for name in ("start.command", "macos/bootstrap.sh", "macos/Install AGENTS HQ.command",
                 "macos/Add to Dock.command", "macos/Stop AGENTS HQ.command"):
        (root / name).chmod(0o755)
    if desktop:
        shortcut = home / "Desktop/AGENTS HQ.app"
        try:
            shortcut.parent.mkdir(parents=True, exist_ok=True)
            if shortcut.is_symlink() and (bundle_id(shortcut) == BUNDLE_ID or not shortcut.exists()):
                shortcut.unlink()
            if not shortcut.exists() and not shortcut.is_symlink():
                shortcut.symlink_to(destination, target_is_directory=True)
        except PermissionError:
            print("Desktop access was unavailable; use the Dock or Applications icon.")
    if pin:
        update_dock(destination, data / "install-backups", run)
    atomic_json(root / ".runtime/mac-install.json", {"application": str(destination), "root": str(root)})
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "ensure", "dock"))
    parser.add_argument("--no-dock", action="store_true")
    parser.add_argument("--no-desktop", action="store_true")
    args = parser.parse_args()
    (ROOT / ".runtime").mkdir(exist_ok=True)
    with (ROOT / ".runtime/mac-setup.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = ROOT / ".runtime/mac-install.json"
        if args.action == "ensure" and marker.exists():
            import json
            metadata = json.loads(marker.read_text())
            if metadata.get("root") == str(ROOT) and bundle_id(metadata.get("application", "")) == BUNDLE_ID:
                return
        app = install(pin=not args.no_dock, desktop=not args.no_desktop and args.action != "dock")
        print("Installed:", app)
        print("Use the AGENTS HQ Dock icon. The server runs without Terminal.")


if __name__ == "__main__":
    main()
