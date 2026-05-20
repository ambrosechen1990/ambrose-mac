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


def test_102187(setup_driver):
    """
    验证注册页面国家切换-清空搜索内容
    1. APP首页点击sign up按钮
    2. 进入sign up页面
    3. 点击国家栏下拉按钮
    4. 跳转至国家选择页面
    5. 点击搜索框，输入"Americ"
    6. 验证下面显示多个国家（筛选结果）
    7. 点击清除按钮
    8. 验证筛选出来的国家消失了，显示默认状态下的国家
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

        # 步骤4: 点击国家栏下拉按钮
        current_step = "步骤4: 点击国家栏下拉按钮"
        print(f"🔄 {current_step}")
        try:
            # 查找国家栏下拉按钮
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
            # 用多策略搜索框定位确认已进入国家选择页面
            search_field = assert_on_country_select_page(driver, timeout=10)
            assert search_field.is_displayed(), "搜索框存在但不可见"
            print(f"✅ {current_step} - 完成，确认已跳转至国家选择页面")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 未成功跳转至国家选择页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 点击搜索框并输入"Americ"
        current_step = "步骤6: 点击搜索框并输入Americ"
        print(f"🔄 {current_step}")
        try:
            search_field = resolve_country_search_field(driver, timeout=8, clickable=True)
            search_field.click()
            time.sleep(1)
            search_field.clear()
            search_field.send_keys("Americ")
            print(f"✅ {current_step} - 完成，已输入Americ")
            time.sleep(3)  # 等待搜索结果加载
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或操作搜索框 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 验证下面显示多个国家
        current_step = "步骤7: 验证下面显示多个国家"
        print(f"🔄 {current_step}")
        try:
            # 查找包含"Americ"的国家选项（应该显示多个，如America, American Samoa等）
            country_selectors = [
                '//XCUIElementTypeStaticText[contains(@name, "Americ")]',
                '//XCUIElementTypeButton[contains(@name, "Americ")]',
                '//XCUIElementTypeOther[contains(@name, "Americ")]',
                '//XCUIElementTypeCell[contains(@name, "Americ")]',
            ]
            
            found_countries = []
            for selector in country_selectors:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                    for elem in elements[:20]:  # 限制检查数量
                        try:
                            if elem.is_displayed():
                                country_name = elem.get_attribute("name")
                                if country_name and "Americ" in country_name:
                                    found_countries.append(country_name)
                        except:
                            continue
                except:
                    continue
            
            print(f"📝 找到的国家数量: {len(found_countries)}")
            if found_countries:
                print(f"📝 找到的国家（前10个）: {found_countries[:10]}")

            found_countries = list(dict.fromkeys(found_countries))
            
            # 验证至少找到一个国家
            assert len(found_countries) > 0, \
                f"输入'Americ'后应该显示多个国家，但未找到任何匹配的国家"
            
            print(f"✅ {current_step} - 完成，找到 {len(found_countries)} 个匹配的国家")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 点击清除按钮
        current_step = "步骤8: 点击清除按钮"
        print(f"🔄 {current_step}")
        try:
            # 使用真机页面实际的删除按钮 commonDelete 清空搜索内容
            clear_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="commonDelete"]'))
            )
            assert clear_btn.is_displayed(), "清除按钮存在但不可见"
            clear_btn.click()

            def _search_text_cleared(_driver):
                try:
                    current_search_field = resolve_country_search_field(driver, timeout=3, clickable=False)
                    current_value = (current_search_field.get_attribute("value") or "").strip()
                    return current_value in {"", "Search"}
                except Exception:
                    return False

            WebDriverWait(driver, 8).until(_search_text_cleared)
            print(f"✅ {current_step} - 完成，已点击清除按钮")
            time.sleep(2)  # 等待搜索内容被清除
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击清除按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤9: 验证筛选出来的国家消失了，显示默认状态下的国家
        current_step = "步骤9: 验证筛选出来的国家消失了，显示默认状态下的国家"
        print(f"🔄 {current_step}")
        try:
            # 1. 验证搜索框内容已被清空
            search_field = resolve_country_search_field(driver, timeout=5, clickable=False)
            search_value = (search_field.get_attribute("value") or "").strip()
            print(f"📝 搜索框当前内容: '{search_value}'")
            assert search_value in {"", "Search"}, f"搜索框应该被清空，但当前内容为: '{search_value}'"

            # 2. 验证显示的是默认状态下的国家列表
            default_country_selectors = [
                '//XCUIElementTypeStaticText',
                '//XCUIElementTypeButton',
                '//XCUIElementTypeOther',
                '//XCUIElementTypeCell',
            ]

            default_countries = []
            for selector in default_country_selectors:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                    for elem in elements[:50]:  # 限制检查数量，避免过慢
                        try:
                            if elem.is_displayed():
                                country_name = elem.get_attribute("name")
                                # 过滤掉空值、搜索框、按钮等非国家名称的元素
                                if country_name and len(country_name) > 2 and len(country_name) < 50:
                                    # 排除搜索框、按钮等UI元素
                                    if country_name not in [
                                        "Search",
                                        "Clear text",
                                        "commonDelete",
                                        "Cancel",
                                        "Done",
                                        "Country/Region",
                                    ]:
                                        if country_name not in default_countries:
                                            default_countries.append(country_name)
                        except:
                            continue
                except:
                    continue

            print(f"📝 清除后显示的默认国家数量: {len(default_countries)}")
            if default_countries:
                print(f"📝 显示的默认国家（前20个）: {default_countries[:20]}")

            # 验证：清除后应该显示默认状态下的国家列表（应该有多个国家显示）
            assert len(default_countries) > 0, \
                f"点击清除按钮后，应该显示默认状态下的国家列表，但未找到任何国家"

            # 3. 验证列表不再只停留在搜索结果，而是恢复为默认列表
            non_filtered_countries = [
                country for country in default_countries
                if country not in found_countries and "Americ" not in country
            ]
            print(f"📝 清除后新增的非筛选国家数量: {len(non_filtered_countries)}")
            if non_filtered_countries:
                print(f"📝 清除后新增的非筛选国家（前10个）: {non_filtered_countries[:10]}")

            assert len(non_filtered_countries) > 0, (
                "点击清除按钮后，列表仍像是停留在搜索结果中；"
                f"当前仅识别到的国家: {default_countries[:10]}"
            )

            print(f"✅ {current_step} - 完成")
            print(f"✅ 验证通过：筛选出来的国家已消失，显示默认状态下的国家列表（共 {len(default_countries)} 个国家）")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102187执行成功！")
        print("✅ 注册页面国家切换-清空搜索内容：清除按钮功能正常，筛选出来的国家已消失，显示默认状态下的国家")
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
        save_failure_screenshot(driver, "test_102187_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102187",
            case_desc="验证注册页面国家切换-清空搜索内容",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])
