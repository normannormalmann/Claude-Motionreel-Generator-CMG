"""Tests für die Studio-App: Logik, HTTP-Schnittstelle, Sicherheit und Oberfläche im Browser.

Aufruf:  <venv-python> -m unittest discover -s tests -v
"""

import http.client
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio-app"))
os.environ["CMG_CLAUDE_BIN"] = str(ROOT / "tests" / "fake_claude.py")
os.environ["CMG_CODEX_BIN"] = str(ROOT / "tests" / "fake_codex.py")

import engines  # noqa: E402
import media_files  # noqa: E402
import studio_app  # noqa: E402
import updates  # noqa: E402
from claude_bridge import StudioBridge, conversation_folder_name  # noqa: E402
from engines import describe_codex_item, describe_tool, resolve_model, unwrap_shell  # noqa: E402

WAIT_SECONDS = 20
REPO_MANIFEST = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
NEWER_MANIFEST = dict(REPO_MANIFEST, cmg="99.0.0")


class HelperTests(unittest.TestCase):
    def test_describe_tool_translates_common_tools(self):
        self.assertEqual(describe_tool("Write", {"file_path": "/a/b/scene.html"})[0], "Erstellt scene.html")
        self.assertEqual(describe_tool("Read", {"file_path": "frames/f1.png"})[0], "Prüft Bild f1.png")
        self.assertEqual(describe_tool("Bash", {"command": "ffmpeg -i x", "description": "Video kodieren"})[0],
                         "Führt aus: Video kodieren")
        self.assertEqual(describe_tool("Bash", {"command": ""})[0], "Führt aus: Befehl")

    def test_unwrap_shell_removes_codex_shell_wrappers(self):
        windows = '"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "ffmpeg -i a.mp4"'
        self.assertEqual(unwrap_shell(windows), "ffmpeg -i a.mp4")
        self.assertEqual(unwrap_shell("/bin/bash -lc 'python render.py --preview'"), "python render.py --preview")
        self.assertEqual(unwrap_shell("python render.py -c config.json"), "python render.py -c config.json")

    def test_describe_codex_item_translates_steps(self):
        files = {"type": "file_change", "changes": [{"path": "/s/scene.html", "kind": "add"},
                                                    {"path": "/s/style.css", "kind": "update"}]}
        self.assertEqual(describe_codex_item(files)[0], "Erstellt scene.html (+1 weitere)")
        self.assertEqual(describe_codex_item({"type": "command_execution", "command": "bash -lc 'ls'"})[0],
                         "Führt aus: ls")
        self.assertEqual(describe_codex_item({"type": "todo_list", "items": []})[0], "Plant die Arbeitsschritte")
        self.assertIsNone(describe_codex_item({"type": "reasoning", "text": "..."}))
        self.assertIsNone(describe_codex_item({"type": "error", "message": "Warnung"}))

    def test_resolve_model_maps_choices_and_falls_back(self):
        self.assertEqual((resolve_model("codex-max")[0].key, resolve_model("codex-max")[1]), ("codex", "gpt-6-astra"))
        self.assertEqual((resolve_model("sonnet")[0].key, resolve_model("sonnet")[1]), ("claude", "sonnet"))
        self.assertEqual((resolve_model("gibt-es-nicht")[0].key, resolve_model("gibt-es-nicht")[1]), ("claude", "opus"))

    def test_codex_auth_status_parsing(self):
        parse = engines.CodexEngine.parse_auth
        self.assertTrue(parse(0, "Logged in using ChatGPT", ""))
        self.assertTrue(parse(0, "", "Logged in using an API key"))
        self.assertFalse(parse(1, "Not logged in", ""))
        self.assertFalse(parse(0, "Not logged in", ""))

    def test_claude_auth_status_ignores_stderr_noise(self):
        parse = engines.ClaudeEngine.parse_auth
        self.assertTrue(parse(0, '{"loggedIn": true}', "(node:123) Warning: something"))
        self.assertFalse(parse(0, "[]", ""))

    def test_codex_runs_without_web_search_apps_and_mcp(self):
        args = engines.CodexEngine().chat_args("gpt-6.1-sol", None)
        for value in ('web_search="disabled"', "features.apps=false", "mcp_servers={}"):
            self.assertEqual(args[args.index(value) - 1], "-c")

    def test_session_ids_are_validated(self):
        self.assertTrue(engines.valid_session_id("00000000-1111-4222-8333-444444444444"))
        self.assertFalse(engines.valid_session_id("--dangerous-flag"))
        self.assertFalse(engines.valid_session_id("a b c d e f g h"))
        self.assertFalse(engines.valid_session_id(None))

    def test_old_single_session_file_is_migrated(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "session.json").write_text(json.dumps({"session_id": "alt-session-1"}), encoding="utf-8")
            bridge = StudioBridge(temp, temp)
            self.assertEqual(bridge.sessions, {"claude": "alt-session-1"})
            self.assertEqual(bridge.engine_key, "claude")

    def test_invalid_stored_session_ids_are_dropped(self):
        with tempfile.TemporaryDirectory() as temp:
            data = {"sessions": {"codex": "--evil", "claude": "test-session-1"}, "engine": "codex"}
            (Path(temp) / "session.json").write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(StudioBridge(temp, temp).sessions, {"claude": "test-session-1"})

    def test_every_run_gets_preview_rule_and_conversation_folder(self):
        for engine in (engines.ClaudeEngine(), engines.CodexEngine()):
            args = engine.chat_args("m", None, "2026-10-20_1412_Intro")
            # Codex bekommt die Anweisungen als JSON-String (TOML-kompatibel, Umlaute maskiert).
            joined = " ".join(json.loads(a.split("=", 1)[1]) if a.startswith("developer_instructions=") else a
                              for a in args)
            self.assertIn("_vorschau.mp4", joined)
            self.assertIn("ausdrücklich", joined)
            self.assertIn("exports/2026-10-20_1412_Intro/", joined)
            self.assertIn("projekte/2026-10-20_1412_Intro/", joined)
        self.assertNotIn("exports/", " ".join(engines.ClaudeEngine().chat_args("m", None)).replace("im Ordner exports", ""))

    def test_conversation_folder_names_are_safe_and_unique(self):
        with tempfile.TemporaryDirectory() as temp:
            name = conversation_folder_name("../../Geheim: Intro für „Café“!", [temp], 0)
            self.assertTrue(name.endswith("_Geheim-Intro-für-Café"), name)
            self.assertNotIn("/", name)
            self.assertNotIn(".", name)
            (Path(temp) / name).mkdir()
            self.assertEqual(conversation_folder_name("../../Geheim: Intro für „Café“!", [temp], 0), name + "-2")
            self.assertTrue(conversation_folder_name("", [temp], 0).endswith("_Gespraech"))
            with tempfile.TemporaryDirectory() as projects:
                (Path(projects) / (name + "-2")).mkdir()
                self.assertEqual(conversation_folder_name("../../Geheim: Intro für „Café“!", [temp, projects], 0),
                                 name + "-3")

    def test_stored_folder_must_be_a_plain_name(self):
        with tempfile.TemporaryDirectory() as temp:
            for bad in ("../ausserhalb", "a/b", ".versteckt", 42):
                (Path(temp) / "session.json").write_text(json.dumps({"sessions": {}, "folder": bad}), encoding="utf-8")
                self.assertIsNone(StudioBridge(temp, temp).folder, bad)

    def test_safe_upload_name_strips_paths_hidden_files_and_devices(self):
        self.assertEqual(media_files.safe_upload_name("..%2F..%2Fmusic.mp3"), "music.mp3")
        self.assertEqual(media_files.safe_upload_name("Mein Song!.mp3"), "Mein Song_.mp3")
        self.assertIsNone(media_files.safe_upload_name(".bashrc"))
        self.assertIsNone(media_files.safe_upload_name(""))
        self.assertIsNone(media_files.safe_upload_name("CON.mp3"))
        self.assertIsNone(media_files.safe_upload_name("nul.png"))

    def test_parse_range(self):
        self.assertEqual(media_files.parse_range("bytes=10-19", 100), (10, 19, True))
        self.assertEqual(media_files.parse_range("bytes=-10", 100), (90, 99, True))
        self.assertEqual(media_files.parse_range(None, 100), (0, 99, False))
        self.assertIsNone(media_files.parse_range("bytes=200-", 100))

    def test_interrupted_upload_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "song.mp3"
            target.write_bytes(b"alt")
            with self.assertRaises(media_files.UploadError):
                media_files.save_upload(io.BytesIO(b"neu"), 10, target)
            self.assertEqual(target.read_bytes(), b"alt")
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), ["song.mp3"])

    def test_svg_is_not_served(self):
        self.assertNotIn(".svg", media_files.MEDIA_TYPES)
        self.assertNotIn(".html", media_files.MEDIA_TYPES)


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.studio = base / "studio"
        self.data = base / "data"
        for folder in (self.studio / "exports", self.studio / "assets", self.data):
            folder.mkdir(parents=True)
        self.server = studio_app.create_server(self.studio, self.data)
        # Nie ins Internet: GitHub-Abfrage und Update-Start werden ersetzt.
        self.remote_manifest = REPO_MANIFEST
        self.launched = []
        self.server.updates = updates.UpdateChecker(
            studio_app.APP_DIR, self.data, self.studio, fetch=lambda: (self.remote_manifest, "a" * 40),
            launch=lambda args, log: self.launched.append(args))
        self.port = self.server.server_address[1]
        self.cookie = "{}={}".format(studio_app.COOKIE_NAME, self.server.session_token)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        # Ein abgebrochener Auftrag schreibt danach noch den Verlauf – erst dann den Temp-Ordner löschen.
        self.server.bridge.stop()
        deadline = time.time() + WAIT_SECONDS
        while self.server.bridge.busy and time.time() < deadline:
            time.sleep(0.1)
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None, session=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        all_headers = {"Host": "127.0.0.1:{}".format(self.port)}
        if session:
            all_headers.update({"Cookie": self.cookie, "X-Studio-Request": "1"})
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
            _, data, _ = self.request("GET", "/api/state?from=0")
            state = json.loads(data)
            if not state["busy"]:
                return state["items"]
            time.sleep(0.2)
        self.fail("Auftrag wurde nicht rechtzeitig fertig")


class SecurityTests(ServerTestCase):
    def test_hello_is_public(self):
        status, data, _ = self.request("GET", "/api/hello", session=False)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["app"], "motion-studio")

    def test_index_without_launch_key_reveals_nothing(self):
        status, data, _ = self.request("GET", "/", session=False)
        self.assertEqual(status, 403)
        self.assertNotIn(self.server.session_token.encode(), data)
        self.assertNotIn(self.server.launch_key.encode(), data)

    def test_launch_key_is_exchanged_for_httponly_cookie(self):
        status, _, response = self.request("GET", "/?k=" + self.server.launch_key, session=False)
        self.assertEqual(status, 303)
        cookie = response.getheader("Set-Cookie")
        self.assertIn(self.server.session_token, cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

    def test_wrong_launch_key_is_rejected(self):
        status, _, response = self.request("GET", "/?k=falsch", session=False)
        self.assertEqual(status, 403)
        self.assertIsNone(response.getheader("Set-Cookie"))

    def test_api_requires_session_cookie(self):
        status, _, _ = self.request("GET", "/api/state", session=False)
        self.assertEqual(status, 403)
        status, _, _ = self.request("GET", "/api/state", headers={"Cookie": "motion_studio=falsch"}, session=False)
        self.assertEqual(status, 403)

    def test_post_requires_custom_header(self):
        status, _, _ = self.request("POST", "/api/ping", body={}, session=False, headers={"Cookie": self.cookie})
        self.assertEqual(status, 403)

    def test_non_ascii_cookie_does_not_crash(self):
        status, _, _ = self.request("GET", "/api/state", session=False,
                                    headers={"Cookie": "motion_studio=äöü".encode("utf-8").decode("latin-1")})
        self.assertEqual(status, 403)

    def test_foreign_host_origin_and_cross_site_are_rejected(self):
        status, _, _ = self.request("GET", "/api/state", headers={"Host": "evil.example:{}".format(self.port)})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/ping", body={}, headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("GET", "/api/state", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)

    def test_pages_send_security_headers(self):
        _, _, response = self.request("GET", "/")
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
        self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
        self.assertEqual(response.getheader("Referrer-Policy"), "no-referrer")

    def test_media_is_sandboxed_and_traversal_rejected(self):
        (self.studio / "exports" / "a.png").write_bytes(b"x")
        _, _, response = self.request("GET", "/media/exports/a.png")
        self.assertTrue(response.getheader("Content-Security-Policy").startswith("sandbox"))
        (self.studio / "secret.mp4").write_bytes(b"x")
        status, _, _ = self.request("GET", "/media/exports/..%2Fsecret.mp4")
        self.assertEqual(status, 404)

    def test_svg_upload_is_rejected(self):
        status, _, _ = self.request("POST", "/api/upload", body=b"<svg/>", headers={"X-Filename": "bild.svg"})
        self.assertEqual(status, 400)


class ChatTests(ServerTestCase):
    def test_chat_runs_and_resumes_session(self):
        status, _, _ = self.request("POST", "/api/chat", body={"message": "Hallo Studio", "model": "sonnet"})
        self.assertEqual(status, 200)
        items = self.wait_until_idle()
        self.assertEqual([item["kind"] for item in items], ["user", "assistant", "tool", "done"])
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

    def test_codex_chat_runs_and_resumes_thread(self):
        status, _, _ = self.request("POST", "/api/chat", body={"message": "Hallo Codex", "model": "codex-max"})
        self.assertEqual(status, 200)
        items = self.wait_until_idle()
        self.assertEqual([item["kind"] for item in items], ["user", "assistant", "tool", "tool", "done"])
        self.assertIn("resume=nein", items[1]["text"])
        self.assertIn("modell=gpt-6-astra", items[1]["text"])
        self.assertEqual(items[2]["text"], "Führt aus: ffmpeg -version")
        self.assertEqual(items[3]["text"], "Erstellt fake.mp4")

        self.request("POST", "/api/chat", body={"message": "Weiter", "model": "codex"})
        items = self.wait_until_idle()
        self.assertIn("resume=ja", items[6]["text"])
        self.assertIn("modell=gpt-6.1-sol", items[6]["text"])
        saved = json.loads((self.data / "session.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["sessions"], saved["engine"], saved["folder"]),
                         ({"codex": "test-thread-1"}, "codex", self.server.bridge.folder))

    def test_switching_engine_adds_note_and_keeps_each_session(self):
        self.request("POST", "/api/chat", body={"message": "Erst Claude", "model": "opus"})
        self.wait_until_idle()
        self.request("POST", "/api/chat", body={"message": "Dann Codex", "model": "codex"})
        items = self.wait_until_idle()
        self.assertEqual(items[4]["kind"], "note")
        self.assertIn("Codex kennt den bisherigen Verlauf", items[4]["text"])
        self.request("POST", "/api/chat", body={"message": "Wieder Claude", "model": "sonnet"})
        items = self.wait_until_idle()
        self.assertIn("resume=ja", [i for i in items if i["kind"] == "assistant"][-1]["text"])

    def test_codex_login_error_is_flagged_with_engine(self):
        self.request("POST", "/api/chat", body={"message": "bitte fehler", "model": "codex"})
        items = self.wait_until_idle()
        self.assertEqual(items[-1]["kind"], "error")
        self.assertTrue(items[-1]["needs_login"])
        self.assertEqual(items[-1]["engine"], "codex")
        self.assertIn("401", items[-1]["text"])

    def test_missing_codex_is_reported(self):
        with mock.patch.object(engines.ps, "codex_command", return_value=None):
            status, data, _ = self.request("POST", "/api/chat", body={"message": "Hallo", "model": "codex"})
            self.assertEqual(status, 503)
            self.assertIn("Codex wurde nicht gefunden", json.loads(data)["error"])
            _, data, _ = self.request("GET", "/api/auth?engine=codex&force=1")
            self.assertFalse(json.loads(data)["installed"])
        _, data, _ = self.request("GET", "/api/state?from=0")
        self.assertFalse(json.loads(data)["busy"])

    def test_auth_and_login_per_engine(self):
        _, data, _ = self.request("GET", "/api/auth?engine=codex&force=1")
        self.assertEqual(json.loads(data), {"engine": "codex", "installed": True, "logged_in": True})
        self.request("POST", "/api/login", body={"engine": "codex"})
        deadline = time.time() + WAIT_SECONDS
        while time.time() < deadline:
            _, data, _ = self.request("GET", "/api/login")
            login = json.loads(data)
            if login["state"] != "running":
                break
            time.sleep(0.2)
        self.assertEqual(login["state"], "done")
        self.assertEqual(login["engine"], "codex")
        self.assertTrue(login["url"].startswith("https://auth.openai.com/"))

    def test_unknown_engine_is_rejected(self):
        status, _, _ = self.request("GET", "/api/auth?engine=gibtsnicht")
        self.assertEqual(status, 400)
        status, _, _ = self.request("POST", "/api/login", body={"engine": "gibtsnicht"})
        self.assertEqual(status, 400)

    def test_conversation_gets_own_folder_that_survives_restart_and_reset(self):
        self.request("POST", "/api/chat", body={"message": "Intro für Studio Nord"})
        self.wait_until_idle()
        folder = self.server.bridge.folder
        self.assertIn("Intro-für-Studio-Nord", folder)
        self.assertTrue((self.studio / "exports" / folder / "fake.mp4").exists())
        self.assertEqual(StudioBridge(self.studio, self.data).folder, folder)
        self.request("POST", "/api/chat", body={"message": "Weiter"})
        self.wait_until_idle()
        self.assertEqual(self.server.bridge.folder, folder)
        self.request("POST", "/api/reset", body={})
        self.assertIsNone(self.server.bridge.folder)
        self.request("POST", "/api/chat", body={"message": "Ganz neues Video"})
        self.wait_until_idle()
        self.assertNotEqual(self.server.bridge.folder, folder)

    def test_folder_failure_does_not_leave_studio_busy(self):
        (self.studio / "exports").rmdir()
        (self.studio / "exports").write_text("keine Ordner hier", encoding="utf-8")
        status, _, _ = self.request("POST", "/api/chat", body={"message": "Hallo"})
        self.assertEqual(status, 200)
        items = self.wait_until_idle()
        self.assertEqual(items[-1]["kind"], "error")
        (self.studio / "exports").unlink()
        (self.studio / "exports").mkdir()
        self.request("POST", "/api/chat", body={"message": "Nochmal"})
        self.assertEqual(self.wait_until_idle()[-1]["kind"], "done")

    def test_conversation_from_older_version_keeps_its_videos_visible(self):
        (self.studio / "exports" / "altes_video.mp4").write_bytes(b"x")
        (self.studio / "exports" / "anderes-gespraech").mkdir()
        (self.studio / "exports" / "anderes-gespraech" / "fremd.mp4").write_bytes(b"x")
        self.server.bridge.items = [{"kind": "user", "text": "Altes Gespräch"}, {"kind": "done"}]
        listing = json.loads(self.request("GET", "/api/files")[1])
        self.assertEqual([f["name"] for f in listing["exports"]], ["altes_video.mp4"])
        self.request("POST", "/api/chat", body={"message": "Weiter"})
        items = self.wait_until_idle()
        self.assertEqual(items[2]["kind"], "note")
        self.assertIn(self.server.bridge.folder, items[2]["text"])
        self.assertTrue((self.studio / "projekte" / self.server.bridge.folder).is_dir())

    def test_reset_archives_and_old_conversation_can_be_found_and_reopened(self):
        self.request("POST", "/api/chat", body={"message": "Intro für Studio Nord"})
        self.wait_until_idle()
        old_folder = self.server.bridge.folder
        old_id = self.server.bridge.conversation_id
        self.request("POST", "/api/reset", body={})
        self.request("POST", "/api/chat", body={"message": "Ganz anderes Thema"})
        self.wait_until_idle()

        listing = json.loads(self.request("GET", "/api/conversations")[1])["conversations"]
        self.assertEqual([(c["title"], c["current"]) for c in listing],
                         [("Ganz anderes Thema", True), ("Intro für Studio Nord", False)])
        hits = json.loads(self.request("GET", "/api/conversations?q=" + quote("studio nord"))[1])["conversations"]
        self.assertEqual([c["id"] for c in hits], [old_id])
        answer_hits = json.loads(self.request("GET", "/api/conversations?q=verstanden")[1])["conversations"]
        self.assertEqual(len(answer_hits), 2, "auch Antworten der KI werden durchsucht")

        status, _, _ = self.request("POST", "/api/conversations/open", body={"id": old_id})
        self.assertEqual(status, 200)
        items = json.loads(self.request("GET", "/api/state?from=0")[1])["items"]
        self.assertEqual(items[0]["text"], "Intro für Studio Nord")
        self.assertEqual(self.server.bridge.folder, old_folder)
        files = json.loads(self.request("GET", "/api/files")[1])
        self.assertEqual([f["name"] for f in files["exports"]], ["fake.mp4"])
        listing = json.loads(self.request("GET", "/api/conversations")[1])["conversations"]
        self.assertEqual([(c["title"], c["current"]) for c in listing],
                         [("Intro für Studio Nord", True), ("Ganz anderes Thema", False)])

        self.request("POST", "/api/chat", body={"message": "Weiter am Intro"})
        items = self.wait_until_idle()
        self.assertIn("resume=ja", [i for i in items if i["kind"] == "assistant"][-1]["text"])
        self.assertEqual(self.server.bridge.folder, old_folder)

    def test_open_conversation_is_guarded(self):
        status, _, _ = self.request("POST", "/api/conversations/open", body={"id": "../session"})
        self.assertEqual(status, 404)
        status, _, _ = self.request("POST", "/api/conversations/open", body={"id": "gibt-es-nicht"})
        self.assertEqual(status, 404)
        self.request("POST", "/api/chat", body={"message": "Erstes"})
        self.wait_until_idle()
        first = self.server.bridge.conversation_id
        self.request("POST", "/api/reset", body={})
        self.request("POST", "/api/chat", body={"message": "langsam bitte"})
        status, _, _ = self.request("POST", "/api/conversations/open", body={"id": first})
        self.assertEqual(status, 409)
        status, _, _ = self.request("GET", "/api/conversations", session=False)
        self.assertEqual(status, 403)

    def test_reset_clears_conversation(self):
        self.request("POST", "/api/chat", body={"message": "Hallo"})
        self.wait_until_idle()
        self.request("POST", "/api/reset", body={})
        _, data, _ = self.request("GET", "/api/state?from=0")
        self.assertEqual(json.loads(data)["items"], [])


class UpdateTests(ServerTestCase):
    def test_update_status_requires_session(self):
        status, _, _ = self.request("GET", "/api/update", session=False)
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/update/start", body={}, session=False,
                                    headers={"Cookie": self.cookie})
        self.assertEqual(status, 403)

    def test_no_update_when_versions_match(self):
        _, data, _ = self.request("GET", "/api/update")
        info = json.loads(data)
        self.assertEqual(info["current"], REPO_MANIFEST["cmg"])
        self.assertFalse(info["available"])
        status, _, _ = self.request("POST", "/api/update/start", body={})
        self.assertEqual(status, 400)
        self.assertEqual(self.launched, [])

    def test_update_is_refused_while_a_job_runs(self):
        self.remote_manifest = NEWER_MANIFEST
        self.request("POST", "/api/chat", body={"message": "langsam bitte"})
        status, _, _ = self.request("POST", "/api/update/start", body={})
        self.assertEqual(status, 409)
        self.assertEqual(self.launched, [])
        self.assertFalse(self.server.updating)

    def test_update_starts_runner_and_blocks_new_jobs(self):
        self.remote_manifest = NEWER_MANIFEST
        _, data, _ = self.request("GET", "/api/update?force=1")
        self.assertTrue(json.loads(data)["available"])
        status, _, _ = self.request("POST", "/api/update/start", body={})
        self.assertEqual(status, 200)
        self.assertEqual(Path(self.launched[0][1]).name, "update_runner.py")
        self.assertTrue(self.server.updating)
        status, _, _ = self.request("POST", "/api/chat", body={"message": "Hallo"})
        self.assertEqual(status, 409)
        status, _, _ = self.request("POST", "/api/update/start", body={})
        self.assertEqual(status, 409)
        self.assertEqual(len(self.launched), 1)

    def test_update_result_is_kept_until_acknowledged(self):
        result_file = self.data / "update-result.json"
        result_file.write_text(json.dumps({"ok": False, "message": "kaputt", "log": "x.log"}), encoding="utf-8")
        for _ in range(2):
            _, data, _ = self.request("GET", "/api/update")
            self.assertEqual(json.loads(data)["result"]["message"], "kaputt")
        status, _, _ = self.request("POST", "/api/update/ack", body={})
        self.assertEqual(status, 200)
        self.assertFalse(result_file.exists())


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

    def test_files_lists_only_current_conversation_and_assets(self):
        (self.studio / "exports" / "alt.mp4").write_bytes(b"x")
        (self.studio / "exports" / "anderes-gespraech").mkdir()
        (self.studio / "exports" / "anderes-gespraech" / "fremd.mp4").write_bytes(b"x")
        (self.studio / "assets" / "logo.png").write_bytes(b"x")
        _, data, _ = self.request("GET", "/api/files")
        listing = json.loads(data)
        self.assertEqual(listing["exports"], [])
        self.assertIsNone(listing["conversation"])
        self.assertEqual(listing["assets"][0]["type"], "image")

        self.request("POST", "/api/chat", body={"message": "Mein Intro"})
        self.wait_until_idle()
        folder = self.server.bridge.folder
        (self.studio / "exports" / folder / "vorschau").mkdir()
        (self.studio / "exports" / folder / "vorschau" / "bild 1.png").write_bytes(b"x")
        listing = json.loads(self.request("GET", "/api/files")[1])
        self.assertEqual(listing["conversation"], folder)
        self.assertEqual(sorted(f["name"] for f in listing["exports"]), ["fake.mp4", "vorschau/bild 1.png"])
        image = next(f for f in listing["exports"] if f["type"] == "image")
        status, body, _ = self.request("GET", image["url"])
        self.assertEqual((status, body), (200, b"x"))

    def test_open_conversation_folder(self):
        opened = []
        with mock.patch.object(studio_app.ps, "open_in_file_manager", opened.append):
            self.request("POST", "/api/open", body={"target": "conversation"})
            self.request("POST", "/api/chat", body={"message": "Intro"})
            self.wait_until_idle()
            self.request("POST", "/api/open", body={"target": "conversation"})
        self.assertEqual(opened, [self.studio / "exports", self.studio / "exports" / self.server.bridge.folder])

    def test_favicon_is_served_without_session(self):
        for path in ("/static/favicon.png", "/favicon.ico", "/static/apple-touch-icon.png"):
            status, body, response = self.request("GET", path, session=False)
            self.assertEqual(status, 200, path)
            self.assertEqual(response.getheader("Content-Type"), "image/png")
            self.assertTrue(body.startswith(b"\x89PNG"))


class BrowserTests(ServerTestCase):
    """Bedient die Oberfläche wie ein Mensch (übersprungen, falls Playwright fehlt)."""

    def test_launch_template_send_shows_answer_and_video(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright nicht installiert")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.server.launch_url)
                self.assertTrue(page.url.endswith("/"), "Startkennung muss aus der Adresse verschwinden")
                page.get_by_role("button", name="Showreel").click()
                self.assertIn("Showreel", page.locator("#prompt").input_value())
                page.get_by_role("button", name="Senden").click()
                page.locator(".done-note").wait_for(timeout=WAIT_SECONDS * 1000)
                self.assertIn("Verstanden", page.locator(".msg-assistant").first.inner_text())
                page.locator(".media-card video").first.wait_for(timeout=WAIT_SECONDS * 1000)
                self.assertTrue(page.locator("#login").is_hidden())
                page.get_by_role("button", name="Info").click()
                self.assertTrue(page.locator("#info").is_visible())
                self.assertEqual(page.locator("#info a[href^='mailto:']").get_attribute("href"),
                                 "mailto:hey@normanschoenherr.de")
                page.keyboard.press("Escape")
                self.assertTrue(page.locator("#info").is_hidden())
                page.reload()
                page.locator(".msg-assistant").first.wait_for(timeout=WAIT_SECONDS * 1000)
            finally:
                browser.close()

    def test_update_badge_dialog_and_start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright nicht installiert")
        self.remote_manifest = NEWER_MANIFEST
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.server.launch_url)
                page.get_by_role("button", name="Update verfügbar").click()
                self.assertIn("Version 99.0.0", page.locator("#update-intro").inner_text())
                self.assertIn("Motion Studio", page.locator("#update-changes").inner_text())
                page.get_by_role("button", name="Jetzt aktualisieren").click()
                page.get_by_text("Das Studio wird aktualisiert").wait_for(timeout=WAIT_SECONDS * 1000)
                self.assertEqual(len(self.launched), 1)
            finally:
                browser.close()

    def test_info_shows_installed_version(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright nicht installiert")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.server.launch_url)
                page.wait_for_function("() => document.getElementById('info-version').textContent !== ''")
                self.assertTrue(page.locator("#update-open").is_hidden())
                page.get_by_role("button", name="Info").click()
                self.assertEqual(page.locator("#info-version").inner_text(), "Version " + REPO_MANIFEST["cmg"])
            finally:
                browser.close()

    def test_preview_video_offers_final_version(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright nicht installiert")
        self.request("POST", "/api/chat", body={"message": "Intro"})
        self.wait_until_idle()
        folder = self.studio / "exports" / self.server.bridge.folder
        (folder / "intro_vorschau.mp4").write_bytes(b"\x00" * 2048)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.server.launch_url)
                card = page.locator(".media-card", has_text="intro_vorschau.mp4")
                card.locator(".media-badge", has_text="Vorschau").wait_for(timeout=WAIT_SECONDS * 1000)
                self.assertEqual(page.locator(".media-card", has_text="fake.mp4").locator(".media-badge").text_content(),
                                 "Final")
                card.get_by_role("button", name="Finale Version erstellen").click()
                page.locator(".msg-user", has_text="finale Version von intro_vorschau.mp4").wait_for(
                    timeout=WAIT_SECONDS * 1000)
                self.assertEqual(page.locator("link[rel=icon]").get_attribute("href"), "/static/favicon.png")
            finally:
                browser.close()

    def test_search_and_reopen_old_conversation_in_browser(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright nicht installiert")
        self.request("POST", "/api/chat", body={"message": "Logo-Animation für Café Blau"})
        self.wait_until_idle()
        self.request("POST", "/api/reset", body={})
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.server.launch_url)
                page.get_by_role("button", name="Gespräche").click()
                page.locator("#conversation-search").fill("café")
                entry = page.locator("#conversation-list li", has_text="Logo-Animation für Café Blau")
                entry.wait_for(timeout=WAIT_SECONDS * 1000)
                entry.get_by_role("button", name="Öffnen").click()
                page.locator(".msg-user", has_text="Logo-Animation für Café Blau").wait_for(timeout=WAIT_SECONDS * 1000)
                page.locator(".media-card", has_text="fake.mp4").wait_for(timeout=WAIT_SECONDS * 1000)
                self.assertTrue(page.locator("#conversations").is_hidden())
                page.get_by_role("button", name="Gespräche").click()
                page.locator("#conversation-search").fill("gibt es nicht")
                page.get_by_text("Keine passenden Gespräche gefunden.").wait_for(timeout=WAIT_SECONDS * 1000)
            finally:
                browser.close()

    def test_codex_model_can_be_chosen_and_used(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright nicht installiert")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.server.launch_url)
                page.locator("#model").select_option("codex-max")
                page.locator("#prompt").fill("Ein kurzes Intro")
                page.get_by_role("button", name="Senden").click()
                page.locator(".done-note").wait_for(timeout=WAIT_SECONDS * 1000)
                self.assertIn("Codex:", page.locator(".msg-assistant").first.inner_text())
                self.assertIn("Erstellt fake.mp4", page.locator(".step").all_inner_texts())
                self.assertTrue(page.locator("#login").is_hidden())
                page.reload()
                self.assertEqual(page.locator("#model").input_value(), "codex-max")
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
