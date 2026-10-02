#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口重启机器脚本

通过串口发送 `SET reset` 重启机器人，供配网兼容性测试在
「每个路由器测完后 / 切换手机设备时」调用。

用法：
  python3 重启机器.py
  python3 重启机器.py --port /dev/cu.usbserial-130 --baud 115200 --wait 60
  python3 重启机器.py --no-wait   # 只发重启命令，不等待

也可被其它脚本 import：
  from 重启机器 import reboot_robot
  reboot_robot(port="...", wait_seconds=60, log_func=print)
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from typing import Callable, Optional


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = os.environ.get("ROBOT_SERIAL_PORT", "/dev/cu.usbserial-130")
DEFAULT_BAUD = int(os.environ.get("ROBOT_SERIAL_BAUD", "115200"))
DEFAULT_CMD = os.environ.get("ROBOT_RESET_CMD", "SET reset")
DEFAULT_WAIT = int(os.environ.get("ROBOT_RESET_WAIT_SECONDS", "60"))


def _log_default(msg: str) -> None:
    print(msg, flush=True)


def _load_port_command_sender():
    """优先复用同目录 端口命令.py 的 send_command。"""
    script = os.path.join(HERE, "端口命令.py")
    if not os.path.isfile(script):
        return None
    try:
        spec = importlib.util.spec_from_file_location("xm_port_command_mod", script)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "send_command", None)
    except Exception:
        return None


def reboot_robot(
    port: Optional[str] = None,
    baud: int = DEFAULT_BAUD,
    command: str = DEFAULT_CMD,
    wait_seconds: int = DEFAULT_WAIT,
    log_func: Callable[[str], None] = _log_default,
) -> bool:
    """
    串口发送重启命令，并可选等待机器重新就绪。

    Returns:
        True: 命令发送成功（等待阶段也会执行）
        False: 串口发送失败
    """
    port = (port or DEFAULT_PORT or "").strip()
    if not port:
        log_func("❌ 未指定串口路径，无法重启机器")
        return False

    log_func(f"🔄 串口重启机器: port={port} baud={baud} cmd={command}")
    sender = _load_port_command_sender()
    ok = False
    detail = ""

    if sender is not None:
        try:
            # settle=0：等待由本函数统一控制，避免端口命令内部再 sleep
            kwargs = {
                "port": port,
                "baudrate": baud,
                "command": command,
                "retry_on_busy": True,
            }
            # 兼容增强版/旧版 端口命令.send_command 签名
            try:
                detail = sender(repeat=1, settle_seconds=0, **kwargs)
            except TypeError:
                detail = sender(**kwargs)
            ok = isinstance(detail, str) and ("❌" not in detail)
            log_func(f"ℹ️ 端口命令结果: {detail}")
        except Exception as e:
            log_func(f"⚠️ 调用端口命令.py 失败: {e}，尝试直接串口发送...")
            ok = False

    if not ok:
        ok = _send_reset_direct(port, baud, command, log_func)

    if not ok:
        log_func("❌ 重启命令发送失败")
        return False

    log_func("✅ 已发送重启命令 SET reset")
    wait_seconds = max(0, int(wait_seconds))
    if wait_seconds > 0:
        log_func(f"⏳ 等待机器重启完成 {wait_seconds}s ({wait_seconds / 60:.1f} min)...")
        time.sleep(wait_seconds)
        log_func("✅ 重启等待结束，可继续下一轮测试")
    return True


def _send_reset_direct(port: str, baud: int, command: str, log_func: Callable[[str], None]) -> bool:
    """端口命令模块不可用时的直接串口发送兜底。"""
    try:
        import serial
    except ImportError:
        log_func("❌ 未安装 pyserial，无法直接发串口命令")
        return False

    # macOS 优先 cu
    use_port = port
    if sys.platform == "darwin" and "tty.usbserial" in port:
        cu = port.replace("tty.usbserial", "cu.usbserial")
        if os.path.exists(cu):
            use_port = cu
            log_func(f"💡 macOS 改用 cu 口: {use_port}")

    if not os.path.exists(use_port):
        log_func(f"❌ 串口不存在: {use_port}")
        return False

    ser = None
    try:
        ser = serial.Serial(use_port, baudrate=baud, timeout=2)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ser.write(b"\r")
        time.sleep(1.0)
        ser.write((command + "\r\n").encode("utf-8"))
        log_func(f"📤 已发送: {command}")
        time.sleep(1.0)
        resp = b""
        start = time.time()
        while time.time() - start < 3:
            if ser.in_waiting:
                resp += ser.read(ser.in_waiting)
                time.sleep(0.05)
            else:
                time.sleep(0.05)
        if resp:
            log_func(f"📥 响应: {resp.decode('utf-8', errors='ignore').strip()}")
        else:
            log_func("⚠️ 未收到响应（重启命令可能仍已生效）")
        return True
    except Exception as e:
        log_func(f"❌ 直接串口发送失败: {e}")
        return False
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="通过串口发送 SET reset 重启机器人")
    parser.add_argument("--port", default=DEFAULT_PORT, help="串口路径")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="波特率")
    parser.add_argument("--command", default=DEFAULT_CMD, help="重启命令，默认 SET reset")
    parser.add_argument(
        "--wait",
        type=int,
        default=DEFAULT_WAIT,
        help="发送后等待秒数，默认 60（1 分钟）",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="只发命令，不等待",
    )
    args = parser.parse_args()
    wait_s = 0 if args.no_wait else args.wait
    ok = reboot_robot(
        port=args.port,
        baud=args.baud,
        command=args.command,
        wait_seconds=wait_s,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
