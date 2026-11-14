# -*- coding: utf-8 -*-
"""界面：翻译结果窗口、悬浮提示、设置窗口。"""
from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import ttk

from capture import virtual_screen_rect
from config import ASSET_DIR
from translate import language_label

BG = "#f4f5f7"
INK = "#111827"
MUTED = "#6b7280"
BLUE = "#2563eb"
BLUE_DARK = "#1d4ed8"
FONT = "Microsoft YaHei UI"

TARGET_OPTIONS = [
    ("简体中文", "zh-CN"),
    ("繁体中文", "zh-TW"),
    ("英语", "en"),
    ("日语", "ja"),
    ("韩语", "ko"),
    ("法语", "fr"),
    ("德语", "de"),
    ("西班牙语", "es"),
    ("俄语", "ru"),
    ("葡萄牙语", "pt"),
    ("意大利语", "it"),
]

PROVIDER_OPTIONS = [
    ("Google 免费接口（无需配置）", "google"),
    ("AI 大模型（OpenAI 兼容接口）", "llm"),
]


def _display_to_code(display: str, options, fallback: str) -> str:
    for name, code in options:
        if name == display:
            return code
    return fallback


def _code_to_display(code: str, options, fallback: str) -> str:
    for name, value in options:
        if value == code:
            return name
    return fallback


class ResultWindow:
    """复用一个结果窗口，避免每次翻译都弹一个新窗口。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.win: tk.Toplevel | None = None
        self._translation = ""

    def _ensure(self) -> None:
        if self.win is not None and self.win.winfo_exists():
            return
        win = tk.Toplevel(self.root)
        win.title("屏幕翻译")
        win.configure(bg=BG)
        try:
            win.iconbitmap(os.path.join(ASSET_DIR, "icon.ico"))
        except tk.TclError:
            pass
        win.minsize(480, 380)
        win.protocol("WM_DELETE_WINDOW", self.hide)
        win.bind("<Escape>", lambda event: self.hide())

        outer = tk.Frame(win, bg=BG, padx=16, pady=14)
        outer.pack(fill="both", expand=True)

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        self.lang_label = tk.Label(
            head, text="", bg=BG, fg=INK, font=(FONT, 10, "bold"),
        )
        self.lang_label.pack(side="left")
        self.provider_label = tk.Label(
            head, text="", bg=BG, fg=MUTED, font=(FONT, 9),
        )
        self.provider_label.pack(side="right")

        tk.Label(outer, text="原文", bg=BG, fg=MUTED, font=(FONT, 9)).pack(
            anchor="w", pady=(12, 4)
        )
        self.original = tk.Text(
            outer, height=5, wrap="word", relief="flat", borderwidth=0,
            highlightthickness=0, bg="#e9ebef", fg="#4b5563",
            font=(FONT, 9), padx=10, pady=8, spacing1=2, spacing3=2,
        )
        self.original.pack(fill="x")

        tk.Label(outer, text="译文", bg=BG, fg=MUTED, font=(FONT, 9)).pack(
            anchor="w", pady=(12, 4)
        )

        footer = tk.Frame(outer, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(10, 0))

        text_frame = tk.Frame(outer, bg=BG)
        text_frame.pack(fill="both", expand=True, pady=(0, 4))
        self.translation = tk.Text(
            text_frame, height=10, wrap="word", relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground="#e2e5ea",
            highlightcolor="#e2e5ea", bg="#ffffff", fg=INK,
            font=(FONT, 11), padx=12, pady=10, spacing1=2, spacing3=2,
        )
        scrollbar = ttk.Scrollbar(
            text_frame, orient="vertical", command=self.translation.yview
        )
        self.translation.configure(yscrollcommand=scrollbar.set)
        self.translation.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.status = tk.Label(
            footer, text="", bg=BG, fg="#059669", font=(FONT, 9),
        )
        self.status.pack(side="left")

        close_btn = tk.Button(
            footer, text="关闭", command=self.hide, bg="#e5e7eb", fg=INK,
            activebackground="#d1d5db", activeforeground=INK,
            relief="flat", borderwidth=0, padx=16, pady=6,
            font=(FONT, 9), cursor="hand2",
        )
        close_btn.pack(side="right")
        self.copy_btn = tk.Button(
            footer, text="复制译文", command=self.copy, bg=BLUE, fg="white",
            activebackground=BLUE_DARK, activeforeground="white",
            relief="flat", borderwidth=0, padx=16, pady=6,
            font=(FONT, 9), cursor="hand2",
        )
        self.copy_btn.pack(side="right", padx=(0, 8))

        self.win = win

    @staticmethod
    def _set_text(widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.yview_moveto(0)
        widget.configure(state="disabled")

    def show(self, original: str, translation: str, target: str,
             detected: str = "", provider: str = "", anchor=None) -> None:
        self._ensure()
        assert self.win is not None
        self._translation = translation
        self.lang_label.configure(
            text=f"{language_label(detected)}  →  {language_label(target)}"
        )
        self.provider_label.configure(text=provider)
        self._set_text(self.original, original)
        self._set_text(self.translation, translation)
        self.status.configure(text="")
        self.copy_btn.configure(text="复制译文")

        vx, vy, vw, vh = virtual_screen_rect()
        width = min(680, max(480, vw - 40))
        height = min(620, max(380, vh - 70))
        x, y = self._position(anchor, width, height)
        self.win.geometry(f"{width}x{height}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        try:
            self.win.attributes("-topmost", True)
            self.win.after(350, self._unpin)
        except tk.TclError:
            pass

    def _unpin(self) -> None:
        try:
            if self.win is not None and self.win.winfo_exists():
                self.win.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _position(self, anchor, width: int, height: int) -> tuple[int, int]:
        vx, vy, vw, vh = virtual_screen_rect()
        if anchor:
            sx, sy, sw, sh = anchor
            x = sx + sw + 16
            y = sy
            if x + width > vx + vw - 12:
                x = sx - width - 16
            if x < vx + 12:
                x = vx + (vw - width) // 2
                y = sy + sh + 16
        else:
            x = vx + (vw - width) // 2
            y = vy + (vh - height) // 2
        x = min(max(x, vx + 12), vx + vw - width - 12)
        y = min(max(y, vy + 12), vy + vh - height - 12)
        return int(x), int(y)

    def copy(self) -> None:
        if not self._translation:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._translation)
        self.root.update()
        self.status.configure(text="已复制到剪贴板 ✓")
        self.copy_btn.configure(text="已复制")
        if self.win is not None:
            self.win.after(1500, self._reset_copy)

    def _reset_copy(self) -> None:
        try:
            self.copy_btn.configure(text="复制译文")
            self.status.configure(text="")
        except tk.TclError:
            pass

    def hide(self) -> None:
        try:
            if self.win is not None and self.win.winfo_exists():
                self.win.withdraw()
        except tk.TclError:
            pass


class BusyToast:
    """无边框悬浮提示；用于「识别中…」和错误消息。"""

    def __init__(self, root: tk.Tk, text: str, anchor=None,
                 timeout: int | None = None, error: bool = False):
        bg = "#7f1d1d" if error else "#111827"
        fg = "#fee2e2" if error else "#f9fafb"
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.96)
        frame = tk.Frame(self.win, bg=bg)
        frame.pack()
        self.label = tk.Label(
            frame, text=text, bg=bg, fg=fg, font=(FONT, 10),
            padx=18, pady=11, wraplength=460, justify="left",
        )
        self.label.pack()
        self.win.update_idletasks()
        width = self.win.winfo_reqwidth()
        height = self.win.winfo_reqheight()
        vx, vy, vw, vh = virtual_screen_rect()
        if anchor:
            x = anchor[0] + anchor[2] + 14
            y = anchor[1] + anchor[3] + 14
        else:
            x = vx + (vw - width) // 2
            y = vy + int(vh * 0.78)
        x = min(max(x, vx + 8), vx + vw - width - 8)
        y = min(max(y, vy + 8), vy + vh - height - 8)
        self.win.geometry(f"+{int(x)}+{int(y)}")
        if timeout:
            self.win.after(timeout, self.close)

    def set_text(self, text: str) -> None:
        try:
            self.label.configure(text=text)
            self.win.update_idletasks()
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass


def show_error_toast(root: tk.Tk, message: str, anchor=None,
                     timeout: int = 4500) -> None:
    BusyToast(root, message, anchor=anchor, timeout=timeout, error=True)


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: dict, on_save):
        self.cfg = copy.deepcopy(cfg)
        self.on_save = on_save
        self.win = tk.Toplevel(root)
        self.win.title("屏幕翻译 - 设置")
        self.win.configure(bg=BG)
        try:
            self.win.iconbitmap(os.path.join(ASSET_DIR, "icon.ico"))
        except tk.TclError:
            pass
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda event: self.close())

        outer = tk.Frame(self.win, bg=BG, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        self._section(outer, "翻译")
        self.target_combo = self._combo(
            outer, "目标语言",
            [name for name, _ in TARGET_OPTIONS],
            _code_to_display(cfg.get("target_lang", "zh-CN"),
                             TARGET_OPTIONS, "简体中文"),
        )
        self.provider_combo = self._combo(
            outer, "翻译引擎",
            [name for name, _ in PROVIDER_OPTIONS],
            _code_to_display(cfg.get("provider", "google"),
                             PROVIDER_OPTIONS, PROVIDER_OPTIONS[0][0]),
        )

        self._section(outer, "AI 大模型（仅当翻译引擎选「AI 大模型」时使用）")
        llm = cfg.get("llm", {})
        self.base_entry = self._entry(outer, "接口地址", llm.get("base_url", ""))
        self.key_entry = self._entry(outer, "API Key", llm.get("api_key", ""), show="•")
        self.model_entry = self._entry(outer, "模型名称", llm.get("model", ""))
        hint = tk.Label(
            outer,
            text="适用于 DeepSeek、OpenAI、Kimi、通义等 OpenAI 兼容接口。",
            bg=BG, fg=MUTED, font=(FONT, 8),
        )
        hint.pack(anchor="w", pady=(2, 0))

        self._section(outer, "快捷键")
        hotkeys = cfg.get("hotkeys", {})
        self.hk_region = self._entry(outer, "选区翻译", hotkeys.get("region", "ctrl+alt+t"))
        self.hk_full = self._entry(outer, "全屏翻译", hotkeys.get("fullscreen", "ctrl+alt+f"))
        self.hk_clip = self._entry(outer, "剪贴板翻译", hotkeys.get("clipboard", "ctrl+alt+c"))
        hint2 = tk.Label(
            outer,
            text="写法示例：ctrl+alt+t。保存后立即生效。",
            bg=BG, fg=MUTED, font=(FONT, 8),
        )
        hint2.pack(anchor="w", pady=(2, 0))

        self.error_label = tk.Label(
            outer, text="", bg=BG, fg="#b91c1c", font=(FONT, 9),
            wraplength=500, justify="left",
        )
        self.error_label.pack(anchor="w", pady=(10, 0))

        buttons = tk.Frame(outer, bg=BG)
        buttons.pack(fill="x", pady=(10, 0))
        tk.Button(
            buttons, text="取消", command=self.close, bg="#e5e7eb", fg=INK,
            activebackground="#d1d5db", relief="flat", borderwidth=0,
            padx=18, pady=7, font=(FONT, 9), cursor="hand2",
        ).pack(side="right")
        tk.Button(
            buttons, text="保存", command=self.save, bg=BLUE, fg="white",
            activebackground=BLUE_DARK, activeforeground="white",
            relief="flat", borderwidth=0, padx=22, pady=7,
            font=(FONT, 9), cursor="hand2",
        ).pack(side="right", padx=(0, 8))

        self.win.update_idletasks()
        width = max(560, self.win.winfo_reqwidth())
        height = self.win.winfo_reqheight()
        vx, vy, vw, vh = virtual_screen_rect()
        x = vx + (vw - width) // 2
        y = vy + (vh - height) // 2
        self.win.geometry(f"{width}x{height}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        try:
            self.win.attributes("-topmost", True)
            self.win.after(400, self._unpin)
        except tk.TclError:
            pass

    def _unpin(self) -> None:
        try:
            if self.win.winfo_exists():
                self.win.attributes("-topmost", False)
        except tk.TclError:
            pass

    @staticmethod
    def _section(parent, text: str) -> None:
        tk.Label(
            parent, text=text, bg=BG, fg=BLUE, font=(FONT, 10, "bold"),
        ).pack(anchor="w", pady=(12, 6))

    @staticmethod
    def _row(parent) -> tk.Frame:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        return row

    @staticmethod
    def _label(row, text: str) -> None:
        tk.Label(
            row, text=text, width=10, anchor="w", bg=BG, fg=INK,
            font=(FONT, 9),
        ).pack(side="left")

    def _combo(self, parent, label: str, values, current: str) -> ttk.Combobox:
        row = self._row(parent)
        self._label(row, label)
        combo = ttk.Combobox(row, values=values, state="readonly",
                             font=(FONT, 9))
        combo.set(current)
        combo.pack(side="left", fill="x", expand=True)
        return combo

    def _entry(self, parent, label: str, value: str, show: str | None = None) -> tk.Entry:
        row = self._row(parent)
        self._label(row, label)
        entry = tk.Entry(
            row, relief="solid", borderwidth=1, highlightthickness=0,
            bg="white", fg=INK, font=(FONT, 9), insertbackground=INK,
        )
        if show:
            entry.configure(show=show)
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        return entry

    def save(self) -> None:
        cfg = copy.deepcopy(self.cfg)
        cfg["target_lang"] = _display_to_code(
            self.target_combo.get(), TARGET_OPTIONS, "zh-CN"
        )
        cfg["provider"] = _display_to_code(
            self.provider_combo.get(), PROVIDER_OPTIONS, "google"
        )
        cfg["llm"] = {
            "base_url": self.base_entry.get().strip(),
            "api_key": self.key_entry.get().strip(),
            "model": self.model_entry.get().strip(),
        }
        cfg["hotkeys"] = {
            "region": self.hk_region.get().strip(),
            "fullscreen": self.hk_full.get().strip(),
            "clipboard": self.hk_clip.get().strip(),
        }
        if not all(cfg["hotkeys"].values()):
            self.error_label.configure(text="快捷键不能留空。")
            return
        error = self.on_save(cfg)
        if error:
            self.error_label.configure(text=error)
            return
        self.close()

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
