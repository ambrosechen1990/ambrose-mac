# -*- coding: utf-8 -*-
"""
串口调试助手
依赖: pip install pyserial
"""

import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.scrolledtext as scrolledtext
from datetime import datetime

try:
    import serial
    from serial.tools import list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    list_ports = None
    SERIAL_AVAILABLE = False

# macOS 字体 / 端口适配（可选）
try:
    from pathlib import Path as _Path
    _compat = _Path(__file__).resolve().parents[1] / "主程序"
    if str(_compat) not in sys.path:
        sys.path.insert(0, str(_compat))
    from platform_compat import mono_font, prefer_mac_serial_ports, IS_MAC
except Exception:
    IS_MAC = sys.platform == "darwin"
    def mono_font(size=10, weight=None):
        fam = "Menlo" if IS_MAC else "Consolas"
        return (fam, size, weight) if weight else (fam, size)
    def prefer_mac_serial_ports(ports):
        return list(ports)


# 主程序嵌入时复用同一窗口，避免重复打开
_embedded_win = None
_embedded_app = None


class SerialToolApp:
    BAUD_RATES = [
        "1200", "2400", "4800", "9600", "14400", "19200",
        "38400", "57600", "115200", "128000", "256000", "460800", "921600",
    ]
    DATA_BITS = ["5", "6", "7", "8"]

    def __init__(self, root, embedded=False):
        if not SERIAL_AVAILABLE:
            raise ImportError("请先安装 pyserial: pip install pyserial")

        self.root = root
        self.embedded = embedded
        self.root.title("串口调试助手")
        self.root.geometry("900x620")
        self.root.minsize(720, 480)

        self.PARITY_MAP = {
            "None": serial.PARITY_NONE, "Odd": serial.PARITY_ODD,
            "Even": serial.PARITY_EVEN, "Mark": serial.PARITY_MARK,
            "Space": serial.PARITY_SPACE,
        }
        self.STOP_BITS_MAP = {
            "1": serial.STOPBITS_ONE,
            "1.5": serial.STOPBITS_ONE_POINT_FIVE,
            "2": serial.STOPBITS_TWO,
        }
        self.FLOW_MAP = {
            "None": (False, False),
            "RTS/CTS": (True, False),
            "XON/XOFF": (False, True),
        }

        self.ser = None
        self.reading = False
        self.read_thread = None
        self.rx_count = 0
        self.tx_count = 0
        self.auto_send_job = None

        self._build_ui()
        self._refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ──────────────────── UI ────────────────────
    def _build_ui(self):
        self._build_menu()

        main = ttk.Frame(self.root, padding=4)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main, width=200)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        left.pack_propagate(False)

        right = ttk.Frame(main)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_serial_settings(left)
        self._build_recv_settings(left)
        self._build_send_settings(left)
        self._build_display(right)
        self._build_input_bar(right)
        self._build_statusbar()

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_m)
        file_m.add_command(label="保存日志...", command=self._save_recv, accelerator="Cmd+S" if IS_MAC else "Ctrl+S")
        file_m.add_command(label="打印日志...", command=self._print_log)
        file_m.add_command(label="清空显示", command=self._clear_display)
        file_m.add_separator()
        file_m.add_command(label="退出", command=self._on_close)

        # 快捷键
        accel = "<Command-s>" if IS_MAC else "<Control-s>"
        self.root.bind(accel, lambda e: self._save_recv())
        self.root.bind(accel.replace("s", "S"), lambda e: self._save_recv())

        tool_m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="工具", menu=tool_m)
        tool_m.add_command(label="刷新串口列表", command=self._refresh_ports)

        help_m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_m)
        help_m.add_command(label="关于", command=lambda: messagebox.showinfo(
            "关于", "串口调试助手\n基于 Python + pyserial + tkinter"))

    def _labeled_combo(self, parent, label, values, default, width=12):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=6, anchor=tk.W).pack(side=tk.LEFT)
        var = tk.StringVar(value=default)
        cb = ttk.Combobox(row, textvariable=var, values=values, width=width, state="readonly")
        cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return var, cb

    def _build_serial_settings(self, parent):
        box = ttk.LabelFrame(parent, text="串口设置", padding=6)
        box.pack(fill=tk.X, pady=(0, 6))

        # 端口行与下方波特率等保持同一布局（不再在右侧塞一个小方块刷新按钮）
        self.port_var, self.port_cb = self._labeled_combo(box, "端口", [], "")
        self.port_cb.configure(state="readonly")

        self.baud_var, _ = self._labeled_combo(box, "波特率", self.BAUD_RATES, "115200")
        self.databits_var, _ = self._labeled_combo(box, "数据位", self.DATA_BITS, "8")
        self.parity_var, _ = self._labeled_combo(box, "校验位", list(self.PARITY_MAP.keys()), "None")
        self.stopbits_var, _ = self._labeled_combo(box, "停止位", list(self.STOP_BITS_MAP.keys()), "1")
        self.flow_var, _ = self._labeled_combo(box, "流控", list(self.FLOW_MAP.keys()), "None")

        ttk.Button(box, text="刷新端口列表", command=self._refresh_ports).pack(fill=tk.X, pady=(6, 0))

    def _build_recv_settings(self, parent):
        box = ttk.LabelFrame(parent, text="接收设置", padding=6)
        box.pack(fill=tk.X, pady=(0, 6))

        self.recv_fmt = tk.StringVar(value="ASCII")
        row = ttk.Frame(box)
        row.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(row, text="ASCII", variable=self.recv_fmt, value="ASCII").pack(side=tk.LEFT)
        ttk.Radiobutton(row, text="Hex", variable=self.recv_fmt, value="Hex").pack(side=tk.LEFT, padx=(8, 0))

        self.auto_wrap = tk.BooleanVar(value=True)
        self.show_send = tk.BooleanVar(value=False)
        self.show_time = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="自动换行", variable=self.auto_wrap).pack(anchor=tk.W)
        ttk.Checkbutton(box, text="显示发送", variable=self.show_send).pack(anchor=tk.W)
        ttk.Checkbutton(box, text="显示时间", variable=self.show_time).pack(anchor=tk.W)

    def _build_send_settings(self, parent):
        box = ttk.LabelFrame(parent, text="发送设置", padding=6)
        box.pack(fill=tk.X, pady=(0, 6))

        self.send_fmt = tk.StringVar(value="Hex")
        row = ttk.Frame(box)
        row.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(row, text="ASCII", variable=self.send_fmt, value="ASCII").pack(side=tk.LEFT)
        ttk.Radiobutton(row, text="Hex", variable=self.send_fmt, value="Hex").pack(side=tk.LEFT, padx=(8, 0))

        row2 = ttk.Frame(box)
        row2.pack(fill=tk.X, pady=2)
        self.auto_resend = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="自动重发", variable=self.auto_resend,
                        command=self._toggle_auto_send).pack(side=tk.LEFT)
        self.resend_interval = tk.StringVar(value="1000")
        ttk.Entry(row2, textvariable=self.resend_interval, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(row2, text="ms").pack(side=tk.LEFT)

        self.line_by_line = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, text="Line by Line", variable=self.line_by_line).pack(anchor=tk.W)

        # 日志操作：嵌入主程序时 macOS 菜单栏常不可见，按钮更直观
        log_box = ttk.LabelFrame(parent, text="日志操作", padding=6)
        log_box.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(log_box, text="保存日志", command=self._save_recv).pack(fill=tk.X, pady=2)
        ttk.Button(log_box, text="打印日志", command=self._print_log).pack(fill=tk.X, pady=2)
        ttk.Button(log_box, text="清空显示", command=self._clear_display).pack(fill=tk.X, pady=2)

    def _build_display(self, parent):
        self.display = scrolledtext.ScrolledText(
            parent, wrap=tk.WORD, font=mono_font(10),
            state=tk.DISABLED, bg="#ffffff", relief=tk.SOLID, borderwidth=1,
        )
        self.display.pack(fill=tk.BOTH, expand=True)
        self.display.tag_configure("rx", foreground="#000000")
        self.display.tag_configure("tx", foreground="#0066cc")
        self.display.tag_configure("time", foreground="#888888")
        self.display.tag_configure("info", foreground="#228B22")

    def _build_input_bar(self, parent):
        bar = ttk.Frame(parent, padding=(0, 6, 0, 0))
        bar.pack(fill=tk.X)

        self.send_entry = ttk.Entry(bar, font=mono_font(11))
        self.send_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=4)
        self.send_entry.bind("<Return>", lambda e: self._send_data())

        self.open_btn = ttk.Button(bar, text="打开", width=8, command=self._toggle_port)
        self.open_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.send_btn = ttk.Button(bar, text="发送", width=8, command=self._send_data)
        self.send_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.save_btn = ttk.Button(bar, text="保存日志", width=8, command=self._save_recv)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.print_btn = ttk.Button(bar, text="打印", width=6, command=self._print_log)
        self.print_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.clear_btn = ttk.Button(bar, text="清空", width=6, command=self._clear_display)
        self.clear_btn.pack(side=tk.LEFT)

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, relief=tk.SUNKEN)
        bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_port = tk.Label(bar, text="CLOSED", fg="red",
                                    font=mono_font(9), anchor=tk.W, padx=6)
        self.status_port.pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        self.status_rx = tk.Label(bar, text="Rx: 0 Bytes", font=mono_font(9), padx=6)
        self.status_rx.pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        self.status_tx = tk.Label(bar, text="Tx: 0 Bytes", font=mono_font(9), padx=6)
        self.status_tx.pack(side=tk.LEFT)

        self.status_info = tk.Label(bar, text="", font=mono_font(9), padx=6, anchor=tk.E)
        self.status_info.pack(side=tk.RIGHT)

    # ──────────────────── 串口操作 ────────────────────
    def _refresh_ports(self):
        ordered = prefer_mac_serial_ports(list_ports.comports())
        ports = [p.device for p in ordered]
        self.port_cb["values"] = ports
        if ports:
            if self.port_var.get() not in ports:
                self.port_var.set(ports[0])
        else:
            self.port_var.set("")
            tip = "未检测到串口（Mac 请查看 /dev/cu.*）" if IS_MAC else "未检测到串口"
            self.status_info.config(text=tip)

    def _toggle_port(self):
        if self.ser and self.ser.is_open:
            self._close_port()
        else:
            self._open_port()

    def _open_port(self):
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("提示", "请先选择串口")
            return
        try:
            rtscts, xonxoff = self.FLOW_MAP[self.flow_var.get()]
            self.ser = serial.Serial(
                port=port,
                baudrate=int(self.baud_var.get()),
                bytesize=int(self.databits_var.get()),
                parity=self.PARITY_MAP[self.parity_var.get()],
                stopbits=self.STOP_BITS_MAP[self.stopbits_var.get()],
                rtscts=rtscts,
                xonxoff=xonxoff,
                timeout=0.05,
            )
        except serial.SerialException as e:
            messagebox.showerror("打开失败", str(e))
            return

        self.rx_count = 0
        self.tx_count = 0
        self._update_counters()
        self.reading = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()

        self.open_btn.config(text="关闭")
        self.status_port.config(text=f"{port} OPEN", fg="green")
        self.status_info.config(text=f"{self.baud_var.get()} 8N1")
        self._set_settings_state("disabled")
        self._append_info(f"已打开 {port}")

        if self.auto_resend.get():
            self._schedule_auto_send()

    def _close_port(self):
        self.reading = False
        self._cancel_auto_send()
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            port_name = self.ser.port or ""
            self.ser = None
        else:
            port_name = ""

        self.open_btn.config(text="打开")
        self.status_port.config(text=f"{port_name} CLOSED" if port_name else "CLOSED", fg="red")
        self.status_info.config(text="")
        self._set_settings_state("readonly")
        self._append_info(f"已关闭 {port_name}".strip())

    def _set_settings_state(self, state: str):
        """打开串口时锁定参数，关闭后恢复。"""
        cb_state = "disabled" if state == "disabled" else "readonly"
        settings_frame = self.port_cb.master.master
        for row in settings_frame.winfo_children():
            for c in row.winfo_children():
                if isinstance(c, ttk.Combobox):
                    c.config(state=cb_state)

    def _read_loop(self):
        buf = bytearray()
        last_rx = time.time()
        while self.reading and self.ser and self.ser.is_open:
            try:
                waiting = self.ser.in_waiting
                if waiting:
                    data = self.ser.read(waiting)
                    buf.extend(data)
                    last_rx = time.time()
                    self.rx_count += len(data)
                    self.root.after(0, self._update_counters)
                # 短暂静默后刷新显示，避免半包拆太碎
                if buf and (time.time() - last_rx) > 0.03:
                    chunk = bytes(buf)
                    buf.clear()
                    self.root.after(0, self._show_rx, chunk)
                else:
                    time.sleep(0.01)
            except serial.SerialException:
                self.root.after(0, self._close_port)
                break
            except Exception:
                time.sleep(0.05)
        if buf:
            self.root.after(0, self._show_rx, bytes(buf))

    # ──────────────────── 发送 ────────────────────
    def _send_data(self, _event=None):
        if not self.ser or not self.ser.is_open:
            messagebox.showwarning("提示", "请先打开串口")
            return
        text = self.send_entry.get()
        if not text:
            return

        try:
            if self.send_fmt.get() == "Hex":
                payload = self._hex_to_bytes(text)
            else:
                if self.line_by_line.get() and not text.endswith("\n"):
                    text += "\n"
                payload = text.encode("utf-8", errors="replace")
        except ValueError as e:
            messagebox.showerror("发送失败", str(e))
            return

        try:
            self.ser.write(payload)
            self.tx_count += len(payload)
            self._update_counters()
            if self.show_send.get():
                self._show_tx(payload)
        except serial.SerialException as e:
            messagebox.showerror("发送失败", str(e))
            self._close_port()

    def _toggle_auto_send(self):
        if self.auto_resend.get():
            if self.ser and self.ser.is_open:
                self._schedule_auto_send()
        else:
            self._cancel_auto_send()

    def _schedule_auto_send(self):
        self._cancel_auto_send()
        try:
            interval = max(10, int(self.resend_interval.get()))
        except ValueError:
            interval = 1000

        def tick():
            if self.auto_resend.get() and self.ser and self.ser.is_open:
                self._send_data()
                self.auto_send_job = self.root.after(interval, tick)

        self.auto_send_job = self.root.after(interval, tick)

    def _cancel_auto_send(self):
        if self.auto_send_job is not None:
            self.root.after_cancel(self.auto_send_job)
            self.auto_send_job = None

    # ──────────────────── 显示 ────────────────────
    def _append_text(self, text: str, tag: str = "rx"):
        self.display.config(state=tk.NORMAL)
        if self.show_time.get() and tag in ("rx", "tx"):
            ts = datetime.now().strftime("[%H:%M:%S.%f")[:-3] + "] "
            self.display.insert(tk.END, ts, "time")
        self.display.insert(tk.END, text, tag)
        if self.auto_wrap.get() and not text.endswith("\n"):
            self.display.insert(tk.END, "\n")
        self.display.see(tk.END)
        self.display.config(state=tk.DISABLED)

    def _append_info(self, msg: str):
        self.display.config(state=tk.NORMAL)
        ts = datetime.now().strftime("[%H:%M:%S] ")
        self.display.insert(tk.END, ts, "time")
        self.display.insert(tk.END, f"*** {msg} ***\n", "info")
        self.display.see(tk.END)
        self.display.config(state=tk.DISABLED)

    def _format_bytes(self, data: bytes, fmt: str) -> str:
        if fmt == "Hex":
            return " ".join(f"{b:02X}" for b in data)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("gbk", errors="replace")

    def _show_rx(self, data: bytes):
        text = self._format_bytes(data, self.recv_fmt.get())
        self._append_text(text, "rx")

    def _show_tx(self, data: bytes):
        # 显示发送时用发送格式，便于对照
        text = self._format_bytes(data, self.send_fmt.get())
        self._append_text(f">> {text}", "tx")

    def _update_counters(self):
        self.status_rx.config(text=f"Rx: {self.rx_count} Bytes")
        self.status_tx.config(text=f"Tx: {self.tx_count} Bytes")

    def _clear_display(self):
        self.display.config(state=tk.NORMAL)
        self.display.delete("1.0", tk.END)
        self.display.config(state=tk.DISABLED)
        self.rx_count = 0
        self.tx_count = 0
        self._update_counters()

    def _get_display_text(self) -> str:
        return self.display.get("1.0", tk.END)

    def _default_log_dir(self) -> str:
        try:
            from platform_compat import app_data_dir
            return str(app_data_dir())
        except Exception:
            from pathlib import Path
            p = Path.home() / "Documents" / "BeatbotDist"
            p.mkdir(parents=True, exist_ok=True)
            return str(p)

    def _default_log_filename(self) -> str:
        port = (self.port_var.get() or "serial").replace("/", "_").replace("\\", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"串口日志_{port}_{ts}.txt"

    def _save_recv(self):
        """保存当前显示区全部内容到文本文件。"""
        content = self._get_display_text().rstrip()
        if not content:
            messagebox.showinfo("提示", "当前没有可保存的日志内容")
            return

        initial_dir = self._default_log_dir()
        path = filedialog.asksaveasfilename(
            title="保存串口日志",
            initialdir=initial_dir,
            initialfile=self._default_log_filename(),
            defaultextension=".txt",
            filetypes=[
                ("文本文件", "*.txt"),
                ("日志文件", "*.log"),
                ("全部文件", "*.*"),
            ],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
                if not content.endswith("\n"):
                    f.write("\n")
            self.status_info.config(text=f"已保存: {path}")
            self._append_info(f"日志已保存: {path}")
            messagebox.showinfo("保存成功", f"日志已保存至：\n{path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _print_log(self):
        """打印当前显示区日志：先落盘，再调用系统打印/预览。"""
        content = self._get_display_text().rstrip()
        if not content:
            messagebox.showinfo("提示", "当前没有可打印的日志内容")
            return

        import os
        import shutil
        import subprocess

        try:
            tmp_path = os.path.join(self._default_log_dir(), self._default_log_filename())
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                if not content.endswith("\n"):
                    f.write("\n")

            printed = False
            if IS_MAC:
                # 优先系统打印对话框；失败则打开预览，用户可 Cmd+P
                if shutil.which("lp"):
                    try:
                        subprocess.run(["lp", tmp_path], check=False, capture_output=True, timeout=10)
                        printed = True
                    except Exception:
                        printed = False
                subprocess.Popen(["open", "-a", "TextEdit", tmp_path])
                self.status_info.config(text="已准备打印预览")
                self._append_info(f"日志已准备打印，文件: {tmp_path}")
                if printed:
                    messagebox.showinfo(
                        "打印",
                        "已发送到系统打印队列，并打开 TextEdit 预览。\n"
                        f"也可在预览窗口按 ⌘P 重新打印。\n\n文件：\n{tmp_path}",
                    )
                else:
                    messagebox.showinfo(
                        "打印",
                        "已打开 TextEdit 预览，请按 ⌘P 打印。\n"
                        f"文件：\n{tmp_path}",
                    )
            else:
                if hasattr(os, "startfile"):
                    os.startfile(tmp_path)
                else:
                    subprocess.Popen(["xdg-open", tmp_path])
                messagebox.showinfo("打印", f"日志已保存，请在打开的文件中打印：\n{tmp_path}")
        except Exception as e:
            messagebox.showerror("打印失败", str(e))

    @staticmethod
    def _hex_to_bytes(text: str) -> bytes:
        cleaned = text.replace(" ", "").replace("\n", "").replace("\t", "").replace(",", "")
        if len(cleaned) % 2 != 0:
            raise ValueError("Hex 长度必须为偶数，例如: AA 55 01 02")
        try:
            return bytes.fromhex(cleaned)
        except ValueError:
            raise ValueError("无效的 Hex 字符串，仅允许 0-9 A-F")

    def _on_close(self):
        global _embedded_win, _embedded_app
        self._cancel_auto_send()
        self.reading = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        if self.embedded:
            _embedded_win = None
            _embedded_app = None
        self.root.destroy()


def open_serial_tool(parent=None):
    """供主程序嵌入调用：以子窗口打开串口调试助手（已打开则前置）。"""
    global _embedded_win, _embedded_app

    if not SERIAL_AVAILABLE:
        messagebox.showerror(
            "缺少依赖",
            "未安装 pyserial，请先执行：\npip install pyserial",
            parent=parent,
        )
        return None

    if _embedded_win is not None:
        try:
            if _embedded_win.winfo_exists():
                _embedded_win.lift()
                _embedded_win.focus_force()
                return _embedded_app
        except tk.TclError:
            _embedded_win = None
            _embedded_app = None

    win = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
    # 不用 transient，避免挡住主界面其它功能窗口
    app = SerialToolApp(win, embedded=True)
    _embedded_win = win
    _embedded_app = app
    return app


def main():
    if not SERIAL_AVAILABLE:
        print("请先安装 pyserial: pip install pyserial")
        sys.exit(1)
    root = tk.Tk()
    try:
        style = ttk.Style()
        if IS_MAC and "aqua" in style.theme_names():
            style.theme_use("aqua")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        elif "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    SerialToolApp(root, embedded=False)
    root.mainloop()


if __name__ == "__main__":
    main()
