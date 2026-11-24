"""Codex integration against the mock app server (same JSON-RPC protocol over stdio)."""
import json
import os
import sys
import threading
import time
import unittest
import urllib.request

from tests.helpers import Harness, MOCK
from agent_hq.codex import discovery


class DiscoveryTests(unittest.TestCase):
    def test_saved_path_wins(self):
        found = discovery.find_codex(sys.executable)
        self.assertEqual(found, {"path": sys.executable, "source": "saved setting"})

    def test_missing_saved_path_is_ignored(self):
        found = discovery.find_codex(os.path.join(os.path.dirname(__file__), "no-such-codex.exe"))
        self.assertTrue(found is None or found["source"] != "saved setting")

    def test_version_parsing(self):
        self.assertRegex(discovery.read_version(sys.executable) or "", r"^\d+\.\d+")


class ConnectionTests(unittest.TestCase):
    def test_connect_reports_real_status(self):
        h = Harness(connect=False)
        try:
            status, res = h.get("/api/codex/status")
            self.assertEqual(res["codex"]["state"], "disconnected")
            self.assertFalse(res["codex"]["signed_in"])
            status, res = h.post("/api/codex/connect")
            self.assertEqual(status, 200, res)
            codex = res["codex"]
            self.assertEqual(codex["state"], "connected")
            self.assertTrue(codex["mock"], "the mock must always be labelled as a mock")
            self.assertIn("Mock", codex["provider"])
            self.assertEqual(codex["account"], {"type": "chatgpt", "plan": "mock"})
            self.assertEqual(codex["default_model"], "mock-model")
            self.assertEqual(len(codex["threads"]), 7)
            self.assertTrue(all(t["status"] == "uninitialized" for t in codex["threads"]))
            self.assertEqual(codex["inference_requests"], 0, "connecting must not run any model request")
            status, res = h.post("/api/codex/test")
            self.assertTrue(res["test"]["ok"])
            self.assertEqual(res["codex"]["inference_requests"], 0)
        finally:
            h.close()

    def test_authentication_failure_is_reported(self):
        h = Harness(auth="none", connect=False)
        try:
            status, res = h.post("/api/codex/connect")
            self.assertEqual(res["codex"]["state"], "auth_required")
            self.assertFalse(res["codex"]["signed_in"])
            status, res = h.post("/api/agents/agent-01/messages", {"text": "hello"})
            self.assertEqual(status, 409)
            self.assertEqual(res["error"]["code"], "auth_required")
            self.assertEqual(h.app.adapter.inference_requests, 0)
        finally:
            h.close()

    def test_missing_executable_is_an_error_state(self):
        h = Harness(connect=False, codex_command=[os.path.join(os.path.dirname(__file__), "no-such-binary.exe")])
        try:
            status, res = h.post("/api/codex/connect")
            self.assertEqual(res["codex"]["state"], "error")
            self.assertTrue(res["codex"]["last_error"])
            status, res = h.post("/api/agents/agent-01/messages", {"text": "hello"})
            self.assertEqual(status, 409)
            self.assertEqual(res["error"]["code"], "not_connected")
        finally:
            h.close()

    def test_unsupported_capability_is_refused_clearly(self):
        h = Harness()
        try:
            h.app.adapter.capabilities["turn/steer"] = False
            h.app.adapter.capabilities["thread/list"] = False
            status, res = h.post("/api/agents/agent-01/messages", {"text": "x", "mode": "steer"})
            self.assertEqual(status, 409)
            self.assertEqual(res["error"]["code"], "unsupported")
            status, res = h.get("/api/codex/threads")
            self.assertEqual(status, 409)
            self.assertEqual(res["error"]["code"], "unsupported")
        finally:
            h.close()

    def test_method_not_found_marks_capability_unsupported(self):
        h = Harness()
        try:
            h.app.adapter.capabilities["experimental/doesNotExist"] = True
            with self.assertRaises(Exception):
                h.app.adapter.request("experimental/doesNotExist", {})
            self.assertFalse(h.app.adapter.capabilities["experimental/doesNotExist"])
        finally:
            h.close()


class TurnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Harness(delay="0.01")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def chat(self, agent_id, text, **extra):
        body = {"text": text}
        body.update(extra)
        status, res = self.h.post("/api/agents/%s/messages" % agent_id, body)
        self.assertEqual(status, 200, res)
        return res["run"]["id"]

    def test_thread_is_created_lazily_and_reused(self):
        h = self.h
        self.assertIsNone(h.app.threads.active("agent-01"))
        run1 = h.wait_run(self.chat("agent-01", "first"))
        thread = h.app.threads.active("agent-01")
        self.assertEqual(run1["status"], "completed")
        self.assertEqual(run1["provider_thread_id"], thread["provider_thread_id"])
        self.assertTrue(run1["provider_turn_id"])
        run2 = h.wait_run(self.chat("agent-01", "second"))
        self.assertEqual(run2["provider_thread_id"], run1["provider_thread_id"], "a new thread per message is not allowed")
        self.assertNotEqual(run2["provider_turn_id"], run1["provider_turn_id"])
        self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM agent_threads WHERE agent_id = 'agent-01'"), 1)

    def test_message_streaming_over_sse(self):
        h = self.h
        events = []
        ready = threading.Event()

        def listen():
            req = urllib.request.Request(h.base + "/api/events")
            with urllib.request.urlopen(req, timeout=20) as res:
                event = {}
                for raw in res:
                    line = raw.decode("utf-8").rstrip("\n")
                    if line.startswith("event: "):
                        event["type"] = line[7:]
                        if event["type"] == "hello":
                            ready.set()
                    elif line.startswith("data: "):
                        event["data"] = json.loads(line[6:])
                    elif line == "" and event:
                        events.append(event)
                        if event.get("type") == "task.completed":
                            return
                        event = {}

        t = threading.Thread(target=listen, daemon=True)
        t.start()
        self.assertTrue(ready.wait(10))
        run_id = self.chat("agent-02", "stream this please [split]")
        t.join(20)
        types = [e["type"] for e in events]
        self.assertIn("task.queued", types)
        self.assertIn("task.started", types)
        self.assertIn("message.started", types)
        self.assertIn("task.completed", types)
        deltas = [e["data"]["payload"]["delta"] for e in events if e["type"] == "message.delta"]
        self.assertGreater(len(deltas), 3, "the reply must arrive as several streamed chunks")
        final = next(e["data"]["payload"]["message"] for e in reversed(events)
                     if e["type"] == "message.completed" and e["data"]["payload"]["message"]["role"] == "assistant")
        self.assertEqual("".join(deltas), final["content"], "the fragmented protocol message must be reassembled exactly")
        self.assertTrue(final["content"].startswith("MOCK reply"))
        self.assertLess(types.index("task.started"), types.index("task.completed"))
        self.assertEqual(h.run_status(run_id), "completed")

    def test_malformed_protocol_output_does_not_break_the_turn(self):
        run = self.h.wait_run(self.chat("agent-03", "handle [garbage] lines"))
        self.assertEqual(run["status"], "completed")
        self.assertGreaterEqual(self.h.app.adapter.rpc.framer.malformed, 2)

    def test_turn_interruption(self):
        h = self.h
        run_id = self.chat("agent-04", "[slow] long task")
        h.wait(lambda: h.run_status(run_id) == "running", message="run to start")
        self.assertIn(h.runtime("agent-04")["status"], ("running", "tool"))
        status, res = h.post("/api/agents/agent-04/interrupt")
        self.assertEqual(status, 200, res)
        run = h.wait_run(run_id)
        self.assertEqual(run["status"], "interrupted")
        self.assertEqual(h.runtime("agent-04")["status"], "idle")
        self.assertFalse(h.app.db.scalar("SELECT COUNT(*) FROM outputs WHERE run_id = ?", (run_id,)),
                         "an interrupted run must not produce an output")

    def test_approval_accept(self):
        h = self.h
        run_id = self.chat("agent-05", "[approve] run the command")
        h.wait(lambda: h.run_status(run_id) == "awaiting_approval", message="approval request")
        self.assertEqual(h.runtime("agent-05")["status"], "awaiting_approval")
        status, res = h.get("/api/approvals")
        pending = [a for a in res["pending"] if a["agent_id"] == "agent-05"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["approval_type"], "command")
        self.assertIn("echo mock-approved-command", pending[0]["request_details"]["command"])
        status, res = h.post("/api/approvals/%s/respond" % pending[0]["id"], {"decision": "accept"})
        self.assertEqual(status, 200, res)
        self.assertEqual(res["approval"]["status"], "accepted")
        run = h.wait_run(run_id)
        self.assertEqual(run["status"], "completed")
        self.assertIn("approval decision: accept", run["result_summary"])
        status, res = h.post("/api/approvals/%s/respond" % pending[0]["id"], {"decision": "accept"})
        self.assertEqual(status, 409, "an approval can be answered only once")

    def test_approval_reject(self):
        h = self.h
        run_id = self.chat("agent-06", "[approve] run the command")
        h.wait(lambda: h.run_status(run_id) == "awaiting_approval", message="approval request")
        pending = [a for a in h.app.approvals.pending() if a["agent_id"] == "agent-06"]
        status, res = h.post("/api/approvals/%s/respond" % pending[0]["id"], {"decision": "decline"})
        self.assertEqual(res["approval"]["status"], "declined")
        run = h.wait_run(run_id)
        self.assertEqual(run["status"], "completed")
        self.assertIn("approval decision: decline", run["result_summary"])
        self.assertIn("declined", run["status_detail"])
        tool = [m for m in h.app.conversations.list("agent-06") if m["role"] == "tool"]
        self.assertEqual(tool[-1]["meta"]["status"], "declined")

    def test_approval_is_never_answered_automatically(self):
        h = self.h
        run_id = self.chat("agent-07", "[approve] wait for the human")
        h.wait(lambda: h.run_status(run_id) == "awaiting_approval", message="approval request")
        time.sleep(1.0)
        self.assertEqual(h.run_status(run_id), "awaiting_approval", "nothing may approve on the user's behalf")
        h.post("/api/agents/agent-07/interrupt")
        run = h.wait_run(run_id)
        self.assertEqual(run["status"], "interrupted")
        self.assertFalse([a for a in h.app.approvals.pending() if a["agent_id"] == "agent-07"])


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def chat(self, agent_id, text):
        status, res = self.h.post("/api/agents/%s/messages" % agent_id, {"text": text})
        self.assertEqual(status, 200, res)
        return res["run"]["id"]

    def test_provider_failure_is_not_reported_as_success(self):
        h = self.h
        run = h.wait_run(self.chat("agent-01", "[fail] please"))
        self.assertEqual(run["status"], "failed")
        self.assertIn("MOCK failure", run["error_message"])
        self.assertFalse(h.app.db.scalar("SELECT COUNT(*) FROM outputs WHERE run_id = ?", (run["id"],)))
        self.assertEqual(h.app.execution.summary()["failed_tasks"], 1)
        self.assertEqual(h.app.execution.summary()["completed_tasks"], 0)

    def test_rate_limit(self):
        h = self.h
        run = h.wait_run(self.chat("agent-01", "[ratelimit] please"))
        self.assertEqual(run["status"], "rate_limited")
        self.assertEqual(run["error_kind"], "usageLimitExceeded")
        self.assertEqual(h.app.adapter.status()["state"], "rate_limited")
        self.assertEqual(run["retry_count"], 0, "a usage limit must not trigger automatic retries")

    def test_retryable_failure_is_retried_once_without_side_effects(self):
        h = self.h
        run = h.wait_run(self.chat("agent-02", "[overload] please"))
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["retry_count"], 1)
        transitions = [t["to_state"] for t in h.app.db.all(
            "SELECT to_state FROM status_transitions WHERE run_id = ? ORDER BY id", (run["id"],))]
        self.assertEqual(transitions, ["queued", "starting", "running", "queued", "starting", "running", "completed"])

    def test_disconnection_marks_outcome_unknown_and_reconnects(self):
        h = self.h
        h.app.settings.set("auto_connect", False)
        run = h.wait_run(self.chat("agent-03", "[crash] now"), timeout=20)
        self.assertEqual(run["status"], "unknown", "a turn cut off by a crash must not be guessed as done or failed")
        self.assertEqual(run["retry_count"], 0, "an ambiguous run must not be retried automatically")
        self.assertEqual(h.app.adapter.status()["state"], "disconnected")
        self.assertEqual(h.runtime("agent-03")["status"], "unknown")
        status, res = h.post("/api/agents/agent-03/messages", {"text": "are you there"})
        self.assertEqual(status, 409)

        status, res = h.post("/api/codex/connect")
        self.assertEqual(res["codex"]["state"], "connected")
        thread_before = h.app.threads.active("agent-03")["provider_thread_id"]
        run2 = h.wait_run(self.chat("agent-03", "back again"))
        self.assertEqual(run2["status"], "completed")
        self.assertEqual(run2["provider_thread_id"], thread_before, "the same thread is resumed after reconnecting")

    def test_unavailable_thread_is_flagged_not_replaced(self):
        h = self.h
        h.wait_run(self.chat("agent-04", "create the thread"))
        thread_id = h.app.threads.active("agent-04")["provider_thread_id"]
        h.app.adapter.archive_thread(thread_id)  # the mock then refuses to resume it, like a missing rollout
        run = h.wait_run(self.chat("agent-04", "use it again"))
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_kind"], "thread_unavailable")
        registry = h.app.threads.public("agent-04")
        self.assertEqual(registry["status"], "unavailable")
        self.assertEqual(registry["provider_thread_id"], thread_id, "the saved thread id must be kept")
        self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM agent_threads WHERE agent_id = 'agent-04'"), 1,
                         "no replacement thread may be created silently")
        # Only an explicit, confirmed reset detaches it.
        status, res = h.post("/api/agents/agent-04/thread/reset", {})
        self.assertEqual(status, 400)
        status, res = h.post("/api/agents/agent-04/thread/reset", {"confirm": True})
        self.assertEqual(res["thread"]["status"], "uninitialized")
        run = h.wait_run(self.chat("agent-04", "fresh start"))
        self.assertEqual(run["status"], "completed")
        self.assertNotEqual(run["provider_thread_id"], thread_id)

    def test_two_agents_cannot_claim_one_thread(self):
        h = self.h
        h.wait_run(self.chat("agent-05", "mine"))
        thread_id = h.app.threads.active("agent-05")["provider_thread_id"]
        status, res = h.post("/api/agents/agent-06/thread/associate", {"thread_id": thread_id})
        self.assertEqual(status, 409)
        self.assertEqual(res["error"]["code"], "thread_claimed")
        status, res = h.post("/api/agents/agent-06/thread/associate", {"thread_id": "not a thread id!"})
        self.assertEqual(status, 400)
        status, res = h.post("/api/agents/agent-06/thread/associate", {"thread_id": "11111111-2222-3333-4444-555555555555"})
        self.assertEqual(status, 400)
        self.assertEqual(res["error"]["code"], "thread_not_found")

    def test_associate_existing_thread_imports_history(self):
        h = self.h
        h.wait_run(self.chat("agent-05", "history to import"))
        thread_id = h.app.threads.active("agent-05")["provider_thread_id"]
        status, res = h.post("/api/agents/agent-05/thread/archive", {"confirm": True})
        self.assertEqual(res["thread"]["status"], "uninitialized")
        status, res = h.get("/api/codex/threads")
        self.assertEqual(status, 200, res)
        listed = next(t for t in res["threads"] if t["id"] == thread_id)
        self.assertIsNone(listed["claimed_by"])
        status, res = h.post("/api/agents/agent-07/thread/associate", {"thread_id": thread_id})
        self.assertEqual(status, 200, res)
        self.assertEqual(res["thread"]["provider_thread_id"], thread_id)
        self.assertGreaterEqual(res["thread"]["imported_messages"], 2)
        contents = [m["content"] for m in h.app.conversations.list("agent-07")]
        self.assertTrue(any("history to import" in c for c in contents))


class IdleCostTests(unittest.TestCase):
    def test_idle_application_makes_no_inference_requests(self):
        h = Harness(scheduler_interval=0.2)
        try:
            for _ in range(5):
                h.get("/api/state")
                h.get("/api/codex/status")
                h.get("/api/log")
                h.post("/api/codex/refresh")
                time.sleep(0.2)
            self.assertEqual(h.app.adapter.inference_requests, 0)
            self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM task_runs"), 0)
            self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM agent_threads"), 0,
                             "unused agents must not get threads")
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
