"""Execution manager: queue, concurrency, duplicates, locks, Run Everything, hand-offs, restart recovery."""
import os
import shutil
import tempfile
import threading
import time
import unittest

from tests.helpers import Harness, ServerProcess


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def add_to_batch(self, agent_id, **task):
        self.h.save_task(agent_id, in_batch=True, **task)

    # ---- single assignment
    def test_assign_and_run_one_task(self):
        h = self.h
        task = h.save_task("agent-01", title="Morning briefing", prompt="Summarise the day",
                           expected_output="Three bullet points", completion_criteria="All three present")
        self.assertEqual(task["state"], "draft")
        self.assertEqual(h.runtime("agent-01")["status"], "assigned")
        status, res = h.post("/api/agents/agent-01/run", {"idempotency_key": "click-1"})
        self.assertEqual(status, 200, res)
        run = h.wait_run(res["run"]["id"])
        self.assertEqual(run["status"], "completed")
        self.assertIn("Assignment: Morning briefing", run["prompt"])
        self.assertIn("Expected output: Three bullet points", run["prompt"])
        self.assertIn("Completion criteria: All three present", run["prompt"])
        self.assertTrue(run["result_summary"].startswith("MOCK reply"))
        # The result is stored and the report file really exists inside the output folder.
        status, res = h.get("/api/agents/agent-01/outputs")
        self.assertEqual(len(res["outputs"]), 1)
        out = res["outputs"][0]
        self.assertTrue(os.path.isfile(out["file_path"]))
        self.assertTrue(os.path.realpath(out["file_path"]).startswith(os.path.realpath(h.outputs)))
        with open(out["file_path"], encoding="utf-8") as fh:
            self.assertIn("MOCK reply", fh.read())
        # A completed one-time assignment is marked completed and the agent is idle again.
        self.assertEqual(h.app.tasks.get_active("agent-01")["state"], "completed")
        self.assertEqual(h.runtime("agent-01")["status"], "idle")
        status, res = h.get("/api/agents/agent-01/history")
        self.assertEqual(res["runs"][0]["status"], "completed")
        self.assertEqual([t["to_state"] for t in res["runs"][0]["transitions"]], ["queued", "starting", "running", "completed"])

    def test_duplicate_clicks_and_refreshes_create_one_run(self):
        h = self.h
        h.save_task("agent-01", prompt="[slow] work")
        results = []

        def click():
            results.append(h.post("/api/agents/agent-01/run", {"idempotency_key": "same-click"}))

        threads = [threading.Thread(target=click) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ids = {res["run"]["id"] for status, res in results if status == 200}
        self.assertEqual(len(ids), 1)
        self.assertEqual(sum(1 for status, res in results if status == 200 and res["created"]), 1)
        # A different key while the assignment is still open also returns the same run.
        status, res = h.post("/api/agents/agent-01/run", {"idempotency_key": "another-click"})
        self.assertEqual(res["run"]["id"], next(iter(ids)))
        self.assertFalse(res["created"])
        self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM task_runs"), 1)
        h.wait(lambda: h.run_status(next(iter(ids))) == "running", message="the single run to start")
        h.post("/api/agents/agent-01/interrupt")
        h.wait_idle("agent-01")
        self.assertEqual(h.app.adapter.inference_requests, 1)

    def test_follow_up_messages_queue_behind_the_running_turn(self):
        h = self.h
        s1, r1 = h.post("/api/agents/agent-01/messages", {"text": "[slow] first"})
        h.wait(lambda: h.run_status(r1["run"]["id"]) == "running", message="first to run")
        s2, r2 = h.post("/api/agents/agent-01/messages", {"text": "second"})
        s3, r3 = h.post("/api/agents/agent-01/messages", {"text": "third"})
        self.assertEqual(h.run_status(r2["run"]["id"]), "queued")
        self.assertEqual(h.run_status(r3["run"]["id"]), "queued")
        self.assertEqual(h.runtime("agent-01")["queued"], 2)
        queued = [m for m in h.app.conversations.list("agent-01") if m["status"] == "queued"]
        self.assertEqual([m["content"] for m in queued], ["second", "third"])
        # One active turn per agent, even though the concurrency limit would allow two.
        self.assertEqual(len([r for r in h.app.execution.open_runs("agent-01") if r["status"] == "running"]), 1)
        h.post("/api/agents/agent-01/interrupt")
        a = h.wait_run(r1["run"]["id"])
        b = h.wait_run(r2["run"]["id"])
        c = h.wait_run(r3["run"]["id"])
        self.assertEqual((a["status"], b["status"], c["status"]), ("interrupted", "completed", "completed"))
        self.assertLess(b["started_at"], c["started_at"] + "~")
        self.assertEqual(len({a["provider_thread_id"], b["provider_thread_id"], c["provider_thread_id"]}), 1)

    def test_steer_running_turn(self):
        h = self.h
        s1, r1 = h.post("/api/agents/agent-01/messages", {"text": "[slow] think"})
        h.wait(lambda: h.run_status(r1["run"]["id"]) == "running", message="run to start")
        status, res = h.post("/api/agents/agent-01/messages", {"text": "focus on tests", "mode": "steer"})
        self.assertEqual(status, 200, res)
        self.assertTrue(res["steered"])
        status, res = h.post("/api/agents/agent-02/messages", {"text": "nothing running", "mode": "steer"})
        self.assertEqual(status, 409)
        h.post("/api/agents/agent-01/interrupt")
        h.wait_idle("agent-01")

    # ---- many agents
    def test_concurrency_limit_and_honest_queue_state(self):
        h = self.h
        self.assertEqual(h.app.settings.get("concurrency"), 2)
        runs = {}
        for n in (1, 2, 3, 4):
            agent_id = "agent-0%d" % n
            self.add_to_batch(agent_id, title="Job %d" % n, prompt="[slow] job %d" % n)
        status, res = h.post("/api/run-everything")
        self.assertEqual(status, 200, res)
        self.assertEqual(len(res["started"]), 4)
        runs = {r["agent_id"]: r["id"] for r in res["started"]}
        h.wait(lambda: sum(1 for r in runs.values() if h.run_status(r) == "running") == 2, message="two running")
        time.sleep(0.5)
        states = {a: h.run_status(r) for a, r in runs.items()}
        self.assertEqual(sorted(states.values()), ["queued", "queued", "running", "running"])
        for agent_id, state in states.items():
            shown = h.runtime(agent_id)["status"]
            if state == "queued":
                self.assertEqual(shown, "queued", "a queued agent must not look like it is working")
                self.assertIn("free slot", h.runtime(agent_id)["detail"])
        # Unassigned agents stay idle.
        for agent_id in ("agent-05", "agent-06", "agent-07"):
            self.assertEqual(h.runtime(agent_id)["status"], "idle")
        summary = h.app.execution.summary()
        self.assertEqual(summary["working_agents"], 2)
        self.assertEqual(summary["queued_tasks"], 2)
        batch = h.app.execution.batch_state()
        self.assertEqual((batch["total"], batch["running"], batch["queued"], batch["finished"]), (4, 2, 2, False))
        # A second batch cannot start on top of the first.
        status, res = h.post("/api/run-everything")
        self.assertEqual(status, 409)
        # Stop Batch stops the batch only.
        s, chat = h.post("/api/agents/agent-07/messages", {"text": "unrelated chat"})
        status, res = h.post("/api/batch/stop")
        self.assertEqual(res["stopped"], 4)
        for run_id in runs.values():
            self.assertIn(h.wait_run(run_id)["status"], ("interrupted", "cancelled"))
        self.assertEqual(h.wait_run(chat["run"]["id"])["status"], "completed", "work outside the batch must not be stopped")
        self.assertTrue(h.app.execution.batch_state()["finished"])

    def test_concurrency_setting_is_respected_and_validated(self):
        h = self.h
        status, res = h.patch("/api/settings", {"concurrency": 8})
        self.assertEqual(status, 400)
        status, res = h.patch("/api/settings", {"concurrency": 0})
        self.assertEqual(status, 400)
        status, res = h.patch("/api/settings", {"concurrency": 1})
        self.assertEqual(status, 200)
        ids = []
        for n in (1, 2, 3):
            s, r = h.post("/api/agents/agent-0%d/messages" % n, {"text": "[slow] x"})
            ids.append(r["run"]["id"])
        h.wait(lambda: any(h.run_status(r) == "running" for r in ids), message="one running")
        time.sleep(0.4)
        self.assertEqual(sum(1 for r in ids if h.run_status(r) in ("running", "starting")), 1)
        for n in (1, 2, 3):
            h.post("/api/agents/agent-0%d/interrupt" % n, {"include_queued": True})
        for r in ids:
            h.wait_run(r)

    def test_run_everything_rules(self):
        h = self.h
        self.add_to_batch("agent-01", title="Briefing", prompt="brief")           # runs
        self.add_to_batch("agent-02", title="Research", prompt="research")        # runs
        h.save_task("agent-03", title="Draft only", prompt="not added")           # saved but not added
        # agent-04: no task
        self.add_to_batch("agent-05", title="Tomorrow", prompt="later",            # scheduled for the future
                          schedule={"recurrence": {"type": "once", "run_at": "2099-01-01T09:00"}})
        self.add_to_batch("agent-06", title="Done already", prompt="done")        # completed one-time
        s, r = h.post("/api/agents/agent-06/run")
        h.wait_run(r["run"]["id"])
        self.add_to_batch("agent-07", title="Off", prompt="disabled", enabled=False)

        status, state = h.get("/api/state")
        self.assertEqual(state["eligible"], ["agent-01", "agent-02"])
        reasons = {s["agent_id"]: s["reason"] for s in state["skipped"]}
        self.assertEqual(reasons["agent-03"], "not added to Run Everything")
        self.assertEqual(reasons["agent-04"], "no assignment")
        self.assertIn("scheduled for later", reasons["agent-05"])
        self.assertEqual(reasons["agent-06"], "already completed")
        self.assertEqual(reasons["agent-07"], "assignment disabled")

        status, res = h.post("/api/run-everything")
        self.assertEqual(sorted(r["agent_id"] for r in res["started"]), ["agent-01", "agent-02"])
        for r in res["started"]:
            self.assertEqual(h.wait_run(r["id"])["status"], "completed")
        self.assertTrue(h.app.execution.batch_state()["finished"])
        self.assertEqual(h.app.execution.batch_state()["completed"], 2)
        # Pressing it again must not repeat completed one-time assignments.
        status, res = h.post("/api/run-everything")
        self.assertEqual(status, 409)
        self.assertEqual(res["error"]["code"], "nothing_eligible")
        self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM task_runs WHERE agent_id = 'agent-05'"), 0,
                         "a future schedule must not be run by Run Everything")
        # Run Now starts a scheduled assignment early, on request.
        s, r = h.post("/api/agents/agent-05/run")
        self.assertEqual(h.wait_run(r["run"]["id"])["status"], "completed")
        # A repeatable assignment may run again.
        self.add_to_batch("agent-01", title="Briefing", prompt="brief", execution_mode="repeatable")
        status, res = h.post("/api/run-everything")
        self.assertEqual([r["agent_id"] for r in res["started"]], ["agent-01"])
        h.wait_run(res["started"][0]["id"])

    def test_failed_batch_run_is_counted_as_failed(self):
        h = self.h
        self.add_to_batch("agent-01", title="Will fail", prompt="[fail] task")
        self.add_to_batch("agent-02", title="Will pass", prompt="fine")
        status, res = h.post("/api/run-everything")
        for r in res["started"]:
            h.wait_run(r["id"])
        batch = h.app.execution.batch_state()
        self.assertEqual((batch["completed"], batch["failed"]), (1, 1))
        self.assertEqual(h.app.tasks.get_active("agent-01")["state"], "pending", "a failed one-time task is not completed")
        self.assertEqual(h.runtime("agent-01")["last_run"]["status"], "failed")
        # Retry is explicit and creates a new run.
        status, res = h.post("/api/agents/agent-02/retry")
        self.assertEqual(status, 409, "a successful run is not retryable")
        status, res = h.post("/api/agents/agent-01/retry")
        self.assertEqual(status, 200, res)
        self.assertEqual(h.wait_run(res["run"]["id"])["status"], "failed")
        self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM task_runs WHERE agent_id = 'agent-01'"), 2)

    def test_timeout_fails_the_run(self):
        h = self.h
        h.save_task("agent-01", title="Too slow", prompt="[slow] forever", max_duration_sec=60)
        s, r = h.post("/api/agents/agent-01/run")
        h.app.db.execute("UPDATE task_runs SET max_duration_sec = 1 WHERE id = ?", (r["run"]["id"],))
        run = h.wait_run(r["run"]["id"], timeout=20)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_kind"], "timeout")

    # ---- workspace locking
    def test_writers_in_the_same_folder_are_serialized(self):
        h = self.h
        shared = os.path.join(h.workspace, "shared")
        os.makedirs(shared)
        for agent_id in ("agent-01", "agent-02"):
            status, res = h.patch("/api/agents/" + agent_id, {"working_directory": shared,
                                                             "permissions": {"sandbox": "workspace-write"}})
            self.assertEqual(status, 200, res)
        s, a = h.post("/api/agents/agent-01/messages", {"text": "[slow] [write] one"})
        h.wait(lambda: h.run_status(a["run"]["id"]) == "running", message="writer one running")
        s, b = h.post("/api/agents/agent-02/messages", {"text": "[write] two"})
        s, c = h.post("/api/agents/agent-03/messages", {"text": "reader elsewhere"})
        time.sleep(0.6)
        self.assertEqual(h.run_status(b["run"]["id"]), "queued", "a second writer must wait for the folder")
        self.assertIn("write access to the same folder", h.runtime("agent-02")["detail"])
        self.assertEqual(h.wait_run(c["run"]["id"])["status"], "completed", "a read-only agent elsewhere is not blocked")
        h.post("/api/agents/agent-01/interrupt")
        h.wait_run(a["run"]["id"])
        run_b = h.wait_run(b["run"]["id"])
        self.assertEqual(run_b["status"], "completed")
        # The file the mock reported was verified on disk before being listed as an output.
        files = [o for o in h.app.outputs.list(agent_id="agent-02") if o["output_type"] == "file"]
        self.assertEqual(len(files), 1)
        self.assertTrue(os.path.isfile(files[0]["file_path"]))

    def test_unverifiable_file_is_not_listed(self):
        h = self.h
        run = {"id": "run_x", "task_id": None, "kind": "chat", "title": "t"}
        agent = h.app.agents.get("agent-01")
        h.app.db.execute(
            "INSERT INTO task_runs(id, agent_id, kind, prompt, idempotency_key, trigger_type, status, queued_at) "
            "VALUES ('run_x', 'agent-01', 'chat', 'p', 'k-x', 'chat', 'completed', 'now')")
        recorded = h.app.outputs.record_file_changes(agent, run, [
            {"path": os.path.join(h.workspace, "does-not-exist.txt"), "kind": {"type": "add"}},
            {"path": os.path.join(h.tmp, "data", "agent_hq.db"), "kind": {"type": "update"}},
            {"path": "C:\\Windows\\win.ini", "kind": {"type": "update"}},
            {"path": "../../etc/passwd", "kind": {"type": "add"}},
        ])
        self.assertEqual(recorded, [], "missing files and files outside the workspace must never be listed")

    # ---- hand-offs
    def test_dependencies_are_off_by_default_and_reject_loops(self):
        h = self.h
        status, res = h.post("/api/dependencies", {"source_agent_id": "agent-01", "destination_agent_id": "agent-02"})
        self.assertEqual(status, 409)
        self.assertEqual(res["error"]["code"], "collaboration_disabled")
        h.patch("/api/settings", {"collaboration_enabled": True})
        status, res = h.post("/api/dependencies", {"source_agent_id": "agent-01", "destination_agent_id": "agent-02"})
        self.assertEqual(status, 200, res)
        h.post("/api/dependencies", {"source_agent_id": "agent-02", "destination_agent_id": "agent-03"})
        status, res = h.post("/api/dependencies", {"source_agent_id": "agent-03", "destination_agent_id": "agent-01"})
        self.assertEqual(status, 400)
        self.assertEqual(res["error"]["code"], "cycle")
        status, res = h.post("/api/dependencies", {"source_agent_id": "agent-01", "destination_agent_id": "agent-01"})
        self.assertEqual(status, 400)

    def test_batch_hand_off_waits_for_the_source_and_transfers_its_result(self):
        h = self.h
        h.patch("/api/settings", {"collaboration_enabled": True})
        h.post("/api/dependencies", {"source_agent_id": "agent-01", "destination_agent_id": "agent-02"})
        self.add_to_batch("agent-01", title="Spec", prompt="[slow] write the spec")
        self.add_to_batch("agent-02", title="Design", prompt="design from the spec")
        status, res = h.post("/api/run-everything")
        runs = {r["agent_id"]: r["id"] for r in res["started"]}
        h.wait(lambda: h.run_status(runs["agent-01"]) == "running", message="source running")
        self.assertEqual(h.run_status(runs["agent-02"]), "blocked")
        self.assertEqual(h.runtime("agent-02")["status"], "queued")
        self.assertEqual(h.app.adapter.inference_requests, 1, "the dependent agent must not start early")
        # Source stopped -> the dependent run is cancelled, not run.
        h.post("/api/agents/agent-01/interrupt")
        h.wait_run(runs["agent-01"])
        self.assertEqual(h.wait_run(runs["agent-02"])["status"], "cancelled")
        self.assertEqual(h.app.adapter.inference_requests, 1)

        # Second batch: the source succeeds, so the dependent run starts with the source's result.
        self.add_to_batch("agent-01", title="Spec", prompt="write the spec", execution_mode="repeatable")
        status, res = h.post("/api/run-everything")
        runs = {r["agent_id"]: r["id"] for r in res["started"]}
        self.assertEqual(h.wait_run(runs["agent-01"])["status"], "completed")
        dependent = h.wait_run(runs["agent-02"])
        self.assertEqual(dependent["status"], "completed")
        self.assertIn("Hand-off from Agent 1", dependent["prompt"])
        self.assertIn("MOCK reply", dependent["prompt"])
        self.assertEqual(dependent["parent_run_id"], runs["agent-01"])
        self.assertEqual(dependent["depth"], 1)
        events = [e["type"] for e in h.app.bus.since(0)]
        self.assertIn("handoff.started", events)

    def test_hand_off_depth_limit_and_approval(self):
        h = self.h
        h.patch("/api/settings", {"collaboration_enabled": True, "max_delegation_depth": 1})
        h.post("/api/dependencies", {"source_agent_id": "agent-01", "destination_agent_id": "agent-02", "require_approval": True})
        h.post("/api/dependencies", {"source_agent_id": "agent-02", "destination_agent_id": "agent-03"})
        for n in (1, 2, 3):
            h.save_task("agent-0%d" % n, title="Step %d" % n, prompt="step %d" % n, execution_mode="repeatable")
        s, r = h.post("/api/agents/agent-01/run")
        self.assertEqual(h.wait_run(r["run"]["id"])["status"], "completed")
        pending = h.wait(lambda: [a for a in h.app.approvals.pending() if a["approval_type"] == "handoff"],
                         message="hand-off approval")
        self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM task_runs WHERE agent_id = 'agent-02'"), 0,
                         "a hand-off that needs approval must not start by itself")
        status, res = h.post("/api/approvals/%s/respond" % pending[0]["id"], {"decision": "accept"})
        self.assertEqual(status, 200, res)
        run2 = h.wait(lambda: h.app.db.one("SELECT * FROM task_runs WHERE agent_id = 'agent-02'"), message="hand-off run")
        self.assertEqual(h.wait_run(run2["id"])["status"], "completed")
        self.assertEqual(run2["trigger_type"], "handoff")
        time.sleep(0.5)
        self.assertEqual(h.app.db.scalar("SELECT COUNT(*) FROM task_runs WHERE agent_id = 'agent-03'"), 0,
                         "the depth limit must stop the chain")
        logs = [e["log"] for e in h.app.bus.log_entries() if e["log"]]
        self.assertTrue(any("depth limit" in line for line in logs))


class RestartRecoveryTests(unittest.TestCase):
    def test_killed_backend_recovers_state_without_duplicating_work(self):
        """A real server process is killed mid-run (no clean-up code runs), then started again on the same data."""
        tmp = tempfile.mkdtemp(prefix="agent-hq-crash-")
        p = ServerProcess(tmp)
        p2 = None
        try:
            p.wait(lambda: p.get("/api/codex/status")[1]["codex"]["state"] == "connected", message="mock connection")
            p.patch("/api/settings", {"concurrency": 1})
            p.patch("/api/agents/agent-02", {"display_name": "Scout", "role": "Researcher"})
            p.post("/api/agents/agent-01/tasks", {"title": "Finished", "prompt": "quick", "in_batch": True})
            s, done = p.post("/api/agents/agent-01/run")
            p.wait(lambda: p.run("agent-01", done["run"]["id"])["status"] == "completed", message="first run")
            s, running = p.post("/api/agents/agent-02/messages", {"text": "[slow] in flight"})
            p.wait(lambda: p.run("agent-02", running["run"]["id"])["status"] == "running", message="in-flight run")
            s, queued = p.post("/api/agents/agent-03/messages", {"text": "queued behind"})
            self.assertEqual(p.run("agent-03", queued["run"]["id"])["status"], "queued")
            p.post("/api/agents/agent-04/tasks", {"title": "Daily", "prompt": "daily",
                                                  "schedule": {"recurrence": {"type": "daily", "time": "09:00"}}})
            thread_before = p.agent("agent-02")["thread"]["provider_thread_id"]
            self.assertEqual(p.get("/api/codex/status")[1]["codex"]["inference_requests"], 2)
            p.kill()

            p2 = ServerProcess(tmp, autoconnect=False)
            # Before Codex is connected: configuration, schedule and queue are back; nothing is guessed.
            self.assertEqual(p2.run("agent-01", done["run"]["id"])["status"], "completed")
            self.assertEqual(p2.run("agent-02", running["run"]["id"])["status"], "recovering")
            self.assertEqual(p2.run("agent-03", queued["run"]["id"])["status"], "queued")
            a2 = p2.agent("agent-02")
            self.assertEqual((a2["display_name"], a2["role"]), ("Scout", "Researcher"))
            self.assertEqual(a2["runtime"]["status"], "unknown")
            self.assertEqual(a2["thread"]["provider_thread_id"], thread_before)
            state = p2.get("/api/state")[1]
            self.assertEqual(state["settings"]["concurrency"], 1)
            self.assertEqual(state["connection"]["state"], "disconnected")
            self.assertEqual(p2.agent("agent-04")["task"]["schedule"]["recurrence"]["type"], "daily")
            self.assertEqual(p2.agent("agent-01")["task"]["state"], "completed")
            self.assertEqual(state["connection"]["inference_requests"], 0)

            p2.post("/api/codex/connect")
            # The cut-off turn is checked with Codex. There is no final result for it, so the outcome
            # stays unknown and it is NOT run again.
            p2.wait(lambda: p2.run("agent-02", running["run"]["id"])["status"] != "recovering", message="reconciliation")
            cut = p2.run("agent-02", running["run"]["id"])
            self.assertEqual(cut["status"], "unknown")
            self.assertEqual(cut["retry_count"], 0)
            # The queued run had never started, so it is safe to run - exactly once.
            p2.wait(lambda: p2.run("agent-03", queued["run"]["id"])["status"] == "completed", message="queued run")
            self.assertEqual(p2.get("/api/codex/status")[1]["codex"]["inference_requests"], 1)
            total = sum(len(p2.get("/api/agents/agent-0%d/history" % n)[1]["runs"]) for n in range(1, 8))
            self.assertEqual(total, 3, "no run may be duplicated by a restart")
            # The user reviews the unknown outcome; the agent returns to idle without anything being re-run.
            status, res = p2.post("/api/agents/agent-02/acknowledge")
            self.assertEqual(res["runtime"]["status"], "idle")
            # Continuing the conversation uses the same thread.
            s, again = p2.post("/api/agents/agent-02/messages", {"text": "continue"})
            p2.wait(lambda: p2.run("agent-02", again["run"]["id"])["status"] == "completed", message="follow-up")
            self.assertEqual(p2.run("agent-02", again["run"]["id"])["provider_thread_id"], thread_before)
        finally:
            p.stop()
            if p2:
                p2.stop()
            time.sleep(0.3)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_completed_turn_is_verified_after_restart(self):
        h = Harness()
        tmp = h.tmp
        try:
            s, r = h.post("/api/agents/agent-01/messages", {"text": "finish while nobody watches"})
            run = h.wait_run(r["run"]["id"])
            # Rewind the record to look as if AGENTS HQ died before seeing the result.
            h.app.db.execute("UPDATE task_runs SET status = 'running', finished_at = NULL, result_summary = NULL WHERE id = ?",
                             (run["id"],))
            h.app.db.execute("DELETE FROM outputs")
            h.stop_server()
            h2 = Harness(tmp=tmp)
            try:
                recovered = h2.wait_run(run["id"])
                self.assertEqual(recovered["status"], "completed")
                self.assertIn("Verified with Codex", recovered["status_detail"])
                self.assertTrue(recovered["result_summary"].startswith("MOCK reply"))
                self.assertEqual(h2.app.adapter.inference_requests, 0, "verification must not re-run the turn")
                self.assertEqual(len(h2.app.outputs.list(agent_id="agent-01")), 1)
            finally:
                h2.stop_server()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
