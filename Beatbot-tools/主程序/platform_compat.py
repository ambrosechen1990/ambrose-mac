# -*- coding: utf-8 -*-
"""macOS / 跨平台适配工具（Beatbot-tools）。"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional


IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")


def project_root() -> Path:
    """Beatbot-tools 根目录（主程序的上一级）。"""
    here = Path(__file__).resolve().parent
    return here.parent


def app_data_dir() -> Path:
    """可写数据目录：Excel / 日志包等默认输出位置。"""
    env = os.environ.get("BEATBOT_DIST")
    candidates = []
    if env:
        candidates.append(Path(env).expanduser())
    if IS_MAC:
        candidates.append(Path.home() / "Documents" / "BeatbotDist")
    candidates.append(Path.home() / "BeatbotDist")
    candidates.append(project_root() / "输出目录")
    last_err = None
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            # 写权限探测
            probe = path / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError as e:
            last_err = e
            continue
    raise OSError(f"无法创建输出目录，最后错误: {last_err}")


def picture_dir() -> Path:
    """截图输出目录（主程序/picture）。"""
    path = Path(__file__).resolve().parent / "picture"
    path.mkdir(parents=True, exist_ok=True)
    return path


def adb_executable() -> str:
    """ADB 可执行路径，可用环境变量 ADB_PATH 覆盖。"""
    env = os.environ.get("ADB_PATH")
    if env and os.path.isfile(env):
        return env
    return "adb"


def run_adb(args: list[str], timeout: Optional[float] = 60) -> subprocess.CompletedProcess:
    """以 list 方式调用 adb（避免 shell=True）。"""
    cmd = [adb_executable(), *args]
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def decode_proc_output(data: bytes | None) -> str:
    if not data:
        return ""
    return data.decode(errors="ignore")


def is_file_locked(path: str) -> bool:
    """检测文件是否被其他进程占用（跨平台）。"""
    if not os.path.exists(path):
        return False
    try:
        if IS_WIN:
            import msvcrt

            with open(path, "a+b") as f:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            return False
        import fcntl

        with open(path, "a+b") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    except Exception:
        # 无法判定时，交给后续 openpyxl 捕获 PermissionError
        return False


def _pick_font(candidates: Iterable[str], fallback: str) -> str:
    try:
        import tkinter as tk
        import tkinter.font as tkfont

        families = getattr(_pick_font, "_families", None)
        if families is None:
            root = None
            try:
                root = tk._default_root  # noqa: SLF001
            except Exception:
                root = None
            own_root = False
            if root is None:
                root = tk.Tk()
                root.withdraw()
                own_root = True
            families = set(tkfont.families(root))
            _pick_font._families = families  # type: ignore[attr-defined]
            if own_root:
                try:
                    root.destroy()
                except Exception:
                    pass
        for name in candidates:
            if name in families:
                return name
    except Exception:
        pass
    return fallback


_UI_FONT_FAMILY: str | None = None
_MONO_FONT_FAMILY: str | None = None


def ui_font_family() -> str:
    global _UI_FONT_FAMILY
    if _UI_FONT_FAMILY:
        return _UI_FONT_FAMILY
    if IS_MAC:
        _UI_FONT_FAMILY = _pick_font(
            ("PingFang SC", "Heiti SC", "Hiragino Sans GB", "Songti SC", "Arial Unicode MS"),
            "Helvetica",
        )
    elif IS_WIN:
        _UI_FONT_FAMILY = _pick_font(("微软雅黑", "Microsoft YaHei", "SimHei"), "Segoe UI")
    else:
        _UI_FONT_FAMILY = _pick_font(("Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans"), "DejaVu Sans")
    return _UI_FONT_FAMILY


def mono_font_family() -> str:
    global _MONO_FONT_FAMILY
    if _MONO_FONT_FAMILY:
        return _MONO_FONT_FAMILY
    if IS_MAC:
        _MONO_FONT_FAMILY = _pick_font(("Menlo", "SF Mono", "Monaco", "Courier New"), "Menlo")
    elif IS_WIN:
        _MONO_FONT_FAMILY = _pick_font(("Consolas", "Courier New"), "Consolas")
    else:
        _MONO_FONT_FAMILY = _pick_font(("DejaVu Sans Mono", "Liberation Mono", "Courier New"), "Courier New")
    return _MONO_FONT_FAMILY


def ui_font(size: int = 12, weight: str | None = None):
    family = ui_font_family()
    if weight:
        return (family, size, weight)
    return (family, size)


def mono_font(size: int = 10, weight: str | None = None):
    family = mono_font_family()
    if weight:
        return (family, size, weight)
    return (family, size)


def pillow_resample():
    """兼容 Pillow 新旧版本的高质量缩放算法。"""
    try:
        from PIL import Image

        return getattr(Image, "Resampling", Image).LANCZOS
    except Exception:
        try:
            from PIL import Image

            return Image.LANCZOS
        except Exception:
            return 1


def prefer_mac_serial_ports(ports):
    """
    ports: list of serial.tools.list_ports.ListPortInfo 或 (device, desc)
    Mac 上优先 /dev/cu.*，并优先 USB 串口芯片。
    """
    items = list(ports)
    if not items:
        return items

    def device_of(p):
        return p.device if hasattr(p, "device") else p[0]

    def desc_of(p):
        if hasattr(p, "description"):
            return (p.description or "") + " " + (getattr(p, "manufacturer", None) or "")
        return p[1] if len(p) > 1 else ""

    if IS_MAC:
        # 过滤重复 tty（与 cu 成对），优先 cu
        cu = [p for p in items if device_of(p).startswith("/dev/cu.")]
        others = [p for p in items if not device_of(p).startswith("/dev/tty.")]
        items = cu or others or items

    keywords = ("CH340", "WCH", "USB SERIAL", "USB-SERIAL", "CP210", "FTDI", "USBUART", "UART")

    def score(p):
        d = desc_of(p).upper()
        dev = device_of(p).upper()
        s = 0
        for i, kw in enumerate(keywords):
            if kw in d or kw in dev:
                s += 100 - i
        if IS_MAC and device_of(p).startswith("/dev/cu."):
            s += 10
        return s

    return sorted(items, key=score, reverse=True)


def setup_tesseract_cmd() -> None:
    """在 Mac 上尝试定位 Homebrew tesseract。"""
    try:
        import pytesseract
    except ImportError:
        return
    if not IS_MAC:
        return
    candidates = [
        os.environ.get("TESSERACT_CMD"),
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "tesseract",
    ]
    for cmd in candidates:
        if not cmd:
            continue
        if cmd == "tesseract" or os.path.isfile(cmd):
            pytesseract.pytesseract.tesseract_cmd = cmd
            return


def create_tk_root():
    """优先 TkinterDnD，失败则退回普通 Tk。"""
    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk()
    except Exception:
        import tkinter as tk

        return tk.Tk()


def mac_help_text(dist_dir: Path, picture: Path) -> str:
    return (
        "【界面布局】\n"
        "主界面为 3 行 × 4 列功能卡片，「使用帮助」固定在右下角最后一格。\n"
        "第1行：轨迹线绘制、池壁轨迹线绘制、日志解析、日志打包下载\n"
        "第2行：日志一键删除、MCU工具、串口调试、（预留）\n"
        "第3行：（预留）…、使用帮助\n\n"
        "【环境依赖项（macOS）】\n"
        "1. 安装 Homebrew 后执行：brew install tesseract\n"
        "2. 安装 ADB：brew install android-platform-tools\n"
        "3. Python 依赖：pip install -r requirements.txt\n"
        "4. 串口功能需 pyserial；USB 转串口芯片（CH340 等）可能需要安装驱动\n"
        "5. 日志打包/删除需本机已安装 ADB，并与设备同一局域网\n"
        "6. 不需要安装 VC_redist（那是 Windows 专用）\n\n"
        "【轨迹线绘制 - 详细步骤】\n"
        "第一步：信息填写\n"
        "1. 点击「轨迹线绘制」卡片，弹出信息填写对话框。\n"
        "2. 必须填写机器序号、泳池编号、机器阶段、固件版本号、轨迹线宽度等所有必填项。\n"
        "3. 轨迹线宽度默认为15，可根据需要调整（必须大于0的整数）。\n"
        "4. 如有空项会显示红色提示，无法进入下一步。\n"
        "5. 选择视频文件（支持MP4、AVI、MOV、MKV格式）。\n\n"
        "第二步：区域绘制\n"
        "6. 用鼠标左键依次点击视频画面，绘制多边形区域。\n"
        "7. 点击右键（或键盘 q）闭合多边形，完成区域绘制。\n"
        "8. 系统会显示 Drawing Complete! 提示。\n\n"
        "第三步：目标跟踪\n"
        "9. 按空格键选择要跟踪的目标（会弹出选择框）。\n"
        "10. 用鼠标拖拽选择目标区域，按回车确认。\n"
        "11. 目标跟踪开始，会显示轨迹线和覆盖率。\n\n"
        "第四步：结束与保存\n"
        "12. 按 q 键手动结束（结束状态为 No），视频播放完毕自动结束（结束状态为 Yes）。\n"
        "13. 自动保存 Coverage / Tracking 截图。\n"
        f"14. 轨迹信息写入 Excel：{dist_dir / '轨迹线绘制记录.xlsx'}\n\n"
        "【池壁轨迹线绘制】\n"
        "流程与轨迹线绘制类似，需绘制两个池壁多边形，并计算中间区域覆盖率。\n"
        f"Excel 保存：{dist_dir / '池壁轨迹线记录.xlsx'}\n\n"
        "【日志解析】\n"
        "选择 zip / tar.gz / tar 压缩包，自动解压并解析 bin 为明文 log。\n\n"
        "【日志打包下载】\n"
        "输入设备 IP，经 ADB 打包并下载到本机。\n"
        f"默认保存目录：{dist_dir}\n\n"
        "【日志一键删除】\n"
        "经 ADB 清空设备 /data/log 与 /tmp/log。\n\n"
        "【MCU工具 / 串口调试】\n"
        "Mac 串口一般为 /dev/cu.usbserial* / /dev/cu.wchusbserial* 等。\n"
        "请勿同时用两个工具占用同一物理串口。\n\n"
        "【注意事项】\n"
        f"1. 图片默认保存：{picture}\n"
        f"2. Excel / 日志包默认保存：{dist_dir}\n"
        "3. 可用环境变量 BEATBOT_DIST 自定义输出目录，ADB_PATH 指定 adb。\n"
        "4. 需要本机已安装 tesseract，否则无法识别视频时间。\n"
        f"5. 当前系统：{platform.system()} {platform.machine()}\n"
    )
