# -*- coding: utf-8 -*-
"""打包 Windows 免安装版。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe packaging\\build_exe.py [版本号]

需要先按 README 创建 .venv 并安装 requirements.txt，
打包工具 PyInstaller 会自动检查/安装。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = sys.argv[1] if len(sys.argv) > 1 else "1.0.0"
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
DIST = os.path.join(ROOT, "dist", "ScreenTranslator")
RELEASE = os.path.join(ROOT, "release")
ZIP_BASE = os.path.join(RELEASE, f"ScreenTranslator-v{VERSION}-win64")


def run(args: list[str]) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    if not os.path.exists(PYTHON):
        print(f"找不到 {PYTHON}\n请先按 README 创建 .venv 并安装 requirements.txt")
        return 1

    probe = subprocess.run(
        [PYTHON, "-m", "pip", "show", "pyinstaller"],
        cwd=ROOT, capture_output=True,
    )
    if probe.returncode != 0:
        run([PYTHON, "-m", "pip", "install", "pyinstaller"])

    if os.path.exists(os.path.join(ROOT, "build")):
        shutil.rmtree(os.path.join(ROOT, "build"))
    if os.path.exists(os.path.join(ROOT, "dist")):
        shutil.rmtree(os.path.join(ROOT, "dist"))

    run([
        PYTHON, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "ScreenTranslator",
        "--icon", os.path.join("assets", "icon.ico"),
        "--add-data", "assets;assets",
        "--collect-all", "rapidocr_onnxruntime",
        "--collect-all", "curl_cffi",
        "--collect-all", "sv_ttk",
        "main.py",
    ])

    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(os.path.join(ROOT, name), DIST)
    shutil.copy2(
        os.path.join(ROOT, "packaging", "使用说明.txt"),
        os.path.join(DIST, "使用说明.txt"),
    )
    for junk in ("config.json", "app.log"):
        path = os.path.join(DIST, junk)
        if os.path.exists(path):
            os.remove(path)

    os.makedirs(RELEASE, exist_ok=True)
    zip_path = ZIP_BASE + ".zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)
    shutil.make_archive(ZIP_BASE, "zip", root_dir=os.path.join(ROOT, "dist"))

    size = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\n构建完成: {zip_path}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
