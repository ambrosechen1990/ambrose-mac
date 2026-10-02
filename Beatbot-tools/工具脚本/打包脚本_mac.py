#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 Beatbot-tools 主程序打包为 macOS .app 客户端。"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "主程序" / "Beatbot.py"
SPEC = ROOT / "工具脚本" / "Beatbot软测工具.spec"
VENV = ROOT / ".venv_build"
DIST = ROOT / "dist"
APP_NAME = "Beatbot软测工具.app"


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> int:
    if platform.system() != "Darwin":
        print("仅支持在 macOS 上打包")
        return 1
    if not MAIN.exists():
        print(f"找不到主程序: {MAIN}")
        return 1

    if not VENV.exists():
        run([sys.executable, "-m", "venv", str(VENV)])
    py = VENV / "bin" / "python"
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(py), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"), "pyinstaller"])

    # 生成 / 更新 spec（动态加载的子工具必须以 data 打入）
    add_data = [
        f"{ROOT / '串口工具'}:串口工具",
        f"{ROOT / 'MCU工具'}:MCU工具",
        f"{ROOT / 'spjz'}:spjz",
        f"{ROOT / 'excel转换工具'}:excel转换工具",
        f"{ROOT / '主程序' / 'icons'}:icons",
        f"{ROOT / '图标'}:图标",
        f"{ROOT / '配置文件'}:配置文件",
        f"{ROOT / '主程序' / 'platform_compat.py'}:.",
    ]
    # Windows 用 ; Mac/Linux 用 :
    datas_arg = []
    for item in add_data:
        src, dst = item.split(":", 1)
        if Path(src).exists():
            datas_arg.extend(["--add-data", f"{src}:{dst}"])

    DIST.mkdir(exist_ok=True)
    cmd = [
        str(py), "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name", "Beatbot软测工具",
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build"),
        *datas_arg,
        "--hidden-import", "serial",
        "--hidden-import", "serial.tools.list_ports",
        "--hidden-import", "openpyxl",
        "--hidden-import", "pandas",
        "--hidden-import", "zstandard",
        "--hidden-import", "pytesseract",
        "--collect-all", "cv2",
        str(MAIN),
    ]
    run(cmd)

    app = DIST / APP_NAME
    if not app.exists():
        # onedir 时可能是 Beatbot软测工具/Beatbot软测工具 或 .app
        candidates = list(DIST.glob("*.app"))
        if candidates:
            app = candidates[0]
        else:
            print("未找到 .app，请检查 dist 目录")
            return 1

    if shutil.which("xattr"):
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(app)], check=False)

    print("\n打包完成:", app)
    print("双击即可打开客户端。")
    print("Excel/日志默认目录: ~/Documents/BeatbotDist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
