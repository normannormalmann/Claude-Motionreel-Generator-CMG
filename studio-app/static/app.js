(() => {
  'use strict';

  const IDLE_POLL_MS = 15000;
  const BUSY_FILES_MS = 6000;
  const LOGIN_POLL_MS = 1500;
  const MAX_THUMBS = 9;

  const TEMPLATES = [
    ['Showreel', 'Erstelle ein 15 Sekunden langes Motion-Design-Showreel für ein fiktives Designstudio.\n' +
      'Format: 1920 × 1080 Pixel, 30 fps.\n' +
      'Stil: redaktionell, präzise, große Typografie, cremefarbener Hintergrund, schwarze Schrift und orange Akzente.\n' +
      'Plane fünf Szenen mit unterschiedlichen Bewegungsideen. Beginne zunächst ohne Audio.\n\n' +
      'Lies CLAUDE.md und prüfe die vorhandenen Werkzeuge. Erstelle dann:\n' +
      '1. Die HTML-Animation mit window.seek(timeInSeconds).\n2. Ein Python-Renderskript mit Playwright.\n' +
      '3. Eine Vorschau mit 960 × 540 Pixeln.\n4. Eine Kontaktübersicht der Vorschau.\n' +
      '5. Nach höchstens zwei visuellen Korrekturrunden den vollständigen MP4-Export.\n\n' +
      'Prüfe die erzeugten Bilder tatsächlich. Achte auf lesbare Texte und saubere Szenenübergänge.\n' +
      'Speichere das fertige Video als exports/showreel.mp4.'],
    ['Produktfilm', 'Erstelle einen 20-Sekunden-Produktfilm für [Produkt].\n\n' +
      'Zielgruppe: [Zielgruppe]\nHauptaussage: [Nutzen]\nFarben: [Farben]\nAbschluss: [Handlungsaufforderung]\n\n' +
      '0–4 Sekunden: Problem zeigen.\n4–9 Sekunden: Produkt vorstellen.\n' +
      '9–15 Sekunden: wichtigste Funktion demonstrieren.\n15–20 Sekunden: Nutzen und Abschluss.\n\n' +
      'Zeige mir zuerst den Szenenplan. Beginne mit dem Rendering nach meiner Freigabe des Plans.'],
    ['Szene ändern', 'Überarbeite nur die zweite Szene:\nDer Text soll 0,5 Sekunden länger stehen bleiben.\n' +
      'Reduziere das Überschwingen der Buchstaben.\nErstelle anschließend eine neue Vorschau.'],
    ['Musik ergänzen', 'Ergänze assets/music.mp3 als Musik.\nPasse wichtige Übergänge an den Rhythmus an.\n' +
      'Blende die Musik am Ende aus.\nExportiere Video mit H.264 und Audio mit AAC.'],
  ];

  const $ = (id) => document.getElementById(id);
  const state = { next: 0, busy: false, startedAt: 0, wake: null, videoSignature: '', knownVideos: null, loginTimer: null };

  // ------------------------------------------------------------ Hilfen

  const sleep = (ms) => new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    state.wake = () => { clearTimeout(timer); resolve(); };
  });

  // Die Anmeldung beim Studio läuft über ein HttpOnly-Cookie; der Kopf-Eintrag schützt vor fremden Seiten.
  async function api(path, options = {}) {
    const headers = Object.assign({ 'X-Studio-Request': '1' }, options.headers || {});
    const response = await fetch(path, Object.assign({}, options, { headers, credentials: 'same-origin' }));
    const data = await response.json().catch(() => ({}));
    if (response.status === 403) throw new Error('Bitte öffne das Studio erneut über das Symbol „Motion Studio“.');
    if (!response.ok) throw new Error(data.error || 'Unbekannter Fehler');
    return data;
  }

  const postJson = (path, body) => api(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}),
  });

  function toast(text) {
    const element = $('toast');
    element.textContent = text;
    element.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { element.hidden = true; }, 4500);
  }

  const escapeHtml = (text) => text.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const inline = (text) => text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // Kleiner, sicherer Markdown-Renderer: Text wird zuerst vollständig maskiert.
  function renderMarkdown(text) {
    const LIST_ITEM = /^\s*([-*]|\d+\.)\s+/;
    let html = '';
    escapeHtml(text).split(/```[\w-]*\n?([\s\S]*?)```/g).forEach((part, index) => {
      if (index % 2 === 1) { html += `<pre><code>${part}</code></pre>`; return; }
      part.split(/\n{2,}/).forEach((block) => {
        const lines = block.split('\n').filter((line) => line.trim());
        if (!lines.length) return;
        if (lines.every((line) => LIST_ITEM.test(line))) {
          html += '<ul>' + lines.map((l) => `<li>${inline(l.replace(LIST_ITEM, ''))}</li>`).join('') + '</ul>';
        } else if (lines.length === 1 && /^#{1,4}\s/.test(lines[0])) {
          html += `<h3>${inline(lines[0].replace(/^#+\s*/, ''))}</h3>`;
        } else {
          html += `<p>${lines.map(inline).join('<br>')}</p>`;
        }
      });
    });
    return html;
  }

  const formatSize = (bytes) => (bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);
  const formatTime = (seconds) => new Date(seconds * 1000).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
  const mediaUrl = (file) => `${file.url}?v=${file.modified}`;

  // ------------------------------------------------------------ Gespräch

  function renderItem(item) {
    const messages = $('messages');
    $('welcome').hidden = true;
    let element;
    if (item.kind === 'user') {
      element = document.createElement('div');
      element.className = 'msg msg-user';
      element.textContent = item.text;
    } else if (item.kind === 'assistant') {
      element = document.createElement('div');
      element.className = 'msg msg-assistant';
      element.innerHTML = renderMarkdown(item.text);
    } else if (item.kind === 'tool') {
      element = document.createElement('div');
      element.className = 'step';
      if (item.detail) {
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        const pre = document.createElement('pre');
        summary.textContent = item.text;
        pre.textContent = item.detail;
        details.append(summary, pre);
        element.append(details);
      } else {
        element.textContent = item.text;
      }
    } else if (item.kind === 'done') {
      element = document.createElement('div');
      element.className = 'done-note';
      element.textContent = '✓ Fertig';
      refreshFiles();
    } else if (item.kind === 'error') {
      element = document.createElement('div');
      element.className = 'msg msg-error';
      element.textContent = item.text;
      if (item.needs_login) showLogin();
    }
    if (!element) return;
    const nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 120;
    messages.append(element);
    if (nearBottom || item.kind === 'user') messages.scrollTop = messages.scrollHeight;
  }

  function setBusy(busy) {
    if (busy && !state.busy) state.startedAt = Date.now();
    state.busy = busy;
    $('working').hidden = !busy;
    $('send').disabled = busy;
  }

  function updateWorkingText() {
    if (!state.busy) return;
    const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
    const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    $('working-text').textContent = `Claude arbeitet … ${clock}`;
  }

  async function pollLoop() {
    for (;;) {
      try {
        const data = await api(`/api/state?from=${state.next}${state.busy ? '&wait=1' : ''}`);
        data.items.forEach(renderItem);
        state.next = data.next;
        setBusy(data.busy);
        if (!data.busy) await sleep(IDLE_POLL_MS);
      } catch (error) {
        toast(error instanceof TypeError ? 'Verbindung zum Studio unterbrochen. Bitte „Motion Studio“ neu starten.' : error.message);
        await sleep(5000);
      }
    }
  }

  async function sendPrompt(event) {
    event.preventDefault();
    const message = $('prompt').value.trim();
    if (!message || state.busy) return;
    try {
      await postJson('/api/chat', { message, model: $('model').value });
      $('prompt').value = '';
      setBusy(true);
      if (state.wake) state.wake();
    } catch (error) {
      toast(error.message);
    }
  }

  // ------------------------------------------------------------ Dateien

  function renderVideos(files) {
    const videos = files.filter((f) => f.type === 'video');
    const images = files.filter((f) => f.type === 'image').slice(0, MAX_THUMBS);
    const signature = files.map((f) => f.name + f.modified).join('|');
    if (signature === state.videoSignature) return;
    state.videoSignature = signature;

    const previous = state.knownVideos;
    state.knownVideos = new Set(videos.map((v) => v.name + v.modified));
    const container = $('videos');
    container.replaceChildren();
    if (!videos.length && !images.length) {
      container.innerHTML = '<p class="empty">Noch keine Videos. Starte links mit einem Auftrag.</p>';
      return;
    }
    videos.forEach((file) => {
      const isNew = previous !== null && !previous.has(file.name + file.modified);
      const card = document.createElement('div');
      card.className = 'media-card' + (isNew ? ' is-new' : '');
      card.innerHTML = `<video controls preload="metadata" src="${escapeHtml(mediaUrl(file))}"></video>
        <div class="media-meta"><strong>${escapeHtml(file.name)}</strong><span>${formatSize(file.size)} · ${formatTime(file.modified)}</span></div>`;
      container.append(card);
      if (isNew) toast(`Neues Video: ${file.name}`);
    });
    if (images.length) {
      const head = document.createElement('p');
      head.className = 'subhead';
      head.textContent = 'Vorschaubilder';
      const grid = document.createElement('div');
      grid.className = 'thumbs';
      images.forEach((file) => {
        const link = document.createElement('a');
        link.href = mediaUrl(file);
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.title = file.name;
        link.innerHTML = `<img loading="lazy" alt="${escapeHtml(file.name)}" src="${escapeHtml(mediaUrl(file))}">`;
        grid.append(link);
      });
      container.append(head, grid);
    }
  }

  function renderAssets(files) {
    const list = $('assets');
    list.replaceChildren(...files.map((file) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      const size = document.createElement('span');
      name.textContent = file.name;
      size.textContent = formatSize(file.size);
      item.append(name, size);
      return item;
    }));
  }

  async function refreshFiles() {
    try {
      const data = await api('/api/files');
      renderVideos(data.exports || []);
      renderAssets(data.assets || []);
    } catch (error) { /* Nächster Versuch beim nächsten Intervall */ }
  }

  async function uploadFiles(fileList) {
    for (const file of fileList) {
      try {
        await api('/api/upload', {
          method: 'POST',
          headers: { 'X-Filename': encodeURIComponent(file.name), 'Content-Type': 'application/octet-stream' },
          body: file,
        });
        toast(`Hochgeladen: ${file.name} – du kannst Claude bitten, assets/${file.name} zu verwenden.`);
      } catch (error) {
        toast(`${file.name}: ${error.message}`);
      }
    }
    refreshFiles();
  }

  // ------------------------------------------------------------ Anmeldung

  function showLogin() { $('login').hidden = false; }

  async function checkLogin(force) {
    try {
      const status = await api('/api/auth' + (force ? '?force=1' : ''));
      if (!status.installed) { toast('Claude Code wurde nicht gefunden. Bitte den Installer erneut starten.'); return false; }
      if (status.logged_in) { $('login').hidden = true; return true; }
      showLogin();
    } catch (error) { toast(error.message); }
    return false;
  }

  async function pollLogin() {
    const info = await api('/api/login').catch(() => null);
    if (!info) return;
    $('login-status').textContent = info.state === 'failed' ? 'Die Anmeldung hat nicht geklappt. Bitte erneut versuchen.' : 'Warte auf die Anmeldung im Browser …';
    if (info.url) { $('login-link').href = info.url; $('login-link').hidden = false; }
    $('login-code').hidden = !/code/i.test(info.output || '');
    if (info.state === 'running') return;
    clearInterval(state.loginTimer);
    if (info.state === 'done' && await checkLogin(true)) toast('Angemeldet – los geht’s!');
  }

  async function startLogin() {
    try {
      await postJson('/api/login');
      $('login-status').textContent = 'Anmeldung wird gestartet …';
      clearInterval(state.loginTimer);
      state.loginTimer = setInterval(pollLogin, LOGIN_POLL_MS);
    } catch (error) { toast(error.message); }
  }

  // ------------------------------------------------------------ Start

  function setupControls() {
    const templates = $('templates');
    TEMPLATES.forEach(([label, text]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.addEventListener('click', () => { $('prompt').value = text; $('prompt').focus(); });
      templates.append(button);
    });

    try { $('model').value = localStorage.getItem('studio-model') || 'opus'; } catch (e) { /* ohne Speicher */ }
    $('model').addEventListener('change', () => { try { localStorage.setItem('studio-model', $('model').value); } catch (e) { /* ohne Speicher */ } });

    $('composer').addEventListener('submit', sendPrompt);
    $('prompt').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) sendPrompt(event);
    });
    $('stop').addEventListener('click', () => postJson('/api/stop').catch((e) => toast(e.message)));
    $('new-project').addEventListener('click', async () => {
      if (state.busy) { toast('Claude arbeitet gerade noch.'); return; }
      if (!window.confirm('Neues Gespräch beginnen? Deine Videos und Dateien bleiben erhalten.')) return;
      try {
        await postJson('/api/reset');
        $('messages').replaceChildren($('welcome'));
        $('welcome').hidden = false;
        state.next = 0;
      } catch (error) { toast(error.message); }
    });
    $('open-folder').addEventListener('click', () => postJson('/api/open', { target: 'studio' }).catch((e) => toast(e.message)));
    document.querySelectorAll('[data-open]').forEach((button) => {
      button.addEventListener('click', () => postJson('/api/open', { target: button.dataset.open }).catch((e) => toast(e.message)));
    });

    const dropzone = $('dropzone');
    $('file-input').addEventListener('change', (event) => { uploadFiles(event.target.files); event.target.value = ''; });
    ['dragenter', 'dragover'].forEach((type) => dropzone.addEventListener(type, (e) => { e.preventDefault(); dropzone.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach((type) => dropzone.addEventListener(type, () => dropzone.classList.remove('is-over')));
    dropzone.addEventListener('drop', (event) => { event.preventDefault(); uploadFiles(event.dataTransfer.files); });
    window.addEventListener('dragover', (event) => event.preventDefault());
    window.addEventListener('drop', (event) => event.preventDefault());

    const info = $('info');
    $('info-open').addEventListener('click', () => { info.hidden = false; $('info-close').focus(); });
    $('info-close').addEventListener('click', () => { info.hidden = true; });
    info.addEventListener('click', (event) => { if (event.target === info) info.hidden = true; });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') info.hidden = true; });

    $('login-start').addEventListener('click', startLogin);
    $('login-check').addEventListener('click', async () => {
      if (!await checkLogin(true)) $('login-status').textContent = 'Noch nicht angemeldet.';
    });
    $('login-code-send').addEventListener('click', () => {
      postJson('/api/login/code', { code: $('login-code-input').value }).catch((e) => toast(e.message));
      $('login-code-input').value = '';
    });
  }

  setupControls();
  checkLogin(false);
  refreshFiles();
  setInterval(() => { if (state.busy) refreshFiles(); }, BUSY_FILES_MS);
  setInterval(updateWorkingText, 1000);
  pollLoop();
})();
