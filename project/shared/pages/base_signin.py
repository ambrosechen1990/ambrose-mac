from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from test_framework import TestCase

class BaseSignIn(TestCase):
    """登录相关的基类，包含所有登录方法"""
    
    def login_with_email(self, email: str, password: str):
        """使用邮箱和密码登录"""
        try:
            # 点击Sign In按钮
            self.driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]').click()
            time.sleep(3)

            # 输入邮箱
            email_input = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
            )
            email_input.click()
            email_input.send_keys('haoc51888@gmail.com')
            print("✅ 输入邮箱")

            # 输入密码
            password_input = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeSecureTextField"'))
            )
            password_input.clear()
            password_input.send_keys('Csx150128')
            time.sleep(3)

            # 点击Sign In按钮
            self.driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign In"]').click()
            time.sleep(5)

            # 验证登录成功
            return self.verify_login_success()
        except Exception as e:
            print(f"❌ 登录失败: {e}")
            return False

    def verify_login_success(self):
        """验证是否登录成功"""
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH,
                    "//XCUIElementTypeStaticText[@name='Home']"))
            )
            print("✅ 登录成功")
            return True
        except Exception as e:
            print(f"❌ 登录失败: {e}")
            return False
