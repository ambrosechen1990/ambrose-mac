import pytest  # 导入pytest用于测试
import time  # 导入time用于延时
import traceback  # 导入traceback用于异常追踪
import os
import subprocess  # 导入subprocess用于执行系统命令
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


def get_adb_path():
    """获取adb路径"""
    # 尝试从环境变量获取
    adb_path = os.environ.get("ADB_PATH")
    if adb_path and os.path.exists(adb_path):
        return adb_path
    
    # 尝试常见路径
    common_paths = [
        "/usr/local/bin/adb",
        "/usr/bin/adb",
        "/opt/homebrew/bin/adb",
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
    ]
    
    for adb_path in common_paths:
        if os.path.exists(adb_path):
            return adb_path
    
    return 'adb'


def get_device_id(driver):
    """从driver获取设备ID"""
    try:
        # 尝试从capabilities获取
        udid = driver.capabilities.get('udid') or driver.capabilities.get('deviceUDID')
        if udid:
            return udid
        
        # 尝试从deviceName获取
        device_name = driver.capabilities.get('deviceName')
        if device_name:
            return device_name
        
        # 如果都获取不到，尝试获取第一个连接的设备
        adb_path = get_adb_path()
        result = subprocess.run(
            [adb_path, 'devices'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # 跳过第一行标题
                if 'device' in line:
                    device_id = line.split('\t')[0]
                    return device_id
        
        return None
    except Exception as e:
        print(f"⚠️ 获取设备ID失败: {e}")
        return None


def disable_network_android(driver):
    """
    关闭Android设备的网络连接
    使用adb命令关闭WiFi和数据连接
    """
    try:
        print("    🔄 关闭Android设备网络...")
        device_id = get_device_id(driver)
        if not device_id:
            print("    ⚠️ 无法获取设备ID，尝试使用默认方法")
            device_id = ""  # 空字符串表示使用默认设备
        
        adb_path = get_adb_path()
        adb_cmd = [adb_path]
        if device_id:
            adb_cmd.extend(['-s', device_id])
        
        # 方法1: 关闭WiFi和数据连接
        print("    📴 关闭WiFi...")
        wifi_result = subprocess.run(
            adb_cmd + ['shell', 'svc', 'wifi', 'disable'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        print("    📴 关闭移动数据...")
        data_result = subprocess.run(
            adb_cmd + ['shell', 'svc', 'data', 'disable'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if wifi_result.returncode == 0 and data_result.returncode == 0:
            print("    ✅ WiFi和移动数据已关闭")
            time.sleep(2)  # 等待网络完全关闭
            return True
        else:
            # 方法2: 使用飞行模式（备用方法）
            print("    ⚠️ 直接关闭失败，尝试使用飞行模式...")
            airplane_result = subprocess.run(
                adb_cmd + ['shell', 'settings', 'put', 'global', 'airplane_mode_on', '1'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if airplane_result.returncode == 0:
                # 需要广播飞行模式状态变化
                subprocess.run(
                    adb_cmd + ['shell', 'am', 'broadcast', '-a', 'android.intent.action.AIRPLANE_MODE', '--ez', 'state', 'true'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                print("    ✅ 已开启飞行模式（网络已关闭）")
                time.sleep(2)
                return True
            else:
                print(f"    ⚠️ 关闭网络失败: WiFi={wifi_result.returncode}, Data={data_result.returncode}, Airplane={airplane_result.returncode}")
                return False
                
    except Exception as e:
        print(f"    ⚠️ 关闭网络异常: {str(e)[:100]}")
        return False


def enable_network_android(driver):
    """
    恢复Android设备的网络连接
    使用adb命令开启WiFi和数据连接
    """
    try:
        print("    🔄 恢复Android设备网络...")
        device_id = get_device_id(driver)
        if not device_id:
            print("    ⚠️ 无法获取设备ID，尝试使用默认方法")
            device_id = ""  # 空字符串表示使用默认设备
        
        adb_path = get_adb_path()
        adb_cmd = [adb_path]
        if device_id:
            adb_cmd.extend(['-s', device_id])
        
        # 方法1: 先关闭飞行模式（如果开启了）
        print("    📶 关闭飞行模式...")
        airplane_result = subprocess.run(
            adb_cmd + ['shell', 'settings', 'put', 'global', 'airplane_mode_on', '0'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if airplane_result.returncode == 0:
            # 广播飞行模式状态变化
            subprocess.run(
                adb_cmd + ['shell', 'am', 'broadcast', '-a', 'android.intent.action.AIRPLANE_MODE', '--ez', 'state', 'false'],
                capture_output=True,
                text=True,
                timeout=10
            )
            time.sleep(1)
        
        # 方法2: 开启WiFi和数据连接
        print("    📶 开启WiFi...")
        wifi_result = subprocess.run(
            adb_cmd + ['shell', 'svc', 'wifi', 'enable'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        print("    📶 开启移动数据...")
        data_result = subprocess.run(
            adb_cmd + ['shell', 'svc', 'data', 'enable'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if wifi_result.returncode == 0 or data_result.returncode == 0:
            print("    ✅ 网络已恢复")
            time.sleep(3)  # 等待网络完全恢复
            return True
        else:
            print(f"    ⚠️ 恢复网络失败: WiFi={wifi_result.returncode}, Data={data_result.returncode}")
            return False
                
    except Exception as e:
        print(f"    ⚠️ 恢复网络异常: {str(e)[:100]}")
        return False


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


def test_102779(setup_driver):
    """
    验证手机网络关闭时，APP用户登录
    1. 重置APP，检测是否已登录，如果已登录则登出
    2. 在Sign In页面，关闭手机网络
    3. 点击登录按钮，进入Sign in页面
    4. 输入邮箱和密码，勾选协议
    5. 点击登录按钮，验证网络错误提示
    6. 重启网络
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    network_disabled = False

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

        # 步骤2: Sign In页面，执行关闭手机网络操作
        current_step = "步骤2: 在Sign In页面关闭手机网络"
        print(f"🔄 {current_step}")
        try:
            # 尝试确认当前在登录相关页面（尽量兼容多种UI写法），但即使未找到也不阻塞关网逻辑
            try:
                sign_in_or_up_found = False
                sign_btn_selectors = [
                    '//android.widget.Button[@text="Sign In"]',
                    '//android.widget.Button[contains(@text,"Sign In")]',
                    '//android.view.View[@content-desc="Sign In"]',
                    '//android.view.View[contains(@content-desc,"Sign In")]',
                    '//android.widget.TextView[@text="Sign In"]',
                    '//android.widget.TextView[contains(@text,"Sign In")]',
                    '//android.widget.Button[@text="Sign Up"]',
                    '//android.widget.Button[contains(@text,"Sign Up")]',
                    '//android.view.View[@content-desc="Sign Up"]',
                    '//android.view.View[contains(@content-desc,"Sign Up")]',
                    '//android.widget.TextView[@text="Sign Up"]',
                    '//android.widget.TextView[contains(@text,"Sign Up")]',
                ]
                for selector in sign_btn_selectors:
                    try:
                        btn = WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located((AppiumBy.XPATH, selector))
                        )
                        if btn.is_displayed():
                            txt = btn.get_attribute("text") or btn.get_attribute("content-desc") or ""
                            print(f"    ✅ 检测到登录相关按钮: {txt}")
                            sign_in_or_up_found = True
                            break
                    except Exception:
                        continue
                if not sign_in_or_up_found:
                    print("    ⚠️ 未显式找到 Sign In/Sign Up 按钮，可能UI有变化，仍继续关闭网络")
            except Exception as e_check:
                print(f"    ⚠️ 检查登录页面元素时出错（可忽略）: {e_check}")

            # 关闭手机网络（关键步骤）
            network_disabled = disable_network_android(driver)
            if network_disabled:
                print(f"✅ {current_step} - 完成，网络已关闭")
            else:
                print(f"⚠️ {current_step} - 关闭网络失败")
                raise Exception("关闭网络失败")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 点击登录按钮，进入Sign in页面
        current_step = "步骤3: 点击登录按钮进入Sign in页面"
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

        # 步骤4: 点击邮箱框，输入邮箱
        current_step = "步骤4: 点击邮箱框，输入邮箱"
        print(f"🔄 {current_step}")
        try:
            email_address = "haoc51888@gmail.com"
            # 先点击输入框区域激活输入
            email_input_area = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[1]/android.view.View[1]'))
            )
            email_input_area.click()
            time.sleep(0.8)  # 等待键盘弹出
            
            # 找到真正的EditText元素
            email_edit_text = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[1]'))
            )
            
            # 尝试使用set_value方法（Appium特有，适用于Compose UI）
            try:
                email_edit_text.set_value(email_address)
                print(f"    ✅ 使用set_value方法输入邮箱: {email_address}")
            except:
                # 如果set_value失败，尝试clear + send_keys
                try:
                    email_edit_text.clear()
                    email_edit_text.send_keys(email_address)
                    print(f"    ✅ 使用send_keys方法输入邮箱: {email_address}")
                except Exception as e2:
                    # 如果还是失败，尝试使用ADB输入
                    print(f"    ⚠️ 常规输入方法失败，尝试使用ADB输入: {e2}")
                    import subprocess
                    subprocess.run(['adb', 'shell', 'input', 'text', email_address.replace('@', '\\@').replace('.', '\\.')], 
                                 capture_output=True, timeout=5)
                    print(f"    ✅ 使用ADB输入邮箱: {email_address}")
            
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 点击密码框，输入密码
        current_step = "步骤5: 点击密码框，输入密码"
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
            
            print(f"    ✅ 密码输入完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 收起输入键盘
        current_step = "步骤6: 收起输入键盘"
        print(f"🔄 {current_step}")
        try:
            # 尝试按返回键收起键盘
            driver.press_keycode(4)  # KEYCODE_BACK
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            print(f"    ⚠️ 收起键盘失败: {e}，继续执行")

        # 步骤7: 点击协议勾选框
        current_step = "步骤7: 点击协议勾选框"
        print(f"🔄 {current_step}")
        try:
            check_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="checkbox"]'))
            )
            check_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 点击登录按钮，断言页面跳出弹框
        current_step = "步骤8: 点击登录按钮，验证网络错误提示"
        print(f"🔄 {current_step}")
        try:
            # 点击登录按钮
            login_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="next"]'))
            )
            login_btn.click()
            print("    ✅ 已点击登录按钮")
            time.sleep(3)  # 等待网络错误提示出现

            # 验证网络错误提示
            error_text = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, '//android.widget.TextView[@text="Network connection error, please check"]'))
            )

            # 验证提示信息存在且可见
            assert error_text.is_displayed(), "网络错误提示信息存在但不可见"
            error_message = error_text.get_attribute("text")
            print(f"    📝 错误提示内容: {error_message}")

            # 断言提示信息正确
            assert error_message == "Network connection error, please check", \
                f"错误提示信息不正确，期望'Network connection error, please check'，实际显示: {error_message}"

            print(f"✅ {current_step} - 完成，网络错误提示显示正确: {error_message}")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102779执行成功！")
        time.sleep(1)
        
        # 步骤9: 重启网络
        current_step = "步骤9: 重启网络"
        print(f"🔄 {current_step}")
        try:
            enable_network_android(driver)
            print(f"✅ {current_step} - 完成，网络已恢复")
            network_disabled = False  # 标记网络已恢复
        except Exception as e:
            print(f"⚠️ {current_step}失败: {e}")
            print("💡 请手动恢复设备的WiFi和移动数据")

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
        save_failure_screenshot(driver, "test_102779_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        # 如果测试失败或网络未恢复，尝试恢复网络连接
        if network_disabled:
            try:
                print("🔄 测试结束，尝试恢复网络连接...")
                enable_network_android(driver)
                print("✅ 网络连接已恢复")
            except Exception as e:
                print(f"⚠️ 恢复网络失败: {e}")
                print("💡 请手动恢复设备的WiFi和移动数据")

        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="102779",
            case_desc="验证手机网络关闭时，APP用户登录",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

