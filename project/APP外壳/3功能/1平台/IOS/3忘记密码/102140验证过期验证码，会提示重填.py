import os
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
                AppiumBy.XPATH,
                '//XCUIElementTypeButton[@name="Resend"] | //XCUIElementTypeButton[contains(@name,"Resend")]',
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


def _type_verification_code(driver, code: str, timeout: int = 12):
    """
    验证码输入框定位：优先 TextField，其次 TextView。
    """
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
        raise TimeoutException("未找到验证码输入框(TextField/TextView)")

    try:
        target.click()
    except Exception:
        rect = target.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})

    try:
        target.clear()
    except Exception:
        pass
    target.send_keys(code)
    time.sleep(0.6)
    _dismiss_keyboard(driver)


def _wait_for_error_tip(driver, expected_error: str, timeout_s: int = 12):
    esc = expected_error.replace('"', '\\"')
    pred = (
        '(type == "XCUIElementTypeStaticText" OR type == "XCUIElementTypeTextView") AND '
        f'(name CONTAINS "{esc}" OR label CONTAINS "{esc}" OR value CONTAINS "{esc}")'
    )
    return WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, pred))
    )


def _submit_verification_if_possible(driver):
    """
    兼容“输入满 6 位自动校验”的版本：有按钮就点，没有就忽略。
    """
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Verify"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Verify")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Submit"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Submit")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Continue"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Continue")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Confirm"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Confirm")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="Done"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="完成"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="完成"]'),
    ]
    for by, sel in selectors:
        try:
            elems = driver.find_elements(by, sel)
        except Exception:
            elems = []
        for e in elems:
            try:
                if e.is_displayed() and e.is_enabled():
                    try:
                        e.click()
                    except Exception:
                        rect = e.rect or {}
                        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
                        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
                        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
                    return True
            except Exception:
                continue
    return False


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


def test_102140(setup_driver):
    """
    102140 验证过期验证码，会提示重填

    1. 重启APP并确保未登录
    2. Sign In -> Forgot password
    3. 输入邮箱 -> Next 到验证码页（触发发码）
    4. 打开 Gmail 获取验证码 code
    5. 切回 APP 等待 300s（让验证码过期）
    6. 输入 code，断言提示：Verification code error, please re-enter
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    expected_error = os.environ.get(
        "OTP_ERROR_TIP", "Verification code error, please re-enter"
    )
    expire_wait_s = int(os.environ.get("OTP_EXPIRE_WAIT_S", "300"))
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

        current_step = "步骤4: 输入邮箱并点击Next进入验证码页"
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

        current_step = "步骤5: Gmail获取验证码code"
        print(f"🔄 {current_step}")
        code = get_gmail_verification_code(
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
        print(f"✅ {current_step} - 完成，code: {code}")

        current_step = f"步骤6: 等待{expire_wait_s}s让验证码过期"
        print(f"🔄 {current_step}")
        time.sleep(expire_wait_s)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 输入过期验证码并断言提示重填"
        print(f"🔄 {current_step}")
        _type_verification_code(driver, code, timeout=12)
        _submit_verification_if_possible(driver)
        _wait_for_error_tip(
            driver,
            expected_error=expected_error,
            timeout_s=int(os.environ.get("ERROR_TIP_TIMEOUT_S", "15")),
        )
        print(f"✅ {current_step} - 完成")

        print("🎉 测试用例102140执行成功！")

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
        save_failure_screenshot(driver, "test_102140_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102140",
            case_desc="102140 验证过期验证码，会提示重填",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
