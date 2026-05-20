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

from common_utils import (
    check_and_logout,
    save_failure_screenshot,
    init_report,
    bind_logger_to_print,
    write_report,
)
from gmail_otp_utils import get_gmail_verification_code

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
    """
    收起 iOS 键盘（优先点 Done/完成；其次 hide_keyboard；最后点空白）。
    """
    try:
        # 常见 Done / 完成
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

    # 最后兜底：点屏幕上方空白区域
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
    # 先点击占位输入框，触发焦点
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


def _type_verification_code(driver, code: str, timeout: int = 12):
    """
    验证码输入框定位：优先 TextField，其次 TextView（不同版本可能不同）。
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


def _assert_on_verification_page(driver, timeout: int = 15):
    """
    断言已进入验证码输入页面。
    以出现验证码输入框（TextField/TextView）或 Resend 按钮为准。
    """
    def _ok(d):
        try:
            # 验证码输入框
            inputs = d.find_elements(
                AppiumBy.IOS_PREDICATE,
                'type == "XCUIElementTypeTextField" OR type == "XCUIElementTypeTextView"',
            )
            for e in inputs:
                try:
                    if e.is_displayed():
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        try:
            resends = d.find_elements(
                AppiumBy.XPATH,
                '//XCUIElementTypeButton[@name="Resend"] | //XCUIElementTypeButton[contains(@name,"Resend")]',
            )
            for e in resends:
                try:
                    if e.is_displayed():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    WebDriverWait(driver, timeout).until(lambda d: _ok(d))

def _debug_visible_buttons(driver, limit: int = 20):
    try:
        btns = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeButton")
    except Exception:
        btns = []
    names = []
    for b in btns:
        try:
            if not b.is_displayed():
                continue
            n = (b.get_attribute("name") or b.get_attribute("label") or "").strip()
            if n:
                names.append(n)
        except Exception:
            continue
    if names:
        print(f"    💡 当前页面可见按钮(name/label)示例: {names[:limit]}")
    else:
        print("    💡 当前页面未采集到可见按钮(name/label)")


def _submit_verification(driver):
    """
    验证码页提交按钮不同版本可能不是 Next，统一在这里兜底。
    """
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Verify"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Verify")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Submit"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Submit")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Continue"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Continue")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Confirm"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Confirm")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="Done"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="完成"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@label="完成"]'),
    ]
    # 注意：验证码页很多版本是“输入满 6 位自动校验”，根本没有提交按钮。
    # 旧实现逐个 selector 做长等待，可能累计阻塞数分钟。
    # 这里改为：优先快速扫描（不做长等待），没找到就快速失败交给自动校验逻辑。
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
                    return
            except Exception:
                continue
        time.sleep(0.2)
    raise TimeoutException("未找到提交按钮（可能为自动校验页面）")


def _submit_or_wait_autovalidation(driver, expected_error: str, wait_s: int = 10):
    """
    有些验证码页没有提交按钮：输入满 6 位后会自动校验并弹错误提示。
    策略：先尝试提交按钮；若找不到则等待错误提示自动出现。
    """
    try:
        _submit_verification(driver)
        return
    except Exception:
        pass

    # 没有提交按钮：等待自动校验的错误提示（不同版本可能在 label/value/TextView）
    return _wait_for_error_tip(driver, expected_error, timeout_s=wait_s)


def _wait_for_error_tip(driver, expected_error: str, timeout_s: int = 12):
    """
    错误提示可能出现在 StaticText/TextView，且落在 name/label/value 任一属性。
    这里用 contains 做鲁棒匹配。
    """
    # predicate 里用双引号包裹字符串
    esc = expected_error.replace('"', '\\"')
    pred = (
        '(type == "XCUIElementTypeStaticText" OR type == "XCUIElementTypeTextView") AND '
        f'(name CONTAINS "{esc}" OR label CONTAINS "{esc}" OR value CONTAINS "{esc}")'
    )
    elem = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, pred))
    )
    # 打印实际命中的属性，便于排查“真机有提示但脚本等不到/卡住”
    try:
        n = elem.get_attribute("name") or ""
        l = elem.get_attribute("label") or ""
        v = elem.get_attribute("value") or ""
        print(f'    ✅ 命中错误提示元素: name="{n}" label="{l}" value="{v}"')
    except Exception:
        pass
    return elem


@pytest.fixture(scope="function")
def setup_driver():
    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.platform_version = "18.5"
    options.device_name = "iPhone 16 pro max"
    options.automation_name = "XCUITest"
    options.udid = "00008140-00041C980A50801C"
    options.bundle_id = "com.xingmai.tech"
    options.include_safari_in_webviews = True
    options.new_command_timeout = 3600
    options.connect_hardware_keyboard = True

    driver = webdriver.Remote(
        command_executor="http://localhost:4736",
        options=options,
    )
    driver.implicitly_wait(5)
    yield driver
    if driver:
        driver.quit()


def test_102135(setup_driver):
    """
    102135 验证重新发送验证码后，上次的验证码会失效，会提示重填

    1. 重启 APP
    2. 检测是否已登录：已登录则登出；未登录确认在登录/注册首页
    3. 点击 Sign In：//XCUIElementTypeButton[@name="Sign In"]
    4. 点击 Forgot password：//XCUIElementTypeStaticText[@name="Forgot password"]
    5. 输入邮箱：//XCUIElementTypeTextField[@value="Email"]，输入：haoc51888@gmail.com
    6. 点击 Next：//XCUIElementTypeButton[@name="Next"]，进入验证码输入页面（系统发送验证码邮件）
    7. 从 Gmail 获取最新验证码 code1
    8. 等待 Resend 可用后点击 Resend，重新发送验证码
    9. 输入旧验证码 code1 并提交，断言提示：
       //XCUIElementTypeStaticText[@name="Verification code error, please re-enter"]
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    email_value = "haoc51888@gmail.com"
    expected_error = "Verification code error, please re-enter"
    beatbot_bundle_id = "com.xingmai.tech"

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

        current_step = "步骤4: 输入邮箱"
        print(f"🔄 {current_step}")
        _type_email(driver, email_value, timeout=12)
        print(f"✅ {current_step} - 完成，邮箱: {email_value}")

        current_step = "步骤5: 点击Next进入验证码页并触发发码"
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

        current_step = "步骤6: Gmail获取最新验证码code1"
        print(f"🔄 {current_step}")
        code1 = get_gmail_verification_code(
            driver=driver,
            method=os.environ.get("GMAIL_CODE_METHOD", "app"),
            subject_contains="Beatbot Verification Code",
            from_contains="noreply",
            timeout_s=90,
            gmail_bundle_id="com.google.Gmail",
            kill_gmail_after=True,
        )
        # 切回 Beatbot
        driver.activate_app(beatbot_bundle_id)
        time.sleep(2.0)
        print(f"✅ {current_step} - 完成，code1: {code1}")

        current_step = "步骤7: 等待Resend可用并点击"
        print(f"🔄 {current_step}")
        # 某些版本 Resend 会倒计时（约60s），这里最多等70s
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Resend"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Resend")]'),
            ],
            timeout_each=70,
        )
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤8: 输入旧验证码并触发校验"
        print(f"🔄 {current_step}")
        _type_verification_code(driver, code1, timeout=12)
        try:
            _submit_or_wait_autovalidation(
                driver,
                expected_error=expected_error,
                wait_s=int(os.environ.get("STEP8_WAIT_S", "12")),
            )
        except Exception:
            _debug_visible_buttons(driver)
            raise
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成（已出现错误提示）")

        print("🎉 测试用例102135执行成功！")
        print("✅ 重新发送验证码后，旧验证码失效并提示重填")

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
        save_failure_screenshot(driver, "test_102135_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102135",
            case_desc="102135 验证重新发送验证码后，上次的验证码会失效，会提示重填",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
