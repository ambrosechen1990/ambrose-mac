import sys
import importlib.util
import logging
import re
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
import types

THIS_DIR = Path(__file__).resolve().parent  # .../平台/IOS/1登录
PLATFORM_DIR = THIS_DIR.parents[1]  # .../平台
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

# cases loader 仍会对「comman」做 monkeypatch；已取消 comman 包，用占位对象承接属性
comman = types.SimpleNamespace()


_EXCLUDED_CASE_FILES = {"__init__.py", "cases.py", "run_cases.py"}


def _extract_case_meta(case_file: Path) -> Tuple[str, str]:
    """
    从文件名提取 case_id 与描述。

    支持：
    - 102650验证登录页面到APP首页的"返回键".py
    - test_102648_email_case_insensitive.py
    """
    match = re.match(r"^(?:test_)?(?P<case_id>\d{6})(?P<desc>.*)$", case_file.stem)
    if not match:
        raise ValueError(f"不是可识别的用例文件名: {case_file.name}")

    case_id = match.group("case_id")
    case_desc = match.group("desc").lstrip("_- ").replace("_", " ").strip()
    if not case_desc:
        case_desc = case_file.stem
    return case_id, case_desc


def _discover_case_files(case_dir: Path) -> List[Path]:
    discovered: List[Tuple[str, Path]] = []
    seen_case_ids: Dict[str, Path] = {}

    for case_file in sorted(case_dir.glob("*.py")):
        if case_file.name in _EXCLUDED_CASE_FILES:
            continue
        try:
            case_id, _ = _extract_case_meta(case_file)
        except ValueError:
            continue

        if case_id in seen_case_ids:
            raise RuntimeError(
                f"发现重复 case_id={case_id}: {seen_case_ids[case_id].name} 和 {case_file.name}"
            )
        seen_case_ids[case_id] = case_file
        discovered.append((case_id, case_file))

    if not discovered:
        raise RuntimeError(f"在 {case_dir} 下未发现可执行的登录用例文件")

    discovered.sort(key=lambda item: item[0])
    return [case_file for _, case_file in discovered]


_CASE_MODULE_CACHE: Dict[str, object] = {}


def _load_case_module(case_file: Path, case_id: str):
    cache_key = str(case_file.resolve())
    if cache_key in _CASE_MODULE_CACHE:
        return _CASE_MODULE_CACHE[cache_key]

    orig_init_report = getattr(comman, "init_report", None)
    orig_bind_logger = getattr(comman, "bind_logger_to_print", None)
    orig_write_report = getattr(comman, "write_report", None)
    orig_save_failure_screenshot = getattr(comman, "save_failure_screenshot", None)

    class _DummyLogger(logging.Logger):
        def __init__(self):
            super().__init__("dummy")

    def _dummy_init_report(run_label: str = "ios"):
        return Path.cwd(), _DummyLogger(), run_label, "0"

    def _dummy(*args, **kwargs):
        return None

    try:
        comman.init_report = _dummy_init_report  # type: ignore
        comman.bind_logger_to_print = _dummy  # type: ignore
        comman.write_report = _dummy  # type: ignore
        comman.save_failure_screenshot = _dummy  # type: ignore

        module_name = f"cases_login_{case_id}"
        spec = importlib.util.spec_from_file_location(module_name, str(case_file))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载模块: {case_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        if orig_init_report is not None:
            comman.init_report = orig_init_report  # type: ignore
        if orig_bind_logger is not None:
            comman.bind_logger_to_print = orig_bind_logger  # type: ignore
        if orig_write_report is not None:
            comman.write_report = orig_write_report  # type: ignore
        if orig_save_failure_screenshot is not None:
            comman.save_failure_screenshot = orig_save_failure_screenshot  # type: ignore

    _CASE_MODULE_CACHE[cache_key] = module
    return module


def _run_old_test(case_file: Path, case_id: str, driver):
    module = _load_case_module(case_file, case_id)
    func_name = f"test_{case_id}"
    if not hasattr(module, func_name):
        raise AttributeError(f"{case_id} module 中找不到函数 {func_name}")
    test_func = getattr(module, func_name)
    return test_func(driver)


def _make_case_runner(case_file: Path, case_id: str):
    return lambda driver, _case_file=case_file, _case_id=case_id: _run_old_test(_case_file, _case_id, driver)


def _build_cases() -> List[Tuple[str, str, Callable]]:
    cases: List[Tuple[str, str, Callable]] = []
    for case_file in _discover_case_files(THIS_DIR):
        case_id, case_desc = _extract_case_meta(case_file)
        cases.append((case_id, case_desc, _make_case_runner(case_file, case_id)))
    return cases


CASES: List[Tuple[str, str, Callable]] = _build_cases()

