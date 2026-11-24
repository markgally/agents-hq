"""Approval manager.

Codex asks for approval through server-to-client JSON-RPC requests. Each one becomes a persistent
approval record, is shown to the user, and is answered only by an explicit user decision. Nothing
here approves automatically; the only automatic answers are refusals required by AGENTS HQ's own rules.
"""
import threading

from . import security, timeutil
from .codex.rpc import RpcError
from .db import dumps, loads, new_id
from .security import clip, redact

# method -> approval type
PROVIDER_METHODS = {
    "item/commandExecution/requestApproval": "command",
    "item/fileChange/requestApproval": "file_change",
    "item/permissions/requestApproval": "permissions",
    "item/tool/requestUserInput": "question",
    "mcpServer/elicitation/request": "tool",
    "execCommandApproval": "command_legacy",
    "applyPatchApproval": "file_change_legacy",
}
DECISIONS = ("accept", "accept_session", "decline", "cancel")
TYPE_LABEL = {"command": "run a command", "command_legacy": "run a command", "file_change": "change files",
              "file_change_legacy": "change files", "permissions": "use extra permissions",
              "question": "ask you a question", "tool": "use an integration", "handoff": "hand work to another agent"}


class ApprovalManager(object):
    def __init__(self, db, bus, adapter, agents):
        self.db = db
        self.bus = bus
        self.adapter = adapter
        self.agents = agents
        self._live = {}   # approval id -> {"rpc_id", "method", "params"} or {"callback"}
        self._lock = threading.Lock()
        # Set by the execution manager.
        self.find_run = lambda thread_id: None            # -> {"run_id", "agent_id"} or None
        self.on_pending_changed = lambda run_id: None

    # ---- reading
    @staticmethod
    def _shape(row):
        row = dict(row)
        row["request_details"] = loads(row["request_details"], {})
        return row

    def pending(self):
        return [self._shape(r) for r in self.db.all("SELECT * FROM approvals WHERE status = 'pending' ORDER BY requested_at")]

    def list(self, agent_id=None, limit=100):
        if agent_id:
            rows = self.db.all("SELECT * FROM approvals WHERE agent_id = ? ORDER BY requested_at DESC LIMIT ?", (agent_id, limit))
        else:
            rows = self.db.all("SELECT * FROM approvals ORDER BY requested_at DESC LIMIT ?", (limit,))
        return [self._shape(r) for r in rows]

    def pending_for_run(self, run_id):
        return self.db.scalar("SELECT COUNT(*) FROM approvals WHERE run_id = ? AND status = 'pending'", (run_id,)) or 0

    # ---- requests from Codex (called on the protocol reader thread; must not block)
    def handle_provider_request(self, rpc_id, method, params):
        kind = PROVIDER_METHODS.get(method)
        if kind is None:
            return False
        thread_id = params.get("threadId") or params.get("conversationId")
        owner = self.find_run(thread_id)
        if owner is None:
            # A request for a thread no agent is running: refuse rather than leave Codex waiting.
            self._answer(rpc_id, method, params, "cancel", None)
            return True
        agent = self.agents.get(owner["agent_id"])
        details = self._details(kind, params)
        refusal = self._policy_refusal(agent, kind, params)
        approval_id = new_id("apr")
        now = timeutil.iso()
        if refusal:
            self.db.execute(
                "INSERT INTO approvals(id, agent_id, run_id, provider_request_id, approval_type, request_details, status, "
                "requested_at, resolved_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (approval_id, agent["id"], owner["run_id"], str(rpc_id), kind, dumps(dict(details, auto_refused=refusal)),
                 "declined", now, now))
            self._answer(rpc_id, method, params, "decline", None)
            self.bus.publish("approval.resolved", {"approval_id": approval_id, "status": "declined", "automatic": True},
                             agent_id=agent["id"], run_id=owner["run_id"], severity="warning", category="approval",
                             log="%s was refused automatically: %s" % (agent["display_name"], refusal))
            return True
        self.db.execute(
            "INSERT INTO approvals(id, agent_id, run_id, provider_request_id, approval_type, request_details, status, "
            "requested_at) VALUES (?,?,?,?,?,?,?,?)",
            (approval_id, agent["id"], owner["run_id"], str(rpc_id), kind, dumps(details), "pending", now))
        with self._lock:
            self._live[approval_id] = {"rpc_id": rpc_id, "method": method, "params": params}
        self.on_pending_changed(owner["run_id"])
        self.bus.publish("approval.requested", {"approval": self.get(approval_id)}, agent_id=agent["id"],
                         run_id=owner["run_id"], severity="warning", category="approval",
                         log="%s needs your approval to %s." % (agent["display_name"], TYPE_LABEL.get(kind, "continue")))
        return True

    def _policy_refusal(self, agent, kind, params):
        """Backend rules that refuse a request regardless of what the model or the user interface says."""
        if kind == "tool":
            server = params.get("serverName") or ""
            if server not in agent["allowed_tools"]:
                return "the integration '%s' is not in this agent's allowed integrations." % server
        if kind == "permissions":
            policy = self.agents.policy()
            fs = (params.get("permissions") or {}).get("fileSystem") or {}
            for key in ("read", "write", "entries"):
                for entry in fs.get(key) or []:
                    path = entry if isinstance(entry, str) else (entry.get("path") if isinstance(entry, dict) else None)
                    if isinstance(path, dict):
                        path = path.get("path")
                    if isinstance(path, str) and any(security.is_within(path, p) or security.is_within(p, path)
                                                     for p in policy.private_roots):
                        return "it asked for access to private application or sign-in storage."
        return None

    @staticmethod
    def _details(kind, params):
        d = {"reason": redact(params.get("reason") or "")[:600]}
        if kind in ("command", "command_legacy"):
            command = params.get("command")
            if isinstance(command, list):
                command = " ".join(str(c) for c in command)
            d["command"] = clip(redact(command or ""), 2000)
            d["cwd"] = params.get("cwd")
            net = params.get("networkApprovalContext")
            if net:
                d["network"] = "%s://%s" % (net.get("protocol"), net.get("host"))
        elif kind == "file_change":
            d["grant_root"] = params.get("grantRoot")
        elif kind == "file_change_legacy":
            d["files"] = sorted((params.get("fileChanges") or {}).keys())[:50]
            d["grant_root"] = params.get("grantRoot")
        elif kind == "permissions":
            perms = params.get("permissions") or {}
            d["cwd"] = params.get("cwd")
            d["network"] = bool((perms.get("network") or {}).get("enabled"))
            fs = perms.get("fileSystem") or {}
            d["read"] = [str(p)[:300] for p in (fs.get("read") or [])][:30]
            d["write"] = [str(p)[:300] for p in (fs.get("write") or [])][:30]
        elif kind == "question":
            d["questions"] = [{"id": q.get("id"), "header": redact(q.get("header") or "")[:120],
                               "question": redact(q.get("question") or "")[:1000],
                               "secret": bool(q.get("isSecret")), "allow_other": bool(q.get("isOther")),
                               "options": [{"label": o.get("label"), "description": o.get("description")}
                                           for o in (q.get("options") or [])][:12]}
                              for q in (params.get("questions") or [])][:8]
        elif kind == "tool":
            d["server"] = params.get("serverName")
            d["message"] = redact(params.get("message") or "")[:1000]
            d["mode"] = params.get("mode")
            if params.get("mode") == "url":
                d["url"] = str(params.get("url") or "")[:500]
        d["item_id"] = params.get("itemId") or params.get("callId")
        return d

    # ---- local approvals (hand-offs between agents)
    def create_local(self, agent_id, run_id, kind, details, callback):
        approval_id = new_id("apr")
        self.db.execute(
            "INSERT INTO approvals(id, agent_id, run_id, approval_type, request_details, status, requested_at) "
            "VALUES (?,?,?,?,?,?,?)", (approval_id, agent_id, run_id, kind, dumps(details), "pending", timeutil.iso()))
        with self._lock:
            self._live[approval_id] = {"callback": callback}
        agent = self.agents.get(agent_id)
        self.bus.publish("approval.requested", {"approval": self.get(approval_id)}, agent_id=agent_id, run_id=run_id,
                         severity="warning", category="approval",
                         log="%s needs your approval to %s." % (agent["display_name"], TYPE_LABEL.get(kind, "continue")))
        return approval_id

    def get(self, approval_id):
        row = self.db.one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        return self._shape(row) if row else None

    # ---- user decision
    def respond(self, approval_id, decision, answers=None):
        security.record_id(approval_id, "approval")
        if decision not in DECISIONS:
            raise security.bad_request("Choose accept, accept for this session, decline, or cancel.")
        approval = self.get(approval_id)
        if approval is None:
            raise security.not_found("There is no approval with that id.")
        if approval["status"] != "pending":
            raise security.conflict("That approval was already answered (%s)." % approval["status"], "already_resolved")
        with self._lock:
            live = self._live.pop(approval_id, None)
        if live is None:
            self._resolve(approval, "expired", "The request is no longer waiting (Codex was restarted or the task ended).")
            raise security.conflict("That request is no longer waiting for an answer.", "expired")
        if decision == "accept_session" and approval["approval_type"] not in ("command", "file_change", "command_legacy"):
            decision = "accept"
        status = {"accept": "accepted", "accept_session": "accepted_session", "decline": "declined", "cancel": "cancelled"}[decision]
        if "callback" in live:
            self._resolve(approval, status)
            live["callback"](decision in ("accept", "accept_session"))
            return self.get(approval_id)
        try:
            self._answer(live["rpc_id"], live["method"], live["params"], decision, answers)
        except RpcError as exc:
            self._resolve(approval, "expired", "Codex disconnected before the answer could be delivered.")
            raise security.conflict("Codex is not connected, so the answer could not be delivered: %s" % redact(exc.message),
                                    "not_connected")
        self._resolve(approval, status)
        return self.get(approval_id)

    def _resolve(self, approval, status, note=None):
        cur = self.db.execute("UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ? AND status = 'pending'",
                              (status, timeutil.iso(), approval["id"]))
        if cur.rowcount == 0:
            return
        if approval.get("run_id"):
            self.on_pending_changed(approval["run_id"])
        agent = self.agents.get(approval["agent_id"])
        words = {"accepted": "accepted", "accepted_session": "accepted for this session", "declined": "declined",
                 "cancelled": "cancelled", "expired": "expired"}[status]
        self.bus.publish("approval.resolved", {"approval_id": approval["id"], "status": status, "note": note},
                         agent_id=approval["agent_id"], run_id=approval.get("run_id"), category="approval",
                         log="Approval %s for %s%s" % (words, agent["display_name"], (": " + note) if note else "."))

    def _answer(self, rpc_id, method, params, decision, answers):
        """Translate a decision into the response shape each Codex request expects."""
        accept = decision in ("accept", "accept_session")
        if method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            result = {"decision": {"accept": "accept", "accept_session": "acceptForSession",
                                   "decline": "decline", "cancel": "cancel"}[decision]}
        elif method in ("execCommandApproval", "applyPatchApproval"):
            result = {"decision": {"accept": "approved", "accept_session": "approved_for_session",
                                   "decline": "denied", "cancel": "abort"}[decision]}
        elif method == "item/permissions/requestApproval":
            requested = params.get("permissions") or {}
            granted = {}
            if accept:
                if requested.get("fileSystem"):
                    granted["fileSystem"] = requested["fileSystem"]
                if requested.get("network"):
                    granted["network"] = requested["network"]
            result = {"permissions": granted, "scope": "turn"}
        elif method == "item/tool/requestUserInput":
            out = {}
            if accept and isinstance(answers, dict):
                for q in params.get("questions") or []:
                    value = answers.get(q.get("id"))
                    if isinstance(value, str):
                        value = [value]
                    if isinstance(value, list):
                        out[q["id"]] = {"answers": [str(v)[:4000] for v in value][:10]}
            result = {"answers": out}
        elif method == "mcpServer/elicitation/request":
            result = {"action": "accept" if accept else ("cancel" if decision == "cancel" else "decline")}
            if accept:
                result["content"] = answers if isinstance(answers, dict) else {}
        else:
            return
        self.adapter.respond(rpc_id, result)

    # ---- lifecycle
    def provider_resolved(self, request_id):
        """Codex reports that a request was settled elsewhere (for example the turn was interrupted)."""
        row = self.db.one("SELECT * FROM approvals WHERE provider_request_id = ? AND status = 'pending'", (str(request_id),))
        if row:
            with self._lock:
                self._live.pop(row["id"], None)
            self._resolve(self._shape(row), "cancelled", "Codex closed the request.")

    def expire_run(self, run_id, note):
        for row in self.db.all("SELECT * FROM approvals WHERE run_id = ? AND status = 'pending'", (run_id,)):
            with self._lock:
                self._live.pop(row["id"], None)
            self._resolve(self._shape(row), "expired", note)

    def expire_all(self, note):
        for row in self.db.all("SELECT * FROM approvals WHERE status = 'pending'"):
            with self._lock:
                live = self._live.pop(row["id"], None)
            if live and "callback" in live:
                with self._lock:
                    self._live[row["id"]] = live  # local hand-off approvals do not depend on Codex
                continue
            self._resolve(self._shape(row), "expired", note)
