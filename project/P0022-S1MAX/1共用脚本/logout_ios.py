import time

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# ========= 多语言按钮文本映射 =========
# Log Out 按钮的多语言文本
LOGOUT_BUTTON_TEXTS = [
    "退出登录",  # zh
    "Log Out",  # en
    "Déconnexion",  # fr
    "Disconnetti",  # it
    "Abmelden",  # de
    "Cerrar sesión",  # es
    "Sair",  # pt
    "logout",  # 小写变体
]

# Confirm 按钮的多语言文本
CONFIRM_BUTTON_TEXTS = [
    "确认",  # zh
    "Confirm",  # en
    "Confirmer",  # fr
    "Conferma",  # it
    "Bestätigen",  # de
    "Confirmar",  # es/pt
]

# Sign In / Sign Up 按钮的多语言文本（用于验证是否回到登录页面）
SIGN_IN_BUTTON_TEXTS = [
    "1登录",  # zh
    "Sign In",  # en
    "Se connecter",  # fr
    "Accedi",  # it
    "Anmelden",  # de
    "Iniciar sesión",  # es
    "Entrar",  # pt
]

SIGN_UP_BUTTON_TEXTS = [
    "2注册",  # zh
    "Sign Up",  # en
    "S'inscrire",  # fr
    "Registrati",  # it
    "Registrieren",  # de
    "Registrarse",  # es
    "Registrar-se",  # pt
]


def get_logout_button_xpaths() -> list:
    """获取 Log Out 按钮的多语言XPath列表"""
    xpaths = []
    for text in LOGOUT_BUTTON_TEXTS:
        xpaths.append(f'//XCUIElementTypeButton[@name="{text}"]')
        xpaths.append(f'//XCUIElementTypeButton[contains(@name,"{text}")]')
    return xpaths


def get_confirm_button_xpaths() -> list:
    """获取 Confirm 按钮的多语言XPath列表"""
    xpaths = []
    for text in CONFIRM_BUTTON_TEXTS:
        xpaths.append(f'//XCUIElementTypeButton[@name="{text}"]')
    return xpaths


def get_sign_in_up_button_xpaths() -> list:
    """获取 Sign In / Sign Up 按钮的多语言XPath列表（用于验证登录页面）"""
    xpaths = []
    for text in SIGN_IN_BUTTON_TEXTS:
        xpaths.append(f'//XCUIElementTypeButton[@name="{text}"]')
    for text in SIGN_UP_BUTTON_TEXTS:
        xpaths.append(f'//XCUIElementTypeButton[@name="{text}"]')
    return xpaths


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

        # “Log Out” 按钮（多语言支持）
        logout_xpaths = get_logout_button_xpaths()
        if wait_and_click(logout_xpaths, wait_time=2, desc="Log Out（多语言）"):
            time.sleep(1)  # 减少等待时间
        else:
            print("未找到Log Out按钮（已尝试多语言），结束登出流程")
            return

        try:
            # Confirm 按钮（多语言支持）
            confirm_xpaths = get_confirm_button_xpaths()
            if wait_and_click(confirm_xpaths, wait_time=2, desc="Confirm（多语言）"):
                time.sleep(1.5)  # 减少等待时间
                print("登出操作完成")

                # 验证返回登录页：快速检测Sign In / Sign Up（多语言支持）
                try:
                    # 快速检测，不等待
                    sign_in_up_xpaths = get_sign_in_up_button_xpaths()
                    sign_in_up_elements = driver.find_elements(AppiumBy.XPATH, ' | '.join(sign_in_up_xpaths))
                    
                    sign_in_up_found = any(elem.is_displayed() for elem in sign_in_up_elements)
                    
                    if sign_in_up_found:
                        print("✅ 成功回到登录页面")
                    else:
                        # 如果快速检测失败，使用WebDriverWait（但时间缩短）
                        # 尝试等待第一个Sign In按钮（多语言）
                        found = False
                        for xpath in sign_in_up_xpaths[:3]:  # 只等待前3个常见的
                            try:
                                WebDriverWait(driver, 2).until(
                                    EC.presence_of_element_located((AppiumBy.XPATH, xpath))
                                )
                                print("✅ 成功回到登录页面（通过等待）")
                                found = True
                                break
                            except Exception:
                                continue
                        if not found:
                            print("⚠️ 可能未完全回到登录页面，尝试再次点击返回登录控件")
                            wait_and_click(sign_in_up_xpaths[:5], wait_time=2, desc="登录页按钮（补偿点击，多语言）")
                except Exception:
                    print("⚠️ 可能未完全回到登录页面，尝试再次点击返回登录控件")
                    sign_in_up_xpaths = get_sign_in_up_button_xpaths()
                    wait_and_click(sign_in_up_xpaths[:5], wait_time=2, desc="登录页按钮（补偿点击，多语言）")

        except Exception as e:
            print("点击Confirm按钮异常:", e)
            try:
                driver.save_screenshot(f"screenshots/Confirm按钮点击失败_{int(time.time())}.png")
                print("已保存Confirm按钮点击失败截图")
            except Exception:
                pass

    except Exception as e:
        print(f"登出流程异常: {e}")

