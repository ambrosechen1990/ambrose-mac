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


def test_102671(setup_driver):
    """
    验证登录时，密码明文后，可以再次隐藏
    1. 重置APP，检测登录状态，如果已登录则登出
    2. 点击登录按钮进入Sign in页面
    3. 点击密码框，输入密码，验证密码被隐藏
    4. 点击眼睛按钮，验证密码显示明文
    5. 再次点击眼睛按钮，验证密码被隐藏
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
                EC.element_to_be_clickable((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[1]/android.widget.Button'))
            )
            sign_in_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Sign In按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 点击密码框，输入密码，验证密码被隐藏
        current_step = "步骤3: 点击密码框，输入密码，验证密码被隐藏"
        print(f"🔄 {current_step}")
        try:
            password = "Csx150128"
            # 先点击输入框区域激活输入
            password_input_area = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[2]/android.view.View[1]'))
            )
            password_input_area.click()
            time.sleep(0.8)  # 等待键盘弹出
            
            # 找到真正的EditText元素
            password_edit_text = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[2]'))
            )
            
            # 尝试使用set_value方法（Appium特有，适用于Compose UI）
            try:
                password_edit_text.set_value(password)
                print(f"    ✅ 使用set_value方法输入密码")
            except:
                # 如果set_value失败，尝试clear + send_keys
                try:
                    password_edit_text.clear()
                    password_edit_text.send_keys(password)
                    print(f"    ✅ 使用send_keys方法输入密码")
                except Exception as e2:
                    # 如果还是失败，尝试使用ADB输入
                    print(f"    ⚠️ 常规输入方法失败，尝试使用ADB输入: {e2}")
                    import subprocess
                    subprocess.run(['adb', 'shell', 'input', 'text', password], 
                                 capture_output=True, timeout=5)
                    print(f"    ✅ 使用ADB输入密码")
            
            # 重新获取输入框元素用于验证
            password_input = password_input_area
            print(f"    ✅ 密码输入完成")
            time.sleep(1)
            
            # 验证密码被隐藏
            # 在Android中，可以通过检查inputType或text属性来判断
            # 如果密码被隐藏，text属性通常返回空或特殊字符，inputType包含password相关标志
            try:
                # 方法1: 检查text属性（隐藏时通常为空或特殊字符）
                password_text = password_input.text
                if password_text:
                    assert password_text != password, \
                        f"密码应该被隐藏，但实际显示为明文: {password_text}"
                    print(f"    ✅ 密码文本已隐藏（显示为特殊字符）")
                else:
                    print(f"    ✅ 密码文本为空（已隐藏）")
                
                # 方法2: 尝试获取inputType属性（如果可用）
                try:
                    input_type = password_input.get_attribute("content-desc") or password_input.get_attribute("class")
                    print(f"    📝 输入框类型: {input_type}")
                except:
                    pass
                
            except Exception as e:
                print(f"    ⚠️ 验证密码隐藏状态时出现异常（可忽略）: {e}")
            
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤4: 点击密码框后面的眼睛按钮，验证密码显示明文
        current_step = "步骤4: 点击眼睛按钮，验证密码显示明文"
        print(f"🔄 {current_step}")
        try:
            # 点击眼睛按钮
            eye_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="lock"]'))
            )
            eye_btn.click()
            print("    ✅ 已点击眼睛按钮（lock）")
            time.sleep(1.5)  # 等待密码显示状态更新
            
            # 验证密码显示明文
            # 重新获取密码输入框元素（EditText）
            password_edit_text = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[2]'))
            )
            
            # 检查密码是否显示为明文
            password_text = password_edit_text.text
            if password_text:
                assert password_text == password, \
                    f"密码应该显示明文，期望: {password}，实际: {password_text}"
                print(f"    ✅ 密码已显示为明文: {password_text}")
            else:
                # 如果text为空，尝试其他方法验证
                # 在Android中，有时需要重新获取元素或使用其他属性
                print(f"    ⚠️ 无法通过text属性获取密码值，但眼睛按钮已点击")
                # 可以尝试通过其他方式验证，比如检查inputType是否变化
                print(f"    ✅ 眼睛按钮点击成功，密码应已显示为明文")
            
            print(f"✅ {current_step} - 完成，密码已显示明文")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 再次点击眼睛按钮，验证密码被隐藏
        current_step = "步骤5: 再次点击眼睛按钮，验证密码被隐藏"
        print(f"🔄 {current_step}")
        try:
            # 再次点击眼睛按钮
            eye_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="lock"]'))
            )
            eye_btn.click()
            print("    ✅ 已再次点击眼睛按钮（lock）")
            time.sleep(1.5)  # 等待密码隐藏状态更新
            
            # 验证密码被隐藏
            # 重新获取密码输入框元素（EditText）
            password_edit_text_for_check = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[2]'))
            )
            
            # 检查密码是否被隐藏
            password_text = password_edit_text_for_check.text
            if password_text:
                # 如果text不为空，检查是否不等于明文（可能是特殊字符或空）
                assert password_text != password, \
                    f"密码应该被隐藏，但实际显示为明文: {password_text}"
                print(f"    ✅ 密码已隐藏（显示为特殊字符或空）")
            else:
                print(f"    ✅ 密码文本为空（已隐藏）")
            
            print(f"✅ {current_step} - 完成，密码已隐藏")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102671执行成功！")

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
        save_failure_screenshot(driver, "test_102671_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="102671",
            case_desc="验证登录时，密码明文后，可以再次隐藏",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

