"""Mac install/process regressions. Never changes the user's Dock or Applications."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
if sys.platform != "darwin":
    raise unittest.SkipTest("macOS installation helpers")
sys.path.insert(0, str(REPO / "macos"))
import common as mac_common
import launcher as mac_launcher
import setup as mac_setup


class Dock:
    def __init__(self, tiles=()):
        self.tiles = list(tiles)
        self.calls = []

    def run(self, args, **kwargs):
        self.calls.append(args)
        if args[1] == "export":
            return subprocess.CompletedProcess(args, 0, plistlib.dumps({"persistent-apps": self.tiles}))
        if args[1] == "write":
            values = [plistlib.loads(value.encode()) for value in args[5:]]
            if args[4] == "-array-add":
                self.tiles.extend(values)
            else:
                self.tiles = values
        return subprocess.CompletedProcess(args, 0, b"")


class MacInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "AGENTS HQ's checkout"
        self.root.mkdir()
        shutil.copytree(REPO / "macos/AGENTS HQ.app", self.root / "macos/AGENTS HQ.app")
        for name in ("start.command", "macos/bootstrap.sh", "macos/Install AGENTS HQ.command",
                     "macos/Add to Dock.command", "macos/Stop AGENTS HQ.command"):
            (self.root / name).write_text("#!/bin/bash\n")
        self.home = self.base / "Test User"
        self.home.mkdir()
        self.dock = Dock()
        self.env = mock.patch.dict(os.environ, {key: "" for key in
            ("PORT", "AGENT_HQ_DATA", "AGENT_HQ_WORKSPACE", "AGENT_HQ_OUTPUTS")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_install_repairs_permissions_and_creates_portable_shortcuts(self):
        exe = self.root / "macos/AGENTS HQ.app/Contents/MacOS/AGENTS HQ"
        exe.chmod(0o644)
        app = mac_setup.install(self.root, self.home, run=self.dock.run)
        self.assertEqual(app, self.home / "Applications/AGENTS HQ.app")
        self.assertTrue(app.joinpath("Contents/MacOS/AGENTS HQ").stat().st_mode & 0o111)
        self.assertTrue(exe.stat().st_mode & 0o111)
        with app.joinpath("Contents/Resources/install.plist").open("rb") as stream:
            self.assertEqual(plistlib.load(stream)["ProjectRoot"], str(self.root))
        self.assertEqual((self.home / "Desktop/AGENTS HQ.app").resolve(), app)
        self.assertEqual(len(self.dock.tiles), 1)

    def test_reinstall_does_not_duplicate_or_restart_an_unchanged_dock(self):
        mac_setup.install(self.root, self.home, run=self.dock.run)
        self.dock.calls.clear()
        mac_setup.install(self.root, self.home, run=self.dock.run)
        self.assertEqual(len(self.dock.tiles), 1)
        self.assertFalse(any(args[0] == "/usr/bin/killall" for args in self.dock.calls))

    def test_unrelated_application_is_not_overwritten(self):
        app = self.home / "Applications/AGENTS HQ.app"
        app.joinpath("Contents").mkdir(parents=True)
        app.joinpath("Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "other.app"}))
        with self.assertRaisesRegex(RuntimeError, "unrelated"):
            mac_setup.install(self.root, self.home, run=self.dock.run)
        self.assertEqual(mac_setup.bundle_id(app), "other.app")

    def test_existing_desktop_file_is_preserved(self):
        path = self.home / "Desktop/AGENTS HQ.app"
        path.parent.mkdir()
        path.write_text("a user file")
        mac_setup.install(self.root, self.home, run=self.dock.run)
        self.assertEqual(path.read_text(), "a user file")

    def test_dock_relocation_preserves_other_apps_order_and_guid(self):
        foreign = {"GUID": 42, "tile-type": "file-tile", "tile-data": {"bundle-identifier": "other.app"}}
        old = mac_setup.dock_tile(self.base / "Old.app", guid=123)
        self.dock.tiles = [foreign, old, mac_setup.dock_tile(self.base / "Duplicate.app")]
        app = self.home / "Applications/AGENTS HQ.app"
        mac_setup.update_dock(app, self.base / "backups", self.dock.run)
        self.assertEqual(len(self.dock.tiles), 2)
        self.assertEqual(self.dock.tiles[0], foreign)
        self.assertEqual(self.dock.tiles[1]["GUID"], 123)
        self.assertEqual(self.dock.tiles[1]["tile-data"]["file-data"]["_CFURLString"], app.as_uri() + "/")

    def test_install_can_leave_dock_and_desktop_unchanged(self):
        mac_setup.install(self.root, self.home, pin=False, desktop=False, run=self.dock.run)
        self.assertEqual(self.dock.calls, [])
        self.assertFalse((self.home / "Desktop").exists())


class MacProcessTests(unittest.TestCase):
    def test_unrelated_listener_is_preserved(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with mock.patch.object(mac_launcher.os, "kill") as kill:
                with self.assertRaisesRegex(RuntimeError, "No process was stopped"):
                    mac_launcher.require_free_port(port)
                kill.assert_not_called()
            self.assertEqual(listener.getsockname()[1], port)

    def test_pid_reuse_or_other_checkout_does_not_authorize_stop(self):
        config = mac_common.configuration()
        state = {"pid": 12345, "root": str(Path(config.root).resolve()), "port": 4181}
        with mock.patch.object(mac_common.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "/usr/bin/python3 other.py\n")):
            self.assertFalse(mac_common.owns_process(state, config))
        state["root"] = "/different/checkout"
        self.assertFalse(mac_common.owns_process(state, config))

    def test_only_owned_process_receives_a_stop_signal(self):
        config = mac_common.configuration()
        state = {"pid": 12345, "root": config.root, "port": 4181}
        with mock.patch.object(mac_launcher, "read_state", return_value=state), \
             mock.patch.object(mac_launcher, "owns_process", side_effect=[True, False]), \
             mock.patch.object(mac_launcher, "state_path") as path, \
             mock.patch.object(mac_launcher.os, "kill") as kill:
            self.assertTrue(mac_launcher.stop(config))
            kill.assert_called_once_with(12345, signal.SIGINT)
            path.return_value.unlink.assert_called_once()

    def test_reopening_owned_server_does_not_spawn_another_process(self):
        config = mac_common.configuration()
        state = {"pid": 12345, "root": config.root, "port": 49876}
        with mock.patch.object(mac_launcher, "read_state", return_value=state), \
             mock.patch.object(mac_launcher, "owns_process", return_value=True), \
             mock.patch.object(mac_launcher, "healthy", return_value=True), \
             mock.patch.object(mac_launcher.subprocess, "Popen") as spawn:
            self.assertEqual(mac_launcher.start(config), 49876)
            spawn.assert_not_called()


@unittest.skipUnless(sys.platform == "darwin", "macOS tools required")
class MacNativeTests(unittest.TestCase):
    def test_background_server_reopens_and_restarts_from_a_spaced_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "AGENTS HQ's live test"
            root.mkdir()
            shutil.copytree(REPO / "agent_hq", root / "agent_hq", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(REPO / "macos", root / "macos", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(REPO / "start.command", root / "start.command")
            (root / ".runtime").mkdir()
            (root / ".runtime/python").symlink_to(Path(sys.executable).parent.parent, target_is_directory=True)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            (root / ".env").write_text(f"PORT={port}\nAGENT_HQ_NO_AUTOCONNECT=1\nAGENT_HQ_MOCK_CODEX=1\n")
            env = os.environ.copy()
            for key in ("PORT", "AGENT_HQ_DATA", "AGENT_HQ_WORKSPACE", "AGENT_HQ_OUTPUTS", "AGENT_HQ_CODEX"):
                env.pop(key, None)
            env.update(AGENT_HQ_NO_AUTOCONNECT="1", AGENT_HQ_MOCK_CODEX="1")
            command = [str(root / ".runtime/python/bin/python3"), str(root / "macos/launcher.py"), "--no-open"]
            def launch(*args):
                return subprocess.run(command + list(args), cwd=root, env=env, capture_output=True, text=True, timeout=30)
            try:
                first = launch()
                self.assertEqual(first.returncode, 0, first.stderr)
                state = json.loads((root / "data/mac-server.json").read_text())
                self.assertTrue(mac_common.healthy(port))
                tty = subprocess.check_output(["/bin/ps", "-p", str(state["pid"]), "-o", "tty="], text=True).strip()
                self.assertIn(tty, ("?", "??"), "background server must not depend on Terminal")
                second = launch()
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(json.loads((root / "data/mac-server.json").read_text())["pid"], state["pid"])
                stopped = launch("--stop")
                self.assertEqual(stopped.returncode, 0, stopped.stderr)
                self.assertFalse(mac_common.healthy(port))
                # LaunchServices must actually run the installed app, not merely
                # accept an open request while a pre-existing server masks failure.
                app = mac_setup.install(root, root.parent / "test-user", pin=False, desktop=False)
                launched = subprocess.run(["/usr/bin/open", "-n", str(app), "--args", "--no-open"],
                                          capture_output=True, text=True, timeout=10)
                self.assertEqual(launched.returncode, 0, launched.stderr)
                for attempt in range(100):
                    if (root / "data/mac-server.json").exists() and mac_common.healthy(port):
                        break
                    time.sleep(.1)
                else:
                    self.fail("Installed app did not start its background server")
                self.assertNotEqual(json.loads((root / "data/mac-server.json").read_text())["pid"], state["pid"])
                self.assertEqual(launch("--stop").returncode, 0)
                # Quick restart must not fail because of the prior socket's TIME_WAIT.
                restarted = launch()
                self.assertEqual(restarted.returncode, 0, restarted.stderr)
                self.assertTrue(mac_common.healthy(port))
            finally:
                launch("--stop")

    def test_dock_property_list_arguments_work_without_touching_real_dock(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            domain = str(base / "fake-dock")
            Path(domain + ".plist").write_bytes(plistlib.dumps({"persistent-apps": []}))
            def run(args, **kwargs):
                if args[0] == "/usr/bin/killall":
                    return subprocess.CompletedProcess(args, 0, b"")
                return subprocess.run([domain if item == "com.apple.dock" else item for item in args], **kwargs)
            app = base / "AGENTS HQ's app.app"
            mac_setup.update_dock(app, base / "backup", run)
            result = subprocess.run(["/usr/bin/defaults", "export", domain, "-"], check=True, capture_output=True)
            tiles = plistlib.loads(result.stdout)["persistent-apps"]
            self.assertEqual(tiles[0]["tile-data"]["file-data"]["_CFURLString"], app.as_uri() + "/")

    def test_bootstrap_rejects_bad_download_and_preserves_existing_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.joinpath("macos").mkdir()
            fake_curl = root / "fake-curl"
            fake_curl.write_text('#!/bin/bash\nfor arg in "$@"; do destination="$arg"; done\nprintf bad > "$destination"\n')
            fake_curl.chmod(0o755)
            script = (REPO / "macos/bootstrap.sh").read_text().replace('/usr/bin/curl ', '"' + str(fake_curl) + '" ')
            bootstrap = root / "macos/bootstrap.sh"
            bootstrap.write_text(script)
            python = root / ".runtime/python/bin/python3"
            python.parent.mkdir(parents=True)
            python.write_text("#!/bin/bash\nexit 1\n")
            python.chmod(0o755)
            result = subprocess.run(["/bin/bash", str(bootstrap)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum did not match", result.stderr)
            self.assertEqual(python.read_text(), "#!/bin/bash\nexit 1\n")
            self.assertFalse((root / ".runtime/bootstrap.lock").exists())


if __name__ == "__main__":
    unittest.main()
