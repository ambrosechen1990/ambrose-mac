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
    resolve_country_search_field,
    click_country_option_by_visible_text,
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


def switch_country(driver, country_name: str):
    """
    切换国家
    
    Args:
        driver: WebDriver实例
        country_name: 国家名称，如"China"或"United States of America"
    
    Returns:
        bool: 切换是否成功
    """
    try:
        arrow_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeImage[@name="login_arrow"]'))
        )
        arrow_btn.click()
        print("✅ 已点击国家栏下拉按钮")
        time.sleep(3)

        search_field = assert_on_country_select_page(driver, timeout=10)
        assert search_field.is_displayed(), "搜索框存在但不可见"

        search_field = resolve_country_search_field(driver, timeout=8, clickable=True)
        search_field.click()
        time.sleep(1)
        search_field.clear()

        if country_name in {"China", "china", "中国"}:
            search_keyword = "China"
            target_texts = ["China"]
        elif country_name in {"美国", "United States"}:
            search_keyword = "america"
            target_texts = ["United States of America", "United States", "America"]
        else:
            search_keyword = country_name
            target_texts = [country_name]

        search_field.send_keys(search_keyword)
        print(f"✅ 已输入搜索关键词: {search_keyword}")
        time.sleep(2)

        clicked_country = click_country_option_by_visible_text(driver, target_texts, timeout=10)
        print(f"✅ 已选择国家: {country_name}，命中的元素: {clicked_country}")
        time.sleep(3)  # 等待返回注册页面并更新国家显示

        return True
    except Exception as e:
        print(f"❌ 切换国家失败: {str(e)}")
        return False


def resolve_email_label(driver, timeout: int = 10):
    """定位注册页账号行显示的 Email 文案或占位值。"""
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Email"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeTextField[@value="Email"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeTextField[@name="Email"]'),
        (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField" AND value == "Email"'),
        (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField" AND name == "Email"'),
        (AppiumBy.XPATH, '//*[contains(@name, "Email")]'),
    ]

    for by, selector in selectors:
        try:
            elements = WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located((by, selector))
            )
            for elem in elements:
                try:
                    if elem.is_displayed():
                        return elem
                except Exception:
                    continue
        except Exception:
            continue

    raise AssertionError("未找到注册页上的 Email 文案/占位元素")


def test_102194(setup_driver):
    """
    验证注册地为任何国家时，提示文案均为"邮箱"
    1. 打开APP，点击首页"2注册"按钮
    2. 国家切为"china"，查看"账号"行的显示
    3. 国家切为"美国"，查看"账号"行的显示，断言//XCUIElementTypeStaticText[@name="Email"]这个元素都是提示输入email
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

        # 步骤4: 国家切为"China"，查看"账号"行的显示
        current_step = "步骤4: 国家切为China，查看账号行的显示"
        print(f"🔄 {current_step}")
        try:
            # 切换国家为China
            if not switch_country(driver, "China"):
                raise Exception("切换国家为China失败")
            
            # 验证"账号"行显示 Email 文案或占位元素
            email_label = resolve_email_label(driver, timeout=10)
            assert email_label.is_displayed(), "Email标签元素存在但不可见"
            
            email_label_text = (
                email_label.get_attribute("name")
                or email_label.get_attribute("value")
                or email_label.text
                or ""
            )
            print(f"📝 China国家下，账号行显示: {email_label_text}")
            
            # 断言显示的是"Email"
            assert email_label_text == "Email", \
                f"China国家下，账号行应该显示'Email'，但实际显示: {email_label_text}"
            
            print(f"✅ {current_step} - 完成，China国家下账号行显示: {email_label_text}")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 国家切为"美国"，查看"账号"行的显示
        current_step = "步骤5: 国家切为美国，查看账号行的显示"
        print(f"🔄 {current_step}")
        try:
            # 切换国家为美国
            if not switch_country(driver, "United States of America"):
                raise Exception("切换国家为United Statest of America失败")
            
            # 验证"账号"行显示 Email 文案或占位元素
            email_label = resolve_email_label(driver, timeout=10)
            assert email_label.is_displayed(), "Email标签元素存在但不可见"
            
            email_label_text = (
                email_label.get_attribute("name")
                or email_label.get_attribute("value")
                or email_label.text
                or ""
            )
            print(f"📝 美国国家下，账号行显示: {email_label_text}")
            
            # 断言显示的是"Email"
            assert email_label_text == "Email", \
                f"美国国家下，账号行应该显示'Email'，但实际显示: {email_label_text}"
            
            print(f"✅ {current_step} - 完成，美国国家下账号行显示: {email_label_text}")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 验证两个国家下都显示Email
        current_step = "步骤6: 验证两个国家下都显示Email"
        print(f"🔄 {current_step}")
        try:
            # 再次验证当前（美国）显示 Email 文案或占位元素
            email_label = resolve_email_label(driver, timeout=10)
            assert email_label.is_displayed(), "Email标签元素应该存在"
            email_label_text = (
                email_label.get_attribute("name")
                or email_label.get_attribute("value")
                or email_label.text
                or ""
            )
            assert email_label_text == "Email", f"应该显示Email，实际显示: {email_label_text}"
            
            print(f"✅ {current_step} - 完成")
            print(f"✅ 验证通过：China和美国两个国家下，账号行都显示'Email'")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102194执行成功！")
        print('✅ 验证注册地为任何国家时，提示文案均为"邮箱"：China和美国都显示Email')
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
        save_failure_screenshot(driver, "test_102194_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102194",
            case_desc='验证注册地为任何国家时，提示文案均为"邮箱"',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

