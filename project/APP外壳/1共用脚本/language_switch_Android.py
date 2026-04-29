#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android平台语言切换功能模块

3功能：
- 支持Android平台的语言切换
- 支持多种语言：中文、English、Français、Italiano、Deutsch、Español、Português
- 切换语言后自动重启APP

使用示例：
    from language_switch_Android import switch_language_android
    switch_language_android(driver, "English")
"""

import time
import os
from typing import Optional, Dict, List
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# 语言配置：语言名称 -> 单元格索引（从2开始，因为第1个可能是标题）
LANGUAGE_CONFIG: Dict[str, int] = {
    "English": 2,
    "Français": 3,
    "Italiano": 4,
    "Deutsch": 5,
    "Español": 6,
    "Português": 7,
    "中文": 8,
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
    "OK",  # 通用
    "确定",  # 中文变体
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
        
        # 步骤0: 重置APP到首页
        print("🔄 重置APP到首页...")
        caps = getattr(driver, "capabilities", {}) or {}
        app_package = caps.get("appPackage") or os.environ.get("ANDROID_APP_PACKAGE")
        
        if app_package:
            # 重试机制：最多重试3次
            max_retries = 3
            reset_success = False
            for attempt in range(max_retries):
                try:
                    driver.terminate_app(app_package)
                    time.sleep(2)
                    driver.activate_app(app_package)
                    time.sleep(3)
                    
                    # 检查是否在首页
                    home_xpaths = [
                        '//android.widget.ImageView[@content-desc="add"]',
                        '//android.view.View[@content-desc="More"]',
                        '//android.widget.TextView[contains(@text,"Sora")]',
                        '//android.widget.TextView[contains(@text,"设备")]',
                    ]
                    for xp in home_xpaths:
                        try:
                            elements = driver.find_elements(AppiumBy.XPATH, xp)
                            for elem in elements:
                                if elem.is_displayed():
                                    print(f"✅ 确认在首页: {xp}")
                                    reset_success = True
                                    break
                            if reset_success:
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
                        wait_time = (attempt + 1) * 5
                        print(f"⚠️ 应用正在安装/卸载中，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    elif attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3
                        print(f"⚠️ 重置APP失败，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {error_msg[:100]}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"⚠️ 重置APP失败: {error_msg[:200]}，继续尝试切换语言")
            
            if not reset_success:
                print("⚠️ 重置APP未成功，但继续尝试切换语言")
        
        # 步骤1: 点击More按钮
        print("📱 步骤1: 点击More按钮...")
        more_selectors = [
            '//android.view.View[@content-desc="More"]',
            '//android.widget.Button[@content-desc="More"]',
            '//android.view.View[contains(@content-desc,"More")]',
        ]
        if not wait_and_click(driver, more_selectors, wait_time=5, desc="More按钮"):
            print("❌ 点击More按钮失败")
            # 添加调试信息
            try:
                elements = driver.find_elements(AppiumBy.XPATH, "//*[@content-desc]")
                print(f"    💡 找到 {len(elements)} 个有content-desc的元素")
                for i, el in enumerate(elements[:10]):
                    try:
                        if el.is_displayed():
                            desc = el.get_attribute("contentDescription") or el.get_attribute("content-desc") or ""
                            if desc:
                                print(f"    💡 元素[{i+1}]: {desc[:50]}")
                    except:
                        pass
            except Exception as e:
                print(f"    ⚠️ 调试信息获取失败: {e}")
            return False
        time.sleep(1.5)
        
        # 步骤2: 点击通用按钮（第2个arrow_right）
        print("📱 步骤2: 点击通用按钮...")
        general_selectors = [
            '(//android.view.View[@content-desc="arrow_right"])[2]',
            '//android.view.View[@content-desc="arrow_right"][2]',
            # 备用：通过父元素查找
            '(//android.view.View[@content-desc="arrow_right"])[2]/ancestor::android.view.View[1]',
        ]
        if not wait_and_click(driver, general_selectors, wait_time=5, desc="通用按钮"):
            print("❌ 点击通用按钮失败")
            # 添加调试信息
            try:
                arrows = driver.find_elements(AppiumBy.XPATH, '//android.view.View[@content-desc="arrow_right"]')
                print(f"    💡 找到 {len(arrows)} 个arrow_right元素")
                for i, arrow in enumerate(arrows[:5], 1):
                    try:
                        if arrow.is_displayed():
                            # 尝试获取父元素的文本
                            try:
                                parent = arrow.find_element(AppiumBy.XPATH, './ancestor::android.view.View[1]')
                                parent_text = parent.get_attribute("contentDescription") or parent.get_attribute("content-desc") or parent.text or ""
                                print(f"    💡 arrow_right[{i}]: 父元素文本='{parent_text[:50]}'")
                            except:
                                print(f"    💡 arrow_right[{i}]: (无法获取父元素文本)")
                    except:
                        pass
            except Exception as e:
                print(f"    ⚠️ 调试信息获取失败: {e}")
            return False
        time.sleep(1.5)
        
        # 步骤3: 点击多语言设置按钮（第2个arrow_right）
        print("📱 步骤3: 点击多语言设置按钮...")
        language_setting_selectors = [
            '(//android.view.View[@content-desc="arrow_right"])[2]',
            '//android.view.View[@content-desc="arrow_right"][2]',
            # 备用：通过父元素查找
            '(//android.view.View[@content-desc="arrow_right"])[2]/ancestor::android.view.View[1]',
        ]
        if not wait_and_click(driver, language_setting_selectors, wait_time=5, desc="多语言设置按钮"):
            print("❌ 点击多语言设置按钮失败")
            # 添加调试信息
            try:
                arrows = driver.find_elements(AppiumBy.XPATH, '//android.view.View[@content-desc="arrow_right"]')
                print(f"    💡 找到 {len(arrows)} 个arrow_right元素")
                for i, arrow in enumerate(arrows[:5], 1):
                    try:
                        if arrow.is_displayed():
                            try:
                                parent = arrow.find_element(AppiumBy.XPATH, './ancestor::android.view.View[1]')
                                parent_text = parent.get_attribute("contentDescription") or parent.get_attribute("content-desc") or parent.text or ""
                                print(f"    💡 arrow_right[{i}]: 父元素文本='{parent_text[:50]}'")
                            except:
                                print(f"    💡 arrow_right[{i}]: (无法获取父元素文本)")
                    except:
                        pass
            except Exception as e:
                print(f"    ⚠️ 调试信息获取失败: {e}")
            return False
        time.sleep(2)
        
        # 步骤4: 等待语言设置页面完全加载
        print("⏳ 等待语言设置页面加载...")
        time.sleep(2)
        
        # 添加详细的调试信息：查看语言设置页面的所有元素
        try:
            # 查找所有可见的文本元素
            all_texts = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView | //android.view.View[@content-desc]')
            visible_texts = []
            for t in all_texts:
                try:
                    if t.is_displayed():
                        text = t.get_attribute("text") or t.get_attribute("contentDescription") or t.get_attribute("content-desc") or ""
                        if text and text.strip():
                            visible_texts.append(text.strip())
                except:
                    continue
            print(f"    💡 语言设置页面找到 {len(visible_texts)} 个可见文本元素")
            print(f"    💡 可见文本（前15个）: {visible_texts[:15]}")
        except Exception as e:
            print(f"    ⚠️ 调试信息获取失败: {e}")
        
        # 步骤5: 获取目标语言的单元格索引
        if target_language not in LANGUAGE_CONFIG:
            print(f"❌ 不支持的语言: {target_language}")
            print(f"💡 支持的语言: {list(LANGUAGE_CONFIG.keys())}")
            return False
        
        cell_index = LANGUAGE_CONFIG[target_language]
        
        # 构建多种可能的选择器（按优先级排序）
        language_selectors = [
            # 优先：通过文本直接查找（最可靠）
            f'//android.widget.TextView[@text="{target_language}"]/ancestor::android.view.View[1]',
            f'//android.view.View[@content-desc="{target_language}"]',
            f'//android.widget.TextView[@text="{target_language}"]',
            # 备用：使用索引（如果页面结构是列表）
            f'//androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup[{cell_index}]',
            f'//android.widget.ListView/android.widget.LinearLayout[{cell_index}]',
            # 备用：通过包含文本查找
            f'//android.widget.TextView[contains(@text,"{target_language}")]/ancestor::android.view.View[1]',
            f'//android.view.View[contains(@content-desc,"{target_language}")]',
        ]
        
        if not wait_and_click(driver, language_selectors, wait_time=5, desc=f"语言选项-{target_language}"):
            print(f"❌ 点击语言选项 {target_language} 失败 (尝试索引 {cell_index})")
            # 再次尝试获取页面信息用于调试
            try:
                all_elements = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView | //android.view.View[@content-desc]')
                matching_elements = []
                for el in all_elements:
                    try:
                        if el.is_displayed():
                            text = el.get_attribute("text") or el.get_attribute("contentDescription") or el.get_attribute("content-desc") or ""
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
        
        # 步骤6: 点击确认按钮（注意：确认按钮的文字会根据当前语言变化）
        print("📱 步骤6: 点击确认按钮...")
        confirm_clicked = False
        for confirm_text in CONFIRM_BUTTON_TEXTS:
            confirm_xpaths = [
                f'//android.widget.Button[@text="{confirm_text}"]',
                f'//android.view.View[@content-desc="{confirm_text}"]',
                f'//android.widget.TextView[@text="{confirm_text}"]',
                f'//android.widget.Button[contains(@text,"{confirm_text}")]',
            ]
            if wait_and_click(driver, confirm_xpaths, wait_time=3, desc=f"确认按钮({confirm_text})"):
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
            if not wait_and_click(driver, generic_confirm_xpaths, wait_time=3, desc="确认按钮(通用)"):
                print("❌ 点击确认按钮失败")
                return False
        
        time.sleep(2)
        
        # 步骤7: 重启APP（使用之前获取的app_package）
        print("🔄 语言切换完成，重启APP...")
        if app_package:
            # 重试机制：最多重试3次
            max_retries = 3
            restart_success = False
            for attempt in range(max_retries):
                try:
                    driver.terminate_app(app_package)
                    time.sleep(2)
                    driver.activate_app(app_package)
                    time.sleep(3)
                    print("✅ APP已重启")
                    restart_success = True
                    break
                except Exception as e:
                    error_msg = str(e)
                    is_app_busy = (
                        "installing or uninstalling" in error_msg.lower() or
                        "cannot be launched" in error_msg.lower() or
                        "busy" in error_msg.lower() or
                        "RequestDenied" in error_msg
                    )
                    
                    if is_app_busy and attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        print(f"⚠️ 应用正在安装/卸载中，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    elif attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3
                        print(f"⚠️ 重启APP失败，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {error_msg[:100]}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"⚠️ 重启APP失败: {error_msg[:200]}")
                        print("💡 请手动重启APP以确保语言切换生效")
            
            if not restart_success:
                print("⚠️ 重启APP未成功，但语言切换可能已生效")
        else:
            print("⚠️ 无法获取appPackage，请手动重启APP")
        
        print(f"✅ 语言切换成功: {target_language}")
        return True
        
    except Exception as e:
        print(f"❌ 语言切换失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def get_available_languages() -> List[str]:
    """
    获取支持的语言列表
    
    Returns:
        List[str]: 支持的语言列表
    """
    return list(LANGUAGE_CONFIG.keys())


if __name__ == "__main__":
    # 测试代码
    print("支持的语言列表:")
    print(f"Android: {get_available_languages()}")
