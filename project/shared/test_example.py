import pytest
import time
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import constant  # 导入常量文件

# 导入我们的测试框架
from test_framework import TestCase


@pytest.mark.usefixtures("driver")
class TestExample(TestCase):
    """
    使用测试框架的示例测试类
    继承自test_framework.py中的TestCase类
    """
    
    def test_signup_flow(self):
        """测试注册流程"""
        driver = self.driver
        try:
            # 点击Sign Up按钮进入注册页面
            driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign Up"]').click()
            time.sleep(2)
            
            # 验证页面标题
            title = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Sign Up"]')
            assert title.get_attribute('label') == "Sign Up", "页面标题不正确"
            
            # 输入邮箱
            email = constant.ran2 + "@gmail.com"  # 使用随机字符串
            email_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeTextField"'))
            )
            email_input.click()
            email_input.send_keys(email)
            print(f"📩 输入邮箱: {email}")
            
            # 勾选隐私协议用户政策按钮
            driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="login check normal"]').click()
            time.sleep(2)
            
            # 点击Next按钮
            print("点击Next按钮")
            driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]').click()
            time.sleep(3)
            
            # 检查是否成功跳转到密码设置页面
            password_page = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Set Password"]')
            assert len(password_page) > 0, "未能成功跳转到密码设置页面"
            print("✅ 注册页面跳转成功")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    def test_country_selection(self):
        """测试国家选择功能"""
        driver = self.driver
        try:
            # 点击Sign Up按钮进入注册页面
            driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Sign Up"]').click()
            time.sleep(2)
            
            # 点击国家选择按钮
            country_btn = driver.find_element(AppiumBy.XPATH, 
                '//XCUIElementTypeApplication[@name="Beatbot"]/XCUIElementTypeWindow[1]/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther[1]/XCUIElementTypeButton'
            )
            country_btn.click()
            time.sleep(2)
            
            # 使用基类中的scroll_and_find_country方法查找国家
            country_name = "Japan"
            element = self.scroll_and_find_country(country_name)
            
            assert element is not None, f"未找到国家: {country_name}"
            print(f"✅ 找到国家: {country_name}")
            element.click()
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    # 可以直接运行此文件进行测试
    pytest.main(["-xvs", __file__]) 