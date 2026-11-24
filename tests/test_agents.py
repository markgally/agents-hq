"""Agent configuration: seven defaults, edits, persistence, and thread preservation."""
import unittest

from tests.helpers import Harness


class AgentConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Harness()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def test_exactly_seven_default_agents(self):
        status, state = self.h.get("/api/state")
        self.assertEqual(status, 200)
        agents = state["agents"]
        self.assertEqual([a["id"] for a in agents], ["agent-0%d" % n for n in range(1, 8)])
        self.assertEqual([a["slot_number"] for a in agents], list(range(1, 8)))
        self.assertEqual([a["sprite_key"] for a in agents], ["mgr", "cap", "in", "sch", "pack", "ved", "rvs"])
        fresh = agents[6]  # agent-07 is not edited by any other test in this class
        self.assertEqual(fresh["display_name"], "Agent 7")
        self.assertEqual(fresh["role"], "Unassigned")
        self.assertEqual(fresh["personality"], "Friendly general-purpose AI assistant")
        self.assertIsNone(fresh["task"])
        self.assertEqual(fresh["runtime"]["status"], "idle")
        self.assertEqual(fresh["thread"]["status"], "uninitialized")
        self.assertEqual(fresh["permissions"], {"sandbox": "read-only", "network": False, "approval": "on-request"})
        self.assertEqual(fresh["allowed_tools"], [])

    def test_seeding_is_idempotent(self):
        self.assertEqual(self.h.app.agents.seed(), 0)
        self.assertEqual(self.h.app.db.scalar("SELECT COUNT(*) FROM agents"), 7)

    def test_eighth_agent_cannot_exist(self):
        with self.assertRaises(Exception):
            self.h.app.db.execute(
                "INSERT INTO agents(id, slot_number, display_name, sprite_key, created_at, updated_at) "
                "VALUES ('agent-08', 8, 'Extra', 'mgr', 'x', 'x')")

    def test_rename_role_and_instructions(self):
        status, res = self.h.patch("/api/agents/agent-01", {
            "display_name": "JARVIS", "role": "Personal Assistant", "instructions": "Always answer briefly.",
            "description": "Helps with daily planning.", "personality": "Calm and precise"})
        self.assertEqual(status, 200, res)
        agent = res["agent"]
        self.assertEqual(agent["display_name"], "JARVIS")
        self.assertEqual(agent["role"], "Personal Assistant")
        self.assertEqual(agent["instructions"], "Always answer briefly.")
        text = self.h.app.agents.developer_instructions(self.h.app.agents.get("agent-01"))
        self.assertIn("JARVIS", text)
        self.assertIn("Personal Assistant", text)
        self.assertIn("Always answer briefly.", text)

    def test_validation(self):
        status, res = self.h.patch("/api/agents/agent-02", {"display_name": "   "})
        self.assertEqual(status, 400)
        status, res = self.h.patch("/api/agents/agent-02", {"display_name": "x" * 41})
        self.assertEqual(status, 400)
        status, res = self.h.patch("/api/agents/agent-02", {"permissions": {"sandbox": "danger-full-access"}})
        self.assertEqual(status, 400, "full access must never be accepted")
        status, res = self.h.patch("/api/agents/agent-02", {"model": "not-a-real-model"})
        self.assertEqual(status, 400)
        status, res = self.h.patch("/api/agents/agent-02", {"sprite_key": "thumb"})
        self.assertEqual(status, 400)
        status, res = self.h.patch("/api/agents/agent-02", {"allowed_tools": ["no_such_server"]})
        self.assertEqual(status, 400)

    def test_model_and_tools_from_discovery(self):
        status, res = self.h.patch("/api/agents/agent-03", {"model": "mock-model-2", "reasoning_effort": "low",
                                                           "allowed_tools": ["mock_tools"]})
        self.assertEqual(status, 200, res)
        self.assertEqual(res["agent"]["model"], "mock-model-2")
        self.assertEqual(res["agent"]["allowed_tools"], ["mock_tools"])

    def test_read_only_forces_network_off(self):
        status, res = self.h.patch("/api/agents/agent-04", {"permissions": {"sandbox": "read-only", "network": True}})
        self.assertEqual(status, 200)
        self.assertFalse(res["agent"]["permissions"]["network"])

    def test_presets_keep_threads_permissions_and_tasks(self):
        self.h.patch("/api/agents/agent-05", {"permissions": {"sandbox": "workspace-write"}})
        self.h.save_task("agent-05", title="Keep me", prompt="Stay")
        status, res = self.h.post("/api/agents/agent-05/messages", {"text": "hello before preset"})
        self.assertEqual(status, 200, res)
        self.h.wait_run(res["run"]["id"])
        thread_before = self.h.app.threads.active("agent-05")["provider_thread_id"]
        messages_before = len(self.h.app.conversations.list("agent-05"))

        status, res = self.h.post("/api/presets/apply", {"preset_id": "it-department"})
        self.assertEqual(status, 400, "a preset must be confirmed")
        status, res = self.h.post("/api/presets/apply", {"preset_id": "it-department", "confirm": True})
        self.assertEqual(status, 200, res)
        agent = next(a for a in res["agents"] if a["id"] == "agent-05")
        self.assertEqual(agent["role"], "Software Developer")
        self.assertEqual(agent["permissions"]["sandbox"], "workspace-write")
        self.assertEqual(agent["task"]["title"], "Keep me")
        self.assertEqual(self.h.app.threads.active("agent-05")["provider_thread_id"], thread_before)
        self.assertEqual(len(self.h.app.conversations.list("agent-05")), messages_before)
        self.assertFalse(self.h.app.execution.open_runs("agent-05"), "a preset must not start work")

    def test_preset_catalogue(self):
        status, res = self.h.get("/api/presets")
        names = [p["name"] for p in res["presets"]]
        self.assertEqual(names, ["Default Office", "Vibe Coding Team", "IT Department", "Personal Workforce", "Business Workforce"])
        for preset in res["presets"]:
            self.assertEqual(len(preset["agents"]), 7)
        vibe = res["presets"][1]["agents"]
        self.assertEqual(vibe[0]["role"], "Software Architect and Project Manager")
        self.assertEqual(vibe[6]["role"], "DevOps Engineer")


class PersistenceTests(unittest.TestCase):
    def test_configuration_and_thread_survive_restart_and_rename(self):
        h = Harness()
        tmp, port = h.tmp, h.port
        try:
            h.patch("/api/agents/agent-02", {"display_name": "Scout", "role": "Researcher", "instructions": "Cite sources."})
            status, res = h.post("/api/agents/agent-02/messages", {"text": "first message"})
            self.assertEqual(status, 200, res)
            h.wait_run(res["run"]["id"])
            thread_id = h.app.threads.active("agent-02")["provider_thread_id"]
            self.assertTrue(thread_id)

            # Renaming and changing the role must not replace the thread.
            h.patch("/api/agents/agent-02", {"display_name": "Scout II", "role": "Senior Researcher"})
            self.assertEqual(h.app.threads.active("agent-02")["provider_thread_id"], thread_id)
            h.stop_server()

            h2 = Harness(tmp=tmp)
            try:
                agent = h2.app.agents.get("agent-02")
                self.assertEqual(agent["display_name"], "Scout II")
                self.assertEqual(agent["role"], "Senior Researcher")
                self.assertEqual(agent["instructions"], "Cite sources.")
                self.assertEqual(h2.app.threads.active("agent-02")["provider_thread_id"], thread_id)
                self.assertGreaterEqual(len(h2.app.conversations.list("agent-02")), 2)

                # The same thread is resumed, not replaced, after the restart.
                status, res = h2.post("/api/agents/agent-02/messages", {"text": "second message"})
                self.assertEqual(status, 200, res)
                run = h2.wait_run(res["run"]["id"])
                self.assertEqual(run["status"], "completed")
                self.assertEqual(run["provider_thread_id"], thread_id)
                self.assertEqual(h2.app.db.scalar("SELECT COUNT(*) FROM agent_threads WHERE agent_id = 'agent-02'"), 1)
            finally:
                h2.stop_server()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
