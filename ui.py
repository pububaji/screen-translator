# -*- coding: utf-8 -*-
"""界面：翻译结果窗口、悬浮提示、设置窗口（Windows 11 / Fluent 风格）。"""
from __future__ import annotations

import copy
import ctypes
import os
import tkinter as tk
from tkinter import ttk

try:
    import sv_ttk
except ImportError:  # pragma: no cover - 没装主题库时退回 Tk 默认外观
    sv_ttk = None

from capture import virtual_screen_rect
from config import ASSET_DIR
from translate import language_label

FONT = "Microsoft YaHei UI"
UI_FONT = (FONT, 10)
SMALL_FONT = (FONT, 9)
HEADER_FONT = (FONT, 15, "bold")

LIGHT = {
    "window": "#fafafa",
    "surface": "#ffffff",
    "surface_alt": "#f3f3f3",
    "text": "#1c1c1c",
    "muted": "#5c5c5c",
    "border": "#e5e5e5",
    "accent": "#005fb8",
    "success": "#0f7b0f",
    "error": "#c42b1c",
    "sel_bg": "#2f60d8",
    "sel_fg": "#ffffff",
    "toast_bg": "#2b2b2b",
    "toast_fg": "#ffffff",
    "pill_bg": "#1f1f1f",
    "pill_fg": "#f3f3f3",
    "selection": "#4cc2ff",
}

DARK = {
    "window": "#1c1c1c",
    "surface": "#2b2b2b",
    "surface_alt": "#252525",
    "text": "#fafafa",
    "muted": "#a0a0a0",
    "border": "#3a3a3a",
    "accent": "#57c8ff",
    "success": "#6ccb5f",
    "error": "#ff99a4",
    "sel_bg": "#2f60d8",
    "sel_fg": "#ffffff",
    "toast_bg": "#2b2b2b",
    "toast_fg": "#ffffff",
    "pill_bg": "#000000",
    "pill_fg": "#f3f3f3",
    "selection": "#4cc2ff",
}

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


def system_theme() -> str:
    """读取 Windows 的“应用模式”设置。"""
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if int(value) else "dark"
    except (OSError, ValueError):
        return "light"


def get_palette() -> dict:
    theme = "light"
    if sv_ttk is not None:
        try:
            theme = sv_ttk.get_theme()
        except Exception:
            pass
    return DARK if theme == "dark" else LIGHT


def init_theme(root: tk.Tk) -> str:
    """应用 Windows 11 风格的 ttk 主题与字体。需在创建窗口前调用。"""
    theme = system_theme()
    if sv_ttk is not None:
        sv_ttk.set_theme(theme, root)
    style = ttk.Style(root)
    style.configure("TButton", font=UI_FONT, padding=(14, 5))
    style.configure("Accent.TButton", font=UI_FONT, padding=(16, 5))
    style.configure("TEntry", font=UI_FONT)
    style.configure("TCombobox", font=UI_FONT)
    style.configure("TLabel", font=UI_FONT)

    palette = get_palette()
    root.option_add("*TCombobox*Listbox.font", UI_FONT)
    root.option_add("*TCombobox*Listbox.background", palette["surface"])
    root.option_add("*TCombobox*Listbox.foreground", palette["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", palette["sel_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", palette["sel_fg"])
    return theme


def _apply_titlebar_theme(window: tk.Toplevel) -> None:
    """深色模式下把系统标题栏也变暗，避免白色标题栏突兀。"""
    if get_palette() is not DARK:
        return
    try:
        window.update_idletasks()
        hwnd = int(window.frame(), 16)
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


def _round_window(window: tk.Toplevel, radius: int = 10) -> None:
    """给无边框窗口加圆角（托盘气泡用）。"""
    try:
        window.update_idletasks()
        hwnd = int(window.frame(), 16)
        width = max(1, window.winfo_width())
        height = max(1, window.winfo_height())
        region = ctypes.windll.gdi32.CreateRoundRectRgn(
            0, 0, width + 1, height + 1, radius * 2, radius * 2
        )
        ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
    except Exception:
        pass


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

        p = get_palette()
        win = tk.Toplevel(self.root)
        win.title("屏幕翻译")
        win.configure(bg=p["window"])
        try:
            win.iconbitmap(os.path.join(ASSET_DIR, "icon.ico"))
        except tk.TclError:
            pass
        win.minsize(520, 420)
        win.protocol("WM_DELETE_WINDOW", self.hide)
        win.bind("<Escape>", lambda event: self.hide())

        outer = tk.Frame(win, bg=p["window"], padx=20, pady=16)
        outer.pack(fill="both", expand=True)

        head = tk.Frame(outer, bg=p["window"])
        head.pack(fill="x")
        self.lang_label = tk.Label(
            head, text="", bg=p["window"], fg=p["text"],
            font=HEADER_FONT, anchor="w",
        )
        self.lang_label.pack(side="left")
        self.provider_label = tk.Label(
            head, text="", bg=p["window"], fg=p["muted"], font=SMALL_FONT,
        )
        self.provider_label.pack(side="right")

        tk.Frame(outer, bg=p["border"], height=1).pack(fill="x", pady=(12, 14))

        self._section(outer, "原文", p)
        self.original = tk.Text(
            outer, height=6, wrap="word", relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=p["border"],
            highlightcolor=p["border"], bg=p["surface_alt"], fg=p["text"],
            selectbackground=p["sel_bg"], selectforeground=p["sel_fg"],
            insertbackground=p["text"], font=UI_FONT,
            padx=12, pady=9, spacing1=1, spacing3=2,
        )
        self.original.pack(fill="x")

        self._section(outer, "译文", p, top=14)

        footer = tk.Frame(outer, bg=p["window"])
        footer.pack(side="bottom", fill="x", pady=(14, 0))

        text_frame = tk.Frame(outer, bg=p["window"])
        text_frame.pack(fill="both", expand=True)
        self.translation = tk.Text(
            text_frame, height=10, wrap="word", relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=p["border"],
            highlightcolor=p["border"], bg=p["surface"], fg=p["text"],
            selectbackground=p["sel_bg"], selectforeground=p["sel_fg"],
            insertbackground=p["text"], font=(FONT, 11),
            padx=12, pady=10, spacing1=1, spacing3=2,
        )
        scrollbar = ttk.Scrollbar(
            text_frame, orient="vertical", command=self.translation.yview
        )
        self.translation.configure(yscrollcommand=scrollbar.set)
        self.translation.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.status = tk.Label(
            footer, text="", bg=p["window"], fg=p["success"], font=SMALL_FONT,
        )
        self.status.pack(side="left")
        self.copy_btn = ttk.Button(
            footer, text="复制译文", style="Accent.TButton", command=self.copy,
        )
        self.copy_btn.pack(side="right")
        ttk.Button(footer, text="关闭", command=self.hide).pack(
            side="right", padx=(0, 8)
        )

        self.win = win
        _apply_titlebar_theme(win)

    @staticmethod
    def _section(parent, text: str, p: dict, top: int = 0) -> None:
        tk.Label(
            parent, text=text, bg=p["window"], fg=p["muted"],
            font=SMALL_FONT,
        ).pack(anchor="w", pady=(top, 5))

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
        width = min(720, max(520, vw - 40))
        height = min(660, max(420, vh - 80))
        x, y = self._position(anchor, width, height)
        self.win.geometry(f"{width}x{height}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        _apply_titlebar_theme(self.win)
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
        self.status.configure(text="已复制到剪贴板")
        self.copy_btn.configure(text="已复制")
        if self.win is not None:
            self.win.after(1600, self._reset_copy)

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
        p = get_palette()
        bg = p["error"] if error else p["toast_bg"]
        fg = "#ffffff" if error else p["toast_fg"]
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=bg)
        frame = tk.Frame(self.win, bg=bg)
        frame.pack()
        self.label = tk.Label(
            frame, text=text, bg=bg, fg=fg, font=UI_FONT,
            padx=18, pady=10, wraplength=460, justify="left",
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
        _round_window(self.win, 10)
        if timeout:
            self.win.after(timeout, self.close)

    def set_text(self, text: str) -> None:
        try:
            self.label.configure(text=text)
            self.win.update_idletasks()
            _round_window(self.win, 10)
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
        p = get_palette()

        self.win = tk.Toplevel(root)
        self.win.title("屏幕翻译 - 设置")
        self.win.configure(bg=p["window"])
        try:
            self.win.iconbitmap(os.path.join(ASSET_DIR, "icon.ico"))
        except tk.TclError:
            pass
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda event: self.close())

        outer = tk.Frame(self.win, bg=p["window"], padx=26, pady=20)
        outer.pack(fill="both", expand=True)

        self._section(outer, "翻译", p, first=True)
        self.target_combo = self._combo(
            outer, "目标语言", [name for name, _ in TARGET_OPTIONS],
            _code_to_display(cfg.get("target_lang", "zh-CN"),
                             TARGET_OPTIONS, "简体中文"), p,
        )
        self.provider_combo = self._combo(
            outer, "翻译引擎", [name for name, _ in PROVIDER_OPTIONS],
            _code_to_display(cfg.get("provider", "google"),
                             PROVIDER_OPTIONS, PROVIDER_OPTIONS[0][0]), p,
        )
        tk.Label(
            outer,
            text="Google 接口为非官方接口，可能限流或失效；建议改用 AI 大模型。",
            bg=p["window"], fg=p["muted"], font=(FONT, 8),
            wraplength=520, justify="left",
        ).pack(anchor="w", pady=(2, 0))

        self._section(outer, "AI 大模型", p)
        tk.Label(
            outer, text="仅当翻译引擎选择「AI 大模型」时使用",
            bg=p["window"], fg=p["muted"], font=(FONT, 8),
        ).pack(anchor="w", pady=(0, 4))
        llm = cfg.get("llm", {})
        self.base_entry = self._entry(outer, "接口地址", llm.get("base_url", ""), p)
        self.key_entry = self._entry(outer, "API Key", llm.get("api_key", ""), p, show="•")
        self.model_entry = self._entry(outer, "模型名称", llm.get("model", ""), p)
        tk.Label(
            outer,
            text="适用于 DeepSeek、OpenAI、Kimi、通义等 OpenAI 兼容接口。",
            bg=p["window"], fg=p["muted"], font=(FONT, 8),
        ).pack(anchor="w", pady=(2, 0))

        self._section(outer, "快捷键", p)
        hotkeys = cfg.get("hotkeys", {})
        self.hk_region = self._entry(outer, "选区翻译", hotkeys.get("region", "ctrl+alt+t"), p)
        self.hk_full = self._entry(outer, "全屏翻译", hotkeys.get("fullscreen", "ctrl+alt+f"), p)
        self.hk_clip = self._entry(outer, "剪贴板翻译", hotkeys.get("clipboard", "ctrl+alt+c"), p)
        tk.Label(
            outer, text="写法示例：ctrl+alt+t。保存后立即生效。",
            bg=p["window"], fg=p["muted"], font=(FONT, 8),
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            outer,
            text="界面会跟随 Windows 的浅色 / 深色模式（重启程序后生效）。",
            bg=p["window"], fg=p["muted"], font=(FONT, 8),
        ).pack(anchor="w", pady=(10, 0))

        self.error_label = tk.Label(
            outer, text="", bg=p["window"], fg=p["error"], font=(FONT, 9),
            wraplength=520, justify="left",
        )
        self.error_label.pack(anchor="w", pady=(10, 0))

        buttons = tk.Frame(outer, bg=p["window"])
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="保存", style="Accent.TButton",
                   command=self.save).pack(side="right")
        ttk.Button(buttons, text="取消", command=self.close).pack(
            side="right", padx=(0, 8)
        )

        self.win.update_idletasks()
        width = max(600, self.win.winfo_reqwidth())
        height = self.win.winfo_reqheight()
        vx, vy, vw, vh = virtual_screen_rect()
        height = min(height, vh - 80)
        x = vx + (vw - width) // 2
        y = vy + (vh - height) // 2
        self.win.geometry(f"{width}x{height}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        _apply_titlebar_theme(self.win)
        try:
            self.win.attributes("-topmost", True)
            self.win.after(400, self._unpin)
        except tk.TclError:
            pass

    @staticmethod
    def _section(parent, text: str, p: dict, first: bool = False) -> None:
        tk.Label(
            parent, text=text, bg=p["window"], fg=p["text"],
            font=(FONT, 10, "bold"),
        ).pack(anchor="w", pady=((0 if first else 14), 6))

    @staticmethod
    def _row(parent, p: dict) -> tk.Frame:
        row = tk.Frame(parent, bg=p["window"])
        row.pack(fill="x", pady=4)
        return row

    def _combo(self, parent, label: str, values, current: str, p: dict) -> ttk.Combobox:
        row = self._row(parent, p)
        tk.Label(
            row, text=label, width=10, anchor="w",
            bg=p["window"], fg=p["muted"], font=UI_FONT,
        ).pack(side="left")
        combo = ttk.Combobox(row, values=values, state="readonly")
        combo.set(current)
        combo.pack(side="left", fill="x", expand=True)
        return combo

    def _entry(self, parent, label: str, value: str, p: dict,
               show: str | None = None) -> ttk.Entry:
        row = self._row(parent, p)
        tk.Label(
            row, text=label, width=10, anchor="w",
            bg=p["window"], fg=p["muted"], font=UI_FONT,
        ).pack(side="left")
        entry = ttk.Entry(row)
        if show:
            entry.configure(show=show)
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def _unpin(self) -> None:
        try:
            if self.win.winfo_exists():
                self.win.attributes("-topmost", False)
        except tk.TclError:
            pass

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
