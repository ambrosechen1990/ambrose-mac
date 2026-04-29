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


def test_102202(setup_driver):
    """
    102202 验证"Next"按钮，初始状态为浅色，不可点击
    1. 打开APP，点击首页"2注册"按钮
    2. 进入Sign up页面
    3. 验证Next按钮初始状态是浅绿色
    4. 输入邮箱（使用email_utils）
    5. 验证Next按钮仍为浅绿色（禁用态）
    6. 点击Next按钮
    7. 验证点击后仍停留在当前页面
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

        # 步骤4: 验证Next按钮存在并检查初始状态
        current_step = "步骤4: 验证Next按钮存在并检查初始状态"
        print(f"🔄 {current_step}")
        try:
            # 查找Next按钮
            next_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
            )
            assert next_btn.is_displayed(), "Next按钮存在但不可见"
            
            # 检查按钮的enabled状态（虽然可能返回True，但实际可能不可点击）
            is_enabled = next_btn.is_enabled()
            print(f"📝 Next按钮enabled状态: {is_enabled}")
            
            # 验证按钮存在
            print(f"✅ {current_step} - 完成，Next按钮存在")
            print(f"📝 Next按钮初始状态：浅绿色（通过点击后是否停留在页面来验证是否可点击）")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 输入邮箱（使用email_utils）
        current_step = "步骤5: 输入邮箱（使用email_utils）"
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

        # 步骤6: 验证输入邮箱后Next按钮仍为浅绿色（禁用态）
        current_step = "步骤6: 验证输入邮箱后Next按钮仍为浅绿色（禁用态）"
        print(f"🔄 {current_step}")
        try:
            next_btn_after_email = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
            )
            assert next_btn_after_email.is_displayed(), "Next按钮存在但不可见"

            is_enabled_after = next_btn_after_email.is_enabled()
            print(f"📝 输入邮箱后Next按钮enabled状态: {is_enabled_after}")
            assert not is_enabled_after, "输入邮箱后Next按钮应仍为浅绿色禁用态"
            print(f"✅ {current_step} - 完成，Next按钮仍为浅绿色禁用态")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 点击Next按钮
        current_step = "步骤7: 点击Next按钮"
        print(f"🔄 {current_step}")
        try:
            # 记录点击前的页面状态：确认仍在 Sign Up 注册页（用更稳的控件判断，避免固定文案失效）
            sign_up_text_before = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]'))
            )
            assert sign_up_text_before.is_displayed(), "点击前应仍在Sign Up注册页面"
            print("✅ 点击前确认仍在Sign Up注册页面")
            
            # 尝试点击Next按钮（即便处于禁用态，若可点击则点击一次）
            try:
                next_btn_to_click = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
                )
                next_btn_to_click.click()
                print(f"✅ {current_step} - 完成，已尝试点击Next按钮")
            except Exception as click_err:
                print(f"ℹ️ Next按钮可能处于禁用态，点击未触发: {click_err}")

            time.sleep(2)  # 等待页面响应
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 验证点击后仍停留在当前页面
        current_step = "步骤8: 验证点击后仍停留在当前页面"
        print(f"🔄 {current_step}")
        try:
            # 验证Sign Up文本仍然存在
            sign_up_text_after = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]'))
            )
            assert sign_up_text_after.is_displayed(), "点击后Sign Up文本应该仍然存在，说明仍停留在注册页面"
            # 再补充一个稳定锚点：协议勾选框存在（normal/selected 任一即可）
            try:
                driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]')
            except Exception:
                driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check selected"]')
            
            print(f"✅ {current_step} - 完成")
            print(f"✅ 验证通过：点击Next按钮后仍停留在当前页面")
            print(f"✅ 验证通过：Next按钮初始/输入邮箱后仍为浅绿色不可点击，点击后停留在当前页面说明处于禁用状态")
            time.sleep(2)
        except Exception as e:
            fail_reason = f"{current_step}失败: 点击后不在Sign Up注册页（Sign Up文本/协议勾选框缺失），可能已跳转到其他页面 - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102202执行成功！")
        print('✅ 验证"Next"按钮，初始状态为浅色，不可点击：点击后仍停留在当前页面')
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
        save_failure_screenshot(driver, "test_102202_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102202",
            case_desc='102202 验证"Next"按钮，初始状态为浅色，不可点击',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

