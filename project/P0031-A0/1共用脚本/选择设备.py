#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2蓝牙配网 - 设备选择独立脚本

3功能：
- 在设备选择列表中选择指定 SN 的设备
- 支持 iOS 和 Android 平台
- 可以单独使用（作为独立脚本）
- 可以被蓝牙配网脚本调用（作为模块）

使用方法：
1. 作为模块导入：
   from 选择设备 import select_device
   result = select_device(driver, target_device_config, platform="ios")

2. 作为独立脚本运行：
   python 选择设备.py
"""

import os
import sys
import json
import time
import re
import logging
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from pathlib import Path

# 尝试导入 Appium 相关模块
try:
    from appium import webdriver
    from appium.webdriver.common.appiumby import AppiumBy
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("❌ 未安装 Appium 相关依赖，请先安装：pip install Appium-Python-Client selenium")
    sys.exit(1)

# ==================== 日志配置 ====================

def _setup_logging(log_func: Optional[Callable[[str], None]] = None):
    """设置日志输出函数"""
    if log_func:
        return log_func
    
    # 默认日志输出
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger(__name__)
    
    def default_log(msg: str):
        print(msg, flush=True)
        logger.info(msg)
    
    return default_log


# ==================== 截图功能 ====================

def _take_screenshot(driver, prefix: str, screenshot_dir: Optional[Path] = None, log_func: Optional[Callable[[str], None]] = None):
    """截图功能"""
    if log_func is None:
        log_func = lambda msg: print(msg, flush=True)
    
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{prefix}_{ts}.png"
        
        if screenshot_dir:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            filepath = screenshot_dir / filename
        else:
            # 如果没有指定目录，保存到当前目录
            filepath = Path(filename)
        
        driver.save_screenshot(str(filepath))
        log_func(f"📸 截图已保存: {filepath}")
    except Exception as e:
        log_func(f"⚠️ 截图失败: {e}")


# ==================== iOS 设备选择 ====================

def _select_device_ios(
    driver,
    target_device_config: Dict[str, Any],
    log_func: Callable[[str], None],
    screenshot_dir: Optional[Path] = None,
    max_attempts: int = 3,
    max_scrolls: int = 10,
) -> bool:
    """
    iOS 平台设备选择
    
    Args:
        driver: Appium WebDriver 实例
        target_device_config: 目标设备配置字典，包含 device_sn 和 device_name
        log_func: 日志输出函数
        screenshot_dir: 截图保存目录（可选）
        max_attempts: 最大尝试次数
        max_scrolls: 最大滑动次数
    
    Returns:
        bool: 选择成功返回 True，失败返回 False
    """
    if not target_device_config:
        log_func("❌ target_device 配置为空，请在 device_config.json 中配置 target_device")
        return False
    
    dev_sn = target_device_config.get("device_sn")
    dev_name = target_device_config.get("device_name")
    
    if not dev_sn:
        log_func("❌ target_device.device_sn 未配置，请在 device_config.json 中配置 target_device.device_sn")
        return False
    
    if not dev_name:
        log_func("❌ target_device.device_name 未配置，请在 device_config.json 中配置 target_device.device_name")
        return False
    
    short_sn = dev_sn[1:] if dev_sn.lower().startswith("b") else dev_sn
    
    log_func(f"🔍 步骤3: 选择设备（{dev_name}, SN: {dev_sn}）...")
    
    # 等待页面加载完成，确保所有设备都显示出来
    log_func("⏳ 等待设备选择页面加载，确保所有设备都显示（10秒）...")
    time.sleep(10)
    
    add_btn_xpath = '//XCUIElementTypeButton[@name="Add"]'
    
    def _verify_device_element(elem, expected_sn, expected_name):
        """严格验证设备元素是否匹配目标设备（同时验证设备名称和SN）"""
        try:
            # 获取元素文本
            elem_text = elem.get_attribute("name") or elem.text or ""
            log_func(f"🔍 验证设备元素文本: '{elem_text}'")
            
            # 首先验证文本中是否包含完整的 SN（简单但有效的检查）
            if expected_sn not in elem_text and short_sn not in elem_text:
                log_func(f"❌ SN不匹配: 期望包含 '{expected_sn}' 或 '{short_sn}'，实际文本: '{elem_text}'")
                return False, None
            
            # 进一步验证：使用正则表达式确保是完整的 SN 匹配（不是部分匹配）
            sn_patterns = [
                rf'\(SN:\s*{re.escape(expected_sn)}\)',  # (SN:B0078) 或 (SN: B0078)
                rf'\(SN:\s*{re.escape(short_sn)}\)',  # (SN:0078) 或 (SN: 0078)
                rf'SN:\s*{re.escape(expected_sn)}',  # SN:B0078 或 SN: B0078
                rf'SN:\s*{re.escape(short_sn)}',  # SN:0078 或 SN: 0078
                rf'\b{re.escape(expected_sn)}\b',  # 完整SN号（单词边界）
                rf'\b{re.escape(short_sn)}\b',  # 完整SN号（无B前缀）
            ]
            
            sn_matched = False
            for pattern in sn_patterns:
                if re.search(pattern, elem_text, re.IGNORECASE):
                    sn_matched = True
                    log_func(f"✅ SN匹配成功: 模式 '{pattern}' 匹配文本 '{elem_text}'")
                    break
            
            if not sn_matched:
                log_func(f"❌ SN正则验证失败: 期望包含 '{expected_sn}' 或 '{short_sn}'，实际文本: '{elem_text}'")
                return False, None
            
            # 关键改进：同时验证设备名称，提高选择精度
            name_matched = False
            name_match_context = ""
            
            # 1. 首先检查元素文本本身是否包含设备名称
            if expected_name and expected_name.lower() in elem_text.lower():
                name_matched = True
                name_match_context = "元素文本本身"
                log_func(f"✅ 设备名称匹配成功（{name_match_context}）: '{expected_name}' 在文本中")
            else:
                # 2. 检查父元素（通常是包含设备信息的容器）
                try:
                    parent = elem.find_element(AppiumBy.XPATH, "..")
                    parent_text = parent.get_attribute("name") or parent.text or ""
                    if expected_name and expected_name.lower() in parent_text.lower():
                        name_matched = True
                        name_match_context = "父元素"
                        log_func(f"✅ 设备名称匹配成功（{name_match_context}）: '{expected_name}' 在父元素中")
                except:
                    pass
                
                # 3. 如果父元素未匹配，检查兄弟元素（同一层级的其他元素）
                if not name_matched:
                    try:
                        parent = elem.find_element(AppiumBy.XPATH, "..")
                        siblings = parent.find_elements(AppiumBy.XPATH, "./*")
                        for sibling in siblings:
                            sibling_text = sibling.get_attribute("name") or sibling.text or ""
                            if expected_name and expected_name.lower() in sibling_text.lower():
                                name_matched = True
                                name_match_context = "兄弟元素"
                                log_func(f"✅ 设备名称匹配成功（{name_match_context}）: '{expected_name}' 在兄弟元素中")
                                break
                    except:
                        pass
                
                # 4. 如果还是没找到，尝试查找附近的元素（使用 XPath 查找包含设备名称的相邻元素）
                if not name_matched:
                    try:
                        nearby_name_elem = driver.find_element(
                            AppiumBy.XPATH,
                            f'//XCUIElementTypeStaticText[contains(@name,"{expected_name}")]'
                        )
                        if nearby_name_elem:
                            elem_location = elem.location
                            name_elem_location = nearby_name_elem.location
                            # 如果两个元素在垂直方向上接近（Y坐标差小于100），认为是同一设备
                            if abs(elem_location['y'] - name_elem_location['y']) < 100:
                                name_matched = True
                                name_match_context = "附近元素"
                                log_func(f"✅ 设备名称匹配成功（{name_match_context}）: '{expected_name}' 在附近元素中")
                    except:
                        pass
            
            # 如果设备名称未匹配，记录警告但继续（因为有些情况下设备名称可能不在同一元素中）
            if not name_matched and expected_name:
                log_func(f"⚠️ 设备名称未匹配: 期望 '{expected_name}'，但未在元素附近找到（SN已匹配，继续验证）")
            
            # 最终验证：SN必须匹配，设备名称如果找到则必须匹配
            if sn_matched:
                if name_matched:
                    log_func(f"✅ 设备验证通过: SN匹配 + 设备名称匹配，文本: '{elem_text}'")
                else:
                    log_func(f"✅ 设备验证通过: SN匹配（设备名称未找到但SN已确认），文本: '{elem_text}'")
                return True, elem_text
            else:
                log_func(f"❌ 设备验证失败: SN未匹配")
                return False, None
            
        except Exception as e:
            log_func(f"⚠️ 验证设备元素时出错: {e}")
            import traceback
            log_func(f"   详细错误: {traceback.format_exc()}")
            return False, None
    
    for attempt in range(max_attempts):
        try:
            log_func(f"🔍 第{attempt + 1}次尝试选择设备...")
            
            # 等待页面加载
            if attempt == 0:
                log_func("⏳ 等待设备选择页面加载，确保所有设备都显示（10秒）...")
                time.sleep(10)
            else:
                time.sleep(2)
            
            # 优先使用精确匹配的选择器（按精确度排序）
            device_selectors = [
                # 最精确：同时包含设备名称和SN（完全匹配）
                f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"SN:{short_sn}")]',
                f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"SN: {short_sn}")]',
                f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"{short_sn}")]',
                # 精确：完全匹配 SN 格式（带括号）
                f'(//XCUIElementTypeStaticText[@name="(SN:{short_sn})"])[1]',
                f'//XCUIElementTypeStaticText[@name="(SN:{short_sn})"]',
                f'//XCUIElementTypeStaticText[@name="(SN: {short_sn})"]',
                # 精确匹配：包含完整 SN
                f'//XCUIElementTypeStaticText[contains(@name,"SN:{short_sn}")]',
                f'//XCUIElementTypeStaticText[contains(@name,"SN: {short_sn})"]',
                # 精确匹配：包含完整 SN（无前缀，但需要验证）
                f'//XCUIElementTypeStaticText[contains(@name,"{short_sn}")]',
            ]
            
            dev_elem = None
            matched_text = None
            
            # 首先尝试不滑动直接查找
            log_func("🔍 首先尝试直接查找设备（不滑动）...")
            for selector in device_selectors:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            is_match, text = _verify_device_element(elem, dev_sn, dev_name)
                            if is_match:
                                dev_elem = elem
                                matched_text = text
                                log_func(f"✅ 直接找到并验证目标设备: {selector}")
                                log_func(f"   匹配文本: {text}")
                                break
                    if dev_elem:
                        break
                except:
                    continue
            
            # 如果直接查找失败，尝试查找所有设备并验证
            if not dev_elem:
                log_func("🔍 直接查找失败，查找所有设备元素进行验证...")
                try:
                    # 优先查找同时包含设备名称和SN的元素（提高精度）
                    priority_elements = []
                    try:
                        priority_elements = driver.find_elements(
                            AppiumBy.XPATH, 
                            f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"SN")]'
                        )
                        log_func(f"🔍 找到 {len(priority_elements)} 个同时包含设备名称和SN的元素（优先验证）")
                    except:
                        pass
                    
                    # 然后查找所有可能包含 SN 的设备元素
                    all_device_elements = driver.find_elements(
                        AppiumBy.XPATH, 
                        '//XCUIElementTypeStaticText[contains(@name,"SN")]'
                    )
                    
                    log_func(f"🔍 总共找到 {len(all_device_elements)} 个可能的设备元素")
                    
                    # 优先验证同时包含设备名称和SN的元素
                    for elem in priority_elements:
                        try:
                            if elem.is_displayed():
                                text = elem.get_attribute("name") or elem.text or ""
                                log_func(f"   优先检查设备（包含名称和SN）: {text}")
                                
                                if dev_sn in text or short_sn in text:
                                    is_match, verified_text = _verify_device_element(elem, dev_sn, dev_name)
                                    if is_match:
                                        dev_elem = elem
                                        matched_text = verified_text
                                        log_func(f"✅ 验证通过，找到目标设备: {text}")
                                        break
                        except Exception as e:
                            log_func(f"⚠️ 检查优先设备元素时出错: {e}")
                            continue
                        if dev_elem:
                            break
                    
                    # 如果优先元素未找到，再验证所有包含SN的元素
                    if not dev_elem:
                        for elem in all_device_elements:
                            if elem in priority_elements:
                                continue
                            try:
                                if elem.is_displayed():
                                    text = elem.get_attribute("name") or elem.text or ""
                                    log_func(f"   检查设备: {text}")
                                    
                                    if dev_sn in text or short_sn in text:
                                        is_match, verified_text = _verify_device_element(elem, dev_sn, dev_name)
                                        if is_match:
                                            dev_elem = elem
                                            matched_text = verified_text
                                            log_func(f"✅ 验证通过，找到目标设备: {text}")
                                            break
                            except Exception as e:
                                log_func(f"⚠️ 检查设备元素时出错: {e}")
                                continue
                            if dev_elem:
                                break
                except Exception as e:
                    log_func(f"⚠️ 查找所有设备元素失败: {e}")
            
            # 如果仍然找不到，先向上滑动到顶部，然后双向滑动查找
            if not dev_elem:
                log_func("🔍 未找到设备，先向上滑动到顶部，然后双向滑动查找...")
                
                # 先向上滑动到顶部（确保从顶部开始查找）
                log_func("⬆️ 向上滑动到列表顶部...")
                for top_scroll in range(5):
                    try:
                        size = driver.get_window_size()
                        start_x = size['width'] // 2
                        start_y = int(size['height'] * 0.3)
                        end_y = int(size['height'] * 0.7)
                        driver.swipe(start_x, start_y, start_x, end_y, 500)
                        time.sleep(1)
                    except:
                        try:
                            driver.execute_script('mobile: swipe', {'direction': 'up'})
                            time.sleep(1)
                        except:
                            break
                
                time.sleep(2)
                
                # 现在从顶部开始，先向下滑动查找
                log_func("⬇️ 从顶部开始向下滑动查找...")
                for scroll_attempt in range(max_scrolls):
                    log_func(f"🔍 第{scroll_attempt + 1}/{max_scrolls}次向下滑动查找设备...")
                    
                    # 优先查找同时包含设备名称和SN的元素
                    try:
                        priority_elements = driver.find_elements(
                            AppiumBy.XPATH,
                            f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"SN")]'
                        )
                        for elem in priority_elements:
                            if elem.is_displayed():
                                is_match, text = _verify_device_element(elem, dev_sn, dev_name)
                                if is_match:
                                    dev_elem = elem
                                    matched_text = text
                                    log_func(f"✅ 向下滑动后找到目标设备（优先匹配）: {text}")
                                    break
                        if dev_elem:
                            break
                    except:
                        pass
                    
                    # 如果优先查找未找到，再尝试所有选择器
                    if not dev_elem:
                        for selector in device_selectors:
                            try:
                                elements = driver.find_elements(AppiumBy.XPATH, selector)
                                for elem in elements:
                                    if elem.is_displayed():
                                        is_match, text = _verify_device_element(elem, dev_sn, dev_name)
                                        if is_match:
                                            dev_elem = elem
                                            matched_text = text
                                            log_func(f"✅ 向下滑动后找到目标设备: {text}")
                                            break
                                if dev_elem:
                                    break
                            except:
                                continue
                    
                    if dev_elem:
                        break
                    
                    # 向下滑动
                    try:
                        size = driver.get_window_size()
                        start_x = size['width'] // 2
                        start_y = int(size['height'] * 0.6)
                        end_y = int(size['height'] * 0.3)
                        driver.swipe(start_x, start_y, start_x, end_y, 500)
                        time.sleep(1.5)
                    except Exception as swipe_err:
                        try:
                            driver.execute_script('mobile: swipe', {'direction': 'down'})
                            time.sleep(1.5)
                        except:
                            log_func(f"⚠️ 滑动失败: {swipe_err}")
                            time.sleep(1)
                
                # 如果向下滑动没找到，尝试向上滑动查找
                if not dev_elem:
                    log_func("⬆️ 向下滑动未找到，尝试向上滑动查找...")
                    for scroll_attempt in range(max_scrolls):
                        log_func(f"🔍 第{scroll_attempt + 1}/{max_scrolls}次向上滑动查找设备...")
                        
                        # 优先查找同时包含设备名称和SN的元素
                        try:
                            priority_elements = driver.find_elements(
                                AppiumBy.XPATH,
                                f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"SN")]'
                            )
                            for elem in priority_elements:
                                if elem.is_displayed():
                                    is_match, text = _verify_device_element(elem, dev_sn, dev_name)
                                    if is_match:
                                        dev_elem = elem
                                        matched_text = text
                                        log_func(f"✅ 向上滑动后找到目标设备（优先匹配）: {text}")
                                        break
                            if dev_elem:
                                break
                        except:
                            pass
                        
                        # 如果优先查找未找到，再尝试所有选择器
                        if not dev_elem:
                            for selector in device_selectors:
                                try:
                                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                                    for elem in elements:
                                        if elem.is_displayed():
                                            is_match, text = _verify_device_element(elem, dev_sn, dev_name)
                                            if is_match:
                                                dev_elem = elem
                                                matched_text = text
                                                log_func(f"✅ 向上滑动后找到目标设备: {text}")
                                                break
                                    if dev_elem:
                                        break
                                except:
                                    continue
                        
                        if dev_elem:
                            break
                        
                        # 向上滑动（向上滚动列表，即从下往上滑动）
                        try:
                            size = driver.get_window_size()
                            start_x = size['width'] // 2
                            start_y = int(size['height'] * 0.3)
                            end_y = int(size['height'] * 0.7)
                            driver.swipe(start_x, start_y, start_x, end_y, 500)
                            time.sleep(1.5)
                        except Exception as swipe_err:
                            try:
                                driver.execute_script('mobile: swipe', {'direction': 'up'})
                                time.sleep(1.5)
                            except:
                                log_func(f"⚠️ 滑动失败: {swipe_err}")
                                time.sleep(1)
            
            # 验证找到的设备
            if not dev_elem:
                log_func("❌ 未找到目标设备元素")
                if attempt < max_attempts - 1:
                    log_func("⏳ 等待2秒后重试...")
                    time.sleep(2)
                    continue
                else:
                    log_func(f"❌ 经过 {max_attempts} 次尝试，仍未找到目标设备 SN: {dev_sn}")
                    if screenshot_dir:
                        _take_screenshot(driver, "pick_device_fail", screenshot_dir, log_func)
                    return False
            
            # 再次验证匹配的文本
            if matched_text and dev_sn not in matched_text and short_sn not in matched_text:
                log_func(f"❌ 验证失败：匹配的文本 '{matched_text}' 不包含目标 SN '{dev_sn}'")
                if attempt < max_attempts - 1:
                    log_func("⏳ 等待2秒后重试...")
                    time.sleep(2)
                    continue
                else:
                    return False
            
            # 点击前再次验证（确保元素仍然有效）
            try:
                log_func(f"🔍 点击前再次验证设备: '{matched_text}'")
                if not dev_elem.is_displayed():
                    log_func("❌ 设备元素已不可见，重新查找...")
                    if attempt < max_attempts - 1:
                        time.sleep(2)
                        continue
                    else:
                        return False
                
                # 再次获取文本验证
                current_text = dev_elem.get_attribute("name") or dev_elem.text or ""
                if dev_sn not in current_text and short_sn not in current_text:
                    log_func(f"❌ 点击前验证失败: 当前文本 '{current_text}' 不包含目标SN")
                    if attempt < max_attempts - 1:
                        time.sleep(2)
                        continue
                    else:
                        return False
                
                log_func(f"✅ 点击前验证通过，准备点击设备: '{current_text}'")
            except Exception as e:
                log_func(f"❌ 点击前验证失败: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                else:
                    return False
            
            # 点击找到的设备
            try:
                log_func(f"✅ 确认选择设备: {matched_text}")
                log_func("⏳ 等待元素完全加载后点击...")
                time.sleep(2)
                dev_elem.click()
                log_func(f"✅ 点击 SN 设备成功: {matched_text}")
                time.sleep(2)
            except Exception as e:
                log_func(f"❌ 点击设备失败: {e}")
                if attempt < max_attempts - 1:
                    if screenshot_dir:
                        _take_screenshot(driver, "pick_device_click_fail", screenshot_dir, log_func)
                    time.sleep(2)
                    continue
                else:
                    if screenshot_dir:
                        _take_screenshot(driver, "pick_device_click_fail", screenshot_dir, log_func)
                    return False
            
            # 选择完设备后，确保设备保持选中状态并点击 Add
            try:
                log_func("🔍 确保设备保持选中状态并查找 Add 按钮...")
                
                def _check_device_selected_ios(device_elem):
                    """检测 iOS 设备是否处于选中状态"""
                    try:
                        # 方法1: 检查元素或其父容器的 selected 属性
                        check_elements = [device_elem]
                        try:
                            parent = device_elem.find_element(AppiumBy.XPATH, "..")
                            check_elements.append(parent)
                        except:
                            pass
                        
                        for elem in check_elements:
                            try:
                                selected = str(elem.get_attribute("selected")).lower()
                                if selected == "true":
                                    return True
                            except:
                                continue
                        
                        # 方法2: 检查 Add 按钮是否启用（间接判断）
                        try:
                            btn = driver.find_element(AppiumBy.XPATH, add_btn_xpath)
                            if btn.is_displayed() and btn.is_enabled():
                                return True
                        except:
                            pass
                        
                        return False
                    except:
                        return False
                
                # 持续确保设备选中状态（最多等待 30 秒）
                ensure_selected_timeout = 30
                ensure_start = time.time()
                last_click_time = 0.0
                consecutive_selected = 0
                min_selected_checks = 3
                
                while time.time() - ensure_start < ensure_selected_timeout:
                    is_selected = _check_device_selected_ios(dev_elem)
                    
                    if is_selected:
                        consecutive_selected += 1
                        log_func(f"✅ 设备已选中（连续 {consecutive_selected} 次检查）")
                        
                        # 如果连续多次检查都选中，尝试点击 Add
                        if consecutive_selected >= min_selected_checks:
                            try:
                                btn = WebDriverWait(driver, 3).until(
                                    EC.element_to_be_clickable((AppiumBy.XPATH, add_btn_xpath))
                                )
                                if btn.is_displayed() and btn.is_enabled():
                                    btn.click()
                                    log_func("✅ Add 按钮已点击")
                                    
                                    # 点击 Add 后，验证是否真的进入了下一步
                                    time.sleep(2)
                                    
                                    # 检查是否已离开设备选择页面
                                    wifi_setup_indicators = [
                                        '//XCUIElementTypeButton[@name="pair net change wifi"]',
                                        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
                                        '//XCUIElementTypeButton[@name="Next"]',
                                    ]
                                    
                                    for indicator in wifi_setup_indicators:
                                        try:
                                            elem = driver.find_element(AppiumBy.XPATH, indicator)
                                            if elem.is_displayed():
                                                log_func(f"✅ 已进入下一步页面（检测到: {indicator}），设备选择成功")
                                                return True
                                        except:
                                            continue
                                    
                                    # 如果未检测到 WiFi 设置页面，检查是否还在设备选择页面
                                    try:
                                        device_list = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeStaticText[contains(@name,"SN")]')
                                        if len(device_list) == 0:
                                            log_func("✅ 设备列表已消失，已进入下一步页面")
                                            return True
                                        else:
                                            log_func("⚠️ 仍在设备选择页面，继续确保选中状态...")
                                            consecutive_selected = 0
                                    except:
                                        log_func("✅ 无法确认页面状态，假设已进入下一步")
                                        return True
                            except Exception as e:
                                log_func(f"⚠️ 点击 Add 按钮失败: {e}，继续确保选中状态...")
                                consecutive_selected = 0
                    else:
                        consecutive_selected = 0
                        log_func("⚠️ 设备未选中，重新点击设备以保持选中状态")
                    
                    # 如果设备未选中，重新点击设备
                    if not is_selected or consecutive_selected < min_selected_checks:
                        now = time.time()
                        if now - last_click_time >= 0.8:
                            try:
                                # 重新定位设备元素（避免 stale element）
                                try:
                                    current_text = dev_elem.get_attribute("name") or dev_elem.text or ""
                                    if dev_sn in current_text or short_sn in current_text:
                                        dev_elem.click()
                                        last_click_time = now
                                        log_func("🔄 重新点击设备以保持选中状态")
                                except:
                                    # 如果元素失效，重新查找
                                    try:
                                        device_selectors = [
                                            f'//XCUIElementTypeStaticText[contains(@name,"{short_sn}")]',
                                            f'//XCUIElementTypeStaticText[contains(@name,"SN:{short_sn}")]',
                                        ]
                                        for selector in device_selectors:
                                            try:
                                                elems = driver.find_elements(AppiumBy.XPATH, selector)
                                                for elem in elems:
                                                    if elem.is_displayed():
                                                        text = elem.get_attribute("name") or elem.text or ""
                                                        if dev_sn in text or short_sn in text:
                                                            dev_elem = elem
                                                            dev_elem.click()
                                                            last_click_time = now
                                                            log_func("🔄 重新找到并点击设备以保持选中状态")
                                                            break
                                                if last_click_time > 0:
                                                    break
                                            except:
                                                continue
                                    except:
                                        pass
                            except Exception as e:
                                log_func(f"⚠️ 重新点击设备失败: {e}")
                    
                    time.sleep(0.5)
                
                # 如果超时仍未成功，尝试传统的点击 Add 方式
                log_func("⚠️ 持续确保选中状态超时，尝试传统方式点击 Add...")
                for retry in range(3):
                    try:
                        btn = WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located((AppiumBy.XPATH, add_btn_xpath))
                        )
                        if btn.is_displayed() and btn.is_enabled():
                            btn.click()
                            log_func("✅ 点击 Add 按钮成功（传统方式）")
                            time.sleep(2)
                            return True
                        log_func("⚠️ Add 按钮暂不可点击，等待后重试")
                        time.sleep(2)
                    except:
                        time.sleep(2)
                
                log_func("❌ 多次尝试后 Add 按钮仍不可点击")
                if screenshot_dir:
                    _take_screenshot(driver, "add_btn_disabled", screenshot_dir, log_func)
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                else:
                    return False
            except Exception as e:
                log_func(f"❌ 查找或点击 Add 按钮失败: {e}")
                if screenshot_dir:
                    _take_screenshot(driver, "add_btn_error", screenshot_dir, log_func)
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                else:
                    return False
                    
        except Exception as e:
            log_func(f"❌ 第{attempt + 1}次选择设备失败: {e}")
            import traceback
            log_func(f"   详细错误: {traceback.format_exc()}")
            if attempt < max_attempts - 1:
                log_func("⏳ 等待3秒后重试...")
                time.sleep(3)
            else:
                return False
    
    return False


# ==================== Android 设备选择 ====================

def _select_device_android(
    driver,
    target_device_config: Dict[str, Any],
    log_func: Callable[[str], None],
    screenshot_dir: Optional[Path] = None,
    max_attempts: int = 3,
    max_scrolls: int = 10,
) -> bool:
    """
    Android 平台设备选择
    
    Args:
        driver: Appium WebDriver 实例
        target_device_config: 目标设备配置字典，包含 device_sn 和 device_name
        log_func: 日志输出函数
        screenshot_dir: 截图保存目录（可选）
        max_attempts: 最大尝试次数
        max_scrolls: 最大滑动次数
    
    Returns:
        bool: 选择成功返回 True，失败返回 False
    """
    device_sn = target_device_config.get('device_sn', 'B0078')
    device_name = target_device_config.get('device_name', 'Sora 70')
    app_package = driver.capabilities.get('appPackage')
    
    log_func(f"🎯 目标设备: {device_name} (SN: {device_sn})")
    
    def _get_parent(elem):
        try:
            return elem.find_element(AppiumBy.XPATH, './..')
        except Exception:
            return None
    
    def _find_clickable_ancestor(elem, max_up=6):
        cur = elem
        for _ in range(max_up):
            if not cur:
                break
            try:
                if str(cur.get_attribute("clickable")).lower() == "true":
                    return cur
            except Exception:
                pass
            cur = _get_parent(cur)
        return elem

    def _find_target_device_elem_fresh():
        """每次都重新定位目标设备元素，避免复用 stale element。"""
        sn_digits_local = device_sn.lstrip('Bb') if device_sn else ""
        sn_with_b_local = f"B{sn_digits_local}" if not device_sn.upper().startswith('B') else device_sn
        fresh_selectors = [
            f'//android.widget.TextView[@text="(SN:{sn_with_b_local})"]',
            f'//android.widget.TextView[@text="(SN: {sn_with_b_local})"]',
            f'//android.widget.TextView[@text="(SN:{sn_digits_local})"]',
            f'//android.widget.TextView[@text="(SN: {sn_digits_local})"]',
            f'//android.widget.TextView[contains(@text,"SN:{sn_with_b_local}")]',
            f'//android.widget.TextView[contains(@text,"SN: {sn_with_b_local}")]',
            f'//android.widget.TextView[contains(@text,"SN:{sn_digits_local}")]',
            f'//android.widget.TextView[contains(@text,"SN: {sn_digits_local}")]',
            f'//android.widget.TextView[contains(@text,"{device_sn}")]',
        ]
        for selector in fresh_selectors:
            try:
                elems = driver.find_elements(AppiumBy.XPATH, selector)
                for elem in elems:
                    try:
                        if elem.is_displayed():
                            txt = elem.text or ""
                            if device_sn in txt or sn_digits_local in txt or sn_with_b_local in txt:
                                return elem
                    except Exception:
                        continue
            except Exception:
                continue
        return None
    
    def _find_add_button_enabled():
        """找"Add"按钮/容器，必须 enabled=true 才算可点击"""
        candidates = [
            '//android.view.View[.//android.widget.TextView[@text="Add"]]',
            '//android.widget.Button[.//android.widget.TextView[@text="Add"]]',
            '//android.widget.TextView[@text="Add"]/ancestor::*[1]',
        ]
        for xp in candidates:
            try:
                els = driver.find_elements(AppiumBy.XPATH, xp)
                for el in els:
                    try:
                        if not el.is_displayed():
                            continue
                        enabled = str(el.get_attribute("enabled")).lower()
                        if enabled == "true":
                            try:
                                clickable = str(el.get_attribute("clickable")).lower()
                                if clickable == "true":
                                    return el
                            except Exception:
                                pass
                            try:
                                btn = el.find_element(AppiumBy.XPATH, ".//android.widget.Button")
                                if btn and btn.is_displayed() and str(btn.get_attribute("enabled")).lower() == "true":
                                    return btn
                            except Exception:
                                return el
                    except Exception:
                        continue
            except Exception:
                continue
        return None
    
    def _check_device_selected(device_elem):
        """检测设备是否处于选中状态"""
        try:
            # 方法1: 检查设备元素或其父容器的 selected 属性
            check_elements = [device_elem]
            try:
                check_elements.append(_find_clickable_ancestor(device_elem))
            except:
                pass
            
            for elem in check_elements:
                try:
                    selected = str(elem.get_attribute("selected")).lower()
                    checked = str(elem.get_attribute("checked")).lower()
                    checkable = str(elem.get_attribute("checkable")).lower()
                    
                    # 如果元素有 selected/checked 属性，检查是否为 true
                    if selected == "true" or checked == "true":
                        return True
                    
                    # 如果元素是 checkable 的，检查是否处于选中状态
                    if checkable == "true":
                        # 尝试查找选中指示器（如 checkbox）
                        try:
                            checkbox = elem.find_element(AppiumBy.XPATH, ".//android.widget.CheckBox[@checked='true']")
                            if checkbox:
                                return True
                        except:
                            pass
                except:
                    continue
            
            # 方法2: 检查是否有视觉选中指示器（如高亮、边框等）
            try:
                # 检查父容器是否有选中相关的属性
                parent = _find_clickable_ancestor(device_elem)
                if parent:
                    # 检查背景色、边框等视觉指示器（如果可用）
                    try:
                        selected_attr = str(parent.get_attribute("selected")).lower()
                        if selected_attr == "true":
                            return True
                    except:
                        pass
            except:
                pass
            
            return False
        except Exception as e:
            log_func(f"⚠️ 检测设备选中状态失败: {e}")
            # 如果检测失败，默认返回 False，让调用者继续点击
            return False
    
    def _ensure_selected_then_click_add(device_elem, timeout=45):
        """
        核心修复点：
        1. 持续检查设备是否处于选中状态
        2. 如果未选中，持续点击设备卡片直到选中
        3. 当 Add 按钮启用时，点击 Add
        4. 点击 Add 后验证是否真的进入了下一步（避免因新设备出现导致状态回退）
        """
        start = time.time()
        last_card_click = 0.0
        last_add_click = 0.0

        log_func("🔄 进入设备选择页：点击目标设备并尝试点击 Add...")

        wifi_setup_indicators = [
            '//android.widget.TextView[@text="Set Up Wi-Fi"]',
            '//android.widget.TextView[contains(@text,"Set up Wi-Fi")]',
            '//android.widget.TextView[contains(@text,"Wi-Fi")]',
            '//android.view.View[@content-desc="password"]',
            '//android.view.View[@content-desc="switch"]',
        ]

        while time.time() - start < timeout:
            # 每轮都刷新目标元素引用，避免 ScrollView 刷新导致 stale
            try:
                fresh_elem = _find_target_device_elem_fresh()
                if fresh_elem is not None:
                    device_elem = fresh_elem
            except Exception:
                pass

            now = time.time()
            # 定期点目标卡片，保证“选中”状态不被新设备刷新冲掉
            if now - last_card_click >= 1.0:
                try:
                    clickable_card = _find_clickable_ancestor(device_elem)
                    clickable_card.click()
                    last_card_click = now
                    log_func("🔄 点击目标设备卡片（保持选中）")
                except Exception as e:
                    log_func(f"⚠️ 点击目标设备卡片失败: {e}")

            # Add：只要按钮启用就点；点之前刚刚点过卡片（保持选中），降低“未选中仍可点”的误差
            try:
                add_btn = _find_add_button_enabled()
                if add_btn and now - last_add_click >= 2.0:
                    log_func("🔍 Add 按钮已启用，点击...")
                    add_btn.click()
                    last_add_click = now
                    log_func("✅ Add 按钮已点击")
                    time.sleep(1.2)
            except Exception as e:
                log_func(f"⚠️ 点击 Add 按钮失败: {e}")

            # 成功判定：进入下一步 WiFi 配网页
            for indicator in wifi_setup_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, indicator)
                    if elem.is_displayed():
                        log_func(f"✅ 已进入下一步页面（检测到: {indicator}），设备选择成功")
                        return True
                except Exception:
                    continue

            # 兜底：设备列表消失也认为进入下一步
            try:
                device_list = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView[contains(@text,"SN")]')
                if not device_list:
                    log_func("✅ 设备列表已消失，已进入下一步页面")
                    return True
            except Exception:
                pass

            time.sleep(0.5)

        log_func("❌ 超时：无法进入 WiFi 设置页面（目标设备/点击 Add 失败或响应过慢）")
        return False
    
    for attempt in range(max_attempts):
        try:
            log_func(f"🔍 第{attempt + 1}次尝试选择设备...")
            
            # 等待页面加载
            time.sleep(2)
            
            # 处理 SN 前缀：配置可能是 "0040" 或 "B0040"，实际显示可能是 "(SN:B0040)" 或 "(SN:0040)"
            sn_digits = device_sn.lstrip('Bb') if device_sn else ""
            sn_with_b = f"B{sn_digits}" if not device_sn.upper().startswith('B') else device_sn
            
            # 优先使用精确匹配的选择器（按精确度排序，支持带/不带 B 前缀）
            device_selectors = [
                # 最精确：完全匹配 SN 格式（带 B 前缀）
                f'//android.widget.TextView[@text="(SN:{sn_with_b})"]',
                f'//android.widget.TextView[@text="(SN: {sn_with_b})"]',
                # 最精确：完全匹配 SN 格式（不带 B 前缀）
                f'//android.widget.TextView[@text="(SN:{sn_digits})"]',
                f'//android.widget.TextView[@text="(SN: {sn_digits})"]',
                # 原始 SN（如果配置中已经带 B）
                f'//android.widget.TextView[@text="(SN:{device_sn})"]',
                f'//android.widget.TextView[@text="(SN: {device_sn})"]',
                # 精确匹配：包含完整 SN（带 B 前缀）
                f'//android.widget.TextView[contains(@text,"SN:{sn_with_b}")]',
                f'//android.widget.TextView[contains(@text,"SN: {sn_with_b}")]',
                # 精确匹配：包含完整 SN（不带 B 前缀）
                f'//android.widget.TextView[contains(@text,"SN:{sn_digits}")]',
                f'//android.widget.TextView[contains(@text,"SN: {sn_digits}")]',
                # 精确匹配：包含完整 SN（原始配置）
                f'//android.widget.TextView[contains(@text,"SN:{device_sn}")]',
                f'//android.widget.TextView[contains(@text,"SN: {device_sn}")]',
                # 精确匹配：包含完整 SN（无冒号）
                f'//android.widget.TextView[contains(@text,"SN {device_sn}")]',
                # 精确匹配：包含完整 SN（无前缀）
                f'//android.widget.TextView[@text="{device_sn}"]',
            ]
            
            device_button = None
            matched_text = None
            
            # 首先尝试不滑动直接查找
            log_func("🔍 首先尝试直接查找设备（不滑动）...")
            for selector in device_selectors:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                    if elements:
                        for elem in elements:
                            try:
                                if elem.is_displayed():
                                    text = elem.text
                                    # 处理 SN 前缀匹配
                                    sn_digits = device_sn.lstrip('Bb') if device_sn else ""
                                    sn_with_b = f"B{sn_digits}" if not device_sn.upper().startswith('B') else device_sn
                                    
                                    # 检查是否匹配（支持带/不带 B 前缀）
                                    if device_sn in text or sn_digits in text or sn_with_b in text:
                                        # 进一步验证：使用正则表达式确保是完整的 SN 匹配
                                        sn_patterns = [
                                            f'SN:{device_sn}', f'SN: {device_sn}',
                                            f'SN:{sn_with_b}', f'SN: {sn_with_b}',
                                            f'SN:{sn_digits}', f'SN: {sn_digits}',
                                            f'\\(SN:{device_sn}\\)', f'\\(SN: {device_sn}\\)',
                                            f'\\(SN:{sn_with_b}\\)', f'\\(SN: {sn_with_b}\\)',
                                            f'\\(SN:{sn_digits}\\)', f'\\(SN: {sn_digits}\\)',
                                        ]
                                        
                                        is_match = False
                                        for pattern in sn_patterns:
                                            if re.search(pattern, text, re.IGNORECASE):
                                                is_match = True
                                                break
                                        
                                        if is_match:
                                            device_button = elem
                                            matched_text = text
                                            log_func(f"✅ 直接找到目标设备元素: {selector}")
                                            log_func(f"   匹配文本: {text}")
                                            break
                            except:
                                continue
                        if device_button:
                            break
                except:
                    continue
            
            # 如果直接查找失败，尝试查找所有设备并验证
            if not device_button:
                log_func("🔍 直接查找失败，查找所有设备元素进行验证...")
                try:
                    all_device_elements = driver.find_elements(
                        AppiumBy.XPATH, 
                        '//android.widget.TextView[contains(@text,"SN")]'
                    )
                    
                    log_func(f"🔍 找到 {len(all_device_elements)} 个可能的设备元素")
                    
                    for elem in all_device_elements:
                        try:
                            if elem.is_displayed():
                                text = elem.text
                                log_func(f"   检查设备: {text}")
                                
                                # 处理 SN 前缀：配置可能是 "0040" 或 "B0040"，实际显示可能是 "(SN:B0040)" 或 "(SN:0040)"
                                # 提取 SN 的数字部分（去掉 B 前缀）
                                sn_digits = device_sn.lstrip('Bb') if device_sn else ""
                                sn_with_b = f"B{sn_digits}" if not device_sn.upper().startswith('B') else device_sn
                                
                                # 检查文本中是否包含 SN（支持多种格式）
                                if device_sn in text or sn_digits in text or sn_with_b in text:
                                    # 进一步验证：确保是完整的 SN 匹配（支持带/不带 B 前缀）
                                    sn_patterns = [
                                        # 原始 SN（带 B 前缀）
                                        f'SN:{device_sn}',
                                        f'SN: {device_sn}',
                                        f'SN {device_sn}',
                                        f'\\(SN:{device_sn}\\)',
                                        f'\\(SN: {device_sn}\\)',
                                        # 带 B 前缀的 SN
                                        f'SN:{sn_with_b}',
                                        f'SN: {sn_with_b}',
                                        f'SN {sn_with_b}',
                                        f'\\(SN:{sn_with_b}\\)',
                                        f'\\(SN: {sn_with_b}\\)',
                                        # 不带 B 前缀的 SN（仅数字部分）
                                        f'SN:{sn_digits}',
                                        f'SN: {sn_digits}',
                                        f'SN {sn_digits}',
                                        f'\\(SN:{sn_digits}\\)',
                                        f'\\(SN: {sn_digits}\\)',
                                    ]
                                    
                                    is_match = False
                                    matched_pattern = None
                                    for pattern in sn_patterns:
                                        if re.search(pattern, text, re.IGNORECASE):
                                            is_match = True
                                            matched_pattern = pattern
                                            break
                                    
                                    if is_match:
                                        device_button = elem
                                        matched_text = text
                                        log_func(f"✅ 验证通过，找到目标设备: {text} (匹配模式: {matched_pattern})")
                                        break
                                    else:
                                        log_func(f"⚠️ SN 部分匹配但正则验证失败: 文本='{text}', 配置SN='{device_sn}', 数字部分='{sn_digits}'")
                        except Exception as e:
                            log_func(f"⚠️ 检查设备元素时出错: {e}")
                            continue
                except Exception as e:
                    log_func(f"⚠️ 查找所有设备元素失败: {e}")
            
            # 如果仍然找不到，先向上滑动到顶部，然后双向滑动查找
            if not device_button:
                log_func("🔍 未找到设备，先向上滑动到顶部，然后双向滑动查找...")
                
                # 先向上滑动到顶部
                log_func("⬆️ 向上滑动到列表顶部...")
                for top_scroll in range(5):
                    try:
                        size = driver.get_window_size()
                        start_x = size['width'] // 2
                        start_y = int(size['height'] * 0.3)
                        end_y = int(size['height'] * 0.7)
                        driver.swipe(start_x, start_y, start_x, end_y, 500)
                        time.sleep(1)
                    except:
                        try:
                            driver.execute_script("mobile: scroll", {"direction": "up"})
                            time.sleep(1)
                        except:
                            break
                
                time.sleep(2)
                
                # 从顶部开始，先向下滑动查找
                log_func("⬇️ 从顶部开始向下滑动查找...")
                for scroll_attempt in range(max_scrolls):
                    log_func(f"🔍 第{scroll_attempt + 1}/{max_scrolls}次向下滑动查找设备...")
                    
                    for selector in device_selectors:
                        try:
                            elements = driver.find_elements(AppiumBy.XPATH, selector)
                            if elements:
                                for elem in elements:
                                    try:
                                        if elem.is_displayed():
                                            text = elem.text
                                            # 处理 SN 前缀匹配
                                            sn_digits = device_sn.lstrip('Bb') if device_sn else ""
                                            sn_with_b = f"B{sn_digits}" if not device_sn.upper().startswith('B') else device_sn
                                            
                                            # 检查是否匹配（支持带/不带 B 前缀）
                                            if device_sn in text or sn_digits in text or sn_with_b in text:
                                                # 进一步验证：使用正则表达式确保是完整的 SN 匹配
                                                sn_patterns = [
                                                    f'SN:{device_sn}', f'SN: {device_sn}',
                                                    f'SN:{sn_with_b}', f'SN: {sn_with_b}',
                                                    f'SN:{sn_digits}', f'SN: {sn_digits}',
                                                    f'\\(SN:{device_sn}\\)', f'\\(SN: {device_sn}\\)',
                                                    f'\\(SN:{sn_with_b}\\)', f'\\(SN: {sn_with_b}\\)',
                                                    f'\\(SN:{sn_digits}\\)', f'\\(SN: {sn_digits}\\)',
                                                ]
                                                
                                                is_match = False
                                                for pattern in sn_patterns:
                                                    if re.search(pattern, text, re.IGNORECASE):
                                                        is_match = True
                                                        break
                                                
                                                if is_match:
                                                    device_button = elem
                                                    matched_text = text
                                                    log_func(f"✅ 向下滑动后找到目标设备: {text}")
                                                    break
                                    except:
                                        continue
                                if device_button:
                                    break
                        except:
                            continue
                    
                    if device_button:
                        break
                    
                    # 向下滑动
                    try:
                        size = driver.get_window_size()
                        start_x = size['width'] // 2
                        start_y = int(size['height'] * 0.6)
                        end_y = int(size['height'] * 0.3)
                        driver.swipe(start_x, start_y, start_x, end_y, 500)
                        time.sleep(1.5)
                    except Exception as swipe_err:
                        try:
                            driver.execute_script("mobile: scroll", {"direction": "down"})
                            time.sleep(1.5)
                        except:
                            log_func(f"⚠️ 滑动失败: {swipe_err}")
                            time.sleep(1)
                
                # 如果向下滑动没找到，尝试向上滑动查找
                if not device_button:
                    log_func("⬆️ 向下滑动未找到，尝试向上滑动查找...")
                    for scroll_attempt in range(max_scrolls):
                        log_func(f"🔍 第{scroll_attempt + 1}/{max_scrolls}次向上滑动查找设备...")
                        
                        for selector in device_selectors:
                            try:
                                elements = driver.find_elements(AppiumBy.XPATH, selector)
                                if elements:
                                    for elem in elements:
                                        try:
                                            if elem.is_displayed():
                                                text = elem.text
                                                # 处理 SN 前缀匹配
                                                sn_digits = device_sn.lstrip('Bb') if device_sn else ""
                                                sn_with_b = f"B{sn_digits}" if not device_sn.upper().startswith('B') else device_sn
                                                
                                                # 检查是否匹配（支持带/不带 B 前缀）
                                                if device_sn in text or sn_digits in text or sn_with_b in text:
                                                    # 进一步验证：使用正则表达式确保是完整的 SN 匹配
                                                    sn_patterns = [
                                                        f'SN:{device_sn}', f'SN: {device_sn}',
                                                        f'SN:{sn_with_b}', f'SN: {sn_with_b}',
                                                        f'SN:{sn_digits}', f'SN: {sn_digits}',
                                                        f'\\(SN:{device_sn}\\)', f'\\(SN: {device_sn}\\)',
                                                        f'\\(SN:{sn_with_b}\\)', f'\\(SN: {sn_with_b}\\)',
                                                        f'\\(SN:{sn_digits}\\)', f'\\(SN: {sn_digits}\\)',
                                                    ]
                                                    
                                                    is_match = False
                                                    for pattern in sn_patterns:
                                                        if re.search(pattern, text, re.IGNORECASE):
                                                            is_match = True
                                                            break
                                                    
                                                    if is_match:
                                                        device_button = elem
                                                        matched_text = text
                                                        log_func(f"✅ 向上滑动后找到目标设备: {text}")
                                                        break
                                        except:
                                            continue
                                    if device_button:
                                        break
                            except:
                                continue
                        
                        if device_button:
                            break
                        
                        # 向上滑动
                        try:
                            size = driver.get_window_size()
                            start_x = size['width'] // 2
                            start_y = int(size['height'] * 0.3)
                            end_y = int(size['height'] * 0.7)
                            driver.swipe(start_x, start_y, start_x, end_y, 500)
                            time.sleep(1.5)
                        except Exception as swipe_err:
                            try:
                                driver.execute_script("mobile: scroll", {"direction": "up"})
                                time.sleep(1.5)
                            except:
                                log_func(f"⚠️ 滑动失败: {swipe_err}")
                                time.sleep(1)
            
            if not device_button:
                log_func("❌ 未找到目标设备元素")
                if attempt < max_attempts - 1:
                    log_func("⏳ 等待2秒后重试...")
                    time.sleep(2)
                    continue
                else:
                    log_func(f"❌ 经过 {max_attempts} 次尝试，仍未找到目标设备 SN: {device_sn}")
                    return False
            
            # 再次验证匹配的文本
            if matched_text and device_sn not in matched_text:
                log_func(f"❌ 验证失败：匹配的文本 '{matched_text}' 不包含目标 SN '{device_sn}'")
                if attempt < max_attempts - 1:
                    log_func("⏳ 等待2秒后重试...")
                    time.sleep(2)
                    continue
                else:
                    return False
            
            # 点击设备
            log_func(f"✅ 确认选择设备: {matched_text}")
            try:
                _find_clickable_ancestor(device_button).click()
            except Exception:
                device_button.click()
            log_func("✅ 点击设备成功")
            time.sleep(1)
            
            # 关键：持续补选直到 Add 可用并点击（解决"新设备出现导致取消选中"）
            if _ensure_selected_then_click_add(device_button, timeout=35):
                log_func("✅ 设备选择并点击 Add 成功")
                time.sleep(2)
                return True
            else:
                log_func("⚠️ Add 按钮未启用或未找到，尝试走确认按钮流程兜底...")
                confirm_selectors = [
                    '//android.widget.Button',
                    '//android.widget.Button[contains(@text,"确定")]',
                    '//android.widget.Button[contains(@text,"OK")]',
                    '//android.widget.Button[contains(@text,"Confirm")]'
                ]
                
                confirm_button = None
                for selector in confirm_selectors:
                    try:
                        confirm_button = driver.find_element(AppiumBy.XPATH, selector)
                        log_func(f"✅ 找到确定按钮: {selector}")
                        break
                    except:
                        continue
                
                if confirm_button:
                    confirm_button.click()
                    log_func("✅ 点击确定按钮")
                    time.sleep(2)
                    return True
                else:
                    log_func("⚠️ 未找到确定按钮，但设备选择成功")
                    return True
                
        except Exception as e:
            log_func(f"❌ 第{attempt + 1}次选择设备失败: {e}")
            import traceback
            log_func(f"   详细错误: {traceback.format_exc()}")
            if attempt < max_attempts - 1:
                log_func("⏳ 等待3秒后重试...")
                time.sleep(3)
            else:
                return False
    
    return False


# ==================== 统一接口 ====================

def select_device(
    driver,
    target_device_config: Dict[str, Any],
    platform: str = "auto",
    log_func: Optional[Callable[[str], None]] = None,
    screenshot_dir: Optional[Path] = None,
    max_attempts: int = 3,
    max_scrolls: int = 10,
) -> bool:
    """
    设备选择统一接口（支持 iOS 和 Android）
    
    Args:
        driver: Appium WebDriver 实例
        target_device_config: 目标设备配置字典，必须包含：
            - device_sn: 设备序列号（如 "B0078" 或 "0078"）
            - device_name: 设备名称（如 "Sora 70"）
        platform: 平台类型，"ios"、"android" 或 "auto"（自动检测）
        log_func: 日志输出函数（可选，默认使用 print）
        screenshot_dir: 截图保存目录（可选）
        max_attempts: 最大尝试次数（默认 3）
        max_scrolls: 最大滑动次数（默认 10）
    
    Returns:
        bool: 选择成功返回 True，失败返回 False
    
    Example:
        # 作为模块使用
        from 选择设备 import select_device
        
        result = select_device(
            driver=driver,
            target_device_config={
                "device_sn": "B0078",
                "device_name": "Sora 70"
            },
            platform="ios",
            log_func=log
        )
    """
    # 设置日志函数
    log = _setup_logging(log_func)
    
    # 自动检测平台
    if platform == "auto":
        try:
            caps = driver.capabilities
            platform_name = caps.get("platformName", "").lower()
            if "ios" in platform_name:
                platform = "ios"
            elif "android" in platform_name:
                platform = "android"
            else:
                # 尝试从其他属性判断
                if caps.get("bundleId") or caps.get("udid"):
                    platform = "ios"
                elif caps.get("appPackage") or caps.get("appActivity"):
                    platform = "android"
                else:
                    log("⚠️ 无法自动检测平台，默认使用 iOS")
                    platform = "ios"
        except Exception as e:
            log(f"⚠️ 自动检测平台失败: {e}，默认使用 iOS")
            platform = "ios"
    
    platform = platform.lower()
    
    if platform == "ios":
        return _select_device_ios(
            driver=driver,
            target_device_config=target_device_config,
            log_func=log,
            screenshot_dir=screenshot_dir,
            max_attempts=max_attempts,
            max_scrolls=max_scrolls,
        )
    elif platform == "android":
        return _select_device_android(
            driver=driver,
            target_device_config=target_device_config,
            log_func=log,
            screenshot_dir=screenshot_dir,
            max_attempts=max_attempts,
            max_scrolls=max_scrolls,
        )
    else:
        log(f"❌ 不支持的平台: {platform}，支持的平台: ios, android")
        return False


# ==================== 独立脚本模式 ====================

def _load_config() -> Optional[Dict[str, Any]]:
    """加载配置文件"""
    script_dir = Path(__file__).resolve().parent
    config_paths = [
        script_dir / "device_config.json",
        script_dir.parent / "device_config.json",
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                print(f"✅ 加载配置文件: {config_path}")
                return config
            except Exception as e:
                print(f"⚠️ 加载配置文件失败 {config_path}: {e}")
    
    print("❌ 未找到配置文件 device_config.json")
    return None


def _create_driver_ios(device_config: Dict[str, Any]):
    """创建 iOS driver"""
    from appium.options.ios import XCUITestOptions
    
    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.device_name = device_config["device_name"]
    options.platform_version = device_config["platform_version"]
    options.bundle_id = device_config.get("bundle_id") or device_config.get("app_package")
    options.automation_name = "XCUITest"
    options.no_reset = True
    options.new_command_timeout = 300
    
    if "udid" in device_config:
        options.udid = device_config["udid"]
    
    server_url = f"http://127.0.0.1:{device_config['port']}"
    print(f"🔗 连接 Appium 服务器: {server_url}")
    driver = webdriver.Remote(server_url, options=options)
    print(f"✅ 设备连接成功: {device_config.get('description', device_config['device_name'])}")
    return driver


def _create_driver_android(device_config: Dict[str, Any]):
    """创建 Android driver"""
    from appium.options.android import UiAutomator2Options
    
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name = device_config["device_name"]
    options.platform_version = device_config["platform_version"]
    options.app_package = device_config.get("app_package")
    options.app_activity = device_config.get("app_activity")
    options.automation_name = "UiAutomator2"
    options.no_reset = True
    options.new_command_timeout = 300
    
    server_url = f"http://127.0.0.1:{device_config['port']}"
    print(f"🔗 连接 Appium 服务器: {server_url}")
    driver = webdriver.Remote(server_url, options=options)
    print(f"✅ 设备连接成功: {device_config.get('description', device_config['device_name'])}")
    return driver


def main():
    """独立脚本模式的主函数"""
    print("🚀 启动设备选择独立脚本")
    print("=" * 80)
    
    # 加载配置
    config = _load_config()
    if not config:
        return 1
    
    target_device = config.get("target_device")
    if not target_device:
        print("❌ 未找到 target_device 配置")
        print("💡 请在 device_config.json 中添加 target_device 配置")
        return 1
    
    device_configs = config.get("device_configs", {})
    if not device_configs:
        print("❌ 未找到 device_configs 配置")
        return 1
    
    # 选择第一个设备进行测试
    first_device_key = list(device_configs.keys())[0]
    first_device = device_configs[first_device_key]
    platform = first_device.get("platform", "ios").lower()
    
    driver = None
    try:
        # 创建 driver
        if platform == "ios":
            driver = _create_driver_ios(first_device)
        elif platform == "android":
            driver = _create_driver_android(first_device)
        else:
            print(f"❌ 不支持的平台: {platform}")
            return 1
        
        # 执行设备选择
        print(f"\n📱 开始选择设备...")
        print(f"   目标设备: {target_device.get('device_name')} (SN: {target_device.get('device_sn')})")
        print("-" * 80)
        
        result = select_device(
            driver=driver,
            target_device_config=target_device,
            platform=platform,
        )
        
        if result:
            print("\n✅ 设备选择成功！")
            return 0
        else:
            print("\n❌ 设备选择失败！")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断脚本")
        return 1
    except Exception as e:
        print(f"\n❌ 脚本异常: {e}")
        import traceback
        print(f"详细错误: {traceback.format_exc()}")
        return 1
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


if __name__ == "__main__":
    sys.exit(main())
