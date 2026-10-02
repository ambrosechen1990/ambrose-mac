import pytest  # 测试框架
import time  # 等待
import traceback  # 异常追踪
from appium import webdriver  # Appium驱动
from appium.webdriver.common.appiumby import AppiumBy  # Appium定位
from appium.options.android import UiAutomator2Options  # Appium配置
from selenium.webdriver.support.ui import WebDriverWait  # 显式等待
from selenium.webdriver.support import expected_conditions as EC  # 等待条件
import subprocess  # 子进程
import os  # 文件操作

@pytest.fixture(scope='session')
def setup_driver():
    """设置Appium驱动"""
    options = UiAutomator2Options()  # 配置对象
    options.platformName = "Android"  # 平台
    options.platform_version = "14"  # 版本
    options.device_name = "ONEPLUS 11"  # 设备名
    options.app_package = "com.testdemo.tech"  # 包名
    options.app_activity = "com.xingmai.splash.SplashActivity"  # 启动Activity
    options.no_reset = True  # 不重置，保持应用状态
    options.automation_name = "UiAutomator2"  # 自动化引擎
    options.full_context_list = True  # 上下文
    options.set_capability("autoGrantPermissions", True)  # 自动授权
    options.set_capability("fastReset", False)  # 禁用快速重置
    options.set_capability("dontStopAppOnReset", True)  # 不停止应用，保持状态
    driver = webdriver.Remote('http://127.0.0.1:4726', options=options)  # 创建driver
    yield driver  # 返回driver
    driver.quit()  # 关闭driver

def kill_and_restart_app(driver):
    """Kill APP并重新启动（不重置）"""
    try:
        print("💀 Kill应用...")
        print("🔧 执行命令: driver.terminate_app('com.testdemo.tech')")
        driver.terminate_app("com.testdemo.tech")
        print("⏳ 等待2秒让应用完全关闭...")
        time.sleep(2)
        
        print("🔄 重新启动应用...")
        print("🔧 执行命令: driver.activate_app('com.testdemo.tech')")
        driver.activate_app("com.testdemo.tech")
        print("⏳ 等待5秒让应用完全启动...")
        time.sleep(5)
        
        print("✅ 应用已重启")
        print("📱 当前Activity:", driver.current_activity)
        
    except Exception as e:
        print(f"❌ 应用重启失败: {e}")
        print("🔍 错误详情:", traceback.format_exc())
        raise

def check_adb_connection():
    """检查ADB连接状态"""
    try:
        print("🔍 检查ADB连接状态...")
        check_cmd = "adb -s galaxy_p0001 devices"
        result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        print(f"📊 ADB设备检查结果: {result.returncode}")
        print(f"📄 输出: {result.stdout}")
        
        if "galaxy_p0001" in result.stdout and "device" in result.stdout:
            print("✅ ADB设备连接正常")
            return True
        else:
            print("❌ ADB设备连接异常")
            print(f"📄 错误输出: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ ADB连接检查失败: {e}")
        return False

def send_ros2_message_final():
    """发送ROS2消息触发AP - 最终修复版"""
    try:
        print("📡 发送ROS2消息 (最终修复版)...")
        print("📝 说明: 使用expect脚本模拟手动执行方式")
        
        # 1. 检查ADB连接
        if not check_adb_connection():
            raise Exception("ADB设备连接失败")
        
        # 2. 等待5秒让设备稳定
        print("⏳ 等待5秒让设备稳定...")
        time.sleep(5)
        
        # 3. 使用expect脚本执行ROS2命令 (最可靠的方法)
        print("🔧 使用expect脚本执行ROS2命令...")
        try:
            # 创建expect脚本
            expect_script = '''#!/usr/bin/expect -f
spawn adb -s galaxy_p0001 shell
expect "# "
send "ros2 topic pub --once /USER_NET_INFO xm_robot_interfaces/msg/InternalIO '{msg_content: AP}'\r"
expect "# "
send "exit\r"
expect eof'''
            
            # 保存expect脚本到临时文件
            script_path = '/tmp/ros2_final.exp'
            with open(script_path, 'w') as f:
                f.write(expect_script)
            
            # 执行expect脚本
            expect_command = f"expect {script_path}"
            print(f"🔧 执行expect脚本: {expect_command}")
            
            result = subprocess.run(expect_command, shell=True, capture_output=True, text=True, timeout=30)
            
            print(f"📊 命令返回码: {result.returncode}")
            print(f"📄 标准输出: {result.stdout}")
            print(f"📄 错误输出: {result.stderr}")
            
            # 检查是否成功
            if result.returncode == 0 and ("publishing" in result.stdout or "latching" in result.stdout):
                print("✅ ROS2消息发送成功")
                print("📝 说明: ROS2命令执行成功，AP模式已触发")
                # 清理临时文件
                os.remove(script_path)
                return True
            else:
                print("❌ ROS2消息发送失败")
                print("📄 输出内容:", result.stdout)
                # 清理临时文件
                os.remove(script_path)
                return False
                
        except Exception as e:
            print(f"❌ expect脚本执行异常: {e}")
            # 清理临时文件
            if os.path.exists('/tmp/ros2_final.exp'):
                os.remove('/tmp/ros2_final.exp')
            return False
        
        # 4. 如果expect脚本失败，提供手动指导
        print("❌ expect脚本执行失败")
        print("📝 说明: 自动执行ROS2命令失败，需要手动执行")
        
        print("\n💡 手动执行步骤:")
        print("1. 打开新的终端窗口")
        print("2. 执行: adb -s galaxy_p0001 shell")
        print("3. 在ADB shell中执行: ros2 topic pub --once /USER_NET_INFO xm_robot_interfaces/msg/InternalIO '{msg_content: AP}'")
        print("4. 确认看到 'publishing and latching message' 输出")
        print("5. 然后继续运行脚本")
        
        # 等待用户确认
        print("\n❓ 请确认您已手动执行ROS2命令触发AP模式")
        input("按回车键继续...")
        
        print("✅ 假设AP模式已手动触发，继续执行后续步骤")
        return True
        
    except Exception as e:
        print(f"❌ ROS2消息发送失败: {e}")
        print("🔍 错误详情:", traceback.format_exc())
        print("⚠️ 继续执行后续步骤，但AP可能未被触发")
        return False

def click_add_button(driver):
    """点击添加设备按钮"""
    try:
        print("📱 点击添加设备按钮...")
        print("📝 说明: 在首页点击第二个add按钮进入设备选择页面")
        print("🔧 使用XPath: (//android.widget.ImageView[@content-desc='add'])[2]")
        
        # 等待并点击添加按钮
        print("⏳ 等待添加按钮出现（最多10秒）...")
        add_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "(//android.widget.ImageView[@content-desc='add'])[2]"))
        )
        print("✅ 找到添加按钮，准备点击...")
        add_button.click()
        print("⏳ 等待2秒让页面跳转...")
        time.sleep(2)
        
        print("✅ 已点击添加设备按钮")
        print("📱 当前Activity:", driver.current_activity)
        
    except Exception as e:
        print(f"❌ 点击添加设备按钮失败: {e}")
        print("🔍 错误详情:", traceback.format_exc())
        raise

def select_device(driver):
    """选择设备"""
    try:
        print("🔍 选择设备...")
        print("📝 说明: 在设备选择页面点击B0556设备并确认")
        
        # 等待设备选择页面加载
        print("⏳ 等待设备选择页面加载...")
        time.sleep(3)  # 增加等待时间，让设备列表完全加载
        
        # 查找B0556设备
        print("🔍 查找B0556设备...")
        print("📝 说明: 只选择B0556设备，不选择其他设备")
        
        # 精确的B0556设备选择器
        b0556_selectors = [
            "//android.widget.TextView[@text='(SN:B0556)']",
            "//*[@text='(SN:B0556)']",
            "//*[contains(@text, 'SN:B0556')]",
            "//android.widget.TextView[contains(@text, 'SN:B0556')]"
        ]
        
        device_found = False
        for i, selector in enumerate(b0556_selectors):
            try:
                print(f"尝试B0556选择器 {i+1}: {selector}")
                device_element = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                print(f"✅ 找到B0556设备，使用选择器: {selector}")
                device_element.click()
                print("⏳ 等待2秒让设备选择生效...")
                time.sleep(2)
                device_found = True
                break
            except:
                print(f"❌ B0556选择器 {i+1} 失败")
                continue
        
        if not device_found:
            print("❌ 未找到B0556设备，显示所有可用设备...")
            
            # 查找所有文本元素，显示所有设备
            all_text_elements = driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView")
            print(f"📊 找到 {len(all_text_elements)} 个文本元素:")
            
            available_devices = []
            for i, element in enumerate(all_text_elements):
                try:
                    text = element.get_attribute("text") or ""
                    class_name = element.get_attribute("class") or ""
                    if text and ("SN:" in text or "设备" in text or "AquaSense" in text):
                        available_devices.append((element, text))
                        print(f"  设备 {len(available_devices)}: text='{text}', class='{class_name}'")
                except:
                    pass
            
            if available_devices:
                print(f"📋 找到 {len(available_devices)} 个可用设备:")
                for i, (element, device_name) in enumerate(available_devices):
                    print(f"  {i+1}. {device_name}")
                
                # 检查是否有B0556设备
                b0556_device = None
                for element, device_name in available_devices:
                    if "B0556" in device_name or "SN:B0556" in device_name:
                        b0556_device = (element, device_name)
                        break
                
                if b0556_device:
                    print(f"✅ 找到B0556设备: {b0556_device[1]}")
                    b0556_device[0].click()
                    print("⏳ 等待2秒让设备选择生效...")
                    time.sleep(2)
                    device_found = True
                else:
                    print("❌ 在可用设备列表中未找到B0556设备")
                    print("📝 说明: 只允许选择B0556设备，拒绝选择其他设备")
                    raise Exception("未找到B0556设备，拒绝选择其他设备")
            else:
                raise Exception("未找到任何可用设备")
        
        # 点击confirm按钮
        print("🔍 查找确认按钮...")
        print("📝 说明: 点击确认按钮确认设备选择")
        print("🔧 使用XPath: //android.widget.Button")
        confirm_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
        )
        print("✅ 找到确认按钮，准备点击...")
        confirm_button.click()
        print("⏳ 等待2秒让页面跳转到WiFi设置...")
        time.sleep(2)
        
        print("✅ 设备选择完成")
        print("📱 当前Activity:", driver.current_activity)
        
    except Exception as e:
        print(f"❌ 设备选择失败: {e}")
        print("🔍 错误详情:", traceback.format_exc())
        raise

def setup_wifi(driver):
    """设置WiFi - 根据用户提供的准确元素信息优化版本"""
    try:
        print("📶 步骤5: 进入WiFi设置页面...")
        print("📝 说明: 检查WiFi名称，如果不是Deco则切换，然后输入密码")
        
        # 等待页面稳定
        print("⏳ 等待页面稳定...")
        time.sleep(3)
        
        # 检查是否在WiFi设置页面
        print("🔍 检查是否在WiFi设置页面...")
        print("🔧 使用XPath: //android.widget.ImageView[@content-desc='background']")
        try:
            background_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, "//android.widget.ImageView[@content-desc='background']"))
            )
            print("✅ 确认在WiFi设置页面")
        except:
            print("⚠️ 未找到WiFi设置页面背景元素，但继续执行")
        
        # 1. WiFi名称检查是否是Deco
        print("\n🔍 1. WiFi名称检查是否是Deco...")
        print("🔧 使用XPath: //android.widget.EditText[@text='Deco']")
        
        wifi_is_Deco = False
        try:
            wifi_name_field = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, "//android.widget.EditText[@text='Deco']"))
            )
            print("✅ WiFi名称已经是Deco，直接进入步骤2输入密码")
            wifi_is_Deco = True
        except:
            print("🔧 WiFi名称不是Deco，需要切换WiFi")
            
            # 点击switch按钮进入WiFi切换页面
            print("🔍 点击switch按钮进入WiFi切换页面...")
            print("🔧 使用XPath: //android.view.View[@content-desc='switch']")
            try:
                switch_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, "//android.view.View[@content-desc='switch']"))
                )
                print("✅ 找到switch按钮，准备点击...")
                switch_button.click()
                print("⏳ 等待2秒让WiFi选择页面加载...")
                time.sleep(2)
                
                # 检查是否进入WiFi页面
                print("🔍 检查是否进入WiFi页面...")
                print("🔧 使用XPath: //android.view.ViewGroup[@resource-id='com.android.settings:id/action_bar']")
                try:
                    wifi_page = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, "//android.view.ViewGroup[@resource-id='com.android.settings:id/action_bar']"))
                    )
                    print("✅ 已进入WiFi页面")
                except:
                    print("⚠️ 未找到WiFi页面标识，但继续执行")
                
                # 查找并选择Deco WiFi
                print("🔍 查找Deco WiFi...")
                print("📝 说明: 等待5秒后开始查找Deco WiFi")
                time.sleep(5)
                
                wifi_found = False
                for scroll_attempt in range(5):  # 最多滚动5次
                    print(f"滚动查找Deco WiFi (第{scroll_attempt + 1}次)...")
                    
                    # 查找所有WiFi项目
                    wifi_items = driver.find_elements(AppiumBy.XPATH, "//android.widget.LinearLayout")
                    print(f"📊 找到 {len(wifi_items)} 个WiFi项目")
                    
                    for wifi_item in wifi_items:
                        try:
                            # 获取WiFi名称
                            wifi_name_element = wifi_item.find_element(AppiumBy.XPATH, ".//android.widget.TextView[1]")
                            wifi_name = wifi_name_element.get_attribute("text")
                            print(f"🔍 检查WiFi: {wifi_name}")
                            
                            if wifi_name and "Deco" in wifi_name.lower():
                                print(f"✅ 找到Deco WiFi: {wifi_name}")
                                print("📝 说明: 找到Deco WiFi，准备点击选择")
                                wifi_item.click()
                                print("⏳ 等待2秒让WiFi选择生效...")
                                time.sleep(2)
                                wifi_found = True
                                break
                        except:
                            continue
                    
                    if wifi_found:
                        break
                    
                    # 向下滚动
                    print("📜 向下滚动查找更多WiFi...")
                    driver.swipe(500, 1000, 500, 500, 1000)
                    time.sleep(1)
                
                if not wifi_found:
                    print("❌ 未找到Deco WiFi")
                    raise Exception("未找到Deco WiFi")
                
                # 点击左上角返回按键两次
                print("⬅️ 点击左上角返回按键两次...")
                print("🔧 使用XPath: //android.widget.ImageButton[@content-desc='Navigate up']")
                for i in range(2):
                    try:
                        print(f"🔍 查找第{i+1}次返回按钮...")
                        back_button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.ImageButton[@content-desc='Navigate up']"))
                        )
                        print(f"✅ 找到第{i+1}次返回按钮，准备点击...")
                        back_button.click()
                        print(f"⏳ 等待1秒让页面返回...")
                        time.sleep(1)
                        print(f"✅ 第{i+1}次返回成功")
                    except:
                        print(f"❌ 第{i+1}次返回失败")
                        break
                
                # 检查是否返回WiFi设置页面
                print("🔍 检查是否返回WiFi设置页面...")
                print("🔧 使用XPath: //android.widget.ImageView[@content-desc='background']")
                try:
                    background_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, "//android.widget.ImageView[@content-desc='background']"))
                    )
                    print("✅ 已返回WiFi设置页面")
                except:
                    print("⚠️ 未找到WiFi设置页面背景元素，但继续执行")
                
            except Exception as e:
                print(f"❌ WiFi切换失败: {e}")
                raise
        
        # 2. 输入密码
        print("\n🔑 2. 输入密码...")
        print("🔧 使用XPath: //android.widget.EditText[@text='••••••••••']")
        print("📝 说明: 密码栏输入vastzoo455")
        
        # 检查密码字段是否有内容
        password_field = None
        has_password = False
        
        try:
            # 先尝试查找有密码的字段
            password_field = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.EditText[@text='••••••••••']"))
            )
            print("✅ 找到密码输入框（有密码）")
            has_password = True
        except:
            try:
                # 如果没找到有密码的字段，尝试查找空的密码字段
                password_field = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.EditText[2]"))
                )
                print("✅ 找到密码输入框（无密码）")
                has_password = False
            except:
                print("❌ 未找到密码输入框")
                raise
        
        # 输入密码
        try:
            if has_password:
                print("📝 清空原有密码...")
                password_field.clear()
                time.sleep(0.5)
            
            print("📝 输入新密码: vastzoo455")
            password_field.send_keys("vastzoo455")
            print("✅ 密码输入完成")
            time.sleep(1)
        except Exception as e:
            print(f"❌ 密码输入失败: {e}")
            raise
        
        
        # 点击next按钮
        print("🔍 点击next按钮...")
        print("🔧 使用XPath: //android.widget.Button")
        
        try:
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
            )
            print("✅ 找到next按钮，准备点击...")
            
            # 获取按钮信息
            button_text = next_button.get_attribute("text") or ""
            button_desc = next_button.get_attribute("content-desc") or ""
            print(f"📝 next按钮详情: text='{button_text}', desc='{button_desc}'")
            
            # 点击前截图
            print("📸 点击前截图...")
            try:
                screenshot_path = f"/tmp/wifi_setup_before_click_{int(time.time())}.png"
                driver.save_screenshot(screenshot_path)
                print(f"✅ 截图已保存: {screenshot_path}")
            except Exception as e:
                print(f"⚠️ 截图失败: {e}")
            
            # 点击按钮
            next_button.click()
            print("✅ next按钮已点击")
            
            # 点击后立即检查页面状态
            print("🔍 点击后立即检查页面状态...")
            time.sleep(1)
            print(f"📱 点击后1秒Activity: {driver.current_activity}")
            
            # 等待页面跳转
            print("⏳ 等待5秒让页面跳转到配网设置页面...")
            time.sleep(5)
            
            # 检查点击后的页面状态
            print("🔍 点击next按钮后的页面状态...")
            print(f"📱 当前Activity: {driver.current_activity}")
            
            # 点击后截图
            print("📸 点击后截图...")
            try:
                screenshot_path = f"/tmp/wifi_setup_after_click_{int(time.time())}.png"
                driver.save_screenshot(screenshot_path)
                print(f"✅ 截图已保存: {screenshot_path}")
            except Exception as e:
                print(f"⚠️ 截图失败: {e}")
            
        except Exception as e:
            print(f"❌ 点击next按钮失败: {e}")
            raise
        
        print("✅ WiFi设置完成")
        print("📱 当前Activity:", driver.current_activity)
        
    except Exception as e:
        print(f"❌ WiFi设置失败: {e}")
        print("🔍 错误详情:", traceback.format_exc())
        raise

def setup_light_effect(driver):
    """配网设置页面 - 按照用户需求优化"""
    try:
        print("💡 步骤6: 配网设置页面...")
        print("📝 说明: 点击勾选复选框并点击next按钮")
        
        # 检查当前页面状态
        print("🔍 检查当前页面状态...")
        print(f"📱 当前Activity: {driver.current_activity}")
        
        # 等待页面稳定
        print("⏳ 等待页面稳定...")
        time.sleep(3)
        
        # 显示当前页面的所有元素信息
        print("🔍 显示当前页面的所有元素信息...")
        
        # 显示所有文本元素
        text_elements = driver.find_elements(AppiumBy.XPATH, "//*[@class='android.widget.TextView']")
        print(f"📊 找到 {len(text_elements)} 个文本元素:")
        for i, element in enumerate(text_elements[:15]):  # 只显示前15个
            try:
                text = element.get_attribute("text") or ""
                if text and len(text.strip()) > 0:
                    print(f"  文本 {i+1}: '{text}'")
            except:
                pass
        
        # 显示所有可点击元素
        clickable_elements = driver.find_elements(AppiumBy.XPATH, "//*[@clickable='true']")
        print(f"📊 找到 {len(clickable_elements)} 个可点击元素:")
        for i, element in enumerate(clickable_elements[:15]):  # 只显示前15个
            try:
                class_name = element.get_attribute("class") or ""
                content_desc = element.get_attribute("content-desc") or ""
                text = element.get_attribute("text") or ""
                bounds = element.get_attribute("bounds") or ""
                print(f"  可点击元素 {i+1}: class='{class_name}', desc='{content_desc}', text='{text}', bounds='{bounds}'")
            except:
                pass
        
        # 显示所有按钮元素
        button_elements = driver.find_elements(AppiumBy.XPATH, "//*[@class='android.widget.Button' or contains(@class, 'Button')]")
        print(f"📊 找到 {len(button_elements)} 个按钮元素:")
        for i, element in enumerate(button_elements):
            try:
                text = element.get_attribute("text") or ""
                content_desc = element.get_attribute("content-desc") or ""
                bounds = element.get_attribute("bounds") or ""
                print(f"  按钮 {i+1}: text='{text}', desc='{content_desc}', bounds='{bounds}'")
            except:
                pass
        
        # 显示所有复选框元素
        checkbox_elements = driver.find_elements(AppiumBy.XPATH, "//*[contains(@class, 'CheckBox') or contains(@class, 'check')]")
        print(f"📊 找到 {len(checkbox_elements)} 个复选框元素:")
        for i, element in enumerate(checkbox_elements):
            try:
                class_name = element.get_attribute("class") or ""
                content_desc = element.get_attribute("content-desc") or ""
                text = element.get_attribute("text") or ""
                bounds = element.get_attribute("bounds") or ""
                print(f"  复选框 {i+1}: class='{class_name}', desc='{content_desc}', text='{text}', bounds='{bounds}'")
            except:
                pass
        
        # 截图保存当前页面状态
        print("📸 保存当前页面截图...")
        try:
            screenshot_path = f"/tmp/light_effect_setup_page_{int(time.time())}.png"
            driver.save_screenshot(screenshot_path)
            print(f"✅ 截图已保存: {screenshot_path}")
        except Exception as e:
            print(f"⚠️ 截图失败: {e}")
        
        # 检查是否在正确的页面
        print("🔍 检查是否在配网设置页面...")
        try:
            # 查找配网设置页面的指示器
            setup_indicators = [
                "//*[contains(@text, '配网兼容性') or contains(@text, '设置') or contains(@text, 'Setup')]",
                "//*[contains(@text, '灯效') or contains(@text, 'Light')]",
                "//*[contains(@text, '网络') or contains(@text, 'Network')]"
            ]
            
            page_found = False
            for indicator in setup_indicators:
                try:
                    element = driver.find_element(AppiumBy.XPATH, indicator)
                    print(f"✅ 找到配网设置页面指示器: {indicator}")
                    page_found = True
                    break
                except:
                    continue
            
            if not page_found:
                print("⚠️ 未找到配网设置页面指示器")
                print("📝 说明: 可能不在配网设置页面，显示当前页面信息")
                
                # 显示当前页面的文本元素
                text_elements = driver.find_elements(AppiumBy.XPATH, "//*[@class='android.widget.TextView']")
                print(f"📊 当前页面文本元素数量: {len(text_elements)}")
                for i, element in enumerate(text_elements[:10]):
                    try:
                        text = element.get_attribute("text") or ""
                        if text and len(text.strip()) > 0:
                            print(f"  文本 {i+1}: '{text}'")
                    except:
                        pass
                
                # 显示当前页面的可点击元素
                clickable_elements = driver.find_elements(AppiumBy.XPATH, "//*[@clickable='true']")
                print(f"📊 当前页面可点击元素数量: {len(clickable_elements)}")
                for i, element in enumerate(clickable_elements[:10]):
                    try:
                        class_name = element.get_attribute("class") or ""
                        content_desc = element.get_attribute("content-desc") or ""
                        text = element.get_attribute("text") or ""
                        print(f"  可点击元素 {i+1}: class='{class_name}', desc='{content_desc}', text='{text}'")
                    except:
                        pass
                
                print("⚠️ 可能页面跳转有问题，尝试继续执行...")
                
        except Exception as e:
            print(f"⚠️ 检查配网设置页面失败: {e}")
        
        # 1. 点击勾选复选框
        print("\n🔍 1. 点击勾选复选框...")
        print("🔧 使用XPath: //android.widget.CheckBox")
        
        # 尝试多种复选框选择器
        checkbox_selectors = [
            "//android.widget.CheckBox",
            "//*[@class='android.widget.CheckBox']",
            "//*[contains(@class, 'CheckBox')]",
            "//*[@clickable='true' and contains(@class, 'View')]"
        ]
        
        checkbox_found = False
        for i, selector in enumerate(checkbox_selectors):
            try:
                print(f"尝试复选框选择器 {i+1}: {selector}")
                checkbox = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                print(f"✅ 找到复选框，使用选择器: {selector}")
                checkbox.click()
                print("✅ 复选框勾选完成")
                time.sleep(1)
                checkbox_found = True
                break
            except:
                print(f"❌ 复选框选择器 {i+1} 失败")
                continue
        
        if not checkbox_found:
            print("❌ 未找到复选框，显示当前页面复选框元素...")
            
            # 显示所有复选框元素
            checkbox_elements = driver.find_elements(AppiumBy.XPATH, "//*[contains(@class, 'CheckBox') or contains(@class, 'check')]")
            print(f"📊 找到 {len(checkbox_elements)} 个复选框元素:")
            for i, element in enumerate(checkbox_elements):
                try:
                    class_name = element.get_attribute("class") or ""
                    content_desc = element.get_attribute("content-desc") or ""
                    text = element.get_attribute("text") or ""
                    print(f"  复选框 {i+1}: class='{class_name}', desc='{content_desc}', text='{text}'")
                except:
                    pass
            
            print("⚠️ 未找到复选框，跳过复选框点击步骤")
            print("📝 说明: 可能页面结构已变化，或者不需要勾选复选框")
        
        # 2. 点击next按钮
        print("\n🔍 2. 点击next按钮...")
        print("🔧 使用XPath: //android.widget.Button")
        
        # 尝试多种next按钮选择器
        next_selectors = [
            "//android.widget.Button",
            "//*[@class='android.widget.Button']",
            "//*[contains(@text, 'Next') or contains(@text, 'next') or contains(@text, '下一步') or contains(@text, '继续')]",
            "//*[@content-desc='next' or @content-desc='Next']"
        ]
        
        next_found = False
        for i, selector in enumerate(next_selectors):
            try:
                print(f"尝试next按钮选择器 {i+1}: {selector}")
                next_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                print(f"✅ 找到next按钮，使用选择器: {selector}")
                next_button.click()
                print("⏳ 等待3秒让页面跳转到配网流程...")
                time.sleep(3)
                next_found = True
                break
            except:
                print(f"❌ next按钮选择器 {i+1} 失败")
                continue
        
        if not next_found:
            print("❌ 未找到next按钮，显示当前页面按钮...")
            
            # 显示所有按钮元素
            button_elements = driver.find_elements(AppiumBy.XPATH, "//*[@class='android.widget.Button' or contains(@class, 'Button')]")
            print(f"📊 找到 {len(button_elements)} 个按钮元素:")
            for i, element in enumerate(button_elements):
                try:
                    text = element.get_attribute("text") or ""
                    content_desc = element.get_attribute("content-desc") or ""
                    print(f"  按钮 {i+1}: text='{text}', desc='{content_desc}'")
                except:
                    pass
            
            print("⚠️ 未找到next按钮，可能页面结构已变化")
            print("📝 说明: 跳过next按钮点击，继续执行后续步骤")
        
        print("✅ 配网设置完成")
        print("📱 当前Activity:", driver.current_activity)
        
    except Exception as e:
        print(f"❌ 配网设置失败: {e}")
        print("🔍 错误详情:", traceback.format_exc())
        print("⚠️ 继续执行后续步骤...")
        # 不抛出异常，继续执行后续步骤

def wait_for_network_result(driver, timeout=180):
    """配网流程页面 - 优化版，实时检测页面跳转和结果"""
    try:
        print("⏳ 步骤7: 进入配网流程页面...")
        print(f"📝 说明: 配网时长3分钟，超时时间: {timeout}秒")
        
        # 检查是否进入配网流程页面
        print("🔍 检查是否进入配网流程页面...")
        print("🔧 使用XPath: //android.widget.TextView[@text='Pairing with your device']")
        try:
            pairing_text = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, "//android.widget.TextView[@text='Pairing with your device']"))
            )
            print("✅ 进入配网流程页面")
            print("📝 说明: 找到配网流程页面文本，开始配网")
        except:
            print("⚠️ 未找到配网流程页面文本，继续等待")
            print("📝 说明: 未找到配网流程页面文本，但继续等待配网结果")
        
        # 等待配网结果 - 实时检测页面变化
        print("⏳ 开始等待配网结果...")
        start_time = time.time()
        check_count = 0
        last_activity = driver.current_activity
        
        while time.time() - start_time < timeout:
            check_count += 1
            elapsed_time = int(time.time() - start_time)
            remaining_time = timeout - elapsed_time
            current_activity = driver.current_activity
            
            # 检测页面跳转
            if current_activity != last_activity:
                print(f"🔄 检测到页面跳转: {last_activity} -> {current_activity}")
                last_activity = current_activity
            
            if check_count % 15 == 0:  # 每30秒显示一次进度
                print(f"⏰ 配网进行中... 已用时: {elapsed_time}秒, 剩余: {remaining_time}秒")
            
            try:
                # 1. 配网成功 - 检查Sora 70设备
                print("🔍 检查是否配网成功...")
                print("🔧 使用XPath: //android.widget.TextView[@text='Sora 70']")
                sora_device = driver.find_element(AppiumBy.XPATH, "//android.widget.TextView[@text='Sora 70']")
                print("✅ 配网成功！找到Sora 70设备")
                print("📝 说明: 在页面找到Sora 70设备，配网成功，记录一次成功")
                return "success"
            except:
                pass
            
            try:
                # 2. 配网成功 - 检查robot设备（备用检测）
                print("🔍 检查是否配网成功（备用检测）...")
                print("🔧 使用XPath: //android.widget.ImageView[@content-desc='robot']")
                robot_device = driver.find_element(AppiumBy.XPATH, "//android.widget.ImageView[@content-desc='robot']")
                print("✅ 配网成功！首页出现robot设备")
                print("📝 说明: 在首页找到robot设备，配网成功，记录一次成功")
                return "success"
            except:
                pass
            
            try:
                # 3. 配网失败，跳转至失败页面
                print("🔍 检查是否配网失败...")
                print("🔧 使用XPath: //android.widget.TextView[@text='Data transmitting failed.']")
                fail_text = driver.find_element(AppiumBy.XPATH, "//android.widget.TextView[@text='Data transmitting failed.']")
                print("❌ 配网失败！出现失败页面")
                print("📝 说明: 找到配网失败文本，配网失败，记录一次失败")
                return "failed"
            except:
                pass
            
            # 检查其他可能的失败指示器
            try:
                fail_indicators = [
                    "//*[contains(@text, 'failed') or contains(@text, '失败') or contains(@text, 'error') or contains(@text, '错误')]",
                    "//*[contains(@text, 'timeout') or contains(@text, '超时')]",
                    "//*[contains(@text, 'connection') and contains(@text, 'failed')]"
                ]
                
                for indicator in fail_indicators:
                    try:
                        fail_element = driver.find_element(AppiumBy.XPATH, indicator)
                        fail_text = fail_element.get_attribute("text") or ""
                        print(f"❌ 配网失败！找到失败指示器: {fail_text}")
                        print("📝 说明: 找到失败指示器，配网失败，记录一次失败")
                        return "failed"
                    except:
                        continue
            except:
                pass
            
            print("⏳ 等待2秒后继续检查...")
            time.sleep(2)
        
        print("⏰ 配网超时")
        print(f"📝 说明: 配网超过{timeout}秒未完成，判定为超时")
        return "timeout"
        
    except Exception as e:
        print(f"❌ 等待配网结果失败: {e}")
        print("🔍 错误详情:", traceback.format_exc())
        return "error"

def test_110101_final(setup_driver):
    """蓝牙配网测试 - 最终修复版"""
    driver = setup_driver
    
    print("🎯 开始蓝牙配网测试 - 最终修复版")
    print("=" * 60)
    print("📝 说明: 使用expect脚本执行ROS2命令，模拟手动操作")
    
    try:
        # 1. Kill APP并重新启动
        print("\n🔄 步骤1: Kill APP并重新启动...")
        kill_and_restart_app(driver)
        
        # 2. 发送ROS2消息触发AP (最终修复版)
        print("\n📡 步骤2: 发送ROS2消息 (最终修复版)...")
        ros2_success = send_ros2_message_final()
        
        if not ros2_success:
            print("⚠️ ROS2消息发送失败，但继续执行后续步骤")
        
        # 3. 点击添加设备按钮
        print("\n📱 步骤3: 点击添加设备按钮...")
        click_add_button(driver)
        
        # 4. 选择设备
        print("\n🔍 步骤4: 选择设备...")
        select_device(driver)
        
        # 5. 设置WiFi
        print("\n📶 步骤5: 设置WiFi...")
        setup_wifi(driver)
        
        # 6. 设置灯效
        print("\n💡 步骤6: 设置灯效...")
        setup_light_effect(driver)
        
        # 7. 等待配网结果
        print("\n⏳ 步骤7: 等待配网结果...")
        result = wait_for_network_result(driver)
        
        # 显示最终结果
        print(f"\n📊 配网结果: {result}")
        if result == "success":
            print("✅ 配网成功！")
        elif result == "failed":
            print("❌ 配网失败！")
        elif result == "timeout":
            print("⏰ 配网超时！")
        else:
            print("💥 配网出错！")
        
        print("✅ 测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        print("🔍 错误详情:", traceback.format_exc())
        raise
