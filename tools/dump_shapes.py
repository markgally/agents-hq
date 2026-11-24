"""Developer aid: print the shape of the main API responses, using the mock Codex app server.

Usage: py -3 tools/dump_shapes.py > shapes.txt
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from helpers import Harness  # noqa: E402


def shape(value, depth=0, limit=5):
    """Replace long strings and long lists so the structure stays readable."""
    if isinstance(value, dict):
        return {k: shape(v, depth + 1, limit) for k, v in value.items()}
    if isinstance(value, list):
        out = [shape(v, depth + 1, limit) for v in value[:2 if depth else limit]]
        if len(value) > len(out):
            out.append("... %d more" % (len(value) - len(out)))
        return out
    if isinstance(value, str) and len(value) > 70:
        return value[:67] + "..."
    return value


def show(title, value):
    print("\n===== %s =====" % title)
    print(json.dumps(shape(value), indent=1, ensure_ascii=True))


h = Harness()
try:
    a1, a2 = "agent-01", "agent-02"
    h.patch("/api/agents/" + a1, {"display_name": "JARVIS", "role": "Personal Assistant",
                                  "permissions": {"sandbox": "workspace-write"}})
    s, res = h.post("/api/agents/%s/messages" % a1, {"text": "Hello [write] please", "idempotency_key": "k1"})
    show("POST messages", res)
    h.wait_idle(a1)
    h.save_task(a2, title="Daily summary", prompt="Summarise [command] [approve]", in_batch=True)
    h.save_task("agent-03", title="Morning check", prompt="Check the folder",
                schedule={"recurrence": {"type": "daily", "time": "09:00"}})
    s, res = h.post("/api/run-everything")
    show("POST run-everything", res)
    h.wait(lambda: h.get("/api/approvals")[1]["pending"], message="approval")
    state = h.get("/api/state")[1]
    state["token"] = "(hidden)"
    show("GET /api/state (agent-02 awaiting approval)", state)
    show("GET /api/approvals", h.get("/api/approvals")[1])
    ap = h.get("/api/approvals")[1]["pending"][0]
    show("POST approval respond", h.post("/api/approvals/%s/respond" % ap["id"], {"decision": "accept"})[1])
    h.wait_idle(a2)
    show("GET agent", h.get("/api/agents/" + a2)[1])
    show("GET messages agent-01", h.get("/api/agents/%s/messages" % a1)[1])
    show("GET messages agent-02", h.get("/api/agents/%s/messages" % a2)[1])
    show("GET outputs", h.get("/api/outputs")[1])
    out = h.get("/api/outputs")[1]["outputs"]
    for o in out[:3]:
        show("GET output detail (%s)" % o.get("kind"), h.get("/api/outputs/" + o["id"])[1])
    show("GET history agent-02", h.get("/api/agents/%s/history" % a2)[1])
    show("GET log", h.get("/api/log?limit=6")[1])
    show("GET codex status", h.get("/api/codex/status")[1])
    show("GET codex threads", h.get("/api/codex/threads")[1])
    show("GET connectors", h.get("/api/connectors")[1])
    show("GET settings", h.get("/api/settings")[1])
    show("GET setup", h.get("/api/setup")[1])
    show("GET presets", h.get("/api/presets")[1])
    show("GET schedules", h.get("/api/schedules")[1])
    show("GET files", h.get("/api/agents/%s/files?q=" % a1)[1])
    show("POST check-folder", h.post("/api/settings/check-folder", {"path": h.workspace})[1])
    show("error example", h.post("/api/agents/%s/run" % "agent-07")[1])
finally:
    h.close()
