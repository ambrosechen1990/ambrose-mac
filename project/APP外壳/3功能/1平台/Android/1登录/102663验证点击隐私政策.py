import pytest  # 导入pytest用于测试
import time  # 导入time用于延时
import traceback  # 导入traceback用于异常追踪
import os
from appium import webdriver  # 导入appium的webdriver
from appium.webdriver.common.appiumby import AppiumBy  # 导入AppiumBy用于元素定位
from selenium.webdriver.support.ui import WebDriverWait  # 导入WebDriverWait用于显式等待
from selenium.webdriver.support import expected_conditions as EC  # 导入EC用于等待条件
from appium.options.android import UiAutomator2Options  # 导入Android的UiAutomator2选项
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

from common_utils_android import (
check_and_logout,
    save_failure_screenshot,
    init_report,
    bind_logger_to_print,
    write_report,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)


@pytest.fixture(scope="function")
def setup_driver():
    """
    Android设备驱动配置 - 为每个测试函数创建独立的WebDriver实例
    """
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.platform_version = "15"
    options.device_name = "Android Device"
    options.automation_name = "UiAutomator2"
    options.app_package = "com.xingmai.tech"
    # 不设置app_activity，让Appium自动检测启动Activity
    options.new_command_timeout = 3600
    options.no_reset = True  # 不重置应用，通过 terminate_app + activate_app 手动重启
    options.full_reset = False

    driver = webdriver.Remote(
        command_executor="http://localhost:4730",
        options=options,
    )
    driver.implicitly_wait(5)
    yield driver
    if driver:
        driver.quit()


def test_102663(setup_driver):
    """
    验证点击隐私政策（Android）

    1. 重置APP，检测登录状态，如果已登录则登出
    2. 点击登录按钮进入Sign in页面
    3. 找到协议文本，点击Privacy Policy超链接
    4. 验证页面跳转到隐私政策页面，检查是否有WebView
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        # 步骤1: 重置APP，检测登录状态，如果已登录则登出
        current_step = "步骤1: 重置APP，检测登录状态并登出"
        print(f"🔄 {current_step}")
        try:
            caps = driver.capabilities
            app_package = caps.get("appPackage") or "com.xingmai.tech"
            driver.terminate_app(app_package)
            time.sleep(1.5)
            driver.activate_app(app_package)
            time.sleep(2)
            print("    ✅ APP已重置")

            # 检测是否已登录（查找 Home/More 元素）
            is_logged_in = False
            login_indicators = [
                '//android.view.View[@content-desc="Home"]',
                '//android.view.View[@content-desc="More"]',
                "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.view.View[2]",
            ]
            for xp in login_indicators:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, xp)
                    for elem in elements:
                        if elem.is_displayed():
                            is_logged_in = True
                            print(f"    ✅ 检测到已登录状态: {xp}")
                            break
                    if is_logged_in:
                        break
                except Exception:
                    continue

            if is_logged_in:
                print("    🔄 检测到已登录，执行登出操作 (logout_android)...")
                time.sleep(1)  # 等待页面稳定
                try:
                    check_and_logout(driver)
                    print("    ✅ 登出操作完成")
                    time.sleep(1.5)
                except Exception as logout_error:
                    print(f"    ⚠️ 登出操作失败: {logout_error}")
                    fail_reason = f"登出操作失败: {logout_error}"
                    raise
            else:
                print("    ℹ️ 未检测到登录状态，已在登录/登录页")

            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤2: 点击登录按钮，进入 Sign in 页面
        current_step = "步骤2: 点击登录按钮进入Sign in页面"
        print(f"🔄 {current_step}")
        try:
            sign_in_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (
                        AppiumBy.XPATH,
                        "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[1]/android.widget.Button",
                    )
                )
            )
            sign_in_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Sign In按钮 - {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 找到协议文本，点击Privacy Policy超链接
        current_step = "步骤3: 点击Privacy Policy超链接"
        print(f"🔄 {current_step}")
        try:
            # 先找到包含协议文本的TextView
            agreement_text = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, '//android.widget.TextView[@text="I have read and understood the Privacy Policy and agree to the User Agreement."]')
                )
            )
            print("    ✅ 找到协议文本")
            
            # 尝试多种方式点击Privacy Policy链接
            # 方式1: 尝试找到可点击的Privacy Policy元素
            privacy_policy_clicked = False
            privacy_policy_selectors = [
                '//android.widget.TextView[@text="Privacy Policy"]',
                '//android.view.View[contains(@text, "Privacy Policy")]',
                '//android.widget.TextView[contains(@text, "Privacy Policy")]',
            ]
            
            for selector in privacy_policy_selectors:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            # 尝试点击元素
                            elem.click()
                            print(f"    ✅ 使用选择器 {selector} 点击Privacy Policy成功")
                            privacy_policy_clicked = True
                            break
                    if privacy_policy_clicked:
                        break
                except Exception as e:
                    print(f"    ⚠️ 选择器 {selector} 点击失败: {e}")
                    continue
            
            # 方式2: 如果直接点击失败，尝试点击协议文本的特定区域（Privacy Policy部分，通常在文本的左侧）
            if not privacy_policy_clicked:
                try:
                    # 获取协议文本的位置和大小
                    location = agreement_text.location
                    size = agreement_text.size
                    # Privacy Policy通常在文本的左侧部分，尝试点击文本的左侧区域
                    click_x = location['x'] + int(size['width'] * 0.3)  # 点击文本左侧30%的位置
                    click_y = location['y'] + int(size['height'] * 0.5)  # 点击文本中间
                    driver.tap([(click_x, click_y)], 100)
                    print("    ✅ 通过坐标点击Privacy Policy区域成功")
                    privacy_policy_clicked = True
                except Exception as e:
                    print(f"    ⚠️ 坐标点击失败: {e}")
            
            if not privacy_policy_clicked:
                raise Exception("无法找到或点击Privacy Policy链接")
            
            print(f"✅ {current_step} - 完成")
            time.sleep(3)  # 等待页面跳转
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤4: 验证页面跳转到隐私政策页面，检查WebView
        current_step = "步骤4: 验证隐私政策页面，检查WebView"
        print(f"🔄 {current_step}")
        try:
            # 验证页面有WebView
            webview = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, '//android.webkit.WebView[@resource-id="com.xingmai.tech:id/webview"]')
                )
            )
            assert webview.is_displayed(), "WebView存在但不可见"
            print("    ✅ 找到WebView元素")
            time.sleep(1)
            print(f"✅ {current_step} - 完成，隐私政策页面显示正常")
            print("🎉 测试用例102663执行成功！")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {e}"
        print("\n" + "=" * 60)
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print("=" * 60)
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102663_failed", RUN_DIR)
        assert False, f"测试失败 - {fail_reason}"
    finally:
        # 确保切换回原生上下文（如果之前在WebView中）
        try:
            contexts = driver.contexts
            if "NATIVE_APP" in contexts:
                driver.switch_to.context("NATIVE_APP")
        except Exception:
            pass
        
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="102663",
            case_desc="验证点击隐私政策",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

