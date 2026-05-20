"""
200001 验证登录页面到 APP 首页的「返回键」（Android）。

步骤（与用例流程图一致）：
  1. 重启 APP
  2. 检测是否已登录；已登录则执行 logout_android（check_and_logout）；未登录则确认在登录/注册入口页
  3. 点击 Sign In 进入登录页
  4. 点击左上角返回；断言回到入口页并显示 Sign Up
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

# 向上查找「APP外壳/1共用脚本」，导入 common_utils_android（登出 logout_android、报告、失败截图）
_cur = Path(__file__).resolve().parent
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

# 初始化本 run 的报告目录与控制台日志
RUN_LABEL = os.environ.get("RUN_LABEL", "android")
RUN_DIR, LOGGER, RUN_LABEL, RUN_TS = init_report(RUN_LABEL)
bind_logger_to_print(LOGGER)

# ---------- 元素定位（Android，与流程图一致）----------
# 步骤2：已登录特征（More）
# 已登录：首页底部/侧边 More
XPATH_MORE = '//android.view.View[@content-desc="More"]'
# More 备用定位
XPATH_MORE_ALT = '//*[@content-desc="More"]'

# 步骤2：登录/注册入口页（Sign In + Sign Up）
# 入口页 Sign In（可选二次确认）
XPATH_LANDING_SIGN_IN = '//*[@text="Sign In" or @content-desc="Sign In"]'
# 入口页 Sign Up（可选二次确认）
XPATH_LANDING_SIGN_UP = '//*[@text="Sign Up" or @content-desc="Sign Up"]'
# 未登录：入口页至少可见 Sign In 或 Sign Up
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)

# 步骤3：进入 Sign In 登录页
# 入口页 Sign In 按钮（优先 TextView）
XPATH_SIGN_IN = '//android.widget.TextView[@text="Sign In"]'
# Sign In 宽松匹配
XPATH_SIGN_IN_FALLBACK = '//*[@text="Sign In"]'

# 步骤4：登录页左上角返回
# 内页/协议页左上角返回
XPATH_BACK = '//android.widget.ImageView[@content-desc="back"]'

# 步骤4：断言回到入口页（流程图要求 Sign Up 可见）
# 断言回到入口页：Sign Up
XPATH_ASSERT_SIGN_UP = '//android.widget.TextView[@text="Sign Up"]'
# Sign Up 宽松匹配
XPATH_ASSERT_SIGN_UP_FALLBACK = '//*[@text="Sign Up"]'


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


def test_200001(setup_driver):
    """
    200001 验证登录页面到 APP 首页的「返回键」。
    """
    driver = setup_driver
    case_result = "success"
    fail_reason = ""
    current_step = "初始化"  # 失败时写入报告，标明停在哪一步

    try:
        # 步骤1: 重启 APP
        current_step = "步骤1: 重启APP"
        print(f"🔄 {current_step}")
        try:
            pkg = os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
            print(f"    🔄 driver.terminate_app / activate_app: {pkg}")
            try:
                # 先结束进程再拉起，保证用例从冷启动状态执行
                driver.terminate_app(pkg)
            except Exception:
                pass
            time.sleep(1.5)
            driver.activate_app(pkg)
            time.sleep(3.0)
            print("    ✅ APP 已重启")
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤2: 检测是否已登录；已登录则登出；未登录则确认在登录/注册入口页
        current_step = "步骤2: 检测登录状态并确保在登录/注册入口页"
        print(f"🔄 {current_step}")
        try:
            is_logged_in = False
            driver.implicitly_wait(0)  # 快速轮询 More，不阻塞
            try:
                for xp in (XPATH_MORE, XPATH_MORE_ALT):
                    print(f"    🔄 检测已登录元素: {xp}")
                    for elem in driver.find_elements(AppiumBy.XPATH, xp):
                        if elem.is_displayed():
                            is_logged_in = True
                            print(f"    ✅ 检测到已登录: {xp}")
                            break
                    if is_logged_in:
                        break
            finally:
                driver.implicitly_wait(5)

            if is_logged_in:
                print("    🔄 已登录，执行 check_and_logout（logout_android.py）")
                check_and_logout(driver)  # 走 logout_android：More → 设置 → Log Out
                print("    ✅ 登出完成")
                time.sleep(2.0)
            else:
                print("    ℹ️ 未检测到 More，判定未登录")

            print(f"    🔄 等待登录/注册入口页: {XPATH_LANDING_ANY}")
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY))
            )
            print("    ✅ 已处于登录/注册入口页（可见 Sign In 或 Sign Up）")

            # 补充确认入口页两个入口均存在（便于排查）
            for label, xp in (
                ("Sign In", XPATH_LANDING_SIGN_IN),
                ("Sign Up", XPATH_LANDING_SIGN_UP),
            ):
                try:
                    el = driver.find_element(AppiumBy.XPATH, xp)
                    if el.is_displayed():
                        print(f"    ✅ 入口页可见 {label}: {xp}")
                except Exception:
                    print(f"    ℹ️ 未单独匹配到 {label}（以 XPATH_LANDING_ANY 为准）")

            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤3: 点击 Sign In，进入登录页
        current_step = "步骤3: 点击 Sign In 进入登录页"
        print(f"🔄 {current_step}")
        try:
            sign_in_btn = None
            last_err = None
            for xp in (XPATH_SIGN_IN, XPATH_SIGN_IN_FALLBACK):
                print(f"    🔄 定位 Sign In: {xp}")
                try:
                    sign_in_btn = WebDriverWait(driver, 18).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, xp))
                    )
                    print(f"    ✅ 找到 Sign In: {xp}")
                    break
                except Exception as e:
                    last_err = e
                    continue
            if sign_in_btn is None:  # 主 XPath 与 fallback 均未找到
                raise TimeoutException(f"未找到 Sign In，最后错误: {last_err}")

            sign_in_btn.click()
            print(f"✅ {current_step} - 完成")
            time.sleep(1.5)
        except Exception as e:
            fail_reason = f"{current_step}失败: 无法找到或点击 Sign In - {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        # 步骤4: 点击左上角返回，断言回到入口页并显示 Sign Up
        current_step = "步骤4: 点击返回并断言入口页显示 Sign Up"
        print(f"🔄 {current_step}")
        try:
            print(f"    🔄 定位返回按钮: {XPATH_BACK}")
            back_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_BACK))
            )
            try:
                back_button.click()  # 优先原生 click
            except Exception:
                r = back_button.rect
                tx = int(r["x"] + r["width"] / 2)
                ty = int(r["y"] + r["height"] / 2)
                print(f"    🔄 click 失败，坐标点击: ({tx}, {ty})")
                driver.tap([(tx, ty)])  # type: ignore[attr-defined]  # click 失败时用中心坐标
            print("    ✅ 已点击返回")
            time.sleep(2.0)

            sign_up_el = None
            last_err = None
            for xp in (XPATH_ASSERT_SIGN_UP, XPATH_ASSERT_SIGN_UP_FALLBACK):
                print(f"    🔄 断言 Sign Up 可见: {xp}")
                try:
                    sign_up_el = WebDriverWait(driver, 18).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, xp))
                    )
                    assert sign_up_el.is_displayed(), "Sign Up 存在但不可见"
                    print(f"    ✅ Sign Up 已显示: {xp}")
                    break
                except Exception as e:
                    last_err = e
                    sign_up_el = None
                    continue
            if sign_up_el is None:
                raise TimeoutException(f"返回后未找到 Sign Up，最后错误: {last_err}")

            print(f"✅ {current_step} - 完成，用例执行成功")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例 200001 执行成功！")

    except Exception as e:
        # 任一步骤 raise 后：标记失败、打印步骤、截图、断言让 pytest 记为 FAILED
        case_result = "failed"
        if not fail_reason:
            fail_reason = f"{current_step}失败: {str(e)}"
        print(f"\n{'=' * 60}")
        print(f"❌ 测试失败")
        print(f"📍 失败步骤: {current_step}")
        print(f"📝 失败原因: {fail_reason}")
        print(f"{'=' * 60}")
        traceback.print_exc()
        save_failure_screenshot(driver, "test_200001_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        # 无论成功失败都写入 platform 报告
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200001",
            case_desc="200001 验证登录页面到APP首页的返回键",
            result=case_result,
            fail_reason=fail_reason,
        )



# 本地直接运行：python 本文件.py 等价于 pytest -s 本文件
if __name__ == "__main__":
    pytest.main(["-s", __file__])
