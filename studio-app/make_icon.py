"""Erzeugt das App-Symbol (icon.png und icon.ico) im Stil der Oberfläche."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
ORANGE = (232, 85, 31, 255)
INK = (27, 26, 23, 255)
CREAM = (244, 239, 230, 255)
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def draw_icon():
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=56, fill=CREAM)
    draw.rounded_rectangle((74, 74, 206, 206), radius=26, fill=INK)
    draw.rounded_rectangle((52, 52, 184, 184), radius=26, fill=ORANGE)
    # Play-Symbol als Hinweis auf Video
    draw.polygon([(100, 88), (100, 148), (150, 118)], fill=CREAM)
    return image


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    target.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    icon.save(target / "icon.png")
    icon.save(target / "icon.ico", sizes=ICO_SIZES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
