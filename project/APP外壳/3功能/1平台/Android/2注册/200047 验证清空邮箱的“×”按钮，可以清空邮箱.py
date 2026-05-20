"""
200047 验证清空邮箱的×按钮，可以清空邮箱（Android）。

  步骤1～3：重启 → 入口页 → Sign Up
  步骤4：邮箱栏输入邮箱（get_simple_email）
  步骤5：点击邮箱右侧 clear（×）
  步骤6：断言邮箱框内容已清除
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
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

# ---------- 元素定位（Android，集中在文件顶部便于维护）----------
# 步骤1～2：已登录判据（More）与登录/注册入口页
# 已登录：首页底部/侧边 More
XPATH_MORE = '//android.view.View[@content-desc="More"]'
# More 备用定位
XPATH_MORE_ALT = '//*[@content-desc="More"]'
# 未登录：入口页至少可见 Sign In 或 Sign Up
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)

# 步骤2：入口页 Sign In（确认在登录/注册落地页时可选）
# 入口页 Sign In 按钮（优先 TextView）
XPATH_SIGN_IN = '//android.widget.TextView[@text="Sign In"]'
# Sign In 宽松匹配
XPATH_SIGN_IN_FALLBACK = '//*[@text="Sign In"]'

# 步骤3：入口页 Sign Up（进入注册流程）
# Compose 注册按钮（部分机型）
XPATH_SIGN_UP_COMPOSE = (
    "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/"
    "android.view.View/android.view.View[2]/android.widget.Button"
)
# 入口页 Sign Up 按钮（优先 TextView）
XPATH_SIGN_UP = '//android.widget.TextView[@text="Sign Up"]'
# Sign Up 宽松匹配
XPATH_SIGN_UP_FALLBACK = '//*[@text="Sign Up"]'

# 注册主页面：邮箱输入（与登录 Sign In 页相同 ScrollView 结构）
# 注册页邮箱输入框 ScrollView 内第 1 个 EditText
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
# 点击聚焦邮箱（部分机型需点内层 View）
XPATH_EMAIL_FOCUS = "//android.widget.ScrollView/android.widget.EditText[1]/android.view.View[2]"
# 无 ScrollView 时的邮箱框 fallback
XPATH_EMAIL_FALLBACK = "//android.widget.EditText"
# 输入邮箱后：EditText 的 @text 为实际邮箱（fhjkkf 仅为示例，运行时替换为 get_simple_email()）
# //android.widget.EditText[@text="<email>"]/android.view.View
# //android.widget.EditText[@text="<email>"]

# 设置密码页：密码 / 确认密码（通常为页面内第 1、2 个 EditText）
XPATH_PASSWORD = "//android.widget.EditText"
# 点击聚焦密码（部分机型需点内层 View）
XPATH_PASSWORD_FOCUS = "//android.widget.EditText/android.view.View[1]"

# 注册页：隐私政策勾选框
XPATH_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
# 注册页提交 Next（Button；非登录页 ImageView next）
XPATH_NEXT = "//android.widget.Button"
# 登录页提交 next（注册用例一般不用，保留与登录脚本命名对齐）
XPATH_NEXT_LOGIN = '//android.widget.ImageView[@content-desc="next"]'

# 邮箱右侧清空 ×（注册页邮箱栏右侧）
XPATH_CLEAR_EMAIL = '//android.widget.ImageView[@content-desc="clear"]'
# 密码右侧清空 ×（设置密码页）
XPATH_CLEAR_PASSWORD = '(//android.widget.ImageView[@content-desc="clear"])[2]'
# 密码明文/密文切换（content-desc=lock）
XPATH_PASSWORD_EYE = '//android.widget.ImageView[@content-desc="lock"]'

# 国家/地区选择
XPATH_COUNTRY_ARROW = '//android.view.View[@content-desc="arrow_down"]'
# 国家列表搜索框
XPATH_COUNTRY_SEARCH = "//android.widget.EditText"

# 内页返回（国家列表取消、用户名页等）
XPATH_BACK = '//android.widget.ImageView[@content-desc="back"]'

# 邮箱格式错误提示（注册页）
XPATH_INVALID_EMAIL_HINT = '//android.widget.TextView[@text="Please sign up using your email address"]'
MSG_INVALID_EMAIL = "Please sign up using your email address"

# Sign Up 免责声明整句（Privacy Policy / User Agreement 为 ClickableSpan，无独立节点）
DISCLAIMER_TEXT = "I have read and understood the Privacy Policy and agree to the User Agreement."
PRIVACY_LINK_PHRASE = "Privacy Policy"
USER_AGREEMENT_LINK_PHRASE = "User Agreement"

# 用户名页 Submit
XPATH_SUBMIT = '//*[@text="Submit"]'
# 用户名页 Skip
XPATH_SKIP = '//*[@text="Skip"]'

_EMAIL_PLACEHOLDERS = ("", "Email", "email")


def _xpath_email_focus_by_text(email: str) -> str:
    """输入后邮箱框内层 View（@text 为实际邮箱）。"""
    return f'//android.widget.EditText[@text="{email}"]/android.view.View'


def _xpath_email_edit_by_text(email: str) -> str:
    """输入后邮箱 EditText（@text 为实际邮箱）。"""
    return f'//android.widget.EditText[@text="{email}"]'


def _read_email_field_text(driver) -> str:
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            if el.is_displayed():
                return (el.text or el.get_attribute("text") or "").strip()
        except Exception:
            continue
    return ""


def _assert_email_cleared(driver, email: str) -> None:
    """清空后：不应再存在 @text=邮箱 的 EditText，且主邮箱框为空或占位 Email。"""
    try:
        stale = driver.find_element(AppiumBy.XPATH, _xpath_email_edit_by_text(email))
        if stale.is_displayed():
            shown = (stale.text or stale.get_attribute("text") or "").strip()
            assert shown in _EMAIL_PLACEHOLDERS, f"清空后仍显示邮箱内容: {shown!r}"
    except Exception:
        pass
    val = _read_email_field_text(driver)
    assert val in _EMAIL_PLACEHOLDERS, f"清空后邮箱应为空或占位 Email，当前: {val!r}"


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


def test_200047(setup_driver):
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

        email = get_simple_email()
        print(f"    📧 生成邮箱: {email}")

        current_step = "步骤4: 在邮箱栏输入邮箱"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            xp_email = _xpath_email_edit_by_text(email)
            print(f"    🔄 断言已输入: {xp_email}")
            email_el = WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp_email))
            )
            assert email_el.is_displayed(), "邮箱输入后未找到对应 EditText"
            shown = (email_el.text or email_el.get_attribute("text") or "").strip()
            assert email in shown or shown == email, f"邮箱框内容与输入不一致: {shown!r} vs {email!r}"
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 点击邮箱右侧 clear（×）"
        print(f"🔄 {current_step}")
        try:
            xp_focus = _xpath_email_focus_by_text(email)
            print(f"    🔄 可选聚焦: {xp_focus}")
            try:
                driver.find_element(AppiumBy.XPATH, xp_focus).click()
                time.sleep(0.3)
            except Exception:
                pass
            print(f"    🔄 定位清空: {XPATH_CLEAR_EMAIL}")
            clear_btn = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_CLEAR_EMAIL))
            )
            clear_btn.click()
            time.sleep(0.6)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤6: 断言邮箱框内容已清除"
        print(f"🔄 {current_step}")
        try:
            _assert_email_cleared(driver, email)
            val = _read_email_field_text(driver)
            print(f"    📝 清除后邮箱框: {val!r}")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        print("🎉 测试用例 200047 执行成功！")
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
        save_failure_screenshot(driver, "test_200047_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200047",
            case_desc='200047 验证清空邮箱的×按钮，可以清空邮箱',
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
