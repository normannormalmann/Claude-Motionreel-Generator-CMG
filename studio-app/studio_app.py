"""Motion Studio – lokale Oberfläche für Claude Code.

Startet einen kleinen Webserver auf 127.0.0.1 und öffnet ihn im Browser.
Nur die Python-Standardbibliothek wird benötigt.

Zugriffsschutz: Der Starter öffnet den Browser mit einer geheimen Startkennung
(/?k=...). Diese wird gegen ein HttpOnly-Cookie getauscht. Ohne Cookie gibt es
keinen Zugriff – auch nicht für andere Programme oder Benutzer auf dem Rechner.
"""

import json
import logging
import os
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import media_files as media  # noqa: E402
import platform_support as ps  # noqa: E402
from claude_bridge import BusyError, ClaudeMissingError, StudioBridge  # noqa: E402
from presets import PresetError, PresetStore  # noqa: E402

IDLE_SHUTDOWN_SECONDS = 180
STARTUP_GRACE_SECONDS = 90
LONG_POLL_SECONDS = 20
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_JSON_BYTES = 200 * 1024
COOKIE_NAME = "motion_studio"
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {"app.css": "text/css", "app.js": "text/javascript", "presets.js": "text/javascript"}
MAX_IMPORT_BYTES = 2 * 1024 * 1024
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "media-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
MEDIA_CSP = "sandbox; default-src 'none'"
LOCKED_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>Motion Studio</title>"
    "<body style='font-family:system-ui;max-width:32rem;margin:15vh auto;padding:0 16px'>"
    "<h1>Motion Studio</h1><p>Bitte öffne das Studio über das Symbol <strong>„Motion Studio“</strong> "
    "auf deinem Desktop bzw. Schreibtisch.</p></body>"
)


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, bridge, studio_dir):
        super().__init__(address, StudioHandler)
        self.bridge = bridge
        self.studio_dir = Path(studio_dir)
        self.presets = PresetStore(studio_dir)
        self.launch_key = secrets.token_urlsafe(32)
        self.session_token = secrets.token_urlsafe(32)
        self.last_seen = time.time() + STARTUP_GRACE_SECONDS

    @property
    def allowed_hosts(self):
        port = self.server_address[1]
        return {"127.0.0.1:{}".format(port), "localhost:{}".format(port)}

    @property
    def launch_url(self):
        return "http://127.0.0.1:{}/?k={}".format(self.server_address[1], self.launch_key)


def tokens_match(supplied, expected):
    return secrets.compare_digest((supplied or "").encode("utf-8"), expected.encode("utf-8"))


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "MotionStudio/1.0"

    def log_message(self, fmt, *args):
        logging.debug("%s - %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------ Antworten

    def _security_headers(self, csp=PAGE_CSP):
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def _send_bytes(self, body, content_type, status=HTTPStatus.OK, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_JSON_BYTES:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------ Sicherheit

    def _is_trusted_origin(self):
        """Wehrt fremde Webseiten ab (DNS-Rebinding, Cross-Site-Anfragen, Einbetten)."""
        if self.headers.get("Host") not in self.server.allowed_hosts:
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.replace("http://", "", 1) in self.server.allowed_hosts

    def _has_session(self):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie") or "")
        except CookieError:
            return False
        morsel = cookie.get(COOKIE_NAME)
        return morsel is not None and tokens_match(morsel.value, self.server.session_token)

    # ------------------------------------------------------------ Routing

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if not self._is_trusted_origin():
            return self._send_error(HTTPStatus.FORBIDDEN, "Zugriff verweigert")
        if url.path == "/api/hello":
            return self._send_json({"app": "motion-studio"})
        if url.path == "/":
            return self._serve_index(query)
        if url.path.startswith("/static/"):
            name = url.path[len("/static/"):]
            if name in STATIC_FILES:
                return self._send_bytes((STATIC_DIR / name).read_bytes(), STATIC_FILES[name] + "; charset=utf-8")
            return self._send_error(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        if not self._has_session():
            return self._send_error(HTTPStatus.FORBIDDEN, "Zugriff verweigert")
        self.server.last_seen = time.time()
        if url.path.startswith("/media/"):
            return self._send_media(url.path)
        routes = {
            "/api/state": lambda: self._state(query),
            "/api/auth": lambda: self._send_json(self.server.bridge.auth_status(force="force" in query)),
            "/api/files": lambda: self._send_json({
                root: media.list_media(self.server.studio_dir, root) for root in media.MEDIA_ROOTS
            }),
            "/api/login": lambda: self._send_json(self.server.bridge.login_snapshot()),
            "/api/presets": lambda: self._send_json({"presets": self.server.presets.list_all()}),
            "/api/presets/export": self._export_presets,
        }
        handler = routes.get(url.path)
        if handler is None:
            return self._send_error(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        return handler()

    def do_POST(self):
        url = urlparse(self.path)
        # Der eigene Kopf-Eintrag erzwingt bei fremden Seiten eine CORS-Vorabprüfung, die wir nie erlauben.
        if not (self._is_trusted_origin() and self._has_session() and self.headers.get("X-Studio-Request") == "1"):
            return self._send_error(HTTPStatus.FORBIDDEN, "Zugriff verweigert")
        self.server.last_seen = time.time()
        try:
            return self._dispatch_post(url.path)
        except BusyError:
            return self._send_error(HTTPStatus.CONFLICT, "Claude arbeitet gerade noch. Bitte warten oder abbrechen.")
        except ClaudeMissingError:
            return self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "Claude Code wurde nicht gefunden. Bitte den Installer erneut starten.")
        except PresetError as error:
            return self._send_error(HTTPStatus.BAD_REQUEST, str(error))

    def _dispatch_post(self, path):
        bridge = self.server.bridge
        if path.startswith("/api/presets/"):
            return self._preset_action(path)
        if path == "/api/chat":
            data = self._read_json()
            message = str(data.get("message", "")).strip()
            if not message:
                return self._send_error(HTTPStatus.BAD_REQUEST, "Bitte einen Auftrag eingeben.")
            bridge.start_chat(message, str(data.get("model", "")))
        elif path == "/api/stop":
            bridge.stop()
        elif path == "/api/reset":
            bridge.reset()
        elif path == "/api/upload":
            return self._upload()
        elif path == "/api/open":
            self._open_folder(self._read_json().get("target"))
        elif path == "/api/login":
            bridge.start_login()
        elif path == "/api/login/code":
            bridge.send_login_code(str(self._read_json().get("code", "")))
        elif path != "/api/ping":
            return self._send_error(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        return self._send_json({"ok": True})

    # ------------------------------------------------------------ Endpunkte

    def _preset_action(self, path):
        store = self.server.presets
        if path == "/api/presets/save":
            return self._send_json({"preset": store.save(self._read_json().get("preset"))})
        if path == "/api/presets/delete":
            store.delete(str(self._read_json().get("id", "")))
            return self._send_json({"ok": True})
        if path == "/api/presets/import":
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_IMPORT_BYTES:
                raise PresetError("Die Datei ist leer oder zu groß.")
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except ValueError:
                raise PresetError("Die Datei ist keine gültige Vorlagen-Datei.")
            imported, skipped = store.import_presets(data)
            return self._send_json({"imported": imported, "skipped": skipped})
        return self._send_error(HTTPStatus.NOT_FOUND, "Nicht gefunden")

    def _export_presets(self):
        body = json.dumps(self.server.presets.export(), ensure_ascii=False, indent=2).encode("utf-8")
        headers = {"Content-Disposition": 'attachment; filename="motion-studio-vorlagen.json"'}
        return self._send_bytes(body, "application/json; charset=utf-8", extra_headers=headers)

    def _serve_index(self, query):
        supplied_key = (query.get("k") or [""])[0]
        if supplied_key and tokens_match(supplied_key, self.server.launch_key):
            cookie = "{}={}; HttpOnly; SameSite=Strict; Path=/".format(COOKIE_NAME, self.server.session_token)
            return self._send_bytes(b"", "text/plain", HTTPStatus.SEE_OTHER, {"Location": "/", "Set-Cookie": cookie})
        if not self._has_session():
            return self._send_bytes(LOCKED_PAGE.encode("utf-8"), "text/html; charset=utf-8", HTTPStatus.FORBIDDEN)
        self.server.last_seen = time.time()
        return self._send_bytes((STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")

    def _state(self, query):
        try:
            start = max(0, int((query.get("from") or ["0"])[0]))
        except ValueError:
            start = 0
        bridge = self.server.bridge
        if "wait" in query:
            return self._send_json(bridge.wait_for_items(start, LONG_POLL_SECONDS))
        return self._send_json(bridge.snapshot(start))

    def _open_folder(self, target):
        folder = self.server.studio_dir
        if target in media.MEDIA_ROOTS:
            folder = folder / target
        folder.mkdir(parents=True, exist_ok=True)
        ps.open_in_file_manager(folder)

    def _upload(self):
        name = media.safe_upload_name(self.headers.get("X-Filename"))
        length = int(self.headers.get("Content-Length") or 0)
        if not name or Path(name).suffix.lower() not in media.MEDIA_TYPES:
            return self._send_error(HTTPStatus.BAD_REQUEST, "Dieser Dateityp wird nicht unterstützt.")
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            return self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Die Datei ist zu groß (max. 500 MB).")
        target_dir = self.server.studio_dir / "assets"
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            media.save_upload(self.rfile, length, target_dir / name)
        except media.UploadError:
            return self._send_error(HTTPStatus.BAD_REQUEST, "Der Upload wurde unterbrochen. Bitte erneut versuchen.")
        return self._send_json({"ok": True, "name": name})

    def _send_media(self, path):
        file_path = media.resolve_media(self.server.studio_dir, path)
        if file_path is None:
            return self._send_error(HTTPStatus.NOT_FOUND, "Datei nicht gefunden")
        size = file_path.stat().st_size
        byte_range = media.parse_range(self.headers.get("Range"), size)
        if byte_range is None:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", "bytes */{}".format(size))
            self.end_headers()
            return None
        start, end, partial = byte_range
        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self.send_header("Content-Type", media.MEDIA_TYPES[file_path.suffix.lower()])
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self._security_headers(MEDIA_CSP)
        if partial:
            self.send_header("Content-Range", "bytes {}-{}/{}".format(start, end, size))
        self.end_headers()
        try:
            with open(file_path, "rb") as handle:
                handle.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = handle.read(min(media.CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        return None


# ---------------------------------------------------------------- Start


def write_private_json(path, data):
    """Schreibt eine Datei, die nur der eigene Benutzer lesen darf."""
    path.write_text(json.dumps(data), encoding="utf-8")
    if not ps.IS_WINDOWS:
        os.chmod(path, 0o600)


def running_instance_url(info_file):
    """Läuft das Studio schon? Dann dessen Startadresse (mit Startkennung) zurückgeben."""
    try:
        info = json.loads(info_file.read_text(encoding="utf-8"))
        base = "http://127.0.0.1:{}/".format(int(info["port"]))
        with urllib.request.urlopen(base + "api/hello", timeout=2) as response:
            if json.loads(response.read().decode("utf-8")).get("app") == "motion-studio":
                return "{}?k={}".format(base, info["key"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def create_server(studio_dir, data_dir, port=0):
    """Port 0 = zufälliger freier Port; so kann kein anderes Programm ihn vorab belegen."""
    bridge = StudioBridge(studio_dir, data_dir)
    return StudioServer(("127.0.0.1", port), bridge, studio_dir)


def watch_idle(server):
    """Beendet das Studio, wenn der Browser geschlossen wurde und nichts mehr läuft."""
    while True:
        time.sleep(10)
        idle = time.time() - server.last_seen
        if idle > IDLE_SHUTDOWN_SECONDS and not server.bridge.busy:
            logging.info("Keine Verbindung mehr – Studio wird beendet.")
            server.shutdown()
            return


def main():
    data_dir = ps.app_data_dir()
    logging.basicConfig(
        filename=str(data_dir / "studio-app.log"), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8",
    )
    info_file = data_dir / "server.json"
    existing = running_instance_url(info_file)
    if existing:
        webbrowser.open(existing)
        return 0

    studio = ps.studio_dir()
    for folder in media.MEDIA_ROOTS:
        (studio / folder).mkdir(parents=True, exist_ok=True)
    server = create_server(studio, data_dir)
    write_private_json(info_file, {"port": server.server_address[1], "key": server.launch_key})
    logging.info("Motion Studio läuft auf Port %s (Studio-Ordner: %s)", server.server_address[1], studio)
    print("Motion Studio läuft – dieses Fenster kann offen bleiben.")

    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, webbrowser.open, args=(server.launch_url,)).start()
    threading.Thread(target=watch_idle, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            info_file.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
