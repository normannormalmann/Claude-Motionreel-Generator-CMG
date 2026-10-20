"""Simuliert die Codex-CLI für Tests (exec --json-Ausgabe, login-Befehle)."""

import json
import os
import sys
import time
from pathlib import Path

THREAD_ID = "test-thread-1"
REQUIRED_FLAGS = ("--json", "--skip-git-repo-check", "--ignore-user-config",
                  "--dangerously-bypass-approvals-and-sandbox")


def emit(event):
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def main():
    args = sys.argv[1:]
    if args[:2] == ["login", "status"]:
        if os.environ.get("CMG_FAKE_CODEX_LOGGED_OUT") == "1":
            print("Not logged in")
            return 1
        print("Logged in using ChatGPT")
        return 0
    if args[:1] == ["login"]:
        print("Starting local login server on http://localhost:1455.")
        print("If your browser did not open, navigate to this URL to authenticate:")
        print("https://auth.openai.com/oauth/authorize?test=1&code_challenge=abc")
        return 0
    if args[:1] != ["exec"] or args[-1] != "-" or not all(flag in args for flag in REQUIRED_FLAGS):
        sys.stderr.write("Unerwarteter Aufruf: {}\n".format(args))
        return 2

    message = sys.stdin.read()
    resumed = args[1] == "resume"
    model = args[args.index("-m") + 1]
    emit({"type": "thread.started", "thread_id": THREAD_ID})
    emit({"type": "turn.started"})
    if "langsam" in message:
        time.sleep(30)
    emit({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message",
          "text": "Codex: **{}** (resume={}, modell={})".format(message.strip()[:40], "ja" if resumed else "nein", model)}})
    command = {"id": "item_1", "type": "command_execution",
               "command": "\"C:\\\\Windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe\" -Command \"ffmpeg -version\"",
               "aggregated_output": "", "exit_code": None, "status": "in_progress"}
    emit({"type": "item.started", "item": command})
    emit({"type": "item.completed", "item": dict(command, exit_code=0, status="completed")})
    emit({"type": "item.completed", "item": {"id": "item_2", "type": "file_change", "status": "completed",
          "changes": [{"path": str(Path.cwd() / "exports" / "fake.mp4"), "kind": "add"}]}})
    exports = Path.cwd() / "exports"
    exports.mkdir(exist_ok=True)
    (exports / "fake.mp4").write_bytes(b"\x00" * 2048)
    if "fehler" in message:
        emit({"type": "error", "message": "unexpected status 401 Unauthorized: Please log in again"})
        emit({"type": "turn.failed", "error": {"message": "401 Unauthorized: Please log in again"}})
        return 1
    emit({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
