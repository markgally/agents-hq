"""Developer aid: print the event stream for one mock run. Usage: py tools/debug_events.py "[command] hello" """
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.helpers import Harness  # noqa: E402

h = Harness()
try:
    sub = h.app.bus.subscribe()
    status, res = h.post("/api/agents/agent-02/messages", {"text": sys.argv[1] if len(sys.argv) > 1 else "hello"})
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            event = sub.queue.get(timeout=0.5)
        except Exception:
            if not h.app.execution.open_runs("agent-02"):
                break
            continue
        runtime = (event["payload"].get("runtime") or {})
        print("%-22s agent=%-9s status=%-10s activity=%-10s %s" % (
            event["type"], event["agent_id"], runtime.get("status", "-"), runtime.get("activity", "-"),
            (event["log"] or "")[:70]))
finally:
    h.close()
