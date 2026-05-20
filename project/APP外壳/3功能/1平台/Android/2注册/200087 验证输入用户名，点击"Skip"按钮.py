"""
200087 验证输入用户名，点击"Skip"按钮（Android）。

  对齐 iOS 102246：
  步骤1～8：重启 → Sign Up → 邮箱 → 隐私 → 密码 → 用户名页
  步骤9：用户名框输入 49 位用户名（ran1）
  步骤10：点击 Skip（//android.widget.TextView[@text="Skip"]）
  步骤11：断言跳转主页面（More 可见）
  步骤12：检查首页用户名显示为默认 Username（非 49 位）
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
from username_utils import ran1  # noqa: E402
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
XPATH_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
XPATH_NEXT = "//android.widget.Button"
XPATH_PASSWORD = "//android.widget.EditText"
XPATH_PASSWORD_EYE = '//android.widget.ImageView[@content-desc="lock"]'

# 主页面 More
XPATH_MORE = '//android.view.View[@content-desc="More"]'
XPATH_MORE_ALT = '//*[@content-desc="More"]'

# 用户名页：聚焦/占位
XPATH_USERNAME_FOCUS = "//android.widget.EditText/android.view.View[1]"
XPATH_USERNAME_PLACEHOLDER = '//android.widget.TextView[@text="Username"]'
XPATH_USERNAME_EDIT = "//android.widget.EditText"

# Skip 按钮（用户指定）
XPATH_SKIP = '//android.widget.TextView[@text="Skip"]'

# 首页用户名展示（默认占位文案）
XPATH_HOME_USERNAME_LABEL = '//android.widget.TextView[@text="Username"]'

TEST_PASSWORD = os.environ.get("REGISTER_PASSWORD", "Csx150128")
USERNAME_LEN = 49


def _assert_on_username_page(driver, timeout_s: int = 15) -> None:
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_SKIP))
    )


def _focus_username_field(driver, timeout_s: int = 10) -> None:
    for xp in (XPATH_USERNAME_FOCUS, XPATH_USERNAME_PLACEHOLDER, XPATH_USERNAME_EDIT):
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            el.click()
            print(f"    ✅ 聚焦用户名框: {xp}")
            return
        except Exception:
            continue
    raise TimeoutException("未找到用户名输入框")


def _type_username_49(driver, username: str, timeout_s: int = 12) -> None:
    _focus_username_field(driver, timeout_s=timeout_s)
    field = None
    for xp in (XPATH_USERNAME_EDIT,):
        try:
            field = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            break
        except Exception:
            continue
    if field is None:
        raise TimeoutException("未找到 EditText 用户名输入框")
    try:
        field.clear()
    except Exception:
        pass
    field.send_keys(username)
    dismiss_keyboard(driver)
    time.sleep(0.8)

    shown = ""
    for el in driver.find_elements(AppiumBy.XPATH, XPATH_USERNAME_EDIT):
        if not el.is_displayed():
            continue
        shown = (el.text or el.get_attribute("text") or "").strip()
        if len(shown) >= len(username) - 2:
            break
    assert len(shown) >= USERNAME_LEN - 2, (
        f"用户名框应已输入约 {USERNAME_LEN} 位，当前长度: {len(shown)}，内容前缀: {shown[:20]!r}"
    )
    print(f"    📝 用户名框已输入，长度: {len(shown)}")


def _click_skip(driver, timeout_s: int = 12) -> None:
    print(f"    🔄 定位 Skip: {XPATH_SKIP}")
    skip_btn = WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_SKIP))
    )
    skip_btn.click()
    time.sleep(2.0)
    print("    ✅ 已点击 Skip")


def _assert_on_main_page_with_more(driver, timeout_s: int = 18) -> None:
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


def _assert_home_shows_default_username_not_49(driver, username_49: str, timeout_s: int = 12) -> None:
    """
    Skip 后首页应显示默认 Username，不应展示刚输入的 49 位用户名。
  优先检查 //android.widget.TextView[@text="Username"]。
    """
    default_visible = False
    try:
        el = WebDriverWait(driver, timeout_s).until(
            EC.presence_of_element_located((AppiumBy.XPATH, XPATH_HOME_USERNAME_LABEL))
        )
        if el.is_displayed():
            default_visible = True
            print(f"    ✅ 首页存在默认 Username 文案: {XPATH_HOME_USERNAME_LABEL}")
    except Exception:
        pass

    shows_49 = False
    shown_samples: list[str] = []
    for el in driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView"):
        try:
            if not el.is_displayed():
                continue
            text = (el.text or el.get_attribute("text") or "").strip()
            if not text:
                continue
            if username_49 in text or text == username_49:
                shows_49 = True
                shown_samples.append(text[:60])
            if text == "Username" or text.endswith(", Username") or "Hi, Username" in text:
                default_visible = True
        except Exception:
            continue

    if shows_49:
        raise AssertionError(
            f"Skip 后首页仍显示 49 位用户名，样例: {shown_samples[:3]}"
        )

    assert default_visible, (
        "Skip 后首页应显示默认 Username（//android.widget.TextView[@text=\"Username\"]），"
        f"且不应出现 49 位用户名"
    )
    print("    ✅ 首页为用户名默认展示（Username），未保留 49 位输入")


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


def test_200087(setup_driver):
    """主流程见文件头；每步独立 try 便于定位失败步骤。"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    username_49 = ""
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
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤8: 点击 Next 进入用户名页"
        print(f"🔄 {current_step}")
        try:
            step_click_next(driver)
            time.sleep(1.0)
            _assert_on_username_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        username_49 = (os.environ.get("USERNAME_49", "") or ran1(USERNAME_LEN))[:USERNAME_LEN]
        assert len(username_49) == USERNAME_LEN, f"用户名应为 {USERNAME_LEN} 位，当前: {len(username_49)}"

        current_step = "步骤9: 输入 49 位用户名"
        print(f"🔄 {current_step}")
        try:
            _type_username_49(driver, username_49)
            print(f"    👤 用户名(49位): {username_49[:12]}...{username_49[-4:]}")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = '步骤10: 点击 Skip'
        print(f"🔄 {current_step}")
        try:
            _click_skip(driver)
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

        current_step = "步骤12: 检查首页用户名为默认 Username（非 49 位）"
        print(f"🔄 {current_step}")
        try:
            _assert_home_shows_default_username_not_49(driver, username_49)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        print("🎉 测试用例 200087 执行成功！")
        print('✅ 输入 49 位用户名后点击 Skip，已跳转主页面且显示默认 Username')
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
        save_failure_screenshot(driver, "test_200087_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200087",
            case_desc='200087 验证输入用户名，点击"Skip"按钮',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
