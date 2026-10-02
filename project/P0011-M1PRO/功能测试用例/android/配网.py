import pytest  # 导入pytest用于测试
import time  # 导入time用于延时
import traceback  # 导入traceback用于异常追踪
from appium import webdriver  # 导入appium的webdriver
from appium.webdriver.common.appiumby import AppiumBy  # 导入AppiumBy用于元素定位
from selenium.webdriver.support.ui import WebDriverWait  # 导入WebDriverWait用于显式等待
from selenium.webdriver.support import expected_conditions as EC  # 导入EC用于等待条件
from selenium.webdriver.common.by import By  # 导入By用于通用定位
import subprocess  # 导入subprocess用于执行系统命令
from appium.options.ios import XCUITestOptions  # 导入iOS的XCUITest选项


@pytest.fixture(scope="function")  # 定义pytest的fixture，作用域为每个函数
def setup_driver():  # 定义setup_driver函数
    """
    iOS设备驱动配置  # 注释：配置iPhone 16的Appium环境
    配置iPhone 16的Appium环境
    """
    # iOS设备配置
    options = XCUITestOptions()  # 创建XCUITest选项对象
    options.platform_name = "iOS"  # 设置平台名称
    options.platform_version = "18.1.1"  # 设置iOS系统版本（真机版本）
    options.device_name = "ambrose的iPhone"  # 设置设备名称（真机名称）
    options.automation_name = "XCUITest"  # 设置自动化引擎
    options.udid = "00008140-000418483493001C"  # 设置设备唯一标识（真机UDID）
    options.bundle_id = "com.testdemo.tech"  # 设置应用包名
    options.include_safari_in_webviews = True  # 包含Safari Webview
    options.new_command_timeout = 3600  # 设置新命令超时时间
    options.connect_hardware_keyboard = True  # 连接硬件键盘

    # 连接Appium服务器
    driver = webdriver.Remote(  # 创建webdriver实例，连接Appium服务
        command_executor='http://localhost:4723',  # Appium服务地址
        options=options  # 传入选项对象
    )

    # 设置隐式等待时间
    driver.implicitly_wait(10)  # 设置隐式等待10秒

    yield driver  # 返回driver供测试用例使用

    # 测试结束后关闭驱动
    if driver:  # 如果driver存在
        driver.quit()  # 关闭driver


def check_and_logout(driver):  # 定义登出函数
    """
    优化版登出流程：  # 注释：登出流程说明
    1. 检测home sel/mine → 执行登出
    2. 如果检测不到，则跳过登出流程
    """
    device_id = "00008140-000418483493001C"  # 设备ID（真机UDID）
    package = "com.testdemo.tech"  # 包名

    try:  # 尝试执行登出流程
        print("开始登出流程...")  # 打印调试信息

        # 1. 检测home sel/mine，最多重试3次
        found = False  # 标记是否找到元素
        for i in range(3):  # 最多重试3次
            for xpath, name in [  # 遍历Home和More按钮
                ('//XCUIElementTypeButton[@name="home sel"]', "home sel"),
                ('//XCUIElementTypeButton[@name="mine"]', "mine")
            ]:
                try:  # 尝试查找元素
                    driver.find_element(AppiumBy.XPATH, xpath)  # 查找元素
                    print(f"检测到{name}元素")  # 打印调试信息
                    found = True  # 标记找到
                    break  # 跳出循环
                except:  # 未找到
                    continue  # 继续查找
            if found:  # 如果找到
                break  # 跳出外层循环
            print(f"第{i + 1}次未检测到home sel/mine，等待2秒重试...")  # 打印调试信息
            time.sleep(2)  # 等待2秒

        if not found:  # 如果未找到
            print("未检测到home sel/mine，跳过登出流程")  # 打印调试信息
            return  # 结束函数

        # 2. 点击mine（如不在mine页）
        try:  # 尝试点击mine按钮
            mine_btn = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="mine"]')  # 查找mine按钮
            mine_btn.click()  # 点击mine
            time.sleep(2)  # 等待2秒
            print("已点击mine按钮")  # 打印调试信息
        except Exception as e:  # 捕获异常
            print("点击mine按钮异常（可能已在mine页）:", e)  # 打印异常

        # 3. 点击编辑按钮
        try:  # 尝试点击编辑按钮
            edit_btn = WebDriverWait(driver, 10).until(  # 等待编辑按钮可点击
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="mine edit"]'))
            )
            edit_btn.click()  # 点击编辑按钮
            time.sleep(2)  # 等待2秒
            print("已点击编辑按钮")  # 打印调试信息
        except Exception as e:  # 捕获异常
            print("点击编辑按钮异常:", e)  # 打印异常
            return  # 结束函数

        # 4. 点击logout
        try:  # 尝试点击logout
            logout_btn = WebDriverWait(driver, 10).until(  # 等待logout按钮可点击
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="logout"]'))
            )
            logout_btn.click()  # 点击logout
            time.sleep(2)  # 等待2秒
            print("已点击logout按钮")  # 打印调试信息
        except Exception as e:  # 捕获异常
            print("点击logout按钮异常:", e)  # 打印异常

        # 5. 点击Log Out确认按钮
        try:  # 尝试点击Log Out确认按钮
            confirm_btn = WebDriverWait(driver, 5).until(  # 等待Log Out按钮可点击
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Confirm"]'))
            )
            confirm_btn.click()  # 点击confirm
            time.sleep(3)  # 等待3秒
            print("登出操作完成")  # 打印调试信息
        except Exception as e:  # 捕获异常
            print("点击Log Out按钮异常:", e)  # 打印异常

    except Exception as e:  # 捕获异常
        print(f"登出流程异常: {e}")  # 打印异常