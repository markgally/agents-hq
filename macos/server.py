"""Mac server process; independent from the app launcher and browser lifetime."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_hq.app import Server, main

if __name__ == "__main__":
    # Permit a quick restart after an owned server shuts down. Windows/Linux
    # entry points and the recovered backend bytecode are unchanged.
    Server.allow_reuse_address = True
    main()
