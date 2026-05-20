import pytest  # 导入pytest用于测试
import time  # 导入time用于延时
import traceback  # 导入traceback用于异常追踪
import os
from appium import webdriver  # 导入appium的webdriver
from appium.webdriver.common.appiumby import AppiumBy  # 导入AppiumBy用于元素定位
from selenium.webdriver.support.ui import WebDriverWait  # 导入WebDriverWait用于显式等待
from selenium.webdriver.support import expected_conditions as EC  # 导入EC用于等待条件
from selenium.common.exceptions import TimeoutException
from appium.options.ios import XCUITestOptions  # 导入iOS的XCUITest选项
import sys
from pathlib import Path

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
    """终止并重新拉起 App，模拟冷启动后的首屏。"""
    caps = driver.capabilities
    bundle_id = caps.get("bundleId") or "com.xingmai.tech"
    driver.terminate_app(bundle_id)
    time.sleep(1.5)
    driver.activate_app(bundle_id)
    time.sleep(2)


def _is_logged_in(driver) -> bool:
    """根据首页 Tab 判断是否已登录。"""
    indicators = [
        '//XCUIElementTypeButton[@name="home sel"]',
        '//XCUIElementTypeButton[@name="mine sel"]',
        '//XCUIElementTypeButton[@name="mine"]',
    ]
    for xpath in indicators:
        try:
            for elem in driver.find_elements(AppiumBy.XPATH, xpath):
                if elem.is_displayed():
                    return True
        except Exception:
            continue
    return False


def _assert_on_login_landing(driver, timeout: int = 10):
    """未登录时应能看到 Sign In 或 Sign Up（登录/注册入口）。"""
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(
            (
                AppiumBy.XPATH,
                '//XCUIElementTypeButton[@name="Sign In"] | //XCUIElementTypeButton[@name="Sign Up"]',
            )
        )
    )


def _click_next_like_button(driver, selectors, timeout_each: int = 4):
    """presence + click，失败则坐标 tap（与注册流 Next 一致）。"""
    btn = None
    for by, sel in selectors:
        try:
            cand = WebDriverWait(driver, timeout_each).until(
                EC.presence_of_element_located((by, sel))
            )
            if cand and cand.is_displayed():
                btn = cand
                break
        except Exception:
            continue
    if btn is None:
        raise TimeoutException("未找到可点击的按钮")
    try:
        btn.click()
    except Exception:
        rect = btn.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})


@pytest.fixture(scope="function")
def setup_driver():
    """
    iOS设备驱动配置 - 为每个测试函数创建独立的WebDriver实例
    """
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


def test_102129(setup_driver):
    """
    102129 验证忘记密码功能按钮

    1) 重启 APP
    2) 若已登录则登出；否则确认处于登录/注册首页（可见 Sign In 或 Sign Up）
    3) 点击 Sign In：//XCUIElementTypeButton[@name="Sign In"]
    4) 点击 Forgot password：//XCUIElementTypeStaticText[@name="Forgot password"]
    5) 成功：页面仍可见 //XCUIElementTypeStaticText[@name="Forgot password"]
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        # 步骤1: 重启 APP + 登录态处理
        current_step = "步骤1: 重启APP并处理登录状态"
        print(f"🔄 {current_step}")
        try:
            _restart_app(driver)
            print("    ✅ APP 已重启")

            if _is_logged_in(driver):
                print("    🔄 检测到已登录，执行登出")
                check_and_logout(driver)
                time.sleep(2)
            else:
                print("    ℹ️ 未检测到已登录 Tab")

            _assert_on_login_landing(driver, timeout=12)
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤2: 点击 Sign In
        current_step = "步骤2: 点击Sign In进入登录页"
        print(f"🔄 {current_step}")
        try:
            sign_in_selectors = [
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Sign In")]'),
            ]
            _click_next_like_button(driver, sign_in_selectors, timeout_each=5)
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击 Sign In - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 点击 Forgot password
        current_step = "步骤3: 点击Forgot password"
        print(f"🔄 {current_step}")
        try:
            forgot_selectors = [
                (AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Forgot password"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Forgot password"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeStaticText[contains(@name,"Forgot password")]'),
            ]
            _click_next_like_button(driver, forgot_selectors, timeout_each=8)
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击 Forgot password - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤4: 断言忘记密码页可见标题文案
        current_step = "步骤4: 验证页面显示 Forgot password"
        print(f"🔄 {current_step}")
        try:
            title = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Forgot password"]')
                )
            )
            assert title.is_displayed(), "Forgot password 文案存在但不可见"
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: 未找到 Forgot password 文案 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102129执行成功！")
        print("✅ 忘记密码入口可点击，且忘记密码页显示 Forgot password")

    except Exception:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败"
        print(f"\n{'=' * 60}")
        print(f"❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102129_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102129",
            case_desc="102129 验证忘记密码功能按钮",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
