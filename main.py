# -*- coding: utf-8 -*-
"""屏幕翻译 —— 框选屏幕上的外文，本地 OCR + 在线翻译。

快捷键（可在设置里修改）：
    Ctrl+Alt+T  选区翻译
    Ctrl+Alt+F  全屏翻译
    Ctrl+Alt+C  剪贴板翻译
"""
from __future__ import annotations

import ctypes
import logging
import logging.handlers
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox


def _enable_dpi_awareness() -> None:
    """必须在创建任何窗口之前调用，保证截图坐标与 Tk 坐标一致。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_enable_dpi_awareness()

import keyboard  # noqa: E402
import pystray  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from capture import RegionSelector, grab_virtual_screen  # noqa: E402
from config import APP_DIR, load_config, save_config  # noqa: E402
from ocr_engine import OcrEngine  # noqa: E402
from translate import TranslateError, get_translator  # noqa: E402
from ui import BusyToast, ResultWindow, SettingsWindow, show_error_toast  # noqa: E402

log = logging.getLogger("screen_translator")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "ScreenTranslator"


# ---------------------------------------------------------------- 开机自启

def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.join(APP_DIR, "main.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{exe}" "{script}"'


def is_startup_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_REG_NAME)
        return bool(value)
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_REG_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- 日志

def setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(APP_DIR, "app.log"),
        maxBytes=1_000_000, backupCount=2, encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


# ---------------------------------------------------------------- 单实例

def acquire_single_instance():
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "Local\\ScreenTranslator_Instance")
    if not handle:
        return None
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


# ---------------------------------------------------------------- 托盘图标

def make_icon() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 61, 61), radius=14, fill=(37, 99, 235, 255))
    font = None
    for path in (
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
    ):
        try:
            font = ImageFont.truetype(path, 38)
            break
        except OSError:
            continue
    if font is not None:
        draw.text((32, 33), "译", font=font, fill="white", anchor="mm")
    return image


# ---------------------------------------------------------------- 主程序

class ScreenTranslatorApp:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("屏幕翻译")
        self.root.report_callback_exception = self._on_tk_exception
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
            self.root.tk.call("tk", "scaling", max(1.0, dpi / 72.0))
        except Exception:
            pass

        self.queue: queue.Queue = queue.Queue()
        self.ocr = OcrEngine()
        self.result = ResultWindow(self.root)
        self.settings_window: SettingsWindow | None = None
        self.selector: RegionSelector | None = None
        self.toast: BusyToast | None = None
        self.busy = False
        self.running = True
        self._last_anchor = None
        self._last_hotkey = 0.0
        self._hotkeys: dict[str, object] = {}
        self._hotkey_error = ""
        self.tray = None

        self._register_hotkeys()
        self._start_tray()
        threading.Thread(target=self._preload_ocr, daemon=True).start()

        self.root.after(80, self._poll_queue)
        if self._hotkey_error:
            self.root.after(
                700,
                lambda: show_error_toast(
                    self.root, self._hotkey_error, timeout=7000
                ),
            )

    # ---------- 启动 / 关闭 ----------

    def run(self) -> None:
        self.root.mainloop()

    def shutdown(self) -> None:
        if not self.running:
            return
        self.running = False
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            if self.tray is not None:
                self.tray.stop()
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _preload_ocr(self) -> None:
        try:
            start = time.time()
            self.ocr.warmup()
            log.info("OCR 模型预加载完成，用时 %.1fs", time.time() - start)
        except Exception:
            log.exception("OCR 模型预加载失败")

    def _on_tk_exception(self, exc_type, exc_value, tb) -> None:
        log.error("界面回调异常", exc_info=(exc_type, exc_value, tb))

    # ---------- 快捷键 ----------

    def _register_hotkeys(self, cfg: dict | None = None) -> None:
        cfg = cfg or self.cfg
        hotkeys = cfg.get("hotkeys", {})
        combos = {
            "region": (hotkeys.get("region") or "").strip(),
            "fullscreen": (hotkeys.get("fullscreen") or "").strip(),
            "clipboard": (hotkeys.get("clipboard") or "").strip(),
        }
        if not all(combos.values()):
            raise ValueError("快捷键不能留空。")
        if len(set(combos.values())) != len(combos):
            raise ValueError("三个功能的快捷键不能相同。")

        for handle in self._hotkeys.values():
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._hotkeys.clear()

        try:
            for action, combo in combos.items():
                self._hotkeys[action] = keyboard.add_hotkey(
                    combo, self._on_hotkey, args=(action,), suppress=True
                )
        except Exception:
            for handle in self._hotkeys.values():
                try:
                    keyboard.remove_hotkey(handle)
                except Exception:
                    pass
            self._hotkeys.clear()
            raise

    def _on_hotkey(self, action: str) -> None:
        now = time.monotonic()
        if now - self._last_hotkey < 0.35:
            return
        self._last_hotkey = now
        self.queue.put(("action", action))

    def apply_settings(self, cfg: dict) -> str | None:
        old_cfg = self.cfg
        try:
            self._register_hotkeys(cfg)
        except Exception as exc:
            try:
                self._register_hotkeys(old_cfg)
            except Exception:
                log.exception("恢复旧快捷键失败")
            return f"快捷键不可用：{exc}"
        self.cfg = cfg
        try:
            save_config(cfg)
        except OSError as exc:
            log.exception("保存配置失败")
            return f"设置已应用，但写入 config.json 失败：{exc}"
        return None

    # ---------- 托盘 ----------

    def _start_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem(
                lambda item: f"选区翻译    {self.cfg['hotkeys'].get('region', '')}",
                self._tray_action_region, default=True,
            ),
            pystray.MenuItem(
                lambda item: f"全屏翻译    {self.cfg['hotkeys'].get('fullscreen', '')}",
                self._tray_action_fullscreen,
            ),
            pystray.MenuItem(
                lambda item: f"剪贴板翻译    {self.cfg['hotkeys'].get('clipboard', '')}",
                self._tray_action_clipboard,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("设置…", self._tray_action_settings),
            pystray.MenuItem(
                "开机自动启动", self._tray_toggle_startup,
                checked=lambda item: is_startup_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._tray_action_quit),
        )
        self.tray = pystray.Icon(
            "ScreenTranslator", make_icon(),
            "屏幕翻译（Ctrl+Alt+T 选区翻译）", menu,
        )
        threading.Thread(target=self._run_tray, daemon=True).start()

    def _run_tray(self) -> None:
        try:
            self.tray.run()
        except Exception:
            log.exception("托盘图标运行异常")

    def _tray_action_region(self, icon=None, item=None) -> None:
        self.queue.put(("action", "region"))

    def _tray_action_fullscreen(self, icon=None, item=None) -> None:
        self.queue.put(("action", "fullscreen"))

    def _tray_action_clipboard(self, icon=None, item=None) -> None:
        self.queue.put(("action", "clipboard"))

    def _tray_action_settings(self, icon=None, item=None) -> None:
        self.queue.put(("action", "settings"))

    def _tray_action_quit(self, icon=None, item=None) -> None:
        self.queue.put(("action", "quit"))

    def _tray_toggle_startup(self, icon=None, item=None) -> None:
        try:
            enable = not is_startup_enabled()
            set_startup_enabled(enable)
            if icon is not None:
                icon.update_menu()
        except Exception:
            log.exception("切换开机自启失败")

    # ---------- 消息循环 ----------

    def _poll_queue(self) -> None:
        if not self.running:
            return
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "action":
                    self._handle_action(payload)
                elif kind == "status":
                    if self.toast is not None:
                        self.toast.set_text(payload)
                elif kind == "done":
                    self._finish(payload)
                elif kind == "error":
                    self._fail(payload)
        except queue.Empty:
            pass
        except Exception:
            log.exception("处理消息失败")
        if self.running:
            self.root.after(80, self._poll_queue)

    def _handle_action(self, action: str) -> None:
        if action == "region":
            self.start_region()
        elif action == "fullscreen":
            self.start_fullscreen()
        elif action == "clipboard":
            self.start_clipboard()
        elif action == "settings":
            self.open_settings()
        elif action == "quit":
            self.shutdown()

    # ---------- 三种入口 ----------

    def start_region(self) -> None:
        if self.busy or self.selector is not None:
            return
        try:
            screenshot, rect = grab_virtual_screen()
        except Exception as exc:
            log.exception("截屏失败")
            show_error_toast(self.root, f"截屏失败：{exc}")
            return
        try:
            self.selector = RegionSelector(
                self.root, screenshot, rect, self._on_region_done
            )
        except Exception as exc:
            log.exception("打开选区界面失败")
            self.selector = None
            show_error_toast(self.root, f"打开选区界面失败：{exc}")

    def _on_region_done(self, result) -> None:
        self.selector = None
        if not result:
            return
        crop, screen_rect = result
        self.begin_ocr(crop, screen_rect)

    def start_fullscreen(self) -> None:
        if self.busy or self.selector is not None:
            return
        try:
            screenshot, rect = grab_virtual_screen()
        except Exception as exc:
            log.exception("截屏失败")
            show_error_toast(self.root, f"截屏失败：{exc}")
            return
        anchor = (rect[0] + rect[2] // 2, rect[1] + rect[3] // 2, 0, 0)
        self.begin_ocr(screenshot, anchor)

    def start_clipboard(self) -> None:
        if self.busy:
            return
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            show_error_toast(self.root, "剪贴板里没有文字。")
            return
        self.busy = True
        self._show_busy("正在翻译…", None)
        threading.Thread(
            target=self._clipboard_worker, args=(text,), daemon=True
        ).start()

    # ---------- 处理线程 ----------

    def begin_ocr(self, image, anchor) -> None:
        if self.busy:
            return
        self.busy = True
        self._show_busy("正在识别文字…", anchor)
        threading.Thread(
            target=self._ocr_worker, args=(image, anchor), daemon=True
        ).start()

    def _ocr_worker(self, image, anchor) -> None:
        try:
            text = self.ocr.recognize(image)
            if not text.strip():
                self.queue.put((
                    "error",
                    "没有识别到文字。请重新框选，尽量框住完整文字并留一点边距。",
                ))
                return
            self.queue.put(("status", "正在翻译…"))
            self._translate_and_post(text, anchor)
        except TranslateError as exc:
            self.queue.put(("error", str(exc)))
        except Exception as exc:
            log.exception("识别失败")
            self.queue.put(("error", f"识别失败：{exc}"))

    def _clipboard_worker(self, text: str) -> None:
        try:
            self.queue.put(("status", "正在翻译…"))
            self._translate_and_post(text, None)
        except TranslateError as exc:
            self.queue.put(("error", str(exc)))
        except Exception as exc:
            log.exception("翻译失败")
            self.queue.put(("error", f"翻译失败：{exc}"))

    def _translate_and_post(self, text: str, anchor) -> None:
        cfg = self.cfg
        translator = get_translator(cfg)
        result = translator.translate(
            text, cfg.get("target_lang", "zh-CN"), cfg.get("source_lang", "auto")
        )
        self.queue.put(("done", {
            "original": text,
            "translation": result.text,
            "target": cfg.get("target_lang", "zh-CN"),
            "detected": result.detected,
            "provider": result.provider,
            "anchor": anchor,
        }))

    # ---------- 界面反馈 ----------

    def _show_busy(self, text: str, anchor) -> None:
        self._close_toast()
        self._last_anchor = anchor
        self.toast = BusyToast(self.root, text, anchor=anchor)

    def _close_toast(self) -> None:
        if self.toast is not None:
            self.toast.close()
            self.toast = None

    def _finish(self, payload: dict) -> None:
        self.busy = False
        self._close_toast()
        self.result.show(
            payload["original"], payload["translation"], payload["target"],
            payload.get("detected", ""), payload.get("provider", ""),
            payload.get("anchor"),
        )

    def _fail(self, message: str) -> None:
        self.busy = False
        self._close_toast()
        show_error_toast(self.root, message, anchor=self._last_anchor)

    def open_settings(self) -> None:
        if self.settings_window is not None:
            try:
                if self.settings_window.win.winfo_exists():
                    self.settings_window.win.deiconify()
                    self.settings_window.win.lift()
                    return
            except tk.TclError:
                pass
        self.settings_window = SettingsWindow(
            self.root, self.cfg, self.apply_settings
        )


def main() -> int:
    setup_logging()
    if acquire_single_instance() is None:
        ctypes.windll.user32.MessageBoxW(
            0,
            "屏幕翻译已经在运行了。\n请查看系统托盘（任务栏右下角）里的“译”图标。",
            "屏幕翻译", 0x40,
        )
        return 0
    try:
        ScreenTranslatorApp().run()
    except Exception:
        log.exception("程序启动失败")
        ctypes.windll.user32.MessageBoxW(
            0, "屏幕翻译启动失败，详情见 D:\\Apps\\ScreenTranslator\\app.log。",
            "屏幕翻译", 0x10,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
