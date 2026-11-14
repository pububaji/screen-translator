# -*- coding: utf-8 -*-
"""生成 assets/icon.ico（桌面快捷方式用）。"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets", "icon.ico")

image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 247, 247), radius=56, fill=(37, 99, 235, 255))
font = None
for path in (
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
):
    try:
        font = ImageFont.truetype(path, 150)
        break
    except OSError:
        continue
if font is not None:
    draw.text((128, 132), "译", font=font, fill="white", anchor="mm")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
image.save(OUT, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("saved", OUT)
