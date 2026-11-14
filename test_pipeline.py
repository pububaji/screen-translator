# -*- coding: utf-8 -*-
"""开发自测：生成英文测试图 -> 本地 OCR -> 在线翻译。"""
from __future__ import annotations

import os
import sys
import time

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config  # noqa: E402
from ocr_engine import OcrEngine  # noqa: E402
from translate import TranslateError, get_translator  # noqa: E402


def build_test_image() -> Image.Image:
    width, height = 980, 300
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = r"C:\Windows\Fonts\segoeui.ttf"
    font = ImageFont.truetype(font_path, 30)
    draw.text((40, 35), "Screen Translator Test", font=font, fill="black")
    draw.text((40, 110), "This sentence should be recognized and translated", font=font, fill="black")
    draw.text((40, 185), "into Chinese automatically.", font=font, fill="black")
    return image


def main() -> int:
    image = build_test_image()
    image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_image.png")
    image.save(image_path)

    start = time.time()
    text = OcrEngine().recognize(image)
    print(f"--- OCR ({time.time() - start:.2f}s) ---")
    print(text)
    if "translator" not in text.lower():
        print("!! OCR 结果不符合预期")
        return 1

    cfg = load_config()
    start = time.time()
    try:
        result = get_translator(cfg).translate(text, cfg["target_lang"], cfg["source_lang"])
    except TranslateError as exc:
        print(f"!! 翻译失败: {exc}")
        return 1
    print(f"--- 翻译 ({time.time() - start:.2f}s, {result.provider}, 检测={result.detected}) ---")
    print(result.text)
    if not any("\u4e00" <= ch <= "\u9fff" for ch in result.text):
        print("!! 译文里没有中文")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
