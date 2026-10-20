# Motion Design Studio

## Umgebung
- Dieses Projekt läuft unter {{BETRIEBSSYSTEM}}.
- {{SHELL_HINWEIS}}
- Python: `{{PYTHON}}`
  - Diesen Pfad direkt aufrufen (in Anführungszeichen); die Umgebung muss nicht aktiviert werden.
  - Sie liegt bewusst außerhalb des Studio-Ordners, damit Cloud-Synchronisierung (OneDrive/iCloud) nicht stört. Lege im Studio-Ordner keine eigene .venv an.
- Temporäre Einzelbilder möglichst im System-Temp-Ordner ablegen und nach dem Export löschen, damit sie nicht synchronisiert werden.
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
- Standard für die finale Version: 1920 × 1080 Pixel, 30 Bilder pro Sekunde.
- Rendere bei neuen Videos und Änderungen immer nur eine Vorschau in niedriger Auflösung (halbe Breite und Höhe, z. B. 960 × 540) und speichere sie als `<name>_vorschau.mp4`.
- Die finale Version in voller Auflösung nur, wenn die Person ausdrücklich darum bittet. Biete sie am Ende an.
- MP4 mit H.264 und Pixelformat yuv420p exportieren.
- Im Motion Studio hat jedes Gespräch einen eigenen Ordner, den das Studio mit jedem Auftrag nennt: Ergebnisse in `exports/<Gespräch>/`, Quelldateien in `projekte/<Gespräch>/`. Ohne diese Angabe gehören Ergebnisse in `exports`.
- Temporäre Einzelbilder getrennt von Quelldateien und Ergebnissen speichern.
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
