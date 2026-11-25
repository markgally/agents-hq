"""Shared local Mac installation and process helpers (stdlib only)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent_hq.config import Config

BUNDLE_ID = "local.agenthq.app"


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def configuration(root=ROOT):
    return Config(root=str(root))


def state_path(config):
    return Path(config.data_dir) / "mac-server.json"


def read_state(config):
    try:
        return json.loads(state_path(config).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def owns_process(state, config):
    """PID alone is insufficient: require our exact runtime, script and checkout."""
    if not state or state.get("root") != str(Path(config.root).resolve()):
        return False
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 1:
        return False
    command = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True).stdout.strip()
    python = str(Path(config.root) / ".runtime/python/bin/python3")
    server = str(Path(config.root) / "macos/server.py")
    return command == python + " " + server


def healthy(port):
    # Ignore proxy environment variables for the loopback-only application.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            data = json.load(response)
        return data.get("ok") is True and data.get("app") == "AGENTS HQ"
    except (OSError, ValueError):
        return False


def show_error(message):
    # Structured argv: paths, quotes and shell characters remain literal.
    subprocess.run(["/usr/bin/osascript", "-e",
                    'on run argv\ndisplay alert "AGENTS HQ" message (item 1 of argv) as critical\nend run',
                    str(message)])
