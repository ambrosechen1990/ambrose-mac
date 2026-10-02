"""
200099 验证“未收到验证码”可以跳转到提示页面（Android）。

操作步骤（与流程图一致）：
  1. 重启 APP
  2. 检测是否已登录；已登录则 check_and_logout；未登录则确认在登录/注册入口页
  3. 点击 Sign In：//android.widget.TextView[@text="Sign In"]，进入登录页
  4. 点击 Forgot password：//android.widget.TextView[@text="Forgot password"]，进入忘记密码页
  5. 输入邮箱并点击 Next，进入验证码输入页
  6. 收起键盘，点击 //android.widget.TextView[@text="Can't receive verification code?"]
  7. 断言提示页存在 //android.widget.TextView[@text="Haven't Received Verification Code"]
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

APP_PKG = os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
FORGOT_EMAIL = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")

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

XPATH_VERIFICATION_TITLE = '//*[@text="Verification code" or contains(@text,"Verification code")]'
XPATH_CANT_RECEIVE = '//android.widget.TextView[@text="Can\'t receive verification code?"]'
XPATH_CANT_RECEIVE_FALLBACK = (
    '//*[contains(@text,"Can\'t receive verification code") '
    'or contains(@text,"Cannot receive verification code") '
    'or contains(@text,"未收到验证码") or contains(@text,"收不到验证码")]'
)
# 提示页标题（优先精确匹配；部分机型为弯引号 ’）
XPATH_TIPS_TITLE_EXACT = '//android.widget.TextView[@text="Haven\'t Received Verification Code"]'
XPATH_TIPS_TITLE_CURLY = "//android.widget.TextView[@text=\"Haven\u2019t Received Verification Code\"]"
XPATH_TIPS_TITLE_FALLBACK = (
    '//*[contains(@text,"Received Verification Code") and contains(@text,"Haven")]'
)


def _restart_app(driver) -> None:
    """步骤1：终止并重新拉起 App，模拟冷启动后的首屏。"""
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
    """
    步骤2：检测登录态并回到登录/注册入口页。

    - 若可见 More，视为已登录，调用 check_and_logout 登出
    - 等待入口页出现 Sign In 或 Sign Up
    """
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
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY)))
    print("    ✅ 已处于登录/注册入口页")


def _tap(driver, el) -> None:
    """通用点击：优先 click，失败则坐标 tap 兜底。"""
    try:
        el.click()
        return
    except Exception:
        pass
    r = el.rect
    driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])  # type: ignore[attr-defined]


def _click_element(driver, xpaths, timeout_s: int = 15) -> str:
    """
    按 XPath 列表依次查找可点击元素并点击。

    Returns:
        实际命中的 XPath（便于日志定位）
    """
    last = None
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout_s).until(EC.presence_of_element_located((AppiumBy.XPATH, xp)))
            last = el
            if el.is_displayed():
                _tap(driver, el)
                print(f"    ✅ 已点击: {xp}")
                return xp
        except Exception as e:
            last = e
            continue
    raise TimeoutError(f"未找到可点击元素: {xpaths}, last={last}")


def _type_email(driver, email: str) -> None:
    """步骤5：在忘记密码页输入邮箱（自动聚焦输入框）。"""
    last = None
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            el = WebDriverWait(driver, 15).until(EC.presence_of_element_located((AppiumBy.XPATH, xp)))
            if el.is_displayed():
                try:
                    el.clear()
                except Exception:
                    pass
                el.send_keys(email)
                return
        except Exception as e:
            last = e
    raise TimeoutError(f"邮箱输入失败: {last}")


def _dismiss_keyboard(driver) -> None:
    """收起键盘，避免遮挡按钮。"""
    try:
        driver.hide_keyboard()
    except Exception:
        pass


def _assert_on_verification_page(driver, timeout_s: int = 25) -> None:
    """断言已进入验证码页（标题 Verification code 可见）。"""
    WebDriverWait(driver, timeout_s).until(EC.presence_of_element_located((AppiumBy.XPATH, XPATH_VERIFICATION_TITLE)))


def _assert_on_no_code_tips_page(driver, timeout_s: int = 20) -> None:
    """断言提示页存在标题 TextView：Haven't Received Verification Code。"""
    last_err: Exception | None = None
    for xp in (
        XPATH_TIPS_TITLE_EXACT,
        XPATH_TIPS_TITLE_CURLY,
        XPATH_TIPS_TITLE_FALLBACK,
    ):
        try:
            el = WebDriverWait(driver, timeout_s, poll_frequency=0.3).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                text = (el.text or el.get_attribute("text") or "").strip()
                print(f"    ✅ 提示页标题已出现: {text!r} ({xp})")
                return
        except Exception as e:
            last_err = e
            continue
    raise TimeoutError(
        f"未找到提示页标题 {XPATH_TIPS_TITLE_EXACT}，last={last_err}"
    )


def _make_driver():
    """创建 Android WebDriver（UiAutomator2），与 200103 等用例一致。"""
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
    """pytest fixture：创建 driver 并在用例结束后释放。"""
    d = _make_driver()
    try:
        yield d
    finally:
        try:
            d.quit()
        except Exception:
            pass


def test_200099(setup_driver):
    """
    200099 主流程（与流程图一致）。

    核心断言：点击 “Can't receive verification code?” 可跳转到提示页。
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
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

        current_step = "步骤4: 输入邮箱"
        print(f"🔄 {current_step}")
        _type_email(driver, FORGOT_EMAIL)
        _dismiss_keyboard(driver)
        print(f"✅ {current_step} - 完成，邮箱: {FORGOT_EMAIL}")

        current_step = "步骤5: 点击 Next 进入验证码页"
        print(f"🔄 {current_step}")
        _click_element(driver, (XPATH_NEXT,), 12)
        _assert_on_verification_page(driver)
        _dismiss_keyboard(driver)
        time.sleep(0.8)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 点击 Can't receive verification code? 跳转提示页"
        print(f"🔄 {current_step}")
        _dismiss_keyboard(driver)
        _click_element(
            driver,
            (XPATH_CANT_RECEIVE, XPATH_CANT_RECEIVE_FALLBACK),
            18,
        )
        time.sleep(1.0)
        _assert_on_no_code_tips_page(driver, 20)
        print(f"✅ {current_step} - 完成")

        print("🎉 测试用例 200099 执行成功！")
    except Exception as e:
        case_result = "failed"
        fail_reason = f"{current_step}失败: {e}"
        print(f"\n{'=' * 60}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_200099_failed", run_dir=RUN_DIR)
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200099",
            case_desc='200099 验证“未收到验证码”可以跳转到提示页面',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])

