import os
import sys
import time
import traceback
from pathlib import Path
from typing import Dict

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
    return elem


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
        return False

    WebDriverWait(driver, timeout).until(lambda d: _ok(d))


def _type_verification_code(driver, code: str, timeout: int = 12):
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


def _assert_on_set_password_page(driver, timeout_s: int = 20):
    pred = (
        '(type == "XCUIElementTypeStaticText" OR type == "XCUIElementTypeNavigationBar") AND '
        '(name CONTAINS "Set Password" OR label CONTAINS "Set Password" OR value CONTAINS "Set Password" OR '
        'name CONTAINS "设置密码" OR label CONTAINS "设置密码" OR value CONTAINS "设置密码")'
    )
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, pred))
    )


def _find_password_fields(driver, timeout_s: int = 12):
    pwd1 = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located(
            (AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeSecureTextField[1]")
        )
    )
    pwd2 = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located(
            (AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeSecureTextField[2]")
        )
    )
    return pwd1, pwd2


def _find_submit_button(driver, timeout_s: int = 12):
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Submit"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Submit")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="完成"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="完成"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="Done"]'),
    ]
    last_err = None
    for by, sel in selectors:
        try:
            e = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((by, sel))
            )
            if e and e.is_displayed():
                return e
        except Exception as ex:
            last_err = ex
            continue
    raise TimeoutException(f"未找到Submit/完成按钮: {last_err}")


def _assert_submit_enabled_and_success(driver, timeout_s: int = 20):
    """
    断言密码==6位时 Submit/完成 可点击且点击后有跳转（不再停留 Set Password）。
    由于不同版本跳转目的页可能不同，这里以“离开 Set Password 页”为成功依据，
    并额外兼容回到登录落地页(Sign In/Sign Up)的判断。
    """
    btn = _find_submit_button(driver, timeout_s=12)
    try:
        enabled = btn.is_enabled()
    except Exception:
        enabled = True
    assert enabled is True, "Submit/完成按钮不可点击（is_enabled=False）"

    try:
        btn.click()
    except Exception:
        rect = btn.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})

    def _left_set_password(d):
        # 1) 回到登录落地页
        try:
            for e in d.find_elements(
                AppiumBy.XPATH,
                '//XCUIElementTypeButton[@name="Sign In"] | //XCUIElementTypeButton[@name="Sign Up"]',
            ):
                if e.is_displayed():
                    return True
        except Exception:
            pass

        # 2) SecureTextField 不再显示（通常已离开设置密码页）
        try:
            fields = d.find_elements(
                AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeSecureTextField"'
            )
        except Exception:
            fields = []
        any_pwd_visible = False
        for f in fields:
            try:
                if f.is_displayed():
                    any_pwd_visible = True
                    break
            except Exception:
                continue
        return not any_pwd_visible

    WebDriverWait(driver, timeout_s).until(lambda d: _left_set_password(d))

def _assert_submit_disabled_or_no_effect(driver):
    """Submit 不可点击或点击后仍停留在 Set Password 页。"""
    btn = _find_submit_button(driver, timeout_s=12)
    try:
        enabled = btn.is_enabled()
    except Exception:
        enabled = True
    if enabled is False:
        return
    try:
        btn.click()
    except Exception:
        rect = btn.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
    time.sleep(1.2)
    _assert_on_set_password_page(driver, timeout_s=8)


def _check_password_rules(driver, expectations: Dict[str, str]):
    for rule_text, expect_color in expectations.items():
        sel = f'//XCUIElementTypeStaticText[@name="{rule_text}"]'
        rule_elem = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.XPATH, sel))
        )
        assert rule_elem.is_displayed(), f"规则提示未显示: {rule_text}"
        color_val = None
        if hasattr(rule_elem, "value_of_css_property"):
            try:
                color_val = rule_elem.value_of_css_property("color")
            except Exception:
                color_val = None
        print(f"📝 规则提示: {rule_text} 颜色: {color_val}")
        if color_val:
            low = color_val.lower()
            if expect_color == "red":
                assert ("255" in color_val or "#ff" in low or "red" in low), f"期望红色但实际为 {color_val}"
            else:
                assert (
                    "128" in color_val or "gray" in low or "grey" in low or "#8" in low
                ), f"期望灰色但实际为 {color_val}"


def _click_acknowledge_after_failure(driver) -> bool:
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="知道了"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="知道了"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Confirm"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Confirm")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="OK"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Ok"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="好的"]'),
    ]
    for by, sel in selectors:
        try:
            btn = WebDriverWait(driver, 3).until(EC.presence_of_element_located((by, sel)))
            if btn and btn.is_displayed():
                try:
                    btn.click()
                except Exception:
                    rect = btn.rect or {}
                    tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
                    tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
                    driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
                time.sleep(0.8)
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


def test_102165(setup_driver):
    """102165 失败后点知道了"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    email_value = os.environ.get("FORGOT_PWD_EMAIL", "haoc51888@gmail.com")
    pwd1_val = os.environ.get("FAIL_PWD1", "Csx150128")
    pwd2_val = os.environ.get("FAIL_PWD2", "Csx150129")
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

        current_step = "步骤5: Gmail获取最新验证码code"
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

        current_step = "步骤6: 输入验证码进入Set Password页"
        print(f"🔄 {current_step}")
        _type_verification_code(driver, code, timeout=12)
        _assert_on_set_password_page(
            driver, timeout_s=int(os.environ.get("SET_PASSWORD_TIMEOUT_S", "20"))
        )
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 两次不同密码并Submit"
        print(f"🔄 {current_step}")
        f1, f2 = _find_password_fields(driver, timeout_s=12)
        for field, val in ((f1, pwd1_val), (f2, pwd2_val)):
            try:
                field.click()
                field.clear()
            except Exception:
                pass
            field.send_keys(val)
            time.sleep(0.5)
        _dismiss_keyboard(driver)
        btn = _find_submit_button(driver, timeout_s=12)
        try:
            btn.click()
        except Exception:
            rect = btn.rect or {}
            driver.execute_script(
                "mobile: tap",
                {"x": int(rect.get("x", 0) + rect.get("width", 0) / 2), "y": int(rect.get("y", 0) + rect.get("height", 0) / 2)},
            )
        time.sleep(1.5)
        _click_acknowledge_after_failure(driver)
        _assert_on_set_password_page(driver, timeout_s=10)
        pwd_a, pwd_b = _find_password_fields(driver, timeout_s=10)
        assert pwd_a.is_displayed() and pwd_b.is_displayed()
        print("🎉 测试用例102165执行成功！")
    except Exception:
        case_result = "failed"
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102165_failed")
        assert False
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102165",
            case_desc="102165 验证密码更换失败后，点击知道了",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
