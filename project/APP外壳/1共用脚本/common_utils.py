"""
iOS 共用工具聚合模块。

主要用途：
- 统一导出邮箱、登出、截图、报告等常用能力
- 提供稳定的 Sign Up 页面判断方法
- 供 iOS 注册/登录脚本直接导入复用
"""

from email_utils import get_next_email, get_next_unsupported_email, get_simple_email
from logout_ios import check_and_logout
from screenshot_utils import ScreenshotContext, safe_execute, save_failure_screenshot
from report_utils import init_report, bind_logger_to_print, write_report
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

__all__ = [
    "get_next_email",
    "get_next_unsupported_email",
    "get_simple_email",
    "check_and_logout",
    "ScreenshotContext",
    "safe_execute",
    "save_failure_screenshot",
    "init_report",
    "bind_logger_to_print",
    "write_report",
    "assert_on_signup_page",
    "resolve_country_search_field",
    "assert_on_country_select_page",
    "click_country_option_by_visible_text",
]


def assert_on_signup_page(driver, timeout: int = 10):
    """
    稳定判断当前是否处于 Sign Up 页面。

    旧脚本大量依赖整句隐私协议文案做定位，但线上页面已改为链接样式，
    且控件类型可能在 Other/TextView 间变化，容易误判失败。
    这里改为：
    1. 必须先看到 Sign Up 标题
    2. 再确认注册页关键控件任一存在（协议勾选框 / 邮箱输入框 / Next）
    """
    sign_up_text = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]'))
    )
    assert sign_up_text.is_displayed(), "Sign Up 文本存在但不可见"

    markers = [
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check selected"]'),
        (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'),
        (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]'),
    ]

    for by, locator in markers:
        try:
            elem = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((by, locator))
            )
            if elem and elem.is_displayed():
                return sign_up_text
        except Exception:
            continue

    raise AssertionError("未检测到注册页关键元素（协议勾选框/邮箱输入框/Next），可能未进入 Sign Up 页面")


def resolve_country_search_field(driver, timeout: int = 10, clickable: bool = False):
    """
    定位国家选择页搜索框。

    真机上搜索框的 name/value 可能不是固定的 "Search"，
    也可能表现为 SearchField/TextField，因此这里使用多策略兜底。
    """
    wait = WebDriverWait(driver, timeout)
    condition = EC.element_to_be_clickable if clickable else EC.presence_of_element_located
    selectors = [
        (AppiumBy.XPATH, '//XCUIElementTypeSearchField[@name="Search"]'),
        (AppiumBy.XPATH, '//XCUIElementTypeSearchField'),
        (AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeSearchField"'),
        (AppiumBy.XPATH, '//XCUIElementTypeTextField[contains(@value, "Search")]'),
        (AppiumBy.XPATH, '//XCUIElementTypeTextField[contains(@name, "Search")]'),
    ]

    for by, locator in selectors:
        try:
            elem = wait.until(condition((by, locator)))
            if elem and elem.is_displayed():
                return elem
        except Exception:
            continue

    raise AssertionError("未找到国家选择页搜索框")


def assert_on_country_select_page(driver, timeout: int = 10):
    """确认已进入国家选择页面，并返回搜索框元素。"""
    return resolve_country_search_field(driver, timeout=timeout, clickable=False)


def click_country_option_by_visible_text(driver, target_texts, timeout: int = 10):
    """
    通过页面可见文本定位并点击国家选项。

    适用于真机上国家项可能暴露为 StaticText / Button / Cell 的场景：
    - 先尝试直接点击与目标文案完全匹配的 StaticText / Button
    - 再尝试点击包含该文本的 Cell / Other / Button 容器
    - 最后回退到 contains 匹配
    """
    if isinstance(target_texts, str):
        target_texts = [target_texts]

    exact_selectors = []
    contains_selectors = []
    for text in target_texts:
        exact_selectors.extend([
            f'//XCUIElementTypeStaticText[@name="{text}"]',
            f'//XCUIElementTypeButton[@name="{text}"]',
            f'//XCUIElementTypeCell[@name="{text}"]',
            f'//XCUIElementTypeOther[@name="{text}"]',
            f'//XCUIElementTypeCell[.//XCUIElementTypeStaticText[@name="{text}"]]',
            f'//XCUIElementTypeOther[.//XCUIElementTypeStaticText[@name="{text}"]]',
            f'//XCUIElementTypeButton[.//XCUIElementTypeStaticText[@name="{text}"]]',
        ])
        contains_selectors.extend([
            f'//XCUIElementTypeStaticText[contains(@name, "{text}")]',
            f'//XCUIElementTypeButton[contains(@name, "{text}")]',
            f'//XCUIElementTypeCell[contains(@name, "{text}")]',
            f'//XCUIElementTypeOther[contains(@name, "{text}")]',
            f'//XCUIElementTypeCell[.//XCUIElementTypeStaticText[contains(@name, "{text}")]]',
            f'//XCUIElementTypeOther[.//XCUIElementTypeStaticText[contains(@name, "{text}")]]',
            f'//XCUIElementTypeButton[.//XCUIElementTypeStaticText[contains(@name, "{text}")]]',
        ])

    selectors = exact_selectors + contains_selectors
    wait = WebDriverWait(driver, timeout)
    seen_names = []

    for selector in selectors:
        try:
            elements = driver.find_elements(AppiumBy.XPATH, selector)
            for elem in elements:
                try:
                    if not elem.is_displayed():
                        continue
                    elem_name = elem.get_attribute("name") or ""
                    if elem_name and elem_name not in seen_names:
                        seen_names.append(elem_name)
                    try:
                        wait.until(lambda _driver: elem.is_enabled() or True)
                    except Exception:
                        pass
                    elem.click()
                    return elem_name or selector
                except Exception:
                    continue
        except Exception:
            continue

    # 最后兜底：爬取页面上所有可见文本，便于匹配真实展示内容
    fallback_xpaths = [
        '//XCUIElementTypeStaticText',
        '//XCUIElementTypeButton',
        '//XCUIElementTypeCell',
        '//XCUIElementTypeOther',
    ]
    for fallback_xpath in fallback_xpaths:
        elements = driver.find_elements(AppiumBy.XPATH, fallback_xpath)
        for elem in elements:
            try:
                if not elem.is_displayed():
                    continue
                text = (elem.get_attribute("name") or elem.get_attribute("label") or "").strip()
                if text:
                    seen_names.append(text)
                if any(target in text for target in target_texts):
                    try:
                        elem.click()
                        return text
                    except Exception:
                        continue
            except Exception:
                continue

    unique_names = []
    for name in seen_names:
        if name and name not in unique_names:
            unique_names.append(name)
    raise AssertionError(f"未找到可点击的目标国家文本。当前可见文本示例: {unique_names[:12]}")

