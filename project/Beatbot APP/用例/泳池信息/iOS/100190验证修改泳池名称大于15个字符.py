# -*- coding: utf-8 -*-
"""
100190 验证修改泳池名称大于15个字符（iOS / 9泳池信息）

参考流程（截图）：
  1. 重启 APP → 检查登录
  2. mine → CommonEdit → 泳池信息 CommonArrow[3]
  3. 点击泳池名称 CommonArrow[1]
  4. 输入 16 个字符，点击 Confirm
  5. 断言 toast：名称不可以超过15个字符（可能为英文，停留极短）
  6. 断言泳池名称未修改成功（仍为原值）
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

CASE_ID = "100190"
CASE_DESC = "100190 验证修改泳池名称大于15个字符"

LOGIN_INDICATORS = [
    '//XCUIElementTypeButton[@name="home sel"]',
    '//XCUIElementTypeButton[@name="mine sel"]',
    '//XCUIElementTypeButton[@name="mine"]',
]

POOL_INFO_ENTRY_XPATH = '(//XCUIElementTypeImage[@name="CommonArrow"])[3]'
POOL_NAME_ENTRY_XPATH = '(//XCUIElementTypeImage[@name="CommonArrow"])[1]'
COMMON_DELETE_XPATH = '//XCUIElementTypeButton[@name="commonDelete"]'
CONFIRM_BTN_XPATH = '//XCUIElementTypeButton[@name="Confirm"]'

# 16 个字符（超过 15 字限制）
OVER_LIMIT_POOL_NAME = os.environ.get("IOS_POOL_NAME_OVER_16", "1234567890123456")

# toast 可能中文/英文，停留极短
MAX_LENGTH_TOAST_KEYWORDS = [
    "名称不可以超过15个字符",
    "不可以超过15个字符",
    "超过15个字符",
    "15个字符",
    "cannot exceed 15",
    "Cannot exceed 15",
    "exceed 15 characters",
    "15 characters",
    "maximum of 15",
    "max 15",
    "15 character",
]

POOL_INFO_FIELD_LABELS = {
    "Pool Name",
    "Pool Material",
    "Sanitation System",
    "Pool Type",
    "Pool Shape",
    "Floor Shape",
    "Water Capacity",
    "Surface Area",
    "Maximum Depth",
    "Pool Amenities",
}


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


def _click_element(driver, item) -> None:
    if isinstance(item, tuple):
        by, sel = item
        el = WebDriverWait(driver, 12).until(EC.presence_of_element_located((by, sel)))
    else:
        el = WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((AppiumBy.XPATH, item))
        )
    if not el.is_displayed():
        raise TimeoutException(f"元素不可见: {item}")
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
    time.sleep(1.0)


def _navigate_to_pool_info_page(driver) -> None:
    _click_mine_tab(driver)
    _click_common_edit(driver)
    _click_element(driver, POOL_INFO_ENTRY_XPATH)
    WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Pool Name"]'))
    )
    print("    ✅ 已进入泳池信息页")


def _click_pool_name_entry(driver) -> None:
    candidates = [
        POOL_NAME_ENTRY_XPATH,
        (AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeImage[`name == "CommonArrow"`][1]'),
    ]
    last_err = None
    for item in candidates:
        try:
            _click_element(driver, item)
            print("    ✅ 已打开泳池名称编辑弹框")
            return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到泳池名称入口 CommonArrow[1]: {last_err}")


def _dismiss_keyboard_if_any(driver) -> None:
    try:
        driver.hide_keyboard()
        time.sleep(0.3)
        return
    except Exception:
        pass
    for xp in (
        '//XCUIElementTypeButton[@name="Done"]',
        '//XCUIElementTypeButton[@name="Return"]',
    ):
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            if el.is_displayed() and el.is_enabled():
                el.click()
                time.sleep(0.3)
                return
        except Exception:
            continue


def _find_pool_name_input(driver):
    for xp in (
        '//XCUIElementTypeTextField',
        '//XCUIElementTypeTextView',
        '//XCUIElementTypeSearchField',
    ):
        try:
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return el
        except Exception:
            continue
    raise TimeoutException("未找到泳池名称输入框")


def _set_text_without_keyboard(driver, text: str) -> None:
    input_el = _find_pool_name_input(driver)
    try:
        input_el.set_value(text)
        time.sleep(0.4)
        current = (input_el.get_attribute("value") or input_el.text or "").strip()
        if current == text or text in current:
            print(f"    ✅ set_value 写入成功: {text!r} (len={len(text)})")
            return
    except Exception:
        pass
    try:
        driver.execute_script("mobile: setValue", {"elementId": input_el.id, "value": text})
        time.sleep(0.4)
        current = (input_el.get_attribute("value") or input_el.text or "").strip()
        if current == text or text in current:
            print(f"    ✅ mobile:setValue 写入成功: {text!r}")
            return
    except Exception:
        pass
    try:
        driver.set_clipboard(content=text, content_type="plaintext")
    except TypeError:
        driver.set_clipboard(text)
    try:
        input_el.click()
        time.sleep(0.2)
        driver.execute_script("mobile: paste", {"elementId": input_el.id})
    except Exception:
        driver.execute_script("mobile: paste", {})
    time.sleep(0.5)
    current = (input_el.get_attribute("value") or input_el.text or "").strip()
    if current != text and text not in current:
        raise AssertionError(f"写入泳池名称失败: 期望 {text!r}, 实际 {current!r}")
    print(f"    ✅ 剪贴板粘贴写入成功: {text!r}")


def _click_common_delete(driver) -> None:
    el = _wait_clickable(driver, COMMON_DELETE_XPATH, timeout=10)
    el.click()
    time.sleep(0.5)
    print("    ✅ 已点击 commonDelete 清空")


def _click_confirm(driver) -> None:
    _dismiss_keyboard_if_any(driver)
    el = _wait_clickable(driver, CONFIRM_BTN_XPATH, timeout=12)
    el.click()
    print("    ✅ 已点击 Confirm")


def _poll_for_short_toast(driver, keywords: list[str], timeout_s: float = 10, poll_s: float = 0.15) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for kw in keywords:
            esc = kw.replace('"', '\\"')
            pred = (
                '(type == "XCUIElementTypeStaticText" OR type == "XCUIElementTypeTextView") AND '
                f'(name CONTAINS "{esc}" OR label CONTAINS "{esc}" OR value CONTAINS "{esc}")'
            )
            try:
                for el in driver.find_elements(AppiumBy.IOS_PREDICATE, pred):
                    if el.is_displayed():
                        text = (el.get_attribute("name") or el.get_attribute("label") or "").strip()
                        print(f"    ✅ 捕获 toast: {text or kw}")
                        return text or kw
            except Exception:
                continue
        time.sleep(poll_s)
    raise AssertionError(
        f"{timeout_s}s 内未捕获超长提示 toast（关键词: {keywords[:3]}...）"
    )


def _read_pool_name_value_on_info_page(driver) -> str:
    try:
        label = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Pool Name"]')
        label_rect = label.rect or {}
        label_y = label_rect.get("y", 0)
        best = ""
        best_dist = 9999
        for el in driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeStaticText"):
            if not el.is_displayed():
                continue
            name = (el.get_attribute("name") or el.get_attribute("label") or "").strip()
            if not name or name == "Pool Name":
                continue
            if name in POOL_INFO_FIELD_LABELS:
                continue
            rect = el.rect or {}
            dist = abs(rect.get("y", 0) - label_y)
            if dist < best_dist and dist < 100:
                best_dist = dist
                best = name
        if best:
            return best
    except Exception:
        pass
    raise AssertionError("未能读取泳池信息页当前名称")


def _assert_pool_name_unchanged(driver, expected_name: str) -> None:
    current = _read_pool_name_value_on_info_page(driver)
    assert current == expected_name, (
        f"泳池名称不应被修改: 期望仍为 {expected_name!r}, 实际 {current!r}"
    )
    assert len(current) <= 15, f"当前名称长度异常: {len(current)}"
    print(f"    ✅ 泳池名称未变，仍为: {expected_name!r}")


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


def test_100190(setup_driver):
    """100190 验证修改泳池名称大于15个字符"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"
    original_pool_name = ""

    over_limit_name = OVER_LIMIT_POOL_NAME
    assert len(over_limit_name) == 16, f"测试数据应为16字符，当前 len={len(over_limit_name)}"

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

        current_step = "步骤3: mine → CommonEdit → 泳池信息页"
        print(f"🔄 {current_step}")
        _navigate_to_pool_info_page(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤4: 记录修改前泳池名称"
        print(f"🔄 {current_step}")
        original_pool_name = _read_pool_name_value_on_info_page(driver)
        print(f"    ℹ️ original_pool_name={original_pool_name!r} (len={len(original_pool_name)})")
        print(f"✅ {current_step} - 完成")

        current_step = "步骤5: 点击泳池名称，输入16字符并 Confirm"
        print(f"🔄 {current_step}")
        _click_pool_name_entry(driver)
        _dismiss_keyboard_if_any(driver)
        _click_common_delete(driver)
        _set_text_without_keyboard(driver, over_limit_name)
        _dismiss_keyboard_if_any(driver)
        _click_confirm(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 断言 toast 提示名称不可超过15字符"
        print(f"🔄 {current_step}")
        toast_text = _poll_for_short_toast(
            driver,
            MAX_LENGTH_TOAST_KEYWORDS,
            timeout_s=float(os.environ.get("TOAST_POLL_TIMEOUT_S", "10")),
            poll_s=float(os.environ.get("TOAST_POLL_INTERVAL_S", "0.15")),
        )
        print(f"    ℹ️ toast={toast_text}")
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 断言修改失败，泳池名称仍为原值"
        print(f"🔄 {current_step}")
        # 若仍在编辑弹框，先 Cancel 回到列表页再断言
        for xp in (
            '//XCUIElementTypeButton[@name="Cancel"]',
            '//XCUIElementTypeButton[@name="cancel"]',
            '//XCUIElementTypeButton[@name="取消"]',
        ):
            try:
                el = driver.find_element(AppiumBy.XPATH, xp)
                if el.is_displayed():
                    el.click()
                    time.sleep(1.0)
                    break
            except Exception:
                continue
        _assert_pool_name_unchanged(driver, original_pool_name)
        print(f"✅ {current_step} - 完成")

        print(f"🎉 测试用例 {CASE_ID} 执行成功！")

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = (
                f"{current_step}失败: {e} | original={original_pool_name!r} "
                f"| over_limit={over_limit_name!r}"
            )
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
