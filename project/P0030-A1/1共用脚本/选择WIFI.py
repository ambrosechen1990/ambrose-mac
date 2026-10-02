#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WiFi 选择模块

3功能：
- 从进入 setup_wifi 页面后，到清除密码、输入密码、点击 next 的完整流程
- 支持 iOS 和 Android 平台
- 包含新老系统选择的代码（iOS 高版本需要处理 Apps 页面）
"""

import os
import time
from typing import Callable, Optional, Any
from pathlib import Path

try:
    from appium import webdriver
    from appium.webdriver.common.appiumby import AppiumBy
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    print("⚠️ Appium 库未安装，请运行 pip install Appium-Python-Client", flush=True)


# 默认日志函数
def _log_default(msg: str) -> None:
    print(msg, flush=True)


# 默认截图函数 (空实现)
def _screenshot_default(driver: Any, prefix: str) -> None:
    print(f"📸 [默认截图] {prefix}")


# ==================== iOS WiFi 设置 ====================

# 高系统点击「切换 WiFi」后，系统设置里「应用列表」页的导航标题：
# 常见为 "Apps"，部分 iOS/语言环境下为单数 "App"（日志里 nav=['App']）。
_IOS_SETTINGS_APPS_NAV_NAMES = frozenset({"Apps", "App", "应用"})


def _ios_nav_bar_names(driver: Any) -> list[str]:
    """收集当前界面 NavigationBar 的 name，便于日志与辅助判断。"""
    names: list[str] = []
    try:
        for nav in driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar"):
            try:
                n = nav.get_attribute("name") or ""
                if n.strip():
                    names.append(n.strip())
            except Exception:
                pass
    except Exception:
        pass
    return names


def _detect_current_page_ios(driver: Any) -> str:
    """
    检测 iOS 当前页面类型（点击「切换 WiFi」之后调用）。

    业务约定：
    - **低系统**：多直接进入系统「无线局域网 / Wi‑Fi」列表。
    - **高系统**：多先进入系统设置里的 **Apps / App / 应用** 列表页，需左上角返回 → 设置主页 → 再点 **WLAN / Wi‑Fi** 或 **com.apple.settings.wifi** 进入列表。

    注意：**不能**把 NavigationBar name=\"Settings\" 当作 WiFi 列表 —— 设置主页也是 Settings，会误判导致不走「返回 + WLAN」分支。

    返回: "wifi_list" | "settings_apps" | "wifi_password" | "unknown"
    """
    # ----- 1) 高系统：设置 - Apps / 应用 列表（须优先于 WiFi；且勿用「App Store」等单行误判设置主页）-----
    try:
        for nav in driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar"):
            try:
                nav_name = nav.get_attribute("name") or ""
                if nav_name in _IOS_SETTINGS_APPS_NAV_NAMES:
                    return "settings_apps"
            except Exception:
                pass
    except Exception:
        pass

    try:
        apps_title = driver.find_element(
            AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Apps"]'
        )
        if apps_title.is_displayed():
            navs = _ios_nav_bar_names(driver)
            if not any(
                "Wi-Fi" in n or "WLAN" in n or "无线局域网" in n for n in navs
            ):
                return "settings_apps"
    except Exception:
        pass

    try:
        app_title = driver.find_element(
            AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="App"]'
        )
        if app_title.is_displayed():
            navs = _ios_nav_bar_names(driver)
            if any(n in _IOS_SETTINGS_APPS_NAV_NAMES for n in navs):
                if not any(
                    "Wi-Fi" in n or "WLAN" in n or "无线局域网" in n for n in navs
                ):
                    return "settings_apps"
    except Exception:
        pass

    for xp in (
        '//XCUIElementTypeButton[@name="Apps"]',
        '//XCUIElementTypeStaticText[@name="Default Apps"]',
    ):
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                navs = _ios_nav_bar_names(driver)
                if any(n in _IOS_SETTINGS_APPS_NAV_NAMES for n in navs):
                    return "settings_apps"
        except Exception:
            continue

    # ----- 2) 系统 WiFi 列表页（严格条件，避免等于「设置」主页）-----
    wifi_nav_xpaths = [
        '//XCUIElementTypeNavigationBar[@name="无线局域网"]',
        '//XCUIElementTypeNavigationBar[contains(@name,"WLAN")]',
        '//XCUIElementTypeNavigationBar[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeNavigationBar[contains(@name,"WiFi")]',
    ]
    for xp in wifi_nav_xpaths:
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                return "wifi_list"
        except Exception:
            continue

    try:
        for nav in driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar"):
            try:
                nav_name = nav.get_attribute("name") or ""
                if "无线局域网" in nav_name or "WLAN" in nav_name:
                    return "wifi_list"
                if "Wi-Fi" in nav_name or "WiFi" in nav_name:
                    return "wifi_list"
            except Exception:
                pass
    except Exception:
        pass

    # 仅用语义上「已在选网列表」的文案，避免把「设置」主页上的 WLAN 行误判为列表页
    wifi_list_secondary_hints = [
        '//XCUIElementTypeStaticText[contains(@name,"选取网络")]',
        '//XCUIElementTypeStaticText[contains(@name,"我的网络")]',
        '//XCUIElementTypeStaticText[contains(@name,"Ask to Join")]',
        '//XCUIElementTypeStaticText[contains(@name,"Other Network")]',
    ]
    for xp in wifi_list_secondary_hints:
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                return "wifi_list"
        except Exception:
            continue

    # ----- 3) 仍停在配网 App 内（未跳进系统设置）-----
    try:
        change = driver.find_element(
            AppiumBy.XPATH, '//XCUIElementTypeButton[@name="pair net change wifi"]'
        )
        if change.is_displayed():
            return "wifi_password"
    except Exception:
        pass

    wifi_password_indicators = [
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeSecureTextField[@placeholder="Wi-Fi Password"]',
        '//XCUIElementTypeSecureTextField[contains(@placeholder,"Password")]',
    ]
    for xp in wifi_password_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                return "wifi_password"
        except Exception:
            continue

    return "unknown"


def _wlan_entry_selectors_ios() -> list[str]:
    """从设置主页进入 WLAN / Wi‑Fi 的可点击项（高系统：Apps 页返回后使用）。"""
    return [
        '//XCUIElementTypeButton[@name="com.apple.settings.wifi"]',
        '//XCUIElementTypeCell[@name="com.apple.settings.wifi"]',
        '//XCUIElementTypeButton[@name="WLAN"]',
        '//XCUIElementTypeCell[@name="WLAN"]',
        '//XCUIElementTypeStaticText[@name="WLAN"]',
        '//XCUIElementTypeButton[contains(@name,"WLAN")]',
        '//XCUIElementTypeCell[contains(@name,"WLAN")]',
        '//XCUIElementTypeButton[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeCell[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeStaticText[@name="Wi-Fi"]',
        '//XCUIElementTypeCell[contains(@name,"无线局域网")]',
        '//XCUIElementTypeStaticText[@name="无线局域网"]',
    ]


def _click_back_button_ios(driver: Any) -> bool:
    """点击系统设置左上角返回（高系统 Apps 页 → 设置主页）。"""
    back_button_selectors = [
        '//XCUIElementTypeButton[@name="Back"]',
        '//XCUIElementTypeButton[@name="返回"]',
        '//XCUIElementTypeNavigationBar/XCUIElementTypeButton[1]',
        '//XCUIElementTypeButton[contains(@name,"Back")]',
    ]
    for selector in back_button_selectors:
        try:
            btn = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            if btn.is_displayed():
                btn.click()
                time.sleep(1)
                return True
        except Exception:
            continue
    try:
        driver.back()
        time.sleep(1)
        return True
    except Exception:
        return False


def _try_click_wlan_entry_ios(
    driver: Any,
    log_func: Callable[[str], None],
    wait_s: int = 3,
) -> bool:
    """在设置主页等页面点击 WLAN / Wi‑Fi 入口（每个选择器最多等待 wait_s 秒）。"""
    for selector in _wlan_entry_selectors_ios():
        try:
            log_func(f"🔍 尝试进入 Wi‑Fi: {selector}")
            btn = WebDriverWait(driver, wait_s).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            if btn.is_displayed():
                btn.click()
                log_func(f"✅ 已点击进入 Wi‑Fi: {selector}")
                time.sleep(2)
                return True
        except Exception as e:
            log_func(f"  ⚠️ 选择器失败: {selector} — {e}")
            continue
    return False


def _handle_ios_high_system_apps_then_wlan(
    driver: Any,
    log_func: Callable[[str], None],
    screenshot_func: Callable[[Any, str], None],
) -> bool:
    """
    高系统：当前在设置 - Apps（应用）→ 返回 → 点 WLAN/Wi‑Fi 进入列表。
    """
    log_func(
        "🔄 高系统路径：设置「App(s)/应用」列表页 → 左上角返回 → 再点 Wi‑Fi/WLAN（含 com.apple.settings.wifi）…"
    )
    if not _click_back_button_ios(driver):
        log_func("⚠️ 点击返回失败，仍尝试查找 Wi‑Fi 入口…")

    time.sleep(2)
    if not _try_click_wlan_entry_ios(driver, log_func, wait_s=4):
        log_func("⚠️ 返回后未找到 WLAN/Wi‑Fi 入口")
        screenshot_func(driver, "wlan_entry_not_found_after_back")
        return False

    time.sleep(2)
    page_type = _detect_current_page_ios(driver)
    navs = _ios_nav_bar_names(driver)
    log_func(f"📄 进入 Wi‑Fi 后页面类型: {page_type}（nav={navs}）")
    if page_type == "wifi_list":
        return True
    if page_type == "wifi_password":
        log_func("ℹ️ 检测到回到 App 密码页，按流程继续")
        return True
    if page_type == "unknown":
        if any("Wi-Fi" in n or "WLAN" in n or "无线局域网" in n for n in navs):
            log_func("✅ 导航栏含 Wi‑Fi/WLAN/无线局域网，认为已进入系统 Wi‑Fi 界面")
            return True
        log_func("ℹ️ 类型为 unknown，但已成功点击 Wi‑Fi 入口，继续后续选网（由选 SSID 步骤校验）")
        return True
    return False


def _enter_wifi_list_page_ios(driver: Any, log_func: Callable[[str], None] = _log_default, screenshot_func: Callable[[Any, str], None] = _screenshot_default) -> bool:
    """
    从 App 内「Set up Wi‑Fi」页点击「切换 WiFi」进入系统 Wi‑Fi 列表。

    - **低系统**：多直接进入系统「无线局域网 / Wi‑Fi」网络列表。
    - **高系统**：多先进系统设置里的 **Apps（应用）** 列表 → 点左上角 **返回** 到设置主页 → 再点 **WLAN / Wi‑Fi** 进入列表。

    注意：不得把仅含 NavigationBar「Settings」的界面当成 WiFi 列表（否则不会走返回+WLAN）。
    """
    log_func("📶 步骤4: 进入系统 WiFi 页面...")
    
    # 1. 点击切换WiFi按钮
    try:
        btn = driver.find_element(
            AppiumBy.XPATH, '//XCUIElementTypeButton[@name="pair net change wifi"]'
        )
        btn.click()
        log_func("✅ 点击切换 WiFi 按钮成功")
        time.sleep(3)
    except Exception as e:
        log_func(f"❌ 点击切换 WiFi 按钮失败: {e}")
        screenshot_func(driver, "click_change_wifi_fail")
        return False
    
    # 2. 检测当前页面类型（多轮：系统跳转动画较慢）
    log_func("🔍 检测页面类型（低系统→WiFi 列表；高系统→设置 Apps 需再返回+进 WLAN）...")
    page_type = "unknown"
    for attempt in range(5):
        page_type = _detect_current_page_ios(driver)
        navs = _ios_nav_bar_names(driver)
        log_func(f"📄 第 {attempt + 1}/5 次检测: {page_type} | nav={navs}")
        if page_type != "unknown":
            break
        if attempt < 4:
            time.sleep(1.5)
    
    log_func(f"📄 最终页面类型: {page_type} | nav={_ios_nav_bar_names(driver)}")
    
    # 3. 低系统：已直达系统 WiFi 列表
    # 3.1 仍停在配网 App（未跳进系统）：等待系统设置拉起后再判
    if page_type == "wifi_password":
        try:
            cw = driver.find_element(
                AppiumBy.XPATH, '//XCUIElementTypeButton[@name="pair net change wifi"]'
            )
            if cw.is_displayed():
                log_func("📱 判断：仍在 App 内且可见「切换 WiFi」，等待系统设置拉起…")
                for _ in range(4):
                    time.sleep(1.5)
                    page_type = _detect_current_page_ios(driver)
                    if page_type != "wifi_password":
                        log_func(f"📄 等待后类型变为: {page_type}")
                        break
        except Exception:
            pass

    if page_type == "wifi_list":
        log_func("✅ 低系统/已直达：WiFi 列表页")
        return True

    if page_type == "wifi_password":
        log_func("✅ 仍在 App 配网页（含密码框/切换 WiFi），跳过系统列表选网")
        return True

    # 4. 高系统：设置 → Apps（应用）→ 返回 → 设置主页 → 点 WLAN/Wi‑Fi
    if page_type == "settings_apps":
        log_func(
            f"✅ 判断：高系统 — 当前在设置「应用」相关页（nav 含 App/Apps/应用之一: {_ios_nav_bar_names(driver)}）"
        )
        if not _handle_ios_high_system_apps_then_wlan(driver, log_func, screenshot_func):
            log_func("❌ 高系统 Apps → 返回 → Wi‑Fi 路径失败")
            screenshot_func(driver, "high_ios_apps_wlan_path_fail")
            return False
        return True

    # 5. 如果页面类型未知，尝试多种策略
    if page_type == "unknown":
        log_func(f"⚠️ 页面类型未知，nav={_ios_nav_bar_names(driver)}，尝试兜底…")
        if any(n in _IOS_SETTINGS_APPS_NAV_NAMES for n in _ios_nav_bar_names(driver)):
            log_func(
                "🔎 导航栏为 App/Apps/应用（系统设置应用列表页），按高系统路径：返回 → com.apple.settings.wifi / WLAN"
            )
            if _handle_ios_high_system_apps_then_wlan(driver, log_func, screenshot_func):
                return True
        
        # 策略1: 检查是否在App内（可能已经返回App）
        try:
            app_indicators = [
                '//XCUIElementTypeButton[@name="pair net change wifi"]',
                '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
                '//XCUIElementTypeButton[@name="Next"]',
            ]
            for indicator in app_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, indicator)
                    if elem.is_displayed():
                        log_func(f"✅ 检测到已返回App内（可能是WiFi密码输入页面）: {indicator}")
                        return True
                except:
                    continue
        except:
            pass
        
        # 策略2: 检查NavigationBar
        try:
            nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
            for nav in nav_bars:
                try:
                    nav_name = nav.get_attribute("name") or ""
                    if (
                        "无线局域网" in nav_name
                        or "WLAN" in nav_name
                        or "Wi-Fi" in nav_name
                        or "WiFi" in nav_name
                    ):
                        log_func(f"✅ 通过NavigationBar快速检测到WiFi列表页面: {nav_name}")
                        return True
                except:
                    pass
        except:
            pass
        
        # 策略3: 重试检测
        for i in range(2):
            log_func(f"⏳ 等待页面加载后再次检测（{i+1}/2）...")
            time.sleep(2)
            page_type = _detect_current_page_ios(driver)
            if page_type == "wifi_list":
                log_func("✅ 等待后检测到WiFi列表页面")
                return True
            elif page_type == "wifi_password":
                log_func("✅ 等待后检测到WiFi密码输入页面")
                return True
            elif page_type == "settings_apps":
                log_func("⚠️ 等待后检测到 Apps 页面，执行高系统完整路径…")
                if _handle_ios_high_system_apps_then_wlan(driver, log_func, screenshot_func):
                    return True

    # 6. 最终验证：检查是否在WiFi列表页面（勿用单独 Settings 导航栏 — 易与设置主页混淆）
    log_func("🔍 最终验证是否在WiFi列表页面...")
    final_indicators = [
        '//XCUIElementTypeNavigationBar[@name="无线局域网"]',
        '//XCUIElementTypeNavigationBar[contains(@name,"WLAN")]',
        '//XCUIElementTypeNavigationBar[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeStaticText[@name="WLAN"]',
        '//XCUIElementTypeButton[@name="WLAN"]',
        '//XCUIElementTypeStaticText[contains(@name,"选取网络")]',
    ]
    for xp in final_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                log_func(f"✅ 最终检测到 iOS WiFi 设置页面元素: {xp}")
                return True
        except:
            continue
    
    log_func("⚠️ 未明显检测到 iOS 系统 WiFi 页面，但继续执行后续步骤")
    return True


def _select_wifi_in_settings_ios(driver: Any, ssid: str, log_func: Callable[[str], None] = _log_default, screenshot_func: Callable[[Any, str], None] = _screenshot_default) -> bool:
    """在 iOS 系统 WiFi 设置页面选择指定 SSID"""
    log_func(f"🔍 在系统 WiFi 列表中寻找: {ssid}")
    max_scroll = 10
    
    selectors = [
        f'//XCUIElementTypeCell[contains(@name,"{ssid}")]',
        f'//XCUIElementTypeStaticText[@name="{ssid}"]',
        f'//XCUIElementTypeStaticText[contains(@name,"{ssid}")]',
    ]
    
    wifi_cell = None
    
    # 首先尝试直接查找
    log_func("🔍 首先尝试直接查找 WiFi（不滑动）...")
    for xp in selectors:
        try:
            wifi_cell = driver.find_element(AppiumBy.XPATH, xp)
            if wifi_cell.is_displayed():
                log_func(f"✅ 直接找到 WiFi 元素: {xp}")
                wifi_cell.click()
                log_func(f"✅ 已点击 WiFi: {ssid}")
                time.sleep(2)
                return True
        except:
            continue
    
    # 如果直接查找失败，向下滑动查找
    if not wifi_cell:
        log_func("🔍 直接查找失败，开始向下滑动查找 WiFi...")
        for i in range(max_scroll):
            log_func(f"🔍 第 {i+1}/{max_scroll} 次向下滚动寻找 WiFi...")
            
            for xp in selectors:
                try:
                    wifi_cell = driver.find_element(AppiumBy.XPATH, xp)
                    if wifi_cell.is_displayed():
                        log_func(f"✅ 向下滑动后找到 WiFi 元素: {xp}")
                        break
                except:
                    continue
            
            if wifi_cell and wifi_cell.is_displayed():
                wifi_cell.click()
                log_func(f"✅ 已点击 WiFi: {ssid}")
                time.sleep(2)
                return True
            
            # 向下滑动
            try:
                size = driver.get_window_size()
                start_x = size['width'] // 2
                start_y = int(size['height'] * 0.6)
                end_y = int(size['height'] * 0.3)
                driver.swipe(start_x, start_y, start_x, end_y, 500)
                time.sleep(2)
            except Exception as e:
                log_func(f"⚠️ 向下滑动失败: {e}")
                time.sleep(2)
    
    # 如果向下滑动未找到，尝试向上滑动查找
    if not wifi_cell:
        log_func("🔍 向下滑动未找到 WiFi，开始向上滑动查找 WiFi...")
        for i in range(max_scroll):
            log_func(f"🔍 向上滑动查找 WiFi（第 {i+1}/{max_scroll} 次）...")
            
            for xp in selectors:
                try:
                    wifi_cell = driver.find_element(AppiumBy.XPATH, xp)
                    if wifi_cell.is_displayed():
                        log_func(f"✅ 向上滑动后找到 WiFi 元素: {xp}")
                        break
                except:
                    continue
            
            if wifi_cell and wifi_cell.is_displayed():
                wifi_cell.click()
                log_func(f"✅ 已点击 WiFi: {ssid}")
                time.sleep(2)
                return True
            
            # 向上滑动
            try:
                size = driver.get_window_size()
                start_x = size['width'] // 2
                start_y = int(size['height'] * 0.3)
                end_y = int(size['height'] * 0.6)
                driver.swipe(start_x, start_y, start_x, end_y, 500)
                time.sleep(2)
            except Exception as e:
                log_func(f"⚠️ 向上滑动失败: {e}")
                time.sleep(2)
    
    log_func(f"❌ 经过向下和向上各 {max_scroll} 次滑动，仍未找到 WiFi: {ssid}")
    screenshot_func(driver, "wifi_not_found")
    return False


def _back_to_app_wifi_page_ios(driver: Any, log_func: Callable[[str], None] = _log_default) -> bool:
    """从系统设置回到 App 的 WiFi 密码输入页面"""
    log_func("🔄 通过后台切换返回 App WiFi 页面...")
    try:
        caps = getattr(driver, "capabilities", {}) or {}
        bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
        if not bundle_id:
            raise RuntimeError("bundleId 未配置")
        driver.activate_app(bundle_id)
        time.sleep(2)
        log_func("✅ 已返回 App")
        return True
    except Exception as e:
        log_func(f"⚠️ 返回 App 失败: {e}")
        return False


def _locate_password_field_ios(driver: Any, log_func: Callable[[str], None] = _log_default, screenshot_func: Callable[[Any, str], None] = _screenshot_default):
    """定位 iOS WiFi 密码输入框"""
    log_func("🔍 定位 WiFi 密码输入框...")
    selectors = [
        '//XCUIElementTypeSecureTextField',
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeSecureTextField[@placeholder="Wi-Fi Password"]',
        '//XCUIElementTypeSecureTextField[contains(@placeholder,"Password")]',
    ]
    last_err = None
    for i, xp in enumerate(selectors, 1):
        try:
            log_func(f"🔍 尝试密码框选择器 {i}: {xp}")
            field = WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if field.is_displayed():
                log_func(f"✅ 找到密码框（选择器 {i}）")
                return field
        except Exception as e:
            last_err = e
            log_func(f"  ⚠️ 选择器 {i} 失败: {e}")
    log_func(f"❌ 未找到密码输入框: {last_err}")
    screenshot_func(driver, "pwd_field_not_found")
    return None


def _input_wifi_password_ios(driver: Any, password: str, log_func: Callable[[str], None] = _log_default, screenshot_func: Callable[[Any, str], None] = _screenshot_default) -> bool:
    """
    按最新要求输入 iOS WiFi 密码：
    - 无论密码框中原来是什么，统一用连续退格清空，然后重新输入密码
    """
    field = _locate_password_field_ios(driver, log_func, screenshot_func)
    if field is None:
        return False

    # 先点击密码框获取焦点
    try:
        field.click()
        time.sleep(2)
    except Exception as e:
        log_func(f"⚠️ 点击密码框失败: {e}")
    
    # 不判断当前内容，直接用退格键"暴力清空"
    log_func("🧹 使用连续退格清除密码框中的所有内容（不判断原内容）...")
    try:
        # 重新定位密码框，避免stale element
        field = _locate_password_field_ios(driver, log_func, screenshot_func)
        if field is None:
            return False
        field.click()
        time.sleep(2)
        field.send_keys("\b" * 50)  # 多发一些退格，确保清空
        time.sleep(2)
    except Exception as e:
        log_func(f"⚠️ 连续退格清除时出错（继续尝试输入新密码）: {e}")
        # 如果清除失败，尝试重新定位密码框
        field = _locate_password_field_ios(driver, log_func, screenshot_func)
        if field is None:
            return False

    # 统一输入新密码
    log_func(f"🔍 输入 WiFi 密码（来自 device_config.json）: {password}")
    try:
        # 再次重新定位密码框，确保元素是最新的
        field = _locate_password_field_ios(driver, log_func, screenshot_func)
        if field is None:
            return False
        field.click()
        time.sleep(2)
        field.send_keys(password)
        time.sleep(2)
        # iOS SecureTextField 出于安全考虑，value 可能为空或返回密文，所以不强校验
        try:
            v = field.get_attribute("value")
            log_func(f"✅ WiFi 密码输入完成（调试信息，当前 value: '{v}'）")
        except Exception:
            log_func("✅ WiFi 密码输入完成（无法读取 value，为正常安全行为）")
        return True
    except Exception as e:
        log_func(f"❌ WiFi 密码输入失败: {e}")
        screenshot_func(driver, "pwd_input_fail")
        return False


# ==================== Android WiFi 设置 ====================

_ANDROID_SYSTEM_SETTINGS_PKG_MARKERS = (
    "com.android.settings",
    "com.samsung.android.settings",
    "com.samsung.android.app.settings",
    "com.oplus.settings",
    "com.coloros.settings",
    "com.miui",
    "com.huawei.systemmanager",
    "com.android.systemui",
    "com.google.android.permissioncontroller",
)


def _safe_current_package_android(driver: Any) -> str:
    try:
        return (driver.current_package or "").strip()
    except Exception:
        return ""


def _is_system_wifi_picker_android(driver: Any, app_package: str) -> bool:
    """是否已离开 App，进入系统 WiFi/设置选择页。"""
    pkg = _safe_current_package_android(driver).lower()
    app_pkg = (app_package or "").lower()
    if not pkg:
        return False
    # 仍在 App 包名内 → 肯定还没进系统选择页
    if app_pkg and pkg == app_pkg:
        return False
    if any(m in pkg for m in _ANDROID_SYSTEM_SETTINGS_PKG_MARKERS):
        return True
    if "settings" in pkg:
        return True
    # 包名变了且不再是 App，也视为已跳出（部分 ROM 自定义包名）
    if app_pkg and pkg != app_pkg:
        return True
    return False


def _still_on_app_wifi_setup_android(driver: Any, app_package: str) -> bool:
    """是否仍停留在 App 的 Set Up Wi-Fi 页（未切到系统列表）。"""
    pkg = _safe_current_package_android(driver)
    app_pkg = (app_package or "").strip()
    if app_pkg and pkg and pkg != app_pkg:
        return False
    indicators = (
        '//android.view.View[@content-desc="switch"]',
        '//android.widget.TextView[@text="Set Up Wi-Fi"]',
        '//android.widget.TextView[contains(@text,"Set Up Wi-Fi")]',
        '//android.view.View[@content-desc="password"]',
    )
    for xp in indicators:
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            if el.is_displayed():
                return True
        except Exception:
            continue
    return False


def _tap_element_center_android(driver: Any, element: Any, log_func: Callable[[str], None]) -> bool:
    """坐标点击元素中心，绕过部分机型 click() 无效。"""
    try:
        loc = element.location
        size = element.size
        x = int(loc["x"] + size["width"] / 2)
        y = int(loc["y"] + size["height"] / 2)
        try:
            driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
            log_func(f"✅ 坐标点击成功: ({x},{y})")
            return True
        except Exception:
            pass
        try:
            driver.tap([(x, y)], 100)
            log_func(f"✅ tap 点击成功: ({x},{y})")
            return True
        except Exception as e:
            log_func(f"⚠️ 坐标点击失败: {e}")
            return False
    except Exception as e:
        log_func(f"⚠️ 获取元素坐标失败: {e}")
        return False


def _click_wifi_switch_android(driver: Any, log_func: Callable[[str], None] = _log_default) -> bool:
    """
    点击 Set Up Wi-Fi 页的 switch，尝试进入系统 WiFi 列表。
    返回 True 仅表示「点到了某个切换入口」，不保证已进入系统页。
    """
    selectors = [
        '//android.view.View[@content-desc="switch"]',
        '//android.view.View[@content-desc="switch"]/..',
        '//android.view.View[@content-desc*="switch"]',
        '//android.widget.ImageView[@content-desc="switch"]',
        '//android.widget.Button[@content-desc="switch"]',
        '//*[contains(@content-desc,"switch")]',
        '//android.widget.TextView[contains(@text,"Change")]',
        '//android.widget.TextView[contains(@text,"切换")]',
        '//android.widget.Button[contains(@text,"Change")]',
        '//android.widget.Button[contains(@text,"切换")]',
    ]
    for xp in selectors:
        try:
            el = WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if not el.is_displayed():
                continue
            # 1) 普通 click
            try:
                el.click()
                log_func(f"✅ 已点击切换入口: {xp}")
                return True
            except Exception:
                pass
            # 2) 父节点
            try:
                parent = el.find_element(AppiumBy.XPATH, "./..")
                parent.click()
                log_func(f"✅ 已点击切换入口父节点: {xp}")
                return True
            except Exception:
                pass
            # 3) 坐标
            if _tap_element_center_android(driver, el, log_func):
                return True
        except Exception:
            continue
    log_func("❌ 未找到可点击的 WiFi switch / 切换入口")
    return False


def _enter_system_wifi_picker_android(
    driver: Any,
    app_package: str,
    log_func: Callable[[str], None],
    screenshot_func: Callable[[Any, str], None],
    max_attempts: int = 3,
) -> bool:
    """点击 switch 并确认已进入系统 WiFi 选择页；失败则重试。"""
    log_func('🔍 set up wifi：点击 switch 进入系统 WiFi 列表...')
    for attempt in range(1, max_attempts + 1):
        log_func(f"🔄 第 {attempt}/{max_attempts} 次尝试进入系统 WiFi 页...")
        before_pkg = _safe_current_package_android(driver)
        clicked = _click_wifi_switch_android(driver, log_func)
        if not clicked:
            time.sleep(1)
            continue

        # 等待包名切换 / 离开 Set Up Wi-Fi
        entered = False
        for _ in range(12):
            time.sleep(0.5)
            if _is_system_wifi_picker_android(driver, app_package):
                entered = True
                break
            if not _still_on_app_wifi_setup_android(driver, app_package):
                # 页面特征已变，也算离开了 setup 页
                entered = True
                break

        after_pkg = _safe_current_package_android(driver)
        log_func(f"ℹ️ 包名: {before_pkg} → {after_pkg}")

        if entered:
            log_func("✅ 已进入系统 WiFi 选择页（离开 Set Up Wi-Fi）")
            time.sleep(1.5)
            return True

        log_func("⚠️ 点击后仍停留在 Set Up Wi-Fi，准备重试...")
        screenshot_func(driver, f"wifi_switch_still_on_setup_{attempt}")
        time.sleep(1)

    log_func("❌ 多次点击 switch 后仍未进入系统 WiFi 页")
    screenshot_func(driver, "wifi_switch_enter_failed")
    return False


def _dump_visible_wifi_ssids_android(driver: Any, log_func: Callable[[str], None]) -> list[str]:
    """采集当前系统 WiFi 列表可见 SSID，便于定位「列表里根本没有目标路由」。"""
    ssids: list[str] = []
    try:
        els = driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView")
        skip = {
            "wlan", "wi-fi", "wifi", "开", "关", "on", "off", "添加网络", "add network",
            "已连接", "connected", "saved", "已保存", "网络与互联网",
            "当前网络", "可用的网络", "网络",
        }
        for el in els:
            try:
                if not el.is_displayed():
                    continue
                text = (el.text or "").strip()
                if not text or len(text) < 2:
                    continue
                if text.lower() in skip:
                    continue
                # 过滤安全提示长文案
                if "安全性" in text or ("点击" in text and len(text) > 20):
                    continue
                if text.isdigit():
                    continue
                if text not in ssids:
                    ssids.append(text)
            except Exception:
                continue
    except Exception as e:
        log_func(f"⚠️ 采集可见 SSID 失败: {e}")
    if ssids:
        preview = ", ".join(ssids[:20])
        more = f" ...(+{len(ssids) - 20})" if len(ssids) > 20 else ""
        log_func(f"📋 当前可见网络/文案: {preview}{more}")
    else:
        log_func("📋 当前未见可用 SSID 文案（列表可能未加载）")
    return ssids


def _ssid_match_android(candidate: str, targets: list[str]) -> bool:
    """大小写不敏感：精确或 contains 命中任一目标/别名。"""
    c = (candidate or "").strip().lower()
    if not c:
        return False
    for t in targets:
        tt = (t or "").strip().lower()
        if not tt:
            continue
        if c == tt or tt in c or c in tt:
            return True
    return False


def _any_target_in_ssids(ssids: list[str], targets: list[str]) -> bool:
    return any(_ssid_match_android(s, targets) for s in (ssids or []))


def _is_softap_ssid(text: str) -> bool:
    t = (text or "").lower()
    return any(
        k in t
        for k in (
            "beatbot",
            "sora neo",
            "iskim",
            "direct-",
            "androidap",
            "iphone",
        )
    )


def _mostly_softap_zone(ssids: list[str]) -> bool:
    """滚到列表底部常见：几乎全是机器人 SoftAP / 办公网，无家用路由段。"""
    if not ssids:
        return False
    soft = sum(1 for s in ssids if _is_softap_ssid(s))
    return soft >= 2 and soft >= len(ssids) * 0.4


def _swipe_wifi_list_android(
    driver: Any,
    direction: str,
    log_func: Callable[[str], None],
    percent: float = 0.75,
) -> bool:
    """direction: up=看下面的网络, down=回到顶部/下拉刷新感。"""
    try:
        size = driver.get_window_size()
        start_x = size["width"] // 2
        if direction == "up":
            start_y = int(size["height"] * 0.75)
            end_y = int(size["height"] * 0.25)
            gesture_dir = "up"
        else:
            start_y = int(size["height"] * 0.28)
            end_y = int(size["height"] * 0.82)
            gesture_dir = "down"
        try:
            driver.execute_script(
                "mobile: swipeGesture",
                {
                    "left": int(size["width"] * 0.1),
                    "top": int(size["height"] * 0.15),
                    "width": int(size["width"] * 0.8),
                    "height": int(size["height"] * 0.7),
                    "direction": gesture_dir,
                    "percent": max(0.3, min(0.9, percent)),
                },
            )
        except Exception:
            driver.swipe(start_x, start_y, start_x, end_y, 500)
        time.sleep(1.0)
        return True
    except Exception as swipe_err:
        err = str(swipe_err).lower()
        if "instrumentation" in err or "session" in err or "proxied" in err:
            raise
        log_func(f"⚠️ 滑动失败: {swipe_err}")
        time.sleep(0.8)
        return False


def _pull_refresh_and_wait_ssid(
    driver: Any,
    targets: list[str],
    log_func: Callable[[str], None],
    rounds: int = 3,
    wait_each: float = 4.0,
) -> list[str]:
    """
    首屏没有目标 SSID 时：下拉刷新 + 等待扫描，避免立刻滚进 SoftAP 区空耗时间。
    """
    ssids: list[str] = []
    for i in range(max(1, rounds)):
        log_func(f"♻️ 目标 SSID 未出现，下拉刷新等待扫描（{i + 1}/{rounds}）...")
        # 先滚回顶部再强下拉
        for _ in range(2):
            _swipe_wifi_list_android(driver, "down", log_func, percent=0.85)
        time.sleep(wait_each)
        ssids = _dump_visible_wifi_ssids_android(driver, log_func)
        if _any_target_in_ssids(ssids, targets):
            log_func("✅ 扫描刷新后已出现目标 SSID")
            return ssids
    return ssids


def _scroll_back_to_wifi_top(driver: Any, log_func: Callable[[str], None], times: int = 5) -> None:
    """从 SoftAP / 弱网区滚回列表顶部（可用的网络附近）。"""
    log_func("⬆️ 检测到 SoftAP/弱网区，滚回列表顶部等待家用路由...")
    for _ in range(times):
        _swipe_wifi_list_android(driver, "down", log_func, percent=0.85)
    time.sleep(2.0)


def _select_wifi_in_settings_android(
    driver: Any,
    wifi_name: str,
    log_func: Callable[[str], None] = _log_default,
    screenshot_func: Callable[[Any, str], None] = _screenshot_default,
    wifi_aliases: Optional[list] = None,
) -> bool:
    """在 Android 系统 WiFi 设置页面选择指定 WiFi（含别名 / 大小写不敏感 / 双向滚动）。"""
    app_package = ""
    try:
        app_package = driver.capabilities.get("appPackage") or ""
    except Exception:
        pass

    # 若仍在 App 的 set up wifi，禁止盲目滚动（否则滑动失败 + UA2 易崩）
    if _still_on_app_wifi_setup_android(driver, app_package):
        log_func("❌ 当前仍在 App Set Up Wi-Fi 页，未进入系统 WiFi 列表，跳过滚动查找")
        screenshot_func(driver, "wifi_still_on_setup_page")
        return False

    targets = [wifi_name] + [a for a in (wifi_aliases or []) if a and a != wifi_name]
    log_func(f"🔍 寻找WiFi: {wifi_name}" + (f" / 别名={targets[1:]}" if len(targets) > 1 else ""))
    log_func(f"ℹ️ 当前包名: {_safe_current_package_android(driver) or '(unknown)'}")

    # 等待系统扫描出更多网络
    time.sleep(3)
    visible = _dump_visible_wifi_ssids_android(driver, log_func)

    # 首屏没有目标：先刷新扫描，再滑动（NETGEAR 等偶发晚出现）
    if not _any_target_in_ssids(visible, targets):
        visible = _pull_refresh_and_wait_ssid(driver, targets, log_func, rounds=3, wait_each=4.0)

    wifi_selectors = []
    for name in targets:
        wifi_selectors.extend(
            [
                f'//android.widget.TextView[@text="{name}"]',
                f'//android.widget.TextView[contains(@text, "{name}")]',
                f'//android.view.View[.//android.widget.TextView[@text="{name}"]]',
                f'//android.view.View[.//android.widget.TextView[contains(@text, "{name}")]]',
                f'//android.widget.LinearLayout[.//android.widget.TextView[@text="{name}"]]',
                f'//android.widget.LinearLayout[.//android.widget.TextView[contains(@text, "{name}")]]',
                f'//android.widget.RelativeLayout[.//android.widget.TextView[@text="{name}"]]',
                f'//android.widget.RelativeLayout[.//android.widget.TextView[contains(@text, "{name}")]]',
                f'//android.widget.FrameLayout[.//android.widget.TextView[@text="{name}"]]',
                f'//android.widget.FrameLayout[.//android.widget.TextView[contains(@text, "{name}")]]',
            ]
        )
        if "_" in name:
            wifi_selectors.append(
                f'//android.widget.TextView[contains(@text, "{name.split("_")[0]}")]'
            )

    def _try_click_wifi() -> bool:
        for selector in wifi_selectors:
            try:
                elements = driver.find_elements(AppiumBy.XPATH, selector)
                for elem in elements:
                    try:
                        if not elem.is_displayed():
                            continue
                        text = (elem.text or "").strip()
                        if not _ssid_match_android(text, targets):
                            continue
                        log_func(f"🔍 找到元素，文本: {text}")
                        try:
                            elem.click()
                            log_func(f"✅ 找到并点击WiFi: {text}")
                            return True
                        except Exception:
                            try:
                                parent = elem.find_element(AppiumBy.XPATH, "./..")
                                parent.click()
                                log_func(f"✅ 通过父容器点击WiFi: {text}")
                                return True
                            except Exception:
                                if _tap_element_center_android(driver, elem, log_func):
                                    log_func(f"✅ 坐标点击WiFi: {text}")
                                    return True
                    except Exception:
                        continue
            except Exception as e:
                err = str(e).lower()
                if "instrumentation" in err or "session" in err:
                    raise
                continue

        try:
            for elem in driver.find_elements(AppiumBy.XPATH, "//android.widget.TextView"):
                try:
                    if not elem.is_displayed():
                        continue
                    text = (elem.text or "").strip()
                    if not _ssid_match_android(text, targets):
                        continue
                    log_func(f"🔍 兜底匹配到 WiFi 文案: {text}")
                    try:
                        elem.click()
                        log_func(f"✅ 找到并点击WiFi: {text}")
                        return True
                    except Exception:
                        if _tap_element_center_android(driver, elem, log_func):
                            log_func(f"✅ 坐标点击WiFi: {text}")
                            return True
                except Exception:
                    continue
        except Exception as e:
            err = str(e).lower()
            if "instrumentation" in err or "session" in err:
                raise
        return False

    log_func("🔍 首先尝试直接查找WiFi（不滚动）...")
    try:
        if _try_click_wifi():
            time.sleep(2)
            return True
    except Exception as e:
        log_func(f"❌ 查找 WiFi 时会话异常: {e}")
        return False

    # 双向滑动：见到 SoftAP 区就回顶刷新，避免空滑到底
    max_scrolls = 10
    seen_target_in_dump = _any_target_in_ssids(visible, targets)

    for round_idx in range(2):
        if round_idx == 1:
            log_func("♻️ 未找到目标 SSID，回顶刷新后再扫一轮...")
            _scroll_back_to_wifi_top(driver, log_func, times=6)
            visible = _pull_refresh_and_wait_ssid(driver, targets, log_func, rounds=2, wait_each=5.0)
            seen_target_in_dump = seen_target_in_dump or _any_target_in_ssids(visible, targets)
            try:
                if _try_click_wifi():
                    time.sleep(2)
                    return True
            except Exception as e:
                log_func(f"❌ 查找 WiFi 时会话异常: {e}")
                return False

        log_func(f"🔍 第{round_idx + 1}轮：先向下滚回顶部...")
        for _ in range(3):
            if _still_on_app_wifi_setup_android(driver, app_package):
                log_func("❌ 滚动过程中检测到仍在 Set Up Wi-Fi，停止查找")
                screenshot_func(driver, "wifi_scroll_back_on_setup")
                return False
            try:
                _swipe_wifi_list_android(driver, "down", log_func, percent=0.8)
            except Exception as e:
                log_func(f"❌ 滑动时 UiAutomator2 已失效: {e}")
                return False
            try:
                if _try_click_wifi():
                    time.sleep(2)
                    return True
            except Exception as e:
                log_func(f"❌ 查找 WiFi 时会话异常: {e}")
                return False

        log_func(f"🔍 第{round_idx + 1}轮：向上滚动查找...")
        softap_hits = 0
        for scroll_attempt in range(max_scrolls):
            if _still_on_app_wifi_setup_android(driver, app_package):
                log_func("❌ 滚动过程中检测到仍在 Set Up Wi-Fi，停止查找")
                screenshot_func(driver, "wifi_scroll_back_on_setup")
                return False

            log_func(f"🔍 第{scroll_attempt + 1}/{max_scrolls}次向上滚动寻找WiFi...")
            try:
                if _try_click_wifi():
                    time.sleep(2)
                    return True
            except Exception as e:
                log_func(f"❌ 滚动查找时会话异常: {e}")
                return False

            # 每滑 2 次 dump 一次，避免滚进 SoftAP 区空耗
            if scroll_attempt % 2 == 1 or scroll_attempt == 0:
                mid = _dump_visible_wifi_ssids_android(driver, log_func)
                if _any_target_in_ssids(mid, targets):
                    seen_target_in_dump = True
                    try:
                        if _try_click_wifi():
                            time.sleep(2)
                            return True
                    except Exception as e:
                        log_func(f"❌ 查找 WiFi 时会话异常: {e}")
                        return False
                if _mostly_softap_zone(mid):
                    softap_hits += 1
                    log_func("⚠️ 当前可视区偏 SoftAP/弱网，停止继续向下空滑")
                    _scroll_back_to_wifi_top(driver, log_func, times=5)
                    # 回顶后再等一轮扫描
                    mid = _pull_refresh_and_wait_ssid(
                        driver, targets, log_func, rounds=2, wait_each=4.0
                    )
                    if _any_target_in_ssids(mid, targets):
                        seen_target_in_dump = True
                        try:
                            if _try_click_wifi():
                                time.sleep(2)
                                return True
                        except Exception as e:
                            log_func(f"❌ 查找 WiFi 时会话异常: {e}")
                            return False
                    # SoftAP 区连续出现且从未 dump 到目标 → 本轮提前结束
                    if softap_hits >= 2 and not seen_target_in_dump:
                        log_func("⏭️ 多次落入 SoftAP 区且未见目标 SSID，结束本轮滑动")
                        break
                    continue

            try:
                _swipe_wifi_list_android(driver, "up", log_func, percent=0.65)
            except Exception as e:
                log_func(f"❌ 滑动时 UiAutomator2 已失效: {e}")
                return False

    log_func(f"❌ 未找到WiFi: {wifi_name}")
    _dump_visible_wifi_ssids_android(driver, log_func)
    try:
        screenshot_func(driver, "wifi_not_found")
    except Exception:
        pass
    return False


def _check_is_home_page_android(driver: Any, app_package: str) -> bool:
    """检测是否在 APP 主页面"""
    try:
        # 检查包名
        current_pkg = driver.current_package
        if current_pkg != app_package:
            return False
        
        # 检查首页特征元素
        home_indicators = [
            '(//android.widget.ImageView[@content-desc="add"])[2]',
            '//android.widget.ImageView[@content-desc="add"]',
            '//android.widget.TextView[contains(@text,"设备")]',
            '//android.widget.TextView[contains(@text,"Sora")]',
            '//android.widget.TextView[contains(@text,"robot")]',
        ]
        
        for indicator in home_indicators:
            try:
                el = driver.find_element(AppiumBy.XPATH, indicator)
                if el.is_displayed():
                    return True
            except:
                continue
        return False
    except:
        return False


def _check_is_wifi_setup_page_android(driver: Any, app_package: str) -> bool:
    """检测是否在 Set up Wi-Fi 页面"""
    try:
        # 检查包名
        current_pkg = driver.current_package
        if current_pkg != app_package:
            return False
        
        # 检查 WiFi 设置页面特征元素
        wifi_setup_indicators = [
            '//android.widget.TextView[@text="Set Up Wi-Fi"]',
            '//android.view.View[@content-desc="password"]',
            '//android.view.View[@content-desc="switch"]',
            '//android.widget.EditText[@text="••••••••••"]',
            '//android.widget.EditText[@hint="Password"]',
            '//android.widget.EditText[@hint="密码"]',
        ]
        
        for indicator in wifi_setup_indicators:
            try:
                el = driver.find_element(AppiumBy.XPATH, indicator)
                if el.is_displayed():
                    return True
            except:
                continue
        return False
    except:
        return False


def _back_to_app_wifi_page_android(driver: Any, app_package: str, log_func: Callable[[str], None] = _log_default, wait_for_wifi_setup_page: Optional[Callable] = None) -> bool:
    """
    从系统设置回到 App 的 WiFi 设置页面
    需要传入 wait_for_wifi_setup_page 函数用于检测是否回到 WiFi 设置页面
    """
    log_func("🔙 返回WiFi设置页面...")
    
    # 检测是否是 OnePlus 设备
    device_name = driver.capabilities.get('deviceName', '').lower()
    is_oneplus = 'oneplus' in device_name or '1+' in device_name or 'oplus' in device_name
    
    # OnePlus 设备需要额外等待和操作
    if is_oneplus:
        log_func("📱 检测到 OnePlus 设备，等待 WiFi 连接页面加载...")
        time.sleep(5)
        
        # 尝试点击"连接"或"确定"按钮（OnePlus 系统 WiFi 页面）
        connect_selectors = [
            '//android.widget.Button[@text="连接"]',
            '//android.widget.Button[@text="Connect"]',
            '//android.widget.Button[contains(@text,"连接")]',
            '//android.widget.Button[contains(@text,"Connect")]',
            '//android.widget.Button[@resource-id="android:id/button1"]',
            '//android.widget.Button[@resource-id="android:id/button2"]',
        ]
        
        for selector in connect_selectors:
            try:
                connect_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if connect_btn.is_displayed():
                    connect_btn.click()
                    log_func(f"✅ 点击连接按钮成功: {selector}")
                    time.sleep(3)
                    break
            except:
                continue
    
    # 先判断是否已回到APP的WiFi设置页（通过包名和页面元素双重验证）
    if _check_is_wifi_setup_page_android(driver, app_package):
        log_func("✅ 已在APP的WiFi设置页（包名和元素双重验证）")
        return True
    
    # 检查是否已返回主页面（如果已返回主页面，说明返回过度了）
    if _check_is_home_page_android(driver, app_package):
        log_func("❌ 检测到已返回主页面，说明返回过度了！")
        log_func("⚠️ 无法返回到 WiFi 设置页面，可能流程异常")
        return False

    # 返回WiFi设置页面：先检查是否在系统设置页面，如果是则先退出
    # 检查当前是否在系统设置页面
    try:
        current_pkg = driver.current_package
        log_func(f"🔍 当前包名: {current_pkg}")
        
        # 常见的系统设置包名
        system_settings_packages = [
            'com.android.settings',
            'com.android.settings.wifi',
            'com.oplus.settings',  # OnePlus
            'com.coloros.settings',  # ColorOS
        ]
        
        if current_pkg and current_pkg in system_settings_packages:
            log_func(f"🔍 检测到仍在系统设置页面（包名: {current_pkg}），先按返回键退出...")
            # 先按返回键退出系统设置（最多3次，每次返回后都检测）
            for back_count in range(3):
                try:
                    driver.press_keycode(4)  # 返回键
                    time.sleep(1.5)
                    
                    # 每次返回后立即检测页面状态
                    if _check_is_wifi_setup_page_android(driver, app_package):
                        log_func(f"✅ 第 {back_count + 1} 次返回后已到达 WiFi 设置页面")
                        return True
                    
                    if _check_is_home_page_android(driver, app_package):
                        log_func(f"❌ 第 {back_count + 1} 次返回后已到达主页面，返回过度！")
                        return False
                except:
                    pass
            time.sleep(2)
            
            # 再次检查包名
            try:
                new_pkg = driver.current_package
                log_func(f"🔍 返回后包名: {new_pkg}")
            except:
                pass
    except Exception as e:
        log_func(f"⚠️ 检查当前包名失败: {e}")
    
    # 方法1：优先后台切回APP
    if app_package:
        try:
            log_func(f"📱 激活APP: {app_package}")
            driver.activate_app(app_package)
            time.sleep(3)  # 等待 APP 完全激活
            log_func("✅ 通过后台切换激活APP成功")
            
            # 激活后立即检测页面状态
            if _check_is_wifi_setup_page_android(driver, app_package):
                log_func("✅ 激活APP后已到达 WiFi 设置页面")
                return True
            
            if _check_is_home_page_android(driver, app_package):
                log_func("❌ 激活APP后已到达主页面，说明返回过度！")
                return False
            
            # 激活后立即检查包名
            try:
                activated_pkg = driver.current_package
                log_func(f"🔍 激活后包名: {activated_pkg}")
                if activated_pkg != app_package:
                    log_func("⚠️ 激活后包名仍不匹配，尝试按返回键（最多2次，每次检测）")
                    # 再按几次返回键，每次返回后都检测
                    for back_count in range(2):
                        try:
                            driver.press_keycode(4)
                            time.sleep(1.5)
                            
                            # 每次返回后立即检测
                            if _check_is_wifi_setup_page_android(driver, app_package):
                                log_func(f"✅ 激活后第 {back_count + 1} 次返回已到达 WiFi 设置页面")
                                return True
                            
                            if _check_is_home_page_android(driver, app_package):
                                log_func(f"❌ 激活后第 {back_count + 1} 次返回已到达主页面，返回过度！")
                                return False
                        except:
                            pass
                    time.sleep(2)
            except:
                pass
        except Exception as e:
            log_func(f"⚠️ activate_app 失败: {e}")
    
    # 检测是否已回到 WiFi 设置页面（使用传入的检测函数）
    if wait_for_wifi_setup_page and wait_for_wifi_setup_page(driver, timeout=3, app_package=app_package):
        log_func("✅ 通过后台切换成功返回到APP的Set up Wi-Fi页面")
        return True
    
    # 再次检测是否已返回主页面
    if _check_is_home_page_android(driver, app_package):
        log_func("❌ 检测到已返回主页面，说明返回过度！")
        return False
    
    # 方法2：未检测到则尝试点击左上角返回按钮（最多2次，每次返回后都检测）
    log_func("⚠️ 后台切换后未检测到WiFi设置页，尝试点击左上角返回按钮（最多2次，每次检测）...")
    back_selectors = [
        '//android.widget.ImageButton[@content-desc="Navigate up"]',
        '//android.widget.ImageButton[@content-desc="Back"]',
        '//android.widget.ImageButton[contains(@content-desc,"返回")]',
        '//android.view.View[@content-desc="Navigate up"]',
        '//android.widget.Button[contains(@text,"Back")]'
    ]
    
    for attempt in range(2):
        log_func(f"🔄 第 {attempt + 1}/2 次尝试返回...")
        clicked_back = False
        for selector in back_selectors:
            try:
                back_btn = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, selector))
                )
                if back_btn.is_displayed():
                    back_btn.click()
                    log_func(f"↩️ 点击左上角返回按钮成功 ({selector})")
                    time.sleep(2)
                    clicked_back = True
                    break
            except:
                continue
        if not clicked_back:
            try:
                driver.press_keycode(4)
                log_func("↩️ 使用物理返回键")
                time.sleep(2)
                clicked_back = True
            except Exception as key_err:
                log_func(f"⚠️ 物理返回键失败: {key_err}")
        
        # 每次返回后立即检测页面状态
        if clicked_back:
            # 检测是否已回到Set up Wi-Fi页面
            if _check_is_wifi_setup_page_android(driver, app_package):
                log_func("✅ 已成功返回到APP的Set up Wi-Fi页面")
                return True
            
            # 检测是否已返回主页面
            if _check_is_home_page_android(driver, app_package):
                log_func("❌ 已返回主页面，说明返回过度！")
                return False
            
            # 使用传入的检测函数再次检测
            if wait_for_wifi_setup_page and wait_for_wifi_setup_page(driver, timeout=3, app_package=app_package):
                log_func("✅ 已成功返回到APP的Set up Wi-Fi页面（通过检测函数）")
                return True
            else:
                log_func("⚠️ 返回后仍未检测到WiFi设置页，继续尝试...")
    
    # 保留扩展返回兜底（OnePlus 设备可多尝试，但每次返回后都检测）
    log_func("⚠️ 前两次返回未成功，继续使用扩展返回尝试（每次返回后都检测）...")
    max_back_attempts = 8 if is_oneplus else 5
    for attempt in range(max_back_attempts):
        log_func(f"🔄 扩展尝试返回 {attempt + 1}/{max_back_attempts} ...")
        clicked_back = False
        for selector in back_selectors:
            try:
                back_btn = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, selector))
                )
                if back_btn.is_displayed():
                    back_btn.click()
                    log_func(f"↩️ 点击左上角返回按钮成功 ({selector})")
                    time.sleep(2)
                    clicked_back = True
                    break
            except:
                continue
        if not clicked_back:
            try:
                driver.press_keycode(4)
                log_func("↩️ 使用物理返回键")
                time.sleep(2)
                clicked_back = True
            except Exception as key_err:
                log_func(f"⚠️ 物理返回键失败: {key_err}")
        
        # 每次返回后立即检测页面状态
        if clicked_back:
            # 检测是否已回到Set up Wi-Fi页面
            if _check_is_wifi_setup_page_android(driver, app_package):
                log_func("✅ 已成功返回到APP的Set up Wi-Fi页面")
                return True
            
            # 检测是否已返回主页面
            if _check_is_home_page_android(driver, app_package):
                log_func("❌ 已返回主页面，说明返回过度！停止返回")
                return False
            
            # 使用传入的检测函数再次检测
            wait_timeout = 5 if is_oneplus else 3
            if wait_for_wifi_setup_page and wait_for_wifi_setup_page(driver, timeout=wait_timeout, app_package=app_package):
                log_func("✅ 已成功返回到APP的Set up Wi-Fi页面（通过检测函数）")
                return True
            else:
                log_func("⚠️ 返回后仍未检测到WiFi设置页，继续尝试...")
        else:
            log_func("⚠️ 本次尝试未找到可点击的返回按钮")
    
    # 最终检测
    if _check_is_wifi_setup_page_android(driver, app_package):
        log_func("✅ 最终检测：已在APP的WiFi设置页")
        return True
    
    if _check_is_home_page_android(driver, app_package):
        log_func("❌ 最终检测：已返回主页面，返回过度！")
        return False
    
    log_func("⚠️ 无法确认是否已返回到WiFi设置页面")
    return False


def _input_wifi_password_android(driver: Any, wifi_password: str, log_func: Callable[[str], None] = _log_default, screenshot_func: Callable[[Any, str], None] = _screenshot_default) -> bool:
    """
    输入 Android WiFi 密码：
    优先点击 //android.widget.ScrollView/android.view.View[2]/android.widget.EditText，
    再输入 device_config.json 中对应路由器密码。
    """
    log_func("🔍 定位并点击密码输入框...")

    # 用户指定元素优先，其余为兜底
    password_selectors = [
        '//android.widget.ScrollView/android.view.View[2]/android.widget.EditText',
        '//android.view.View[@content-desc="password"]/preceding-sibling::android.widget.EditText',
        "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.widget.EditText",
        '//android.widget.EditText[@text="••••••••••"]',
        "//android.widget.EditText[2]",
        "//android.widget.EditText[1]",
        "//android.widget.EditText",
        "//android.widget.EditText[@hint='Password']",
        "//android.widget.EditText[@hint='密码']",
        "//android.widget.EditText[@hint='password']",
    ]

    def _locate_password_field():
        device_name = str(driver.capabilities.get('deviceName', '')).lower()
        is_oneplus = 'oneplus' in device_name or '1+' in device_name or 'oplus' in device_name
        wait_timeout = 5 if is_oneplus else 3
        for i, selector in enumerate(password_selectors):
            try:
                log_func(f"🔍 尝试密码选择器 {i + 1}: {selector}")
                field = WebDriverWait(driver, wait_timeout).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                log_func(f"✅ 找到密码输入框，使用选择器 {i + 1}")
                return field
            except Exception as e:
                log_func(f"⚠️ 密码选择器 {i + 1} 失败: {e}")
                continue
        return None

    password_field = _locate_password_field()
    if password_field is None:
        log_func("❌ 未找到密码输入框")
        screenshot_func(driver, "password_field_not_found")
        return False

    # 必须先点击密码框获取焦点
    log_func("👆 点击密码框...")
    try:
        password_field.click()
        time.sleep(1)
        log_func("✅ 已点击密码框")
    except Exception as e:
        log_func(f"❌ 点击密码框失败: {e}")
        screenshot_func(driver, "password_field_click_fail")
        return False

    # 清空后再输入配置中的路由器密码
    log_func("🧹 清除密码框中的现有内容...")
    try:
        password_field = _locate_password_field() or password_field
        password_field.click()
        time.sleep(0.3)
        password_field.clear()
        time.sleep(0.5)
    except Exception:
        log_func("⚠️ clear() 清除失败，改用退格键清空...")
        try:
            password_field = _locate_password_field() or password_field
            password_field.click()
            time.sleep(0.3)
            for _ in range(30):
                driver.press_keycode(67)  # KEYCODE_DEL
            time.sleep(0.5)
        except Exception as e:
            log_func(f"⚠️ 备用清除方法也失败: {e}")

    log_func(f"🔑 输入 device_config.json 中的路由器密码: {wifi_password}")
    try:
        password_field = _locate_password_field()
        if password_field is None:
            log_func("❌ 输入前重新定位密码框失败")
            screenshot_func(driver, "password_field_relocate_fail")
            return False
        password_field.click()
        time.sleep(0.5)
        password_field.send_keys(wifi_password)
        time.sleep(1)
        log_func("✅ 密码输入完成")
        return True
    except Exception as e:
        log_func(f"❌ 密码输入失败: {e}")
        screenshot_func(driver, "password_input_fail")
        return False


def _hide_keyboard_android(driver: Any, log_func: Callable[[str], None] = _log_default) -> None:
    """输入密码后收起键盘。"""
    log_func("⌨️ 收起键盘...")
    try:
        driver.hide_keyboard()
        log_func("✅ hide_keyboard 收起键盘成功")
        time.sleep(1)
        return
    except Exception as e:
        log_func(f"⚠️ hide_keyboard 失败: {e}，尝试按返回键收起")
    try:
        driver.press_keycode(4)  # KEYCODE_BACK
        time.sleep(1)
        log_func("✅ 已按返回键尝试收起键盘")
    except Exception as e:
        log_func(f"⚠️ 收起键盘失败，继续后续步骤: {e}")


def _click_checkbox_and_next_android(
    driver: Any,
    log_func: Callable[[str], None],
    screenshot_func: Callable[[Any, str], None],
) -> bool:
    """
    对齐 iOS set up wifi 后的操作：
    勾选 checkbox → Next → 再勾选 → 再 Next
    """
    checkbox_xp = '//android.widget.ImageView[@content-desc="checkbox"]'
    next_xp = '//android.widget.Button'

    def _click_checkbox(round_no: int) -> bool:
        try:
            log_func(f"☑️ 第{round_no}次勾选 checkbox...")
            checkbox = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, checkbox_xp))
            )
            checkbox.click()
            log_func(f"✅ 第{round_no}次已勾选 checkbox")
            time.sleep(1)
            return True
        except Exception as e:
            log_func(f"❌ 第{round_no}次勾选 checkbox 失败: {e}")
            screenshot_func(driver, f"android_checkbox_fail_{round_no}")
            return False

    def _click_next(round_no: int) -> bool:
        try:
            log_func(f"➡️ 第{round_no}次点击 Next（//android.widget.Button）...")
            next_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, next_xp))
            )
            next_btn.click()
            log_func(f"✅ 第{round_no}次点击 Next 成功")
            time.sleep(2)
            return True
        except Exception as e:
            log_func(f"❌ 第{round_no}次点击 Next 失败: {e}")
            screenshot_func(driver, f"android_next_fail_{round_no}")
            return False

    if not _click_checkbox(1):
        return False
    if not _click_next(1):
        return False
    if not _click_checkbox(2):
        return False
    if not _click_next(2):
        return False

    log_func("✅ 两轮（勾选 checkbox + Next）完成，进入配网进展页")
    return True


def _click_next_button_android(driver: Any, log_func: Callable[[str], None] = _log_default) -> bool:
    """点击 Android Next 按钮（参考 M1 Pro 扫码配网的操作步骤）"""
    log_func("✅ 点击next按钮确认WiFi设置...")
    try:
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
        )
        next_button.click()
        time.sleep(5)  # 参考 M1 Pro：等待 5 秒（原为 2 秒）
        log_func("✅ WiFi设置完成")
        return True
    except Exception as e:
        log_func(f"❌ 点击Next按钮失败: {e}")
        return False


# ==================== 统一接口 ====================

def perform_wifi_setup(
    driver: Any,
    wifi_name: str,
    wifi_password: str,
    platform: str,
    log_func: Callable[[str], None] = _log_default,
    screenshot_func: Callable[[Any, str], None] = _screenshot_default,
    wait_for_wifi_setup_page: Optional[Callable] = None,
    wifi_aliases: Optional[list] = None,
) -> bool:
    """
    整体 WiFi 设置步骤（从进入 setup_wifi 页面后到点击 next）
    
    Args:
        driver: Appium WebDriver 实例
        wifi_name: WiFi 名称（SSID）
        wifi_password: WiFi 密码
        platform: 平台类型，"ios" 或 "android"
        log_func: 日志输出函数
        screenshot_func: 截图函数
        wait_for_wifi_setup_page: Android 专用，用于检测是否回到 WiFi 设置页面的函数
        wifi_aliases: 可选 SSID 别名列表（大小写不敏感匹配）
    
    Returns:
        bool: 是否成功完成 WiFi 设置
    """
    if platform.lower() == "ios":
        return _perform_wifi_setup_ios(driver, wifi_name, wifi_password, log_func, screenshot_func)
    elif platform.lower() == "android":
        return _perform_wifi_setup_android(
            driver,
            wifi_name,
            wifi_password,
            log_func,
            screenshot_func,
            wait_for_wifi_setup_page,
            wifi_aliases=wifi_aliases,
        )
    else:
        log_func(f"❌ 不支持的平台类型: {platform}")
        return False


def _perform_wifi_setup_ios(
    driver: Any,
    wifi_name: str,
    wifi_password: str,
    log_func: Callable[[str], None],
    screenshot_func: Callable[[Any, str], None],
) -> bool:
    """iOS WiFi 设置流程"""
    # 1. 进入系统 WiFi 列表页面
    if not _enter_wifi_list_page_ios(driver, log_func, screenshot_func):
        return False
    
    # 2. 在系统 WiFi 列表中选择 WiFi
    if not _select_wifi_in_settings_ios(driver, wifi_name, log_func, screenshot_func):
        return False
    
    # 3. 返回 App 的 WiFi 密码输入页面
    if not _back_to_app_wifi_page_ios(driver, log_func):
        return False
    
    # 4. 输入 WiFi 密码
    if not _input_wifi_password_ios(driver, wifi_password, log_func, screenshot_func):
        return False

    # 5. 关闭键盘：点击 Done
    log_func("⌨️ 输入密码后点击 Done 收起键盘...")

    done_clicked = False
    done_selectors = [
        '//XCUIElementTypeButton[@name="Done"]',
        '//XCUIElementTypeButton[contains(@name,"Done")]',
        '//XCUIElementTypeButton[@name="完成"]',
        '//XCUIElementTypeButton[contains(@name,"完成")]',
    ]

    for i, xp in enumerate(done_selectors, 1):
        try:
            log_func(f"🔍 尝试 Done 按钮选择器 {i}: {xp}")
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            if btn.is_displayed():
                btn.click()
                log_func(f"✅ 点击 Done 按钮成功（选择器 {i}）")
                time.sleep(2)
                done_clicked = True
                break
        except Exception as e:
            log_func(f"  ⚠️ Done 按钮选择器 {i} 失败: {e}")
            continue

    if not done_clicked:
        log_func("⚠️ 未找到 Done 按钮，尝试使用 hide_keyboard 隐藏键盘")
        try:
            driver.hide_keyboard()
            log_func("✅ 使用 hide_keyboard 隐藏键盘成功")
            time.sleep(2)
        except Exception as e:
            log_func(f"⚠️ hide_keyboard 也失败: {e}，继续后续步骤")

    # 6~9. Done 后：勾选 action sheet un sel → Next → 再勾选 → 再 Next，进入配网进展页
    checkbox_xp = '//XCUIElementTypeButton[@name="action sheet un sel"]'
    next_xp = '//XCUIElementTypeButton[@name="Next"]'

    def _click_checkbox(round_no: int) -> bool:
        try:
            log_func(f"☑️ 第{round_no}次勾选 action sheet un sel...")
            checkbox = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, checkbox_xp))
            )
            checkbox.click()
            log_func(f"✅ 第{round_no}次已勾选 action sheet un sel")
            time.sleep(1)
            return True
        except Exception as e:
            log_func(f"❌ 第{round_no}次勾选 action sheet un sel 失败: {e}")
            screenshot_func(driver, f"action_sheet_un_sel_fail_{round_no}")
            return False

    def _click_next(round_no: int) -> bool:
        try:
            log_func(f"➡️ 第{round_no}次点击 Next...")
            next_btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, next_xp))
            )
            next_btn.click()
            log_func(f"✅ 第{round_no}次点击 Next 成功")
            time.sleep(2)
            return True
        except Exception as e:
            log_func(f"❌ 第{round_no}次点击 Next 失败: {e}")
            screenshot_func(driver, f"next_btn_fail_{round_no}")
            return False

    if not _click_checkbox(1):
        return False
    if not _click_next(1):
        return False
    if not _click_checkbox(2):
        return False
    if not _click_next(2):
        return False

    log_func("✅ Done 后两轮（勾选 action sheet un sel + Next）完成，进入配网进展页")
    return True


def _perform_wifi_setup_android(
    driver: Any,
    wifi_name: str,
    wifi_password: str,
    log_func: Callable[[str], None],
    screenshot_func: Callable[[Any, str], None],
    wait_for_wifi_setup_page: Optional[Callable] = None,
    wifi_aliases: Optional[list] = None,
) -> bool:
    """
    Android set up wifi 流程（对齐用户步骤 / 参考 iOS）：
      1) 点击 //android.view.View[@content-desc="switch"] 切换选择的路由器
         —— 必须确认已离开 Set Up Wi-Fi、进入系统列表后才继续
      2) 在系统列表中选择 wifi_name（来自 device_config.json，支持 aliases）
      3) 返回 App 后点击密码框并输入对应路由器密码
      4) 收起键盘
      5) 勾选 checkbox → Next → 再勾选 → 再 Next（对齐 iOS）
    """
    app_package = driver.capabilities.get('appPackage')

    # 1. 点击 switch，并验证真正进入系统 WiFi 页（此前误报「已进入」导致在 App 页空滚）
    if not _enter_system_wifi_picker_android(driver, app_package, log_func, screenshot_func):
        return False

    # 2. 在系统 WiFi 列表中选择 device_config 中的路由器名
    if not _select_wifi_in_settings_android(
        driver, wifi_name, log_func, screenshot_func, wifi_aliases=wifi_aliases
    ):
        return False

    # 3. 返回 App 的 set up wifi 页面
    if not _back_to_app_wifi_page_android(driver, app_package, log_func, wait_for_wifi_setup_page):
        log_func("⚠️ 返回 WiFi 设置页面失败，但继续尝试输入密码")

    # 4. 点击密码框并输入对应路由器密码（优先 ScrollView/.../EditText）
    log_func(
        f'🔑 点击密码框 //android.widget.ScrollView/android.view.View[2]/android.widget.EditText '
        f'并输入路由器 [{wifi_name}] 密码'
    )
    if not _input_wifi_password_android(driver, wifi_password, log_func, screenshot_func):
        return False

    # 5. 收起键盘
    _hide_keyboard_android(driver, log_func)

    # 6. 对齐 iOS：勾选 checkbox + Next，共两轮
    if not _click_checkbox_and_next_android(driver, log_func, screenshot_func):
        return False

    return True


if __name__ == "__main__":
    # 测试代码
    print("🚀 WiFi 选择模块测试")
    print("此模块需要在实际的 Appium 环境中测试")
