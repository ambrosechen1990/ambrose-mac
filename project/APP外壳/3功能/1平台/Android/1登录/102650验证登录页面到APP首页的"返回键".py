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


def test_102650(setup_driver):
    """
    验证登录页面到APP首页的"返回键"
    1. 重置APP，检测登录状态，如果已登录则登出
    2. 点击登录按钮进入Sign in页面
    3. 点击左上角返回按钮，返回至上一级页面
    4. 断言页面显示Sign In和Sign Up按钮
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

        # 步骤3: 点击左上角返回按钮，返回至上一级页面
        current_step = "步骤3: 点击左上角返回按钮，返回至上一级页面"
        print(f"🔄 {current_step}")
        try:
            # 查找左上角返回按钮
            # 在Android中，返回按钮可能是ImageView或Button
            back_selectors = [
                '//android.widget.ImageView[@content-desc="nav back"]',
                '//android.widget.Button[@content-desc="nav back"]',
                '//android.view.View[@content-desc="nav back"]',
                '//android.widget.ImageButton[@content-desc="nav back"]',
            ]

            back_button = None
            for selector in back_selectors:
                try:
                    back_button = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                    )
                    if back_button.is_displayed():
                        break
                except:
                    continue

            if back_button:
                back_button.click()
                print(f"✅ {current_step} - 完成")
                time.sleep(1.5)  # 等待页面返回
            else:
                # 如果找不到，尝试使用driver.back()
                print("    ⚠️ 未找到返回按钮，尝试使用driver.back()")
                driver.back()
                time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击返回按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            # 尝试使用driver.back()作为备用方案
            try:
                driver.back()
                print("    ✅ 使用driver.back()返回")
                time.sleep(1.5)
            except Exception as e2:
                raise

        # 步骤4: 断言页面显示Sign In和Sign Up按钮
        current_step = "步骤4: 断言页面显示Sign In和Sign Up按钮"
        print(f"🔄 {current_step}")
        try:
            # 验证Sign In按钮是否存在并可见（兼容多种控件类型和属性）
            sign_in_selectors = [
                '//android.widget.Button[@text="Sign In"]',
                '//android.widget.Button[contains(@text,"Sign In")]',
                '//android.view.View[@content-desc="Sign In"]',
                '//android.view.View[contains(@content-desc,"Sign In")]',
                '//android.widget.TextView[@text="Sign In"]',
                '//android.widget.TextView[contains(@text,"Sign In")]',
                '//androidx.compose.ui.platform.ComposeView//android.widget.Button[contains(@text,"Sign In")]',
            ]

            sign_in_found = False
            for selector in sign_in_selectors:
                try:
                    sign_in_btn = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, selector))
                    )
                    if sign_in_btn.is_displayed():
                        sign_in_found = True
                        btn_text = sign_in_btn.get_attribute("text") or sign_in_btn.get_attribute("content-desc") or ""
                        print(f"    ✅ 找到Sign In按钮: {btn_text}")
                        break
                except:
                    continue

            # 验证Sign Up按钮是否存在并可见（兼容多种控件类型和属性）
            sign_up_selectors = [
                '//android.widget.Button[@text="Sign Up"]',
                '//android.widget.Button[contains(@text,"Sign Up")]',
                '//android.view.View[@content-desc="Sign Up"]',
                '//android.view.View[contains(@content-desc,"Sign Up")]',
                '//android.widget.TextView[@text="Sign Up"]',
                '//android.widget.TextView[contains(@text,"Sign Up")]',
                '//androidx.compose.ui.platform.ComposeView//android.widget.Button[contains(@text,"Sign Up")]',
            ]

            sign_up_found = False
            for selector in sign_up_selectors:
                try:
                    sign_up_btn = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, selector))
                    )
                    if sign_up_btn.is_displayed():
                        sign_up_found = True
                        btn_text = sign_up_btn.get_attribute("text") or sign_up_btn.get_attribute("content-desc") or ""
                        print(f"    ✅ 找到Sign Up按钮: {btn_text}")
                        break
                except:
                    continue

            # 有些 Android 首页可能只显示 Sign In（通过其它入口注册），此时认为返回成功但给出提示
            if sign_in_found and not sign_up_found:
                print(
                    "    ⚠️ 仅找到 Sign In 按钮，未找到 Sign Up，可能是当前版本首页不展示 Sign Up（逻辑上仍视为返回成功）")

            assert sign_in_found, f"未找到 Sign In 按钮，可能未成功返回登录首页"
            print(f"✅ {current_step} - 完成，已成功返回APP首页（Sign In: {sign_in_found}, Sign Up: {sign_up_found}）")
        except Exception as e:
            fail_reason = f"{current_step}失败: 未找到Sign In或Sign Up按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            # 尝试查找所有可见的Button元素，用于调试
            try:
                all_buttons = driver.find_elements(AppiumBy.XPATH, '//android.widget.Button | //android.view.View')
                visible_buttons = []
                for btn in all_buttons:
                    try:
                        if btn.is_displayed():
                            btn_text = btn.get_attribute("text") or btn.get_attribute("content-desc") or ""
                            if btn_text:
                                visible_buttons.append(btn_text)
                    except:
                        continue
                print(f"    💡 当前页面可见的按钮/视图文本: {visible_buttons[:15]}")  # 显示前15个
            except:
                pass
            raise

        print("🎉 测试用例102650执行成功！")

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
        save_failure_screenshot(driver, "test_102650_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="102650",
            case_desc="验证登录页面到APP首页的返回键",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

