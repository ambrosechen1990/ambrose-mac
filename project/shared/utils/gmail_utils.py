import time
import re
from typing import Optional
from datetime import datetime, timedelta
import sys
import os
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import imaplib
import email
import logging
from selenium.webdriver.common.by import By
from config.gmail_config import GMAIL_CONFIG
# from appium.webdriver.common.actions.action_builder import ActionBuilder
# from appium.webdriver.common.actions.pointer_input import PointerInput

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

class GmailUtils:
    def __init__(self, driver):
        """
        初始化Gmail工具类
        
        Args:
            driver: Appium WebDriver实例，如果为None则使用默认driver
        """
        self.driver = driver
        self.email_address = GMAIL_CONFIG['email']
        self.password = GMAIL_CONFIG['password']
        self.imap_server = GMAIL_CONFIG['imap_server']
        self.imap_port = GMAIL_CONFIG['imap_port']
        
    def get_email_time(self, element):
        """
        获取邮件的时间信息
        
        Args:
            element: 邮件元素
            
        Returns:
            datetime对象，如果无法获取则返回None
        """
        try:
            # 查找时间元素
            time_element = element.find_element(AppiumBy.XPATH, 
                ".//XCUIElementTypeStaticText[contains(@name, ':')]")
            time_text = time_element.text
            
            # 解析时间
            current_time = datetime.now()
            if '今天' in time_text:
                # 处理"今天 HH:MM"格式
                time_parts = time_text.split(' ')[1].split(':')
                return current_time.replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=0,
                    microsecond=0
                )
            elif '昨天' in time_text:
                # 处理"昨天 HH:MM"格式
                time_parts = time_text.split(' ')[1].split(':')
                yesterday = current_time - timedelta(days=1)
                return yesterday.replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=0,
                    microsecond=0
                )
            else:
                # 处理"MM-DD HH:MM"格式
                date_parts = time_text.split(' ')[0].split('-')
                time_parts = time_text.split(' ')[1].split(':')
                return current_time.replace(
                    month=int(date_parts[0]),
                    day=int(date_parts[1]),
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=0,
                    microsecond=0
                )
        except:
            return None
            
    def get_latest_verification_code(self):
        """
        在邮件内容中查找最新的验证码
        
        Returns:
            最新的验证码字符串，如果未找到则返回None
        """
        try:
            # 获取所有验证码框
            code_boxes = self.driver.find_elements(AppiumBy.XPATH, 
                "//XCUIElementTypeStaticText[contains(@name, '验证码')]")
            
            if not code_boxes:
                logging.error("未找到验证码框")
                return None
                
            latest_code = None
            latest_time = None
            
            for code_box in code_boxes:
                try:
                    # 获取验证码框的位置
                    box_location = code_box.location
                    box_size = code_box.size
                    
                    # 在验证码框下方查找数字
                    all_elements = self.driver.find_elements(AppiumBy.XPATH, 
                        "//XCUIElementTypeStaticText | //XCUIElementTypeTextView")
                    
                    for element in all_elements:
                        try:
                            element_location = element.location
                            element_text = element.text
                            
                            # 检查元素是否在验证码框下方
                            if (element_location['y'] > box_location['y'] + box_size['height'] and
                                element_location['x'] >= box_location['x'] and
                                element_location['x'] <= box_location['x'] + box_size['width']):
                                
                                # 检查是否是6位数字
                                if re.match(r'^\d{6}$', element_text):
                                    # 获取验证码的时间信息
                                    time_element = element.find_element(AppiumBy.XPATH, 
                                        ".//preceding::XCUIElementTypeStaticText[contains(@name, ':')][1]")
                                    code_time = self.get_email_time(time_element)
                                    
                                    if code_time and (latest_time is None or code_time > latest_time):
                                        latest_time = code_time
                                        latest_code = element_text
                        except:
                            continue
                except:
                    continue
            
            return latest_code
            
        except Exception as e:
            logging.error(f"获取最新验证码失败: {str(e)}")
            return None
        
    def get_verification_code(self, wait_time: int = 10, max_retries: int = 2):
        """
        进入Gmail，直接读取页面所有文本内容，提取第一个6位数字作为验证码，获取到后立即返回。
        """
        for attempt in range(max_retries):
            try:
                logging.info(f"尝试获取验证码 (第{attempt + 1}次)")

                # 先kill掉Gmail，确保每次都从收件箱进入
                try:
                    self.driver.terminate_app("com.google.Gmail")
                    time.sleep(1)
                except Exception as e:
                    print("Gmail kill失败（可能未启动，无需担心）：", e)

                # 再启动Gmail
                try:
                    self.driver.activate_app("com.google.Gmail")
                    time.sleep(2)
                except Exception as e:
                    print("Gmail启动失败：", e)

                # 确保在收件箱页面
                try:
                    primary_tab = self.driver.find_element(AppiumBy.XPATH,
                        "//XCUIElementTypeButton[@name='主要']")
                    primary_tab.click()
                    time.sleep(1)
                except:
                    pass

                # 等待邮件列表加载
                time.sleep(2)

                # 查找noreply邮件
                noreply_email = None
                try:
                    noreply_email = self.driver.find_element(AppiumBy.XPATH,
                        "//XCUIElementTypeCell[contains(@name, 'noreply') or contains(@name, 'no-reply')]")
                except:
                    try:
                        noreply_email = self.driver.find_element(AppiumBy.XPATH,
                            "//XCUIElementTypeStaticText[contains(@name, 'noreply') or contains(@name, 'no-reply')]/..")
                    except:
                        try:
                            noreply_email = self.driver.find_element(AppiumBy.XPATH,
                                "//XCUIElementTypeStaticText[contains(@name, '验证码')]/..")
                        except:
                            pass

                if not noreply_email:
                    logging.error("未找到noreply邮件")
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    return None

                # 点击noreply邮件
                try:
                    self.tap_element(noreply_email)
                except:
                    location = noreply_email.location
                    size = noreply_email.size
                    x = location['x'] + size['width'] / 2
                    y = location['y'] + size['height'] / 2
                    self.driver.tap([(x, y)])

                time.sleep(2)
                # 进入邮件后再多等2秒，确保内容加载
                time.sleep(2)

                # 获取所有文本元素
                all_elements = self.driver.find_elements(AppiumBy.XPATH,
                    "//XCUIElementTypeStaticText | //XCUIElementTypeTextView")

                all_texts = []
                for element in all_elements:
                    try:
                        text = element.text
                        all_texts.append(text)
                    except:
                        continue
                print("页面所有文本内容：", all_texts)

                # 直接提取第一个6位数字
                code = None
                for text in all_texts:
                    match = re.search(r'\b\d{6}\b', text)
                    if match:
                        code = match.group(0)
                        break

                if code:
                    try:
                        back_button = self.driver.find_element(AppiumBy.XPATH, 
                            "//XCUIElementTypeButton[@name='返回']")
                        back_button.click()
                        time.sleep(1)
                    except Exception as e:
                        print("返回按钮点击失败：", e)
                    print(f"成功获取验证码: {code}")
                    return code
                else:
                    print("未找到6位数字，自动截图以便排查")
                    self.driver.save_screenshot("no_code_found.png")
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    return None
            except Exception as e:
                logging.error(f"获取验证码失败: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                return None

    def tap_element(self, element, hold_time=0.15):
        rect = element.rect
        x = rect['x'] + rect['width'] // 2
        y = rect['y'] + rect['height'] // 2
        actions = ActionBuilder(self.driver)
        actions.w3c_actions.pointer_action.move_to_location(x, y)
        actions.w3c_actions.pointer_action.pointer_down()
        actions.w3c_actions.pointer_action.pause(hold_time)
        actions.w3c_actions.pointer_action.release()
        actions.perform() 

# 兼容旧用法，导出顶层函数
def get_verification_code(driver, wait_time: int = 10, max_retries: int = 2):
    """
    兼容顶层导入用法，直接调用GmailUtils实例方法
    """
    return GmailUtils(driver).get_verification_code(wait_time, max_retries) 