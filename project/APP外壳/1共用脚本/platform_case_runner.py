"""
平台功能用例总调度器。

主要用途：
- 递归发现 3功能/1平台 下的测试脚本
- 为 iOS / Android 提供统一执行入口
- 生成聚合日志、总报告和汇总 sheet
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from report_utils import (
    append_case_to_aggregate_report,
    append_case_to_summary_report,
    bind_logger_to_print,
    init_report,
)
from screenshot_utils import save_failure_screenshot


SHARED_DIR = Path(__file__).resolve().parent
APP_SHELL_ROOT = SHARED_DIR.parent
PLATFORM_ROOT = APP_SHELL_ROOT / "3功能" / "1平台"

if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

CASE_FILE_RE = re.compile(r"^(?:test_)?(?P<case_id>\d{6})(?P<desc>.*)$")
EXCLUDED_FILES = {"run_cases.py", "cases.py", "__init__.py", "conftest.py"}
CASE_MODULE_CACHE: dict[tuple[str, str], object] = {}

PLATFORM_CONFIG = {
    "ios": {
        "dir_name": "IOS",
        "platform_name": "ios",
        "common_module": "common_utils",
        "run_label": "ios_platform",
    },
    "android": {
        "dir_name": "Android",
        "platform_name": "android",
        "common_module": "common_utils_android",
        "run_label": "android_platform",
    },
}


def _extract_case_meta(case_file: Path) -> tuple[str, str]:
    match = CASE_FILE_RE.match(case_file.stem)
    if not match:
        raise ValueError(f"不是可识别的用例文件: {case_file.name}")

    case_id = match.group("case_id")
    case_desc = match.group("desc").lstrip("_- ").replace("_", " ").strip()
    if not case_desc:
        case_desc = case_file.stem
    return case_id, case_desc


def _discover_case_files(case_root: Path) -> list[Path]:
    discovered: list[tuple[str, str, Path]] = []
    seen_case_ids: dict[str, Path] = {}

    for case_file in sorted(case_root.rglob("*.py")):
        if case_file.name in EXCLUDED_FILES:
            continue
        try:
            case_id, _ = _extract_case_meta(case_file)
        except ValueError:
            continue

        if case_id in seen_case_ids:
            raise RuntimeError(
                f"发现重复 case_id={case_id}: {seen_case_ids[case_id].relative_to(case_root)} "
                f"和 {case_file.relative_to(case_root)}"
            )
        seen_case_ids[case_id] = case_file
        discovered.append((case_id, str(case_file.relative_to(case_root)), case_file))

    if not discovered:
        raise RuntimeError(f"在 {case_root} 下未发现可执行的用例文件")

    discovered.sort(key=lambda item: (item[0], item[1]))
    return [case_file for _, _, case_file in discovered]


def _patch_case_module_dependencies(common_module_name: str):
    common_utils = importlib.import_module(common_module_name)

    class _DummyLogger(logging.Logger):
        def __init__(self):
            super().__init__("dummy")

    def _dummy_init_report(run_label: str = "platform"):
        return Path.cwd(), _DummyLogger(), run_label, "0"

    def _dummy(*args, **kwargs):
        return None

    patch_names = [
        "init_report",
        "bind_logger_to_print",
        "write_report",
        "save_failure_screenshot",
    ]
    originals = {name: getattr(common_utils, name, None) for name in patch_names}
    common_utils.init_report = _dummy_init_report  # type: ignore[attr-defined]
    common_utils.bind_logger_to_print = _dummy  # type: ignore[attr-defined]
    common_utils.write_report = _dummy  # type: ignore[attr-defined]
    common_utils.save_failure_screenshot = _dummy  # type: ignore[attr-defined]
    return common_utils, originals


def _restore_case_module_dependencies(common_utils, originals):
    for name, value in originals.items():
        if value is not None:
            setattr(common_utils, name, value)


def _load_case_module(case_file: Path, common_module_name: str):
    cache_key = (common_module_name, str(case_file.resolve()))
    if cache_key in CASE_MODULE_CACHE:
        return CASE_MODULE_CACHE[cache_key]

    common_utils, originals = _patch_case_module_dependencies(common_module_name)
    try:
        rel_name = re.sub(r"[^0-9A-Za-z_]+", "_", str(case_file.relative_to(APP_SHELL_ROOT)))
        module_name = f"platform_suite_{rel_name}"
        spec = importlib.util.spec_from_file_location(module_name, str(case_file))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载模块: {case_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        _restore_case_module_dependencies(common_utils, originals)

    CASE_MODULE_CACHE[cache_key] = module
    return module


def _resolve_test_function(module, case_id: str, case_file: Path):
    preferred_name = f"test_{case_id}"
    if hasattr(module, preferred_name):
        return getattr(module, preferred_name)

    test_functions = [
        func
        for name, func in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("test_") and getattr(func, "__module__", None) == module.__name__
    ]
    if len(test_functions) == 1:
        return test_functions[0]
    if not test_functions:
        raise AttributeError(f"{case_file.name} 中找不到 test_ 开头的测试函数")
    raise AttributeError(f"{case_file.name} 中存在多个 test_ 函数，无法自动判断要执行哪一个")


def _make_driver(platform_key: str):
    if platform_key == "ios":
        from appium import webdriver
        from appium.options.ios import XCUITestOptions

        options = XCUITestOptions()
        options.platform_name = "iOS"
        options.platform_version = os.environ.get("IOS_PLATFORM_VERSION", "18.5")
        options.device_name = os.environ.get("IOS_DEVICE_NAME", "iPhone 16 pro max")
        options.udid = os.environ.get("IOS_UDID", "00008140-00041C980A50801C")
        options.bundle_id = os.environ.get("IOS_BUNDLE_ID", "com.xingmai.tech")
        options.automation_name = "XCUITest"
        options.include_safari_in_webviews = True
        options.new_command_timeout = 3600
        options.connect_hardware_keyboard = True
        appium_url = os.environ.get("APPIUM_URL", "http://localhost:4736")
    elif platform_key == "android":
        from appium import webdriver
        from appium.options.android import UiAutomator2Options

        options = UiAutomator2Options()
        options.platform_name = os.environ.get("ANDROID_PLATFORM_NAME", "Android")
        options.platform_version = os.environ.get("ANDROID_PLATFORM_VERSION", "15")
        options.device_name = os.environ.get("ANDROID_DEVICE_NAME", "Android Device")
        options.automation_name = "UiAutomator2"
        options.app_package = os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
        options.new_command_timeout = 3600
        options.no_reset = True
        options.full_reset = False
        appium_url = os.environ.get("APPIUM_URL", "http://localhost:4730")
    else:
        raise ValueError(f"不支持的平台: {platform_key}")

    driver = webdriver.Remote(command_executor=appium_url, options=options)
    driver.implicitly_wait(5)
    return driver


def _build_case_name(case_root: Path, case_file: Path, case_id: str, case_desc: str) -> str:
    parent_label = str(case_file.parent.relative_to(case_root)).replace("\\", "/")
    if parent_label == ".":
        return f"{case_id} {case_desc}"
    return f"[{parent_label}] {case_id} {case_desc}"


def run_platform_suite(platform_key: str, run_label: str | None = None) -> int:
    if platform_key not in PLATFORM_CONFIG:
        raise ValueError(f"未知平台: {platform_key}")

    config = PLATFORM_CONFIG[platform_key]
    case_root = PLATFORM_ROOT / config["dir_name"]
    common_module_name = config["common_module"]
    run_label = run_label or os.environ.get("RUN_LABEL", config["run_label"])
    platform_name = config["platform_name"]

    case_files = _discover_case_files(case_root)
    run_dir, logger, run_label, run_ts = init_report(run_label)
    bind_logger_to_print(logger)

    print(f"开始执行 {platform_name} 平台功能用例，共 {len(case_files)} 条")
    print(f"报告目录: {run_dir}")

    failed_count = 0
    report_path = None
    summary_path = None

    for index, case_file in enumerate(case_files, start=1):
        case_id, case_desc = _extract_case_meta(case_file)
        case_name = _build_case_name(case_root, case_file, case_id, case_desc)
        start_time = datetime.now()
        result = "success"
        fail_reason = ""
        screenshot_path = ""
        driver = None

        print(f"[{index}/{len(case_files)}] 开始执行: {case_name}")
        try:
            driver = _make_driver(platform_key)
            module = _load_case_module(case_file, common_module_name)
            test_func = _resolve_test_function(module, case_id, case_file)
            test_func(driver)
            print(f"✅ 用例通过: {case_name}")
        except Exception as exc:
            result = "failed"
            failed_count += 1
            fail_reason = f"{type(exc).__name__}: {exc}"
            print(f"❌ 用例失败: {case_name} - {fail_reason}")
            logger.exception("用例执行异常: %s", case_name)
            if driver is not None:
                screenshot_path = save_failure_screenshot(
                    driver,
                    step_name=f"test_{case_id}_failed",
                    run_dir=run_dir,
                ) or ""
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception as quit_exc:
                    print(f"关闭驱动失败: {quit_exc}")

            test_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
            report_path = append_case_to_aggregate_report(
                run_dir=run_dir,
                run_label=run_label,
                run_ts=run_ts,
                platform=platform_name,
                case_name=case_name,
                result=result,
                fail_reason=fail_reason,
                screenshot_path=screenshot_path,
                test_time=test_time,
            )
            summary_path = append_case_to_summary_report(
                run_dir=run_dir,
                run_label=run_label,
                run_ts=run_ts,
                case_name=case_name,
                result=result,
                test_time=test_time,
            )

    passed_count = len(case_files) - failed_count
    print(
        f"执行完成：总计 {len(case_files)} 条，通过 {passed_count} 条，失败 {failed_count} 条"
    )
    if report_path:
        print(f"聚合报告: {report_path}")
    if summary_path:
        print(f"汇总报告: {summary_path}")

    return 0 if failed_count == 0 else 1
