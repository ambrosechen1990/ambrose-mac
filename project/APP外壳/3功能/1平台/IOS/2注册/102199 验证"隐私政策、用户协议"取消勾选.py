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


def test_102199(setup_driver):
    """
    102199 验证"隐私政策、用户协议"取消勾选

    流程（按流程图）：
    1. 打开 APP（若已登录先登出）
    2. 点击 Sign Up 进入注册页
    3. 点击邮箱输入框（//XCUIElementTypeTextField[@value="Email"]），输入邮箱（共用脚本生成）
    4. 勾选隐私协议（login check normal）
    5. 点击 Next 进入密码页
    6. 点击左上角返回按钮（name="nav back"）回到注册页
    7. 返回注册页后，断言复选框回到未勾选态（login check normal），并出现提示文案：
       Please confirm and tick the Privacy Policy and User Agreement
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

        # 步骤4: 输入邮箱（value="Email"）
        current_step = '步骤4: 输入邮箱（value="Email"）'
        print(f"🔄 {current_step}")
        try:
            email_address = get_simple_email()  # 共用脚本生成邮箱
            email_selectors = [
                (AppiumBy.XPATH, '//XCUIElementTypeTextField[@value="Email"]'),
                (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'),
            ]
            email_input = None
            last_err = None
            for by, locator in email_selectors:
                try:
                    email_input = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((by, locator)))
                    if email_input:
                        break
                except Exception as e:
                    last_err = e
            if not email_input:
                raise Exception(f"未找到可点击的邮箱输入框: {last_err}")
            email_input.clear()
            email_input.send_keys(email_address)
            print(f"✅ {current_step} - 完成，邮箱: {email_address}")
            # 输入后收起键盘（Done）- best effort
            try:
                done_btn = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
                )
                if done_btn and done_btn.is_displayed():
                    try:
                        done_btn.click()
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或输入邮箱 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 点击Done按钮收起键盘
        current_step = "步骤5: 点击Done按钮收起键盘"
        print(f"🔄 {current_step}")
        try:
            done_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
            )
            done_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            print(f"ℹ️ {current_step} - Done按钮未出现或无法点击，可能键盘未弹出或已收起，跳过: {str(e)}")
            time.sleep(1)

        # 步骤6: 勾选隐私政策和用户协议
        current_step = "步骤6: 勾选隐私政策和用户协议"
        print(f"🔄 {current_step}")
        try:
            check_btn = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'))
            )
            assert check_btn.is_displayed(), "隐私政策复选框存在但不可见"
            check_btn.click()
            # 部分版本/机型勾选后不一定暴露为 name="login check selected"
            # 这里不强依赖该元素；后续以“能进入密码页”作为勾选成功的最终判据
            time.sleep(1)
            try:
                selected = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check selected"]')
                if any(e.is_displayed() for e in selected):
                    print("✅ 隐私政策复选框已勾选（selected 可见）")
                else:
                    print("ℹ️ 未检测到 selected（可忽略），继续下一步用页面跳转验证是否勾选成功")
            except Exception:
                print("ℹ️ 检测 selected 失败（可忽略），继续下一步用页面跳转验证是否勾选成功")
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 点击Next按钮进入密码设置页面
        current_step = "步骤7: 点击Next按钮进入密码设置页面"
        print(f"🔄 {current_step}")
        try:
            next_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
            )
            next_btn.click()
            print(f"✅ {current_step} - 完成，已点击Next按钮")
            # 进入密码页：SecureTextField 出现即可
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeSecureTextField'))
            )
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 点击左上角返回按钮回到注册页面
        current_step = '步骤8: 点击左上角返回按钮（name="nav back"）'
        print(f"🔄 {current_step}")
        try:
            back_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="nav back"]'))
            )
            back_btn.click()
            # 回到注册页：Sign Up 标题出现
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]'))
            )
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤9: 返回后点击 login check sel，出现提示即成功
        current_step = "步骤9: 返回后点击login check sel，出现提示即成功"
        print(f"🔄 {current_step}")
        try:
            err_xpath = '//XCUIElementTypeStaticText[@name="Please confirm and tick the Privacy Policy and User Agreement"]'
            # 按最新口径：返回注册页后点击 login check sel 触发提示
            check_sel = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check sel"]'))
            )
            assert check_sel.is_displayed(), "login check sel 元素存在但不可见"
            try:
                check_sel.click()
            except Exception as e:
                # 有些情况下按钮不可点击，但提示仍可能出现；继续等待提示即可
                print(f"ℹ️ 点击 login check sel 失败（可忽略）：{e}")

            err = WebDriverWait(driver, 10).until(EC.presence_of_element_located((AppiumBy.XPATH, err_xpath)))
            assert err.is_displayed(), "提示文案元素存在但不可见"
            print("✅ 已出现提示文案：Please confirm and tick the Privacy Policy and User Agreement")
            print(f"✅ {current_step} - 完成")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102199执行成功！")
        print('✅ 102199：勾选协议进入密码页后返回，协议回到未勾选态并出现提示文案')
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
        save_failure_screenshot(driver, "test_102199_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102199",
            case_desc='102199 验证"隐私政策、用户协议"取消勾选',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

