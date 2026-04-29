import pytest
import time
import traceback
import subprocess
import os
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

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common_utils_android import (
check_and_logout,
    save_failure_screenshot,
    init_report,
    bind_logger_to_print,
    write_report,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)


def adb_input_text(text: str):
    try:
        safe_text = text.replace(" ", "%s")
        subprocess.run(
            ["adb", "shell", "input", "text", safe_text],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except Exception as e:
        print(f"    ⚠️ ADB 输入文本失败: {e}")
        return False


def fill_compose_input(driver, index: int, text: str, field_desc: str = ""):
    current_desc = field_desc or f"第{index}个输入框"
    print(f"    🔄 准备输入 {current_desc} 文本: {text}")
    try:
        click_xpath = f'//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[{index}]/android.view.View[1]'
        input_xpath = f'//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[{index}]'

        try:
            click_area = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, click_xpath))
            )
            click_area.click()
            time.sleep(0.5)
        except Exception as e:
            print(f"    ⚠️ 点击{current_desc}外层区域失败（可忽略）: {e}")

        input_el = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.XPATH, input_xpath))
        )

        try:
            input_el.set_value(text)
            print(f"    ✅ 通过 set_value 填写{current_desc}完成")
            return True
        except Exception as e1:
            print(f"    ⚠️ set_value 输入{current_desc}失败: {e1}")

        try:
            input_el.clear()
            time.sleep(0.3)
            input_el.send_keys(text)
            print(f"    ✅ 通过 send_keys 填写{current_desc}完成")
            return True
        except Exception as e2:
            print(f"    ⚠️ send_keys 输入{current_desc}失败: {e2}")

        if adb_input_text(text):
            print(f"    ✅ 通过 ADB 填写{current_desc}完成")
            return True

        print(f"    ❌ 无法向{current_desc}输入文本")
        return False
    except Exception as e:
        print(f"    ❌ 填写{current_desc}时异常: {e}")
        return False


@pytest.fixture(scope="function")
def setup_driver():
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.platform_version = "15"
    options.automation_name = "UiAutomator2"
    options.device_name = "Android"
    options.app_package = "com.xingmai.tech"
    options.new_command_timeout = 300
    options.no_reset = True

    driver = None
    try:
        driver = webdriver.Remote("http://127.0.0.1:4723/wd/hub", options=options)
        yield driver
    finally:
        if driver:
            driver.quit()


def test_102652(setup_driver):
    """
    验证正确密码，邮箱未注册，无法登录（Android）
    1. 重置APP，检测登录状态，如果已登录则登出
    2. 进入 Sign in 页面
    3. 输入未注册邮箱：haoc51888chenhao@gmail.com
    4. 输入密码：Csx150128
    5. 勾选用户协议和隐私政策
    6. 点击登录按钮
    7. 断言提示：This email is not registered. Please check and re-enter.
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        current_step = "步骤1: 重置APP并根据需要登出"
        print(f"🔄 {current_step}")
        try:
            caps = driver.capabilities
            app_package = caps.get("appPackage") or "com.xingmai.tech"
            driver.terminate_app(app_package)
            time.sleep(1.5)
            driver.activate_app(app_package)
            time.sleep(2)
            print("    ✅ APP已重启（不清除数据）")

            is_logged_in = False
            login_indicators = [
                '//android.view.View[@content-desc="More"]',
                '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[3]/android.view.View[2]',
            ]
            for xp in login_indicators:
                try:
                    els = driver.find_elements(AppiumBy.XPATH, xp)
                    for el in els:
                        if el.is_displayed():
                            is_logged_in = True
                            print(f"    ✅ 检测到已登录状态: {xp}")
                            break
                    if is_logged_in:
                        break
                except Exception:
                    continue

            if is_logged_in:
                print("    🔄 执行登出流程...")
                check_and_logout(driver)
                time.sleep(1.5)
                print("    ✅ 已登出")
            else:
                print("    ℹ️ 未检测到登录态，保持当前状态")

            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤2: 进入 Sign in 页面"
        print(f"🔄 {current_step}")
        try:
            sign_in_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable(
                    (
                        AppiumBy.XPATH,
                        '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[1]/android.widget.Button',
                    )
                )
            )
            sign_in_btn.click()
            time.sleep(1.5)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法进入Sign in页面 - {e}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤3: 输入未注册邮箱"
        print(f"🔄 {current_step}")
        try:
            email = "haoc51888chenhao@gmail.com"
            if not fill_compose_input(driver, 1, email, "邮箱输入框"):
                raise RuntimeError("邮箱输入失败")
            print(f"    ✅ 已输入未注册邮箱: {email}")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤4: 输入密码"
        print(f"🔄 {current_step}")
        try:
            password = "Csx150128"
            if not fill_compose_input(driver, 2, password, "密码输入框"):
                raise RuntimeError("密码输入失败")
            print("    ✅ 密码输入完成")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤5: 勾选协议"
        print(f"🔄 {current_step}")
        try:
            checkbox = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable(
                    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="checkbox"]')
                )
            )
            checkbox.click()
            time.sleep(0.8)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: 勾选协议失败 - {e}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤6: 点击登录按钮"
        print(f"🔄 {current_step}")
        try:
            login_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable(
                    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="next"]')
                )
            )
            login_btn.click()
            time.sleep(2)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: 点击登录失败 - {e}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤7: 断言提示未注册邮箱错误"
        print(f"🔄 {current_step}")
        try:
            msg_selectors = [
                '//android.widget.TextView[@text="This email is not registered. Please check and re-enter."]',
                '//android.widget.TextView[contains(@text, "This email is not registered")]',
            ]
            found = False
            for xp in msg_selectors:
                try:
                    msg_el = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, xp))
                    )
                    if msg_el.is_displayed():
                        text_val = msg_el.get_attribute("text") or ""
                        print(f"    ✅ 找到错误提示: {text_val}")
                        found = True
                        break
                except Exception:
                    continue

            assert found, "未找到未注册邮箱错误提示文案"
            print(f"✅ {current_step} - 完成")
            print("🎉 测试用例102652执行成功！")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {e}"
        print("\n" + "=" * 60)
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print("=" * 60)
        traceback.print_exc()
        save_failure_screenshot(driver, "test_102652_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="102652",
            case_desc="验证正确密码，邮箱未注册，无法登录",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])


