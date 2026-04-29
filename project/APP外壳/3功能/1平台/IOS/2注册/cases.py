import os
import sys
import re
import importlib.util
import logging
import types
from pathlib import Path

# APP外壳 已取消 comman：共用逻辑在「1共用脚本」
_cur = Path(__file__).resolve().parent
_shared = None
for _ in range(24):
    _cand = _cur / "1共用脚本"
    if _cand.is_dir() and (_cand / "common_utils.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 APP外壳/1共用脚本（需包含 common_utils.py）")
from typing import Callable, Dict, List, Tuple


# 共用逻辑在 project/APP外壳/1共用脚本（由各用例先注入 sys.path）
THIS_DIR = Path(__file__).resolve().parent  # .../平台/IOS/2注册
PLATFORM_DIR = THIS_DIR.parents[1]  # .../平台
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

# cases loader 仍会对「comman」做 monkeypatch；已取消 comman 包，用占位对象承接属性
comman = types.SimpleNamespace()


def _find_case_file(case_dir: Path, case_id: str) -> Path:
    # Files are like: 102025验证注册时邮箱显示包含不支持的特殊字符.py
    # Search both current directory and archive/ to allow reducing clutter.
    search_dirs = [case_dir, case_dir / "archive"]
    for d in search_dirs:
        matches = sorted(d.glob(f"{case_id}*.py")) if d.exists() else []
        if matches:
            return matches[0]
    raise FileNotFoundError(f"未找到 case_id={case_id} 对应的用例文件（在 {case_dir} 或 {case_dir/'archive'}）")


_CASE_MODULE_CACHE: Dict[str, object] = {}


def _load_case_module(case_id: str):
    """
    加载旧的 pytest 用例脚本，但在加载/执行期间将其 report/screenshot 行为禁用，
    从而让统一 runner 来写报告。
    """
    if case_id in _CASE_MODULE_CACHE:
        return _CASE_MODULE_CACHE[case_id]

    case_dir = THIS_DIR
    case_file = _find_case_file(case_dir, case_id)

    # Patch comman exports BEFORE executing the old module code, so that
    # `from report_utils / screenshot_utils import ...`（经 1共用脚本）
    # will bind to our no-op functions.
    orig_init_report = getattr(comman, "init_report", None)
    orig_bind_logger = getattr(comman, "bind_logger_to_print", None)
    orig_write_report = getattr(comman, "write_report", None)
    orig_save_failure_screenshot = getattr(comman, "save_failure_screenshot", None)

    class _DummyLogger(logging.Logger):
        def __init__(self):
            super().__init__("dummy")

    def _dummy_init_report(run_label: str = "ios"):
        # Return a stable but non-writing run_dir to avoid clutter.
        return Path.cwd(), _DummyLogger(), run_label, "0"

    def _dummy(*args, **kwargs):
        return None

    try:
        comman.init_report = _dummy_init_report  # type: ignore
        comman.bind_logger_to_print = _dummy  # type: ignore
        comman.write_report = _dummy  # type: ignore
        comman.save_failure_screenshot = _dummy  # type: ignore

        module_name = f"cases_register_{case_id}"
        spec = importlib.util.spec_from_file_location(module_name, str(case_file))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载模块: {case_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        # Restore original exports
        if orig_init_report is not None:
            comman.init_report = orig_init_report  # type: ignore
        if orig_bind_logger is not None:
            comman.bind_logger_to_print = orig_bind_logger  # type: ignore
        if orig_write_report is not None:
            comman.write_report = orig_write_report  # type: ignore
        if orig_save_failure_screenshot is not None:
            comman.save_failure_screenshot = orig_save_failure_screenshot  # type: ignore

    _CASE_MODULE_CACHE[case_id] = module
    return module


def _run_old_test(case_id: str, driver):
    module = _load_case_module(case_id)
    func_name = f"test_{case_id}"
    if not hasattr(module, func_name):
        raise AttributeError(f"{case_id} module 中找不到函数 {func_name}")
    test_func = getattr(module, func_name)
    return test_func(driver)


# 试点用例：先迁移 3 个注册用例验证 runner 合并写报告是否通顺
CASES: List[Tuple[str, str, Callable]] = [
    ("102025", "验证注册时邮箱显示包含不支持的特殊字符", lambda driver: _run_old_test("102025", driver)),
    ("102205", "验证清空邮箱的“×”按钮，可以清空邮箱", lambda driver: _run_old_test("102205", driver)),
    # 该用例文件名以 102179 开头
    ("102179", "验证输入用户名名字超过50个字符，点击Submit按钮", lambda driver: _run_old_test("102179", driver)),
]

