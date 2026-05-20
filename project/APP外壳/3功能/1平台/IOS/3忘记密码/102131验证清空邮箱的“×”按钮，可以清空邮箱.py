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


def _type_email(driver, email: str, timeout: int = 10):
    """
    注意：你给的长 XPath 可能命中的是容器（Other），其 value 为空。
    做法：先点击容器/占位输入框触发焦点，再用 predicate 找真正的 TextField 输入。
    """
    focus_selectors = [
        (
            AppiumBy.XPATH,
            '//XCUIElementTypeApplication[@name="Beatbot"]/XCUIElementTypeWindow[1]/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther',
        ),
        (AppiumBy.XPATH, '//XCUIElementTypeTextField[@value="Email"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeTextField[contains(@value,"Email")]'),
    ]

    # 先触发焦点（不强依赖具体类型）
    try:
        _click_with_tap_fallback(driver, focus_selectors, timeout_each=max(3, timeout // 2))
    except Exception:
        # 不阻塞：后面用 predicate 直接找 TextField
        pass

    # 再定位真正的 TextField
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


def test_102131(setup_driver):
    """
    102131 验证清空邮箱的“×”按钮，可以清空邮箱

    1. 重启 APP；若已登录则登出；确认在登录/注册入口页
    2. 点击 Sign In 进入登录页
    3. 点击 Forgot password 进入忘记密码页
    4. 点击邮箱输入框（指定 XPath 或 //XCUIElementTypeTextField[@value="Email"]），输入 haoc51888@gmail.com
    5. 点击右侧 ×：//XCUIElementTypeButton[@name="login delete"]
    6. 断言邮箱已清空（TextField value 回到 Email/为空）
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
        field = _type_email(driver, email_value, timeout=12)
        # 真机上 value 不一定等于完整输入内容；以「不再是占位符」或「出现清除按钮」作为成功判定
        try:
            WebDriverWait(driver, 6).until(
                lambda d: (
                    (field.get_attribute("value") or "").strip() not in {"", "Email"}
                    or len(d.find_elements(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login delete"]')) > 0
                )
            )
        except Exception:
            pass
        val = (field.get_attribute("value") or "").strip()
        print(f"✅ {current_step} - 完成，当前值: {val}")

        current_step = "步骤5: 点击右侧×清空邮箱"
        print(f"🔄 {current_step}")
        _click_with_tap_fallback(
            driver,
            selectors=[(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login delete"]')],
            timeout_each=8,
        )
        time.sleep(1.2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 断言邮箱已清空"
        print(f"🔄 {current_step}")
        cleared = False
        try:
            tf = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeTextField')
            cur_val = tf.get_attribute("value") or ""
            if cur_val in ("", "Email") or "Email" in cur_val:
                cleared = True
        except Exception:
            cur_val = ""

        if not cleared:
            try:
                placeholder = driver.find_elements(
                    AppiumBy.XPATH, '//XCUIElementTypeTextField[@value="Email"]'
                )
                cleared = any(e.is_displayed() for e in placeholder)
            except Exception:
                cleared = False

        assert cleared, f"点击×后邮箱未清空，当前值: {cur_val}"
        print(f"✅ {current_step} - 完成")

        print("🎉 测试用例102131执行成功！")
        print("✅ 输入邮箱后点击×可清空邮箱")

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
        save_failure_screenshot(driver, "test_102131_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102131",
            case_desc="102131 验证清空邮箱的“×”按钮，可以清空邮箱",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
