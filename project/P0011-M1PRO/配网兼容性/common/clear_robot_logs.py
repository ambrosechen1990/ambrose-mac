#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清空机器人 /data/log 目录的辅助脚本。

用法:
   python3 clear_robot_logs.py --device galaxy_p0001

如未指定 --device，将优先读取环境变量 ROBOT_DEVICE_ID，最后默认 galaxy_p0001。
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def get_adb_path() -> str:
    """自动定位 adb 可执行文件."""
    env_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    candidates = []
    if env_home:
        candidates.append(Path(env_home) / "platform-tools" / "adb")
    candidates.extend(
        Path(p) / "platform-tools" / "adb"
        for p in [
            "~/Library/Android/sdk",
            "~/Android/Sdk",
            "/usr/local/share/android-sdk",
            "/opt/android-sdk",
        ]
    )
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.exists():
            return str(candidate)
    return "adb"  # fallback to PATH


def run_cmd(cmd, err_msg, verbose: bool = True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if verbose:
            print(f"❌ {err_msg}: {result.stderr.strip()}", file=sys.stderr)
        raise RuntimeError(f"{err_msg}: {result.stderr.strip()}")
    if verbose and result.stdout.strip():
        print(result.stdout.strip())
    return result.stdout.strip()


def clear_logs(adb_path: str, device: str, verbose: bool = True) -> None:
    """执行日志清空命令."""
    if verbose:
        print(f"🧹 正在清空 {device} 的日志...")

    # 步骤1: 进入 /data 目录，检查并删除 *.tar.gz 文件
    if verbose:
        print(f"🔍 检查 /data 目录下的旧日志包...")
    
    # 列出 /data 下的 tar.gz 文件
    list_data_tar_cmd = [
        adb_path,
        "-s",
        device,
        "shell",
        "cd /data && ls -t *.tar.gz 2>/dev/null | head -n 1"
    ]
    tar_in_data = run_cmd(list_data_tar_cmd, "列出 /data 下 tar.gz 文件失败", verbose=False)

    if tar_in_data:
        if verbose:
            print(f"🗑️ 检测到 /data 下的旧日志包: {tar_in_data}，正在删除...")
        rm_data_tar_cmd = [
            adb_path,
            "-s",
            device,
            "shell",
            f"rm /data/{tar_in_data}"
        ]
        run_cmd(rm_data_tar_cmd, f"删除 /data/{tar_in_data} 失败", verbose=verbose)
        if verbose:
            print(f"✅ 已删除 /data/{tar_in_data}")
    else:
        if verbose:
            print("✅ /data 目录下未找到旧日志包")

    # 步骤2: 进入 /data/log 目录，清空所有文件
    if verbose:
        print(f"🧹 正在清空 /data/log 目录...")
    clear_log_cmd = [
        adb_path,
        "-s",
        device,
        "shell",
        "cd /data/log || exit 1; rm -rf *"
    ]
    run_cmd(clear_log_cmd, "清空 /data/log 失败", verbose=verbose)
    if verbose:
        print("✅ /data/log 目录已清空")


def main() -> None:
    parser = argparse.ArgumentParser(description="清空机器人日志目录")
    parser.add_argument(
        "--device",
        default=os.environ.get("ROBOT_DEVICE_ID", "galaxy_p0001"),
        help="adb 设备序列号（默认取 ROBOT_DEVICE_ID 或 galaxy_p0001）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，仅在失败时输出",
    )
    args = parser.parse_args()

    adb_path = get_adb_path()

    try:
        clear_logs(adb_path, args.device, verbose=not args.quiet)
    except Exception as exc:
        if not args.quiet:
            print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

