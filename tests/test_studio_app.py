"""Tests für die Studio-App: Logik, HTTP-Schnittstelle und Oberfläche im Browser.

Aufruf:  <venv-python> -m unittest discover -s tests -v
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio-app"))
os.environ["CMG_CLAUDE_BIN"] = str(ROOT / "tests" / "fake_claude.py")

import studio_app  # noqa: E402
from claude_bridge import describe_tool  # noqa: E402

WAIT_SECONDS = 20


class HelperTests(unittest.TestCase):
    def test_describe_tool_translates_common_tools(self):
        self.assertEqual(describe_tool("Write", {"file_path": "/a/b/scene.html"})[0], "Erstellt scene.html")
        self.assertEqual(describe_tool("Read", {"file_path": "frames/f1.png"})[0], "Prüft Bild f1.png")
        self.assertEqual(describe_tool("Bash", {"command": "ffmpeg -i x", "description": "Video kodieren"})[0],
                         "Führt aus: Video kodieren")
        self.assertEqual(describe_tool("Bash", {"command": ""})[0], "Führt aus: Befehl")

    def test_safe_upload_name_strips_paths_and_hidden_files(self):
        self.assertEqual(studio_app.safe_upload_name("..%2F..%2Fmusic.mp3"), "music.mp3")
        self.assertEqual(studio_app.safe_upload_name("Mein Song!.mp3"), "Mein Song_.mp3")
        self.assertIsNone(studio_app.safe_upload_name(".bashrc"))
        self.assertIsNone(studio_app.safe_upload_name(""))


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.studio = base / "studio"
        self.data = base / "data"
        for folder in (self.studio / "exports", self.studio / "assets", self.data):
            folder.mkdir(parents=True)
        self.server = studio_app.create_server(self.studio, self.data, port=0)
        self.port = self.server.server_address[1]
        self.token = self.server.token
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.bridge.stop()
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None, token=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        all_headers = {"Host": "127.0.0.1:{}".format(self.port)}
        if token:
            all_headers["X-Studio-Token"] = self.token
        all_headers.update(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body).encode("utf-8")
            all_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=all_headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data, response

    def wait_until_idle(self):
        deadline = time.time() + WAIT_SECONDS
        while time.time() < deadline:
            status, data, _ = self.request("GET", "/api/state?from=0")
            state = json.loads(data)
            if not state["busy"]:
                return state["items"]
            time.sleep(0.2)
        self.fail("Auftrag wurde nicht rechtzeitig fertig")


class SecurityTests(ServerTestCase):
    def test_hello_is_public(self):
        status, data, _ = self.request("GET", "/api/hello", token=False)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["app"], "motion-studio")

    def test_api_requires_token(self):
        status, _, _ = self.request("GET", "/api/state", token=False)
        self.assertEqual(status, 403)

    def test_foreign_host_is_rejected(self):
        status, _, _ = self.request("GET", "/api/state", headers={"Host": "evil.example:{}".format(self.port)})
        self.assertEqual(status, 403)

    def test_foreign_origin_is_rejected(self):
        status, _, _ = self.request("POST", "/api/ping", body={}, headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)

    def test_media_path_traversal_is_rejected(self):
        (self.studio / "secret.mp4").write_bytes(b"x")
        status, _, _ = self.request("GET", "/media/exports/..%2Fsecret.mp4")
        self.assertEqual(status, 404)

    def test_index_contains_token(self):
        status, data, _ = self.request("GET", "/", token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.token.encode(), data)


class ChatTests(ServerTestCase):
    def test_chat_runs_and_resumes_session(self):
        status, _, _ = self.request("POST", "/api/chat", body={"message": "Hallo Studio", "model": "sonnet"})
        self.assertEqual(status, 200)
        items = self.wait_until_idle()
        kinds = [item["kind"] for item in items]
        self.assertEqual(kinds, ["user", "assistant", "tool", "done"])
        self.assertIn("resume=nein", items[1]["text"])
        self.assertEqual(items[2]["text"], "Erstellt fake.mp4")

        self.request("POST", "/api/chat", body={"message": "Weiter"})
        items = self.wait_until_idle()
        self.assertIn("resume=ja", items[5]["text"])
        self.assertTrue((self.data / "chat.json").exists())

    def test_login_error_is_flagged(self):
        self.request("POST", "/api/chat", body={"message": "bitte fehler"})
        items = self.wait_until_idle()
        self.assertEqual(items[-1]["kind"], "error")
        self.assertTrue(items[-1]["needs_login"])

    def test_second_chat_while_busy_conflicts_and_stop_works(self):
        self.request("POST", "/api/chat", body={"message": "langsam bitte"})
        status, _, _ = self.request("POST", "/api/chat", body={"message": "noch einer"})
        self.assertEqual(status, 409)
        self.request("POST", "/api/stop", body={})
        items = self.wait_until_idle()
        self.assertEqual(items[-1]["kind"], "error")
        self.assertIn("abgebrochen", items[-1]["text"])

    def test_reset_clears_conversation(self):
        self.request("POST", "/api/chat", body={"message": "Hallo"})
        self.wait_until_idle()
        self.request("POST", "/api/reset", body={})
        status, data, _ = self.request("GET", "/api/state?from=0")
        self.assertEqual(json.loads(data)["items"], [])


class FileTests(ServerTestCase):
    def test_media_supports_range_requests(self):
        (self.studio / "exports" / "clip.mp4").write_bytes(bytes(range(256)) * 4)
        status, data, response = self.request("GET", "/media/exports/clip.mp4", headers={"Range": "bytes=10-19"})
        self.assertEqual(status, 206)
        self.assertEqual(data, bytes(range(10, 20)))
        self.assertEqual(response.getheader("Content-Range"), "bytes 10-19/1024")

    def test_upload_lands_in_assets_with_safe_name(self):
        status, _, _ = self.request("POST", "/api/upload", body=b"ID3data",
                                    headers={"X-Filename": "..%2Fmusik.mp3", "Content-Type": "application/octet-stream"})
        self.assertEqual(status, 200)
        self.assertEqual((self.studio / "assets" / "musik.mp3").read_bytes(), b"ID3data")

    def test_upload_rejects_unknown_types(self):
        status, _, _ = self.request("POST", "/api/upload", body=b"x", headers={"X-Filename": "virus.exe"})
        self.assertEqual(status, 400)

    def test_files_lists_exports_and_assets(self):
        (self.studio / "exports" / "a.mp4").write_bytes(b"x")
        (self.studio / "assets" / "logo.png").write_bytes(b"x")
        _, data, _ = self.request("GET", "/api/files")
        listing = json.loads(data)
        self.assertEqual([f["name"] for f in listing["exports"]], ["a.mp4"])
        self.assertEqual(listing["assets"][0]["type"], "image")


class BrowserTests(ServerTestCase):
    """Bedient die Oberfläche wie ein Mensch (übersprungen, falls Playwright fehlt)."""

    def test_template_send_shows_answer_and_video(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright nicht installiert")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto("http://127.0.0.1:{}/".format(self.port))
                page.get_by_role("button", name="Showreel").click()
                self.assertIn("Showreel", page.locator("#prompt").input_value())
                page.get_by_role("button", name="Senden").click()
                page.locator(".done-note").wait_for(timeout=WAIT_SECONDS * 1000)
                self.assertIn("Verstanden", page.locator(".msg-assistant").first.inner_text())
                page.locator(".media-card video").first.wait_for(timeout=WAIT_SECONDS * 1000)
                self.assertTrue(page.locator("#login").is_hidden())
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
