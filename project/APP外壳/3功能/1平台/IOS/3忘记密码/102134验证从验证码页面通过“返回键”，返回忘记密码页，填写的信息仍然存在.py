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


def _type_email_into_forgot(driver, email: str, timeout: int = 12):
    """
    Forgot password 页邮箱输入框：优先点击占位符 Email 触发焦点，再用 predicate 抓真实 TextField 输入。
    """
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


def _assert_email_still_present(driver, email: str, timeout: int = 10):
    """
    返回忘记密码页后，断言邮箱输入仍存在。
    iOS 上常见表现：TextField 的 value 直接等于输入内容；或可通过 @value 精确匹配定位。
    """
    # 1) 直接匹配 value
    try:
        tf = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (AppiumBy.XPATH, f'//XCUIElementTypeTextField[@value="{email}"]')
            )
        )
        assert tf.is_displayed(), "邮箱输入框存在但不可见"
        return
    except Exception:
        pass

    # 2) 退化：取任意 TextField 的 value 判断包含 email
    def _has_email(d):
        try:
            fields = d.find_elements(AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"')
            for f in fields:
                try:
                    if not f.is_displayed():
                        continue
                    v = (f.get_attribute("value") or "").strip()
                    if email in v:
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    WebDriverWait(driver, timeout).until(lambda d: _has_email(d))


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


def test_102134(setup_driver):
    """
    102134 验证从验证码页面通过“返回键”，返回忘记密码页，填写的信息仍然存在

    1. 重启 APP
    2. 检测是否已登录：已登录则登出；未登录确认在登录/注册首页
    3. 点击 Sign In：//XCUIElementTypeButton[@name="Sign In"]
    4. 点击 Forgot password：//XCUIElementTypeStaticText[@name="Forgot password"]
    5. 点击邮箱输入框：//XCUIElementTypeTextField[@value="Email"]，输入邮箱：haoc51888@gmail.com
    6. 点击 Done 收起键盘：//XCUIElementTypeButton[@name="Done"]
    7. 点击 Next：//XCUIElementTypeButton[@name="Next"]，进入验证码输入页面
    8. 点击左上角返回按键：//XCUIElementTypeButton[@name="nav back"]，返回上一级
       断言 //XCUIElementTypeTextField[@value="haoc51888@gmail.com"] 仍存在
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    email_value = "haoc51888@gmail.com"

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
        _type_email_into_forgot(driver, email_value, timeout=12)
        print(f"✅ {current_step} - 完成，邮箱: {email_value}")

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

        current_step = "步骤6: 点击Next进入验证码页"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
            ],
            timeout_each=10,
        )
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 点击nav back返回忘记密码页"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="nav back"]'),
                (
                    AppiumBy.XPATH,
                    '//XCUIElementTypeButton[contains(@name, "Back") or contains(@name, "返回") or contains(@name, "nav")]',
                ),
            ],
            timeout_each=10,
        )
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤8: 断言返回后邮箱仍存在"
        print(f"🔄 {current_step}")
        _assert_email_still_present(driver, email_value, timeout=12)
        print(f"✅ {current_step} - 完成")

        print("🎉 测试用例102134执行成功！")
        print("✅ 从验证码页返回后邮箱输入仍保留")

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
        save_failure_screenshot(driver, "test_102134_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102134",
            case_desc="102134 验证从验证码页面通过“返回键”，返回忘记密码页，填写的信息仍然存在",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
