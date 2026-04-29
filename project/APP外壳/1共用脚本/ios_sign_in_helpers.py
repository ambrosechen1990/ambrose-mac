# -*- coding: utf-8 -*-
"""
iOS Sign in：解析邮箱/密码可输入元素（多策略，避免 Other 容器不满足 clickable 或层级不一致）。
"""
from __future__ import annotations

import time
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ios_sign_in_locators import (
    IOS_SIGN_IN_EMAIL_CLEAR_BUTTON_XPATH,
    IOS_SIGN_IN_EMAIL_CONTAINER_XPATH,
    IOS_SIGN_IN_EMAIL_TEXT_FIELD_XPATH,
    IOS_SIGN_IN_PASSWORD_CLEAR_BUTTON_XPATH,
    IOS_SIGN_IN_PASSWORD_CONTAINER_XPATH,
    IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH,
    IOS_SIGN_IN_PASSWORD_TEXT_FIELD_XPATH,
)


def _tap_center(driver: WebDriver, el: WebElement) -> None:
    """容器类 Other 有时不可点：先试 click，再试 move_to_element 点击。"""
    try:
        el.click()
        return
    except Exception:
        pass
    try:
        from selenium.webdriver.common.action_chains import ActionChains

        ActionChains(driver).move_to_element(el).click().perform()
    except Exception:
        pass


def _visible_elements(driver: WebDriver, xpath: str) -> list[WebElement]:
    visible: list[WebElement] = []
    for el in driver.find_elements(AppiumBy.XPATH, xpath):
        try:
            if el.is_displayed():
                visible.append(el)
        except Exception:
            continue
    return visible


def _first_visible(driver: WebDriver, xpaths: list[str]) -> WebElement | None:
    for xpath in xpaths:
        visible = _visible_elements(driver, xpath)
        if visible:
            return visible[0]
    return None


def _read_element_text(el: WebElement) -> tuple[str | None, str | None, str | None, str | None]:
    try:
        el_type = el.get_attribute("type")
    except Exception:
        el_type = None
    try:
        value = el.get_attribute("value")
    except Exception:
        value = None
    try:
        name = el.get_attribute("name")
    except Exception:
        name = None
    try:
        text = el.text
    except Exception:
        text = None
    return el_type, value, name, text


def resolve_sign_in_email_input(driver: WebDriver, timeout: float = 18.0) -> WebElement:
    """
    1) 容器下 TextField（若存在）
    2) 点「Email」文案后 Predicate 找 TextField
    3) 容器 Other：presence + 中心 tap，再试 TextField / Predicate
    """
    w = WebDriverWait(driver, timeout)

    def _by_predicate() -> WebElement:
        return WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
        )

    # 1) 子 TextField
    try:
        el = w.until(EC.presence_of_element_located((AppiumBy.XPATH, IOS_SIGN_IN_EMAIL_TEXT_FIELD_XPATH)))
        if el.is_displayed():
            return el
    except TimeoutException:
        pass

    # 2) 经典：点 Email 标签再 Predicate
    try:
        lbl = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Email"]'))
        )
        lbl.click()
        time.sleep(0.45)
        return _by_predicate()
    except TimeoutException:
        pass

    # 3) Inspector 容器：不要求 clickable，点中心后再找输入
    try:
        box = w.until(EC.presence_of_element_located((AppiumBy.XPATH, IOS_SIGN_IN_EMAIL_CONTAINER_XPATH)))
        _tap_center(driver, box)
        time.sleep(0.45)
    except TimeoutException:
        pass

    try:
        el = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.XPATH, IOS_SIGN_IN_EMAIL_TEXT_FIELD_XPATH))
        )
        if el.is_displayed():
            return el
    except TimeoutException:
        pass

    return _by_predicate()


def resolve_sign_in_password_input(driver: WebDriver, timeout: float = 18.0) -> WebElement:
    """密码：子 SecureTextField → 点 Password 文案 → Predicate；最后容器 tap + 再找子节点。"""
    w = WebDriverWait(driver, timeout)

    def _by_predicate() -> WebElement:
        return WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeSecureTextField"'))
        )

    try:
        el = w.until(EC.presence_of_element_located((AppiumBy.XPATH, IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH)))
        if el.is_displayed():
            return el
    except TimeoutException:
        pass

    try:
        lbl = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Password"]'))
        )
        lbl.click()
        time.sleep(0.45)
        return _by_predicate()
    except TimeoutException:
        pass

    try:
        box = w.until(EC.presence_of_element_located((AppiumBy.XPATH, IOS_SIGN_IN_PASSWORD_CONTAINER_XPATH)))
        _tap_center(driver, box)
        time.sleep(0.45)
    except TimeoutException:
        pass

    try:
        el = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((AppiumBy.XPATH, IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH))
        )
        if el.is_displayed():
            return el
    except TimeoutException:
        pass

    return _by_predicate()


def resolve_sign_in_clear_button(driver: WebDriver, target: str, timeout: float = 8.0) -> WebElement:
    """
    解析登录页输入框右侧删除按钮。

    说明：
    - Inspector 中邮箱/密码删除按钮可分别用 [1] / [2] 定位
    - 但真机运行时，空输入框右侧按钮可能根本不出现在树里，此时页面上只剩 1 个 login delete
    - 因此这里先走精确 XPath，再回退到当前可见的 login delete 按钮
    """
    if target not in {"email", "password"}:
        raise ValueError(f"target 必须是 email 或 password，实际: {target}")

    preferred_xpath = (
        IOS_SIGN_IN_EMAIL_CLEAR_BUTTON_XPATH
        if target == "email"
        else IOS_SIGN_IN_PASSWORD_CLEAR_BUTTON_XPATH
    )
    pick_last = target == "password"
    all_delete_xpath = '//XCUIElementTypeButton[@name="login delete"]'

    try:
        el = WebDriverWait(driver, min(timeout, 2.5)).until(
            EC.presence_of_element_located((AppiumBy.XPATH, preferred_xpath))
        )
        if el.is_displayed():
            return el
    except TimeoutException:
        pass
    except Exception:
        pass

    visible = _visible_elements(driver, all_delete_xpath)
    if visible:
        return visible[-1] if pick_last else visible[0]

    if target == "email":
        _tap_center(driver, resolve_sign_in_email_input(driver, timeout=max(3.0, timeout)))
    else:
        _tap_center(driver, resolve_sign_in_password_input(driver, timeout=max(3.0, timeout)))
    time.sleep(0.35)

    try:
        el = WebDriverWait(driver, min(timeout, 2.5)).until(
            EC.presence_of_element_located((AppiumBy.XPATH, preferred_xpath))
        )
        if el.is_displayed():
            return el
    except TimeoutException:
        pass
    except Exception:
        pass

    visible = _visible_elements(driver, all_delete_xpath)
    if visible:
        return visible[-1] if pick_last else visible[0]

    raise TimeoutException(f"未找到 {target} 输入框右侧的 login delete 按钮")


def wait_sign_in_field_cleared(driver: WebDriver, target: str, timeout: float = 6.0) -> str:
    """
    等待登录页输入框进入“已清空”状态。

    iOS 真机上点击删除后，原有 TextField / SecureTextField 可能直接从树里消失，
    页面回到占位态，因此不能强依赖旧输入节点仍存在。
    """
    if target == "email":
        field_xpaths = [IOS_SIGN_IN_EMAIL_TEXT_FIELD_XPATH]
        clear_xpath = IOS_SIGN_IN_EMAIL_CLEAR_BUTTON_XPATH
        placeholder_name = "Email"
    elif target == "password":
        field_xpaths = [
            IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH,
            IOS_SIGN_IN_PASSWORD_TEXT_FIELD_XPATH,
        ]
        clear_xpath = IOS_SIGN_IN_PASSWORD_CLEAR_BUTTON_XPATH
        placeholder_name = "Password"
    else:
        raise ValueError(f"target 必须是 email 或 password，实际: {target}")

    placeholder_xpath = f'//XCUIElementTypeStaticText[@name="{placeholder_name}"]'
    generic_delete_xpath = '//XCUIElementTypeButton[@name="login delete"]'
    deadline = time.monotonic() + timeout
    last_state = "未知"

    while time.monotonic() < deadline:
        field = _first_visible(driver, field_xpaths)
        if field is not None:
            try:
                value = field.get_attribute("value")
            except Exception:
                value = None
            if value in ("", None, placeholder_name):
                return f"value={value!r}"
            last_state = f"value={value!r}"
        else:
            if _visible_elements(driver, placeholder_xpath):
                return f"placeholder={placeholder_name}"

            target_delete = _visible_elements(driver, clear_xpath)
            any_delete = _visible_elements(driver, generic_delete_xpath)
            if not target_delete and not any_delete:
                return "delete_button_hidden"
            last_state = "field_missing_but_delete_still_visible"

        time.sleep(0.35)

    raise TimeoutException(f"{target} 输入框未清空，最后状态: {last_state}")


def wait_sign_in_password_visible(driver: WebDriver, expected_password: str, timeout: float = 8.0) -> str:
    """
    等待密码切换为明文可见。

    真机切换后，密码输入框不一定还挂在原容器 XPath 下，因此需要同时检查：
    - 容器内 TextField
    - 当前页面全部可见 TextField
    """
    deadline = time.monotonic() + timeout
    last_state = "未找到明文密码输入框"

    while time.monotonic() < deadline:
        candidates = _visible_elements(driver, IOS_SIGN_IN_PASSWORD_TEXT_FIELD_XPATH)
        candidates.extend(_visible_elements(driver, "//XCUIElementTypeTextField"))

        seen = set()
        for el in candidates:
            el_id = id(el)
            if el_id in seen:
                continue
            seen.add(el_id)

            el_type, value, name, text = _read_element_text(el)
            normalized = [x for x in (value, name, text) if x]
            if el_type == "XCUIElementTypeTextField" and expected_password in normalized:
                return f"type={el_type}, value={value!r}"

            if el_type == "XCUIElementTypeTextField" and value not in ("", None, "Email", "Password"):
                last_state = f"type={el_type}, value={value!r}"

        time.sleep(0.35)

    raise TimeoutException(f"密码未切换为明文显示，最后状态: {last_state}")


def wait_sign_in_password_hidden(driver: WebDriver, plain_password: str, timeout: float = 8.0) -> str:
    """
    等待密码切换回隐藏状态。

    优先检查 SecureTextField；如果层级变化，则退回通用解析逻辑。
    """
    deadline = time.monotonic() + timeout
    last_state = "未找到隐藏态密码输入框"

    while time.monotonic() < deadline:
        candidates = _visible_elements(driver, IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH)
        candidates.extend(_visible_elements(driver, "//XCUIElementTypeSecureTextField"))

        seen = set()
        for el in candidates:
            el_id = id(el)
            if el_id in seen:
                continue
            seen.add(el_id)

            el_type, value, name, text = _read_element_text(el)
            if el_type == "XCUIElementTypeSecureTextField" and value != plain_password:
                return f"type={el_type}, value={value!r}"
            last_state = f"type={el_type}, value={value!r}, name={name!r}, text={text!r}"

        try:
            el = resolve_sign_in_password_input(driver, timeout=2.0)
            el_type, value, name, text = _read_element_text(el)
            if el_type == "XCUIElementTypeSecureTextField" and value != plain_password:
                return f"type={el_type}, value={value!r}"
            last_state = f"type={el_type}, value={value!r}, name={name!r}, text={text!r}"
        except Exception:
            pass

        time.sleep(0.35)

    raise TimeoutException(f"密码未切换回隐藏状态，最后状态: {last_state}")
