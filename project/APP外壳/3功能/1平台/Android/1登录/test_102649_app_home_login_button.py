# 102649：验证 APP 首页登录功能按钮（Android）。原中文文件名不利于 pytest 收集。
import pytest  # 导入pytest用于测试
import time  # 导入time用于延时
import traceback  # 导入traceback用于异常追踪
import os
from appium import webdriver  # 导入appium的webdriver
from appium.webdriver.common.appiumby import AppiumBy  # 导入AppiumBy用于元素定位
from selenium.webdriver.support.ui import WebDriverWait  # 导入WebDriverWait用于显式等待
from selenium.webdriver.support import expected_conditions as EC  # 导入EC用于等待条件
from selenium.webdriver.common.by import By  # 导入By用于通用定位
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
    get_next_email,
    get_simple_email,
    check_and_logout,
    save_failure_screenshot,
    ScreenshotContext,
    safe_execute,
    init_report,
    bind_logger_to_print,
    write_report,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

from username_utils import ran1, ran2, ran3, ran4, ran5, ran6


@pytest.fixture(scope="function")
def setup_driver():
    """
    Android设备驱动配置 - 为每个测试函数创建独立的WebDriver实例

    Returns:
        WebDriver: 配置好的Android WebDriver实例
    """
    # Android设备配置
    options = UiAutomator2Options()  # 创建UiAutomator2选项对象
    options.platform_name = "Android"  # 设置平台名称
    options.platform_version = "15"  # 设置Android系统版本（根据实际设备调整）
    options.device_name = "Android Device"  # 设置设备名称
    options.automation_name = "UiAutomator2"  # 设置自动化引擎
    options.app_package = "com.xingmai.tech"  # 设置应用包名
    # 不设置app_activity，让Appium自动检测启动Activity
    options.new_command_timeout = 3600  # 设置新命令超时时间
    options.no_reset = True  # 不重置应用，保留应用数据和权限设置（通过terminate_app和activate_app手动重置）
    options.full_reset = False  # 不完全重置（保留应用数据）

    # 连接Appium服务器
    driver = webdriver.Remote(  # 创建webdriver实例，连接Appium服务
        command_executor='http://localhost:4730',  # Appium服务地址（根据实际端口调整）
        options=options  # 传入选项对象
    )

    # 设置隐式等待时间
    driver.implicitly_wait(5)  # 设置隐式等待5秒

    yield driver  # 返回driver供测试用例使用

    # 测试结束后关闭驱动
    if driver:  # 如果driver存在
        driver.quit()  # 关闭driver


def test_102649(setup_driver):
    """
    验证APP首页登录功能按钮
    1. 重置APP，检测登录状态，如果已登录则登出
    2. 点击登录按钮进入Sign in页面
    3. 断言页面显示用户协议和隐私政策文本
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        # 步骤1: 重置APP，进入APP页面，检测真机页面，如果已登录，执行登出操作
        current_step = "步骤1: 重置APP，检测登录状态并登出"
        print(f"🔄 {current_step}")
        try:
            # 重置APP
            caps = driver.capabilities
            app_package = caps.get("appPackage") or "com.xingmai.tech"
            driver.terminate_app(app_package)
            time.sleep(1.5)
            driver.activate_app(app_package)
            time.sleep(2)
            print("    ✅ APP已重置")

            # 检测是否已登录（查找Home/More元素）
            is_logged_in = False
            login_indicators = [
                '//android.view.View[@content-desc="Home"]',
                '//android.view.View[@content-desc="More"]',
                '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[3]/android.view.View[2]',
            ]

            for indicator in login_indicators:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, indicator)
                    for elem in elements:
                        if elem.is_displayed():
                            is_logged_in = True
                            print(f"    ✅ 检测到已登录状态: {indicator}")
                            break
                    if is_logged_in:
                        break
                except:
                    continue

            # 如果已登录，执行登出操作
            if is_logged_in:
                print("    🔄 检测到已登录，执行登出操作...")
                check_and_logout(driver)
                print("    ✅ 登出操作完成")
                time.sleep(1.5)
            else:
                print("    ℹ️ 未检测到登录状态，已在登录页面")

            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤2: 点击登录按钮，进入Sign in页面
        current_step = "步骤2: 点击登录按钮进入Sign in页面"
        print(f"🔄 {current_step}")
        try:
            sign_in_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH,
                                            '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[1]/android.widget.Button'))
            )
            sign_in_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Sign In按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 断言页面显示用户协议和隐私政策文本
        current_step = "步骤3: 断言页面显示用户协议和隐私政策文本"
        print(f"🔄 {current_step}")
        try:
            # 验证用户协议和隐私政策文本是否存在并可见
            # 在Android中，可能是TextView或其他元素
            agreement_selectors = [
                '//android.widget.TextView[@text="I have read and understood the Privacy Policy and agree to the User Agreement."]',
                '//android.widget.TextView[contains(@text, "Privacy Policy")]',
                '//android.widget.TextView[contains(@text, "User Agreement")]',
                '//android.view.View[contains(@content-desc, "Privacy Policy")]',
            ]

            agreement_found = False
            for selector in agreement_selectors:
                try:
                    agreement_text = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, selector))
                    )
                    if agreement_text.is_displayed():
                        agreement_found = True
                        text_value = agreement_text.get_attribute("text") or agreement_text.get_attribute(
                            "content-desc") or ""
                        print(f"    ✅ 找到用户协议和隐私政策文本: {text_value[:50]}...")
                        break
                except:
                    continue

            assert agreement_found, "未找到用户协议和隐私政策文本"
            print(f"✅ {current_step} - 完成，页面已显示用户协议和隐私政策文本")
        except Exception as e:
            fail_reason = f"{current_step}失败: 未找到用户协议和隐私政策文本 - {str(e)}"
            print(f"❌ {fail_reason}")
            # 尝试查找所有可见的TextView元素，用于调试
            try:
                all_textviews = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView')
                visible_texts = []
                for tv in all_textviews:
                    try:
                        if tv.is_displayed():
                            text_value = tv.get_attribute("text") or tv.get_attribute("content-desc") or ""
                            if text_value:
                                visible_texts.append(text_value[:50])
                    except:
                        continue
                print(f"    💡 当前页面可见的TextView元素: {visible_texts[:10]}")  # 显示前10个
            except:
                pass
            raise

        print("🎉 测试用例102649执行成功！")

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {str(e)}"
        print(f"\n{'=' * 60}")
        print(f"❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102649_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="102649",
            case_desc="验证APP首页登录功能按钮",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

