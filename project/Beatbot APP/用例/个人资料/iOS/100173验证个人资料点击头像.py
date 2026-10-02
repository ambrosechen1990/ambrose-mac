# -*- coding: utf-8 -*-
"""
100174 验证头像页面返回（iOS / 8个人资料）

参考流程（截图）：
  1. 重启 APP
  2. 检查是否已登录；未登录则登录
  3. 点击 mine → 设置页
  4. 点击 CommonEdit → 账号与安全页
  5. 点击头像进入头像页，断言存在 Change Avatar
  6. 点击返回，断言回到个人资料页（不再显示 Change Avatar）
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
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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

from common_utils_iOS共用 import (  # noqa: E402
    bind_logger_to_print,
    init_report,
    save_failure_screenshot,
    write_report,
)
from ios_sign_in_helpers_登录辅助 import resolve_sign_in_email_input, resolve_sign_in_password_input

RUN_LABEL = os.environ.get("RUN_LABEL", "ios")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

LOGIN_EMAIL = os.environ.get("IOS_LOGIN_EMAIL", "haoc51888@gmail.com")
LOGIN_PASSWORD = os.environ.get("IOS_LOGIN_PASSWORD", "Csx150128")
BUNDLE_ID = os.environ.get("IOS_BUNDLE_ID", "com.xingmai.tech")

CASE_ID = "100174"
CASE_DESC = "100174 验证头像页面返回"

LOGIN_INDICATORS = [
    '//XCUIElementTypeButton[@name="home sel"]',
    '//XCUIElementTypeButton[@name="mine sel"]',
    '//XCUIElementTypeButton[@name="mine"]',
]

CHANGE_AVATAR_XPATH = '//XCUIElementTypeButton[@name="Change Avatar"]'
CHANGE_AVATAR_TEXT_XPATH = '//XCUIElementTypeStaticText[@name="Change Avatar"]'


def _wait_clickable(driver, xpath: str, timeout: float = 10):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, xpath))
    )


def _is_logged_in(driver) -> bool:
    for xp in LOGIN_INDICATORS:
        try:
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return True
        except Exception:
            continue
    return False


def _restart_app(driver) -> None:
    caps = getattr(driver, "capabilities", {}) or {}
    bundle_id = caps.get("bundleId") or BUNDLE_ID
    driver.terminate_app(bundle_id)
    time.sleep(1.5)
    driver.activate_app(bundle_id)
    time.sleep(2)


def _wait_for_bottom_mine_after_login(driver, timeout_s: float) -> None:
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
    raise AssertionError(f"{timeout_s}s 内未检测到底部 mine")


def _perform_ios_login(driver) -> None:
    _wait_clickable(driver, '//XCUIElementTypeButton[@name="Sign In"]', timeout=12).click()
    time.sleep(1.5)

    email_input = resolve_sign_in_email_input(driver)
    email_input.clear()
    email_input.send_keys(LOGIN_EMAIL)
    time.sleep(0.6)

    pwd_input = resolve_sign_in_password_input(driver)
    pwd_input.clear()
    pwd_input.send_keys(LOGIN_PASSWORD)
    time.sleep(0.6)

    try:
        WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
        ).click()
        time.sleep(0.5)
    except Exception:
        pass

    _wait_clickable(driver, '//XCUIElementTypeButton[@name="login check normal"]', timeout=8).click()
    time.sleep(0.6)

    WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'name == "login icon"'))
    ).click()
    time.sleep(float(os.environ.get("LOGIN_POST_CLICK_WAIT_S", "4")))

    _wait_for_bottom_mine_after_login(
        driver, timeout_s=float(os.environ.get("LOGIN_SUCCESS_TIMEOUT_S", "45"))
    )


def _click_mine_tab(driver) -> None:
    for xp in (
        '//XCUIElementTypeButton[@name="mine"]',
        '//XCUIElementTypeButton[@name="mine sel"]',
    ):
        try:
            _wait_clickable(driver, xp, timeout=10).click()
            time.sleep(1.2)
            return
        except Exception:
            continue
    raise TimeoutException("未找到 mine 按钮")


def _click_common_edit(driver) -> None:
    _wait_clickable(driver, '//XCUIElementTypeButton[@name="CommonEdit"]', timeout=12).click()
    time.sleep(1.5)


def _click_personal_profile_entry(driver) -> None:
    candidates = [
        '//XCUIElementTypeStaticText[@name="Personal Information"]',
        '//XCUIElementTypeButton[@name="Personal Information"]',
        '//XCUIElementTypeStaticText[contains(@name,"Personal")]',
        '//XCUIElementTypeStaticText[@name="个人资料"]',
        '//XCUIElementTypeButton[@name="个人资料"]',
        '//XCUIElementTypeStaticText[contains(@name,"资料")]',
        '//XCUIElementTypeStaticText[@name="Profile"]',
        '//XCUIElementTypeButton[@name="Profile"]',
    ]
    last_err = None
    for xp in candidates:
        try:
            el = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                try:
                    el.click()
                except Exception:
                    rect = el.rect or {}
                    driver.execute_script(
                        "mobile: tap",
                        {
                            "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                            "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
                        },
                    )
                time.sleep(1.5)
                return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到个人资料入口: {last_err}")


def _click_avatar_to_enter_avatar_page(driver) -> None:
    """
    截图提示 locator：//XCUIElementTypeScrollView/XCUIElementTypeOther/XCUIElementTypeImage[1]
    这里做可兼容的 class chain / xpath 兜底。
    """
    candidates = [
        (AppiumBy.XPATH, "//XCUIElementTypeScrollView/XCUIElementTypeOther/XCUIElementTypeImage[1]"),
        (AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeScrollView/**/XCUIElementTypeImage[1]"),
        (AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeImage[1]"),
    ]
    last_err = None
    for by, sel in candidates:
        try:
            el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((by, sel)))
            if not el.is_displayed():
                continue
            try:
                el.click()
            except Exception:
                rect = el.rect or {}
                driver.execute_script(
                    "mobile: tap",
                    {
                        "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                        "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
                    },
                )
            time.sleep(1.2)
            return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到头像 Image[1]: {last_err}")


def _assert_on_avatar_page(driver) -> None:
    selectors = [CHANGE_AVATAR_XPATH, CHANGE_AVATAR_TEXT_XPATH]
    last_err = None
    for xp in selectors:
        try:
            el = WebDriverWait(driver, 12).until(EC.presence_of_element_located((AppiumBy.XPATH, xp)))
            if el.is_displayed():
                print(f"    ✅ 已进入头像页，命中: {xp}")
                return
        except Exception as e:
            last_err = e
    raise AssertionError(f"未进入头像页（Change Avatar 不可见）：{last_err}")


def _tap_nav_back(driver) -> None:
    """
    iOS 返回：优先找导航栏 Back/返回；失败则点左上角坐标。
    """
    candidates = [
        '//XCUIElementTypeButton[@name="Back"]',
        '//XCUIElementTypeButton[@label="Back"]',
        '//XCUIElementTypeButton[@name="返回"]',
        '//XCUIElementTypeButton[@label="返回"]',
        '//XCUIElementTypeButton[@name="个人资料"]',
        '//XCUIElementTypeButton[contains(@name,"Personal")]',
    ]
    for xp in candidates:
        try:
            el = WebDriverWait(driver, 4).until(EC.presence_of_element_located((AppiumBy.XPATH, xp)))
            if el.is_displayed() and el.is_enabled():
                el.click()
                time.sleep(1.0)
                return
        except Exception:
            continue

    size = driver.get_window_size()
    x = int(size["width"] * float(os.environ.get("IOS_BACK_TAP_X_RATIO", "0.06")))
    y = int(size["height"] * float(os.environ.get("IOS_BACK_TAP_Y_RATIO", "0.07")))
    driver.execute_script("mobile: tap", {"x": x, "y": y})
    time.sleep(1.0)


def _assert_left_avatar_page(driver) -> None:
    """
    返回后不应再显示 Change Avatar；且应能看到个人资料页入口元素（如头像 Image 或 Personal Info 文案）。
    """
    # 1) Change Avatar 不存在或不可见
    for xp in (CHANGE_AVATAR_XPATH, CHANGE_AVATAR_TEXT_XPATH):
        try:
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    raise AssertionError("返回后仍停留在头像页（Change Avatar 仍可见）")
        except AssertionError:
            raise
        except Exception:
            continue

    # 2) 个人资料页特征：存在 ScrollView 或头像 Image[1]
    WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, "//XCUIElementTypeScrollView"))
    )


@pytest.fixture(scope="function")
def setup_driver():
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


def test_100174(setup_driver):
    """100174 验证头像页面返回"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        current_step = "步骤1: 重启 APP"
        print(f"🔄 {current_step}")
        _restart_app(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤2: 检查登录状态，未登录则登录"
        print(f"🔄 {current_step}")
        if _is_logged_in(driver):
            print("    ℹ️ 已登录")
        else:
            _perform_ios_login(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤3: 点击 mine 进入设置页"
        print(f"🔄 {current_step}")
        _click_mine_tab(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 点击 CommonEdit 进入账号与安全页"
        print(f"🔄 {current_step}")
        _click_common_edit(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤5: 进入个人资料页并点击头像进入头像页"
        print(f"🔄 {current_step}")
        _click_personal_profile_entry(driver)
        _click_avatar_to_enter_avatar_page(driver)
        _assert_on_avatar_page(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 点击返回并断言回到个人资料页"
        print(f"🔄 {current_step}")
        _tap_nav_back(driver)
        _assert_left_avatar_page(driver)
        print(f"✅ {current_step} - 完成")

        print(f"🎉 测试用例 {CASE_ID} 执行成功！")

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
