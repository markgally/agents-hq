"""Mock Codex app server for automated tests and the explicitly labelled test mode.

It speaks the same newline-delimited JSON-RPC protocol over stdio as `codex app-server`, covering the
methods AGENTS HQ uses. It performs no AI inference: every reply starts with "MOCK" and AGENTS HQ labels the
connection as a mock in the user interface. It is never used by the normal application.

Behaviour is driven by markers inside the prompt text:
  [slow]      pause mid-turn (so a test can interrupt)
  [approve]   ask for command approval before continuing
  [fail]      end the turn with status "failed"
  [ratelimit] fail with usageLimitExceeded
  [overload]  fail once with serverOverloaded, succeed on the next attempt
  [write]     create a file in the working folder and report a fileChange item
  [command]   report a commandExecution item
  [crash]     exit the process in the middle of the turn
  [garbage]   emit a malformed line before the reply
  [split]     emit one message in two separate writes

Environment:
  MOCK_CODEX_STATE   folder for persisted thread data (default: a temp folder per process)
  MOCK_CODEX_AUTH    "none" to report a signed-out account
  MOCK_CODEX_DELAY   seconds between streamed chunks (default 0.02)
"""
import json
import os
import sys
import tempfile
import threading
import time
import uuid

STATE_DIR = os.environ.get("MOCK_CODEX_STATE") or tempfile.mkdtemp(prefix="mock-codex-")
AUTH = os.environ.get("MOCK_CODEX_AUTH", "chatgpt")
DELAY = float(os.environ.get("MOCK_CODEX_DELAY", "0.02"))
STATE_FILE = os.path.join(STATE_DIR, "threads.json")

_out_lock = threading.Lock()
_state_lock = threading.Lock()
_pending = {}          # server->client request id -> {"event", "result"}
_turns = {}            # turn id -> {"interrupt": Event, "thread": id, "steer": [text]}
_overloaded_once = set()
_next_request = [0]


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"threads": {}}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE_FILE)


def write_raw(text):
    with _out_lock:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()


def send(obj):
    write_raw(json.dumps(obj, separators=(",", ":")) + "\n")


def notify(method, params):
    send({"method": method, "params": params})


def ask_client(method, params, timeout=600):
    with _state_lock:
        _next_request[0] += 1
        rid = "srv-%d" % _next_request[0]
        slot = {"event": threading.Event(), "result": None}
        _pending[rid] = slot
    send({"id": rid, "method": method, "params": params})
    slot["event"].wait(timeout)
    return slot["result"]


def thread_view(tid, record, include_turns=False):
    return {"id": tid, "name": record.get("name"), "preview": record.get("preview", ""), "cwd": record.get("cwd") or os.getcwd(),
            "createdAt": record.get("createdAt"), "updatedAt": record.get("updatedAt"), "cliVersion": "mock",
            "ephemeral": False, "modelProvider": "mock", "model": "mock-model", "originator": record.get("originator", "agent_hq"),
            "projectId": None, "sessionId": tid, "source": "vscode", "status": {"type": "idle"},
            "path": os.path.join(STATE_DIR, tid + ".jsonl"),
            "turns": record.get("turns", []) if include_turns else []}


def now_ms():
    return int(time.time() * 1000)


def run_turn(thread_id, turn_id, text, cwd):
    ctl = _turns[turn_id]
    items = []

    def interrupted():
        return ctl["interrupt"].is_set()

    def finish(status, error=None):
        turn = {"id": turn_id, "status": status, "items": [], "error": error, "itemsView": "notLoaded",
                "startedAt": ctl["started"], "completedAt": int(time.time()), "durationMs": now_ms() - ctl["started_ms"]}
        with _state_lock:
            state = load_state()
            record = state["threads"].get(thread_id)
            if record is not None:
                record.setdefault("turns", []).append(dict(turn, items=items, itemsView="full"))
                record["updatedAt"] = int(time.time())
                record["preview"] = record.get("preview") or text[:80]
                save_state(state)
        notify("thread/status/changed", {"threadId": thread_id, "status": {"type": "idle"}})
        notify("turn/completed", {"threadId": thread_id, "turn": turn})
        _turns.pop(turn_id, None)

    def item(obj, deltas=None):
        notify("item/started", {"threadId": thread_id, "turnId": turn_id, "startedAtMs": now_ms(), "item": dict(obj)})
        if deltas:
            for method, payload in deltas:
                if interrupted():
                    break
                time.sleep(DELAY)
                notify(method, dict(payload, threadId=thread_id, turnId=turn_id, itemId=obj["id"]))
        notify("item/completed", {"threadId": thread_id, "turnId": turn_id, "completedAtMs": now_ms(), "item": dict(obj)})
        items.append(dict(obj))

    notify("thread/status/changed", {"threadId": thread_id, "status": {"type": "active", "activeFlags": []}})
    notify("turn/started", {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress", "items": [],
                                                           "itemsView": "notLoaded"}})
    item({"type": "userMessage", "id": "item-" + uuid.uuid4().hex[:8], "clientId": None,
          "content": [{"type": "text", "text": text}]})

    if "[garbage]" in text:
        write_raw("this is not json\n{\"broken\": \n")

    if "[slow]" in text:
        for _ in range(int(os.environ.get("MOCK_CODEX_SLOW_STEPS", "150"))):
            if interrupted():
                break
            time.sleep(0.04)

    if "[crash]" in text:
        time.sleep(0.2)
        os._exit(3)

    if interrupted():
        return finish("interrupted")

    if "[fail]" in text:
        err = {"message": "MOCK failure requested by the test prompt.", "codexErrorInfo": "other", "additionalDetails": None}
        notify("error", {"threadId": thread_id, "turnId": turn_id, "willRetry": False, "error": err})
        return finish("failed", err)

    if "[ratelimit]" in text:
        err = {"message": "MOCK usage limit reached.", "codexErrorInfo": "usageLimitExceeded", "additionalDetails": None}
        notify("error", {"threadId": thread_id, "turnId": turn_id, "willRetry": False, "error": err})
        return finish("failed", err)

    if "[overload]" in text and thread_id not in _overloaded_once:
        _overloaded_once.add(thread_id)
        err = {"message": "MOCK server overloaded.", "codexErrorInfo": "serverOverloaded", "additionalDetails": None}
        notify("error", {"threadId": thread_id, "turnId": turn_id, "willRetry": False, "error": err})
        return finish("failed", err)

    decision = None
    if "[approve]" in text:
        cmd_id = "item-" + uuid.uuid4().hex[:8]
        command = "echo mock-approved-command"
        notify("item/started", {"threadId": thread_id, "turnId": turn_id, "startedAtMs": now_ms(), "item": {
            "type": "commandExecution", "id": cmd_id, "command": command, "cwd": cwd, "status": "inProgress",
            "commandActions": [{"type": "unknown", "command": command}], "source": "agent",
            "aggregatedOutput": None, "exitCode": None, "durationMs": None}})
        result = ask_client("item/commandExecution/requestApproval", {
            "threadId": thread_id, "turnId": turn_id, "itemId": cmd_id, "startedAtMs": now_ms(),
            "command": command, "cwd": cwd, "reason": "MOCK: the test prompt asked for an approval."})
        decision = (result or {}).get("decision") if isinstance(result, dict) else None
        accepted = decision in ("accept", "acceptForSession")
        done = {"type": "commandExecution", "id": cmd_id, "command": command, "cwd": cwd,
                "status": "completed" if accepted else "declined", "commandActions": [{"type": "unknown", "command": command}],
                "source": "agent", "aggregatedOutput": "mock-approved-command\n" if accepted else None,
                "exitCode": 0 if accepted else None, "durationMs": 5}
        notify("item/completed", {"threadId": thread_id, "turnId": turn_id, "completedAtMs": now_ms(), "item": done})
        items.append(done)
        if decision == "cancel" or interrupted():
            return finish("interrupted")

    if "[command]" in text:
        cmd_id = "item-" + uuid.uuid4().hex[:8]
        base = {"type": "commandExecution", "id": cmd_id, "command": "dir", "cwd": cwd, "source": "agent",
                "commandActions": [{"type": "listFiles", "command": "dir", "path": cwd}]}
        notify("item/started", {"threadId": thread_id, "turnId": turn_id, "startedAtMs": now_ms(),
                                "item": dict(base, status="inProgress", aggregatedOutput=None, exitCode=None, durationMs=None)})
        notify("item/commandExecution/outputDelta", {"threadId": thread_id, "turnId": turn_id, "itemId": cmd_id,
                                                     "delta": "mock listing line 1\nmock listing line 2\n"})
        done = dict(base, status="completed", aggregatedOutput="mock listing line 1\nmock listing line 2\n", exitCode=0, durationMs=12)
        notify("item/completed", {"threadId": thread_id, "turnId": turn_id, "completedAtMs": now_ms(), "item": done})
        items.append(done)

    if "[mcp]" in text:
        call_id = "item-" + uuid.uuid4().hex[:8]
        base = {"type": "mcpToolCall", "id": call_id, "server": "mock_tools", "tool": "lookup",
                "arguments": {"query": "mock"}, "result": None, "error": None}
        notify("item/started", {"threadId": thread_id, "turnId": turn_id, "startedAtMs": now_ms(),
                                "item": dict(base, status="inProgress", durationMs=None)})
        for _ in range(25):  # a tool call takes a moment; the client may interrupt it
            if interrupted():
                break
            time.sleep(0.04)
        stopped = interrupted()
        done = dict(base, status="failed" if stopped else "completed", durationMs=1000,
                    result=None if stopped else {"content": [{"type": "text", "text": "MOCK tool result"}]})
        notify("item/completed", {"threadId": thread_id, "turnId": turn_id, "completedAtMs": now_ms(), "item": done})
        items.append(done)
        if stopped:
            return finish("interrupted")

    if "[write]" in text:
        path = os.path.join(cwd, "mock-output-%s.txt" % uuid.uuid4().hex[:6])
        status = "completed"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("MOCK file written by the mock Codex app server.\n")
        except OSError:
            status = "failed"
        item({"type": "fileChange", "id": "item-" + uuid.uuid4().hex[:8], "status": status,
              "changes": [{"path": path, "kind": {"type": "add"}, "diff": "+MOCK file written by the mock Codex app server.\n"}]})

    reply = "MOCK reply (no AI was used). You said: %s" % text.replace("\n", " ")[:160]
    if decision is not None:
        reply += " | approval decision: %s" % decision
    if ctl["steer"]:
        reply += " | steered with: %s" % " / ".join(ctl["steer"])
    msg_id = "item-" + uuid.uuid4().hex[:8]
    base = {"type": "agentMessage", "id": msg_id, "phase": "final_answer", "delivery": None, "memoryCitation": None,
            "moderation": None, "questions": None}
    notify("item/started", {"threadId": thread_id, "turnId": turn_id, "startedAtMs": now_ms(), "item": dict(base, text="")})
    words = reply.split(" ")
    for index, word in enumerate(words):
        if interrupted():
            return finish("interrupted")
        time.sleep(DELAY)
        payload = json.dumps({"method": "item/agentMessage/delta",
                              "params": {"threadId": thread_id, "turnId": turn_id, "itemId": msg_id,
                                         "delta": word + (" " if index < len(words) - 1 else "")}}, separators=(",", ":")) + "\n"
        if "[split]" in text and index == 0:
            half = len(payload) // 2
            write_raw(payload[:half])
            time.sleep(0.05)
            write_raw(payload[half:])
        else:
            write_raw(payload)
    done = dict(base, text=reply)
    notify("item/completed", {"threadId": thread_id, "turnId": turn_id, "completedAtMs": now_ms(), "item": done})
    items.append(done)
    usage = {"inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 0, "reasoningOutputTokens": 0, "totalTokens": 0}
    notify("thread/tokenUsage/updated", {"threadId": thread_id, "turnId": turn_id,
                                         "tokenUsage": {"last": usage, "total": usage, "modelContextWindow": None}})
    finish("completed")


def handle(msg):
    rid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method is None:  # a response to one of our requests
        slot = _pending.pop(rid, None)
        if slot:
            slot["result"] = msg.get("result") if "result" in msg else {"error": msg.get("error")}
            slot["event"].set()
        return

    def ok(result):
        send({"id": rid, "result": result})

    def err(code, message):
        send({"id": rid, "error": {"code": code, "message": message}})

    if method == "initialized":
        return
    if method == "initialize":
        return ok({"userAgent": "mock-codex/0.0 (test)", "codexHome": STATE_DIR, "platformFamily": "mock", "platformOs": "mock"})
    if method == "account/read":
        if AUTH == "none":
            return ok({"account": None, "requiresOpenaiAuth": True})
        return ok({"account": {"type": "chatgpt", "email": None, "planType": "mock", "workspaceName": None},
                   "requiresOpenaiAuth": True, "userId": "mock-user"})
    if method == "model/list":
        return ok({"data": [
            {"id": "mock-model", "model": "mock-model", "displayName": "Mock Model", "description": "Test model, no AI.",
             "hidden": False, "isDefault": True, "defaultReasoningEffort": "medium",
             "supportedReasoningEfforts": [{"reasoningEffort": "low", "description": ""}, {"reasoningEffort": "medium", "description": ""}]},
            {"id": "mock-model-2", "model": "mock-model-2", "displayName": "Mock Model 2", "description": "Second test model.",
             "hidden": False, "isDefault": False, "defaultReasoningEffort": "low",
             "supportedReasoningEfforts": [{"reasoningEffort": "low", "description": ""}]}], "nextCursor": None})
    if method == "account/rateLimits/read":
        return ok({"rateLimits": {"primary": {"usedPercent": 1, "windowDurationMins": 300, "resetsAt": int(time.time()) + 3600},
                                  "secondary": None, "planType": "mock", "rateLimitReachedType": None}})
    if method == "mcpServerStatus/list":
        return ok({"data": [{"name": "mock_tools", "authStatus": "unsupported", "runtimeStatus": "connected",
                             "resources": [], "resourceTemplates": [], "tools": {"echo": {}}, "toolsError": None,
                             "serverInfo": {"name": "mock_tools", "title": "Mock tools", "version": "0"}},
                            {"name": "mock_needs_login", "authStatus": "notLoggedIn",
                             "runtimeStatus": "authenticationRequired", "resources": [], "resourceTemplates": [],
                             "tools": {}, "toolsError": None,
                             "serverInfo": {"name": "mock_needs_login", "title": "Mock needs login", "version": "0"}}],
                   "nextCursor": None})
    if method == "thread/start":
        tid = str(uuid.uuid4())
        with _state_lock:
            state = load_state()
            state["threads"][tid] = {"cwd": params.get("cwd"), "createdAt": int(time.time()), "updatedAt": int(time.time()),
                                     "turns": [], "name": None, "preview": "",
                                     "developerInstructions": params.get("developerInstructions")}
            save_state(state)
            record = state["threads"][tid]
        notify("thread/started", {"thread": thread_view(tid, record)})
        return ok({"thread": thread_view(tid, record), "model": "mock-model", "modelProvider": "mock",
                   "cwd": params.get("cwd") or os.getcwd(), "approvalPolicy": params.get("approvalPolicy") or "on-request",
                   "approvalsReviewer": "user", "sandbox": {"type": "readOnly", "networkAccess": False},
                   "reasoningEffort": None, "disabledPluginIds": [], "instructionSources": []})
    if method in ("thread/resume", "thread/read", "thread/archive", "thread/name/set"):
        tid = params.get("threadId")
        with _state_lock:
            state = load_state()
            record = state["threads"].get(tid)
            if record is None or (record.get("archived") and method == "thread/resume"):
                return err(-32600, "no rollout found for thread id %s" % tid)
            if method == "thread/archive":
                record["archived"] = True
                save_state(state)
            if method == "thread/name/set":
                record["name"] = params.get("name")
                save_state(state)
        if method in ("thread/archive", "thread/name/set"):
            return ok({})
        if method == "thread/read":
            return ok({"thread": thread_view(tid, record, bool(params.get("includeTurns")))})
        return ok({"thread": thread_view(tid, record, True), "model": "mock-model", "modelProvider": "mock",
                   "cwd": record.get("cwd") or os.getcwd(), "approvalPolicy": "on-request", "approvalsReviewer": "user",
                   "sandbox": {"type": "readOnly", "networkAccess": False}, "reasoningEffort": None,
                   "disabledPluginIds": [], "instructionSources": []})
    if method == "thread/list":
        with _state_lock:
            state = load_state()
        data = [thread_view(tid, rec) for tid, rec in state["threads"].items() if not rec.get("archived")]
        data.sort(key=lambda t: t.get("updatedAt") or 0, reverse=True)
        return ok({"data": data[:int(params.get("limit") or 40)], "nextCursor": None})
    if method == "turn/start":
        tid = params.get("threadId")
        with _state_lock:
            if tid not in load_state()["threads"]:
                return err(-32600, "thread not found: %s" % tid)
            if any(t["thread"] == tid for t in _turns.values()):
                return err(-32600, "a turn is already in progress for this thread")
            turn_id = str(uuid.uuid4())
            _turns[turn_id] = {"interrupt": threading.Event(), "thread": tid, "steer": [],
                               "started": int(time.time()), "started_ms": now_ms()}
        text = " ".join(i.get("text", "") for i in params.get("input", []) if i.get("type") == "text")
        cwd = params.get("cwd") or os.getcwd()
        ok({"turn": {"id": turn_id, "status": "inProgress", "items": [], "itemsView": "notLoaded"}})
        threading.Thread(target=run_turn, args=(tid, turn_id, text, cwd), daemon=True).start()
        return
    if method == "turn/interrupt":
        ctl = _turns.get(params.get("turnId"))
        if ctl:
            ctl["interrupt"].set()
        for slot in list(_pending.values()):
            slot["result"] = {"decision": "cancel"}
            slot["event"].set()
        return ok({})
    if method == "turn/steer":
        ctl = _turns.get(params.get("expectedTurnId"))
        if not ctl:
            return err(-32600, "no active turn to steer")
        ctl["steer"].append(" ".join(i.get("text", "") for i in params.get("input", []) if i.get("type") == "text"))
        return ok({"turnId": params.get("expectedTurnId")})
    if rid is not None:
        return err(-32601, "Method not found: %s" % method)


def main():
    for raw in sys.stdin.buffer:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        if isinstance(msg, dict):
            try:
                handle(msg)
            except Exception as exc:  # keep serving; report through JSON-RPC when possible
                if msg.get("id") is not None and msg.get("method"):
                    send({"id": msg["id"], "error": {"code": -32603, "message": "mock server error: %s" % exc}})


if __name__ == "__main__":
    main()
