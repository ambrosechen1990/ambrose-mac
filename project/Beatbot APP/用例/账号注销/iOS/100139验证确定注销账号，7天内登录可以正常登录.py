# -*- coding: utf-8 -*-
"""
100139 验证确定注销账号，7天内登录可以正常登录（iOS / 6账号注销）

流程：
  1. 重启 APP
  2. 检查是否已登录；未登录则调用登录流程
  3. 点击 mine → 设置页
  4. 点击 CommonEdit → 账号与安全页
  5. 点击 Account Deletion → 弹出确认框
  6. 点击 Confirm 确定注销
  7. 页面回到登录/注册入口，使用 haoc51888@gmail.com / Csx150128 登录
  8. 断言 mine 按钮存在（7 天内仍可正常登录）
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

LOGIN_INDICATORS = [
    '//XCUIElementTypeButton[@name="home sel"]',
    '//XCUIElementTypeButton[@name="mine sel"]',
    '//XCUIElementTypeButton[@name="mine"]',
]

ACCOUNT_DELETION_XPATH = '//XCUIElementTypeStaticText[@name="Account Deletion"]'
CONFIRM_BUTTON_XPATH = '//XCUIElementTypeButton[@name="Confirm"]'
MINE_BUTTON_XPATH = '//XCUIElementTypeButton[@name="mine"]'
SIGN_IN_XPATH = '//XCUIElementTypeButton[@name="Sign In"]'

CASE_ID = "100139"
CASE_DESC = "100139 验证确定注销账号，7天内登录可以正常登录"


def _wait_clickable(driver, xpath: str, timeout: float = 10):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, xpath))
    )


def _is_logged_in(driver) -> bool:
    for indicator in LOGIN_INDICATORS:
        try:
            for elem in driver.find_elements(AppiumBy.XPATH, indicator):
                if elem.is_displayed():
                    print(f"    ✅ 检测到已登录: {indicator}")
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
    print("    ✅ APP 已重启")


def _wait_for_bottom_mine_after_login(driver, timeout_s: float) -> None:
    candidates = [
        MINE_BUTTON_XPATH,
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
    raise AssertionError(f"{timeout_s}s 内未检测到底部 mine 按钮")


def _perform_ios_login(driver) -> None:
    """Sign In 登录（步骤2 未登录 / 步骤7 注销后重新登录）。"""
    sign_in_btn = _wait_clickable(driver, SIGN_IN_XPATH, timeout=15)
    sign_in_btn.click()
    time.sleep(1.5)

    email_input = resolve_sign_in_email_input(driver)
    email_input.clear()
    email_input.send_keys(LOGIN_EMAIL)
    time.sleep(0.8)

    password_input = resolve_sign_in_password_input(driver)
    password_input.clear()
    password_input.send_keys(LOGIN_PASSWORD)
    time.sleep(0.8)

    try:
        done_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
        )
        done_btn.click()
        time.sleep(0.8)
    except Exception:
        pass

    check_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="login check normal"]', timeout=8)
    check_btn.click()
    time.sleep(0.8)

    login_btn = WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'name == "login icon"'))
    )
    login_btn.click()
    time.sleep(float(os.environ.get("LOGIN_POST_CLICK_WAIT_S", "4")))

    _wait_for_bottom_mine_after_login(
        driver, timeout_s=float(os.environ.get("LOGIN_SUCCESS_TIMEOUT_S", "45"))
    )
    print(f"    ✅ 登录成功: {LOGIN_EMAIL}")


def _click_mine_tab(driver) -> None:
    """步骤3：点击 mine 进入设置页。"""
    for xp, desc in [
        (MINE_BUTTON_XPATH, "mine"),
        ('//XCUIElementTypeButton[@name="mine sel"]', "mine sel"),
    ]:
        try:
            btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            btn.click()
            print(f"    ✅ 已点击 {desc}，进入设置页")
            time.sleep(1.5)
            return
        except Exception:
            continue
    raise AssertionError("未找到 mine / mine sel 按钮")


def _click_common_edit(driver) -> None:
    """步骤4：点击 CommonEdit 进入账号与安全页。"""
    edit_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="CommonEdit"]', timeout=12)
    edit_btn.click()
    time.sleep(1.5)
    print("    ✅ 已点击 CommonEdit，进入账号与安全页")


def _click_account_deletion(driver) -> None:
    """步骤5：点击 Account Deletion。"""
    el = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, ACCOUNT_DELETION_XPATH))
    )
    assert el.is_displayed(), "Account Deletion 不可见"
    try:
        el.click()
    except Exception:
        rect = el.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
    time.sleep(1.0)
    print("    ✅ 已点击 Account Deletion")


def _click_confirm_on_dialog(driver) -> None:
    """步骤6：点击 Confirm 确定注销。"""
    confirm_btn = _wait_clickable(driver, CONFIRM_BUTTON_XPATH, timeout=12)
    confirm_btn.click()
    time.sleep(float(os.environ.get("DEACTIVATE_CONFIRM_WAIT_S", "3")))
    print("    ✅ 已点击 Confirm")


def _wait_for_landing_or_sign_in(driver, timeout_s: float = 25) -> None:
    """步骤7 前：等待回到登录/注册入口（Sign In 可见）。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            for el in driver.find_elements(AppiumBy.XPATH, SIGN_IN_XPATH):
                if el.is_displayed():
                    print("    ✅ 已回到登录/注册入口页（Sign In 可见）")
                    return
        except Exception:
            pass
        time.sleep(0.8)
    raise AssertionError(f"{timeout_s}s 内未回到登录/注册入口页")


def _assert_mine_visible(driver) -> None:
    """步骤7 断言：登录后 mine 按钮存在。"""
    mine_btn = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, MINE_BUTTON_XPATH))
    )
    assert mine_btn.is_displayed(), "mine 按钮不可见，登录可能失败"
    print("    ✅ 断言通过：mine 按钮存在，7 天内可正常登录")


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


def test_100139(setup_driver):
    """
    100139 验证确定注销账号，7天内登录可以正常登录

    1. 重启 APP
    2. 检查登录；未登录则登录
    3–5. mine → CommonEdit → Account Deletion
    6. Confirm 确定注销
    7. 重新登录并断言 mine
    """
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
            print("    ℹ️ 已登录，进入步骤3")
        else:
            print("    🔄 未登录，执行登录流程…")
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

        current_step = "步骤5: 点击 Account Deletion"
        print(f"🔄 {current_step}")
        _click_account_deletion(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 点击 Confirm 确定注销"
        print(f"🔄 {current_step}")
        _click_confirm_on_dialog(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 注销后重新登录并断言 mine"
        print(f"🔄 {current_step}")
        _wait_for_landing_or_sign_in(driver)
        print(f"    🔄 使用账号 {LOGIN_EMAIL} 重新登录…")
        _perform_ios_login(driver)
        _assert_mine_visible(driver)
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
