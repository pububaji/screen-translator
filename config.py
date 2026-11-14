# -*- coding: utf-8 -*-
"""配置文件的读取与保存。"""
from __future__ import annotations

import copy
import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "target_lang": "zh-CN",
    "source_lang": "auto",
    "provider": "google",          # google | llm
    "hotkeys": {
        "region": "ctrl+alt+t",
        "fullscreen": "ctrl+alt+f",
        "clipboard": "ctrl+alt+c",
    },
    "google": {
        "endpoint": "https://translate.googleapis.com/translate_a/single",
    },
    "llm": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
    except FileNotFoundError:
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(user_cfg, dict):
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, user_cfg)


def save_config(cfg: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)
