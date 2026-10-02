# -*- coding: utf-8 -*-
"""
100178 验证能正常修改头像（iOS / 8个人资料）

参考流程（截图）：
  1. 重启 APP
  2. 检查是否已登录；未登录则登录
  3. 点击 mine 按钮：//XCUIElementTypeButton[@name="mine"]，进入设置页面
  4. 点击编辑按钮：//XCUIElementTypeButton[@name="CommonEdit"]，进入账号与安全页面
  5. 点击头像按钮：//XCUIElementTypeScrollView/XCUIElementTypeOther/XCUIElementTypeImage[1]，进入头像页
  6. 点击切换头像按钮：//XCUIElementTypeButton[@name="Change Avatar"]，弹出选择框（含 Choose from Phone Album）
  7. 点击选择头像按钮：//XCUIElementTypeButton[@name="Choose from Phone Album"]，进入相册
  8. 随机点击一张图片（示例：Cell[1]/Cell[3]/Cell[5]）
  9. 图片选中后页面出现：//XCUIElementTypeStaticText[@name="完成"] 并点击，页面返回上级菜单页面
  10. 断言头像已变更：头像 Image 与步骤 8 选择图片一致（这里用“头像元素截图 hash 变化”做稳健校验）
"""

import hashlib
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

CASE_ID = "100178"
CASE_DESC = "100178 验证能正常修改头像"

LOGIN_INDICATORS = [
    '//XCUIElementTypeButton[@name="home sel"]',
    '//XCUIElementTypeButton[@name="mine sel"]',
    '//XCUIElementTypeButton[@name="mine"]',
]

CHANGE_AVATAR_BTN_XPATH = '//XCUIElementTypeButton[@name="Change Avatar"]'

CHOOSE_FROM_PHONE_ALBUM_SELECTORS = [
    '//XCUIElementTypeButton[@name="Choose from Phone Album"]',
    '//XCUIElementTypeButton[@name="choose from Phone Album"]',
    '//XCUIElementTypeButton[contains(@name,"Phone Album")]',
    '//XCUIElementTypeButton[contains(@name,"相册")]',
    '//XCUIElementTypeButton[contains(@name,"从手机相册")]',
]

FINISH_BUTTON_SELECTORS = [
    '//XCUIElementTypeStaticText[@name="完成"]',
    '//XCUIElementTypeButton[@name="完成"]',
    '//XCUIElementTypeStaticText[@name="Done"]',
    '//XCUIElementTypeButton[@name="Done"]',
]


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

def _resolve_account_security_avatar_thumbnail(driver):
    """
    账号与安全页的头像缩略图（截图步骤5的 Image[1]）。
    用于：修改前/后 hash 对比，确保真的换了头像。
    """
    candidates = [
        (AppiumBy.XPATH, "//XCUIElementTypeScrollView/XCUIElementTypeOther/XCUIElementTypeImage[1]"),
        (AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeScrollView/**/XCUIElementTypeImage[1]"),
        (AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeImage[1]"),
    ]
    last_err = None
    for by, sel in candidates:
        try:
            el = WebDriverWait(driver, 12).until(EC.presence_of_element_located((by, sel)))
            if el.is_displayed():
                return el
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到账号与安全页头像缩略图 Image[1]: {last_err}")


def _enter_avatar_page_from_account_security(driver) -> None:
    """
    兼容两种 UI：
    - 账号与安全页直接可点头像（截图步骤5）
    - 需要先点“个人资料/Personal Information/Profile”入口，再点头像
    """
    try:
        _click_avatar_to_enter_avatar_page(driver)
        return
    except Exception as direct_err:
        print(f"    ℹ️ 账号与安全页直接点头像失败，尝试进入个人资料入口: {direct_err}")

    _click_personal_profile_entry(driver)
    _click_avatar_to_enter_avatar_page(driver)


def _assert_on_avatar_page(driver) -> None:
    # 用可见性断言，避免元素存在但不可见（动画/遮罩）导致误判
    el = WebDriverWait(driver, 12).until(
        EC.visibility_of_element_located((AppiumBy.XPATH, CHANGE_AVATAR_BTN_XPATH))
    )
    assert el.is_displayed(), "Change Avatar 不可见"


def _wait_return_to_upper_menu_after_finish(driver) -> None:
    """
    点击相册“完成”后回到上级菜单页（截图步骤9）。
    这里以“账号与安全页头像缩略图出现”为准。
    """
    WebDriverWait(driver, 25).until(lambda d: _resolve_account_security_avatar_thumbnail(d))
    time.sleep(1.0)


def _click_change_avatar(driver) -> None:
    _wait_clickable(driver, CHANGE_AVATAR_BTN_XPATH, timeout=12).click()
    time.sleep(1.0)


def _assert_choose_from_phone_album_visible(driver) -> None:
    last_err = None
    for xp in CHOOSE_FROM_PHONE_ALBUM_SELECTORS:
        try:
            el = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                print(f"    ✅ 修改头像弹框已出现（命中: {xp}）")
                return
        except Exception as e:
            last_err = e
    raise AssertionError(f"未检测到 Choose from Phone Album（最后错误: {last_err}）")


def _click_choose_from_phone_album(driver) -> None:
    last_err = None
    for xp in CHOOSE_FROM_PHONE_ALBUM_SELECTORS:
        try:
            _wait_clickable(driver, xp, timeout=10).click()
            time.sleep(2.0)
            return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"点击 Choose from Phone Album 失败（最后错误: {last_err}）")


def _try_click_system_permissions_if_any(driver) -> None:
    candidates = [
        '//XCUIElementTypeButton[@name="允许"]',
        '//XCUIElementTypeButton[@name="Allow"]',
        '//XCUIElementTypeButton[@name="好"]',
        '//XCUIElementTypeButton[@name="OK"]',
    ]
    for xp in candidates:
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            if el.is_displayed() and el.is_enabled():
                el.click()
                time.sleep(1.0)
                return
        except Exception:
            continue


def _select_photo_cell(driver) -> str:
    """
    参考截图：随机点击 Cell[1]/Cell[3]/Cell[5]
    返回：点击到的 xpath（用于日志追踪）
    """
    candidates = [
        '//XCUIElementTypeCollectionView/XCUIElementTypeCollectionView/XCUIElementTypeCell[1]',
        '//XCUIElementTypeCollectionView/XCUIElementTypeCollectionView/XCUIElementTypeCell[3]',
        '//XCUIElementTypeCollectionView/XCUIElementTypeCollectionView/XCUIElementTypeCell[5]',
        '(//XCUIElementTypeCollectionView//XCUIElementTypeCell)[1]',
    ]
    last_err = None
    for xp in candidates:
        try:
            el = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                el.click()
                time.sleep(1.2)
                print(f"    ✅ 已选择相册图片（命中: {xp}）")
                return xp
        except Exception as e:
            last_err = e
    raise TimeoutException(f"相册选择图片失败（最后错误: {last_err}）")


def _click_finish(driver) -> None:
    last_err = None
    for xp in FINISH_BUTTON_SELECTORS:
        try:
            el = WebDriverWait(driver, 25).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            if el.is_displayed():
                el.click()
                time.sleep(2.0)
                print(f"    ✅ 已点击完成（命中: {xp}）")
                return
        except Exception as e:
            last_err = e
    raise AssertionError(f"未检测到可点击的“完成/Done”（最后错误: {last_err}）")


def _resolve_avatar_image_element(driver):
    """
    截图提示头像区域为 Image[2]，但不同版本层级可能不同；
    这里按常见结构做多 selector 兜底。
    """
    candidates = [
        (AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeImage[2]"),
        (AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeImage[1]"),
        (AppiumBy.XPATH, "//XCUIElementTypeImage[2]"),
        (AppiumBy.XPATH, "//XCUIElementTypeImage[1]"),
    ]
    last_err = None
    for by, sel in candidates:
        try:
            el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((by, sel)))
            if el.is_displayed():
                return el
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到头像 Image 元素用于截图比对（最后错误: {last_err}）")


def _element_png_md5(el) -> str:
    png = el.screenshot_as_png
    return hashlib.md5(png).hexdigest()


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


def test_100178(setup_driver):
    """100178 验证能正常修改头像"""
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"

    before_hash = ""
    after_hash = ""
    picked_cell = ""

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

        current_step = "步骤5: 在账号与安全页记录头像缩略图 hash，并点击头像进入头像页"
        print(f"🔄 {current_step}")
        thumb_el = _resolve_account_security_avatar_thumbnail(driver)
        before_hash = _element_png_md5(thumb_el)
        print(f"    ℹ️ before_hash={before_hash}")
        try:
            thumb_el.click()
        except Exception:
            rect = thumb_el.rect or {}
            driver.execute_script(
                "mobile: tap",
                {
                    "x": int(rect.get("x", 0) + rect.get("width", 0) / 2),
                    "y": int(rect.get("y", 0) + rect.get("height", 0) / 2),
                },
            )
        time.sleep(1.2)
        _assert_on_avatar_page(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤6: 点击 Change Avatar 弹出修改头像弹框"
        print(f"🔄 {current_step}")
        _click_change_avatar(driver)
        _assert_choose_from_phone_album_visible(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤7: 点击 Choose from Phone Album 进入相册"
        print(f"🔄 {current_step}")
        _click_choose_from_phone_album(driver)
        _try_click_system_permissions_if_any(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤8: 相册随机选择图片（cell[1]/[3]/[5]）"
        print(f"🔄 {current_step}")
        picked_cell = _select_photo_cell(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤9: 点击“完成”，返回上级菜单页面"
        print(f"🔄 {current_step}")
        _click_finish(driver)
        _wait_return_to_upper_menu_after_finish(driver)
        print(f"✅ {current_step} - 完成")

        current_step = "步骤10: 断言头像已变更（上级菜单页头像缩略图 hash 与修改前不同）"
        print(f"🔄 {current_step}")
        after_el = _resolve_account_security_avatar_thumbnail(driver)
        after_hash = _element_png_md5(after_el)
        print(f"    ℹ️ after_hash={after_hash}")
        assert before_hash and after_hash, "头像 hash 为空"
        assert before_hash != after_hash, (
            "头像疑似未变更（hash 未变化）。"
            f" picked_cell={picked_cell}, before={before_hash}, after={after_hash}"
        )
        print("    ✅ 头像已变更（hash 已变化）")
        print(f"✅ {current_step} - 完成")

        print(f"🎉 测试用例 {CASE_ID} 执行成功！")

    except Exception as e:
        case_result = "failed"
        if not fail_reason:
            fail_reason = (
                f"{current_step}失败: {e} | picked_cell={picked_cell} "
                f"| before={before_hash} after={after_hash}"
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

