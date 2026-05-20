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
    assert_on_country_select_page,
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


def test_102189(setup_driver):
    """
    验证从国家列表"取消"，返回注册主页面
    1. 点击Sign up按钮进入Sign up页面
    2. 点击国家栏下拉按钮，进入国家选择页面
    3. 记录当前显示的国家（China）
    4. 点击左上角返回按钮
    5. 验证返回注册主页面
    6. 验证国家没有变化，仍显示之前的国家（China）
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
            # 如果已经处于登出状态，忽略错误
            print(f"ℹ️ {current_step} - 已处于登出状态或登出失败（可忽略）: {str(e)}")
            time.sleep(2)

        # 步骤1: 验证在APP首页（登录页面）
        current_step = "步骤1: 验证在APP首页（登录页面）"
        print(f"🔄 {current_step}")
        try:
            # 验证登录页面的Sign Up按钮存在
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
            time.sleep(3)  # 等待页面跳转
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

        # 步骤4: 记录当前显示的国家（China）
        current_step = "步骤4: 记录当前显示的国家（China）"
        print(f"🔄 {current_step}")
        try:
            # 查找显示国家名称的元素
            country_display_selectors = [
                '//XCUIElementTypeStaticText[@name="China"]',
                '//XCUIElementTypeStaticText[contains(@name, "China")]',
                '//XCUIElementTypeButton[@name="China"]',
                '//XCUIElementTypeButton[contains(@name, "China")]',
                '//XCUIElementTypeOther[@name="China"]',
                '//XCUIElementTypeOther[contains(@name, "China")]',
            ]
            
            country_display_element = None
            displayed_country_before = None
            
            for selector in country_display_selectors:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            country_display_element = elem
                            displayed_country_before = elem.get_attribute("name")
                            print(f"✅ 找到国家显示元素，使用选择器: {selector}")
                            break
                    if country_display_element:
                        break
                except:
                    continue
            
            if not country_display_element:
                raise Exception("无法找到国家显示元素，请检查页面元素")
            
            print(f"📝 进入国家选择页面前，注册页面显示的国家: {displayed_country_before}")
            
            # 验证显示的国家是China
            assert "China" in displayed_country_before, f"当前显示的国家应该包含'China'，但实际为: {displayed_country_before}"
            
            print(f"✅ {current_step} - 完成，记录的国家: {displayed_country_before}")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或验证国家显示元素 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 点击国家栏下拉按钮

        current_step = "步骤5: 点击国家栏下拉按钮"
        print(f"🔄 {current_step}")
        try:
            # 查找国家栏下拉按钮（注意：图片中写的是Typelmage，应该是TypeImage）
            arrow_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeImage[@name="login_arrow"]'))
            )
            assert arrow_btn.is_displayed(), "国家栏下拉按钮存在但不可见"
            arrow_btn.click()
            print(f"✅ {current_step} - 完成，已点击国家栏下拉按钮")
            time.sleep(3)  # 等待跳转到国家选择页面
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击国家栏下拉按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 验证跳转至国家选择页面
        current_step = "步骤6: 验证跳转至国家选择页面"
        print(f"🔄 {current_step}")
        try:
            # 用多策略搜索框定位确认已进入国家选择页面
            search_field = assert_on_country_select_page(driver, timeout=10)
            assert search_field.is_displayed(), "搜索框存在但不可见"
            print(f"✅ {current_step} - 完成，确认已跳转至国家选择页面")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 未成功跳转至国家选择页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 点击左上角返回按钮
        current_step = "步骤7: 点击左上角返回按钮"
        print(f"🔄 {current_step}")
        try:
            # 查找左上角返回按钮
            back_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeNavigationBar[@name="_TtGC7BeatBot16SwiftUIContainerV7SwiftUI7AnyView_"]/XCUIElementTypeButton'))
            )
            assert back_btn.is_displayed(), "返回按钮存在但不可见"
            back_btn.click()
            print(f"✅ {current_step} - 完成，已点击左上角返回按钮")
            time.sleep(3)  # 等待返回注册主页面
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击返回按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 验证返回注册主页面
        current_step = "步骤8: 验证返回注册主页面"
        print(f"🔄 {current_step}")
        try:
            # 验证Sign Up文本元素存在（说明已返回注册主页面）
            sign_up_text = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]'))
            )
            assert sign_up_text.is_displayed(), "Sign Up文本元素存在但不可见"
            print(f"✅ {current_step} - 完成，确认已返回注册主页面")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 未成功返回注册主页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤9: 验证国家没有变化，仍显示之前的国家（China）
        current_step = "步骤9: 验证国家没有变化，仍显示之前的国家（China）"
        print(f"🔄 {current_step}")
        try:
            # 查找显示国家名称的元素
            country_display_selectors = [
                '//XCUIElementTypeStaticText[@name="China"]',
                '//XCUIElementTypeStaticText[contains(@name, "China")]',
                '//XCUIElementTypeButton[@name="China"]',
                '//XCUIElementTypeButton[contains(@name, "China")]',
                '//XCUIElementTypeOther[@name="China"]',
                '//XCUIElementTypeOther[contains(@name, "China")]',
            ]
            
            country_display_element_after = None
            displayed_country_after = None
            
            for selector in country_display_selectors:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            country_display_element_after = elem
                            displayed_country_after = elem.get_attribute("name")
                            print(f"✅ 找到国家显示元素，使用选择器: {selector}")
                            break
                    if country_display_element_after:
                        break
                except:
                    continue
            
            if not country_display_element_after:
                raise Exception("无法找到国家显示元素，请检查页面元素")
            
            print(f"📝 返回注册主页面后，显示的国家: {displayed_country_after}")
            print(f"📝 进入国家选择页面前，显示的国家: {displayed_country_before}")
            
            # 验证国家没有变化
            assert "China" in displayed_country_after, f"返回后显示的国家应该包含'China'，但实际为: {displayed_country_after}"
            
            # 验证国家名称一致（或包含相同的国家标识）
            assert "China" in displayed_country_before and "China" in displayed_country_after, f"国家应该没有变化，但前后不一致。之前: {displayed_country_before}，之后: {displayed_country_after}"
            
            print(f"✅ {current_step} - 完成")
            print(f"✅ 验证通过：国家没有变化，仍显示之前的国家（China）")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102189执行成功！")
        print('✅ 验证从国家列表"取消"，返回注册主页面：国家没有变化，仍显示之前的国家')
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
        save_failure_screenshot(driver, "test_102189_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102189",
            case_desc='验证从国家列表"取消"，返回注册主页面',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])
