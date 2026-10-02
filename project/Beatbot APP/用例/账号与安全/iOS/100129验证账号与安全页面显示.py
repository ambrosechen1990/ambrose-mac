# -*- coding: utf-8 -*-
"""
100129 验证账号与安全页面显示（iOS / 4显示）

流程：
  1. 重启 APP
  2. 检查是否已登录；未登录则调用登录流程
  3. 点击 mine → 设置页
  4. 点击 CommonEdit → 账号与安全页
  5. 断言页面 8 项文案均显示
"""
import os  # 环境变量、路径
import sys  # 动态注入共用脚本路径
import time  # 步骤间等待
import traceback  # 失败时打印堆栈
from pathlib import Path

import pytest  # 测试框架与 fixture
from appium import webdriver  # Appium WebDriver
from appium.options.ios import XCUITestOptions  # iOS 能力配置
from appium.webdriver.common.appiumby import AppiumBy  # iOS 元素定位
from selenium.webdriver.support import expected_conditions as EC  # 显式等待条件
from selenium.webdriver.support.ui import WebDriverWait  # 显式等待

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
    bind_logger_to_print,  # 日志绑定到 print
    init_report,  # 初始化报告目录
    save_failure_screenshot,  # 失败截图
    write_report,  # 写入 xlsx/html 报告
)
from ios_sign_in_helpers_登录辅助 import (  # Sign In 页邮箱/密码输入解析
    resolve_sign_in_email_input,
    resolve_sign_in_password_input,
)

# ---------- 报告与运行配置 ----------
RUN_LABEL = os.environ.get("RUN_LABEL", "ios")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

# ---------- 登录账号（可通过环境变量覆盖） ----------
LOGIN_EMAIL = os.environ.get("IOS_LOGIN_EMAIL", "haoc51888@gmail.com")
LOGIN_PASSWORD = os.environ.get("IOS_LOGIN_PASSWORD", "Csx150128")
BUNDLE_ID = os.environ.get("IOS_BUNDLE_ID", "com.xingmai.tech")

# ---------- 已登录态判据：底部 Tab 选中态或 mine 按钮 ----------
LOGIN_INDICATORS = [
    '//XCUIElementTypeButton[@name="home sel"]',
    '//XCUIElementTypeButton[@name="mine sel"]',
    '//XCUIElementTypeButton[@name="mine"]',
]

# ---------- 账号与安全页需展示的 8 项文案（流程图步骤 5） ----------
ACCOUNT_SECURITY_LABELS = [
    "Avatar",
    "Name",
    "Region",
    "Time Zone",
    "My Pool",
    "Email",
    "Password",
    "Account Deletion",
]


def _wait_clickable(driver, xpath: str, timeout: float = 10):
    """等待元素可点击并返回。"""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, xpath))
    )


def _wait_visible_static_text(driver, name: str, timeout: float = 10):
    """
    等待 StaticText 出现且可见。
    定位：//XCUIElementTypeStaticText[@name="{name}"]
    """
    xpath = f'//XCUIElementTypeStaticText[@name="{name}"]'
    el = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((AppiumBy.XPATH, xpath))
    )
    assert el.is_displayed(), f"元素存在但不可见: {name}"
    return el


def _is_logged_in(driver) -> bool:
    """
    检测是否已登录。
    任意 LOGIN_INDICATORS 可见即视为已登录。
    """
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
    """
    步骤1：重启 APP（terminate + activate），回到默认启动态。
    """
    caps = getattr(driver, "capabilities", {}) or {}
    bundle_id = caps.get("bundleId") or BUNDLE_ID
    driver.terminate_app(bundle_id)
    time.sleep(1.5)
    driver.activate_app(bundle_id)
    time.sleep(2)
    print("    ✅ APP 已重启")


def _wait_for_bottom_mine_after_login(driver, timeout_s: float) -> None:
    """
    登录成功后等待底部 Mine Tab 出现。
    兼容 mine / mine sel / label 等多种构建差异。
    """
    candidates = [
        '//XCUIElementTypeButton[@name="mine"]',
        '//XCUIElementTypeButton[@name="mine sel"]',
        '//XCUIElementTypeButton[@label="mine"]',
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
    步骤2（未登录分支）：执行 Sign In 登录。
    流程对齐 100015：Sign In → 邮箱 → 密码 → Done → 勾选协议 → login icon → 等待 Mine。
    """
    # 进入 Sign In 页
    sign_in_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="Sign In"]', timeout=12)
    sign_in_btn.click()
    time.sleep(1.5)

    # 输入邮箱
    email_input = resolve_sign_in_email_input(driver)
    email_input.clear()
    email_input.send_keys(LOGIN_EMAIL)
    time.sleep(0.8)

    # 输入密码
    password_input = resolve_sign_in_password_input(driver)
    password_input.clear()
    password_input.send_keys(LOGIN_PASSWORD)
    time.sleep(0.8)

    # 收起键盘（Done 可能不存在则跳过）
    try:
        done_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Done"]'))
        )
        done_btn.click()
        time.sleep(0.8)
    except Exception:
        pass

    # 勾选用户协议与隐私政策
    check_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="login check normal"]', timeout=8)
    check_btn.click()
    time.sleep(0.8)

    # 点击登录按钮
    login_btn = WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'name == "login icon"'))
    )
    login_btn.click()
    post_wait = float(os.environ.get("LOGIN_POST_CLICK_WAIT_S", "4"))
    time.sleep(post_wait)

    # 断言登录成功：底部出现 Mine
    timeout_ok = float(os.environ.get("LOGIN_SUCCESS_TIMEOUT_S", "45"))
    _wait_for_bottom_mine_after_login(driver, timeout_s=timeout_ok)
    print("    ✅ 登录成功，已出现 Mine Tab")


def _click_mine_tab(driver) -> None:
    """
    步骤3：点击更多（mine）按钮，进入设置页。
    定位：//XCUIElementTypeButton[@name="mine"]（优先，兼容 mine sel）。
    """
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
    raise AssertionError("未找到可点击的 mine / mine sel 按钮")


def _click_common_edit(driver) -> None:
    """
    步骤4：点击编辑按钮，进入账号与安全页。
    定位：//XCUIElementTypeButton[@name="CommonEdit"]
    """
    edit_btn = _wait_clickable(driver, '//XCUIElementTypeButton[@name="CommonEdit"]', timeout=12)
    edit_btn.click()
    time.sleep(1.5)
    print("    ✅ 已点击 CommonEdit，进入账号与安全页")


def _assert_account_security_page(driver) -> None:
    """
    步骤5：断言账号与安全页 8 项文案均显示。
    每项对应 XCUIElementTypeStaticText[@name="..."]。
    """
    missing = []
    for label in ACCOUNT_SECURITY_LABELS:
        try:
            _wait_visible_static_text(driver, label, timeout=12)
            print(f"    ✅ 页面显示: {label}")
        except Exception as e:
            missing.append(f"{label}({e})")
    if missing:
        raise AssertionError("账号与安全页缺少元素: " + "; ".join(missing))


@pytest.fixture(scope="function")
def setup_driver():
    """
    iOS 设备驱动配置：每个测试函数独立创建 WebDriver。
    可通过环境变量覆盖 UDID、Appium 地址等。
    """
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


def test_100129(setup_driver):
    """
    100129 验证账号与安全页面显示

    1. 重启 APP
    2. 检查是否已登录；未登录则执行登录
    3. 点击 mine，进入设置页
    4. 点击 CommonEdit，进入账号与安全页
    5. 断言 Avatar / Name / Region / Time Zone / My Pool / Email / Password / Account Deletion 均显示
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

        # ---------- 步骤3：点击 mine → 设置页 ----------
        current_step = "步骤3: 点击 mine 进入设置页"
        print(f"🔄 {current_step}")
        _click_mine_tab(driver)
        print(f"✅ {current_step} - 完成")

        # ---------- 步骤4：点击 CommonEdit → 账号与安全页 ----------
        current_step = "步骤4: 点击 CommonEdit 进入账号与安全页"
        print(f"🔄 {current_step}")
        _click_common_edit(driver)
        print(f"✅ {current_step} - 完成")

        # ---------- 步骤5：断言页面元素 ----------
        current_step = "步骤5: 断言账号与安全页元素显示"
        print(f"🔄 {current_step}")
        _assert_account_security_page(driver)
        print(f"✅ {current_step} - 完成")

        print("🎉 测试用例100129执行成功！")

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
        save_failure_screenshot(driver, "test_100129_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        # 无论成功失败均写入测试报告
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="ios",
            case_id="100129",
            case_desc="100129 验证账号与安全页面显示",
            result=case_result,
            fail_reason=fail_reason,
        )


if __name__ == "__main__":
    pytest.main(["-s", __file__])
