"""Live probe of the installed Codex app server. Prints what the server actually answers.

    py -3 tools/codex_probe.py            handshake, account, models, rate limits, thread count
    py -3 tools/codex_probe.py --turn     also start one thread in workspace/_probe and run one short turn

No credentials are read or printed. Thread previews and e-mail addresses are not printed.
"""
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent_hq import CLIENT_NAME, __version__  # noqa: E402
from agent_hq.codex import discovery  # noqa: E402
from agent_hq.codex.rpc import JsonRpcProcess, RpcError  # noqa: E402


def keys(obj):
    return sorted(obj.keys()) if isinstance(obj, dict) else type(obj).__name__


def main():
    found = discovery.find_codex()
    if not found:
        print("codex executable: NOT FOUND")
        return 2
    print("codex executable source:", found["source"])
    print("codex version:", discovery.read_version(found["path"]))

    seen = []
    done = threading.Event()
    server_requests = []

    def on_note(method, params):
        seen.append((method, params))
        if method == "turn/completed":
            done.set()

    def on_req(rid, method, params):
        server_requests.append((method, keys(params)))
        return False  # decline everything in the probe

    rpc = JsonRpcProcess([found["path"], "app-server", "--listen", "stdio://"],
                         on_notification=on_note, on_request=on_req).start()
    try:
        init = rpc.request("initialize", {"clientInfo": {"name": CLIENT_NAME, "title": "AGENTS HQ", "version": __version__}},
                           timeout=30)
        print("initialize ->", {k: (v if k != "codexHome" else "<path>") for k, v in init.items()})
        rpc.notify("initialized")

        def call(method, params=None, show=None):
            try:
                res = rpc.request(method, params, timeout=40)
            except RpcError as exc:
                print("%s -> ERROR code=%s kind=%s %s" % (method, exc.code, exc.kind, exc.message[:200]))
                return None
            print("%s -> %s" % (method, show(res) if show else keys(res)))
            return res

        call("account/read", {"refreshToken": False}, lambda r: {
            "requiresOpenaiAuth": r.get("requiresOpenaiAuth"),
            "accountType": (r.get("account") or {}).get("type"),
            "planType": (r.get("account") or {}).get("planType"),
            "hasEmail": bool((r.get("account") or {}).get("email")),
        })
        call("model/list", {}, lambda r: [
            {"id": m.get("id"), "model": m.get("model"), "displayName": m.get("displayName"),
             "isDefault": m.get("isDefault"), "hidden": m.get("hidden"),
             "defaultEffort": m.get("defaultReasoningEffort"),
             "efforts": [e.get("reasoningEffort") for e in m.get("supportedReasoningEfforts", [])]}
            for m in r.get("data", [])])
        call("account/rateLimits/read", None, lambda r: {
            "primary": (r.get("rateLimits") or {}).get("primary"),
            "secondary": (r.get("rateLimits") or {}).get("secondary"),
            "planType": (r.get("rateLimits") or {}).get("planType"),
            "reached": (r.get("rateLimits") or {}).get("rateLimitReachedType"),
        })
        call("thread/list", {"limit": 5}, lambda r: {
            "returned": len(r.get("data", [])), "hasMore": bool(r.get("nextCursor")),
            "sources": sorted({json.dumps(t.get("source")) for t in r.get("data", [])}),
            "originators": sorted({str(t.get("originator")) for t in r.get("data", [])}),
            "threadKeys": keys(r["data"][0]) if r.get("data") else None,
        })
        call("thread/loaded/list", {}, lambda r: {"loaded": len(r.get("data", []))})
        call("mcpServerStatus/list", {}, lambda r: {
            "servers": [{"name": s.get("name"), "keys": keys(s)} for s in r.get("data", [])][:10]})
        call("permissionProfile/list", {}, lambda r: r)
        call("windowsSandbox/readiness", None, lambda r: r)

        if "--resume" in sys.argv:
            thread_id = sys.argv[sys.argv.index("--resume") + 1]
            resumed = call("thread/resume", {"threadId": thread_id}, lambda r: {
                "threadId": r["thread"]["id"], "turns": len(r["thread"].get("turns", [])),
                "status": r["thread"].get("status"), "sandbox": r.get("sandbox"),
                "approvalPolicy": r.get("approvalPolicy"), "model": r.get("model")})
            if resumed:
                call("turn/start", {"threadId": thread_id, "input": [
                    {"type": "text", "text": "What exact phrase did you reply with in your previous message? Answer with only that phrase."}]},
                     lambda r: {"turnId": r["turn"]["id"], "status": r["turn"]["status"]})
                print("turn finished:", done.wait(120))
                final = [p["item"].get("text") for m, p in seen
                         if m == "item/completed" and p.get("item", {}).get("type") == "agentMessage"]
                print("completed agent text:", [repr((t or "")[:200]) for t in final])
            bogus = "00000000-0000-7000-8000-000000000000"
            call("thread/resume", {"threadId": bogus}, lambda r: "UNEXPECTED SUCCESS")
            if "--archive" in sys.argv:
                call("thread/archive", {"threadId": thread_id}, lambda r: "archived")

        if "--turn" in sys.argv:
            cwd = os.path.join(ROOT, "workspace", "_probe")
            os.makedirs(cwd, exist_ok=True)
            started = call("thread/start", {"cwd": cwd, "sandbox": "read-only", "approvalPolicy": "on-request",
                                            "developerInstructions": "You are a connectivity probe. Answer in one short line."},
                           lambda r: {"threadId": r["thread"]["id"], "model": r.get("model"),
                                      "modelProvider": r.get("modelProvider"), "sandbox": r.get("sandbox"),
                                      "approvalPolicy": r.get("approvalPolicy"), "reasoningEffort": r.get("reasoningEffort"),
                                      "threadStatus": r["thread"].get("status"), "source": r["thread"].get("source"),
                                      "originator": r["thread"].get("originator"), "ephemeral": r["thread"].get("ephemeral"),
                                      "hasPath": bool(r["thread"].get("path"))})
            if started:
                thread_id = started["thread"]["id"]
                t0 = time.time()
                turn = call("turn/start", {"threadId": thread_id,
                                           "input": [{"type": "text", "text": "Reply with exactly: AGENTS HQ probe OK"}]},
                            lambda r: {"turnId": r["turn"]["id"], "status": r["turn"]["status"]})
                if turn:
                    finished = done.wait(120)
                    print("turn finished:", finished, "seconds: %.1f" % (time.time() - t0))
                order = []
                for method, params in seen:
                    if not order or order[-1][0] != method:
                        order.append([method, 1])
                    else:
                        order[-1][1] += 1
                print("notification sequence:", ", ".join("%s x%d" % (m, n) for m, n in order))
                for method, params in seen:
                    if method in ("item/started", "item/completed"):
                        item = params.get("item", {})
                        print("  %s type=%s keys=%s" % (method, item.get("type"), keys(item)))
                    elif method == "turn/completed":
                        t = params.get("turn", {})
                        print("  turn/completed status=%s error=%s durationMs=%s items=%d" % (
                            t.get("status"), t.get("error"), t.get("durationMs"), len(t.get("items", []))))
                    elif method == "thread/tokenUsage/updated":
                        print("  tokenUsage keys=%s" % keys(params.get("tokenUsage")))
                    elif method == "thread/status/changed":
                        print("  thread status=%s" % json.dumps(params.get("status")))
                    elif method == "error":
                        print("  error=%s willRetry=%s" % (json.dumps(params.get("error"))[:300], params.get("willRetry")))
                text = "".join(p.get("delta", "") for m, p in seen if m == "item/agentMessage/delta")
                print("streamed agent text:", repr(text[:200]))
                final = [p["item"].get("text") for m, p in seen
                         if m == "item/completed" and p.get("item", {}).get("type") == "agentMessage"]
                print("completed agent text:", [repr((t or "")[:200]) for t in final])
                call("thread/read", {"threadId": thread_id, "includeTurns": True}, lambda r: {
                    "turns": len(r["thread"].get("turns", [])), "status": r["thread"].get("status"),
                    "name": r["thread"].get("name")})
                print("PROBE_THREAD_ID", thread_id)
        print("server->client requests seen:", server_requests)
        print("notification methods seen:", sorted({m for m, _ in seen}))
        print("malformed lines:", rpc.framer.malformed, "invalid messages:", rpc.invalid_messages)
    finally:
        rpc.close()
        tail = list(rpc.stderr_tail)[-8:]
        print("stderr lines captured: %d" % len(rpc.stderr_tail))
        for line in tail:
            print("  stderr:", line[:220])
    return 0


if __name__ == "__main__":
    sys.exit(main())
