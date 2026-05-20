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


def test_102203(setup_driver):
    """
    102203 验证只填写正确邮箱，“Next”按钮还是浅色，不可点击

    流程（按流程图）：
    1. 打开 APP（若已登录先登出）
    2. 点击 Sign Up 进入注册页
    3. 点击 Next（未输入邮箱、未勾选协议）→ 页面提示：
       Please confirm and tick the Privacy Policy and User Agreement
    4. 输入邮箱（//XCUIElementTypeTextField[@value="Email"]，邮箱使用共用脚本生成）
    5. 再点击 Next → 仍提示上述文案（仍停留在注册页）
    6. 勾选协议（login check normal）
    7. 点击 Next → 进入 Set Password 页面（出现 StaticText: Set Password）
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

        # 步骤4: 点击 Next
        current_step = "步骤4: 点击Next（未输入邮箱、未勾选协议）"
        print(f"🔄 {current_step}")
        try:
            WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
            ).click()
            err = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located(
                    (
                        AppiumBy.XPATH,
                        '//XCUIElementTypeStaticText[@name="Please sign up using your email address"]',
                    )
                )
            )
            assert err.is_displayed(), "提示文案元素存在但不可见"
            print("✅ 已出现提示：Please sign up using your email address")
            # 仍在注册页
            assert WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]'))
            ).is_displayed()
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 输入邮箱（value="Email"）
        current_step = '步骤5: 输入邮箱（value="Email"）'
        print(f"🔄 {current_step}")
        try:
            email_address = get_simple_email()
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
            # 输入后收起键盘（Done）- best effort，避免遮挡 Next
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
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤6: 再次点击 Next（仍应提示，仍停留注册页）
        current_step = "步骤6: 再次点击Next（仍应提示）"
        print(f"🔄 {current_step}")
        try:
            # Next 可能处于禁用态，element_to_be_clickable 会超时；改为 presence + best-effort click
            next_selectors = [
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next "]'),
                (AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Next"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeOther[@name="Next"]'),
            ]
            next_btn = None
            last_err = None
            for by, locator in next_selectors:
                try:
                    next_btn = WebDriverWait(driver, 6).until(EC.presence_of_element_located((by, locator)))
                    if next_btn and next_btn.is_displayed():
                        break
                except Exception as e:
                    last_err = e
                    continue
            if not next_btn:
                raise Exception(f"未找到 Next 元素: {last_err}")
            try:
                next_btn.click()
            except Exception as click_err:
                print(f"ℹ️ Next 可能处于禁用态，点击未触发（可忽略）：{click_err}")

            err = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located(
                    (
                        AppiumBy.XPATH,
                        '//XCUIElementTypeStaticText[@name="Please confirm and tick the Privacy Policy and User Agreement"]',
                    )
                )
            )
            assert err.is_displayed(), "提示文案元素存在但不可见"
            assert WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]'))
            ).is_displayed()
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 勾选协议（login check normal）
        current_step = "步骤7: 勾选协议（login check normal）"
        print(f"🔄 {current_step}")
        try:
            # 不同版本勾选框 name 可能不一致（normal/sel/selected）
            check_selectors = [
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check sel"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check selected"]'),
                (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"login check")]'),
            ]
            check_btn = None
            last_err = None
            for by, locator in check_selectors:
                try:
                    check_btn = WebDriverWait(driver, 6).until(EC.presence_of_element_located((by, locator)))
                    if check_btn and check_btn.is_displayed():
                        break
                except Exception as e:
                    last_err = e
                    continue
            if not check_btn:
                raise Exception(f"未找到协议勾选按钮: {last_err}")

            try:
                check_btn.click()
            except Exception as click_err:
                # 有些勾选按钮可见但不可点击（被遮挡/禁用），继续交给下一步跳转判定
                print(f"ℹ️ 勾选按钮点击失败（可忽略）：{click_err}")

            print(f"✅ {current_step} - 完成（后续以进入 Set Password 判定是否勾选成功）")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 点击 Next → 进入 Set Password 页面
        current_step = "步骤8: 点击Next进入Set Password页面"
        print(f"🔄 {current_step}")
        try:
            # Next 可能仍被判定为不可点击，这里 best-effort 点击
            try:
                WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'))
                ).click()
            except Exception as click_err:
                print(f"ℹ️ 点击 Next 失败（可忽略，继续等待页面跳转）：{click_err}")
            set_pwd = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Set Password"]'))
            )
            assert set_pwd.is_displayed(), "Set Password 文案存在但不可见"
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例102203执行成功！")
        print('✅ 102203：只填写正确邮箱时 Next 不可进入 Set Password；勾选协议后可进入 Set Password')
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
        save_failure_screenshot(driver, "test_102203_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="102203",
            case_desc='102203 验证只填写正确邮箱，“Next”按钮还是浅色，不可点击',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    # 直接运行时，用 pytest 执行当前文件
    pytest.main(["-s", __file__])

