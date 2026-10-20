"""Erzeugt die Screenshots für die README.

Rendert ein kurzes Beispielvideo, spielt ein typisches Gespräch ein und
fotografiert die Oberfläche (hell, dunkel, Modellauswahl, Anmeldung bei Claude und ChatGPT, Vorlagen).

Aufruf (mit dem Python des Studios, das Playwright enthält):
    <venv-python> docs/make_screenshots.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "images"
sys.path.insert(0, str(ROOT / "studio-app"))
os.environ["CMG_CLAUDE_BIN"] = str(ROOT / "tests" / "fake_claude.py")
os.environ["CMG_CODEX_BIN"] = str(ROOT / "tests" / "fake_codex.py")
os.environ["CMG_FAKE_CODEX_LOGGED_OUT"] = "1"  # damit das Studio den ChatGPT-Anmeldedialog zeigt

import studio_app  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

FPS = 30
DURATION = 3
SCENES = [
    {"bg": "#f4efe6", "fg": "#1b1a17", "accent": "#e8551f", "title": "Studio Nord", "sub": "Motion Showreel 2026"},
    {"bg": "#e8551f", "fg": "#fffdf9", "accent": "#1b1a17", "title": "Bewegung", "sub": "mit Haltung"},
    {"bg": "#1b1a17", "fg": "#f4efe6", "accent": "#e8551f", "title": "Typografie", "sub": "die man spürt"},
]

DEMO_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;font-family:Georgia,'Times New Roman',serif}
#stage{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;padding:0 9vw}
#title{font-size:12vw;line-height:.9;letter-spacing:-.04em;font-weight:700}
#sub{font:500 2.4vw system-ui,sans-serif;margin-top:2.5vw;letter-spacing:.02em}
#bar{position:absolute;left:9vw;bottom:12vh;height:1.2vw;width:0}
</style></head><body><div id="stage"><div id="title"></div><div id="sub"></div></div><div id="bar"></div>
<script>
const SCENES = __SCENES__;
const ease = t => 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3);
window.seek = (t) => {
  const index = Math.min(SCENES.length - 1, Math.floor(t));
  const local = t - index, s = SCENES[index];
  document.body.style.background = s.bg;
  const title = document.getElementById('title'), sub = document.getElementById('sub'), bar = document.getElementById('bar');
  title.textContent = s.title; title.style.color = s.fg;
  sub.textContent = s.sub; sub.style.color = s.fg;
  title.style.transform = `translateY(${(1 - ease(local * 2.5)) * 6}vw)`;
  title.style.opacity = ease(local * 3);
  sub.style.opacity = ease(local * 3 - .6);
  bar.style.background = s.accent; bar.style.width = (ease(local * 1.6) * 40) + 'vw';
};
window.seek(0);
</script></body></html>"""


def render_demo_media(studio, ffmpeg):
    """Rendert ein kleines Showreel und Vorschaubilder in den Beispiel-Studio-Ordner."""
    html = DEMO_HTML.replace("__SCENES__", json.dumps(SCENES))
    frames = Path(tempfile.mkdtemp())
    previews = studio / "exports" / "vorschau"
    previews.mkdir(parents=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.set_content(html)
        for index in range(FPS * DURATION):
            page.evaluate("t => window.seek(t)", 0.55 + index / FPS)
            page.screenshot(path=str(frames / "f_{:04d}.png".format(index)))
        small = browser.new_page(viewport={"width": 640, "height": 360})
        small.set_content(html)
        for number, moment in enumerate((0.6, 0.95, 1.6, 1.95, 2.6, 2.95), start=1):
            small.evaluate("t => window.seek(t)", moment)
            small.screenshot(path=str(previews / "vorschau_{:02d}.png".format(number)))
        browser.close()
    subprocess.run([ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", str(frames / "f_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(studio / "exports" / "showreel.mp4")], check=True)
    shutil.rmtree(frames, ignore_errors=True)
    (studio / "assets" / "musik.mp3").write_bytes(b"\0" * 3_400_000)
    (studio / "assets" / "logo.png").write_bytes((previews / "vorschau_01.png").read_bytes())


def demo_conversation():
    request = ("Erstelle ein 15-Sekunden-Showreel für mein Designstudio „Studio Nord“: "
               "große Typografie, Creme, Schwarz und Orange, fünf Szenen.")
    steps = ["Erstellt showreel.html", "Erstellt render.py", "Führt aus: Vorschau in 960 × 540 rendern",
             "Prüft Bild kontaktbogen.png", "Bearbeitet showreel.html",
             "Führt aus: MP4 in voller Auflösung exportieren"]
    answer = ("Dein Showreel ist fertig: **exports/showreel.mp4** (15 Sekunden, 1920 × 1080).\n\n"
              "- **Szene 1–2:** Titel „Studio Nord“ mit weich einlaufender Typografie\n"
              "- **Szene 3:** Farbwechsel auf Orange, der Balken gibt den Takt vor\n"
              "- **Szene 4–5:** dunkler Abschluss mit ruhigem Ausklang\n\n"
              "Nach der ersten Vorschau habe ich zwei Dinge korrigiert: Der Untertitel in Szene 2 "
              "stand zu kurz, und der Übergang zu Szene 4 hatte einen leeren Frame.\n\n"
              "Möchtest du noch Musik ergänzen? Lege dazu einfach eine Datei rechts unter „Eigene Dateien“ ab.")
    items = [{"kind": "user", "text": request}]
    items += [{"kind": "tool", "text": step, "detail": ""} for step in steps]
    items += [{"kind": "assistant", "text": answer}, {"kind": "done"}]
    return items


DEMO_PRESET = {
    "id": "demo-studio-nord", "name": "Studio Nord – Reel",
    "text": "Erstelle ein Instagram-Reel für Studio Nord über [Thema].\n"
            "Die erste Sekunde muss sofort Aufmerksamkeit erzeugen. Schließe mit: [Handlungsaufforderung].",
    "brand": {"format": "9:16", "duration": 15, "colors": ["#E8551F", "#1B1A17", "#F4EFE6"],
              "fonts": "Georgia für Titel, Inter für Text", "logo": "assets/logo.png",
              "notes": "Ruhige, präzise Bewegungen. Immer per Du."},
}


def open_preset_editor(page):
    page.get_by_role("button", name="Vorlagen verwalten").click()
    page.locator("#preset-list li", has_text="Studio Nord").get_by_role("button", name="Bearbeiten").click()
    page.locator("#ed-brand-box").evaluate("box => { box.open = true; }")


def open_preset_fill(page):
    page.get_by_role("button", name="Studio Nord – Reel").click()
    page.locator("#fill-form input").nth(0).fill("Unser neues Büro")


def show_model_list(page):
    """Zeigt die Modellauswahl aufgeklappt (ein natives Auswahlmenü lässt sich nicht fotografieren).

    Dafür wird eine Kopie der echten Auswahl als Liste unter das Feld gelegt – mit denselben Einträgen.
    """
    page.evaluate("""() => {
        const select = document.getElementById('model');
        const label = select.closest('label');
        label.style.position = 'relative';
        const list = select.cloneNode(true);
        list.removeAttribute('id');
        list.size = select.options.length + list.querySelectorAll('optgroup').length;
        list.value = select.value;
        Object.assign(list.style, {
            position: 'absolute', top: 'calc(100% + 8px)', right: '0', height: 'auto', zIndex: 5,
            minWidth: select.offsetWidth + 'px', borderRadius: '12px', padding: '8px', backgroundImage: 'none',
            boxShadow: '0 16px 40px rgba(0, 0, 0, .14)', overflow: 'hidden',
        });
        label.append(list);
    }""")
    label = page.locator(".model-select").bounding_box()
    menu = page.locator(".model-select select").nth(1).bounding_box()
    left = max(0, label["x"] - 32)
    return {"x": left, "y": 0, "width": menu["x"] + menu["width"] + 32 - left, "height": menu["y"] + menu["height"] + 32}


def take_screenshots(server):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        shots = [
            ("studio-hell.png", {"width": 1440, "height": 900}, "light", None),
            ("studio-dunkel.png", {"width": 1440, "height": 900}, "dark", None),
            ("anmeldung.png", {"width": 1440, "height": 900}, "light", "login"),
            ("anmeldung-chatgpt.png", {"width": 1440, "height": 900}, "light", "login-codex"),
            ("modell-auswahl.png", {"width": 1440, "height": 900}, "light", "models"),
            ("vorlage-bearbeiten.png", {"width": 1440, "height": 1000}, "light", "editor"),
            ("vorlage-ausfuellen.png", {"width": 1440, "height": 900}, "light", "fill"),
        ]
        for name, viewport, scheme, mode in shots:
            context = browser.new_context(viewport=viewport, color_scheme=scheme, device_scale_factor=2)
            page = context.new_page()
            page.goto(server.launch_url)
            page.locator(".msg-assistant").first.wait_for()
            page.locator(".media-card video").first.wait_for()
            page.evaluate("""() => Promise.all([...document.querySelectorAll('video')].map(v =>
                v.readyState >= 2 ? null : new Promise(r => v.addEventListener('loadeddata', r, {once: true}))))""")
            # Auf ein fertig geladenes Standbild warten, damit kein Ladesymbol im Bild ist.
            page.evaluate("""() => Promise.all([...document.querySelectorAll('video')].map(v =>
                new Promise(r => { v.addEventListener('seeked', r, {once: true}); v.currentTime = 0.4; })))""")
            page.wait_for_function("() => [...document.querySelectorAll('video')].every(v => v.readyState >= 4)")
            page.wait_for_timeout(2000)
            page.mouse.move(0, viewport["height"] - 1)
            if mode == "login":
                page.evaluate("""() => { document.getElementById('login').hidden = false;
                    document.getElementById('login-status').textContent = 'Warte auf die Anmeldung im Browser …'; }""")
            if mode == "login-codex":
                page.locator("#model").select_option("codex-max")
                page.locator("#login").wait_for()
                page.evaluate("""() => { document.getElementById('login-status').textContent =
                    'Warte auf die Anmeldung im Browser …'; }""")
            clip = show_model_list(page) if mode == "models" else None
            if mode == "editor":
                open_preset_editor(page)
            if mode == "fill":
                open_preset_fill(page)
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUTPUT / name), clip=clip)
            context.close()
        browser.close()


def main():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg wurde nicht gefunden.")
        return 1
    base = Path(tempfile.mkdtemp())
    studio, data = base / "studio", base / "data"
    for folder in (studio / "exports", studio / "assets", data):
        folder.mkdir(parents=True)
    render_demo_media(studio, ffmpeg)
    (studio / "presets.json").write_text(json.dumps({"version": 1, "presets": [DEMO_PRESET]}, ensure_ascii=False),
                                         encoding="utf-8")
    (data / "chat.json").write_text(json.dumps(demo_conversation(), ensure_ascii=False), encoding="utf-8")

    server = studio_app.create_server(studio, data)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        take_screenshots(server)
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(base, ignore_errors=True)
    print("Screenshots gespeichert in", OUTPUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
