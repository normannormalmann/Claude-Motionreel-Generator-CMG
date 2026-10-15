# Motion Design Studio

## Umgebung
- Dieses Projekt läuft unter {{BETRIEBSSYSTEM}}.
- {{SHELL_HINWEIS}}
- Python: {{PYTHON}} (die virtuelle Umgebung muss nicht aktiviert werden).
- Playwright mit Chromium ist installiert.
- FFmpeg steht über PATH zur Verfügung.
- `tools/selbsttest.py` prüft die komplette Render-Kette (Playwright → Bilder → FFmpeg → MP4).

## Technischer Aufbau
- Erstelle Animationen zunächst mit HTML, CSS und JavaScript.
- Stelle eine Funktion window.seek(timeInSeconds) bereit.
- Jeder Zeitpunkt muss unabhängig und reproduzierbar renderbar sein.
- Verwende beim Export keine laufende Echtzeituhr.
- Warte vor Aufnahmen auf geladene Schriften und Bilder.
- Verwende für reproduzierbare Zufallseffekte einen festen Seed.

## Ausgabe
- Standard: 1920 × 1080 Pixel, 30 Bilder pro Sekunde.
- Vorschau zuerst in reduzierter Auflösung rendern.
- MP4 mit H.264 und Pixelformat yuv420p exportieren.
- Quelldateien, temporäre Bilder und Ergebnisse getrennt speichern.
- Ergebnisse gehören in den Ordner exports.
- Eigene Medien (Musik, Logos, Bilder) liegen im Ordner assets.

## Gestaltung
- Klare Typografie und gut lesbare Texte.
- Eine nachvollziehbare visuelle Idee pro Szene.
- Bewegungen mit gezielter Beschleunigung und Abbremsung.
- Keine unmotivierten Partikel, Glows oder Übergänge.

## Qualitätsprüfung
- Erstelle nach jedem Entwurf eine Kontaktübersicht.
- Prüfe Überlagerungen, abgeschnittene Texte und leere Frames.
- Prüfe besonders die Übergänge zwischen Szenen.
- Benenne konkrete Fehler und korrigiere sie.
- Beschränke automatische Überarbeitungen zunächst auf zwei Runden.

## Zusammenarbeit
- Die Person, mit der du arbeitest, hat eventuell keine technischen Vorkenntnisse.
- Erkläre Ergebnisse und nächste Schritte in einfachen Worten, ohne Fachjargon.
- Nenne am Ende immer den Speicherort des fertigen Videos.
