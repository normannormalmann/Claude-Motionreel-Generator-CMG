"""Tests für stop_studio.py: beendet ein laufendes Studio vor einem Update – aber nie mitten im Auftrag.

Startet dafür ein echtes Studio als eigenen Prozess (mit dem Fake-Claude aus fake_claude.py).
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "studio-app"
sys.path.insert(0, str(APP_DIR))

import stop_studio  # noqa: E402

START_TIMEOUT = 60


class StopStudioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        env = dict(os.environ, CMG_STUDIO_DIR=str(base / "studio"),
                   CMG_CLAUDE_BIN=str(ROOT / "tests" / "fake_claude.py"))
        if stop_studio.IS_WINDOWS:
            env["LOCALAPPDATA"] = str(base)
            self.data_dir = base / "Claude-Motion-Studio"
        else:
            env["XDG_DATA_HOME"] = str(base)
            self.data_dir = base / "claude-motion-studio"
        group = {} if stop_studio.IS_WINDOWS else {"start_new_session": True}
        self.process = subprocess.Popen(
            [sys.executable, str(APP_DIR / "studio_app.py"), "--no-browser"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **group,
        )
        # Läuft auch, wenn setUp scheitert; vor dem Löschen des Temp-Ordners (umgekehrte Reihenfolge).
        self.addCleanup(self._kill_studio)
        self.base = self._wait_for_server()

    def _kill_studio(self):
        if self.process.poll() is None:
            if stop_studio.IS_WINDOWS:
                stop_studio._terminate(self.process.pid)
            else:
                os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=30)
        if not stop_studio.IS_WINDOWS:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)  # verwaiste Kindprozesse (Fake-Claude)
            except OSError:
                pass
        time.sleep(0.5)  # Windows gibt Dateien erst kurz nach dem Prozessende frei.

    def _wait_for_server(self):
        deadline = time.time() + START_TIMEOUT
        info_file = self.data_dir / "server.json"
        while time.time() < deadline:
            try:
                info = json.loads(info_file.read_text(encoding="utf-8"))
                base = "http://127.0.0.1:{}/".format(info["port"])
                if stop_studio.is_running(base):
                    self.info = info
                    return base
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.2)
        self.fail("Studio ist nicht gestartet")

    def _start_slow_job(self):
        _, headers, _ = stop_studio._get(self.base + "?k=" + self.info["key"])
        cookie = headers.get("Set-Cookie").split(";")[0]
        request = urllib.request.Request(
            self.base + "api/chat", data=json.dumps({"message": "langsam bitte"}).encode("utf-8"),
            headers={"Cookie": cookie, "X-Studio-Request": "1", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
        self.assertTrue(stop_studio.is_busy(self.base, self.info["key"]))

    def test_port_owner_is_the_studio_process(self):
        pid, command = stop_studio.port_owner(self.info["port"])
        self.assertIn("studio_app.py", command)
        self.assertIsNone(self.process.poll())
        self.assertIsInstance(pid, int)

    def test_idle_studio_is_stopped_and_server_file_removed(self):
        self.assertFalse(stop_studio.is_busy(self.base, self.info["key"]))
        code, message = stop_studio.stop_studio(self.data_dir)
        self.assertEqual(code, stop_studio.EXIT_STOPPED, message)
        self.assertIsNotNone(self.process.wait(timeout=30))
        self.assertFalse((self.data_dir / "server.json").exists())

    def test_busy_studio_is_left_running(self):
        self._start_slow_job()
        code, _ = stop_studio.stop_studio(self.data_dir)
        self.assertEqual(code, stop_studio.EXIT_BUSY)
        self.assertIsNone(self.process.poll())
        self.assertTrue(stop_studio.is_running(self.base))

    def test_wrong_launch_key_does_not_count_as_idle(self):
        self.assertIsNone(stop_studio.is_busy(self.base, "falsch"))

    def test_nothing_to_do_without_running_studio(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(stop_studio.stop_studio(empty)[0], stop_studio.EXIT_STOPPED)
            stale = Path(empty) / "server.json"
            stale.write_text(json.dumps({"port": 9, "key": "x"}), encoding="utf-8")
            self.assertEqual(stop_studio.stop_studio(empty)[0], stop_studio.EXIT_STOPPED)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
