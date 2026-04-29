import time
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def check_and_logout(driver) -> None:
    """
    检查并执行登出流程（Android）
    
    步骤：
    1. 检查页面是否有 More 按钮（不重置APP，因为调用方已经重置）
    2. 点击 More 按钮，进入 more 页面
    3. 点击 edit 按钮
    4. 进入 Account and Security 页面，点击 Log Out 按钮
    5. 页面跳出弹框，点击 Confirm，退出已登录账号
    """
    try:
        print("    [登出] 开始登出流程...")
        
        # 步骤1: 检查页面是否有 More 按钮（使用多个XPath，包括Compose路径）
        print("    [登出] 步骤1: 检查页面是否有 More 按钮")
        more_selectors = [
            # content-desc 为 More 的视图（优先使用）
            '//android.view.View[@content-desc="More"]',
            # Compose 路径（用户提供的正确路径）
            "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.view.View[2]",
            # 备用 Compose 路径（旧版本兼容）
            "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[3]/android.view.View[2]",
            # 备用 Compose 路径
            "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[4]/android.view.View/android.view.View[2]",
        ]
        
        more_found = False
        more_element = None
        used_selector = None
        
        for selector in more_selectors:
            try:
                more_elements = driver.find_elements(AppiumBy.XPATH, selector)
                for elem in more_elements:
                    if elem.is_displayed():
                        more_found = True
                        more_element = elem
                        used_selector = selector
                        print(f"    [登出] ✅ 检测到 More 按钮: {selector}")
                        break
                if more_found:
                    break
            except Exception as e:
                print(f"    [登出] ⚠️ 检查 More 按钮时出错 (selector={selector}): {e}")
                continue
        
        if not more_found:
            print("    [登出] ℹ️ 未检测到 More 按钮，可能未登录，跳过登出流程")
            return
        
        # 步骤2: 点击 More 按钮，进入 more 页面
        print("    [登出] 步骤2: 点击 More 按钮，进入 more 页面")
        try:
            # 如果已经找到了元素，直接使用；否则重新等待
            if more_element:
                more_btn = more_element
            else:
                more_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, used_selector or more_selectors[0]))
                )
            
            # 尝试点击
            more_btn.click()
            print(f"    [登出] ✅ 已点击 More 按钮 (使用: {used_selector})")
            time.sleep(2)  # 增加等待时间，确保页面跳转完成
        except Exception as e:
            print(f"    [登出] ❌ 点击 More 按钮失败: {e}")
            # 尝试使用备用方法：直接使用找到的元素点击
            try:
                if more_element:
                    more_element.click()
                    print("    [登出] ✅ 使用备用方法点击 More 按钮成功")
                    time.sleep(2)
                else:
                    raise
            except Exception as e2:
                print(f"    [登出] ❌ 备用方法也失败: {e2}")
                raise
        
        # 步骤3: 点击 edit 按钮
        print("    [登出] 步骤3: 点击 edit 按钮")
        try:
            edit_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="edit"]')
                )
            )
            edit_btn.click()
            print("    [登出] ✅ 已点击 edit 按钮")
            time.sleep(2)  # 增加等待时间，确保进入 Account and Security 页面
        except Exception as e:
            print(f"    [登出] ❌ 点击 edit 按钮失败: {e}")
            print("    [登出] ⚠️ 尝试查找当前页面元素...")
            # 尝试获取当前页面源码的一部分用于调试
            try:
                page_source = driver.page_source[:500]  # 只取前500字符
                print(f"    [登出] 当前页面源码片段: {page_source}")
            except:
                pass
            raise
        
        # 步骤4: 进入 Account and Security 页面，点击 Log Out 按钮
        print("    [登出] 步骤4: 点击 Log Out 按钮")
        try:
            logout_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (AppiumBy.XPATH, '//android.widget.TextView[@text="Log Out"]')
                )
            )
            logout_btn.click()
            print("    [登出] ✅ 已点击 Log Out 按钮")
            time.sleep(1.5)  # 增加等待时间，确保弹框出现
        except Exception as e:
            print(f"    [登出] ❌ 点击 Log Out 按钮失败: {e}")
            print("    [登出] ⚠️ 尝试查找当前页面元素...")
            # 尝试获取当前页面源码的一部分用于调试
            try:
                page_source = driver.page_source[:500]
                print(f"    [登出] 当前页面源码片段: {page_source}")
            except:
                pass
            raise
        
        # 步骤5: 页面跳出弹框，点击 Confirm，退出已登录账号
        print("    [登出] 步骤5: 点击 Confirm 按钮，确认登出")
        try:
            confirm_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (AppiumBy.XPATH, '//android.widget.TextView[@text="Confirm"]')
                )
            )
            confirm_btn.click()
            print("    [登出] ✅ 已点击 Confirm 按钮")
            time.sleep(3)  # 增加等待时间，确保登出完成，返回登录页面
            
            # 验证是否成功登出（检查是否回到登录页面）
            try:
                # 尝试查找登录页面的特征元素（Sign In 或 Sign Up 按钮）
                sign_in_elements = driver.find_elements(
                    AppiumBy.XPATH, '//android.widget.Button[contains(@text, "Sign")]'
                )
                if sign_in_elements:
                    print("    [登出] ✅ 成功登出，已返回登录页面")
                else:
                    print("    [登出] ⚠️ 登出完成，但无法确认是否已返回登录页面")
            except Exception:
                print("    [登出] ⚠️ 无法验证登出结果，但登出操作已完成")
            
        except Exception as e:
            print(f"    [登出] ❌ 点击 Confirm 按钮失败: {e}")
            print("    [登出] ⚠️ 尝试查找当前页面元素...")
            # 尝试获取当前页面源码的一部分用于调试
            try:
                page_source = driver.page_source[:500]
                print(f"    [登出] 当前页面源码片段: {page_source}")
            except:
                pass
            raise
        
        print("    [登出] ✅ 登出流程完成")
        
    except Exception as e:
        print(f"    [登出] ❌ 登出流程异常: {e}")
        import traceback
        print(f"    [登出] 异常堆栈: {traceback.format_exc()}")
        # 抛出异常，让调用方知道登出失败
        raise

