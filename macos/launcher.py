"""Start/reopen or stop only this checkout's background server; never kill a port."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

from common import ROOT, atomic_json, configuration, healthy, owns_process, read_state, show_error, state_path


def require_free_port(port):
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT must be between 1 and 65535.")
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(f"Port {port} is already in use. No process was stopped. "
                               "Choose a different PORT in the project's .env file and reopen AGENTS HQ.") from error


def start(config):
    existing = read_state(config)
    if owns_process(existing, config):
        port = existing["port"]
        for attempt in range(50):
            if healthy(port):
                return port
            if not owns_process(existing, config):
                break
            time.sleep(.2)
        else:
            raise RuntimeError("An AGENTS HQ server is already starting. Try reopening it shortly.")
    require_free_port(config.port)
    env = os.environ.copy()
    env.update(PORT=str(config.port), AGENT_HQ_DATA=config.data_dir,
               AGENT_HQ_WORKSPACE=config.default_workspace, AGENT_HQ_OUTPUTS=config.default_outputs,
               PYTHONUNBUFFERED="1")
    runtime = Path(config.root) / ".runtime/python/bin"
    # Finder/Dock launches do not inherit the user's interactive shell PATH.
    bins = (runtime, Path.home() / ".local/bin", Path.home() / ".cargo/bin",
            Path("/opt/homebrew/bin"), Path("/usr/local/bin"))
    env["PATH"] = os.pathsep.join(map(str, bins)) + os.pathsep + env.get("PATH", "")
    log_path = Path(config.data_dir) / "mac-server.log"
    with log_path.open("ab") as log:
        process = subprocess.Popen([str(runtime / "python3"), str(Path(config.root) / "macos/server.py")],
                                   cwd=config.root, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True)
    state = {"pid": process.pid, "port": config.port, "root": str(Path(config.root).resolve())}
    atomic_json(state_path(config), state)
    for attempt in range(100):
        if process.poll() is not None:
            raise RuntimeError("AGENTS HQ could not start. See " + str(log_path))
        if healthy(config.port):
            return config.port
        time.sleep(.2)
    raise RuntimeError("AGENTS HQ is taking longer than expected. See " + str(log_path))


def stop(config):
    state = read_state(config)
    if not owns_process(state, config):
        return False
    os.kill(state["pid"], signal.SIGINT)
    for attempt in range(100):
        if not owns_process(state, config):
            state_path(config).unlink(missing_ok=True)
            return True
        time.sleep(.1)
    raise RuntimeError("AGENTS HQ has not finished stopping. No other process was stopped.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-open", action="store_true", help="Start without opening the dashboard")
    args = parser.parse_args()
    config = configuration()
    Path(config.data_dir).mkdir(parents=True, exist_ok=True)
    with (Path(config.data_dir) / "mac-launcher.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.stop:
            stop(config)
        else:
            port = start(config)
            if not args.no_open:
                subprocess.run(["/usr/bin/open", f"http://127.0.0.1:{port}/"], check=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if "--no-open" in sys.argv:
            print(str(error), file=sys.stderr)
        else:
            show_error(error)
        sys.exit(1)
