import pytest  # 导入pytest用于测试
import time  # 导入time用于延时
import traceback  # 导入traceback用于异常追踪
import os
from appium import webdriver  # 导入appium的webdriver
from appium.webdriver.common.appiumby import AppiumBy  # 导入AppiumBy用于元素定位
from selenium.webdriver.support.ui import WebDriverWait  # 导入WebDriverWait用于显式等待
from selenium.webdriver.support import expected_conditions as EC  # 导入EC用于等待条件
from selenium.webdriver.common.by import By  # 导入By用于通用定位
import subprocess  # 导入subprocess用于执行系统命令
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

RUN_LABEL = os.environ.get("RUN_LABEL", "ios")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

from username_utils import ran1, ran2, ran3, ran4, ran5, ran6


@pytest.fixture(scope="function")
def setup_driver():
    """
    iOS设备驱动配置 - 为每个测试函数创建独立的WebDriver实例

    配置iPhone 16的Appium环境，包括设备信息、应用包名、自动化引擎等

    Returns:
        WebDriver: 配置好的iOS WebDriver实例
    """
    # iOS设备配置
    options = XCUITestOptions()  # 创建XCUITest选项对象
    options.platform_name = "iOS"  # 设置平台名称
    options.platform_version = "18.5"  # 设置iOS系统版本（真机版本）
    options.device_name = "iPhone 16 pro max"  # 设置设备名称（真机名称）
    options.automation_name = "XCUITest"  # 设置自动化引擎
    options.udid = "00008140-00041C980A50801C"  # 设置设备唯一标识（真机UDID）
    options.bundle_id = "com.xingmai.tech"  # 设置应用包名
    options.include_safari_in_webviews = True  # 包含Safari Webview
    options.new_command_timeout = 3600  # 设置新命令超时时间
    options.connect_hardware_keyboard = True  # 连接硬件键盘

    # 连接Appium服务器
    driver = webdriver.Remote(  # 创建webdriver实例，连接Appium服务
        command_executor='http://localhost:4736',  # Appium服务地址
        options=options  # 传入选项对象
    )

    # 设置隐式等待时间
    driver.implicitly_wait(5)  # 设置隐式等待10秒

    yield driver  # 返回driver供测试用例使用

    # 测试结束后关闭驱动
    if driver:  # 如果driver存在
        driver.quit()  # 关闭driver


def test_102248(setup_driver):
    """
    验证输入用户名，点击返回按钮
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    
    try:
        # 步骤0: 登出
        current_step = "步骤0: 登出，确保从登出状态开始测试"
        print(f"🔄 {current_step}")
        check_and_logout(driver)
        print(f"✅ {current_step} - 完成")
        time.sleep(2)
    except Exception as e:
        fail_reason = f"{current_step}失败: {str(e)}"
        print(f"❌ {fail_reason}")
        raise
    
    try:
        # 步骤1: 点击Sign Up按钮进入注册页面
        current_step = "步骤1: 点击Sign Up按钮进入注册页面"
        print(f"🔄 {current_step}")
        try:
            sign_Up_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign Up"]'))
            )
            sign_Up_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Sign Up按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤2: 输入包含特殊字符的邮箱地址
        current_step = "步骤2: 输入邮箱地址"
        print(f"🔄 {current_step}")
        try:
            email_address = get_next_email()
            email_input = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
            )
            email_input.clear()
            email_input.send_keys(email_address)
            print(f"✅ {current_step} - 完成，邮箱: {email_address}")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或输入邮箱 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 同意隐私政策
        current_step = "步骤3: 同意隐私政策"
        print(f"🔄 {current_step}")
        try:
            check_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'))
            )
            check_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击隐私政策复选框 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤4: 点击Done按钮（第一次）
        current_step = "步骤4: 点击Done按钮（收起键盘）"
        print(f"🔄 {current_step}")
        try:
            done_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
            )
            done_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Done按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 点击Next按钮进入密码设置
        current_step = "步骤5: 点击Next按钮进入密码设置"
        print(f"🔄 {current_step}")
        try:
            next_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
            )
            next_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Next按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 设置密码
        current_step = "步骤6: 设置密码"
        print(f"🔄 {current_step}")
        try:
            # 输入密码
            password_input = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeSecureTextField[1]'))
            )
            password_input.clear()
            password_input.send_keys('Csx150128')
            time.sleep(2)
            
            # 确认密码
            retype_password_input = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeSecureTextField[2]'))
            )
            retype_password_input.clear()
            retype_password_input.send_keys('Csx150128')
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或输入密码框 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 点击Done按钮（第二次）
        current_step = "步骤7: 点击Done按钮（收起键盘）"
        print(f"🔄 {current_step}")
        try:
            done_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
            )
            done_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Done按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 点击Next按钮进入个人信息页面
        current_step = "步骤8: 点击Next按钮进入个人信息页面"
        print(f"🔄 {current_step}")
        try:
            next_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
            )
            next_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Next按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤9: 设置用户名
        current_step = "步骤9: 设置用户名"
        print(f"🔄 {current_step}")
        try:
            username = ran1()
            username_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
            )
            username_input.clear()
            username_input.send_keys(username)
            print(f"✅ {current_step} - 完成，用户名: {username}")
            time.sleep(3)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或输入用户名框 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤10: 点击Done按钮收起键盘
        current_step = "步骤10: 点击Done按钮收起键盘"
        print(f"🔄 {current_step}")
        try:
            done_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
            )
            done_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Done按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤11: 点击左上角返回按钮
        current_step = "步骤11: 点击左上角返回按钮"
        print(f"🔄 {current_step}")
        try:
            back_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="nav back"]'))
            )
            back_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(3)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击返回按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤12: 验证跳转到APP主页面
        current_step = "步骤12: 验证跳转到APP主页面"
        print(f"🔄 {current_step}")
        try:
            home_btn = WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="home sel"]'))
            )
            mine_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="mine"]'))
            )
            assert home_btn.get_attribute("name") == "home sel", "未找到home sel按钮，未跳转到主页面"
            assert mine_btn.get_attribute("name") == "mine", "未找到mine按钮，未跳转到主页面"
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: 未成功跳转到主页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤13: 验证用户名显示为默认的"Username"
        current_step = "步骤13: 验证用户名显示为默认的'Username'"
        print(f"🔄 {current_step}")
        try:
            # 尝试多个可能的选择器
            username_selectors = [
                '//XCUIElementTypeStaticText[@name="Hi, Username"]',
                '//XCUIElementTypeStaticText[contains(@name, "Username")]',
                '//XCUIElementTypeStaticText[contains(@name, "Hi")]',
            ]
            
            username_text = None
            for selector in username_selectors:
                try:
                    username_text = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, selector))
                    )
                    print(f"✅ 找到用户名元素，使用选择器: {selector}")
                    break
                except:
                    continue
            
            if not username_text:
                raise Exception("无法找到用户名显示元素，尝试了以下选择器: " + ", ".join(username_selectors))
            
            username_display = username_text.get_attribute("name")
            print(f"📝 用户名显示内容: {username_display}")
            
            # 断言用户名显示为默认的"Username"
            assert username_display == "Hi, Username", f"用户名显示不正确，期望'Hi, Username'，实际显示: {username_display}"
            # 确保不包含新设置的用户名
            assert username not in username_display, f"用户名不应显示新设置的用户名'{username}'，但实际显示: {username_display}"
            print(f"✅ {current_step} - 完成，用户名显示为默认值: {username_display}")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise
        
        print("🎉 测试用例102248执行成功！")
        time.sleep(2)

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {str(e)}"
        print(f"\n{'='*60}")
        print(f"❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'='*60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102248_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102248",
            case_desc="验证输入用户名，点击返回按钮",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])