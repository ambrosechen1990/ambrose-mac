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
    raise ImportError("未找到 APP外壳/1共用脚本（需包含 common_utils.py ）")

from common_utils import (
    check_and_logout,
    save_failure_screenshot,
    init_report,
    bind_logger_to_print,
    write_report,
)

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
    return field


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


def test_102133(setup_driver):
    """
    102133 验证错误邮箱-未注册的邮箱，不能找回密码

    1. 重启 APP
    2. 检测是否已登录：已登录则登出；未登录确认在登录/注册首页
    3. 点击 Sign In：//XCUIElementTypeButton[@name="Sign In"]
    4. 点击 Forgot password：//XCUIElementTypeStaticText[@name="Forgot password"]
    5. 点击邮箱输入框：//XCUIElementTypeTextField[@value="Email"]，输入未注册邮箱
    6. 点击 Next：//XCUIElementTypeButton[@name="Next"]
       断言页面显示：
       //XCUIElementTypeStaticText[@name="This email is not registered. Please check and re-enter."]
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    # 固定使用未注册邮箱（按用例要求）
    unregistered_email = "1234567771246@163.com"
    expected_error = "This email is not registered. Please check and re-enter."

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

        current_step = "步骤4: 点击邮箱框输入未注册邮箱"
        print(f"🔄 {current_step}")
        _type_email(driver, unregistered_email, timeout=12)
        print(f"✅ {current_step} - 完成，邮箱: {unregistered_email}")

        current_step = "步骤5: 点击Done收起键盘"
        print(f"🔄 {current_step}")
        try:
            _click_with_tap_fallback(
                driver,
                selectors=[(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]')],
                timeout_each=3,
            )
            print(f"✅ {current_step} - 完成")
        except Exception:
            print(f"ℹ️ {current_step} - 未出现Done按钮，跳过")

        current_step = "步骤6: 点击Next提交"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
            ],
            timeout_each=10,
        )
        time.sleep(1.5)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 断言未注册邮箱错误提示"
        print(f"🔄 {current_step}")
        err = WebDriverWait(driver, 12).until(
            EC.presence_of_element_located(
                (AppiumBy.XPATH, f'//XCUIElementTypeStaticText[@name="{expected_error}"]')
            )
        )
        assert err.is_displayed(), "错误提示存在但不可见"
        print(f"✅ {current_step} - 完成，错误提示已显示")

        print("🎉 测试用例102133执行成功！")
        print("✅ 未注册邮箱点击Next提示邮箱未注册")

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
        save_failure_screenshot(driver, "test_102133_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102133",
            case_desc="102133 验证错误邮箱-未注册的邮箱，不能找回密码",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
