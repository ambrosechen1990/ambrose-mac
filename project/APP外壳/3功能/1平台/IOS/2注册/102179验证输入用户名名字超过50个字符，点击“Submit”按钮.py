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
from email_utils import get_next_unused_special_char_email
from common_utils import (
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


def test_102179(setup_driver):
    """
    验证输入用户名名字超过50个字符，点击"Submit"按钮
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

        # 步骤2-5: 输入邮箱 -> 勾选协议 -> Next -> 确认进入密码页（若后端提示邮箱已占用，自动换邮箱重试）
        current_step = "步骤2-5: 输入邮箱并进入设置密码页面"
        print(f"🔄 {current_step}")
        last_email = ""
        try:
            max_attempts = 6
            last_error = None

            for attempt in range(1, max_attempts + 1):
                # 2) 输入邮箱
                email_address = get_next_unused_special_char_email()
                last_email = email_address
                email_input = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
                )
                email_input.clear()
                email_input.send_keys(email_address)
                print(f"✅ 步骤2: 输入邮箱 - 完成（第{attempt}次尝试），邮箱: {email_address}")
                time.sleep(1.2)

                # 3) 勾选协议（已勾选则跳过）
                try:
                    driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check selected"]')
                except Exception:
                    check_btn = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'))
                    )
                    check_btn.click()
                print("✅ 步骤3: 同意隐私政策 - 完成")
                time.sleep(0.8)

                # 4) Done 收起键盘（可能不存在）
                try:
                    done_btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
                    )
                    done_btn.click()
                    print("✅ 步骤4: Done收起键盘 - 完成")
                    time.sleep(0.8)
                except Exception:
                    print("ℹ️ 步骤4: Done未出现，可能键盘已收起，跳过")

                # 5) 点击 Next
                next_btn = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
                )
                next_btn.click()
                print("✅ 步骤5: 点击Next - 完成")
                time.sleep(1.8)

                # 验证进入 set password 页面（短等待；失败则换邮箱重试）
                try:
                    WebDriverWait(driver, 6).until(
                        EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeSecureTextField[1]'))
                    )
                    WebDriverWait(driver, 6).until(
                        EC.presence_of_element_located((AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeSecureTextField[2]'))
                    )
                    print("✅ 已进入set password页面")
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    print(f"ℹ️ 第{attempt}次尝试未进入密码页，准备更换邮箱重试。原因: {e}")
                    # 若仍在注册页，继续下一轮；否则让异常抛出（避免误判）
                    try:
                        WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
                        )
                    except Exception:
                        raise
                    time.sleep(1.2)

            if last_error is not None:
                raise last_error

        except Exception as e:
            fail_reason = f"{current_step}失败: 未成功进入设置密码页面（最后一次邮箱: {last_email}） - {str(e)}"
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

        # 步骤9: 设置超过50个字符的用户名
        current_step = "步骤9: 设置超过50个字符的用户名"
        print(f"🔄 {current_step}")
        try:
            # 生成超过50个字符的用户名（使用60个字符）
            username = ran4(60)
            username_length = len(username)
            print(f"📝 生成的用户名长度: {username_length} 个字符")
            assert username_length > 50, f"用户名长度应该超过50个字符，实际: {username_length}"
            
            # 先尝试点击 Username 区域，再用更具体的输入框定位器输入
            username_entry_selectors = [
                (AppiumBy.XPATH, '//XCUIElementTypeTextField[@value="Username"]'),
                (
                    AppiumBy.XPATH,
                    '//XCUIElementTypeApplication[@name="Beatbot"]/XCUIElementTypeWindow[1]/'
                    'XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/'
                    'XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/'
                    'XCUIElementTypeOther/XCUIElementTypeOther'
                ),
                (AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Username"]'),
            ]

            clicked_entry = False
            for by, selector in username_entry_selectors:
                try:
                    username_entry = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((by, selector))
                    )
                    username_entry.click()
                    clicked_entry = True
                    print(f"✅ 已点击用户名区域: {selector}")
                    time.sleep(0.5)
                    break
                except Exception:
                    continue

            if not clicked_entry:
                print("ℹ️ 未命中用户名区域专用定位，直接尝试输入框定位")

            username_field_selectors = [
                (AppiumBy.XPATH, '//XCUIElementTypeTextField[@value="Username"]'),
                (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'),
            ]

            username_field = None
            for by, selector in username_field_selectors:
                try:
                    username_field = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((by, selector))
                    )
                    print(f"✅ 命中用户名输入框定位: {selector}")
                    break
                except Exception:
                    continue

            if username_field is None:
                raise Exception("未找到可输入的用户名输入框")

            username_field.clear()
            username_field.send_keys(username)
            print(f"✅ {current_step} - 完成，输入的用户名长度: {username_length} 个字符")
            print(f"📝 输入的用户名前50个字符: {username[:50]}")
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

        # 步骤11: 点击submit
        current_step = "步骤11: 点击submit"
        print(f"🔄 {current_step}")
        try:
            submit_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Submit"]'))
            )
            submit_btn.click()
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

        # 步骤13: 验证用户名只保留50个字符
        current_step = "步骤13: 验证用户名只保留50个字符"
        print(f"🔄 {current_step}")
        try:
            # 尝试多个可能的选择器
            username_selectors = [
                '//XCUIElementTypeStaticText[contains(@name, "Hi")]',
                '//XCUIElementTypeStaticText[contains(@name, "Username")]',
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

            # 期望显示格式: "Hi, " + 输入用户名的前50个字符
            expected_username = username[:50]  # 只取前50个字符
            expected_display = f"Hi, {expected_username}"
            
            # 断言用户名显示为输入用户名的前50个字符
            assert username_display == expected_display,                 f"用户名显示不正确，期望'{expected_display}'，实际显示: {username_display}"
            
            # 验证显示的用户名长度不超过50个字符（不包括"Hi, "）
            displayed_username = username_display.replace("Hi, ", "")
            assert len(displayed_username) == 50,                 f"显示的用户名长度应该为50个字符，实际: {len(displayed_username)} 个字符"
            
            print(f"✅ {current_step} - 完成")
            print(f"📝 输入的用户名长度: {len(username)} 个字符")
            print(f"📝 显示的用户名长度: {len(displayed_username)} 个字符（已截断为50个字符）")
            print(f"📝 显示的用户名: {displayed_username}")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102179执行成功！")
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
        save_failure_screenshot(driver, "test_102179_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102179",
            case_desc="验证输入用户名名字超过50个字符，点击Submit按钮",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])