# -*- coding: utf-8 -*-
"""
100142 验证重新发送验证码后，上次的验证码会失效，会提示重填（iOS / 7忘记密码）

流程：
  1. 重启 APP
  2. 检查是否已登录；未登录则调用登录流程
  3. 点击 mine → 设置页
  4. 点击 CommonEdit → 账号与安全页
  5. 点击 Password → 修改密码页
  6. 点击 Get Verification Code → 验证码输入页
  7. Gmail 获取验证码 code1，回到验证码页等待 40s
  8. 点击 Resend，输入旧验证码 code1
  9. 断言：Verification code error, please re-enter
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
from gmail_otp_utils_iOS验证码 import get_gmail_verification_code  # noqa: E402
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
RESEND_SELECTORS = [
    (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Resend"]'),
    (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Resend")]'),
]
ERR_OTP = os.environ.get(
    "OTP_ERROR_TIP", "Verification code error, please re-enter"
)
ERR_OTP_XPATH = f'//XCUIElementTypeStaticText[@name="{ERR_OTP}"]'

CASE_ID = "100142"
CASE_DESC = "100142 验证重新发送验证码后，上次的验证码会失效，会提示重填"


def _click_with_tap_fallback(driver, selectors, timeout_each: int = 8):
    elem = None
    for by, sel in selectors:
        try:
            cand = WebDriverWait(driver, timeout_each).until(
                EC.presence_of_element_located((by, sel))
            )
            if cand and cand.is_displayed():
                elem = cand
                break
        except Exception:
            continue
    if elem is None:
        raise TimeoutException("未找到可点击元素")
    try:
        elem.click()
    except Exception:
        rect = elem.rect or {}
        driver.execute_script(
            "mobile: tap",
            {
                "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
            },
        )


def _dismiss_keyboard(driver) -> None:
    try:
        for b in driver.find_elements(
            AppiumBy.XPATH,
            '//XCUIElementTypeButton[@name="Done" or @label="Done" or @name="完成"]',
        ):
            if b.is_displayed() and b.is_enabled():
                b.click()
                time.sleep(0.4)
                return
    except Exception:
        pass
    try:
        driver.hide_keyboard()
    except Exception:
        pass


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
        EC.element_to_be_clickable(
            (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]')
        )
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
    assert el.is_displayed()
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
    time.sleep(1.5)
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
        for by, sel in RESEND_SELECTORS:
            try:
                for e in d.find_elements(by, sel):
                    if e.is_displayed():
                        return True
            except Exception:
                continue
        return False

    WebDriverWait(driver, timeout).until(_ok)
    print("    ✅ 已在验证码输入页")


def _ensure_on_verification_page(driver) -> None:
    try:
        driver.activate_app(BUNDLE_ID)
    except Exception:
        pass
    time.sleep(1.5)
    _assert_on_verification_page(driver, timeout=15)


def _type_verification_code(driver, code: str, timeout: int = 12) -> None:
    candidates = []
    try:
        candidates = driver.find_elements(
            AppiumBy.IOS_PREDICATE,
            'type == "XCUIElementTypeTextField" OR type == "XCUIElementTypeTextView"',
        )
    except Exception:
        pass

    target = None
    for e in candidates:
        try:
            if e.is_displayed():
                target = e
                break
        except Exception:
            continue
    if target is None:
        raise TimeoutException("未找到验证码输入框")

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


def _click_resend_when_ready(driver) -> None:
    """点击 Resend（步骤7 已等待 40s 后调用，此处仅轮询可点击）。"""
    max_wait = int(os.environ.get("WAIT_RESEND_MAX_S", "75"))
    print(f"    ⏳ 等待 Resend 可点击（最多 {max_wait}s）...")
    try:
        driver.activate_app(BUNDLE_ID)
    except Exception:
        pass
    _click_with_tap_fallback(driver, RESEND_SELECTORS, timeout_each=max_wait)
    time.sleep(1.5)
    print("    ✅ 已点击 Resend")


def _wait_for_error_tip(driver, timeout_s: int = 15) -> None:
    esc = ERR_OTP.replace('"', '\\"')
    pred = (
        '(type == "XCUIElementTypeStaticText" OR type == "XCUIElementTypeTextView") AND '
        f'(name == "{esc}" OR name CONTAINS "{esc}" OR label CONTAINS "{esc}" OR value CONTAINS "{esc}")'
    )
    try:
        el = WebDriverWait(driver, timeout_s).until(
            EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, pred))
        )
        assert el.is_displayed()
        print(f"    ✅ 已出现错误提示: {ERR_OTP}")
        return
    except Exception:
        pass

    el = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, ERR_OTP_XPATH))
    )
    assert el.is_displayed()
    print(f"    ✅ 已出现错误提示: {ERR_OTP_XPATH}")


def _submit_or_wait_autovalidation(driver, wait_s: int = 12) -> None:
    """验证码页可能无提交按钮，输入 6 位后自动校验。"""
    submit_selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Verify"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Submit"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Confirm"]'),
    ]
    for by, sel in submit_selectors:
        try:
            for e in driver.find_elements(by, sel):
                if e.is_displayed() and e.is_enabled():
                    e.click()
                    time.sleep(1.0)
                    return
        except Exception:
            continue
    time.sleep(wait_s)


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


def test_100142(setup_driver):
    """
    100142 验证重新发送验证码后，上次的验证码会失效，会提示重填

    已登录路径：mine → CommonEdit → Password → Get Verification Code
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    code1 = ""

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

        current_step = "步骤7: Gmail 获取验证码并等待 40s"
        print(f"🔄 {current_step}")
        code1 = get_gmail_verification_code(
            driver=driver,
            method=os.environ.get("GMAIL_CODE_METHOD", "app"),
            subject_contains=os.environ.get(
                "GMAIL_SUBJECT_CONTAINS", "Beatbot Verification Code"
            ),
            from_contains=os.environ.get("GMAIL_FROM_CONTAINS", "noreply"),
            timeout_s=int(os.environ.get("GMAIL_TIMEOUT_S", "90")),
            gmail_bundle_id=os.environ.get("GMAIL_BUNDLE_ID", "com.google.Gmail"),
            kill_gmail_after=True,
        )
        _ensure_on_verification_page(driver)
        wait_s = int(os.environ.get("WAIT_BEFORE_RESEND_S", "40"))
        print(f"    ⏳ 在验证码页等待 {wait_s}s…")
        time.sleep(wait_s)
        print(f"✅ {current_step} - 完成，code1: {code1}")

        current_step = "步骤8: 点击 Resend 并输入旧验证码"
        print(f"🔄 {current_step}")
        _click_resend_when_ready(driver)
        _ensure_on_verification_page(driver)
        _type_verification_code(driver, code1)
        _submit_or_wait_autovalidation(
            driver, wait_s=int(os.environ.get("STEP8_WAIT_S", "12"))
        )
        print(f"✅ {current_step} - 完成")

        current_step = "步骤9: 断言验证码错误提示"
        print(f"🔄 {current_step}")
        _wait_for_error_tip(driver, timeout_s=20)
        print(f"✅ {current_step} - 完成")

        print(f"🎉 测试用例 {CASE_ID} 执行成功！")
        print("✅ 重新发送验证码后，旧验证码失效并提示重填")

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
