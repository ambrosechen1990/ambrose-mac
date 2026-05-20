"""
200062 验证一个地区注册过的的邮箱，不可以在另一个地区继续注册（Android）。

  对齐 iOS 102221：
  步骤1～3：重启 → 入口页 → Sign Up
  步骤4：国家切换至 France
  步骤5：输入已在美国注册过的邮箱 haoc51888@gmail.com
  步骤6：勾选隐私政策
  步骤7：点击 Next
  步骤8：断言弹出「账号已注册」提示（未进入密码页）
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

from register_case_base import (  # noqa: E402
    step_restart_app,
    step_ensure_landing,
    step_click_sign_up,
    step_assert_on_signup_page,
    dismiss_keyboard,
    step_select_country_from_search,
    step_type_email,
    step_toggle_checkbox,
    step_click_next,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

# ---------- 元素定位（Android，集中在文件顶部便于维护）----------
XPATH_MORE = '//android.view.View[@content-desc="More"]'
XPATH_MORE_ALT = '//*[@content-desc="More"]'
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)
XPATH_SIGN_IN = '//android.widget.TextView[@text="Sign In"]'
XPATH_SIGN_IN_FALLBACK = '//*[@text="Sign In"]'
XPATH_SIGN_UP_COMPOSE = (
    "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/"
    "android.view.View/android.view.View[2]/android.widget.Button"
)
XPATH_SIGN_UP = '//android.widget.TextView[@text="Sign Up"]'
XPATH_SIGN_UP_FALLBACK = '//*[@text="Sign Up"]'
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
XPATH_EMAIL_FOCUS = "//android.widget.ScrollView/android.widget.EditText[1]/android.view.View[2]"
XPATH_EMAIL_FALLBACK = "//android.widget.EditText"
XPATH_PASSWORD = "//android.widget.EditText"
XPATH_PASSWORD_FOCUS = "//android.widget.EditText/android.view.View[1]"
XPATH_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
XPATH_NEXT = "//android.widget.Button"
XPATH_NEXT_LOGIN = '//android.widget.ImageView[@content-desc="next"]'
XPATH_CLEAR_EMAIL = '(//android.widget.ImageView[@content-desc="clear"])[1]'
XPATH_CLEAR_PASSWORD = '(//android.widget.ImageView[@content-desc="clear"])[2]'
XPATH_PASSWORD_EYE = '//android.widget.ImageView[@content-desc="lock"]'
XPATH_COUNTRY_ARROW = '//android.view.View[@content-desc="arrow_down"]'
XPATH_COUNTRY_SEARCH = "//android.widget.EditText"
XPATH_BACK = '//android.widget.ImageView[@content-desc="back"]'
XPATH_INVALID_EMAIL_HINT = '//android.widget.TextView[@text="Please sign up using your email address"]'
MSG_INVALID_EMAIL = "Please sign up using your email address"
DISCLAIMER_TEXT = "I have read and understood the Privacy Policy and agree to the User Agreement."
PRIVACY_LINK_PHRASE = "Privacy Policy"
USER_AGREEMENT_LINK_PHRASE = "User Agreement"
XPATH_SUBMIT = '//*[@text="Submit"]'
XPATH_SKIP = '//*[@text="Skip"]'

# 已在美国注册过的邮箱（固定账号，勿用 get_simple_email）
REGISTERED_EMAIL = os.environ.get("REGISTERED_EMAIL", "haoc51888@gmail.com")
# 切换至另一地区（对齐 iOS 102221：France）
COUNTRY_SEARCH_KEYWORD = os.environ.get("REGISTER_COUNTRY_SEARCH", "france")
COUNTRY_TARGET_TEXTS = ("France", "法国", "france")

MSG_ALREADY_REGISTERED = "This email is already registered. Ready to sign in now?"
XPATH_ALERT_ALREADY_REGISTERED = (
    f'//android.widget.TextView[@text="{MSG_ALREADY_REGISTERED}"]'
)
XPATH_ALERT_ALREADY_REGISTERED_FALLBACK = (
    '//android.widget.TextView[contains(@text,"already registered")]'
)
XPATH_ALERT_CONFIRM = '//*[@text="Confirm"]'
XPATH_ALERT_CANCEL = '//*[@text="Cancel"]'


def _assert_already_registered_alert(driver, timeout_s: int = 15) -> None:
    """断言已注册提示弹框；不应进入设置密码页。"""
    alert = None
    last_err: Exception | None = None
    for xp in (XPATH_ALERT_ALREADY_REGISTERED, XPATH_ALERT_ALREADY_REGISTERED_FALLBACK):
        try:
            alert = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if alert.is_displayed():
                break
        except Exception as e:
            last_err = e
            alert = None
    if alert is None or not alert.is_displayed():
        raise TimeoutException(f"未出现已注册提示弹框: {last_err}")

    confirm = WebDriverWait(driver, 6).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_ALERT_CONFIRM))
    )
    cancel = WebDriverWait(driver, 6).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_ALERT_CANCEL))
    )
    assert confirm.is_displayed(), "弹框中未显示 Confirm 按钮"
    assert cancel.is_displayed(), "弹框中未显示 Cancel 按钮"
    shown = (alert.text or alert.get_attribute("text") or "").strip()
    print(f"    ✅ 弹框提示: {shown or MSG_ALREADY_REGISTERED}")

    pwd_fields = driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD)
    lock_icons = driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD_EYE)
    if len(pwd_fields) >= 2 or lock_icons:
        raise AssertionError("出现已注册弹框时不应进入设置密码页")


def _make_driver():
    """创建 Appium UiAutomator2 驱动；可通过环境变量覆盖包名、设备、Appium URL。"""
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
    """用例级 fixture：执行结束关闭 driver。"""
    driver = _make_driver()
    try:
        yield driver
    finally:
        driver.quit()


def test_200062(setup_driver):
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
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤2: 检测登录状态并确保在登录/注册入口页"
        print(f"🔄 {current_step}")
        try:
            step_ensure_landing(driver, check_and_logout)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤3: 点击 Sign Up 进入注册页"
        print(f"🔄 {current_step}")
        try:
            step_click_sign_up(driver)
            step_assert_on_signup_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤4: 国家切换至 France"
        print(f"🔄 {current_step}")
        try:
            clicked = step_select_country_from_search(
                driver,
                search_keyword=COUNTRY_SEARCH_KEYWORD,
                target_texts=COUNTRY_TARGET_TEXTS,
            )
            print(f"    ✅ 已选国家: {clicked}")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        email = REGISTERED_EMAIL
        print(f"    📧 已注册邮箱（美国）: {email}")

        current_step = "步骤5: 输入已注册邮箱"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤6: 勾选隐私政策"
        print(f"🔄 {current_step}")
        try:
            step_toggle_checkbox(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤7: 点击 Next"
        print(f"🔄 {current_step}")
        try:
            step_click_next(driver)
            time.sleep(1.0)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤8: 断言弹出已注册提示（未继续下一步）"
        print(f"🔄 {current_step}")
        try:
            _assert_already_registered_alert(driver, timeout_s=15)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        print("🎉 测试用例 200062 执行成功！")
        print("✅ 已注册邮箱在 France 再次注册，弹出已注册提示（未继续下一步）")
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
        save_failure_screenshot(driver, "test_200062_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200062",
            case_desc="200062 验证一个地区注册过的的邮箱，不可以在另一个地区继续注册",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
