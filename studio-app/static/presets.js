/* Vorlagen: auswählen, ausfüllen, anlegen, bearbeiten, importieren und exportieren. */
(() => {
  'use strict';

  const PLACEHOLDER = /\[([^\[\]\n]{1,40})\]/g;
  const MAX_COLORS = 6;
  const DEFAULT_COLOR = '#E8551F';
  const FORMAT_LABELS = {
    '16:9': '16:9 Querformat (1920 × 1080 Pixel)',
    '9:16': '9:16 Hochformat (1080 × 1920 Pixel)',
    '1:1': '1:1 Quadrat (1080 × 1080 Pixel)',
    '4:5': '4:5 Hochformat (1080 × 1350 Pixel)',
  };
  const OVERLAYS = ['preset-fill', 'preset-manager', 'preset-editor'];

  const $ = (id) => document.getElementById(id);
  let ctx = null;
  let presets = [];
  let editingId = null;
  let filling = null;

  // ------------------------------------------------------------ Logik

  const placeholders = (text) => [...new Set([...text.matchAll(PLACEHOLDER)].map((m) => m[1].trim()))];

  function brandLines(brand) {
    if (!brand) return [];
    const lines = [];
    if (brand.format) lines.push(`Format: ${FORMAT_LABELS[brand.format] || brand.format}`);
    if (brand.duration) lines.push(`Länge: ${brand.duration} Sekunden`);
    if (brand.colors && brand.colors.length) lines.push(`Farben: ${brand.colors.join(', ')} – verwende genau diese Farben`);
    if (brand.fonts) lines.push(`Schriften: ${brand.fonts}`);
    if (brand.logo) lines.push(`Logo: ${brand.logo} – binde es gut sichtbar ein`);
    if (brand.notes) lines.push(`Weitere Hinweise: ${brand.notes}`);
    return lines;
  }

  function compose(preset, values) {
    let text = preset.text.replace(PLACEHOLDER, (match, name) => (values[name.trim()] || '').trim() || match);
    const lines = brandLines(preset.brand);
    if (lines.length) {
      text += `\n\nVorgaben aus der Vorlage „${preset.name}“ (haben Vorrang vor Standardwerten):\n`
        + lines.map((line) => `- ${line}`).join('\n');
    }
    return text;
  }

  function setPrompt(text) {
    ctx.prompt.value = text;
    ctx.prompt.focus();
    ctx.prompt.scrollTop = 0;
  }

  // ------------------------------------------------------------ Fenster

  let returnFocus = null;
  let editorSnapshot = '';
  const allClosed = () => OVERLAYS.every((overlayId) => $(overlayId).hidden);

  function open(id) {
    if (allClosed()) returnFocus = document.activeElement;
    OVERLAYS.forEach((overlayId) => { $(overlayId).hidden = overlayId !== id; });
  }

  function close(id) {
    if ($(id).hidden) return;
    $(id).hidden = true;
    if (allClosed() && returnFocus && document.contains(returnFocus)) returnFocus.focus();
    if (allClosed()) returnFocus = null;
  }

  // Schließen auf Wunsch: Beim Editor nur nach Rückfrage, falls etwas geändert wurde.
  function requestClose(id) {
    if (id === 'preset-editor' && JSON.stringify(collectEditor()) !== editorSnapshot
        && !window.confirm('Ungespeicherte Änderungen verwerfen?')) return;
    close(id);
  }

  function makeButton(label, onClick, className) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    if (className) button.className = className;
    button.addEventListener('click', onClick);
    return button;
  }

  function renderChips() {
    const bar = $('templates');
    bar.replaceChildren(...presets.map((preset) => {
      const chip = makeButton(preset.name, () => usePreset(preset), preset.builtin ? '' : 'chip-own');
      if (preset.brand) { chip.classList.add('chip-brand'); chip.title = 'Mit Marken-Vorgaben'; }
      return chip;
    }));
    bar.append(
      makeButton('＋ Als Vorlage speichern', () => openEditor(null, { text: ctx.prompt.value }), 'chip-action'),
      makeButton('Vorlagen verwalten', openManager, 'chip-action'),
    );
  }

  function usePreset(preset) {
    const names = placeholders(preset.text);
    if (!names.length && !preset.brand) { close('preset-manager'); setPrompt(compose(preset, {})); return; }
    filling = preset;
    $('fill-title').textContent = `Vorlage „${preset.name}“`;
    const form = $('fill-form');
    form.replaceChildren(...names.map((name, index) => {
      const label = document.createElement('label');
      const input = document.createElement('input');
      label.textContent = name;
      input.dataset.name = name;
      input.id = `fill-${index}`;
      label.append(input);
      return label;
    }));
    $('fill-intro').hidden = !names.length;
    renderBrandSummary($('fill-brand'), preset.brand);
    open('preset-fill');
    const first = form.querySelector('input');
    if (first) first.focus(); else $('fill-apply').focus();
  }

  function renderBrandSummary(container, brand) {
    const lines = brandLines(brand);
    container.hidden = !lines.length;
    if (!lines.length) return;
    const head = document.createElement('strong');
    head.textContent = 'Marken-Vorgaben';
    const list = document.createElement('ul');
    lines.forEach((line) => { const li = document.createElement('li'); li.textContent = line; list.append(li); });
    const swatches = document.createElement('div');
    swatches.className = 'swatches';
    (brand.colors || []).forEach((color) => {
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.background = color;
      swatch.title = color;
      swatches.append(swatch);
    });
    container.replaceChildren(head, list, swatches);
  }

  function applyFill() {
    const values = {};
    $('fill-form').querySelectorAll('input').forEach((input) => { values[input.dataset.name] = input.value; });
    close('preset-fill');
    setPrompt(compose(filling, values));
  }

  function presetMeta(preset) {
    const parts = [preset.builtin ? 'eingebaut' : 'eigene Vorlage'];
    const count = placeholders(preset.text).length;
    if (count) parts.push(`${count} ${count === 1 ? 'Platzhalter' : 'Platzhalter'}`);
    if (preset.brand) parts.push('mit Marken-Vorgaben');
    return parts.join(' · ');
  }

  function openManager() {
    const list = $('preset-list');
    list.replaceChildren(...presets.map((preset) => {
      const item = document.createElement('li');
      const info = document.createElement('div');
      const name = document.createElement('strong');
      const meta = document.createElement('span');
      name.textContent = preset.name;
      meta.className = 'preset-meta';
      meta.textContent = presetMeta(preset);
      info.append(name, meta);
      const actions = document.createElement('div');
      actions.className = 'preset-actions';
      actions.append(makeButton('Verwenden', () => usePreset(preset), 'ghost small'));
      if (preset.builtin) {
        actions.append(makeButton('Kopieren', () => openEditor(preset, { copy: true }), 'ghost small'));
      } else {
        actions.append(
          makeButton('Bearbeiten', () => openEditor(preset), 'ghost small'),
          makeButton('Kopieren', () => openEditor(preset, { copy: true }), 'ghost small'),
          makeButton('Löschen', () => deletePreset(preset), 'danger small'),
        );
      }
      item.append(info, actions);
      return item;
    }));
    open('preset-manager');
  }

  // ------------------------------------------------------------ Bearbeiten

  function addColorInput(value) {
    const colors = $('ed-colors');
    if (colors.children.length >= MAX_COLORS) return;
    const wrapper = document.createElement('span');
    wrapper.className = 'color-chip';
    const input = document.createElement('input');
    input.type = 'color';
    input.value = value || DEFAULT_COLOR;
    input.setAttribute('aria-label', 'Farbe');
    const remove = makeButton('×', () => { wrapper.remove(); updateColorButton(); }, 'ghost small');
    remove.setAttribute('aria-label', 'Farbe entfernen');
    wrapper.append(input, remove);
    colors.append(wrapper);
    updateColorButton();
  }

  function updateColorButton() {
    $('ed-add-color').disabled = $('ed-colors').children.length >= MAX_COLORS;
  }

  function fillLogoOptions(selected) {
    const select = $('ed-logo');
    const images = ctx.getAssets().filter((file) => file.type === 'image').map((file) => `assets/${file.name}`);
    if (selected && !images.includes(selected)) images.push(selected);
    const none = new Option('kein Logo', '');
    select.replaceChildren(none, ...images.map((path) => new Option(path.replace('assets/', ''), path)));
    select.value = selected || '';
  }

  function updatePlaceholderHint() {
    const names = placeholders($('ed-text').value);
    $('ed-placeholders').textContent = names.length
      ? `Wird beim Verwenden abgefragt: ${names.join(', ')}` : 'Keine Platzhalter erkannt.';
  }

  function openEditor(preset, options = {}) {
    const source = preset || { name: '', text: options.text || '', brand: null };
    const brand = source.brand || {};
    editingId = preset && !preset.builtin && !options.copy ? preset.id : null;
    $('editor-title').textContent = editingId ? 'Vorlage bearbeiten' : 'Neue Vorlage';
    $('ed-name').value = options.copy ? `${source.name} (Kopie)` : source.name;
    $('ed-text').value = source.text;
    $('ed-format').value = brand.format || '';
    $('ed-duration').value = brand.duration || '';
    $('ed-fonts').value = brand.fonts || '';
    $('ed-notes').value = brand.notes || '';
    $('ed-colors').replaceChildren();
    (brand.colors || []).forEach(addColorInput);
    updateColorButton();
    fillLogoOptions(brand.logo || '');
    $('ed-brand-box').open = Boolean(source.brand);
    $('ed-error').hidden = true;
    updatePlaceholderHint();
    open('preset-editor');
    editorSnapshot = JSON.stringify(collectEditor());
    $('ed-name').focus();
  }

  function collectEditor() {
    return {
      id: editingId,
      name: $('ed-name').value,
      text: $('ed-text').value,
      brand: {
        format: $('ed-format').value,
        duration: Number($('ed-duration').value) || 0,
        colors: [...$('ed-colors').querySelectorAll('input')].map((input) => input.value.toUpperCase()),
        fonts: $('ed-fonts').value,
        logo: $('ed-logo').value,
        notes: $('ed-notes').value,
      },
    };
  }

  async function saveEditor() {
    try {
      await ctx.postJson('/api/presets/save', { preset: collectEditor() });
      close('preset-editor');
      await load();
      ctx.toast('Vorlage gespeichert.');
    } catch (error) {
      $('ed-error').textContent = error.message;
      $('ed-error').hidden = false;
    }
  }

  async function deletePreset(preset) {
    if (!window.confirm(`Vorlage „${preset.name}“ wirklich löschen?`)) return;
    try {
      await ctx.postJson('/api/presets/delete', { id: preset.id });
      await load();
      openManager();
      ctx.toast('Vorlage gelöscht.');
    } catch (error) { ctx.toast(error.message); }
  }

  async function importFile(file) {
    try {
      const result = await ctx.api('/api/presets/import', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: await file.text(),
      });
      await load();
      openManager();
      const skipped = result.skipped ? `, ${result.skipped} übersprungen` : '';
      ctx.toast(`${result.imported} Vorlage(n) importiert${skipped}.`);
    } catch (error) { ctx.toast(error.message); }
  }

  // ------------------------------------------------------------ Start

  async function load() {
    try {
      presets = (await ctx.api('/api/presets')).presets || [];
      renderChips();
    } catch (error) { ctx.toast(error.message); }
  }

  function wire() {
    $('fill-apply').addEventListener('click', applyFill);
    $('fill-form').addEventListener('submit', (event) => { event.preventDefault(); applyFill(); });
    $('preset-new').addEventListener('click', () => openEditor(null));
    $('ed-save').addEventListener('click', saveEditor);
    $('editor-form').addEventListener('submit', (event) => { event.preventDefault(); saveEditor(); });
    $('ed-add-color').addEventListener('click', () => addColorInput());
    $('ed-text').addEventListener('input', updatePlaceholderHint);
    $('preset-import').addEventListener('change', (event) => {
      if (event.target.files[0]) importFile(event.target.files[0]);
      event.target.value = '';
    });
    OVERLAYS.forEach((id) => {
      const overlay = $(id);
      // Nur schließen, wenn Maus-Drücken UND Loslassen auf dem Hintergrund waren (nicht beim Markieren von Text).
      let pressedOnBackdrop = false;
      overlay.addEventListener('mousedown', (event) => { pressedOnBackdrop = event.target === overlay; });
      overlay.addEventListener('click', (event) => {
        if (id !== 'preset-editor' && pressedOnBackdrop && event.target === overlay) close(id);
      });
      overlay.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => requestClose(id)));
    });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      const visible = OVERLAYS.find((id) => !$(id).hidden);
      if (visible) { event.stopPropagation(); requestClose(visible); }
    });
  }

  window.CMGPresets = {
    init(context) { ctx = context; wire(); load(); },
    compose,
    placeholders,
  };
})();
