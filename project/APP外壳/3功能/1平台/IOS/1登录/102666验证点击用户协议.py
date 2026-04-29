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
    driver.implicitly_wait(5)  # 设置隐式等待5秒

    yield driver  # 返回driver供测试用例使用

    # 测试结束后关闭驱动
    if driver:  # 如果driver存在
        driver.quit()  # 关闭driver


def test_102666(setup_driver):
    """
    验证点击用户协议
    1. 重置APP，检测登录状态，如果已登录则登出
    2. 点击登录按钮进入Sign in页面
    3. 点击用户协议按钮
    4. 验证页面跳转到用户协议页面，检查特定元素，并向下滑动验证没有乱码
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
            bundle_id = caps.get("bundleId") or "com.xingmai.tech"
            driver.terminate_app(bundle_id)
            time.sleep(1.5)
            driver.activate_app(bundle_id)
            time.sleep(2)
            print("    ✅ APP已重置")
            
            # 检测是否已登录（查找home sel/mine sel/mine元素）
            is_logged_in = False
            login_indicators = [
                '//XCUIElementTypeButton[@name="home sel"]',
                '//XCUIElementTypeButton[@name="mine sel"]',
                '//XCUIElementTypeButton[@name="mine"]',
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
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]'))
            )
            sign_in_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Sign In按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 点击用户协议按钮
        current_step = "步骤3: 点击用户协议按钮"
        print(f"🔄 {current_step}")
        try:
            user_agreement_link = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeLink[@name="User Agreement"]'))
            )
            user_agreement_link.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)  # 等待页面跳转
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击User Agreement按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤4: 验证页面跳转到用户协议页面，检查特定元素，并向下滑动验证没有乱码
        current_step = "步骤4: 验证用户协议页面内容"
        print(f"🔄 {current_step}")
        try:
            # 4.1: 验证页面有"Last Modified: July 17th, 2024"
            last_modified_text = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Last Modified: July 17th, 2024"]'))
            )
            assert last_modified_text.is_displayed(), "Last Modified文本存在但不可见"
            print("    ✅ 找到Last Modified文本")
            
            # 4.2: 验证页面有"Introduction"
            introduction_text = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Introduction"]'))
            )
            assert introduction_text.is_displayed(), "Introduction文本存在但不可见"
            print("    ✅ 找到Introduction文本")
            
            # 4.3: 向下滑动，验证页面显示没有乱码
            print("    🔄 开始向下滑动，验证页面内容...")
            screen_size = driver.get_window_size()
            start_x = int(screen_size['width'] * 0.5)
            start_y = int(screen_size['height'] * 0.7)
            end_y = int(screen_size['height'] * 0.3)
            
            # 滑动3次，检查是否有乱码
            has_garbled_text = False
            for i in range(3):
                # 滑动
                driver.swipe(start_x, start_y, start_x, end_y, duration=500)
                time.sleep(1)
                
                # 获取当前页面所有可见文本
                try:
                    all_texts = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeStaticText')
                    visible_texts = []
                    for text_elem in all_texts:
                        try:
                            if text_elem.is_displayed():
                                text_content = text_elem.get_attribute("name") or ""
                                if text_content:
                                    visible_texts.append(text_content)
                                    # 检查是否有乱码（包含异常字符）
                                    # 乱码检测：检查是否有全角字符或异常Unicode字符
                                    for char in text_content:
                                        char_code = ord(char)
                                        # 检查全角字符范围（可能是乱码）
                                        if 0xFF00 <= char_code <= 0xFFEF:
                                            # 全角字符，可能是乱码
                                            has_garbled_text = True
                                            print(f"    ⚠️ 检测到可能的乱码字符: {char} (U+{char_code:04X}) 在文本: {text_content[:50]}")
                                            break
                                        # 中文字符是正常的（0x4E00-0x9FFF）
                                        # 英文和常见标点符号也是正常的
                        except:
                            continue
                    
                    if i == 0:
                        print(f"    ✅ 第{i+1}次滑动，获取到{len(visible_texts)}个可见文本元素")
                except Exception as e:
                    print(f"    ⚠️ 获取页面文本时出错: {e}")
            
            # 断言没有乱码
            assert not has_garbled_text, "页面检测到乱码，用户协议页面显示异常"
            print("    ✅ 页面滑动验证完成，未检测到乱码")
            
            print(f"✅ {current_step} - 完成，用户协议页面显示正常")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102666执行成功！")

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
        save_failure_screenshot(driver, "test_102666_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102666",
            case_desc="验证点击用户协议",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

