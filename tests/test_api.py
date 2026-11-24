"""API surface: state snapshot, event replay, Bot Log, setup checks, settings, connectors, outputs."""
import json
import os
import threading
import time
import unittest
import urllib.request

from tests.helpers import Harness


class StateAndEventsTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def test_health(self):
        status, res = self.h.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(res["app"], "AGENTS HQ")
        self.assertTrue(res["database"]["ok"])
        self.assertNotIn("token", res)

    def test_state_snapshot_shape(self):
        status, state = self.h.get("/api/state")
        for key in ("app", "version", "token", "mock", "settings", "connection", "agents", "dependencies", "approvals",
                    "batch", "eligible", "skipped", "summary", "last_event_id", "sprites", "server_time"):
            self.assertIn(key, state)
        self.assertEqual(state["app"], "AGENTS HQ")
        self.assertEqual(state["settings"]["timezone"], "Asia/Manila")
        self.assertEqual(state["settings"]["concurrency"], 2)
        self.assertFalse(state["settings"]["collaboration_enabled"])
        self.assertEqual(state["dependencies"], [], "no wires by default")
        self.assertEqual(state["summary"]["total_agents"], 7)
        self.assertEqual(state["summary"]["idle_agents"], 7)
        self.assertEqual(state["eligible"], [])
        dump = json.dumps(state).lower()
        for gone in ("groq", "affiliate", "thumbnail", "tiktok", "youtube", "claude"):
            self.assertNotIn(gone, dump, "the old video workflow must not appear in state")

    def read_events(self, path, until, timeout=15):
        events = []
        req = urllib.request.Request(self.h.base + path)
        deadline = time.time() + timeout
        with urllib.request.urlopen(req, timeout=timeout) as res:
            event = {}
            for raw in res:
                line = raw.decode("utf-8").rstrip("\n")
                if line.startswith("id: "):
                    event["id"] = int(line[4:])
                elif line.startswith("event: "):
                    event["type"] = line[7:]
                elif line.startswith("data: "):
                    event["data"] = json.loads(line[6:])
                elif line == "" and event:
                    events.append(event)
                    if until(event) or time.time() > deadline:
                        break
                    event = {}
        return events

    def test_reconnecting_client_receives_missed_events_exactly_once(self):
        h = self.h
        first = h.app.bus.last_id()
        h.patch("/api/agents/agent-01", {"display_name": "JARVIS"})
        status, res = h.post("/api/agents/agent-01/messages", {"text": "hello"})
        h.wait_run(res["run"]["id"])
        events = self.read_events("/api/events?last_id=%d" % first, lambda e: e["type"] == "hello")
        ids = [e["id"] for e in events if e.get("id")]
        self.assertEqual(ids, sorted(set(ids)), "events are replayed in order without duplicates")
        self.assertGreater(len(ids), 3)
        self.assertTrue(all(i > first for i in ids))
        types = [e["type"] for e in events]
        for expected in ("agent.updated", "task.queued", "task.started", "thread.updated", "task.completed", "output.created"):
            self.assertIn(expected, types)
        self.assertEqual(types[-1], "hello")
        # Replaying from the newest id returns nothing old.
        events = self.read_events("/api/events?last_id=%d" % ids[-1], lambda e: e["type"] == "hello")
        self.assertEqual([e["type"] for e in events], ["hello"])
        # A fresh client (no id) gets no backlog: it loads /api/state instead.
        events = self.read_events("/api/events", lambda e: e["type"] == "hello")
        self.assertEqual([e["type"] for e in events], ["hello"])

    def test_live_status_events_follow_the_real_lifecycle(self):
        h = self.h
        seen = []
        ready = threading.Event()

        def until(event):
            if event["type"] == "hello":
                ready.set()
            seen.append(event)
            return event["type"] == "task.cancelled"

        t = threading.Thread(target=lambda: self.read_events("/api/events", until), daemon=True)
        t.start()
        self.assertTrue(ready.wait(10))
        h.patch("/api/agents/agent-02", {"allowed_tools": ["mock_tools"]})
        del seen[:]
        status, res = h.post("/api/agents/agent-02/messages", {"text": "[mcp] work"})
        h.wait(lambda: h.runtime("agent-02")["status"] == "tool", message="tool use")
        h.post("/api/agents/agent-02/interrupt")
        t.join(15)
        # Every event that carries `payload.runtime` is the agent's current state; the dashboard applies each one.
        statuses = [e["data"]["payload"]["runtime"]["status"] for e in seen
                    if e["data"].get("agent_id") == "agent-02" and "runtime" in e["data"]["payload"]]
        self.assertIn("queued", statuses)
        self.assertIn("running", statuses)
        self.assertIn("cancelling", statuses)
        self.assertNotIn("completed", [e["type"].split(".")[-1] for e in seen if e["type"].startswith("task.")],
                         "an interrupted task must never be announced as completed")
        self.assertIn("tool", statuses, "using an integration is reported as tool use")
        other = [e for e in seen if "runtime" in e["data"]["payload"] and e["data"].get("agent_id") != "agent-02"]
        self.assertEqual(other, [], "other agents' states do not change")

    def test_bot_log_filters_and_persistence(self):
        h = self.h
        h.save_task("agent-01", title="Good", prompt="ok")
        h.save_task("agent-02", title="Bad", prompt="[fail] no")
        for agent_id in ("agent-01", "agent-02"):
            s, r = h.post("/api/agents/%s/run" % agent_id)
            h.wait_run(r["run"]["id"])
        s, r = h.post("/api/agents/agent-03/messages", {"text": "[approve] please"})
        h.wait(lambda: h.app.approvals.pending(), message="approval")
        status, res = h.get("/api/log")
        entries = res["entries"]
        self.assertTrue(entries)
        text = " | ".join(e["log"] for e in entries)
        self.assertIn("Agent 1 completed task: Good", text)
        self.assertIn("Agent 2 failed task: Bad", text)
        self.assertEqual([e["id"] for e in entries], sorted(e["id"] for e in entries))
        by = lambda cat: [e["log"] for e in h.get("/api/log?category=%s" % cat)[1]["entries"]]
        self.assertTrue(all("fail" in line.lower() or "error" in line.lower() for line in by("error")))
        self.assertTrue(any("completed" in line for line in by("completed")))
        self.assertTrue(any("approval" in line.lower() for line in by("approval")))
        self.assertTrue(all("completed" not in line for line in by("working")))
        only = h.get("/api/log?agent_id=agent-02")[1]["entries"]
        self.assertTrue(only and all(e["agent_id"] == "agent-02" for e in only))
        self.assertEqual(h.get("/api/log?category=nonsense")[0], 400)
        approval = h.app.approvals.pending()[0]
        h.post("/api/approvals/%s/respond" % approval["id"], {"decision": "decline"})
        h.wait_run(r["run"]["id"])
        # No idle chatter is ever written to the log.
        for line in (e["log"] for e in h.get("/api/log")[1]["entries"]):
            for chatter in ("Coffee break", "arcade", "hide-and-seek", "Anyone have a new task"):
                self.assertNotIn(chatter, line)

    def test_command_center_summary_counts_real_runs(self):
        h = self.h
        h.save_task("agent-01", title="Good", prompt="ok")
        h.save_task("agent-02", title="Bad", prompt="[fail] no")
        h.save_task("agent-03", title="Later", prompt="later", schedule={"recurrence": {"type": "daily", "time": "09:00"}})
        for agent_id in ("agent-01", "agent-02"):
            s, r = h.post("/api/agents/%s/run" % agent_id)
            h.wait_run(r["run"]["id"])
        s, slow = h.post("/api/agents/agent-04/messages", {"text": "[slow] busy"})
        h.wait(lambda: h.run_status(slow["run"]["id"]) == "running", message="running")
        summary = h.get("/api/state")[1]["summary"]
        self.assertEqual((summary["total_agents"], summary["working_agents"], summary["idle_agents"]), (7, 1, 6))
        self.assertEqual((summary["completed_tasks"], summary["failed_tasks"], summary["queued_tasks"]), (1, 1, 0))
        self.assertEqual(summary["pending_approvals"], 0)
        self.assertEqual(summary["next_scheduled"]["agent_id"], "agent-03")
        h.post("/api/agents/agent-04/interrupt")
        h.wait_run(slow["run"]["id"])


class SetupAndSettingsTests(unittest.TestCase):
    def test_setup_cannot_finish_without_real_prerequisites(self):
        h = Harness(connect=False)
        try:
            status, res = h.get("/api/setup")
            checks = {c["id"]: c["ok"] for c in res["checks"]}
            self.assertFalse(res["ready"])
            self.assertFalse(checks["codex_connected"])
            self.assertFalse(checks["codex_signed_in"])
            self.assertTrue(checks["workspace"])
            self.assertTrue(checks["outputs"])
            self.assertTrue(checks["agents"])
            self.assertTrue(checks["database"])
            status, res = h.post("/api/setup/finish")
            self.assertEqual(status, 409)
            self.assertEqual(res["error"]["code"], "setup_incomplete")
            self.assertFalse(h.app.settings.get("setup_complete"))
            # The office stays usable while disconnected.
            self.assertEqual(h.get("/api/state")[0], 200)
            self.assertEqual(h.patch("/api/agents/agent-01", {"display_name": "Offline edit"})[0], 200)

            h.post("/api/codex/connect")
            status, res = h.post("/api/setup/finish")
            self.assertEqual(status, 200, res)
            self.assertTrue(res["setup_complete"])
            self.assertTrue(h.get("/api/state")[1]["settings"]["setup_complete"])
        finally:
            h.close()

    def test_setup_blocks_when_not_signed_in(self):
        h = Harness(auth="none", connect=False)
        try:
            h.post("/api/codex/connect")
            status, res = h.get("/api/setup")
            checks = {c["id"]: c["ok"] for c in res["checks"]}
            self.assertTrue(checks["codex_connected"])
            self.assertFalse(checks["codex_signed_in"])
            self.assertEqual(h.post("/api/setup/finish")[0], 409)
        finally:
            h.close()

    def test_settings_validation_and_folder_checks(self):
        h = Harness()
        try:
            for bad in ({"timezone": "Nowhere/None"}, {"default_timeout_sec": 5}, {"max_retries": 3},
                        {"approval_default": "always-yes"}, {"missed_policy_default": "maybe"},
                        {"overlap_policy_default": "pile-up"}, {"no_such_setting": 1},
                        {"max_delegation_depth": 99}, {"default_workspace": os.path.join(h.tmp, "data")}):
                status, res = h.patch("/api/settings", bad)
                self.assertEqual(status, 400, bad)
            status, res = h.patch("/api/settings", {"tutorial_seen": True, "concurrency": 3, "timezone": "UTC"})
            self.assertEqual(status, 200, res)
            self.assertEqual((res["settings"]["tutorial_seen"], res["settings"]["concurrency"], res["settings"]["timezone"]),
                             (True, 3, "UTC"))

            new = os.path.join(h.tmp, "new-workspace")
            status, res = h.post("/api/settings/check-folder", {"path": new})
            self.assertEqual(status, 400, "a missing folder is reported, not silently created")
            self.assertFalse(os.path.exists(new))
            status, res = h.post("/api/settings/check-folder", {"path": new, "create": True})
            self.assertEqual(status, 200, res)
            self.assertTrue(res["folder"]["created"] and res["folder"]["readable"] and res["folder"]["writable"])
            self.assertFalse(res["folder"]["inside_permitted"])
            self.assertEqual(os.listdir(new), [], "the write test leaves nothing behind")
            for bad in (os.path.join(h.tmp, "data", "sneaky"), os.path.join(h.tmp, "a", "b", "c"), "relative\\path", ""):
                status, res = h.post("/api/settings/check-folder", {"path": bad, "create": True})
                self.assertEqual(status, 400, bad)
            self.assertFalse(os.path.exists(os.path.join(h.tmp, "data", "sneaky")))
            self.assertFalse(os.path.exists(os.path.join(h.tmp, "a")))
            status, res = h.patch("/api/settings", {"allowed_roots": [h.workspace, new]})
            self.assertEqual(status, 400, "the output folder cannot be left outside the permitted folders")
            status, res = h.patch("/api/settings", {"allowed_roots": [h.workspace, h.outputs, new]})
            self.assertEqual(status, 200, res)
            status, res = h.patch("/api/agents/agent-01", {"working_directory": new})
            self.assertEqual(status, 200, res)
        finally:
            h.close()

    def test_connectors_report_true_status(self):
        h = Harness(connect=False)
        try:
            status, res = h.get("/api/connectors")
            self.assertFalse(res["available"])
            by_name = {i["name"]: i for i in res["items"]}
            self.assertEqual(by_name["Gmail"]["status"], "unsupported")
            self.assertEqual(by_name["Local files"]["status"], "connected")
            h.post("/api/codex/connect")
            status, res = h.get("/api/connectors")
            self.assertTrue(res["available"])
            by_name = {i["name"]: i for i in res["items"]}
            self.assertEqual(by_name["Mock tools"]["status"], "connected")
            self.assertEqual(by_name["Mock needs login"]["status"], "configuration_required")
            self.assertEqual(by_name["WhatsApp"]["status"], "unsupported")
            self.assertNotIn("connected", [i["status"] for i in res["items"] if i["source"] == "not built in"])
        finally:
            h.close()

    def test_disconnect_with_active_work_needs_confirmation_and_is_honest(self):
        h = Harness()
        try:
            h.app.settings.set("auto_connect", False)
            s, r = h.post("/api/agents/agent-01/messages", {"text": "[slow] busy"})
            h.wait(lambda: h.run_status(r["run"]["id"]) == "running", message="running")
            status, res = h.post("/api/codex/disconnect")
            self.assertEqual(status, 409)
            self.assertEqual(res["error"]["code"], "confirmation_required")
            self.assertEqual(res["error"]["details"]["active"], 1)
            self.assertEqual(h.run_status(r["run"]["id"]), "running", "nothing is stopped without confirmation")
            status, res = h.post("/api/codex/disconnect", {"confirm": True})
            self.assertEqual(status, 200, res)
            self.assertEqual(res["codex"]["state"], "disconnected")
            run = h.wait_run(r["run"]["id"])
            self.assertIn(run["status"], ("interrupted", "unknown"))
            self.assertNotEqual(run["status"], "completed")
        finally:
            h.close()


class OutputsApiTests(unittest.TestCase):
    def test_aggregate_outputs_view_and_filters(self):
        h = Harness()
        try:
            h.save_task("agent-01", title="Alpha report", prompt="alpha")
            h.save_task("agent-02", title="Beta report", prompt="beta")
            for agent_id in ("agent-01", "agent-02"):
                s, r = h.post("/api/agents/%s/run" % agent_id)
                h.wait_run(r["run"]["id"])
            s, r = h.post("/api/agents/agent-01/messages", {"text": "chat answer"})
            h.wait_run(r["run"]["id"])
            status, res = h.get("/api/outputs")
            self.assertEqual(len(res["outputs"]), 3)
            self.assertEqual(len(h.get("/api/outputs?agent_id=agent-02")[1]["outputs"]), 1)
            self.assertEqual(len(h.get("/api/outputs?q=alpha")[1]["outputs"]), 1)
            self.assertEqual(len(h.get("/api/outputs?date_from=2099-01-01")[1]["outputs"]), 0)
            self.assertEqual(h.get("/api/outputs?agent_id=agent-99")[0], 400)
            chat = [o for o in res["outputs"] if o["run_kind"] == "chat"][0]
            self.assertIsNone(chat["file_path"], "a chat answer has no file, and none is invented")
            detail = h.get("/api/outputs/%s" % chat["id"])[1]["output"]
            self.assertTrue(detail["content"].startswith("MOCK reply"))
            self.assertEqual(h.post("/api/outputs/%s/reveal" % chat["id"])[0], 409)
            today = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 8 * 3600))  # today's date in Manila
            self.assertEqual(len(h.get("/api/outputs?date_from=%s&date_to=%s" % (today, today))[1]["outputs"]), 3)
            self.assertEqual(h.get("/api/outputs?date_from=yesterday")[0], 400)
            # Open file / open folder act on the verified report file only.
            report = [o for o in res["outputs"] if o["run_title"] == "Alpha report"][0]
            self.assertEqual(h.post("/api/outputs/%s/open" % report["id"])[0], 200)
            self.assertEqual(h.post("/api/outputs/%s/reveal" % report["id"])[0], 200)
            self.assertEqual([k for k, p in h.launched], ["open", "reveal"])
            self.assertTrue(all(os.path.realpath(p) == os.path.realpath(report["file_path"]) for k, p in h.launched))
            # A program or script is never launched, even from inside the workspace.
            script = os.path.join(h.outputs, "agent-01", "run-me.bat")
            with open(script, "w") as fh:
                fh.write("echo no")
            h.app.db.execute("UPDATE outputs SET verified_file_path = ? WHERE id = ?", (script, report["id"]))
            status, res = h.post("/api/outputs/%s/open" % report["id"])
            self.assertEqual((status, res["error"]["code"]), (409, "unsafe_type"))
            self.assertEqual(len(h.launched), 2)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
