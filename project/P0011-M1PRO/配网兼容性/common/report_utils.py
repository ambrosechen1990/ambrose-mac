#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告与输出目录工具

3功能：
- 在当前工程的 reports 目录下，为每一次测试运行创建一个独立的输出文件夹
- 输出文件夹命名规范：
  2蓝牙配网-YYYY年MM月DD日 HHMMSS
- 返回并导出以下信息：
  - 运行目录路径
  - 日志文件路径（bluetooth_pairing.log）
  - 截图目录路径（screenshots）

使用方式（在蓝牙配网脚本中）：

    from report_utils import init_run_env

    RUN_DIR, LOG_FILE, SCREENSHOT_DIR = init_run_env()

    logging.basicConfig(
        ...,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )
"""

import os
from datetime import datetime
from pathlib import Path


def init_run_env(prefix: str = "2蓝牙配网") -> tuple[Path, Path, Path]:
    """
    创建一次测试运行的输出目录，并返回相关路径。

    报告目录规则：
    - 自动识别当前项目目录（P0011-M1PRO、P0024 等）
    - 在当前项目目录下的 reports 文件夹保存报告
    - 例如：P0011-M1PRO/配网兼容性/reports/ 或 P0024/配网兼容性/reports/

    :param prefix: 目录名前缀，默认 "2蓝牙配网"
    :return: (run_dir, log_file, screenshot_dir)
    """
    import re
    
    # 当前文件所在目录（common 目录）
    base_dir = Path(__file__).resolve().parent
    
    # 向上查找 "配网兼容性" 目录
    # 报告将保存在：项目目录/配网兼容性/reports/
    current = base_dir
    compatibility_dir = None
    
    # 项目目录匹配模式：P 开头，后跟数字（如 P0011-M1PRO, P0024）
    project_pattern = re.compile(r'^P\d+$')
    
    # 向上查找，找到 "配网兼容性" 目录
    while current.parent != current:
        if current.name == "配网兼容性":
            compatibility_dir = current
            break
        current = current.parent
    
    # 如果找到了配网兼容性目录，使用其下的 reports 目录
    # 这样无论项目是 P0011-M1PRO 还是 P0024，都会在对应的项目目录下创建 reports
    if compatibility_dir:
        reports_dir = compatibility_dir / "reports"
    else:
        # 如果找不到，回退到原来的逻辑（在 common 同级目录创建 reports）
        reports_dir = base_dir.parent / "reports"
    
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 生成形如：2蓝牙配网-2025年12月03日 165623 的目录名
    now = datetime.now()
    folder_name = f"{prefix}-{now.year}年{now.month:02d}月{now.day:02d}日 {now.hour:02d}{now.minute:02d}{now.second:02d}"
    run_dir = reports_dir / folder_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # 日志文件路径
    log_file = run_dir / "bluetooth_pairing.log"

    # 截图目录
    screenshot_dir = run_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # 通过环境变量暴露给下游脚本（可选）
    os.environ["BT_RUN_DIR"] = str(run_dir)
    os.environ["BT_LOG_FILE"] = str(log_file)
    os.environ["BT_SCREENSHOT_DIR"] = str(screenshot_dir)

    return run_dir, log_file, screenshot_dir


