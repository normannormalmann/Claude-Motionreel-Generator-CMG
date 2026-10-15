"""Verbindung zu Claude Code: Aufträge ausführen, Fortschritt sammeln, Anmeldung."""

import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

import platform_support as ps

ALLOWED_MODELS = ("opus", "sonnet")
ALLOWED_TOOLS = ("Bash", "PowerShell", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "TodoWrite")
MAX_ITEMS = 600
MAX_STDERR_CHARS = 4000
AUTH_CACHE_SECONDS = 30
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
LOGIN_HINT = re.compile(r"log ?in|logged out|api key|authenticat|anmeld|unauthori[sz]ed|oauth", re.IGNORECASE)
URL_PATTERN = re.compile(r"https://\S+")

APP_SYSTEM_PROMPT = (
    "Du arbeitest im Motion Studio, einer grafischen Oberfläche. Die Person sieht keine Konsole, "
    "nur deine Textantworten und die Videos im Ordner exports. Antworte auf Deutsch, kurz und ohne "
    "Fachjargon. Brauchst du eine Entscheidung oder Freigabe, stelle die Frage am Ende deiner "
    "Antwort und warte auf die nächste Nachricht. Nenne fertige Videos immer mit ihrem Dateinamen."
)


class BusyError(Exception):
    """Es läuft bereits ein Auftrag."""


class ClaudeMissingError(Exception):
    """Claude Code wurde nicht gefunden."""


def describe_tool(name, tool_input):
    """Übersetzt einen Werkzeugaufruf in eine verständliche Zeile."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    filename = Path(path).name if path else ""
    if name == "Write":
        return "Erstellt " + filename, path
    if name in ("Edit", "MultiEdit"):
        return "Bearbeitet " + filename, path
    if name == "Read":
        verb = "Prüft Bild " if filename.lower().endswith(IMAGE_SUFFIXES) else "Liest "
        return verb + filename, path
    if name in ("Bash", "PowerShell"):
        command = str(tool_input.get("command", ""))
        first_line = command.splitlines()[0][:90] if command.strip() else "Befehl"
        label = tool_input.get("description") or first_line
        return "Führt aus: " + label, command
    if name in ("Glob", "Grep"):
        return "Sucht im Projekt", str(tool_input.get("pattern", ""))
    if name == "TodoWrite":
        return "Plant die Arbeitsschritte", ""
    return "Arbeitsschritt: " + name, ""


class StudioBridge:
    def __init__(self, studio_dir, data_dir):
        self.studio_dir = Path(studio_dir)
        self.data_dir = Path(data_dir)
        self._lock = threading.Condition()
        self._process = None
        self._stderr = ""
        self._auth_cache = (0.0, None)
        self._login_process = None
        self._login_lines = []
        self._login_state = "idle"
        self.items = self._load_json("chat.json", [])
        self.session_id = self._load_json("session.json", {}).get("session_id")
        self.busy = False
        self._stopped = False

    # ------------------------------------------------------------ Persistenz

    def _load_json(self, name, default):
        try:
            return json.loads((self.data_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _save_json(self, name, data):
        target = self.data_dir / name
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, target)

    def _persist(self):
        self.items = self.items[-MAX_ITEMS:]
        self._save_json("chat.json", self.items)
        self._save_json("session.json", {"session_id": self.session_id})

    def _add(self, item):
        with self._lock:
            self.items.append(item)
            self._lock.notify_all()

    # ------------------------------------------------------------ Status

    def snapshot(self, start):
        with self._lock:
            return {"items": self.items[start:], "next": len(self.items), "busy": self.busy}

    def wait_for_items(self, start, timeout):
        with self._lock:
            self._lock.wait_for(lambda: len(self.items) > start or not self.busy, timeout=timeout)
        return self.snapshot(start)

    def auth_status(self, force=False):
        checked_at, cached = self._auth_cache
        if cached is not None and not force and time.time() - checked_at < AUTH_CACHE_SECONDS:
            return cached
        command = ps.claude_command()
        if not command:
            result = {"installed": False, "logged_in": False}
        else:
            try:
                output = subprocess.run(
                    command + ["auth", "status", "--json"], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=30, env=ps.tool_environment(),
                    **ps.hidden_process_flags()
                )
                logged_in = bool(json.loads(output.stdout or "{}").get("loggedIn"))
            except (OSError, ValueError, subprocess.SubprocessError):
                logged_in = False
            result = {"installed": True, "logged_in": logged_in}
        self._auth_cache = (time.time(), result)
        return result

    # ------------------------------------------------------------ Aufträge

    def start_chat(self, message, model):
        command = ps.claude_command()
        if not command:
            raise ClaudeMissingError()
        model = model if model in ALLOWED_MODELS else ALLOWED_MODELS[0]
        with self._lock:
            if self.busy:
                raise BusyError()
            self.busy = True
            self.items.append({"kind": "user", "text": message})
            self._lock.notify_all()

        args = command + [
            "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--permission-mode", "acceptEdits",
            "--append-system-prompt", APP_SYSTEM_PROMPT,
        ]
        if self.session_id:
            args += ["--resume", self.session_id]
        args += ["--allowedTools"] + list(ALLOWED_TOOLS)

        session_flags = {} if ps.IS_WINDOWS else {"start_new_session": True}
        try:
            self._process = subprocess.Popen(
                args, cwd=str(self.studio_dir), env=ps.tool_environment(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **ps.hidden_process_flags(), **session_flags
            )
        except OSError as error:
            self._finish({"kind": "error", "text": "Claude konnte nicht gestartet werden: {}".format(error)})
            return
        threading.Thread(target=self._run, args=(self._process, message), daemon=True).start()

    def _run(self, process, message):
        self._stderr = ""
        threading.Thread(target=self._collect_stderr, args=(process,), daemon=True).start()
        try:
            process.stdin.write(message.encode("utf-8"))
            process.stdin.close()
        except OSError:
            pass

        final = None
        for raw_line in process.stdout:
            event = self._parse(raw_line)
            if event is None:
                continue
            if event.get("session_id"):
                self.session_id = event["session_id"]
            if event.get("type") == "result":
                final = event
            else:
                self._handle_event(event)
        process.stdout.close()
        process.wait()
        self._finish(self._final_item(process.returncode, final))

    def _collect_stderr(self, process):
        for raw_line in process.stderr:
            self._stderr = (self._stderr + raw_line.decode("utf-8", "replace"))[-MAX_STDERR_CHARS:]
        process.stderr.close()

    @staticmethod
    def _parse(raw_line):
        try:
            event = json.loads(raw_line.decode("utf-8", "replace"))
        except ValueError:
            return None
        return event if isinstance(event, dict) else None

    def _handle_event(self, event):
        if event.get("type") != "assistant":
            return
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                self._add({"kind": "assistant", "text": block["text"]})
            elif block.get("type") == "tool_use":
                label, detail = describe_tool(block.get("name", ""), block.get("input"))
                self._add({"kind": "tool", "text": label, "detail": detail})

    def _final_item(self, return_code, final):
        if final and not final.get("is_error") and final.get("subtype", "success") == "success":
            return {"kind": "done", "cost": final.get("total_cost_usd")}
        if self._stopped or (return_code is not None and return_code < 0):
            return {"kind": "error", "text": "Auftrag abgebrochen."}
        text = (final or {}).get("result") or self._stderr.strip() or "Claude hat den Auftrag mit einem Fehler beendet."
        needs_login = bool(LOGIN_HINT.search(text))
        if needs_login:
            self._auth_cache = (0.0, None)
        return {"kind": "error", "text": text[-1500:], "needs_login": needs_login}

    def _finish(self, item):
        with self._lock:
            self.items.append(item)
            self.busy = False
            self._process = None
            self._stopped = False
            self._persist()
            self._lock.notify_all()

    def stop(self):
        process = self._process
        if not process or process.poll() is not None:
            return
        self._stopped = True
        if ps.IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                           capture_output=True, **ps.hidden_process_flags())
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                process.terminate()

    def reset(self):
        with self._lock:
            if self.busy:
                raise BusyError()
            self.items = []
            self.session_id = None
            self._persist()
            self._lock.notify_all()

    # ------------------------------------------------------------ Anmeldung

    def start_login(self):
        command = ps.claude_command()
        if not command:
            raise ClaudeMissingError()
        if self._login_state == "running":
            return
        self._login_lines = []
        self._login_state = "running"
        self._login_process = subprocess.Popen(
            command + ["auth", "login"], env=ps.tool_environment(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            **ps.hidden_process_flags()
        )
        threading.Thread(target=self._run_login, args=(self._login_process,), daemon=True).start()

    def _run_login(self, process):
        for raw_line in process.stdout:
            line = raw_line.decode("utf-8", "replace").rstrip()
            if line:
                self._login_lines.append(line)
        process.wait()
        self._auth_cache = (0.0, None)
        self._login_state = "done" if process.returncode == 0 else "failed"

    def send_login_code(self, code):
        process = self._login_process
        if process and process.poll() is None:
            process.stdin.write((code.strip() + "\n").encode("utf-8"))
            process.stdin.flush()

    def login_snapshot(self):
        text = "\n".join(self._login_lines[-30:])
        urls = URL_PATTERN.findall(text)
        return {"state": self._login_state, "output": text, "url": urls[-1] if urls else None}
