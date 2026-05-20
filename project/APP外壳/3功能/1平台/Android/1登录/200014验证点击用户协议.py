"""
200014 验证点击用户协议（Android）。

步骤：重启 → 登出/入口页 → Sign In → User Agreement → 断言 Last Modified / Introduction（对齐 iOS 102666）。
免责声明内 User Agreement 为 ClickableSpan，点击策略与 200013 相同（换行时优先第二行左侧）。
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

# ---------- 通用入口/登录定位（200001 架构）----------
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

# Sign In 免责声明整句（Privacy Policy / User Agreement 为 ClickableSpan）
DISCLAIMER_TEXT = "I have read and understood the Privacy Policy and agree to the User Agreement."
PRIVACY_LINK_PHRASE = "Privacy Policy"
USER_AGREEMENT_LINK_PHRASE = "User Agreement"

# ---------- 免责声明内链接点击（ClickableSpan 无独立节点，需坐标/短节点策略）----------
# 以下辅助函数仅本文件使用：计算矩形、点击 User Agreement 区域、等待进入 WebView/隐私页

def _rect_of(el) -> dict:
    loc = el.location
    sz = el.size
    return {"x": int(loc["x"]), "y": int(loc["y"]), "w": int(sz["width"]), "h": int(sz["height"])}


def _rects_overlap(a: dict, b: dict, pad: int = 4) -> bool:
    ax1, ay1, ax2, ay2 = a["x"] - pad, a["y"] - pad, a["x"] + a["w"] + pad, a["y"] + a["h"] + pad
    bx1, by1, bx2, by2 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)


def _x_ratio_for_phrase_in_line(text: str, phrase: str) -> float:
    """按短语在免责声明中的位置计算横向点击比例；User Agreement 在句末，默认偏右 (~0.82)。"""
    t = text.strip() or DISCLAIMER_TEXT
    pos = t.find(phrase)
    if pos < 0:
        return 0.82 if phrase == USER_AGREEMENT_LINK_PHRASE else 0.38
    mid = pos + len(phrase) / 2.0
    return mid / max(len(t), 1)


def _click_gesture_at(driver, x: int, y: int) -> None:
    try:
        driver.execute_script("mobile: clickGesture", {"x": int(x), "y": int(y)})
    except Exception:
        driver.tap([(int(x), int(y))])  # type: ignore[attr-defined]


def _sign_in_password_field_visible(driver) -> bool:
    try:
        els = driver.find_elements(AppiumBy.XPATH, "//android.widget.ScrollView/android.widget.EditText[2]")
        return bool(els and els[0].is_displayed())
    except Exception:
        return False


def _exact_disclaimer_textview_visible(driver) -> bool:
    try:
        els = driver.find_elements(
            AppiumBy.XPATH, f'//android.widget.TextView[@text="{DISCLAIMER_TEXT}"]'
        )
        return bool(els and els[0].is_displayed())
    except Exception:
        return False


def _user_agreement_page_indicators_hit(driver) -> bool:
    """
    是否已进入用户协议页（对齐 200011 隐私页判定思路：WebView/返回栏 + 协议正文特征）。
    仍停在 Sign In 且免责声明可见时返回 False，避免误判。
    """

    def _any_visible(xp: str) -> bool:
        try:
            for e in driver.find_elements(AppiumBy.XPATH, xp):
                if e.is_displayed():
                    return True
        except Exception:
            pass
        return False

    on_sign_in = _sign_in_password_field_visible(driver) and _exact_disclaimer_textview_visible(driver)

    if _any_visible("//android.webkit.WebView") and not on_sign_in:
        return True
    try:
        for w in driver.find_elements(
            AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().classNameMatches(".*WebView")'
        ):
            if w.is_displayed() and not on_sign_in:
                return True
    except Exception:
        pass

    for xp in (
        '//*[@content-desc="Navigate up"]',
        '//*[contains(@content-desc,"Navigate up")]',
        '//*[@content-desc="Close tab"]',
        '//android.widget.ImageButton[contains(@content-desc,"Back")]',
        '//android.widget.ImageView[@content-desc="back"]',
    ):
        if _any_visible(xp) and not on_sign_in:
            return True

    # 误进隐私政策标题页则不算用户协议成功
    if _any_visible(
        '//*[contains(@text,"Beatbot") and contains(@text,"Privacy Policy") and string-length(@text) < 120]'
    ):
        return False

    if _any_visible('//*[contains(@text,"Last Modified")]'):
        return True
    if _any_visible(
        '//*[contains(@text,"Introduction") and string-length(@text) < 64]'
    ):
        return True
    for sub in ("Terms of Service", "Governing Law", "Acceptable Use"):
        if _any_visible(f'//*[contains(@text,"{sub}") and string-length(@text) < 800]'):
            return True

    if not on_sign_in:
        return True

    return False


def _try_click_short_user_agreement_link(driver) -> bool:
    phrase = USER_AGREEMENT_LINK_PHRASE
    xps = (
        f'//*[(@clickable="true" or @focusable="true") and @text="{phrase}"]',
        f'//*[@clickable="true" and (@content-desc="{phrase}" or contains(@content-desc,"{phrase}"))]',
        f'//android.view.View[@clickable="true" and contains(@text,"{phrase}") and string-length(@text) < 48]',
        f'//*[@clickable="true" and string-length(@text) < 48 and contains(@text,"{phrase}")]',
        f'//android.widget.Button[contains(@text,"{phrase}")]',
    )
    driver.implicitly_wait(0)
    try:
        for xp in xps:
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                try:
                    if not el.is_displayed():
                        continue
                    txt = (el.text or el.get_attribute("content-desc") or "").strip()
                    if phrase not in txt:
                        continue
                    if len(txt) >= len(DISCLAIMER_TEXT) * 0.92:
                        continue
                    el.click()
                    time.sleep(1.2)
                    if _user_agreement_page_indicators_hit(driver):
                        return True
                except Exception:
                    continue
        try:
            el = driver.find_element(
                AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().clickable(true).textContains("{phrase}")',
            )
            txt = (el.text or "").strip()
            if txt and len(txt) < len(DISCLAIMER_TEXT) * 0.88:
                el.click()
                time.sleep(1.2)
                if _user_agreement_page_indicators_hit(driver):
                    return True
        except Exception:
            pass
    finally:
        driver.implicitly_wait(5)
    return False


def _try_click_clickable_overlapping_disclaimer_user_agreement(driver, disclaimer_el) -> bool:
    drect = _rect_of(disclaimer_el)
    phrase = USER_AGREEMENT_LINK_PHRASE
    driver.implicitly_wait(0)
    try:
        for el in driver.find_elements(AppiumBy.XPATH, '//*[@clickable="true" or @focusable="true"]'):
            try:
                if not el.is_displayed():
                    continue
                txt = (el.text or el.get_attribute("content-desc") or "").strip()
                if phrase not in txt:
                    continue
                if txt == DISCLAIMER_TEXT or len(txt) >= len(DISCLAIMER_TEXT) * 0.92:
                    continue
                if not _rects_overlap(drect, _rect_of(el), pad=4):
                    continue
                el.click()
                time.sleep(1.2)
                if _user_agreement_page_indicators_hit(driver):
                    return True
            except Exception:
                continue
    finally:
        driver.implicitly_wait(5)
    return False


def _scroll_disclaimer_into_view(driver, el) -> None:
    """尽量把含 User Agreement 的声明滚进可视区（Compose ScrollView）。"""
    try:
        driver.find_element(
            AppiumBy.ANDROID_UIAUTOMATOR,
            'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().textContains("User Agreement"))',
        )
        time.sleep(0.45)
    except Exception:
        pass
    try:
        r = _rect_of(el)
        wh = driver.get_window_size()
        bottom = r["y"] + r["h"]
        if bottom > int(wh["height"] * 0.88):
            x = int(wh["width"] * 0.5)
            y0 = int(wh["height"] * 0.65)
            y1 = int(wh["height"] * 0.35)
            try:
                driver.swipe(x, y0, x, y1, 450)  # type: ignore[attr-defined]
            except Exception:
                _click_gesture_at(driver, x, y1)
            time.sleep(0.45)
    except Exception:
        pass


def _tap_user_agreement_on_sign_in_disclaimer(driver, timeout_s: int = 18) -> None:
    """
    触发「User Agreement」超链接（策略对齐 200011 Privacy Policy：短节点 → 重叠可点击 → 矩形内坐标扫描）。
    环境变量 ANDROID_USER_AGREEMENT_LINK_X_RATIO（0~1）可微调横向位置（句末建议 0.78~0.92）。
    """
    if _try_click_short_user_agreement_link(driver):
        return

    block_xps = (
        f'//android.widget.TextView[@text="{DISCLAIMER_TEXT}"]',
        '//android.widget.TextView[contains(@text,"Privacy Policy") and contains(@text,"User Agreement")]',
    )
    el = None
    for xp in block_xps:
        try:
            el = WebDriverWait(driver, timeout_s).until(EC.presence_of_element_located((AppiumBy.XPATH, xp)))
            break
        except Exception:
            continue
    if el is None:
        raise TimeoutException("未找到协议整句 TextView，无法点击 User Agreement 链接")

    _scroll_disclaimer_into_view(driver, el)
    try:
        el = driver.find_element(
            AppiumBy.XPATH,
            f'//android.widget.TextView[@text="{DISCLAIMER_TEXT}"]',
        )
    except Exception:
        pass

    if _try_click_clickable_overlapping_disclaimer_user_agreement(driver, el):
        return

    text = (el.text or "").strip() or DISCLAIMER_TEXT
    base_ratio = _x_ratio_for_phrase_in_line(text, USER_AGREEMENT_LINK_PHRASE)
    env_ratio = os.environ.get("ANDROID_USER_AGREEMENT_LINK_X_RATIO", "").strip()
    if env_ratio:
        base_ratio = float(env_ratio)

    loc = el.location
    size = el.size
    x0, y0, w, h = int(loc["x"]), int(loc["y"]), int(size["width"]), int(size["height"])
    wrapped = h > 52
    if wrapped:
        ry_list = (0.62, 0.72, 0.80, 0.88)
        rx_candidates = [0.16, 0.22, 0.28, 0.34, 0.40, 0.48, 0.56, 0.64, 0.72, 0.80, 0.88, 0.94]
    else:
        ry_list = (0.48, 0.56, 0.64)
        rx_candidates = []
        for delta in (0.0, -0.06, 0.06, -0.10, 0.10, -0.14, 0.14, -0.04, 0.04):
            rx_candidates.append(max(0.06, min(0.96, base_ratio + delta)))
        rx_candidates.extend([0.88, 0.91, 0.94, max(0.06, base_ratio - 0.20)])

    env_ry = os.environ.get("ANDROID_USER_AGREEMENT_LINK_Y_RATIO", "").strip()
    if env_ry:
        ry_list = (float(env_ry),) + tuple(ry for ry in ry_list if abs(ry - float(env_ry)) > 0.05)

    ty_mid = int(y0 + h * (0.78 if wrapped else 0.52))
    tx_end = int(x0 + w * (0.32 if wrapped else min(0.96, max(base_ratio, 0.80))))
    _click_gesture_at(driver, tx_end, ty_mid)
    time.sleep(0.15)
    _click_gesture_at(driver, tx_end, ty_mid)
    time.sleep(0.9)
    if _user_agreement_page_indicators_hit(driver):
        return

    deadline = time.time() + max(16.0, float(timeout_s))
    driver.implicitly_wait(0)
    try:
        while time.time() < deadline:
            for ry in ry_list:
                ty = int(y0 + h * ry)
                for rx in rx_candidates:
                    tx = int(x0 + w * rx)
                    _click_gesture_at(driver, tx, ty)
                    time.sleep(0.85)
                    if _user_agreement_page_indicators_hit(driver):
                        return
            time.sleep(0.35)
    finally:
        driver.implicitly_wait(5)

    raise TimeoutException(
        "多次点击仍未进入用户协议页。可设置 ANDROID_USER_AGREEMENT_LINK_X_RATIO（约 0.78~0.92 点句末 User Agreement；"
        "换行时试 0.20~0.40 点第二行左侧）。"
    )


def _wait_until_user_agreement_navigation_opened(driver, timeout_s: int = 22) -> None:
    deadline = time.time() + max(timeout_s, 8)
    driver.implicitly_wait(0)
    try:
        while time.time() < deadline:
            if _user_agreement_page_indicators_hit(driver):
                return
            time.sleep(0.45)
    finally:
        driver.implicitly_wait(5)
    raise TimeoutException(
        "未判定进入用户协议页。可设 ANDROID_USER_AGREEMENT_LINK_X_RATIO 微调点击；或补充 _user_agreement_page_indicators_hit。"
    )

LAST_MODIFIED_SNIPPET = "Last Modified"
LAST_MODIFIED_DETAIL = "July 17th, 2024"
INTRODUCTION = "Introduction"


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



def test_200014(setup_driver):
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

        # 步骤4: 点击 User Agreement 并断言
        current_step = "步骤4: 点击 User Agreement 并断言 Last Modified + Introduction"
        print(f"🔄 {current_step}")
        try:
            print("    🔄 _tap_user_agreement_on_sign_in_disclaimer（换行时优先点第二行左侧 User Agreement）")
            _tap_user_agreement_on_sign_in_disclaimer(driver, timeout_s=18)
            time.sleep(0.8)
            _wait_until_user_agreement_navigation_opened(driver, timeout_s=24)
            WebDriverWait(driver, 22).until(
                EC.presence_of_element_located((
                    AppiumBy.XPATH,
                    '//*[contains(@text,"Last Modified")]',
                ))
            )
            WebDriverWait(driver, 22).until(
                EC.presence_of_element_located((
                    AppiumBy.XPATH,
                    '//*[@text="Introduction" or contains(@text,"Introduction")]',
                ))
            )
            print(f"✅ {current_step} - 完成")
        except Exception as e:
            fail_reason = f"{current_step}失败: {str(e)}"
            print(f"❌ {fail_reason}")
            raise

        print("🎉 测试用例 200014 执行成功！")

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
        save_failure_screenshot(driver, "test_200014_failed")
        assert False, f"测试失败 - {fail_reason}"
    finally:
        # 无论成功失败都写入 platform 报告
        write_report(
            run_dir=RUN_DIR,
            run_label=RUN_LABEL,
            run_ts=RUN_TS,
            platform="android",
            case_id="200014",
            case_desc="200014 验证点击用户协议",
            result=case_result,
            fail_reason=fail_reason,
        )



# 本地直接运行：python 本文件.py 等价于 pytest -s 本文件
if __name__ == "__main__":
    pytest.main(["-s", __file__])
