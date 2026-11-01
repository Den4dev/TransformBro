# -*- coding: utf-8 -*-
"""Генерирует иконку приложения assets/TransformBro.ico (16..256 px)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(exist_ok=True)
SIZE = 256
S = {
    "base": (30, 30, 46), "surface": (49, 50, 68), "blue": (137, 180, 250),
    "mauve": (203, 166, 247), "green": (166, 227, 161), "text": (205, 214, 244),
}

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([6, 6, SIZE - 6, SIZE - 6], radius=52, fill=S["base"])
d.rounded_rectangle([6, 6, SIZE - 6, SIZE - 6], radius=52, outline=S["surface"], width=3)

# две стрелки конвертации
arrow_top = [(58, 96), (150, 96)]
d.line(arrow_top, fill=S["blue"], width=13)
d.polygon([(150, 80), (176, 96), (150, 112)], fill=S["blue"])
arrow_bot = [(198, 160), (106, 160)]
d.line(arrow_bot, fill=S["mauve"], width=13)
d.polygon([(106, 144), (80, 160), (106, 176)], fill=S["mauve"])

def font(px):
    for p in (r"C:\Windows\Fonts\segoebd.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
        try:
            return ImageFont.truetype(p, px)
        except OSError:
            continue
    return ImageFont.load_default()

for text, xy, color in (("F", (30, 26), S["text"]), ("L", (186, 186), S["green"])):
    d.text(xy, text, font=font(62), fill=color)

sizes = [16, 24, 32, 48, 64, 128, 256]
img.save(OUT / "TransformBro.ico", format="ICO", sizes=[(s, s) for s in sizes])
img.save(OUT / "TransformBro.png")
print("ok:", (OUT / "TransformBro.ico").stat().st_size, "bytes")
