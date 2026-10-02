# -*- coding: utf-8 -*-
"""
100148 验证从输入验证码页面返回修改密码页，60S再进入“输入验证码”页面，需要重发验证码，且倒计时重置（iOS / 7忘记密码）

进入步骤参考流程图（已登录路径）：
  1. 重启 APP
  2. 检查是否已登录；未登录则调用登录流程
  3. 点击 mine → 设置页
  4. 点击 CommonEdit → 账号与安全页
  5. 点击 Password → change password 页
  6. 点击 Get Verification Code → 验证码页
  7. 左上角返回（nav back），回到 change password 页，等待 60s
  8. 再次点击 Get Verification Code，断言 Resend 倒计时重置（接近 60s，如 Resend(55s)）

后续倒计时解析与断言参考 100102。
"""

import os
import re
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

CASE_ID = "100148"
CASE_DESC = "100148 验证返回后60S再进入验证码页需重发且倒计时重置"


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
        try:
            resends = d.find_elements(
                AppiumBy.IOS_PREDICATE,
                '(type == "XCUIElementTypeButton" OR type == "XCUIElementTypeStaticText") AND '
                '(name CONTAINS "Resend" OR label CONTAINS "Resend" OR value CONTAINS "Resend" OR '
                'name CONTAINS "重新发送" OR label CONTAINS "重新发送" OR value CONTAINS "重新发送")',
            )
        except Exception:
            resends = []
        for e in resends:
            try:
                if e.is_displayed():
                    return True
            except Exception:
                continue
        return False

    WebDriverWait(driver, timeout).until(_ok)
    print("    ✅ 已在验证码页")


def _click_nav_back(driver) -> None:
    """
    左上角返回（流程图给定元素：nav back）。
    若 click 失败则坐标 tap。
    """
    candidates = [
        (AppiumBy.ACCESSIBILITY_ID, "nav back"),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="nav back"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"nav back")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeNavigationBar//XCUIElementTypeButton[1]'),
        (
            AppiumBy.IOS_PREDICATE,
            'type == "XCUIElementTypeButton" AND (name == "nav back" OR name CONTAINS "back" OR name CONTAINS "Back")',
        ),
    ]
    last_err = None
    for by, sel in candidates:
        try:
            el = WebDriverWait(driver, 6).until(EC.presence_of_element_located((by, sel)))
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
            print(f"    ✅ 已点击返回: {by} / {sel}")
            return
        except Exception as e:
            last_err = e
    # 最后兜底：屏幕左上角
    size = driver.get_window_size()
    tap_x = int(size["width"] * float(os.environ.get("IOS_BACK_TAP_X_RATIO", "0.08")))
    tap_y = int(size["height"] * float(os.environ.get("IOS_BACK_TAP_Y_RATIO", "0.10")))
    driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
    time.sleep(1.5)
    print(f"    ✅ 左上角坐标返回兜底: ({tap_x}, {tap_y}); last={last_err}")


def _assert_on_change_password_page(driver, timeout: int = 15) -> None:
    """
    返回后应在 change password 页：至少能看到 Get Verification Code 按钮。
    """
    el = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((AppiumBy.XPATH, GET_CODE_BUTTON_XPATH))
    )
    assert el.is_displayed(), "未回到 change password 页（Get Verification Code 不可见）"
    print("    ✅ 已回到 change password 页")


def _get_resend_seconds(driver):
    """
    从 Resend 文案中提取倒计时秒数。不同版本可能：
    - Resend(56s)
    - Resend 56s / Resend in 56s
    - 重新发送(56) 等
    """
    pred = (
        '(type == "XCUIElementTypeButton" OR type == "XCUIElementTypeStaticText") AND '
        '(name CONTAINS "Resend" OR label CONTAINS "Resend" OR value CONTAINS "Resend" OR '
        'name CONTAINS "重新发送" OR label CONTAINS "重新发送" OR value CONTAINS "重新发送")'
    )
    try:
        elems = driver.find_elements(AppiumBy.IOS_PREDICATE, pred)
    except Exception:
        elems = []
    for e in elems:
        try:
            if not e.is_displayed():
                continue
            t = (
                e.get_attribute("name")
                or e.get_attribute("label")
                or e.get_attribute("value")
                or ""
            ).strip()
            if not t:
                continue
            m = re.search(r"(\d{1,3})\s*s", t)
            if not m:
                m = re.search(r"\((\d{1,3})", t)
            if not m:
                m = re.search(r"\b(\d{1,3})\b", t)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None


def _wait_resend_countdown_reset(driver, timeout_s: int = 20, min_expected_s: int = 45):
    """
    断言 Resend 倒计时重新开始（接近 60s）。
    """

    def _ok(d):
        sec = _get_resend_seconds(d)
        return sec is not None and sec >= min_expected_s

    WebDriverWait(driver, timeout_s).until(lambda d: _ok(d))
    return _get_resend_seconds(driver)


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


def test_100148(setup_driver):
    """
    100148 验证返回后60S再进入验证码页需重发且倒计时重置
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    wait_on_change_password_s = int(os.environ.get("WAIT_ON_CHANGE_PASSWORD_S", "60"))
    resend_reset_min_s = int(os.environ.get("RESEND_RESET_MIN_S", "45"))

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

        current_step = "步骤5: 点击 Password 进入 change password 页"
        print(f"🔄 {current_step}")
        _click_password_entry(driver)
        _assert_on_change_password_page(driver, timeout=15)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 点击 Get Verification Code 进入验证码页"
        print(f"🔄 {current_step}")
        _click_get_verification_code(driver)
        _assert_on_verification_page(driver, timeout=18)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 返回 change password 页并等待 60s"
        print(f"🔄 {current_step}")
        _click_nav_back(driver)
        _assert_on_change_password_page(driver, timeout=15)
        print(f"    ⏳ 在 change password 页等待 {wait_on_change_password_s}s…")
        time.sleep(wait_on_change_password_s)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤8: 再次进入验证码页并断言倒计时重置"
        print(f"🔄 {current_step}")
        _click_get_verification_code(driver)
        _assert_on_verification_page(driver, timeout=18)
        sec = _wait_resend_countdown_reset(
            driver,
            timeout_s=int(os.environ.get("RESEND_RESET_ASSERT_TIMEOUT_S", "20")),
            min_expected_s=resend_reset_min_s,
        )
        print(f"✅ {current_step} - 完成，当前倒计时约: {sec}s")

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

