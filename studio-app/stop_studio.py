"""Beendet ein laufendes Motion Studio vor einem Update (wird vom Installer aufgerufen).

Aufruf:  python stop_studio.py <app-daten-ordner>

Läuft gerade ein Auftrag, bleibt das Studio unangetastet (Rückgabewert 3), damit kein
Render-Lauf verloren geht. Funktioniert auch mit älteren Studio-Versionen: Die Instanz wird
über die Startkennung aus server.json angesprochen. Beendet wird nur der Prozess, der genau
diesen Port belegt und dessen Befehlszeile studio_app.py enthält.
"""

import base64
import http.client
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.cookies import CookieError, SimpleCookie
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
COOKIE_NAME = "motion_studio"
APP_SCRIPT = "studio_app.py"
REQUEST_TIMEOUT = 3
COMMAND_TIMEOUT = 60
SHUTDOWN_WAIT_SECONDS = 15
EXIT_STOPPED, EXIT_FAILED, EXIT_BUSY = 0, 1, 3
LINUX_LISTEN_STATE = "0A"
WINDOWS_PORT_OWNER = (
    "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
    "$c = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
    "if ($c) {{ $p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\"; "
    "@{{ pid = [int]$c.OwningProcess; command = [string]$p.CommandLine }} | ConvertTo-Json -Compress }}"
)
HTTP_ERRORS = (OSError, ValueError, AttributeError, CookieError, http.client.HTTPException)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _get(url, headers=None):
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, error.headers, error.read()


def _json_object(body):
    data = json.loads(body.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def is_running(base):
    try:
        _, _, body = _get(base + "api/hello")
        return _json_object(body).get("app") == "motion-studio"
    except HTTP_ERRORS:
        return False


def is_busy(base, launch_key):
    """Fragt die Instanz mit der Startkennung, ob gerade ein Auftrag läuft (None = unbekannt)."""
    try:
        _, headers, _ = _get(base + "?k=" + launch_key)
        cookie = SimpleCookie(headers.get("Set-Cookie") or "").get(COOKIE_NAME)
        if cookie is None:
            return None
        status, _, body = _get(base + "api/state", {"Cookie": "{}={}".format(COOKIE_NAME, cookie.value)})
        return bool(_json_object(body).get("busy")) if status == 200 else None
    except HTTP_ERRORS:
        return None


def _run(args):
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    result = subprocess.run(args, capture_output=True, timeout=COMMAND_TIMEOUT, **flags)
    return result.stdout.decode("utf-8-sig", "replace").strip()


def _windows_port_owner(port):
    script = WINDOWS_PORT_OWNER.format(port=int(port))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    output = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded])
    if not output:
        return None
    data = json.loads(output)
    return int(data["pid"]), data.get("command") or ""


def _linux_listening_inodes(port):
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(table).read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) > 9 and fields[3] == LINUX_LISTEN_STATE and int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(fields[9])
    return inodes


def _linux_port_owner_pid(port):
    """Sucht über /proc, welcher eigene Prozess den Port belegt (ohne lsof/ss)."""
    targets = {"socket:[{}]".format(inode) for inode in _linux_listening_inodes(port)}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if any(os.readlink(str(fd)) in targets for fd in (entry / "fd").iterdir()):
                return int(entry.name)
        except OSError:
            continue
    return None


def port_owner(port):
    """(PID, Befehlszeile) des Prozesses, der auf dem Port lauscht – oder None."""
    if IS_WINDOWS:
        return _windows_port_owner(port)
    if IS_MAC:
        output = _run(["lsof", "-nP", "-iTCP:{}".format(int(port)), "-sTCP:LISTEN", "-t"])
        pid = int(output.split()[0]) if output else None
    else:
        pid = _linux_port_owner_pid(int(port))
    if pid is None:
        return None
    return pid, _run(["ps", "-p", str(pid), "-o", "command="])


def _terminate(pid):
    if IS_WINDOWS:
        # /T beendet auch Kindprozesse; der venv-Starter von pythonw.exe endet dann von selbst.
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def stop_studio(data_dir):
    info_file = Path(data_dir) / "server.json"
    try:
        info = json.loads(info_file.read_text(encoding="utf-8"))
        port = int(info["port"])
        launch_key = str(info["key"])
    except (OSError, ValueError, KeyError, TypeError):
        return EXIT_STOPPED, "Das Studio läuft nicht."
    base = "http://127.0.0.1:{}/".format(port)
    if not is_running(base):
        info_file.unlink(missing_ok=True)
        return EXIT_STOPPED, "Das Studio läuft nicht."
    if is_busy(base, launch_key) is not False:
        return EXIT_BUSY, "Das Studio arbeitet gerade an einem Auftrag."
    try:
        owner = port_owner(port)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        return EXIT_FAILED, "Das laufende Studio wurde nicht gefunden ({}).".format(type(error).__name__)
    if owner is None or not re.search(r"\b" + re.escape(APP_SCRIPT) + r"\b", owner[1]):
        return EXIT_FAILED, "Das laufende Studio wurde nicht eindeutig gefunden."
    _terminate(owner[0])
    deadline = time.time() + SHUTDOWN_WAIT_SECONDS
    while is_running(base) and time.time() < deadline:
        time.sleep(0.5)
    if is_running(base):
        return EXIT_FAILED, "Das laufende Studio konnte nicht beendet werden."
    info_file.unlink(missing_ok=True)
    return EXIT_STOPPED, "Das laufende Studio wurde beendet."


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return EXIT_FAILED
    code, message = stop_studio(argv[1])
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
