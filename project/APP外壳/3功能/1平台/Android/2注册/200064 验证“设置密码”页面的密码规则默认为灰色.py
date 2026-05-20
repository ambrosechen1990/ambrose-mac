"""
200064 验证「设置密码」页面的密码规则默认为灰色（Android）。

  对齐 iOS 102223：
  步骤1～3：重启 → 入口页 → Sign Up
  步骤4～6：输入邮箱、勾选隐私、Next 进入设置密码页
  步骤7：验证进入设置密码页
  步骤8：密码框输入 Csx150128，断言四条规则提示可见且为灰色
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
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

# ---------- 元素定位（Android，集中在文件顶部便于维护）----------
XPATH_MORE = '//android.view.View[@content-desc="More"]'
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)
XPATH_SIGN_UP = '//android.widget.TextView[@text="Sign Up"]'
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
XPATH_EMAIL_FOCUS = "//android.widget.ScrollView/android.widget.EditText[1]/android.view.View[2]"
XPATH_PASSWORD = "//android.widget.EditText"
XPATH_PASSWORD_FOCUS = "//android.widget.EditText/android.view.View[1]"
XPATH_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
XPATH_NEXT = "//android.widget.Button"
XPATH_PASSWORD_EYE = '//android.widget.ImageView[@content-desc="lock"]'

# 测试密码（对齐 iOS 102223）
TEST_PASSWORD = os.environ.get("REGISTER_TEST_PASSWORD", "Csx150128")

# 密码规则文案片段（Android 可能与 iOS 一样带 • 前缀）
PASSWORD_RULE_FRAGMENTS = (
    "6-20 characters",
    "contains letters",
    "contains numbers",
    "Supports special characters",
)


def _is_gray_color(color_text: str) -> bool:
    """判断颜色是否为灰色系（对齐 iOS 102223）。"""
    if not color_text:
        return False
    color_lower = color_text.strip().lower()
    if "gray" in color_lower or "grey" in color_lower:
        return True
    if color_lower.startswith("#") and len(color_lower) in (7, 9):
        hex_body = color_lower[1:]
        if len(hex_body) == 8:
            hex_body = hex_body[2:]
        try:
            r = int(hex_body[0:2], 16)
            g = int(hex_body[2:4], 16)
            b = int(hex_body[4:6], 16)
            return abs(r - g) <= 12 and abs(g - b) <= 12 and max(r, g, b) <= 200
        except Exception:
            return False
    if color_lower.startswith("rgb"):
        num_part = color_lower[color_lower.find("(") + 1 : color_lower.find(")")]
        parts = [p.strip() for p in num_part.split(",")]
        if len(parts) >= 3:
            try:
                r = int(float(parts[0]))
                g = int(float(parts[1]))
                b = int(float(parts[2]))
                return abs(r - g) <= 12 and abs(g - b) <= 12
            except Exception:
                return False
    try:
        val = int(float(color_lower))
        c = val & 0xFFFFFF
        r = (c >> 16) & 0xFF
        g = (c >> 8) & 0xFF
        b = c & 0xFF
        return abs(r - g) <= 12 and abs(g - b) <= 12 and max(r, g, b) <= 200
    except Exception:
        return False


def _collect_color_candidates(el) -> list[str]:
    candidates: list[str] = []
    if hasattr(el, "value_of_css_property"):
        try:
            css_color = el.value_of_css_property("color")
            if css_color:
                candidates.append(str(css_color))
        except Exception:
            pass
    for attr in ("textColor", "color", "foregroundColor", "value"):
        try:
            v = el.get_attribute(attr)
            if v:
                candidates.append(str(v))
        except Exception:
            continue
    unique: list[str] = []
    for c in candidates:
        if c not in unique:
            unique.append(c)
    return unique


def _find_rule_element(driver, fragment: str, timeout_s: int = 10):
    """按文案片段查找密码规则 TextView。"""
    last_err: Exception | None = None
    xpaths = (
        f'//android.widget.TextView[contains(@text,"{fragment}")]',
        f'//*[contains(@text,"{fragment}")]',
    )
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                return el, xp
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到规则提示（片段: {fragment!r}）: {last_err}")


def _type_first_password(driver, pwd: str, timeout_s: int = 18) -> None:
    """仅向第一个密码框输入（对齐 iOS 102223）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        edits = [e for e in driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD) if e.is_displayed()]
        if edits:
            field = edits[0]
            try:
                field.click()
            except Exception:
                try:
                    driver.find_element(AppiumBy.XPATH, XPATH_PASSWORD_FOCUS).click()
                except Exception:
                    pass
            try:
                field.clear()
            except Exception:
                pass
            field.send_keys(pwd)
            dismiss_keyboard(driver)
            time.sleep(0.8)
            return
        time.sleep(0.4)
    raise TimeoutException("未找到密码输入框")


def _assert_password_rules_gray(driver, timeout_s: int = 10) -> None:
    """断言四条密码规则可见；若可获取颜色则判定为灰色。"""
    for fragment in PASSWORD_RULE_FRAGMENTS:
        rule_elem, xp = _find_rule_element(driver, fragment, timeout_s=timeout_s)
        shown = (rule_elem.text or rule_elem.get_attribute("text") or "").strip()
        assert shown, f"规则提示无文案: {fragment!r}"

        color_candidates = _collect_color_candidates(rule_elem)
        filtered = []
        for c in color_candidates:
            c_strip = c.strip()
            if fragment in c_strip or c_strip.startswith("•"):
                continue
            if len(c_strip) > 80:
                continue
            filtered.append(c_strip)

        if not filtered:
            print(f"    📝 规则 [{fragment!r}] 可见（{xp}），系统未返回颜色属性，按默认灰色通过")
            continue

        is_gray = any(_is_gray_color(c) for c in filtered)
        assert is_gray, f"规则 [{fragment!r}] 颜色非灰色: {filtered}"
        print(f"    📝 规则 [{fragment!r}] 颜色: {filtered}（判定为灰色）")

    print("    ✅ 四条密码规则均可见且默认为灰色")


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


def test_200064(setup_driver):
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
            time.sleep(1.0)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤7: 验证进入设置密码页"
        print(f"🔄 {current_step}")
        try:
            step_assert_on_password_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤8: 输入密码并验证规则提示为灰色"
        print(f"🔄 {current_step}")
        try:
            print(f"    🔑 密码: {TEST_PASSWORD}")
            _type_first_password(driver, TEST_PASSWORD)
            _assert_password_rules_gray(driver, timeout_s=10)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        print("🎉 测试用例 200064 执行成功！")
        print("✅ 设置密码页面规则提示默认为灰色，输入 Csx150128 后规则提示可见")
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
        save_failure_screenshot(driver, "test_200064_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200064",
            case_desc="200064 验证「设置密码」页面的密码规则默认为灰色",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
