# -*- coding: utf-8 -*-
"""
100187 验证点击泳池信息按钮（iOS / 9泳池信息）

参考流程（截图）：
  1. 重启 APP
  2. 检查是否已登录；未登录则登录
  3. 点击 mine → 设置页
  4. 点击 CommonEdit → 账号与安全页
  5. 点击泳池信息入口：(//XCUIElementTypeImage[@name="CommonArrow"])[3]
  6. 断言泳池信息页各字段可见
"""

import os
import sys
import time
import traceback
from pathlib import Path

import pytest
from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

_cur = Path(__file__).resolve().parent
_shared = None
for _ in range(24):
    _cand = _cur / "common"
    if _cand.is_dir() and (_cand / "common_utils_iOS共用.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 Beatbot APP/common（需包含 common_utils_iOS共用.py）")

from common_utils_iOS共用 import (  # noqa: E402
    bind_logger_to_print,
    init_report,
    save_failure_screenshot,
    write_report,
)
from ios_sign_in_helpers_登录辅助 import resolve_sign_in_email_input, resolve_sign_in_password_input

RUN_LABEL = os.environ.get("RUN_LABEL", "ios")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

LOGIN_EMAIL = os.environ.get("IOS_LOGIN_EMAIL", "haoc51888@gmail.com")
LOGIN_PASSWORD = os.environ.get("IOS_LOGIN_PASSWORD", "Csx150128")
BUNDLE_ID = os.environ.get("IOS_BUNDLE_ID", "com.xingmai.tech")

CASE_ID = "100187"
CASE_DESC = "100187 验证点击泳池信息按钮"

LOGIN_INDICATORS = [
    '//XCUIElementTypeButton[@name="home sel"]',
    '//XCUIElementTypeButton[@name="mine sel"]',
    '//XCUIElementTypeButton[@name="mine"]',
]

POOL_INFO_ENTRY_XPATH = '(//XCUIElementTypeImage[@name="CommonArrow"])[3]'

POOL_INFO_FIELD_LABELS = [
    "Pool Name",
    "Pool Material",
    "Sanitation System",
    "Pool Type",
    "Pool Shape",
    "Floor Shape",
    "Water Capacity",
    "Surface Area",
    "Maximum Depth",
    "Pool Amenities",
]


def _wait_clickable(driver, xpath: str, timeout: float = 10):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, xpath))
    )


def _is_logged_in(driver) -> bool:
    for xp in LOGIN_INDICATORS:
        try:
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return True
        except Exception:
            continue
    return False


def _restart_app(driver) -> None:
    caps = getattr(driver, "capabilities", {}) or {}
    bundle_id = caps.get("bundleId") or BUNDLE_ID
    driver.terminate_app(bundle_id)
    time.sleep(1.5)
    driver.activate_app(bundle_id)
    time.sleep(2)


def _wait_for_bottom_mine_after_login(driver, timeout_s: float) -> None:
    candidates = [
        '//XCUIElementTypeButton[@name="mine"]',
        '//XCUIElementTypeButton[@name="mine sel"]',
        '//XCUIElementTypeButton[contains(@name,"mine")]',
    ]
    deadline = time.monotonic() + timeout_s
    poll = float(os.environ.get("LOGIN_SUCCESS_POLL_S", "1.0"))
    while time.monotonic() < deadline:
        for xp in candidates:
            try:
                for el in driver.find_elements(AppiumBy.XPATH, xp):
                    if el.is_displayed():
                        return
            except Exception:
                continue
        time.sleep(poll)
    raise AssertionError(f"{timeout_s}s 内未检测到底部 mine")


def _perform_ios_login(driver) -> None:
    _wait_clickable(driver, '//XCUIElementTypeButton[@name="Sign In"]', timeout=12).click()
    time.sleep(1.5)

    email_input = resolve_sign_in_email_input(driver)
    email_input.clear()
    email_input.send_keys(LOGIN_EMAIL)
    time.sleep(0.6)

    pwd_input = resolve_sign_in_password_input(driver)
    pwd_input.clear()
    pwd_input.send_keys(LOGIN_PASSWORD)
    time.sleep(0.6)

    try:
        WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
        ).click()
        time.sleep(0.5)
    except Exception:
        pass

    _wait_clickable(driver, '//XCUIElementTypeButton[@name="login check normal"]', timeout=8).click()
    time.sleep(0.6)

    WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'name == "login icon"'))
    ).click()
    time.sleep(float(os.environ.get("LOGIN_POST_CLICK_WAIT_S", "4")))

    _wait_for_bottom_mine_after_login(
        driver, timeout_s=float(os.environ.get("LOGIN_SUCCESS_TIMEOUT_S", "45"))
    )


def _click_mine_tab(driver) -> None:
    for xp in (
        '//XCUIElementTypeButton[@name="mine"]',
        '//XCUIElementTypeButton[@name="mine sel"]',
    ):
        try:
            _wait_clickable(driver, xp, timeout=10).click()
            time.sleep(1.2)
            return
        except Exception:
            continue
    raise TimeoutException("未找到 mine 按钮")


def _click_common_edit(driver) -> None:
    _wait_clickable(driver, '//XCUIElementTypeButton[@name="CommonEdit"]', timeout=12).click()
    time.sleep(1.5)


def _click_pool_info_entry(driver) -> None:
    """点击账号与安全页第 3 个 CommonArrow，进入泳池信息页。"""
    candidates = [
        POOL_INFO_ENTRY_XPATH,
        '(//XCUIElementTypeImage[@name="CommonArrow"])[3]',
        (AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeImage[`name == "CommonArrow"`][3]'),
    ]
    last_err = None
    for item in candidates:
        try:
            if isinstance(item, tuple):
                by, sel = item
                el = WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((by, sel))
                )
            else:
                el = WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, item))
                )
            if not el.is_displayed():
                continue
            try:
                el.click()
            except Exception:
                rect = el.rect or {}
                driver.execute_script(
                    "mobile: tap",
                    {
                        "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                        "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
                    },
                )
            time.sleep(1.5)
            print(f"    ✅ 已点击泳池信息入口")
            return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到泳池信息入口 CommonArrow[3]: {last_err}")


def _assert_pool_info_page_fields(driver) -> None:
    """断言泳池信息页各字段标签均可见。"""
    missing = []
    for label in POOL_INFO_FIELD_LABELS:
        xp = f'//XCUIElementTypeStaticText[@name="{label}"]'
        try:
            el = WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                print(f"    ✅ 字段可见: {label}")
            else:
                missing.append(label)
        except Exception:
            missing.append(label)

    if missing:
        raise AssertionError(f"泳池信息页缺少字段: {', '.join(missing)}")
    print("    ✅ 泳池信息页全部字段均已显示")


@pytest.fixture(scope="function")
def setup_driver():
    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.platform_version = os.environ.get("IOS_PLATFORM_VERSION", "18.5")
    options.device_name = os.environ.get("IOS_DEVICE_NAME", "iPhone 16 pro max")
    options.automation_name = "XCUITest"
    options.udid = os.environ.get("IOS_UDID", "00008140-00041C980A50801C")
    options.bundle_id = BUNDLE_ID
    options.include_safari_in_webviews = True
    options.new_command_timeout = 3600
    options.connect_hardware_keyboard = True

    driver = webdriver.Remote(
        command_executor=os.environ.get("APPIUM_SERVER_URL", "http://localhost:4736"),
        options=options,
    )
    driver.implicitly_wait(5)
    yield driver
    if driver:
        driver.quit()


def test_100187(setup_driver):
    """100187 验证点击泳池信息按钮"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        current_step = "步骤1: 重启 APP"
        print(f"🔄 {current_step}")
        _restart_app(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤2: 检查登录状态，未登录则登录"
        print(f"🔄 {current_step}")
        if _is_logged_in(driver):
            print("    ℹ️ 已登录")
        else:
            _perform_ios_login(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤3: 点击 mine 进入设置页"
        print(f"🔄 {current_step}")
        _click_mine_tab(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 点击 CommonEdit 进入账号与安全页"
        print(f"🔄 {current_step}")
        _click_common_edit(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤5: 点击泳池信息按钮进入泳池信息页"
        print(f"🔄 {current_step}")
        _click_pool_info_entry(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 断言泳池信息页各字段可见"
        print(f"🔄 {current_step}")
        _assert_pool_info_page_fields(driver)
        print(f"✅ {current_step} - 完成")

        print(f"🎉 测试用例 {CASE_ID} 执行成功！")

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {e}"
        print(f"\n{'=' * 60}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, f"test_{CASE_ID}_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id=CASE_ID,
            case_desc=CASE_DESC,
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
