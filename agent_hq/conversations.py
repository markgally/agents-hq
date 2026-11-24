"""Local conversation store.

Holds what the Chat tab needs to present and recover a conversation. Codex remains the authoritative
thread history; `import_thread` rebuilds the local view from Codex when asked.
"""
import threading
import time

from . import timeutil
from .db import dumps, loads, new_id
from .security import clip, redact, redact_deep

MAX_TOOL_OUTPUT = 20000
FLUSH_INTERVAL = 0.6


class ConversationManager(object):
    def __init__(self, db, bus):
        self.db = db
        self.bus = bus
        self._live = {}      # message id -> {"text": str, "flushed": float, "dirty": bool}
        self._lock = threading.Lock()

    # ---- writing
    def add(self, agent_id, role, content, kind="text", thread_id=None, run_id=None, provider_message_id=None,
            status="complete", meta=None, message_id=None):
        message_id = message_id or new_id("msg")
        now = timeutil.iso()
        content = redact(content) if content else content  # the stored transcript never keeps credentials
        meta = redact_deep(meta) if meta else meta
        with self.db.tx() as c:
            if provider_message_id:
                row = c.execute("SELECT id FROM messages WHERE agent_id = ? AND thread_id IS ? AND provider_message_id = ?",
                                (agent_id, thread_id, provider_message_id)).fetchone()
                if row:
                    c.execute("UPDATE messages SET content = ?, status = ?, meta = ?, kind = ? WHERE id = ?",
                              (content, status, dumps(meta or {}), kind, row["id"]))
                    return row["id"]
            seq = c.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM messages").fetchone()[0]
            c.execute("INSERT INTO messages(id, agent_id, thread_id, run_id, provider_message_id, role, kind, content, "
                      "meta, status, created_at, seq) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (message_id, agent_id, thread_id, run_id, provider_message_id, role, kind, content,
                       dumps(meta or {}), status, now, seq))
        return message_id

    def update(self, message_id, content=None, status=None, meta=None, thread_id=None):
        fields, params = [], []
        if content is not None:
            fields.append("content = ?")
            params.append(redact(content))
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if meta is not None:
            fields.append("meta = ?")
            params.append(dumps(redact_deep(meta)))
        if thread_id is not None:
            fields.append("thread_id = ?")
            params.append(thread_id)
        if fields:
            self.db.execute("UPDATE messages SET %s WHERE id = ?" % ", ".join(fields), params + [message_id])
        with self._lock:
            if status in ("complete", "cancelled"):
                self._live.pop(message_id, None)

    def append_live(self, message_id, delta, limit=None):
        """Buffer streamed text and write it to the database at most every FLUSH_INTERVAL seconds."""
        with self._lock:
            entry = self._live.setdefault(message_id, {"text": "", "flushed": 0.0})
            if limit is None or len(entry["text"]) < limit:
                entry["text"] += delta
            text = entry["text"]
            due = time.time() - entry["flushed"] >= FLUSH_INTERVAL
            if due:
                entry["flushed"] = time.time()
        if due:
            self.db.execute("UPDATE messages SET content = ? WHERE id = ?", (redact(text), message_id))
        return text

    def live_text(self, message_id):
        with self._lock:
            entry = self._live.get(message_id)
            return entry["text"] if entry else None

    # ---- reading
    def _shape(self, row):
        row = dict(row)
        row["meta"] = loads(row["meta"], {})
        live = self.live_text(row["id"])
        if live is not None and row["status"] == "streaming":
            row["content"] = redact(live)
        return row

    def get(self, message_id):
        row = self.db.one("SELECT * FROM messages WHERE id = ?", (message_id,))
        return self._shape(row) if row else None

    def list(self, agent_id, limit=300, before_seq=None):
        sql = "SELECT * FROM messages WHERE agent_id = ?"
        params = [agent_id]
        if before_seq:
            sql += " AND seq < ?"
            params.append(int(before_seq))
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        return [self._shape(r) for r in reversed(self.db.all(sql, params))]

    def clear(self, agent_id):
        self.db.execute("DELETE FROM messages WHERE agent_id = ?", (agent_id,))

    def finish_streaming_for_run(self, run_id, status="complete"):
        """Close any message still marked as streaming when a run ends for any reason."""
        rows = self.db.all("SELECT id FROM messages WHERE run_id = ? AND status = 'streaming'", (run_id,))
        for row in rows:
            live = self.live_text(row["id"])
            self.update(row["id"], content=live, status=status)

    # ---- import from Codex
    def import_thread(self, agent_id, thread):
        """Rebuild local messages for a thread from Codex's own record. Returns the number imported."""
        thread_id = thread.get("id")
        count = 0
        for turn in thread.get("turns", []) or []:
            for item in turn.get("items", []) or []:
                kind = item.get("type")
                if kind == "userMessage":
                    text = "\n".join(p.get("text", "") for p in item.get("content", []) if p.get("type") == "text")
                    if text.strip():
                        self.add(agent_id, "user", redact(text), thread_id=thread_id, provider_message_id=item.get("id"),
                                 meta={"imported": True, "turn_id": turn.get("id")})
                        count += 1
                elif kind == "agentMessage" and (item.get("text") or "").strip():
                    self.add(agent_id, "assistant", redact(item["text"]), thread_id=thread_id,
                             provider_message_id=item.get("id"), meta={"imported": True, "turn_id": turn.get("id")})
                    count += 1
                elif kind == "commandExecution":
                    self.add(agent_id, "tool", clip(redact(item.get("aggregatedOutput") or ""), MAX_TOOL_OUTPUT),
                             kind="command", thread_id=thread_id, provider_message_id=item.get("id"),
                             meta={"imported": True, "command": redact(item.get("command") or ""),
                                   "exit_code": item.get("exitCode"), "status": item.get("status"),
                                   "turn_id": turn.get("id")})
                    count += 1
        return count
