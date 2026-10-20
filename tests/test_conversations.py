"""Tests für das Gesprächsarchiv (conversations.py)."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio-app"))

import conversations  # noqa: E402


def record(conversation_id, *texts, updated=1.0, answer="Fertig."):
    items = []
    for text in texts:
        items += [{"kind": "user", "text": text}, {"kind": "tool", "text": "Erstellt x.html"},
                  {"kind": "assistant", "text": answer}, {"kind": "done"}]
    return {"id": conversation_id, "items": items, "sessions": {}, "engine": "claude",
            "folder": conversation_id, "updated": updated}


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.archive = conversations.ConversationArchive(temp.name)

    def test_save_load_and_remove(self):
        self.archive.save(record("2026-10-20_1412_Intro", "Intro für Studio Nord"))
        self.assertEqual(self.archive.load("2026-10-20_1412_Intro")["items"][0]["text"], "Intro für Studio Nord")
        self.archive.remove("2026-10-20_1412_Intro")
        with self.assertRaises(conversations.ConversationNotFoundError):
            self.archive.load("2026-10-20_1412_Intro")

    def test_ids_cannot_escape_the_archive(self):
        for bad in ("../session", "a/b", "..", "", None, ".versteckt"):
            with self.assertRaises(conversations.ConversationNotFoundError):
                self.archive.load(bad)

    def test_search_finds_titles_and_all_messages_case_insensitive(self):
        self.archive.save(record("a", "Showreel für Studio Nord", updated=1))
        self.archive.save(record("b", "Produktfilm", "Mach das LOGO größer", updated=2))
        self.archive.save(record("c", "Reel", answer="Ich habe die Musik von Café Blau eingebaut.", updated=3))
        self.assertEqual([s["id"] for s in self.archive.search("")], ["c", "b", "a"])
        self.assertEqual([s["id"] for s in self.archive.search("studio nord")], ["a"])
        hits = self.archive.search("logo")
        self.assertEqual([s["id"] for s in hits], ["b"])
        self.assertIn("LOGO", hits[0]["snippet"])
        self.assertEqual([s["id"] for s in self.archive.search("café   blau")], ["c"])
        self.assertEqual(self.archive.search("showreel")[0]["snippet"], "", "Titel wird nicht wiederholt")
        self.assertEqual(self.archive.search("gibt es nicht"), [])
        self.assertEqual(self.archive.search("x.html"), [], "Arbeitsschritte werden nicht durchsucht")

    def test_search_ignores_line_breaks_and_survives_odd_files(self):
        self.archive.save(record("a", "Reel", answer="Das Logo\n\nerscheint   groß."))
        self.assertEqual([s["id"] for s in self.archive.search("logo erscheint")], ["a"])
        for name, content in (("liste", '{"id": "liste", "items": ["kein dict"]}'),
                              ("zeit", '{"id": "zeit", "items": [], "updated": "gestern"}')):
            (self.archive.folder / (name + ".json")).write_text(content, encoding="utf-8")
        self.assertEqual([s["id"] for s in self.archive.search("")], ["a"])

    def test_unique_ids_never_overwrite_archived_conversations(self):
        self.archive.save(record("2026-10-20_1412_Intro", "Alt"))
        self.assertEqual(self.archive.unique_id("2026-10-20_1412_Intro"), "2026-10-20_1412_Intro-2")
        self.assertEqual(self.archive.unique_id("neu"), "neu")

    def test_current_conversation_is_not_listed_twice(self):
        self.archive.save(record("gleich", "Überbleibsel"))
        results = self.archive.search("", record("gleich", "Aktuell"))
        self.assertEqual([(s["title"], s["current"]) for s in results], [("Aktuell", True)])

    def test_snippet_has_no_markdown_marks(self):
        self.archive.save(record("a", "Reel", answer="Fertig: **reel_vorschau.mp4** in `exports`"))
        self.assertEqual(self.archive.search("vorschau")[0]["snippet"], "Fertig: reel_vorschau.mp4 in exports")

    def test_current_conversation_is_listed_first(self):
        self.archive.save(record("alt", "Altes Video", updated=99))
        current = record("neu", "Neues Video", updated=1)
        results = self.archive.search("", current)
        self.assertEqual([(s["id"], s["current"]) for s in results], [("neu", True), ("alt", False)])

    def test_summary_counts_requests_and_titles(self):
        summary = conversations.summarize(record("a", "Erste Zeile\nzweite Zeile", "Noch was"))
        self.assertEqual((summary["title"], summary["messages"]), ("Erste Zeile", 2))
        self.assertEqual(conversations.conversation_title([]), "Gespräch ohne Auftrag")

    def test_broken_files_are_ignored(self):
        self.archive.save(record("gut", "Intro"))
        (self.archive.folder / "kaputt.json").write_text("{nicht json", encoding="utf-8")
        (self.archive.folder / "falsch.json").write_text('{"id": "../x", "items": []}', encoding="utf-8")
        self.assertEqual([s["id"] for s in self.archive.search("")], ["gut"])


if __name__ == "__main__":
    unittest.main()
