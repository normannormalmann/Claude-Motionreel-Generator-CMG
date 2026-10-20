(() => {
  'use strict';

  const IDLE_POLL_MS = 15000;
  const BUSY_FILES_MS = 6000;
  const LOGIN_POLL_MS = 1500;
  const MAX_THUMBS = 9;
  const UPDATE_CHECK_MS = 6 * 60 * 60 * 1000;
  const UPDATE_GIVE_UP_MS = 30 * 60 * 1000;
  const DEFAULT_MODEL = 'opus';
  const ENGINES = {
    claude: {
      label: 'Claude',
      loginTitle: 'Bei Claude anmelden',
      loginIntro: 'Damit Claude für dich arbeiten kann, melde dich einmalig mit deinem Claude-Konto an. Dein Browser öffnet sich dafür.',
      missing: 'Claude Code wurde nicht gefunden. Bitte den Installer erneut starten.',
      usesCode: true,
    },
    codex: {
      label: 'ChatGPT',
      loginTitle: 'Bei ChatGPT anmelden',
      loginIntro: 'Damit ChatGPT (über Codex) für dich arbeiten kann, melde dich einmalig mit deinem ChatGPT-Konto an, z. B. Plus oder Pro. Dein Browser öffnet sich dafür.',
      missing: 'Codex wurde nicht gefunden. Bitte den Installer erneut starten, er richtet Codex mit ein.',
      usesCode: false,
    },
  };

  const $ = (id) => document.getElementById(id);
  const state = {
    next: 0, busy: false, startedAt: 0, wake: null, videoSignature: '', knownVideos: null,
    loginTimer: null, loginEngine: 'claude', runEngine: null, assets: [], update: null, updating: false,
  };

  const engineOf = (model) => (model.startsWith('codex') ? 'codex' : 'claude');
  const currentEngine = () => engineOf($('model').value);

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
    } else if (item.kind === 'note') {
      element = document.createElement('div');
      element.className = 'step step-note';
      element.textContent = item.text;
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
      if (item.needs_login) showLogin(item.engine || currentEngine());
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
    if (!$('update').hidden && !state.updating && !$('update-start').hidden) {
      $('update-start').disabled = busy;
      $('update-status').textContent = busy ? 'Warte, bis der laufende Auftrag fertig ist.' : '';
    }
  }

  function updateWorkingText() {
    if (!state.busy) return;
    const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
    const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    const label = ENGINES[state.runEngine || currentEngine()].label;
    $('working-text').textContent = `${label} arbeitet … ${clock}`;
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
        // Während eines Updates ist das Studio absichtlich kurz weg.
        if (!state.updating) {
          toast(error instanceof TypeError ? 'Verbindung zum Studio unterbrochen. Bitte „Motion Studio“ neu starten.' : error.message);
        }
        await sleep(5000);
      }
    }
  }

  async function sendMessage(message) {
    if (!message || state.busy) return false;
    try {
      await postJson('/api/chat', { message, model: $('model').value });
      state.runEngine = currentEngine();
      setBusy(true);
      if (state.wake) state.wake();
      return true;
    } catch (error) {
      toast(error.message);
      return false;
    }
  }

  async function sendPrompt(event) {
    event.preventDefault();
    if (await sendMessage($('prompt').value.trim())) $('prompt').value = '';
  }

  // Vorschauen heißen *_vorschau.mp4; die volle Auflösung gibt es nur auf ausdrückliche Anfrage.
  const isPreview = (file) => /vorschau/i.test(file.name);

  function requestFinal(file) {
    if (state.busy) { toast('Es läuft gerade noch ein Auftrag.'); return; }
    sendMessage(`Bitte erstelle jetzt die finale Version von ${file.name} in voller Auflösung.`);
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
      container.innerHTML = '<p class="empty">Noch keine Videos in diesem Gespräch. Starte links mit einem Auftrag.</p>';
      return;
    }
    videos.forEach((file) => {
      const isNew = previous !== null && !previous.has(file.name + file.modified);
      const card = document.createElement('div');
      card.className = 'media-card' + (isNew ? ' is-new' : '');
      card.innerHTML = `<video controls preload="metadata" src="${escapeHtml(mediaUrl(file))}"></video>
        <div class="media-meta"><strong>${escapeHtml(file.name)}</strong><span>${formatSize(file.size)} · ${formatTime(file.modified)}</span></div>`;
      const actions = document.createElement('div');
      actions.className = 'media-actions';
      const badge = document.createElement('span');
      badge.className = 'media-badge' + (isPreview(file) ? '' : ' is-final');
      badge.textContent = isPreview(file) ? 'Vorschau' : 'Final';
      actions.append(badge);
      if (isPreview(file)) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'ghost small';
        button.textContent = 'Finale Version erstellen';
        button.title = 'Rendert dieses Video in voller Auflösung';
        button.addEventListener('click', () => requestFinal(file));
        actions.append(button);
      }
      card.append(actions);
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
    state.assets = files;
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
        toast(`Hochgeladen: ${file.name} – du kannst die KI bitten, assets/${file.name} zu verwenden.`);
      } catch (error) {
        toast(`${file.name}: ${error.message}`);
      }
    }
    refreshFiles();
  }

  // ------------------------------------------------------------ Anmeldung

  function showLogin(engine) {
    const info = ENGINES[engine] || ENGINES.claude;
    if (state.loginEngine !== engine) {
      clearInterval(state.loginTimer);
      $('login-status').textContent = '';
      $('login-link').hidden = true;
      $('login-code').hidden = true;
    }
    state.loginEngine = engine in ENGINES ? engine : 'claude';
    $('login-title').textContent = info.loginTitle;
    $('login-intro').textContent = info.loginIntro;
    $('login').hidden = false;
  }

  // Liefert den Anmeldestatus: 'ok', 'login' (Anmeldung nötig), 'missing' oder 'unknown'.
  async function checkLogin(force, engine = currentEngine()) {
    try {
      const status = await api(`/api/auth?engine=${engine}` + (force ? '&force=1' : ''));
      if (!status.installed) { toast(ENGINES[engine].missing); return 'missing'; }
      if (status.logged_in) { $('login').hidden = true; return 'ok'; }
      showLogin(engine);
      return 'login';
    } catch (error) { toast(error.message); }
    return 'unknown';
  }

  async function pollLogin() {
    const info = await api('/api/login').catch(() => null);
    if (!info || info.engine !== state.loginEngine) return;
    $('login-status').textContent = info.state === 'failed' ? 'Die Anmeldung hat nicht geklappt. Bitte erneut versuchen.' : 'Warte auf die Anmeldung im Browser …';
    if (info.url) { $('login-link').href = info.url; $('login-link').hidden = false; }
    $('login-code').hidden = !ENGINES[state.loginEngine].usesCode || !/code/i.test(info.output || '');
    if (info.state === 'running') return;
    clearInterval(state.loginTimer);
    if (info.state === 'done' && await checkLogin(true, state.loginEngine) === 'ok') toast('Angemeldet – los geht’s!');
  }

  async function startLogin() {
    try {
      await postJson('/api/login', { engine: state.loginEngine });
      $('login-status').textContent = 'Anmeldung wird gestartet …';
      clearInterval(state.loginTimer);
      state.loginTimer = setInterval(pollLogin, LOGIN_POLL_MS);
    } catch (error) { toast(error.message); }
  }

  // ------------------------------------------------------------ Updates

  function openUpdateDialog() {
    const info = state.update;
    if (!info) return;
    $('update-title').textContent = 'Update verfügbar';
    $('update-intro').textContent = `Version ${info.latest} ist verfügbar. Installiert ist ${info.current ? `Version ${info.current}` : 'eine ältere Version'}.`;
    $('update-changes').replaceChildren(...info.changes.map((change) => {
      const item = document.createElement('li');
      const versions = document.createElement('span');
      versions.textContent = change.from ? ` ${change.from} → ${change.to}` : ` neu: ${change.to}`;
      item.append(change.name, versions);
      return item;
    }));
    $('update-note').hidden = false;
    $('update-start').hidden = false;
    $('update-start').disabled = state.busy;
    $('update-close').textContent = 'Später';
    $('update-status').textContent = state.busy ? 'Warte, bis der laufende Auftrag fertig ist.' : '';
    $('update').hidden = false;
  }

  function showUpdateFailure(result) {
    $('update-title').textContent = 'Update hat nicht geklappt';
    $('update-intro').textContent = `${result.message || 'Beim Update ist ein Fehler aufgetreten.'} Das Studio läuft mit der bisherigen Version weiter. Du kannst es später erneut versuchen.`;
    $('update-changes').replaceChildren();
    $('update-note').hidden = true;
    $('update-start').hidden = true;
    $('update-close').textContent = 'Schließen';
    $('update-status').textContent = result.log ? `Protokoll: ${result.log}` : '';
    $('update').hidden = false;
  }

  async function checkUpdate(force) {
    try {
      const info = await api('/api/update' + (force ? '?force=1' : ''));
      state.update = info;
      $('info-version').textContent = info.current ? `Version ${info.current}` : '';
      $('update-open').hidden = !info.available;
      if (info.result) {
        if (info.result.ok) toast(`Update installiert – du nutzt jetzt Version ${info.result.version}.`);
        else showUpdateFailure(info.result);
        postJson('/api/update/ack').catch(() => { /* wird beim nächsten Start erneut gemeldet */ });
      }
    } catch (error) { /* Die Update-Prüfung ist optional. */ }
  }

  async function startUpdate() {
    if (state.busy) { toast('Es läuft gerade noch ein Auftrag.'); return; }
    $('update-start').disabled = true;
    $('update-close').disabled = true;
    try {
      await postJson('/api/update/start');
      state.updating = true;
      $('update-status').textContent = 'Das Studio wird aktualisiert … Das kann einige Minuten dauern. Danach öffnet es sich in einem neuen Tab, und du kannst diesen hier schließen.';
      setTimeout(() => {
        $('update-status').textContent = 'Das Studio hat sich nicht wieder gemeldet. Starte es bitte über das Symbol „Motion Studio“. Es zeigt dann, ob das Update geklappt hat.';
        $('update-close').disabled = false;
        $('update-close').textContent = 'Schließen';
      }, UPDATE_GIVE_UP_MS);
    } catch (error) {
      $('update-status').textContent = error.message;
      $('update-start').disabled = false;
      $('update-close').disabled = false;
    }
  }

  // ------------------------------------------------------------ Start

  function setupControls() {
    try { $('model').value = localStorage.getItem('studio-model') || DEFAULT_MODEL; } catch (e) { /* ohne Speicher */ }
    if (!$('model').value) $('model').value = DEFAULT_MODEL;
    $('model').addEventListener('change', async () => {
      if (await checkLogin(false) === 'missing') $('model').value = DEFAULT_MODEL;
      try { localStorage.setItem('studio-model', $('model').value); } catch (e) { /* ohne Speicher */ }
    });

    $('composer').addEventListener('submit', sendPrompt);
    $('prompt').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) sendPrompt(event);
    });
    $('stop').addEventListener('click', () => postJson('/api/stop').catch((e) => toast(e.message)));
    $('new-project').addEventListener('click', async () => {
      if (state.busy) { toast('Es läuft gerade noch ein Auftrag.'); return; }
      if (!window.confirm('Neues Gespräch beginnen? Deine Videos und Dateien bleiben erhalten.')) return;
      try {
        await postJson('/api/reset');
        $('messages').replaceChildren($('welcome'));
        $('welcome').hidden = false;
        state.next = 0;
        state.knownVideos = null;
        refreshFiles();
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
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      info.hidden = true;
      if (!state.updating) $('update').hidden = true;
    });

    $('update-open').addEventListener('click', openUpdateDialog);
    $('update-start').addEventListener('click', startUpdate);
    $('update-close').addEventListener('click', () => { $('update').hidden = true; });

    $('login-start').addEventListener('click', startLogin);
    $('login-check').addEventListener('click', async () => {
      if (await checkLogin(true, state.loginEngine) !== 'ok') $('login-status').textContent = 'Noch nicht angemeldet.';
    });
    $('login-code-send').addEventListener('click', () => {
      postJson('/api/login/code', { code: $('login-code-input').value }).catch((e) => toast(e.message));
      $('login-code-input').value = '';
    });
  }

  setupControls();
  window.CMGPresets.init({ api, postJson, toast, prompt: $('prompt'), getAssets: () => state.assets });
  checkLogin(false).then((result) => {
    if (result === 'missing' && currentEngine() !== 'claude') { $('model').value = DEFAULT_MODEL; checkLogin(false); }
  });
  refreshFiles();
  checkUpdate(false);
  setInterval(() => checkUpdate(false), UPDATE_CHECK_MS);
  setInterval(() => { if (state.busy) refreshFiles(); }, BUSY_FILES_MS);
  setInterval(updateWorkingText, 1000);
  pollLoop();
})();
