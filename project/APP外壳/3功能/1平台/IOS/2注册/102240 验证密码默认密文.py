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


def test_102240(setup_driver):
    """
    102240 验证密码默认密文
    1) 登出后首页 Sign Up → 注册页
    2) 输入邮箱（get_simple_email()），勾选隐私，点击 Done 收起键盘
    3) 点击 Next 进入 set password 页
    4) 密码框输入 Csx150128，确认密文显示（应显示为•，值不等于明文）
    5) 断言密码框为密文，测试通过
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        # 步骤0: 登出，确保从登出状态开始测试
        current_step = "步骤0: 登出，确保从登出状态开始测试"
        print(f"🔄 {current_step}")
        try:
            check_and_logout(driver)
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            print(f"ℹ️ {current_step} - 已处于登出状态或登出失败（可忽略）: {str(e)}")
            time.sleep(2)

        # 步骤1: 验证在APP首页（登录页面）
        current_step = "步骤1: 验证在APP首页（登录页面）"
        print(f"🔄 {current_step}")
        try:
            sign_up_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign Up"]'))
            )
            assert sign_up_btn.is_displayed(), "Sign Up按钮存在但不可见"
            print(f"✅ {current_step} - 完成，确认在APP首页（登录页面）")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 未找到Sign Up按钮，可能不在登录页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤2: 点击Sign Up按钮进入注册页面
        current_step = "步骤2: 点击Sign Up按钮进入注册页面"
        print(f"🔄 {current_step}")
        try:
            sign_up_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign Up"]'))
            )
            sign_up_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(3)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Sign Up按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 验证进入Sign Up页面
        current_step = "步骤3: 验证进入Sign Up页面"
        print(f"🔄 {current_step}")
        try:
            sign_up_text = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]'))
            )
            assert sign_up_text.is_displayed(), "Sign Up文本元素存在但不可见"
            print(f"✅ {current_step} - 完成，确认已进入Sign Up注册页面")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 未成功进入Sign Up页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤4: 输入邮箱
        current_step = "步骤4: 输入邮箱"
        print(f"🔄 {current_step}")
        try:
            email_address = get_simple_email()
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

        # 步骤5: 勾选隐私政策和用户协议
        current_step = "步骤5: 勾选隐私政策和用户协议"
        print(f"🔄 {current_step}")
        try:
            check_btn = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'))
            )
            assert check_btn.is_displayed(), "隐私政策复选框存在但不可见"
            try:
                checked_btn = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check selected"]')
                if not checked_btn.is_displayed():
                    check_btn.click()
                    print("✅ 隐私政策复选框已勾选")
                else:
                    print("✅ 隐私政策复选框已勾选（预期状态）")
            except:
                check_btn.click()
                print("✅ 隐私政策复选框已勾选")
            time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5.1: 收起键盘（Done）
        current_step = "步骤5.1: 收起键盘（Done）"
        print(f"🔄 {current_step}")
        try:
            done_btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
            )
            done_btn.click()
            print("✅ 已点击Done收起键盘")
            time.sleep(1)
        except Exception as e:
            print(f"ℹ️ {current_step} - 未找到Done按钮，可能键盘已收起: {e}")
            time.sleep(0.5)

        # 步骤6: 点击Next进入set password页面
        current_step = "步骤6: 点击Next进入set password页面"
        print(f"🔄 {current_step}")
        try:
            next_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
            )
            next_btn.click()
            print(f"✅ {current_step} - 完成，已点击Next按钮")
            time.sleep(3)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Next按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 验证进入set password页面
        current_step = "步骤7: 验证进入set password页面"
        print(f"🔄 {current_step}")
        try:
            password_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeSecureTextField[1]'))
            )
            retype_password_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeSecureTextField[2]'))
            )
            assert password_input.is_displayed() and retype_password_input.is_displayed(), "未成功进入密码设置页面"
            print("✅ 成功进入set password页面")
            time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: 未成功进入密码设置页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 输入密码并验证默认密文
        current_step = "步骤8: 输入密码并验证默认密文"
        print(f"🔄 {current_step}")
        try:
            secure_password_input = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeSecureTextField[1]'))
            )
            pwd = "Csx150128"
            secure_password_input.click()
            secure_password_input.clear()
            secure_password_input.send_keys(pwd)
            print(f"✅ 已输入密码: {pwd}")
            time.sleep(1)

            # 默认应为密文（SecureTextField 且不展示明文）
            default_type = secure_password_input.get_attribute("type") or ""
            default_value = secure_password_input.get_attribute("value") or ""
            print(f"📝 默认状态 value: '{default_value}', type: '{default_type}'")
            assert "SecureTextField" in default_type, "默认应为密文输入框"
            assert default_value != pwd, "默认状态不应展示明文"
            print("✅ 默认为密文显示")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤9: 点击眼睛一次，切换为明文
        current_step = "步骤9: 点击眼睛切换明文"
        print(f"🔄 {current_step}")
        try:
            eye_btn = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login pwd hide"]'))
            )
            eye_btn.click()
            time.sleep(1)

            plain_password_input = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeTextField[1]'))
            )
            plain_value = plain_password_input.get_attribute("value") or ""
            plain_type = plain_password_input.get_attribute("type") or ""
            print(f"📝 明文状态 value: '{plain_value}', type: '{plain_type}'")
            assert plain_value == pwd, f"切换明文后应显示原密码，当前值: '{plain_value}'"
            print("✅ 点击一次眼睛后显示明文")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤10: 再点击眼睛一次，切回密文
        current_step = "步骤10: 再次点击眼睛切回密文"
        print(f"🔄 {current_step}")
        try:
            eye_btn = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login pwd hide"]'))
            )
            eye_btn.click()
            time.sleep(1)

            secure_password_input_after = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeSecureTextField[1]'))
            )
            secure_value_after = secure_password_input_after.get_attribute("value") or ""
            secure_type_after = secure_password_input_after.get_attribute("type") or ""
            print(f"📝 再次密文状态 value: '{secure_value_after}', type: '{secure_type_after}'")
            assert "SecureTextField" in secure_type_after, "再次点击后应切回密文输入框"
            assert secure_value_after != pwd, "切回密文后不应显示明文"
            print("✅ 再点击一次眼睛后恢复密文显示")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102240执行成功！")
        print('✅ 密码默认密文，点击眼睛切换明文，再点击恢复密文')
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
        save_failure_screenshot(driver, "test_102240_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102240",
            case_desc='102240 验证密码默认密文',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])
