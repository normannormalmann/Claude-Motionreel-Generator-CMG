"""Dateien im Studio-Ordner: Auflisten, sichere Namen, Uploads, Byte-Bereiche."""

import os
import re
from pathlib import Path
from urllib.parse import quote, unquote

# Bewusst ohne SVG/HTML: Diese könnten im Browser Skripte ausführen.
MEDIA_TYPES = {
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".ttf": "font/ttf", ".otf": "font/otf", ".woff2": "font/woff2",
}
MEDIA_ROOTS = ("exports", "assets")
MAX_MEDIA_FILES = 80
MAX_NAME_LENGTH = 120
CHUNK_SIZE = 64 * 1024
UNSAFE_CHARACTERS = re.compile(r"[^\w.\- ]")
WINDOWS_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL"} | {"{}{}".format(p, n) for p in ("COM", "LPT") for n in range(1, 10)}
RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)$")


class UploadError(Exception):
    """Upload konnte nicht vollständig gespeichert werden."""


def list_media(studio_dir, root, subdir=None, top_level_only=False):
    """Neueste Mediendateien in root – oder nur in dessen Unterordner subdir (z. B. eines Gesprächs)."""
    base = Path(studio_dir) / root
    url_prefix = root
    if subdir:
        base = base / subdir
        url_prefix = "{}/{}".format(root, quote(subdir))
    if not base.is_dir():
        return []
    candidates = base.glob("*") if top_level_only else base.rglob("*")
    files = [p for p in candidates if p.is_file() and p.suffix.lower() in MEDIA_TYPES]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in files[:MAX_MEDIA_FILES]:
        relative = path.relative_to(base).as_posix()
        stat = path.stat()
        result.append({
            "name": relative,
            "url": "/media/{}/{}".format(url_prefix, quote(relative)),
            "type": MEDIA_TYPES[path.suffix.lower()].split("/")[0],
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return result


def safe_upload_name(raw_name):
    """Nur der reine Dateiname, ohne Pfade, versteckte Dateien oder Windows-Gerätenamen."""
    name = UNSAFE_CHARACTERS.sub("_", Path(unquote(raw_name or "")).name).strip()
    if not name or name.startswith("."):
        return None
    if name.split(".")[0].strip().upper() in WINDOWS_DEVICE_NAMES:
        return None
    return name[:MAX_NAME_LENGTH]


def resolve_media(studio_dir, url_path):
    """Löst /media/<root>/<datei> auf – nur innerhalb des jeweiligen Ordners."""
    parts = url_path.split("/", 3)  # ["", "media", root, rest]
    if len(parts) != 4 or parts[2] not in MEDIA_ROOTS:
        return None
    base = (Path(studio_dir) / parts[2]).resolve()
    candidate = (base / unquote(parts[3])).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.is_file() or candidate.suffix.lower() not in MEDIA_TYPES:
        return None
    return candidate


def parse_range(header, size):
    """Gibt (start, ende, teilweise) zurück oder None, wenn der Bereich ungültig ist."""
    match = RANGE_PATTERN.match(header or "")
    if not match or not (match.group(1) or match.group(2)):
        return 0, size - 1, False
    if match.group(1):
        start = int(match.group(1))
        end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
    else:
        start, end = max(0, size - int(match.group(2))), size - 1
    if start > end:
        return None
    return start, end, True


def save_upload(stream, length, target):
    """Schreibt erst in eine temporäre Datei; bei Abbruch bleibt die alte Datei unverändert."""
    temp = target.with_name(target.name + ".upload")
    remaining = length
    try:
        with open(temp, "wb") as handle:
            while remaining > 0:
                chunk = stream.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                handle.write(chunk)
                remaining -= len(chunk)
        if remaining > 0:
            raise UploadError("Upload unvollständig")
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
