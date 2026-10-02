# -*- coding: utf-8 -*-
"""
100146 验证错误验证码，会提示重填（iOS / 7忘记密码）

进入验证码页面参考 100144（已登录路径：mine → CommonEdit → Password → Get Verification Code）
后续操作参考 100100：输入错误验证码 111111，断言提示
  Verification code error, please re-enter
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

LOGIN_INDICATORS = [
    '//XCUIElementTypeButton[@name="home sel"]',
    '//XCUIElementTypeButton[@name="mine sel"]',
    '//XCUIElementTypeButton[@name="mine"]',
]

PASSWORD_ENTRY_XPATH = '//XCUIElementTypeStaticText[@name="Password"]'
GET_CODE_BUTTON_XPATH = '//XCUIElementTypeButton[@name="Get Verification Code"]'

CASE_ID = "100146"
CASE_DESC = "100146 验证错误验证码，会提示重填"


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
    deadline = time.monotonic() + timeout_s
    poll = float(os.environ.get("LOGIN_SUCCESS_POLL_S", "1.0"))
    while time.monotonic() < deadline:
        for xp in LOGIN_INDICATORS:
            try:
                for el in driver.find_elements(AppiumBy.XPATH, xp):
                    if el.is_displayed():
                        return
            except Exception:
                continue
        time.sleep(poll)
    raise AssertionError(f"{timeout_s}s 内未检测到底部 mine")


def _perform_ios_login(driver) -> None:
    sign_in_btn = WebDriverWait(driver, 12).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]'))
    )
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

    check_btn = WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'))
    )
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
    for xp, desc in [
        ('//XCUIElementTypeButton[@name="mine"]', "mine"),
        ('//XCUIElementTypeButton[@name="mine sel"]', "mine sel"),
    ]:
        try:
            btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            btn.click()
            print(f"    ✅ 已点击 {desc}")
            time.sleep(1.5)
            return
        except Exception:
            continue
    raise AssertionError("未找到 mine 按钮")


def _click_common_edit(driver) -> None:
    edit_btn = WebDriverWait(driver, 12).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="CommonEdit"]'))
    )
    edit_btn.click()
    time.sleep(1.5)
    print("    ✅ 已点击 CommonEdit")


def _click_password_entry(driver) -> None:
    el = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, PASSWORD_ENTRY_XPATH))
    )
    assert el.is_displayed(), "Password 入口不可见"
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
    print("    ✅ 已点击 Password")


def _click_get_verification_code(driver) -> None:
    btn = WebDriverWait(driver, 12).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, GET_CODE_BUTTON_XPATH))
    )
    btn.click()
    time.sleep(2.0)
    print("    ✅ 已点击 Get Verification Code")


def _assert_on_verification_page(driver, timeout: int = 18) -> None:
    def _ok(d):
        try:
            for e in d.find_elements(
                AppiumBy.IOS_PREDICATE,
                'type == "XCUIElementTypeTextField" OR type == "XCUIElementTypeTextView"',
            ):
                if e.is_displayed():
                    return True
        except Exception:
            pass
        return False

    WebDriverWait(driver, timeout).until(_ok)
    print("    ✅ 已在验证码页")


def _dismiss_keyboard(driver) -> None:
    try:
        for b in driver.find_elements(
            AppiumBy.XPATH,
            '//XCUIElementTypeButton[@name="Done" or @label="Done" or @name="完成" or @label="完成"]',
        ):
            if b.is_displayed() and b.is_enabled():
                b.click()
                time.sleep(0.4)
                return
    except Exception:
        pass
    try:
        driver.hide_keyboard()
        time.sleep(0.4)
    except Exception:
        pass


def _type_verification_code(driver, code: str, timeout: int = 12):
    candidates = []
    try:
        candidates = WebDriverWait(driver, timeout).until(
            lambda d: d.find_elements(
                AppiumBy.IOS_PREDICATE,
                'type == "XCUIElementTypeTextField" OR type == "XCUIElementTypeTextView"',
            )
        )
    except Exception:
        candidates = []

    target = None
    for e in candidates:
        try:
            if e.is_displayed():
                target = e
                break
        except Exception:
            continue

    if target is None:
        raise TimeoutException("未找到验证码输入框(TextField/TextView)")

    try:
        target.click()
    except Exception:
        rect = target.rect or {}
        driver.execute_script(
            "mobile: tap",
            {
                "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
            },
        )
    try:
        target.clear()
    except Exception:
        pass
    target.send_keys(code)
    time.sleep(0.6)
    _dismiss_keyboard(driver)


def _submit_verification_if_possible(driver):
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Verify"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Verify")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Submit"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Submit")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Continue"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Continue")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Confirm"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Confirm")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="Done"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="完成"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="完成"]'),
    ]
    for by, sel in selectors:
        try:
            elems = driver.find_elements(by, sel)
        except Exception:
            elems = []
        for e in elems:
            try:
                if e.is_displayed() and e.is_enabled():
                    try:
                        e.click()
                    except Exception:
                        rect = e.rect or {}
                        driver.execute_script(
                            "mobile: tap",
                            {
                                "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                                "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
                            },
                        )
                    return True
            except Exception:
                continue
    return False


def _wait_for_error_tip(driver, expected_error: str, timeout_s: int = 12):
    esc = expected_error.replace('"', '\\"')
    pred = (
        '(type == "XCUIElementTypeStaticText" OR type == "XCUIElementTypeTextView") AND '
        f'(name CONTAINS "{esc}" OR label CONTAINS "{esc}" OR value CONTAINS "{esc}")'
    )
    return WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, pred))
    )


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


def test_100146(setup_driver):
    """
    100146 验证错误验证码，会提示重填
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    wrong_code = os.environ.get("WRONG_OTP_CODE", "111111")
    expected_error = os.environ.get(
        "OTP_ERROR_TIP", "Verification code error, please re-enter"
    )

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

        current_step = "步骤5: 点击 Password"
        print(f"🔄 {current_step}")
        _click_password_entry(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 点击 Get Verification Code 进入验证码页"
        print(f"🔄 {current_step}")
        _click_get_verification_code(driver)
        _assert_on_verification_page(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 输入错误验证码并断言提示重填"
        print(f"🔄 {current_step}")
        _type_verification_code(driver, wrong_code, timeout=12)
        _submit_verification_if_possible(driver)
        _wait_for_error_tip(
            driver,
            expected_error=expected_error,
            timeout_s=int(os.environ.get("ERROR_TIP_TIMEOUT_S", "15")),
        )
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

