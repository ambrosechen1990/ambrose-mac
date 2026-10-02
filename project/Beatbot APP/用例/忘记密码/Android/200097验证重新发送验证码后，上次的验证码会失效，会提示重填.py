"""
200097 验证重新发送验证码后，上次的验证码会失效，会提示重填（Android）。

步骤（与流程图一致）：
  1. 重启 APP
  2. 检测是否已登录；已登录则登出；未登录则确认在登录/注册入口页
  3. 点击 Sign In：//android.widget.TextView[@text="Sign In"]
  4. 点击 Forgot password：//android.widget.TextView[@text="Forgot password"]
  5. 输入邮箱 haoc51888@gmail.com，点击 Next 进入验证码页
  6. 打开 Gmail 获取最新验证码 code1（gmail_otp_utils_Android验证码）
  7. kill Gmail，回到 Beatbot 验证码页，等待约 49 秒后点击 Resend
  8. 输入旧验证码 code1，收起键盘
  9. 断言：Verification code error, please re-enter
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
# 验证码分格：父容器 EditText + 子 View[1]~[6]（流程图 / Inspector）
OTP_DIGIT_CELL_XPATHS = [
    f"//android.widget.EditText/android.view.View[{i}]" for i in range(1, 7)
]
XPATH_RESEND = '//android.widget.TextView[@text="Resend"]'
XPATH_RESEND_FALLBACK = '//*[contains(@text,"Resend") or contains(@text,"重新发送")]'
XPATH_VERIFICATION_TITLE = (
    '//*[@text="Verification code" or contains(@text,"Verification code") or contains(@text,"验证码")]'
)
XPATH_NO_CODE = (
    '//*[contains(@text,"receive verification code") or contains(@text,"收到验证码") '
    'or contains(@text,"Cannot receive") or contains(@text,"未收到")]'
)
XPATH_ERR_OTP = '//android.widget.TextView[@text="Verification code error, please re-enter"]'
XPATH_ERR_OTP_FALLBACK = f'//*[contains(@text,"{os.environ.get("OTP_ERROR_TIP", "Verification code error, please re-enter")}")]'

ERR_OTP = os.environ.get("OTP_ERROR_TIP", "Verification code error, please re-enter")

# Android KEYCODE_0=7 … KEYCODE_9=16
_ANDROID_DIGIT_KEYCODE = {str(d): 7 + d for d in range(10)}

# Android KEYCODE_0=7 … KEYCODE_9=16
_KEYCODE_DIGIT = {str(d): 7 + d for d in range(10)}


def _restart_app(driver) -> None:
    """步骤1：重启被测 APP。"""
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
    步骤2：检测登录态。

    - 已登录：调用 check_and_logout 登出
    - 未登录：等待登录/注册入口页
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
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY))
    )
    print("    ✅ 已处于登录/注册入口页")


def _tap_element(driver, el) -> None:
    """点击元素；失败时用坐标 tap。"""
    try:
        el.click()
        return
    except Exception:
        pass
    rect = el.rect or {}
    x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
    y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
    driver.tap([(x, y)])


def _click_element(driver, xpaths, timeout_s: int = 15) -> None:
    """按 XPath 列表查找可点击元素并点击。"""
    last_err = None
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            _tap_element(driver, el)
            print(f"    ✅ 已点击: {xp}")
            return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到可点击元素: {xpaths}，{last_err}")


def _dismiss_keyboard(driver) -> None:
    """收起键盘。"""
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
    """步骤5：在忘记密码页输入邮箱。"""
    el = None
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            el = WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
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


def _assert_on_verification_page(driver, timeout_s: int = 18) -> None:
    """断言已进入验证码输入页。"""
    def _ok(d):
        for xp in (
            XPATH_RESEND,
            XPATH_RESEND_FALLBACK,
            XPATH_NO_CODE,
            XPATH_VERIFICATION_TITLE,
            XPATH_CODE_INPUT,
            *OTP_DIGIT_CELL_XPATHS,
        ):
            for el in d.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return True
        return False

    WebDriverWait(driver, timeout_s).until(_ok)


def _find_otp_digit_cells(driver) -> list:
    """
    查找验证码分格输入框（优先 EditText/android.view.View[1~6]）。
    """
    cells: list = []
    for xp in OTP_DIGIT_CELL_XPATHS:
        for el in driver.find_elements(AppiumBy.XPATH, xp):
            try:
                if el.is_displayed():
                    cells.append(el)
                    break
            except Exception:
                continue
    if len(cells) >= 4:
        return cells[:6]

    container = None
    for el in driver.find_elements(AppiumBy.XPATH, XPATH_CODE_INPUT):
        try:
            if el.is_displayed():
                container = el
                break
        except Exception:
            continue
    if container is None:
        return cells

    views = []
    try:
        for v in container.find_elements(AppiumBy.XPATH, ".//android.view.View"):
            if not v.is_displayed():
                continue
            rect = v.rect or {}
            w = int(rect.get("width", 0) or 0)
            h = int(rect.get("height", 0) or 0)
            if 10 < w < 250 and 10 < h < 250:
                views.append(v)
    except Exception:
        pass
    views.sort(key=lambda v: (int((v.rect or {}).get("x", 0)), int((v.rect or {}).get("y", 0))))
    return views[:6] if len(views) >= 4 else cells


def _find_otp_single_edit(driver):
    """查找验证码页主输入容器 EditText（排除不可见）。"""
    visible = []
    for el in driver.find_elements(AppiumBy.XPATH, XPATH_CODE_INPUT):
        try:
            if el.is_displayed():
                visible.append(el)
        except Exception:
            continue
    if not visible:
        return None
    if len(visible) == 1:
        return visible[0]
    visible.sort(
        key=lambda e: int((e.rect or {}).get("width", 0)) * int((e.rect or {}).get("height", 0)),
        reverse=True,
    )
    return visible[0]


def _ensure_beatbot_verification_page(driver, timeout_s: int = 20) -> None:
    """Gmail 取码后切回 Beatbot 并确认在验证码页。"""
    print("    🔄 切回 Beatbot 验证码页...")
    try:
        driver.activate_app(APP_PKG)
    except Exception:
        pass
    time.sleep(1.5)
    _assert_on_verification_page(driver, timeout_s=timeout_s)
    print("    ✅ 已在 Beatbot 验证码页")


def _fetch_gmail_code(driver) -> str:
    """步骤6：Gmail 获取最新验证码（取码后 kill Gmail 并回到 Beatbot）。"""
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


def _wait_and_click_resend(
    driver,
    *,
    min_wait_s: int = 49,
    max_wait_s: int = 75,
) -> None:
    """
    步骤7：等待倒计时结束后点击 Resend。

    - 至少等待 min_wait_s（流程图约 49 秒）
    - 轮询直到 Resend 可点击
    """
    _ensure_beatbot_verification_page(driver)
    print(f"    ⏳ 等待 Resend 可点击（至少 {min_wait_s}s，最多 {max_wait_s}s）...")
    start = time.time()

    while time.time() - start < min_wait_s:
        time.sleep(min(5.0, min_wait_s - (time.time() - start)))
        try:
            driver.activate_app(APP_PKG)
        except Exception:
            pass

    deadline = start + max_wait_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            driver.activate_app(APP_PKG)
            time.sleep(0.6)
        except Exception:
            pass
        _dismiss_keyboard(driver)
        for xp in (XPATH_RESEND, XPATH_RESEND_FALLBACK):
            try:
                WebDriverWait(driver, 4).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, xp))
                )
                el = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, xp))
                )
                try:
                    el.click()
                except Exception:
                    r = el.rect
                    driver.tap(
                        [(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))]
                    )
                print(f"    ✅ 已点击 Resend: {xp}")
                return
            except Exception as e:
                last_err = e
        time.sleep(2.0)

    raise TimeoutException(f"等待 Resend 可点击超时（max={max_wait_s}s）: {last_err}")


def _send_text_to_editable(driver, el, text: str) -> bool:
    """向可编辑控件写入文本（send_keys / replaceElementValue）。"""
    _tap_element(driver, el)
    time.sleep(0.25)
    try:
        el.clear()
    except Exception:
        pass
    try:
        el.send_keys(text)
        return True
    except Exception:
        pass
    try:
        driver.execute_script(
            "mobile: replaceElementValue",
            {"elementId": el.id, "text": text},
        )
        return True
    except Exception:
        return False


def _type_digits_via_keycode(driver, digits: str) -> None:
    """通过系统键盘 keycode 逐位输入（分格 View 不可 send_keys 时使用）。"""
    for ch in digits:
        kc = _ANDROID_DIGIT_KEYCODE.get(ch)
        if kc is None:
            continue
        driver.press_keycode(kc)
        time.sleep(0.1)


def _type_verification_code(driver, code: str) -> None:
    """
    步骤8：输入验证码。

    分格 UI 的 android.view.View 仅用于展示/聚焦，不可 send_keys；
    优先父级 EditText 整串输入，否则 tap 首格后 press_keycode。
    """
    digits = "".join(c for c in str(code) if c.isdigit())
    if len(digits) < 4:
        raise ValueError(f"验证码无效: {code!r}")

    _ensure_beatbot_verification_page(driver)
    time.sleep(0.6)

    container = _find_otp_single_edit(driver)
    if container is not None and _send_text_to_editable(driver, container, digits):
        print(f"    ✅ EditText 整串输入验证码: {digits}")
        time.sleep(0.5)
        _dismiss_keyboard(driver)
        return

    cells = _find_otp_digit_cells(driver)
    if cells:
        print("    ℹ️ 分格 UI：点击首格后输入")
        _tap_element(driver, cells[0])
        time.sleep(0.5)
        if container is not None and _send_text_to_editable(driver, container, digits):
            print(f"    ✅ 聚焦后 EditText 输入验证码: {digits}")
            _dismiss_keyboard(driver)
            return
        _type_digits_via_keycode(driver, digits)
        time.sleep(0.5)
        _dismiss_keyboard(driver)
        print(f"    ✅ press_keycode 输入验证码: {digits}")
        return

    for el in driver.find_elements(AppiumBy.XPATH, XPATH_CODE_INPUT):
        try:
            if el.is_displayed() and _send_text_to_editable(driver, el, digits):
                print(f"    ✅ 兜底 EditText 输入验证码: {digits}")
                _dismiss_keyboard(driver)
                return
        except Exception:
            continue

    raise TimeoutException(
        f"未找到可输入的验证码框（{XPATH_CODE_INPUT}；分格 View 不可直接 send_keys）"
    )


def _assert_otp_error_tip(driver, timeout_s: int = 25) -> None:
    """步骤9：断言出现验证码错误提示。"""
    for xp in (XPATH_ERR_OTP, XPATH_ERR_OTP_FALLBACK):
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            assert el.is_displayed(), f"未显示错误提示: {xp}"
            print(f"    ✅ 已出现错误提示: {xp}")
            return
        except Exception:
            continue
    raise TimeoutException(
        f"未找到错误提示: {XPATH_ERR_OTP} 或 contains {ERR_OTP}"
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
    """pytest fixture：创建并释放 driver。"""
    d = _make_driver()
    try:
        yield d
    finally:
        try:
            d.quit()
        except Exception:
            pass


def test_200097(setup_driver):
    """
    200097 主流程。

    核心断言：点击 Resend 后，旧验证码失效，提示 Verification code error, please re-enter。
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

        current_step = "步骤6: Gmail 获取验证码"
        print(f"🔄 {current_step}")
        verification_code = _fetch_gmail_code(driver)
        _ensure_beatbot_verification_page(driver)
        print(f"✅ {current_step} - 完成，code: {verification_code}")

        code1 = verification_code

        current_step = "步骤7: kill Gmail 后等待并点击 Resend"
        print(f"🔄 {current_step}")
        min_wait = int(os.environ.get("WAIT_BEFORE_RESEND_S", "49"))
        max_wait = int(os.environ.get("WAIT_RESEND_MAX_S", "75"))
        _wait_and_click_resend(driver, min_wait_s=min_wait, max_wait_s=max_wait)
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤8: 输入旧验证码"
        print(f"🔄 {current_step}")
        _type_verification_code(driver, code1)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤9: 断言验证码错误提示"
        print(f"🔄 {current_step}")
        time.sleep(2.5)
        _assert_otp_error_tip(driver, timeout_s=25)
        print(f"✅ {current_step} - 完成")

        print("🎉 测试用例 200097 执行成功！")
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
        save_failure_screenshot(driver, "test_200097_failed", run_dir=RUN_DIR)
        assert False, f"测试失败 - {fail_reason}"

    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200097",
            case_desc="200097 验证重新发送验证码后，上次的验证码会失效，会提示重填",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
