import traceback
import pytest
import time
import os
import sys
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from appium.options.android import UiAutomator2Options  # Android选项
from appium.options.ios import XCUITestOptions  # iOS选项
from selenium.common import InvalidSessionIdException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ========================
# pytest hook：测试失败截图保存
# ========================
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == 'call' and report.failed:
        instance = getattr(item, 'instance', None)
        if instance:
            driver = getattr(instance, 'driver', None)
            if driver:
                filename = f"screenshots/{item.name}_{int(time.time())}.png"
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                driver.save_screenshot(filename)
                print(f"失败截图已保存：{filename}")


# 全局变量用于复用 options 配置
options = None
bundle_id = None  # 全局变量，用于存储bundleId


# ========================
# Appium driver 启动与关闭（session 级别，只执行一次）
# ========================
@pytest.fixture(scope="class")
def setup_driver():
    global options, bundle_id
    
    # 从配置文件读取bundleId
    bundle_id = "com.xingmai.tech"  # 默认值
    try:
        # 先尝试从当前目录读取
        bundle_id_file = "bundle_id.txt"
        
        # 如果当前目录没有，尝试从项目根目录读取
        if not os.path.exists(bundle_id_file):
            bundle_id_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bundle_id.txt")
        
        if os.path.exists(bundle_id_file):
            with open(bundle_id_file, "r") as f:
                bundle_id = f.read().strip()
            print(f"✅ 成功读取bundleId配置: {bundle_id}")
        else:
            print(f"⚠️ 未找到bundleId配置文件，使用默认值: {bundle_id}")
    except Exception as e:
        print(f"⚠️ 读取bundleId配置出错: {e}")

    # 使用iOS的XCUITestOptions
    options = XCUITestOptions()
    
    # iOS 配置项
    options.platform_name = "iOS"
    options.platform_version = "18.4"
    options.device_name = "iPhone 16 Plus"
    options.udid = "00008140-000648C82ED0801C"
    options.bundle_id = bundle_id
    options.include_safari_in_webviews = True
    options.new_command_timeout = 3600
    options.connect_hardware_keyboard = True

    print(f"🚀 正在连接到设备，使用bundleId: {bundle_id}")
    # 创建 driver 实例，确保每次都重新创建
    driver = webdriver.Remote('http://127.0.0.1:4723', options=options)

    # 检查 driver session 是否有效
    if not driver.session_id:
        print("Session is invalid, creating new session...")
        driver.quit()
        driver = webdriver.Remote('http://127.0.0.1:4723', options=options)

    yield driver

    # 退出时检查 session 是否有效
    if driver.session_id:
        try:
            driver.quit()  # 如果会话有效，则退出
        except InvalidSessionIdException:
            print("会话已经结束，无法退出")


# ========================
# driver 注入每个测试类
# ========================
@pytest.fixture(scope='class')
def driver(request, setup_driver):
    request.cls.driver = setup_driver
    return setup_driver


# ========================
# 测试用例类
# ========================
@pytest.mark.usefixtures("driver")
class TestCase:
    # 每个测试用例前自动执行的初始化方法
    def setup_method(self, method):
        driver = self.driver
        try:
            if self.is_logged_in():
                print("检测到已登录状态，进行退出登录")
                self.logout()
                time.sleep(2)
        except:
            pass
        # 强制停止和重新启动 App
        try:
            driver.terminate_app(bundle_id)
            time.sleep(1)
            driver.activate_app(bundle_id)
            time.sleep(1)
        except:
            try:
                # Android 用 shell 强制停止，iOS 可跳过
                driver.execute_script("mobile: shell", {"command": "am", "args": ["force-stop", bundle_id]})
                time.sleep(1)
                driver.activate_app(bundle_id)
            except:
                # 最后兜底策略：重启整个 driver 会话
                driver.quit()
                driver = webdriver.Remote('http://127.0.0.1:4723', options=options)
                self.driver = driver
                time.sleep(1)

    # 验证登录相关方法
    def is_logged_in(self):
        try:
            more_elements = self.driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="mine"]')
            return len(more_elements) > 0
        except:
            return False

    # 通用方法：滑动查找元素（适配 iOS 页面下滑）
    def scroll_and_find_element(self, by_locator, max_swipes=5):
        for i in range(max_swipes):
            try:
                return self.driver.find_element(*by_locator)
            except:
                size = self.driver.get_window_size()
                start_y = size['height'] * 0.7
                end_y = size['height'] * 0.3
                start_x = size['width'] * 0.5
                self.driver.swipe(start_x, start_y, start_x, end_y, duration=800)
                time.sleep(1)
        raise Exception(f"滑动{max_swipes}次后未找到元素: {by_locator}")

    # 退出登录流程（点击 mine -> 滑动找到退出区域 -> 点击 Log Out 按钮）
    def logout(self):
        try:
            print("👉 尝试点击 mine 按钮进入个人中心")
            mine_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="mine"]'))
            )
            mine_button.click()
            time.sleep(2)
        except Exception as e:
            print(f"❌ 无法点击 mine 按钮：{e}")
            traceback.print_exc()
            return

        try:
            print("👉 滑动查找退出登录区域按钮")
            logout_cell = self.scroll_and_find_element((
                AppiumBy.XPATH, '//XCUIElementTypeTable/XCUIElementTypeCell[9]/XCUIElementTypeOther'
            ))
            logout_cell.click()
            time.sleep(1)
        except Exception as e:
            print(f"❌ 未找到退出登录区域：{e}")
            traceback.print_exc()
            return

        try:
            print("👉 等待 Log Out 确认按钮")
            confirm_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Log Out"]'))
            )
            confirm_button.click()
            print("✅ 成功退出登录")
            time.sleep(2)
        except Exception as e:
            print(f"❌ 点击 Log Out 确认按钮失败：{e}")
            traceback.print_exc()

    # 每个用例后自动执行，确保退出登录
    def teardown_method(self, method):
        try:
            if self.is_logged_in():
                print("🚪 Teardown：检测到已登录，退出登录")
                self.logout()
        except Exception as e:
            print("❌ Teardown异常：", e)
        finally:
            print("🛑 Driver session closed.")

    # 滑动查询
    def scroll_and_find_country(self, country_name, max_swipes=10):
        """
        在列表中循环滑动查找指定国家名，找到就返回元素，找不到返回None
        支持部分匹配，例如传入"United States"可以匹配"United States of America"
        """
        driver = self.driver
        for i in range(max_swipes):
            try:
                # 使用多种定位方式查找国家
                try:
                    # 精确匹配
                    element = driver.find_element(AppiumBy.ACCESSIBILITY_ID, country_name)
                    print(f"✅ 通过精确AccessibilityID找到国家: {country_name}")
                    return element
                except:
                    # 尝试使用XPath定位含有国家名的元素（包含匹配）
                    try:
                        element = driver.find_element(AppiumBy.XPATH, 
                            f'//XCUIElementTypeStaticText[contains(@name, "{country_name}") or contains(@label, "{country_name}")]')
                        actual_text = element.get_attribute('label') or element.get_attribute('name')
                        print(f"✅ 通过部分匹配XPath找到国家: 输入[{country_name}] 匹配到[{actual_text}]")
                        return element
                    except:
                        # 继续尝试其他查找方式
                        try:
                            element = driver.find_element(AppiumBy.XPATH, 
                                f'//XCUIElementTypeCell[contains(@name, "{country_name}") or contains(@label, "{country_name}")]')
                            actual_text = element.get_attribute('label') or element.get_attribute('name')
                            print(f"✅ 通过部分匹配Cell找到国家: 输入[{country_name}] 匹配到[{actual_text}]")
                            return element
                        except:
                            # 最后尝试使用模糊匹配方式查找
                            try:
                                # 获取所有StaticText和Cell元素
                                all_texts = driver.find_elements(AppiumBy.XPATH, 
                                    '//XCUIElementTypeStaticText | //XCUIElementTypeCell')
                                
                                # 遍历检查是否有包含国家名的元素
                                for elem in all_texts:
                                    try:
                                        text = elem.get_attribute('label') or elem.get_attribute('name') or ""
                                        if country_name.lower() in text.lower():
                                            print(f"✅ 通过完全模糊匹配找到国家: 输入[{country_name}] 匹配到[{text}]")
                                            return elem
                                    except:
                                        continue
                            except:
                                pass
                
                # 如果所有查找方式都失败，则向上滑动继续查找
                print(f"滑动第{i+1}次查找{country_name}")
                # 向上滑动一次（注意方向是 up，因为屏幕坐标系滑动）
                driver.execute_script("mobile: swipe", {"direction": "up"})
                time.sleep(0.5)  # 增加等待时间确保滑动完成
            except Exception as e:
                print(f"滑动查找出错: {e}")
                # 继续尝试滑动
                try:
                    driver.execute_script("mobile: swipe", {"direction": "up"})
                    time.sleep(0.5)
                except:
                    pass
        
        print(f"滑动{max_swipes}次后仍未找到国家: {country_name}")
        return None


# 如果作为主模块运行，执行测试示例
if __name__ == "__main__":
    print("test_framework.py - 自动化测试框架核心文件")
    print("此文件不应直接运行，而是被其他测试文件导入使用")
    print("查看示例用法: test_example_with_framework.py") 