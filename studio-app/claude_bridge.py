"""Verbindung zu den KI-Motoren (Claude Code, Codex): Aufträge ausführen, Fortschritt sammeln, Anmeldung."""

import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

import platform_support as ps
from engines import RunState, engine_for, resolve_model, valid_session_id

MAX_ITEMS = 600
MAX_STDERR_CHARS = 4000
AUTH_CACHE_SECONDS = 30
LOGIN_HINT = re.compile(r"log ?in|logged out|api key|authenticat|anmeld|unauthori[sz]ed|oauth", re.IGNORECASE)
URL_PATTERN = re.compile(r"https://\S+")


class BusyError(Exception):
    """Es läuft bereits ein Auftrag."""


class EngineMissingError(Exception):
    """Der gewählte Motor (Claude Code oder Codex) wurde nicht gefunden."""

    def __init__(self, engine):
        super().__init__(engine.label)
        self.engine = engine


class StudioBridge:
    def __init__(self, studio_dir, data_dir):
        self.studio_dir = Path(studio_dir)
        self.data_dir = Path(data_dir)
        self._lock = threading.Condition()
        self._process = None
        self._stderr = ""
        self._auth_cache = {}
        self._login_process = None
        self._login_engine = None
        self._login_lines = []
        self._login_state = "idle"
        self.items = self._load_json("chat.json", [])
        self.sessions, self.engine_key = self._load_sessions()
        self.busy = False
        self._stopped = False

    # ------------------------------------------------------------ Persistenz

    def _load_json(self, name, default):
        try:
            return json.loads((self.data_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _load_sessions(self):
        data = self._load_json("session.json", {})
        data = data if isinstance(data, dict) else {}
        sessions = data.get("sessions")
        engine_key = data.get("engine")
        if not isinstance(sessions, dict):
            # Ältere Versionen kannten nur Claude: {"session_id": "..."}
            sessions = {"claude": data.get("session_id")}
            engine_key = "claude" if data.get("session_id") else None
        sessions = {key: value for key, value in sessions.items() if valid_session_id(value)}
        return sessions, engine_key

    def _save_json(self, name, data):
        target = self.data_dir / name
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, target)

    def _persist(self):
        self.items = self.items[-MAX_ITEMS:]
        self._save_json("chat.json", self.items)
        self._save_json("session.json", {"sessions": self.sessions, "engine": self.engine_key})

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

    def auth_status(self, engine_key="claude", force=False):
        engine = engine_for(engine_key)
        checked_at, cached = self._auth_cache.get(engine.key, (0.0, None))
        if cached is not None and not force and time.time() - checked_at < AUTH_CACHE_SECONDS:
            return cached
        command = engine.command()
        if not command:
            result = {"engine": engine.key, "installed": False, "logged_in": False}
        else:
            try:
                output = subprocess.run(
                    command + engine.auth_args(), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=30, env=ps.tool_environment(),
                    **ps.hidden_process_flags()
                )
                logged_in = engine.parse_auth(output.returncode, output.stdout, output.stderr)
            except (OSError, subprocess.SubprocessError):
                logged_in = False
            result = {"engine": engine.key, "installed": True, "logged_in": logged_in}
        self._auth_cache[engine.key] = (time.time(), result)
        return result

    # ------------------------------------------------------------ Aufträge

    def start_chat(self, message, model_choice):
        engine, model = resolve_model(model_choice)
        command = engine.command()
        if not command:
            raise EngineMissingError(engine)
        with self._lock:
            if self.busy:
                raise BusyError()
            self.busy = True
            if self.items and self.engine_key and self.engine_key != engine.key:
                self.items.append({"kind": "note", "text": "Ab hier arbeitet {0}. {0} kennt den bisherigen "
                                   "Verlauf dieses Gesprächs nicht.".format(engine.label)})
            self.engine_key = engine.key
            self.items.append({"kind": "user", "text": message})
            self._lock.notify_all()

        args = command + engine.chat_args(model, self.sessions.get(engine.key))
        session_flags = {} if ps.IS_WINDOWS else {"start_new_session": True}
        try:
            self._process = subprocess.Popen(
                args, cwd=str(self.studio_dir), env=ps.tool_environment(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **ps.hidden_process_flags(), **session_flags
            )
        except OSError as error:
            self._finish({"kind": "error", "text": "{} konnte nicht gestartet werden: {}".format(engine.label, error)})
            return
        threading.Thread(target=self._run, args=(self._process, message, engine), daemon=True).start()

    def _run(self, process, message, engine):
        self._stderr = ""
        threading.Thread(target=self._collect_stderr, args=(process,), daemon=True).start()
        try:
            process.stdin.write(message.encode("utf-8"))
            process.stdin.close()
        except OSError:
            pass

        run = RunState(self._add)
        for raw_line in process.stdout:
            event = self._parse(raw_line)
            if event is None:
                continue
            engine.consume(event, run)
            if run.session_id:
                self.sessions[engine.key] = run.session_id
        process.stdout.close()
        process.wait()
        self._finish(self._final_item(process.returncode, run, engine))

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

    def _final_item(self, return_code, run, engine):
        if run.success:
            return {"kind": "done", "cost": run.cost}
        if self._stopped or (return_code is not None and return_code < 0):
            return {"kind": "error", "text": "Auftrag abgebrochen."}
        text = (run.error_text or self._stderr.strip()
                or "{} hat den Auftrag mit einem Fehler beendet.".format(engine.label))
        needs_login = bool(LOGIN_HINT.search(text))
        if needs_login:
            self._auth_cache.pop(engine.key, None)
        return {"kind": "error", "text": text[-1500:], "needs_login": needs_login, "engine": engine.key}

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
        self._kill_tree(process)

    @staticmethod
    def _kill_tree(process):
        """Beendet einen Prozess samt Kindprozessen (Codex startet unter Node einen eigenen Prozess)."""
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
            self.sessions = {}
            self.engine_key = None
            self._persist()
            self._lock.notify_all()

    # ------------------------------------------------------------ Anmeldung

    def start_login(self, engine_key="claude"):
        engine = engine_for(engine_key)
        command = engine.command()
        if not command:
            raise EngineMissingError(engine)
        session_flags = {} if ps.IS_WINDOWS else {"start_new_session": True}
        with self._lock:
            previous = self._login_process
            if previous and previous.poll() is None:
                if self._login_engine == engine.key:
                    return
                # Ein laufendes "codex login" hält Port 1455 belegt – vor dem Wechsel sicher beenden.
                self._kill_tree(previous)
                try:
                    previous.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            self._login_lines = []
            self._login_engine = engine.key
            try:
                self._login_process = subprocess.Popen(
                    command + engine.login_args(), env=ps.tool_environment(),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    **ps.hidden_process_flags(), **session_flags
                )
            except OSError as error:
                self._login_process = None
                self._login_state = "failed"
                self._login_lines.append("{} konnte nicht gestartet werden: {}".format(engine.label, error))
                return
            self._login_state = "running"
        threading.Thread(target=self._run_login, args=(self._login_process, engine.key), daemon=True).start()

    def _run_login(self, process, engine_key):
        lines = self._login_lines
        for raw_line in process.stdout:
            line = raw_line.decode("utf-8", "replace").rstrip()
            if line:
                lines.append(line)
        process.wait()
        process.stdout.close()
        process.stdin.close()
        self._auth_cache.pop(engine_key, None)
        with self._lock:
            if process is self._login_process:
                self._login_state = "done" if process.returncode == 0 else "failed"

    def send_login_code(self, code):
        process = self._login_process
        if process and process.poll() is None:
            process.stdin.write((code.strip() + "\n").encode("utf-8"))
            process.stdin.flush()

    def login_snapshot(self):
        text = "\n".join(self._login_lines[-30:])
        urls = URL_PATTERN.findall(text)
        return {"state": self._login_state, "engine": self._login_engine,
                "output": text, "url": urls[-1] if urls else None}
