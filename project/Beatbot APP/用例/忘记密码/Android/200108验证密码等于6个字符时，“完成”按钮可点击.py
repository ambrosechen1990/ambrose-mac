"""
200108 验证密码等于6个字符时，完成按钮可点击（Android）。

步骤1～7进设置密码页；步骤8输入6位密码；步骤9 Submit 成功
"""

import os
import re
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
    check_and_logout,
    save_failure_screenshot,
    init_report,
    bind_logger_to_print,
    write_report,
)
from gmail_otp_utils_Android验证码 import get_gmail_verification_code  # noqa: E402

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

APP_PKG = os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
FORGOT_EMAIL = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
UNREGISTERED_EMAIL = os.environ.get("FORGOT_UNREGISTERED_EMAIL", "1234567771246@163.com")
NEW_PASSWORD = os.environ.get("FORGOT_NEW_PASSWORD", "Csx150128")

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
XPATH_BACK = '//android.widget.ImageView[@content-desc="back"]'
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
XPATH_EMAIL_FALLBACK = "//android.widget.EditText"
XPATH_CLEAR_EMAIL = '//android.widget.ImageView[@content-desc="clear"]'
XPATH_NEXT = "//android.widget.Button"
XPATH_PASSWORD = "//android.widget.EditText"
XPATH_SUBMIT = (
    '//*[@text="Submit" or @text="Done" or @text="完成" or contains(@text,"Submit") or contains(@text,"Done")]'
)
XPATH_RESEND = '//*[contains(@text,"Resend") or contains(@text,"重新发送")]'
XPATH_NO_CODE = (
    '//*[contains(@text,"receive verification code") or contains(@text,"收到验证码") '
    'or contains(@text,"Cannot receive") or contains(@text,"未收到")]'
)
XPATH_PRIVACY = '//*[contains(@text,"Privacy Policy") and contains(@text,"User Agreement")]'
XPATH_PASSWORD_EYE = '//android.widget.ImageView[@content-desc="lock"]'

ERR_NOT_REGISTERED = "This email is not registered. Please check and re-enter."
ERR_OTP = os.environ.get("OTP_ERROR_TIP", "Verification code error, please re-enter")
ERR_PWD_FAIL = os.environ.get("PWD_FAIL_TIP", "Password recovery failed. Please try again.")


def _restart_app(driver) -> None:
    """步骤：终止并重新拉起 App，模拟冷启动后的首屏。"""
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
    """步骤：检测登录态并回到登录/注册入口页（已登录则执行登出）。"""
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


def _click_element(driver, xpaths, timeout_s: int = 15) -> None:
    """按 XPath 列表依次查找可点击元素并点击；click 失败时用坐标 tap 兜底。"""
    last_err = None
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            try:
                el.click()
            except Exception:
                r = el.rect
                driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])
            print(f"    ✅ 已点击: {xp}")
            return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到可点击元素: {xpaths}，{last_err}")


def _dismiss_keyboard(driver) -> None:
    """尝试收起键盘，避免遮挡按钮/输入框。"""
    try:
        driver.hide_keyboard()
        time.sleep(0.4)
        return
    except Exception:
        pass
    try:
        size = driver.get_window_size()
        driver.tap([(int(size["width"] * 0.5), int(size["height"] * 0.12))])
        time.sleep(0.4)
    except Exception:
        pass


def _type_email(driver, email: str) -> None:
    """在忘记密码页输入邮箱（自动定位输入框并清空后输入）。"""
    el = None
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            el = WebDriverWait(driver, 12).until(EC.presence_of_element_located((AppiumBy.XPATH, xp)))
            el.click()
            break
        except Exception:
            continue
    if el is None:
        raise TimeoutException("未找到邮箱输入框")
    try:
        el.clear()
    except Exception:
        pass
    el.send_keys(email)
    time.sleep(0.5)


def _get_email_text(driver) -> str:
    """读取邮箱输入框当前文本（用于断言或调试）。"""
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            return (el.text or el.get_attribute("text") or "").strip()
        except Exception:
            continue
    return ""


def _assert_on_forgot_page(driver, timeout_s: int = 12) -> None:
    """断言仍处于“忘记密码”页（Forgot password 文案可见）。"""
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_FORGOT_PASSWORD_FALLBACK))
    )


def _assert_on_verification_page(driver, timeout_s: int = 18) -> None:
    """断言已进入验证码页（Resend/未收到验证码/输入框等元素可见）。"""
    def _ok(d):
        """_ok：辅助函数（已补充 docstring）。"""
        for xp in (XPATH_RESEND, XPATH_NO_CODE, XPATH_EMAIL_FALLBACK):
            for el in d.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return True
        return False
    WebDriverWait(driver, timeout_s).until(_ok)


def _fetch_gmail_code(driver) -> str:
    """打开 Gmail 获取最新验证码，并切回被测 App。"""
    code = get_gmail_verification_code(
        driver=driver,
        method=os.environ.get("GMAIL_CODE_METHOD", "app"),
        subject_contains=os.environ.get("GMAIL_SUBJECT_CONTAINS", "Beatbot Verification Code"),
        from_contains=os.environ.get("GMAIL_FROM_CONTAINS", "noreply"),
        timeout_s=int(os.environ.get("GMAIL_TIMEOUT_S", "90")),
        gmail_bundle_id=os.environ.get("GMAIL_BUNDLE_ID", "com.google.android.gm"),
        kill_gmail_after=True,
    )
    driver.activate_app(APP_PKG)
    time.sleep(2.0)
    return code


def _type_verification_code(driver, code: str) -> None:
    """在验证码页输入验证码并收起键盘。"""
    target = None
    for el in driver.find_elements(AppiumBy.XPATH, XPATH_EMAIL_FALLBACK):
        if el.is_displayed():
            target = el
            break
    if target is None:
        raise TimeoutException("未找到验证码输入框")
    try:
        target.click()
        target.clear()
    except Exception:
        pass
    target.send_keys(code)
    time.sleep(1.0)
    _dismiss_keyboard(driver)


def _get_code_field_text(driver) -> str:
    """读取验证码输入框文本（用于断言/调试）。"""
    for el in driver.find_elements(AppiumBy.XPATH, XPATH_EMAIL_FALLBACK):
        if el.is_displayed():
            return (el.text or el.get_attribute("text") or "").strip()
    return ""


def _assert_on_set_password_page(driver, timeout_s: int = 20) -> None:
    """断言已进入“设置密码”页（至少出现两个密码输入框）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        edits = [e for e in driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD) if e.is_displayed()]
        if len(edits) >= 2:
            return
        time.sleep(0.4)
    raise TimeoutException("未进入设置密码页")


def _find_password_fields(driver, timeout_s: int = 12):
    """查找“Password/Retype Password”两个输入框并返回。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        edits = [e for e in driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD) if e.is_displayed()]
        if len(edits) >= 2:
            return edits[0], edits[1]
        time.sleep(0.4)
    raise TimeoutException("未找到密码输入框")


def _type_passwords(driver, password: str) -> None:
    """在两个密码输入框中输入同一个密码（用于设置新密码）。"""
    f1, f2 = _find_password_fields(driver)
    for f in (f1, f2):
        try:
            f.click()
            f.clear()
        except Exception:
            pass
        f.send_keys(password)
        time.sleep(0.3)
    _dismiss_keyboard(driver)


def _find_submit_button(driver):
    """查找提交按钮（Submit/Done/完成）用于提交设置密码。"""
    for xp in (XPATH_SUBMIT, XPATH_NEXT):
        for el in driver.find_elements(AppiumBy.XPATH, xp):
            if not el.is_displayed():
                continue
            txt = (el.text or el.get_attribute("text") or "").strip().lower()
            if xp == XPATH_NEXT and txt == "next":
                continue
            return el
    raise TimeoutException("未找到 Submit/完成 按钮")


def _assert_submit_stays_on_password_page(driver) -> None:
    """断言点击提交后仍停留在设置密码页（用于不可点击场景的兜底验证）。"""
    btn = _find_submit_button(driver)
    try:
        if btn.is_enabled() is False:
            return
    except Exception:
        pass
    try:
        btn.click()
    except Exception:
        r = btn.rect
        driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])
    time.sleep(1.2)
    _assert_on_set_password_page(driver, 8)


def _assert_submit_success(driver, timeout_s: int = 25) -> None:
    """断言提交成功后的跳转结果（等待页面离开设置密码页）。"""
    btn = _find_submit_button(driver)
    try:
        btn.click()
    except Exception:
        r = btn.rect
        driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])
    time.sleep(2.0)

    def _left(d):
        """_left：辅助函数（已补充 docstring）。"""
        for xp in (XPATH_SIGN_IN_FALLBACK, XPATH_FORGOT_PASSWORD_FALLBACK, XPATH_PRIVACY):
            for el in d.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return True
        return len([e for e in d.find_elements(AppiumBy.XPATH, XPATH_PASSWORD) if e.is_displayed()]) < 2

    WebDriverWait(driver, timeout_s).until(_left)


def _assert_text_contains(driver, text: str, timeout_s: int = 12) -> None:
    """通用断言：页面存在包含指定文本的可见元素。"""
    xp = f'//*[contains(@text,"{text}")]'
    el = WebDriverWait(driver, timeout_s).until(EC.presence_of_element_located((AppiumBy.XPATH, xp)))
    assert el.is_displayed(), f"未找到文案: {text}"


def _check_rule_colors(driver, expectations) -> None:
    """_check_rule_colors：辅助函数（已补充 docstring）。"""
    if not expectations:
        return
    for fragment, expect in expectations.items():
        el = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.XPATH, f'//*[contains(@text,"{fragment}")]'))
        )
        color = ""
        try:
            color = el.value_of_css_property("color") or ""
        except Exception:
            pass
        print(f"    规则 {fragment}: {color}")
        if color:
            low = color.lower()
            if expect == "red":
                assert "255" in color or "#ff" in low or "red" in low
            else:
                assert "128" in color or "gray" in low or "grey" in low


def _make_driver():
    """创建 Android WebDriver（UiAutomator2），从环境变量读取能力项。"""
    url = os.environ.get("APPIUM_URL", os.environ.get("APPIUM_SERVER_URL", "http://localhost:4730"))
    options = UiAutomator2Options()
    options.platform_name = os.environ.get("ANDROID_PLATFORM_NAME", "Android")
    options.platform_version = os.environ.get("ANDROID_PLATFORM_VERSION", "15")
    options.device_name = os.environ.get("ANDROID_DEVICE_NAME", "Android Device")
    options.automation_name = "UiAutomator2"
    options.app_package = APP_PKG
    act = os.environ.get("ANDROID_APP_ACTIVITY", "").strip()
    if act:
        options.app_activity = act
    options.new_command_timeout = 3600
    options.no_reset = True
    options.full_reset = False
    driver = webdriver.Remote(command_executor=url, options=options)
    driver.implicitly_wait(5)
    return driver


@pytest.fixture(scope="function")
def setup_driver():
    """pytest fixture：创建 driver，并在用例结束后 quit。"""
    driver = _make_driver()
    try:
        yield driver
    finally:
        driver.quit()

def test_200108(setup_driver):
    """验证密码等于6个字符时，完成按钮可点击"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    verification_code = ""
    try:

        current_step = "步骤1: 重启APP并处理登录状态"
        print(f"🔄 {current_step}")
        try:
            _restart_app(driver)
            _ensure_landing_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤2: 点击 Sign In 进入登录页"
        print(f"🔄 {current_step}")
        try:
            _click_element(driver, (XPATH_SIGN_IN, XPATH_SIGN_IN_FALLBACK), 18)
            time.sleep(1.5)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤3: 点击 Forgot password 进入忘记密码页"
        print(f"🔄 {current_step}")
        try:
            _click_element(driver, (XPATH_FORGOT_PASSWORD, XPATH_FORGOT_PASSWORD_FALLBACK), 15)
            time.sleep(1.5)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤4: 输入邮箱"
        print(f"🔄 {current_step}")
        try:
            _type_email(driver, FORGOT_EMAIL)
            _dismiss_keyboard(driver)
            print(f"✅ {current_step} - 完成，邮箱: {FORGOT_EMAIL}")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 点击 Next 进入验证码页"
        print(f"🔄 {current_step}")
        try:
            _click_element(driver, (XPATH_NEXT,), 12)
            _assert_on_verification_page(driver)
            time.sleep(1.0)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤6: Gmail 获取验证码"
        print(f"🔄 {current_step}")
        try:
            verification_code = _fetch_gmail_code(driver)
            print(f"✅ {current_step} - 完成，code: {verification_code}")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤7: 输入验证码进入设置密码页"
        print(f"🔄 {current_step}")
        try:
            _type_verification_code(driver, verification_code)
            _assert_on_set_password_page(driver)
            time.sleep(1.0)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤8: 输入6位密码"
        print(f"🔄 {current_step}")
        try:
            pwd6 = os.environ.get("PASSWORD_6", "Csx150")
            _type_passwords(driver, pwd6)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤9: 点击 Submit 断言成功"
        print(f"🔄 {current_step}")
        try:
            _assert_submit_success(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise


        print("🎉 测试用例 200108 执行成功！")
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
        save_failure_screenshot(driver, "test_200108_failed", run_dir=RUN_DIR)
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200108",
            case_desc="200108 验证密码等于6个字符时，完成按钮可点击",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
