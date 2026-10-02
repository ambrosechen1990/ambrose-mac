# -*- coding: utf-8 -*-
"""
200130 验证「账号所在地」按注册地显示 — 美国（Android / 4显示）

流程：
  1. 重启 APP
  2. 检查登录：未登录则登录；已登录则 logout_Android登出 登出后再登录
  3. 使用美国注册账号 haoc51888@gmail.com / Csx150128 登录
  4. 点击 More → 设置页；点击 edit → 账号与安全页
  5. 断言 Region 标签及「United States of America」显示
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
    check_and_logout,
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
EXPECTED_REGION_VALUE = os.environ.get(
    "ANDROID_EXPECTED_REGION", "United States of America"
)

CASE_ID = "200130"
CASE_DESC = '200130 验证「账号所在地」是根据账号注册地显示（美国）'

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
XPATH_REGION_LABEL = '//android.widget.TextView[@text="Region"]'
XPATH_REGION_VALUE = f'//android.widget.TextView[@text="{EXPECTED_REGION_VALUE}"]'


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
    """步骤3：Sign In 登录（对齐 200015）。"""
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
    print(f"    ✅ 已输入邮箱: {LOGIN_EMAIL}")

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


def _ensure_target_account_logged_in(driver) -> None:
    """
    步骤2：检查登录状态。
    - 未登录：直接登录目标账号
    - 已登录：调用 logout_Android登出（check_and_logout）登出后再登录
    """
    if _is_logged_in(driver):
        print("    🔄 已登录，执行 logout_Android登出 登出…")
        check_and_logout(driver)
        time.sleep(2)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY))
        )
    else:
        print("    ℹ️ 未登录，跳过登出")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY))
        )
    _perform_android_login(driver)


def _click_more(driver) -> None:
    """步骤4：点击 More 进入设置页。"""
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
    """步骤5：点击 edit 进入账号与安全页。"""
    edit_btn = WebDriverWait(driver, 12).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_EDIT))
    )
    edit_btn.click()
    print("    ✅ 已点击 edit")
    time.sleep(2.0)


def _assert_region_display(driver) -> None:
    """步骤5：断言 Region 标签及美国注册地文案。"""
    region_label = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_REGION_LABEL))
    )
    assert region_label.is_displayed(), "Region 标签不可见"
    print("    ✅ 页面显示: Region")

    region_value = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_REGION_VALUE))
    )
    assert region_value.is_displayed(), f"{EXPECTED_REGION_VALUE} 不可见"
    print(f"    ✅ 账号所在地显示: {EXPECTED_REGION_VALUE}")


@pytest.fixture(scope="function")
def setup_driver():
    driver = _make_driver()
    driver.implicitly_wait(5)
    try:
        yield driver
    finally:
        driver.quit()


def test_200130(setup_driver):
    """
    200130 验证「账号所在地」是根据账号注册地显示（美国）

    1. 重启 APP
    2. 检查登录；已登录则登出后重新登录目标账号
    3. haoc51888@gmail.com / Csx150128 登录
    4. More → edit
    5. 断言 Region + United States of America
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

        current_step = "步骤2: 检查登录并登录目标账号"
        print(f"🔄 {current_step}")
        _ensure_target_account_logged_in(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤3: 点击 More 进入设置页"
        print(f"🔄 {current_step}")
        _click_more(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 点击 edit 进入账号与安全页"
        print(f"🔄 {current_step}")
        _click_edit(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤5: 断言账号所在地（美国）"
        print(f"🔄 {current_step}")
        _assert_region_display(driver)
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
