"""Output manager: stores real results and only ever references files that were verified on disk."""
import mimetypes
import os
import subprocess
import sys

from . import security, timeutil
from .db import new_id
from .security import clip, redact

MAX_CONTENT = 400000
MAX_PREVIEW_BYTES = 200000
# Files that may be opened with the operating system's default application. Anything else can only be
# revealed in its folder, so AGENTS HQ never launches a script or program on the user's behalf.
SAFE_OPEN_EXT = {".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".log", ".xml", ".yaml", ".yml", ".pdf",
                 ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXT_EXT = {".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".log", ".xml", ".yaml", ".yml", ".py", ".js", ".ts",
            ".tsx", ".jsx", ".html", ".css", ".sql", ".sh", ".bat", ".ps1", ".toml", ".ini", ".cfg", ".java", ".go",
            ".rs", ".c", ".h", ".cpp", ".cs", ".rb", ".php"}


class OutputManager(object):
    def __init__(self, db, bus, agents):
        self.db = db
        self.bus = bus
        self.agents = agents
        self.launch = self._launch  # replaced in automated tests so no window opens

    # ---- recording
    def _insert(self, agent_id, run, title, output_type, content=None, path=None, status="completed"):
        output_id = new_id("out")
        size = None
        mime = None
        if path:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = None
            mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        elif content is not None:
            size = len(content.encode("utf-8"))
            mime = "text/markdown" if output_type in ("markdown", "text") else "text/plain"
        self.db.execute(
            "INSERT INTO outputs(id, agent_id, run_id, task_id, title, output_type, content, verified_file_path, "
            "mime_type, size_bytes, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (output_id, agent_id, run["id"], run.get("task_id"), title[:200], output_type, content, path, mime, size,
             status, timeutil.iso()))
        output = self.get(output_id)
        # Chat answers stay out of the Bot Log (the chat turn itself is already logged); task results and files are logged.
        noteworthy = output_type == "file" or run.get("kind") == "task"
        self.bus.publish("output.created", {"output": self.summary(output)}, agent_id=agent_id, run_id=run["id"],
                         category="completed", log=("Output saved: %s." % title[:120]) if noteworthy else None)
        return output

    def record_result(self, agent, run, text, status="completed"):
        """Store the agent's final answer. Task results are also written to the output folder and verified."""
        text = clip(redact(text or ""), MAX_CONTENT)
        if not text.strip():
            return None
        title = redact(run.get("title") or text.strip().splitlines()[0][:80])
        path = None
        if run["kind"] == "task":
            path = self._write_report(agent, run, title, text)
        return self._insert(agent["id"], run, title, "markdown", content=text, path=path, status=status)

    def _write_report(self, agent, run, title, text):
        """Write a Markdown report into the agent's output folder. Returns the path only if the file exists."""
        try:
            base = self.agents.policy().check_workdir(self.agents.output_dir(agent))
        except security.ApiError:
            return None
        folder = os.path.join(base, agent["id"])
        stamp = timeutil.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(folder, "%s-%s.md" % (stamp, security.slug(title)))
        header = "# %s\n\n- Agent: %s (%s)\n- Finished: %s UTC\n- Run: %s\n\n---\n\n" % (
            title, agent["display_name"], agent["role"], timeutil.iso(), run["id"])
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(header + text + "\n")
        except OSError:
            return None
        return os.path.realpath(path) if os.path.isfile(path) else None

    def record_file_changes(self, agent, run, changes):
        """Record files Codex reported changing, keeping only those that exist inside a permitted workspace."""
        policy = self.agents.policy()
        recorded = []
        seen = set()
        for change in changes:
            path = change.get("path")
            kind = (change.get("kind") or {}).get("type") if isinstance(change.get("kind"), dict) else change.get("kind")
            if not isinstance(path, str) or kind == "delete":
                continue
            try:
                resolved = policy.check_file(path)
            except security.ApiError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            title = "%s %s" % ("Created" if kind == "add" else "Changed", os.path.basename(resolved))
            recorded.append(self._insert(agent["id"], run, title, "file", path=resolved))
        return recorded

    # ---- reading
    @staticmethod
    def summary(row):
        out = {k: row[k] for k in ("id", "agent_id", "run_id", "task_id", "title", "output_type", "mime_type",
                                   "size_bytes", "status", "created_at")}
        out["file_path"] = row["verified_file_path"]
        out["file_name"] = os.path.basename(row["verified_file_path"]) if row["verified_file_path"] else None
        out["has_content"] = row["content"] is not None
        if row["content"]:
            out["excerpt"] = row["content"][:240]
        return out

    def get(self, output_id):
        return self.db.one("SELECT * FROM outputs WHERE id = ?", (output_id,))

    def require(self, output_id, agent_id=None):
        row = self.get(security.record_id(output_id, "output"))
        if row is None or (agent_id and row["agent_id"] != agent_id):
            raise security.not_found("There is no output with that id.")
        return row

    def list(self, agent_id=None, task_id=None, status=None, date_from=None, date_to=None, query=None, limit=200):
        sql = ("SELECT o.*, r.title AS run_title, r.kind AS run_kind, r.status AS run_status FROM outputs o "
               "LEFT JOIN task_runs r ON r.id = o.run_id WHERE 1=1")
        params = []
        if agent_id:
            sql += " AND o.agent_id = ?"
            params.append(agent_id)
        if task_id:
            sql += " AND o.task_id = ?"
            params.append(task_id)
        if status:
            sql += " AND o.status = ?"
            params.append(status)
        if date_from:
            sql += " AND o.created_at >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND o.created_at < ?"
            params.append(date_to)
        if query:
            sql += " AND (o.title LIKE ? OR o.content LIKE ?)"
            like = "%" + query.replace("%", "").replace("_", "")[:80] + "%"
            params += [like, like]
        sql += " ORDER BY o.created_at DESC, o.rowid DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        out = []
        for row in self.db.all(sql, params):
            item = self.summary(row)
            item["run_title"] = redact(row["run_title"])
            item["run_kind"] = row["run_kind"]
            out.append(item)
        return out

    def detail(self, output_id):
        row = self.require(output_id)
        item = self.summary(row)
        item["content"] = row["content"]
        item["file_exists"] = None
        item["preview"] = None
        item["can_open"] = False
        path = row["verified_file_path"]
        if path:
            try:
                resolved = self.agents.policy().check_file(path)
                item["file_exists"] = True
                ext = os.path.splitext(resolved)[1].lower()
                item["can_open"] = ext in SAFE_OPEN_EXT
                if row["content"] is None and ext in TEXT_EXT and os.path.getsize(resolved) <= MAX_PREVIEW_BYTES:
                    with open(resolved, encoding="utf-8", errors="replace") as fh:
                        item["preview"] = redact(fh.read())
            except security.ApiError:
                item["file_exists"] = False
            except OSError:
                item["file_exists"] = False
        return item

    def file_for_download(self, output_id):
        """Return (path or None, filename, mime, text content or None) for a download."""
        row = self.require(output_id)
        if row["verified_file_path"]:
            path = self.agents.policy().check_file(row["verified_file_path"])
            return path, security.safe_filename(os.path.basename(path)), row["mime_type"] or "application/octet-stream", None
        if row["content"] is None:
            raise security.not_found("This output has nothing to download.")
        return None, security.safe_filename(security.slug(row["title"]) + ".md"), "text/markdown; charset=utf-8", row["content"]

    def reveal(self, output_id):
        """Show the file in the operating system's file manager."""
        row = self.require(output_id)
        if not row["verified_file_path"]:
            raise security.conflict("This output is not a file.", "no_file")
        path = self.agents.policy().check_file(row["verified_file_path"])
        try:
            self.launch("reveal", path)
        except OSError:
            raise security.conflict("The folder could not be opened on this computer.", "open_failed")
        return {"ok": True, "folder": os.path.dirname(path)}

    @staticmethod
    def _launch(kind, path):
        """Hand a verified path to the operating system. Fixed argument lists only; no shell is involved."""
        if kind == "reveal":
            if os.name == "nt":
                subprocess.Popen(["explorer.exe", "/select,", path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        elif os.name == "nt":
            os.startfile(path)  # noqa: S606 - extension allow-listed by the caller, path verified inside a workspace
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def open(self, output_id):
        """Open a document-type file with its default application. Programs and scripts are never launched."""
        row = self.require(output_id)
        if not row["verified_file_path"]:
            raise security.conflict("This output is not a file.", "no_file")
        path = self.agents.policy().check_file(row["verified_file_path"])
        if os.path.splitext(path)[1].lower() not in SAFE_OPEN_EXT:
            raise security.conflict("For safety, this file type is not opened directly. Use Open folder instead.",
                                    "unsafe_type")
        try:
            self.launch("open", path)
        except OSError:
            raise security.conflict("The file could not be opened on this computer.", "open_failed")
        return {"ok": True}

    def clear(self, agent_id=None):
        """Remove output records. Files on disk are left where they are."""
        if agent_id:
            self.db.execute("DELETE FROM outputs WHERE agent_id = ?", (agent_id,))
        else:
            self.db.execute("DELETE FROM outputs")
