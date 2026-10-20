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


def summarize(record, query=""):
    """Eintrag für die Liste – oder None, wenn die Suche nicht passt."""
    items = record.get("items") or []
    title = conversation_title(items)
    snippet = ""
    if query:
        texts = [str(i.get("text", "")) for i in items if i.get("kind") in SEARCHABLE_KINDS]
        matches = [text for text in texts if query in text.lower()]
        if not matches and query not in title.lower():
            return None
        # Der Titel steht schon da; als Ausschnitt lieber eine andere passende Nachricht zeigen.
        others = [text for text in matches if text.strip().splitlines()[0][:MAX_TITLE] != title]
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


class ConversationArchive:
    def __init__(self, data_dir):
        self.folder = Path(data_dir) / "conversations"

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

    def records(self):
        if not self.folder.is_dir():
            return []
        files = sorted(self.folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for path in files[:MAX_ARCHIVED]:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(record, dict) and valid_id(record.get("id")) and isinstance(record.get("items"), list):
                result.append(record)
        return result

    def search(self, query, current=None):
        """Gespräche, neueste zuerst; mit Suchbegriff nur die passenden (Titel und alle Nachrichten)."""
        query = " ".join(str(query or "").lower().split())
        records = ([current] if current else []) + self.records()
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
