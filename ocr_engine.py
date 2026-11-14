# -*- coding: utf-8 -*-
"""本地离线 OCR（RapidOCR / PP-OCR 模型，中英混排）。"""
from __future__ import annotations

import logging
import threading

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


class OcrEngine:
    """懒加载 RapidOCR，并把识别出的文字按阅读顺序拼成文本。"""

    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()

    def warmup(self) -> None:
        self._ensure()

    def _ensure(self):
        with self._lock:
            if self._engine is None:
                from rapidocr_onnxruntime import RapidOCR  # 延迟导入，加快启动

                self._engine = RapidOCR()
            return self._engine

    def recognize(self, image: Image.Image) -> str:
        """返回按阅读顺序排列的文本；没有识别到内容时返回空字符串。"""
        prepared = self._prepare(image)
        array = np.asarray(prepared)
        if array.ndim == 3 and array.shape[2] == 3:
            array = np.ascontiguousarray(array[:, :, ::-1])  # RGB -> BGR
        engine = self._ensure()
        result, _elapse = engine(array)
        if not result:
            return ""
        return _layout_text(_parse_boxes(result))

    @staticmethod
    def _prepare(image: Image.Image) -> Image.Image:
        """小截图放大一点，显著提升小字号文字的识别率。"""
        image = image.convert("RGB")
        width, height = image.size
        scale = 1.0
        if width < 500 or height < 120:
            scale = 2.0
        elif width < 1200 and height < 600:
            scale = 1.5
        if scale > 1.0:
            image = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.LANCZOS,
            )
        return image


def _parse_boxes(result) -> list[tuple[float, float, float, float, str]]:
    boxes = []
    for entry in result:
        try:
            box, text, score = entry[0], entry[1], entry[2]
        except (TypeError, IndexError):
            continue
        if not text or not str(text).strip():
            continue
        try:
            if score is not None and float(score) < 0.32:
                continue
        except (TypeError, ValueError):
            pass
        points = np.asarray(box, dtype=float)
        if points.ndim != 2 or points.shape[0] == 0:
            continue
        left = float(points[:, 0].min())
        right = float(points[:, 0].max())
        top = float(points[:, 1].min())
        bottom = float(points[:, 1].max())
        boxes.append((left, top, right, bottom, str(text).strip()))
    return boxes


def _layout_text(boxes: list[tuple[float, float, float, float, str]]) -> str:
    """把文本框按行聚合，行内按水平位置拼接，行间用换行。"""
    if not boxes:
        return ""

    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    lines: list[list[tuple[float, float, float, float, str]]] = []
    for box in boxes:
        top, bottom = box[1], box[3]
        height = max(1.0, bottom - top)
        target = None
        for line in lines:
            line_top = min(item[1] for item in line)
            line_bottom = max(item[3] for item in line)
            overlap = min(bottom, line_bottom) - max(top, line_top)
            if overlap > 0.5 * min(height, max(1.0, line_bottom - line_top)):
                target = line
                break
        if target is None:
            lines.append([box])
        else:
            target.append(box)

    lines.sort(key=lambda line: min(item[1] for item in line))
    output = []
    for line in lines:
        line.sort(key=lambda item: item[0])
        pieces = []
        previous = None
        for item in line:
            if previous is not None:
                gap = item[0] - previous[2]
                threshold = max(2.0, min(item[3] - item[1], previous[3] - previous[1]) * 0.28)
                if gap > threshold:
                    pieces.append(" ")
            pieces.append(item[4])
            previous = item
        text = "".join(pieces).strip()
        if text:
            output.append(text)
    return "\n".join(output)
