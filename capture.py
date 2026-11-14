# -*- coding: utf-8 -*-
"""截屏与屏幕区域选择。"""
from __future__ import annotations

import ctypes
import logging
import tkinter as tk

import keyboard
import mss
from PIL import Image, ImageEnhance, ImageTk

log = logging.getLogger(__name__)

HINT_TEXT = "拖动鼠标框选要翻译的文字    Esc / 右键取消"

ACCENT = "#4cc2ff"
PILL_BG = "#1f1f1f"
PILL_FG = "#f3f3f3"


def _round_rect_points(left: float, top: float, right: float,
                       bottom: float, radius: float) -> tuple[float, ...]:
    radius = max(0.0, min(radius, (right - left) / 2, (bottom - top) / 2))
    r = radius
    return (
        left + r, top, right - r, top,
        right, top, right, top + r,
        right, bottom - r, right, bottom,
        right - r, bottom, left + r, bottom,
        left, bottom, left, bottom - r,
        left, top + r, left, top,
    )


def virtual_screen_rect() -> tuple[int, int, int, int]:
    """整个虚拟桌面（含多显示器）的屏幕坐标。"""
    user32 = ctypes.windll.user32
    return (
        int(user32.GetSystemMetrics(76)),  # SM_XVIRTUALSCREEN
        int(user32.GetSystemMetrics(77)),  # SM_YVIRTUALSCREEN
        int(user32.GetSystemMetrics(78)),  # SM_CXVIRTUALSCREEN
        int(user32.GetSystemMetrics(79)),  # SM_CYVIRTUALSCREEN
    )


def grab_virtual_screen() -> tuple[Image.Image, tuple[int, int, int, int]]:
    """截取整个虚拟桌面，返回 (PIL 图像, 屏幕坐标矩形)。"""
    with mss.MSS() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    rect = (
        int(monitor["left"]),
        int(monitor["top"]),
        int(monitor["width"]),
        int(monitor["height"]),
    )
    return image, rect


class RegionSelector:
    """全屏半透明遮罩，拖动框选一块区域。

    完成后回调 on_done((PIL裁剪图, 屏幕坐标矩形))；取消时回调 on_done(None)。
    """

    def __init__(self, root: tk.Tk, screenshot: Image.Image,
                 rect: tuple[int, int, int, int], on_done):
        self.root = root
        self.screenshot = screenshot
        self.rect = rect
        self.on_done = on_done
        self._start: tuple[int, int] | None = None
        self._done = False
        self._cancel_requested = False
        self._esc_handle = None
        self._check_timer = None

        x, y, width, height = rect
        self.width = self.screenshot.width
        self.height = self.screenshot.height
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{width}x{height}{x:+d}{y:+d}")

        self.canvas = tk.Canvas(
            self.win, highlightthickness=0, borderwidth=0,
            cursor="crosshair", bg="black",
        )
        self.canvas.pack(fill="both", expand=True)

        # 整屏压暗的截图做背景：比 Tk 的网点填充干净得多
        dark = ImageEnhance.Brightness(screenshot).enhance(0.42)
        self.photo = ImageTk.PhotoImage(dark)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

        self.hint_text = self.canvas.create_text(
            width // 2, 24, anchor="n", text=HINT_TEXT,
            fill=PILL_FG, font=("Microsoft YaHei UI", 10),
        )
        self.hint_bg = self.canvas.create_polygon(
            0, 0, 0, 0, smooth=True, splinesteps=12,
            fill=PILL_BG, outline="", tags="hint_bg",
        )
        self.canvas.tag_lower(self.hint_bg, self.hint_text)
        self._fit_hint_bg()

        self.sel_id = self.canvas.create_rectangle(
            0, 0, 0, 0, outline=ACCENT, width=2, state="hidden",
        )
        self.size_text = self.canvas.create_text(
            0, 0, anchor="nw", text="", fill=PILL_FG,
            font=("Microsoft YaHei UI", 9), state="hidden",
        )
        self.size_bg = self.canvas.create_polygon(
            0, 0, 0, 0, smooth=True, splinesteps=12,
            fill=PILL_BG, outline="", state="hidden",
        )
        self.canvas.tag_lower(self.size_bg, self.size_text)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-3>", lambda event: self._request_cancel())
        self.win.bind("<Escape>", lambda event: self._request_cancel())
        self.win.bind("<ButtonPress-3>", lambda event: self._request_cancel())
        self.win.after(30, self._activate)

    # ---------- 初始化 / 取消 ----------

    def _activate(self) -> None:
        if self._done:
            return
        try:
            self.win.focus_force()
            self.win.grab_set()
        except tk.TclError:
            return
        try:
            self._esc_handle = keyboard.add_hotkey(
                "esc", self._request_cancel, suppress=False
            )
        except Exception:  # pragma: no cover
            log.exception("注册 Esc 取消快捷键失败")
        self._check_timer = self.win.after(60, self._poll_cancel)

    def _request_cancel(self) -> None:
        self._cancel_requested = True

    def _poll_cancel(self) -> None:
        if self._done:
            return
        if self._cancel_requested:
            self._finish(None)
            return
        try:
            self._check_timer = self.win.after(60, self._poll_cancel)
        except tk.TclError:
            pass

    # ---------- 绘制 ----------

    def _fit_hint_bg(self) -> None:
        bbox = self.canvas.bbox(self.hint_text)
        if bbox:
            left, top, right, bottom = bbox
            self.canvas.coords(
                self.hint_bg,
                *_round_rect_points(left - 12, top - 6, right + 12, bottom + 6, 9),
            )

    def _update_selection(self, left: int, top: int, right: int, bottom: int) -> None:
        self.canvas.coords(self.sel_id, left, top, right, bottom)
        self.canvas.itemconfigure(self.sel_id, state="normal")

        label = f"{right - left} × {bottom - top}"
        self.canvas.itemconfigure(self.size_text, text=label, state="normal")
        text_y = top + 4 if top < 30 else top - 24
        self.canvas.coords(self.size_text, left + 6, text_y)
        bbox = self.canvas.bbox(self.size_text)
        if bbox:
            l, t, r, b = bbox
            self.canvas.coords(
                self.size_bg, *_round_rect_points(l - 5, t - 2, r + 5, b + 2, 7)
            )
            self.canvas.itemconfigure(self.size_bg, state="normal")
        self.canvas.tag_raise(self.sel_id)
        self.canvas.tag_raise(self.size_bg)
        self.canvas.tag_raise(self.size_text)

    # ---------- 鼠标事件 ----------

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        return (
            max(0, min(self.width, int(x))),
            max(0, min(self.height, int(y))),
        )

    def _on_press(self, event) -> None:
        if self._done:
            return
        self._start = self._clamp(event.x, event.y)
        self.canvas.itemconfigure(self.hint_text, state="hidden")
        self.canvas.itemconfigure(self.hint_bg, state="hidden")

    def _on_drag(self, event) -> None:
        if self._done or self._start is None:
            return
        x, y = self._clamp(event.x, event.y)
        start_x, start_y = self._start
        left, right = sorted((start_x, x))
        top, bottom = sorted((start_y, y))
        self._update_selection(left, top, right, bottom)

    def _on_release(self, event) -> None:
        if self._done:
            return
        if self._start is None:
            return
        x, y = self._clamp(event.x, event.y)
        start_x, start_y = self._start
        left, right = sorted((start_x, x))
        top, bottom = sorted((start_y, y))
        if right - left < 6 or bottom - top < 6:
            self._finish(None)
            return
        crop = self.screenshot.crop((left, top, right, bottom))
        screen_rect = (self.rect[0] + left, self.rect[1] + top, right - left, bottom - top)
        self._finish((crop, screen_rect))

    # ---------- 结束 ----------

    def _finish(self, result) -> None:
        if self._done:
            return
        self._done = True
        if self._check_timer is not None:
            try:
                self.win.after_cancel(self._check_timer)
            except tk.TclError:
                pass
            self._check_timer = None
        if self._esc_handle is not None:
            try:
                keyboard.remove_hotkey(self._esc_handle)
            except Exception:
                pass
            self._esc_handle = None
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        callback = self.on_done
        self.on_done = lambda *_: None
        callback(result)
