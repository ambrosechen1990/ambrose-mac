# -*- coding: utf-8 -*-
"""Beatbot 软测工具 — macOS 主程序（由 Softwaretest-win.py 转换适配）。

运行：python3 Beatbot.py
依赖：同目录 platform_compat.py；brew install tesseract android-platform-tools
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Toplevel, simpledialog
import cv2
import os
from datetime import datetime
import numpy as np
import logging
import atexit
import zstandard as zstd
import shutil
import tempfile
from PIL import Image, ImageTk
import threading
import concurrent.futures
import sys
from tkinterdnd2 import DND_FILES, TkinterDnD
import multiprocessing
import zipfile
import tarfile
from concurrent.futures import ProcessPoolExecutor
import json
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
import openpyxl.styles
from openpyxl.utils import get_column_letter
import pytesseract
import re
import time
import subprocess
import webbrowser
import socket
import importlib.util

from platform_compat import (
    app_data_dir,
    create_tk_root,
    decode_proc_output,
    is_file_locked,
    mac_help_text,
    mono_font,
    picture_dir,
    pillow_resample,
    run_adb,
    setup_tesseract_cmd,
    ui_font,
)

# 强制纳入打包依赖：MCU/串口工具运行时需要（PyInstaller 不会分析 data 里的 .py）
import tkinter.scrolledtext  # noqa: F401

try:
    import serial  # noqa: F401
    from serial.tools import list_ports  # noqa: F401
except ImportError:
    serial = None
    list_ports = None

# 主程序目录与数据目录（json/txt 等用户数据归拢在 data/ 下）
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
TEMP_DIR = os.path.join(DATA_DIR, "temp")
for _data_sub in (HISTORY_DIR, CONFIG_DIR, TEMP_DIR):
    os.makedirs(_data_sub, exist_ok=True)


def _resource_roots():
    """源码目录 + 打包解压目录（_MEIPASS）。"""
    roots = []
    if getattr(sys, "_MEIPASS", None):
        roots.append(sys._MEIPASS)
    here = os.path.dirname(os.path.abspath(__file__))
    roots.append(here)
    roots.append(os.path.dirname(here))  # Beatbot-tools/
    roots.append(os.getcwd())
    # 去重保序
    seen = set()
    out = []
    for r in roots:
        if r and r not in seen and os.path.isdir(r):
            seen.add(r)
            out.append(r)
    return out


def _find_file(rel_candidates):
    """在资源根下查找文件；rel_candidates 为相对路径列表。"""
    for root in _resource_roots():
        for rel in rel_candidates:
            path = os.path.normpath(os.path.join(root, rel))
            if os.path.isfile(path):
                return path
        # 兼容：根下直接放了脚本
        for rel in rel_candidates:
            base = os.path.basename(rel)
            path = os.path.join(root, base)
            if os.path.isfile(path):
                return path
    return None


def _load_module_from_file(module_name: str, script_path: str):
    """用绝对路径加载 .py（避免中文包名/打包路径导致 import 失败）。"""
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {script_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def open_video_capture(path: str):
    """打开本地视频：优先 CAP_FFMPEG，避免 macOS AVFoundation 异常。"""
    if not path or not os.path.isfile(path):
        return None
    backends = []
    if hasattr(cv2, "CAP_FFMPEG"):
        backends.append(cv2.CAP_FFMPEG)
    backends.append(getattr(cv2, "CAP_ANY", 0))
    for backend in backends:
        try:
            cap = cv2.VideoCapture(path, backend)
        except Exception:
            continue
        if cap is not None and cap.isOpened():
            return cap
        try:
            cap.release()
        except Exception:
            pass
    # 最后再试默认后端
    try:
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            return cap
        cap.release()
    except Exception:
        pass
    return None


def safe_named_window(title: str, flags=None):
    """创建 OpenCV 窗口（须在主线程调用）。"""
    if flags is None:
        flags = getattr(cv2, "WINDOW_NORMAL", 0)
    try:
        cv2.namedWindow(title, flags)
    except Exception:
        cv2.namedWindow(title)


def _load_serial_tool_opener():
    """加载串口工具 open_serial_tool；失败返回 None。"""
    script = _find_file([
        os.path.join("serial_tool", "串口工具.py"),
        os.path.join("串口工具", "串口工具.py"),
        os.path.join("Beatbot-tools", "串口工具", "串口工具.py"),
        os.path.join("Softwaretest", "串口工具", "串口工具.py"),
    ])
    if not script:
        return None
    try:
        mod = _load_module_from_file("xm_serial_debug_tool", script)
        return getattr(mod, "open_serial_tool", None)
    except Exception as e:
        print(f"[串口工具] 加载失败: {script} -> {e}")
        return None


# 启动时尝试加载；失败也不阻断主程序（点击时再试一次）
open_serial_tool = _load_serial_tool_opener()


def _load_video_calib_opener():
    """加载视频标定矫正 open_video_calib_tool；失败返回 None。"""
    script = _find_file([
        os.path.join("spjz", "视频标定矫正.py"),
        os.path.join("Beatbot-tools", "spjz", "视频标定矫正.py"),
        os.path.join("视频矫正", "视频标定矫正.py"),
    ])
    if not script:
        return None
    try:
        mod = _load_module_from_file("xm_video_calib_tool", script)
        return getattr(mod, "open_video_calib_tool", None)
    except Exception as e:
        print(f"[视频标定矫正] 加载失败: {script} -> {e}")
        return None


open_video_calib_tool = _load_video_calib_opener()


class ExcelBlockingDialog:
    """Excel文件被占用时的强弹框，只有关闭Excel文件后才能关闭"""

    def __init__(self, parent, excel_path):
        self.parent = parent
        self.excel_path = excel_path
        self.dialog = None
        self.result = False

    def show(self):
        """显示强弹框，直到Excel文件关闭"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("保存失败")
        self.dialog.geometry("400x200")
        self.dialog.resizable(False, False)

        # 设置窗口居中
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (200 // 2)
        self.dialog.geometry(f"400x200+{x}+{y}")

        # 设置窗口始终在最前面
        self.dialog.attributes('-topmost', True)
        self.dialog.lift()
        self.dialog.focus_force()

        # 设置模态窗口
        self.dialog.grab_set()
        self.dialog.transient(self.parent)

        # 创建主框架
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(expand=True, fill="both")

        # 错误图标和消息
        error_frame = ttk.Frame(main_frame)
        error_frame.pack(expand=True, fill="both")

        # 错误图标（红色X）
        error_icon = ttk.Label(error_frame, text="✕", font=("Arial", 48), foreground="red")
        error_icon.pack(pady=(0, 10))

        # 错误消息
        error_msg = ttk.Label(error_frame,
                              text="文件被占用，需关闭Excel表格才能保存数据",
                              font=ui_font(12),
                              wraplength=350,
                              justify="center")
        error_msg.pack(pady=(0, 20))

        # 文件路径显示
        path_label = ttk.Label(error_frame,
                               text=f"文件路径：{self.excel_path}",
                               font=ui_font(9),
                               foreground="gray",
                               wraplength=350)
        path_label.pack()

        # 确定按钮
        ok_button = ttk.Button(main_frame, text="确定", command=self.on_ok_click)
        ok_button.pack(pady=(20, 0))

        # 绑定回车键
        self.dialog.bind('<Return>', lambda e: self.on_ok_click())

        # 开始检查Excel文件状态
        self.check_excel_status()

        # 等待窗口关闭
        self.dialog.wait_window()
        return self.result

    def on_ok_click(self):
        """点击确定按钮的处理"""
        # 检查Excel文件是否已关闭
        if self.is_excel_file_available():
            self.result = True
            self.dialog.destroy()
        else:
            # 文件仍然被占用，显示提示
            self.dialog.bell()  # 播放提示音
            # 显示提示信息
            messagebox.showinfo("提示", "需关闭Excel表格才能保存数据")

    def is_excel_file_available(self):
        """检查Excel文件是否可用（未被占用）"""
        if not os.path.exists(self.excel_path):
            return True
        if is_file_locked(self.excel_path):
            return False
        try:
            wb = load_workbook(self.excel_path, read_only=True)
            wb.close()
            return True
        except (PermissionError, FileNotFoundError, OSError):
            return False
        except Exception:
            return not is_file_locked(self.excel_path)

    def check_excel_status(self):
        """定期检查Excel文件状态"""
        if self.dialog and self.dialog.winfo_exists():
            if self.is_excel_file_available():
                # 文件已可用，自动关闭弹框
                self.result = True
                self.dialog.destroy()
            else:
                # 继续检查
                self.dialog.after(1000, self.check_excel_status)  # 每秒检查一次


class ThreadSafeExcelDialog:
    """线程安全的Excel文件占用弹框，专门用于子线程"""

    def __init__(self, excel_path):
        self.excel_path = excel_path
        self.result = False

    def show(self):
        try:
            print("ThreadSafeExcelDialog.show() 开始")
            # 创建一个全新的Tk实例
            temp_root = tk.Tk()
            print("Tk实例创建成功")
            temp_root.withdraw()
            temp_root.attributes('-topmost', True)
            temp_root.title("Excel文件占用提示")

            # 设置窗口居中
            temp_root.update_idletasks()
            x = (temp_root.winfo_screenwidth() // 2) - (400 // 2)
            y = (temp_root.winfo_screenheight() // 2) - (200 // 2)
            temp_root.geometry(f"400x200+{x}+{y}")

            # 确保窗口在最前面
            temp_root.lift()
            temp_root.focus_force()

            # 创建主框架
            main_frame = ttk.Frame(temp_root, padding="20")
            main_frame.pack(expand=True, fill="both")

            # 错误图标和消息
            error_frame = ttk.Frame(main_frame)
            error_frame.pack(expand=True, fill="both")

            # 错误图标（红色X）
            error_icon = ttk.Label(error_frame, text="✕", font=("Arial", 48), foreground="red")
            error_icon.pack(pady=(0, 10))

            # 错误消息
            error_msg = ttk.Label(error_frame,
                                  text="文件被占用，需关闭Excel表格才能保存数据",
                                  font=ui_font(12),
                                  wraplength=350,
                                  justify="center")
            error_msg.pack(pady=(0, 20))

            # 文件路径显示
            path_label = ttk.Label(error_frame,
                                   text=f"文件路径：{self.excel_path}",
                                   font=ui_font(9),
                                   foreground="gray",
                                   wraplength=350)
            path_label.pack()

            # 确定按钮
            def on_ok_click():
                # 检查Excel文件是否已关闭
                if is_excel_file_available():
                    self.result = True
                    temp_root.destroy()
                else:
                    temp_root.bell()
                    messagebox.showinfo("提示", "需关闭Excel表格才能保存数据")

            def is_excel_file_available():
                """检查Excel文件是否可用（未被占用）"""
                if not os.path.exists(self.excel_path):
                    return True
                if is_file_locked(self.excel_path):
                    return False
                try:
                    wb = load_workbook(self.excel_path, read_only=True)
                    wb.close()
                    return True
                except (PermissionError, FileNotFoundError, OSError):
                    return False
                except Exception:
                    return not is_file_locked(self.excel_path)

            ok_button = ttk.Button(main_frame, text="确定", command=on_ok_click)
            ok_button.pack(pady=(20, 0))

            # 绑定回车键
            temp_root.bind('<Return>', lambda e: on_ok_click())

            # 开始检查Excel文件状态
            def check_excel_status():
                if temp_root.winfo_exists():
                    if is_excel_file_available():
                        self.result = True
                        temp_root.destroy()
                    else:
                        temp_root.after(1000, check_excel_status)

            temp_root.after(1000, check_excel_status)

            # 等待窗口关闭
            print("开始等待窗口关闭...")
            temp_root.wait_window()
            print(f"窗口已关闭，返回结果: {self.result}")
            return self.result

        except Exception as e:
            print(f"显示弹框失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def resource_path(relative_path):
    # 兼容pyinstaller打包和源码运行
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def process_one_bin(args):
    src_file, target_dir, filename = args
    print(f"[DEBUG] 正在解析: {src_file}，输出到: {os.path.join(target_dir, filename[:-4] + '.log')}")
    log_file = os.path.join(target_dir, filename[:-4] + ".log")
    try:
        hex_list = []
        with open(src_file, 'r') as f_in:
            for line in f_in:
                line = line.strip()
                if len(line) > 14:
                    hex_list.append(line[14:])
        hex_str = ''.join(hex_list)
        hex_str = ''.join(filter(lambda c: c in '0123456789abcdefABCDEF', hex_str))
        data = bytes.fromhex(hex_str)
        zstd_magic = b'\x28\xb5\x2f\xfd'
        idx = 0
        with open(log_file, 'w', encoding='utf-8') as f_out:
            while True:
                idx = data.find(zstd_magic, idx)
                if idx == -1:
                    break
                next_idx = data.find(zstd_magic, idx + 4)
                chunk = data[idx:next_idx] if next_idx != -1 else data[idx:]
                try:
                    dctx = zstd.ZstdDecompressor()
                    decompressed = dctx.decompress(chunk)
                    f_out.write(decompressed.decode('utf-8', errors='replace'))
                except Exception as e:
                    print(f'解压第{idx}段失败: {e}')
                idx = next_idx if next_idx != -1 else len(data)
        print(f"已生成log文件: {log_file}")
        return 1
    except Exception as e:
        print(f"转换{src_file}失败: {e}")
        return 0


# 轨迹线绘制信息弹窗（含历史）
def _history_path(filename):
    """优先 data/history，兼容旧版主程序目录下的历史文件。"""
    name = os.path.basename(filename)
    new_path = os.path.join(HISTORY_DIR, name)
    legacy_path = os.path.join(APP_DIR, name)
    if os.path.exists(new_path):
        return new_path
    if os.path.exists(legacy_path):
        return legacy_path
    return new_path


def get_history(path):
    path = _history_path(path)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_history(path, value):
    path = os.path.join(HISTORY_DIR, os.path.basename(path))
    history = get_history(path)
    if value and value not in history:
        history.append(value)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False)


def make_mac_safe_dialog_buttons(parent, on_ok, on_cancel, font=None):
    """
    创建在 macOS 上颜色仍可见的「确定/取消」按钮。
    原生 tk.Button 在 Aqua 下常忽略 bg/fg，导致「确定」白字看不清；
    这里用 Frame+Label 模拟图1 风格的蓝底主按钮 + 白底次按钮。

    注意：只绑定 Button-1，并用 after 延迟关闭窗口，避免对话框销毁后
    同一次鼠标松开落到主界面功能卡上（点击穿透）。
    """
    if font is None:
        font = ui_font(12)
    try:
        parent_bg = parent.cget("bg")
    except Exception:
        parent_bg = "#f0f0f0"
    bar = tk.Frame(parent, bg=parent_bg)

    # 主按钮：系统蓝底 + 白字（强制着色，不受 Aqua 主题覆盖）
    ok_wrap = tk.Frame(bar, bg="#007AFF", padx=0, pady=0, highlightthickness=0)
    ok_btn = tk.Label(
        ok_wrap,
        text="确定",
        font=font,
        bg="#007AFF",
        fg="#FFFFFF",
        padx=22,
        pady=6,
        cursor="hand2",
    )
    ok_btn.pack()
    ok_wrap.pack(side=tk.LEFT, padx=10)

    def _ok(event=None):
        # 延迟执行，等本次点击序列结束，防止穿透到下层窗口
        bar.after_idle(on_ok)
        return "break"

    def _ok_enter(_event=None):
        ok_btn.configure(bg="#0062cc")
        ok_wrap.configure(bg="#0062cc")

    def _ok_leave(_event=None):
        ok_btn.configure(bg="#007AFF")
        ok_wrap.configure(bg="#007AFF")

    for w in (ok_wrap, ok_btn):
        w.bind("<Button-1>", _ok)
        w.bind("<Enter>", _ok_enter)
        w.bind("<Leave>", _ok_leave)

    # 次按钮：白底黑字描边
    cancel_wrap = tk.Frame(
        bar, bg="#FFFFFF", highlightbackground="#C7C7CC", highlightthickness=1, padx=0, pady=0
    )
    cancel_btn = tk.Label(
        cancel_wrap,
        text="取消",
        font=font,
        bg="#FFFFFF",
        fg="#000000",
        padx=22,
        pady=6,
        cursor="hand2",
    )
    cancel_btn.pack()
    cancel_wrap.pack(side=tk.LEFT, padx=10)

    def _cancel(event=None):
        bar.after_idle(on_cancel)
        return "break"

    def _cancel_enter(_event=None):
        cancel_btn.configure(bg="#F2F2F7")
        cancel_wrap.configure(bg="#F2F2F7")

    def _cancel_leave(_event=None):
        cancel_btn.configure(bg="#FFFFFF")
        cancel_wrap.configure(bg="#FFFFFF")

    for w in (cancel_wrap, cancel_btn):
        w.bind("<Button-1>", _cancel)
        w.bind("<Enter>", _cancel_enter)
        w.bind("<Leave>", _cancel_leave)

    return bar, ok_btn, cancel_btn


def show_info_dialog(parent=None):
    """填写轨迹线信息。须在主线程调用；先建完再显示，避免控件逐条刷出。"""
    # 预缓存字体，避免建窗过程中反复枚举系统字体
    label_font = ui_font(12)
    tip_font = ui_font(10, "bold")

    master = parent
    if master is None:
        try:
            master = tk._default_root  # noqa: SLF001
        except Exception:
            master = None

    root = tk.Toplevel(master) if master is not None else tk.Toplevel()
    root.withdraw()  # 先隐藏，全部控件创建完成后再一次性显示
    root.title("填写轨迹线信息")
    root.resizable(False, False)

    # 对话框内也配置错误样式（可能早于主窗 setup_styles）
    style = ttk.Style(root)
    style.configure(
        'Error.TCombobox',
        fieldbackground='#ffebee',
        background='#ffebee',
        bordercolor='#f44336',
        lightcolor='#f44336',
        darkcolor='#f44336',
    )
    style.configure(
        'Error.TEntry',
        fieldbackground='#ffebee',
        bordercolor='#f44336',
        lightcolor='#f44336',
        darkcolor='#f44336',
    )

    # 历史记录相对主程序目录读取，避免 cwd 变化找不到
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sn_history = get_history(os.path.join(base_dir, 'sn_history.json'))
    pool_history = get_history(os.path.join(base_dir, 'pool_history.json'))
    fw_history = get_history(os.path.join(base_dir, 'fw_history.json'))

    # 创建主框架
    main_frame = ttk.Frame(root, padding="20")
    main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    # 配置网格权重
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    main_frame.columnconfigure(1, weight=1)

    # 创建标签和输入框（窗口仍隐藏，不会逐条闪现）
    ttk.Label(main_frame, text="机器序号:", font=label_font).grid(row=0, column=0, sticky=tk.W, pady=5)
    sn_var = tk.StringVar()
    sn_combo = ttk.Combobox(main_frame, textvariable=sn_var, values=sn_history, width=30, font=label_font)
    sn_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)

    ttk.Label(main_frame, text="泳池编号:", font=label_font).grid(row=1, column=0, sticky=tk.W, pady=5)
    pool_var = tk.StringVar()
    pool_combo = ttk.Combobox(main_frame, textvariable=pool_var, values=pool_history, width=30, font=label_font)
    pool_combo.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)

    ttk.Label(main_frame, text="机器阶段:", font=label_font).grid(row=2, column=0, sticky=tk.W, pady=5)
    stage_var = tk.StringVar()
    stage_combo = ttk.Combobox(main_frame, textvariable=stage_var,
                               values=["手板", "T0", "EVT1", "EVT2", "DVT1", "DVT2", "MP"], width=30,
                               font=label_font)
    stage_combo.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)

    ttk.Label(main_frame, text="固件版本号:", font=label_font).grid(row=3, column=0, sticky=tk.W, pady=5)
    fw_var = tk.StringVar()
    fw_combo = ttk.Combobox(main_frame, textvariable=fw_var, values=fw_history, width=30, font=label_font)
    fw_combo.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)

    ttk.Label(main_frame, text="轨迹线宽度:", font=label_font).grid(row=4, column=0, sticky=tk.W, pady=5)
    track_width_var = tk.StringVar(value="15")  # 默认值 15
    track_width_entry = ttk.Entry(main_frame, textvariable=track_width_var, width=32, font=label_font)
    track_width_entry.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)

    # 错误提示标签
    error_label = ttk.Label(main_frame, text="", foreground="red", font=tip_font)
    error_label.grid(row=5, column=0, columnspan=2, pady=10)

    result = {}

    def on_ok():
        # 获取输入值并去除首尾空格
        sn = sn_var.get().strip()
        pool = pool_var.get().strip()
        stage = stage_var.get().strip()
        fw = fw_var.get().strip()
        track_width_str = track_width_var.get().strip()

        # 验证输入
        missing_fields = []
        if not sn:
            missing_fields.append("机器序号")
        if not pool:
            missing_fields.append("泳池编号")
        if not stage:
            missing_fields.append("机器阶段")
        if not fw:
            missing_fields.append("固件版本号")
        if not track_width_str:
            missing_fields.append("轨迹线宽度")

        if missing_fields:
            # 显示错误信息
            error_text = f"请填写以下必填项：\n{', '.join(missing_fields)}"
            error_label.config(text=error_text)

            # 高亮显示空的输入框
            if not sn:
                sn_combo.config(style='Error.TCombobox')
            else:
                sn_combo.config(style='TCombobox')

            if not pool:
                pool_combo.config(style='Error.TCombobox')
            else:
                pool_combo.config(style='TCombobox')

            if not stage:
                stage_combo.config(style='Error.TCombobox')
            else:
                stage_combo.config(style='TCombobox')

            if not fw:
                fw_combo.config(style='Error.TCombobox')
            else:
                fw_combo.config(style='TCombobox')

            if not track_width_str:
                track_width_entry.config(style='Error.TEntry')
            else:
                track_width_entry.config(style='TEntry')

            # 震动窗口提示
            root.bell()
            return

        # 验证轨迹线宽度是否为有效数字
        try:
            track_width = int(track_width_str)
            if track_width <= 0:
                error_label.config(text="轨迹线宽度必须大于0！")
                track_width_entry.config(style='Error.TEntry')
                root.bell()
                return
        except ValueError:
            error_label.config(text="轨迹线宽度必须是有效的数字！")
            track_width_entry.config(style='Error.TEntry')
            root.bell()
            return

        # 所有字段都已填写，保存结果
        result['sn'] = sn
        result['pool'] = pool
        result['stage'] = stage
        result['fw'] = fw
        result['track_width'] = track_width

        # 保存到历史记录
        save_history(os.path.join(base_dir, 'sn_history.json'), result['sn'])
        save_history(os.path.join(base_dir, 'pool_history.json'), result['pool'])
        save_history(os.path.join(base_dir, 'fw_history.json'), result['fw'])

        root.destroy()

    def on_cancel():
        result.clear()  # 清空结果，表示用户取消
        root.destroy()

    # 创建按钮框架（图1 风格：蓝底「确定」+ 白底「取消」，macOS 强制着色可见）
    button_frame = tk.Frame(main_frame, bg="#f0f0f0")
    button_frame.grid(row=6, column=0, columnspan=2, pady=20)
    btn_bar, _, _ = make_mac_safe_dialog_buttons(button_frame, on_ok, on_cancel, font=label_font)
    btn_bar.configure(bg="#f0f0f0")
    btn_bar.pack()

    # 绑定回车 / Esc
    root.bind("<Return>", lambda e: on_ok())
    root.bind("<KP_Enter>", lambda e: on_ok())
    root.bind("<Escape>", lambda e: on_cancel())

    # 布局完成后再定位并一次性显示，并强制激活窗口（避免需先点标题栏）
    root.update_idletasks()
    w, h = 500, 400
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    if master is not None:
        try:
            root.transient(master)
        except Exception:
            pass

    root.deiconify()
    root.lift()
    root.focus_force()
    try:
        root.wait_visibility()
    except Exception:
        pass
    # 模态期间保持置顶：避免其它功能大窗（如视频标定）盖住本对话框
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    root.grab_set()
    sn_combo.focus_set()
    # 再点一次激活，防止 macOS 首次点击被系统用来激活窗口
    root.after(50, lambda: (root.lift(), root.focus_force(), sn_combo.focus_set()))

    root.wait_window()

    return result


def append_to_excel(info, coverage_img_path, tracking_img_path):
    print(f"开始写入Excel，coverage图片: {coverage_img_path}")
    print(f"tracking图片: {tracking_img_path}")
    print(f"info数据: {info}")

    # Excel / 日志默认输出到 ~/Documents/BeatbotDist（可用 BEATBOT_DIST 覆盖）
    dist_dir = str(app_data_dir())
    os.makedirs(dist_dir, exist_ok=True)
    excel_path = os.path.join(dist_dir, '轨迹线绘制记录.xlsx')
    print(f"Excel文件路径: {excel_path}")

    # 直接使用原始图片路径，不复制到dist目录
    coverage_filename = os.path.basename(coverage_img_path)
    tracking_filename = os.path.basename(tracking_img_path)

    try:
        if not os.path.exists(excel_path):
            # 创建新的Excel文件
            wb = Workbook()
            ws = wb.active
            ws.append(
                ['序号', '视频开始时间', '机器序号', '泳池编号', '机器阶段', '固件版本号', 'coverage 截图',
                 'tracking 截图',
                 '结束状态', '覆盖率'])
            for cell in ws[ws.max_row]:
                cell.alignment = openpyxl.styles.Alignment(horizontal='center', vertical='center')
        else:
            # 尝试加载现有Excel文件
            try:
                wb = load_workbook(excel_path)
                ws = wb.active
            except PermissionError:
                # Excel文件被占用，显示强弹框
                print("Excel文件被占用，显示强弹框...")
                result = show_excel_blocking_dialog(excel_path)

                if result:
                    # Excel文件已关闭，重新尝试加载
                    try:
                        wb = load_workbook(excel_path)
                        ws = wb.active
                    except Exception as retry_error:
                        print(f"重新加载失败: {retry_error}")
                        raise
                else:
                    # 用户取消或出现其他问题
                    raise PermissionError("用户取消操作")
            except Exception as e:
                print(f"现有Excel文件损坏，创建新文件: {e}")
                # 如果文件损坏，备份原文件并创建新文件
                backup_path = excel_path + f".backup_{int(time.time())}"
                if os.path.exists(excel_path):
                    try:
                        os.rename(excel_path, backup_path)
                        print(f"已备份损坏文件到: {backup_path}")
                    except:
                        pass
                wb = Workbook()
                ws = wb.active
                ws.append(
                    ['序号', '视频开始时间', '机器序号', '泳池编号', '机器阶段', '固件版本号', 'coverage 截图',
                     'tracking 截图',
                     '结束状态', '覆盖率'])
                for cell in ws[ws.max_row]:
                    cell.alignment = openpyxl.styles.Alignment(horizontal='center', vertical='center')

        # 添加数据行
        row = [ws.max_row, info['start_time'], info['sn'], info['pool'], info['stage'], info['fw'],
               coverage_filename, tracking_filename, info['end_status'], info['coverage']]
        ws.append(row)
        for cell in ws[ws.max_row]:
            cell.alignment = openpyxl.styles.Alignment(horizontal='center', vertical='center')

        # 添加coverage图片到G列
        try:
            print(f"尝试添加coverage图片: {coverage_img_path}")
            if os.path.exists(coverage_img_path):
                coverage_img = XLImage(coverage_img_path)
                coverage_img.width = 200
                coverage_img.height = 150
                coverage_img.anchor = f'G{ws.max_row}'
                ws.add_image(coverage_img)
                print(f"✓ 已添加coverage图片到Excel G列: {coverage_img_path}")
            else:
                print(f"✗ Coverage图片文件不存在: {coverage_img_path}")
        except Exception as e:
            print(f"✗ 添加coverage图片失败: {e}")
            import traceback
            traceback.print_exc()

        # 添加tracking图片到H列
        try:
            print(f"尝试添加tracking图片: {tracking_img_path}")
            if os.path.exists(tracking_img_path):
                tracking_img = XLImage(tracking_img_path)
                tracking_img.width = 200
                tracking_img.height = 150
                tracking_img.anchor = f'H{ws.max_row}'
                ws.add_image(tracking_img)
                print(f"✓ 已添加tracking图片到Excel H列: {tracking_img_path}")
            else:
                print(f"✗ Tracking图片文件不存在: {tracking_img_path}")
        except Exception as e:
            print(f"✗ 添加tracking图片失败: {e}")
            import traceback
            traceback.print_exc()

        # 设置列宽
        ws.column_dimensions['G'].width = 35
        ws.column_dimensions['H'].width = 35
        ws.row_dimensions[ws.max_row].height = 120

        # 保存Excel文件（带重试机制）
        max_retries = 1
        for attempt in range(max_retries):
            try:
                wb.save(excel_path)
                print(f"Excel文件已保存: {excel_path}")
                # 显示成功提示
                messagebox.showinfo("提示", "数据已上传至 D:/dist/轨迹线绘制记录.xlsx")
                break
            except PermissionError:
                if attempt < max_retries - 1:
                    print(f"Excel文件被占用，等待重试... (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(2)
                else:
                    # 使用强弹框，直到Excel文件关闭
                    print("Excel文件被占用，显示强弹框...")
                    try:
                        result = show_excel_blocking_dialog(excel_path)
                        print(f"弹框返回结果: {result}")

                        if result:
                            # Excel文件已关闭，重新尝试保存
                            print("Excel文件已关闭，重新尝试保存...")
                            try:
                                wb.save(excel_path)
                                print(f"Excel文件已成功保存: {excel_path}")
                                # 显示成功提示
                                messagebox.showinfo("提示", "数据已上传至 D:/dist/轨迹线绘制记录.xlsx")
                                break
                            except Exception as retry_error:
                                print(f"重新保存失败: {retry_error}")
                                # 如果重新保存仍然失败，再次显示弹框
                                print("重新保存失败，再次显示弹框...")
                                result = show_excel_blocking_dialog(excel_path)
                                if result:
                                    wb.save(excel_path)
                                    print(f"Excel文件最终保存成功: {excel_path}")
                                    messagebox.showinfo("提示", "数据已上传至 D:/dist/轨迹线绘制记录.xlsx")
                                    break
                                else:
                                    raise PermissionError("用户取消保存操作")
                        else:
                            # 用户取消或出现其他问题
                            print("用户取消保存操作")
                            messagebox.showwarning("保存失败", "文件被占用，无法保存此次数据，请确保已关闭excel程序")
                            raise PermissionError("用户取消保存操作")
                    except Exception as dialog_error:
                        print(f"显示弹框时发生错误: {dialog_error}")
                        raise
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"保存失败，重试中... (尝试 {attempt + 1}/{max_retries}): {e}")
                    time.sleep(1)
                else:
                    messagebox.showerror("保存失败", f"保存 Excel 时发生错误：{e}")
                    raise

    except Exception as e:
        print(f"写入Excel时发生错误: {e}")
        import traceback
        traceback.print_exc()
        raise


class _TrackSmoother:
    """平滑跟踪框与中心点，抑制帧间抖动导致的轨迹锯齿。"""

    def __init__(self, bbox_alpha=0.42, center_alpha=0.36, trail_alpha=0.28,
                 min_step=4.0, max_jump=35.0):
        self.bbox_alpha = bbox_alpha
        self.center_alpha = center_alpha
        self.trail_alpha = trail_alpha
        self.min_step = min_step
        self.max_jump = max_jump
        self.perp_damp = 1.0
        self.instant_bind = False
        self.ref_wh = None
        self._bbox = None
        self._center = None
        self._trail_pos = None
        self._last_trail = None
        self._velocity = (0.0, 0.0)
        self._raw_center = None

    def reset(self):
        self._bbox = None
        self._center = None
        self._trail_pos = None
        self._last_trail = None
        self._velocity = (0.0, 0.0)
        self._raw_center = None

    def break_trail(self):
        """断开轨迹链，避免重锁定后画出跨池飞线。"""
        self._last_trail = None

    def update(self, bbox):
        x, y, w, h = [float(v) for v in bbox]
        raw_cx = x + w / 2.0
        raw_cy = y + h / 2.0
        self._raw_center = (raw_cx, raw_cy)

        if self.instant_bind:
            if self.ref_wh is not None:
                rw, rh = [float(v) for v in self.ref_wh]
                w, h = max(4.0, rw), max(4.0, rh)
                x, y = raw_cx - w / 2.0, raw_cy - h / 2.0
            self._bbox = [x, y, w, h]
            cx, cy = raw_cx, raw_cy
            prev = self._center
            self._center = (cx, cy)
            if prev is not None:
                self._velocity = (cx - prev[0], cy - prev[1])
            self._trail_pos = (cx, cy)
            bind_x, bind_y = int(round(cx)), int(round(cy))
            smooth_bbox = [int(round(x)), int(round(y)), max(1, int(round(w))), max(1, int(round(h)))]
            record = True
            if self._last_trail is not None:
                dist = ((bind_x - self._last_trail[0]) ** 2 + (bind_y - self._last_trail[1]) ** 2) ** 0.5
                if dist < max(1.0, self.min_step * 0.25):
                    record = False
            if record:
                self._last_trail = (bind_x, bind_y)
            bind_point = (bind_x, bind_y)
            return bind_point, bind_point, smooth_bbox, record

        if self._bbox is None:
            self._bbox = [x, y, w, h]
        else:
            a = self.bbox_alpha
            self._bbox = [
                a * x + (1 - a) * self._bbox[0],
                a * y + (1 - a) * self._bbox[1],
                a * w + (1 - a) * self._bbox[2],
                a * h + (1 - a) * self._bbox[3],
            ]

        cx = self._bbox[0] + self._bbox[2] / 2.0
        cy = self._bbox[1] + self._bbox[3] / 2.0

        if self.perp_damp < 1.0 and self._center is not None:
            spd2 = self._velocity[0] ** 2 + self._velocity[1] ** 2
            if spd2 > 9.0:
                spd = spd2 ** 0.5
                ux, uy = self._velocity[0] / spd, self._velocity[1] / spd
                ox, oy = self._center
                dx, dy = cx - ox, cy - oy
                parallel = dx * ux + dy * uy
                px, py = dx - parallel * ux, dy - parallel * uy
                cx = ox + parallel * ux + px * self.perp_damp
                cy = oy + parallel * uy + py * self.perp_damp

        if self._center is not None:
            ox, oy = self._center
            a = self.center_alpha
            cx = a * cx + (1 - a) * ox
            cy = a * cy + (1 - a) * oy

        prev = self._center
        self._center = (cx, cy)
        if prev is not None:
            self._velocity = (cx - prev[0], cy - prev[1])

        if self._trail_pos is None:
            self._trail_pos = (cx, cy)
        else:
            ta = self.trail_alpha
            tx, ty = self._trail_pos
            self._trail_pos = (ta * cx + (1 - ta) * tx, ta * cy + (1 - ta) * ty)

        trail_x, trail_y = self._trail_pos
        smooth_bbox = [int(round(v)) for v in self._bbox]
        if smooth_bbox[2] <= 0:
            smooth_bbox[2] = 1
        if smooth_bbox[3] <= 0:
            smooth_bbox[3] = 1

        record = True
        if self._last_trail is not None:
            dist = ((trail_x - self._last_trail[0]) ** 2 + (trail_y - self._last_trail[1]) ** 2) ** 0.5
            if dist < self.min_step:
                record = False
        if record:
            self._last_trail = (int(round(trail_x)), int(round(trail_y)))

        display_point = (int(round(cx)), int(round(cy)))
        trail_point = (int(round(trail_x)), int(round(trail_y)))
        return display_point, trail_point, smooth_bbox, record

    @property
    def bind_point(self):
        """与跟踪框中心一致的位置，用于轨迹尾段绑定目标。"""
        if self.instant_bind and self._raw_center is not None:
            return (int(round(self._raw_center[0])), int(round(self._raw_center[1])))
        if self._bbox is not None:
            return (
                int(round(self._bbox[0] + self._bbox[2] / 2.0)),
                int(round(self._bbox[1] + self._bbox[3] / 2.0)),
            )
        if self._center is None:
            return None
        return (int(round(self._center[0])), int(round(self._center[1])))

    @property
    def live_center(self):
        """跟踪辅助与显示：与平滑框中心一致，避免框/轨迹分裂抖动。"""
        bp = self.bind_point
        if bp is not None:
            return bp
        if self._center is None:
            return None
        return (int(round(self._center[0])), int(round(self._center[1])))


class TrajectoryLine:
    def __init__(self):
        # 固定视频帧大小和默认轨迹线宽度
        self.FRAME_WIDTH = 640
        self.FRAME_HEIGHT = 480
        self.TRACK_WIDTH = 15  # 默认轨迹线宽度
        # 轨迹平滑参数（抑制跟踪器帧间抖动）
        self.TRACK_BBOX_ALPHA = 0.42
        self.TRACK_CENTER_ALPHA = 0.38
        self.TRACK_TRAIL_ALPHA = 0.55
        self.TRACK_MIN_STEP = 3.0
        self.TRACK_SOURCE_SWITCH_MARGIN = 1.14
        self.TRACK_MAX_JUMP_BASE = 48.0
        self.TRACK_MAX_JUMP_SPEED_FACTOR = 4.5
        self.TRACK_MAX_TRAIL_SEGMENT = 70.0
        self.TRACK_SOURCE_AGREE_DIST = 42.0
        self.TRACK_MIL_COLOR_MAX_DIST = 55.0
        self.TRACK_REGION_MAX_MISS = 8
        self.TRACK_UPDATE_MAX_MISS = 48  # 倍速视频允许更长续跟，减少误判丢失
        self.TRACK_REINIT_AFTER_CLAMP = 6
        self.TRACK_RECONNECT_MAX_GAP = 900.0  # 重标注断点允许的最大连接跨度(px)
        self.TRACK_REGION_MIN_INSIDE = 0.35
        self.TRACK_COLOR_MIN_SCORE = 0.10
        self.TRACK_MIL_NUDGE_BLEND = 0.15
        self.TRACK_GREEN_MAX_RATIO = 0.22
        self.TRACK_LOCK_MIN_SCORE = 0.11
        self.TRACK_MIN_SATURATION = 42.0
        # 视频倍速：默认自动检测（20x/30x 等）；仅手动覆盖时设置 TRACK_VIDEO_SPEED
        self.TRACK_VIDEO_SPEED = 1.0
        self.TRACK_AUTO_SPEED = True
        self.TRACK_SPEED_CALIB = 2.8  # 帧间位移(px) / 此值 ≈ 倍速

        # 设置日志文件夹路径
        self.LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
        os.makedirs(self.LOG_DIR, exist_ok=True)

        # 设置日志文件名称和路径
        log_file_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".log"
        log_file_path = os.path.join(self.LOG_DIR, log_file_name)

        # 配置日志记录
        logging.basicConfig(
            filename=log_file_path,
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        atexit.register(logging.shutdown)

    def create_tracker(self):
        """创建跟踪器。OpenCV 4.x 官方包常无 CSRT/KCF，优先 legacy，其次 MIL。"""
        def _try(name, factory):
            try:
                tracker = factory()
                if tracker is not None:
                    print(f"使用跟踪器: {name}")
                    return tracker
            except AttributeError:
                return None
            except Exception as exc:
                logging.debug("跟踪器 %s 创建失败: %s", name, exc)
            return None

        # CSRT legacy（带参数）
        if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
            def _csrt_legacy():
                try:
                    params = cv2.legacy.TrackerCSRT_Params()
                    params.psr_threshold = 0.035
                    return cv2.legacy.TrackerCSRT_create(params)
                except Exception:
                    return cv2.legacy.TrackerCSRT_create()
            t = _try("CSRT(legacy)", _csrt_legacy)
            if t is not None:
                return t

        ordered = []
        if hasattr(cv2, "TrackerCSRT_create"):
            ordered.append(("CSRT", cv2.TrackerCSRT_create))
        if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerKCF_create"):
            ordered.append(("KCF(legacy)", cv2.legacy.TrackerKCF_create))
        if hasattr(cv2, "TrackerKCF_create"):
            ordered.append(("KCF", cv2.TrackerKCF_create))
        if hasattr(cv2, "TrackerMIL_create"):
            ordered.append(("MIL", cv2.TrackerMIL_create))
        if hasattr(cv2, "TrackerNano_create"):
            ordered.append(("Nano", cv2.TrackerNano_create))
        if hasattr(cv2, "TrackerDaSiamRPN_create"):
            ordered.append(("DaSiamRPN", cv2.TrackerDaSiamRPN_create))

        for name, factory in ordered:
            t = _try(name, factory)
            if t is not None:
                return t

        logging.error("未找到可用跟踪器")
        return None

    def _prepare_track_frame(self, frame, drift_state=None):
        """倍速较高时用原帧跟踪，避免模糊+大位移导致 MIL 失锁。"""
        peak = 1.0
        if drift_state is not None:
            peak = max(
                float(drift_state.get("peak_speed_factor", 1.0)),
                float(drift_state.get("speed_factor_auto", 1.0)),
                float(drift_state.get("speed_factor", 1.0)),
            )
        if peak >= 8.0:
            return frame
        return cv2.GaussianBlur(frame, (3, 3), 0)

    def _peak_frame_step(self, drift_state):
        samples = drift_state.get("speed_samples", []) if drift_state else []
        if not samples:
            return 10.0
        return max(6.0, float(np.percentile(samples, 90)))

    def _frame_step_limit(self, drift_state, speed_factor):
        """根据实测帧间位移与倍速，计算允许的最大步长。"""
        peak_sf = max(
            float(speed_factor),
            float(drift_state.get("peak_speed_factor", 1.0)) if drift_state else float(speed_factor),
        )
        step = self._peak_frame_step(drift_state or {})
        return min(380.0, max(55.0 + peak_sf * 5.0, step * 2.6))

    def _make_track_smoother(self):
        return _TrackSmoother(
            bbox_alpha=self.TRACK_BBOX_ALPHA,
            center_alpha=self.TRACK_CENTER_ALPHA,
            trail_alpha=self.TRACK_TRAIL_ALPHA,
            min_step=self.TRACK_MIN_STEP,
            max_jump=self.TRACK_MAX_JUMP_BASE,
        )

    def _new_drift_state(self):
        return {
            "region_miss": 0,
            "update_miss": 0,
            "jump_clamp": 0,
            "color_miss": 0,
            "color_model": None,
            "template": None,
            "frame_idx": 0,
            "stable_source": None,
            "stable_bbox": None,
            "speed_samples": [],
            "speed_factor_auto": 1.0,
            "last_raw_center": None,
            "speed_announced": False,
            "last_good_bbox": None,
            "lock_lost": 0,
            "init_center": None,
            "bootstrap_frames": 0,
            "track_fail_streak": 0,
            "stagnant_frames": 0,
            "last_resolved_center": None,
            "peak_speed_factor": 1.0,
            "reacquire_frames": 0,
            "mil_low_streak": 0,
            "trail_break": False,
        }

    def _apply_video_speed_from_info(self, info):
        """从弹窗或手动设置读取视频倍速（可选）。"""
        raw = info.get("video_speed") if info else None
        if raw in (None, ""):
            return
        try:
            self.TRACK_VIDEO_SPEED = max(1.0, float(raw))
            print(f"视频倍速设置: {self.TRACK_VIDEO_SPEED}x")
        except (TypeError, ValueError):
            pass

    def _get_speed_factor(self, drift_state, smoother=None):
        manual = max(1.0, float(getattr(self, "TRACK_VIDEO_SPEED", 1.0) or 1.0))
        auto = max(1.0, float(drift_state.get("speed_factor_auto", 1.0)))
        if getattr(self, "TRACK_AUTO_SPEED", True):
            if manual <= 1.0:
                return auto
            return max(manual, auto)
        return manual

    def _update_speed_estimate_from_bbox(self, drift_state, bbox):
        """根据融合框的帧间位移自动估算倍速（20x/30x 等，无需用户填写）。"""
        if bbox is None:
            return
        cx, cy = self._bbox_center(bbox)
        prev = drift_state.get("last_raw_center")
        drift_state["last_raw_center"] = (cx, cy)
        if prev is None:
            return
        dist = ((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) ** 0.5
        if dist >= 14.0:
            calib = max(1.5, float(getattr(self, "TRACK_SPEED_CALIB", 2.8)))
            instant_sf = max(1.0, min(60.0, dist / calib))
            drift_state["peak_speed_factor"] = max(
                float(drift_state.get("peak_speed_factor", 1.0)), instant_sf)
        if dist < 0.5:
            return
        samples = drift_state.setdefault("speed_samples", [])
        samples.append(dist)
        if len(samples) > 40:
            del samples[: len(samples) - 40]
        if len(samples) < 2:
            return
        p75 = float(np.percentile(samples, 75))
        calib = max(1.5, float(getattr(self, "TRACK_SPEED_CALIB", 2.8)))
        estimated = max(1.0, min(60.0, p75 / calib))
        prev_sf = float(drift_state.get("speed_factor_auto", 1.0))
        if estimated >= prev_sf:
            drift_state["speed_factor_auto"] = estimated
        else:
            drift_state["speed_factor_auto"] = prev_sf * 0.90 + estimated * 0.10
        if not drift_state.get("speed_announced") and drift_state["speed_factor_auto"] >= 8.0:
            sf = drift_state["speed_factor_auto"]
            print(f"自动检测视频倍速约 {sf:.0f}x（轨迹已绑定目标，无需手动设置）")
            drift_state["speed_announced"] = True
        peak = float(drift_state.get("peak_speed_factor", 1.0))
        drift_state["peak_speed_factor"] = max(peak, float(drift_state.get("speed_factor_auto", 1.0)))

    def _update_speed_estimate(self, drift_state, smoother):
        """辅助：用平滑后速度微调倍速估计（主逻辑见 _update_speed_estimate_from_bbox）。"""
        if smoother is None or smoother._center is None:
            return
        vx, vy = smoother._velocity
        speed = (vx * vx + vy * vy) ** 0.5
        if speed < 0.8:
            return
        samples = drift_state.setdefault("speed_samples", [])
        samples.append(speed)
        if len(samples) > 40:
            del samples[: len(samples) - 40]
        if len(samples) < 2:
            return
        p75 = float(np.percentile(samples, 75))
        calib = max(1.5, float(getattr(self, "TRACK_SPEED_CALIB", 2.8)))
        estimated = max(1.0, min(60.0, p75 / calib))
        prev_sf = float(drift_state.get("speed_factor_auto", 1.0))
        if estimated > prev_sf:
            drift_state["speed_factor_auto"] = estimated

    def _should_instant_bind(self, drift_state, speed_factor):
        sf = max(1.0, float(speed_factor))
        if sf >= 2.5:
            return True
        samples = drift_state.get("speed_samples", [])
        if len(samples) >= 2 and float(np.percentile(samples, 75)) >= 8.0:
            return True
        if samples and float(samples[-1]) >= 6.0:
            return True
        return False

    def _bbox_jump_limit(self, drift_state=None, speed_factor=1.0):
        """跟踪框允许的最大帧间位移（超出则整帧忽略，对齐旧版逻辑）。"""
        sf = max(1.0, float(speed_factor))
        peak = sf
        if drift_state is not None:
            peak = max(sf, float(drift_state.get("peak_speed_factor", 1.0)))
        return min(110.0, self.TRACK_MAX_JUMP_BASE + peak * 2.0)

    def _trail_jump_limit(self, drift_state=None, speed_factor=1.0):
        """轨迹落笔允许的最大段长（随实测位移与倍速放宽）。"""
        ds = drift_state or {}
        sf = max(1.0, float(speed_factor))
        peak = max(sf, float(ds.get("peak_speed_factor", 1.0)))
        step = self._peak_frame_step(ds)
        return min(240.0, max(32.0 + peak * 5.0, step * 2.4))

    def _tune_smoother_for_speed(self, smoother, speed_factor, drift_state=None):
        if smoother is None:
            return
        sf = max(1.0, float(speed_factor))
        peak = sf
        if drift_state is not None:
            peak = max(sf, float(drift_state.get("peak_speed_factor", 1.0)))
        smoother.instant_bind = False
        smoother.min_step = max(1.5, self.TRACK_MIN_STEP * (1.2 / max(1.0, peak ** 0.32)))
        smoother.bbox_alpha = min(0.58, self.TRACK_BBOX_ALPHA + peak * 0.004)
        smoother.center_alpha = min(0.55, self.TRACK_CENTER_ALPHA + peak * 0.006)
        if peak >= 18.0:
            smoother.trail_alpha = 0.78
        elif peak >= 6.0:
            smoother.trail_alpha = min(0.72, self.TRACK_TRAIL_ALPHA + peak * 0.012)
        else:
            smoother.trail_alpha = min(0.62, self.TRACK_TRAIL_ALPHA + peak * 0.008)
        smoother.perp_damp = 1.0

    def _dampen_lateral_bbox(self, bbox, smoother, speed_factor):
        """沿运动方向保留位移，抑制垂直于运动方向的帧间抖动（仅常速）。"""
        if smoother is not None and getattr(smoother, "instant_bind", False):
            return bbox
        if smoother is None or smoother._center is None:
            return bbox
        sf = max(1.0, float(speed_factor))
        if sf < 5.0:
            return bbox
        vx, vy = smoother._velocity
        spd2 = vx * vx + vy * vy
        if spd2 < 9.0:
            return bbox
        spd = spd2 ** 0.5
        ux, uy = vx / spd, vy / spd
        damp = max(0.06, 0.42 / (sf ** 0.22))

        x, y, w, h = [float(v) for v in bbox]
        cx, cy = x + w / 2.0, y + h / 2.0
        ox, oy = smoother._center
        dx, dy = cx - ox, cy - oy
        parallel = dx * ux + dy * uy
        px, py = dx - parallel * ux, dy - parallel * uy
        ncx = ox + parallel * ux + px * damp
        ncy = oy + parallel * uy + py * damp
        return [ncx - w / 2.0, ncy - h / 2.0, w, h]

    def _extract_template(self, frame, bbox):
        x, y, w, h = [int(v) for v in bbox]
        x = max(0, min(x, self.FRAME_WIDTH - 1))
        y = max(0, min(y, self.FRAME_HEIGHT - 1))
        w = max(4, min(w, self.FRAME_WIDTH - x))
        h = max(4, min(h, self.FRAME_HEIGHT - y))
        roi = frame[y:y + h, x:x + w]
        if roi.size == 0:
            return None
        return cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    def _learn_color_model(self, frame, bbox):
        """从用户框选区域学习机器人颜色特征，用于后续纠偏。"""
        x, y, w, h = [int(v) for v in bbox]
        x = max(0, min(x, self.FRAME_WIDTH - 1))
        y = max(0, min(y, self.FRAME_HEIGHT - 1))
        w = max(2, min(w, self.FRAME_WIDTH - x))
        h = max(2, min(h, self.FRAME_HEIGHT - y))
        roi = frame[y:y + h, x:x + w]
        if roi.size == 0:
            return None
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        h_ch, s_ch, v_ch = cv2.split(hsv)
        valid = (s_ch > 50) & (v_ch > 55)
        if np.count_nonzero(valid) < 12:
            valid = (s_ch > 35) & (v_ch > 40)
        if np.count_nonzero(valid) < 8:
            valid = np.ones(h_ch.shape, dtype=bool)
        h_vals = h_ch[valid]
        s_vals = s_ch[valid]
        v_vals = v_ch[valid]
        h_lo = int(np.percentile(h_vals, 10))
        h_hi = int(np.percentile(h_vals, 90))
        s_lo = int(max(45, np.percentile(s_vals, 12) - 18))
        v_lo = int(max(40, np.percentile(v_vals, 12) - 30))
        lower = np.array([max(0, h_lo - 8), s_lo, v_lo], dtype=np.uint8)
        upper = np.array([min(179, h_hi + 8), 255, 255], dtype=np.uint8)
        return {
            "lower": lower,
            "upper": upper,
            "ref_area": float(w * h),
            "ref_wh": (float(w), float(h)),
        }

    def _bbox_color_score(self, frame, bbox, color_model):
        if color_model is None:
            return 1.0
        x, y, w, h = [int(v) for v in bbox]
        if w <= 1 or h <= 1:
            return 0.0
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(self.FRAME_WIDTH, x + w), min(self.FRAME_HEIGHT, y + h)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.0
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, color_model["lower"], color_model["upper"])
        return cv2.countNonZero(mask) / float(mask.size)

    def _bbox_green_ratio(self, frame, bbox):
        x, y, w, h = [int(v) for v in bbox]
        if w <= 1 or h <= 1:
            return 0.0
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(self.FRAME_WIDTH, x + w), min(self.FRAME_HEIGHT, y + h)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.0
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array([35, 35, 35], dtype=np.uint8),
                            np.array([95, 255, 255], dtype=np.uint8))
        return cv2.countNonZero(green) / float(green.size)

    def _bbox_mean_saturation(self, frame, bbox):
        x, y, w, h = [int(v) for v in bbox]
        if w <= 1 or h <= 1:
            return 0.0
        roi = frame[max(0, y):min(self.FRAME_HEIGHT, y + h),
        max(0, x):min(self.FRAME_WIDTH, x + w)]
        if roi.size == 0:
            return 0.0
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        return float(np.mean(hsv[:, :, 1]))

    def _bbox_center(self, bbox_or_point):
        vals = [float(v) for v in bbox_or_point]
        if len(vals) == 2:
            return vals[0], vals[1]
        x, y, w, h = vals[:4]
        return x + w / 2.0, y + h / 2.0

    def _bbox_center_dist(self, bbox_a, bbox_b):
        ax, ay = self._bbox_center(bbox_a)
        bx, by = self._bbox_center(bbox_b)
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    def _bbox_target_confidence(self, frame, bbox, color_model):
        if color_model is None:
            return 1.0
        if self._bbox_green_ratio(frame, bbox) > self.TRACK_GREEN_MAX_RATIO:
            return 0.0
        sat = self._bbox_mean_saturation(frame, bbox)
        if sat < self.TRACK_MIN_SATURATION:
            return 0.0
        color_score = self._bbox_color_score(frame, bbox, color_model)
        return color_score * min(1.0, sat / 85.0)

    def _region_search_mask(self, region_contour=None, region_mask=None):
        if region_mask is not None:
            return region_mask
        if region_contour is None:
            return None
        mask = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH), dtype=np.uint8)
        contour = np.asarray(region_contour, dtype=np.int32)
        if contour.ndim == 2:
            contour = contour.reshape(-1, 1, 2)
        cv2.fillPoly(mask, [contour], 255)
        return mask

    def _recover_bbox_by_color(
            self,
            frame,
            color_model,
            hint_center=None,
            search_radius=120,
            region_contour=None,
            region_mask=None,
    ):
        """在有效区域内按颜色搜索机器人，纠正 MIL 跟到轨迹线/池底纹理的情况。"""
        if color_model is None:
            return None

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, color_model["lower"], color_model["upper"])
        sat_floor = int(max(self.TRACK_MIN_SATURATION - 5, color_model["lower"][1]))
        sat_mask = cv2.inRange(hsv[:, :, 1], np.array([sat_floor], dtype=np.uint8), np.array([255], dtype=np.uint8))
        mask = cv2.bitwise_and(mask, sat_mask)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

        region = self._region_search_mask(region_contour, region_mask)
        if region is not None:
            mask = cv2.bitwise_and(mask, region)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        ref_area = color_model["ref_area"]
        ref_w, ref_h = color_model["ref_wh"]
        best_box = None
        best_score = -1.0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < ref_area * 0.12 or area > ref_area * 5.0:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            if w < 4 or h < 4:
                continue
            aspect = w / float(h)
            if aspect < 0.25 or aspect > 4.0:
                continue
            cx, cy = x + w / 2.0, y + h / 2.0
            box = (x, y, w, h)
            conf = self._bbox_target_confidence(frame, box, color_model)
            if conf < self.TRACK_COLOR_MIN_SCORE * 0.8:
                continue
            if self._bbox_green_ratio(frame, box) > self.TRACK_GREEN_MAX_RATIO:
                continue
            area_score = 1.0 - min(1.0, abs(area - ref_area) / max(ref_area, 1.0))
            size_score = 1.0 - min(
                1.0,
                (abs(w - ref_w) / max(ref_w, 1.0) + abs(h - ref_h) / max(ref_h, 1.0)) * 0.5,
            )
            if hint_center is not None:
                dist = ((cx - hint_center[0]) ** 2 + (cy - hint_center[1]) ** 2) ** 0.5
                if dist > search_radius:
                    continue
                dist_score = 1.0 - dist / search_radius
            else:
                dist_score = 0.35
            score = conf * 0.45 + area_score * 0.2 + size_score * 0.15 + dist_score * 0.2
            if score > best_score:
                best_score = score
                best_box = box
        return best_box

    def _match_template_bbox(
            self,
            frame,
            template,
            hint_center=None,
            search_radius=150,
            region_mask=None,
    ):
        if template is None or template.size == 0:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        th, tw = template.shape[:2]
        if th < 4 or tw < 4:
            return None

        if hint_center is not None:
            hx, hy = int(hint_center[0]), int(hint_center[1])
            pad = int(search_radius)
            x1 = max(0, hx - pad - tw)
            y1 = max(0, hy - pad - th)
            x2 = min(gray.shape[1], hx + pad + tw)
            y2 = min(gray.shape[0], hy + pad + th)
            search = gray[y1:y2, x1:x2]
            offset = (x1, y1)
        elif region_mask is not None:
            ys, xs = np.where(region_mask > 0)
            if len(xs) == 0:
                return None
            x1, x2 = int(xs.min()), int(xs.max())
            y1, y2 = int(ys.min()), int(ys.max())
            search = gray[y1:y2 + 1, x1:x2 + 1]
            offset = (x1, y1)
        else:
            search = gray
            offset = (0, 0)

        if search.shape[0] < th or search.shape[1] < tw:
            return None
        res = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val < 0.40:
            return None
        x, y = max_loc
        return (offset[0] + x, offset[1] + y, tw, th)

    def _hint_search_radius(self, speed_factor):
        sf = max(1.0, float(speed_factor))
        return int(170 * max(1.0, sf ** 0.65))

    def _max_jump_distance(self, smoother, speed_factor):
        sf = max(1.0, float(speed_factor))
        if smoother is None or smoother._center is None:
            return min(self.TRACK_MAX_JUMP_BASE * sf, 28.0 + sf * 2.8)
        limit = self._adaptive_jump_limit(smoother, sf)
        cap = 38.0 + sf * 4.0
        return min(limit, cap)

    def _source_agree_distance(self, speed_factor):
        sf = max(1.0, float(speed_factor))
        return self.TRACK_SOURCE_AGREE_DIST + sf * 1.2

    def _mil_color_max_distance(self, speed_factor):
        sf = max(1.0, float(speed_factor))
        return self.TRACK_MIL_COLOR_MAX_DIST + sf * 1.5

    def _velocity_hint(self, smoother, drift_state):
        """框停住时用历史速度外推搜索中心。"""
        if smoother is None:
            return None
        base = smoother.bind_point or smoother.live_center
        if base is None:
            return None
        vx, vy = smoother._velocity
        spd = (vx * vx + vy * vy) ** 0.5
        stagnant = drift_state.get("stagnant_frames", 0) if drift_state else 0
        peak = max(1.0, float(drift_state.get("peak_speed_factor", 1.0)) if drift_state else 1.0)
        if spd < 1.5 and stagnant < 4:
            return self._predict_center(smoother) or base
        steps = max(1, min(14, stagnant // 2 + 2))
        boost = min(4.0, max(1.0, peak ** 0.42))
        hx = base[0] + vx * steps * boost
        hy = base[1] + vy * steps * boost
        return (
            max(0.0, min(float(self.FRAME_WIDTH), hx)),
            max(0.0, min(float(self.FRAME_HEIGHT), hy)),
        )

    def _tracking_hint(self, smoother, drift_state=None):
        stagnant = drift_state.get("stagnant_frames", 0) if drift_state else 0
        lock_lost = drift_state.get("lock_lost", 0) if drift_state else 0
        if stagnant >= 4 or lock_lost >= 1:
            vhint = self._velocity_hint(smoother, drift_state)
            if vhint is not None:
                return vhint
        if drift_state is not None and lock_lost >= 1:
            last_good = drift_state.get("last_good_bbox")
            if last_good is not None:
                return self._bbox_center(last_good)
        if smoother is None:
            return None
        return self._predict_center(smoother) or smoother.bind_point

    def _note_bbox_stagnation(self, drift_state, bbox):
        """记录跟踪框是否连续多帧几乎不动（MIL 卡死时触发全区域重搜）。"""
        if bbox is None:
            return
        center = self._bbox_center(bbox)
        prev = drift_state.get("last_resolved_center")
        if prev is not None:
            dist = ((center[0] - prev[0]) ** 2 + (center[1] - prev[1]) ** 2) ** 0.5
            if dist < 2.5:
                drift_state["stagnant_frames"] = drift_state.get("stagnant_frames", 0) + 1
            else:
                drift_state["stagnant_frames"] = 0
        drift_state["last_resolved_center"] = center

    def _is_target_locked(self, frame, bbox, color_model, template=None, drift_state=None):
        """判断当前框是否仍锁定在机器人上（非轨迹线/污渍）。"""
        if drift_state and drift_state.get("bootstrap_frames", 0) > 0:
            return bbox is not None
        if bbox is None or color_model is None:
            return bbox is not None
        conf = self._bbox_target_confidence(frame, bbox, color_model)
        if conf < self.TRACK_LOCK_MIN_SCORE * 0.75:
            return False
        if self._bbox_green_ratio(frame, bbox) > self.TRACK_GREEN_MAX_RATIO:
            return False
        if template is not None and template.size > 0:
            x, y, w, h = [int(v) for v in bbox]
            x1, y1 = max(0, x), max(0, y)
            x2, y2 = min(self.FRAME_WIDTH, x + w), min(self.FRAME_HEIGHT, y + h)
            roi = frame[y1:y2, x1:x2]
            th, tw = template.shape[:2]
            if roi.size > 0 and roi.shape[0] >= th and roi.shape[1] >= tw:
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                if float(res.max()) < 0.30:
                    return False
        return True

    def _bootstrap_tracking(
            self,
            smoother,
            init_box,
            drift_state,
            all_track_points=None,
            coverage_points=None,
            trail_draw_state=None,
            coverage_draw_state=None,
            reconnect=False,
            region_contour=None,
            region_mask=None,
            coverage_region_contour=None,
            coverage_region_mask=None,
    ):
        """框选/重标注目标后初始化平滑器与轨迹起点。"""
        ibox = [float(v) for v in init_box]
        drift_state["last_good_bbox"] = tuple(ibox)
        drift_state["init_center"] = self._bbox_center(ibox)
        drift_state["bootstrap_frames"] = 45
        drift_state["lock_lost"] = 0
        drift_state["track_fail_streak"] = 0
        drift_state["stagnant_frames"] = 0
        drift_state["reacquire_frames"] = 12
        drift_state["stagnant_announced"] = False
        drift_state["last_resolved_center"] = self._bbox_center(ibox)
        drift_state["last_raw_center"] = self._bbox_center(ibox)
        drift_state["mil_low_streak"] = 0
        drift_state["trail_break"] = False
        drift_state["stable_bbox"] = tuple(ibox)
        drift_state["stable_source"] = "init"
        if smoother is not None:
            smoother.reset()
            color_model = drift_state.get("color_model")
            if color_model:
                smoother.ref_wh = color_model["ref_wh"]
        cx, cy = self._bbox_center(ibox)
        trail_point = (int(round(cx)), int(round(cy)))
        if smoother is not None:
            _bind, trail_point, _sb, _rec = smoother.update(ibox)
            if _bind is not None:
                trail_point = _bind
        tip = trail_point
        trail_limit = self._trail_jump_limit(
            drift_state, self._get_speed_factor(drift_state, smoother))
        reconnect_gap = max(trail_limit, float(getattr(self, "TRACK_RECONNECT_MAX_GAP", 900.0)))
        # 重标注：显示轨迹始终连接断点→新起点，避免出现空白缺口
        if all_track_points is not None:
            if trail_draw_state is not None:
                trail_draw_state.pop("skip_connect", None)
            if reconnect and len(all_track_points) >= 1:
                last = all_track_points[-1]
                dist = ((tip[0] - last[0]) ** 2 + (tip[1] - last[1]) ** 2) ** 0.5
                if dist > reconnect_gap:
                    # 超远距离仍强制连线，保证视觉连续
                    self._append_trail_point(
                        all_track_points, tip, max_segment=reconnect_gap, force=True)
                else:
                    self._append_trail_point(
                        all_track_points, tip, max_segment=max(trail_limit, 120.0), force=True)
            else:
                self._append_trail_point(
                    all_track_points, tip, max_segment=max(trail_limit, 480.0), force=True)
        # 覆盖率：仅黄框内落点；重标注断点跨越大时不硬连，避免虚增覆盖率
        if coverage_points is not None and self._center_in_region(
                cx, cy,
                coverage_region_contour if coverage_region_contour is not None else region_contour,
                coverage_region_mask if coverage_region_mask is not None else region_mask,
        ):
            if coverage_draw_state is not None and reconnect and len(coverage_points) >= 1:
                last = coverage_points[-1]
                dist = ((tip[0] - last[0]) ** 2 + (tip[1] - last[1]) ** 2) ** 0.5
                if dist > trail_limit * 1.2:
                    coverage_draw_state["skip_connect"] = True
                else:
                    coverage_draw_state.pop("skip_connect", None)
            self._append_trail_point(
                coverage_points, tip, max_segment=max(trail_limit, 480.0), force=True)
        return tip, [int(round(v)) for v in ibox]

    def _reacquire_target_bbox(
            self,
            frame,
            color_model,
            template,
            drift_state,
            speed_factor,
            region_contour=None,
            region_mask=None,
    ):
        """失锁后在可靠位置附近重新搜索机器人。"""
        hint = None
        last_good = drift_state.get("last_good_bbox")
        if last_good is not None:
            hint = self._bbox_center(last_good)
        elif drift_state.get("init_center") is not None:
            hint = drift_state["init_center"]

        sf = max(1.0, float(speed_factor))
        region = self._region_search_mask(region_contour, region_mask)
        radii = [
            int(self._hint_search_radius(sf) * 1.6),
            int(self._hint_search_radius(sf) * 2.8),
            int(self._hint_search_radius(sf) * 4.0),
        ]
        best_box = None
        best_score = -1.0
        strict_lock = drift_state.get("lock_lost", 0) < 4
        for radius in radii:
            color_box = self._recover_bbox_by_color(
                frame, color_model, hint_center=hint, search_radius=radius,
                region_contour=region_contour, region_mask=region_mask,
            )
            tpl_box = self._match_template_bbox(
                frame, template, hint_center=hint, search_radius=radius, region_mask=region,
            )
            for box in (color_box, tpl_box):
                if box is None:
                    continue
                box = self._snap_bbox_to_ref_size(box, color_model)
                if strict_lock and not self._is_target_locked(
                        frame, box, color_model, template, drift_state,
                ):
                    continue
                conf = self._bbox_target_confidence(frame, box, color_model)
                score = conf
                if hint is not None:
                    dist = self._bbox_center_dist(box, hint)
                    score += max(0.0, 1.0 - dist / max(radius, 1)) * 0.35
                if score > best_score:
                    best_score = score
                    best_box = box
            if best_box is not None:
                break
        return best_box

    def _is_plausible_bbox(self, bbox, smoother, speed_factor, hint=None, drift_state=None):
        if drift_state and drift_state.get("bootstrap_frames", 0) > 0:
            return True
        if smoother is None or smoother._center is None:
            return True
        ref = hint or self._tracking_hint(smoother, drift_state)
        if ref is None:
            return True
        return self._bbox_center_dist(bbox, ref) <= self._max_jump_distance(smoother, speed_factor)

    def _filter_candidates_by_hint(self, candidates, hint, speed_factor):
        if hint is None or not candidates:
            return candidates
        radius = self._hint_search_radius(speed_factor) * 1.25
        filtered = [
            item for item in candidates
            if self._bbox_center_dist(item[1], hint) <= radius
        ]
        if filtered:
            return filtered
        return [min(candidates, key=lambda item: self._bbox_center_dist(item[1], hint))]

    def _snap_bbox_to_ref_size(self, bbox, color_model):
        """保持用户框选时的宽高，只更新中心，避免颜色轮廓不对称导致框偏移。"""
        if color_model is None:
            return [float(v) for v in bbox]
        ref_w, ref_h = color_model["ref_wh"]
        x, y, w, h = [float(v) for v in bbox]
        cx, cy = x + w / 2.0, y + h / 2.0
        nw = max(4.0, float(ref_w))
        nh = max(4.0, float(ref_h))
        nx = max(0.0, min(cx - nw / 2.0, self.FRAME_WIDTH - nw))
        ny = max(0.0, min(cy - nh / 2.0, self.FRAME_HEIGHT - nh))
        return [nx, ny, nw, nh]

    def _mil_is_reliable(self, frame, mil_bbox, color_model, color_bbox=None, hint=None, speed_factor=1.0):
        if mil_bbox is None:
            return False
        if color_model is not None:
            conf = self._bbox_target_confidence(frame, mil_bbox, color_model)
            if conf < self.TRACK_COLOR_MIN_SCORE * 0.88:
                return False
        if color_bbox is not None:
            if self._bbox_center_dist(mil_bbox, color_bbox) > self._mil_color_max_distance(speed_factor):
                return False
        if hint is not None:
            if self._bbox_center_dist(mil_bbox, hint) > self._max_jump_distance(None, speed_factor) * 1.05:
                return False
        return True

    def _pick_consensus_bbox(
            self,
            frame,
            mil_bbox,
            color_bbox,
            template_bbox,
            color_model,
            hint,
            smoother,
            speed_factor,
    ):
        """多源一致性：颜色/模板一致时优先；MIL 与二者分歧过大则拒绝 MIL。"""
        agree = self._source_agree_distance(speed_factor)
        mil_max = self._mil_color_max_distance(speed_factor)

        aux_boxes = []
        if color_bbox is not None:
            aux_boxes.append(("color", color_bbox))
        if template_bbox is not None:
            aux_boxes.append(("template", template_bbox))

        if len(aux_boxes) >= 2:
            d_ct = self._bbox_center_dist(color_bbox, template_bbox)
            if d_ct <= agree:
                cx = (self._bbox_center(color_bbox)[0] + self._bbox_center(template_bbox)[0]) * 0.5
                cy = (self._bbox_center(color_bbox)[1] + self._bbox_center(template_bbox)[1]) * 0.5
                if mil_bbox is not None and self._bbox_center_dist(mil_bbox, (cx, cy)) > mil_max:
                    return self._snap_bbox_to_ref_size(color_bbox, color_model), "color"
                if mil_bbox is not None and self._mil_is_reliable(
                        frame, mil_bbox, color_model, color_bbox=color_bbox,
                        hint=hint, speed_factor=speed_factor,
                ):
                    return self._snap_bbox_to_ref_size(
                        self._nudge_bbox_toward(mil_bbox, (cx, cy), blend=0.10),
                        color_model,
                    ), "mil"
                return self._snap_bbox_to_ref_size(color_bbox, color_model), "color"

        if color_bbox is not None and mil_bbox is not None:
            d_mc = self._bbox_center_dist(mil_bbox, color_bbox)
            if d_mc > mil_max:
                if self._bbox_target_confidence(frame, color_bbox, color_model) >= self.TRACK_COLOR_MIN_SCORE * 0.85:
                    return self._snap_bbox_to_ref_size(color_bbox, color_model), "color"
                return None, None
            if self._mil_is_reliable(
                    frame, mil_bbox, color_model, color_bbox=color_bbox,
                    hint=hint, speed_factor=speed_factor,
            ):
                return self._snap_bbox_to_ref_size(
                    self._nudge_bbox_toward(mil_bbox, self._bbox_center(color_bbox)),
                    color_model,
                ), "mil"

        if mil_bbox is not None and self._mil_is_reliable(
                frame, mil_bbox, color_model, color_bbox=color_bbox,
                hint=hint, speed_factor=speed_factor,
        ):
            return self._snap_bbox_to_ref_size(mil_bbox, color_model), "mil"
        if color_bbox is not None:
            if hint is None or self._bbox_center_dist(color_bbox, hint) <= self._max_jump_distance(smoother,
                                                                                                   speed_factor):
                return self._snap_bbox_to_ref_size(color_bbox, color_model), "color"
        if template_bbox is not None:
            if hint is None or self._bbox_center_dist(template_bbox, hint) <= self._max_jump_distance(smoother,
                                                                                                      speed_factor):
                return self._snap_bbox_to_ref_size(template_bbox, color_model), "template"
        return None, None

    def _nudge_bbox_toward(self, base_bbox, target_center, blend=None):
        if blend is None:
            blend = self.TRACK_MIL_NUDGE_BLEND
        bx, by = self._bbox_center(base_bbox)
        tx, ty = target_center
        cx = bx * (1.0 - blend) + tx * blend
        cy = by * (1.0 - blend) + ty * blend
        w, h = float(base_bbox[2]), float(base_bbox[3])
        return [cx - w / 2.0, cy - h / 2.0, w, h]

    def _score_bbox_candidate(self, frame, bbox, color_model, hint, source_weight, speed_factor=1.0):
        conf = self._bbox_target_confidence(frame, bbox, color_model)
        if conf < self.TRACK_COLOR_MIN_SCORE * 0.75:
            return -1.0
        if self._bbox_green_ratio(frame, bbox) > self.TRACK_GREEN_MAX_RATIO * 0.65:
            return -1.0
        cx, cy = self._bbox_center(bbox)
        score = conf * source_weight
        if hint is not None:
            dist = ((cx - hint[0]) ** 2 + (cy - hint[1]) ** 2) ** 0.5
            hint_r = self._hint_search_radius(speed_factor) * 1.25
            if dist > hint_r:
                return -1.0
            score += max(0.0, 1.0 - dist / hint_r) * 0.55
        sat = self._bbox_mean_saturation(frame, bbox)
        score += min(0.22, sat / 320.0)
        return score

    def _near_track_center(self, bbox, smoother, drift_state, speed_factor, slack=1.25):
        """候选框必须在当前跟踪轨迹附近，防止颜色误匹配跳到远处。"""
        if bbox is None:
            return False
        ref = None
        if smoother is not None:
            ref = smoother.bind_point or smoother.live_center
        if ref is None and drift_state is not None:
            last_good = drift_state.get("last_good_bbox")
            if last_good is not None:
                ref = self._bbox_center(last_good)
        if ref is None:
            return True
        limit = self._max_jump_distance(smoother, speed_factor) * slack
        return self._bbox_center_dist(bbox, ref) <= limit

    def _aux_sources_agree(self, color_bbox, template_bbox, speed_factor):
        if color_bbox is None or template_bbox is None:
            return False
        return self._bbox_center_dist(color_bbox, template_bbox) <= self._source_agree_distance(
            speed_factor
        )

    def _resolve_tracking_bbox(
            self,
            frame,
            tracker,
            smoother,
            drift_state,
            region_contour=None,
            region_mask=None,
    ):
        """MIL 为主，颜色仅在近距离微调（对齐旧版稳定策略）。"""
        drift_state["frame_idx"] = drift_state.get("frame_idx", 0) + 1
        color_model = drift_state.get("color_model")
        hint = None
        if smoother is not None and smoother._center is not None:
            hint = smoother.live_center
        elif drift_state.get("last_good_bbox") is not None:
            hint = self._bbox_center(drift_state["last_good_bbox"])
        speed_factor = self._get_speed_factor(drift_state, smoother)
        drift_state["speed_factor"] = speed_factor

        mil_ok, raw_bbox = tracker.update(self._prepare_track_frame(frame, drift_state))
        if not mil_ok:
            recovered = self._recover_on_track_fail(
                frame, tracker, smoother, drift_state, color_model,
                region_contour, region_mask, hint=hint,
            )
            if recovered is not None:
                drift_state["last_good_bbox"] = tuple(float(v) for v in recovered)
                drift_state["lock_lost"] = 0
                drift_state["stable_source"] = "color"
                return recovered, "color", True
            last_good = drift_state.get("last_good_bbox")
            if last_good is not None:
                drift_state["lock_lost"] = drift_state.get("lock_lost", 0) + 1
                return [float(v) for v in last_good], "hold", True
            return None, None, False

        mil_bbox = self._snap_bbox_to_ref_size([float(v) for v in raw_bbox], color_model)
        search_hint = drift_state.get("last_raw_center")
        if search_hint is None and drift_state.get("last_good_bbox") is not None:
            search_hint = self._bbox_center(drift_state["last_good_bbox"])
        if search_hint is None:
            search_hint = hint
        if search_hint is not None and color_model is not None:
            local_r = min(110, int(self._hint_search_radius(speed_factor) * 0.55))
            color_bbox = self._recover_bbox_by_color(
                frame, color_model, hint_center=search_hint, search_radius=local_r,
                region_contour=region_contour, region_mask=region_mask,
            )
            if color_bbox is not None:
                dist_mc = self._bbox_center_dist(mil_bbox, color_bbox)
                mil_conf = self._bbox_target_confidence(frame, mil_bbox, color_model)
                color_conf = self._bbox_target_confidence(frame, color_bbox, color_model)
                if dist_mc < 55 and color_conf >= self.TRACK_COLOR_MIN_SCORE * 0.55:
                    blend = 0.08
                    if speed_factor >= 12.0 and color_conf >= mil_conf * 0.88:
                        blend = min(0.38, 0.12 + speed_factor * 0.010)
                    elif dist_mc < 38 and mil_conf >= self.TRACK_COLOR_MIN_SCORE * 0.50:
                        blend = 0.14
                    mil_bbox = self._nudge_bbox_toward(
                        mil_bbox, self._bbox_center(color_bbox), blend=blend)

        drift_state["last_good_bbox"] = tuple(float(v) for v in mil_bbox)
        drift_state["lock_lost"] = 0
        drift_state["stable_source"] = "mil"
        return mil_bbox, "mil", True

    def _recover_on_track_fail(
            self,
            frame,
            tracker,
            smoother,
            drift_state,
            color_model,
            region_contour=None,
            region_mask=None,
            hint=None,
    ):
        """MIL 失锁时在预测位置附近用颜色/模板快速找回（30x 等高速视频）。"""
        sf = max(
            self._get_speed_factor(drift_state, smoother),
            float(drift_state.get("peak_speed_factor", 1.0)),
        )
        search_hint = hint
        lock_lost = drift_state.get("lock_lost", 0)
        if lock_lost >= 6:
            search_hint = self._velocity_hint(smoother, drift_state) or hint
        if search_hint is None and drift_state.get("last_good_bbox") is not None:
            search_hint = self._bbox_center(drift_state["last_good_bbox"])
        radius = int(self._hint_search_radius(sf) * (1.85 if sf >= 12.0 else 1.35))
        region = self._region_search_mask(region_contour, region_mask)
        color_bbox = self._recover_bbox_by_color(
            frame, color_model, hint_center=search_hint, search_radius=radius,
            region_contour=region_contour, region_mask=region_mask,
        )
        template_bbox = self._match_template_bbox(
            frame, drift_state.get("template"), hint_center=search_hint,
            search_radius=radius, region_mask=region,
        )
        best = None
        best_conf = -1.0
        for cand in (color_bbox, template_bbox):
            if cand is None:
                continue
            conf = self._bbox_target_confidence(frame, cand, color_model)
            if conf > best_conf:
                best_conf = conf
                best = cand
        # 失锁时适当放宽置信度，优先找回目标
        if best is None or best_conf < self.TRACK_COLOR_MIN_SCORE * 0.55:
            return None
        best = self._snap_bbox_to_ref_size(best, color_model)
        self._try_reinit_tracker(tracker, frame, best, drift_state)
        return [float(v) for v in best]

    def _correct_bbox_with_color(
            self,
            frame,
            bbox,
            tracker,
            smoother,
            drift_state,
            region_contour=None,
            region_mask=None,
    ):
        color_model = drift_state.get("color_model")
        if color_model is None:
            return bbox

        confidence = self._bbox_target_confidence(frame, bbox, color_model)
        if confidence >= self.TRACK_COLOR_MIN_SCORE:
            drift_state["color_miss"] = 0
            return bbox

        hint = self._predict_center(smoother) or smoother.live_center
        radius = min(320, 100 + drift_state.get("color_miss", 0) * 35)
        recovered = self._recover_bbox_by_color(
            frame,
            color_model,
            hint_center=hint,
            search_radius=radius,
            region_contour=region_contour,
            region_mask=region_mask,
        )
        if recovered is None and drift_state.get("color_miss", 0) >= 1:
            recovered = self._recover_bbox_by_color(
                frame,
                color_model,
                hint_center=None,
                search_radius=9999,
                region_contour=region_contour,
                region_mask=region_mask,
            )

        drift_state["color_miss"] = drift_state.get("color_miss", 0) + 1
        if recovered is None:
            return None

        if drift_state["color_miss"] <= 2 or drift_state["color_miss"] % 10 == 0:
            print("跟踪框偏离机器人，已根据颜色特征自动纠正")
        drift_state["color_miss"] = 0
        self._try_reinit_tracker(tracker, frame, recovered, drift_state)
        return [float(v) for v in recovered]

    def _predict_center(self, smoother):
        if smoother._center is None:
            return None
        return (
            smoother._center[0] + smoother._velocity[0],
            smoother._center[1] + smoother._velocity[1],
        )

    def _adaptive_jump_limit(self, smoother, speed_factor=1.0):
        speed = (smoother._velocity[0] ** 2 + smoother._velocity[1] ** 2) ** 0.5
        sf = max(1.0, float(speed_factor))
        return max(
            self.TRACK_MAX_JUMP_BASE * sf,
            speed * self.TRACK_MAX_JUMP_SPEED_FACTOR * max(1.0, sf ** 0.35) + 14.0 * (sf ** 0.5),
        )

    def _clamp_bbox_jump(self, bbox, smoother, speed_factor=1.0):
        """大幅跳变时拒绝本帧位置（由上层维持上一帧），小幅跳变才钳位。"""
        if smoother._center is None:
            return bbox, False
        x, y, w, h = [float(v) for v in bbox]
        cx, cy = x + w / 2.0, y + h / 2.0
        px, py = self._predict_center(smoother)
        dx, dy = cx - px, cy - py
        dist = (dx * dx + dy * dy) ** 0.5
        limit = self._max_jump_distance(smoother, speed_factor)
        hard_reject = limit * 1.35
        if dist > hard_reject:
            return bbox, True
        if dist <= limit:
            return bbox, False
        scale = limit / dist
        cx = px + dx * scale
        cy = py + dy * scale
        return [cx - w / 2.0, cy - h / 2.0, w, h], True

    def _predict_bbox(self, smoother):
        if smoother._bbox is None:
            return None
        vx, vy = smoother._velocity
        return [
            smoother._bbox[0] + vx,
            smoother._bbox[1] + vy,
            smoother._bbox[2],
            smoother._bbox[3],
        ]

    def _try_reinit_tracker(self, tracker, frame, bbox, drift_state=None):
        if bbox is None:
            return False
        x, y, w, h = [int(round(v)) for v in bbox]
        w, h = max(2, w), max(2, h)
        x = max(0, min(x, self.FRAME_WIDTH - w))
        y = max(0, min(y, self.FRAME_HEIGHT - h))
        init_box = (x, y, w, h)
        track_frame = self._prepare_track_frame(frame, drift_state)
        try:
            tracker.init(track_frame, init_box)
            return True
        except Exception:
            try:
                tracker.init(frame, init_box)
                return True
            except Exception as exc:
                logging.debug("tracker reinit failed: %s", exc)
                return False

    def _append_trail_point(self, all_track_points, point, max_segment=None, force=False):
        if point is None:
            return False
        if max_segment is None:
            max_segment = getattr(self, "TRACK_MAX_TRAIL_SEGMENT", 70.0)
        if all_track_points:
            last = all_track_points[-1]
            dist = ((point[0] - last[0]) ** 2 + (point[1] - last[1]) ** 2) ** 0.5
            if dist < 0.5:
                return False
            # 长跨度统一插值连线（含 force 重标注），避免显示缺口
            if dist > max_segment:
                steps = max(2, int(np.ceil(dist / max_segment)))
                added = False
                for i in range(1, steps + 1):
                    t = i / steps
                    mid = (
                        int(round(last[0] + t * (point[0] - last[0]))),
                        int(round(last[1] + t * (point[1] - last[1]))),
                    )
                    if not all_track_points or all_track_points[-1] != mid:
                        all_track_points.append(mid)
                        added = True
                return added
        if not all_track_points or all_track_points[-1] != point:
            all_track_points.append(point)
        return True

    def _record_trail_points(
            self,
            draw_point,
            raw_cx,
            raw_cy,
            source,
            smoother,
            trail_limit,
            all_track_points=None,
            coverage_points=None,
            coverage_region_contour=None,
            coverage_region_mask=None,
    ):
        """显示轨迹与绿框同用平滑中心；覆盖率用原始中心且仅限黄框内。"""
        if source == "hold" or smoother is None or draw_point is None:
            return
        min_move = max(0.8, smoother.min_step * 0.22)
        reconnect_gap = max(trail_limit, float(getattr(self, "TRACK_RECONNECT_MAX_GAP", 900.0)))

        if all_track_points is not None:
            should_draw = True
            force_connect = source in ("reacquire", "color")
            if all_track_points:
                last = all_track_points[-1]
                seg = ((draw_point[0] - last[0]) ** 2 + (draw_point[1] - last[1]) ** 2) ** 0.5
                if seg < min_move:
                    should_draw = False
                elif seg > trail_limit:
                    # 失锁重获等造成的大跨度：插值连接，不丢段
                    if force_connect or seg <= reconnect_gap:
                        self._append_trail_point(
                            all_track_points, draw_point, max_segment=trail_limit, force=True)
                        should_draw = False
                    else:
                        should_draw = False
            if should_draw:
                self._append_trail_point(all_track_points, draw_point, max_segment=trail_limit)

        if (
                coverage_points is not None
                and raw_cx is not None
                and raw_cy is not None
                and self._center_in_region(raw_cx, raw_cy, coverage_region_contour, coverage_region_mask)
        ):
            cov_point = (int(round(raw_cx)), int(round(raw_cy)))
            should_cov = True
            if coverage_points:
                last = coverage_points[-1]
                seg = ((cov_point[0] - last[0]) ** 2 + (cov_point[1] - last[1]) ** 2) ** 0.5
                if seg < min_move:
                    should_cov = False
            if should_cov:
                self._append_trail_point(coverage_points, cov_point, max_segment=trail_limit)

    def _trail_live_tip(self, smoother, draw_point):
        """轨迹尾段与平滑框中心一致。"""
        if smoother is not None:
            bp = smoother.bind_point
            if bp is not None:
                return bp
        return draw_point

    def _hold_last_valid_track(
            self, smoother, all_track_points=None, predict_forward=False, drift_state=None,
    ):
        last_good = drift_state.get("last_good_bbox") if drift_state else None
        lock_lost = drift_state.get("lock_lost", 0) if drift_state else 0
        if last_good is not None:
            bbox = [int(round(v)) for v in last_good]
            cx, cy = self._bbox_center(bbox)
            center = (int(round(cx)), int(round(cy)))
            return center, bbox, self._trail_live_tip(smoother, center)
        if smoother is None or smoother._bbox is None:
            return None, None, None
        center = smoother.bind_point or smoother.live_center
        bbox = [int(round(v)) for v in smoother._bbox]
        if bbox[2] <= 0:
            bbox[2] = 1
        if bbox[3] <= 0:
            bbox[3] = 1
        if predict_forward and lock_lost == 0 and smoother._center is not None:
            px, py = self._predict_center(smoother)
            center = (int(round(px)), int(round(py)))
            bbox[0] = int(round(bbox[0] + smoother._velocity[0]))
            bbox[1] = int(round(bbox[1] + smoother._velocity[1]))
            if all_track_points is not None:
                self._append_trail_point(all_track_points, center)
        return center, bbox, self._trail_live_tip(smoother, center)

    def _center_in_region(self, cx, cy, contour=None, mask=None):
        """跟踪中心是否在有效区域内（池边允许框体部分超出黄线）。"""
        if contour is not None and cv2.pointPolygonTest(contour, (float(cx), float(cy)), False) < 0:
            return False
        if mask is not None:
            h, w = mask.shape[:2]
            ix, iy = int(round(cx)), int(round(cy))
            if not (0 <= ix < w and 0 <= iy < h and mask[iy, ix] > 0):
                return False
        return True

    def _track_in_region(self, bbox, contour=None, mask=None):
        """运行时跟踪：中心点在区域内即可，避免池边框体越界导致轨迹中断。"""
        if contour is None and mask is None:
            return True
        cx, cy = self._bbox_center(bbox)
        return self._center_in_region(cx, cy, contour, mask)

    def _bbox_in_contour(self, bbox, contour, min_inside_ratio=None):
        """检查跟踪框中心与主体是否在用户划定的有效区域内。"""
        if contour is None:
            return True
        ratio = self.TRACK_REGION_MIN_INSIDE if min_inside_ratio is None else min_inside_ratio
        x, y, w, h = [float(v) for v in bbox]
        if w <= 1 or h <= 1:
            return False
        cx, cy = x + w / 2.0, y + h / 2.0
        if cv2.pointPolygonTest(contour, (cx, cy), False) < 0:
            return False
        inside = 0
        total = 0
        for uy in (0.2, 0.5, 0.8):
            for ux in (0.2, 0.5, 0.8):
                px = x + w * ux
                py = y + h * uy
                total += 1
                if cv2.pointPolygonTest(contour, (px, py), False) >= 0:
                    inside += 1
        return (inside / total) >= ratio

    def _bbox_in_mask(self, bbox, mask, min_inside_ratio=None):
        """基于掩码检查跟踪框是否仍在有效区域。"""
        if mask is None:
            return True
        ratio = self.TRACK_REGION_MIN_INSIDE if min_inside_ratio is None else min_inside_ratio
        x, y, w, h = [int(v) for v in bbox]
        if w <= 1 or h <= 1:
            return False
        h_max, w_max = mask.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_max, x + w), min(h_max, y + h)
        if x2 <= x1 or y2 <= y1:
            return False
        roi = mask[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        cx, cy = x + w // 2, y + h // 2
        if not (0 <= cx < w_max and 0 <= cy < h_max and mask[cy, cx] > 0):
            return False
        return (cv2.countNonZero(roi) / roi.size) >= ratio

    def _reset_drift_state(self, drift_state, keep_color_model=False):
        color_model = drift_state.get("color_model") if keep_color_model else None
        template = drift_state.get("template") if keep_color_model else None
        drift_state.clear()
        drift_state.update(self._new_drift_state())
        if keep_color_model:
            drift_state["color_model"] = color_model
            drift_state["template"] = template

    def _apply_tracker_frame(
            self,
            tracker,
            smoother,
            frame,
            all_track_points,
            region_contour=None,
            region_mask=None,
            drift_state=None,
            coverage_points=None,
            coverage_region_contour=None,
            coverage_region_mask=None,
    ):
        """执行一帧跟踪更新，返回 (center, smooth_bbox) 或 (None, None)。"""
        if drift_state is None:
            drift_state = self._new_drift_state()

        bbox, source, success = self._resolve_tracking_bbox(
            frame, tracker, smoother, drift_state, region_contour, region_mask)

        if not success or bbox is None:
            last_good = drift_state.get("last_good_bbox")
            if last_good is not None:
                bbox = [float(v) for v in last_good]
                success = True
                source = "hold"
            else:
                sf = drift_state.get("speed_factor", 1.0)
                recovered = self._reacquire_target_bbox(
                    frame, drift_state.get("color_model"), drift_state.get("template"),
                    drift_state, sf, region_contour, region_mask,
                )
                if recovered is not None and self._near_track_center(
                        recovered, smoother, drift_state, sf, slack=2.8,
                ):
                    bbox = [float(v) for v in recovered]
                    self._try_reinit_tracker(tracker, frame, recovered, drift_state)
                    drift_state["lock_lost"] = 0
                    drift_state["reacquire_frames"] = 8
                    drift_state["trail_break"] = False  # 重获后连线，不断开
                    success = True
                    source = "reacquire"

        if not success:
            drift_state["update_miss"] = min(
                drift_state.get("update_miss", 0) + 1, self.TRACK_UPDATE_MAX_MISS + 1)
            drift_state["lock_lost"] = drift_state.get("lock_lost", 0) + 1
            um = drift_state["update_miss"]
            if um == 1 or um == self.TRACK_UPDATE_MAX_MISS:
                print(f"跟踪器短暂失效，预测续跟（{um}/{self.TRACK_UPDATE_MAX_MISS}）")
            if um == self.TRACK_UPDATE_MAX_MISS:
                print("跟踪器长时间失效，请按空格键重新框选目标")
            return self._hold_last_valid_track(
                smoother, all_track_points, predict_forward=False, drift_state=drift_state)

        in_region = self._track_in_region(bbox, region_contour, region_mask)
        if not in_region:
            drift_state["region_miss"] = drift_state.get("region_miss", 0) + 1
            if drift_state["region_miss"] == 1:
                logging.debug("目标离开黄框覆盖区，显示轨迹继续绘制")
        else:
            drift_state["region_miss"] = 0
        if source != "hold":
            drift_state["update_miss"] = 0
        if drift_state.get("bootstrap_frames", 0) > 0:
            drift_state["bootstrap_frames"] -= 1

        prev_raw = drift_state.get("last_raw_center")
        self._update_speed_estimate_from_bbox(drift_state, bbox)
        speed_factor = self._get_speed_factor(drift_state, smoother)
        self._tune_smoother_for_speed(smoother, speed_factor, drift_state)

        trail_limit = self._trail_jump_limit(drift_state, speed_factor)
        step_limit = self._frame_step_limit(drift_state, speed_factor)
        if source != "hold" and prev_raw is not None and drift_state.get("bootstrap_frames", 0) == 0:
            cx, cy = self._bbox_center(bbox)
            jump = ((cx - prev_raw[0]) ** 2 + (cy - prev_raw[1]) ** 2) ** 0.5
            if jump > step_limit:
                drift_state["lock_lost"] = drift_state.get("lock_lost", 0) + 1
                logging.debug("track teleport clamped: %.1fpx > %.1f", jump, step_limit)
                ratio = step_limit / jump
                cx = prev_raw[0] + (cx - prev_raw[0]) * ratio
                cy = prev_raw[1] + (cy - prev_raw[1]) * ratio
                bw, bh = max(2.0, float(bbox[2])), max(2.0, float(bbox[3]))
                bbox = [cx - bw / 2.0, cy - bh / 2.0, bw, bh]

        bbox = self._dampen_lateral_bbox(bbox, smoother, speed_factor)

        if drift_state.pop("trail_break", False):
            smoother.break_trail()

        bind_point, _trail_point, smooth_bbox, _record = smoother.update(bbox)
        display_bbox = [int(round(v)) for v in smooth_bbox]
        if bind_point is not None:
            draw_point = bind_point
        else:
            dcx, dcy = self._bbox_center(display_bbox)
            draw_point = (int(round(dcx)), int(round(dcy)))
        raw_cx, raw_cy = smoother._raw_center if smoother._raw_center is not None else self._bbox_center(bbox)

        self._record_trail_points(
            draw_point,
            raw_cx,
            raw_cy,
            source,
            smoother,
            trail_limit,
            all_track_points=all_track_points,
            coverage_points=coverage_points,
            coverage_region_contour=coverage_region_contour,
            coverage_region_mask=coverage_region_mask,
        )
        self._update_speed_estimate(drift_state, smoother)
        drift_state["track_fail_streak"] = 0

        return draw_point, display_bbox, self._trail_live_tip(smoother, draw_point)

    def _draw_trajectory_incremental(self, trail_canvas, white_trail, points, track_width, draw_state):
        """仅绘制新增轨迹段，避免每帧重画全部历史导致卡死。"""
        drawn = int(draw_state.get("count", 0))
        if drawn >= len(points):
            return
        thin = max(1, track_width // 4)
        while drawn < len(points):
            if drawn > 0:
                if draw_state.pop("skip_connect", False):
                    drawn += 1
                    draw_state["count"] = drawn
                    continue
                p0, p1 = points[drawn - 1], points[drawn]
                cv2.line(trail_canvas, p0, p1, (0, 255, 0), track_width)
                cv2.line(white_trail, p0, p1, (255, 255, 255), thin)
            drawn += 1
        draw_state["count"] = drawn

    def _draw_live_trail_tip(self, overlay, points, live_tip, track_width, max_segment=None):
        """绘制当前帧尾段（不写入历史缓存）。"""
        if live_tip is None or not points or points[-1] == live_tip:
            return
        if max_segment is None:
            max_segment = getattr(self, "TRACK_MAX_TRAIL_SEGMENT", 70.0)
        last = points[-1]
        dist = ((live_tip[0] - last[0]) ** 2 + (live_tip[1] - last[1]) ** 2) ** 0.5
        # 允许更大跨度的尾段连接，避免短暂失锁后尾线空白
        limit = max(max_segment * 1.08, float(getattr(self, "TRACK_RECONNECT_MAX_GAP", 900.0)) * 0.35)
        if dist > limit:
            return
        thin = max(1, track_width // 4)
        cv2.line(overlay, last, live_tip, (0, 255, 0), track_width)
        cv2.line(overlay, last, live_tip, (255, 255, 255), thin)

    def _calc_trail_coverage(self, trail_canvas, region_mask):
        """仅统计黄色有效区域内的轨迹覆盖面积。"""
        if region_mask is None or trail_canvas is None:
            return 0.0
        polygon_area = int(cv2.countNonZero(region_mask))
        if polygon_area <= 0:
            return 0.0
        green = (
                (trail_canvas[:, :, 1] > 200)
                & (trail_canvas[:, :, 0] < 80)
                & (trail_canvas[:, :, 2] < 80)
        )
        in_region = region_mask > 0
        covered = int(np.count_nonzero(green & in_region))
        return (covered / polygon_area) * 100.0

    def _draw_trajectory(self, overlay, white_trail, points, track_width, live_tip=None, max_segment=None):
        """兼容旧调用：全量重绘（仅短轨迹时使用）。"""
        draw_state = {"count": 0}
        trail_canvas = np.zeros_like(overlay)
        self._draw_trajectory_incremental(trail_canvas, white_trail, points, track_width, draw_state)
        overlay[:] = cv2.add(overlay, trail_canvas)
        self._draw_live_trail_tip(overlay, points, live_tip, track_width, max_segment)

    def extract_time_from_frame(self, frame):
        h, w, _ = frame.shape
        roi = frame[h - 60:h, w - 250:w]  # 右下角区域，可根据实际调整
        pil_img = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        text = pytesseract.image_to_string(pil_img, config='--psm 7')
        match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', text)
        if match:
            return match.group(0)
        else:
            return ""

    def process_video(self, video_path, info):
        try:
            frame_count = 0
            coverage_rate = 0
            if not os.path.exists(video_path):
                logging.error(f"视频文件 {video_path} 不存在")
                return

            cap = open_video_capture(video_path)
            if not cap or not cap.isOpened():
                logging.error(f"无法打开视频文件 {video_path}")
                return

            ret, frame = cap.read()
            if not ret:
                logging.error("无法读取视频文件")
                return

            # 使用当前功能开始时间，而不是从视频中提取时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            info['start_time'] = current_time
            # 用户设置的轨迹线宽度（填写弹窗），缺省用默认值
            track_width = int(info.get('track_width', self.TRACK_WIDTH) or self.TRACK_WIDTH)
            if track_width <= 0:
                track_width = self.TRACK_WIDTH
            print(f"使用轨迹线宽度: {track_width}")
            self._apply_video_speed_from_info(info)

            frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))

            tracker = None
            track_smoother = None
            init_box = None
            all_track_points = []
            coverage_points = []
            polygon_points = []  # 存储多边形的点
            drawing_polygon = True  # 标记是否在绘制多边形

            def on_mouse(event, x, y, flags, param):
                nonlocal drawing_polygon
                if drawing_polygon:
                    if event == cv2.EVENT_LBUTTONDOWN:
                        polygon_points.append((x, y))
                    elif event == cv2.EVENT_RBUTTONDOWN and len(polygon_points) > 2:
                        drawing_polygon = False

            safe_named_window("Tracking")
            cv2.setMouseCallback("Tracking", on_mouse)
            print("请使用鼠标左键点击绘制多边形区域，右键完成绘制")

            # 绘制多边形区域
            while drawing_polygon:
                temp_frame = frame.copy()
                if len(polygon_points) > 1:
                    for i in range(1, len(polygon_points)):
                        cv2.line(temp_frame, polygon_points[i - 1], polygon_points[i], (0, 255, 255), 2)
                    if len(polygon_points) > 2:
                        cv2.line(temp_frame, polygon_points[-1], polygon_points[0], (0, 255, 255), 2)

                cv2.imshow("Tracking", temp_frame)
                key = cv2.waitKey(1) & 0xFF

                # 检查窗口是否被关闭
                if cv2.getWindowProperty("Tracking", cv2.WND_PROP_VISIBLE) < 1:
                    print("窗口被关闭，退出多边形绘制")
                    cv2.destroyAllWindows()
                    return

                if key == ord('q') and len(polygon_points) > 2:
                    drawing_polygon = False

            if len(polygon_points) < 3:
                print("多边形区域无效，至少需要3个点")
                return

            # 创建多边形掩码
            mask = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH), dtype=np.uint8)
            cv2.fillPoly(mask, [np.array(polygon_points, np.int32)], 255)
            polygon_area = cv2.countNonZero(mask)

            # 找到多边形的轮廓
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            white_trail = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            trail_canvas = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            coverage_canvas = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            coverage_dummy = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            trail_draw_state = {"count": 0}
            coverage_draw_state = {"count": 0}

            print("按空格键选择要跟踪的目标，按 q 键退出")
            end_status = 'Yes'
            current_center = None
            current_bbox = None
            trail_live_tip = None
            drift_state = self._new_drift_state()

            while True:
                frame_count += 1
                if not ret:
                    print("视频播放完毕或读取失败")
                    break

                # 先更新跟踪，再绘制轨迹，避免轨迹落后目标一帧
                current_center = None
                current_bbox = None
                trail_live_tip = None
                if tracker:
                    if track_smoother is None:
                        track_smoother = self._make_track_smoother()
                    current_center, current_bbox, trail_live_tip = self._apply_tracker_frame(
                        tracker, track_smoother, frame, all_track_points,
                        region_contour=contours[0], region_mask=mask,
                        drift_state=drift_state, coverage_points=coverage_points,
                        coverage_region_contour=contours[0], coverage_region_mask=mask)
                    if current_center is None:
                        drift_state["track_fail_streak"] = drift_state.get("track_fail_streak", 0) + 1
                        if drift_state["track_fail_streak"] >= self.TRACK_UPDATE_MAX_MISS:
                            # 不销毁跟踪器，继续用颜色/模板重获；仅提示可手动重标
                            if drift_state["track_fail_streak"] == self.TRACK_UPDATE_MAX_MISS:
                                print("目标短暂失锁，正在自动找回（也可按空格重新框选）")
                            if drift_state.get("last_good_bbox") is not None:
                                cx, cy = self._bbox_center(drift_state["last_good_bbox"])
                                current_center = (int(round(cx)), int(round(cy)))
                                bb = drift_state["last_good_bbox"]
                                current_bbox = [int(round(v)) for v in bb]
                                trail_live_tip = self._trail_live_tip(track_smoother, current_center)
                        elif drift_state.get("last_good_bbox") is not None:
                            cx, cy = self._bbox_center(drift_state["last_good_bbox"])
                            current_center = (int(round(cx)), int(round(cy)))
                            bb = drift_state["last_good_bbox"]
                            current_bbox = [int(round(v)) for v in bb]
                            trail_live_tip = self._trail_live_tip(track_smoother, current_center)

                overlay = frame.copy()

                # 显示多边形区域
                cv2.polylines(overlay, [np.array(polygon_points, np.int32)], isClosed=True, color=(0, 255, 255),
                              thickness=2)

                # 绘制轨迹线（含实时尾段连接到当前目标）
                trail_seg = self._trail_jump_limit(
                    drift_state,
                    self._get_speed_factor(drift_state, track_smoother) if track_smoother else 1.0,
                )
                self._draw_trajectory_incremental(
                    trail_canvas, white_trail, all_track_points, track_width, trail_draw_state)
                self._draw_trajectory_incremental(
                    coverage_canvas, coverage_dummy, coverage_points, track_width, coverage_draw_state)
                self._draw_live_trail_tip(
                    overlay, all_track_points, trail_live_tip or current_center, track_width, max_segment=trail_seg)

                track_overlay = cv2.add(cv2.add(overlay, trail_canvas), white_trail)

                if frame_count % 20 == 0:
                    coverage_rate = self._calc_trail_coverage(coverage_canvas, mask)

                cv2.putText(overlay, f"Coverage: {coverage_rate:.2f}%", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 139, 255), 2)

                # 显示结果帧
                alpha = 0.3
                coverage_view = cv2.add(overlay, trail_canvas)
                result_frame = cv2.addWeighted(coverage_view, alpha, frame, 1 - alpha, 0)
                result_track_frame = cv2.addWeighted(track_overlay, alpha, frame, 1 - alpha, 0)

                # 在tracking窗口中显示覆盖率信息（黄色背景框）
                coverage_text = f"Coverage: {coverage_rate:.2f}%"
                text_size = cv2.getTextSize(coverage_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                text_width = text_size[0]
                text_height = text_size[1]

                # 绘制黄色背景框
                cv2.rectangle(result_track_frame, (5, 5), (text_width + 15, text_height + 15), (0, 255, 255), -1)
                # 绘制黑色边框
                cv2.rectangle(result_track_frame, (5, 5), (text_width + 15, text_height + 15), (0, 0, 0), 2)
                # 绘制文字
                cv2.putText(result_track_frame, coverage_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

                # 在tracking窗口中显示进度条
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                progress = current_frame / total_frames if total_frames > 0 else 0

                progress_bar_width = int(self.FRAME_WIDTH * progress)
                cv2.rectangle(result_track_frame, (0, self.FRAME_HEIGHT - 10), (self.FRAME_WIDTH, self.FRAME_HEIGHT),
                              (50, 50, 50),
                              -1)
                cv2.rectangle(result_track_frame, (0, self.FRAME_HEIGHT - 10), (progress_bar_width, self.FRAME_HEIGHT),
                              (0, 255, 0), -1)

                if current_bbox:
                    x, y, w, h = current_bbox
                    cv2.rectangle(result_track_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                cv2.imshow("Coverage", result_frame)
                cv2.imshow("Tracking", result_track_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == ord('Q'):
                    end_status = 'No'
                    break
                elif key == ord(' '):
                    init_box = cv2.selectROI("Select object", frame, fromCenter=False)
                    if any(init_box):
                        if not self._bbox_in_contour(init_box, contours[0]):
                            print("请在黄色泳池多边形内框选目标，否则容易跟丢")
                        tracker = self.create_tracker()
                        if tracker is not None:
                            tracker.init(self._prepare_track_frame(frame, drift_state), init_box)
                            track_smoother = self._make_track_smoother()
                            drift_state.clear()
                            drift_state.update(self._new_drift_state())
                            drift_state["color_model"] = self._learn_color_model(frame, init_box)
                            drift_state["template"] = self._extract_template(frame, init_box)
                            drift_state["init_center"] = self._bbox_center(init_box)
                            drift_state["last_good_bbox"] = tuple(float(v) for v in init_box)
                            if drift_state["color_model"]:
                                track_smoother.ref_wh = drift_state["color_model"]["ref_wh"]
                            is_reselect = len(all_track_points) > 0
                            self._bootstrap_tracking(
                                track_smoother, init_box, drift_state, all_track_points,
                                coverage_points=coverage_points,
                                trail_draw_state=trail_draw_state,
                                coverage_draw_state=coverage_draw_state,
                                reconnect=is_reselect,
                                region_contour=contours[0],
                                region_mask=mask)
                            self._tune_smoother_for_speed(
                                track_smoother,
                                self._get_speed_factor(drift_state, track_smoother),
                                drift_state,
                            )
                            if is_reselect:
                                print("目标重新标注完成，断点已与新起点轨迹连接")
                            else:
                                print("目标选择完成，开始跟踪（颜色+模板辅助）")
                        else:
                            print("无法初始化跟踪器，请确保已安装 OpenCV contrib 模块")
                    cv2.destroyWindow("Select object")

                ret, frame = cap.read()
                if ret:
                    frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))

            # 保存最后一帧图片
            if len(all_track_points) > 0:
                output_dir = str(picture_dir())
                os.makedirs(output_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # 保存Coverage窗口图片（使用result_frame）
                coverage_output_path = os.path.join(output_dir, f"Coverage_rate_{timestamp}.png")
                pil_coverage_img = Image.fromarray(cv2.cvtColor(result_frame, cv2.COLOR_BGR2RGB))
                pil_coverage_img.save(coverage_output_path, optimize=True, quality=85)
                print(f"Coverage图像已保存至 {coverage_output_path}")

                # 保存Tracking窗口图片（使用result_track_frame）
                tracking_output_path = os.path.join(output_dir, f"Tracking_{timestamp}.png")
                pil_tracking_img = Image.fromarray(cv2.cvtColor(result_track_frame, cv2.COLOR_BGR2RGB))
                pil_tracking_img.save(tracking_output_path, optimize=True, quality=85)
                print(f"Tracking图像已保存至 {tracking_output_path}")

                # 写入Excel（包含两张图片）
                info['end_status'] = end_status
                info['coverage'] = f"{coverage_rate:.2f}%"
                try:
                    append_to_excel(info, coverage_output_path, tracking_output_path)
                    print("数据已成功写入Excel表格")
                except Exception as e:
                    print(f"写入Excel时发生错误: {e}")
                    logging.error(f"写入Excel时发生错误: {str(e)}")
            else:
                print("未检测到有效的轨迹线")

        except Exception as e:
            logging.error(f"处理视频时出现错误: {str(e)}")
            print(f"处理视频时出现错误: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            if 'cap' in locals() and cap is not None:
                cap.release()
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass

    def process_pool_wall_video(self, video_path, info):
        """处理池壁轨迹线绘制视频"""
        try:
            frame_count = 0
            coverage_rate = 0
            if not os.path.exists(video_path):
                logging.error(f"视频文件 {video_path} 不存在")
                return

            cap = open_video_capture(video_path)
            if not cap or not cap.isOpened():
                logging.error(f"无法打开视频文件 {video_path}")
                return

            ret, frame = cap.read()
            if not ret:
                logging.error("无法读取视频文件")
                return

            # 使用当前功能开始时间，而不是从视频中提取时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            info['start_time'] = current_time
            # 用户设置的轨迹线宽度（填写弹窗），缺省用默认值
            track_width = int(info.get('track_width', self.TRACK_WIDTH) or self.TRACK_WIDTH)
            if track_width <= 0:
                track_width = self.TRACK_WIDTH
            print(f"使用轨迹线宽度: {track_width}")
            self._apply_video_speed_from_info(info)

            frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))

            tracker = None
            track_smoother = None
            init_box = None
            all_track_points = []
            coverage_points = []

            # 池壁轨迹线绘制相关变量
            wall_polygons = []  # 存储两个池壁多边形
            drawing_wall = True  # 标记是否在绘制池壁多边形
            current_polygon = []  # 当前正在绘制的多边形点
            polygon_count = 0  # 已绘制的多边形数量

            def on_mouse_wall(event, x, y, flags, param):
                nonlocal drawing_wall, current_polygon, polygon_count
                if drawing_wall and polygon_count < 2:
                    if event == cv2.EVENT_LBUTTONDOWN:
                        current_polygon.append((x, y))
                    elif event == cv2.EVENT_RBUTTONDOWN and len(current_polygon) > 2:
                        # 完成一个多边形
                        wall_polygons.append(current_polygon.copy())
                        current_polygon = []
                        polygon_count += 1
                        if polygon_count >= 2:
                            drawing_wall = False

            safe_named_window("Pool Wall Drawing")
            cv2.setMouseCallback("Pool Wall Drawing", on_mouse_wall)
            print("请使用鼠标左键点击绘制两个池壁多边形区域，右键完成绘制")
            print("第一个多边形绘制完成后，继续绘制第二个多边形")

            # 绘制池壁多边形
            while drawing_wall:
                temp_frame = frame.copy()

                # 显示已完成的多边形
                for i, polygon in enumerate(wall_polygons):
                    if len(polygon) > 1:
                        for j in range(1, len(polygon)):
                            cv2.line(temp_frame, polygon[j - 1], polygon[j], (0, 255, 255), 2)
                        if len(polygon) > 2:
                            cv2.line(temp_frame, polygon[-1], polygon[0], (0, 255, 255), 2)
                    cv2.putText(temp_frame, f"Wall {i + 1}",
                                (polygon[0][0], polygon[0][1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                # 显示当前正在绘制的多边形
                if len(current_polygon) > 1:
                    for i in range(1, len(current_polygon)):
                        cv2.line(temp_frame, current_polygon[i - 1], current_polygon[i], (0, 255, 0), 2)
                    if len(current_polygon) > 2:
                        cv2.line(temp_frame, current_polygon[-1], current_polygon[0], (0, 255, 0), 2)

                # 显示当前点击的点
                for point in current_polygon:
                    cv2.circle(temp_frame, point, 5, (0, 255, 0), -1)

                # 显示提示信息
                cv2.putText(temp_frame, f"Draw Wall Polygon {polygon_count + 1}/2",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(temp_frame, "Left click to add points, Right click to finish",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                cv2.imshow("Pool Wall Drawing", temp_frame)
                key = cv2.waitKey(1) & 0xFF

                # 检查窗口是否被关闭
                if cv2.getWindowProperty("Pool Wall Drawing", cv2.WND_PROP_VISIBLE) < 1:
                    print("窗口被关闭，退出池壁多边形绘制")
                    cv2.destroyAllWindows()
                    return

                if key == ord('q') and len(current_polygon) > 2:
                    drawing_wall = False

            if len(wall_polygons) < 2:
                print("需要绘制两个池壁多边形")
                cv2.destroyAllWindows()
                return

            # 创建两个多边形的掩码
            wall1_mask = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH), dtype=np.uint8)
            wall2_mask = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH), dtype=np.uint8)

            cv2.fillPoly(wall1_mask, [np.array(wall_polygons[0], np.int32)], 255)
            cv2.fillPoly(wall2_mask, [np.array(wall_polygons[1], np.int32)], 255)

            # 计算两个多边形之间的中间区域（并集减去交集）
            union_mask = cv2.bitwise_or(wall1_mask, wall2_mask)
            intersection_mask = cv2.bitwise_and(wall1_mask, wall2_mask)
            middle_mask = cv2.bitwise_xor(union_mask, intersection_mask)  # 中间区域 = 并集 - 交集
            middle_area = cv2.countNonZero(middle_mask)

            # 显示绘制完成的多边形，等待用户确认
            print("两个池壁多边形绘制完成！")
            print("按空格键开始选择跟踪目标，按 q 键退出")

            # 显示最终的多边形绘制结果
            final_draw_frame = frame.copy()

            # 显示两个多边形
            for i, polygon in enumerate(wall_polygons):
                if len(polygon) > 1:
                    for j in range(1, len(polygon)):
                        cv2.line(final_draw_frame, polygon[j - 1], polygon[j], (0, 255, 255), 2)
                    if len(polygon) > 2:
                        cv2.line(final_draw_frame, polygon[-1], polygon[0], (0, 255, 255), 2)
                cv2.putText(final_draw_frame, f"Wall {i + 1}",
                            (polygon[0][0], polygon[0][1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            # 显示中间区域（用半透明红色填充）
            middle_overlay = final_draw_frame.copy()
            middle_overlay[middle_mask > 0] = [0, 0, 255]  # 红色填充中间区域
            final_draw_frame = cv2.addWeighted(final_draw_frame, 0.7, middle_overlay, 0.3, 0)

            # 显示提示信息
            cv2.putText(final_draw_frame, "Pool Walls Drawing Complete!",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(final_draw_frame, "Press Q to quit, or wait 3 seconds to continue",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # 显示绘制完成窗口，立即继续
            print("绘制完成，立即开始目标跟踪")
            cv2.destroyWindow("Pool Wall Drawing")  # 关闭绘制窗口

            # 确保中间区域有效
            if middle_area == 0:
                print("两个多边形之间没有中间区域")
                return

            white_trail = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            trail_canvas = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            coverage_canvas = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            coverage_dummy = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            trail_draw_state = {"count": 0}
            coverage_draw_state = {"count": 0}

            print("按空格键选择要跟踪的目标，按 q 键退出")
            end_status = 'Yes'
            current_center = None
            current_bbox = None
            trail_live_tip = None
            drift_state = self._new_drift_state()

            while True:
                frame_count += 1
                if not ret:
                    print("视频播放完毕或读取失败")
                    break

                current_center = None
                current_bbox = None
                trail_live_tip = None
                if tracker:
                    if track_smoother is None:
                        track_smoother = self._make_track_smoother()
                    current_center, current_bbox, trail_live_tip = self._apply_tracker_frame(
                        tracker, track_smoother, frame, all_track_points,
                        region_mask=union_mask, drift_state=drift_state,
                        coverage_points=coverage_points,
                        coverage_region_mask=middle_mask)
                    if current_center is None:
                        drift_state["track_fail_streak"] = drift_state.get("track_fail_streak", 0) + 1
                        if drift_state["track_fail_streak"] >= self.TRACK_UPDATE_MAX_MISS:
                            if drift_state["track_fail_streak"] == self.TRACK_UPDATE_MAX_MISS:
                                print("目标短暂失锁，正在自动找回（也可按空格重新框选）")
                            if drift_state.get("last_good_bbox") is not None:
                                cx, cy = self._bbox_center(drift_state["last_good_bbox"])
                                current_center = (int(round(cx)), int(round(cy)))
                                bb = drift_state["last_good_bbox"]
                                current_bbox = [int(round(v)) for v in bb]
                                trail_live_tip = self._trail_live_tip(track_smoother, current_center)
                        elif drift_state.get("last_good_bbox") is not None:
                            cx, cy = self._bbox_center(drift_state["last_good_bbox"])
                            current_center = (int(round(cx)), int(round(cy)))
                            bb = drift_state["last_good_bbox"]
                            current_bbox = [int(round(v)) for v in bb]
                            trail_live_tip = self._trail_live_tip(track_smoother, current_center)

                overlay = frame.copy()

                # 显示池壁多边形
                for i, polygon in enumerate(wall_polygons):
                    if len(polygon) > 1:
                        for j in range(1, len(polygon)):
                            cv2.line(overlay, polygon[j - 1], polygon[j], (0, 255, 255), 2)
                        if len(polygon) > 2:
                            cv2.line(overlay, polygon[-1], polygon[0], (0, 255, 255), 2)
                    cv2.putText(overlay, f"Wall {i + 1}",
                                (polygon[0][0], polygon[0][1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                # 显示中间区域
                middle_overlay = overlay.copy()
                middle_overlay[middle_mask > 0] = [255, 0, 0]  # 红色填充中间区域
                cv2.addWeighted(overlay, 0.7, middle_overlay, 0.3, 0, overlay)
                cv2.putText(overlay, "Middle Area",
                            (10, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

                trail_seg = self._trail_jump_limit(
                    drift_state,
                    self._get_speed_factor(drift_state, track_smoother) if track_smoother else 1.0,
                )
                self._draw_trajectory_incremental(
                    trail_canvas, white_trail, all_track_points, track_width, trail_draw_state)
                self._draw_trajectory_incremental(
                    coverage_canvas, coverage_dummy, coverage_points, track_width, coverage_draw_state)
                self._draw_live_trail_tip(
                    overlay, all_track_points, trail_live_tip or current_center, track_width, max_segment=trail_seg)

                track_overlay = cv2.add(cv2.add(overlay, trail_canvas), white_trail)

                if frame_count % 20 == 0:
                    coverage_rate = self._calc_trail_coverage(coverage_canvas, middle_mask)

                cv2.putText(overlay, f"Middle Area Coverage: {coverage_rate:.2f}%", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 139, 255), 2)

                # 显示结果帧
                alpha = 0.3
                coverage_view = cv2.add(overlay, trail_canvas)
                result_frame = cv2.addWeighted(coverage_view, alpha, frame, 1 - alpha, 0)
                result_track_frame = cv2.addWeighted(track_overlay, alpha, frame, 1 - alpha, 0)

                # 在tracking窗口中显示覆盖率信息（黄色背景框）
                coverage_text = f"Middle Area Coverage: {coverage_rate:.2f}%"
                text_size = cv2.getTextSize(coverage_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                text_width = text_size[0]
                text_height = text_size[1]

                # 绘制黄色背景框
                cv2.rectangle(result_track_frame, (5, 5), (text_width + 15, text_height + 15), (0, 255, 255), -1)
                # 绘制黑色边框
                cv2.rectangle(result_track_frame, (5, 5), (text_width + 15, text_height + 15), (0, 0, 0), 2)
                # 绘制文字
                cv2.putText(result_track_frame, coverage_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

                # 在tracking窗口中显示进度条
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                progress = current_frame / total_frames if total_frames > 0 else 0

                progress_bar_width = int(self.FRAME_WIDTH * progress)
                cv2.rectangle(result_track_frame, (0, self.FRAME_HEIGHT - 10), (self.FRAME_WIDTH, self.FRAME_HEIGHT),
                              (50, 50, 50),
                              -1)
                cv2.rectangle(result_track_frame, (0, self.FRAME_HEIGHT - 10), (progress_bar_width, self.FRAME_HEIGHT),
                              (0, 255, 0), -1)

                if current_bbox:
                    x, y, w, h = current_bbox
                    cv2.rectangle(result_track_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                cv2.imshow("Pool Wall Coverage", result_frame)
                cv2.imshow("Pool Wall Tracking", result_track_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == ord('Q'):
                    end_status = 'No'
                    break
                elif key == ord(' '):
                    init_box = cv2.selectROI("Select object", frame, fromCenter=False)
                    if any(init_box):
                        if not self._bbox_in_mask(init_box, union_mask):
                            print("请在池壁有效区域内框选目标，否则容易跟丢")
                        tracker = self.create_tracker()
                        if tracker is not None:
                            tracker.init(self._prepare_track_frame(frame, drift_state), init_box)
                            track_smoother = self._make_track_smoother()
                            drift_state.clear()
                            drift_state.update(self._new_drift_state())
                            drift_state["color_model"] = self._learn_color_model(frame, init_box)
                            drift_state["template"] = self._extract_template(frame, init_box)
                            drift_state["init_center"] = self._bbox_center(init_box)
                            drift_state["last_good_bbox"] = tuple(float(v) for v in init_box)
                            if drift_state["color_model"]:
                                track_smoother.ref_wh = drift_state["color_model"]["ref_wh"]
                            is_reselect = len(all_track_points) > 0
                            self._bootstrap_tracking(
                                track_smoother, init_box, drift_state, all_track_points,
                                coverage_points=coverage_points,
                                trail_draw_state=trail_draw_state,
                                coverage_draw_state=coverage_draw_state,
                                reconnect=is_reselect,
                                region_mask=union_mask,
                                coverage_region_mask=middle_mask)
                            self._tune_smoother_for_speed(
                                track_smoother,
                                self._get_speed_factor(drift_state, track_smoother),
                                drift_state,
                            )
                            if is_reselect:
                                print("目标重新标注完成，断点已与新起点轨迹连接")
                            else:
                                print("目标选择完成，开始跟踪（颜色+模板辅助）")
                        else:
                            print("无法初始化跟踪器，请确保已安装 OpenCV contrib 模块")
                    cv2.destroyWindow("Select object")

                ret, frame = cap.read()
                if ret:
                    frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))

            # 保存最后一帧图片
            if len(all_track_points) > 0:
                output_dir = str(picture_dir())
                os.makedirs(output_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # 保存Pool Wall Coverage窗口图片
                coverage_output_path = os.path.join(output_dir, f"Pool_Wall_Coverage_{timestamp}.png")
                pil_coverage_img = Image.fromarray(cv2.cvtColor(result_frame, cv2.COLOR_BGR2RGB))
                pil_coverage_img.save(coverage_output_path, optimize=True, quality=85)
                print(f"Pool Wall Coverage图像已保存至 {coverage_output_path}")

                # 保存Pool Wall Tracking窗口图片
                tracking_output_path = os.path.join(output_dir, f"Pool_Wall_Tracking_{timestamp}.png")
                pil_tracking_img = Image.fromarray(cv2.cvtColor(result_track_frame, cv2.COLOR_BGR2RGB))
                pil_tracking_img.save(tracking_output_path, optimize=True, quality=85)
                print(f"Pool Wall Tracking图像已保存至 {tracking_output_path}")

                # 写入Excel（包含两张图片）
                info['end_status'] = end_status
                info['coverage'] = f"{coverage_rate:.2f}%"
                try:
                    self.append_pool_wall_to_excel(info, coverage_output_path, tracking_output_path)
                    print("池壁轨迹线数据已成功写入Excel表格")
                except Exception as e:
                    print(f"写入Excel时发生错误: {e}")
                    logging.error(f"写入Excel时发生错误: {str(e)}")
            else:
                print("未检测到有效的轨迹线")

        except Exception as e:
            logging.error(f"处理池壁轨迹线视频时出现错误: {str(e)}")
            print(f"处理池壁轨迹线视频时出现错误: {str(e)}")
        finally:
            if 'cap' in locals():
                cap.release()
            cv2.destroyAllWindows()

    def append_pool_wall_to_excel(self, info, coverage_img_path, tracking_img_path):
        """将池壁轨迹线数据写入Excel"""
        print(f"开始写入池壁轨迹线Excel，coverage图片: {coverage_img_path}")
        print(f"tracking图片: {tracking_img_path}")
        print(f"info数据: {info}")

        # 使用 app_data_dir()（macOS: ~/Documents/BeatbotDist）
        dist_dir = str(app_data_dir())
        os.makedirs(dist_dir, exist_ok=True)
        excel_path = os.path.join(dist_dir, '池壁轨迹线记录.xlsx')
        print(f"Excel文件路径: {excel_path}")

        # 直接使用原始图片路径，不复制到dist目录
        coverage_filename = os.path.basename(coverage_img_path)
        tracking_filename = os.path.basename(tracking_img_path)

        try:
            if not os.path.exists(excel_path):
                # 创建新的Excel文件
                wb = Workbook()
                ws = wb.active
                ws.append(
                    ['序号', '视频开始时间', '机器序号', '泳池编号', '机器阶段', '固件版本号', 'coverage 截图',
                     'tracking 截图',
                     '结束状态', '中间区域覆盖率'])
                for cell in ws[ws.max_row]:
                    cell.alignment = openpyxl.styles.Alignment(horizontal='center', vertical='center')
            else:
                # 尝试加载现有Excel文件
                try:
                    wb = load_workbook(excel_path)
                    ws = wb.active
                except PermissionError:
                    # Excel文件被占用，显示强弹框
                    print("⚠ Excel文件被占用，显示强弹框...")
                    result = show_excel_blocking_dialog(excel_path)

                    if result:
                        # Excel文件已关闭，重新尝试加载
                        try:
                            wb = load_workbook(excel_path)
                            ws = wb.active
                        except Exception as retry_error:
                            print(f"✗ 重新加载失败: {retry_error}")
                            raise
                    else:
                        # 用户取消或出现其他问题
                        raise PermissionError("用户取消操作")
                except Exception as e:
                    print(f"现有Excel文件损坏，创建新文件: {e}")
                    # 如果文件损坏，备份原文件并创建新文件
                    backup_path = excel_path + f".backup_{int(time.time())}"
                    if os.path.exists(excel_path):
                        try:
                            os.rename(excel_path, backup_path)
                            print(f"已备份损坏文件到: {backup_path}")
                        except:
                            pass
                    wb = Workbook()
                    ws = wb.active
                    ws.append(
                        ['序号', '视频开始时间', '机器序号', '泳池编号', '机器阶段', '固件版本号', 'coverage 截图',
                         'tracking 截图',
                         '结束状态', '中间区域覆盖率'])
                    for cell in ws[ws.max_row]:
                        cell.alignment = openpyxl.styles.Alignment(horizontal='center', vertical='center')

            # 添加数据行
            row = [ws.max_row, info['start_time'], info['sn'], info['pool'], info['stage'], info['fw'],
                   coverage_filename, tracking_filename, info['end_status'], info['coverage']]
            ws.append(row)
            for cell in ws[ws.max_row]:
                cell.alignment = openpyxl.styles.Alignment(horizontal='center', vertical='center')

            # 添加coverage图片到G列
            try:
                print(f"尝试添加coverage图片: {coverage_img_path}")
                if os.path.exists(coverage_img_path):
                    coverage_img = XLImage(coverage_img_path)
                    coverage_img.width = 200
                    coverage_img.height = 150
                    coverage_img.anchor = f'G{ws.max_row}'
                    ws.add_image(coverage_img)
                    print(f"✓ 已添加coverage图片到Excel G列: {coverage_img_path}")
                else:
                    print(f"✗ Coverage图片文件不存在: {coverage_img_path}")
            except Exception as e:
                print(f"✗ 添加coverage图片失败: {e}")
                import traceback
                traceback.print_exc()

            # 添加tracking图片到H列
            try:
                print(f"尝试添加tracking图片: {tracking_img_path}")
                if os.path.exists(tracking_img_path):
                    tracking_img = XLImage(tracking_img_path)
                    tracking_img.width = 200
                    tracking_img.height = 150
                    tracking_img.anchor = f'H{ws.max_row}'
                    ws.add_image(tracking_img)
                    print(f"✓ 已添加tracking图片到Excel H列: {tracking_img_path}")
                else:
                    print(f"✗ Tracking图片文件不存在: {tracking_img_path}")
            except Exception as e:
                print(f"✗ 添加tracking图片失败: {e}")
                import traceback
                traceback.print_exc()

            # 设置列宽
            ws.column_dimensions['G'].width = 35
            ws.column_dimensions['H'].width = 35
            ws.row_dimensions[ws.max_row].height = 120

            # 保存Excel文件（增强的重试机制）
            max_retries = 1
            for attempt in range(max_retries):
                try:
                    wb.save(excel_path)
                    print(f"✓ Excel文件已成功保存: {excel_path}")
                    # 显示成功提示
                    messagebox.showinfo("提示", "池壁轨迹线数据已上传至 D:/dist/池壁轨迹线记录.xlsx")
                    break
                except PermissionError as e:
                    if attempt < max_retries - 1:
                        print(f"⚠ Excel文件被占用，等待重试... (尝试 {attempt + 1}/{max_retries})")
                        time.sleep(3)  # 增加等待时间
                    else:
                        # 使用强弹框，直到Excel文件关闭
                        print("⚠ Excel文件被占用，显示强弹框...")
                        try:
                            result = show_excel_blocking_dialog(excel_path)
                            print(f"弹框返回结果: {result}")

                            if result:
                                # Excel文件已关闭，重新尝试保存
                                print("Excel文件已关闭，重新尝试保存...")
                                try:
                                    wb.save(excel_path)
                                    print(f"✓ Excel文件已成功保存: {excel_path}")
                                    # 显示成功提示
                                    messagebox.showinfo("提示", "池壁轨迹线数据已上传至 D:/dist/池壁轨迹线记录.xlsx")
                                    break
                                except Exception as retry_error:
                                    print(f"✗ 重新保存失败: {retry_error}")
                                    # 如果重新保存仍然失败，再次显示弹框
                                    print("重新保存失败，再次显示弹框...")
                                    result = show_excel_blocking_dialog(excel_path)
                                    if result:
                                        wb.save(excel_path)
                                        print(f"✓ Excel文件最终保存成功: {excel_path}")
                                        messagebox.showinfo("提示",
                                                            "池壁轨迹线数据已上传至 D:/dist/池壁轨迹线记录.xlsx")
                                        break
                                    else:
                                        raise PermissionError("用户取消保存操作")
                            else:
                                # 用户取消或出现其他问题
                                print("用户取消保存操作")
                                messagebox.showwarning("保存失败", "文件被占用，无法保存此次数据，请确保已关闭excel程序")
                                raise PermissionError("用户取消保存操作")
                        except Exception as dialog_error:
                            print(f"显示弹框时发生错误: {dialog_error}")
                            raise
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"⚠ 保存失败，重试中... (尝试 {attempt + 1}/{max_retries}): {e}")
                        time.sleep(2)
                    else:
                        # 最后一次尝试失败，尝试保存到备用位置
                        print("⚠ 保存失败，尝试保存到备用位置...")
                        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup_excel")
                        os.makedirs(backup_dir, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_path = os.path.join(backup_dir, f'池壁轨迹线记录_{timestamp}.xlsx')
                        try:
                            wb.save(backup_path)
                            print(f"✓ 已保存到备用位置: {backup_path}")
                            messagebox.showinfo("保存成功", f"数据已保存到备用位置：\n{backup_path}")
                        except Exception as backup_error:
                            print(f"✗ 备用保存也失败: {backup_error}")
                            messagebox.showerror("保存失败", f"无法保存Excel文件：\n{str(backup_error)}")
                            raise

        except Exception as e:
            print(f"写入Excel时发生错误: {e}")
            import traceback
            traceback.print_exc()
            raise


class IPInputDialog(simpledialog.Dialog):
    def __init__(self, parent, title, history_file=None):
        self.history_file = history_file or os.path.join(HISTORY_DIR, "ip_history.txt")
        self.ip_var = None
        self.history = []
        legacy_ip = os.path.join(APP_DIR, "ip_history.txt")
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r', encoding='utf-8') as f:
                self.history = [line.strip() for line in f if line.strip()]
        elif os.path.exists(legacy_ip):
            with open(legacy_ip, 'r', encoding='utf-8') as f:
                self.history = [line.strip() for line in f if line.strip()]
        super().__init__(parent, title)

    def body(self, master):
        # 设置窗口大小和居中
        self.geometry("400x200")
        self.resizable(False, False)
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.winfo_screenheight() // 2) - (200 // 2)
        self.geometry(f"400x200+{x}+{y}")

        # 设置窗口始终在最前面
        self.attributes('-topmost', True)
        self.lift()
        self.focus_force()

        # 创建主框架
        main_frame = ttk.Frame(master, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置网格权重
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # 创建标签和输入框
        ttk.Label(main_frame, text="请选择或输入机器IP地址：", font=ui_font(12)).grid(row=0, column=0, sticky=tk.W,
                                                                                     pady=5)
        self.combo = ttk.Combobox(main_frame, values=self.history, width=30, font=ui_font(12))
        self.combo.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)

        # 错误提示标签
        self.error_label = ttk.Label(main_frame, text="", foreground="red", font=ui_font(10, "bold"))
        self.error_label.grid(row=2, column=0, pady=10)

        self.combo.focus_set()
        return self.combo

    def validate(self):
        ip = self.combo.get().strip()
        if not ip:
            # 显示错误信息
            self.error_label.config(text="请输入IP地址！")
            # 高亮显示空的输入框
            self.combo.config(style='Error.TCombobox')
            # 震动窗口提示
            self.bell()
            return False

        # 清除错误提示
        self.error_label.config(text="")
        self.combo.config(style='TCombobox')
        return True

    def apply(self):
        ip = self.combo.get().strip()
        if ip:
            # 保存历史，去重，最多10个
            if ip in self.history:
                self.history.remove(ip)
            self.history.insert(0, ip)
            self.history = self.history[:10]
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                for item in self.history:
                    f.write(item + '\n')
            self.ip_var = ip


class LogPackParseDialog:
    """日志打包 + 解析合并窗口：可「打包并解析」或「仅解析本地包」。"""

    def __init__(self, parent, history_file=None):
        self.parent = parent
        self.history_file = history_file or os.path.join(HISTORY_DIR, "ip_history.txt")
        self.history = []
        self.result = None  # ("pack_parse", ip) | ("parse_local", None) | None
        legacy_ip = os.path.join(APP_DIR, "ip_history.txt")
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                self.history = [line.strip() for line in f if line.strip()]
        elif os.path.exists(legacy_ip):
            with open(legacy_ip, "r", encoding="utf-8") as f:
                self.history = [line.strip() for line in f if line.strip()]

        self.win = tk.Toplevel(parent)
        self.win.title("日志打包解析")
        self.win.resizable(False, False)
        self.win.withdraw()
        try:
            self.win.transient(parent)
        except Exception:
            pass

        main = ttk.Frame(self.win, padding="20")
        main.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main.columnconfigure(0, weight=1)

        ttk.Label(
            main,
            text="先从设备打包下载日志，再自动解析；也可只解析本地压缩包。",
            font=ui_font(11),
            wraplength=360,
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 12))

        ttk.Label(main, text="机器 IP（打包并解析时必填）：", font=ui_font(12)).grid(
            row=1, column=0, sticky=tk.W, pady=4
        )
        self.combo = ttk.Combobox(main, values=self.history, width=32, font=ui_font(12))
        self.combo.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=4)
        if self.history:
            self.combo.set(self.history[0])

        self.error_label = ttk.Label(main, text="", foreground="red", font=ui_font(10, "bold"))
        self.error_label.grid(row=3, column=0, sticky=tk.W, pady=(4, 8))

        btn_row = tk.Frame(main, bg="#f0f0f0")
        btn_row.grid(row=4, column=0, sticky=tk.EW, pady=(12, 0))

        def _btn(parent, text, cmd, primary=False):
            if primary:
                f = tk.Frame(parent, bg="#007AFF", highlightthickness=0, bd=0)
                lbl = tk.Label(
                    f, text=text, bg="#007AFF", fg="white",
                    font=ui_font(12, "bold"), padx=14, pady=8, cursor="hand2",
                )
            else:
                f = tk.Frame(parent, bg="#ffffff", highlightbackground="#c7c7cc",
                             highlightthickness=1, bd=0)
                lbl = tk.Label(
                    f, text=text, bg="#ffffff", fg="#1d1d1f",
                    font=ui_font(12), padx=14, pady=8, cursor="hand2",
                )
            lbl.pack()
            for w in (f, lbl):
                w.bind("<ButtonRelease-1>", lambda e, c=cmd: c())
            return f

        _btn(btn_row, "打包并解析", self._on_pack_parse, primary=True).pack(side=tk.LEFT, padx=(0, 8))
        _btn(btn_row, "仅解析本地包", self._on_parse_local).pack(side=tk.LEFT, padx=(0, 8))
        _btn(btn_row, "取消", self._on_cancel).pack(side=tk.LEFT)

        self.win.bind("<Escape>", lambda e: self._on_cancel())
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.win.update_idletasks()
        w, h = 420, 240
        x = max(0, (self.win.winfo_screenwidth() - w) // 2)
        y = max(0, (self.win.winfo_screenheight() - h) // 2)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.deiconify()
        try:
            self.win.attributes("-topmost", True)
        except Exception:
            pass
        self.win.lift()
        self.win.focus_force()
        self.win.grab_set()
        self.combo.focus_set()
        self.win.wait_window()

    def _save_ip(self, ip):
        if ip in self.history:
            self.history.remove(ip)
        self.history.insert(0, ip)
        self.history = self.history[:10]
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            for item in self.history:
                f.write(item + "\n")

    def _on_pack_parse(self):
        ip = self.combo.get().strip()
        if not ip:
            self.error_label.config(text="请输入 IP 地址！")
            self.combo.config(style="Error.TCombobox")
            self.win.bell()
            return
        self.error_label.config(text="")
        self.combo.config(style="TCombobox")
        self._save_ip(ip)
        self.result = ("pack_parse", ip)
        self.win.grab_release()
        self.win.destroy()

    def _on_parse_local(self):
        self.result = ("parse_local", None)
        self.win.grab_release()
        self.win.destroy()

    def _on_cancel(self):
        self.result = None
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()


# 全局主窗口引用
_main_window = None


def show_excel_blocking_dialog(excel_path):
    """显示Excel文件占用弹框的通用函数"""
    global _main_window

    import threading

    print(f"显示弹框 - 当前线程: {threading.current_thread().name}")
    print(f"是否为主线程: {threading.current_thread() is threading.main_thread()}")

    if threading.current_thread() is threading.main_thread():
        # 在主线程中，直接显示弹框
        print("在主线程中显示弹框")
        if _main_window is None:
            # 如果没有主窗口，创建一个临时的
            print("创建临时主窗口")
            temp_root = tk.Tk()
            temp_root.withdraw()
            temp_root.attributes('-topmost', True)
            dialog = ExcelBlockingDialog(temp_root, excel_path)
            result = dialog.show()
            temp_root.destroy()
            return result
        else:
            # 使用主窗口
            print("使用现有主窗口")
            dialog = ExcelBlockingDialog(_main_window, excel_path)
            return dialog.show()
    else:
        # 在子线程中，使用更简单的方法
        print("在子线程中显示弹框")
        try:
            # 使用messagebox直接显示，这是最简单的线程安全方法
            print("使用messagebox显示弹框")
            result = messagebox.askokcancel(
                "Excel文件占用提示",
                f"文件被占用，需关闭Excel表格才能保存数据\n\n文件路径：{excel_path}\n\n请关闭Excel文件后点击确定。"
            )
            print(f"messagebox返回结果: {result}")

            if result:
                # 用户点击了确定，检查文件是否真的可用
                print("用户点击确定，检查文件状态...")
                try:
                    if is_file_locked(excel_path):
                        raise PermissionError("file locked")
                    wb = load_workbook(excel_path, read_only=True)
                    wb.close()
                    print("文件检查通过")
                    return True
                except Exception as check_error:
                    print(f"文件检查失败: {check_error}")
                    messagebox.showwarning("保存失败", "文件被占用，无法保存此次数据，请确保已关闭excel程序")
                    return False
            else:
                print("用户取消操作")
                messagebox.showwarning("保存失败", "文件被占用，无法保存此次数据，请确保已关闭excel程序")
                return False

        except Exception as e:
            print(f"显示弹框失败: {e}")
            import traceback
            traceback.print_exc()
            return False


class MainApplication:
    def __init__(self, root):
        print("进入MainApplication.__init__")
        global _main_window
        _main_window = root  # 保存全局引用
        self.root = root
        self.root.title("Beatbot 软测工具 (macOS)")
        self.is_parsing = False  # 防抖标志

        # 设置窗口大小（3行4列功能区）
        self.root.geometry("1280x800")
        self.root.minsize(1100, 700)

        # 配置根窗口的网格权重
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 设置样式
        self.setup_styles()

        # 创建主框架
        self.main_frame = ttk.Frame(root)
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=16, pady=12)

        # 配置主框架的网格权重：3行 × 4列
        for i in range(3):
            self.main_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):
            self.main_frame.grid_columnconfigure(i, weight=1)

        # 创建轨迹线处理器实例
        self.trajectory = TrajectoryLine()

        # 初始化进度条相关变量
        self.progress_var = tk.DoubleVar()
        self.progress_bar = None
        self.progress_label = None
        self.progress_bottom = None

        # 创建功能区域
        self.create_function_areas()

    def setup_styles(self):
        style = ttk.Style()
        # 配置标签样式
        style.configure(
            'Icon.TLabel',
            font=ui_font(36),  # 3行布局下图标略缩小
            padding=6,
            anchor='center',
            justify='center'
        )
        style.configure(
            'Function.TLabel',
            font=ui_font(11, 'bold'),
            padding=3,
            anchor='center',
            justify='center'
        )
        # 配置按钮样式
        style.configure(
            'Function.TButton',
            padding=10
        )
        # 配置错误样式
        style.configure(
            'Error.TCombobox',
            fieldbackground='#ffebee',  # 浅红色背景
            background='#ffebee',
            bordercolor='#f44336',  # 红色边框
            lightcolor='#f44336',
            darkcolor='#f44336'
        )
        style.configure(
            'Error.TEntry',
            fieldbackground='#ffebee',
            bordercolor='#f44336',
            lightcolor='#f44336',
            darkcolor='#f44336'
        )
        # 配置强调按钮样式
        style.configure(
            'Accent.TButton',
            background='#2196f3',  # 蓝色背景
            foreground='white',
            font=ui_font(10, 'bold')
        )

    def update_image_size(self, event, label, img_path):
        w, h = event.width, event.height
        max_img_w, max_img_h = int(w * 0.7), int(h * 0.5)
        try:
            img = Image.open(img_path)
            img = img.resize((max_img_w, max_img_h), pillow_resample())
            photo = ImageTk.PhotoImage(img)
            label.config(image=photo)
            label.image = photo
        except Exception:
            pass

    def _bind_card_click(self, widget, command):
        """整卡可点：递归绑定 Frame/图标/文字。"""
        if command is None:
            return
        state = {"last": 0.0}

        def _on_click(_event=None, cmd=command):
            try:
                if getattr(self, "_modal_open", False):
                    return "break"
            except Exception:
                pass
            now = time.time()
            if now - state["last"] < 0.35:
                return "break"
            state["last"] = now
            try:
                cmd()
            except Exception as e:
                messagebox.showerror("功能打开失败", str(e), parent=self.root)
            return "break"

        def _bind_tree(w):
            w.bind("<Button-1>", _on_click)
            try:
                w.configure(cursor="hand2")
            except tk.TclError:
                pass
            for child in w.winfo_children():
                _bind_tree(child)

        _bind_tree(widget)

    def _resolve_card_icon_path(self, name, preferred=None):
        """按功能名查找图标，统一 png/jpeg/jpg 与 icons/图标 目录。"""
        if not name:
            return None
        candidates = []
        if preferred:
            candidates.append(preferred)
        if name == "日志打包解析":
            for rel in ("日志解析.jpeg", "日志打包下载.jpeg", "日志解析.png", "日志打包下载.png"):
                candidates.extend([
                    resource_path(os.path.join("icons", rel)),
                    resource_path(os.path.join("图标", rel)),
                ])
        if name == "使用帮助":
            candidates.extend([
                resource_path(os.path.join("图标", "black.png")),
                resource_path(os.path.join("icons", "black.png")),
                _find_file([os.path.join("图标", "black.png"), os.path.join("icons", "black.png")]),
            ])
        for ext in (".png", ".jpeg", ".jpg"):
            rel = f"{name}{ext}"
            candidates.extend([
                resource_path(os.path.join("icons", rel)),
                resource_path(os.path.join("图标", rel)),
                _find_file([os.path.join("icons", rel), os.path.join("图标", rel)]),
            ])
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return None

    def _make_card_icon_image(self, icon_path, size=72):
        """加载图标并居中放入固定正方形画布，保证各卡片视觉尺寸一致。"""
        img = Image.open(icon_path).convert("RGBA")
        img.thumbnail((size, size), pillow_resample())
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
        return ImageTk.PhotoImage(canvas)

    def create_function_areas(self):
        """创建功能区域：3行 × 4列；图标+文字作为整体在卡片中居中。"""
        self.card_progress = {}
        # 布局：
        # 第1行：视频标定矫正 / 轨迹 / 池壁 / 日志打包解析
        # 第2行：日志删除 / MCU工具 / 串口调试 / 手机型号转换
        # 第3行：预留… / 使用帮助（末格）
        function_cards = [
            {"name": "视频标定矫正", "command": self.open_video_calib, "row": 0, "column": 0, "icon": None},
            {"name": "轨迹线绘制", "command": self.mcu_tools, "row": 0, "column": 1,
             "icon": resource_path("icons/轨迹线绘制.jpeg")},
            {"name": "池壁轨迹线绘制", "command": self.pool_wall_trajectory, "row": 0, "column": 2,
             "icon": resource_path("icons/池壁轨迹线绘制.jpeg")},
            {"name": "日志打包解析", "command": self.log_pack_and_parse, "row": 0, "column": 3,
             "icon": resource_path("icons/日志解析.jpeg")},
            {"name": "日志一键删除", "command": self.delete_log, "row": 1, "column": 0, "icon": None},
            {"name": "MCU工具", "command": self.open_mcu_tool, "row": 1, "column": 1, "icon": None},
            {"name": "串口调试", "command": self.serial_debug_tool, "row": 1, "column": 2, "icon": None},
            {"name": "手机型号转换", "command": self.open_phone_model_conversion, "row": 1, "column": 3, "icon": None},
            {"name": "", "command": None, "row": 2, "column": 0, "icon": None},
            {"name": "", "command": None, "row": 2, "column": 1, "icon": None},
            {"name": "", "command": None, "row": 2, "column": 2, "icon": None},
            {"name": "使用帮助", "command": self.show_help, "row": 2, "column": 3,
             "icon": resource_path(os.path.join("图标", "black.png"))},
        ]
        card_bg = "#f5f5f7"
        card_fg = "#1d1d1f"
        empty_bg = "#fafafa"
        title_font = ui_font(12, "bold")
        icon_font = ui_font(34)
        icon_size = 72
        emoji_fallback = {
            "视频标定矫正": "📐",
            "轨迹线绘制": "📊",
            "池壁轨迹线绘制": "🏊",
            "日志打包解析": "📦",
            "日志一键删除": "⚡",
            "MCU工具": "🔧",
            "串口调试": "🔌",
            "手机型号转换": "📱",
            "使用帮助": "📖",
        }

        for i in range(3):
            self.main_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):
            self.main_frame.grid_columnconfigure(i, weight=1)

        for row in range(3):
            for col in range(4):
                func = next((f for f in function_cards if f["row"] == row and f["column"] == col), None)
                has_feature = bool(func and func.get("name") and func.get("command"))
                bg = card_bg if has_feature else empty_bg
                # tk.Frame/Label：macOS 上 ttk.Label 常吞掉点击，且易顶对齐
                frame = tk.Frame(
                    self.main_frame,
                    bg=bg,
                    highlightbackground="#d2d2d7" if has_feature else "#e5e5ea",
                    highlightthickness=1,
                    bd=0,
                    width=280,
                    height=180,
                    cursor="hand2" if has_feature else "arrow",
                )
                frame.grid(row=row, column=col, sticky="nsew", padx=10, pady=8)
                frame.grid_propagate(False)
                frame.pack_propagate(False)

                # 内容区铺满；进度条叠在底部，不挤占居中布局
                content = tk.Frame(frame, bg=bg)
                content.pack(expand=True, fill="both")
                progress_area = tk.Frame(frame, bg=bg, height=44)
                progress_area.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0)
                progress_area.lift()

                if not func or not func.get("name"):
                    continue

                # 图标 + 文字作为整体，在卡片中心居中
                block = tk.Frame(content, bg=bg)
                block.place(relx=0.5, rely=0.48, anchor="center")

                icon_img = None
                icon_path = self._resolve_card_icon_path(func["name"], func.get("icon"))
                if icon_path:
                    try:
                        icon_img = self._make_card_icon_image(icon_path, size=icon_size)
                    except Exception:
                        icon_img = None

                if icon_img:
                    icon_label = tk.Label(block, image=icon_img, bg=bg, cursor="hand2", bd=0)
                    icon_label.image = icon_img
                    icon_label.pack(side="top", pady=(0, 10))
                else:
                    emoji = emoji_fallback.get(func["name"], "📦")
                    icon_label = tk.Label(
                        block, text=emoji, font=icon_font,
                        bg=bg, fg=card_fg, cursor="hand2", bd=0,
                        width=3, height=1,
                    )
                    icon_label.pack(side="top", pady=(0, 10))

                label = tk.Label(
                    block, text=func["name"], font=title_font,
                    bg=bg, fg=card_fg, cursor="hand2", bd=0,
                )
                label.pack(side="top")

                progress_var = tk.DoubleVar()
                progress_text = tk.Label(
                    progress_area, text="", font=ui_font(8),
                    fg="#666666", bg=bg, anchor="center", justify="center",
                )
                progress_bar = ttk.Progressbar(progress_area, variable=progress_var, length=160, mode="determinate")
                progress_label = tk.Label(progress_area, text="", font=ui_font(9), bg=bg)
                progress_bar.place_forget()
                progress_text.place_forget()
                self.card_progress[(row, col)] = {
                    "bar": progress_bar,
                    "label": progress_label,
                    "var": progress_var,
                    "text": progress_text,
                }

                if has_feature:
                    self._bind_card_click(frame, func["command"])

    def show_card_progress(self, row, col, total, text=None):
        p = self.card_progress.get((row, col))
        if p:
            p['bar'].config(maximum=total)
            p['var'].set(0)
            if text is not None:
                p['text'].config(text=text)
                p['text'].place(relx=0.5, rely=0.25, anchor='center')
            else:
                p['text'].config(text="")
                p['text'].place(relx=0.5, rely=0.25, anchor='center')
            p['bar'].place(relx=0.5, rely=0.65, anchor='center')

    def update_card_progress(self, row, col, value, total, text=None):
        p = self.card_progress.get((row, col))
        if p:
            p['bar'].config(maximum=total)
            p['var'].set(value)
            if text is not None:
                p['text'].config(text=text)
            p['bar'].update()
            p['text'].update()

    def close_card_progress(self, row, col):
        p = self.card_progress.get((row, col))
        if p:
            p['bar'].place_forget()
            p['text'].place_forget()
            p['var'].set(0)
            p['text'].config(text="")

    def _make_card_command(self, cmd):
        return lambda e: cmd()

    def open_video_calib(self):
        """打开视频标定矫正（嵌入为子窗口，来自 Beatbot-tools/spjz）。"""
        global open_video_calib_tool
        opener = open_video_calib_tool or _load_video_calib_opener()
        open_video_calib_tool = opener
        if opener is None:
            hint = _find_file([
                os.path.join("spjz", "视频标定矫正.py"),
                os.path.join("Beatbot-tools", "spjz", "视频标定矫正.py"),
            ]) or "(未找到 视频标定矫正.py)"
            messagebox.showerror(
                "无法打开",
                "未找到视频标定矫正模块。\n\n"
                "请确认打包时已包含 spjz，或源码目录存在：\n"
                "Beatbot-tools/spjz/视频标定矫正.py\n\n"
                f"查找结果: {hint}",
            )
            return
        try:
            opener(self.root)
        except Exception as e:
            messagebox.showerror("视频标定矫正", f"打开失败：\n{e}")

    def serial_debug_tool(self):
        """打开串口调试助手（嵌入为子窗口，来自 Beatbot-tools/串口工具）。"""
        global open_serial_tool
        opener = open_serial_tool or _load_serial_tool_opener()
        open_serial_tool = opener
        if opener is None:
            hint = _find_file([
                os.path.join("serial_tool", "串口工具.py"),
                os.path.join("串口工具", "串口工具.py"),
            ]) or "(未找到 串口工具.py)"
            messagebox.showerror(
                "无法打开",
                "未找到串口工具模块。\n\n"
                "请确认打包时已包含串口工具，或源码目录存在：\n"
                "Beatbot-tools/串口工具/串口工具.py\n\n"
                f"查找结果: {hint}",
            )
            return
        try:
            opener(self.root)
        except Exception as e:
            messagebox.showerror("串口调试", f"打开失败：\n{e}")

    def _mcu_tool_script_path(self):
        """定位 MCU 工具脚本（源码 / 打包均可）。"""
        found = _find_file([
            os.path.join("mcu_tool", "Python版", "20260804MCU工具.py"),
            os.path.join("MCU工具", "Python版", "20260804MCU工具.py"),
            os.path.join("mcu_tool", "20260804MCU工具.py"),
            os.path.join("MCU工具", "20260804MCU工具.py"),
            os.path.join("Beatbot-tools", "MCU工具", "20260804MCU工具.py"),
            os.path.join("Softwaretest", "MCU工具", "Python版", "20260804MCU工具.py"),
            os.path.join("..", "MCU工具", "Python版", "20260804MCU工具.py"),
        ])
        if found:
            return found
        # 兼容旧 resource_path
        try:
            p = resource_path(os.path.join("MCU工具", "Python版", "20260804MCU工具.py"))
            if os.path.isfile(p):
                return p
        except Exception:
            pass
        return os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "MCU工具", "Python版", "20260804MCU工具.py"
        ))

    def _excel_tool_script_path(self):
        """定位 excel_tool.py（源码 / 打包均可）。"""
        found = _find_file([
            os.path.join("excel转换工具", "excel_tool.py"),
            os.path.join("excel_tool", "excel_tool.py"),
            os.path.join("Beatbot-tools", "excel转换工具", "excel_tool.py"),
            os.path.join("..", "excel转换工具", "excel_tool.py"),
        ])
        if found:
            return found
        try:
            p = resource_path(os.path.join("excel转换工具", "excel_tool.py"))
            if os.path.isfile(p):
                return p
        except Exception:
            pass
        return os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "excel转换工具", "excel_tool.py"
        ))

    def open_phone_model_conversion(self):
        """手机型号转换：内嵌打开 excel转换工具/excel_tool.py（可与其它功能并行）。"""
        win = getattr(self, "_phone_model_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
                    return
            except tk.TclError:
                self._phone_model_win = None

        excel_tool_script = self._excel_tool_script_path()
        if not os.path.isfile(excel_tool_script):
            messagebox.showerror(
                "手机型号转换",
                "未找到 excel_tool.py。\n\n"
                "请确认打包时已包含 excel转换工具，或源码目录存在该文件。\n\n"
                f"期望路径：\n{excel_tool_script}",
            )
            return

        try:
            tool_dir = os.path.dirname(excel_tool_script)
            if tool_dir and tool_dir not in sys.path:
                sys.path.insert(0, tool_dir)
            mod = _load_module_from_file("xm_excel_phone_model_tool", excel_tool_script)
            ExcelToolApp = getattr(mod, "ExcelToolApp", None)
            if ExcelToolApp is None:
                raise AttributeError("excel_tool.py 中未找到 ExcelToolApp")

            top = tk.Toplevel(self.root)
            top.title("手机型号转换")
            # 不用 transient/grab，避免挡住主界面其它功能窗
            ExcelToolApp(top)
            self._phone_model_win = top

            def _on_destroy(event, w=top):
                if event.widget is w:
                    self._phone_model_win = None

            top.bind("<Destroy>", _on_destroy)
            try:
                top.lift()
                top.focus_force()
            except tk.TclError:
                pass
        except Exception as e:
            messagebox.showerror("手机型号转换", f"打开失败：\n{e}")

    def open_mcu_tool(self):
        """打开内嵌 MCU 工具（InnovateTool）窗口。"""
        # 已打开则前置
        win = getattr(self, "_mcu_tool_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
                    return
            except tk.TclError:
                self._mcu_tool_win = None

        script = self._mcu_tool_script_path()
        if not os.path.isfile(script):
            messagebox.showerror(
                "MCU工具",
                f"未找到 MCU 工具脚本：\n{script}\n\n请确认打包资源或源码目录存在该文件。",
            )
            return
        try:
            # 确保打包环境下 scrolledtext / serial 已就绪
            import tkinter.scrolledtext  # noqa: F401
            mod = _load_module_from_file("xm_innovate_mcu_tool", script)
            if not hasattr(mod, "MainApp"):
                raise AttributeError("MCU 工具模块缺少 MainApp")
            child = mod.MainApp(master=self.root)
            self._mcu_tool_win = child

            def _on_destroy(event, w=child):
                if event.widget is w:
                    self._mcu_tool_win = None

            child.bind("<Destroy>", _on_destroy)
        except Exception as e:
            messagebox.showerror("MCU工具", f"打开失败：\n{e}")

    def _start_trajectory_workflow(self, process_func):
        """主线程弹窗选参；OpenCV 窗口也必须在主线程（macOS Cocoa HighGUI 限制）。"""
        try:
            print("打开轨迹线参数填写弹窗...")
            info = show_info_dialog(self.root)
            if not info:
                print("用户取消参数填写")
                return
            video_path = self._ask_trajectory_video()
            if not video_path:
                print("未选择视频文件")
                return

            def _run():
                try:
                    process_func(video_path, info)
                except Exception as exc:
                    import traceback
                    traceback.print_exc()
                    try:
                        messagebox.showerror(
                            "轨迹线绘制",
                            f"处理视频失败：\n{exc}",
                            parent=self.root,
                        )
                    except Exception:
                        pass

            # 不可放到后台线程：cv2.namedWindow/imshow/waitKey 在子线程会抛
            # “Unknown C++ exception from OpenCV code”
            self.root.after(50, _run)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            messagebox.showerror("轨迹线绘制", f"打开参数弹窗失败：\n{exc}", parent=self.root)

    def _ask_trajectory_video(self):
        return filedialog.askopenfilename(
            parent=self.root,
            title="选择视频文件",
            filetypes=[
                ("MP4 文件", "*.mp4"),
                ("AVI 文件", "*.avi"),
                ("MOV 文件", "*.mov"),
                ("MKV 文件", "*.mkv"),
                ("所有文件", "*.*")
            ]
        )

    def mcu_tools(self):
        self._start_trajectory_workflow(self.trajectory.process_video)

    def pool_wall_trajectory(self):
        """池壁轨迹线绘制功能"""
        self._start_trajectory_workflow(self.trajectory.process_pool_wall_video)

    def show_progress(self, total):
        if not hasattr(self, 'progress_var'):
            self.progress_var = tk.DoubleVar()
        if not hasattr(self, 'progress_bar') or self.progress_bar is None:
            self.progress_bar = ttk.Progressbar(self.main_frame, maximum=total, variable=self.progress_var, length=400)
            self.progress_bar.grid(row=2, column=0, columnspan=4, sticky='ew', padx=20, pady=(10, 0))
        if not hasattr(self, 'progress_label') or self.progress_label is None:
            self.progress_label = ttk.Label(self.main_frame, text="", font=ui_font(12))
            self.progress_label.grid(row=3, column=0, columnspan=4, sticky='ew', padx=20)
        self.progress_bar.config(maximum=total)
        self.progress_var.set(0)
        self.progress_bar.grid()
        self.progress_label.grid()

    def update_progress(self, value, total):
        if hasattr(self, 'progress_bar') and self.progress_bar:
            self.progress_bar.config(maximum=total)
            self.progress_var.set(value)
            self.progress_bar.update()
        if hasattr(self, 'progress_label') and self.progress_label:
            self.progress_label.update()

    def close_progress(self):
        if hasattr(self, 'progress_bar') and self.progress_bar:
            self.progress_bar.grid_remove()
        if hasattr(self, 'progress_label') and self.progress_label:
            self.progress_label.grid_remove()

    def show_help(self):
        if hasattr(self, 'help_win') and self.help_win and self.help_win.winfo_exists():
            self.help_win.lift()
            self.help_win.focus_force()
            return
        self.help_win = tk.Toplevel(self.root)
        self.help_win.title("使用帮助")
        self.help_win.geometry("640x520")
        self.help_win.resizable(True, True)

        # 设置窗口始终在最前面
        self.help_win.attributes('-topmost', True)
        self.help_win.lift()
        self.help_win.focus_force()
        help_text = mac_help_text(app_data_dir(), picture_dir())
        # 用grid布局分上下两行，保证版本号可见
        content_frame = ttk.Frame(self.help_win)
        content_frame.pack(expand=True, fill="both")
        content_frame.rowconfigure(0, weight=1)
        content_frame.rowconfigure(1, weight=0)
        content_frame.columnconfigure(0, weight=1)
        text = tk.Text(content_frame, wrap="word", font=ui_font(12), padx=10, pady=10)
        text.insert("1.0", help_text)
        text.config(state="disabled")
        text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        import datetime, os
        version_file = os.path.join(os.path.dirname(__file__), 'help_version.txt')
        today = datetime.datetime.now().strftime('%Y%m%d')
        version = f'{today}-1'
        if os.path.exists(version_file):
            with open(version_file, 'r+') as f:
                lines = f.readlines()
                if lines and lines[-1].startswith(today):
                    last = lines[-1].strip()
                    last_num = int(last.split('-')[-1])
                    version = f'{today}-{last_num + 1}'
                f.write(version + '\n')
        else:
            with open(version_file, 'w') as f:
                f.write(version + '\n')
        version_label = ttk.Label(content_frame, text=f"版本号：{version}", font=ui_font(10), foreground="#888888")
        version_label.grid(row=1, column=0, sticky="ew", pady=(0, 8))

    def log_pack_and_parse(self):
        """合并入口：先打包下载，再解析；也可仅解析本地压缩包。"""
        dlg = LogPackParseDialog(self.root)
        if not dlg.result:
            return
        action, ip = dlg.result
        if action == "parse_local":
            self.unzip_and_parse_zip()
            return
        if action == "pack_parse":
            if not self.is_same_lan(ip):
                messagebox.showerror("网络错误", "目标设备不在同一局域网内，无法操作！")
                return
            threading.Thread(target=self._do_pack_then_parse, args=(ip,), daemon=True).start()

    def unzip_and_parse_zip(self):
        archive_path = filedialog.askopenfilename(
            title="选择压缩包",
            filetypes=[
                ("压缩包", "*.zip *.tar.gz *.tar"),
                ("Zip files", "*.zip"),
                ("Tar GZ files", "*.tar.gz"),
                ("Tar files", "*.tar"),
                ("所有文件", "*.*")
            ]
        )
        if archive_path:
            threading.Thread(
                target=lambda: self.extract_zip_and_parse_with_progress(archive_path),
                daemon=True,
            ).start()

    def _log_card_pos(self):
        """日志打包解析功能卡坐标。"""
        return 0, 3

    def extract_zip_and_parse_with_progress(self, archive_path, done_msg=None):
        import tarfile, zipfile, os
        row, col = self._log_card_pos()
        extract_dir = os.path.splitext(os.path.splitext(archive_path)[0])[0] if archive_path.endswith('.tar.gz') else \
            os.path.splitext(archive_path)[0]
        print(f"[DEBUG] 解压目录: {extract_dir}")
        try:
            self.root.after(0, lambda: self.show_card_progress(row, col, 100, "正在解压日志包..."))
            if archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif archive_path.endswith('.tar.gz') or archive_path.endswith('.tar'):
                with tarfile.open(archive_path, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_dir)
            else:
                self.root.after(0, lambda: [
                    self.close_card_progress(row, col),
                    messagebox.showerror("错误", "不支持的压缩包格式"),
                ])
                return
            # 收集所有bin文件
            bin_files = []
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    if file.lower().endswith('.bin'):
                        bin_files.append((os.path.join(root, file), root, file))
            print(f"[DEBUG] 查找到bin文件: {bin_files}")
            total = len(bin_files)
            if total == 0:
                self.root.after(0, lambda: [
                    self.close_card_progress(row, col),
                    messagebox.showinfo(
                        "完成",
                        done_msg or f"已解压，但未找到 bin 文件。\n目录: {extract_dir}",
                    ),
                ])
                return
            self.root.after(0, lambda: self.show_card_progress(row, col, total, f"0/{total} bin文件解析中..."))
            count = 0
            with ProcessPoolExecutor(max_workers=4) as executor:
                for idx, result in enumerate(executor.map(process_one_bin, bin_files), 1):
                    count += result
                    c = count
                    self.root.after(
                        0, self.update_card_progress, row, col, c, total,
                        f"{c}/{total} bin文件解析中...",
                    )
            msg = done_msg or f"共解析了 {count} 个 bin 文件"
            self.root.after(0, lambda: [
                self.close_card_progress(row, col),
                messagebox.showinfo("完成", msg),
            ])
        except Exception as e:
            err = str(e)
            self.root.after(0, lambda: [
                self.close_card_progress(row, col),
                messagebox.showerror("解析失败", err),
            ])

    def batch_convert_multi_folders(self, folders):
        import os
        import shutil
        import concurrent.futures

        if not folders:
            print("[DEBUG] 没有拖拽到任何文件夹")
            return

        # 防止重复运行
        if getattr(self, "_is_running_multi_folder", False):
            print("[DEBUG] 多文件夹转换任务已在运行中，忽略本次请求。")
            return
        self._is_running_multi_folder = True
        self._has_shown_multi_folder_msg = False

        # 1. 收集所有 bin 文件及其目标路径
        all_bin_files = []
        for folder in folders:
            new_folder = folder + "_log"
            for root, dirs, files in os.walk(folder):
                rel_path = os.path.relpath(root, folder)
                target_dir = os.path.join(new_folder, rel_path) if rel_path != '.' else new_folder
                os.makedirs(target_dir, exist_ok=True)
                for filename in files:
                    src_file = os.path.join(root, filename)
                    if filename.lower().endswith('.bin'):
                        all_bin_files.append((src_file, target_dir, filename))
                    else:
                        dst_file = os.path.join(target_dir, filename)
                        shutil.copy2(src_file, dst_file)

        total = len(all_bin_files)
        print(f"[DEBUG] 拖拽解析，总共 {total} 个 bin 文件")
        row, col = self._log_card_pos()
        self.root.after(0, lambda: self.show_card_progress(row, col, total))

        def run_and_update():
            count = 0
            max_workers = min(32, os.cpu_count() * 3)
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(process_one_bin, args) for args in all_bin_files]
                for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                    try:
                        result = fut.result()
                        count += result
                    except Exception as e:
                        print(f"[ERROR] 子任务失败: {e}")
                    self.root.after(
                        0,
                        lambda i=i: self.update_card_progress(
                            row, col, i, total, f"解析中... ({i}/{total})"
                        ),
                    )

            def show_msg():
                if self._has_shown_multi_folder_msg:
                    return
                self._has_shown_multi_folder_msg = True
                self.close_card_progress(row, col)
                self.progress_label.config(
                    text=f"已将 {count} 个 bin 文件转为明文 log，其他文件已原样保留到各自 _log 文件夹"
                )
                self.is_parsing = False
                self._is_running_multi_folder = False
                print("[DEBUG] 多文件夹转换完成，弹窗提示")
                messagebox.showinfo(
                    "完成",
                    f"已将 {count} 个 bin 文件转为明文 log，其他文件已原样保留到各自 _log 文件夹",
                )

            self.root.after(0, show_msg)

        threading.Thread(target=run_and_update, daemon=True).start()

    def is_same_lan(self, ip):
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            return '.'.join(local_ip.split('.')[:3]) == '.'.join(ip.split('.')[:3])
        except:
            return False

    def _do_pack_then_parse(self, ip):
        """后台：打包下载完成后自动解析。"""
        import os
        row, col = self._log_card_pos()
        try:
            self.root.after(0, lambda: self.show_card_progress(row, col, 100, "正在连接设备..."))
            run_adb(["-s", f"{ip}:5555", "root"], timeout=30)
            self.root.after(0, lambda: self.update_card_progress(row, col, 15, 100, "正在连接设备..."))
            proc = run_adb(["connect", f"{ip}:5555"], timeout=30)
            out_str = decode_proc_output(proc.stdout)
            if "connected to" not in out_str:
                self.root.after(0, lambda: [
                    self.close_card_progress(row, col),
                    messagebox.showerror("连接失败", f"ADB连接失败：{out_str}"),
                ])
                return
            self.root.after(0, lambda: self.update_card_progress(row, col, 30, 100, "正在获取设备信息..."))
            sn = "UNKNOWN"
            try:
                sn_proc = run_adb(["-s", f"{ip}:5555", "shell", "cat /mnt/private/sn.txt"], timeout=30)
                sn = decode_proc_output(sn_proc.stdout).strip()
                if not sn or "not found" in sn or "error" in sn.lower():
                    sn_proc2 = run_adb(["-s", f"{ip}:5555", "shell", "hostname"], timeout=30)
                    sn = decode_proc_output(sn_proc2.stdout).strip() or "UNKNOWN"
            except Exception:
                sn = "UNKNOWN"
            time_proc = run_adb(["-s", f"{ip}:5555", "shell", "date +%Y-%m-%d-%H-%M-%S"], timeout=30)
            timestamp = decode_proc_output(time_proc.stdout).strip()
            run_adb(["-s", f"{ip}:5555", "shell", f"rm -f /data/manual_pack-{sn}-*.tar.gz"], timeout=30)
            tar_name = f"/data/manual_pack-{sn}-{timestamp}.tar.gz"
            self.root.after(0, lambda: self.update_card_progress(row, col, 45, 100, "正在打包日志..."))
            pack_shell = (
                f"tar -czf {tar_name} "
                "/data/clean_record /data/conf /data/DP_clean_record /data/log /data/transfer_data "
                "/etc/os_version /mnt/private /tmp/log /tmp/XM_LOG"
            )
            run_adb(["-s", f"{ip}:5555", "shell", pack_shell], timeout=600)
            self.root.after(0, lambda: self.update_card_progress(row, col, 70, 100, "正在下载日志包..."))
            dist_dir = str(app_data_dir())
            os.makedirs(dist_dir, exist_ok=True)
            local_path = os.path.join(dist_dir, os.path.basename(tar_name))
            run_adb(["-s", f"{ip}:5555", "pull", tar_name, local_path], timeout=600)
            if not os.path.isfile(local_path):
                self.root.after(0, lambda: [
                    self.close_card_progress(row, col),
                    messagebox.showerror("下载失败", f"未找到下载文件：\n{local_path}"),
                ])
                return
            self.root.after(0, lambda: self.update_card_progress(row, col, 85, 100, "打包完成，开始解析..."))
            self.extract_zip_and_parse_with_progress(
                local_path,
                done_msg=f"打包并解析完成。\n日志包: {local_path}",
            )
        except Exception as e:
            err_msg = str(e)
            self.root.after(0, lambda: [
                self.close_card_progress(row, col),
                messagebox.showerror("异常", f"日志打包解析流程异常：{err_msg}"),
            ])

    def pack_log(self):
        """兼容旧入口：转到合并窗口。"""
        self.log_pack_and_parse()

    def delete_log(self):
        # 日志一键删除功能，弹窗选择/输入IP
        dlg = IPInputDialog(self.root, "日志一键删除")
        ip = dlg.ip_var
        if ip is None:
            return  # 用户点击取消，直接返回不提示
        if not self.is_same_lan(ip):
            messagebox.showerror("网络错误", "目标设备不在同一局域网内，无法操作！")
            return

        def do_delete():
            try:
                run_adb(["-s", f"{ip}:5555", "root"], timeout=10)
                proc = run_adb(["connect", f"{ip}:5555"], timeout=10)
                out_str = decode_proc_output(proc.stdout)
                if "connected to" not in out_str:
                    self.root.after(0, lambda: messagebox.showerror("连接失败", f"ADB连接失败：{out_str}"))
                    return
                for shell_cmd in ("rm -rf /data/log/*", "rm -rf /tmp/log/*"):
                    run_adb(["-s", f"{ip}:5555", "shell", shell_cmd], timeout=10)
                self.root.after(0, lambda: messagebox.showinfo("完成", "一键清除已完成"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("异常", f"日志删除异常：{e}"))

        threading.Thread(target=do_delete, daemon=True).start()


# 保证主入口只在主进程执行，防止多进程时重复启动GUI
if __name__ == "__main__":
    import traceback

    print("程序已启动 (Beatbot-tools / macOS)")
    try:
        multiprocessing.freeze_support()  # 兼容 pyinstaller 多进程打包
        setup_tesseract_cmd()
        print("准备初始化 Tk 根窗口")
        root = create_tk_root()
        try:
            root.lift()
            root.attributes("-topmost", True)
            root.after(200, lambda: root.attributes("-topmost", False))
            root.focus_force()
        except Exception:
            pass
        print("Tk 根窗口初始化完成")
        app = MainApplication(root)
        print("MainApplication初始化完成")
        root.mainloop()
    except Exception as e:
        print("程序启动异常：", e)
        traceback.print_exc()
        try:
            messagebox.showerror("启动失败", str(e))
        except Exception:
            pass
