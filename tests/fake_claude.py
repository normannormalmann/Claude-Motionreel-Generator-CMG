"""Simuliert die Claude-Code-CLI für Tests (stream-json-Ausgabe, auth-Befehle)."""

import json
import re
import sys
import time
from pathlib import Path

SESSION_ID = "test-session-1"
FOLDER_HINT = re.compile(r"exports/([\w-]+)/")


def emit(event):
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def main():
    args = sys.argv[1:]
    if args[:2] == ["auth", "status"]:
        emit({"loggedIn": True, "authMethod": "claude.ai"})
        return 0
    if args[:2] == ["auth", "login"]:
        print("Öffne https://claude.ai/oauth/authorize?test=1 im Browser")
        return 0

    message = sys.stdin.read()
    resumed = "--resume" in args
    # Wie das echte Claude: Ergebnisse in den Gesprächsordner, den das Studio vorgibt.
    match = FOLDER_HINT.search(" ".join(args))
    folder = match.group(1) if match else "ohne-ordner"
    emit({"type": "system", "subtype": "init", "session_id": SESSION_ID})
    if "langsam" in message:
        time.sleep(30)
    emit({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Verstanden: **{}** (resume={})".format(message.strip()[:40], "ja" if resumed else "nein")},
        {"type": "tool_use", "name": "Write", "input": {"file_path": "exports/{}/fake.mp4".format(folder)}},
    ]}})
    exports = Path.cwd() / "exports" / folder
    exports.mkdir(parents=True, exist_ok=True)
    (exports / "fake.mp4").write_bytes(b"\x00" * 2048)
    if "fehler" in message:
        emit({"type": "result", "subtype": "error_during_execution", "is_error": True,
              "result": "Invalid API key · Please run /login", "session_id": SESSION_ID})
        return 1
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "ok",
          "session_id": SESSION_ID, "total_cost_usd": 0.01})
    return 0


if __name__ == "__main__":
    sys.exit(main())
