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
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None
import multiprocessing
from platform_compat import (
    app_data_dir,
    create_tk_root,
    is_file_locked,
    mac_help_text,
    mono_font,
    picture_dir,
    pillow_resample,
    run_adb,
    decode_proc_output,
    setup_tesseract_cmd,
    ui_font,
)
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

# 强制纳入打包依赖：MCU/串口工具运行时需要（PyInstaller 不会分析 data 里的 .py）
import tkinter.scrolledtext  # noqa: F401
try:
    import serial  # noqa: F401
    from serial.tools import list_ports  # noqa: F401
except ImportError:
    serial = None
    list_ports = None


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


def _load_serial_tool_opener():
    """加载串口工具 open_serial_tool；失败返回 None。"""
    script = _find_file([
        os.path.join("serial_tool", "串口工具.py"),
        os.path.join("串口工具", "串口工具.py"),
        os.path.join("Beatbot-tools", "串口工具", "串口工具.py"),
        os.path.join("Softwaretest-win", "串口工具", "串口工具.py"),
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
def get_history(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_history(path, value):
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
    # 短暂置顶帮助获得系统焦点，随后取消，避免挡住后续对话框
    try:
        root.attributes("-topmost", True)
        root.update()
        root.attributes("-topmost", False)
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


class TrajectoryLine:
    def __init__(self):
        # 固定视频帧大小和默认轨迹线宽度
        self.FRAME_WIDTH = 640
        self.FRAME_HEIGHT = 480
        self.TRACK_WIDTH = 15  # 默认轨迹线宽度

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
        """创建跟踪器，兼容不同OpenCV版本"""
        try:
            if hasattr(cv2, 'legacy') and hasattr(cv2.legacy, 'TrackerCSRT_create'):
                return cv2.legacy.TrackerCSRT_create()
            elif hasattr(cv2, 'TrackerCSRT_create'):
                return cv2.TrackerCSRT_create()
            else:
                logging.error("未找到CSRT跟踪器")
                return None
        except Exception as e:
            logging.error(f"创建跟踪器失败: {str(e)}")
            return None

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

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
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

            frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))

            tracker = None
            init_box = None
            all_track_points = []
            polygon_points = []  # 存储多边形的点
            drawing_polygon = True  # 标记是否在绘制多边形

            def on_mouse(event, x, y, flags, param):
                nonlocal drawing_polygon
                if drawing_polygon:
                    if event == cv2.EVENT_LBUTTONDOWN:
                        polygon_points.append((x, y))
                    elif event == cv2.EVENT_RBUTTONDOWN and len(polygon_points) > 2:
                        drawing_polygon = False

            cv2.namedWindow("Tracking")
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
            # 获取多边形内的所有点
            points_inside_polygon = []
            for y in range(self.FRAME_HEIGHT):
                for x in range(self.FRAME_WIDTH):
                    if cv2.pointPolygonTest(contours[0], (x, y), False) >= 0:
                        points_inside_polygon.append((x, y))

            white_trail = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)

            print("按空格键选择要跟踪的目标，按 q 键退出")
            end_status = 'Yes'

            while True:
                frame_count += 1
                if not ret:
                    print("视频播放完毕或读取失败")
                    break

                overlay = frame.copy()

                # 显示多边形区域
                cv2.polylines(overlay, [np.array(polygon_points, np.int32)], isClosed=True, color=(0, 255, 255),
                              thickness=2)

                # 绘制轨迹线（透明绿色）
                for i in range(1, len(all_track_points)):
                    if all_track_points[i - 1] and all_track_points[i]:
                        cv2.line(overlay, all_track_points[i - 1], all_track_points[i], (0, 255, 0), track_width)
                        cv2.line(white_trail, all_track_points[i - 1], all_track_points[i], (255, 255, 255),
                                 max(1, track_width // 4))

                # 叠加白色轨迹层
                track_overlay = cv2.add(overlay, white_trail)

                if frame_count % 20 == 0:
                    covered_area = 0
                    for point in points_inside_polygon:
                        x, y = point
                        if overlay[y, x][1] == 255 and overlay[y, x][0] == 0 and overlay[y, x][2] == 0:
                            covered_area += 1
                    coverage_rate = (covered_area / polygon_area) * 100 if polygon_area > 0 else 0

                cv2.putText(overlay, f"Coverage: {coverage_rate:.2f}%", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 139, 255), 2)

                # 显示结果帧
                alpha = 0.3
                result_frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
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

                cv2.imshow("Coverage", result_frame)
                cv2.imshow("Tracking", result_track_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == ord('Q'):
                    end_status = 'No'
                    break
                elif key == ord(' '):
                    init_box = cv2.selectROI("Select object", frame, fromCenter=False)
                    if any(init_box):
                        tracker = self.create_tracker()
                        if tracker is not None:
                            tracker.init(frame, init_box)
                            current_track_points = []
                            all_track_points.extend(current_track_points)
                            print("目标选择完成，开始跟踪")
                        else:
                            print("无法初始化跟踪器，请确保已安装 OpenCV contrib 模块")
                    cv2.destroyWindow("Select object")

                if tracker:
                    success, bbox = tracker.update(frame)
                    if success:
                        x, y, w, h = [int(v) for v in bbox]
                        center_point = (int(x + w / 2), int(y + h / 2))
                        all_track_points.append(center_point)
                        # 在当前帧上显示跟踪框
                        cv2.rectangle(result_track_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    else:
                        print("目标跟踪失败，请重新选择目标")
                        tracker = None

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
        finally:
            if 'cap' in locals():
                cap.release()
            cv2.destroyAllWindows()

    def process_pool_wall_video(self, video_path, info):
        """处理池壁轨迹线绘制视频"""
        try:
            frame_count = 0
            coverage_rate = 0
            if not os.path.exists(video_path):
                logging.error(f"视频文件 {video_path} 不存在")
                return

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
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

            frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))

            tracker = None
            init_box = None
            all_track_points = []

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

            cv2.namedWindow("Pool Wall Drawing")
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

            print("按空格键选择要跟踪的目标，按 q 键退出")
            end_status = 'Yes'

            while True:
                frame_count += 1
                if not ret:
                    print("视频播放完毕或读取失败")
                    break

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

                # 绘制轨迹线（透明绿色）
                for i in range(1, len(all_track_points)):
                    if all_track_points[i - 1] and all_track_points[i]:
                        cv2.line(overlay, all_track_points[i - 1], all_track_points[i], (0, 255, 0), track_width)
                        cv2.line(white_trail, all_track_points[i - 1], all_track_points[i], (255, 255, 255),
                                 max(1, track_width // 4))

                # 叠加白色轨迹层
                track_overlay = cv2.add(overlay, white_trail)

                if frame_count % 20 == 0:
                    # 计算中间区域的覆盖率
                    covered_area = 0
                    for y in range(self.FRAME_HEIGHT):
                        for x in range(self.FRAME_WIDTH):
                            if middle_mask[y, x] > 0:  # 在中间区域内
                                if overlay[y, x][1] == 255 and overlay[y, x][0] == 0 and overlay[y, x][2] == 0:
                                    covered_area += 1
                    coverage_rate = (covered_area / middle_area) * 100 if middle_area > 0 else 0

                cv2.putText(overlay, f"Middle Area Coverage: {coverage_rate:.2f}%", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 139, 255), 2)

                # 显示结果帧
                alpha = 0.3
                result_frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
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

                cv2.imshow("Pool Wall Coverage", result_frame)
                cv2.imshow("Pool Wall Tracking", result_track_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == ord('Q'):
                    end_status = 'No'
                    break
                elif key == ord(' '):
                    init_box = cv2.selectROI("Select object", frame, fromCenter=False)
                    if any(init_box):
                        tracker = self.create_tracker()
                        if tracker is not None:
                            tracker.init(frame, init_box)
                            current_track_points = []
                            all_track_points.extend(current_track_points)
                            print("目标选择完成，开始跟踪")
                        else:
                            print("无法初始化跟踪器，请确保已安装 OpenCV contrib 模块")
                    cv2.destroyWindow("Select object")

                if tracker:
                    success, bbox = tracker.update(frame)
                    if success:
                        x, y, w, h = [int(v) for v in bbox]
                        center_point = (int(x + w / 2), int(y + h / 2))
                        all_track_points.append(center_point)
                        # 在当前帧上显示跟踪框
                        cv2.rectangle(result_track_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    else:
                        print("目标跟踪失败，请重新选择目标")
                        tracker = None

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

        # Excel 默认输出到 ~/Documents/BeatbotDist（可用 BEATBOT_DIST 覆盖）
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
    def __init__(self, parent, title, history_file='ip_history.txt'):
        self.history_file = history_file
        self.ip_var = None
        self.history = []
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
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

    def buttonbox(self):
        """自定义按钮：中文「确定/取消」，样式与轨迹线信息弹窗一致。"""
        box = tk.Frame(self)
        bar, _, _ = make_mac_safe_dialog_buttons(box, self.ok, self.cancel, font=ui_font(12))
        try:
            bar.configure(bg=box.cget("bg"))
        except Exception:
            pass
        bar.pack(pady=8)
        box.pack()
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

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
            with open(self.history_file, 'w') as f:
                for item in self.history:
                    f.write(item + '\n')
            self.ip_var = ip


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
        self.root.title("Beatbot软测工具")
        self.is_parsing = False  # 防抖标志
        self._modal_open = False  # 模态弹窗期间屏蔽主界面卡片点击穿透

        # 设置窗口大小（3行4列功能区）
        self.root.geometry("1280x800")
        self.root.minsize(1100, 700)

        # 配置根窗口的网格权重
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 设置样式
        self.setup_styles()
        # 预热字体缓存，避免首次弹窗卡顿
        try:
            ui_font(12)
        except Exception:
            pass

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

        # macOS 上从 IDE 启动时窗口常被挡在后面，主动前置一次
        try:
            self.root.update_idletasks()
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception:
            pass

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
        # 配置强调按钮样式（macOS aqua 主题会忽略 ttk 前景色，弹窗请用 tk.Button）
        style.configure(
            'Accent.TButton',
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
        """整卡可点：递归绑定 Frame/图标/文字。仅绑定 Button-1，避免弹窗关闭后松开鼠标穿透触发。"""
        if command is None:
            return

        # 防抖：避免一次点击被父子控件重复触发
        state = {"last": 0.0}

        def _on_click(_event=None, cmd=command):
            # 有模态对话框时忽略主界面卡片点击
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
                messagebox.showerror("功能打开失败", str(e))
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

    def _run_modal(self, factory):
        """运行模态流程期间屏蔽主界面卡片点击，防止弹窗按钮点击穿透。"""
        self._modal_open = True
        try:
            return factory()
        finally:
            # 稍延迟解除，覆盖弹窗销毁后的同一次鼠标松开
            def _unlock():
                self._modal_open = False
            try:
                self.root.after(200, _unlock)
            except Exception:
                self._modal_open = False

    def _resolve_card_icon_path(self, name, preferred=None):
        """按功能名查找图标，统一 png/jpeg/jpg 与 icons/图标 目录。"""
        if not name:
            return None
        candidates = []
        if preferred:
            candidates.append(preferred)
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
        # 第1行：轨迹 / 池壁 / 日志解析 / 日志打包
        # 第2行：日志删除 / MCU工具 / 串口调试 / 手机型号转换
        # 第3行：预留… / 使用帮助（末格）
        function_cards = [
            {"name": "轨迹线绘制", "command": self.mcu_tools, "row": 0, "column": 0},
            {"name": "池壁轨迹线绘制", "command": self.pool_wall_trajectory, "row": 0, "column": 1},
            {"name": "日志解析", "command": self.unzip_and_parse_zip, "row": 0, "column": 2},
            {"name": "日志打包下载", "command": self.pack_log, "row": 0, "column": 3},
            {"name": "日志一键删除", "command": self.delete_log, "row": 1, "column": 0},
            {"name": "MCU工具", "command": self.open_mcu_tool, "row": 1, "column": 1},
            {"name": "串口调试", "command": self.serial_debug_tool, "row": 1, "column": 2},
            {"name": "手机型号转换", "command": self.open_phone_model_conversion, "row": 1, "column": 3},
            {"name": "", "command": None, "row": 2, "column": 0},
            {"name": "", "command": None, "row": 2, "column": 1},
            {"name": "", "command": None, "row": 2, "column": 2},
            {"name": "使用帮助", "command": self.show_help, "row": 2, "column": 3},
        ]
        card_bg = "#f5f5f7"
        card_fg = "#1d1d1f"
        empty_bg = "#fafafa"
        title_font = ui_font(12, "bold")
        icon_font = ui_font(34)
        icon_size = 72
        emoji_fallback = {
            "轨迹线绘制": "📊",
            "池壁轨迹线绘制": "🏊",
            "日志解析": "📄",
            "日志打包下载": "📦",
            "日志一键删除": "🗑",
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
                # 使用 tk.Frame/Label：macOS 上 ttk.Label 经常吞掉点击
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

                # 内容区铺满整卡；进度条叠在底部，不挤占居中布局
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
            else:
                percent = int((value / total) * 100)
                p['text'].config(text=f"进度：{percent}%")

    def close_card_progress(self, row, col):
        p = self.card_progress.get((row, col))
        if p:
            p['bar'].place_forget()
            p['text'].place_forget()

    def _make_card_command(self, cmd):
        return lambda e: cmd()

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
            os.path.join("mcu_tool", "20260804MCU工具.py"),
            os.path.join("MCU工具", "20260804MCU工具.py"),
            os.path.join("Beatbot-tools", "MCU工具", "20260804MCU工具.py"),
            os.path.join("..", "MCU工具", "20260804MCU工具.py"),
        ])
        if found:
            return found
        # 兼容旧 resource_path
        try:
            p = resource_path(os.path.join("MCU工具", "20260804MCU工具.py"))
            if os.path.isfile(p):
                return p
        except Exception:
            pass
        return os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "MCU工具", "20260804MCU工具.py"
        ))

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

    def _excel_tool_script_path(self):
        """定位 excel_tool.py（源码 / 打包 Resources 均可）。"""
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
        # 源码相对路径兜底
        return os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "excel转换工具", "excel_tool.py"
        ))

    def open_phone_model_conversion(self):
        """手机型号转换：内嵌打开 `excel转换工具/excel_tool.py` 的 GUI 子功能。"""

        def _run():
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
                # 确保同目录的 excel_映射 / excel_to_script_names 可被导入
                tool_dir = os.path.dirname(excel_tool_script)
                if tool_dir and tool_dir not in sys.path:
                    sys.path.insert(0, tool_dir)
                mod = _load_module_from_file("xm_excel_phone_model_tool", excel_tool_script)
                ExcelToolApp = getattr(mod, "ExcelToolApp", None)
            except Exception as e:
                messagebox.showerror("手机型号转换", f"加载失败：\n{e}")
                return

            if ExcelToolApp is None:
                messagebox.showerror("手机型号转换", "excel_tool.py 中未找到 ExcelToolApp 类")
                return

            top = tk.Toplevel(self.root)
            top.title("手机型号转换")
            try:
                top.transient(self.root)
                top.grab_set()
            except tk.TclError:
                pass

            ExcelToolApp(top)
            try:
                top.focus_force()
            except tk.TclError:
                pass

            self.root.wait_window(top)

        self._run_modal(_run)

    def mcu_tools(self):
        """轨迹线绘制：弹窗与选文件必须在主线程，避免控件逐条刷出/卡顿。"""
        def _run():
            info = show_info_dialog(parent=self.root)
            if not info:
                return
            video_path = filedialog.askopenfilename(
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
            if video_path:
                self.root.after(10, lambda: self.trajectory.process_video(video_path, info))
        self._run_modal(_run)

    def pool_wall_trajectory(self):
        """池壁轨迹线绘制功能"""
        def _run():
            info = show_info_dialog(parent=self.root)
            if not info:
                return
            video_path = filedialog.askopenfilename(
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
            if video_path:
                self.root.after(10, lambda: self.trajectory.process_pool_wall_video(video_path, info))
        self._run_modal(_run)

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
            threading.Thread(target=lambda: self.extract_zip_and_parse_with_progress(archive_path), daemon=True).start()

    def extract_zip_and_parse_with_progress(self, archive_path):
        import tarfile, zipfile, os
        extract_dir = os.path.splitext(os.path.splitext(archive_path)[0])[0] if archive_path.endswith('.tar.gz') else \
            os.path.splitext(archive_path)[0]
        print(f"[DEBUG] 解压目录: {extract_dir}")
        if archive_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        elif archive_path.endswith('.tar.gz') or archive_path.endswith('.tar'):
            with tarfile.open(archive_path, 'r:*') as tar_ref:
                tar_ref.extractall(extract_dir)
        else:
            self.root.after(0, lambda: messagebox.showerror("错误", "不支持的压缩包格式"))
            return
        # 收集所有bin文件
        bin_files = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower().endswith('.bin'):
                    bin_files.append((os.path.join(root, file), root, file))
        print(f"[DEBUG] 查找到bin文件: {bin_files}")
        total = len(bin_files)
        self.root.after(0, lambda: self.show_card_progress(0, 2, total))
        count = 0
        with ProcessPoolExecutor(max_workers=4) as executor:
            for idx, result in enumerate(executor.map(process_one_bin, bin_files), 1):
                count += result
                c = count
                self.root.after(0, self.update_card_progress, 0, 2, c, total, f"{c}/{total} bin文件解析中...")
        self.root.after(0, self.close_card_progress, 0, 2)
        self.root.after(0, lambda: messagebox.showinfo("完成", f"共解析了 {count} 个 bin 文件"))

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
        self.root.after(0, lambda: self.show_card_progress(0, 2, total))

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
                    self.root.after(0,
                                    lambda i=i: self.update_card_progress(0, 2, i, total, f"解析中... ({i}/{total})"))

            def show_msg():
                if self._has_shown_multi_folder_msg:
                    return
                self._has_shown_multi_folder_msg = True
                self.close_card_progress(0, 2)
                self.progress_label.config(
                    text=f"已将 {count} 个 bin 文件转为明文 log，其他文件已原样保留到各自 _log 文件夹"
                )
                self.is_parsing = False
                self._is_running_multi_folder = False
                print("[DEBUG] 多文件夹转换完成，弹窗提示")
                messagebox.showinfo("完成",
                                    f"已将 {count} 个 bin 文件转为明文 log，其他文件已原样保留到各自 _log 文件夹")

            self.root.after(0, show_msg)

        threading.Thread(target=run_and_update, daemon=True).start()

    def is_same_lan(self, ip):
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            return '.'.join(local_ip.split('.')[:3]) == '.'.join(ip.split('.')[:3])
        except:
            return False


    def pack_log(self):
        # 日志打包下载功能，弹窗选择/输入IP
        def _run():
            dlg = IPInputDialog(self.root, "日志打包下载")
            return dlg.ip_var
        ip = self._run_modal(_run)
        if ip is None:
            return  # 用户点击取消，直接返回不提示
        if not self.is_same_lan(ip):
            messagebox.showerror("网络错误", "目标设备不在同一局域网内，无法操作！")
            return

        def do_pack():
            import os
            try:
                self.root.after(0, lambda: self.show_card_progress(0, 3, 100, "正在连接设备..."))
                run_adb(["-s", f"{ip}:5555", "root"], timeout=30)
                self.root.after(0, lambda: self.update_card_progress(0, 3, 20, 100, "正在连接设备..."))
                proc = run_adb(["connect", f"{ip}:5555"], timeout=30)
                out_str = decode_proc_output(proc.stdout)
                if "connected to" not in out_str:
                    self.root.after(0, lambda: [self.close_card_progress(0, 3),
                                                messagebox.showerror("连接失败", f"ADB连接失败：{out_str}")])
                    return
                self.root.after(0, lambda: self.update_card_progress(0, 3, 40, 100, "正在获取设备信息..."))
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
                self.root.after(0, lambda: self.update_card_progress(0, 3, 50, 100, "正在打包日志..."))
                pack_shell = (
                    f"tar -czf {tar_name} "
                    "/data/clean_record /data/conf /data/DP_clean_record /data/log /data/transfer_data "
                    "/etc/os_version /mnt/private /tmp/log /tmp/XM_LOG"
                )
                run_adb(["-s", f"{ip}:5555", "shell", pack_shell], timeout=600)
                self.root.after(0, lambda: self.update_card_progress(0, 3, 70, 100, "正在下载日志包..."))
                dist_dir = str(app_data_dir())
                os.makedirs(dist_dir, exist_ok=True)
                local_path = os.path.join(dist_dir, os.path.basename(tar_name))
                run_adb(["-s", f"{ip}:5555", "pull", tar_name, local_path], timeout=600)
                self.root.after(0, lambda: [self.update_card_progress(0, 3, 100, 100, "日志打包并下载完成"),
                                            self.close_card_progress(0, 3),
                                            messagebox.showinfo("完成", f"日志已下载至: {local_path}")])
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: [self.close_card_progress(0, 3),
                                            messagebox.showerror("异常", f"日志打包流程异常：{err_msg}")])

        threading.Thread(target=do_pack, daemon=True).start()

    def delete_log(self):
        # 日志一键删除功能，弹窗选择/输入IP
        def _run():
            dlg = IPInputDialog(self.root, "日志一键删除")
            return dlg.ip_var
        ip = self._run_modal(_run)
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

    print("程序已启动")
    try:
        multiprocessing.freeze_support()  # 兼容 pyinstaller 多进程打包
        setup_tesseract_cmd()
        print("准备初始化 Tk 根窗口")
        root = create_tk_root()
        print("Tk 根窗口初始化完成")
        app = MainApplication(root)
        print("MainApplication初始化完成")
        root.mainloop()
    except Exception as e:
        print("程序启动异常：", e)
        traceback.print_exc()
        try:
            messagebox.showerror("启动失败", f"程序启动异常：\n{e}")
        except Exception:
            pass