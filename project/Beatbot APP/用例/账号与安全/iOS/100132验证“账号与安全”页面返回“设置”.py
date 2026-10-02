# -*- coding: utf-8 -*-
"""
100132 验证「账号与安全」页面返回「设置」（iOS / 4显示）

流程：
  1. 重启 APP
  2. 检查是否已登录；未登录则调用登录流程
  3. 点击 mine → 设置页
  4. 点击 CommonEdit → 账号与安全页
  5. 点击左上角返回（nav back / 导航栏返回）→ 断言回到设置页（General 可见）
"""
import os
import sys
import time
import traceback
from pathlib import Path

import pytest
from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# 共用逻辑在「common」
_cur = Path(__file__).resolve().parent
_shared = None
for _ in range(24):
    _cand = _cur / "common"
    if _cand.is_dir() and (_cand / "common_utils_iOS共用.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 Beatbot APP/common（需包含 common_utils_iOS共用.py）")

from common_utils_iOS共用 import (
    bind_logger_to_print,
    init_report,
    save_failure_screenshot,
    write_report,
)
from ios_sign_in_helpers_登录辅助 import resolve_sign_in_email_input, resolve_sign_in_password_input

RUN_LABEL = os.environ.get("RUN_LABEL", "ios")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

# ---------- 登录账号（未登录时使用，可通过环境变量覆盖） ----------
LOGIN_EMAIL = os.environ.get("IOS_LOGIN_EMAIL", "haoc51888@gmail.com")
LOGIN_PASSWORD = os.environ.get("IOS_LOGIN_PASSWORD", "Csx150128")
BUNDLE_ID = os.environ.get("IOS_BUNDLE_ID", "com.xingmai.tech")

# ---------- 已登录态判据 ----------
LOGIN_INDICATORS = [
    '//XCUIElementTypeButton[@name="home sel"]',
    '//XCUIElementTypeButton[@name="mine sel"]',
    '//XCUIElementTypeButton[@name="mine"]',
]

# ---------- 步骤 5：返回键与设置页判据 ----------
# 注意：DynamicBackground 为全屏背景图，不是左上角返回键，不可用于点击返回。
ACCOUNT_SECURITY_TITLE = "Account and Security"
SETTINGS_PAGE_INDICATOR = "General"

# 返回键候选（按优先级）：与注册/忘记密码等页一致使用 nav back
BACK_BUTTON_SELECTORS = [
    (AppiumBy.ACCESSIBILITY_ID, "nav back"),
    (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="nav back"]'),
    (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"nav back")]'),
    (AppiumBy.XPATH, '//XCUIElementTypeNavigationBar//XCUIElementTypeButton[1]'),
    (
        AppiumBy.IOS_PREDICATE,
        'type == "XCUIElementTypeButton" AND (name == "nav back" OR name CONTAINS "back" OR name CONTAINS "Back")',
    ),
]

CASE_ID = "100132"
CASE_DESC = '100132 验证「账号与安全」页面返回「设置」'


def _wait_clickable(driver, xpath: str, timeout: float = 10):
    """等待元素可点击并返回。"""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, xpath))
    )


def _wait_visible_static_text(driver, name: str, timeout: float = 12):
    """等待 StaticText 出现且可见。"""
    xpath = f'//XCUIElementTypeStaticText[@name="{name}"]'
    el = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((AppiumBy.XPATH, xpath))
    )
    assert el.is_displayed(), f"元素存在但不可见: {name}"
    return el


def _click_with_tap_fallback(driver, selectors, timeout_each: int = 8):
    """按候选定位点击；失败时对元素中心坐标 mobile:tap。"""
    elem = None
    used = None
    for by, sel in selectors:
        try:
            cand = WebDriverWait(driver, timeout_each).until(
                EC.presence_of_element_located((by, sel))
            )
            if cand and cand.is_displayed():
                elem = cand
                used = f"{by} / {sel}"
                break
        except Exception:
            continue
    if elem is None:
        raise TimeoutError("未找到可点击的返回按钮")
    try:
        elem.click()
    except Exception:
        rect = elem.rect or {}
        tap_x = int(rect.get("x", 0) + rect.get("width", 0) / 2)
        tap_y = int(rect.get("y", 0) + rect.get("height", 0) / 2)
        driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
    print(f"    ✅ 返回键点击成功: {used}")


def _tap_screen_top_left(driver) -> None:
    """
    兜底：点击屏幕左上角（返回箭头区域）。
    DynamicBackground 覆盖全屏时，nav back 偶发不可点时可用。
    """
    size = driver.get_window_size()
    rx = float(os.environ.get("IOS_BACK_TAP_X_RATIO", "0.08"))
    ry = float(os.environ.get("IOS_BACK_TAP_Y_RATIO", "0.10"))
    tap_x = int(size["width"] * rx)
    tap_y = int(size["height"] * ry)
    driver.execute_script("mobile: tap", {"x": tap_x, "y": tap_y})
    print(f"    ✅ 已坐标点击左上角返回区域: ({tap_x}, {tap_y})")


def _is_logged_in(driver) -> bool:
    """任意底部 Tab 选中态或 mine 可见即视为已登录。"""
    for indicator in LOGIN_INDICATORS:
        try:
            for elem in driver.find_elements(AppiumBy.XPATH, indicator):
                if elem.is_displayed():
                    print(f"    ✅ 检测到已登录: {indicator}")
                    return True
        except Exception:
            continue
    return False


def _restart_app(driver) -> None:
    """步骤1：重启 APP。"""
    caps = getattr(driver, "capabilities", {}) or {}
    bundle_id = caps.get("bundleId") or BUNDLE_ID
    driver.terminate_app(bundle_id)
    time.sleep(1.5)
    driver.activate_app(bundle_id)
    time.sleep(2)
    print("    ✅ APP 已重启")


def _wait_for_bottom_mine_after_login(driver, timeout_s: float) -> None:
    """登录成功后等待底部 Mine Tab。"""
    candidates = [
        '//XCUIElementTypeButton[@name="mine"]',
        '//XCUIElementTypeButton[@name="mine sel"]',
        '//XCUIElementTypeButton[contains(@name,"mine")]',
    ]
    deadline = time.monotonic() + timeout_s
    poll = float(os.environ.get("LOGIN_SUCCESS_POLL_S", "1.0"))
    while time.monotonic() < deadline:
        for xp in candidates:
            try:
                for el in driver.find_elements(AppiumBy.XPATH, xp):
                    if el.is_displayed():
                        return
            except Exception:
                continue
        time.sleep(poll)
    raise AssertionError(f"{timeout_s}s 内未检测到底部 Mine Tab")


def _perform_ios_login(driver) -> None:
    """
    步骤2（未登录分支）：Sign In 登录（对齐 100015 / 100129）。
    """
    sign_in_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="Sign In"]', timeout=12)
    sign_in_btn.click()
    time.sleep(1.5)

    email_input = resolve_sign_in_email_input(driver)
    email_input.clear()
    email_input.send_keys(LOGIN_EMAIL)
    time.sleep(0.8)

    password_input = resolve_sign_in_password_input(driver)
    password_input.clear()
    password_input.send_keys(LOGIN_PASSWORD)
    time.sleep(0.8)

    try:
        done_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
        )
        done_btn.click()
        time.sleep(0.8)
    except Exception:
        pass

    check_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="login check normal"]', timeout=8)
    check_btn.click()
    time.sleep(0.8)

    login_btn = WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'name == "login icon"'))
    )
    login_btn.click()
    time.sleep(float(os.environ.get("LOGIN_POST_CLICK_WAIT_S", "4")))

    _wait_for_bottom_mine_after_login(
        driver, timeout_s=float(os.environ.get("LOGIN_SUCCESS_TIMEOUT_S", "45"))
    )
    print("    ✅ 登录成功")


def _click_mine_tab(driver) -> None:
    """步骤3：点击 mine 进入设置页。"""
    for xp, desc in [
        ('//XCUIElementTypeButton[@name="mine"]', "mine"),
        ('//XCUIElementTypeButton[@name="mine sel"]', "mine sel"),
    ]:
        try:
            btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            btn.click()
            print(f"    ✅ 已点击 {desc}，进入设置页")
            time.sleep(1.5)
            return
        except Exception:
            continue
    raise AssertionError("未找到 mine / mine sel 按钮")


def _click_common_edit(driver) -> None:
    """步骤4：点击 CommonEdit 进入账号与安全页。"""
    edit_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="CommonEdit"]', timeout=12)
    edit_btn.click()
    time.sleep(1.5)
    print("    ✅ 已点击 CommonEdit，进入账号与安全页")


def _click_back_from_account_security(driver) -> None:
    """
    步骤5：点击左上角返回。

    Inspector 说明：
    - DynamicBackground 为整页背景 XCUIElementTypeImage，尺寸接近全屏，不是返回键。
    - 返回键通常在 NavigationBar 内，本 App 多为 accessibility id / name = nav back。
    """
    _wait_visible_static_text(driver, ACCOUNT_SECURITY_TITLE, timeout=12)
    print(f"    ℹ️ 当前在账号与安全页: {ACCOUNT_SECURITY_TITLE}")

    try:
        _click_with_tap_fallback(driver, BACK_BUTTON_SELECTORS, timeout_each=10)
    except Exception as e:
        print(f"    ⚠️ nav back 等定位未命中，尝试左上角坐标: {e}")
        _tap_screen_top_left(driver)

    time.sleep(1.5)


def _assert_back_to_settings_page(driver) -> None:
    """
    步骤5 断言：回到设置页。
    判据：//XCUIElementTypeStaticText[@name="General"] 可见。
    """
    _wait_visible_static_text(driver, SETTINGS_PAGE_INDICATOR)
    print(f"    ✅ 已回到设置页，可见: {SETTINGS_PAGE_INDICATOR}")


@pytest.fixture(scope="function")
def setup_driver():
    """iOS Appium 驱动配置。"""
    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.platform_version = os.environ.get("IOS_PLATFORM_VERSION", "18.5")
    options.device_name = os.environ.get("IOS_DEVICE_NAME", "iPhone 16 pro max")
    options.automation_name = "XCUITest"
    options.udid = os.environ.get("IOS_UDID", "00008140-00041C980A50801C")
    options.bundle_id = BUNDLE_ID
    options.include_safari_in_webviews = True
    options.new_command_timeout = 3600
    options.connect_hardware_keyboard = True

    driver = webdriver.Remote(
        command_executor=os.environ.get("APPIUM_SERVER_URL", "http://localhost:4736"),
        options=options,
    )
    driver.implicitly_wait(5)
    yield driver
    if driver:
        driver.quit()


def test_100132(setup_driver):
    """
    100132 验证「账号与安全」页面返回「设置」

    1. 重启 APP
    2. 检查登录；未登录则登录
    3. 点击 mine → 设置页
    4. 点击 CommonEdit → 账号与安全页
    5. 点击 nav back 返回 → 断言 General 显示（设置页）
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        # ---------- 步骤1：重启 APP ----------
        current_step = "步骤1: 重启 APP"
        print(f"🔄 {current_step}")
        _restart_app(driver)
        print(f"✅ {current_step} - 完成")

        # ---------- 步骤2：检查登录；未登录则登录 ----------
        current_step = "步骤2: 检查登录状态，未登录则登录"
        print(f"🔄 {current_step}")
        if _is_logged_in(driver):
            print("    ℹ️ 已登录，进入步骤3")
        else:
            print("    🔄 未登录，执行登录流程…")
            _perform_ios_login(driver)
        print(f"✅ {current_step} - 完成")

        # ---------- 步骤3：mine → 设置页 ----------
        current_step = "步骤3: 点击 mine 进入设置页"
        print(f"🔄 {current_step}")
        _click_mine_tab(driver)
        print(f"✅ {current_step} - 完成")

        # ---------- 步骤4：CommonEdit → 账号与安全页 ----------
        current_step = "步骤4: 点击 CommonEdit 进入账号与安全页"
        print(f"🔄 {current_step}")
        _click_common_edit(driver)
        print(f"✅ {current_step} - 完成")

        # ---------- 步骤5：返回并断言设置页 ----------
        current_step = "步骤5: 点击返回并断言回到设置页"
        print(f"🔄 {current_step}")
        _click_back_from_account_security(driver)
        _assert_back_to_settings_page(driver)
        print(f"✅ {current_step} - 完成")

        print(f"🎉 测试用例{CASE_ID}执行成功！")

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {e}"
        print(f"\n{'=' * 60}")
        print(f"❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, f"test_{CASE_ID}_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id=CASE_ID,
            case_desc=CASE_DESC,
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
