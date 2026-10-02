"""
200120 验证密码为大写字母+字符时，“完成”按钮不可点击（Android）。

操作步骤（与流程图一致）：
  1. 重启 APP
  2. 检测是否已登录；已登录则 check_and_logout；未登录则确认在登录/注册入口页
  3. 点击 Sign In：//android.widget.TextView[@text="Sign In"]
  4. 点击 Forgot password：//android.widget.TextView[@text="Forgot password"]
  5. 输入邮箱 haoc51888@gmail.com，点击 Next 进入验证码页
  6. Gmail 获取最新验证码
  7. 输入验证码进入设置密码页；密码/确认密码均输入 CSX!@#（大写字母+特殊字符）；收起键盘；点击 Submit
  8. 断言仍停留在设置密码页（不可完成修改密码）
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
from gmail_otp_utils_Android验证码 import get_gmail_verification_code  # noqa: E402

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

APP_PKG = os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
FORGOT_EMAIL = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD_200120", "CSX!@#")

XPATH_MORE = '//android.view.View[@content-desc="More"]'
XPATH_MORE_ALT = '//*[@content-desc="More"]'
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)
XPATH_SIGN_IN = '//android.widget.TextView[@text="Sign In"]'
XPATH_SIGN_IN_FALLBACK = '//*[@text="Sign In"]'
XPATH_FORGOT_PASSWORD = '//android.widget.TextView[@text="Forgot password"]'
XPATH_FORGOT_PASSWORD_FALLBACK = '//*[contains(@text,"Forgot password")]'
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
XPATH_EMAIL_FALLBACK = "//android.widget.EditText"
XPATH_NEXT = "//android.widget.Button"
XPATH_CODE_INPUT = "//android.widget.EditText"
XPATH_PASSWORD = "//android.widget.EditText"
XPATH_SUBMIT = (
    '//*[@text="Submit" or @text="Done" or @text="完成" '
    'or contains(@text,"Submit") or contains(@text,"Done")]'
)
XPATH_VERIFICATION_TITLE = (
    '//*[@text="Verification code" or contains(@text,"Verification code") or contains(@text,"验证码")]'
)
XPATH_RESEND = '//*[contains(@text,"Resend") or contains(@text,"重新发送")]'


def _restart_app(driver) -> None:
    """步骤1：重启 APP。"""
    print(f"    🔄 重启 APP: {APP_PKG}")
    try:
        driver.terminate_app(APP_PKG)
    except Exception:
        pass
    time.sleep(1.5)
    driver.activate_app(APP_PKG)
    time.sleep(3.0)
    print("    ✅ APP 已重启")


def _ensure_landing_page(driver) -> None:
    """步骤2：检测登录态，已登录则登出，否则确认在入口页。"""
    is_logged_in = False
    driver.implicitly_wait(0)
    try:
        for xp in (XPATH_MORE, XPATH_MORE_ALT):
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    is_logged_in = True
                    break
            if is_logged_in:
                break
    finally:
        driver.implicitly_wait(5)
    if is_logged_in:
        print("    🔄 已登录，执行登出")
        check_and_logout(driver)
        time.sleep(2.0)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY))
    )
    print("    ✅ 已处于登录/注册入口页")


def _tap(driver, el) -> None:
    try:
        el.click()
        return
    except Exception:
        pass
    r = el.rect
    driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])  # type: ignore[attr-defined]


def _click_element(driver, xpaths, timeout_s: int = 15) -> str:
    last = None
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            _tap(driver, el)
            print(f"    ✅ 已点击: {xp}")
            return xp
        except Exception as e:
            last = e
    raise TimeoutError(f"未找到可点击元素: {xpaths}, last={last}")


def _dismiss_keyboard(driver) -> None:
    try:
        driver.hide_keyboard()
    except Exception:
        pass
    time.sleep(0.3)


def _type_email(driver, email: str) -> None:
    """步骤5：输入邮箱。"""
    el = None
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            el = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                break
        except Exception:
            continue
    if el is None:
        raise TimeoutError("未找到邮箱输入框")
    try:
        el.clear()
    except Exception:
        pass
    el.send_keys(email)
    time.sleep(0.5)


def _assert_on_verification_page(driver, timeout_s: int = 18) -> None:
    def _ok(d):
        for xp in (
            XPATH_VERIFICATION_TITLE,
            XPATH_RESEND,
            XPATH_CODE_INPUT,
        ):
            for el in d.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return True
        return False

    WebDriverWait(driver, timeout_s).until(_ok)


def _fetch_gmail_code(driver) -> str:
    """步骤6：Gmail 取码并回到 Beatbot。"""
    return get_gmail_verification_code(
        driver=driver,
        method=os.environ.get("GMAIL_CODE_METHOD", "app"),
        subject_contains=os.environ.get("GMAIL_SUBJECT_CONTAINS", "Beatbot Verification Code"),
        from_contains=os.environ.get("GMAIL_FROM_CONTAINS", "noreply"),
        timeout_s=int(os.environ.get("GMAIL_TIMEOUT_S", "90")),
        gmail_bundle_id=os.environ.get("GMAIL_BUNDLE_ID", "com.google.android.gm"),
        kill_gmail_after=True,
        return_app_package=APP_PKG,
    )


def _ensure_on_verification_page(driver, timeout_s: int = 20) -> None:
    """Gmail 返回后确认在验证码页。"""
    try:
        driver.activate_app(APP_PKG)
    except Exception:
        pass
    time.sleep(1.5)
    _assert_on_verification_page(driver, timeout_s=timeout_s)


def _type_verification_code(driver, code: str) -> None:
    """输入 6 位验证码。"""
    target = None
    for el in driver.find_elements(AppiumBy.XPATH, XPATH_CODE_INPUT):
        if el.is_displayed():
            target = el
            break
    if target is None:
        raise TimeoutError("未找到验证码输入框")
    try:
        target.click()
        target.clear()
    except Exception:
        pass
    target.send_keys(code)
    time.sleep(1.2)
    _dismiss_keyboard(driver)


def _assert_on_set_password_page(driver, timeout_s: int = 25) -> None:
    """断言进入设置密码页（至少 2 个 EditText）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        edits = [e for e in driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD) if e.is_displayed()]
        if len(edits) >= 2:
            print("    ✅ 已进入设置密码页")
            return
        time.sleep(0.4)
    raise TimeoutError("未进入设置密码页")


def _type_passwords(driver, password: str) -> None:
    """步骤7：密码、确认密码均输入同一串。"""
    edits = [e for e in driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD) if e.is_displayed()]
    if len(edits) < 2:
        raise TimeoutError("未找到两个密码输入框")
    for i, el in enumerate(edits[:2], 1):
        try:
            el.click()
            el.clear()
        except Exception:
            pass
        el.send_keys(password)
        print(f"    ✅ 密码框[{i}] 已输入")
        time.sleep(0.3)


def _find_submit_button(driver):
    for xp in (XPATH_SUBMIT,):
        for el in driver.find_elements(AppiumBy.XPATH, xp):
            if not el.is_displayed():
                continue
            txt = (el.text or el.get_attribute("text") or "").strip().lower()
            if txt == "next":
                continue
            return el
    raise TimeoutError("未找到 Submit/完成 按钮")


def _assert_submit_stays_on_password_page(driver) -> None:
    """
    步骤8：点击 Submit 后仍停留在设置密码页（仅大写字母+特殊字符，缺数字/小写，无法完成）。
    """
    btn = _find_submit_button(driver)
    try:
        if btn.is_enabled() is False:
            print("    ✅ Submit 不可点击（enabled=false）")
            _assert_on_set_password_page(driver, timeout_s=8)
            return
    except Exception:
        pass

    try:
        btn.click()
    except Exception:
        r = btn.rect
        driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])  # type: ignore[attr-defined]
    time.sleep(1.5)
    _assert_on_set_password_page(driver, timeout_s=10)
    print("    ✅ 点击 Submit 后仍停留在设置密码页")


def _make_driver():
    url = os.environ.get(
        "APPIUM_URL",
        os.environ.get("APPIUM_SERVER_URL", "http://localhost:4730"),
    )
    options = UiAutomator2Options()
    options.platform_name = os.environ.get("ANDROID_PLATFORM_NAME", "Android")
    options.platform_version = os.environ.get("ANDROID_PLATFORM_VERSION", "15")
    options.device_name = os.environ.get("ANDROID_DEVICE_NAME", "Android Device")
    options.automation_name = "UiAutomator2"
    options.app_package = APP_PKG
    act = os.environ.get("ANDROID_APP_ACTIVITY", "").strip()
    if act:
        options.app_activity = act
    udid = os.environ.get("UDID", "").strip()
    if udid:
        options.udid = udid
    options.new_command_timeout = int(os.environ.get("NEW_COMMAND_TIMEOUT", "3600"))
    options.no_reset = True
    options.full_reset = False
    driver = webdriver.Remote(command_executor=url, options=options)
    driver.implicitly_wait(5)
    return driver


@pytest.fixture
def setup_driver():
    driver = _make_driver()
    try:
        yield driver
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def test_200120(setup_driver):
    """
    200120：密码为大写字母+字符（CSX!@#）时 Submit 不可完成修改密码。
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    verification_code = ""

    try:
        current_step = "步骤1: 重启APP并处理登录状态"
        print(f"🔄 {current_step}")
        _restart_app(driver)
        _ensure_landing_page(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤2: 点击 Sign In 进入登录页"
        print(f"🔄 {current_step}")
        _click_element(driver, (XPATH_SIGN_IN, XPATH_SIGN_IN_FALLBACK), 18)
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤3: 点击 Forgot password 进入忘记密码页"
        print(f"🔄 {current_step}")
        _click_element(driver, (XPATH_FORGOT_PASSWORD, XPATH_FORGOT_PASSWORD_FALLBACK), 15)
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 输入邮箱并点击 Next 进入验证码页"
        print(f"🔄 {current_step}")
        _type_email(driver, FORGOT_EMAIL)
        _dismiss_keyboard(driver)
        _click_element(driver, (XPATH_NEXT,), 12)
        _assert_on_verification_page(driver)
        time.sleep(1.0)
        print(f"✅ {current_step} - 完成，邮箱: {FORGOT_EMAIL}")

        current_step = "步骤5: Gmail 获取验证码"
        print(f"🔄 {current_step}")
        verification_code = _fetch_gmail_code(driver)
        print(f"✅ {current_step} - 完成，code: {verification_code}")

        current_step = "步骤6: 输入验证码进入设置密码页"
        print(f"🔄 {current_step}")
        _ensure_on_verification_page(driver)
        _type_verification_code(driver, verification_code)
        _assert_on_set_password_page(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 输入密码 CSX!@#（大写+字符）并点击 Submit"
        print(f"🔄 {current_step}")
        _type_passwords(driver, TEST_PASSWORD)
        _dismiss_keyboard(driver)
        _assert_submit_stays_on_password_page(driver)
        print(f"✅ {current_step} - 完成，password: {TEST_PASSWORD}")

        print("🎉 测试用例 200120 执行成功！")

    except Exception as e:
        case_result = "failed"
        fail_reason = f"{current_step}失败: {e}"
        print(f"\n{'=' * 60}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_200120_failed", run_dir=RUN_DIR)
        assert False, f"测试失败 - {fail_reason}"

    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200120",
            case_desc="200120 验证密码为大写字母+字符时，“完成”按钮不可点击",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
