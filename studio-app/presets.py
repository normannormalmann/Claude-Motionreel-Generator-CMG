"""Vorlagen (Presets): eingebaute und eigene Aufträge, optional mit Marken-Vorgaben.

Eigene Vorlagen liegen als presets.json im Studio-Ordner, damit sie mit
gesichert und weitergegeben werden können.
"""

import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

FILE_NAME = "presets.json"
FILE_VERSION = 1
MAX_PRESETS = 200
MAX_NAME = 80
MAX_TEXT = 8000
MAX_FONTS = 120
MAX_NOTES = 1000
MAX_COLORS = 6
MAX_DURATION_SECONDS = 600
FORMATS = ("16:9", "9:16", "1:1", "4:5")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_PATTERN = re.compile(r"^assets/[^\\:*?\"<>|\x00-\x1f]+\.(png|jpe?g|gif|webp)$", re.IGNORECASE)
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")

SHOWREEL_TEXT = (
    "Erstelle ein 15 Sekunden langes Motion-Design-Showreel für ein fiktives Designstudio.\n"
    "Format: 1920 × 1080 Pixel, 30 fps.\n"
    "Stil: redaktionell, präzise, große Typografie, cremefarbener Hintergrund, schwarze Schrift und orange Akzente.\n"
    "Plane fünf Szenen mit unterschiedlichen Bewegungsideen. Beginne zunächst ohne Audio.\n\n"
    "Lies CLAUDE.md und prüfe die vorhandenen Werkzeuge. Erstelle dann:\n"
    "1. Die HTML-Animation mit window.seek(timeInSeconds).\n2. Ein Python-Renderskript mit Playwright.\n"
    "3. Eine Vorschau mit 960 × 540 Pixeln.\n4. Eine Kontaktübersicht der Vorschau.\n"
    "5. Nach höchstens zwei visuellen Korrekturrunden den vollständigen MP4-Export.\n\n"
    "Prüfe die erzeugten Bilder tatsächlich. Achte auf lesbare Texte und saubere Szenenübergänge.\n"
    "Speichere das fertige Video als exports/showreel.mp4."
)
PRODUCT_TEXT = (
    "Erstelle einen 20-Sekunden-Produktfilm für [Produkt].\n\n"
    "Zielgruppe: [Zielgruppe]\nHauptaussage: [Nutzen]\nAbschluss: [Handlungsaufforderung]\n\n"
    "0–4 Sekunden: Problem zeigen.\n4–9 Sekunden: Produkt vorstellen.\n"
    "9–15 Sekunden: wichtigste Funktion demonstrieren.\n15–20 Sekunden: Nutzen und Abschluss.\n\n"
    "Zeige mir zuerst den Szenenplan. Beginne mit dem Rendering nach meiner Freigabe des Plans."
)
REEL_TEXT = (
    "Erstelle ein Instagram-Reel über [Thema].\n"
    "Die erste Sekunde muss sofort Aufmerksamkeit erzeugen.\n"
    "Halte alle Texte groß, kurz und innerhalb der sicheren Zone (oben und unten je 250 Pixel frei).\n"
    "Schließe mit dieser Aufforderung: [Handlungsaufforderung]."
)

BUILTIN_PRESETS = (
    {"id": "builtin-showreel", "name": "Showreel", "text": SHOWREEL_TEXT, "brand": None},
    {"id": "builtin-produktfilm", "name": "Produktfilm", "text": PRODUCT_TEXT, "brand": None},
    {"id": "builtin-reel", "name": "Instagram-Reel", "text": REEL_TEXT,
     "brand": {"format": "9:16", "duration": 15, "colors": [], "fonts": "", "logo": "", "notes": ""}},
    {"id": "builtin-szene", "name": "Szene ändern", "brand": None, "text": (
        "Überarbeite nur die zweite Szene:\nDer Text soll 0,5 Sekunden länger stehen bleiben.\n"
        "Reduziere das Überschwingen der Buchstaben.\nErstelle anschließend eine neue Vorschau.")},
    {"id": "builtin-musik", "name": "Musik ergänzen", "brand": None, "text": (
        "Ergänze assets/music.mp3 als Musik.\nPasse wichtige Übergänge an den Rhythmus an.\n"
        "Blende die Musik am Ende aus.\nExportiere Video mit H.264 und Audio mit AAC.")},
)


class PresetError(ValueError):
    """Ungültige Vorlage – die Meldung ist für Menschen gedacht."""


def _clean_text(value, limit, label, required=False, single_line=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise PresetError("{} muss ein Text sein.".format(label))
    text = value.strip()
    if single_line and CONTROL_CHARACTERS.search(text):
        raise PresetError("{} darf keine Zeilenumbrüche oder Steuerzeichen enthalten.".format(label))
    if required and not text:
        raise PresetError("Bitte {} angeben.".format(label))
    if len(text) > limit:
        raise PresetError("{} ist zu lang (höchstens {} Zeichen).".format(label, limit))
    return text


def _clean_brand(raw):
    if not raw or not isinstance(raw, dict):
        return None
    colors = raw.get("colors") or []
    if not isinstance(colors, list) or len(colors) > MAX_COLORS:
        raise PresetError("Höchstens {} Farben sind möglich.".format(MAX_COLORS))
    for color in colors:
        if not isinstance(color, str) or not COLOR_PATTERN.match(color):
            raise PresetError("Ungültige Farbe: {}".format(color))
    brand_format = raw.get("format") or ""
    if brand_format and brand_format not in FORMATS:
        raise PresetError("Unbekanntes Format: {}".format(brand_format))
    duration = raw.get("duration") or 0
    try:
        duration = int(duration)
    except (TypeError, ValueError, OverflowError):
        raise PresetError("Die Länge muss eine Zahl in Sekunden sein.")
    if not 0 <= duration <= MAX_DURATION_SECONDS:
        raise PresetError("Die Länge darf höchstens {} Sekunden betragen.".format(MAX_DURATION_SECONDS))
    logo = _clean_text(raw.get("logo"), MAX_FONTS, "Das Logo", single_line=True)
    if logo and (".." in logo or not LOGO_PATTERN.match(logo)):
        raise PresetError("Das Logo muss eine Bilddatei im Ordner assets sein.")
    brand = {
        "format": brand_format,
        "duration": duration,
        "colors": [c.upper() for c in colors],
        "fonts": _clean_text(raw.get("fonts"), MAX_FONTS, "Schriften", single_line=True),
        "logo": logo,
        "notes": _clean_text(raw.get("notes"), MAX_NOTES, "Hinweise"),
    }
    has_content = any(brand[key] for key in brand)
    return brand if has_content else None


def validate(raw):
    """Prüft eine Vorlage und gibt eine bereinigte Kopie zurück."""
    if not isinstance(raw, dict):
        raise PresetError("Ungültige Vorlage.")
    return {
        "name": _clean_text(raw.get("name"), MAX_NAME, "einen Namen", required=True),
        "text": _clean_text(raw.get("text"), MAX_TEXT, "einen Auftragstext", required=True),
        "brand": _clean_brand(raw.get("brand")),
    }


class PresetStore:
    def __init__(self, studio_dir):
        self.path = Path(studio_dir) / FILE_NAME
        self._lock = threading.Lock()

    # ------------------------------------------------------------ Datei

    def _backup_path(self, suffix):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return self.path.with_name("{}.{}-{}-{}".format(FILE_NAME, suffix, stamp, uuid.uuid4().hex[:6]))

    def _load_user_presets(self):
        """Liest eigene Vorlagen. Gibt (vorlagen, unvollständig) zurück."""
        if not self.path.exists():
            return [], False
        try:
            raw_text = self.path.read_text(encoding="utf-8")
        except OSError:
            # Z. B. kurz gesperrt durch Virenscanner oder Cloud-Synchronisierung: nichts verändern.
            raise PresetError("Die Vorlagen konnten gerade nicht gelesen werden. Bitte gleich noch einmal versuchen.")
        try:
            data = json.loads(raw_text)
        except (ValueError, RecursionError):
            # Defekte Datei nicht überschreiben, sondern mit Zeitstempel beiseitelegen.
            try:
                os.replace(self.path, self._backup_path("defekt"))
            except OSError:
                raise PresetError("Die Vorlagen-Datei ist beschädigt und konnte nicht gesichert werden.")
            return [], False
        entries = data.get("presets") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            return [], True
        presets = []
        for entry in entries:
            try:
                if not isinstance(entry, dict) or not entry.get("id"):
                    raise PresetError("ohne Kennung")
                presets.append(dict(validate(entry), id=str(entry["id"])))
            except PresetError:
                continue
        return presets, len(presets) != len(entries)

    def _write(self, presets, incomplete):
        """Speichert; wurden beim Lesen Einträge verworfen, bleibt das Original als Sicherung erhalten."""
        if incomplete and self.path.exists():
            shutil.copy2(self.path, self._backup_path("sicherung"))
        self._save_user_presets(presets)

    def _save_user_presets(self, presets):
        temp = self.path.with_name(FILE_NAME + ".tmp")
        data = {"version": FILE_VERSION, "presets": presets}
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    # ------------------------------------------------------------ Zugriff

    def list_all(self):
        with self._lock:
            user, _ = self._load_user_presets()
        builtins = [dict(p, builtin=True) for p in BUILTIN_PRESETS]
        return builtins + [dict(p, builtin=False) for p in user]

    def save(self, raw):
        """Legt eine Vorlage an oder ändert eine eigene. Eingebaute bleiben unverändert."""
        preset = validate(raw)
        preset_id = str(raw.get("id") or "")
        if preset_id.startswith("builtin-"):
            raise PresetError("Eingebaute Vorlagen können nicht geändert werden. Lege eine Kopie an.")
        with self._lock:
            presets, incomplete = self._load_user_presets()
            existing = next((i for i, p in enumerate(presets) if p["id"] == preset_id), None)
            if existing is None:
                if len(presets) >= MAX_PRESETS:
                    raise PresetError("Es sind höchstens {} eigene Vorlagen möglich.".format(MAX_PRESETS))
                preset["id"] = uuid.uuid4().hex
                presets = presets + [preset]
            else:
                preset["id"] = preset_id
                presets = presets[:existing] + [preset] + presets[existing + 1:]
            self._write(presets, incomplete)
        return dict(preset, builtin=False)

    def delete(self, preset_id):
        with self._lock:
            presets, incomplete = self._load_user_presets()
            remaining = [p for p in presets if p["id"] != preset_id]
            if len(remaining) == len(presets):
                raise PresetError("Diese Vorlage gibt es nicht (mehr).")
            self._write(remaining, incomplete)

    def import_presets(self, items):
        """Übernimmt gültige Vorlagen als neue Kopien. Gibt (übernommen, übersprungen) zurück."""
        if isinstance(items, dict):
            items = items.get("presets", [])
        if not isinstance(items, list):
            raise PresetError("Die Datei enthält keine Vorlagen.")
        imported, skipped = [], 0
        for item in items:
            try:
                imported.append(dict(validate(item), id=uuid.uuid4().hex))
            except PresetError:
                skipped += 1
        with self._lock:
            presets, incomplete = self._load_user_presets()
            room = max(0, MAX_PRESETS - len(presets))
            accepted = imported[:room]
            skipped += len(imported) - len(accepted)
            self._write(presets + accepted, incomplete)
        return len(accepted), skipped

    def export(self):
        with self._lock:
            presets, _ = self._load_user_presets()
        return {"version": FILE_VERSION, "presets": [{k: v for k, v in p.items() if k != "id"} for p in presets]}
