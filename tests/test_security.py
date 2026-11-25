"""Security: request gate, validation, path boundaries, redaction, downloads, permissions."""
import http.client
import json
import os
import unittest

from tests.helpers import Harness
from agent_hq import security
from agent_hq.security import ApiError, PathPolicy, redact


class RedactionTests(unittest.TestCase):
    def test_secrets_are_removed(self):
        samples = [
            "key sk-abcdefghijklmnopqrstuvwxyz0123456789 end",
            "gsk_abcdefghijklmnopqrstuvwxyz0123456789ABCD",
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz.0123456789",
            "token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "password=hunter2hunter2",
            "OPENAI_API_KEY=abcd1234efgh5678",
            "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n-----END PRIVATE KEY-----",
        ]
        secrets = ["sk-abcdefghijklmnopqrstuvwxyz0123456789", "gsk_abcdefghijklmnopqrstuvwxyz0123456789ABCD",
                   "abcdefghijklmnopqrstuvwxyz.0123456789", "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
                   "ghp_abcdefghijklmnopqrstuvwxyz0123456789", "hunter2hunter2", "abcd1234efgh5678",
                   "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"]
        for sample, secret in zip(samples, secrets):
            cleaned = redact(sample)
            self.assertNotIn(secret, cleaned, sample)
            self.assertIn("[redacted", cleaned)

    def test_ordinary_text_is_untouched(self):
        text = "Agent 1 completed task: Morning briefing in 12 seconds. See report-2026.md"
        self.assertEqual(redact(text), text)


class PathPolicyTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="agent-hq-paths-"))
        self.root = os.path.join(self.tmp, "allowed")
        self.work = os.path.join(self.root, "project")
        self.private = os.path.join(self.root, "private-data")
        self.outside = os.path.join(self.tmp, "outside")
        for d in (self.work, self.private, self.outside):
            os.makedirs(d)
        with open(os.path.join(self.work, "ok.txt"), "w") as fh:
            fh.write("ok")
        with open(os.path.join(self.private, "secret.txt"), "w") as fh:
            fh.write("secret")
        with open(os.path.join(self.outside, "other.txt"), "w") as fh:
            fh.write("other")
        self.policy = PathPolicy([self.root], [self.private])

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inside_workspace_is_allowed(self):
        self.assertEqual(self.policy.check_workdir(self.work), self.work)
        self.assertEqual(self.policy.check_file(os.path.join(self.work, "ok.txt")), os.path.join(self.work, "ok.txt"))
        self.assertEqual(self.policy.resolve_relative(self.work, "ok.txt"), os.path.join(self.work, "ok.txt"))

    def test_relative_paths_accept_both_separator_styles_inside_the_workspace(self):
        folder = os.path.join(self.work, "notes")
        os.makedirs(folder)
        path = os.path.join(folder, "report.txt")
        with open(path, "w") as fh:
            fh.write("report")
        for relative in ("notes/report.txt", "notes\\report.txt", "notes\\../notes/report.txt"):
            with self.subTest(relative=relative):
                self.assertEqual(self.policy.resolve_relative(self.work, relative), path)
                self.assertEqual(self.policy.check_file(self.policy.resolve_relative(self.work, relative)), path)

    def test_windows_and_mixed_separator_escapes_are_rejected_on_every_os(self):
        for relative in ("..\\outside\\other.txt", "sub\\..\\..\\outside/other.txt",
                         "sub/..\\../outside/other.txt", "\\etc\\passwd",
                         "\\\\server\\share\\file.txt", "C:\\Windows\\file.txt", "C:relative.txt"):
            with self.subTest(relative=relative), self.assertRaises(ApiError):
                self.policy.resolve_relative(self.work, relative)

    def test_invalid_relative_path_inputs_still_raise_api_errors(self):
        for relative in (None, 123, [], "", "   ", "notes\\bad\x00name.txt"):
            with self.subTest(relative=relative), self.assertRaises(ApiError):
                self.policy.resolve_relative(self.work, relative)

    def test_traversal_and_outside_paths_are_rejected(self):
        for bad in (os.path.join(self.work, "..", "outside", "other.txt"), os.path.join(self.outside, "other.txt"),
                    "C:\\Windows\\System32\\drivers\\etc\\hosts", "/etc/passwd"):
            with self.assertRaises(ApiError, msg=bad):
                self.policy.check_file(bad)
        for bad in ("../outside/other.txt", "..\\outside\\other.txt", os.path.join(self.outside, "other.txt"),
                    "sub/../../outside/other.txt"):
            with self.assertRaises(ApiError, msg=bad):
                self.policy.resolve_relative(self.work, bad)
        with self.assertRaises(ApiError):
            self.policy.check_workdir(self.outside)
        with self.assertRaises(ApiError):
            self.policy.check_workdir(self.tmp)  # a parent of the allowed folder is not allowed

    def test_private_roots_are_rejected_even_inside_an_allowed_folder(self):
        with self.assertRaises(ApiError):
            self.policy.check_file(os.path.join(self.private, "secret.txt"))
        with self.assertRaises(ApiError):
            self.policy.check_workdir(self.private)
        with self.assertRaises(ApiError):
            self.policy.check_workdir(self.root)  # a folder that contains private data cannot be a workspace
        with self.assertRaises(ApiError):
            self.policy.resolve_relative(self.work, "../private-data/secret.txt")

    def test_symlink_escape_is_rejected(self):
        link = os.path.join(self.work, "link-out")
        try:
            os.symlink(self.outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links cannot be created on this machine without extra privileges")
        with self.assertRaises(ApiError):
            self.policy.check_file(os.path.join(link, "other.txt"))
        with self.assertRaises(ApiError):
            self.policy.resolve_relative(self.work, "link-out/other.txt")
        with self.assertRaises(ApiError):
            self.policy.resolve_relative(self.work, "link-out\\other.txt")

    def test_filenames_are_sanitised(self):
        self.assertNotIn("/", security.safe_filename("../../etc/passwd"))
        self.assertNotIn("\\", security.safe_filename("..\\..\\win.ini"))
        self.assertNotIn("\n", security.safe_filename("a\r\nSet-Cookie: x"))
        self.assertTrue(security.safe_filename(""))
        self.assertRegex(security.slug("Morning briefing: 50% done!"), r"^[a-z0-9\-]+$")


class RequestGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Harness()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def raw(self, method, path, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.h.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True)
            hdrs = {"Host": "localhost:%d" % self.h.port}
            hdrs.update(headers or {})
            data = body if body is not None else b""
            if method != "GET":
                hdrs.setdefault("Content-Length", str(len(data)))
            for k, v in hdrs.items():
                conn.putheader(k, v)
            conn.endheaders()
            if data:
                conn.send(data)
            res = conn.getresponse()
            payload = res.read()
            return res.status, payload, dict(res.getheaders())
        finally:
            conn.close()

    def code(self, payload):
        return json.loads(payload.decode("utf-8"))["error"]["code"]

    def test_binds_to_localhost_only(self):
        self.assertEqual(self.h.server.server_address[0], "127.0.0.1")

    def test_foreign_host_header_is_rejected(self):
        for host in ("evil.example.com", "evil.example.com:%d" % self.h.port, "localhost.evil.example.com", "10.0.0.5:%d" % self.h.port):
            status, payload, _ = self.raw("GET", "/api/state", {"Host": host})
            self.assertEqual(status, 403, host)
            self.assertEqual(self.code(payload), "forbidden_host")
            status, payload, _ = self.raw("GET", "/", {"Host": host})
            self.assertEqual(status, 403, host)

    def test_cross_site_requests_are_rejected(self):
        token = {"X-AHQ-Token": self.h.token, "Content-Type": "application/json"}
        body = b'{"display_name":"Hacked"}'
        for origin in ("https://evil.example.com", "http://localhost:9999", "null"):
            hdrs = dict(token, Origin=origin)
            status, payload, _ = self.raw("PATCH", "/api/agents/agent-07", hdrs, body)
            self.assertEqual(status, 403, origin)
            self.assertEqual(self.code(payload), "forbidden_origin")
        status, payload, _ = self.raw("PATCH", "/api/agents/agent-07", dict(token, **{"Sec-Fetch-Site": "cross-site"}), body)
        self.assertEqual(status, 403)
        status, payload, _ = self.raw("GET", "/api/state", {"Origin": "https://evil.example.com"})
        self.assertEqual(status, 403, "another site must not be able to read state (it contains the session token)")
        self.assertEqual(self.h.app.agents.get("agent-07")["display_name"], "Agent 7")

    def test_same_origin_request_is_accepted(self):
        hdrs = {"X-AHQ-Token": self.h.token, "Content-Type": "application/json",
                "Origin": "http://localhost:%d" % self.h.port, "Sec-Fetch-Site": "same-origin"}
        status, payload, _ = self.raw("PATCH", "/api/agents/agent-06", hdrs, b'{"description":"ok"}')
        self.assertEqual(status, 200, payload)

    def test_state_changes_need_the_session_token(self):
        status, res = self.h.post("/api/agents/agent-07/messages", {"text": "hi"}, token=False)
        self.assertEqual(status, 403)
        self.assertEqual(res["error"]["code"], "bad_token")
        status, res = self.h.post("/api/agents/agent-07/messages", {"text": "hi"}, token=False, headers={"X-AHQ-Token": "wrong"})
        self.assertEqual(status, 403)
        status, res = self.h.post("/api/run-everything", token=False)
        self.assertEqual(status, 403)
        self.assertEqual(self.h.app.db.scalar("SELECT COUNT(*) FROM task_runs WHERE agent_id = 'agent-07'"), 0)

    def test_no_cors_headers_are_sent(self):
        status, payload, headers = self.raw("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertFalse([k for k in headers if k.lower().startswith("access-control-")])
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")

    def test_body_rules(self):
        token = {"X-AHQ-Token": self.h.token}
        status, payload, _ = self.raw("POST", "/api/agents/agent-07/messages", dict(token, **{"Content-Type": "text/plain"}), b'{"text":"x"}')
        self.assertEqual(status, 415, "form-style content types (which browsers send cross-site without preflight) are refused")
        status, payload, _ = self.raw("POST", "/api/agents/agent-07/messages",
                                      dict(token, **{"Content-Type": "application/x-www-form-urlencoded"}), b"text=x")
        self.assertEqual(status, 415)
        status, payload, _ = self.raw("POST", "/api/agents/agent-07/messages", dict(token, **{"Content-Type": "application/json"}), b"{not json")
        self.assertEqual(status, 400)
        status, payload, _ = self.raw("POST", "/api/agents/agent-07/messages", dict(token, **{"Content-Type": "application/json"}), b"[1,2]")
        self.assertEqual(status, 400)
        status, payload, _ = self.raw("POST", "/api/agents/agent-07/messages",
                                      dict(token, **{"Content-Type": "application/json", "Content-Length": str(50 * 1024 * 1024)}), b"")
        self.assertEqual(status, 413)

    def test_unknown_paths_ids_and_methods(self):
        self.assertEqual(self.h.get("/api/nope")[0], 404)
        self.assertEqual(self.h.get("/api/agents/agent-08")[0], 404)
        self.assertEqual(self.h.get("/api/agents/agent-1")[0], 404)
        self.assertEqual(self.h.get("/api/agents/..%2F..%2Fetc")[0], 404)
        self.assertEqual(self.h.delete("/api/state")[0], 405)
        self.assertEqual(self.h.get("/api/outputs/does-not-exist")[0], 404)
        self.assertEqual(self.h.post("/api/approvals/apr_missing/respond", {"decision": "accept"})[0], 404)
        status, res = self.h.post("/api/agents/agent-07/messages", {"text": ""})
        self.assertEqual(status, 400)
        status, res = self.h.post("/api/agents/agent-07/messages", {"text": "x" * 200001})
        self.assertEqual(status, 400)
        status, res = self.h.post("/api/agents/agent-07/tasks", {"title": "No prompt"})
        self.assertEqual(status, 400)
        status, res = self.h.post("/api/agents/agent-07/tasks", {"title": "T", "prompt": "p", "priority": "urgent!!"})
        self.assertEqual(status, 400)

    def test_errors_do_not_leak_internals(self):
        status, res = self.h.get("/api/agents/agent-08")
        text = json.dumps(res)
        for leak in ("Traceback", "File \"", self.h.tmp, "sqlite"):
            self.assertNotIn(leak, text)

    def test_static_files_cannot_escape_the_static_folder(self):
        for path in ("/../server.py", "/..%2Fserver.py", "/..%5C..%5C.env", "/%2e%2e/%2e%2e/.env", "/.env", "/../.env",
                     "/assets/../../.env", "/..\\.env", "/../data/agent_hq.db", "/../agent_hq/app.py"):
            status, payload, _ = self.raw("GET", path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"GROQ", payload)
        status, payload, headers = self.raw("GET", "/")
        self.assertEqual(status, 200)
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_there_is_no_command_execution_endpoint(self):
        for path in ("/api/exec", "/api/shell", "/api/command", "/api/run", "/api/eval", "/api/launch-suite", "/api/key",
                     "/api/transcribe", "/api/groq", "/api/video", "/api/brief"):
            self.assertEqual(self.h.post(path, {"command": "whoami"})[0], 404, path)


class WorkspaceAndPermissionTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def test_working_folder_must_be_inside_an_allowed_folder(self):
        h = self.h
        outside = os.path.join(h.tmp, "elsewhere")
        os.makedirs(outside)
        status, res = h.patch("/api/agents/agent-01", {"working_directory": outside})
        self.assertEqual(status, 400, res)
        status, res = h.patch("/api/agents/agent-01", {"working_directory": os.path.join(h.workspace, "..", "elsewhere")})
        self.assertEqual(status, 400)
        status, res = h.patch("/api/agents/agent-01", {"working_directory": os.path.join(h.workspace, "missing-folder")})
        self.assertEqual(status, 400)
        status, res = h.patch("/api/agents/agent-01", {"working_directory": os.path.join(h.tmp, "data")})
        self.assertEqual(status, 400, "the application's own data folder is never a workspace")
        inside = os.path.join(h.workspace, "project-a")
        os.makedirs(inside)
        status, res = h.patch("/api/agents/agent-01", {"working_directory": inside})
        self.assertEqual(status, 200, res)

    def test_private_folders_cannot_become_allowed_roots(self):
        h = self.h
        status, res = h.patch("/api/settings", {"allowed_roots": [h.workspace, os.path.join(h.tmp, "data")]})
        self.assertEqual(status, 400)
        status, res = h.patch("/api/settings", {"allowed_roots": [h.workspace, h.tmp]})
        self.assertEqual(status, 400, "a folder that contains the application's data is refused")
        status, res = h.patch("/api/settings", {"allowed_roots": [h.workspace, os.path.join(os.path.expanduser("~"), ".codex")]})
        self.assertEqual(status, 400, "Codex's private folder is refused")
        drive = os.path.splitdrive(h.tmp)[0] + os.sep
        status, res = h.patch("/api/settings", {"allowed_roots": [drive]})
        self.assertEqual(status, 400, "a whole drive is refused")

    def test_turn_parameters_follow_the_agents_permissions(self):
        h = self.h
        agent = h.app.agents.get("agent-01")
        run = {"prompt": "p", "working_directory": None, "attachments": None}
        params = h.app.execution._turn_params(agent, run, "thread-x", False)
        self.assertEqual(params["sandboxPolicy"]["type"], "readOnly")
        self.assertEqual(params["approvalPolicy"], "on-request")
        self.assertNotIn("dangerFullAccess", json.dumps(params))
        h.patch("/api/agents/agent-01", {"permissions": {"sandbox": "workspace-write", "network": True, "approval": "untrusted"}})
        agent = h.app.agents.get("agent-01")
        params = h.app.execution._turn_params(agent, run, "thread-x", False)
        policy = params["sandboxPolicy"]
        self.assertEqual(policy["type"], "workspaceWrite")
        self.assertTrue(policy["networkAccess"])
        self.assertEqual(params["approvalPolicy"], "untrusted")
        for root in policy["writableRoots"]:
            self.assertTrue(security.is_within(root, h.workspace) or security.is_within(root, h.outputs), root)

    def test_attachments_must_be_inside_the_working_folder(self):
        h = self.h
        with open(os.path.join(h.workspace, "notes.txt"), "w") as fh:
            fh.write("notes")
        with open(os.path.join(h.tmp, "outside.txt"), "w") as fh:
            fh.write("outside")
        for bad in ("../outside.txt", "..\\outside.txt", "sub/..\\../outside.txt",
                    os.path.join(h.tmp, "outside.txt"), "../data/agent_hq.db", "missing.txt"):
            status, res = h.post("/api/agents/agent-01/messages", {"text": "read this", "attachments": [bad]})
            self.assertEqual(status, 400, bad)
        self.assertEqual(h.app.adapter.inference_requests, 0)
        status, res = h.post("/api/agents/agent-01/messages", {"text": "read this", "attachments": ["notes.txt"]})
        self.assertEqual(status, 200, res)
        h.wait_run(res["run"]["id"])
        status, res = h.get("/api/agents/agent-01/files")
        self.assertIn("notes.txt", res["files"])

    def test_tool_from_an_integration_that_is_not_allowed_is_stopped(self):
        h = self.h
        status, res = h.post("/api/agents/agent-02/messages", {"text": "[mcp] use the mock tool"})
        run = h.wait_run(res["run"]["id"])
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_kind"], "policy")
        self.assertIn("mock_tools", run["error_message"])
        # Once the user allows that integration for this agent, the same request goes through.
        h.patch("/api/agents/agent-02", {"allowed_tools": ["mock_tools"]})
        status, res = h.post("/api/agents/agent-02/messages", {"text": "[mcp] use the mock tool"})
        self.assertEqual(h.wait_run(res["run"]["id"])["status"], "completed")

    def test_secrets_never_reach_the_log_or_events(self):
        h = self.h
        secret = "sk-testsecret0123456789abcdefghijklmnop"
        status, res = h.post("/api/agents/agent-03/messages", {"text": "[fail] my key is %s" % secret})
        run = h.wait_run(res["run"]["id"])
        h.save_task("agent-04", title="Deploy with %s" % secret, prompt="noop")
        status, res = h.post("/api/agents/agent-04/run")
        h.wait_run(res["run"]["id"])
        dump = json.dumps(h.app.bus.since(0)) + json.dumps(h.app.bus.log_entries())
        self.assertNotIn(secret, dump)
        outputs = h.app.outputs.list(agent_id="agent-04")
        self.assertNotIn(secret, json.dumps(outputs))
        self.assertEqual(len(outputs), 1)
        with open(outputs[0]["file_path"], encoding="utf-8") as fh:
            self.assertNotIn(secret, fh.read())
        self.assertNotIn("testsecret", outputs[0]["file_name"])
        transcript = json.dumps(h.app.conversations.list("agent-03"))
        self.assertNotIn(secret, transcript, "the stored chat transcript masks credentials too")
        status, res = h.get("/api/agents/agent-03/history")
        self.assertNotIn(secret, json.dumps(res))

    def test_outputs_download_open_and_reveal_are_bounded(self):
        h = self.h
        h.save_task("agent-01", title="Report <script>alert(1)</script>", prompt="write")
        status, res = h.post("/api/agents/agent-01/run")
        h.wait_run(res["run"]["id"])
        out = h.get("/api/agents/agent-01/outputs")[1]["outputs"][0]
        self.assertNotIn("<", out["file_name"])
        status, payload, headers = h.get("/api/outputs/%s/download" % out["id"], raw=True)
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn(b"MOCK reply", payload)
        # A record whose file was moved out of the allowed folders is refused, not followed.
        h.app.db.execute("UPDATE outputs SET verified_file_path = ? WHERE id = ?",
                         (os.path.join(h.tmp, "data", "agent_hq.db"), out["id"]))
        status, payload, headers = h.get("/api/outputs/%s/download" % out["id"], raw=True)
        self.assertNotEqual(status, 200)
        self.assertNotIn(b"SQLite format", payload)
        self.assertNotEqual(h.post("/api/outputs/%s/open" % out["id"])[0], 200)
        self.assertNotEqual(h.post("/api/outputs/%s/reveal" % out["id"])[0], 200)
        # A file that no longer exists is reported, never invented.
        h.app.db.execute("UPDATE outputs SET verified_file_path = ? WHERE id = ?",
                         (os.path.join(h.outputs, "agent-01", "gone.md"), out["id"]))
        status, res = h.get("/api/outputs/%s" % out["id"])
        self.assertEqual(status, 200)
        self.assertFalse(res["output"]["file_exists"])

    def test_history_is_cleared_only_with_confirmation(self):
        h = self.h
        status, res = h.post("/api/agents/agent-05/messages", {"text": "remember me"})
        h.wait_run(res["run"]["id"])
        status, res = h.post("/api/history/clear", {"agent_id": "agent-05"})
        self.assertEqual(status, 400)
        self.assertEqual(res["error"]["code"], "confirmation_required")
        self.assertGreaterEqual(len(h.app.conversations.list("agent-05")), 2)
        thread = h.app.threads.active("agent-05")["provider_thread_id"]
        status, res = h.post("/api/history/clear", {"agent_id": "agent-05", "confirm": True})
        self.assertEqual(status, 200, res)
        self.assertEqual(h.app.conversations.list("agent-05"), [])
        self.assertEqual(h.app.threads.active("agent-05")["provider_thread_id"], thread,
                         "clearing AGENTS HQ's local history does not detach the Codex thread")


if __name__ == "__main__":
    unittest.main()
