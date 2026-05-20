"""
200019 验证登录时，密码明文后，可以再次隐藏（Android）。

两次点击 lock：明文 → 再隐藏。
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

# ---------- 元素定位（Android，集中在文件顶部便于维护）----------
# 步骤1～2：已登录判据（More）与登录/注册入口页
# 步骤3：进入 Sign In 登录表单页
# 以下 XPath 供步骤4+ 输入、勾选、提交、断言时按需使用
# 已登录：首页底部/侧边 More
XPATH_MORE = '//android.view.View[@content-desc="More"]'
# More 备用定位
XPATH_MORE_ALT = '//*[@content-desc="More"]'
# 未登录：入口页至少可见 Sign In 或 Sign Up
XPATH_LANDING_ANY = (
    '//*[(@text="Sign In" or @text="Sign Up") or contains(@text,"Sign In") or contains(@text,"Sign Up") '
    'or @content-desc="Sign In" or @content-desc="Sign Up"]'
)
# 入口页 Sign In 按钮（优先 TextView）
XPATH_SIGN_IN = '//android.widget.TextView[@text="Sign In"]'
# Sign In 宽松匹配
XPATH_SIGN_IN_FALLBACK = '//*[@text="Sign In"]'
# 登录页邮箱输入框 ScrollView 内第 1 个 EditText
XPATH_EMAIL = "//android.widget.ScrollView/android.widget.EditText[1]"
# 点击聚焦邮箱（部分机型需点内层 View）
XPATH_EMAIL_FOCUS = "//android.widget.ScrollView/android.widget.EditText[1]/android.view.View[2]"
# 登录页密码输入框第 2 个 EditText
XPATH_PASSWORD = "//android.widget.ScrollView/android.widget.EditText[2]"
# 点击聚焦密码
XPATH_PASSWORD_FOCUS = "//android.widget.ScrollView/android.widget.EditText[2]/android.view.View[2]"
# 免责声明勾选框
XPATH_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
# 登录提交（next）
XPATH_NEXT = '//android.widget.ImageView[@content-desc="next"]'
# 邮箱右侧清空 ×
XPATH_CLEAR_EMAIL = '(//android.widget.ImageView[@content-desc="clear"])[1]'
# 密码右侧清空 ×
XPATH_CLEAR_PASSWORD = '(//android.widget.ImageView[@content-desc="clear"])[2]'
# 密码明文/密文切换（content-desc=lock）
XPATH_PASSWORD_EYE = '//android.widget.ImageView[@content-desc="lock"]'
# 登录成功判据：再次出现 More
XPATH_LOGGED_IN_MORE = '//*[@content-desc="More"] | //android.view.View[@content-desc="More"]'



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


def _password_field_text_blob(el) -> str:
    parts: list[str] = []
    for attr in ("text", "name", "content-desc", "hint"):
        try:
            v = el.get_attribute(attr)
            if v:
                parts.append(str(v).strip())
        except Exception:
            pass
    try:
        if el.text:
            parts.append(str(el.text).strip())
    except Exception:
        pass
    return " ".join(p for p in parts if p)


def _assert_password_plain_visible(driver, pwd_xpath: str, expected: str, timeout_s: float = 8.0) -> str:
    deadline = time.time() + timeout_s
    last_state = "未读取到明文"
    while time.time() < deadline:
        pwd_el = driver.find_element(AppiumBy.XPATH, pwd_xpath)
        blob = _password_field_text_blob(pwd_el)
        if expected and expected in blob:
            return blob
        for sub in pwd_el.find_elements(AppiumBy.XPATH, ".//*[@text]"):
            try:
                t = (sub.get_attribute("text") or sub.text or "").strip()
                if expected and expected in t:
                    return t
            except Exception:
                continue
        last_state = f"blob={blob!r}, password_attr={pwd_el.get_attribute('password')!r}"
        time.sleep(0.35)
    raise AssertionError(f"密码未显示为明文（期望包含 {expected!r}），最后状态: {last_state}")


def _assert_password_masked(driver, pwd_xpath: str, plain_password: str, timeout_s: float = 8.0) -> str:
    """断言密码已隐藏（可读文本中不应包含完整明文）。"""
    deadline = time.time() + timeout_s
    last_state = ""
    while time.time() < deadline:
        pwd_el = driver.find_element(AppiumBy.XPATH, pwd_xpath)
        blob = _password_field_text_blob(pwd_el)
        for sub in pwd_el.find_elements(AppiumBy.XPATH, ".//*[@text]"):
            try:
                t = (sub.get_attribute("text") or sub.text or "").strip()
                if plain_password and plain_password in t:
                    last_state = f"子节点仍为明文: {t!r}"
                    break
            except Exception:
                continue
        else:
            if not plain_password or plain_password not in blob:
                return blob or "masked"
            last_state = f"仍为明文: {blob!r}"
        time.sleep(0.35)
    raise AssertionError(f"密码未恢复密文，最后状态: {last_state}")


def _click_password_visibility_toggle(driver, timeout_s: int = 18) -> None:
    eye = WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_PASSWORD_EYE))
    )
    try:
        eye.click()
    except Exception:
        r = eye.rect
        driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])  # type: ignore[attr-defined]
    time.sleep(0.6)


def test_200019(setup_driver):
    """主流程见文件头步骤说明；每步独立 try 便于定位失败步骤。"""
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

        # 步骤2: 检测是否已登录；已登录则登出；确认在登录/注册入口页
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
            print("    ✅ 已处于登录/注册入口页")
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
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤4: 输入密码"
        print(f"🔄 {current_step}")
        try:
            pwd_value = os.environ.get("LOGIN_OK_PASSWORD", "Csx150128")
            print(f"    🔄 密码已填入（长度 {len(pwd_value)}）")
            for focus_xp in (XPATH_PASSWORD_FOCUS, XPATH_PASSWORD):
                try:
                    driver.find_element(AppiumBy.XPATH, focus_xp).click()
                    break
                except Exception:
                    continue
            print(f"    🔄 定位: {XPATH_PASSWORD}")
            pwd_el = WebDriverWait(driver, 18).until(
                EC.presence_of_element_located((AppiumBy.XPATH, XPATH_PASSWORD))
            )
            try:
                pwd_el.clear()
            except Exception:
                pass
            pwd_el.send_keys(pwd_value)
            time.sleep(0.3)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤5: 点击 lock 显示明文"
        print(f"🔄 {current_step}")
        try:
            _click_password_visibility_toggle(driver)
            _assert_password_plain_visible(driver, XPATH_PASSWORD, pwd_value)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        current_step = "步骤6: 再次点击 lock 隐藏密码"
        print(f"🔄 {current_step}")
        try:
            _click_password_visibility_toggle(driver)
            _assert_password_masked(driver, XPATH_PASSWORD, pwd_value)
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise


        print("🎉 测试用例 200019 执行成功！")

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
        save_failure_screenshot(driver, "test_200019_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:

        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200019",
            case_desc="200019 验证登录时，密码明文后，可以再次隐藏",
            result=case_result,
            fail_reason=fail_reason,
        )



# 本地直接运行：python 本文件.py 等价于 pytest -s 本文件
if __name__ == "__main__":
    pytest.main(["-s", __file__])

