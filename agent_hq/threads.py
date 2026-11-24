"""Thread manager: exactly one primary Codex thread per agent.

Thread ids always come from Codex. An association that cannot be resumed is marked unavailable and
reported; it is never silently replaced with a new thread.
"""
from . import security, timeutil
from .codex.rpc import RpcError
from .db import new_id
from .security import redact


class ThreadUnavailable(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


class ThreadManager(object):
    def __init__(self, db, bus, adapter, agents, conversations):
        self.db = db
        self.bus = bus
        self.adapter = adapter
        self.agents = agents
        self.conversations = conversations
        self.is_agent_busy = lambda agent_id: False  # set by the execution manager

    # ---- reading
    def active(self, agent_id):
        return self.db.one("SELECT * FROM agent_threads WHERE agent_id = ? AND archived_at IS NULL", (agent_id,))

    def registry(self):
        """One entry per agent for the Codex Integration dialog."""
        rows = {r["agent_id"]: r for r in self.db.all("SELECT * FROM agent_threads WHERE archived_at IS NULL")}
        out = []
        for agent in self.agents.list():
            row = rows.get(agent["id"])
            out.append(self.public(agent["id"], row, agent))
        return out

    def public(self, agent_id, row=None, agent=None):
        if row is None:
            row = self.active(agent_id)
        if row is None:
            return {"agent_id": agent_id, "status": "uninitialized", "provider_thread_id": None,
                    "detail": "No thread yet. One is created the first time this agent is used."}
        status = row["status"]
        detail = row["status_detail"]
        if status == "active" and self.adapter.account_scope and row["account_scope"] not in (self.adapter.account_scope, "unknown"):
            status = "unavailable"
            detail = "This thread belongs to a different Codex account than the one signed in now."
        return {"agent_id": agent_id, "id": row["id"], "status": status, "detail": detail,
                "provider_thread_id": row["provider_thread_id"], "origin": row["origin"],
                "loaded": row["provider_thread_id"] in self.adapter.loaded_threads,
                "created_at": row["created_at"], "last_used_at": row["last_used_at"]}

    def history(self, agent_id):
        return self.db.all("SELECT id, provider_thread_id, origin, status, created_at, last_used_at, archived_at "
                           "FROM agent_threads WHERE agent_id = ? ORDER BY created_at DESC", (agent_id,))

    def _publish(self, agent_id, log=None, severity="info"):
        self.bus.publish("thread.updated", {"thread": self.public(agent_id)}, agent_id=agent_id, log=log,
                         severity=severity, category=("error" if severity == "error" else "info") if log else None)

    # ---- thread parameters
    def _thread_params(self, agent, cwd):
        perms = agent["permissions"]
        params = {"cwd": cwd, "sandbox": perms["sandbox"], "approvalPolicy": perms["approval"],
                  "developerInstructions": self.agents.developer_instructions(agent)}
        if agent.get("model"):
            params["model"] = agent["model"]
        return params

    # ---- ensure (used by the execution manager, never by idle code)
    def ensure(self, agent, cwd):
        """Return (provider_thread_id, created, config_changed) for an agent, creating or resuming as needed."""
        row = self.active(agent["id"])
        scope = self.adapter.account_scope or "unknown"
        if row is None:
            res = self.adapter.start_thread(self._thread_params(agent, cwd))
            thread_id = res["thread"]["id"]
            now = timeutil.iso()
            self.db.execute(
                "INSERT INTO agent_threads(id, agent_id, provider, account_scope, provider_thread_id, origin, status, "
                "applied_config_hash, created_at, last_used_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id("thr"), agent["id"], "codex", scope, thread_id, "created", "active",
                 self.agents.config_hash(agent), now, now))
            self.adapter.name_thread(thread_id, "AGENTS HQ - %s" % agent["display_name"])
            self._publish(agent["id"], log="A Codex thread was created for %s." % agent["display_name"])
            return thread_id, True, False

        thread_id = row["provider_thread_id"]
        if row["account_scope"] not in (scope, "unknown") and scope != "unknown":
            raise ThreadUnavailable("This agent's thread belongs to a different Codex account than the one signed in now. "
                                    "Sign in to the original account, or reset the thread in Codex Integration.")
        if thread_id not in self.adapter.loaded_threads:
            params = self._thread_params(agent, cwd)
            params["threadId"] = thread_id
            params["excludeTurns"] = True
            try:
                self.adapter.resume_thread(params)
            except RpcError as exc:
                if exc.kind in ("closed", "timeout"):
                    raise
                detail = "Codex could not reopen this thread: %s" % redact(exc.message)[:300]
                self.db.execute("UPDATE agent_threads SET status = 'unavailable', status_detail = ? WHERE id = ?",
                                (detail, row["id"]))
                self._publish(agent["id"], log="%s's thread is unavailable." % agent["display_name"], severity="error")
                raise ThreadUnavailable(detail + " Nothing was replaced. Use Codex Integration to retry, associate "
                                                 "another thread, or reset this agent's thread.")
            if row["status"] != "active":
                self.db.execute("UPDATE agent_threads SET status = 'active', status_detail = NULL WHERE id = ?", (row["id"],))
        elif row["status"] == "unavailable":
            raise ThreadUnavailable(row["status_detail"] or "This agent's thread is unavailable.")
        changed = row["applied_config_hash"] != self.agents.config_hash(agent)
        return thread_id, False, changed

    def mark_used(self, agent, thread_id):
        self.db.execute("UPDATE agent_threads SET last_used_at = ?, applied_config_hash = ? "
                        "WHERE agent_id = ? AND provider_thread_id = ? AND archived_at IS NULL",
                        (timeutil.iso(), self.agents.config_hash(agent), agent["id"], thread_id))

    # ---- explicit user actions
    def _require_idle(self, agent_id):
        if self.is_agent_busy(agent_id):
            raise security.conflict("This agent is working. Stop its task or wait for it to finish first.", "agent_busy")

    def resume(self, agent_id):
        """Try to reopen the saved thread now (for example after it was marked unavailable)."""
        agent = self.agents.get(agent_id)
        row = self.active(agent_id)
        if row is None:
            raise security.conflict("This agent has no thread yet. It is created the first time the agent is used.",
                                    "no_thread")
        self.adapter.loaded_threads.discard(row["provider_thread_id"])
        if row["status"] == "unavailable":
            self.db.execute("UPDATE agent_threads SET status = 'active', status_detail = NULL WHERE id = ?", (row["id"],))
        try:
            self.ensure(agent, self.agents.workdir(agent))
        except ThreadUnavailable as exc:
            raise security.conflict(exc.message, "thread_unavailable")
        self._publish(agent_id, log="%s's thread was reopened." % agent["display_name"])
        return self.public(agent_id)

    def discover(self, search=None):
        """Threads known to the connected Codex, marked with the agent that already uses each one."""
        res = self.adapter.list_threads(limit=40, search=search or None)
        claimed = {r["provider_thread_id"]: r["agent_id"]
                   for r in self.db.all("SELECT provider_thread_id, agent_id FROM agent_threads WHERE archived_at IS NULL")}
        out = []
        for t in res.get("data", []):
            out.append({"id": t.get("id"), "name": redact(t.get("name") or "")[:120],
                        "preview": redact(t.get("preview") or "")[:160], "cwd": t.get("cwd"),
                        "updated_at": t.get("updatedAt"), "originator": t.get("originator"),
                        "from_agent_hq": t.get("originator") == "agent_hq",
                        "claimed_by": claimed.get(t.get("id"))})
        return {"threads": out, "has_more": bool(res.get("nextCursor"))}

    def associate(self, agent_id, provider_thread_id, import_history=True):
        """Attach an existing Codex thread chosen by the user. The previous association is archived, not deleted."""
        agent = self.agents.get(agent_id)
        provider_thread_id = security.thread_id(provider_thread_id)
        self._require_idle(agent_id)
        other = self.db.one("SELECT agent_id FROM agent_threads WHERE provider_thread_id = ? AND archived_at IS NULL",
                            (provider_thread_id,))
        if other and other["agent_id"] != agent_id:
            raise security.conflict("That thread is already the primary thread of %s." % other["agent_id"], "thread_claimed")
        if other:
            return self.public(agent_id)
        try:
            res = self.adapter.read_thread(provider_thread_id, include_turns=bool(import_history))
        except RpcError as exc:
            raise security.bad_request("Codex could not find that thread: %s" % redact(exc.message)[:200], "thread_not_found")
        now = timeutil.iso()
        with self.db.tx() as c:
            c.execute("UPDATE agent_threads SET status = 'archived', archived_at = ? WHERE agent_id = ? AND archived_at IS NULL",
                      (now, agent_id))
            c.execute(
                "INSERT INTO agent_threads(id, agent_id, provider, account_scope, provider_thread_id, origin, status, "
                "created_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_id("thr"), agent_id, "codex", self.adapter.account_scope or "unknown", provider_thread_id,
                 "associated", "active", now))
        imported = 0
        if import_history:
            imported = self.conversations.import_thread(agent_id, res.get("thread") or {})
        self._publish(agent_id, log="%s was associated with an existing Codex thread." % agent["display_name"])
        result = self.public(agent_id)
        result["imported_messages"] = imported
        return result

    def archive_association(self, agent_id, reason="archived"):
        """Detach the agent from its thread. The Codex thread itself is left untouched."""
        agent = self.agents.get(agent_id)
        self._require_idle(agent_id)
        row = self.active(agent_id)
        if row is None:
            return self.public(agent_id)
        self.db.execute("UPDATE agent_threads SET status = 'archived', archived_at = ? WHERE id = ?",
                        (timeutil.iso(), row["id"]))
        self.adapter.loaded_threads.discard(row["provider_thread_id"])
        self._publish(agent_id, log="%s's thread association was %s. The agent starts a new thread on next use."
                                    % (agent["display_name"], reason))
        return self.public(agent_id)

    def reset(self, agent_id, confirm):
        if confirm is not True:
            raise security.bad_request("Resetting a thread must be confirmed.", "confirmation_required")
        return self.archive_association(agent_id, reason="reset")

    def sync_history(self, agent_id):
        """Refresh the local conversation view from Codex's record of the thread."""
        self.agents.get(agent_id)
        row = self.active(agent_id)
        if row is None:
            raise security.conflict("This agent has no thread yet.", "no_thread")
        try:
            res = self.adapter.read_thread(row["provider_thread_id"], include_turns=True)
        except RpcError as exc:
            raise security.conflict("Codex could not read this thread: %s" % redact(exc.message)[:200], "thread_unavailable")
        imported = self.conversations.import_thread(agent_id, res.get("thread") or {})
        self.bus.publish("messages.reloaded", {"imported": imported}, agent_id=agent_id)
        return {"imported_messages": imported, "turns": len((res.get("thread") or {}).get("turns", []))}
