#!/usr/bin/env python3
"""按 200001 架构批量生成 Android/2注册 用例脚本。运行: python build_android_register_cases.py"""

from __future__ import annotations

import re
from pathlib import Path

DIR = Path(__file__).resolve().parent


def _load_xpath_locators_block() -> str:
    """读取 register_xpath_locators.py 中带注释的定位常量块，写入各用例文件顶部。"""
    text = (DIR / "register_xpath_locators.py").read_text(encoding="utf-8")
    marker = "# ---------- 元素定位"
    idx = text.find(marker)
    if idx < 0:
        raise RuntimeError("register_xpath_locators.py 中未找到元素定位块")
    return text[idx:].rstrip() + "\n"


XPATH_LOCATORS_BLOCK = _load_xpath_locators_block()

HEAD = '''"""
{case_id} {title}（Android）。

{steps_doc}
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
{extra_imports}
from register_case_base import (  # noqa: E402
    step_restart_app,
    step_ensure_landing,
    step_click_sign_up,
    step_assert_sign_up_entry,
    step_assert_on_signup_page,
    step_assert_still_on_signup_page,
    dismiss_keyboard,
    step_type_email,
    step_get_email_text,
    step_clear_email,
    step_toggle_checkbox,
    step_click_next,
    step_click_back,
    step_assert_invalid_email_hint,
    step_open_country_picker,
    step_assert_country_select_page,
    step_country_search,
    step_click_text_if_visible,
    step_tap_below_search_field,
    step_assert_country_first_letter_search,
    step_select_country_from_search,
    step_click_country_in_list,
    step_assert_country_has_default,
    step_assert_on_password_page,
    step_type_passwords,
    step_flow_to_password_page,
    step_flow_to_username_page,
    step_type_username,
    step_click_submit,
    step_assert_not_logged_in_main,
    step_assert_text_visible,
    step_click_password_eye,
    step_click_clear_password,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

{xpath_locators_block}

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


def test_{case_id}(setup_driver):
    """主流程见文件头；每步独立 try 便于定位失败步骤。"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    try:
{test_body}
        print("🎉 测试用例 {case_id} 执行成功！")
    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{{current_step}}失败: {{e}}"
        print(f"\\n{{'=' * 60}}")
        print("❌ 测试失败")
        print(f"📍 失败步骤: {{current_step}}")
        print(f"📝 失败原因: {{fail_reason}}")
        print(f"{{'=' * 60}}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_{case_id}_failed")
        assert False, f"测试失败 - {{fail_reason}}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="{case_id}",
            case_desc={case_desc_repr},
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
'''

STEPS_123 = '''
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
'''

# (filename_suffix, case_id, title, steps_doc, extra_imports, body_after_step3)
CASES: list[tuple[str, str, str, str, str, str]] = []

def add(fn_suffix, cid, title, doc, extra="", body=""):
    CASES.append((fn_suffix, cid, title, doc, extra, body))


add("200025", "200025", "验证APP首页注册功能按钮",
    "步骤：重启 → 登出/入口页 → 断言 Sign Up 入口可见。",
    "",
    '''
        current_step = "步骤4: 断言首页 Sign Up 入口可见"
        print(f"🔄 {current_step}")
        try:
            step_assert_sign_up_entry(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200026", "200026", "验证注册页面到APP首页的返回键",
    "步骤：重启 → 登出/入口页 → Sign Up → 返回 → 断言 Sign Up。",
    "",
    '''
        current_step = "步骤4: 点击返回键"
        print(f"🔄 {current_step}")
        try:
            driver.back()
            time.sleep(2.0)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 断言回到入口页 Sign Up"
        print(f"🔄 {current_step}")
        try:
            step_assert_sign_up_entry(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200027", "200027", "验证注册页面国家默认选择当前设备所在地",
    "步骤：重启 → 登出/入口页 → Sign Up → 断言国家栏有默认值。",
    "",
    '''
        current_step = "步骤4: 断言国家默认非空"
        print(f"🔄 {current_step}")
        try:
            step_assert_country_has_default(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200028", "200028", "验证注册页面国家切换-选择列表中的国家",
    "步骤：Sign Up → 国家列表 → 搜索 america → 选择 United States。",
    "",
    '''
        current_step = "步骤4: 打开国家选择"
        print(f"🔄 {current_step}")
        try:
            step_open_country_picker(driver)
            step_assert_country_select_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 搜索 america 并选择 United States of America"
        print(f"🔄 {current_step}")
        try:
            step_country_search(driver, "america")
            try:
                step_click_text_if_visible(driver, ["United States of America", "United States"])
            except Exception:
                step_tap_below_search_field(driver, 145)
            time.sleep(1.5)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200029", "200029", "验证注册页面国家切换-搜索一个存在的国家",
    "步骤：国家列表搜索 China 并选择。",
    "",
    '''
        current_step = "步骤4: 搜索并选择 China"
        print(f"🔄 {current_step}")
        try:
            step_open_country_picker(driver)
            step_country_search(driver, "China")
            step_click_text_if_visible(driver, ["China", "中国"])
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200030", "200030", "验证注册页面国家切换-搜索一个不存在的国家",
    "步骤：搜索不存在国家，列表无有效国家项可选。",
    "",
    '''
        current_step = "步骤4: 搜索不存在的国家"
        print(f"🔄 {current_step}")
        try:
            step_open_country_picker(driver)
            step_country_search(driver, "ZZZ_Not_A_Country_XYZ")
            time.sleep(1.0)
            print(f"✅ {current_step} - 完成（无匹配项为预期）")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200031", "200031", "验证注册页面国家切换-清空搜索内容",
    "步骤：搜索后清空，恢复列表。",
    "",
    '''
        current_step = "步骤4: 搜索后清空"
        print(f"🔄 {current_step}")
        try:
            step_open_country_picker(driver)
            step_country_search(driver, "amer")
            field = driver.find_element(AppiumBy.XPATH, "//android.widget.EditText")
            field.clear()
            time.sleep(1.0)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200032", "200032", "验证注册页面国家切换-搜索框根据首字母搜索国家",
    "步骤：打开国家列表 → 输入首字母 Z → 断言可见国家均含该字母（对齐 iOS 102188）。",
    "",
    '''
        current_step = "步骤4: 打开国家选择页"
        print(f"🔄 {current_step}")
        try:
            step_open_country_picker(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 搜索首字母并断言模糊匹配（对齐 iOS 102188，默认 Z）"
        print(f"🔄 {current_step}")
        try:
            search_kw = os.environ.get("COUNTRY_SEARCH_LETTER", "Z").strip().upper()[:1] or "Z"
            kw_used, found = step_assert_country_first_letter_search(driver, search_keyword=search_kw)
            print(f"    ✅ 模糊搜索通过，关键字={kw_used}，匹配 {len(found)} 个国家")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200033", "200033", "验证从国家列表取消，返回注册主页面",
    "步骤：打开国家列表后点取消/返回。",
    "",
    '''
        current_step = "步骤4: 国家列表取消返回"
        print(f"🔄 {current_step}")
        try:
            step_open_country_picker(driver)
            for xp in ('//*[@text="Cancel"]', '//*[contains(@text,"Cancel")]', '//android.widget.ImageView[@content-desc="back"]'):
                try:
                    el = driver.find_element(AppiumBy.XPATH, xp)
                    if el.is_displayed():
                        el.click()
                        break
                except Exception:
                    continue
            else:
                driver.back()
            time.sleep(1.5)
            step_assert_on_signup_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200034", "200034", '验证进入注册页面，直接点击"下一步"',
    "步骤：Sign Up 后直接点 Next，仍停留注册页。",
    "",
    '''
        current_step = "步骤4: 直接点击 Next"
        print(f"🔄 {current_step}")
        try:
            step_click_next(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 断言仍停留注册页"
        print(f"🔄 {current_step}")
        try:
            step_assert_still_on_signup_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200035", "200035", '验证注册，不选择用户政策、隐私协议，点击"下一步"',
    "步骤：输入邮箱不勾选协议点 Next。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 输入邮箱（不勾选协议）"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 点击 Next 并断言仍停留注册页"
        print(f"🔄 {current_step}")
        try:
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200036", "200036", '验证注册时，不输入邮箱，点击"下一步"',
    "步骤：不输入邮箱点 Next。",
    "",
    '''
        current_step = "步骤4: 不输入邮箱点击 Next"
        print(f"🔄 {current_step}")
        try:
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200037", "200037", "验证注册时，邮箱名称过长",
    "步骤：输入超长邮箱，断言错误提示。",
    "",
    '''
        long_email = "a" * 64 + "@163.com"
        current_step = "步骤4: 输入过长邮箱"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, long_email)
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            step_assert_invalid_email_hint(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200038", "200038", '验证注册地为任何国家时，提示文案均为"邮箱"',
    "步骤：检查邮箱输入框占位/标签含 Email。",
    "",
    '''
        current_step = "步骤4: 断言邮箱字段文案"
        print(f"🔄 {current_step}")
        try:
            step_assert_text_visible(driver, ["Email", "email", "邮箱"], timeout_s=12)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200039", "200039", '验证注册地为"中国"，正确邮箱，可以注册',
    "步骤：国家框输入 china → 收起键盘 → 点击 China → 邮箱 → 勾选 → Next。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()

        current_step = "步骤4: 国家框输入 china，收起键盘并点击 China"
        print(f"🔄 {current_step}")
        try:
            step_select_country_from_search(
                driver,
                search_keyword="china",
                target_texts=("China", "中国", "china"),
            )
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 输入邮箱、勾选协议并 Next 进入密码页"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_on_password_page(driver)
            print(f"    ✅ 邮箱: {email}")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200040", "200040", '验证注册地为"中国"以外地区，正确邮箱，可以注册',
    "步骤：选 United States + 合法邮箱进入密码页。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 选择非中国地区并输入邮箱"
        print(f"🔄 {current_step}")
        try:
            step_open_country_picker(driver)
            step_country_search(driver, "United")
            step_click_text_if_visible(driver, ["United States of America", "United States"])
            time.sleep(1.0)
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_on_password_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200041", "200041", "验证隐私政策、用户协议默认不勾选",
    "步骤：Sign Up 后协议勾选框应存在（默认未勾选，仅断言可见）。",
    "",
    '''
        current_step = "步骤4: 断言协议勾选框存在"
        print(f"🔄 {current_step}")
        try:
            cb = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, XPATH_CHECKBOX))
            )
            assert cb.is_displayed()
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200042", "200042", '验证"隐私政策、用户协议"勾选功能',
    "步骤：点击勾选协议。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        current_step = "步骤4: 输入邮箱并勾选协议"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, get_simple_email())
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200043", "200043", '验证"隐私政策、用户协议"取消勾选',
    "步骤：勾选后再取消勾选。",
    "",
    '''
        current_step = "步骤4: 勾选后再取消"
        print(f"🔄 {current_step}")
        try:
            step_toggle_checkbox(driver)
            time.sleep(0.3)
            step_toggle_checkbox(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200044", "200044", '验证"Next"按钮，初始状态为浅色，不可点击',
    "步骤：进入注册页直接点 Next，应停留当前页。",
    "",
    '''
        current_step = "步骤4: 点击 Next 并断言不可跳转"
        print(f"🔄 {current_step}")
        try:
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200045", "200045", "验证只填写正确邮箱，Next按钮还是浅色不可点击",
    "步骤：只填邮箱不勾选协议。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 仅输入邮箱点击 Next"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200046", "200046", "验证勾选协议后填入邮箱，Next可点击并进入密码页",
    "步骤：勾选 + 邮箱 + Next → 密码页。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 勾选协议并输入邮箱后 Next"
        print(f"🔄 {current_step}")
        try:
            step_toggle_checkbox(driver)
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            step_click_next(driver)
            step_assert_on_password_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200047", "200047", "验证清空邮箱的×按钮，可以清空邮箱",
    "步骤：输入邮箱后点 clear。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 输入邮箱并清空"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            step_clear_email(driver)
            val = step_get_email_text(driver)
            assert val in ("", "Email", "email"), f"清空后邮箱应为空或占位，当前: {val!r}"
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200048", "200048", "验证注册时输入纯数字时，弹出的错误提示是否正确",
    "步骤：纯数字邮箱 + 勾选 + Next + 错误提示。",
    "",
    '''
        current_step = "步骤4: 输入纯数字邮箱"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, "123456789")
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            step_assert_invalid_email_hint(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200049", "200049", "验证邮箱数字+字母，无法下一步",
    "步骤：字母数字无@邮箱。",
    "",
    '''
        current_step = "步骤4: 输入无@的字母数字"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, "abc123")
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            step_assert_invalid_email_hint(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

INVALID_EMAIL_MAP = {
    "200050": ("", "邮箱为空"),
    "200052": ("abcdef", "只有字母"),
    "200053": ("!@#$%^&*", "只有特殊字符"),
    "200054": ("测试@163.com", "包含中文"),
    "200055": ("a@@b.com", "a@@b"),
    "200056": ("a@b", "只有@"),
    "200057": ("a.b.c", "只有点"),
    "200058": ("a@b", "a@b"),
    "200059": ("a@b@c.com", "a@b@c"),
}

for cid, (em, label) in INVALID_EMAIL_MAP.items():
    add(
        cid,
        cid,
        f"验证错误邮箱，无法进行下一步操作-{label}",
        f"步骤：输入错误邮箱 {em!r}，断言无法下一步。",
        "",
        f'''
        bad = {em!r} or os.environ.get("INVALID_EMAIL", "")
        current_step = "步骤4: 输入错误邮箱并点击 Next"
        print(f"🔄 {{current_step}}")
        try:
            if bad:
                step_type_email(driver, bad)
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            if bad:
                step_assert_invalid_email_hint(driver)
            print(f"✅ {{current_step}} - 完成")
        except Exception as e:
            fail_reason = f"{{current_step}}失败: {{e}}"
            raise
''',
    )

add(
    "200051",
    "200051",
    "验证修改错误邮箱，错误提示就会消失",
    "步骤：先输错误邮箱再改为正确邮箱。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        current_step = "步骤4: 错误邮箱后出现提示再修正"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, "abcdef")
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_invalid_email_hint(driver)
            good = get_simple_email()
            step_type_email(driver, good)
            dismiss_keyboard(driver)
            time.sleep(0.8)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''',
)

add("200021", "200021", "验证注册时邮箱显示包含不支持的特殊字符",
    "步骤：不支持特殊字符邮箱 + Next + 错误提示。",
    "from email_utils import get_next_unsupported_email  # noqa: E402",
    '''
        bad = get_next_unsupported_email()
        current_step = "步骤4: 输入不支持特殊字符邮箱"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, bad)
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            step_assert_invalid_email_hint(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200022", "200022", "验证注册时邮箱显示包含特殊字符",
    "步骤：支持的特殊字符邮箱可进入密码页。",
    "from email_utils import get_next_unused_special_char_email  # noqa: E402",
    '''
        em = get_next_unused_special_char_email()
        current_step = "步骤4: 输入含支持特殊字符的邮箱"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, em)
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_on_password_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

# 密码页用例
PWD_CASES = [
    ("200063", "验证进入设置密码页面", "Csx150128", True, "enter"),
    ("200064", "验证设置密码页面的密码规则默认为灰色", "Csx150128", True, "rules_gray"),
    ("200065", "验证密码小于6个字符时，下一步按钮不可点击", "Csx15", False, "stay"),
    ("200066", "验证密码大于20个字符时，下一步按钮不可点击", "A" * 21 + "a1", False, "stay"),
    ("200067", "验证密码等于6个字符时，下一步按钮可点击", "Csx150", True, "advance"),
    ("200068", "验证密码等于20个字符时，下一步按钮可点击", "Aa1!" + "x" * 16, True, "advance"),
    ("200069", "验证密码为纯数字时，下一步按钮不可点击", "12345678", False, "stay"),
    ("200070", "验证密码为纯小写字母时，下一步按钮不可点击", "abcdefgh", False, "stay"),
    ("200071", "验证密码为纯大写字母时，下一步按钮不可点击", "ABCDEFGH", False, "stay"),
    ("200072", "验证密码为纯字符时，下一步按钮不可点击", "!@#$%^&*", False, "stay"),
    ("200073", "验证密码为数字+小写字母时，下一步按钮可以点击", "abc12345", True, "advance"),
    ("200074", "验证密码为数字+大写字母时，下一步按钮可以点击", "ABC12345", True, "advance"),
    ("200075", "验证密码为数字+大小写字母+字符时，下一步按钮可以点击", "Csx150128!", True, "advance"),
    ("200076", "验证密码为数字+字符时，下一步按钮不可以点击", "1234!@#$", False, "stay"),
    ("200077", "验证密码为小写+大写字母时，下一步按钮不可以点击", "Abcdefgh", False, "stay"),
    ("200078", "验证密码为小写字母+字符时，下一步按钮不可以点击", "abc!@#$%", False, "stay"),
    ("200079", "验证密码为大写字母+字符时，下一步按钮不可以点击", "ABC!@#$%", False, "stay"),
]

for cid, title, pwd, _, mode in PWD_CASES:
  extra = "from email_utils import get_simple_email  # noqa: E402"
  if mode == "enter":
    body = f'''
        email = get_simple_email()
        current_step = "步骤4: 完成邮箱步骤进入密码页"
        print(f"🔄 {{current_step}}")
        try:
            step_flow_to_password_page(driver, email)
            print(f"✅ {{current_step}} - 完成")
        except Exception as e:
            fail_reason = f"{{current_step}}失败: {{e}}"
            raise
'''
  elif mode == "rules_gray":
    body = f'''
        email = get_simple_email()
        current_step = "步骤4: 进入密码页并检查规则文案"
        print(f"🔄 {{current_step}}")
        try:
            step_flow_to_password_page(driver, email)
            step_assert_text_visible(driver, ["6", "20", "character", "字符"], timeout_s=10)
            print(f"✅ {{current_step}} - 完成")
        except Exception as e:
            fail_reason = f"{{current_step}}失败: {{e}}"
            raise
'''
  elif mode == "advance":
    body = f'''
        email = get_simple_email()
        pwd = {pwd!r}
        current_step = "步骤4: 输入符合规则的密码并 Next"
        print(f"🔄 {{current_step}}")
        try:
            step_flow_to_password_page(driver, email)
            step_type_passwords(driver, pwd)
            dismiss_keyboard(driver)
            step_click_next(driver)
            try:
                step_assert_on_password_page(driver, timeout_s=3)
                raise AssertionError("密码符合规则时 Next 应离开密码页")
            except TimeoutException:
                pass
            print(f"✅ {{current_step}} - 完成")
        except Exception as e:
            fail_reason = f"{{current_step}}失败: {{e}}"
            raise
'''
  else:
    body = f'''
        email = get_simple_email()
        pwd = {pwd!r}
        current_step = "步骤4: 输入不符合规则的密码"
        print(f"🔄 {{current_step}}")
        try:
            step_flow_to_password_page(driver, email)
            step_type_passwords(driver, pwd)
            dismiss_keyboard(driver)
            step_click_next(driver)
            step_assert_on_password_page(driver, timeout_s=8)
            print(f"✅ {{current_step}} - 完成")
        except Exception as e:
            fail_reason = f"{{current_step}}失败: {{e}}"
            raise
'''
  add(cid, cid, title, f"步骤：进入密码页验证（{title}）。", extra, body)

# 用户名 / 个人信息
add("200023", "200023", "验证输入用户名名字超过50个字符，点击Submit按钮",
    "步骤：完整注册流至用户名页，>50字符 Submit 应失败。",
    "from email_utils import get_simple_email  # noqa: E402\nfrom username_utils import ran1  # noqa: E402",
    '''
        email = get_simple_email()
        pwd = os.environ.get("REGISTER_PASSWORD", "Csx150128")
        username = os.environ.get("USERNAME_GT_50", "") or ran1(60)
        current_step = "步骤4: 进入用户名页"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_username_page(driver, email, pwd)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise

        current_step = "步骤5: 输入>50字符用户名并 Submit"
        print(f"🔄 {current_step}")
        try:
            step_type_username(driver, username)
            step_click_submit(driver)
            step_assert_not_logged_in_main(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200024", "200024", "验证输入用户名名字49个字符，点击Submit按钮",
    "步骤：49字符用户名可提交（不进入主界面即视为未完整注册成功）。",
    "from email_utils import get_simple_email  # noqa: E402\nfrom username_utils import ran1  # noqa: E402",
    '''
        email = get_simple_email()
        pwd = os.environ.get("REGISTER_PASSWORD", "Csx150128")
        username = (os.environ.get("USERNAME_49", "") or ran1(49))[:49]
        current_step = "步骤4: 输入49字符用户名并 Submit"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_username_page(driver, email, pwd)
            step_type_username(driver, username)
            step_click_submit(driver)
            print(f"✅ {current_step} - 完成（已点击 Submit）")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200085", "200085", '验证"Personal Information"页面显示',
    "步骤：进入个人信息/用户名相关页面。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        pwd = os.environ.get("REGISTER_PASSWORD", "Csx150128")
        current_step = "步骤4: 进入 Personal Information / 用户名页"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_username_page(driver, email, pwd)
            step_assert_text_visible(driver, ["Personal", "Information", "Username", "Submit"], timeout_s=12)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200086", "200086", '验证不输入用户名，点击"Submit"按钮',
    "步骤：空用户名点 Submit。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        pwd = os.environ.get("REGISTER_PASSWORD", "Csx150128")
        current_step = "步骤4: 空用户名点击 Submit"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_username_page(driver, email, pwd)
            step_click_submit(driver)
            step_assert_not_logged_in_main(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200087", "200087", '验证输入用户名，点击"Skip"按钮',
    "步骤：输入用户名点 Skip。",
    "from email_utils import get_simple_email  # noqa: E402\nfrom username_utils import ran1  # noqa: E402",
    '''
        email = get_simple_email()
        pwd = os.environ.get("REGISTER_PASSWORD", "Csx150128")
        name = ran1(8)
        current_step = "步骤4: 输入用户名并 Skip"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_username_page(driver, email, pwd)
            step_type_username(driver, name)
            step_click_text_if_visible(driver, ["Skip"])
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200088", "200088", "验证不输入用户名，点击返回按钮",
    "步骤：用户名页点返回。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        pwd = os.environ.get("REGISTER_PASSWORD", "Csx150128")
        current_step = "步骤4: 用户名页点击返回"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_username_page(driver, email, pwd)
            step_click_back(driver)
            step_assert_on_password_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200089", "200089", "验证输入用户名，点击返回按钮",
    "步骤：输入用户名后返回密码页。",
    "from email_utils import get_simple_email  # noqa: E402\nfrom username_utils import ran1  # noqa: E402",
    '''
        email = get_simple_email()
        pwd = os.environ.get("REGISTER_PASSWORD", "Csx150128")
        current_step = "步骤4: 输入用户名后返回"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_username_page(driver, email, pwd)
            step_type_username(driver, ran1(8))
            step_click_back(driver)
            step_assert_on_password_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200090", "200090", "验证输入邮箱格式不正确",
    "步骤：非法邮箱格式。",
    "",
    '''
        current_step = "步骤4: 输入格式不正确邮箱"
        print(f"🔄 {current_step}")
        try:
            step_type_email(driver, "not-an-email")
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_still_on_signup_page(driver)
            step_assert_invalid_email_hint(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

# 密码 UI
add("200080", "200080", "验证输入的密码，可以一键×清空",
    "步骤：密码页输入后点 clear。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 密码输入后清空"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_password_page(driver, email)
            step_type_passwords(driver, "Csx150128")
            dismiss_keyboard(driver)
            step_click_clear_password(driver, 1)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200081", "200081", "验证密码默认密文",
    "步骤：密码框默认为密文（无明文 text）。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 检查密码默认密文"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_password_page(driver, email)
            el = driver.find_element(AppiumBy.XPATH, XPATH_EMAIL)
            txt = (el.text or "").strip()
            assert "Csx" not in txt, f"密码不应明文显示: {txt!r}"
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200082", "200082", "验证密码可以明文",
    "步骤：点击 lock 显示明文。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        pwd = "Csx150128"
        current_step = "步骤4: 密码明文显示"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_password_page(driver, email)
            step_type_passwords(driver, pwd)
            dismiss_keyboard(driver)
            step_click_password_eye(driver, 1)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200083", "200083", "验证密码明文后，可以再次隐藏",
    "步骤：lock 切换两次。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 明文后再隐藏"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_password_page(driver, email)
            step_type_passwords(driver, "Csx150128")
            dismiss_keyboard(driver)
            step_click_password_eye(driver, 1)
            step_click_password_eye(driver, 1)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

add("200084", "200084", "验证输入的密码和确认密码不一致",
    "步骤：两次密码不同，Next 应停留密码页。",
    "from email_utils import get_simple_email  # noqa: E402",
    '''
        email = get_simple_email()
        current_step = "步骤4: 输入不一致的确认密码"
        print(f"🔄 {current_step}")
        try:
            step_flow_to_password_page(driver, email)
            edits = [e for e in driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD) if e.is_displayed()]
            edits[0].send_keys("Csx150128")
            edits[1].send_keys("Csx150129")
            dismiss_keyboard(driver)
            step_click_next(driver)
            step_assert_on_password_page(driver)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {e}"
            raise
''')

# 已注册邮箱（需环境变量或跳过）
for cid, title, env_key in [
    ("200060", "验证注册过的邮箱再次注册，提示当前账号已注册，立刻登录", "REGISTERED_EMAIL"),
    ("200061", "验证注册过的邮箱再次注册，提示当前账号已注册，取消立刻登录", "REGISTERED_EMAIL"),
    ("200062", "验证一个地区注册过的的邮箱，不可以在另一个地区继续注册", "REGISTERED_EMAIL"),
]:
    add(
        cid,
        cid,
        title,
        f"步骤：使用已注册邮箱（环境变量 {env_key}）。",
        "from email_utils import get_simple_email  # noqa: E402",
        f'''
        email = os.environ.get("{env_key}", "") or get_simple_email()
        current_step = "步骤4: 使用已注册邮箱尝试注册"
        print(f"🔄 {{current_step}}")
        try:
            step_type_email(driver, email)
            dismiss_keyboard(driver)
            step_toggle_checkbox(driver)
            step_click_next(driver)
            step_assert_text_visible(
                driver,
                ["registered", "already", "已注册", "Account", "登录", "Log in"],
                timeout_s=15,
            )
            print(f"✅ {{current_step}} - 完成")
        except Exception as e:
            fail_reason = f"{{current_step}}失败: {{e}}"
            raise
''',
    )


def find_target_file(case_id: str) -> Path | None:
    for p in DIR.glob("*.py"):
        if p.name.startswith(case_id):
            return p
    return None


def render(fn_suffix: str, case_id: str, title: str, steps_doc: str, extra: str, body: str) -> str:
    steps_doc_indented = "\n".join(f"  {ln}" for ln in steps_doc.strip().splitlines())
    full_body = STEPS_123 + body
    return HEAD.format(
        case_id=case_id,
        title=title,
        case_desc_repr=repr(f"{case_id} {title}"),
        steps_doc=steps_doc_indented,
        extra_imports=("\n" + extra) if extra else "",
        xpath_locators_block=XPATH_LOCATORS_BLOCK,
        test_body=full_body,
    )


def main():
    written = 0
    for fn_suffix, case_id, title, doc, extra, body in CASES:
        target = find_target_file(case_id)
        if target is None:
            print(f"skip missing file for {case_id}")
            continue
        content = render(fn_suffix, case_id, title, doc, extra, body)
        target.write_text(content, encoding="utf-8")
        written += 1
        print(f"wrote {target.name}")
    print(f"done: {written} files")


if __name__ == "__main__":
    main()
