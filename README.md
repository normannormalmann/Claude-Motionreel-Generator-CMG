# Claude Motionreel Generator (CMG)

🇬🇧 [English version](README.en.md)

**Dein eigenes Studio für KI-erstellte Motion-Design-Videos, eingerichtet mit einem Doppelklick.**

Du beschreibst Claude in normalen Worten, welches Video du möchtest. Claude baut daraus eine Animation, prüft die Einzelbilder und speichert das fertige Video als MP4-Datei.

Dieses Paket installiert alles, was dafür nötig ist. Technische Vorkenntnisse brauchst du nicht.

---

## Was du brauchst

- Einen Computer mit **Windows 10/11**, **macOS** oder **Linux** (Ubuntu, Debian, Fedora, Arch)
- Eine **Internetverbindung** und etwa **3 GB freien Speicherplatz**
- Ein **Claude-Konto mit Zugang zu Claude Code**, z. B. Claude Pro oder Max
- Etwa **15–30 Minuten**. Der Großteil läuft automatisch.

---

## Installation

### Windows

1. Klicke oben auf dieser Seite auf den grünen Knopf **„Code“** und dann auf **„Download ZIP“**.
2. Öffne deinen Download-Ordner. Klicke mit der rechten Maustaste auf die ZIP-Datei und wähle **„Alle extrahieren“**.
3. Öffne den entpackten Ordner und doppelklicke auf **`Windows-Installation.bat`**.
4. Falls Windows warnt („Der Computer wurde durch Windows geschützt“): Klicke auf **„Weitere Informationen“** und dann auf **„Trotzdem ausführen“**.
5. Fragt Windows zwischendurch „Möchten Sie zulassen, dass …“, klicke auf **„Ja“**.

<details>
<summary>Alternative: Installation mit einer Zeile (für Fortgeschrittene)</summary>

Öffne über das Startmenü **PowerShell**, füge diese Zeile ein und drücke Enter:

```powershell
irm https://raw.githubusercontent.com/normannormalmann/Claude-Motionreel-Generator-CMG/main/install.ps1 -OutFile "$env:TEMP\cmg.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\cmg.ps1"
```
</details>

### Mac

1. Öffne das Programm **Terminal**. Drücke dazu `⌘ Cmd` + `Leertaste`, tippe `Terminal` und drücke Enter.
2. Kopiere diese Zeile, füge sie im Terminal ein (`⌘ Cmd` + `V`) und drücke Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/normannormalmann/Claude-Motionreel-Generator-CMG/main/install.sh | bash
```

3. Wenn du nach deinem **Passwort** gefragt wirst, gib dein Mac-Passwort ein und drücke Enter. **Beim Tippen erscheinen keine Zeichen.** Das ist normal.
4. Bietet dein Mac an, die „Befehlszeilen-Entwicklerwerkzeuge“ zu installieren, klicke auf **„Installieren“**.
5. Fragt dein Mac, ob „Terminal“ auf den Ordner **Dokumente** zugreifen darf, klicke auf **„Erlauben“**.

<details>
<summary>Alternative: Doppelklick statt Terminal</summary>

Lade wie bei Windows die ZIP-Datei herunter und doppelklicke auf **`Mac-Installation.command`**.
Meldet macOS, dass die Datei nicht geöffnet werden kann: Öffne **Systemeinstellungen → Datenschutz & Sicherheit**, scrolle nach unten und klicke auf **„Dennoch öffnen“**.
</details>

### Linux

Öffne ein Terminal, füge diese Zeile ein und drücke Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/normannormalmann/Claude-Motionreel-Generator-CMG/main/install.sh | bash
```

Wenn du nach deinem Passwort gefragt wirst, gib es ein und drücke Enter. Beim Tippen erscheinen keine Zeichen.

---

## Dein erstes Video

1. Doppelklicke auf **„Motion Studio“** auf deinem Schreibtisch bzw. Desktop. Auf dem Mac findest du es auch im Finder unter **Programme**. Das Studio öffnet sich in deinem Browser.
2. Beim ersten Start klickst du auf **„Jetzt anmelden“** und meldest dich mit deinem Claude-Konto an.
3. Klicke unten auf eine Vorlage, z. B. **„Showreel“**, oder beschreibe dein Video in eigenen Worten. Klicke dann auf **„Senden“**.
4. Claude plant, rendert und prüft das Video. Du siehst links, woran Claude gerade arbeitet. Fertige Videos erscheinen rechts und lassen sich direkt abspielen.
5. Für Änderungen schreibst du einfach weiter, z. B. „Mach die zweite Szene langsamer“.

Eigene Musik, Logos oder Bilder ziehst du rechts in das Feld **„Eigene Dateien“**. Mit **„Neues Gespräch“** beginnst du ein neues Projekt. Deine Videos bleiben dabei erhalten.

> **Gut zu wissen:** Damit du nicht bei jedem Schritt etwas bestätigen musst, darf Claude im Studio selbstständig Dateien anlegen und Befehle ausführen, etwa zum Rendern. Das Studio ist nur auf deinem eigenen Computer und nur über das Symbol „Motion Studio“ erreichbar. Claude hat dabei grundsätzlich dieselben Rechte wie du. Gib Claude deshalb nur Dateien und Webseiten zur Verarbeitung, denen du vertraust.

**Wo ist mein Studio-Ordner?**

| System | Ordner |
|---|---|
| Windows | **Dokumente** → `Claude-Motion-Studio` |
| Mac | **Dokumente** → `Claude-Motion-Studio` |
| Linux | **Dokumente** bzw. **Documents** → `Claude-Motion-Studio` |

Darin findest du:

- `exports`: deine fertigen Videos
- `assets`: hier legst du eigene Musik, Logos oder Bilder ab
- `BEISPIEL-PROMPTS.md`: weitere Beispiel-Aufträge
- `CLAUDE.md`: die Arbeitsregeln für Claude. Du kannst sie anpassen.

---

## Was genau installiert wird

| Programm | Wofür |
|---|---|
| **Claude Code** | Die KI, die deine Videos plant und baut |
| **Motion Studio** | Die Oberfläche im Browser, über die du mit Claude arbeitest |
| **Python** mit Playwright, Pillow und NumPy | Steuert das Rendern der Einzelbilder |
| **Chromium** (über Playwright) | Ein unsichtbarer Browser, der die Animation abfotografiert |
| **FFmpeg** | Setzt die Einzelbilder zu einer MP4-Datei zusammen |
| **Node.js** | Hilfswerkzeug für Claude (optional) |
| **Git** (nur Windows) | Wird von Claude Code unter Windows benötigt |
| **Homebrew** (nur Mac) | Paketverwaltung, über die Python und FFmpeg installiert werden |

Die Python-Umgebung liegt bewusst nicht im Ordner Dokumente, sondern im versteckten Programmdaten-Ordner. So bremst sie OneDrive oder iCloud nicht aus.

Bereits installierte Programme werden erkannt und nicht doppelt installiert. Du kannst die Installation gefahrlos erneut starten. Deine eigene `CLAUDE.md` wird dabei nicht überschrieben.

Am Ende rendert der Installer automatisch eine kurze Testanimation. So ist sichergestellt, dass alles funktioniert.

---

## Häufige Probleme

| Problem | Lösung |
|---|---|
| Die Installation bricht mit „FEHLER“ ab | Starte sie einfach noch einmal. Hilft das nicht, schicke die Datei `cmg-install.log` aus deinem Temp-Ordner an den Support. Den Pfad zeigt die Fehlermeldung an. |
| Das Studio öffnet sich nicht | Warte ein paar Sekunden und doppelklicke erneut auf „Motion Studio“. Ein Neustart des Computers hilft ebenfalls. |
| „Verbindung zum Studio unterbrochen“ | Das Studio beendet sich einige Minuten, nachdem du den Browser-Tab geschlossen hast. Starte es einfach wieder über „Motion Studio“. |
| Windows: „winget ist nicht verfügbar“ | Installiere im Microsoft Store die App **„App-Installer“** und starte die Installation erneut. |
| Windows: Python wird nicht gefunden | Installiere Python 3.13 von [python.org](https://www.python.org/downloads/), setze dabei den Haken bei **„Add python.exe to PATH“** und starte die Installation erneut. |
| Das Video zeigt leere oder falsche Bilder | Bitte Claude, `window.seek()`, das Laden der Bilder und Schriften und den Aufnahmezeitpunkt zu prüfen. |
| Das Video wirkt hektisch | Bitte Claude um weniger Szenen, längere Standzeiten und ruhigere Übergänge. |
| Fedora: Der Selbsttest meldet fehlendes H.264 | Aktiviere [RPM Fusion](https://rpmfusion.org/Configuration) und installiere `ffmpeg` daraus. |

---

## Für Fortgeschrittene

- **Anderer Studio-Ordner:** Setze vor der Installation die Umgebungsvariable `CMG_STUDIO_DIR`.
- **Ohne Rückfragen installieren:** `CMG_NONINTERACTIVE=1`
- **Claude Code direkt in der Konsole:** `studio-im-terminal.ps1` (Windows) oder `studio-im-terminal.sh` (Mac/Linux) im Studio-Ordner.
- **Protokoll der Studio-App:** `studio-app.log` im Programmdaten-Ordner (`%LOCALAPPDATA%\Claude-Motion-Studio` bzw. `~/.local/share/claude-motion-studio`).
- Jede Änderung wird automatisch unter Windows, macOS und Ubuntu getestet. Den Stand siehst du unter **Actions**.
