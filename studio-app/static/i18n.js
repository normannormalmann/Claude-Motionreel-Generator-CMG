/* Sprachen der Oberfläche. Deutsch ist der Ausgangstext; EN ordnet jedem deutschen Text die englische Fassung zu.
   Platzhalter heißen {0}, {1} … Auch Meldungen des Servers (der immer deutsch antwortet) laufen hierüber. */
(() => {
  'use strict';

  const STORAGE_KEY = 'studio-lang';
  const LANGUAGES = ['de', 'en'];
  const MAX_NESTING = 3;

  const EN = {
    // Kopfzeile und Gespräch
    'Update verfügbar': 'Update available',
    'Modell': 'Model',
    'Opus – beste Qualität': 'Opus – best quality',
    'Sonnet – schneller': 'Sonnet – faster',
    'GPT-6-Astra – beste Qualität': 'GPT-6-Astra – best quality',
    'GPT-6.1-Sol – schneller': 'GPT-6.1-Sol – faster',
    'Gespräche': 'Conversations',
    'Ordner öffnen': 'Open folder',
    'Neues Gespräch': 'New conversation',
    'Gespräch mit Claude': 'Conversation with Claude',
    'Was möchtest du heute erstellen?': 'What would you like to create today?',
    'Beschreibe dein Video in eigenen Worten oder wähle unten eine Vorlage. Die KI plant, rendert und prüft das Video. Fertige Videos erscheinen rechts. Oben unter „Modell“ wählst du zwischen Claude und ChatGPT.':
      'Describe your video in your own words or pick a template below. The AI plans, renders and checks the video. Finished videos appear on the right. Use “Model” at the top to choose between Claude and ChatGPT.',
    'Die KI arbeitet …': 'The AI is working …',
    'Abbrechen': 'Cancel',
    'Vorlagen': 'Templates',
    'Zum Beispiel: Erstelle ein 10-Sekunden-Intro für mein Café „Bohne & Blatt“ in warmen Farben …':
      'For example: Create a 10-second intro for my café “Bean & Leaf” in warm colours …',
    'Strg/⌘ + Enter zum Senden': 'Ctrl/⌘ + Enter to send',
    'Senden': 'Send',
    'Videos dieses Gesprächs': 'Videos in this conversation',
    'Ordner dieses Gesprächs öffnen': 'Open this conversation’s folder',
    'Ordner': 'Folder',
    'Noch keine Videos in diesem Gespräch. Starte links mit einem Auftrag.':
      'No videos in this conversation yet. Start with a request on the left.',
    'Eigene Dateien': 'Your files',
    'Musik, Logos oder Bilder': 'Music, logos or images',
    'hierher ziehen oder klicken': 'drag here or click',
    '{0} arbeitet … {1}': '{0} is working … {1}',
    '✓ Fertig': '✓ Done',
    'Vorschau': 'Preview',
    'Final': 'Final',
    'Finale Version erstellen': 'Create final version',
    'Rendert dieses Video in voller Auflösung': 'Renders this video in full resolution',
    'Bitte erstelle jetzt die finale Version von {0} in voller Auflösung.':
      'Please create the final version of {0} in full resolution now.',
    'Neues Video: {0}': 'New video: {0}',
    'Vorschaubilder': 'Preview images',
    'Hochgeladen: {0} – du kannst die KI bitten, assets/{0} zu verwenden.':
      'Uploaded: {0} – you can ask the AI to use assets/{0}.',
    'Es läuft gerade noch ein Auftrag.': 'A request is still running.',
    'Neues Gespräch beginnen? Deine Videos und Dateien bleiben erhalten.':
      'Start a new conversation? Your videos and files will be kept.',
    'Verbindung zum Studio unterbrochen. Bitte „Motion Studio“ neu starten.':
      'Lost connection to the studio. Please restart “Motion Studio”.',
    'Bitte öffne das Studio erneut über das Symbol „Motion Studio“.':
      'Please open the studio again using the “Motion Studio” icon.',
    'Unbekannter Fehler': 'Unknown error',

    // Unterstützen
    'Dein Video ist fertig! Gefällt dir das Studio? Ein Stern auf GitHub hilft anderen, es zu finden – und über einen Kaffee freue ich mich sehr.':
      'Your video is ready! Enjoying the studio? A star on GitHub helps others find it – and I’d love a coffee.',
    'Gefällt dir das Studio? Ich entwickle es in meiner Freizeit – über einen Stern oder einen Kaffee freue ich mich sehr.':
      'Enjoying the studio? I build it in my spare time – a star or a coffee would mean a lot.',
    '⭐ Stern auf GitHub geben': '⭐ Star on GitHub',
    '☕ Kaffee spendieren': '☕ Buy me a coffee',
    'Schließen': 'Close',

    // Anmeldung
    'Bei Claude anmelden': 'Sign in to Claude',
    'Bei ChatGPT anmelden': 'Sign in to ChatGPT',
    'Damit Claude für dich arbeiten kann, melde dich einmalig mit deinem Claude-Konto an. Dein Browser öffnet sich dafür.':
      'For Claude to work for you, sign in once with your Claude account. Your browser will open for this.',
    'Damit ChatGPT (über Codex) für dich arbeiten kann, melde dich einmalig mit deinem ChatGPT-Konto an, z. B. Plus oder Pro. Dein Browser öffnet sich dafür.':
      'For ChatGPT (via Codex) to work for you, sign in once with your ChatGPT account, e.g. Plus or Pro. Your browser will open for this.',
    'Claude Code wurde nicht gefunden. Bitte den Installer erneut starten.':
      'Claude Code was not found. Please run the installer again.',
    'Codex wurde nicht gefunden. Bitte den Installer erneut starten, er richtet Codex mit ein.':
      'Codex was not found. Please run the installer again; it sets up Codex as well.',
    'Anmeldeseite öffnen': 'Open sign-in page',
    'Code aus dem Browser einfügen:': 'Paste the code from your browser:',
    'Bestätigen': 'Confirm',
    'Jetzt anmelden': 'Sign in now',
    'Ich bin angemeldet': 'I’m signed in',
    'Die Anmeldung hat nicht geklappt. Bitte erneut versuchen.': 'Sign-in didn’t work. Please try again.',
    'Warte auf die Anmeldung im Browser …': 'Waiting for sign-in in your browser …',
    'Angemeldet – los geht’s!': 'Signed in – let’s go!',
    'Anmeldung wird gestartet …': 'Starting sign-in …',
    'Noch nicht angemeldet.': 'Not signed in yet.',

    // Info
    'Entwickelt von Norman Schönherr. Fragen, Ideen oder Feedback? Melde dich gern.':
      'Made by Norman Schönherr. Questions, ideas or feedback? Get in touch.',
    'Webseite': 'Website',
    'E-Mail': 'Email',
    'Sprache': 'Language',
    'Version {0}': 'Version {0}',
    'Claude und Claude Code sind Produkte von Anthropic, ChatGPT und Codex sind Produkte von OpenAI. CMG ist ein unabhängiges Projekt und steht mit keinem der beiden Unternehmen in Verbindung.':
      'Claude and Claude Code are products of Anthropic; ChatGPT and Codex are products of OpenAI. CMG is an independent project and is not affiliated with either company.',

    // Gespräche
    'Durchsuchen, z. B. „Studio Nord“ oder „Logo“': 'Search, e.g. “Studio North” or “logo”',
    'Gespräche durchsuchen': 'Search conversations',
    '1 Auftrag': '1 request',
    '{0} Aufträge': '{0} requests',
    'aktuelles Gespräch': 'current conversation',
    'Öffnen': 'Open',
    'Keine passenden Gespräche gefunden.': 'No matching conversations found.',
    'Noch keine Gespräche.': 'No conversations yet.',
    'Gespräch ohne Auftrag': 'Conversation without a request',

    // Updates
    'Während des Updates schließt sich das Studio kurz und öffnet sich danach von selbst in einem neuen Tab. Deine Videos, Dateien, Vorlagen und Gespräche bleiben erhalten.':
      'During the update the studio closes briefly and then reopens by itself in a new tab. Your videos, files, templates and conversations are kept.',
    'Jetzt aktualisieren': 'Update now',
    'Später': 'Later',
    'Version {0} ist verfügbar. Installiert ist {1}.': 'Version {0} is available. Installed: {1}.',
    'eine ältere Version': 'an older version',
    ' neu: {0}': ' new: {0}',
    'Warte, bis der laufende Auftrag fertig ist.': 'Wait until the current request has finished.',
    'Update hat nicht geklappt': 'Update failed',
    'Beim Update ist ein Fehler aufgetreten.': 'An error occurred during the update.',
    '{0} Das Studio läuft mit der bisherigen Version weiter. Du kannst es später erneut versuchen.':
      '{0} The studio keeps running with the previous version. You can try again later.',
    'Protokoll: {0}': 'Log: {0}',
    'Update installiert – du nutzt jetzt Version {0}.': 'Update installed – you’re now using version {0}.',
    'Das Studio wird aktualisiert … Das kann einige Minuten dauern. Danach öffnet es sich in einem neuen Tab, und du kannst diesen hier schließen.':
      'The studio is updating … This can take a few minutes. It then opens in a new tab, and you can close this one.',
    'Das Studio hat sich nicht wieder gemeldet. Starte es bitte über das Symbol „Motion Studio“. Es zeigt dann, ob das Update geklappt hat.':
      'The studio hasn’t come back. Please start it using the “Motion Studio” icon. It will then show whether the update worked.',

    // Vorlagen
    'Vorlage': 'Template',
    'Vorlage „{0}“': 'Template “{0}”',
    'Fülle die Felder aus. Leere Felder bleiben als Platzhalter im Auftrag stehen.':
      'Fill in the fields. Empty fields stay in the request as placeholders.',
    'In den Auftrag übernehmen': 'Insert into request',
    'Neue Vorlage': 'New template',
    'Importieren': 'Import',
    'Exportieren': 'Export',
    'Name': 'Name',
    'Auftrag': 'Request',
    'Marken-Vorgaben (optional)': 'Brand guidelines (optional)',
    'Marken-Vorgaben': 'Brand guidelines',
    'Mit Marken-Vorgaben': 'With brand guidelines',
    'mit Marken-Vorgaben': 'with brand guidelines',
    'Format': 'Format',
    'beliebig': 'any',
    '16:9 Querformat': '16:9 landscape',
    '9:16 Hochformat (Reels, Stories)': '9:16 portrait (Reels, Stories)',
    '1:1 Quadrat': '1:1 square',
    '4:5 Hochformat (Feed)': '4:5 portrait (feed)',
    'Länge in Sekunden': 'Length in seconds',
    'Farben': 'Colours',
    '＋ Farbe': '＋ Colour',
    'Farbe': 'Colour',
    'Farbe entfernen': 'Remove colour',
    'Schriften': 'Fonts',
    'z. B. Inter für Text, Playfair Display für Titel': 'e.g. Inter for text, Playfair Display for titles',
    'Logo (aus „Eigene Dateien“)': 'Logo (from “Your files”)',
    'kein Logo': 'no logo',
    'Weitere Hinweise': 'Additional notes',
    'z. B. Tonalität, Dinge, die nie vorkommen sollen': 'e.g. tone of voice, things that must never appear',
    'Speichern': 'Save',
    '＋ Als Vorlage speichern': '＋ Save as template',
    'Vorlagen verwalten': 'Manage templates',
    'eingebaut': 'built-in',
    'eigene Vorlage': 'your template',
    '{0} Platzhalter': '{0} placeholder(s)',
    'Verwenden': 'Use',
    'Kopieren': 'Copy',
    'Bearbeiten': 'Edit',
    'Löschen': 'Delete',
    'Vorlage bearbeiten': 'Edit template',
    '{0} (Kopie)': '{0} (copy)',
    'Wird beim Verwenden abgefragt: {0}': 'Asked for when used: {0}',
    'Keine Platzhalter erkannt.': 'No placeholders found.',
    'Ungespeicherte Änderungen verwerfen?': 'Discard unsaved changes?',
    'Vorlage gespeichert.': 'Template saved.',
    'Vorlage „{0}“ wirklich löschen?': 'Really delete template “{0}”?',
    'Vorlage gelöscht.': 'Template deleted.',
    '{0} Vorlage(n) importiert{1}.': '{0} template(s) imported{1}.',
    ', {0} übersprungen': ', {0} skipped',
    'Format: {0}': 'Format: {0}',
    'Länge: {0} Sekunden': 'Length: {0} seconds',
    'Farben: {0} – verwende genau diese Farben': 'Colours: {0} – use exactly these colours',
    'Schriften: {0}': 'Fonts: {0}',
    'Logo: {0} – binde es gut sichtbar ein': 'Logo: {0} – place it clearly visible',
    'Weitere Hinweise: {0}': 'Additional notes: {0}',
    'Vorgaben aus der Vorlage „{0}“ (haben Vorrang vor Standardwerten):':
      'Guidelines from the template “{0}” (take priority over defaults):',
    '16:9 Querformat (1920 × 1080 Pixel)': '16:9 landscape (1920 × 1080 pixels)',
    '9:16 Hochformat (1080 × 1920 Pixel)': '9:16 portrait (1080 × 1920 pixels)',
    '1:1 Quadrat (1080 × 1080 Pixel)': '1:1 square (1080 × 1080 pixels)',
    '4:5 Hochformat (1080 × 1350 Pixel)': '4:5 portrait (1080 × 1350 pixels)',

    // Meldungen des Servers
    'Zugriff verweigert': 'Access denied',
    'Nicht gefunden': 'Not found',
    'Datei nicht gefunden': 'File not found',
    'Unbekannter Dienst.': 'Unknown service.',
    'Es läuft gerade noch ein Auftrag. Bitte warten oder abbrechen.': 'A request is still running. Please wait or cancel it.',
    'Es gibt gerade kein Update.': 'There is no update right now.',
    '{0} wurde nicht gefunden. Bitte den Installer erneut starten.': '{0} was not found. Please run the installer again.',
    'Dieses Gespräch gibt es nicht mehr.': 'This conversation no longer exists.',
    'Bitte einen Auftrag eingeben.': 'Please enter a request.',
    'Das Studio wird gerade aktualisiert.': 'The studio is being updated.',
    'Die Datei ist leer oder zu groß.': 'The file is empty or too large.',
    'Die Datei ist keine gültige Vorlagen-Datei.': 'The file is not a valid template file.',
    'Das Update läuft bereits.': 'The update is already running.',
    'Dieser Dateityp wird nicht unterstützt.': 'This file type is not supported.',
    'Die Datei ist zu groß (max. 500 MB).': 'The file is too large (max. 500 MB).',
    'Der Upload wurde unterbrochen. Bitte erneut versuchen.': 'The upload was interrupted. Please try again.',
    'Ab hier arbeitet {0}. {1} kennt den bisherigen Verlauf dieses Gesprächs nicht.':
      'From here on, {0} is working. {1} doesn’t know the earlier part of this conversation.',
    'Neue Videos dieses Gesprächs landen ab jetzt im Ordner exports/{0}.':
      'New videos from this conversation are now saved in the folder exports/{0}.',
    '{0} konnte nicht gestartet werden: {1}': '{0} could not be started: {1}',
    'Auftrag abgebrochen.': 'Request cancelled.',
    '{0} hat den Auftrag mit einem Fehler beendet.': '{0} finished the request with an error.',
    '{0} muss ein Text sein.': '{0} must be text.',
    '{0} darf keine Zeilenumbrüche oder Steuerzeichen enthalten.': '{0} must not contain line breaks or control characters.',
    'Bitte {0} angeben.': 'Please enter {0}.',
    '{0} ist zu lang (höchstens {1} Zeichen).': '{0} is too long (at most {1} characters).',
    'einen Namen': 'a name',
    'einen Auftragstext': 'a request text',
    'Höchstens {0} Farben sind möglich.': 'At most {0} colours are possible.',
    'Ungültige Farbe: {0}': 'Invalid colour: {0}',
    'Unbekanntes Format: {0}': 'Unknown format: {0}',
    'Die Länge muss eine Zahl in Sekunden sein.': 'The length must be a number of seconds.',
    'Die Länge darf höchstens {0} Sekunden betragen.': 'The length may be at most {0} seconds.',
    'Das Logo muss eine Bilddatei im Ordner assets sein.': 'The logo must be an image file in the assets folder.',
    'Ungültige Vorlage.': 'Invalid template.',
    'Die Vorlagen konnten gerade nicht gelesen werden. Bitte gleich noch einmal versuchen.':
      'The templates couldn’t be read just now. Please try again in a moment.',
    'Die Vorlagen-Datei ist beschädigt und konnte nicht gesichert werden.':
      'The template file is damaged and could not be backed up.',
    'Eingebaute Vorlagen können nicht geändert werden. Lege eine Kopie an.':
      'Built-in templates can’t be changed. Make a copy instead.',
    'Es sind höchstens {0} eigene Vorlagen möglich.': 'At most {0} of your own templates are possible.',
    'Diese Vorlage gibt es nicht (mehr).': 'This template doesn’t exist (any more).',
    'Die Datei enthält keine Vorlagen.': 'The file contains no templates.',
    'Die Datei enthält keine gültigen Vorlagen.': 'The file contains no valid templates.',
    'Das Update wurde unterbrochen.': 'The update was interrupted.',
    'Der Installer hat mit einem Fehler aufgehört.': 'The installer stopped with an error.',
    'Das Update hat zu lange gedauert und wurde abgebrochen.': 'The update took too long and was cancelled.',
    'Das Update konnte nicht ausgeführt werden ({0}).': 'The update could not be run ({0}).',

    // Arbeitsschritte der KI
    'Erstellt {0}': 'Creates {0}',
    'Bearbeitet {0}': 'Edits {0}',
    'Löscht {0}': 'Deletes {0}',
    'Liest {0}': 'Reads {0}',
    'Prüft Bild {0}': 'Checks image {0}',
    'Führt aus: {0}': 'Runs: {0}',
    'Sucht im Web: {0}': 'Searches the web: {0}',
    'Arbeitsschritt: {0}': 'Step: {0}',
    '{0} (+{1} weitere)': '{0} (+{1} more)',
    'Sucht im Projekt': 'Searches the project',
    'Plant die Arbeitsschritte': 'Plans the steps',
  };

  // Absätze mit Links oder Code: als Ganzes übersetzt (feste, vertrauenswürdige Texte).
  const EN_HTML = {
    'presets-file': 'Your own templates are saved as <code>presets.json</code> in the studio folder.',
    'placeholder-tip': 'Tip: Write placeholders in square brackets, e.g. <code>[Product]</code>. When you use the template, the studio asks for them in a form.',
    'disclaimer': 'Use at your own risk: Claude works autonomously on your computer, and AI results can be wrong. Details in the <a href="https://github.com/normannormalmann/Claude-Motionreel-Generator-CMG/blob/main/README.en.md#disclaimer" target="_blank" rel="noopener noreferrer">disclaimer</a>.',
  };

  const BUILTIN_EN = {
    'builtin-showreel': {
      name: 'Showreel',
      text: 'Create a 15-second motion design showreel for a fictional design studio.\n'
        + 'Format of the final version: 1920 × 1080 pixels, 30 fps.\n'
        + 'Style: editorial, precise, large typography, cream background, black text and orange accents.\n'
        + 'Plan five scenes with different motion ideas. Start without audio for now.\n\n'
        + 'Read CLAUDE.md and check the available tools. Then create:\n'
        + '1. The HTML animation with window.seek(timeInSeconds).\n2. A Python render script using Playwright.\n'
        + '3. A contact sheet of the key moments.\n'
        + '4. After at most two rounds of visual corrections, a preview as MP4 at 960 × 540 pixels.\n\n'
        + 'Actually check the generated frames. Pay attention to readable text and clean scene transitions.\n'
        + 'We’ll create the final version in full resolution once I like the preview.',
    },
    'builtin-produktfilm': {
      name: 'Product film',
      text: 'Create a 20-second product film for [Product].\n\n'
        + 'Target audience: [Audience]\nKey message: [Benefit]\nEnding: [Call to action]\n\n'
        + '0–4 seconds: show the problem.\n4–9 seconds: introduce the product.\n'
        + '9–15 seconds: demonstrate the most important feature.\n15–20 seconds: benefit and ending.\n\n'
        + 'Show me the scene plan first. Start rendering once I approve the plan.',
    },
    'builtin-reel': {
      name: 'Instagram Reel',
      text: 'Create an Instagram Reel about [Topic].\n'
        + 'The first second must grab attention immediately.\n'
        + 'Keep all text large, short and inside the safe zone (leave 250 pixels free at the top and bottom).\n'
        + 'End with this call to action: [Call to action].',
    },
    'builtin-szene': {
      name: 'Change a scene',
      text: 'Only revise the second scene:\nThe text should stay on screen 0.5 seconds longer.\n'
        + 'Reduce the overshoot of the letters.\nThen create a new preview.',
    },
    'builtin-musik': {
      name: 'Add music',
      text: 'Add assets/music.mp3 as music.\nAlign important transitions with the rhythm.\n'
        + 'Fade out the music at the end.\nCreate a new preview with sound (video H.264, audio AAC).',
    },
  };

  function detect() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (LANGUAGES.includes(stored)) return stored;
    } catch (error) { /* ohne Speicher: Browsersprache */ }
    return /^de\b/i.test(navigator.language || '') ? 'de' : 'en';
  }

  const lang = detect();
  // Nur eigene Einträge zählen – sonst fände z. B. ein Dateiname "constructor" etwas aus Object.prototype.
  const lookup = (table, key) => (Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined);

  const fill = (text, args) => text.replace(/\{(\d+)\}/g, (match, index) => (
    args[index] === undefined ? match : String(args[index])));

  /** Übersetzt einen deutschen Ausgangstext; {0}, {1} … werden durch args ersetzt. */
  function t(text, ...args) {
    return fill((lang === 'en' && lookup(EN, text)) || text, args);
  }

  const escapeRegex = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const TEMPLATES = Object.keys(EN).filter((key) => /\{\d+\}/.test(key)).map((key) => {
    const order = [...key.matchAll(/\{(\d+)\}/g)].map((m) => Number(m[1]));
    const pattern = escapeRegex(key).replace(/\\\{\d+\\\}/g, '([\\s\\S]+?)');
    return { key, order, regex: new RegExp(`^${pattern}$`) };
  });

  /** Übersetzt einen fertigen Text vom Server, auch mit eingesetzten Werten (z. B. Dateinamen). */
  function server(text, depth = 0) {
    if (lang !== 'en' || typeof text !== 'string' || !text) return text;
    const exact = lookup(EN, text);
    if (exact) return exact;
    if (depth >= MAX_NESTING) return text;
    for (const template of TEMPLATES) {
      const match = template.regex.exec(text);
      if (!match) continue;
      const args = [];
      template.order.forEach((index, position) => { args[index] = server(match[position + 1], depth + 1); });
      return fill(EN[template.key], args);
    }
    return text;
  }

  const ATTRIBUTES = ['placeholder', 'title', 'aria-label'];

  /** Übersetzt die festen Texte der Seite einmal beim Start. */
  function applyToPage(root = document.body) {
    document.documentElement.lang = lang;
    if (lang !== 'en') return;
    root.querySelectorAll('[data-i18n-html]').forEach((element) => {
      const html = lookup(EN_HTML, element.dataset.i18nHtml);
      if (html) element.innerHTML = html;
    });
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const trimmed = node.nodeValue.trim();
      const english = trimmed && lookup(EN, trimmed);
      if (english) node.nodeValue = node.nodeValue.replace(trimmed, english);
    }
    root.querySelectorAll('*').forEach((element) => {
      ATTRIBUTES.forEach((name) => {
        const value = element.getAttribute(name);
        const english = value && lookup(EN, value);
        if (english) element.setAttribute(name, english);
      });
    });
  }

  function localizePreset(preset) {
    const english = lang === 'en' && preset.builtin && lookup(BUILTIN_EN, preset.id);
    return english ? Object.assign({}, preset, english) : preset;
  }

  function setLanguage(next) {
    if (!LANGUAGES.includes(next) || next === lang) return;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (error) {
      return false; // Ohne Browser-Speicher würde die Seite nach dem Neuladen wieder die alte Sprache zeigen.
    }
    window.location.reload();
    return true;
  }

  window.CMGI18n = {
    lang,
    locale: lang === 'en' ? 'en-GB' : 'de-DE',
    t,
    server,
    applyToPage,
    localizePreset,
    setLanguage,
  };
})();
