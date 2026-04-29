#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包并拉取机器人日志的辅助脚本。

用法:
   python3 pack_robot_logs.py --device galaxy_p0001 --dest ./reports/run_xxx

如未指定 --device，将优先读取环境变量 ROBOT_DEVICE_ID。
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def get_adb_path() -> str:
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
    return "adb"


def run_cmd(cmd, err_msg, verbose: bool = True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if verbose:
            print(f"❌ {err_msg}: {result.stderr.strip()}", file=sys.stderr)
        raise RuntimeError(f"{err_msg}: {result.stderr.strip()}")
    if verbose and result.stdout.strip():
        print(result.stdout.strip())
    return result.stdout.strip()


def pack_logs(adb_path: str, device: str, dest: Path, verbose: bool = True) -> Path:
    if verbose:
        print(f"📦 正在触发 {device} 的日志打包 ...")
    
    # 执行 pack 命令
    pack_cmd = [adb_path, "-s", device, "shell", "pack"]
    pack_output = run_cmd(pack_cmd, "pack 命令执行失败", verbose=verbose)
    
    if verbose:
        print("✅ pack 命令已执行，正在定位最新 tar 包")

    # 查找最新生成的 tar.gz 文件，优先在 /data/log，其次在 /data
    find_tar_cmd = [
        adb_path,
        "-s",
        device,
        "shell",
        "find /data /data/log -maxdepth 1 -name '*.tar.gz' -printf '%T@ %p\\n' 2>/dev/null | sort -r | head -n 1 | awk '{print $2}'"
    ]
    
    tar_path = run_cmd(find_tar_cmd, "查找 tar.gz 文件失败", verbose=False)
    
    if not tar_path:
        raise RuntimeError("未找到可用的 tar.gz 日志包")

    dest.mkdir(parents=True, exist_ok=True)
    target_file = dest / Path(tar_path).name

    if verbose:
        print(f"⬇️ 正在拉取 {tar_path} 到 {target_file}")

    pull_cmd = [
        adb_path,
        "-s",
        device,
        "pull",
        tar_path,
        str(target_file),
    ]
    run_cmd(pull_cmd, "adb pull 失败", verbose=verbose)

    if verbose:
        print(f"✅ 日志包已保存: {target_file}")
    return target_file


def main() -> None:
    parser = argparse.ArgumentParser(description="打包并拉取机器人日志")
    parser.add_argument(
        "--device",
        default=os.environ.get("ROBOT_DEVICE_ID", "galaxy_p0001"),
        help="adb 设备序列号（默认取 ROBOT_DEVICE_ID 或 galaxy_p0001）",
    )
    parser.add_argument(
        "--dest",
        default=".",
        help="日志保存目录，默认当前目录",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，仅在失败时输出",
    )
    args = parser.parse_args()

    adb_path = get_adb_path()
    dest_dir = Path(args.dest).expanduser().resolve()

    try:
        pack_logs(adb_path, args.device, dest_dir, verbose=not args.quiet)
    except Exception as exc:
        if not args.quiet:
            print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
