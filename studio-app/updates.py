"""Update-Prüfung: Gibt es auf GitHub eine neuere, geprüfte Version des Studios?

Maßgeblich ist versions.json: Sie nennt die Studio-Version und die getesteten Versionen von Codex
und den Python-Paketen. Der Installer legt eine Kopie neben die App; das Studio vergleicht sie
höchstens einmal täglich mit der Fassung auf GitHub. Dabei wird der Commit von main festgehalten:
Das Update installiert genau diesen Stand (Installer und alle Dateien aus demselben Commit).
Das Update selbst führt update_runner.py aus.
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import platform_support as ps

REPOSITORY = "normannormalmann/Claude-Motionreel-Generator-CMG"
GITHUB_RAW = "https://raw.githubusercontent.com/" + REPOSITORY
GITHUB_HEAD_URL = "https://api.github.com/repos/" + REPOSITORY + "/commits/main"
MANIFEST_NAME = "versions.json"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
FETCH_TIMEOUT_SECONDS = 5
MAX_MANIFEST_BYTES = 64 * 1024
VERSION_PATTERN = re.compile(r"\d{1,6}(\.\d{1,6}){1,3}")
PACKAGE_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,40}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
LOCAL_TEST_SERVER = re.compile(r"http://(127\.0\.0\.1|localhost)(:\d{1,5})?")
COMPONENT_LABELS = {"cmg": "Motion Studio", "codex": "Codex (ChatGPT)"}
RESULT_FIELDS = {"ok": bool, "finished_at": (int, float), "version": (str, type(None)),
                 "message": (str, type(None)), "log": (str, type(None))}


class ManifestError(ValueError):
    """versions.json fehlt oder hat ein unerwartetes Format."""


class UpdateUnavailableError(Exception):
    """Es gibt kein Update, das eingespielt werden könnte."""


def repository_urls():
    """(Rohdateien, aktueller Commit von main). Für Tests nur auf einen lokalen Server umlenkbar."""
    override = os.environ.get("CMG_REPO_RAW", "")
    if LOCAL_TEST_SERVER.fullmatch(override):
        return override, override + "/commits/main"
    return GITHUB_RAW, GITHUB_HEAD_URL


def parse_version(text):
    if not isinstance(text, str) or not VERSION_PATTERN.fullmatch(text):
        raise ManifestError("Ungültige Versionsnummer: {!r}".format(text))
    return tuple(int(part) for part in text.split("."))


def validate_commit(text):
    if not isinstance(text, str) or not COMMIT_PATTERN.fullmatch(text):
        raise ManifestError("Ungültiger Commit: {!r}".format(text))
    return text


def validate_manifest(data):
    """Prüft versions.json streng und gibt eine bereinigte Kopie zurück."""
    if not isinstance(data, dict):
        raise ManifestError("versions.json muss ein Objekt sein.")
    packages = data.get("python_packages")
    if not isinstance(packages, dict) or not packages:
        raise ManifestError("python_packages fehlt.")
    for name, version in packages.items():
        if not isinstance(name, str) or not PACKAGE_PATTERN.fullmatch(name):
            raise ManifestError("Ungültiger Paketname: {!r}".format(name))
        parse_version(version)
    parse_version(data.get("cmg"))
    parse_version(data.get("codex"))
    return {"cmg": data["cmg"], "codex": data["codex"], "python_packages": dict(packages)}


def load_manifest(path):
    try:
        return validate_manifest(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def read_limited(url, limit, headers=None):
    """Lädt höchstens limit Bytes; leere oder zu große Antworten gelten als Fehler."""
    request = urllib.request.Request(url, headers=dict({"Cache-Control": "no-cache"}, **(headers or {})))
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        body = response.read(limit + 1)
    if len(body) > limit or not body:
        raise ManifestError("Unerwartete Antwort von {}".format(url))
    return body


def fetch_remote_manifest():
    """(versions.json, Commit) des aktuellen Stands von main – beides aus demselben Commit."""
    raw_base, head_url = repository_urls()
    head = read_limited(head_url, 100, {"Accept": "application/vnd.github.sha"})
    commit = validate_commit(head.decode("ascii", "replace").strip())
    body = read_limited("{}/{}/{}".format(raw_base, commit, MANIFEST_NAME), MAX_MANIFEST_BYTES)
    return validate_manifest(json.loads(body.decode("utf-8"))), commit


def describe_changes(current, latest):
    """Liste der Bausteine, deren Version sich ändert – für die Anzeige im Studio."""
    if current is None:
        return [{"name": COMPONENT_LABELS["cmg"], "from": None, "to": latest["cmg"]}]
    pairs = [(COMPONENT_LABELS[key], current.get(key), latest[key]) for key in ("cmg", "codex")]
    old_packages = current.get("python_packages", {})
    pairs += [(name.capitalize(), old_packages.get(name), version)
              for name, version in sorted(latest["python_packages"].items())]
    return [{"name": name, "from": old, "to": new} for name, old, new in pairs if old != new]


def launch_detached(args, log_path=None):
    """Startet einen Prozess, der das Ende des Studios überlebt."""
    if ps.IS_WINDOWS:
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    else:
        options = {"start_new_session": True}
    output = open(log_path, "ab") if log_path else subprocess.DEVNULL
    try:
        subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                         close_fds=True, env=ps.tool_environment(), **options)
    finally:
        if log_path:
            output.close()


def _is_newer(latest, current):
    return bool(latest) and (current is None or parse_version(latest["cmg"]) > parse_version(current["cmg"]))


class UpdateChecker:
    def __init__(self, app_dir, data_dir, studio_dir, fetch=fetch_remote_manifest, launch=launch_detached):
        self.app_dir = Path(app_dir)
        self.data_dir = Path(data_dir)
        self.studio_dir = Path(studio_dir)
        self._fetch = fetch
        self._launch = launch
        self.enabled = os.environ.get("CMG_NO_UPDATE_CHECK") != "1"

    @property
    def cache_file(self):
        return self.data_dir / "update-check.json"

    @property
    def result_file(self):
        return self.data_dir / "update-result.json"

    def installed(self):
        """Installierte versions.json; im Repo (Entwicklung) liegt sie eine Ebene höher."""
        return load_manifest(self.app_dir / MANIFEST_NAME) or load_manifest(self.app_dir.parent / MANIFEST_NAME)

    def _read_cache(self):
        try:
            cache = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return validate_manifest(cache["manifest"]), validate_commit(cache["commit"]), float(cache["checked_at"])
        except (OSError, ValueError, KeyError, TypeError):
            return None, None, None

    def _latest(self, force):
        """(versions.json, Commit, Prüfzeitpunkt, Fehler) – höchstens einmal täglich frisch von GitHub."""
        manifest, commit, checked_at = self._read_cache()
        if manifest and not force and time.time() - checked_at < CHECK_INTERVAL_SECONDS:
            return manifest, commit, checked_at, None
        try:
            manifest, commit = self._fetch()
        except (OSError, ValueError) as error:
            # Ohne Internet bleibt es beim letzten bekannten Stand – kein Grund für eine Fehlermeldung.
            return manifest, commit, checked_at, type(error).__name__
        checked_at = time.time()
        try:
            self.cache_file.write_text(json.dumps({"checked_at": checked_at, "manifest": manifest, "commit": commit}),
                                       encoding="utf-8")
        except OSError:
            pass  # Ohne Cache wird beim nächsten Mal einfach neu gefragt.
        return manifest, commit, checked_at, None

    def last_result(self):
        """Ergebnis des letzten Updates – bleibt stehen, bis es mit acknowledge_result() bestätigt wird."""
        try:
            result = json.loads(self.result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(result, dict):
            return None
        return {key: result[key] for key, kind in RESULT_FIELDS.items() if key in result and isinstance(result[key], kind)}

    def acknowledge_result(self):
        try:
            self.result_file.unlink()
        except OSError:
            pass

    def status(self, force=False):
        current = self.installed()
        result = self.last_result()
        if not self.enabled:
            return {"enabled": False, "current": current and current["cmg"], "available": False, "result": result}
        latest, _, checked_at, error = self._latest(force)
        available = _is_newer(latest, current)
        return {
            "enabled": True,
            "current": current and current["cmg"],
            "latest": latest and latest["cmg"],
            "available": available,
            "changes": describe_changes(current, latest) if available else [],
            "checked_at": checked_at,
            "error": error,
            "result": result,
        }

    def start(self):
        """Startet den Update-Helfer für den frisch geprüften Commit; das Studio beendet sich danach selbst."""
        latest, commit, _, error = self._latest(force=True)
        if error or not _is_newer(latest, self.installed()):
            raise UpdateUnavailableError()
        runner = self.app_dir / "update_runner.py"
        args = [sys.executable, str(runner), str(self.data_dir), str(self.studio_dir), str(self.app_dir), commit]
        self._launch(args, self.data_dir / "update-runner.log")
