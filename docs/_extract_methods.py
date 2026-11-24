import json
from pathlib import Path
root = Path(__file__).parent / "codex-schema"
data = json.loads((root / "ClientRequest.json").read_text(encoding="utf-8"))
methods = []
for item in data.get("oneOf", data.get("anyOf", [])):
    props = item.get("properties", {})
    m = props.get("method", {})
    enum = m.get("enum") or m.get("const")
    if isinstance(enum, list):
        methods.extend(enum)
    elif isinstance(enum, str):
        methods.append(enum)
methods = sorted(set(methods))
(root / "METHODS.txt").write_text("\n".join(methods) + "\n", encoding="utf-8")
print("count", len(methods))
for m in methods:
    print(m)

# also notifications
notif = json.loads((root / "ServerNotification.json").read_text(encoding="utf-8"))
nmethods = []
for item in notif.get("oneOf", notif.get("anyOf", [])):
    props = item.get("properties", {})
    m = props.get("method", {})
    enum = m.get("enum") or m.get("const")
    if isinstance(enum, list):
        nmethods.extend(enum)
    elif isinstance(enum, str):
        nmethods.append(enum)
nmethods = sorted(set(nmethods))
(root / "NOTIFICATIONS.txt").write_text("\n".join(nmethods) + "\n", encoding="utf-8")
print("notifications", len(nmethods))
for m in nmethods:
    if any(x in m for x in ("turn", "thread", "agent", "account", "error", "command", "file", "approval")):
        print("N", m)
