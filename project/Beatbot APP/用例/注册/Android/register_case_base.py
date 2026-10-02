"""
Android 注册用例共用步骤（供 2注册 目录下各用例 import）。

与 200001 登录模板对齐的前置步骤：
  步骤1 重启 APP → 步骤2 登出/入口页 → 步骤3 点击 Sign Up
"""

from __future__ import annotations

import os
import time
from typing import Iterable, Optional, Sequence

from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from register_xpath_locators import *  # noqa: F403,F401

# 兼容旧生成脚本中的命名
XPATH_EMAIL_EDIT = XPATH_EMAIL  # noqa: F405
XPATH_NEXT_BTN = XPATH_NEXT  # noqa: F405


def step_restart_app(driver, pkg: Optional[str] = None) -> None:
    pkg = pkg or os.environ.get("ANDROID_APP_PACKAGE", "com.xingmai.tech")
    try:
        driver.terminate_app(pkg)
    except Exception:
        pass
    time.sleep(1.5)
    driver.activate_app(pkg)
    time.sleep(3.0)


def step_ensure_landing(driver, check_and_logout_fn, timeout_s: int = 30) -> None:
    is_logged_in = False
    driver.implicitly_wait(0)
    try:
        for xp in (XPATH_MORE, XPATH_MORE_ALT):
            for elem in driver.find_elements(AppiumBy.XPATH, xp):
                if elem.is_displayed():
                    is_logged_in = True
                    break
            if is_logged_in:
                break
    finally:
        driver.implicitly_wait(5)
    if is_logged_in:
        check_and_logout_fn(driver)
        time.sleep(2.0)
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_LANDING_ANY))
    )


def step_click_sign_up(driver, timeout_s: int = 18) -> None:
    last_err = None
    for xp in (XPATH_SIGN_UP_COMPOSE, XPATH_SIGN_UP, XPATH_SIGN_UP_FALLBACK):
        try:
            el = WebDriverWait(driver, timeout_s).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp)))
            el.click()
            time.sleep(1.5)
            return
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到/无法点击 Sign Up: {last_err}")


def step_assert_sign_up_entry(driver, timeout_s: int = 18):
    for xp in (XPATH_SIGN_UP_COMPOSE, XPATH_SIGN_UP, XPATH_SIGN_UP_FALLBACK):
        try:
            el = WebDriverWait(driver, timeout_s).until(EC.presence_of_element_located((AppiumBy.XPATH, xp)))
            if el.is_displayed():
                return el
        except Exception:
            continue
    raise TimeoutException("入口页未找到 Sign Up")


def step_assert_on_signup_page(driver, timeout_s: int = 18) -> None:
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_CHECKBOX))
    )


def step_assert_still_on_signup_page(driver, timeout_s: int = 10) -> None:
    el = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_CHECKBOX))
    )
    assert el.is_displayed(), "点击 Next 后未看到 checkbox，可能已跳转（不符合预期）"


def is_on_signup_registration_page(driver) -> bool:
    """是否已在注册主页面（有协议勾选框或 ScrollView 邮箱框）。"""
    try:
        for el in driver.find_elements(AppiumBy.XPATH, XPATH_CHECKBOX):
            if el.is_displayed():
                return True
    except Exception:
        pass
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if el.is_displayed():
                    return True
        except Exception:
            continue
    return False


def is_on_country_select_page(driver) -> bool:
    """是否仍在国家选择页（有搜索框且未见注册页主控件）。"""
    if is_on_signup_registration_page(driver):
        return False
    try:
        for el in driver.find_elements(AppiumBy.XPATH, XPATH_COUNTRY_SEARCH):
            if el.is_displayed():
                return True
    except Exception:
        pass
    return False


def step_ensure_back_on_signup_page(driver, timeout_s: float = 22.0) -> None:
    """选中国家后等待回到注册页；若仍停在国家列表则 back 或再点一次结果行。"""
    deadline = time.time() + timeout_s
    back_tried = False
    while time.time() < deadline:
        if is_on_signup_registration_page(driver):
            print("    ✅ 已回到注册主页面")
            return
        if is_on_country_select_page(driver):
            if not back_tried:
                print("    🔄 仍停在国家列表，尝试点击返回")
                try:
                    step_click_back(driver, timeout_s=6)
                except Exception:
                    try:
                        driver.back()
                    except Exception:
                        pass
                back_tried = True
                time.sleep(1.5)
                continue
            print("    🔄 仍停在国家列表，尝试点击首条搜索结果区域")
            try:
                step_tap_below_search_field(driver, offset_y=145)
            except Exception:
                pass
            time.sleep(1.5)
            continue
        time.sleep(0.5)
    raise TimeoutException("选中国家后未回到注册主页面（未找到 checkbox / 邮箱输入框）")


def dismiss_keyboard(driver) -> None:
    try:
        driver.hide_keyboard()
        time.sleep(0.4)
        return
    except Exception:
        pass
    try:
        size = driver.get_window_size()
        driver.tap([(int(size["width"] * 0.5), int(size["height"] * 0.12))])  # type: ignore[attr-defined]
        time.sleep(0.4)
    except Exception:
        pass


def step_type_email(driver, email: str, timeout_s: int = 10) -> None:
    if not is_on_signup_registration_page(driver):
        step_ensure_back_on_signup_page(driver, timeout_s=18.0)
    for xp in (XPATH_EMAIL_FOCUS, XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            WebDriverWait(driver, timeout_s).until(EC.presence_of_element_located((AppiumBy.XPATH, xp))).click()
            break
        except Exception:
            continue
    el = None
    for xp in (XPATH_EMAIL, XPATH_EMAIL_FALLBACK):
        try:
            el = WebDriverWait(driver, timeout_s).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            break
        except Exception:
            continue
    if el is None:
        raise TimeoutException("未找到注册页邮箱输入框")
    try:
        el.clear()
    except Exception:
        pass
    el.send_keys(email)
    time.sleep(0.4)


def step_get_email_text(driver) -> str:
    el = driver.find_element(AppiumBy.XPATH, XPATH_EMAIL)
    return (el.text or el.get_attribute("text") or "").strip()


def step_clear_email(driver, timeout_s: int = 8) -> None:
    el = WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_CLEAR_EMAIL))
    )
    el.click()
    time.sleep(0.5)


def step_toggle_checkbox(driver, timeout_s: int = 14) -> None:
    if not is_on_signup_registration_page(driver):
        step_ensure_back_on_signup_page(driver, timeout_s=18.0)
    WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_CHECKBOX))
    ).click()
    time.sleep(0.3)


def step_click_next(driver, timeout_s: int = 12) -> None:
    WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_NEXT_BTN))
    ).click()
    time.sleep(1.2)


def step_click_back(driver, timeout_s: int = 15) -> None:
    back = WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_BACK))
    )
    try:
        back.click()
    except Exception:
        r = back.rect
        driver.tap([(int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2))])  # type: ignore[attr-defined]
    time.sleep(1.5)


def step_assert_invalid_email_hint(driver, timeout_s: int = 12) -> None:
    el = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_INVALID_EMAIL_HINT))
    )
    assert el.is_displayed(), "邮箱错误提示存在但不可见"


def step_open_country_picker(driver, timeout_s: int = 15) -> None:
    WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_COUNTRY_ARROW))
    ).click()
    time.sleep(1.5)


def step_assert_country_select_page(driver, timeout_s: int = 12) -> None:
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_COUNTRY_SEARCH))
    )


def step_country_search(driver, keyword: str, timeout_s: int = 10) -> None:
    field = WebDriverWait(driver, timeout_s).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_COUNTRY_SEARCH))
    )
    field.click()
    time.sleep(0.4)
    try:
        field.clear()
    except Exception:
        pass
    field.send_keys(keyword)
    time.sleep(2.0)


# 国家选择页采集/首字母搜索（对齐 iOS 102188）
COUNTRY_NAME_IGNORED = frozenset({
    "Search",
    "search",
    "Cancel",
    "Clear",
    "Clear text",
    "Done",
    "Country/Region",
    "Country",
    "Region",
    "Sign Up",
    "Next",
    "Sign In",
})


def collect_visible_country_names(driver, limit: int = 80) -> list[str]:
    """采集国家选择页当前可见的国家名称（Android TextView / content-desc）。"""
    names: list[str] = []
    for xp in (
        '//*[@text and string-length(@text) >= 3]',
        '//*[@content-desc and string-length(@content-desc) >= 3]',
    ):
        try:
            for el in driver.find_elements(AppiumBy.XPATH, xp):
                if len(names) >= limit:
                    return names
                try:
                    if not el.is_displayed():
                        continue
                    name = (
                        (el.text or "").strip()
                        or (el.get_attribute("text") or "").strip()
                        or (el.get_attribute("content-desc") or "").strip()
                    )
                    if not name or name in COUNTRY_NAME_IGNORED:
                        continue
                    if len(name) < 3 or len(name) > 50:
                        continue
                    if name.lower() in ("search", "country/region"):
                        continue
                    if name not in names:
                        names.append(name)
                except Exception:
                    continue
        except Exception:
            continue
    return names


def pick_fallback_search_keyword(country_names: Sequence[str]) -> tuple[Optional[str], Optional[str]]:
    """从默认列表中选一个可稳定命中的首字母（对齐 iOS _pick_fallback_search_keyword）。"""
    for country_name in country_names:
        for ch in country_name.strip():
            if ch.isalpha():
                return ch.upper(), country_name
    return None, None


def step_assert_country_first_letter_search(
    driver,
    search_keyword: str = "Z",
    timeout_s: float = 14.0,
) -> tuple[str, list[str]]:
    """
    对齐 iOS 102188：输入首字母后，断言可见国家名均包含该字母（模糊搜索）。
    不要求点击具体国家；若无结果则改用默认列表中某国首字母重试。
    """
    step_assert_country_select_page(driver, timeout_s=int(timeout_s))
    default_before = collect_visible_country_names(driver)
    if default_before:
        print(f"    📝 国家页默认可见国家（前10）: {default_before[:10]}")

    kw = search_keyword.strip().upper()[:1] or "Z"
    step_country_search(driver, kw)
    time.sleep(1.5)

    found = [c for c in collect_visible_country_names(driver) if kw in c.upper()]

    if not found:
        fb_kw, matched = pick_fallback_search_keyword(default_before)
        if fb_kw and fb_kw != kw:
            print(
                f"    ℹ️ 关键字 {kw} 未命中，改用可见国家「{matched}」的首字母 {fb_kw} 继续验证"
            )
            kw = fb_kw
            step_country_search(driver, kw)
            time.sleep(1.5)
            found = [c for c in collect_visible_country_names(driver) if kw in c.upper()]

    print(f"    📝 搜索关键词: {kw}")
    print(f"    📝 找到的国家数量: {len(found)}")
    if found:
        print(f"    📝 找到的国家（前20）: {found[:20]}")

    assert found, f"输入「{kw}」后应显示匹配国家，但未找到任何匹配项"
    for country in found:
        assert kw in country.upper(), (
            f"国家「{country}」不包含字母「{kw}」，不符合模糊搜索要求"
        )
    return kw, found


def step_click_country_in_list(
    driver,
    target_texts: Sequence[str],
    timeout_s: float = 16.0,
) -> str:
    """
    在国家选择页列表中点击目标国家（收起键盘后扫描下方列表）。
    支持 text / content-desc、精确与 contains、不区分大小写；失败时坐标点击首条结果区域。
    """
    targets = [t for t in target_texts if t]
    deadline = time.time() + timeout_s
    driver.implicitly_wait(0)
    try:
        while time.time() < deadline:
            for t in targets:
                for xp in (
                    f'//*[@text="{t}"]',
                    f'//*[contains(@text,"{t}")]',
                    f'//*[@content-desc="{t}"]',
                    f'//*[contains(@content-desc,"{t}")]',
                ):
                    try:
                        for el in driver.find_elements(AppiumBy.XPATH, xp):
                            if not el.is_displayed():
                                continue
                            blob = (
                                (el.text or "")
                                or (el.get_attribute("text") or "")
                                or (el.get_attribute("content-desc") or "")
                            ).strip()
                            if blob in COUNTRY_NAME_IGNORED:
                                continue
                            el.click()
                            time.sleep(1.5)
                            if is_on_signup_registration_page(driver):
                                return t
                    except Exception:
                        continue

            for el in driver.find_elements(
                AppiumBy.XPATH,
                '//*[@text or @content-desc]',
            ):
                try:
                    if not el.is_displayed():
                        continue
                    blob = (
                        (el.text or "")
                        or (el.get_attribute("text") or "")
                        or (el.get_attribute("content-desc") or "")
                    ).strip()
                    if not blob or blob in COUNTRY_NAME_IGNORED:
                        continue
                    if len(blob) < 2 or len(blob) > 50:
                        continue
                    blob_lower = blob.lower()
                    for t in targets:
                        if t.lower() in blob_lower or blob_lower in t.lower():
                            el.click()
                            time.sleep(1.5)
                            if is_on_signup_registration_page(driver):
                                return blob
                except Exception:
                    continue
            time.sleep(0.4)
    finally:
        driver.implicitly_wait(5)

    offsets = (120, 145, 170, 200)
    last_err: Optional[Exception] = None
    for off in offsets:
        try:
            step_tap_below_search_field(driver, offset_y=off)
            time.sleep(1.8)
            if is_on_signup_registration_page(driver):
                return f"coordinate_tap@{off}"
            for t in targets:
                for el in driver.find_elements(AppiumBy.XPATH, f'//*[contains(@text,"{t}")]'):
                    if el.is_displayed():
                        el.click()
                        time.sleep(1.5)
                        if is_on_signup_registration_page(driver):
                            return t
        except Exception as e:
            last_err = e
    raise TimeoutException(f"未找到可点击国家 {targets}，坐标兜底也失败: {last_err}")


def step_select_country_from_search(
    driver,
    search_keyword: str = "china",
    target_texts: Optional[Sequence[str]] = None,
    open_picker: bool = True,
) -> str:
    """
    对齐 iOS 102195 / 用户操作流程：打开国家列表 → 搜索框输入关键词 → 收起键盘 → 点击下方匹配国家。
    """
    if target_texts is None:
        if search_keyword.lower() in ("china", "中国"):
            target_texts = ("China", "中国", "china")
        else:
            target_texts = (search_keyword,)

    if open_picker:
        step_open_country_picker(driver)
        step_assert_country_select_page(driver)

    step_country_search(driver, search_keyword)
    print(f"    📝 已在国家搜索框输入: {search_keyword}")
    dismiss_keyboard(driver)
    time.sleep(0.8)

    visible = collect_visible_country_names(driver)
    if visible:
        print(f"    📝 收起键盘后可见国家（前15）: {visible[:15]}")

    clicked = step_click_country_in_list(driver, target_texts)
    print(f"    ✅ 已点击国家项，命中: {clicked}")
    step_ensure_back_on_signup_page(driver, timeout_s=22.0)
    time.sleep(0.8)
    return clicked


def step_click_text_if_visible(driver, texts: Sequence[str], timeout_s: int = 10) -> str:
    """通用可见文本点击（非国家列表场景仍可使用）。"""
    return step_click_country_in_list(driver, texts, timeout_s=timeout_s)


def step_tap_below_search_field(driver, offset_y: int = 140) -> None:
    field = driver.find_element(AppiumBy.XPATH, XPATH_COUNTRY_SEARCH)
    loc = field.location
    sz = field.size
    x = int(loc["x"] + sz["width"] * 0.5)
    y = int(loc["y"] + sz["height"] + offset_y)
    driver.tap([(x, y)])  # type: ignore[attr-defined]
    time.sleep(1.2)


def step_assert_country_has_default(driver) -> None:
    arrow = WebDriverWait(driver, 18).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_COUNTRY_ARROW))
    )
    assert arrow.is_displayed(), "国家下拉箭头存在但不可见"
    visible = []
    for t in driver.find_elements(AppiumBy.XPATH, '//*[@text and string-length(@text) > 0]'):
        try:
            if t.is_displayed() and (t.text or "").strip():
                visible.append((t.text or "").strip())
        except Exception:
            continue
    assert visible, "页面无可见文本，无法确认国家默认值"


def step_assert_on_password_page(driver, timeout_s: int = 18) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        edits = [e for e in driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD) if e.is_displayed()]
        if len(edits) >= 2:
            return
        time.sleep(0.4)
    raise TimeoutException("未进入设置密码页（需要至少 2 个 EditText）")


def step_type_passwords(driver, pwd: str, timeout_s: int = 18) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        edits = []
        for e in driver.find_elements(AppiumBy.XPATH, XPATH_PASSWORD):
            try:
                if e.is_displayed():
                    edits.append(e)
            except Exception:
                continue
        if len(edits) >= 2:
            for idx in (0, 1):
                try:
                    edits[idx].click()
                    edits[idx].clear()
                except Exception:
                    pass
                edits[idx].send_keys(pwd)
                time.sleep(0.3)
                dismiss_keyboard(driver)
            return
        time.sleep(0.4)
    raise TimeoutException("未找到密码/确认密码输入框")


def step_assert_password_next_stays(driver, timeout_s: int = 6) -> None:
    """点击密码页 Next 后仍应停留在密码页（按钮不可跳转场景）。"""
    step_click_next(driver, timeout_s=timeout_s)
    step_assert_on_password_page(driver, timeout_s=8)


def step_assert_password_next_advances_or_stays(
    driver, should_advance: bool, timeout_s: int = 8
) -> None:
    step_click_next(driver)
    if should_advance:
        try:
            step_assert_on_password_page(driver, timeout_s=3)
            raise AssertionError("密码符合规则时 Next 应离开密码页，但仍停留在密码页")
        except TimeoutException:
            pass
    else:
        step_assert_on_password_page(driver, timeout_s=timeout_s)


def step_flow_to_password_page(driver, email: str, pwd: str = "Csx150128") -> None:
    step_type_email(driver, email)
    dismiss_keyboard(driver)
    step_toggle_checkbox(driver)
    step_click_next(driver)
    step_assert_on_password_page(driver)


def step_flow_to_username_page(driver, email: str, pwd: str = "Csx150128") -> None:
    step_flow_to_password_page(driver, email, pwd)
    step_type_passwords(driver, pwd)
    dismiss_keyboard(driver)
    step_click_next(driver)


def step_type_username(driver, username: str, timeout_s: int = 18) -> None:
    el = WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((AppiumBy.XPATH, XPATH_PASSWORD))
    )
    try:
        el.click()
        el.clear()
    except Exception:
        pass
    el.send_keys(username)
    time.sleep(0.4)
    dismiss_keyboard(driver)


def step_click_submit(driver, timeout_s: int = 18) -> None:
    for xp in (
        XPATH_SUBMIT,
        '//android.widget.Button[@text="Submit"]',
        '//android.widget.TextView[@text="Submit"]',
    ):
        try:
            WebDriverWait(driver, 4).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp))).click()
            time.sleep(1.5)
            return
        except Exception:
            continue
    btns = [b for b in driver.find_elements(AppiumBy.XPATH, XPATH_NEXT) if b.is_displayed()]
    if not btns:
        raise TimeoutException("未找到 Submit 按钮")
    btns[-1].click()
    time.sleep(1.5)


def step_assert_not_logged_in_main(driver) -> None:
    try:
        more = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((AppiumBy.XPATH, XPATH_MORE_ALT))
        )
        if more.is_displayed():
            raise AssertionError("不应进入主界面（More 可见）")
    except TimeoutException:
        pass


def step_assert_text_visible(driver, texts: Iterable[str], timeout_s: int = 10) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for t in texts:
            for xp in (f'//*[@text="{t}"]', f'//*[contains(@text,"{t}")]'):
                try:
                    el = driver.find_element(AppiumBy.XPATH, xp)
                    if el.is_displayed():
                        return
                except Exception:
                    continue
        time.sleep(0.4)
    raise TimeoutException(f"未找到文案: {list(texts)}")


def step_click_password_eye(driver, index: int = 1) -> None:
    xps = [
        f'(//android.widget.ImageView[@content-desc="lock"])[{index}]',
        '//android.widget.ImageView[@content-desc="lock"]',
    ]
    for xp in xps:
        try:
            WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            ).click()
            time.sleep(0.4)
            return
        except Exception:
            continue
    raise TimeoutException("未找到密码明文/隐藏切换按钮 lock")


def step_click_clear_password(driver, index: int = 1) -> None:
    xp = f'(//android.widget.ImageView[@content-desc="clear"])[{index}]'
    WebDriverWait(driver, 8).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp))).click()
    time.sleep(0.4)
