"""
200095 验证错误邮箱-未注册的邮箱，不能找回密码（Android）。

步骤（与流程图一致）：
  1. 重启 APP
  2. 检测是否已登录；已登录则 check_and_logout；未登录则确认在登录/注册入口页
  3. 点击 Sign In 进入登录页
  4. 点击 Forgot password 进入忘记密码页
  5. 点击邮箱输入框，输入未注册邮箱（流程图：gjjjjk@163.com）
  6. 收起键盘，点击 Next，断言页面提示：
     This email is not registered. Please check and re-enter.
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
_shared = None
for _ in range(24):
    _cand = _cur / "common"
    if _cand.is_dir() and (_cand / "common_utils_Android共用.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 Beatbot APP/common（需包含 common_utils_Android共用.py）")

from common_utils_Android共用 import (  # noqa: E402
    check_and_logout,
    save_failure_screenshot,
    init_report,
    bind_logger_to_print,
    write_report,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

# 流程图指定未注册邮箱（可用环境变量覆盖）
UNREGISTERED_EMAIL = os.environ.get("FORGOT_UNREGISTERED_EMAIL", "gjjjjk@163.com")
EXPECTED_ERROR = "This email is not registered. Please check and re-enter."

# ---------- 元素定位（Android，与流程图一致）----------
XPATH_MORE = '//android.view.View[@content-desc="More"]'
XPATH_MORE_ALT = '//*[@content-desc="More"]'
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)

# 步骤3：Sign In
XPATH_SIGN_IN = '//android.widget.TextView[@text="Sign In"]'
XPATH_SIGN_IN_FALLBACK = '//*[@text="Sign In"]'

# 步骤4：Forgot password
XPATH_FORGOT_PASSWORD = '//android.widget.TextView[@text="Forgot password"]'
XPATH_FORGOT_PASSWORD_FALLBACK = '//*[contains(@text,"Forgot password")]'

# 步骤5：邮箱输入（与 200093 同口径）
XPATH_EMAIL_LABEL = '//android.widget.TextView[@text="Email"]'
XPATH_EMAIL_FOCUS = "//android.widget.EditText/android.view.View[1]"
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
XPATH_EMAIL_FALLBACK = "//android.widget.EditText"

# 步骤6：Next
XPATH_NEXT = "//android.widget.Button"

# 错误提示
XPATH_ERR_NOT_REGISTERED = (
    f'//android.widget.TextView[@text="{EXPECTED_ERROR}"]'
)
XPATH_ERR_NOT_REGISTERED_FALLBACK = (
    '//*[contains(@text,"This email is not registered") and contains(@text,"re-enter")]'
)


def _restart_app(driver) -> None:
    """步骤1：终止并重新拉起 App，模拟冷启动后的首屏。"""
    pkg = os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
    print(f"    🔄 重启 APP: {pkg}")
    try:
        driver.terminate_app(pkg)
    except Exception:
        pass
    time.sleep(1.5)
    driver.activate_app(pkg)
    time.sleep(3.0)
    print("    ✅ APP 已重启")


def _ensure_landing_page(driver) -> None:
    """
    步骤2：检测登录态并回到登录/注册入口页。

    - 若可见 More，视为已登录，调用 check_and_logout 登出
    - 等待入口页出现 Sign In 或 Sign Up
    """
    is_logged_in = False
    driver.implicitly_wait(0)
    try:
        for xp in (XPATH_MORE, XPATH_MORE_ALT):
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    is_logged_in = True
                    break
            if is_logged_in:
                break
    finally:
        driver.implicitly_wait(5)

    if is_logged_in:
        print("    🔄 已登录，执行登出（logout_Android登出 / check_and_logout）")
        check_and_logout(driver)
        time.sleep(2.0)
    else:
        print("    ℹ️ 未检测到 More，判定未登录")

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY))
    )
    print("    ✅ 已处于登录/注册入口页")


def _click_element(driver, xpaths: tuple[str, ...], timeout_s: int = 15) -> str:
    """
    按 XPath 列表依次查找可点击元素并点击；click 失败时用坐标 tap 兜底。

    Returns:
        实际点击成功的 XPath 字符串。
    """
    last_err: Exception | None = None
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            try:
                el.click()
            except Exception:
                r = el.rect
                driver.tap(  # type: ignore[attr-defined]
                    [(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))]
                )
            print(f"    ✅ 已点击: {xp}")
            return xp
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到可点击元素: {xpaths}，最后错误: {last_err}")


def _dismiss_keyboard(driver) -> None:
    """收起软键盘，避免遮挡 Next / 错误提示。"""
    try:
        driver.hide_keyboard()
        time.sleep(0.4)
        return
    except Exception:
        pass
    try:
        size = driver.get_window_size()
        driver.tap([(int(size["width"] * 0.5), int(size["height"] * 0.12))])  # type: ignore[attr-defined]
        time.sleep(0.4)
    except Exception:
        pass


def _focus_and_type_email(driver, email: str) -> None:
    """
    步骤5：聚焦邮箱输入区并输入邮箱。

    按流程图优先点击 Email 占位 TextView 或 EditText 内层 View，
    再向 EditText 写入邮箱。
    """
    for xp in (XPATH_EMAIL_LABEL, XPATH_EMAIL_FOCUS, XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            el = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                el.click()
                print(f"    ✅ 已聚焦邮箱区: {xp}")
                break
        except Exception:
            continue

    edit = None
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            edit = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if edit.is_displayed():
                break
        except Exception:
            edit = None
    if edit is None:
        raise TimeoutException("未找到邮箱 EditText")

    try:
        edit.clear()
    except Exception:
        pass
    edit.send_keys(email)
    time.sleep(0.6)
    _dismiss_keyboard(driver)


def _assert_not_registered_error(driver, timeout_s: int = 12) -> None:
    """步骤6：断言提示“邮箱未注册”的错误文案出现。"""
    el = None
    for xp in (XPATH_ERR_NOT_REGISTERED, XPATH_ERR_NOT_REGISTERED_FALLBACK):
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                print(f"    ✅ 未注册邮箱错误提示: {xp}")
                return
        except Exception:
            el = None
    raise TimeoutException("未找到未注册邮箱错误提示")


def _make_driver():
    """创建 Appium UiAutomator2 驱动；包名、设备、Appium URL 可通过环境变量覆盖。"""
    appium_url = os.environ.get(
        "APPIUM_URL", os.environ.get("APPIUM_SERVER_URL", "http://localhost:4730")
    )
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
    """用例级 fixture：每个测试函数独立创建 WebDriver，结束后 quit。"""
    driver = _make_driver()
    try:
        yield driver
    finally:
        driver.quit()


def test_200095(setup_driver):
    """
    200095 主流程（与流程图一致）。

    步骤1 重启 → 步骤2 登出/入口页 → 步骤3 Sign In → 步骤4 Forgot password
    → 步骤5 输入未注册邮箱 → 步骤6 Next 并断言错误提示。
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        current_step = "步骤1: 重启APP"
        print(f"🔄 {current_step}")
        try:
            _restart_app(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤2: 检测登录状态并确保在登录/注册入口页"
        print(f"🔄 {current_step}")
        try:
            _ensure_landing_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤3: 点击 Sign In 进入登录页"
        print(f"🔄 {current_step}")
        try:
            _click_element(driver, (XPATH_SIGN_IN, XPATH_SIGN_IN_FALLBACK), timeout_s=18)
            time.sleep(1.5)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤4: 点击 Forgot password 进入忘记密码页"
        print(f"🔄 {current_step}")
        try:
            _click_element(
                driver,
                (XPATH_FORGOT_PASSWORD, XPATH_FORGOT_PASSWORD_FALLBACK),
                timeout_s=15,
            )
            time.sleep(1.5)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = f"步骤5: 输入未注册邮箱 {UNREGISTERED_EMAIL}"
        print(f"🔄 {current_step}")
        try:
            _focus_and_type_email(driver, UNREGISTERED_EMAIL)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤6: 点击 Next 并断言未注册邮箱提示"
        print(f"🔄 {current_step}")
        try:
            _click_element(driver, (XPATH_NEXT,), timeout_s=12)
            time.sleep(1.5)
            _assert_not_registered_error(driver, timeout_s=12)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        print("🎉 测试用例 200095 执行成功！")
        print("✅ 未注册邮箱点击 Next 提示邮箱未注册")

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
        save_failure_screenshot(driver, "test_200095_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200095",
            case_desc="200095 验证错误邮箱-未注册的邮箱，不能找回密码",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])

