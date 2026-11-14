# -*- coding: utf-8 -*-
"""翻译引擎：Google 免费接口 / OpenAI 兼容的大模型接口。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

try:  # Google 会拦截普通 requests 的 TLS 指纹，用 curl_cffi 模拟浏览器
    from curl_cffi import requests as browser_requests
except ImportError:  # pragma: no cover - 没装时退回普通 requests
    browser_requests = None

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 常用语言代码 -> 中文名称
LANGUAGE_NAMES = {
    "auto": "自动检测",
    "en": "英语",
    "zh": "中文",
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "it": "意大利语",
    "ar": "阿拉伯语",
    "th": "泰语",
    "vi": "越南语",
    "id": "印尼语",
    "ms": "马来语",
    "tr": "土耳其语",
    "nl": "荷兰语",
    "pl": "波兰语",
    "hi": "印地语",
    "sv": "瑞典语",
    "uk": "乌克兰语",
    "he": "希伯来语",
    "fa": "波斯语",
    "el": "希腊语",
    "cs": "捷克语",
    "da": "丹麦语",
    "fi": "芬兰语",
    "no": "挪威语",
    "ro": "罗马尼亚语",
    "hu": "匈牙利语",
    "bg": "保加利亚语",
}


def language_label(code: str) -> str:
    if not code:
        return "自动检测"
    return LANGUAGE_NAMES.get(code, code)


class TranslateError(Exception):
    """带用户可读中文说明的翻译错误。"""


@dataclass
class TranslationResult:
    text: str
    detected: str
    provider: str


class GoogleTranslator:
    """Google 网页翻译的免费接口，免 Key，通常可以直接访问。"""

    name = "Google 翻译"
    MAX_CHUNK = 1600

    def __init__(self, cfg: dict):
        self.endpoint = cfg.get("google", {}).get(
            "endpoint", "https://translate.googleapis.com/translate_a/single"
        )
        if browser_requests is not None:
            self.session = browser_requests.Session(impersonate="chrome")
        else:
            self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def translate(self, text: str, target: str, source: str = "auto") -> TranslationResult:
        chunks = _split_text(text, self.MAX_CHUNK)
        if not chunks:
            raise TranslateError("没有可翻译的内容。")

        parts = []
        detected = source if source != "auto" else ""
        for index, chunk in enumerate(chunks):
            data = self._translate_chunk(chunk, target, source)
            parts.append(data["text"])
            if data["detected"]:
                detected = data["detected"]
            if index + 1 < len(chunks):
                time.sleep(0.15)  # 避免连续请求被限流
        return TranslationResult("".join(parts), detected, self.name)

    def _translate_chunk(self, text: str, target: str, source: str) -> dict:
        params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = self.session.get(self.endpoint, params=params, timeout=15)
                if resp.status_code != 200:
                    raise TranslateError(f"翻译接口返回 HTTP {resp.status_code}。")
                data = resp.json()
                segments = data[0] or []
                translated = "".join(
                    seg[0] or "" for seg in segments if isinstance(seg, list) and seg
                )
                detected = data[2] if len(data) > 2 and isinstance(data[2], str) else ""
                if not translated.strip():
                    raise TranslateError("翻译接口没有返回内容。")
                return {"text": translated, "detected": detected}
            except TranslateError:
                raise
            except Exception as exc:  # requests / curl_cffi / JSON 解析错误
                last_error = exc
                log.warning("Google 翻译第 %s 次失败: %s", attempt + 1, exc)
                time.sleep(0.8 * (attempt + 1))
        raise TranslateError(
            "无法连接 Google 翻译接口，请检查网络，或在设置里改用「AI 大模型」引擎。"
        ) from last_error


class LLMTranslator:
    """任意 OpenAI 兼容接口（DeepSeek / OpenAI / Kimi / 通义 等）。"""

    name = "AI 大模型"

    def __init__(self, cfg: dict):
        llm = cfg.get("llm", {})
        self.base_url = (llm.get("base_url") or "").strip().rstrip("/")
        self.api_key = (llm.get("api_key") or "").strip()
        self.model = (llm.get("model") or "").strip()
        if not self.base_url or not self.api_key or not self.model:
            raise TranslateError(
                "AI 大模型引擎还没配置好：请在「设置」里填写接口地址、API Key 和模型名。"
            )

    def translate(self, text: str, target: str, source: str = "auto") -> TranslationResult:
        target_name = language_label(target)
        system_prompt = (
            f"你是一名专业翻译。请把用户提供的文本翻译成{target_name}。\n"
            "要求：只输出译文本身，不要解释、不要加引号、不要用 Markdown 代码块；"
            "保留原文的换行与段落结构；人名、品牌名、代码、变量名保持原样。"
        )
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = self.base_url + "/chat/completions"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as exc:
            raise TranslateError("无法连接 AI 接口，请检查网络和接口地址。") from exc

        if resp.status_code == 401:
            raise TranslateError("AI 接口鉴权失败（401），请检查 API Key 是否填写正确。")
        if resp.status_code != 200:
            detail = resp.text[:200].replace("\n", " ")
            raise TranslateError(f"AI 接口返回 HTTP {resp.status_code}：{detail}")

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise TranslateError("AI 接口返回的数据无法解析。") from exc

        content = _strip_code_fence((content or "").strip())
        if not content:
            raise TranslateError("AI 接口返回了空内容。")
        return TranslationResult(content, source if source != "auto" else "", self.name)


def get_translator(cfg: dict):
    provider = (cfg.get("provider") or "google").lower()
    if provider == "llm":
        return LLMTranslator(cfg)
    return GoogleTranslator(cfg)


def _split_text(text: str, limit: int) -> list[str]:
    """按行切分长文本，保证拼回去与原文一致（除纯空白块）。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    chunks: list[str] = []
    buf = ""
    for i, line in enumerate(lines):
        piece = line + ("\n" if i < len(lines) - 1 else "")
        if len(buf) + len(piece) <= limit:
            buf += piece
            continue
        if buf:
            chunks.append(buf)
        while len(piece) > limit:
            chunks.append(piece[:limit])
            piece = piece[limit:]
        buf = piece
    if buf:
        chunks.append(buf)
    return [chunk for chunk in chunks if chunk.strip()]


def _strip_code_fence(text: str) -> str:
    if text.startswith("```") and text.endswith("```") and len(text) >= 6:
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text
