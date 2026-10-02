# -*- coding: utf-8 -*-
"""项目根路径与默认配置/数据/输出目录。"""

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
BROWSER_PROFILE = ROOT / ".browser_profile"

PRODUCTS_XLSX = CONFIG_DIR / "产品列表.xlsx"
QUESTION_TEMPLATES_JSON = CONFIG_DIR / "question_templates.json"
QUESTION_TEMPLATES_XLSX = CONFIG_DIR / "测试题库.xlsx"
FAQ_EXCEL = DATA_DIR / "APP故障库.xlsx"

AGENT_URL = "https://cn-iot.beatbot.com/agent/"


def new_run_dir(name: str, base: Path | None = None) -> Path:
    """每跑一次建一个 `<时间>_<脚本名>` 目录，报告、Excel、截图都落在里面。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = Path(base or OUTPUT_DIR) / f"{stamp}_{name}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_dirs(name: str, base: Path | None = None) -> list[Path]:
    """同名脚本的历史运行目录，按时间从旧到新。"""
    base = Path(base or OUTPUT_DIR)
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob(f"*_{name}") if p.is_dir())


def latest_run_dir(name: str, base: Path | None = None) -> Path | None:
    """找同名脚本最近一次的运行目录，供断点续跑/回归对比定位上一轮结果。"""
    dirs = run_dirs(name, base)
    return dirs[-1] if dirs else None
