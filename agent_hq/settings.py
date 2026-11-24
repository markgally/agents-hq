"""Application preferences and execution settings (key/value, stored in SQLite)."""
import os

from . import security, timeutil
from .db import dumps, loads

APPROVAL_CHOICES = ("on-request", "untrusted", "never")
SANDBOX_CHOICES = ("read-only", "workspace-write")
# Settings the dashboard may change. (`setup_complete` is set only by the verified Setup Guide finish step.)
EDITABLE = ("concurrency", "default_timeout_sec", "max_retries", "timezone", "approval_default",
            "missed_policy_default", "overlap_policy_default", "auto_connect", "collaboration_enabled",
            "tutorial_seen", "max_delegation_depth", "max_child_tasks", "retention_days", "codex_path",
            "allowed_roots", "default_workspace", "default_output_dir")


class Settings(object):
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.defaults = {
            "setup_complete": False,
            "tutorial_seen": False,
            "concurrency": 2,
            "default_timeout_sec": 1800,
            "max_retries": 1,
            "timezone": timeutil.DEFAULT_TZ,
            "default_workspace": config.default_workspace,
            "default_output_dir": config.default_outputs,
            "allowed_roots": [config.default_workspace, config.default_outputs],
            "approval_default": "on-request",
            "missed_policy_default": "skip",
            "overlap_policy_default": "skip",
            "schedule_grace_sec": 300,
            "codex_path": "",
            "auto_connect": True,
            "collaboration_enabled": False,
            "max_delegation_depth": 2,
            "max_child_tasks": 6,
            "retention_days": 0,
            "current_batch_id": "",
            "last_connected_at": "",
        }

    def get(self, key):
        row = self.db.one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            return self.defaults.get(key)
        return loads(row["value"], self.defaults.get(key))

    def set(self, key, value):
        self.db.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, dumps(value), timeutil.iso()))

    def all(self):
        out = dict(self.defaults)
        for row in self.db.all("SELECT key, value FROM settings"):
            out[row["key"]] = loads(row["value"], out.get(row["key"]))
        return out

    def public(self):
        data = self.all()
        data["timezone_available"] = timeutil.tz_available(data["timezone"])
        return data

    def ensure_default_dirs(self):
        """Create the built-in workspace and output folders (only the built-in ones)."""
        for path in (self.config.default_workspace, self.config.default_outputs):
            try:
                os.makedirs(path, exist_ok=True)
            except OSError:
                pass

    # ---- validated update from the API
    def update(self, body, policy_factory):
        if not isinstance(body, dict):
            raise security.bad_request("Settings must be an object.")
        unknown = sorted(set(body) - set(EDITABLE))
        if unknown:
            raise security.bad_request("Unknown setting: %s." % ", ".join(str(k)[:40] for k in unknown[:5]))
        changed = {}
        if "concurrency" in body:
            changed["concurrency"] = security.integer(body["concurrency"], "Maximum concurrent agents", 1, 7)
        if "default_timeout_sec" in body:
            changed["default_timeout_sec"] = security.integer(body["default_timeout_sec"], "Default task timeout", 60, 6 * 3600)
        if "max_retries" in body:
            changed["max_retries"] = security.integer(body["max_retries"], "Retry limit", 0, 2)
        if "timezone" in body:
            tz = security.text(body["timezone"], "Time zone", 64, required=True, multiline=False)
            try:
                timeutil.get_tz(tz)
            except ValueError as exc:
                raise security.bad_request(str(exc))
            changed["timezone"] = tz
        if "approval_default" in body:
            changed["approval_default"] = security.choice(body["approval_default"], "Approval preference", APPROVAL_CHOICES)
        if "missed_policy_default" in body:
            changed["missed_policy_default"] = security.choice(body["missed_policy_default"], "Missed-run policy", ("skip", "catch_up"))
        if "overlap_policy_default" in body:
            changed["overlap_policy_default"] = security.choice(body["overlap_policy_default"], "Overlap policy", ("skip", "queue"))
        for key, label in (("auto_connect", "Connect at start-up"), ("collaboration_enabled", "Collaboration"),
                           ("tutorial_seen", "Tutorial seen")):
            if key in body:
                changed[key] = security.boolean(body[key], label)
        if "max_delegation_depth" in body:
            changed["max_delegation_depth"] = security.integer(body["max_delegation_depth"], "Maximum hand-off depth", 1, 6)
        if "max_child_tasks" in body:
            changed["max_child_tasks"] = security.integer(body["max_child_tasks"], "Maximum hand-offs per run", 1, 12)
        if "retention_days" in body:
            changed["retention_days"] = security.integer(body["retention_days"], "History retention", 0, 3650)
        if "codex_path" in body:
            path = security.text(body["codex_path"], "Codex executable", 500, multiline=False)
            if path and not os.path.isfile(path):
                raise security.bad_request("There is no file at that Codex executable path.")
            # Only a Codex executable can be named here; AGENTS HQ never runs an arbitrary program from a setting.
            if path and os.path.basename(path).lower() not in ("codex", "codex.exe"):
                raise security.bad_request("The file must be the Codex executable (codex or codex.exe).")
            changed["codex_path"] = path

        roots = None
        if "allowed_roots" in body:
            if not isinstance(body["allowed_roots"], list) or not body["allowed_roots"] or len(body["allowed_roots"]) > 20:
                raise security.bad_request("List between 1 and 20 permitted workspace folders.")
            policy = policy_factory([])
            roots = []
            for item in body["allowed_roots"]:
                resolved = policy.check_root(item)
                if resolved not in roots:
                    roots.append(resolved)
            changed["allowed_roots"] = roots
        effective_roots = roots if roots is not None else self.get("allowed_roots")
        for key, label in (("default_workspace", "Default working folder"), ("default_output_dir", "Output folder")):
            if key in body:
                changed[key] = policy_factory(effective_roots).check_workdir(body[key])
        if roots is not None:
            policy = policy_factory(roots)
            for key in ("default_workspace", "default_output_dir"):
                current = changed.get(key, self.get(key))
                try:
                    policy.check_workdir(current)
                except security.ApiError:
                    raise security.bad_request(
                        "The %s must stay inside a permitted workspace. Change it first, then remove the folder."
                        % ("default working folder" if key == "default_workspace" else "output folder"))
        for key, value in changed.items():
            self.set(key, value)
        return changed
