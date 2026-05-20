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

# APP外壳 已取消 comman：共用逻辑在「1共用脚本」
_cur = Path(__file__).resolve().parent
_shared = None
for _ in range(24):
    _cand = _cur / "1共用脚本"
    if _cand.is_dir() and (_cand / "common_utils.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 APP外壳/1共用脚本（需包含 common_utils.py）")

from common_utils import (  # noqa: E402
    check_and_logout,
    save_failure_screenshot,
    init_report,
    bind_logger_to_print,
    write_report,
)
from gmail_otp_utils import get_gmail_verification_code  # noqa: E402

RUN_LABEL = os.environ.get("RUN_LABEL", "ios")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)


def _restart_app(driver):
    caps = driver.capabilities
    bundle_id = caps.get("bundleId") or "com.xingmai.tech"
    driver.terminate_app(bundle_id)
    time.sleep(1.5)
    driver.activate_app(bundle_id)
    time.sleep(2)


def _is_logged_in(driver) -> bool:
    indicators = [
        '//XCUIElementTypeButton[@name="home sel"]',
        '//XCUIElementTypeButton[@name="mine sel"]',
        '//XCUIElementTypeButton[@name="mine"]',
    ]
    for xp in indicators:
        try:
            for e in driver.find_elements(AppiumBy.XPATH, xp):
                if e.is_displayed():
                    return True
        except Exception:
            continue
    return False


def _assert_on_login_landing(driver, timeout: int = 12):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(
            (
                AppiumBy.XPATH,
                '//XCUIElementTypeButton[@name="Sign In"] | //XCUIElementTypeButton[@name="Sign Up"]',
            )
        )
    )


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
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})


def _dismiss_keyboard(driver):
    try:
        done_btns = driver.find_elements(
            AppiumBy.XPATH,
            '//XCUIElementTypeButton[@name="Done" or @label="Done" or @name="完成" or @label="完成"]',
        )
        for b in done_btns:
            try:
                if b.is_displayed() and b.is_enabled():
                    b.click()
                    time.sleep(0.4)
                    return
            except Exception:
                continue
    except Exception:
        pass

    try:
        driver.hide_keyboard()
        time.sleep(0.4)
        return
    except Exception:
        pass

    try:
        size = driver.get_window_size()
        driver.execute_script(
            "mobile: tap",
            {"x": int(size["width"] * 0.5), "y": int(size["height"] * 0.15)},
        )
        time.sleep(0.4)
    except Exception:
        pass


def _type_email(driver, email: str, timeout: int = 12):
    try:
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeTextField[@value="Email"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeTextField[contains(@value,"Email")]'),
            ],
            timeout_each=6,
        )
    except Exception:
        pass
    field = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(
            (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"')
        )
    )
    try:
        field.clear()
    except Exception:
        pass
    field.send_keys(email)
    time.sleep(0.6)
    _dismiss_keyboard(driver)
    return field


def _assert_on_verification_page(driver, timeout: int = 15):
    """
    断言已进入验证码输入页面：以出现验证码输入框（TextField/TextView）或 Resend 为准。
    """

    def _ok(d):
        try:
            inputs = d.find_elements(
                AppiumBy.IOS_PREDICATE,
                'type == "XCUIElementTypeTextField" OR type == "XCUIElementTypeTextView"',
            )
        except Exception:
            inputs = []
        for e in inputs:
            try:
                if e.is_displayed():
                    return True
            except Exception:
                continue

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

    WebDriverWait(driver, timeout).until(lambda d: _ok(d))


def _assert_on_forgot_password_page(driver, timeout: int = 12):
    """
    断言已回到 Forgot password 输入邮箱页（以 Email 输入框/Next 按钮为准）。
    """

    def _ok(d):
        try:
            if d.find_elements(AppiumBy.XPATH, '//XCUIElementTypeTextField[@value="Email"]'):
                return True
        except Exception:
            pass
        try:
            btns = d.find_elements(
                AppiumBy.XPATH,
                '//XCUIElementTypeButton[@name="Next"] | //XCUIElementTypeButton[contains(@name,"Next")]',
            )
            for b in btns:
                try:
                    if b.is_displayed():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    WebDriverWait(driver, timeout).until(lambda d: _ok(d))


def _get_resend_seconds(driver):
    """
    从 Resend 文案中提取倒计时秒数。不同版本可能：
    - Resend(56s)
    - Resend 56s / Resend in 56s
    - 重新发送(56) 等
    返回 int 或 None（未解析到）。
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
    断言 Resend 倒计时“重新开始”（接近 60s）。
    min_expected_s 默认 45：避免刚进页面就已经跳到 44/43 造成误判。
    """

    def _ok(d):
        sec = _get_resend_seconds(d)
        if sec is None:
            return False
        return sec >= min_expected_s

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
    options.bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")
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


def test_102141(setup_driver):
    """
    102141 验证从输入验证码页面返回忘记密码页，60S再进入“输入验证码”页面，需要重发验证码，且倒计时重置
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    wait_on_forgot_s = int(os.environ.get("WAIT_ON_FORGOT_PASSWORD_S", "60"))
    resend_reset_min_s = int(os.environ.get("RESEND_RESET_MIN_S", "45"))
    beatbot_bundle_id = os.environ.get("APP_BUNDLE_ID", "com.xingmai.tech")

    try:
        current_step = "步骤1: 重启APP并处理登录状态"
        print(f"🔄 {current_step}")
        _restart_app(driver)
        if _is_logged_in(driver):
            check_and_logout(driver)
            time.sleep(2)
        _assert_on_login_landing(driver, timeout=12)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤2: 点击Sign In进入登录页"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Sign In")]'),
            ],
            timeout_each=8,
        )
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤3: 点击Forgot password进入忘记密码页"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Forgot password"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Forgot password"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeStaticText[contains(@name,"Forgot password")]'),
            ],
            timeout_each=10,
        )
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 输入邮箱并点击Next进入验证码页(第一次)"
        print(f"🔄 {current_step}")
        _type_email(driver, email_value, timeout=12)
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
            ],
            timeout_each=10,
        )
        _assert_on_verification_page(driver, timeout=18)
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成，邮箱: {email_value}")

        current_step = "步骤5: 点击左上返回(nav back)返回忘记密码页"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="nav back"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"nav back")]'),
                (AppiumBy.ACCESSIBILITY_ID, "nav back"),
            ],
            timeout_each=12,
        )
        _assert_on_forgot_password_page(driver, timeout=15)
        time.sleep(1.0)
        print(f"✅ {current_step} - 完成")

        current_step = f"步骤6: 在忘记密码页停留{wait_on_forgot_s}s"
        print(f"🔄 {current_step}")
        time.sleep(wait_on_forgot_s)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 打开Gmail获取第一次验证码code1"
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
        driver.activate_app(beatbot_bundle_id)
        time.sleep(2.0)
        print(f"✅ {current_step} - 完成，code1: {code1}")

        current_step = "步骤8: 再次点击Next进入验证码页(第二次)"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
            ],
            timeout_each=10,
        )
        _assert_on_verification_page(driver, timeout=18)
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤9: 断言Resend倒计时重置(接近60s重新开始)"
        print(f"🔄 {current_step}")
        sec = _wait_resend_countdown_reset(
            driver,
            timeout_s=int(os.environ.get("RESEND_RESET_ASSERT_TIMEOUT_S", "20")),
            min_expected_s=resend_reset_min_s,
        )
        print(f"✅ {current_step} - 完成，当前倒计时约: {sec}s")

        current_step = "步骤10: 再次打开Gmail获取第二次验证码code2并断言与code1不同"
        print(f"🔄 {current_step}")
        code2 = get_gmail_verification_code(
            driver=driver,
            method=os.environ.get("GMAIL_CODE_METHOD", "app"),
            subject_contains=os.environ.get(
                "GMAIL_SUBJECT_CONTAINS", "Beatbot Verification Code"
            ),
            from_contains=os.environ.get("GMAIL_FROM_CONTAINS", "noreply"),
            timeout_s=int(os.environ.get("GMAIL_TIMEOUT_S_2", "120")),
            gmail_bundle_id=os.environ.get("GMAIL_BUNDLE_ID", "com.google.Gmail"),
            kill_gmail_after=True,
        )
        driver.activate_app(beatbot_bundle_id)
        time.sleep(2.0)
        if code2 == code1:
            raise AssertionError(f"第二次验证码未变化：code1={code1}, code2={code2}")
        print(f"✅ {current_step} - 完成，code2: {code2}（与code1不同）")

        print("🎉 测试用例102141执行成功！")

    except Exception:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败"
        print(f"\n{'=' * 60}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102141_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102141",
            case_desc="102141 验证从输入验证码页面返回忘记密码页，60S再进入“输入验证码”页面，需要重发验证码，且倒计时重置",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
