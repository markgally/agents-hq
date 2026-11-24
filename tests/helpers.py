"""Shared test harness: a real AGENTS HQ server on a free port, backed by the mock Codex app server."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent_hq.app import AgentHQ, serve  # noqa: E402
from agent_hq.config import Config  # noqa: E402

MOCK = os.path.join(ROOT, "agent_hq", "codex", "mock_server.py")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerProcess(object):
    """AGENTS HQ as a real child process (mock Codex), so tests can kill it without any clean-up running."""

    def __init__(self, tmp, port=None, autoconnect=True, slow_steps=None):
        self.tmp = tmp
        self.port = port or free_port()
        self.base = "http://127.0.0.1:%d" % self.port
        env = dict(os.environ)
        env.update({
            "PORT": str(self.port), "AGENT_HQ_DATA": os.path.join(tmp, "data"),
            "AGENT_HQ_WORKSPACE": os.path.join(tmp, "workspace"), "AGENT_HQ_OUTPUTS": os.path.join(tmp, "outputs"),
            "AGENT_HQ_MOCK_CODEX": "1", "AGENT_HQ_NO_AUTOCONNECT": "" if autoconnect else "1",
            "MOCK_CODEX_STATE": os.path.join(tmp, "mock-codex"), "MOCK_CODEX_AUTH": "chatgpt", "MOCK_CODEX_DELAY": "0.01",
            "PYTHONIOENCODING": "utf-8",
        })
        if slow_steps:
            env["MOCK_CODEX_SLOW_STEPS"] = str(slow_steps)
        import subprocess
        self.proc = subprocess.Popen([sys.executable, "-m", "agent_hq"], cwd=ROOT, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.token = None
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                status, state = self.get("/api/state")
                self.token = state["token"]
                return
            except (OSError, ValueError):
                if self.proc.poll() is not None:
                    raise AssertionError("AGENTS HQ exited during start-up (code %s)" % self.proc.returncode)
                time.sleep(0.1)
        raise AssertionError("AGENTS HQ did not start")

    def request(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if method != "GET" and self.token:
            headers["X-AHQ-Token"] = self.token
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            exc.close()
            return exc.code, json.loads(payload.decode("utf-8"))

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body=None):
        return self.request("POST", path, body if body is not None else {})

    def patch(self, path, body):
        return self.request("PATCH", path, body)

    def agent(self, agent_id):
        return self.get("/api/agents/" + agent_id)[1]["agent"]

    def run(self, agent_id, run_id):
        runs = self.get("/api/agents/%s/history" % agent_id)[1]["runs"]
        return next(r for r in runs if r["id"] == run_id)

    def wait(self, predicate, timeout=20.0, message="condition"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.1)
        raise AssertionError("Timed out waiting for %s" % message)

    def kill(self):
        """Hard kill: no shutdown handlers run. The mock app server child is killed too (its pipe closes)."""
        self.proc.kill()
        self.proc.wait(10)
        time.sleep(0.5)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(10)


class Harness(object):
    """Starts AGENTS HQ against the mock app server in a throwaway folder."""

    def __init__(self, auth="chatgpt", connect=True, delay="0.005", tmp=None, port=None, scheduler_interval=3600.0,
                 codex_command=None):
        self.tmp = tmp or tempfile.mkdtemp(prefix="agent-hq-test-")
        self.owns_tmp = tmp is None
        self.port = port or free_port()
        os.environ["MOCK_CODEX_STATE"] = os.path.join(self.tmp, "mock-codex")
        os.environ["MOCK_CODEX_AUTH"] = auth
        os.environ["MOCK_CODEX_DELAY"] = delay
        self.workspace = os.path.join(self.tmp, "workspace")
        self.outputs = os.path.join(self.tmp, "outputs")
        self.config = Config(root=ROOT, data_dir=os.path.join(self.tmp, "data"), port=self.port,
                             codex_command=codex_command or [sys.executable, MOCK], autoconnect=False,
                             default_workspace=self.workspace, default_outputs=self.outputs,
                             scheduler_interval=scheduler_interval)
        self.app = AgentHQ(self.config)
        self.launched = []  # tests never open Explorer or documents; the request is recorded instead
        self.app.outputs.launch = lambda kind, path: self.launched.append((kind, path))
        self.server = serve(self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.app.start()
        self.base = "http://127.0.0.1:%d" % self.port
        self.token = self.app.token
        if connect:
            self.app.adapter.connect()

    # ---- HTTP
    def request(self, method, path, body=None, headers=None, token=True, raw=False):
        data = None
        hdrs = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        if token and method != "GET":
            hdrs["X-AHQ-Token"] = self.token
        hdrs.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                payload = res.read()
                if raw:
                    return res.status, payload, dict(res.headers)
                return res.status, json.loads(payload.decode("utf-8")) if payload else None
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            exc.close()
            if raw:
                return exc.code, payload, dict(exc.headers)
            try:
                return exc.code, json.loads(payload.decode("utf-8"))
            except ValueError:
                return exc.code, {"raw": payload.decode("utf-8", "replace")}

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body if body is not None else {}, **kw)

    def patch(self, path, body, **kw):
        return self.request("PATCH", path, body, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    # ---- waiting
    def wait(self, predicate, timeout=15.0, interval=0.05, message="condition"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(interval)
        raise AssertionError("Timed out waiting for %s" % message)

    def runtime(self, agent_id):
        return self.app.execution.agent_state(agent_id)

    def wait_idle(self, agent_id, timeout=15.0):
        return self.wait(lambda: not self.app.execution.open_runs(agent_id), timeout, message="%s to finish" % agent_id)

    def run_status(self, run_id):
        return self.app.execution.get(run_id)["status"]

    def wait_run(self, run_id, statuses=("completed", "failed", "interrupted", "cancelled", "rate_limited", "unknown"),
                 timeout=15.0):
        self.wait(lambda: self.run_status(run_id) in statuses, timeout, message="run %s to reach %s" % (run_id, statuses))
        return self.app.execution.get(run_id)

    def save_task(self, agent_id, title="Test task", prompt="Say hello", **extra):
        body = {"title": title, "prompt": prompt}
        body.update(extra)
        status, res = self.post("/api/agents/%s/tasks" % agent_id, body)
        assert status == 200, res
        return res["task"]

    # ---- shutdown
    def stop_server(self):
        """Stop the HTTP server and services but keep the data folder (to test restarts)."""
        self.server.shutdown()
        self.server.server_close()
        self.app.stop()

    def close(self):
        try:
            self.stop_server()
        finally:
            if self.owns_tmp:
                shutil.rmtree(self.tmp, ignore_errors=True)
