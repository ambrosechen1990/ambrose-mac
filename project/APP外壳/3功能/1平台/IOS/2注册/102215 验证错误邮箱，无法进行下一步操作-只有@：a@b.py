import pytest  # 导入pytest用于测试
import time  # 导入time用于延时
import traceback  # 导入traceback用于异常追踪
import os
from appium import webdriver  # 导入appium的webdriver
from appium.webdriver.common.appiumby import AppiumBy  # 导入AppiumBy用于元素定位
from selenium.webdriver.support.ui import WebDriverWait  # 导入WebDriverWait用于显式等待
from selenium.webdriver.support import expected_conditions as EC  # 导入EC用于等待条件
from selenium.common.exceptions import TimeoutException
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
    assert_on_signup_page,
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


def test_102215(setup_driver):
    """
    102215 验证错误邮箱，无法进行下一步操作-只有@：a@b
    1. 打开APP，点击首页"2注册"按钮
    2. 进入Sign Up页面
    3. 邮箱输入错误格式（如：asd@gmial）
    4. 勾选隐私政策与用户协议
    5. 点击Next按钮
    6. 断言仍停留在当前页面，并提示"Please sign up using your email address"
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

        # 步骤4: 邮箱输入错误格式 asd@gmial
        current_step = "步骤4: 邮箱输入错误格式"
        print(f"🔄 {current_step}")
        try:
            wrong_email = "asd@gmial"
            email_input = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
            )
            email_input.clear()
            email_input.send_keys(wrong_email)
            print(f"✅ {current_step} - 完成，输入错误邮箱: {wrong_email}")
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

        # 新增步骤: 收起键盘（Done）
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

        # 步骤6: 点击Next按钮
        current_step = "步骤6: 点击Next按钮"
        print(f"🔄 {current_step}")
        try:
            next_btn_selectors = [
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next "]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
                (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeButton" AND name CONTAINS "Next"'),
            ]

            next_btn = None
            for by, sel in next_btn_selectors:
                try:
                    candidate = WebDriverWait(driver, 4).until(
                        EC.presence_of_element_located((by, sel))
                    )
                    if candidate and candidate.is_displayed():
                        next_btn = candidate
                        break
                except Exception:
                    continue

            if next_btn is None:
                raise TimeoutException("未找到 Next 按钮元素")

            try:
                next_btn.click()
            except Exception:
                rect = next_btn.rect or {}
                tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
                tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
                driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
            print(f"✅ {current_step} - 完成，已点击Next按钮")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Next按钮 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 验证停留当前页面，提示信息出现
        current_step = "步骤7: 验证停留当前页面并出现提示"
        print(f"🔄 {current_step}")
        try:
            # 验证隐私协议元素仍在，说明仍停留在注册页
            assert_on_signup_page(driver, timeout=5)

            # 查找提示信息
            error_selectors = [
                '//XCUIElementTypeStaticText[@name="Please sign up using your email address"]',
                '//XCUIElementTypeStaticText[contains(@name, "Please sign up using your email address")]',
                '//XCUIElementTypeStaticText[contains(@name, "email address")]',
            ]
            error_elem = None
            error_text = None
            for sel in error_selectors:
                try:
                    elems = driver.find_elements(AppiumBy.XPATH, sel)
                    for elem in elems:
                        if elem.is_displayed():
                            error_elem = elem
                            error_text = elem.get_attribute("name")
                            print(f"✅ 找到提示信息元素，选择器: {sel}")
                            break
                    if error_elem:
                        break
                except:
                    continue

            assert error_elem is not None, "未找到错误提示元素"
            assert "Please sign up using your email address" in (error_text or ""), f"提示内容不匹配: {error_text}"
            print(f"✅ {current_step} - 完成，提示信息: {error_text}")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102215执行成功！")
        print('✅ 验证错误邮箱（缺少合法域）勾选隐私后点击Next，停留当前页并提示“Please sign up using your email address”')
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
        save_failure_screenshot(driver, "test_102215_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102215",
            case_desc='102215 验证错误邮箱，无法进行下一步操作-只有@：a@b',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])
