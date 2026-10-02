# -*- coding: utf-8 -*-
"""
100164 验证密码为大写字母+字符时，“完成”按钮不可点击（iOS / 7忘记密码）

前置步骤参考 100144（已登录改密路径）
Set Password 页断言参考 100120：大写字母+字符密码，Submit 不可点击
"""

import os
import sys
import time
import traceback
from pathlib import Path
from typing import Dict

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

CASE_ID = "100164"
CASE_DESC = "100164 验证密码为大写字母+字符时，“完成”按钮不可点击"

RULE_SPECIAL = (
    "• Supports special characters:! @ # $ % ^ & * ( ) - _ = + \\ | [ ] { } ; : / ? . , ~ > < `"
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


def _type_verification_code(driver, code: str, timeout: int = 12) -> None:
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
        raise TimeoutError("未找到验证码输入框(TextField/TextView)")

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


def _assert_on_set_password_page(driver, timeout_s: int = 20) -> None:
    pred = (
        '(type == "XCUIElementTypeStaticText" OR type == "XCUIElementTypeNavigationBar") AND '
        '(name CONTAINS "Set Password" OR label CONTAINS "Set Password" OR value CONTAINS "Set Password" OR '
        'name CONTAINS "设置密码" OR label CONTAINS "设置密码" OR value CONTAINS "设置密码")'
    )
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, pred))
    )
    print("    ✅ 已在 Set Password 页")


def _find_password_fields(driver, timeout_s: int = 12):
    pwd1 = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeSecureTextField[1]"))
    )
    pwd2 = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeSecureTextField[2]"))
    )
    return pwd1, pwd2


def _type_password_both_fields(driver, password: str) -> None:
    pwd1, pwd2 = _find_password_fields(driver, timeout_s=12)
    for field in (pwd1, pwd2):
        try:
            field.click()
        except Exception:
            rect = field.rect or {}
            driver.execute_script(
                "mobile: tap",
                {
                    "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                    "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
                },
            )
        try:
            field.clear()
        except Exception:
            pass
        field.send_keys(password)
        time.sleep(0.5)


def _find_submit_button(driver, timeout_s: int = 12):
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Submit"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Submit")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="完成"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="完成"]'),
    ]
    last_err = None
    for by, sel in selectors:
        try:
            e = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((by, sel))
            )
            if e and e.is_displayed():
                return e
        except Exception as ex:
            last_err = ex
    raise TimeoutException(f"未找到 Submit/完成 按钮: {last_err}")


def _assert_submit_disabled_or_no_effect(driver) -> None:
    btn = _find_submit_button(driver, timeout_s=12)
    try:
        enabled = btn.is_enabled()
    except Exception:
        enabled = True
    if enabled is False:
        print("    ✅ Submit/完成 is_enabled=False")
        return
    try:
        btn.click()
    except Exception:
        rect = btn.rect or {}
        driver.execute_script(
            "mobile: tap",
            {
                "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
            },
        )
    time.sleep(1.2)
    _assert_on_set_password_page(driver, timeout_s=8)
    print("    ✅ 点击 Submit 无效，仍停留在 Set Password 页")


def _check_password_rules(driver, expectations: Dict[str, str]) -> None:
    for rule_text, expect_color in expectations.items():
        sel = f'//XCUIElementTypeStaticText[@name="{rule_text}"]'
        rule_elem = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.XPATH, sel))
        )
        assert rule_elem.is_displayed(), f"规则提示未显示: {rule_text}"
        color_val = None
        if hasattr(rule_elem, "value_of_css_property"):
            try:
                color_val = rule_elem.value_of_css_property("color")
            except Exception:
                color_val = None
        print(f"    📝 规则提示: {rule_text} 颜色: {color_val or '未available'}")
        if not color_val:
            continue
        low = str(color_val).lower()
        if expect_color == "red":
            assert ("255" in color_val or "#ff" in low or "red" in low), f"期望红色但实际为 {color_val}"
        else:
            assert (
                "128" in color_val or "gray" in low or "grey" in low or "#8" in low
            ), f"期望灰色但实际为 {color_val}"


def _navigate_to_set_password_page(driver) -> str:
    if _is_logged_in(driver):
        print("    ℹ️ 已登录")
    else:
        _perform_ios_login(driver)
    _click_mine_tab(driver)
    _click_common_edit(driver)
    _click_password_entry(driver)
    _click_get_verification_code(driver)
    _assert_on_verification_page(driver, timeout=18)

    code = get_gmail_verification_code(
        driver=driver,
        method=os.environ.get("GMAIL_CODE_METHOD", "app"),
        subject_contains=os.environ.get("GMAIL_SUBJECT_CONTAINS", "Beatbot Verification Code"),
        from_contains=os.environ.get("GMAIL_FROM_CONTAINS", "noreply"),
        timeout_s=int(os.environ.get("GMAIL_TIMEOUT_S", "90")),
        gmail_bundle_id=os.environ.get("GMAIL_BUNDLE_ID", "com.google.Gmail"),
        kill_gmail_after=True,
    )
    try:
        driver.activate_app(BUNDLE_ID)
    except Exception:
        pass
    time.sleep(2.0)
    _assert_on_verification_page(driver, timeout=18)
    _type_verification_code(driver, code, timeout=12)
    _assert_on_set_password_page(
        driver, timeout_s=int(os.environ.get("SET_PASSWORD_TIMEOUT_S", "25"))
    )
    return code


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


def test_100164(setup_driver):
    """100164 验证密码为大写字母+字符时，“完成”按钮不可点击"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    password_value = os.environ.get("TEST_PASSWORD", "!@#*XINGMAI")
    expectations = {
        "• 6-20 characters": "gray",
        "• contains letters": "gray",
        "• contains numbers": "red",
        RULE_SPECIAL: "gray",
    }

    try:
        current_step = "步骤1: 重启 APP"
        print(f"🔄 {current_step}")
        _restart_app(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤2-7: 进入 Set Password 页（100144 路径 + Gmail）"
        print(f"🔄 {current_step}")
        code = _navigate_to_set_password_page(driver)
        print(f"✅ {current_step} - 完成，code: {code}")

        current_step = "步骤8: 输入大写字母+字符密码(两次)并收起键盘"
        print(f"🔄 {current_step}")
        _type_password_both_fields(driver, password_value)
        _dismiss_keyboard(driver)
        print(f"✅ {current_step} - 完成，password: {password_value}")

        current_step = "步骤9: 校验密码规则文案颜色（参考100120）"
        print(f"🔄 {current_step}")
        _check_password_rules(driver, expectations)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤10: 点击 Submit，断言不可完成修改密码"
        print(f"🔄 {current_step}")
        _assert_submit_disabled_or_no_effect(driver)
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
