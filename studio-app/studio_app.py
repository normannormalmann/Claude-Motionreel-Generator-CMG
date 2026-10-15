"""Motion Studio – lokale Oberfläche für Claude Code.

Startet einen kleinen Webserver auf 127.0.0.1 und öffnet ihn im Browser.
Nur die Python-Standardbibliothek wird benötigt.
"""

import json
import logging
import re
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import platform_support as ps  # noqa: E402
from claude_bridge import BusyError, ClaudeMissingError, StudioBridge  # noqa: E402

PREFERRED_PORT = 47615
IDLE_SHUTDOWN_SECONDS = 180
STARTUP_GRACE_SECONDS = 90
LONG_POLL_SECONDS = 20
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_JSON_BYTES = 200 * 1024
CHUNK_SIZE = 64 * 1024
MAX_MEDIA_FILES = 80
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {"app.css": "text/css", "app.js": "text/javascript"}
MEDIA_TYPES = {
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".svg": "image/svg+xml", ".ttf": "font/ttf", ".otf": "font/otf", ".woff2": "font/woff2",
}
MEDIA_ROOTS = ("exports", "assets")
SAFE_NAME = re.compile(r"[^\w.\- ]")


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, bridge, studio_dir, token):
        super().__init__(address, StudioHandler)
        self.bridge = bridge
        self.studio_dir = Path(studio_dir)
        self.token = token
        self.last_seen = time.time() + STARTUP_GRACE_SECONDS

    @property
    def allowed_hosts(self):
        port = self.server_address[1]
        return {"127.0.0.1:{}".format(port), "localhost:{}".format(port)}


def list_media(studio_dir, root):
    base = studio_dir / root
    if not base.is_dir():
        return []
    files = [p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_TYPES]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in files[:MAX_MEDIA_FILES]:
        relative = path.relative_to(base).as_posix()
        stat = path.stat()
        result.append({
            "name": relative,
            "url": "/media/{}/{}".format(root, quote(relative)),
            "type": MEDIA_TYPES[path.suffix.lower()].split("/")[0],
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return result


def safe_upload_name(raw_name):
    name = SAFE_NAME.sub("_", Path(unquote(raw_name or "")).name).strip()
    if not name or name.startswith("."):
        return None
    return name[:120]


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "MotionStudio/1.0"

    def log_message(self, fmt, *args):
        logging.debug("%s - %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------ Antworten

    def _send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status)

    def _send_bytes(self, body, content_type):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

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
        """Schützt vor fremden Webseiten (DNS-Rebinding, Cross-Site-Anfragen)."""
        if self.headers.get("Host") not in self.server.allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.replace("http://", "", 1) in self.server.allowed_hosts

    def _has_token(self, query):
        supplied = self.headers.get("X-Studio-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(supplied, self.server.token)

    # ------------------------------------------------------------ Routing

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if not self._is_trusted_origin():
            return self._send_error(HTTPStatus.FORBIDDEN, "Zugriff verweigert")
        if url.path == "/api/hello":
            return self._send_json({"app": "motion-studio"})
        if url.path == "/":
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", self.server.token)
            return self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
        if url.path.startswith("/static/"):
            name = url.path[len("/static/"):]
            if name in STATIC_FILES:
                return self._send_bytes((STATIC_DIR / name).read_bytes(), STATIC_FILES[name] + "; charset=utf-8")
            return self._send_error(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        if not self._has_token(query):
            return self._send_error(HTTPStatus.FORBIDDEN, "Zugriff verweigert")
        self.server.last_seen = time.time()
        if url.path.startswith("/media/"):
            return self._send_media(url.path)
        routes = {
            "/api/state": lambda: self._state(query),
            "/api/auth": lambda: self._send_json(self.server.bridge.auth_status(force="force" in query)),
            "/api/files": lambda: self._send_json({
                root: list_media(self.server.studio_dir, root) for root in MEDIA_ROOTS
            }),
            "/api/login": lambda: self._send_json(self.server.bridge.login_snapshot()),
        }
        handler = routes.get(url.path)
        if handler is None:
            return self._send_error(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        return handler()

    def do_POST(self):
        url = urlparse(self.path)
        if not self._is_trusted_origin() or not self._has_token({}):
            return self._send_error(HTTPStatus.FORBIDDEN, "Zugriff verweigert")
        self.server.last_seen = time.time()
        bridge = self.server.bridge
        try:
            if url.path == "/api/chat":
                data = self._read_json()
                message = str(data.get("message", "")).strip()
                if not message:
                    return self._send_error(HTTPStatus.BAD_REQUEST, "Bitte einen Auftrag eingeben.")
                bridge.start_chat(message, str(data.get("model", "")))
                return self._send_json({"ok": True})
            if url.path == "/api/stop":
                bridge.stop()
                return self._send_json({"ok": True})
            if url.path == "/api/reset":
                bridge.reset()
                return self._send_json({"ok": True})
            if url.path == "/api/upload":
                return self._upload()
            if url.path == "/api/open":
                return self._open_folder(self._read_json().get("target"))
            if url.path == "/api/login":
                bridge.start_login()
                return self._send_json({"ok": True})
            if url.path == "/api/login/code":
                bridge.send_login_code(str(self._read_json().get("code", "")))
                return self._send_json({"ok": True})
            if url.path == "/api/ping":
                return self._send_json({"ok": True})
        except BusyError:
            return self._send_error(HTTPStatus.CONFLICT, "Claude arbeitet gerade noch. Bitte warten oder abbrechen.")
        except ClaudeMissingError:
            return self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "Claude Code wurde nicht gefunden. Bitte den Installer erneut starten.")
        return self._send_error(HTTPStatus.NOT_FOUND, "Nicht gefunden")

    # ------------------------------------------------------------ Endpunkte

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
        if target in MEDIA_ROOTS:
            folder = folder / target
        folder.mkdir(parents=True, exist_ok=True)
        ps.open_in_file_manager(folder)
        return self._send_json({"ok": True})

    def _upload(self):
        name = safe_upload_name(self.headers.get("X-Filename"))
        length = int(self.headers.get("Content-Length") or 0)
        if not name or Path(name).suffix.lower() not in MEDIA_TYPES:
            return self._send_error(HTTPStatus.BAD_REQUEST, "Dieser Dateityp wird nicht unterstützt.")
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            return self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Die Datei ist zu groß (max. 500 MB).")
        target_dir = self.server.studio_dir / "assets"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / name
        remaining = length
        with open(target, "wb") as handle:
            while remaining > 0:
                chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                handle.write(chunk)
                remaining -= len(chunk)
        return self._send_json({"ok": True, "name": name})

    def _resolve_media(self, path):
        parts = path.split("/", 3)  # ["", "media", root, rest]
        if len(parts) != 4 or parts[2] not in MEDIA_ROOTS:
            return None
        base = (self.server.studio_dir / parts[2]).resolve()
        candidate = (base / unquote(parts[3])).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        if not candidate.is_file() or candidate.suffix.lower() not in MEDIA_TYPES:
            return None
        return candidate

    def _send_media(self, path):
        file_path = self._resolve_media(path)
        if file_path is None:
            return self._send_error(HTTPStatus.NOT_FOUND, "Datei nicht gefunden")
        size = file_path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        match = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if match and (match.group(1) or match.group(2)):
            if match.group(1):
                start = int(match.group(1))
                end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
            else:
                start = max(0, size - int(match.group(2)))
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", "bytes */{}".format(size))
                self.end_headers()
                return None
            status = HTTPStatus.PARTIAL_CONTENT
        self.send_response(status)
        self.send_header("Content-Type", MEDIA_TYPES[file_path.suffix.lower()])
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", "bytes {}-{}/{}".format(start, end, size))
        self.end_headers()
        try:
            with open(file_path, "rb") as handle:
                handle.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = handle.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        return None


# ---------------------------------------------------------------- Start


def running_instance_url(info_file):
    """Läuft das Studio schon? Dann dessen Adresse zurückgeben."""
    try:
        port = json.loads(info_file.read_text(encoding="utf-8"))["port"]
        url = "http://127.0.0.1:{}/".format(port)
        with urllib.request.urlopen(url + "api/hello", timeout=2) as response:
            if json.loads(response.read().decode("utf-8")).get("app") == "motion-studio":
                return url
    except (OSError, ValueError, KeyError):
        pass
    return None


def create_server(studio_dir, data_dir, port=PREFERRED_PORT):
    bridge = StudioBridge(studio_dir, data_dir)
    token = secrets.token_urlsafe(24)
    try:
        return StudioServer(("127.0.0.1", port), bridge, studio_dir, token)
    except OSError:
        return StudioServer(("127.0.0.1", 0), bridge, studio_dir, token)


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
    for folder in ("exports", "assets"):
        (studio / folder).mkdir(parents=True, exist_ok=True)
    server = create_server(studio, data_dir)
    port = server.server_address[1]
    info_file.write_text(json.dumps({"port": port}), encoding="utf-8")
    url = "http://127.0.0.1:{}/".format(port)
    logging.info("Motion Studio läuft unter %s (Studio-Ordner: %s)", url, studio)
    print("Motion Studio läuft unter {} – dieses Fenster kann offen bleiben.".format(url))

    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    threading.Thread(target=watch_idle, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
