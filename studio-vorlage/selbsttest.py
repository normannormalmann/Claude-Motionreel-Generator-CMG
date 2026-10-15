"""Selbsttest des Motion Studios.

Rendert eine kurze Animation mit Playwright (Chromium) und setzt die Bilder
mit FFmpeg zu einer MP4 zusammen. Läuft alles durch, ist die Render-Kette
vollständig eingerichtet.

Aufruf:  <venv-python> tools/selbsttest.py [--ffmpeg PFAD]
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WIDTH, HEIGHT = 320, 180
FPS = 10
FRAME_COUNT = 10
H264_ENCODERS = ("libx264", "libopenh264")

ANIMATION_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body { margin: 0; width: 320px; height: 180px; overflow: hidden; background: #f4efe6; }
  #box { position: absolute; top: 65px; width: 50px; height: 50px; background: #ff5a1f; }
</style></head>
<body><div id="box"></div>
<script>
  window.seek = (t) => { document.getElementById('box').style.left = (20 + t * 230) + 'px'; };
  window.seek(0);
</script></body></html>"""


def render_frames(frame_dir):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.set_content(ANIMATION_HTML)
            for index in range(FRAME_COUNT):
                page.evaluate("t => window.seek(t)", index / FPS)
                page.screenshot(path=str(frame_dir / "frame_{:04d}.png".format(index)))
        finally:
            browser.close()


def encode_video(ffmpeg, frame_dir, output):
    """Kodiert die Bilder als H.264. Gibt den genutzten Encoder zurück."""
    for encoder in H264_ENCODERS:
        command = [
            ffmpeg, "-nostdin", "-y", "-loglevel", "error",
            "-framerate", str(FPS),
            "-i", str(frame_dir / "frame_%04d.png"),
            "-c:v", encoder, "-pix_fmt", "yuv420p",
            str(output),
        ]
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if result.returncode == 0 and output.exists() and output.stat().st_size > 0:
            return encoder
    raise RuntimeError(
        "FFmpeg konnte kein H.264-Video erzeugen. "
        "Deiner FFmpeg-Version fehlt vermutlich der H.264-Encoder (libx264)."
    )


def main():
    # Playwright-Meldungen enthalten Rahmenzeichen, die eine Windows-Konsole sonst nicht ausgeben kann.
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"), help="Pfad zu ffmpeg")
    args = parser.parse_args()

    if not args.ffmpeg:
        print("Selbsttest fehlgeschlagen: ffmpeg wurde nicht gefunden.")
        return 1

    with tempfile.TemporaryDirectory(prefix="cmg-selbsttest-") as tmp:
        work_dir = Path(tmp)
        try:
            render_frames(work_dir)
            encoder = encode_video(args.ffmpeg, work_dir, work_dir / "selbsttest.mp4")
        except Exception as error:  # Meldung für Laien verständlich ausgeben
            print("Selbsttest fehlgeschlagen: {}".format(error))
            return 1

    print("Selbsttest erfolgreich: Animation gerendert und als MP4 ({}) gespeichert.".format(encoder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
