# -*- coding: utf-8 -*-
"""
100140 验证修改密码按钮（iOS / 7忘记密码）

流程：
  1. 重启 APP
  2. 检查是否已登录；未登录则调用登录流程
  3. 点击 mine → 设置页
  4. 点击 CommonEdit → 账号与安全页
  5. 点击 Password（修改密码入口）
  6. 断言页面已跳转（出现 Get Verification Code 按钮）
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

PASSWORD_ENTRY_XPATH = '//XCUIElementTypeStaticText[@name="Password"]'
GET_VERIFICATION_CODE_XPATH = '//XCUIElementTypeButton[@name="Get Verification Code"]'

CASE_ID = "100140"
CASE_DESC = "100140 验证修改密码按钮"


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
    raise AssertionError(f"{timeout_s}s 内未检测到底部 Mine Tab")


def _perform_ios_login(driver) -> None:
    sign_in_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="Sign In"]', timeout=12)
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
    print("    ✅ 登录成功")


def _click_mine_tab(driver) -> None:
    """步骤3：点击 mine 进入设置页。"""
    for xp, desc in [
        ('//XCUIElementTypeButton[@name="mine"]', "mine"),
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


def _click_password_entry(driver) -> None:
    """步骤5：点击 Password（修改密码入口，StaticText）。"""
    el = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, PASSWORD_ENTRY_XPATH))
    )
    assert el.is_displayed(), "Password 入口不可见"
    try:
        el.click()
    except Exception:
        rect = el.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
    time.sleep(1.5)
    print("    ✅ 已点击 Password")


def _assert_page_jumped(driver) -> None:
    """步骤6：断言已进入修改密码页，出现 Get Verification Code 按钮。"""
    timeout = float(os.environ.get("IOS_PAGE_JUMP_ASSERT_TIMEOUT_S", "15"))
    btn = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((AppiumBy.XPATH, GET_VERIFICATION_CODE_XPATH))
    )
    assert btn.is_displayed(), "Get Verification Code 按钮不可见"
    print(f"    ✅ 页面跳转成功，已找到: {GET_VERIFICATION_CODE_XPATH}")


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


def test_100140(setup_driver):
    """
    100140 验证修改密码按钮

    1. 重启 APP
    2. 检查登录；未登录则登录
    3. mine → 设置
    4. CommonEdit → 账号与安全
    5. Password → 修改密码流程
    6. 断言出现 Get Verification Code 按钮
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

        current_step = "步骤5: 点击 Password（修改密码）"
        print(f"🔄 {current_step}")
        _click_password_entry(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 断言页面跳转后出现 Get Verification Code"
        print(f"🔄 {current_step}")
        _assert_page_jumped(driver)
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
