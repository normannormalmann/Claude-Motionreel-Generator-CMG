"""Archiv früherer Gespräche: speichern, durchsuchen, wieder öffnen.

Jedes Gespräch liegt als eigene JSON-Datei im App-Datenordner (nicht im synchronisierten
Studio-Ordner). Das aktuelle Gespräch verwaltet weiterhin claude_bridge.StudioBridge.
"""

import json
import os
import re
import time
from pathlib import Path

ID_PATTERN = re.compile(r"\w[\w-]{0,79}")
MAX_TITLE = 80
MAX_RESULTS = 100
MAX_ARCHIVED = 1000
SNIPPET_RADIUS = 60
SEARCHABLE_KINDS = ("user", "assistant")
MARKDOWN_MARKS = re.compile(r"[*`]+")


class ConversationNotFoundError(Exception):
    """Das Gespräch gibt es nicht (mehr)."""


def valid_id(value):
    return isinstance(value, str) and bool(ID_PATTERN.fullmatch(value))


def conversation_title(items):
    for item in items:
        if item.get("kind") == "user" and str(item.get("text", "")).strip():
            return str(item["text"]).strip().splitlines()[0][:MAX_TITLE]
    return "Gespräch ohne Auftrag"


def _snippet(text, query):
    """Kurzer Ausschnitt rund um den ersten Treffer."""
    position = text.lower().find(query)
    start = max(0, position - SNIPPET_RADIUS)
    end = min(len(text), position + len(query) + SNIPPET_RADIUS)
    snippet = " ".join(MARKDOWN_MARKS.sub("", text[start:end]).split())
    return ("…" if start else "") + snippet + ("…" if end < len(text) else "")


def _normalize(text):
    return " ".join(str(text).split())


def summarize(record, query=""):
    """Eintrag für die Liste – oder None, wenn die Suche nicht passt."""
    items = record.get("items") or []
    title = conversation_title(items)
    snippet = ""
    if query:
        # Zeilenumbrüche und doppelte Leerzeichen zählen wie ein Leerzeichen.
        texts = [_normalize(i.get("text", "")) for i in items if i.get("kind") in SEARCHABLE_KINDS]
        matches = [text for text in texts if query in text.lower()]
        if not matches and query not in title.lower():
            return None
        # Der Titel steht schon da; als Ausschnitt lieber eine andere passende Nachricht zeigen.
        others = [text for text in matches if not text.startswith(_normalize(title))]
        snippet = _snippet(others[0], query) if others else ""
    return {
        "id": record["id"],
        "title": title,
        "folder": record.get("folder"),
        "engine": record.get("engine"),
        "updated": record.get("updated") or 0,
        "messages": sum(1 for item in items if item.get("kind") == "user"),
        "snippet": snippet,
    }


def _valid_record(record):
    return (isinstance(record, dict) and valid_id(record.get("id")) and isinstance(record.get("items"), list)
            and all(isinstance(item, dict) for item in record["items"])
            and isinstance(record.get("updated", 0), (int, float)))


class ConversationArchive:
    def __init__(self, data_dir):
        self.folder = Path(data_dir) / "conversations"
        self._cache = {}  # Pfad -> (Änderungszeit, Gespräch): Die Suche liest nur Geändertes neu.

    def _path(self, conversation_id):
        if not valid_id(conversation_id):
            raise ConversationNotFoundError()
        return self.folder / (conversation_id + ".json")

    def save(self, record):
        """Speichert ein Gespräch (überschreibt eine ältere Fassung mit derselben Kennung)."""
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self._path(record["id"])
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, target)

    def load(self, conversation_id):
        try:
            record = json.loads(self._path(conversation_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ConversationNotFoundError()
        if not isinstance(record, dict) or record.get("id") != conversation_id:
            raise ConversationNotFoundError()
        return record

    def remove(self, conversation_id):
        try:
            self._path(conversation_id).unlink()
        except OSError:
            pass

    def exists(self, conversation_id):
        return valid_id(conversation_id) and self._path(conversation_id).exists()

    def unique_id(self, base):
        """Eine Kennung, die es im Archiv noch nicht gibt (z. B. nach einem gelöschten Ordner)."""
        candidate, number = base, 2
        while self.exists(candidate):
            candidate, number = "{}-{}".format(base, number), number + 1
        return candidate

    def _read(self, path):
        try:
            mtime = path.stat().st_mtime
            cached = self._cache.get(path)
            if cached and cached[0] == mtime:
                return mtime, cached[1]
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not _valid_record(record):
            return None
        self._cache[path] = (mtime, record)
        return mtime, record

    def records(self):
        if not self.folder.is_dir():
            return []
        entries = [entry for entry in (self._read(path) for path in self.folder.glob("*.json")) if entry]
        entries.sort(key=lambda entry: entry[0], reverse=True)
        return [record for _, record in entries[:MAX_ARCHIVED]]

    def search(self, query, current=None):
        """Gespräche, neueste zuerst; mit Suchbegriff nur die passenden (Titel und alle Nachrichten)."""
        query = _normalize(query or "").lower()
        current_id = current["id"] if current else None
        archived = [record for record in self.records() if record["id"] != current_id]
        records = ([current] if current else []) + archived
        summaries = []
        for record in records:
            summary = summarize(record, query)
            if summary:
                summary["current"] = record is current
                summaries.append(summary)
        summaries.sort(key=lambda s: (not s["current"], -s["updated"]))
        return summaries[:MAX_RESULTS]


def new_conversation_id(folder):
    """Kennung eines Gesprächs: sein Ordnername – für Gespräche ohne Ordner ein Zeitstempel."""
    return folder if valid_id(folder) else "gespraech-{}".format(int(time.time() * 1000))
