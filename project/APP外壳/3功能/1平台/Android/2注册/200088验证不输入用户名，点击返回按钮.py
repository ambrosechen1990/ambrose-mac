"""
200088 验证不输入用户名，点击返回按钮（Android）。

  对齐 iOS 102247：
  步骤1～3：重启 → 入口页 → Sign Up
  步骤4～8：邮箱 → 勾选隐私 → 设置密码 → Next 进入用户名页
  步骤9：验证用户名页、不输入用户名
  步骤10：点击返回（//android.widget.ImageView[@content-desc="back"]）
  步骤11：断言跳转主页面（//android.view.View[@content-desc="More"]）
"""

import os
import sys
import time
import traceback
from pathlib import Path

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

_cur = Path(__file__).resolve().parent
if str(_cur) not in sys.path:
    sys.path.insert(0, str(_cur))
_shared = None
for _ in range(24):
    _cand = _cur / "1共用脚本"
    if _cand.is_dir() and (_cand / "common_utils_android.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 APP外壳/1共用脚本（需包含 common_utils_android.py）")

from common_utils_android import (  # noqa: E402
    check_and_logout,
    save_failure_screenshot,
    init_report,
    bind_logger_to_print,
    write_report,
)

from email_utils import get_simple_email  # noqa: E402
from register_case_base import (  # noqa: E402
    step_restart_app,
    step_ensure_landing,
    step_click_sign_up,
    step_assert_on_signup_page,
    dismiss_keyboard,
    step_type_email,
    step_toggle_checkbox,
    step_click_next,
    step_assert_on_password_page,
    step_type_passwords,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

# ---------- 元素定位（Android，集中在文件顶部便于维护）----------
XPATH_SIGN_UP = '//android.widget.TextView[@text="Sign Up"]'
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
XPATH_PASSWORD = "//android.widget.EditText"
XPATH_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
XPATH_NEXT = "//android.widget.Button"
XPATH_PASSWORD_EYE = '//android.widget.ImageView[@content-desc="lock"]'

# 主页面 More（对齐 iOS 102247/102248 返回后主页面判据）
XPATH_MORE = '//android.view.View[@content-desc="More"]'
XPATH_MORE_ALT = '//*[@content-desc="More"]'

# 用户名页返回按钮（用户指定）
XPATH_BACK = '//android.widget.ImageView[@content-desc="back"]'

# 用户名页
XPATH_SUBMIT = '//*[@text="Submit"]'
XPATH_SKIP = '//*[@text="Skip"]'
XPATH_USERNAME_FIELD = "//android.widget.EditText"
XPATH_PERSONAL_INFO = '//*[contains(@text,"Personal Information") or contains(@text,"Personal")]'

TEST_PASSWORD = os.environ.get("REGISTER_PASSWORD", "Csx150128")
_USERNAME_PLACEHOLDERS = ("", "Username", "username")


def _assert_on_username_page(driver, timeout_s: int = 15) -> None:
    """断言在 Personal Information / 用户名页，且未输入用户名。"""
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_BACK))
    )
    submit_visible = False
    skip_visible = False
    try:
        if driver.find_element(AppiumBy.XPATH, XPATH_SUBMIT).is_displayed():
            submit_visible = True
    except Exception:
        pass
    try:
        if driver.find_element(AppiumBy.XPATH, XPATH_SKIP).is_displayed():
            skip_visible = True
    except Exception:
        pass
    assert submit_visible or skip_visible, "用户名页应显示 Submit 或 Skip"

    try:
        WebDriverWait(driver, 4).until(
            EC.presence_of_element_located((AppiumBy.XPATH, XPATH_PERSONAL_INFO))
        )
        print("    ✅ 已识别 Personal Information 标题")
    except Exception:
        print("    ℹ️ 未找到 Personal Information 标题，以 Submit/Skip 为准")

    username_val = ""
    for el in driver.find_elements(AppiumBy.XPATH, XPATH_USERNAME_FIELD):
        if not el.is_displayed():
            continue
        username_val = (el.text or el.get_attribute("text") or "").strip()
        if username_val:
            break
    assert username_val in _USERNAME_PLACEHOLDERS, (
        f"用户名输入框应为空或占位 Username，当前: {username_val!r}"
    )
    print(f"    📝 用户名框内容: {username_val!r}（未输入）")


def _click_back_button(driver, timeout_s: int = 12) -> None:
    """点击左上角返回（content-desc=back）。"""
    print(f"    🔄 定位返回: {XPATH_BACK}")
    back = WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_BACK))
    )
    try:
        back.click()
    except Exception:
        r = back.rect
        driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])  # type: ignore[attr-defined]
    time.sleep(1.5)
    print("    ✅ 已点击返回按钮")


def _assert_on_main_page_with_more(driver, timeout_s: int = 18) -> None:
    """点击返回后应进入 APP 主页面，More 可见。"""
    last_err: Exception | None = None
    for xp in (XPATH_MORE, XPATH_MORE_ALT):
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            assert el.is_displayed(), f"More 存在但不可见: {xp}"
            print(f"    ✅ 主页面 More 可见: {xp}")
            return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未跳转到主页面（More 不可见）: {last_err}")


def _make_driver():
    appium_url = os.environ.get("APPIUM_URL", os.environ.get("APPIUM_SERVER_URL", "http://localhost:4730"))
    options = UiAutomator2Options()
    options.platform_name = os.environ.get("ANDROID_PLATFORM_NAME", "Android")
    options.platform_version = os.environ.get("ANDROID_PLATFORM_VERSION", "15")
    options.device_name = os.environ.get("ANDROID_DEVICE_NAME", "Android Device")
    options.automation_name = "UiAutomator2"
    options.app_package = os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
    app_activity = os.environ.get("ANDROID_APP_ACTIVITY", "").strip()
    if app_activity:
        options.app_activity = app_activity
    options.new_command_timeout = 3600
    options.no_reset = True
    options.full_reset = False
    driver = webdriver.Remote(command_executor=appium_url, options=options)
    driver.implicitly_wait(5)
    return driver


@pytest.fixture(scope="function")
def setup_driver():
    driver = _make_driver()
    try:
        yield driver
    finally:
        driver.quit()


def test_200088(setup_driver):
    """主流程见文件头；每步独立 try 便于定位失败步骤。"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    try:

        current_step = "步骤1: 重启APP"
        print(f"🔄 {current_step}")
        try:
            step_restart_app(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤2: 检测登录状态并确保在登录/注册入口页"
        print(f"🔄 {current_step}")
        try:
            step_ensure_landing(driver, check_and_logout)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤3: 点击 Sign Up 进入注册页"
        print(f"🔄 {current_step}")
        try:
            step_click_sign_up(driver)
            step_assert_on_signup_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        email = get_simple_email()
        pwd = TEST_PASSWORD
        print(f"    📧 邮箱: {email}")

        current_step = "步骤4: 输入邮箱"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 勾选隐私政策"
        print(f"🔄 {current_step}")
        try:
            step_toggle_checkbox(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤6: 点击 Next 进入设置密码页"
        print(f"🔄 {current_step}")
        try:
            step_click_next(driver)
            step_assert_on_password_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤7: 设置密码"
        print(f"🔄 {current_step}")
        try:
            step_type_passwords(driver, pwd)
            dismiss_keyboard(driver)
            print(f"    🔑 密码: {pwd}")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤8: 点击 Next 进入用户名页"
        print(f"🔄 {current_step}")
        try:
            step_click_next(driver)
            time.sleep(1.0)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤9: 验证用户名页且不输入用户名"
        print(f"🔄 {current_step}")
        try:
            _assert_on_username_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤10: 点击返回按钮"
        print(f"🔄 {current_step}")
        try:
            _click_back_button(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤11: 断言跳转主页面（More 可见）"
        print(f"🔄 {current_step}")
        try:
            _assert_on_main_page_with_more(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        print("🎉 测试用例 200088 执行成功！")
        print("✅ 不输入用户名点击返回，已跳转主页面（More 可见）")
    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {e}"
        print(f"\n{'=' * 60}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_200088_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200088",
            case_desc="200088 验证不输入用户名，点击返回按钮",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
