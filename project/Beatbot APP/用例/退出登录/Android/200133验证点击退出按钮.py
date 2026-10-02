# -*- coding: utf-8 -*-
"""
200133 验证点击退出按钮（Android / 5退出登录）

流程：
  1. 重启 APP
  2. 检查是否已登录；未登录则登录；已登录则进入步骤 3
  3. 点击 More → 设置页
  4. 点击 edit → 账号与安全页
  5. 点击 Log Out → 断言确认弹窗「Are you sure you want to log out?」
"""
import os
import sys
import time
import traceback
from pathlib import Path

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

_cur = Path(__file__).resolve().parent
_shared = None
for _ in range(24):
    _cand = _cur / "common"
    if _cand.is_dir() and (_cand / "common_utils_Android共用.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 Beatbot APP/common（需包含 common_utils_Android共用.py）")

from common_utils_Android共用 import (  # noqa: E402
    bind_logger_to_print,
    init_report,
    save_failure_screenshot,
    write_report,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

APP_PACKAGE = os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
LOGIN_EMAIL = os.environ.get("LOGIN_EMAIL", "haoc51888@gmail.com")
LOGIN_PASSWORD = os.environ.get("LOGIN_OK_PASSWORD", "Csx150128")

CASE_ID = "200133"
CASE_DESC = "200133 验证点击退出按钮"
LOGOUT_CONFIRM_TEXT = os.environ.get(
    "ANDROID_LOGOUT_CONFIRM_TEXT", "Are you sure you want to log out?"
)

# ---------- 元素定位 ----------
XPATH_MORE = '//android.view.View[@content-desc="More"]'
XPATH_MORE_ALT = '//*[@content-desc="More"]'
XPATH_LOGGED_IN_MORE = '//*[@content-desc="More"] | //android.view.View[@content-desc="More"]'
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)
XPATH_SIGN_IN = '//android.widget.TextView[@text="Sign In"]'
XPATH_SIGN_IN_FALLBACK = '//*[@text="Sign In"]'
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
XPATH_EMAIL_FOCUS = "//android.widget.ScrollView/android.widget.EditText[1]/android.view.View[2]"
XPATH_PASSWORD = "//android.widget.ScrollView/android.widget.EditText[2]"
XPATH_PASSWORD_FOCUS = "//android.widget.ScrollView/android.widget.EditText[2]/android.view.View[2]"
XPATH_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
XPATH_NEXT = '//android.widget.ImageView[@content-desc="next"]'
XPATH_EDIT = '//android.widget.ImageView[@content-desc="edit"]'
XPATH_LOG_OUT = '//android.widget.TextView[@text="Log Out"]'
XPATH_LOGOUT_CONFIRM = f'//android.widget.TextView[@text="{LOGOUT_CONFIRM_TEXT}"]'


def _make_driver():
    appium_url = os.environ.get("APPIUM_URL", os.environ.get("APPIUM_SERVER_URL", "http://localhost:4730"))
    options = UiAutomator2Options()
    options.platform_name = os.environ.get("ANDROID_PLATFORM_NAME", "Android")
    options.platform_version = os.environ.get("ANDROID_PLATFORM_VERSION", "15")
    options.device_name = os.environ.get("ANDROID_DEVICE_NAME", "Android Device")
    options.automation_name = "UiAutomator2"
    options.app_package = APP_PACKAGE
    app_activity = os.environ.get("ANDROID_APP_ACTIVITY", "").strip()
    if app_activity:
        options.app_activity = app_activity
    options.new_command_timeout = 3600
    options.no_reset = True
    options.full_reset = False
    return webdriver.Remote(command_executor=appium_url, options=options)


def _is_logged_in(driver) -> bool:
    driver.implicitly_wait(0)
    try:
        for xp in (XPATH_MORE, XPATH_MORE_ALT):
            for elem in driver.find_elements(AppiumBy.XPATH, xp):
                if elem.is_displayed():
                    print(f"    ✅ 检测到已登录: {xp}")
                    return True
    finally:
        driver.implicitly_wait(5)
    return False


def _restart_app(driver) -> None:
    try:
        driver.terminate_app(APP_PACKAGE)
    except Exception:
        pass
    time.sleep(1.5)
    driver.activate_app(APP_PACKAGE)
    time.sleep(3.0)
    print("    ✅ APP 已重启")


def _perform_android_login(driver) -> None:
    """未登录时执行登录（对齐 200015 / 200129）。"""
    sign_in_btn = None
    last_err = None
    for xp in (XPATH_SIGN_IN, XPATH_SIGN_IN_FALLBACK):
        try:
            sign_in_btn = WebDriverWait(driver, 18).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            break
        except Exception as e:
            last_err = e
    if sign_in_btn is None:
        raise TimeoutException(f"未找到 Sign In: {last_err}")

    sign_in_btn.click()
    time.sleep(1.5)

    for focus_xp in (XPATH_EMAIL_FOCUS, XPATH_EMAIL):
        try:
            driver.find_element(AppiumBy.XPATH, focus_xp).click()
            break
        except Exception:
            continue
    email_el = WebDriverWait(driver, 18).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_EMAIL))
    )
    try:
        email_el.clear()
    except Exception:
        pass
    email_el.send_keys(LOGIN_EMAIL)
    time.sleep(0.3)

    for focus_xp in (XPATH_PASSWORD_FOCUS, XPATH_PASSWORD):
        try:
            driver.find_element(AppiumBy.XPATH, focus_xp).click()
            break
        except Exception:
            continue
    pwd_el = WebDriverWait(driver, 18).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_PASSWORD))
    )
    try:
        pwd_el.clear()
    except Exception:
        pass
    pwd_el.send_keys(LOGIN_PASSWORD)
    time.sleep(0.3)

    try:
        driver.hide_keyboard()
    except Exception:
        size = driver.get_window_size()
        driver.tap([(int(size["width"] * 0.5), int(size["height"] * 0.12))])  # type: ignore[attr-defined]

    cb = WebDriverWait(driver, 18).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_CHECKBOX))
    )
    cb.click()
    time.sleep(0.4)

    nxt = WebDriverWait(driver, 18).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_NEXT))
    )
    nxt.click()
    time.sleep(1.2)

    timeout_s = int(os.environ.get("LOGIN_SUCCESS_TIMEOUT_S", "45"))
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LOGGED_IN_MORE))
    )
    print("    ✅ 登录成功（More 可见）")


def _click_more(driver) -> None:
    """步骤3：点击 More 进入设置页。"""
    last_err = None
    for xp in (XPATH_MORE, XPATH_MORE_ALT):
        try:
            btn = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            btn.click()
            print(f"    ✅ 已点击 More: {xp}")
            time.sleep(2.0)
            return
        except Exception as e:
            last_err = e
    raise AssertionError(f"未找到 More 按钮: {last_err}")


def _click_edit(driver) -> None:
    """步骤4：点击 edit 进入账号与安全页。"""
    edit_btn = WebDriverWait(driver, 12).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_EDIT))
    )
    edit_btn.click()
    print("    ✅ 已点击 edit，进入账号与安全页")
    time.sleep(2.0)


def _click_log_out(driver) -> None:
    """步骤5：点击 Log Out。"""
    logout_btn = WebDriverWait(driver, 12).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_LOG_OUT))
    )
    logout_btn.click()
    print("    ✅ 已点击 Log Out")
    time.sleep(1.5)


def _assert_logout_confirm_dialog(driver) -> None:
    """步骤5 断言：退出确认弹窗文案可见。"""
    confirm_el = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LOGOUT_CONFIRM))
    )
    assert confirm_el.is_displayed(), f"确认文案不可见: {LOGOUT_CONFIRM_TEXT}"
    print(f"    ✅ 退出确认弹窗已显示: {LOGOUT_CONFIRM_TEXT}")


@pytest.fixture(scope="function")
def setup_driver():
    driver = _make_driver()
    driver.implicitly_wait(5)
    try:
        yield driver
    finally:
        driver.quit()


def test_200133(setup_driver):
    """
    200133 验证点击退出按钮

    1. 重启 APP
    2. 检查登录；未登录则登录
    3. More → 设置页
    4. edit → 账号与安全页
    5. Log Out → 断言确认弹窗
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
            print("    🔄 未登录，执行登录…")
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY))
            )
            _perform_android_login(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤3: 点击 More 进入设置页"
        print(f"🔄 {current_step}")
        _click_more(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 点击 edit 进入账号与安全页"
        print(f"🔄 {current_step}")
        _click_edit(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤5: 点击 Log Out 并断言确认弹窗"
        print(f"🔄 {current_step}")
        _click_log_out(driver)
        _assert_logout_confirm_dialog(driver)
        print(f"✅ {current_step} - 完成")

        print(f"🎉 测试用例 {CASE_ID} 执行成功！")

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {e}"
        print(f"\n{'=' * 60}")
        print(f"❌ 测试失败")
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
            platform="android",
            case_id=CASE_ID,
            case_desc=CASE_DESC,
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
