# Beispiel-Aufträge für dein Motion Studio

Kopiere einen der Texte unten, füge ihn im Motion Studio ein und klicke auf „Senden“.
Das Studio legt für jedes Gespräch einen eigenen Ordner in `exports` an und lässt
zuerst immer nur eine Vorschau rendern. Die finale Version in voller Auflösung
bekommst du per Knopf „Finale Version erstellen“ oder mit einer kurzen Bitte.
Ersetze Angaben in [eckigen Klammern] durch deine eigenen.

---

## 1. Dein erstes Video

```
Erstelle in diesem Projekt ein 15 Sekunden langes
Motion-Design-Showreel für ein fiktives Designstudio.

Format: 1920 × 1080 Pixel, 30 fps.
Stil: redaktionell, präzise, große Typografie,
cremefarbener Hintergrund, schwarze Schrift und orange Akzente.

Plane fünf Szenen mit unterschiedlichen Bewegungsideen.
Beginne zunächst ohne Audio.

Lies CLAUDE.md und prüfe die vorhandenen Werkzeuge.
Erstelle dann:
1. Die HTML-Animation mit window.seek(timeInSeconds).
2. Ein Python-Renderskript mit Playwright.
3. Eine Kontaktübersicht der wichtigsten Momente.
4. Nach höchstens zwei visuellen Korrekturrunden
   eine Vorschau als MP4 mit 960 × 540 Pixeln.

Prüfe die erzeugten Bilder tatsächlich.
Achte auf lesbare Texte und saubere Szenenübergänge.
Dokumentiere den genauen Befehl für einen erneuten Export.
```

---

## 2. Eine Szene verbessern

```
Überarbeite nur die zweite Szene:
Der Text soll 0,5 Sekunden länger stehen bleiben.
Reduziere das Überschwingen der Buchstaben.
Erstelle anschließend eine neue Vorschau.
```

---

## 3. Produktvideo mit Ablaufplan

```
Erstelle einen 20-Sekunden-Produktfilm für [Produkt].

Zielgruppe: [Zielgruppe]
Hauptaussage: [Nutzen]
Farben: [Farben]
Abschluss: [Handlungsaufforderung]

0–4 Sekunden: Problem zeigen.
4–9 Sekunden: Produkt vorstellen.
9–15 Sekunden: wichtigste Funktion demonstrieren.
15–20 Sekunden: Nutzen und Abschluss.

Zeige mir zuerst den Szenenplan.
Beginne mit dem Rendering nach meiner Freigabe des Plans.
```

---

## 4. Musik ergänzen

Lege zuerst eine Audiodatei, für die du die Nutzungsrechte hast,
als `music.mp3` in den Ordner `assets`. Dann:

```
Ergänze assets/music.mp3 als Musik.
Passe wichtige Übergänge an den Rhythmus an.
Blende die Musik am Ende aus.
Erstelle eine neue Vorschau mit Ton (Video H.264, Audio AAC).
```

---

## 5. Den Ablauf dauerhaft speichern

Sobald dein erstes Video funktioniert hat:

```
Fasse unseren funktionierenden Ablauf als Projekt-Skill unter
.claude/skills/motion-studio/SKILL.md zusammen.
Dokumentiere die Befehle, Vorschau, visuelle Prüfung,
Audio und MP4-Ausgabe. Verweise auf die vorhandenen Skripte.
```

---

## Tipps

- **Konkret beschreiben:** „Text 0,5 Sekunden länger“ funktioniert besser als „etwas langsamer“.
- **Video wirkt hektisch?** Bitte um weniger Szenen, längere Standzeiten und ruhigere Übergänge.
- **Leere oder falsche Bilder?** Bitte Claude, `window.seek()`, das Laden der Bilder/Schriften und den Aufnahmezeitpunkt zu prüfen.
