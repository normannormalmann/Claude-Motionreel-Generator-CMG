"""Ende-zu-Ende-Test des Updates: echtes Studio → Update-Helfer → Installer → Neustart.

Ein lokaler Webserver spielt GitHub und liefert eine neuere versions.json sowie einen
Test-Installer, der nur die neue versions.json in den App-Ordner schreibt.
"""

import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio-app"))

import stop_studio  # noqa: E402

TIMEOUT = 90
COMMIT = "0123456789abcdef0123456789abcdef01234567"
OLD = {"cmg": "1.0.0", "codex": "0.162.1",
       "python_packages": {"playwright": "1.64.0", "pillow": "13.0.0", "numpy": "2.5.4"}}
NEW = dict(OLD, cmg="99.0.0")
FAKE_PS1 = """if ($env:CMG_UPDATE -ne '1' -or $env:CMG_REF -ne '__COMMIT__') { exit 3 }
[IO.File]::WriteAllText((Join-Path $env:CMG_TEST_APP_DIR 'versions.json'), '{manifest}')
exit 0
"""
FAKE_SH = """#!/bin/bash
[ "$CMG_UPDATE" = "1" ] && [ "$CMG_REF" = "__COMMIT__" ] || exit 3
printf '%s' '{manifest}' > "$CMG_TEST_APP_DIR/versions.json"
"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class UpdateEndToEndTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.app = base / "app"
        shutil.copytree(ROOT / "studio-app", self.app, ignore=shutil.ignore_patterns("__pycache__"))
        (self.app / "versions.json").write_text(json.dumps(OLD), encoding="utf-8")
        self.data = base / ("Claude-Motion-Studio" if stop_studio.IS_WINDOWS else "claude-motion-studio")
        self._serve_fake_github(base / "github")
        self.env = dict(os.environ, CMG_STUDIO_DIR=str(base / "studio"), CMG_NO_BROWSER="1",
                        CMG_REPO_RAW=self.remote, CMG_TEST_APP_DIR=str(self.app),
                        CMG_CLAUDE_BIN=str(ROOT / "tests" / "fake_claude.py"))
        self.env["LOCALAPPDATA" if stop_studio.IS_WINDOWS else "XDG_DATA_HOME"] = str(base)
        self.env.pop("CMG_NO_UPDATE_CHECK", None)
        self.addCleanup(self._stop_all)

    def _serve_fake_github(self, folder):
        # Wie GitHub: aktueller Commit von main und alle Dateien unter /<commit>/…
        (folder / "commits").mkdir(parents=True)
        (folder / "commits" / "main").write_text(COMMIT, encoding="utf-8")
        files = folder / COMMIT
        files.mkdir()
        manifest = json.dumps(NEW)
        (files / "versions.json").write_text(manifest, encoding="utf-8")
        for name, script in (("install.ps1", FAKE_PS1), ("install.sh", FAKE_SH)):
            (files / name).write_text(script.replace("{manifest}", manifest).replace("__COMMIT__", COMMIT),
                                      encoding="utf-8")
        handler = functools.partial(QuietHandler, directory=str(folder))
        self.github = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.github.serve_forever, daemon=True).start()
        self.remote = "http://127.0.0.1:{}".format(self.github.server_address[1])

    def _stop_all(self):
        stop_studio.stop_studio(self.data)
        self.github.shutdown()
        self.github.server_close()
        time.sleep(0.5)

    def _wait_for_studio(self, other_than=None):
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            try:
                info = json.loads((self.data / "server.json").read_text(encoding="utf-8"))
                base = "http://127.0.0.1:{}/".format(info["port"])
                if info["port"] != other_than and stop_studio.is_running(base):
                    return base, info
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.3)
        self.fail("Studio ist nicht (neu) gestartet")

    @staticmethod
    def _session(base, info):
        _, headers, _ = stop_studio._get(base + "?k=" + info["key"])
        return headers.get("Set-Cookie").split(";")[0]

    @staticmethod
    def _call(base, cookie, path, body=None):
        headers = {"Cookie": cookie, "X-Studio-Request": "1", "Content-Type": "application/json"}
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(base + path, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_update_restarts_studio_with_new_version(self):
        studio = subprocess.Popen([sys.executable, str(self.app / "studio_app.py")], env=self.env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base, info = self._wait_for_studio()
        cookie = self._session(base, info)
        status = self._call(base, cookie, "api/update?force=1")
        self.assertTrue(status["available"], status)
        self.assertEqual((status["current"], status["latest"]), ("1.0.0", "99.0.0"))

        self.assertEqual(self._call(base, cookie, "api/update/start", {}), {"ok": True})
        studio.wait(timeout=TIMEOUT)  # das alte Studio beendet sich selbst

        new_base, new_info = self._wait_for_studio(other_than=info["port"])
        status = self._call(new_base, self._session(new_base, new_info), "api/update")
        self.assertTrue(status["result"]["ok"], status["result"])
        self.assertEqual(status["result"]["version"], "99.0.0")
        self.assertEqual(status["current"], "99.0.0")
        self.assertFalse(status["available"])


if __name__ == "__main__":
    unittest.main()
