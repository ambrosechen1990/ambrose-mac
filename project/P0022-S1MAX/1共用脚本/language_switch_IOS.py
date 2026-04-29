#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语言切换功能模块

3功能：
- 支持iOS和Android平台的语言切换
- 支持多种语言：中文、English、Français、Italiano、Deutsch、Español、Português
- 切换语言后自动重启APP

使用示例：
    # 方式1：直接导入
    from copywriting.comman.language_switch import switch_language

    # 方式2：从comman模块导入（如果copywriting/comman/__init__.py已导出）
    from copywriting.comman import switch_language

    # iOS
    switch_language(driver, "English", platform="iOS")

    # Android
    switch_language(driver, "中文", platform="Android")
"""

import time
import os
from typing import Optional, Dict, List
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# 语言配置：语言名称 -> 单元格索引（从2开始，因为第1个可能是标题）
LANGUAGE_CONFIG: Dict[str, Dict[str, int]] = {
    "iOS": {
        "English": 2,
        "Français": 3,
        "Italiano": 4,
        "Deutsch": 5,
        "Español": 6,
        "Português": 7,
        "Čeština": 8,
        "中文": 9,
    },
    "Android": {
        "English": 2,
        "Français": 3,
        "Italiano": 4,
        "Deutsch": 5,
        "Español": 6,
        "Português": 7,
        "Čeština": 8,
        "中文": 9,
    }
}

# 确认按钮的多语言文本（根据当前语言可能显示不同的文字）
CONFIRM_BUTTON_TEXTS = [
    "确认",  # 中文
    "Confirm",  # English
    "Confirmer",  # Français
    "Conferma",  # Italiano
    "Bestätigen",  # Deutsch
    "Confirmar",  # Español
    "Confirmar",  # Português
    "Potvrdit",  # Čeština
    "OK",  # 通用
    "确定",  # 中文变体
]

# "查看更多"按钮的多语言文本
VIEW_MORE_BUTTON_TEXTS = {
    "中文": "查看更多",
    "English": "View More",
    "Français": "Voir plus",
    "Italiano": "Vedi altro",
    "Deutsch": "Mehr anzeigen",
    "Español": "Ver más",
    "Português": "Ver mais",
}

# "查看更多"按钮的XPath选择器（iOS）
VIEW_MORE_SELECTORS_IOS = [
    # 中文
    '//XCUIElementTypeStaticText[@name="查看更多"]',
    '//XCUIElementTypeButton[@name="查看更多"]',
    '//XCUIElementTypeStaticText[contains(@name,"查看更多")]',
    # 英语
    '//XCUIElementTypeStaticText[@name="View More"]',
    '//XCUIElementTypeButton[@name="View More"]',
    '//XCUIElementTypeStaticText[contains(@name,"View More")]',
    # 法语
    '//XCUIElementTypeStaticText[@name="Voir plus"]',
    '//XCUIElementTypeButton[@name="Voir plus"]',
    '//XCUIElementTypeStaticText[contains(@name,"Voir plus")]',
    # 意大利语
    '//XCUIElementTypeStaticText[@name="Vedi altro"]',
    '//XCUIElementTypeButton[@name="Vedi altro"]',
    '//XCUIElementTypeStaticText[contains(@name,"Vedi altro")]',
    # 德语
    '//XCUIElementTypeStaticText[@name="Mehr anzeigen"]',
    '//XCUIElementTypeButton[@name="Mehr anzeigen"]',
    '//XCUIElementTypeStaticText[contains(@name,"Mehr anzeigen")]',
    # 西班牙语
    '//XCUIElementTypeStaticText[@name="Ver más"]',
    '//XCUIElementTypeButton[@name="Ver más"]',
    '//XCUIElementTypeStaticText[contains(@name,"Ver más")]',
    # 葡萄牙语
    '//XCUIElementTypeStaticText[@name="Ver mais"]',
    '//XCUIElementTypeButton[@name="Ver mais"]',
    '//XCUIElementTypeStaticText[contains(@name,"Ver mais")]',
]

# "查看更多"按钮的XPath选择器（Android）
VIEW_MORE_SELECTORS_ANDROID = [
    # 中文
    '//android.widget.TextView[@text="查看更多"]',
    '//android.widget.Button[@text="查看更多"]',
    '//android.view.View[@text="查看更多"]',
    # 英语
    '//android.widget.TextView[@text="View More"]',
    '//android.widget.Button[@text="View More"]',
    '//android.view.View[@text="View More"]',
    # 法语
    '//android.widget.TextView[@text="Voir plus"]',
    '//android.widget.Button[@text="Voir plus"]',
    '//android.view.View[@text="Voir plus"]',
    # 意大利语
    '//android.widget.TextView[@text="Vedi altro"]',
    '//android.widget.Button[@text="Vedi altro"]',
    '//android.view.View[@text="Vedi altro"]',
    # 德语
    '//android.widget.TextView[@text="Mehr anzeigen"]',
    '//android.widget.Button[@text="Mehr anzeigen"]',
    '//android.view.View[@text="Mehr anzeigen"]',
    # 西班牙语
    '//android.widget.TextView[@text="Ver más"]',
    '//android.widget.Button[@text="Ver más"]',
    '//android.view.View[@text="Ver más"]',
    # 葡萄牙语
    '//android.widget.TextView[@text="Ver mais"]',
    '//android.widget.Button[@text="Ver mais"]',
    '//android.view.View[@text="Ver mais"]',
]


def wait_and_click(driver, xpath_list: List[str], wait_time: int = 6, desc: str = "") -> bool:
    """
    依次尝试多个 xpath，找到即点击（优化版：快速失败）

    Args:
        driver: Appium WebDriver
        xpath_list: XPath选择器列表
        wait_time: 等待时间（秒），仅用于第一个选择器
        desc: 描述信息（用于日志）

    Returns:
        bool: 是否成功点击
    """
    # 先快速尝试所有选择器（不等待），找到即点击
    for xp in xpath_list:
        try:
            elements = driver.find_elements(AppiumBy.XPATH, xp)
            for el in elements:
                try:
                    if el.is_displayed() and el.is_enabled():
                        el.click()
                        if desc:
                            print(f"✅ 点击{desc}: {xp}")
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    # 如果快速查找失败，对第一个选择器使用等待（仅等待一次）
    if xpath_list:
        try:
            el = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xpath_list[0]))
            )
            if el.is_displayed() and el.is_enabled():
                el.click()
                if desc:
                    print(f"✅ 点击{desc}: {xpath_list[0]}")
                return True
        except Exception:
            pass

    return False


def switch_language_ios(driver, target_language: str) -> bool:
    """
    iOS平台语言切换

    Args:
        driver: Appium WebDriver
        target_language: 目标语言（如 "English", "中文", "Français" 等）

    Returns:
        bool: 是否切换成功
    """
    try:
        print(f"🌐 开始切换语言到: {target_language}")

        # 步骤0: 先重置APP到首页，确保能够找到mine按钮
        print("🔄 重置APP到首页...")
        caps = getattr(driver, "capabilities", {}) or {}
        bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")

        if bundle_id:
            # 重试机制：最多重试3次
            max_retries = 3
            reset_success = False
            for attempt in range(max_retries):
                try:
                    driver.terminate_app(bundle_id)
                    time.sleep(2)
                    driver.activate_app(bundle_id)
                    time.sleep(3)

                    # 检查是否在首页
                    home_xpaths = [
                        '//XCUIElementTypeButton[@name="home add"]',
                        '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
                        '//XCUIElementTypeStaticText[contains(@name,"设备")]',
                    ]
                    for xp in home_xpaths:
                        try:
                            elem = driver.find_element(AppiumBy.XPATH, xp)
                            if elem.is_displayed():
                                print(f"✅ 确认在首页: {xp}")
                                reset_success = True
                                break
                        except Exception:
                            continue

                    if reset_success:
                        break
                except Exception as e:
                    error_msg = str(e)
                    # 检测是否是应用正在安装/卸载的错误
                    is_app_busy = (
                            "installing or uninstalling" in error_msg.lower() or
                            "cannot be launched" in error_msg.lower() or
                            "busy" in error_msg.lower() or
                            "RequestDenied" in error_msg
                    )

                    if is_app_busy and attempt < max_retries - 1:
                        # 应用正在安装/卸载，等待后重试
                        wait_time = (attempt + 1) * 5  # 递增等待时间：5秒、10秒、15秒
                        print(f"⚠️ 应用正在安装/卸载中，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    elif attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3
                        print(
                            f"⚠️ 重置APP失败，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {error_msg[:100]}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"⚠️ 重置APP失败: {error_msg[:200]}，继续尝试切换语言")

            if not reset_success:
                print("⚠️ 重置APP未成功，但继续尝试切换语言")

        # 步骤1: 点击 mine 按钮
        if not wait_and_click(
                driver,
                ['//XCUIElementTypeButton[@name="mine"]'],
                desc="mine按钮"
        ):
            print("❌ 点击mine按钮失败")
            return False
        time.sleep(1.5)

        # 步骤2: 点击"通用"（第2个Cell）
        # 注意：通用按钮的文字可能根据当前语言变化，所以优先使用索引和箭头图标
        general_selectors = [
            '(//XCUIElementTypeImage[@name="CommonArrow"])[2]',  # 优先使用箭头图标（第2个）
            '//XCUIElementTypeTable/XCUIElementTypeCell[2]',
            '//XCUIElementTypeStaticText[@name="通用"]/ancestor::XCUIElementTypeCell[1]',
            '//XCUIElementTypeStaticText[@name="General"]/ancestor::XCUIElementTypeCell[1]',
        ]
        if not wait_and_click(driver, general_selectors, desc="通用"):
            print("❌ 点击通用失败")
            return False
        time.sleep(1.5)

        # 步骤3: 点击"语言设置"（按照流程图：多语言栏点击第2个CommonArrow）
        # 注意：根据流程图，在通用页面应该点击第2个CommonArrow进入语言设置页面
        language_setting_selectors = [
            '(//XCUIElementTypeImage[@name="CommonArrow"])[2]',  # 优先使用箭头图标（第2个）- 按照流程图
            '//XCUIElementTypeTable/XCUIElementTypeCell[2]',
            '//XCUIElementTypeStaticText[@name="语言设置"]/ancestor::XCUIElementTypeCell[1]',
            '//XCUIElementTypeStaticText[@name="Language"]/ancestor::XCUIElementTypeCell[1]',
            '//XCUIElementTypeStaticText[@name="Language Settings"]/ancestor::XCUIElementTypeCell[1]',
        ]
        if not wait_and_click(driver, language_setting_selectors, desc="语言设置"):
            print("❌ 点击语言设置失败")
            # 添加调试信息：查看当前页面的所有CommonArrow和可见文本
            try:
                arrows = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeImage[@name="CommonArrow"]')
                print(f"    💡 当前页面找到 {len(arrows)} 个CommonArrow")
                for i, arrow in enumerate(arrows[:5], 1):
                    try:
                        if arrow.is_displayed():
                            # 获取箭头所在的cell文本
                            try:
                                cell = arrow.find_element(AppiumBy.XPATH, './ancestor::XCUIElementTypeCell[1]')
                                cell_text = cell.get_attribute("name") or cell.text or ""
                                print(f"    💡 CommonArrow[{i}]: {cell_text[:50]}")
                            except:
                                print(f"    💡 CommonArrow[{i}]: (无法获取文本)")
                    except:
                        pass

                # 查看所有可见的StaticText
                texts = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeStaticText')
                visible_texts = []
                for t in texts:
                    try:
                        if t.is_displayed():
                            text = t.get_attribute("name") or t.text or ""
                            if text and text.strip():
                                visible_texts.append(text.strip())
                    except:
                        continue
                print(f"    💡 当前页面可见文本（前10个）: {visible_texts[:10]}")
            except Exception as e:
                print(f"    ⚠️ 调试信息获取失败: {e}")
            return False
        time.sleep(2)

        # 步骤4: 等待语言设置页面完全加载
        print("⏳ 等待语言设置页面加载...")
        time.sleep(2)

        # 添加详细的调试信息：查看语言设置页面的所有元素
        try:
            # 尝试多种可能的页面结构
            cells = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeTable/XCUIElementTypeCell')
            print(f"    💡 语言设置页面找到 {len(cells)} 个Cell (Table结构)")

            # 如果找不到Cell，尝试查找其他可能的元素类型
            if len(cells) == 0:
                # 尝试查找所有StaticText
                all_texts = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeStaticText')
                visible_texts = []
                for t in all_texts:
                    try:
                        if t.is_displayed():
                            text = t.get_attribute("name") or t.text or ""
                            if text and text.strip():
                                visible_texts.append(text.strip())
                    except:
                        continue
                print(f"    💡 页面找到 {len(visible_texts)} 个可见文本元素")
                print(f"    💡 可见文本（前15个）: {visible_texts[:15]}")

                # 尝试查找所有可点击的元素
                clickable_elements = driver.find_elements(AppiumBy.XPATH,
                                                          '//XCUIElementTypeButton | //XCUIElementTypeCell | //XCUIElementTypeOther')
                clickable_texts = []
                for el in clickable_elements:
                    try:
                        if el.is_displayed() and el.get_attribute("enabled") != "false":
                            text = el.get_attribute("name") or el.text or ""
                            if text and text.strip():
                                clickable_texts.append(text.strip())
                    except:
                        continue
                print(f"    💡 可点击元素文本（前15个）: {clickable_texts[:15]}")
            else:
                # 如果找到了Cell，显示它们的文本
                for i, cell in enumerate(cells[:10], 1):  # 显示前10个
                    try:
                        if cell.is_displayed():
                            cell_text = cell.get_attribute("name") or cell.text or ""
                            # 尝试获取cell内的所有文本
                            try:
                                texts = cell.find_elements(AppiumBy.XPATH, './/XCUIElementTypeStaticText')
                                all_texts = []
                                for t in texts:
                                    if t.is_displayed():
                                        t_text = t.get_attribute("name") or t.text or ""
                                        if t_text and t_text.strip():
                                            all_texts.append(t_text.strip())
                                if all_texts:
                                    cell_text = " / ".join(all_texts)
                            except:
                                pass
                            if cell_text and cell_text.strip():
                                print(f"    💡 Cell[{i}]: {cell_text[:60]}")
                    except:
                        pass
        except Exception as e:
            print(f"    ⚠️ 调试信息获取失败: {e}")

        # 获取目标语言的单元格索引
        if target_language not in LANGUAGE_CONFIG["iOS"]:
            print(f"❌ 不支持的语言: {target_language}")
            print(f"💡 支持的语言: {list(LANGUAGE_CONFIG['iOS'].keys())}")
            return False

        cell_index = LANGUAGE_CONFIG["iOS"][target_language]

        # 构建多种可能的选择器（按优先级排序）
        language_selectors = [
            # 优先：通过文本直接查找（最可靠）
            f'//XCUIElementTypeStaticText[@name="{target_language}"]/ancestor::XCUIElementTypeCell[1]',
            f'//XCUIElementTypeCell[.//XCUIElementTypeStaticText[@name="{target_language}"]]',
            f'//XCUIElementTypeButton[@name="{target_language}"]',
            f'//XCUIElementTypeStaticText[@name="{target_language}"]/ancestor::XCUIElementTypeButton[1]',
            # 备用：使用索引（如果页面结构是Table/Cell）
            f'//XCUIElementTypeTable/XCUIElementTypeCell[{cell_index}]',
            # 备用：通过包含文本查找
            f'//XCUIElementTypeStaticText[contains(@name,"{target_language}")]/ancestor::XCUIElementTypeCell[1]',
            f'//XCUIElementTypeCell[.//XCUIElementTypeStaticText[contains(@name,"{target_language}")]]',
        ]

        if not wait_and_click(driver, language_selectors, wait_time=5, desc=f"语言选项-{target_language}"):
            print(f"❌ 点击语言选项 {target_language} 失败 (尝试索引 {cell_index})")
            # 再次尝试获取页面信息用于调试
            try:
                all_elements = driver.find_elements(AppiumBy.XPATH,
                                                    '//XCUIElementTypeStaticText | //XCUIElementTypeButton')
                matching_elements = []
                for el in all_elements:
                    try:
                        if el.is_displayed():
                            text = el.get_attribute("name") or el.text or ""
                            if target_language in text or text in target_language:
                                matching_elements.append(text)
                    except:
                        continue
                if matching_elements:
                    print(f"    💡 找到包含 '{target_language}' 的元素: {matching_elements}")
                else:
                    print(f"    💡 未找到包含 '{target_language}' 的元素")
            except Exception as e:
                print(f"    ⚠️ 最终调试信息获取失败: {e}")
            return False
        time.sleep(1.5)

        # 步骤5: 点击确认按钮（注意：确认按钮的文字会根据当前语言变化）
        confirm_clicked = False
        for confirm_text in CONFIRM_BUTTON_TEXTS:
            confirm_xpaths = [
                f'//XCUIElementTypeButton[@name="{confirm_text}"]',
                f'//XCUIElementTypeButton[contains(@name,"{confirm_text}")]',
            ]
            if wait_and_click(driver, confirm_xpaths, wait_time=3, desc=f"确认按钮({confirm_text})"):
                confirm_clicked = True
                break

        if not confirm_clicked:
            # 尝试通用按钮选择器
            generic_confirm_xpaths = [
                '//XCUIElementTypeButton[contains(@name,"确认")]',
                '//XCUIElementTypeButton[contains(@name,"Confirm")]',
                '//XCUIElementTypeButton[contains(@name,"OK")]',
                '//XCUIElementTypeButton[last()]',  # 最后一个按钮通常是确认
            ]
            if not wait_and_click(driver, generic_confirm_xpaths, wait_time=3, desc="确认按钮(通用)"):
                print("❌ 点击确认按钮失败")
                return False

        time.sleep(2)

        # 步骤6: 重启APP（使用之前获取的bundle_id）
        print("🔄 语言切换完成，重启APP...")
        if bundle_id:
            # 重试机制：最多重试3次
            max_retries = 3
            restart_success = False
            for attempt in range(max_retries):
                try:
                    driver.terminate_app(bundle_id)
                    time.sleep(2)
                    driver.activate_app(bundle_id)
                    time.sleep(3)
                    print("✅ APP已重启")
                    restart_success = True
                    break
                except Exception as e:
                    error_msg = str(e)
                    # 检测是否是应用正在安装/卸载的错误
                    is_app_busy = (
                            "installing or uninstalling" in error_msg.lower() or
                            "cannot be launched" in error_msg.lower() or
                            "busy" in error_msg.lower() or
                            "RequestDenied" in error_msg
                    )

                    if is_app_busy and attempt < max_retries - 1:
                        # 应用正在安装/卸载，等待后重试
                        wait_time = (attempt + 1) * 5  # 递增等待时间：5秒、10秒、15秒
                        print(f"⚠️ 应用正在安装/卸载中，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    elif attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3
                        print(
                            f"⚠️ 重启APP失败，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {error_msg[:100]}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"⚠️ 重启APP失败: {error_msg[:200]}")
                        print("💡 请手动重启APP以确保语言切换生效")

            if not restart_success:
                print("⚠️ 重启APP未成功，但语言切换可能已生效")
        else:
            print("⚠️ 无法获取bundleId，请手动重启APP")

        print(f"✅ 语言切换成功: {target_language}")
        return True

    except Exception as e:
        print(f"❌ 语言切换失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def switch_language_android(driver, target_language: str) -> bool:
    """
    Android平台语言切换

    Args:
        driver: Appium WebDriver
        target_language: 目标语言（如 "English", "中文", "Français" 等）

    Returns:
        bool: 是否切换成功
    """
    try:
        print(f"🌐 开始切换语言到: {target_language}")

        # 步骤0: 先重置APP到首页，确保能够找到mine按钮
        print("🔄 重置APP到首页...")
        caps = getattr(driver, "capabilities", {}) or {}
        app_package = caps.get("appPackage") or os.environ.get("ANDROID_APP_PACKAGE")

        if app_package:
            try:
                driver.terminate_app(app_package)
                time.sleep(2)
                driver.activate_app(app_package)
                time.sleep(3)

                # 检查是否在首页（快速检查，不等待）
                home_xpaths = [
                    '//android.widget.Button[@content-desc="home add"]',
                    '//android.widget.TextView[contains(@text,"Sora")]',
                    '//android.widget.TextView[contains(@text,"设备")]',
                ]
                for xp in home_xpaths:
                    try:
                        elements = driver.find_elements(AppiumBy.XPATH, xp)
                        for elem in elements:
                            if elem.is_displayed():
                                print(f"✅ 确认在首页: {xp}")
                                break
                        else:
                            continue
                        break
                    except Exception:
                        continue
            except Exception as e:
                print(f"⚠️ 重置APP失败: {e}，继续尝试切换语言")

        # 步骤1: 点击 More/我的 按钮
        # Android 上，中文环境显示"我的"，英文环境显示"More"
        # 优先使用当前 APP 实际使用的 Compose 布局路径（不依赖文本，最可靠）
        # 注意：More按钮是View[2]，根据日志显示成功路径是 View[2]/View[2]
        mine_selectors = [
            # 最新 Compose 路径（根据日志，成功路径是 View[2]/View[2]）
            '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/'
            'android.view.View/android.view.View/android.view.View[2]/android.view.View[2]',
            # 尝试View[3]（More按钮位置）
            '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/'
            'android.view.View/android.view.View/android.view.View[3]/android.view.View[2]',
            # 尝试View[4]（如果View[3]不是）
            '//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/'
            'android.view.View/android.view.View/android.view.View[4]/android.view.View[2]',
            # 另一种Compose路径（View[2]）
            '//androidx.compose.ui.platform.ComposeView/android.view.View/'
            'android.view.View/android.view.View/android.view.View[2]/'
            'android.view.View/android.view.View[2]',
            # 通过 content-desc（多语言支持 - 优先 More/我的）
            '//android.view.View[@content-desc="More"]',  # 英文
            '//android.view.View[@content-desc="我的"]',  # 中文
            '//android.view.View[@content-desc="Me"]',
            '//android.view.View[@content-desc="Mine"]',
            '//android.view.View[@content-desc="Moi"]',  # 法语
            '//android.view.View[@content-desc="Yo"]',  # 西班牙语
            '//android.view.View[@content-desc="Ich"]',  # 德语
            '//android.view.View[@content-desc="Io"]',  # 意大利语
            '//android.view.View[@content-desc="Eu"]',  # 葡萄牙语
            '//android.widget.Button[@content-desc="More"]',  # 英文
            '//android.widget.Button[@content-desc="我的"]',  # 中文
            '//android.widget.Button[@content-desc="Me"]',
            '//android.widget.Button[@content-desc="Mine"]',
            # 通过文本（多语言支持）
            '//android.widget.TextView[@text="More"]',  # 英文
            '//android.widget.TextView[@text="我的"]',  # 中文
            '//android.widget.TextView[@text="Me"]',
            '//android.widget.TextView[@text="Mine"]',
            '//android.widget.TextView[@text="Moi"]',  # 法语
            '//android.widget.TextView[@text="Yo"]',  # 西班牙语
            '//android.widget.TextView[@text="Ich"]',  # 德语
            '//android.widget.TextView[@text="Io"]',  # 意大利语
            '//android.widget.TextView[@text="Eu"]',  # 葡萄牙语
            # 通过部分匹配
            '//android.view.View[contains(@content-desc,"More")]',
            '//android.view.View[contains(@content-desc,"我的")]',
            '//android.view.View[contains(@content-desc,"Me")]',
            '//android.view.View[contains(@content-desc,"Mine")]',
            '//android.widget.TextView[contains(@text,"More")]',
            '//android.widget.TextView[contains(@text,"我的")]',
            '//android.widget.TextView[contains(@text,"Me")]',
            '//android.widget.TextView[contains(@text,"Mine")]',
            # 通过resource-id（如果有）
            '//android.view.View[contains(@resource-id,"more")]',
            '//android.view.View[contains(@resource-id,"mine")]',
            '//android.widget.Button[contains(@resource-id,"more")]',
            '//android.widget.Button[contains(@resource-id,"mine")]',
        ]
        if not wait_and_click(driver, mine_selectors, wait_time=3, desc="More/我的按钮"):  # 增加等待时间
            print("❌ 点击More/我的按钮失败")
            # 尝试获取页面信息用于调试
            try:
                # 查找所有可点击元素
                elements = driver.find_elements(AppiumBy.XPATH, "//*[@clickable='true']")
                print(f"    💡 找到 {len(elements)} 个可点击元素")
                for i, el in enumerate(elements[:10]):  # 显示前10个
                    try:
                        text = el.text or el.get_attribute("contentDescription") or el.get_attribute(
                            "content-desc") or ""
                        if text:
                            print(f"    💡 元素{i + 1}: {text[:50]}")
                    except:
                        pass

                # 查找所有ComposeView下的View元素
                compose_views = driver.find_elements(AppiumBy.XPATH,
                                                     '//androidx.compose.ui.platform.ComposeView//android.view.View')
                print(f"    💡 找到 {len(compose_views)} 个ComposeView下的View元素")
                for i, view in enumerate(compose_views[:10]):  # 显示前10个
                    try:
                        if view.is_displayed():
                            text = view.get_attribute("contentDescription") or view.get_attribute(
                                "content-desc") or view.text or ""
                            if text:
                                print(f"    💡 ComposeView View[{i + 1}]: {text[:50]}")
                    except:
                        pass
            except Exception as e:
                print(f"    ⚠️ 调试信息获取失败: {e}")
            return False
        time.sleep(1)  # 减少等待时间

        # 步骤2: 点击"通用"（第2个Cell）
        # Android中可能是不同的元素类型
        # 优先使用索引位置（不依赖文本，更可靠）
        general_selectors = [
            '//android.widget.ListView/android.widget.LinearLayout[2]',
            '//androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup[2]',
            '//android.widget.TableLayout/android.widget.TableRow[2]',
            '//androidx.recyclerview.widget.RecyclerView//android.view.ViewGroup[2]',
            '//android.widget.LinearLayout[2]',
        ]
        if not wait_and_click(driver, general_selectors, wait_time=2, desc="通用(索引)"):  # 减少等待时间
            # 尝试通过文本查找（支持多语言）
            general_text_selectors = [
                # 中文
                '//android.widget.TextView[@text="通用"]',
                '//android.widget.TextView[contains(@text,"通用")]',
                # 英文
                '//android.widget.TextView[@text="General"]',
                '//android.widget.TextView[contains(@text,"General")]',
                # 法语
                '//android.widget.TextView[@text="Généralités"]',
                '//android.widget.TextView[contains(@text,"Généralités")]',
                '//android.widget.TextView[contains(@text,"Général")]',
                # 西班牙语
                '//android.widget.TextView[@text="General"]',
                '//android.widget.TextView[contains(@text,"General")]',
                # 德语
                '//android.widget.TextView[@text="Allgemein"]',
                '//android.widget.TextView[contains(@text,"Allgemein")]',
                # 意大利语
                '//android.widget.TextView[@text="Generale"]',
                '//android.widget.TextView[contains(@text,"Generale")]',
                # 葡萄牙语
                '//android.widget.TextView[@text="Geral"]',
                '//android.widget.TextView[contains(@text,"Geral")]',
                # 通用匹配（包含"通用"、"General"等关键词）
                '//android.widget.TextView[contains(@text,"通用") or contains(@text,"General") or contains(@text,"Général") or contains(@text,"Allgemein") or contains(@text,"Generale") or contains(@text,"Geral")]',
            ]
            if not wait_and_click(driver, general_text_selectors, wait_time=2, desc="通用(文本)"):  # 减少等待时间
                print("❌ 点击通用失败")
                # 尝试查找所有可见的TextView，用于调试
                try:
                    all_texts = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView')
                    visible_texts = []
                    for tv in all_texts:
                        try:
                            text = tv.get_attribute("text") or tv.get_attribute("content-desc") or ""
                            if text and tv.is_displayed():
                                visible_texts.append(text)
                        except Exception:
                            continue
                    print(f"💡 当前页面可见的文本: {visible_texts[:10]}")  # 只显示前10个
                except Exception:
                    pass
                return False
        time.sleep(1)  # 减少等待时间

        # 步骤3: 点击"语言设置"（第2个Cell）
        # 优先使用索引位置（不依赖文本，更可靠）
        language_setting_selectors = [
            '//android.widget.ListView/android.widget.LinearLayout[2]',
            '//androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup[2]',
            '//android.widget.TableLayout/android.widget.TableRow[2]',
            '//androidx.recyclerview.widget.RecyclerView//android.view.ViewGroup[2]',
            '//android.widget.LinearLayout[2]',
        ]
        if not wait_and_click(driver, language_setting_selectors, wait_time=2, desc="语言设置(索引)"):  # 减少等待时间
            # 尝试通过文本查找（支持多语言）
            language_setting_text_selectors = [
                # 中文
                '//android.widget.TextView[@text="语言设置"]',
                '//android.widget.TextView[contains(@text,"语言")]',
                # 英文
                '//android.widget.TextView[@text="Language"]',
                '//android.widget.TextView[@text="Language Settings"]',
                '//android.widget.TextView[contains(@text,"Language")]',
                # 法语
                '//android.widget.TextView[@text="Langue"]',
                '//android.widget.TextView[@text="Paramètres de langue"]',
                '//android.widget.TextView[contains(@text,"Langue")]',
                '//android.widget.TextView[contains(@text,"langue")]',
                # 西班牙语
                '//android.widget.TextView[@text="Idioma"]',
                '//android.widget.TextView[@text="Configuración de idioma"]',
                '//android.widget.TextView[contains(@text,"Idioma")]',
                '//android.widget.TextView[contains(@text,"idioma")]',
                # 德语
                '//android.widget.TextView[@text="Sprache"]',
                '//android.widget.TextView[@text="Spracheinstellungen"]',
                '//android.widget.TextView[contains(@text,"Sprache")]',
                # 意大利语
                '//android.widget.TextView[@text="Lingua"]',
                '//android.widget.TextView[@text="Impostazioni lingua"]',
                '//android.widget.TextView[contains(@text,"Lingua")]',
                '//android.widget.TextView[contains(@text,"lingua")]',
                # 葡萄牙语
                '//android.widget.TextView[@text="Idioma"]',
                '//android.widget.TextView[@text="Configurações de idioma"]',
                '//android.widget.TextView[contains(@text,"Idioma")]',
                '//android.widget.TextView[contains(@text,"idioma")]',
                # 通用匹配（包含"语言"、"Language"、"Langue"等关键词）
                '//android.widget.TextView[contains(@text,"语言") or contains(@text,"Language") or contains(@text,"Langue") or contains(@text,"Idioma") or contains(@text,"Sprache") or contains(@text,"Lingua")]',
            ]
            if not wait_and_click(driver, language_setting_text_selectors, wait_time=2,
                                  desc="语言设置(文本)"):  # 减少等待时间
                print("❌ 点击语言设置失败")
                # 尝试查找所有可见的TextView，用于调试
                try:
                    all_texts = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView')
                    visible_texts = []
                    for tv in all_texts:
                        try:
                            text = tv.get_attribute("text") or tv.get_attribute("content-desc") or ""
                            if text and tv.is_displayed():
                                visible_texts.append(text)
                        except Exception:
                            continue
                    print(f"💡 当前页面可见的文本: {visible_texts[:15]}")  # 显示前15个
                except Exception:
                    pass
                return False
        time.sleep(1)  # 减少等待时间

        # 步骤4: 获取目标语言的单元格索引
        if target_language not in LANGUAGE_CONFIG["Android"]:
            print(f"❌ 不支持的语言: {target_language}")
            print(f"💡 支持的语言: {list(LANGUAGE_CONFIG['Android'].keys())}")
            return False

        cell_index = LANGUAGE_CONFIG["Android"][target_language]

        # Android中语言选项的选择器
        language_selectors = [
            f'//android.widget.ListView/android.widget.LinearLayout[{cell_index}]',
            f'//androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup[{cell_index}]',
            f'//android.widget.TableLayout/android.widget.TableRow[{cell_index}]',
        ]

        # 也尝试通过文本查找
        language_text_selectors = [
            f'//android.widget.TextView[@text="{target_language}"]',
            f'//android.widget.TextView[contains(@text,"{target_language}")]',
        ]

        all_selectors = language_selectors + language_text_selectors

        # 点击目标语言
        if not wait_and_click(driver, all_selectors, wait_time=2, desc=f"语言选项-{target_language}"):  # 减少等待时间
            print(f"❌ 点击语言选项 {target_language} 失败")
            return False
        time.sleep(1)  # 减少等待时间

        # 步骤5: 点击确认按钮（注意：确认按钮的文字会根据当前语言变化）
        confirm_clicked = False
        for confirm_text in CONFIRM_BUTTON_TEXTS:
            confirm_xpaths = [
                f'//android.widget.Button[@text="{confirm_text}"]',
                f'//android.widget.Button[contains(@text,"{confirm_text}")]',
                f'//android.widget.TextView[@text="{confirm_text}"]',
                f'//android.widget.TextView[contains(@text,"{confirm_text}")]',
            ]
            if wait_and_click(driver, confirm_xpaths, wait_time=2, desc=f"确认按钮({confirm_text})"):  # 减少等待时间
                confirm_clicked = True
                break

        if not confirm_clicked:
            # 尝试通用按钮选择器
            generic_confirm_xpaths = [
                '//android.widget.Button[contains(@text,"确认")]',
                '//android.widget.Button[contains(@text,"Confirm")]',
                '//android.widget.Button[contains(@text,"OK")]',
                '//android.widget.Button[last()]',  # 最后一个按钮通常是确认
            ]
            if not wait_and_click(driver, generic_confirm_xpaths, wait_time=2, desc="确认按钮(通用)"):  # 减少等待时间
                print("❌ 点击确认按钮失败")
                return False

        time.sleep(1)  # 减少等待时间

        # 步骤6: 重启APP（使用之前获取的app_package）
        print("🔄 语言切换完成，重启APP...")
        if app_package:
            try:
                driver.terminate_app(app_package)
                time.sleep(1)  # 减少等待时间
                driver.activate_app(app_package)
                time.sleep(2)  # 减少等待时间
                print("✅ APP已重启")
            except Exception as e:
                print(f"⚠️ 重启APP失败: {e}")
                print("💡 请手动重启APP以确保语言切换生效")
        else:
            print("⚠️ 无法获取appPackage，请手动重启APP")

        print(f"✅ 语言切换成功: {target_language}")
        return True

    except Exception as e:
        print(f"❌ 语言切换失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def switch_language(driver, target_language: str, platform: Optional[str] = None) -> bool:
    """
    语言切换主函数（自动检测平台或手动指定）

    Args:
        driver: Appium WebDriver
        target_language: 目标语言（如 "English", "中文", "Français" 等）
        platform: 平台类型（"iOS" 或 "Android"），如果为None则自动检测

    Returns:
        bool: 是否切换成功

    Examples:
        >>> # iOS
        >>> switch_language(driver, "English", platform="iOS")
        >>>
        >>> # Android
        >>> switch_language(driver, "中文", platform="Android")
        >>>
        >>> # 自动检测平台
        >>> switch_language(driver, "Français")
    """
    # 自动检测平台
    if platform is None:
        try:
            caps = getattr(driver, "capabilities", {}) or {}
            platform_name = caps.get("platformName", "").lower()
            if "ios" in platform_name:
                platform = "iOS"
            elif "android" in platform_name:
                platform = "Android"
            else:
                print("⚠️ 无法自动检测平台，默认使用iOS")
                platform = "iOS"
        except Exception:
            print("⚠️ 无法自动检测平台，默认使用iOS")
            platform = "iOS"

    print(f"📱 检测到平台: {platform}")

    if platform == "iOS":
        return switch_language_ios(driver, target_language)
    elif platform == "Android":
        return switch_language_android(driver, target_language)
    else:
        print(f"❌ 不支持的平台: {platform}")
        return False


def get_available_languages(platform: str = "iOS") -> List[str]:
    """
    获取支持的语言列表

    Args:
        platform: 平台类型（"iOS" 或 "Android"）

    Returns:
        List[str]: 支持的语言列表
    """
    return list(LANGUAGE_CONFIG.get(platform, LANGUAGE_CONFIG["iOS"]).keys())


if __name__ == "__main__":
    # 测试代码
    print("支持的语言列表:")
    print(f"iOS: {get_available_languages('iOS')}")
    print(f"Android: {get_available_languages('Android')}")

