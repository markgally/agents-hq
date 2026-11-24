"""Paths and start-up configuration."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PORT = 4181

# Only these keys are read from .env. Anything else in that file is ignored and never loaded.
_ENV_KEYS = ("PORT", "AGENT_HQ_DATA", "AGENT_HQ_WORKSPACE", "AGENT_HQ_OUTPUTS", "AGENT_HQ_CODEX",
             "AGENT_HQ_MOCK_CODEX", "AGENT_HQ_NO_AUTOCONNECT")


def read_env_file(root=ROOT):
    values = {}
    path = os.path.join(root, ".env")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key in _ENV_KEYS:
                    values[key] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


class Config(object):
    def __init__(self, root=ROOT, data_dir=None, port=None, codex_command=None, mock=None,
                 scheduler_interval=15.0, autoconnect=None, default_workspace=None, default_outputs=None):
        env = read_env_file(root)

        def setting(key):
            return os.environ.get(key) or env.get(key) or ""

        self.root = root
        self.static_dir = os.path.join(root, "static")
        self.data_dir = os.path.abspath(data_dir or setting("AGENT_HQ_DATA") or os.path.join(root, "data"))
        self.db_path = os.path.join(self.data_dir, "agent_hq.db")
        self.schema_cache_dir = os.path.join(self.data_dir, "codex-schema")
        self.default_workspace = os.path.abspath(
            default_workspace or setting("AGENT_HQ_WORKSPACE") or os.path.join(root, "workspace"))
        self.default_outputs = os.path.abspath(
            default_outputs or setting("AGENT_HQ_OUTPUTS") or os.path.join(root, "outputs"))
        try:
            self.port = int(port if port is not None else (setting("PORT") or DEFAULT_PORT))
        except ValueError:
            self.port = DEFAULT_PORT
        # A mock app server is used only by automated tests and by an explicitly labelled development mode.
        self.mock = bool(mock) if mock is not None else setting("AGENT_HQ_MOCK_CODEX") == "1"
        self.codex_command = codex_command
        self.codex_path_override = setting("AGENT_HQ_CODEX") or None
        self.scheduler_interval = scheduler_interval
        if autoconnect is None:
            autoconnect = setting("AGENT_HQ_NO_AUTOCONNECT") != "1"
        self.autoconnect = autoconnect
