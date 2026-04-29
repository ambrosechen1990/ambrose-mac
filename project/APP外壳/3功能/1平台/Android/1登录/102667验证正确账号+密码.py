import pytest  # 导入pytest用于测试
import time  # 导入time用于延时
import traceback  # 导入traceback用于异常追踪
import os
from appium import webdriver  # 导入appium的webdriver
from appium.webdriver.common.appiumby import AppiumBy  # 导入AppiumBy用于元素定位
from selenium.webdriver.support.ui import WebDriverWait  # 导入WebDriverWait用于显式等待
from selenium.webdriver.support import expected_conditions as EC  # 导入EC用于等待条件
from appium.options.android import UiAutomator2Options  # 导入Android的UiAutomator2选项
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


@pytest.fixture(scope="function")
def setup_driver():
    """
    Android设备驱动配置 - 为每个测试函数创建独立的WebDriver实例
    """
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.platform_version = "15"
    options.device_name = "Android Device"
    options.automation_name = "UiAutomator2"
    options.app_package = "com.xingmai.tech"
    # 不设置app_activity，让Appium自动检测启动Activity
    options.new_command_timeout = 3600
    options.no_reset = True  # 不重置应用，通过 terminate_app + activate_app 手动重启
    options.full_reset = False

    driver = webdriver.Remote(
        command_executor="http://localhost:4730",
        options=options,
    )
    driver.implicitly_wait(5)
    yield driver
    if driver:
        driver.quit()


def _fill_edit_text(driver, index: int, text: str, field_desc: str):
    """
    通用输入方法：支持 Compose 下的 EditText 输入，包含 set_value/send_keys/ADB 多级兜底
    index: 第几个 EditText（1=邮箱，2=密码）
    """
    print(f"    🔄 准备输入{field_desc}: {text}")
    area_xpath = f"//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[{index}]/android.view.View[1]"
    input_xpath = f"//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.widget.EditText[{index}]"

    # 先点击输入区域激活
    area = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, area_xpath))
    )
    area.click()
    time.sleep(0.8)

    # 再找到真正的 EditText
    edit = WebDriverWait(driver, 5).until(
        EC.presence_of_element_located((AppiumBy.XPATH, input_xpath))
    )

    # 优先 set_value
    try:
        edit.set_value(text)
        print(f"    ✅ 使用 set_value 输入{field_desc}")
        return
    except Exception as e1:
        print(f"    ⚠️ set_value 输入{field_desc}失败，尝试 send_keys: {e1}")

    # 再尝试 clear + send_keys
    try:
        edit.clear()
        edit.send_keys(text)
        print(f"    ✅ 使用 send_keys 输入{field_desc}")
        return
    except Exception as e2:
        print(f"    ⚠️ send_keys 输入{field_desc}失败，尝试 ADB: {e2}")

    # 最后兜底 ADB
    try:
        import subprocess

        safe_text = text.replace("@", "\\@").replace(".", "\\.")
        subprocess.run(
            ["adb", "shell", "input", "text", safe_text],
            capture_output=True,
            timeout=5,
        )
        print(f"    ✅ 使用 ADB 输入{field_desc}")
    except Exception as e3:
        print(f"    ❌ ADB 输入{field_desc}也失败: {e3}")
        raise


def test_102667(setup_driver):
    """
    验证正确账号+密码登录（Android）

    1. 重置APP，检测登录状态，如果已登录则执行登出（logout_android.check_and_logout）
    2. 点击登录按钮进入 Sign in 页面
    3. 点击邮箱框，输入邮箱：CHENhao2026@gmail.com
    4. 点击密码框，输入密码：csx150128
    5. 收起输入键盘
    6. 勾选协议勾选框
    7. 点击登录按钮
    8. 断言页面显示 More 按钮（Compose 路径或 content-desc="More"）
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        # 步骤1: 重置APP，检测登录状态，如果已登录则登出
        current_step = "步骤1: 重置APP，检测登录状态并登出"
        print(f"🔄 {current_step}")
        try:
            caps = driver.capabilities
            app_package = caps.get("appPackage") or "com.xingmai.tech"
            driver.terminate_app(app_package)
            time.sleep(1.5)
            driver.activate_app(app_package)
            time.sleep(2)
            print("    ✅ APP已重置")

            # 检测是否已登录（查找 Home/More 元素）
            is_logged_in = False
            login_indicators = [
                '//android.view.View[@content-desc="Home"]',
                '//android.view.View[@content-desc="More"]',
                # 用户提供的正确路径
                "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.view.View[2]",
                # 备用路径（旧版本兼容）
                "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[3]/android.view.View[2]",
            ]
            for xp in login_indicators:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, xp)
                    for elem in elements:
                        if elem.is_displayed():
                            is_logged_in = True
                            print(f"    ✅ 检测到已登录状态: {xp}")
                            break
                    if is_logged_in:
                        break
                except Exception:
                    continue

            if is_logged_in:
                print("    🔄 检测到已登录，执行登出操作 (logout_android)...")
                time.sleep(1)  # 等待页面稳定
                try:
                    check_and_logout(driver)
                    print("    ✅ 登出操作完成")
                    time.sleep(1.5)
                except Exception as logout_error:
                    print(f"    ⚠️ 登出操作失败: {logout_error}")
                    # 登出失败不应该阻止测试继续，但记录错误
                    fail_reason = f"登出操作失败: {logout_error}"
                    raise
            else:
                print("    ℹ️ 未检测到登录状态，已在登录/登录页")

            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤2: 点击登录按钮，进入 Sign in 页面
        current_step = "步骤2: 点击登录按钮进入Sign in页面"
        print(f"🔄 {current_step}")
        try:
            sign_in_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (
                        AppiumBy.XPATH,
                        "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[1]/android.widget.Button",
                    )
                )
            )
            sign_in_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击Sign In按钮 - {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 输入邮箱
        current_step = "步骤3: 点击邮箱框，输入邮箱"
        print(f"🔄 {current_step}")
        try:
            email = "CHENhao2026@gmail.com"
            _fill_edit_text(driver, 1, email, "邮箱")
            time.sleep(1)
            print(f"✅ {current_step} - 完成（邮箱={email}）")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤4: 输入密码
        current_step = "步骤4: 点击密码框，输入密码"
        print(f"🔄 {current_step}")
        try:
            password = "csx150128"
            _fill_edit_text(driver, 2, password, "密码")
            print("    ✅ 密码输入完成")
            time.sleep(1)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤5: 收起输入键盘
        current_step = "步骤5: 收起输入键盘"
        print(f"🔄 {current_step}")
        try:
            driver.press_keycode(4)  # KEYCODE_BACK
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            print(f"    ⚠️ 收起键盘失败: {e}，继续执行")

        # 步骤6: 勾选协议
        current_step = "步骤6: 点击协议勾选框"
        print(f"🔄 {current_step}")
        try:
            checkbox = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="checkbox"]')
                )
            )
            checkbox.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1)
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤7: 点击登录按钮
        current_step = "步骤7: 点击登录按钮"
        print(f"🔄 {current_step}")
        try:
            login_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="next"]')
                )
            )
            login_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(3)  # 等待跳转首页
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击登录(next)按钮 - {e}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤8: 断言登录成功，校验 More 按钮
        current_step = "步骤8: 断言登录成功，校验More按钮"
        print(f"🔄 {current_step}")
        try:
            more_selectors = [
                # content-desc 为 More 的视图（优先使用）
                '//android.view.View[@content-desc="More"]',
                # Compose 路径（用户提供的正确路径）
                "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.view.View[2]",
                # 备用 Compose 路径（旧版本兼容）
                "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[3]/android.view.View[2]",
            ]

            more_found = False
            for selector in more_selectors:
                try:
                    more_btn = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, selector))
                    )
                    if more_btn.is_displayed():
                        more_found = True
                        desc = more_btn.get_attribute("content-desc") or ""
                        print(f"    ✅ 找到More按钮: {selector}, content-desc={desc}")
                        break
                except Exception:
                    continue

            assert more_found, "未找到 More 按钮，登录可能未成功"
            print("✅ 登录成功，底部More按钮已显示（Android使用More而非mine）")
            print("🎉 测试用例102667执行成功！")
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
        save_failure_screenshot(driver, "test_102667_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="102667",
            case_desc="验证正确账号+密码登录，并校验More按钮",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
