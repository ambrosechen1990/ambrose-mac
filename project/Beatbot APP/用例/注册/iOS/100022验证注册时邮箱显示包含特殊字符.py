# -*- coding: utf-8 -*-
"""
100022 验证注册时邮箱显示包含特殊字符（iOS / 2注册）

流程：
  1. 登出后进入 Sign Up
  2. 输入特殊字符邮箱（get_next_unused_special_char_email）
  3. 勾选协议 → Done → Next
  4. 断言提示：Please sign up using your email address
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

from email_utils_邮箱工具 import get_next_unused_special_char_email  # noqa: E402
from common_utils_iOS共用 import (  # noqa: E402
    assert_on_signup_page,
    check_and_logout,
    init_report,
    bind_logger_to_print,
    save_failure_screenshot,
    write_report,
)

RUN_LABEL = os.environ.get("RUN_LABEL", "ios")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

PROMPT_TEXT = "Please sign up using your email address"
PROMPT_XPATH = f'//XCUIElementTypeStaticText[@name="{PROMPT_TEXT}"]'

CASE_ID = "100022"
CASE_DESC = "100022 验证注册时邮箱显示包含特殊字符"


def _click_next(driver) -> None:
    next_btn_selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next "]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Next")]'),
        (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeButton" AND name CONTAINS "Next"'),
    ]
    next_btn = None
    for by, sel in next_btn_selectors:
        try:
            candidate = WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((by, sel))
            )
            if candidate and candidate.is_displayed():
                next_btn = candidate
                break
        except Exception:
            continue
    if next_btn is None:
        raise TimeoutException("未找到 Next 按钮")
    try:
        next_btn.click()
    except Exception:
        rect = next_btn.rect or {}
        driver.execute_script(
            "mobile: tap",
            {
                "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
            },
        )


def _assert_email_format_prompt(driver) -> None:
    """断言出现邮箱格式提示，且仍停留在注册页。"""
    assert_on_signup_page(driver, timeout=5)

    error_selectors = [
        PROMPT_XPATH,
        f'//XCUIElementTypeStaticText[contains(@name, "{PROMPT_TEXT}")]',
        '//XCUIElementTypeStaticText[contains(@name, "email address")]',
    ]
    error_elem = None
    error_text = None
    for sel in error_selectors:
        try:
            for elem in driver.find_elements(AppiumBy.XPATH, sel):
                if elem.is_displayed():
                    error_elem = elem
                    error_text = elem.get_attribute("name")
                    print(f"    ✅ 找到提示: {sel}")
                    break
            if error_elem:
                break
        except Exception:
            continue

    assert error_elem is not None, f"未找到提示元素: {PROMPT_XPATH}"
    assert PROMPT_TEXT in (error_text or ""), f"提示内容不匹配: {error_text}"
    print(f"    ✅ 页面提示: {error_text}")


@pytest.fixture(scope="function")
def setup_driver():
    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.platform_version = os.environ.get("IOS_PLATFORM_VERSION", "18.5")
    options.device_name = os.environ.get("IOS_DEVICE_NAME", "iPhone 16 pro max")
    options.automation_name = "XCUITest"
    options.udid = os.environ.get("IOS_UDID", "00008140-00041C980A50801C")
    options.bundle_id = os.environ.get("IOS_BUNDLE_ID", "com.xingmai.tech")
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


def test_100022(setup_driver):
    """
    100022 验证注册时邮箱显示包含特殊字符

    输入特殊字符邮箱 → Next → 断言 Please sign up using your email address
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    try:
        current_step = "步骤0: 登出"
        print(f"🔄 {current_step}")
        try:
            check_and_logout(driver)
        except Exception as e:
            print(f"    ℹ️ 登出跳过: {e}")
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤1: 点击 Sign Up"
        print(f"🔄 {current_step}")
        sign_up_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign Up"]'))
        )
        sign_up_btn.click()
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤2: 输入特殊字符邮箱"
        print(f"🔄 {current_step}")
        email_address = get_next_unused_special_char_email()
        email_input = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
        )
        email_input.clear()
        email_input.send_keys(email_address)
        print(f"    ✅ 邮箱: {email_address}")
        time.sleep(1.2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤3: 勾选隐私政策"
        print(f"🔄 {current_step}")
        try:
            driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check selected"]')
        except Exception:
            check_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'))
            )
            check_btn.click()
        time.sleep(0.8)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 收起键盘（Done）"
        print(f"🔄 {current_step}")
        try:
            done_btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
            )
            done_btn.click()
            time.sleep(0.8)
        except Exception:
            print("    ℹ️ Done 未出现，跳过")
        print(f"✅ {current_step} - 完成")

        current_step = "步骤5: 点击 Next"
        print(f"🔄 {current_step}")
        _click_next(driver)
        time.sleep(2)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 断言提示文案"
        print(f"🔄 {current_step}")
        _assert_email_format_prompt(driver)
        print(f"✅ {current_step} - 完成")

        print(f"🎉 测试用例 {CASE_ID} 执行成功！")

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
