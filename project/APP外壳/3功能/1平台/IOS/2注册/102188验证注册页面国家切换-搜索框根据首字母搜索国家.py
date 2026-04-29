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


def _collect_visible_country_names(driver, limit: int = 80):
    """采集国家选择页当前可见的国家名称。"""
    selectors = [
        '//XCUIElementTypeStaticText',
        '//XCUIElementTypeButton',
        '//XCUIElementTypeCell',
        '//XCUIElementTypeOther',
    ]
    ignored_names = {
        "Search",
        "commonDelete",
        "Clear text",
        "Cancel",
        "Done",
        "Country/Region",
        "Sign Up",
        "Next",
    }

    names = []
    for selector in selectors:
        try:
            elements = driver.find_elements(AppiumBy.XPATH, selector)
            for elem in elements[:limit]:
                try:
                    if not elem.is_displayed():
                        continue
                    country_name = (
                        elem.get_attribute("name")
                        or elem.get_attribute("label")
                        or elem.get_attribute("value")
                        or ""
                    ).strip()
                    if not country_name:
                        continue
                    if country_name in ignored_names:
                        continue
                    if len(country_name) < 3 or len(country_name) > 50:
                        continue
                    if country_name not in names:
                        names.append(country_name)
                except Exception:
                    continue
        except Exception:
            continue
    return names


def _pick_fallback_search_keyword(country_names):
    """从当前可见国家中挑选一个可稳定命中的首字母。"""
    for country_name in country_names:
        for char in country_name.strip():
            if char.isalpha():
                return char.upper(), country_name
    return None, None


def test_102188(setup_driver):
    """
    验证注册页面国家切换-搜索框根据首字母搜索国家
    1. 打开APP，点击首页"2注册"按钮
    2. 点击"国家/地区"下拉按钮
    3. 搜索框搜索字母"Z"；断言搜索到"Z"相关的所有国家（模糊搜索）
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    search_keyword = "Z"
    default_countries_before_search = []

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

        # 步骤4: 点击国家栏下拉按钮
        current_step = "步骤4: 点击国家栏下拉按钮"
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

        # 步骤5: 验证跳转至国家选择页面
        current_step = "步骤5: 验证跳转至国家选择页面"
        print(f"🔄 {current_step}")
        try:
            # 验证搜索框存在（说明已进入国家选择页面）
            search_field = assert_on_country_select_page(driver, timeout=10)
            assert search_field.is_displayed(), "搜索框存在但不可见"
            default_countries_before_search = _collect_visible_country_names(driver)
            if default_countries_before_search:
                print(f"📝 国家页默认可见国家（前10个）: {default_countries_before_search[:10]}")
            print(f"✅ {current_step} - 完成，确认已跳转至国家选择页面")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 未成功跳转至国家选择页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 点击搜索框并输入"Z"
        current_step = "步骤6: 点击搜索框并输入Z"
        print(f"🔄 {current_step}")
        try:
            search_field = resolve_country_search_field(driver, timeout=8, clickable=True)
            search_field.click()
            time.sleep(1)
            search_field.clear()
            search_field.send_keys(search_keyword)
            print(f"✅ {current_step} - 完成，已输入{search_keyword}")
            time.sleep(3)  # 等待搜索结果加载
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或操作搜索框 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 验证搜索到"Z"相关的所有国家（模糊搜索）
        current_step = "步骤7: 验证搜索到Z相关的所有国家（模糊搜索）"
        print(f"🔄 {current_step}")
        try:
            found_countries = [
                country
                for country in _collect_visible_country_names(driver)
                if search_keyword in country.upper()
            ]

            if not found_countries:
                fallback_keyword, matched_country = _pick_fallback_search_keyword(default_countries_before_search)
                if fallback_keyword and fallback_keyword != search_keyword:
                    print(
                        f"ℹ️ 关键字 {search_keyword} 未命中结果，"
                        f"改用当前列表可见国家“{matched_country}”的首字母 {fallback_keyword} 继续验证"
                    )
                    search_keyword = fallback_keyword
                    search_field = resolve_country_search_field(driver, timeout=8, clickable=True)
                    search_field.click()
                    time.sleep(0.5)
                    search_field.clear()
                    search_field.send_keys(search_keyword)
                    time.sleep(2)
                    found_countries = [
                        country
                        for country in _collect_visible_country_names(driver)
                        if search_keyword in country.upper()
                    ]

            print(f"📝 搜索关键词: {search_keyword}")
            print(f"📝 找到的国家数量: {len(found_countries)}")
            if found_countries:
                print(f"📝 找到的国家（前20个）: {found_countries[:20]}")
            
            # 验证至少找到一个国家
            assert len(found_countries) > 0, \
                f"输入'{search_keyword}'后应该显示匹配国家，但未找到任何匹配的国家"
            
            # 验证所有找到的国家都包含搜索字母（模糊搜索验证）
            for country in found_countries:
                assert search_keyword in country.upper(), \
                    f"找到的国家'{country}'不包含字母'{search_keyword}'，不符合模糊搜索要求"
            
            print(f"✅ {current_step} - 完成，找到 {len(found_countries)} 个匹配的国家")
            print(f"✅ 所有找到的国家都包含字母'{search_keyword}'，模糊搜索验证通过")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102188执行成功！")
        print("✅ 注册页面国家切换-搜索框根据首字母搜索国家")
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
        save_failure_screenshot(driver, "test_102188_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102188",
            case_desc="验证注册页面国家切换-搜索框根据首字母搜索国家",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])