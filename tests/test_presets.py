"""Tests für Vorlagen: Speicherung, Prüfung, HTTP-Schnittstelle und Bedienung im Browser."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio-app"))
sys.path.insert(0, str(ROOT / "tests"))

import presets  # noqa: E402
from presets import PresetError, PresetStore  # noqa: E402
from test_studio_app import WAIT_SECONDS, ServerTestCase  # noqa: E402

BRAND = {"format": "9:16", "duration": 15, "colors": ["#e8551f", "#1B1A17"],
         "fonts": "Inter", "logo": "assets/logo.png", "notes": "Locker, per Du"}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = PresetStore(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_builtins_come_first_and_are_read_only(self):
        listed = self.store.list_all()
        self.assertTrue(all(p["builtin"] for p in listed[:len(presets.BUILTIN_PRESETS)]))
        with self.assertRaises(PresetError):
            self.store.save({"id": "builtin-showreel", "name": "X", "text": "Y"})

    def test_create_update_delete_roundtrip(self):
        created = self.store.save({"name": "Café-Intro", "text": "Intro für [Café]", "brand": BRAND})
        self.assertEqual(created["brand"]["colors"], ["#E8551F", "#1B1A17"])
        self.store.save({"id": created["id"], "name": "Café-Intro 2", "text": "Neu"})
        reloaded = PresetStore(self.temp.name).list_all()[-1]
        self.assertEqual((reloaded["name"], reloaded["text"], reloaded["brand"]), ("Café-Intro 2", "Neu", None))
        self.store.delete(created["id"])
        self.assertEqual(len(self.store.list_all()), len(presets.BUILTIN_PRESETS))

    def test_invalid_input_is_rejected_with_readable_message(self):
        cases = [
            {"name": "", "text": "x"},
            {"name": "x", "text": ""},
            {"name": "x" * 81, "text": "x"},
            {"name": "x", "text": "x", "brand": {"colors": ["rot"]}},
            {"name": "x", "text": "x", "brand": {"format": "21:9"}},
            {"name": "x", "text": "x", "brand": {"duration": 9999}},
            {"name": "x", "text": "x", "brand": {"logo": "../geheim.png"}},
            {"name": "x", "text": "x", "brand": {"logo": "assets/../../geheim.png"}},
            {"name": "x", "text": "x", "brand": {"colors": ["#000000"] * 7}},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(PresetError):
                self.store.save(case)

    def test_empty_brand_is_stored_as_none(self):
        saved = self.store.save({"name": "x", "text": "y", "brand": {"format": "", "colors": [], "duration": 0}})
        self.assertIsNone(saved["brand"])

    def test_import_creates_copies_and_skips_invalid(self):
        imported, skipped = self.store.import_presets({"presets": [
            {"name": "A", "text": "a"}, {"name": "", "text": "kaputt"}, {"name": "B", "text": "b", "brand": BRAND},
        ]})
        self.assertEqual((imported, skipped), (2, 1))
        exported = self.store.export()["presets"]
        self.assertEqual([p["name"] for p in exported], ["A", "B"])
        self.assertNotIn("id", exported[0])

    def test_corrupt_file_is_set_aside_not_overwritten(self):
        path = Path(self.temp.name) / presets.FILE_NAME
        path.write_text("{kaputt", encoding="utf-8")
        self.assertEqual(len(self.store.list_all()), len(presets.BUILTIN_PRESETS))
        self.assertTrue((Path(self.temp.name) / (presets.FILE_NAME + ".defekt")).exists())


class PresetApiTests(ServerTestCase):
    def test_save_list_export_import_delete(self):
        status, data, _ = self.request("POST", "/api/presets/save",
                                       body={"preset": {"name": "Reel", "text": "Über [Thema]", "brand": BRAND}})
        self.assertEqual(status, 200)
        preset_id = json.loads(data)["preset"]["id"]

        _, data, _ = self.request("GET", "/api/presets")
        names = [p["name"] for p in json.loads(data)["presets"]]
        self.assertIn("Reel", names)
        self.assertIn("Showreel", names)

        status, data, response = self.request("GET", "/api/presets/export")
        self.assertIn("attachment", response.getheader("Content-Disposition"))
        exported = data

        status, data, _ = self.request("POST", "/api/presets/import", body=exported,
                                       headers={"Content-Type": "application/json"})
        self.assertEqual(json.loads(data), {"imported": 1, "skipped": 0})

        self.request("POST", "/api/presets/delete", body={"id": preset_id})
        _, data, _ = self.request("GET", "/api/presets")
        self.assertEqual([p["name"] for p in json.loads(data)["presets"]].count("Reel"), 1)

    def test_invalid_preset_returns_400_with_message(self):
        status, data, _ = self.request("POST", "/api/presets/save", body={"preset": {"name": "", "text": "x"}})
        self.assertEqual(status, 400)
        self.assertIn("Namen", json.loads(data)["error"])

    def test_invalid_import_returns_400(self):
        status, _, _ = self.request("POST", "/api/presets/import", body=b"kein json",
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_presets_require_session(self):
        status, _, _ = self.request("GET", "/api/presets", session=False)
        self.assertEqual(status, 403)


class PresetBrowserTests(ServerTestCase):
    """Legt eine Vorlage mit Platzhalter und Marken-Vorgaben an und verwendet sie."""

    def test_create_fill_and_delete_preset(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright nicht installiert")
        (self.studio / "assets" / "logo.png").write_bytes(b"x")
        timeout = WAIT_SECONDS * 1000
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.on("dialog", lambda dialog: dialog.accept())
                page.goto(self.server.launch_url)
                page.locator("#assets li").first.wait_for(timeout=timeout)

                page.locator("#prompt").fill("Erstelle ein Intro für [Firma] mit Fokus auf [Thema].")
                page.get_by_role("button", name="＋ Als Vorlage speichern").click()
                page.locator("#ed-name").fill("Firmen-Intro")
                self.assertIn("Firma, Thema", page.locator("#ed-placeholders").inner_text())
                page.locator("#ed-brand-box summary").click()
                page.locator("#ed-format").select_option("9:16")
                page.locator("#ed-duration").fill("12")
                page.get_by_role("button", name="＋ Farbe").click()
                page.locator("#ed-logo").select_option("assets/logo.png")
                page.locator("#ed-save").click()

                page.get_by_role("button", name="Firmen-Intro").click()
                page.locator("#fill-form input").nth(0).fill("Studio Nord")
                page.locator("#fill-form input").nth(1).fill("Nachhaltigkeit")
                page.locator("#fill-apply").click()
                prompt = page.locator("#prompt").input_value()
                for expected in ("Studio Nord", "Nachhaltigkeit", "9:16 Hochformat", "12 Sekunden",
                                 "#E8551F", "assets/logo.png"):
                    self.assertIn(expected, prompt)

                page.get_by_role("button", name="Vorlagen verwalten").click()
                item = page.locator("#preset-list li", has_text="Firmen-Intro")
                item.get_by_role("button", name="Löschen").click()
                page.locator("#preset-list li", has_text="Firmen-Intro").wait_for(state="detached", timeout=timeout)
                self.assertFalse(json.loads((self.studio / "presets.json").read_text(encoding="utf-8"))["presets"])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
