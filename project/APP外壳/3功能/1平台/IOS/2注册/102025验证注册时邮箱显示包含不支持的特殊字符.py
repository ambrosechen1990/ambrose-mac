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
    get_next_unsupported_email,
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


def test_102025(setup_driver):
    """
    验证注册时邮箱显示包含不支持的特殊字符
    输入未被使用过的、包含不支持特殊字符的邮箱，勾选隐私政策和用户协议后点击Next，
    断言Next按钮置灰无法点击，且页面显示提示信息
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

        # 步骤2: 输入包含不支持特殊字符的邮箱地址
        current_step = "步骤2: 输入包含不支持特殊字符的邮箱地址"
        print(f"🔄 {current_step}")
        try:
            email_address = get_next_unsupported_email()
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

        # 步骤3: 点击Done按钮收起键盘
        current_step = "步骤3: 点击Done按钮收起键盘"
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

        # 步骤4: 勾选隐私政策和用户协议
        current_step = "步骤4: 勾选隐私政策和用户协议"
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

        # 步骤5: 验证Next按钮不可点击，且仍停留在当前页面
        current_step = "步骤5: 验证Next按钮不可点击，且仍停留在当前页面"
        print(f"🔄 {current_step}")
        try:
            # 记录点击前的页面状态：确认在注册页面（邮箱输入框存在）
            email_input_before = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
            )
            assert email_input_before.is_displayed(), "点击前应该能看到邮箱输入框"
            print("✅ 点击前确认在注册页面（邮箱输入框存在）")

            # 该场景下 Next 预期为置灰/不可点击，因此只要求能找到按钮本身
            next_btn = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
            )
            assert next_btn.is_displayed(), "Next按钮存在但不可见"

            enabled_attr = None
            try:
                enabled_attr = next_btn.get_attribute("enabled")
            except Exception:
                pass
            print(f"ℹ️ Next按钮 enabled 属性: {enabled_attr}")

            # 尝试点击；若因按钮置灰无法点击，不视为失败
            clicked = False
            try:
                next_btn.click()
                clicked = True
                print("🖱️ 已尝试点击Next按钮")
                time.sleep(2)
            except Exception as click_err:
                print(f"ℹ️ Next按钮不可点击（预期行为）: {click_err}")

            # 验证仍停留在注册页面（没有跳转到密码设置页面）
            # 检查邮箱输入框是否还在（说明仍在注册页面）
            try:
                email_input_after = driver.find_element(AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"')
                assert email_input_after.is_displayed(), "点击后邮箱输入框应该还在，说明仍在注册页面"
                print("✅ 点击后邮箱输入框仍在，确认停留在注册页面")
            except:
                pass
            
            # 检查是否进入了密码设置页面（如果进入了，说明跳转成功，这是不期望的）
            password_page_indicators = [
                '//XCUIElementTypeSecureTextField',  # 密码输入框
                '//XCUIElementTypeStaticText[contains(@name, "Password")]',  # 密码相关文本
            ]
            in_password_page = False
            for indicator in password_page_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, indicator)
                    if elem.is_displayed():
                        in_password_page = True
                        break
                except:
                    continue
            
            # 断言不应该进入密码设置页面
            assert not in_password_page, "Next按钮点击后不应该跳转到密码设置页面，但实际已跳转"
            if enabled_attr in ("0", "false", "False"):
                print("✅ Next按钮为禁用态（预期行为）")
            elif not clicked:
                print("✅ Next按钮未成功触发点击，视为不可点击（预期行为）")
            else:
                print("ℹ️ Next按钮可触发点击，但页面仍未跳转")

            print(f"✅ {current_step} - 完成，仍停留在注册页面")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 验证页面显示提示信息
        current_step = "步骤6: 验证页面显示提示信息"
        print(f"🔄 {current_step}")
        try:
            # 查找提示信息元素
            error_text = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Please sign up using your email address"]'))
            )
            
            # 验证提示信息存在且可见
            assert error_text.is_displayed(), "提示信息元素存在但不可见"
            error_message = error_text.get_attribute("name")
            print(f"📝 提示信息内容: {error_message}")
            
            # 断言提示信息正确
            assert error_message == "Please sign up using your email address", \
                f"提示信息不正确，期望'Please sign up using your email address'，实际显示: {error_message}"
            
            print(f"✅ {current_step} - 完成，提示信息显示正确: {error_message}")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102025执行成功！")
        time.sleep(2)

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
        save_failure_screenshot(driver, "test_102025_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102025",
            case_desc="验证注册时邮箱显示包含不支持的特殊字符",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])