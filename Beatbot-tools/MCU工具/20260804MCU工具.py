# -*- coding: utf-8 -*-
"""
XM InnovateTool (Python 版)
由 Qt/C++ InnovateToolSoftware 移植，功能对齐原版 V3.02。

依赖: pip install pyserial
运行: python 20260804MCU工具.py

功能开关说明：
- ENABLE_IP_FEATURE=False：暂时屏蔽 IP 录入/连接 UI 与入口（串口调试仍可用）
- 将 ENABLE_IP_FEATURE 改为 True 即可恢复 IP 相关显示与连接逻辑
"""

from __future__ import annotations

import os
import re
import sys
import time
import socket
import subprocess
import threading
from datetime import datetime
from typing import Callable, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.scrolledtext as scrolledtext

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("请先安装 pyserial: pip install pyserial")
    sys.exit(1)


# ──────────────────── 功能开关 ────────────────────
# [功能点] IP 调试总开关：False=屏蔽 IP UI/连接入口；True=恢复
# 串口路径不受影响。IP 实现代码保留，便于后续排查 ROS/ADB 桥通路。
ENABLE_IP_FEATURE = True


# ──────────────────── IP / ADB 常量（功能暂时屏蔽，代码保留） ────────────────────
# [功能点] ADB 默认端口（设备网络调试口，不是 Innovate ASCII 口）
DEFAULT_TCP_PORT = 5555
# [功能点] 设备端 Innovate IP 桥端口（由本工具经 ADB 拉起，与 PC 串口无关）
INNOVATE_IP_BRIDGE_PORT = 9998
# [功能点] 5555 为 ADB；其它为候选裸 TCP
CANDIDATE_TCP_PORTS = (8111, 6668, 9998, 8080, 8000, 1883)
ADB_PORTS = {5555}

BRIDGE_SCRIPT_NAME = "innovate_ip_bridge.py"
BRIDGE_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), BRIDGE_SCRIPT_NAME)
BRIDGE_REMOTE = f"/data/{BRIDGE_SCRIPT_NAME}"


def adb_cmd(args: List[str], timeout: float = 12.0) -> subprocess.CompletedProcess:
    # [功能点-IP] 调用本机 adb 命令（仅 ENABLE_IP_FEATURE=True 时由连接流程使用）
    return subprocess.run(
        ["adb", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def ensure_lf_file(path: str) -> str:
    """保证推到设备的脚本为 LF 换行，返回可用于 push 的本地路径。"""
    # [功能点-IP] 推送前统一 LF，避免设备端 python 因 CRLF 启动失败
    data = open(path, "rb").read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    tmp = os.path.join(os.path.dirname(path), "_push_" + os.path.basename(path))
    open(tmp, "wb").write(data)
    return tmp


def start_innovate_ip_bridge(adb_serial: str) -> int:
    """经 ADB 推送并启动设备端 Innovate TCP 桥（纯网络路径，不使用本机 COM）。

    [功能点-IP] 设备桥只监听 127.0.0.1:9998，再通过 adb forward 转到本机回环口。
    返回本机 forward 端口，供 TCP 连接。当前 ENABLE_IP_FEATURE=False，入口已屏蔽。
    """
    if not os.path.isfile(BRIDGE_LOCAL):
        raise OSError(f"缺少桥接脚本: {BRIDGE_LOCAL}")
    push_path = ensure_lf_file(BRIDGE_LOCAL)
    try:
        r = adb_cmd(["-s", adb_serial, "push", push_path, BRIDGE_REMOTE], timeout=20)
        if r.returncode != 0:
            raise OSError((r.stderr or r.stdout or "push 失败").strip())
    finally:
        try:
            os.remove(push_path)
        except Exception:
            pass
    # 停旧桥接进程（在 PC 侧解析 pid，避免 adb shell 转义问题）
    for _ in range(3):
        ps = adb_cmd(["-s", adb_serial, "shell", "ps"], timeout=8)
        pids = []
        for line in (ps.stdout or "").splitlines():
            if "innovate_ip_bridge" in line and "grep" not in line:
                pid = line.strip().split()[0]
                if pid.isdigit():
                    pids.append(pid)
        if not pids:
            break
        for pid in pids:
            adb_cmd(["-s", adb_serial, "shell", f"kill -9 {pid}"], timeout=5)
        time.sleep(0.5)
    time.sleep(0.5)
    # 清空旧日志，便于确认新进程
    adb_cmd(
        ["-s", adb_serial, "shell", "rm -f /data/innovate_ip_bridge.log /data/innovate_ip_bridge.stdout"],
        timeout=5,
    )
    # 后台启动：单条 adb shell，末尾 &；同会话稍等再脱离
    env_prefix = (
        "HOME=/ ROS_LOG_DIR=/data/log ROS_LOCALHOST_ONLY=1 "
        "LD_LIBRARY_PATH=/obd/lib:/obd/network:/obd/xingmai_robot_interfaces/lib:/usr/lib:/opt/ros/humble/lib "
        "AMENT_PREFIX_PATH=/obd/ros_component:/opt/ros/humble:/obd/xingmai_robot_interfaces "
        "PYTHONPATH=/opt/ros/humble/lib/python3.10/site-packages:"
        "/opt/ros/humble/lib/python3.10/dist-packages:"
        "/obd/xingmai_robot_interfaces/lib/python3.10/site-packages "
    )
    start_cmd = (
        env_prefix
        + f"setsid python3 {BRIDGE_REMOTE} "
        + "</dev/null >/data/innovate_ip_bridge.stdout 2>&1 & "
        + "sleep 1; echo BRIDGE_SPAWNED"
    )
    r = adb_cmd(["-s", adb_serial, "shell", start_cmd], timeout=20)
    if "BRIDGE_SPAWNED" not in ((r.stdout or "") + (r.stderr or "")):
        pass
    time.sleep(1.2)
    # 本机端口转发：PC 连 127.0.0.1:local -> 设备 127.0.0.1:9998
    local_port = INNOVATE_IP_BRIDGE_PORT
    adb_cmd(
        ["-s", adb_serial, "forward", "--remove", f"tcp:{local_port}"],
        timeout=5,
    )
    adb_cmd(
        ["-s", adb_serial, "forward", f"tcp:{local_port}", f"tcp:{INNOVATE_IP_BRIDGE_PORT}"],
        timeout=8,
    )
    deadline = time.time() + 30
    last_err = "端口未就绪"
    while time.time() < deadline:
        # 确认进程在
        ps = adb_cmd(["-s", adb_serial, "shell", "ps"], timeout=5)
        alive = "innovate_ip_bridge" in (ps.stdout or "")
        sock = try_tcp_connect("127.0.0.1", local_port, timeout=0.8)
        lg = adb_cmd(
            ["-s", adb_serial, "shell",
             "cat /data/innovate_ip_bridge.log 2>/dev/null; echo ====; "
             "cat /data/innovate_ip_bridge.stdout 2>/dev/null"],
            timeout=5,
        )
        text = lg.stdout or ""
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
            if alive and ("listening" in text or "ROS ready" in text or "boot argv" in text):
                return local_port
            last_err = (text.strip() or "TCP 通但桥未就绪") + ("" if alive else "；进程不存在")
        else:
            last_err = text.strip() or ("进程在、端口未开" if alive else "进程未起来")
        time.sleep(0.5)
    # 附带日志便于排查
    lg = adb_cmd(
        ["-s", adb_serial, "shell", "cat /data/innovate_ip_bridge.log 2>/dev/null | tail -20"],
        timeout=5,
    )
    detail = (lg.stdout or "").strip() or last_err
    raise OSError(
        f"设备端 Innovate 桥未就绪（adb forward :{local_port}）。\n{detail}"
    )


def adb_connect_device(host: str, port: int = 5555) -> str:
    """[功能点-IP] adb connect，返回 serial 字符串 host:port。"""
    serial = f"{host}:{port}"
    r = adb_cmd(["connect", serial], timeout=15)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    ok = False
    for _ in range(12):
        st = adb_cmd(["-s", serial, "get-state"], timeout=5)
        if (st.stdout or "").strip() == "device":
            ok = True
            break
        time.sleep(0.4)
    if not ok:
        raise OSError(out or f"ADB 无法连接 {serial}")
    # 提权（与 SoftTest 一致，失败可忽略）
    try:
        adb_cmd(["-s", serial, "root"], timeout=10)
        time.sleep(0.6)
        adb_cmd(["connect", serial], timeout=10)
    except Exception:
        pass
    st = adb_cmd(["-s", serial, "get-state"], timeout=5)
    if (st.stdout or "").strip() != "device":
        raise OSError(f"ADB 连接后设备状态异常: {(st.stdout or st.stderr or '').strip()}")
    return serial


def parse_ip_port(text: str) -> Tuple[str, Optional[int]]:
    """[功能点-IP] 解析 '192.168.1.100' 或 '192.168.1.100:5555'。未写端口时返回 port=None。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("请输入设备IP")
    port: Optional[int] = None
    if ":" in text:
        host, _, port_s = text.rpartition(":")
        host = host.strip()
        try:
            port = int(port_s.strip())
        except ValueError:
            raise ValueError("端口必须是数字")
        if not (1 <= port <= 65535):
            raise ValueError("端口范围 1~65535")
    else:
        host = text
    parts = host.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        raise ValueError("IP 格式不正确，例如 192.168.1.100")
    return host, port


def ping_host(host: str, timeout_ms: int = 1000) -> bool:
    """ICMP 可达性检测（Windows ping）。"""
    try:
        # -n 1 发1包；-w 超时毫秒
        r = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), host],
            capture_output=True, text=True, encoding="gbk", errors="ignore",
            timeout=max(3, timeout_ms // 500 + 2),
        )
        out = (r.stdout or "") + (r.stderr or "")
        return ("TTL=" in out) or ("ttl=" in out)
    except Exception:
        return False


def try_tcp_connect(host: str, port: int, timeout: float = 1.5) -> Optional[socket.socket]:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(0.05)
        return sock
    except OSError:
        return None


def get_local_ipv4_list() -> List[str]:
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip not in ips and not ip.startswith("127."):
            ips.append(ip)
    except Exception:
        pass
    return ips


def same_lan(target_ip: str) -> bool:
    """判断目标 IP 是否与本机处于同一 /24 网段。"""
    locals_ = get_local_ipv4_list()
    if not locals_:
        return False
    t = target_ip.split(".")
    for lip in locals_:
        l = lip.split(".")
        if l[:3] == t[:3]:
            return True
    return False


# ──────────────────── 通信总线（串口 / TCP） ────────────────────
class SerialHub:
    """统一收发：串口或 TCP，对上层命令协议一致（文本 + \\r\\n）。

    [功能点] 当前工具默认只用串口路径（ENABLE_IP_FEATURE=False）。
    IP/TCP 方法仍保留，恢复开关后可继续用。
    """

    def __init__(self, ui_root=None):
        self.ui_root = ui_root
        self.ser: Optional[serial.Serial] = None
        self.sock: Optional[socket.socket] = None
        self.adb_serial: Optional[str] = None
        self.ip_forward_port: Optional[int] = None  # adb forward 本机端口（IP 路径）
        self.mode: Optional[str] = None  # 'serial' | 'tcp'
        self._readers: List[Callable[[str], None]] = []
        self._reading = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.on_raw: Optional[Callable[[str], None]] = None
        self.on_lost: Optional[Callable[[str], None]] = None
        self._user_closing = False

    def add_reader(self, cb: Callable[[str], None]):
        if cb not in self._readers:
            self._readers.append(cb)

    def remove_reader(self, cb: Callable[[str], None]):
        if cb in self._readers:
            self._readers.remove(cb)

    def is_open(self) -> bool:
        if self.mode == "serial":
            return bool(self.ser and self.ser.is_open)
        if self.mode == "tcp":
            return self.sock is not None
        return False

    def transport(self) -> str:
        return self.mode or ""

    def open_serial(self, port: str, baud: int = 115200) -> None:
        """[功能点-串口] 本机 USB 串口（CH340 等 @115200）下发 Innovate ASCII，与 IP 完全独立。"""
        self.close()
        self.ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
        )
        self.mode = "serial"
        self._start_reader()

    def open_tcp(self, host: str, port: int = DEFAULT_TCP_PORT, timeout: float = 3.0) -> None:
        # [功能点-IP] 直连裸 TCP（当前入口已屏蔽）
        self.close()
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(0.05)
        self.sock = sock
        self.mode = "tcp"
        self._start_reader()

    def open_tcp_sock(self, sock: socket.socket) -> None:
        # [功能点-IP] 接管已建立的 TCP socket
        self.close()
        sock.settimeout(0.05)
        self.sock = sock
        self.mode = "tcp"
        self._start_reader()

    def open_ip_bridge(self, host: str, adb_port: int = 5555) -> None:
        """[功能点-IP] 纯 IP：ADB 拉起设备端桥 + forward，不打开本机 COM（入口已屏蔽）。"""
        self.close()
        adb_id = adb_connect_device(host, adb_port)
        self.adb_serial = adb_id
        local_port = start_innovate_ip_bridge(adb_id)
        self.ip_forward_port = local_port
        # 经 adb forward 连本机回环，不直连设备 WiFi 端口、不使用 COM
        sock = socket.create_connection(("127.0.0.1", local_port), timeout=5.0)
        sock.settimeout(0.05)
        self.sock = sock
        self.mode = "tcp"
        self._start_reader()

    def open(self, port: str, baud: int = 115200) -> None:
        # [功能点-串口] 兼容旧接口，等同 open_serial
        self.open_serial(port, baud)

    def close(self):
        # [功能点] 关闭当前通路；若曾走 IP，顺带清理设备端桥与 adb forward
        self._user_closing = True
        self._reading = False
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        # [功能点-IP] 清理 IP 路径：结束设备端桥、撤销 forward（不碰本机串口）
            if self.adb_serial:
                try:
                    ps = adb_cmd(["-s", self.adb_serial, "shell", "ps"], timeout=5)
                    for line in (ps.stdout or "").splitlines():
                        if "innovate_ip_bridge" in line and "grep" not in line:
                            pid = line.strip().split()[0]
                            if pid.isdigit():
                                adb_cmd(
                                    ["-s", self.adb_serial, "shell", f"kill -9 {pid}"],
                                    timeout=5,
                                )
                except Exception:
                    pass
            if self.ip_forward_port:
                try:
                    adb_cmd(
                        ["-s", self.adb_serial, "forward",
                         "--remove", f"tcp:{self.ip_forward_port}"],
                        timeout=5,
                    )
                except Exception:
                    pass
        self.adb_serial = None
        self.ip_forward_port = None
        self.mode = None
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=0.5)
        self._thread = None
        self._user_closing = False

    def can_send_innovate(self) -> bool:
        """[功能点] 当前通路是否可下发 Innovate ASCII（串口打开即可；IP 恢复后亦支持）。"""
        if self.mode == "serial":
            return bool(self.ser and self.ser.is_open)
        if self.mode == "tcp":
            return self.sock is not None
        return False

    def send(self, text: str):
        # [功能点] 统一下发：命令文本 + \\r\\n
        if not self.is_open():
            return
        payload = f"{text}\r\n".encode("utf-8", errors="replace")
        with self._lock:
            try:
                if self.mode == "serial" and self.ser:
                    self.ser.write(payload)
                elif self.mode == "tcp" and self.sock:
                    self.sock.sendall(payload)
            except (serial.SerialException, OSError, socket.error) as e:
                if not self._user_closing:
                    self._notify_lost(f"发送失败，连接已断开 ({e})")

    def _start_reader(self):
        self._reading = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _notify_lost(self, reason: str):
        if self._user_closing or self.mode is None:
            return

        def run():
            if self._user_closing:
                return
            self.close()
            if self.on_lost:
                try:
                    self.on_lost(reason)
                except Exception:
                    pass

        root = self.ui_root
        if root is not None:
            try:
                root.after(0, run)
                return
            except Exception:
                pass
        run()

    def _read_loop(self):
        buf = bytearray()
        last = time.time()
        last_adb_check = 0.0
        while self._reading:
            try:
                chunk = b""
                if self.mode == "serial" and self.ser and self.ser.is_open:
                    n = self.ser.in_waiting
                    if n:
                        chunk = self.ser.read(n)
                elif self.mode == "tcp" and self.sock:
                    try:
                        chunk = self.sock.recv(4096)
                        if chunk == b"":
                            self._notify_lost("设备已断开连接")
                            break
                    except socket.timeout:
                        chunk = b""
                else:
                    break

                if chunk:
                    buf.extend(chunk)
                    last = time.time()
                if buf and (time.time() - last) > 0.03:
                    text = bytes(buf).decode("utf-8", errors="replace")
                    buf.clear()
                    self._dispatch(text)
                else:
                    time.sleep(0.01)
            except (serial.SerialException, OSError, socket.error):
                if not self._user_closing:
                    self._notify_lost("连接异常断开")
                break
            except Exception:
                time.sleep(0.05)
        if buf:
            text = bytes(buf).decode("utf-8", errors="replace")
            self._dispatch(text)

    def _safe_call(self, fn, text: str):
        try:
            fn(text)
        except Exception:
            pass

    def _dispatch(self, text: str):
        def run():
            if self.on_raw:
                self._safe_call(self.on_raw, text)
            for cb in list(self._readers):
                self._safe_call(cb, text)

        root = self.ui_root
        if root is not None:
            try:
                root.after(0, run)
                return
            except Exception:
                pass
        run()



# macOS 字体 / 端口适配
try:
    import sys as _sys
    from pathlib import Path as _Path
    _compat_dir = _Path(__file__).resolve().parents[1] / "主程序"
    if str(_compat_dir) not in _sys.path:
        _sys.path.insert(0, str(_compat_dir))
    from platform_compat import ui_font_family, mono_font_family, prefer_mac_serial_ports, IS_MAC
except Exception:
    IS_MAC = __import__("sys").platform == "darwin"
    def ui_font_family():
        return "PingFang SC" if IS_MAC else "微软雅黑"
    def mono_font_family():
        return "Menlo" if IS_MAC else "Consolas"
    def prefer_mac_serial_ports(ports):
        return list(ports)

def list_serial_ports():
    """[功能点-串口] 列出本机串口；优先 CH340/WCH/USB-Serial，Mac 优先 /dev/cu.*。"""
    ports = prefer_mac_serial_ports(list(list_ports.comports()))
    return [(p.device, p.description or "") for p in ports]


# 统一字体（Mac 优先 PingFang SC / Menlo）——须在窗口类之前定义
UI_FONT = ui_font_family()
FONT_LABEL = (UI_FONT, 10)
FONT_TITLE = (UI_FONT, 10, "bold")
FONT_HINT = (UI_FONT, 9)
FONT_BTN = (UI_FONT, 10)
FONT_BTN_LG = (UI_FONT, 11)
FONT_INPUT = (UI_FONT, 10)
FONT_MONO = (mono_font_family(), 10)
FONT_KEYS = (UI_FONT, 11)

BG = "#f5f5f5"
BG_PANEL = "#eeeeee"


# ──────────────────── 数据显示窗口（图2布局） ────────────────────
class DataShowWindow(tk.Toplevel):
    # 右栏两列，顺序对齐原版截图
    READ_CMDS = [
        ("state", "READ state."),
        ("ver", "READ ver."),
        ("imu", "READ imu."),
        ("UAC", "READ watermsg ver."),
        ("ultra", "READ ultra."),
        ("tof", "READ tof."),
        ("battery", "READ battery."),
        ("sensor", "READ water sensor."),
        ("box", "READ box."),
        ("adc", "READ adc."),
        ("motor error", "READ motor error."),
        ("other error", "READ other error."),
        ("wheel", "READ motor wheel."),
        ("water pump", "READ water pump."),
        ("prop", "READ motor prop."),
        ("air pump", "READ air pump."),
        ("side brush", "READ side brush."),
        ("speed", "READ motor speed."),
        ("motor I", "READ motor current."),
        ("depth", "READ water depth."),
        ("SN", "READ sn."),
        ("SOC", "READ soc."),
        ("wifi", "READ wifi."),
        ("sound", "SET audio 1."),
    ]

    def __init__(self, master, hub: SerialHub):
        super().__init__(master)
        self.hub = hub
        self.title("data show")
        self.geometry("800x500")
        self.resizable(False, False)
        self.configure(bg="#f0f0f0")
        self._last_ms = 0
        self._lines: List[str] = ["NULL"] * 5

        # 左侧日志区
        left = tk.Frame(self, bg="white", highlightthickness=1, highlightbackground="#c0c0c0")
        left.place(x=10, y=10, width=580, height=480)
        self.log_labels = []
        for i in range(5):
            lb = tk.Label(
                left, text="NULL", anchor="nw", justify="left",
                font=FONT_MONO, bg="white", fg="#222",
                wraplength=560,
            )
            lb.place(x=4, y=4 + i * 94, width=570, height=90)
            self.log_labels.append(lb)

        # 右侧按钮 12行 x 2列
        for i, (name, cmd) in enumerate(self.READ_CMDS):
            col = i % 2
            row = i // 2
            x = 610 + col * 90
            y = 10 + row * 40
            btn = tk.Button(
                self, text=name, font=FONT_LABEL,
                command=lambda c=cmd: self._send(c),
            )
            btn.place(x=x, y=y, width=80, height=32)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.hub.add_reader(self.on_recv)
        self.withdraw()

    def _send(self, cmd: str):
        self.hub.send(cmd)

    def on_recv(self, data: str):
        now = int(time.time() * 1000)
        if now - self._last_ms >= 200:
            self._last_ms = now
            for i in range(4, 0, -1):
                self._lines[i] = self._lines[i - 1]
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._lines[0] = f"{ts} {data}"
        else:
            self._lines[0] = self._lines[0] + data
        for i, lb in enumerate(self.log_labels):
            lb.config(text=self._lines[i])

    def _on_close(self):
        self.withdraw()

    def show(self):
        self.deiconify()
        self.lift()
        self.focus_force()


# ──────────────────── 开发调试窗口 ────────────────────
class DevelopWindow(tk.Toplevel):
    def __init__(self, master, hub: SerialHub):
        super().__init__(master)
        self.hub = hub
        self.title("develop")
        self.geometry("780x560")
        self.minsize(700, 480)
        self._log = ""
        self._log_temp = ""
        self._last_ms = 0
        self._cycle_ms = 1000
        self._cycle_on = False
        self._cycle_acc = 0

        btns = ttk.Frame(self, padding=6)
        btns.pack(fill=tk.X)

        rows = [
            [
                ("clear navi", lambda: self.hub.send("SET clear navi.")),
                ("frm pair", lambda: self.hub.send("SET rfm pair.")),
                ("rtc write", self._rtc_write),
                ("rtc read", lambda: self.hub.send("READ rtc.")),
                ("start info", lambda: self.hub.send("READ start.")),
                ("navi", lambda: self.hub.send("READ navi.")),
                ("MCU", lambda: self.hub.send("READ mcu.")),
            ],
            [
                ("IMU sensor", lambda: self.hub.send("IMU sensor.")),
                ("IMU filter", lambda: self.hub.send("IMU gyro filter.")),
                ("IMU flag", lambda: self.hub.send("IMU flag.")),
                ("IMU cali", lambda: self.hub.send("IMU set calibrate.")),
                ("IMU scale", lambda: self.hub.send("IMU scale.")),
                ("imu data", lambda: self.hub.send("IMU data.")),
                ("imu wall", lambda: self.hub.send("IMU wall data.")),
            ],
            [
                ("IMU base", self._imu_base),
                ("set scale", self._imu_set_scale),
                ("LOG", lambda: self.hub.send("READ log all.")),
                ("clear log", self._clear_log),
                ("save log", self._save_log),
            ],
        ]
        for r, row in enumerate(rows):
            for c, (name, cmd) in enumerate(row):
                ttk.Button(btns, text=name, width=12, command=cmd).grid(
                    row=r, column=c, padx=2, pady=2
                )

        send_bar = ttk.Frame(self, padding=(6, 0, 6, 6))
        send_bar.pack(fill=tk.X)
        self.send_var = tk.StringVar()
        ent = ttk.Entry(send_bar, textvariable=self.send_var, font=(mono_font_family(), 11))
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ent.bind("<Return>", lambda e: self._send_custom())
        ttk.Button(send_bar, text="发送", width=8, command=self._send_custom).pack(side=tk.LEFT)
        self.cycle_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            send_bar, text="重复发送", variable=self.cycle_var,
            command=self._toggle_cycle,
        ).pack(side=tk.LEFT, padx=8)

        self.txt = scrolledtext.ScrolledText(
            self, font=FONT_MONO, state=tk.NORMAL, wrap=tk.WORD
        )
        self.txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.hub.add_reader(self.on_recv)
        self.after(10, self._cycle_tick)
        self.withdraw()

    def _rtc_write(self):
        now = datetime.now()
        cmd = (
            f"SET rtc {now.year} {now.month} {now.day} "
            f"{now.hour} {now.minute} {now.second}."
        )
        self.hub.send(cmd)

    def _imu_base(self):
        try:
            num = float(self.send_var.get().strip() or "0")
        except ValueError:
            num = 0.0
        if -180.0 < num < 180.0:
            self.hub.send(f"IMU base {num}.")
        else:
            self.hub.send("IMU base 0.")

    def _imu_set_scale(self):
        try:
            num = float(self.send_var.get().strip() or "0")
        except ValueError:
            return
        if 0.95 < num < 1.05:
            self.hub.send(f"IMU set scale {num}.")

    def _clear_log(self):
        self._log = ""
        self._log_temp = ""
        self.txt.delete("1.0", tk.END)

    def _save_log(self):
        content = self._log + self._log_temp
        name = f"./Log{datetime.now().strftime('%y%m%d-%H%M')}.txt"
        try:
            with open(name, "w", encoding="utf-8") as f:
                f.write(datetime.now().strftime("%H:%M:%S "))
                f.write(content)
            messagebox.showinfo("保存日志", f"已保存: {os.path.abspath(name)}", parent=self)
        except Exception as e:
            messagebox.showerror("保存失败", str(e), parent=self)

    def _send_custom(self):
        s = self.send_var.get()
        if s.startswith("APP "):
            if s.startswith("APP cycle"):
                m = re.search(r"\d+", s)
                if m:
                    num = int(m.group())
                    if 40 <= num <= 100000:
                        self._cycle_ms = num
                        self.on_recv("OK" + s)
                    else:
                        self.on_recv("error" + s)
                else:
                    self.on_recv("APP error")
            else:
                self.on_recv("APP error")
            return
        self.hub.send(s)

    def _toggle_cycle(self):
        self._cycle_on = self.cycle_var.get()
        self._cycle_acc = 0

    def _cycle_tick(self):
        if self._cycle_on:
            if self._cycle_acc == 0:
                self._send_custom()
            self._cycle_acc += 10
            if self._cycle_acc >= self._cycle_ms:
                self._cycle_acc = 0
        else:
            self._cycle_acc = 0
        try:
            self.after(10, self._cycle_tick)
        except tk.TclError:
            pass

    def on_recv(self, data: str):
        now = int(time.time() * 1000)
        at_bottom = True
        try:
            self.txt.update_idletasks()
            yview = self.txt.yview()
            at_bottom = yview[1] >= 0.98
        except Exception:
            pass

        if now - self._last_ms >= 200:
            self._log += self._log_temp
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._log_temp = f"{ts} {data}"
        else:
            self._log_temp += data
        self._last_ms = now

        self.txt.delete("1.0", tk.END)
        self.txt.insert(tk.END, self._log + self._log_temp)
        if at_bottom:
            self.txt.see(tk.END)

    def _on_close(self):
        self.withdraw()

    def show(self):
        self.deiconify()
        self.lift()
        self.focus_force()


# ──────────────────── 软测模式窗口（图3布局） ────────────────────
class SoftTestWindow(tk.Toplevel):
    """7 组预设：大轮 / 主水泵 / 推进器，点击确定依次下发。"""

    def __init__(self, master, hub: SerialHub):
        super().__init__(master)
        self.hub = hub
        self.title("soft test")
        self.geometry("700x420")
        self.resizable(False, False)
        self.configure(bg="#f0f0f0")
        self._motor_send = 0
        self._last_ms = 0
        self.edits = {}

        # 表头
        tk.Label(self, text="大轮  mm/s", bg="#f0f0f0", font=FONT_BTN_LG).place(x=40, y=8)
        tk.Label(self, text="主水泵 rpm", bg="#f0f0f0", font=FONT_BTN_LG).place(x=220, y=8)
        tk.Label(self, text="推进器 rpm", bg="#f0f0f0", font=FONT_BTN_LG).place(x=400, y=8)

        for g in range(1, 8):
            y = 36 + (g - 1) * 42
            xs = [20, 90, 200, 270, 380, 450]  # wl wr pl pr ol or
            kinds = ("wl", "wr", "pl", "pr", "ol", "or")
            for x, kind in zip(xs, kinds):
                var = tk.StringVar()
                ent = tk.Entry(self, textvariable=var, font=(mono_font_family(), 11), justify="center")
                ent.place(x=x, y=y, width=60, height=28)
                self.edits[(g, kind)] = var
            tk.Button(
                self, text=f"确定 {g}", font=FONT_BTN_LG,
                command=lambda n=g: self._start_group(n),
            ).place(x=550, y=y - 2, width=90, height=32)

        self.ack = tk.Label(
            self, text="NULL", anchor="nw", justify="left",
            font=FONT_MONO, bg="#f0f0f0",
        )
        self.ack.place(x=20, y=340, width=660, height=60)

        self.bind("<Key>", self._on_key)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.hub.add_reader(self.on_recv)
        self.after(100, self._tick)
        self.withdraw()

    def _ival(self, g: int, kind: str) -> Optional[int]:
        s = self.edits[(g, kind)].get().strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def _start_group(self, g: int):
        self._motor_send = g * 10

    def _tick(self):
        s = self._motor_send
        if s in (10, 20, 30, 40, 50, 60, 70):
            g = s // 10
            self._motor_send = s + 1
            wl, wr = self._ival(g, "wl"), self._ival(g, "wr")
            if wl is not None or wr is not None:
                self.hub.send(f"MV wheel motor {wl or 0} {wr or 0}.")
        elif s in (11, 21, 31, 41, 51, 61, 71):
            g = s // 10
            self._motor_send = s + 1
            pl, pr = self._ival(g, "pl"), self._ival(g, "pr")
            if pl is not None or pr is not None:
                self.hub.send(f"MV water pump {pl or 0} {pr or 0}.")
        elif s in (12, 22, 32, 42, 52, 62, 72):
            g = s // 10
            self._motor_send = 0
            ol, or_ = self._ival(g, "ol"), self._ival(g, "or")
            if ol is not None or or_ is not None:
                self.hub.send(f"MV prop motor {ol or 0} {or_ or 0}.")
        elif s != 0:
            self._motor_send = 0
        try:
            self.after(100, self._tick)
        except tk.TclError:
            pass

    def _on_key(self, event):
        if event.char in "1234567":
            self._start_group(int(event.char))

    def on_recv(self, data: str):
        now = int(time.time() * 1000)
        if now - self._last_ms >= 400:
            self._last_ms = now
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.ack.config(text=f"{ts} {data}")
        else:
            self.ack.config(text=self.ack.cget("text") + data)

    def _on_close(self):
        self.withdraw()

    def show(self):
        self.deiconify()
        self.lift()
        self.focus_force()


# ──────────────────── 主窗口 ────────────────────
MODE_STATE = {
    0: 0,    # 自动
    1: 2,    # 手动
    2: 5,    # 急停
    3: 6,    # 清洁
    4: 100,  # 探索
    5: 101,  # 弓子
    6: 102,  # 随机
    7: 103,  # 沿边
}

PROP_NORM_SPEED = 2000
PROP_MIN_SPEED = 600
WHEEL_NORM_SPEED = 160
WHEEL_DIFF_SPEED = 40
WHEEL_MIN_SPEED = 40


class MainApp(tk.Toplevel):
    """InnovateTool 主窗。

    - 独立运行：MainApp() → 内部建隐藏 Tk 根窗口
    - 嵌入软测：MainApp(master=主窗口) → 作为子 Toplevel
    """

    def __init__(self, master=None):
        self._own_root = None
        if master is None:
            # [功能点] 独立启动时自建隐藏根窗口
            self._own_root = tk.Tk()
            self._own_root.withdraw()
            master = self._own_root
        super().__init__(master)
        self.title("XM InnovateTool V3.02")
        self.geometry("980x600")
        self.minsize(960, 580)
        self.resizable(False, False)
        self.configure(bg=BG)

        self.hub = SerialHub(ui_root=self)
        self.hub.on_raw = self._on_raw
        self.hub.on_lost = self._on_link_lost
        self._ack_last_ms = 0
        self._block_slider = False
        self._motor_sure = 0
        self._equal_count = 0
        self._active_scale = None
        self._scale_widgets = []

        self._build_ui()
        self._refresh_ports()
        self._create_children()
        self.after(10, self._motor_sure_tick)

        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.focus_set()
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _create_children(self):
        self.data_win = DataShowWindow(self, self.hub)
        self.test_win = SoftTestWindow(self, self.hub)
        self.dev_win = DevelopWindow(self, self.hub)

    # ---------- UI ----------
    def _place_scale(self, x, y, height, from_, to, value, command, width=28):
        """自绘竖滑条：无蓝色滑块，选中后变灰，无外框、无半灰半白。"""
        var = tk.IntVar(value=value)
        lo, hi = min(from_, to), max(from_, to)
        # from_ > to 时顶部为大值（与原 tk.Scale 一致）
        invert = from_ > to

        canvas = tk.Canvas(
            self, width=width, height=height + 10,
            bg=BG, highlightthickness=0, bd=0,
        )
        canvas.place(x=x, y=y)

        meta = {
            "var": var,
            "lo": lo,
            "hi": hi,
            "invert": invert,
            "cmd": command,
            "step": 1,
            "height": height,
            "width": width,
            "thumb_h": 12,
            "selected": False,
            "canvas": canvas,
        }

        def _ratio():
            span = hi - lo
            if span <= 0:
                return 0.0
            r = (var.get() - lo) / span
            return (1.0 - r) if invert else r

        def _draw():
            canvas.delete("all")
            w, h = width, height + 10
            track_x = w // 2
            pad = meta["thumb_h"] // 2 + 2
            # 整段轨道统一浅灰（避免一半白一半灰）
            canvas.create_line(
                track_x, pad, track_x, h - pad,
                fill="#bdbdbd", width=4, capstyle=tk.ROUND,
            )
            r = _ratio()
            ty = pad + r * (h - 2 * pad)
            tw, th = w - 6, meta["thumb_h"]
            color = "#757575" if meta["selected"] else "#42a5f5"  # 选中灰 / 默认蓝
            canvas.create_rectangle(
                3, ty - th / 2, 3 + tw, ty + th / 2,
                fill=color, outline="#616161" if meta["selected"] else "#1e88e5",
                width=1, tags=("thumb",),
            )

        def _set_from_y(ey):
            w, h = width, height + 10
            pad = meta["thumb_h"] // 2 + 2
            usable = h - 2 * pad
            r = (ey - pad) / usable
            r = max(0.0, min(1.0, r))
            if invert:
                r = 1.0 - r
            new_v = int(round(lo + r * (hi - lo)))
            new_v = max(lo, min(hi, new_v))
            if new_v != var.get():
                self._block(True)
                var.set(new_v)
                self._block(False)
                _draw()
                self._slider_cb(command)
            else:
                _draw()

        def _on_press(e):
            # 第一次点击仅选中，不改数值；已选中时再点击/拖动才调参
            already = meta["selected"]
            meta["_allow_drag"] = already
            self._activate_scale(meta)
            if already:
                _set_from_y(e.y)

        def _on_drag(e):
            if meta.get("_allow_drag"):
                _set_from_y(e.y)

        canvas.bind("<Button-1>", _on_press)
        canvas.bind("<B1-Motion>", _on_drag)
        canvas.bind("<Up>", lambda e: self._nudge_scale(meta, +1))
        canvas.bind("<Down>", lambda e: self._nudge_scale(meta, -1))

        meta["draw"] = _draw

        class _Proxy:
            pass

        proxy = _Proxy()
        proxy._mcu_var = var
        proxy._mcu_lo = lo
        proxy._mcu_hi = hi
        proxy._mcu_cmd = command
        proxy._mcu_step = 1
        proxy._meta = meta
        proxy.focus_set = lambda: canvas.focus_set()
        meta["proxy"] = proxy

        _draw()
        var.trace_add("write", lambda *_: _draw())
        self._scale_widgets.append(meta)
        return var

    def _activate_scale(self, sc, focus=True):
        # sc 可能是 meta dict 或带 _meta 的 proxy
        meta = sc if isinstance(sc, dict) else getattr(sc, "_meta", None)
        if meta is None:
            return
        self._active_scale = meta["proxy"]
        if focus:
            meta["canvas"].focus_set()
        for other in self._scale_widgets:
            other["selected"] = False
            other["draw"]()
        meta["selected"] = True
        meta["draw"]()

    def _nudge_scale(self, sc, direction: int):
        if sc is None:
            return "break"
        meta = sc if isinstance(sc, dict) else getattr(sc, "_meta", None)
        if meta is None and hasattr(sc, "_mcu_var"):
            # 兼容旧 Scale 对象
            var, lo, hi, step = sc._mcu_var, sc._mcu_lo, sc._mcu_hi, sc._mcu_step
            cmd = sc._mcu_cmd
            new_v = max(lo, min(hi, var.get() + direction * step))
            if new_v != var.get():
                self._block(True)
                var.set(new_v)
                self._block(False)
                self._slider_cb(cmd)
            return "break"
        var = meta["var"]
        lo, hi, step = meta["lo"], meta["hi"], meta["step"]
        new_v = max(lo, min(hi, var.get() + direction * step))
        if new_v == var.get():
            return "break"
        self._block(True)
        var.set(new_v)
        self._block(False)
        meta["draw"]()
        self._slider_cb(meta["cmd"])
        return "break"

    def _slider_cb(self, fn):
        if self._block_slider:
            return
        fn()

    def _lbl(self, text, x, y, w=80, h=24, font=None, anchor="center", fg="#333333"):
        lb = tk.Label(
            self, text=text, font=font or FONT_LABEL, bg=BG, fg=fg,
            justify="center", anchor=anchor,
        )
        lb.place(x=x, y=y, width=w, height=h)
        return lb

    def _btn(self, text, x, y, w, h, command, font=None):
        b = tk.Button(
            self, text=text, font=font or FONT_BTN, command=command,
            bg="#e8e8e8", activebackground="#d8d8d8", relief=tk.GROOVE,
            bd=1, cursor="hand2",
        )
        b.place(x=x, y=y, width=w, height=h)
        return b

    def _build_ui(self):
        # ========== 顶部连接栏 ==========
        # [功能点-串口] 端口选择 / 打开关闭 / 刷新
        top_bar = tk.Frame(self, bg=BG_PANEL, height=52)
        top_bar.place(x=0, y=0, width=980, height=52)

        tk.Label(top_bar, text="串口", font=FONT_LABEL, bg=BG_PANEL, fg="#333").place(x=14, y=12, width=36, height=28)
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(
            top_bar, textvariable=self.port_var, state="readonly", font=FONT_INPUT,
        )
        self.port_cb.place(x=52, y=12, width=120, height=28)
        self.open_btn = tk.Button(
            top_bar, text="打开串口", font=FONT_BTN, command=self._toggle_port,
            bg="#e8e8e8", relief=tk.GROOVE, bd=1, cursor="hand2",
        )
        self.open_btn.place(x=180, y=10, width=88, height=32)
        tk.Button(
            top_bar, text="↻", font=FONT_BTN, command=self._refresh_ports,
            bg="#e8e8e8", relief=tk.GROOVE, bd=1, cursor="hand2",
        ).place(x=274, y=10, width=32, height=32)

        # [功能点-IP] 设备 IP 录入 / 连接（暂时屏蔽显示；改 ENABLE_IP_FEATURE=True 恢复）
        self.ip_var = tk.StringVar()
        self.ip_entry = None
        self.ip_btn = None
        if ENABLE_IP_FEATURE:
            tk.Label(top_bar, text="设备IP", font=FONT_LABEL, bg=BG_PANEL, fg="#333").place(
                x=330, y=12, width=52, height=28
            )
            self.ip_entry = tk.Entry(
                top_bar, textvariable=self.ip_var, font=FONT_INPUT, relief=tk.SOLID, bd=1,
            )
            self.ip_entry.place(x=384, y=12, width=150, height=28)
            self.ip_btn = tk.Button(
                top_bar, text="连接", font=FONT_BTN, command=self._toggle_ip,
                bg="#e8e8e8", relief=tk.GROOVE, bd=1, cursor="hand2",
            )
            self.ip_btn.place(x=544, y=10, width=72, height=32)
            tk.Label(
                top_bar, text="可写IP或IP:端口", font=FONT_HINT, bg=BG_PANEL, fg="#888",
            ).place(x=622, y=14, width=120, height=24)

        # ========== 右侧模式按钮 ==========
        # [功能点] 数据模式 / 软测模式子窗口
        self._btn("数据模式", 820, 66, 130, 40, lambda: self.data_win.show(), FONT_BTN_LG)
        self._btn("软测模式", 820, 118, 130, 40, lambda: self.test_win.show(), FONT_BTN_LG)

        # ========== 分组标题 ==========
        # 大轮
        self._lbl("大轮电机 B", 36, 68, 110, 24, FONT_TITLE)
        self._lbl("T/G          Y/H", 30, 92, 120, 22, FONT_HINT, fg="#666")
        # 主水泵
        self._lbl("主水泵 N", 188, 68, 100, 24, FONT_TITLE)
        self._lbl("U/J          I/K", 180, 92, 120, 22, FONT_HINT, fg="#666")
        # 推进器
        self._lbl("推进器 M", 360, 68, 100, 24, FONT_TITLE)
        self._lbl("7/4       8/5       9/6", 340, 92, 160, 22, FONT_HINT, fg="#666")
        # 边刷 / 浮腔 / 试剂
        self._lbl("边刷", 540, 68, 70, 22, FONT_TITLE)
        self._lbl("O        P", 530, 90, 90, 20, FONT_HINT, fg="#666")
        self._lbl("浮腔泵", 640, 68, 70, 22, FONT_TITLE)
        self._lbl("{        }", 630, 90, 90, 20, FONT_HINT, fg="#666")
        self._lbl("试剂泵", 740, 68, 60, 22, FONT_TITLE)
        self._lbl("|", 758, 90, 24, 20, FONT_HINT, fg="#666")

        # ========== 主滑条（加宽间距）==========
        self.sliders = {}
        y_main, h_main = 120, 220
        # 大轮 两根，间距加大
        lw = self._place_scale(48, y_main, h_main, 100, 0, 50, self._set_wheel)
        rw = self._place_scale(108, y_main, h_main, 100, 0, 50, self._set_wheel)
        self.sliders["wheel"] = (lw, rw)

        lp = self._place_scale(200, y_main, h_main, 200, 0, 100, self._set_pump)
        rp = self._place_scale(260, y_main, h_main, 200, 0, 100, self._set_pump)
        self.sliders["pump"] = (lp, rp)

        lpr = self._place_scale(352, y_main, h_main, 100, 0, 50, self._set_prop)
        rpr = self._place_scale(412, y_main, h_main, 100, 0, 50, self._set_prop)
        self.sliders["prop"] = (lpr, rpr)

        side = self._place_scale(472, y_main, h_main, 100, 0, 50, self._set_side)
        self.sliders["side"] = (side, None)
        self._lbl("侧推进器", 452, 350, 72, 22, FONT_HINT, fg="#555")

        # 短滑条：边刷 / 浮腔泵 / 试剂泵
        y_short, h_short = 118, 100
        lb = self._place_scale(545, y_short, h_short, 2, 0, 1, self._set_brush, width=28)
        rb = self._place_scale(595, y_short, h_short, 2, 0, 1, self._set_brush, width=28)
        self.sliders["brush"] = (lb, rb)

        la = self._place_scale(650, y_short, h_short, 2, 0, 1, self._set_air, width=28)
        ra = self._place_scale(700, y_short, h_short, 2, 0, 1, self._set_air, width=28)
        self.sliders["air"] = (la, ra)

        re_ = self._place_scale(750, y_short, h_short, 2, 0, 1, self._set_reagent, width=28)
        self.sliders["reagent"] = (re_, None)

        # 仓门 / 流道
        self._lbl("仓门", 545, 240, 80, 22, FONT_TITLE)
        self._lbl("<          >", 535, 262, 100, 20, FONT_HINT, fg="#666")
        self._lbl("流道", 665, 240, 80, 22, FONT_TITLE)
        self._lbl("；          ‘", 655, 262, 100, 20, FONT_HINT, fg="#666")
        lh = self._place_scale(555, 288, 70, 1, 0, 0, self._set_hatch, width=26)
        rh = self._place_scale(605, 288, 70, 1, 0, 0, self._set_hatch, width=26)
        self.sliders["hatch"] = (lh, rh)
        lr = self._place_scale(675, 288, 70, 1, 0, 0, self._set_runner, width=26)
        rr = self._place_scale(725, 288, 70, 1, 0, 0, self._set_runner, width=26)
        self.sliders["runner"] = (lr, rr)

        # ========== 右侧控制区 ==========
        right = tk.Frame(self, bg=BG_PANEL, highlightthickness=1, highlightbackground="#ddd")
        right.place(x=820, y=175, width=140, height=200)

        self.prop_mode = tk.BooleanVar(value=False)
        tk.Checkbutton(
            right, text="推进器 Q", variable=self.prop_mode,
            font=FONT_LABEL, bg=BG_PANEL, activebackground=BG_PANEL, fg="#333",
        ).place(x=12, y=8, width=110, height=24)

        tk.Label(
            right, text="W   E   R\nS   D   F\nX   C   V",
            font=FONT_KEYS, bg=BG_PANEL, fg="#333", justify="center",
        ).place(x=20, y=40, width=100, height=72)

        tk.Label(
            right,
            text="A: 全部复位\nB: 大轮停止\nN: 主水泵停止\nM: 推进器停止",
            font=FONT_HINT, bg=BG_PANEL, fg="#555", justify="left", anchor="nw",
        ).place(x=12, y=118, width=120, height=72)

        self.mode_var = tk.StringVar(value="自动")
        mode_cb = ttk.Combobox(
            self, textvariable=self.mode_var, state="readonly", font=FONT_INPUT,
            values=["自动", "手动", "急停", "清洁", "探索", "弓子", "随机", "沿边"],
        )
        mode_cb.place(x=820, y=392, width=130, height=34)
        mode_cb.bind("<<ComboboxSelected>>", self._on_mode)

        self._btn("急停", 820, 440, 130, 42, self._emergency_stop, FONT_BTN_LG)

        # ========== 底部输入区 ==========
        bottom = tk.Frame(self, bg=BG_PANEL, height=56)
        bottom.place(x=0, y=390, width=800, height=56)

        tk.Label(bottom, text="大轮", font=FONT_LABEL, bg=BG_PANEL, fg="#333").place(x=16, y=14, width=36, height=28)
        self.edit_wheel = tk.StringVar()
        tk.Entry(bottom, textvariable=self.edit_wheel, font=FONT_INPUT, relief=tk.SOLID, bd=1).place(
            x=54, y=14, width=64, height=28
        )
        tk.Label(bottom, text="mm/s", font=FONT_HINT, bg=BG_PANEL, fg="#666").place(x=122, y=14, width=40, height=28)

        tk.Label(bottom, text="主水泵", font=FONT_LABEL, bg=BG_PANEL, fg="#333").place(x=175, y=14, width=48, height=28)
        self.edit_pump = tk.StringVar()
        tk.Entry(bottom, textvariable=self.edit_pump, font=FONT_INPUT, relief=tk.SOLID, bd=1).place(
            x=226, y=14, width=64, height=28
        )
        tk.Label(bottom, text="rpm", font=FONT_HINT, bg=BG_PANEL, fg="#666").place(x=294, y=14, width=36, height=28)

        tk.Label(bottom, text="推进器", font=FONT_LABEL, bg=BG_PANEL, fg="#333").place(x=340, y=14, width=48, height=28)
        self.edit_prop = tk.StringVar()
        tk.Entry(bottom, textvariable=self.edit_prop, font=FONT_INPUT, relief=tk.SOLID, bd=1).place(
            x=392, y=14, width=64, height=28
        )
        tk.Label(bottom, text="rpm", font=FONT_HINT, bg=BG_PANEL, fg="#666").place(x=460, y=14, width=36, height=28)

        tk.Button(
            bottom, text="电机确定", font=FONT_BTN, command=self._motor_confirm,
            bg="#e8e8e8", relief=tk.GROOVE, bd=1, cursor="hand2",
        ).place(x=520, y=10, width=96, height=36)

        # ========== 状态栏 ==========
        self.cmd_label = tk.Label(
            self, text="motor speed: 0 0 mm/s", font=FONT_LABEL,
            bg=BG, fg="#1565c0", anchor="w",
        )
        self.cmd_label.place(x=16, y=456, width=780, height=24)

        self.ack_label = tk.Label(
            self, text="NULL", font=FONT_MONO,
            bg="#fafafa", fg="#333", anchor="nw", justify="left",
            wraplength=780, relief=tk.SOLID, bd=1,
        )
        self.ack_label.place(x=16, y=484, width=780, height=96)

    # ---------- 串口 / IP ----------
    def _refresh_ports(self):
        # [功能点-串口] 刷新本机 COM 列表，优先选中 CH340
        ports = list_serial_ports()
        values = [f"{d}  ({desc})" if desc else d for d, desc in ports]
        self.port_cb["values"] = values
        if values:
            ch = next((v for v in values if any(k in v.upper() for k in ("CH340", "WCH", "USBSERIAL", "USB-SERIAL", "CU."))), values[0])
            self.port_var.set(ch)
        else:
            self.port_var.set("")

    def _current_port(self) -> str:
        raw = self.port_var.get().strip()
        return raw.split()[0] if raw else ""

    def _set_link_ui(self, mode: Optional[str]):
        """[功能点] 根据当前连接方式刷新顶部按钮。mode: None/serial/tcp"""
        if mode == "serial":
            self.open_btn.config(text="关闭串口")
            self.port_cb.config(state="disabled")
            if self.ip_btn is not None:
                self.ip_btn.config(text="连接")
            if self.ip_entry is not None:
                self.ip_entry.config(state="disabled")
        elif mode == "tcp":
            # IP 路径 UI（ENABLE_IP_FEATURE=True 时才会走到）
            if self.ip_btn is not None:
                self.ip_btn.config(text="断开")
            if self.ip_entry is not None:
                self.ip_entry.config(state="disabled")
            self.open_btn.config(text="打开串口")
            self.port_cb.config(state="readonly")
        else:
            self.open_btn.config(text="打开串口")
            self.port_cb.config(state="readonly")
            if self.ip_btn is not None:
                self.ip_btn.config(text="连接")
            if self.ip_entry is not None:
                self.ip_entry.config(state="normal")

    def _toggle_port(self):
        # [功能点-串口] 打开/关闭本机 USB 串口
        if self.hub.is_open() and self.hub.transport() == "serial":
            self.hub.close()
            self._set_link_ui(None)
            self.cmd_label.config(text="串口已关闭")
            return
        if self.hub.is_open() and self.hub.transport() == "tcp":
            messagebox.showwarning("提示", "请先断开 IP 连接，再打开串口")
            return
        port = self._current_port()
        if not port:
            messagebox.showwarning("提示", "请先选择串口")
            return
        try:
            self.hub.open_serial(port, 115200)
        except serial.SerialException as e:
            messagebox.showerror("打开失败", str(e))
            return
        self._set_link_ui("serial")
        self.cmd_label.config(text=f"串口已连接 {port}")

    def _toggle_ip(self):
        # [功能点-IP] IP 连接/断开入口（当前 ENABLE_IP_FEATURE=False，UI 已隐藏）
        if not ENABLE_IP_FEATURE:
            messagebox.showinfo("提示", "IP 功能已暂时屏蔽，请使用串口调试")
            return
        if self.hub.is_open() and self.hub.transport() == "tcp":
            self.hub.close()
            self._set_link_ui(None)
            self.cmd_label.config(text="IP 已断开")
            return
        if self.hub.is_open() and self.hub.transport() == "serial":
            messagebox.showwarning("提示", "请先关闭串口，再连接设备 IP")
            return
        try:
            host, port = parse_ip_port(self.ip_var.get())
        except ValueError as e:
            messagebox.showwarning("提示", str(e))
            return
        if not same_lan(host):
            messagebox.showerror(
                "网络错误",
                f"目标设备 {host} 与本机不在同一局域网，无法连接！\n"
                f"本机IP: {', '.join(get_local_ipv4_list()) or '未知'}",
            )
            return
        if self.ip_btn is not None:
            self.ip_btn.config(state="disabled", text="连接中…")
        self.update_idletasks()

        def do_connect():
            err = None
            used_port = None
            used_mode = None
            if not ping_host(host):
                err = (
                    f"无法 ping 通 {host}。\n"
                    "请确认电脑与设备在同一局域网，且设备已开机联网。"
                )
            else:
                # 默认 / 5555：纯 IP 路径（ADB 拉桥 + TCP:9998），不使用本机 COM
                try_adb = (port in ADB_PORTS) if port is not None else True
                if try_adb:
                    adb_port = port if port in ADB_PORTS else 5555
                    try:
                        self.hub.open_ip_bridge(host, adb_port)
                        used_port = INNOVATE_IP_BRIDGE_PORT
                        used_mode = "tcp"
                    except Exception as e:
                        if port in ADB_PORTS or port is None:
                            err = (
                                f"IP 调试通道建立失败 {host}\n{e}\n\n"
                                "请确认：设备网络调试已开、本机已装 adb，\n"
                                f"且同目录存在 {BRIDGE_SCRIPT_NAME}。"
                            )
                if used_mode is None and err is None:
                    ports = [port] if (port is not None and port not in ADB_PORTS) else [
                        p for p in CANDIDATE_TCP_PORTS if p not in ADB_PORTS
                    ]
                    for p in ports:
                        if p in (8111, INNOVATE_IP_BRIDGE_PORT):
                            continue
                        sock = try_tcp_connect(host, p, timeout=1.2)
                        if sock is not None:
                            try:
                                self.hub.open_tcp_sock(sock)
                                used_port = p
                                used_mode = "tcp"
                                break
                            except Exception:
                                try:
                                    sock.close()
                                except Exception:
                                    pass
                    if used_mode is None and err is None:
                        err = (
                            f"设备 {host} 可以 ping 通，但未能建立 IP 调试通道。\n"
                            "请使用 IP:5555，或改用「打开串口」。"
                        )

            def done():
                if self.ip_btn is not None:
                    self.ip_btn.config(state="normal")
                if err:
                    self._set_link_ui(None)
                    messagebox.showerror("连接失败", err)
                    return
                self._set_link_ui(used_mode)
                self.ip_var.set(f"{host}:{used_port}")
                self.cmd_label.config(text=f"IP 已连接 {host}:{used_port}（网络路径）")
                self.ack_label.config(
                    text="IP 路径已就绪（ROS/motor_control）。已自动切入手动态，输入参数后点「电机确定」。"
                )
                # IP 调试默认切手动，并持续由设备端桥发布
                try:
                    self.hub.send("SET state 2.")
                except Exception:
                    pass

            self.after(0, done)

        threading.Thread(target=do_connect, daemon=True).start()

    def _on_link_lost(self, reason: str):
        # [功能点] 链路异常断开时复位顶部连接状态
        self._set_link_ui(None)
        self.cmd_label.config(text=reason)
        messagebox.showwarning("连接断开", reason)

    def _on_raw(self, data: str):
        # [功能点] 回显设备 ACK / 原始文本（限流刷新）
        now = int(time.time() * 1000)
        if now - self._ack_last_ms >= 200:
            self._ack_last_ms = now
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.ack_label.config(text=f"{ts} {data}")
        else:
            self.ack_label.config(text=self.ack_label.cget("text") + data)

    def _send(self, cmd: str):
        # [功能点] UI 命令统一出口 → SerialHub.send
        self.cmd_label.config(text=cmd)
        try:
            self.hub.send(cmd)
        except OSError as e:
            messagebox.showwarning("无法下发", str(e))

    # ---------- 模式 / 急停 ----------
    def _on_mode(self, _evt=None):
        # [功能点] 工作模式切换 → SET state N.
        names = ["自动", "手动", "急停", "清洁", "探索", "弓子", "随机", "沿边"]
        try:
            idx = names.index(self.mode_var.get())
        except ValueError:
            return
        state = MODE_STATE.get(idx)
        if state is not None:
            self._send(f"SET state {state}.")

    def _emergency_stop(self):
        # [功能点] 急停 → SET stop
        self._send("SET stop")
        self.mode_var.set("急停")

    # ---------- 滑条映射（与 C++ 一致） ----------
    # [功能点] 滑条即时下发 Innovate ASCII（MV ...）
    def _pair(self, key):
        a, b = self.sliders[key]
        return a.get(), (b.get() if b is not None else None)

    def _set_wheel(self):
        # [功能点] 大轮电机
        l, r = self._pair("wheel")
        ls, rs = (l - 50) * 5, (r - 50) * 5
        self._send(f"MV wheel motor {ls} {rs}.")

    def _set_pump(self):
        # [功能点] 主水泵
        l, r = self._pair("pump")
        ls, rs = (l - 100) * 50, (r - 100) * 50
        self._send(f"MV water pump {ls} {rs}.")

    def _set_prop(self):
        # [功能点] 推进器
        l, r = self._pair("prop")
        ls, rs = (l - 50) * 50, (r - 50) * 50
        self._send(f"MV prop motor {ls} {rs}.")

    def _set_side(self):
        # [功能点] 侧推进器
        l, _ = self._pair("side")
        self._send(f"MV prop side motor {(l - 50) * 100}.")

    def _set_brush(self):
        # [功能点] 边刷
        l, r = self._pair("brush")
        mp = {0: -60, 1: 0, 2: 60}
        self._send(f"MV side brush {mp.get(l, 0)} {mp.get(r, 0)}.")

    def _set_air(self):
        # [功能点] 浮腔泵
        l, r = self._pair("air")
        # 滑条 0/1/2 -> 命令 2/0/1
        mp = {0: 2, 1: 0, 2: 1}
        self._send(f"MV air pump {mp.get(l, 0)} {mp.get(r, 0)}.")

    def _set_reagent(self):
        # [功能点] 试剂泵
        l, _ = self._pair("reagent")
        mp = {0: 2, 1: 0, 2: 1}
        self._send(f"MV reagent motor {mp.get(l, 0)}.")

    def _set_hatch(self):
        l, r = self._pair("hatch")
        self._send(f"MV hatch motor {l} {r}.")

    def _set_runner(self):
        l, r = self._pair("runner")
        self._send(f"MV runner motor {l} {r}.")

    def _block(self, state: bool):
        self._block_slider = state

    def _reset_all_sliders(self):
        self._block(True)
        defaults = {
            "wheel": (50, 50), "pump": (100, 100), "prop": (50, 50),
            "side": (50, None), "brush": (1, 1), "air": (1, 1),
            "reagent": (1, None), "hatch": (0, 0), "runner": (0, 0),
        }
        for k, (lv, rv) in defaults.items():
            a, b = self.sliders[k]
            a.set(lv)
            if b is not None and rv is not None:
                b.set(rv)
        self.edit_wheel.set("")
        self.edit_pump.set("")
        self.edit_prop.set("")
        self._block(False)

    # ---------- 电机确定（定时依次发） ----------
    def _motor_confirm(self):
        # [功能点] 「电机确定」：按编辑框依次下发轮/泵/推进器 Innovate 指令
        if not self.hub.is_open():
            tip = "请先打开串口" if not ENABLE_IP_FEATURE else "请先打开串口或连接设备 IP"
            messagebox.showwarning("提示", tip)
            return
        if not self.hub.can_send_innovate():
            tip = (
                "当前连接不可下发指令，请重新连接串口"
                if not ENABLE_IP_FEATURE
                else "当前连接不可下发指令，请重新连接串口或 IP"
            )
            messagebox.showwarning("提示", tip)
            return
        self._motor_sure = 1

    def _motor_sure_tick(self):
        s = self._motor_sure
        if s == 1:
            self._motor_sure += 1
            t = self.edit_wheel.get().strip()
            if t:
                try:
                    v = int(t)
                    self._send(f"MV wheel motor {v} {v}.")
                except ValueError:
                    pass
        elif s == 10:
            self._motor_sure += 1
            t = self.edit_pump.get().strip()
            if t:
                try:
                    v = int(t)
                    self._send(f"MV water pump {v} {v}.")
                except ValueError:
                    pass
            self._motor_sure += 1
        elif s == 20:
            self._motor_sure = 0
            t = self.edit_prop.get().strip()
            if t:
                try:
                    v = int(t)
                    self._send(f"MV prop motor {v} {v}.")
                except ValueError:
                    pass
        elif s != 0:
            self._motor_sure += 1
        try:
            self.after(10, self._motor_sure_tick)
        except tk.TclError:
            pass

    # ---------- 键盘 ----------
    def _adj(self, var: tk.IntVar, delta: int, lo: int, hi: int, mid: int, band: int = 4, apply=None):
        v = var.get() + delta
        v = max(lo, min(hi, v))
        if mid - band < v < mid + band:
            v = mid
        self._block(True)
        var.set(v)
        self._block(False)
        if apply:
            apply()

    def _cycle3(self, var: tk.IntVar, apply=None):
        self._block(True)
        var.set((var.get() + 1) % 3)
        self._block(False)
        if apply:
            apply()

    def _toggle01(self, var: tk.IntVar, apply=None):
        self._block(True)
        var.set(0 if var.get() else 1)
        self._block(False)
        if apply:
            apply()

    def _on_key_press(self, event):
        # 输入框获得焦点时，不抢字母键 / 方向键
        w = self.focus_get()
        if isinstance(w, (ttk.Entry, tk.Entry, tk.Text, scrolledtext.ScrolledText)):
            if event.keysym not in ("Escape",):
                return

        key = event.keysym
        ch = event.char

        # ↑↓：调节当前选中的滑条（先鼠标点一下选中）
        if key in ("Up", "Down"):
            sc = self._active_scale
            # 若焦点在某个滑条 Canvas 上，定位对应 meta
            if isinstance(w, tk.Canvas):
                for m in self._scale_widgets:
                    if m["canvas"] is w:
                        sc = m["proxy"]
                        break
            if sc is not None:
                return self._nudge_scale(sc, +1 if key == "Up" else -1)
            return

        if key in ("a", "A"):
            self._reset_all_sliders()
            return
        if key in ("q", "Q"):
            self.prop_mode.set(not self.prop_mode.get())
            return

        # 大轮
        if key in ("b", "B"):
            self._block(True)
            self.sliders["wheel"][0].set(50)
            self.sliders["wheel"][1].set(50)
            self._block(False)
            self._set_wheel()
            return
        if key in ("t", "T"):
            self._adj(self.sliders["wheel"][0], 4, 0, 100, 50, apply=self._set_wheel)
            return
        if key in ("g", "G"):
            self._adj(self.sliders["wheel"][0], -4, 0, 100, 50, apply=self._set_wheel)
            return
        if key in ("y", "Y"):
            self._adj(self.sliders["wheel"][1], 4, 0, 100, 50, apply=self._set_wheel)
            return
        if key in ("h", "H"):
            self._adj(self.sliders["wheel"][1], -4, 0, 100, 50, apply=self._set_wheel)
            return

        # 水泵
        if key in ("n", "N"):
            self._block(True)
            self.sliders["pump"][0].set(100)
            self.sliders["pump"][1].set(100)
            self._block(False)
            self._set_pump()
            return
        if key in ("u", "U"):
            self._adj(self.sliders["pump"][0], 4, 0, 200, 100, apply=self._set_pump)
            return
        if key in ("j", "J"):
            self._adj(self.sliders["pump"][0], -4, 0, 200, 100, apply=self._set_pump)
            return
        if key in ("i", "I"):
            self._adj(self.sliders["pump"][1], 4, 0, 200, 100, apply=self._set_pump)
            return
        if key in ("k", "K"):
            self._adj(self.sliders["pump"][1], -4, 0, 200, 100, apply=self._set_pump)
            return

        # 推进器
        if key in ("m", "M"):
            self._block(True)
            self.sliders["prop"][0].set(50)
            self.sliders["prop"][1].set(50)
            self.sliders["side"][0].set(50)
            self._block(False)
            self._set_prop()
            self._set_side()
            return
        if key == "7":
            self._adj(self.sliders["prop"][0], 4, 0, 100, 50, apply=self._set_prop)
            return
        if key == "4":
            self._adj(self.sliders["prop"][0], -4, 0, 100, 50, apply=self._set_prop)
            return
        if key == "8":
            self._adj(self.sliders["prop"][1], 4, 0, 100, 50, apply=self._set_prop)
            return
        if key == "5":
            self._adj(self.sliders["prop"][1], -4, 0, 100, 50, apply=self._set_prop)
            return
        if key == "9":
            self._adj(self.sliders["side"][0], 4, 0, 100, 50, apply=self._set_side)
            return
        if key == "6":
            self._adj(self.sliders["side"][0], -4, 0, 100, 50, apply=self._set_side)
            return

        if key in ("o", "O"):
            self._cycle3(self.sliders["brush"][0], apply=self._set_brush)
            return
        if key in ("p", "P"):
            self._cycle3(self.sliders["brush"][1], apply=self._set_brush)
            return
        if ch in ("[", "{"):
            self._cycle3(self.sliders["air"][0], apply=self._set_air)
            return
        if ch in ("]", "}"):
            self._cycle3(self.sliders["air"][1], apply=self._set_air)
            return
        if ch in ("\\", "|"):
            self._cycle3(self.sliders["reagent"][0], apply=self._set_reagent)
            return
        if ch in (",", "<"):
            self._toggle01(self.sliders["hatch"][0], apply=self._set_hatch)
            return
        if ch in (".", ">"):
            self._toggle01(self.sliders["hatch"][1], apply=self._set_hatch)
            return
        if ch in (";", ":"):
            self._toggle01(self.sliders["runner"][0], apply=self._set_runner)
            return
        if ch in ("'", '"'):
            self._toggle01(self.sliders["runner"][1], apply=self._set_runner)
            return

        # WASD 方向控制
        if key.upper() not in ("W", "E", "R", "S", "D", "F", "X", "C", "V"):
            return

        if self.prop_mode.get():
            try:
                base = int(self.edit_prop.get().strip() or "0")
            except ValueError:
                base = 0
            if base < PROP_MIN_SPEED or base > 3000:
                base = PROP_NORM_SPEED
            mapping = {
                "W": (PROP_MIN_SPEED, base),
                "E": (base, base),
                "R": (base, PROP_MIN_SPEED),
                "S": (-1500, 1500) if base > 1500 else (-base, base),
                "D": (0, 0),
                "F": (1500, -1500) if base > 1500 else (base, -base),
                "X": (-1000, -1600),
                "C": (-base, -base),
                "V": (-1600, -1000),
            }
            ls, rs = mapping[key.upper()]
            self._send(f"MV prop motor {ls} {rs}.")
        else:
            try:
                base = int(self.edit_wheel.get().strip() or "0")
            except ValueError:
                base = 0
            if base < WHEEL_MIN_SPEED or base > 300:
                base = WHEEL_NORM_SPEED
            mapping = {
                "W": (base - WHEEL_DIFF_SPEED, base),
                "E": (base, base),
                "R": (base, base - WHEEL_DIFF_SPEED),
                "S": (-100, 100) if base > 100 else (-base, base),
                "D": (0, 0),
                "F": (100, -100) if base > 100 else (base, -base),
                "X": (-100, -160),
                "C": (-base, -base),
                "V": (-160, -100),
            }
            ls, rs = mapping[key.upper()]
            self._send(f"MV wheel motor {ls} {rs}.")

    def _on_key_release(self, event):
        if event.keysym in ("equal", "plus") or event.char == "=":
            self._equal_count += 1
            if self._equal_count >= 3:
                self._equal_count = 0
                self.dev_win.show()
        else:
            self._equal_count = 0

    def _on_close(self):
        # [功能点] 关闭工具窗；独立运行时一并销毁隐藏根窗口
        self.hub.close()
        self.destroy()
        if self._own_root is not None:
            try:
                self._own_root.destroy()
            except Exception:
                pass

    def mainloop(self, n=0):
        # 独立运行走隐藏根的 mainloop；嵌入时由软测主程序驱动事件循环
        if self._own_root is not None:
            self._own_root.mainloop(n)


def open_as_child(master):
    """[功能点] 供软测主程序嵌入调用：以子窗口打开 MCU 工具。"""
    return MainApp(master=master)


def main():
    # [功能点] 程序入口：独立启动主界面（默认仅串口；IP 由 ENABLE_IP_FEATURE 控制）
    app = MainApp()
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
    app.mainloop()


if __name__ == "__main__":
    main()
