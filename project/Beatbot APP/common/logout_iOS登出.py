"""
iOS 登出流程工具。

主要用途：
- 检测当前 iOS 端是否处于已登录状态
- 自动进入个人中心执行登出
- 为 iOS 用例提供统一的前置清理能力
"""

import time

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def check_and_logout(driver) -> None:
    """
    检查并执行登出流程（iOS），未检测到首页元素则跳过。
    优化：快速检测，减少等待时间
    """
    try:
        print("开始登出流程...")

        def wait_and_click(xpath_list, wait_time=2, desc=""):
            """依次尝试多个 xpath，找到即点击。
            优化：先快速尝试所有xpath，如果快速查找失败，再对第一个xpath使用WebDriverWait。
            """
            # 快速尝试所有xpath
            for xp in xpath_list:
                try:
                    el = driver.find_element(AppiumBy.XPATH, xp)
                    if el.is_displayed() and el.is_enabled():
                        el.click()
                        if desc:
                            print(f"✅ 点击{desc}: {xp}")
                        return True
                except (Exception):
                    continue
            
            # 如果快速查找失败，对第一个xpath使用WebDriverWait
            if xpath_list:
                try:
                    el = WebDriverWait(driver, wait_time).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, xpath_list[0]))
                    )
                    if el.is_displayed() and el.is_enabled():
                        el.click()
                        if desc:
                            print(f"✅ 点击{desc}: {xpath_list[0]} (通过等待)")
                        return True
                except Exception:
                    pass
            
            return False

        # 快速检测：先尝试find_elements，不等待
        found = False
        for xpath, name in [
            ('//XCUIElementTypeButton[@name="home sel"]', "home sel"),
            ('//XCUIElementTypeButton[@name="mine sel"]', "mine sel"),
            ('//XCUIElementTypeButton[@name="mine"]', "mine"),
        ]:
            try:
                elements = driver.find_elements(AppiumBy.XPATH, xpath)
                for elem in elements:
                    if elem.is_displayed():
                        print(f"检测到{name}元素")
                        found = True
                        break
                if found:
                    break
            except Exception:
                continue
        
        # 如果快速检测失败，最多重试1次（减少重试次数）
        if not found:
            time.sleep(0.5)  # 短暂等待
            for xpath, name in [
                ('//XCUIElementTypeButton[@name="home sel"]', "home sel"),
                ('//XCUIElementTypeButton[@name="mine sel"]', "mine sel"),
                ('//XCUIElementTypeButton[@name="mine"]', "mine"),
            ]:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, xpath)
                    for elem in elements:
                        if elem.is_displayed():
                            print(f"检测到{name}元素（重试）")
                            found = True
                            break
                    if found:
                        break
                except Exception:
                    continue

        if not found:
            print("未检测到home sel/mine sel/mine，跳过登出流程")
            return

        try:
            # 优先尝试点击mine sel按钮（进入设置）
            if wait_and_click(['//XCUIElementTypeButton[@name="mine sel"]'], wait_time=2, desc="mine sel按钮（进入设置）"):
                time.sleep(1)  # 减少等待时间
            elif wait_and_click(['//XCUIElementTypeButton[@name="mine"]'], wait_time=2, desc="mine按钮"):
                time.sleep(1)  # 减少等待时间
            else:
                print("点击mine sel/mine按钮失败，跳过登出流程")
                return
        except Exception as e:
            print("点击mine sel/mine按钮异常（可能已在设置页）:", e)
            return  # 添加return，避免继续执行

        try:
            # 点击CommonEdit编辑按钮
            if wait_and_click(['//XCUIElementTypeButton[@name="CommonEdit"]'], wait_time=2, desc="CommonEdit编辑按钮"):
                time.sleep(1)  # 减少等待时间
            else:
                print("未找到CommonEdit编辑按钮，结束登出流程")
                return
        except Exception as e:
            print("点击CommonEdit编辑按钮异常:", e)
            return

        # “Log Out” 按钮兼容大小写/空格
        if wait_and_click([
            '//XCUIElementTypeButton[@name="Log Out"]',
            '//XCUIElementTypeButton[@name="logout"]',
            '//XCUIElementTypeButton[contains(@name,"Log Out")]'
        ], wait_time=2, desc="Log Out"):
            time.sleep(1)  # 减少等待时间
        else:
            print("未找到Log Out按钮，结束登出流程")
            return

        try:
            if wait_and_click(['//XCUIElementTypeButton[@name="Confirm"]'], wait_time=2, desc="Confirm"):
                time.sleep(1.5)  # 减少等待时间
                print("登出操作完成")

                # 验证返回登录页：快速检测Sign In / Sign Up
                try:
                    # 快速检测，不等待
                    sign_in_elements = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]')
                    sign_up_elements = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign Up"]')
                    
                    sign_in_found = any(elem.is_displayed() for elem in sign_in_elements)
                    sign_up_found = any(elem.is_displayed() for elem in sign_up_elements)
                    
                    if sign_in_found or sign_up_found:
                        print("✅ 成功回到登录页面")
                    else:
                        # 如果快速检测失败，使用WebDriverWait（但时间缩短）
                        WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]'))
                        )
                        print("✅ 成功回到登录页面（通过等待）")
                except Exception:
                    print("⚠️ 可能未完全回到登录页面，尝试再次点击返回登录控件")
                    wait_and_click([
                        '//XCUIElementTypeButton[@name="Sign In"]',
                        '//XCUIElementTypeButton[@name="Sign Up"]'
                    ], wait_time=2, desc="登录页按钮（补偿点击）")

        except Exception as e:
            print("点击Confirm按钮异常:", e)
            try:
                driver.save_screenshot(f"screenshots/Confirm按钮点击失败_{int(time.time())}.png")
                print("已保存Confirm按钮点击失败截图")
            except Exception:
                pass

    except Exception as e:
        print(f"登出流程异常: {e}")

