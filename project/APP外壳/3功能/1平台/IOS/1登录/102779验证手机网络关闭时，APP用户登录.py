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
from ios_sign_in_helpers import resolve_sign_in_email_input, resolve_sign_in_password_input

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


def disable_network_ios(driver):
    """
    关闭iOS设备的网络连接
    通过后台切换到WLAN页面，点击WLAN开关关闭网络
    """
    return _set_wifi_enabled(driver, False)


def _find_first_matching_element(driver, selectors, wait_seconds=2, clickable=False):
    condition_factory = EC.element_to_be_clickable if clickable else EC.presence_of_element_located
    for selector in selectors:
        try:
            element = WebDriverWait(driver, wait_seconds).until(
                condition_factory((AppiumBy.XPATH, selector))
            )
            if element.is_displayed():
                return element, selector
        except Exception:
            continue
    return None, None


def _open_wifi_settings_page(driver):
    wifi_entry_selectors = [
        '//XCUIElementTypeButton[@name="com.apple.settings.wifi"]',
        '//XCUIElementTypeCell[@name="com.apple.settings.wifi"]',
        '//XCUIElementTypeButton[@name="WLAN"]',
        '//XCUIElementTypeCell[@name="WLAN"]',
        '//XCUIElementTypeStaticText[@name="WLAN"]',
        '//XCUIElementTypeButton[@name="Wi-Fi"]',
        '//XCUIElementTypeCell[@name="Wi-Fi"]',
        '//XCUIElementTypeStaticText[@name="Wi-Fi"]',
        '//XCUIElementTypeButton[@name="WiFi"]',
        '//XCUIElementTypeCell[@name="WiFi"]',
        '//XCUIElementTypeButton[@name="无线局域网"]',
        '//XCUIElementTypeCell[@name="无线局域网"]',
        '//XCUIElementTypeStaticText[@name="无线局域网"]',
        '//XCUIElementTypeButton[contains(@name,"WLAN")]',
        '//XCUIElementTypeCell[contains(@name,"WLAN")]',
        '//XCUIElementTypeButton[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeCell[contains(@name,"Wi-Fi")]',
    ]

    wifi_entry, selector = _find_first_matching_element(driver, wifi_entry_selectors, wait_seconds=3, clickable=True)
    if wifi_entry:
        wifi_entry.click()
        print(f"    ✅ 已进入WiFi页面: {selector}")
        time.sleep(2)
        return True

    back_selectors = [
        '//XCUIElementTypeButton[@name="Back"]',
        '//XCUIElementTypeButton[@name="返回"]',
        '//XCUIElementTypeNavigationBar/XCUIElementTypeButton[1]',
    ]
    back_btn, back_selector = _find_first_matching_element(driver, back_selectors, wait_seconds=2, clickable=True)
    if back_btn:
        back_btn.click()
        print(f"    ✅ 已点击返回按钮: {back_selector}")
        time.sleep(1.5)
        wifi_entry, selector = _find_first_matching_element(driver, wifi_entry_selectors, wait_seconds=3, clickable=True)
        if wifi_entry:
            wifi_entry.click()
            print(f"    ✅ 返回后进入WiFi页面: {selector}")
            time.sleep(2)
            return True

    print("    ❌ 无法进入WiFi设置页面")
    return False


def _find_wifi_switch(driver):
    switch_selectors = [
        '//XCUIElementTypeSwitch[@name="WLAN"]',
        '//XCUIElementTypeSwitch[@name="Wi-Fi"]',
        '//XCUIElementTypeSwitch[@name="Wi‑Fi"]',
        '//XCUIElementTypeSwitch[@name="WiFi"]',
        '//XCUIElementTypeSwitch[@name="无线局域网"]',
        '//XCUIElementTypeCell[contains(@name,"WLAN")]//XCUIElementTypeSwitch',
        '//XCUIElementTypeCell[contains(@name,"Wi-Fi")]//XCUIElementTypeSwitch',
        '//XCUIElementTypeCell[contains(@name,"WiFi")]//XCUIElementTypeSwitch',
        '//XCUIElementTypeCell[contains(@name,"无线局域网")]//XCUIElementTypeSwitch',
        '(//XCUIElementTypeSwitch)[1]',
    ]
    return _find_first_matching_element(driver, switch_selectors, wait_seconds=3, clickable=False)


def _switch_value_is_on(value):
    return str(value).strip().lower() in {"1", "true", "on"}


def _set_wifi_enabled(driver, enabled: bool):
    action_text = "打开" if enabled else "关闭"
    target_state = "开启" if enabled else "关闭"
    try:
        print(f"    🔄 通过后台切换到WLAN页面{action_text}网络...")
        driver.activate_app("com.apple.Preferences")
        time.sleep(2)

        wlan_switch, selector = _find_wifi_switch(driver)
        if not wlan_switch:
            print("    🔄 未直接找到WLAN开关，尝试进入WiFi页面...")
            if not _open_wifi_settings_page(driver):
                return False
            wlan_switch, selector = _find_wifi_switch(driver)

        if not wlan_switch:
            print("    ⚠️ 查找WLAN开关失败：未匹配到任何可见开关")
            return False

        print(f"    ✅ 已找到WLAN开关: {selector}")
        current_value = wlan_switch.get_attribute("value")
        is_on = _switch_value_is_on(current_value)
        print(f"    ℹ️ 当前WLAN状态值: {current_value}")

        need_click = (enabled and not is_on) or ((not enabled) and is_on)
        if need_click:
            wlan_switch.click()
            print(f"    ✅ WLAN开关已点击，目标状态: {target_state}")
            time.sleep(1.5)

            verify_switch, verify_selector = _find_wifi_switch(driver)
            if verify_switch:
                verify_value = verify_switch.get_attribute("value")
                verify_is_on = _switch_value_is_on(verify_value)
                print(f"    ℹ️ 点击后状态值: {verify_value}（{verify_selector}）")
                return verify_is_on == enabled
            return True

        print(f"    ℹ️ WLAN已经是{target_state}状态")
        return True
    except Exception as e:
        print(f"    ⚠️ {action_text}网络异常: {str(e)[:120]}")
        return False
    finally:
        try:
            driver.activate_app("com.xingmai.tech")
            time.sleep(1.5)
            print("    ✅ 已返回应用")
        except Exception as e:
            print(f"    ⚠️ 返回应用失败: {str(e)[:100]}")


def enable_network_ios(driver):
    """
    恢复iOS设备的网络连接
    通过后台切换到WLAN页面，点击WLAN开关打开网络
    """
    return _set_wifi_enabled(driver, True)


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

        # 步骤2: Sign In页面，执行关闭手机网络操作
        current_step = "步骤2: 在Sign In页面关闭手机网络"
        print(f"🔄 {current_step}")
        try:
            # 确认在Sign In页面
            sign_in_btn = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]'))
            )
            assert sign_in_btn.is_displayed(), "Sign In按钮存在但不可见"
            print("    ✅ 确认在Sign In页面")
            
            # 关闭手机网络
            network_disabled = disable_network_ios(driver)
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
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]'))
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
            # 点击邮箱标签
            email_input = resolve_sign_in_email_input(driver)
            email_input.clear()
            email_input.send_keys(email_address)
            print(f"    ✅ 邮箱输入完成: {email_address}")
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
            # 点击密码标签
            password_input = resolve_sign_in_password_input(driver)
            password_input.clear()
            password_input.send_keys(password)
            print(f"    ✅ 密码输入完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 点击键盘done，收起键盘
        current_step = "步骤6: 点击键盘Done，收起键盘"
        print(f"🔄 {current_step}")
        try:
            done_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
            )
            done_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            print(f"    ⚠️ 未找到Done按钮，可能键盘已自动收起: {e}")
            time.sleep(0.5)

        # 步骤7: 点击协议勾选框
        current_step = "步骤7: 点击协议勾选框"
        print(f"🔄 {current_step}")
        try:
            check_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'))
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
            # 点击登录按钮（使用iOS Predicate语法）
            login_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'name == "login icon"'))
            )
            login_btn.click()
            print("    ✅ 已点击登录按钮")
            time.sleep(3)  # 等待网络错误提示出现

            # 验证网络错误提示
            error_text = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Network connection error, please check"]'))
            )

            # 验证提示信息存在且可见
            assert error_text.is_displayed(), "网络错误提示信息存在但不可见"
            error_message = error_text.get_attribute("name")
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
            enable_network_ios(driver)
            print(f"✅ {current_step} - 完成，网络已恢复")
            network_disabled = False  # 标记网络已恢复
        except Exception as e:
            print(f"⚠️ {current_step}失败: {e}")
            print("💡 请手动恢复设备的WiFi和蜂窝数据")

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
                enable_network_ios(driver)
                print("✅ 网络连接已恢复")
            except Exception as e:
                print(f"⚠️ 恢复网络失败: {e}")
                print("💡 请手动恢复设备的WiFi和蜂窝数据")

        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102779",
            case_desc="验证手机网络关闭时，APP用户登录",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])