#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告与输出目录工具

3功能：
- 为每一次测试运行创建一个独立的输出文件夹（日志 + 截图 + Excel 等）
- 输出文件夹命名规范：{prefix}-YYYY年MM月DD日 HHMMSS
- P0025-V1：统一保存在项目根目录下「2测试报告」内；其他工程仍可用配网目录下 reports/
- 返回并导出：运行目录、日志路径、截图目录（并设置环境变量 BT_RUN_DIR 等）

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
    - **P0025-V1**：`…/P0025-V1/2测试报告/`（与 1共用脚本、3用例 同级）
    - **其他工程**：`…/配网兼容性/reports/` 或 `…/1配网兼容性/reports/` 等

    :param prefix: 目录名前缀，默认 "2蓝牙配网"
    :return: (run_dir, log_file, screenshot_dir)
    """
    # 当前文件所在目录（1共用脚本）
    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent

    # P0025-V1：所有脚本生成的运行目录与 Excel 报告统一落在项目根下「2测试报告」
    if base_dir.name == "1共用脚本" and project_root.name == "P0025-V1":
        reports_dir = project_root / "2测试报告"
    else:
        # 向上查找 "配网兼容性" 目录
        current = base_dir
        compatibility_dir = None

        _COMPAT_DIR_NAMES = frozenset({"配网兼容性", "1配网兼容性"})
        while current.parent != current:
            if current.name in _COMPAT_DIR_NAMES:
                compatibility_dir = current
                break
            current = current.parent

        # 共用脚本与「1配网兼容性」同级时，显式探测
        if compatibility_dir is None:
            _fallback_candidates = [
                project_root / "3用例" / "1配网兼容性",
                project_root / "3用例" / "配网兼容性",
                project_root / "1配网兼容性",
                project_root / "配网兼容性",
            ]
            for c in _fallback_candidates:
                if c.is_dir():
                    compatibility_dir = c
                    break

        if compatibility_dir:
            reports_dir = compatibility_dir / "reports"
        else:
            reports_dir = project_root / "reports"
    
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


