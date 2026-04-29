#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android 扫码配网测试脚本
支持多设备/多路由器扫码配网测试
"""

import json
import time
import sys
import os
import subprocess
import logging
import re
import signal
import atexit
import errno
from datetime import datetime
from pathlib import Path

# 可靠获取脚本所在目录，__file__ 不可用时回退到 argv 或当前目录
def get_script_dir() -> Path:
    try:
        return Path(__file__).resolve().parent
    except NameError:
        pass
    if sys.argv and sys.argv[0]:
        try:
            return Path(sys.argv[0]).resolve().parent
        except Exception:
            pass
    return Path.cwd()

SCRIPT_DIR = get_script_dir()
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# 尝试导入report_utils，如果不存在则使用默认路径
try:
    from report_utils import init_run_env
except ImportError:
    # 如果report_utils不在当前路径，尝试从common目录导入
    common_path = str(SCRIPT_DIR.parent / "common")
    sys.path.insert(0, common_path)
    try:
        from report_utils import init_run_env
    except ImportError:
        # 如果还是找不到，尝试从蓝牙配网目录导入（向后兼容）
        sys.path.insert(0, str(SCRIPT_DIR.parent / "2蓝牙配网"))
        try:
            from report_utils import init_run_env
        except ImportError:
            # 如果还是找不到，使用默认方式
            init_run_env = None

# ==================== 配置和日志设置 ====================

# 初始化本次运行的输出目录
if init_run_env:
    RUN_DIR, LOG_FILE, SCREENSHOT_DIR = init_run_env(prefix="1扫码配网-Android")
    screenshot_dir = str(SCREENSHOT_DIR)
else:
    # 回退到默认方式
    RUN_DIR = None
    LOG_FILE = 'android_qrcode_pairing.log'
    screenshot_dir = "screenshots"

# 配置日志
if RUN_DIR:
    log_file_path = str(LOG_FILE)
else:
    log_file_path = LOG_FILE

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file_path, encoding='utf-8')
    ]
)

# 创建截图目录
if not os.path.exists(screenshot_dir):
    os.makedirs(screenshot_dir)
logger = logging.getLogger(__name__)

# 全局步骤等待时间（秒）
STEP_DELAY_SECONDS = 2

# 机器人热点触发所需的设备ID，可通过环境变量覆盖
ROBOT_DEVICE_ID = os.environ.get('ROBOT_DEVICE_ID', 'galaxy_p0001')

# 全局测试数据（用于信号处理和退出时保存）
_global_test_data = {
    'total_tests': 0,
    'success_count': 0,
    'failure_count': 0,
    'detailed_results': {},
    'test_config': None,
    'interrupted': False
}

# 测试数据临时文件路径
TEST_DATA_TEMP_FILE = 'test_data_temp.json'

def force_print(message):
    """强制输出到控制台和日志"""
    print(message, flush=True)
    logger.info(message)

def take_screenshot(driver, device_name, wifi_name, step_name="failure"):
    """截图功能"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}-{device_name}-{wifi_name}-{step_name}.png"
        filepath = os.path.join(screenshot_dir, filename)
        driver.save_screenshot(filepath)
        force_print(f"📸 截图已保存: {filepath}")
        return filepath
    except Exception as e:
        force_print(f"❌ 截图失败: {e}")
        return None

def wait_after_step(step_name, seconds=STEP_DELAY_SECONDS):
    """步骤完成后等待一段时间，确保页面稳定"""
    try:
        force_print(f"⏳ {step_name}完成，等待 {seconds} 秒以确保页面稳定...")
        time.sleep(seconds)
    except Exception as e:
        force_print(f"⚠️ 等待步骤 '{step_name}' 出错: {e}")

def save_test_data_to_file():
    """将测试数据保存到临时文件"""
    try:
        data = {
            'total_tests': _global_test_data['total_tests'],
            'success_count': _global_test_data['success_count'],
            'failure_count': _global_test_data['failure_count'],
            'detailed_results': _global_test_data['detailed_results'],
            'test_config': _global_test_data['test_config'],
            'interrupted': _global_test_data['interrupted'],
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(TEST_DATA_TEMP_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        force_print(f"⚠️ 保存测试数据到临时文件失败: {e}")

def load_test_data_from_file():
    """从临时文件加载测试数据"""
    try:
        if os.path.exists(TEST_DATA_TEMP_FILE):
            with open(TEST_DATA_TEMP_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
    except Exception as e:
        force_print(f"⚠️ 从临时文件加载测试数据失败: {e}")
    return None

def cleanup_temp_file():
    """清理临时文件"""
    try:
        if os.path.exists(TEST_DATA_TEMP_FILE):
            os.remove(TEST_DATA_TEMP_FILE)
            force_print(f"✅ 已清理临时文件: {TEST_DATA_TEMP_FILE}")
    except Exception as e:
        force_print(f"⚠️ 清理临时文件失败: {e}")

def emergency_save_and_exit(signum=None, frame=None):
    """紧急保存测试数据并退出"""
    if hasattr(emergency_save_and_exit, '_executing'):
        return
    emergency_save_and_exit._executing = True
    
    force_print("\n⚠️ 收到终止信号，正在紧急保存测试数据...")
    try:
        save_test_data_to_file()
        if _global_test_data['test_config']:
            try:
                finalize_results(
                    _global_test_data['total_tests'],
                    _global_test_data['success_count'],
                    _global_test_data['failure_count'],
                    _global_test_data['detailed_results'],
                    _global_test_data['test_config'],
                    interrupted=True
                )
            except NameError:
                force_print("⚠️ finalize_results 函数未定义，仅保存数据")
        force_print("✅ 测试数据已保存")
    except Exception as e:
        force_print(f"❌ 紧急保存失败: {e}")
    
    if signum is not None:
        sys.exit(0)

# ==================== 设备配置加载 ====================

def load_device_config():
    """加载设备配置文件（只加载 Android 设备）"""
    import os
    
    def filter_android_devices(config):
        """过滤出 Android 设备"""
        if not config:
            return config
        filtered_config = config.copy()
        filtered_config['device_configs'] = {
            k: v for k, v in config.get('device_configs', {}).items()
            if v.get('platform', 'android') == 'android'
        }
        return filtered_config
    
    # 优先从环境变量读取（用于 Web 管理页面传递的临时配置）
    env_config_file = os.environ.get('DEVICE_CONFIG_FILE')
    if env_config_file and os.path.exists(env_config_file):
        try:
            with open(env_config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                force_print(f"✅ 从环境变量配置文件加载: {env_config_file}")
                return filter_android_devices(config)
        except Exception as e:
            force_print(f"⚠️ 加载环境变量配置文件失败: {e}，尝试其他方式")
    
    # 优先尝试从 common 目录读取统一配置文件
    common_config_path = str((SCRIPT_DIR.parent / 'common' / 'device_config.json').resolve())
    
    if os.path.exists(common_config_path):
        try:
            with open(common_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                force_print(f"✅ 从 common 目录加载配置文件: {common_config_path}")
                # 过滤出 Android 设备
                return filter_android_devices(config)
        except Exception as e:
            force_print(f"⚠️ 加载 common 配置文件失败: {e}，尝试其他方式")
    
    # 尝试从上一级目录的统一配置文件读取（向后兼容）
    unified_config_path = str((SCRIPT_DIR.parent / 'device_config.json').resolve())
    
    if os.path.exists(unified_config_path):
        try:
            with open(unified_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 过滤出 Android 设备
                return filter_android_devices(config)
        except Exception as e:
            force_print(f"⚠️ 加载统一配置文件失败: {e}，尝试从当前目录读取")
    
    # 如果统一配置文件不存在，从当前目录读取（向后兼容）
    try:
        with open('device_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            return filter_android_devices(config)
    except Exception as e:
        force_print(f"❌ 加载配置文件失败: {e}")
        return None

# ==================== 工具函数 ====================

def get_adb_path():
    """获取 ADB 完整路径"""
    android_home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    
    if not android_home:
        possible_paths = [
            os.path.expanduser('~/Library/Android/sdk'),
            os.path.expanduser('~/Android/Sdk'),
            '/usr/local/share/android-sdk',
            '/opt/android-sdk',
        ]
        
        for path in possible_paths:
            adb_candidate = os.path.join(path, 'platform-tools', 'adb')
            if os.path.exists(adb_candidate):
                android_home = path
                break
    
    if android_home:
        adb_path = os.path.join(android_home, 'platform-tools', 'adb')
        if os.path.exists(adb_path):
            return adb_path
    
    return 'adb'

# ==================== 蓝牙控制 ====================

def disable_bluetooth(device_name):
    """关闭指定设备的蓝牙"""
    force_print(f"📴 关闭设备 {device_name} 的蓝牙...")
    try:
        adb_path = get_adb_path()
        
        # 方法1: 使用 settings 命令（适用于 Android 6.0+）
        result = subprocess.run(
            [adb_path, '-s', device_name, 'shell', 'settings', 'put', 'global', 'bluetooth_on', '0'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            force_print(f"✅ 蓝牙已关闭（设备: {device_name}）")
            time.sleep(2)  # 等待蓝牙完全关闭
            return True
        else:
            # 方法2: 使用 service call（备用方法）
            force_print("⚠️ settings 方法失败，尝试使用 service call...")
            result2 = subprocess.run(
                [adb_path, '-s', device_name, 'shell', 'service', 'call', 'bluetooth_manager', '8'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result2.returncode == 0:
                force_print(f"✅ 蓝牙已关闭（设备: {device_name}，使用 service call）")
                time.sleep(2)
                return True
            else:
                force_print(f"⚠️ 关闭蓝牙失败: {result2.stderr.strip()}")
                return False
                
    except Exception as e:
        force_print(f"⚠️ 关闭蓝牙异常: {e}")
        return False

def enable_bluetooth(device_name):
    """打开指定设备的蓝牙"""
    force_print(f"📱 打开设备 {device_name} 的蓝牙...")
    try:
        adb_path = get_adb_path()
        
        # 方法1: 使用 settings 命令（适用于 Android 6.0+）
        result = subprocess.run(
            [adb_path, '-s', device_name, 'shell', 'settings', 'put', 'global', 'bluetooth_on', '1'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            force_print(f"✅ 蓝牙已打开（设备: {device_name}）")
            time.sleep(2)  # 等待蓝牙完全启动
            return True
        else:
            # 方法2: 使用 service call（备用方法）
            force_print("⚠️ settings 方法失败，尝试使用 service call...")
            result2 = subprocess.run(
                [adb_path, '-s', device_name, 'shell', 'service', 'call', 'bluetooth_manager', '6'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result2.returncode == 0:
                force_print(f"✅ 蓝牙已打开（设备: {device_name}，使用 service call）")
                time.sleep(2)
                return True
            else:
                force_print(f"⚠️ 打开蓝牙失败: {result2.stderr.strip()}")
                return False
                
    except Exception as e:
        force_print(f"⚠️ 打开蓝牙异常: {e}")
        return False

# ==================== 热点触发（共用脚本优先） ====================

def trigger_robot_hotspot():
    """触发机器热点（仅调用 common/hotspot_trigger.py，设备 ID 统一在该脚本中配置）"""
    force_print("📡 步骤1: 触发机器热点...")

    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../配网兼容性
        common_dir = os.path.join(base_dir, "common")
        if common_dir not in sys.path:
            sys.path.insert(0, common_dir)

        import hotspot_trigger  # type: ignore

        # 扫码配网按原流程：先 sleep 10 秒再发 ROS2
        force_print("🔌 使用 common/hotspot_trigger.py 触发热点（sleep_before=10）...")
        ok = hotspot_trigger.trigger_hotspot(sleep_before=10, log=force_print)
        if ok:
            force_print("✅ common/hotspot_trigger.py 触发热点成功")
            return True
        force_print("❌ common/hotspot_trigger.py 返回失败")
        return False

    except Exception as e:
        force_print(f"❌ 调用 common/hotspot_trigger.py 触发热点失败: {e}")
        return False

# ==================== 设备检测和删除 ====================

def _is_driver_crashed_error(err):
    """检测是否是 UiAutomator2 崩溃错误"""
    if not err:
        return False
    err_str = str(err).lower()
    return ('instrumentation process is not running' in err_str or 
            'cannot be proxied' in err_str or
            'crashed' in err_str)

def _is_session_terminated_error(err):
    """检测是否是会话终止错误或连接错误"""
    if not err:
        return False
    err_str = str(err).lower()
    err_type = type(err).__name__
    
    # 检测会话终止错误
    session_errors = (
        'session is either terminated or not started' in err_str or
        'nosuchdrivererror' in err_str or
        'invalid session id' in err_str or
        'session does not exist' in err_str or
        'invalidsessionidexception' in err_str
    )
    
    # 检测连接错误（Connection refused, Connection reset, Max retries exceeded等）
    connection_errors = (
        'connection refused' in err_str or
        'connection reset' in err_str or
        'max retries exceeded' in err_str or
        'failed to establish a new connection' in err_str or
        'newconnectionerror' in err_type.lower() or
        'httperror' in err_type.lower() or
        'urllib3' in err_type.lower()
    )
    
    # 检查错误代码（如果有的话）
    err_errno = getattr(err, 'errno', None)
    if err_errno:
        connection_errors = connection_errors or (
            err_errno == errno.ECONNREFUSED or
            err_errno == errno.ECONNRESET
        )
    
    # 检查嵌套的异常（urllib3 错误通常包装在 HTTPError 中）
    if hasattr(err, 'reason') and err.reason:
        reason_str = str(err.reason).lower()
        if 'connection refused' in reason_str or 'connection reset' in reason_str:
            connection_errors = True
    
    return session_errors or connection_errors

def check_session_validity(driver):
    """检查 Appium 会话是否有效"""
    if driver is None:
        return False
    
    try:
        # 尝试获取当前活动（一个轻量级的操作来验证会话）
        driver.current_activity
        return True
    except Exception as e:
        if _is_session_terminated_error(e):
            force_print(f"⚠️ 检测到会话已失效或连接失败: {type(e).__name__}: {str(e)[:100]}")
            return False
        # 其他错误可能是正常的，返回 True
        return True

def ensure_valid_session(driver, device_config=None):
    """确保 driver 会话有效，如果失效则重建
    
    Args:
        driver: Appium driver
        device_config: 设备配置，用于会话失效时重建driver
    
    Returns:
        (driver: WebDriver or None, is_new: bool)
        如果重建失败返回 None，否则返回 driver（可能是新的或原来的）
    """
    if driver is None:
        if device_config:
            force_print("⚠️ Driver 为 None，创建新 driver...")
            new_driver = create_device_driver(device_config)
            if new_driver:
                force_print("✅ Driver 创建成功")
                return new_driver, True
        return None, False
    
    if not check_session_validity(driver):
        force_print("⚠️ 会话已失效，需要重建driver")
        if device_config:
            try:
                driver.quit()
            except:
                pass
            time.sleep(2)
            new_driver = create_device_driver(device_config)
            if new_driver:
                force_print("✅ Driver重建成功")
                return new_driver, True
            else:
                force_print("❌ Driver重建失败")
                return None, False
        else:
            force_print("❌ 会话失效且无法重建（缺少device_config）")
            return None, False
    
    return driver, False

def check_is_on_home_page(driver, device_config=None):
    """检查是否在应用首页"""
    try:
        # 首先检查会话是否有效
        if not check_session_validity(driver):
            force_print("⚠️ 检查首页时会话已失效")
            return False
        
        # 等待页面加载
        time.sleep(2)
        
        # 优先检测 add 按钮，这是首页最可靠的标识
        home_indicators = [
            '//android.widget.ImageView[@content-desc="add"]',  # 优先：add 按钮
            '(//android.widget.ImageView[@content-desc="add"])[2]',  # 第二个 add 按钮
            '//android.widget.TextView[contains(@text,"设备")]',
            '//android.widget.TextView[contains(@text,"Sora")]',
            '//android.widget.TextView[contains(@text,"robot")]',
            '//android.widget.ImageView[@content-desc="robot"]'
        ]
        
        for indicator in home_indicators:
            try:
                element = driver.find_element(AppiumBy.XPATH, indicator)
                if element.is_displayed():
                    force_print(f"✅ 确认在应用首页: {indicator}")
                    return True
            except Exception as e:
                # 如果检测到会话失效，立即返回 False
                if _is_session_terminated_error(e):
                    force_print(f"⚠️ 检查首页元素时会话失效: {e}")
                    return False
                continue
        return False
    except Exception as e:
        if _is_session_terminated_error(e):
            force_print(f"⚠️ 检查首页状态时会话失效: {e}")
        else:
            force_print(f"⚠️ 检查首页状态失败: {e}")
        return False

def check_add_device_button(driver, device_config=None):
    """检测首页是否有add device按钮，返回找到的选择器（如果找到）
    
    Args:
        driver: Appium driver
        device_config: 设备配置，用于会话失效时重建driver
    
    Returns:
        (found: bool, new_driver: WebDriver or None)
    """
    try:
        # 首先确保会话有效
        driver, is_new = ensure_valid_session(driver, device_config)
        if driver is None:
            return False, None
        if is_new:
            # 如果重建了 driver，需要重新等待页面加载
            time.sleep(3)
        
        # 等待页面加载
        time.sleep(2)
        
        force_print("🔍 开始检测add device按钮...")
        
        # 尝试多种选择器查找add device按钮
        selectors = [
            "(//android.widget.ImageView[@content-desc='add'])[2]",
            "//android.widget.ImageView[@content-desc='add']",
            "//android.widget.Button[contains(@text,'Add')]",
            "//android.widget.Button[contains(@text,'添加')]",
            "//android.widget.ImageView[contains(@content-desc,'add')]"
        ]
        
        for i, selector in enumerate(selectors, 1):
            try:
                # 在每次尝试前确保会话有效
                driver, is_new = ensure_valid_session(driver, device_config)
                if driver is None:
                    return False, None
                if is_new:
                    time.sleep(2)  # 重建后等待页面加载
                
                force_print(f"🔍 尝试选择器 {i}: {selector}")
                element = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, selector))
                )
                if element and element.is_displayed():
                    # 额外检查：确保元素真的可见且可点击
                    try:
                        location = element.location
                        size = element.size
                        force_print(f"🔍 元素位置: {location}, 大小: {size}")
                        
                        # 检查元素是否真的在屏幕可见区域
                        if location['x'] >= 0 and location['y'] >= 0 and size['width'] > 0 and size['height'] > 0:
                            force_print(f"✅ 找到真正可见的add device按钮（选择器 {i}）")
                            # 保存找到的选择器到driver的session中，供后续使用
                            if not hasattr(driver, '_add_button_selector'):
                                driver._add_button_selector = selector
                            return True, None
                        else:
                            force_print(f"⚠️ 元素位置异常: {location}, {size}")
                    except Exception as e:
                        force_print(f"⚠️ 检查元素位置失败: {e}")
                        # 如果元素存在但无法获取位置，也认为找到了
                        force_print(f"✅ 找到add device按钮（选择器 {i}）")
                        if not hasattr(driver, '_add_button_selector'):
                            driver._add_button_selector = selector
                        return True, None
                else:
                    force_print(f"⚠️ 找到元素但不可见: {selector}")
            except Exception as e:
                # 检查是否是会话失效错误
                if _is_session_terminated_error(e) and device_config:
                    force_print(f"⚠️ 选择器 {i} 时会话失效，重建driver...")
                    try:
                        driver.quit()
                    except:
                        pass
                    time.sleep(2)
                    new_driver = create_device_driver(device_config)
                    if new_driver:
                        driver = new_driver
                        force_print("✅ Driver重建成功，继续检测add按钮")
                        # 继续尝试下一个选择器
                        continue
                    else:
                        force_print("❌ Driver重建失败")
                        return False, None
                else:
                    force_print(f"⚠️ 选择器 {i} 失败: {str(e)[:50]}...")
                    continue
        
        force_print("❌ 未找到add device按钮")
        return False, driver
        
    except Exception as e:
        if _is_session_terminated_error(e) and device_config:
            force_print("⚠️ 检测add device按钮时会话失效，重建driver...")
            try:
                driver.quit()
            except:
                pass
            time.sleep(2)
            new_driver = create_device_driver(device_config)
            if new_driver:
                force_print("✅ Driver重建成功")
                return False, new_driver
            else:
                force_print("❌ Driver重建失败")
                return False, None
        else:
            force_print(f"❌ 检测add device按钮失败: {e}")
            return False, driver

def delete_paired_device(driver):
    """删除已配对的设备"""
    force_print("🔧 开始删除已配对设备...")
    try:
        # 先检查是否有 more 按钮
        more_selectors = [
            '//android.widget.ImageView[@content-desc="more"]',
            '//android.widget.Button[@content-desc="more"]',
            '//android.view.View[@content-desc="more"]'
        ]
        
        more_button = None
        for selector in more_selectors:
            try:
                more_button = driver.find_element(AppiumBy.XPATH, selector)
                if more_button.is_displayed():
                    force_print(f"✅ 找到more按钮: {selector}")
                    break
            except:
                continue
        
        if not more_button:
            force_print("⚠️ 未找到more按钮，可能没有已配对设备")
            return False
        
        # 点击more按钮
        force_print("🔍 点击more按钮")
        more_button.click()
        time.sleep(2)
        force_print("✅ 点击more按钮成功")
        
        # 点击Remove按钮
        remove_selectors = [
            '//android.widget.TextView[@text="Remove"]',
            '//android.widget.Button[@text="Remove"]',
            '//android.widget.TextView[contains(@text,"Remove")]'
        ]
        
        remove_button = None
        for selector in remove_selectors:
            try:
                remove_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if remove_button.is_displayed():
                    force_print(f"✅ 找到Remove按钮: {selector}")
                    break
            except:
                continue
        
        if not remove_button:
            force_print("⚠️ 未找到Remove按钮")
            return False
        
        force_print("🔍 点击Remove按钮")
        remove_button.click()
        time.sleep(2)
        force_print("✅ 点击Remove按钮成功")
        
        # 点击Confirm按钮
        confirm_selectors = [
            '//android.widget.TextView[@text="Confirm"]',
            '//android.widget.Button[@text="Confirm"]',
            '//android.widget.TextView[contains(@text,"Confirm")]',
            '//android.widget.Button[contains(@text,"确认")]'
        ]
        
        confirm_button = None
        for selector in confirm_selectors:
            try:
                confirm_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if confirm_button.is_displayed():
                    force_print(f"✅ 找到Confirm按钮: {selector}")
                    break
            except:
                continue
        
        if not confirm_button:
            force_print("⚠️ 未找到Confirm按钮")
            return False
        
        force_print("🔍 点击Confirm按钮")
        confirm_button.click()
        time.sleep(3)
        force_print("✅ 点击Confirm按钮成功")
        
        # 刷新页面，确保按钮状态更新
        force_print("🔄 刷新首页状态...")
        try:
            # 重新激活应用
            app_package = driver.capabilities.get('appPackage')
            if app_package:
                driver.activate_app(app_package)
            time.sleep(2)
        except:
            pass
        
        return True
    except Exception as e:
        force_print(f"❌ 删除设备失败: {e}")
        return False

def ensure_add_device_button(driver, device_config=None):
    """确保首页有add device按钮，如果没有则删除设备
    
    Args:
        driver: Appium driver
        device_config: 设备配置，用于会话失效时重建driver
    
    Returns:
        (success: bool, new_driver: WebDriver or None)
    """
    max_attempts = 3
    force_print("🔍 确保首页存在 add device 按钮")
    
    # 首先确保会话有效
    driver, is_new = ensure_valid_session(driver, device_config)
    if driver is None:
        return False, None
    if is_new:
        time.sleep(3)  # 重建后等待页面加载
    
    # 首先检查是否在首页，如果不在则切换到首页
    try:
        if not check_is_on_home_page(driver):
            force_print("⚠️ 当前不在应用首页，切换到首页...")
            try:
                # 尝试按返回键返回首页
                for _ in range(3):
                    try:
                        driver.press_keycode(4)  # 返回键
                        time.sleep(1)
                    except Exception as e:
                        if _is_session_terminated_error(e) and device_config:
                            force_print("⚠️ 会话失效，重建driver...")
                            try:
                                driver.quit()
                            except:
                                pass
                            time.sleep(2)
                            new_driver = create_device_driver(device_config)
                            if new_driver:
                                driver = new_driver
                                force_print("✅ Driver重建成功，继续操作")
                            else:
                                return False, driver, None
                        else:
                            raise
                
                # 等待页面加载
                time.sleep(2)
                
                # 再次检查是否在首页
                if check_is_on_home_page(driver):
                    force_print("✅ 已切换到应用首页")
                else:
                    force_print("⚠️ 按返回键后仍未在首页，尝试重置应用...")
                    try:
                        reset_app_to_home(driver)
                    except Exception as e:
                        if _is_session_terminated_error(e) and device_config:
                            force_print("⚠️ 重置应用时会话失效，重建driver...")
                            try:
                                driver.quit()
                            except:
                                pass
                            time.sleep(2)
                            new_driver = create_device_driver(device_config)
                            if new_driver:
                                driver = new_driver
                                force_print("✅ Driver重建成功")
                            else:
                                return False, driver, None
                        else:
                            raise
            except Exception as e:
                if _is_session_terminated_error(e) and device_config:
                    force_print("⚠️ 切换首页时会话失效，重建driver...")
                    try:
                        driver.quit()
                    except:
                        pass
                    time.sleep(2)
                    new_driver = create_device_driver(device_config)
                    if new_driver:
                        driver = new_driver
                        force_print("✅ Driver重建成功")
                    else:
                        return False, driver, None
                else:
                    force_print(f"⚠️ 切换首页失败: {e}，尝试重置应用...")
                    try:
                        reset_app_to_home(driver)
                    except Exception as reset_err:
                        if _is_session_terminated_error(reset_err) and device_config:
                            force_print("⚠️ 重置应用时会话失效，重建driver...")
                            try:
                                driver.quit()
                            except:
                                pass
                            time.sleep(2)
                            new_driver = create_device_driver(device_config)
                            if new_driver:
                                driver = new_driver
                                force_print("✅ Driver重建成功")
                            else:
                                return False, driver, None
                        else:
                            raise
    except Exception as e:
        if _is_session_terminated_error(e) and device_config:
            force_print("⚠️ 检查首页状态时会话失效，重建driver...")
            try:
                driver.quit()
            except:
                pass
            time.sleep(2)
            new_driver = create_device_driver(device_config)
            if new_driver:
                driver = new_driver
                force_print("✅ Driver重建成功")
            else:
                return False, None
        else:
            force_print(f"⚠️ 检查首页状态失败: {e}")
    
    # 首先检查页面是否有已配对的设备
    has_paired_device = False
    try:
        device_indicators = [
            "//android.widget.TextView[contains(@text,'Sora')]",
            "//android.widget.TextView[contains(@text,'robot')]",
            "//android.widget.TextView[contains(@text,'设备')]",
            "//android.widget.TextView[contains(@text,'standby')]"
        ]
        
        for indicator in device_indicators:
            try:
                elements = driver.find_elements(AppiumBy.XPATH, indicator)
                if elements:
                    force_print(f"🔍 检测到已配对设备指示器: {indicator}")
                    has_paired_device = True
                    break
            except:
                continue
        
        # 检查是否有 more 按钮（更可靠的标识）
        try:
            more_button = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="more"]')
            if more_button.is_displayed():
                force_print("🔍 检测到more按钮，存在已配对设备")
                has_paired_device = True
        except:
            pass
        
        if has_paired_device:
            force_print("🔍 检测到已配对设备，需要先删除")
        else:
            force_print("🔍 未检测到已配对设备")
    except Exception as e:
        force_print(f"⚠️ 检查已配对设备失败: {e}")
    
    for attempt in range(1, max_attempts + 1):
        force_print(f"🔁 第 {attempt}/{max_attempts} 次检查")
        
        # 再次确认是否在首页
        if not check_is_on_home_page(driver):
            force_print("⚠️ 不在首页，切换到首页...")
            try:
                for _ in range(3):
                    driver.press_keycode(4)  # 返回键
                    time.sleep(1)
                time.sleep(2)
            except:
                pass
        
        # 如果检测到有已配对设备，直接执行删除操作（参考蓝牙配网）
        if has_paired_device:
            force_print("🔧 检测到已配对设备，直接执行删除操作")
            force_print("🔍 检查是否有more按钮...")
            try:
                more_button = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="more"]')
                if more_button.is_displayed():
                    force_print("✅ 找到more按钮，开始删除设备...")
                    if delete_paired_device(driver):
                        force_print("✅ 设备删除完成，等待页面刷新...")
                        time.sleep(5)
                        # 重新检查是否有已配对设备
                        has_paired_device = False
                        try:
                            more_button = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="more"]')
                            if more_button.is_displayed():
                                has_paired_device = True
                        except:
                            pass
                    else:
                        force_print("❌ 删除设备失败")
                        if attempt < max_attempts:
                            continue
                        return False, driver
                else:
                    force_print("⚠️ more按钮不可见，可能设备已删除")
                    has_paired_device = False
            except Exception as e:
                force_print(f"⚠️ 检查more按钮失败: {e}")
                # 如果找不到more按钮，可能设备已删除，继续检查add按钮
                has_paired_device = False
        
        # 检查是否有add device按钮
        try:
            found, new_driver = check_add_device_button(driver, device_config=device_config)
            if found:
                force_print("✅ add device按钮已就绪")
                if new_driver is not None:
                    driver = new_driver
                return True, driver
        except Exception as e:
            if _is_session_terminated_error(e) and device_config:
                force_print("⚠️ 检查add按钮时会话失效，重建driver...")
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(2)
                new_driver = create_device_driver(device_config)
                if new_driver:
                    driver = new_driver
                    force_print("✅ Driver重建成功，重试检查add按钮")
                    # 重试一次
                    try:
                        found, retry_driver = check_add_device_button(driver, device_config=device_config)
                        if found:
                            force_print("✅ add device按钮已就绪")
                            if retry_driver is not None:
                                driver = retry_driver
                            return True, driver
                    except Exception as retry_err:
                        force_print(f"⚠️ 重试检查add按钮失败: {retry_err}")
                        return False, driver
                else:
                    return False, None
            else:
                raise
        
        # 如果未找到 add 按钮，且未检测到已配对设备，尝试检查more按钮并删除
        if not has_paired_device:
            force_print("⚠️ 未找到 add device 按钮，检查是否有more按钮...")
            try:
                more_button = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="more"]')
                if more_button.is_displayed():
                    force_print("✅ 找到more按钮，开始删除设备...")
                    if delete_paired_device(driver):
                        force_print("✅ 设备删除完成，等待页面刷新...")
                        time.sleep(5)
                    else:
                        force_print("❌ 删除设备失败")
                        if attempt < max_attempts:
                            continue
                        return False, driver
                else:
                    force_print("⚠️ 未找到more按钮，可能没有可删除的设备")
            except Exception as e:
                force_print(f"⚠️ 检查more按钮失败: {e}")
                # 如果找不到more按钮，可能是页面不在首页，尝试返回首页
                if attempt < max_attempts:
                    force_print("⚠️ 尝试返回首页后重试...")
                    try:
                        for _ in range(3):
                            driver.press_keycode(4)  # 返回键
                            time.sleep(1)
                        time.sleep(2)
                    except:
                        pass
        
        wait_after_step("删除已配对设备", seconds=2)
    
    force_print("❌ 多次尝试后仍无法找到 add device 按钮")
    return False, driver

# ==================== 扫码配网流程 ====================

def click_add_device_button(driver):
    """点击添加设备按钮"""
    force_print("📱 步骤2: 点击添加设备按钮...")
    try:
        # 等待页面稳定
        time.sleep(2)
        
        # 优先使用之前找到的选择器（如果存在）
        selectors = []
        if hasattr(driver, '_add_button_selector') and driver._add_button_selector:
            selectors.append(driver._add_button_selector)
            force_print(f"🔍 优先使用之前找到的选择器: {driver._add_button_selector}")
        
        # 添加其他备选选择器
        all_selectors = [
            "(//android.widget.ImageView[@content-desc='add'])[2]",
            "//android.widget.ImageView[@content-desc='add']",
            "//android.widget.Button[contains(@text,'Add')]",
            "//android.widget.Button[contains(@text,'添加')]",
            "//android.widget.ImageView[contains(@content-desc,'add')]"
        ]
        
        # 去重并保持顺序
        for sel in all_selectors:
            if sel not in selectors:
                selectors.append(sel)
        
        add_button = None
        used_selector = None
        
        for i, selector in enumerate(selectors, 1):
            try:
                force_print(f"🔍 尝试选择器 {i}: {selector}")
                add_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if add_button and add_button.is_displayed():
                    # 验证元素位置
                    try:
                        location = add_button.location
                        size = add_button.size
                        if location['x'] >= 0 and location['y'] >= 0 and size['width'] > 0 and size['height'] > 0:
                            used_selector = selector
                            force_print(f"✅ 找到可点击的add device按钮（选择器 {i}）")
                            break
                    except:
                        # 如果无法获取位置，也认为找到了
                        used_selector = selector
                        force_print(f"✅ 找到add device按钮（选择器 {i}）")
                        break
            except Exception as e:
                force_print(f"⚠️ 选择器 {i} 失败: {str(e)[:50]}...")
                continue
        
        if not add_button or not used_selector:
            force_print("❌ 未找到可点击的add device按钮")
            # 尝试截图以便调试
            try:
                take_screenshot(driver, "unknown", "unknown", "add_button_not_found")
            except:
                pass
            return False
        
        # 点击按钮
        try:
            add_button.click()
            force_print(f"✅ 点击添加设备按钮成功（使用选择器: {used_selector}）")
            time.sleep(3)
            return True
        except Exception as click_err:
            force_print(f"⚠️ 标准点击失败，尝试强制点击: {click_err}")
            try:
                # 尝试使用JavaScript点击
                driver.execute_script("arguments[0].click();", add_button)
                force_print("✅ 强制点击添加设备按钮成功")
                time.sleep(3)
                return True
            except Exception as force_err:
                force_print(f"❌ 强制点击也失败: {force_err}")
                # 尝试截图以便调试
                try:
                    take_screenshot(driver, "unknown", "unknown", "add_button_click_failed")
                except:
                    pass
                return False
        
    except Exception as e:
        force_print(f"❌ 点击添加设备按钮失败: {e}")
        # 尝试截图以便调试
        try:
            take_screenshot(driver, "unknown", "unknown", "add_button_error")
        except:
            pass
        return False

def scan_qrcode(driver):
    """使用摄像头扫描二维码（参考蓝牙配网的检测逻辑）"""
    force_print("📷 步骤3: 使用摄像头扫描二维码...")
    try:
        # 等待扫码页面出现
        time.sleep(3)
        
        # 获取 app_package 用于验证（参考蓝牙配网）
        app_package = driver.capabilities.get('appPackage')
        
        # WiFi 设置页面指示器（参考 iOS 脚本，使用多个指示器确保及时检测）
        wifi_setup_indicators = [
            '//android.widget.TextView[@text="Set Up Wi-Fi"]',  # 最精确
            '//android.view.View[@content-desc="switch"]',  # WiFi 切换按钮
            '//android.view.View[@content-desc="password"]',  # 密码输入框
            '//android.widget.EditText[@hint="Password"]',  # 密码输入框（备用）
            '//android.widget.EditText[@hint*="密码"]',  # 中文密码输入框
            '//android.widget.Button[contains(@text,"Next")]',  # Next 按钮
            '//android.widget.TextView[contains(@text,"Wi-Fi")]',  # 包含 Wi-Fi 的文本
            '//android.widget.TextView[contains(@text,"WiFi")]',  # 包含 WiFi 的文本
            '//android.widget.TextView[@text="Agree"]',  # Agree 按钮出现也说明已跳转到 WiFi 设置页面
        ]
        
        # 立即检查是否已经跳转到WIFI设置页面（参考 iOS 脚本：直接检查多个指示器）
        force_print("🔍 检查是否已经跳转到WiFi设置页面...")
        for indicator in wifi_setup_indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, indicator)
                if elem.is_displayed():
                    # 如果提供了 app_package，校验当前包名
                    if app_package:
                        try:
                            current_pkg = driver.current_package
                            if current_pkg and current_pkg != app_package:
                                continue  # 包名不匹配，跳过
                        except Exception:
                            pass
                    force_print(f"✅ 扫码成功，已跳转到WIFI设置页面: {indicator}")
                    # 如果检测到 Agree 按钮，立即处理（参考 iOS 脚本）
                    if "Agree" in indicator:
                        if handle_agree_popup(driver, timeout=4):
                            force_print("✅ 已处理 Agree 按钮，继续后续流程")
                        else:
                            force_print("ℹ️ 未检测到 Agree 按钮，可能已跳过或不存在")
                    return True
            except Exception:
                continue
        
        # 如果设备出现，扫描框会被覆盖，无法扫描二维码
        # 点击"Add Device"位置，确保扫描框可见（尝试点击3次）
        force_print("🔍 点击Add Device位置，确保扫描框可见...")
        add_device_selectors = [
            '//android.widget.TextView[@text="Add Device"]',
            '//android.widget.TextView[contains(@text,"Add Device")]',
            '//android.widget.TextView[contains(@text,"添加设备")]'
        ]
        
        for click_attempt in range(3):
            force_print(f"🔍 第 {click_attempt + 1}/3 次尝试点击Add Device位置...")
            clicked = False
            for selector in add_device_selectors:
                try:
                    add_device_element = driver.find_element(AppiumBy.XPATH, selector)
                    if add_device_element.is_displayed():
                        try:
                            add_device_element.click()
                            force_print(f"✅ 点击Add Device位置成功（选择器: {selector}）")
                            time.sleep(1)  # 优化：从2秒减少到1秒
                            clicked = True
                            # 点击后立即检查是否已跳转到WIFI设置页面（参考 iOS 脚本：直接检查指示器）
                            for indicator in wifi_setup_indicators:
                                try:
                                    check_elem = driver.find_element(AppiumBy.XPATH, indicator)
                                    if check_elem.is_displayed():
                                        if app_package:
                                            try:
                                                current_pkg = driver.current_package
                                                if current_pkg and current_pkg != app_package:
                                                    continue
                                            except Exception:
                                                pass
                                        force_print(f"✅ 点击后扫码成功，已跳转到WIFI设置页面: {indicator}")
                                        if "Agree" in indicator:
                                            handle_agree_popup(driver, timeout=4)
                                        return True
                                except Exception:
                                    continue
                            break
                        except Exception as click_err:
                            force_print(f"⚠️ 点击失败，尝试强制点击: {click_err}")
                            try:
                                driver.execute_script("arguments[0].click();", add_device_element)
                                force_print("✅ 强制点击Add Device位置成功")
                                time.sleep(1)  # 优化：从2秒减少到1秒
                                clicked = True
                                # 点击后立即检查是否已跳转到WIFI设置页面（参考 iOS 脚本：直接检查指示器）
                                for indicator in wifi_setup_indicators:
                                    try:
                                        check_elem = driver.find_element(AppiumBy.XPATH, indicator)
                                        if check_elem.is_displayed():
                                            if app_package:
                                                try:
                                                    current_pkg = driver.current_package
                                                    if current_pkg and current_pkg != app_package:
                                                        continue
                                                except Exception:
                                                    pass
                                            force_print(f"✅ 强制点击后扫码成功，已跳转到WIFI设置页面: {indicator}")
                                            if "Agree" in indicator:
                                                handle_agree_popup(driver, timeout=4)
                                            return True
                                    except Exception:
                                        continue
                                break
                            except:
                                continue
                except:
                    continue
            
            if clicked:
                break
            else:
                force_print(f"⚠️ 第 {click_attempt + 1} 次点击Add Device位置失败")
                if click_attempt < 2:
                    time.sleep(1)
        
        # 再次检查是否已经跳转到WIFI设置页面（可能在点击过程中已扫码成功，参考 iOS 脚本）
        force_print("🔍 再次检查是否已经跳转到WiFi设置页面...")
        for indicator in wifi_setup_indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, indicator)
                if elem.is_displayed():
                    if app_package:
                        try:
                            current_pkg = driver.current_package
                            if current_pkg and current_pkg != app_package:
                                continue
                        except Exception:
                            pass
                    force_print(f"✅ 扫码成功，已跳转到WIFI设置页面: {indicator}")
                    if "Agree" in indicator:
                        if handle_agree_popup(driver, timeout=4):
                            force_print("✅ 已处理 Agree 按钮，继续后续流程")
                        else:
                            force_print("ℹ️ 未检测到 Agree 按钮，可能已跳过或不存在")
                    return True
            except Exception:
                continue
        
        # 如果还在扫码页面，等待扫码完成（参考 iOS 脚本：直接检查多个指示器，更及时）
        force_print("⏳ 等待扫码完成...")
        max_wait = 60  # 最多等待60秒
        start_time = time.time()
        click_attempted = False  # 标记是否已尝试点击恢复
        
        while time.time() - start_time < max_wait:
            # 参考 iOS 脚本：直接检查多个指示器，更及时检测页面跳转
            for indicator in wifi_setup_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, indicator)
                    if elem.is_displayed():
                        # 如果提供了 app_package，校验当前包名
                        if app_package:
                            try:
                                current_pkg = driver.current_package
                                if current_pkg and current_pkg != app_package:
                                    continue  # 包名不匹配，跳过
                            except Exception:
                                pass
                        force_print(f"✅ 扫码成功，已跳转到WIFI设置页面: {indicator}")
                        # 如果检测到 Agree 按钮，立即处理（参考 iOS 脚本）
                        if "Agree" in indicator:
                            if handle_agree_popup(driver, timeout=4):
                                force_print("✅ 已处理 Agree 按钮，继续后续流程")
                            else:
                                force_print("ℹ️ 未检测到 Agree 按钮，可能已跳过或不存在")
                        return True
                except Exception:
                    continue
            
            # 如果等待超过10秒仍未跳转，尝试点击页面顶部恢复扫码（只尝试一次）
            elapsed_time = time.time() - start_time
            if elapsed_time >= 10 and not click_attempted:
                force_print("⚠️ 等待10秒仍未跳转到Set up wifi页面，尝试点击页面顶部恢复扫码...")
                recovery_selectors = [
                    '//android.view.ViewGroup/android.view.View',
                    '//android.view.ViewGroup/android.view.View/android.view.View',
                    '//android.view.ViewGroup'
                ]
                recovery_success = False
                
                for click_count in range(3):
                    try:
                        force_print(f"🔍 第 {click_count + 1}/3 次尝试点击页面顶部恢复扫码（3个选择器）")
                        for recovery_selector in recovery_selectors:
                            try:
                                recovery_elements = driver.find_elements(AppiumBy.XPATH, recovery_selector)
                            except Exception as find_err:
                                force_print(f"⚠️ 查找元素失败({recovery_selector}): {str(find_err)[:50]}")
                                continue
                            
                            if recovery_elements:
                                # 先尝试点击页面顶部的元素（y 较小）
                                clicked_this_selector = False
                                for idx, recovery_element in enumerate(recovery_elements):
                                    try:
                                        if recovery_element.is_displayed():
                                            location = recovery_element.location
                                            if location['y'] < driver.get_window_size()['height'] * 0.3:
                                                try:
                                                    recovery_element.click()
                                                    force_print(f"✅ 第 {click_count + 1} 次点击顶部元素成功（选择器: {recovery_selector}, 元素 {idx+1}，y={location['y']}）")
                                                    time.sleep(1)  # 优化：从2秒减少到1秒
                                                    # 点击后立即检查是否已跳转到WIFI设置页面（参考 iOS 脚本：直接检查指示器）
                                                    for indicator in wifi_setup_indicators:
                                                        try:
                                                            check_elem = driver.find_element(AppiumBy.XPATH, indicator)
                                                            if check_elem.is_displayed():
                                                                if app_package:
                                                                    try:
                                                                        current_pkg = driver.current_package
                                                                        if current_pkg and current_pkg != app_package:
                                                                            continue
                                                                    except Exception:
                                                                        pass
                                                                force_print(f"✅ 点击后扫码成功，已跳转到WIFI设置页面: {indicator}")
                                                                if "Agree" in indicator:
                                                                    handle_agree_popup(driver, timeout=4)
                                                                return True
                                                        except Exception:
                                                            continue
                                                    recovery_success = True
                                                    clicked_this_selector = True
                                                    break
                                                except Exception as click_err:
                                                    force_print(f"⚠️ 点击失败，尝试强制点击: {str(click_err)[:50]}")
                                                    try:
                                                        driver.execute_script("arguments[0].click();", recovery_element)
                                                        force_print("✅ 强制点击成功")
                                                        time.sleep(1)  # 优化：从2秒减少到1秒
                                                        # 点击后立即检查是否已跳转到WIFI设置页面（参考 iOS 脚本：直接检查指示器）
                                                        for indicator in wifi_setup_indicators:
                                                            try:
                                                                check_elem = driver.find_element(AppiumBy.XPATH, indicator)
                                                                if check_elem.is_displayed():
                                                                    if app_package:
                                                                        try:
                                                                            current_pkg = driver.current_package
                                                                            if current_pkg and current_pkg != app_package:
                                                                                continue
                                                                        except Exception:
                                                                            pass
                                                                    force_print(f"✅ 强制点击后扫码成功，已跳转到WIFI设置页面: {indicator}")
                                                                    if "Agree" in indicator:
                                                                        handle_agree_popup(driver, timeout=4)
                                                                    return True
                                                            except Exception:
                                                                continue
                                                        recovery_success = True
                                                        clicked_this_selector = True
                                                        break
                                                    except:
                                                        continue
                                    except Exception:
                                        continue
                                
                                # 如果顶部元素未点击成功，尝试点击第一个可见元素
                                if not clicked_this_selector:
                                    for idx, recovery_element in enumerate(recovery_elements):
                                        try:
                                            if recovery_element.is_displayed():
                                                try:
                                                    recovery_element.click()
                                                    force_print(f"✅ 第 {click_count + 1} 次点击元素成功（选择器: {recovery_selector}, 元素 {idx+1}）")
                                                    time.sleep(1)  # 优化：从2秒减少到1秒
                                                    # 点击后立即检查是否已跳转到WIFI设置页面（参考 iOS 脚本：直接检查指示器）
                                                    for indicator in wifi_setup_indicators:
                                                        try:
                                                            check_elem = driver.find_element(AppiumBy.XPATH, indicator)
                                                            if check_elem.is_displayed():
                                                                if app_package:
                                                                    try:
                                                                        current_pkg = driver.current_package
                                                                        if current_pkg and current_pkg != app_package:
                                                                            continue
                                                                    except Exception:
                                                                        pass
                                                                force_print(f"✅ 点击后扫码成功，已跳转到WIFI设置页面: {indicator}")
                                                                if "Agree" in indicator:
                                                                    handle_agree_popup(driver, timeout=4)
                                                                return True
                                                        except Exception:
                                                            continue
                                                    recovery_success = True
                                                    clicked_this_selector = True
                                                    break
                                                except Exception as click_err:
                                                    force_print(f"⚠️ 点击失败: {str(click_err)[:50]}")
                                                    continue
                                        except Exception:
                                            continue
                            else:
                                force_print(f"⚠️ 第 {click_count + 1} 次：未找到匹配的元素 ({recovery_selector})")
                    
                    except Exception as e:
                        force_print(f"⚠️ 第 {click_count + 1} 次查找/点击元素失败: {str(e)[:50]}")
                    
                    # 如果点击后仍未跳转，等待一下再继续下一次点击
                    if click_count < 2:
                        time.sleep(1)
                
                click_attempted = True
                if recovery_success:
                    force_print("✅ 恢复扫码操作完成，继续等待跳转...")
                else:
                    force_print("⚠️ 恢复扫码操作未成功，继续等待...")
            
            # 检查间隔改为1秒（与蓝牙配网一致）
            time.sleep(1)
        
        force_print("❌ 扫码超时，未跳转到WIFI设置页面")
        # 尝试截图以便调试
        try:
            take_screenshot(driver, "unknown", "unknown", "scan_qr_timeout")
        except:
            pass
        return False
        
    except Exception as e:
        force_print(f"❌ 扫码失败: {e}")
        # 尝试截图以便调试
        try:
            take_screenshot(driver, "unknown", "unknown", "scan_qr_error")
        except:
            pass
        return False

def wait_for_wifi_setup_page(driver, timeout=15, app_package=None):
    """等待进入WiFi设置页面（可选校验当前包名匹配APP）"""
    indicators = [
        '//android.widget.TextView[@text="Set Up Wi-Fi"]',
        '//android.view.View[@content-desc="password"]',
        '//android.widget.EditText[@hint="Password"]',
        '//android.widget.Button[contains(@text,"Next")]',
        '//android.view.View[@content-desc="switch"]',
        '//android.widget.TextView[contains(@text,"Wi-Fi")]',
        '//android.widget.TextView[contains(@text,"WiFi")]'
    ]
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        # 如果提供了 app_package，则校验当前前台包名，避免系统WiFi页的误判
        if app_package:
            try:
                current_pkg = driver.current_package
                if current_pkg and current_pkg != app_package:
                    time.sleep(0.5)
                    continue
            except Exception:
                pass
        for indicator in indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, indicator)
                if elem and elem.is_displayed():
                    force_print(f"✅ 检测到WiFi设置页面元素: {indicator}")
                    return True
            except:
                continue
        time.sleep(1)
    
    return False

def handle_agree_popup(driver, timeout=6):
    """
    选择设备进入 Set up Wi-Fi 页面时，可能出现弹框，需要点击 Agree
    参考蓝牙配网的实现
    """
    try:
        agree = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@text="Agree"]'))
        )
        if agree and agree.is_displayed():
            agree.click()
            force_print("✅ 已点击 Agree 弹框")
            time.sleep(1)
            return True
    except Exception:
        pass
    return False


def handle_light_effect_page_after_password(driver, timeout=10):
    """
    步骤：输入密码后点击 Next，页面跳转至灯效页面
    灯效页面需要：
      1) 勾选: //android.widget.ImageView[@content-desc="checkbox"]
      2) 点击 Next: //android.widget.Button
    完成后进入 connect robot hotspot 页面
    """
    try:
        force_print("🔍 步骤：等待灯效页面出现...")
        checkbox = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="checkbox"]'))
        )
        if checkbox and checkbox.is_displayed():
            force_print("✅ 检测到灯效页面")
            try:
                checkbox.click()
                force_print("✅ 灯效页面：已勾选 checkbox")
                time.sleep(0.6)
            except Exception as e:
                force_print(f"⚠️ 灯效页面：勾选 checkbox 失败: {e}")

            # 点击灯效页面 Next 按钮，进入 connect robot hotspot 页面
            try:
                next_btn = WebDriverWait(driver, 6).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
                )
                next_btn.click()
                force_print("✅ 灯效页面：已点击 Next 按钮，等待进入 connect robot hotspot 页面...")
                time.sleep(2)  # 等待跳转到 connect robot hotspot 页面
                return True
            except Exception as e:
                force_print(f"⚠️ 灯效页面：点击 Next 失败: {e}")
                return False
        return False
    except Exception:
        # 未出现灯效页面，可能已直接进入 connect robot hotspot 页面
        force_print("ℹ️ 未检测到灯效页面，可能已直接进入 connect robot hotspot 页面")
        return False

def setup_wifi(driver, wifi_name, wifi_password):
    """设置 WiFi（模块化）：调用 common/选择WIFI.py，并处理灯效/引导页"""
    force_print(f"📶 步骤4: 设置WiFi ({wifi_name})...")

    # 可能会有 Agree 弹框
    try:
        handle_agree_popup(driver, timeout=3)
    except Exception:
        pass

    try:
        import importlib.util
        import os
        import time

        script_dir = os.path.dirname(os.path.abspath(__file__))
        common_dir = os.path.join(os.path.dirname(script_dir), "common")
        module_file = os.path.join(common_dir, "选择WIFI.py")
        if not os.path.exists(module_file):
            force_print(f"❌ 未找到 common/选择WIFI.py: {module_file}")
            return False

        spec = importlib.util.spec_from_file_location("p0022_wifi_setup_module", module_file)
        if not spec or not spec.loader:
            force_print("❌ 无法加载 common/选择WIFI.py（spec 为空）")
            return False

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        force_print("📶 使用独立 WiFi 选择模块: common/选择WIFI.py")

        def _shot(drv, prefix: str) -> None:
            try:
                take_screenshot(drv, "unknown", wifi_name, prefix)
            except Exception:
                pass

        app_package = None
        try:
            app_package = driver.current_package
        except Exception:
            pass

        ok = bool(
            mod.perform_wifi_setup(
                driver=driver,
                wifi_name=wifi_name,
                wifi_password=wifi_password,
                platform="android",
                log_func=force_print,
                screenshot_func=_shot,
                app_package=app_package,
            )
        )
        if not ok:
            return False

        # 输入密码 Next 后，可能出现灯效页（checkbox + Next）
        try:
            handled_light = handle_light_effect_page_after_password(driver, timeout=10)
            if handled_light:
                force_print("ℹ️ 已完成灯效页操作，继续后续配网流程")
        except Exception:
            pass

        time.sleep(2)
        force_print("✅ WiFi设置完成（模块）")
        return True
        
    except Exception as e:
        force_print(f"❌ 设置WiFi失败: {e}")
        try:
            take_screenshot(driver, "unknown", wifi_name, "wifi_setup_failed")
        except Exception:
            pass
        return False


# ==================== 应用重置功能 ====================

def reset_app_to_home(driver, device_config=None):
    """重置应用到首页（不清除数据）
    
    Args:
        driver: Appium driver
        device_config: 设备配置，用于会话失效时重建driver
    
    Returns:
        (success: bool, new_driver: WebDriver or None)
    """
    force_print("🔄 重置应用到首页...")
    try:
        # 首先检查会话是否有效
        if not check_session_validity(driver):
            force_print("⚠️ 会话已失效，需要重建driver")
            if device_config:
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(2)
                new_driver = create_device_driver(device_config)
                if new_driver:
                    force_print("✅ Driver重建成功")
                    driver = new_driver
                else:
                    force_print("❌ Driver重建失败")
                    return False, None
            else:
                force_print("❌ 会话失效且无法重建（缺少device_config）")
                return False, None
        
        # 方法1: 使用Appium的terminate_app和activate_app
        try:
            driver.terminate_app(driver.capabilities['appPackage'])
            time.sleep(3)
            driver.activate_app(driver.capabilities['appPackage'])
            time.sleep(5)
        except Exception as e:
            if _is_session_terminated_error(e) and device_config:
                force_print("⚠️ 重置应用时会话失效，重建driver...")
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(2)
                new_driver = create_device_driver(device_config)
                if new_driver:
                    driver = new_driver
                    force_print("✅ Driver重建成功，继续重置应用")
                    # 重试重置应用
                    try:
                        driver.terminate_app(driver.capabilities['appPackage'])
                        time.sleep(3)
                        driver.activate_app(driver.capabilities['appPackage'])
                        time.sleep(5)
                    except Exception as retry_err:
                        force_print(f"⚠️ 重试重置应用失败: {retry_err}")
                        return False, driver
                else:
                    return False, None
            else:
                raise
        
        # 确保返回到应用首页
        force_print("🔍 检查是否在应用首页...")
        try:
            # 检查是否在应用首页（通过查找首页特征元素）
            home_indicators = [
                '//android.widget.ImageView[@content-desc="add"]',
                '//android.widget.TextView[contains(@text,"设备")]',
                '//android.widget.TextView[contains(@text,"Sora")]',
                '//android.widget.TextView[contains(@text,"robot")]'
            ]
            
            is_on_home = False
            for indicator in home_indicators:
                try:
                    element = driver.find_element(AppiumBy.XPATH, indicator)
                    if element.is_displayed():
                        force_print(f"✅ 确认在应用首页: {indicator}")
                        is_on_home = True
                        break
                except Exception as e:
                    if _is_driver_crashed_error(e):
                        force_print("⚠️ 检测到UiAutomator2崩溃，尝试重建driver...")
                        if device_config:
                            try:
                                driver.quit()
                            except:
                                pass
                            time.sleep(2)
                            new_driver = create_device_driver(device_config)
                            if new_driver:
                                force_print("✅ Driver重建成功，继续检查首页状态")
                                driver = new_driver
                                # 重新检查首页状态
                                for retry_indicator in home_indicators:
                                    try:
                                        retry_element = driver.find_element(AppiumBy.XPATH, retry_indicator)
                                        if retry_element.is_displayed():
                                            force_print(f"✅ 确认在应用首页: {retry_indicator}")
                                            is_on_home = True
                                            break
                                    except:
                                        continue
                                break
                            else:
                                force_print("❌ Driver重建失败")
                                return False, None
                        else:
                            force_print("❌ UiAutomator2崩溃且无法重建（缺少device_config）")
                            return False, None
                    continue
            
            if not is_on_home:
                force_print("⚠️ 不在应用首页，尝试返回首页...")
                # 尝试按返回键返回首页
                try:
                    driver.press_keycode(4)  # 返回键
                    time.sleep(2)
                    driver.press_keycode(4)  # 再次按返回键
                    time.sleep(2)
                    force_print("✅ 已按返回键返回首页")
                except Exception as e:
                    if _is_driver_crashed_error(e):
                        force_print("⚠️ 按返回键时检测到UiAutomator2崩溃，尝试重建driver...")
                        if device_config:
                            try:
                                driver.quit()
                            except:
                                pass
                            time.sleep(2)
                            new_driver = create_device_driver(device_config)
                            if new_driver:
                                force_print("✅ Driver重建成功")
                                driver = new_driver
                            else:
                                force_print("❌ Driver重建失败")
                                return False, None
                        else:
                            force_print("❌ UiAutomator2崩溃且无法重建（缺少device_config）")
                            return False, None
                    else:
                        force_print("⚠️ 按返回键失败，但应用已重启")
            
        except Exception as e:
            if _is_driver_crashed_error(e):
                force_print("⚠️ 检查首页状态时检测到UiAutomator2崩溃，尝试重建driver...")
                if device_config:
                    try:
                        driver.quit()
                    except:
                        pass
                    time.sleep(2)
                    new_driver = create_device_driver(device_config)
                    if new_driver:
                        force_print("✅ Driver重建成功")
                        driver = new_driver
                    else:
                        force_print("❌ Driver重建失败")
                        return False, None
                else:
                    force_print("❌ UiAutomator2崩溃且无法重建（缺少device_config）")
                    return False, None
            else:
                force_print(f"⚠️ 检查首页状态失败: {e}")
        
        force_print("✅ 应用重置成功")
        return True, driver
        
    except Exception as e:
        if _is_driver_crashed_error(e):
            force_print("⚠️ 重置应用时检测到UiAutomator2崩溃，尝试重建driver...")
            if device_config:
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(2)
                new_driver = create_device_driver(device_config)
                if new_driver:
                    force_print("✅ Driver重建成功，重试重置应用")
                    # 重试重置应用
                    return reset_app_to_home(new_driver, device_config=device_config)
                else:
                    force_print("❌ Driver重建失败")
                    return False, None
            else:
                force_print("❌ UiAutomator2崩溃且无法重建（缺少device_config）")
                return False, None
        force_print(f"⚠️ Appium重置失败，尝试ADB方法: {e}")
    except Exception as e:
        if _is_driver_crashed_error(e):
            raise RuntimeError("UiAutomator2_CRASHED") from e
        force_print(f"⚠️ Appium重置失败，尝试ADB方法: {e}")
    
    # 如果 Appium 方法失败，尝试 ADB 方法
    try:
        # 方法2: 使用ADB命令
        import subprocess
        device_name = driver.capabilities['deviceName']
        app_package = driver.capabilities['appPackage']
        
        # 获取 adb 完整路径
        adb_path = get_adb_path()
        
        # 强制停止应用
        subprocess.run([adb_path, '-s', device_name, 'shell', 'am', 'force-stop', app_package], 
                     capture_output=True, timeout=10)
        time.sleep(2)
        
        # 重新启动应用
        subprocess.run([adb_path, '-s', device_name, 'shell', 'am', 'start', '-n', 
                       f"{app_package}/{driver.capabilities['appActivity']}"], 
                     capture_output=True, timeout=10)
        time.sleep(5)
        
        # 确保返回到应用首页
        force_print("🔍 检查是否在应用首页...")
        try:
            # 检查是否在应用首页
            home_indicators = [
                '//android.widget.ImageView[@content-desc="add"]',
                '//android.widget.TextView[contains(@text,"设备")]',
                '//android.widget.TextView[contains(@text,"Sora")]',
                '//android.widget.TextView[contains(@text,"robot")]'
            ]
            
            is_on_home = False
            for indicator in home_indicators:
                try:
                    element = driver.find_element(AppiumBy.XPATH, indicator)
                    if element.is_displayed():
                        force_print(f"✅ 确认在应用首页: {indicator}")
                        is_on_home = True
                        break
                except Exception as e:
                    if _is_driver_crashed_error(e):
                        raise RuntimeError("UiAutomator2_CRASHED") from e
                    continue
            
            if not is_on_home:
                force_print("⚠️ 不在应用首页，尝试返回首页...")
                # 尝试按返回键返回首页
                try:
                    driver.press_keycode(4)  # 返回键
                    time.sleep(2)
                    driver.press_keycode(4)  # 再次按返回键
                    time.sleep(2)
                    force_print("✅ 已按返回键返回首页")
                except Exception as e:
                    if _is_driver_crashed_error(e):
                        raise RuntimeError("UiAutomator2_CRASHED") from e
                    force_print("⚠️ 按返回键失败，但应用已重启")
            
        except RuntimeError as e:
            if "UiAutomator2_CRASHED" in str(e):
                raise
            force_print(f"⚠️ 检查首页状态失败: {e}")
        except Exception as e:
            if _is_driver_crashed_error(e):
                raise RuntimeError("UiAutomator2_CRASHED") from e
            force_print(f"⚠️ 检查首页状态失败: {e}")
        
        force_print("✅ ADB重置成功")
        return True, driver
    except RuntimeError as e:
        if "UiAutomator2_CRASHED" in str(e):
            raise
        force_print(f"❌ 应用重置失败: {e}")
        return False
    except Exception as e2:
        if _is_driver_crashed_error(e2):
            raise RuntimeError("UiAutomator2_CRASHED") from e2
        force_print(f"❌ 应用重置失败: {e2}")
        return False

# ==================== connect hotspot / 配网结果（补回被裁剪的公共能力） ====================

def _is_home_after_pairing(driver) -> bool:
    """判断是否已回到首页（用于配网成功判定）"""
    try:
        # 首页强特征：add 按钮或 Home tab
        add_candidates = [
            '//android.widget.ImageView[@content-desc="add"]',
            '(//android.widget.ImageView[@content-desc="add"])[2]',
        ]
        for xp in add_candidates:
            try:
                els = driver.find_elements(AppiumBy.XPATH, xp)
                if any(e.is_displayed() for e in els):
                    return True
            except Exception:
                continue

        home_tabs = driver.find_elements(AppiumBy.XPATH, '//android.view.View[@content-desc="Home"]')
        if any(e.is_displayed() for e in home_tabs):
            return True
    except Exception:
        return False
    return False


def wait_for_pairing_result(driver, timeout: int = 180) -> str:
    """
    等待配网结果：success / failed / timeout / success_need_next
    """
    force_print("⏳ 等待配网结果...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            if _is_home_after_pairing(driver):
                force_print("✅ 已回到首页，判定配网成功")
                return "success"

            # 配网进行中
            try:
                pairing_text = driver.find_element(AppiumBy.XPATH, '//android.widget.TextView[@text="Pairing with your device"]')
                if pairing_text.is_displayed():
                    force_print("🔄 配网进行中...")
                    time.sleep(5)
                    continue
            except Exception:
                pass

            # 失败
            failure_indicators = [
                '//android.widget.TextView[@text="Data transmitting failed."]',
                '//android.widget.TextView[contains(@text,"failed")]',
                '//android.widget.TextView[contains(@text,"失败")]',
                '//android.widget.TextView[contains(@text,"error")]',
            ]
            for xp in failure_indicators:
                try:
                    el = driver.find_element(AppiumBy.XPATH, xp)
                    if el.is_displayed():
                        force_print(f"❌ 配网失败: {xp}")
                        return "failed"
                except Exception:
                    continue

            # 成功页需要 Next
            try:
                btns = driver.find_elements(AppiumBy.XPATH, "//android.widget.Button")
                if any(b.is_displayed() for b in btns):
                    # 如果不在首页且存在按钮，很多版本是成功页 Next
                    return "success_need_next"
            except Exception:
                pass

            time.sleep(2)
        except Exception as e:
            force_print(f"⚠️ 检查配网结果异常: {e}")
            time.sleep(2)

    force_print("⏰ 配网超时")
    return "timeout"


def handle_post_pairing_success_flow(driver, timeout: int = 35) -> bool:
    """
    成功页收尾：Next -> 已绑定/Already paired -> 回首页
    """
    # 1) 点击 Next（页面上第一个 Button 兜底）
    try:
        next_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
        )
        next_btn.click()
        time.sleep(1.2)
        force_print("✅ 成功页：已点击 Next")
    except Exception as e:
        force_print(f"❌ 成功页：点击 Next 失败: {e}")
        return False

    # 2) 绑定弹框确认：优先文字按钮，否则点最左按钮兜底
    bound_xpaths = [
        '//android.widget.Button[contains(@text,"Already paired")]',
        '//android.widget.Button[contains(@text,"已绑定")]',
        '//android.widget.Button[contains(@text,"已配对")]',
        '//android.widget.Button[@resource-id="android:id/button1"]',
    ]
    clicked = False
    for xp in bound_xpaths:
        try:
            el = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp)))
            el.click()
            clicked = True
            force_print(f"✅ 绑定弹框：已点击确认按钮 ({xp})")
            time.sleep(1.2)
            break
        except Exception:
            continue

    if not clicked:
        try:
            btns = driver.find_elements(AppiumBy.XPATH, "//android.widget.Button")
            visible = [b for b in btns if b.is_displayed()]
            if visible:
                # 取最左侧
                def center_x(b):
                    try:
                        r = b.rect
                        return float(r.get("x", 0)) + float(r.get("width", 0)) / 2.0
                    except Exception:
                        return 1e9
                visible.sort(key=center_x)
                visible[0].click()
                clicked = True
                force_print("✅ 绑定弹框：已点击最左按钮(兜底)")
                time.sleep(1.2)
        except Exception:
            pass

    # 3) 校验回首页
    start = time.time()
    while time.time() - start < timeout:
        if _is_home_after_pairing(driver):
            force_print("✅ 收尾完成：已回到首页")
            return True
        time.sleep(1)
    force_print("❌ 收尾失败：未在超时内回到首页")
    return False


def connect_device_hotspot(driver, device_config=None) -> bool:
    """
    connect robot hotspot 页面触发连接：
    - 点击页面按钮 -> 弹框 Confirm -> 系统 Join
    - 或进入系统热点列表后点击指定热点项（OPLUS/OnePlus 系统）
    """
    force_print("📡 连接设备热点（connect robot hotspot）...")
    try:
        # 1) 先尝试点击页面上的通用按钮（可能触发弹框/跳转）
        try:
            btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
            )
            btn.click()
            time.sleep(1)
        except Exception:
            pass

        # 2) 弹框 Confirm
        try:
            confirm = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.TextView[@text="Confirm"]'))
            )
            confirm.click()
            force_print("✅ 已点击 Confirm")
            time.sleep(1)
        except Exception:
            pass

        # 3) 系统 Join
        try:
            join = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.Button[@resource-id="android:id/button1"]'))
            )
            join.click()
            force_print("✅ 已点击 Join")
            time.sleep(2)
            return True
        except Exception:
            pass

        # 4) OPLUS 热点列表点击（用户指定路径）
        hotspot_item_xpath = '//androidx.recyclerview.widget.RecyclerView[@resource-id="com.oplus.wirelesssettings:id/recycler_view"]/android.widget.LinearLayout[3]/android.widget.FrameLayout'
        try:
            item = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((AppiumBy.XPATH, hotspot_item_xpath)))
            item.click()
            force_print("✅ 已点击热点列表项（OPLUS）")
            time.sleep(2)
            return True
        except Exception as e:
            force_print(f"⚠️ 未能点击热点列表项（OPLUS）: {e}")

        # 如果以上都没命中，返回失败
        force_print("❌ 连接设备热点失败：未命中任何可操作步骤")
        return False
    except Exception as e:
        force_print(f"❌ 连接设备热点异常: {e}")
        return False

# ==================== 单次配网流程 ====================

def single_pairing_flow(driver, wifi_name, wifi_password, device_config=None):
    """单次扫码配网流程（支持 UiAutomator2 崩溃恢复）
    
    返回: (result, message, new_driver)
    - result: "success", "failed", "timeout", "error"
    - message: 结果描述
    - new_driver: 如果 driver 被重建，返回新的 driver；否则返回 None
    """
    force_print(f"\n🔄 开始单次扫码配网流程 (WiFi: {wifi_name})")
    force_print("=" * 60)
    
    max_recovery_attempts = 2  # 最多尝试恢复2次
    
    for recovery_attempt in range(max_recovery_attempts):
        try:
            # 步骤0: 重置应用到首页（不清除数据）
            force_print("🔄 重置应用到首页（不清除数据）...")
            try:
                success, new_driver = reset_app_to_home(driver, device_config=device_config)
                if not success:
                    force_print("⚠️ 应用重置失败，但继续执行")
                if new_driver is not None:
                    driver = new_driver
                    force_print("🔄 更新 driver 引用（driver 已重建）")
            except RuntimeError as e:
                if "UiAutomator2_CRASHED" in str(e) and device_config and recovery_attempt < max_recovery_attempts - 1:
                    force_print(f"⚠️ UiAutomator2 崩溃，尝试重建 driver (第 {recovery_attempt + 1}/{max_recovery_attempts} 次)...")
                    try:
                        driver.quit()
                    except:
                        pass
                    time.sleep(3)
                    new_driver = create_device_driver(device_config)
                    if not new_driver:
                        return "error", "无法重建 Appium 会话", None
                    force_print("✅ Driver 重建成功，重试配网流程...")
                    driver = new_driver
                    continue
                else:
                    raise
            wait_after_step("应用重置")
            
            # 步骤1: 触发机器热点
            if not trigger_robot_hotspot():
                return "error", "触发机器热点失败", None
            wait_after_step("触发机器热点")
            
            # 步骤2: 确保有add device按钮
            success, new_driver = ensure_add_device_button(driver, device_config=device_config)
            if not success:
                return "error", "无法找到add device按钮", None
            if new_driver is not None:
                driver = new_driver
                force_print("🔄 更新 driver 引用（driver 已重建）")
            wait_after_step("确认首页add按钮")
            
            # 步骤3: 点击添加设备按钮
            if not click_add_device_button(driver):
                return "error", "点击添加设备按钮失败", None
            wait_after_step("点击添加设备按钮")
            
            # 步骤4: 扫描二维码
            if not scan_qrcode(driver):
                return "error", "扫描二维码失败", None
            wait_after_step("扫描二维码")
            
            # 步骤5: 设置WiFi
            if not setup_wifi(driver, wifi_name, wifi_password):
                return "error", "设置WiFi失败", None
            wait_after_step("设置WiFi")
            
            # 步骤6: 连接设备热点（灯效页面后直接进入 connect robot hotspot 页面）
            if not connect_device_hotspot(driver, device_config):
                return "error", "连接设备热点失败", None
            wait_after_step("连接设备热点")
            
            # 步骤8: 等待配网结果
            result = wait_for_pairing_result(driver)
            
            # 新流程：成功页需要点击 Next -> 配对弹框确认 -> 回到 Home（参考 iOS 脚本和蓝牙配网脚本）
            if result == "success_need_next":
                force_print("ℹ️ 检测到成功页 Next，需要完成收尾跳转首页...")
                if handle_post_pairing_success_flow(driver, timeout=45):
                    result = "success"
                else:
                    # 再兜底：如果其实已经回到首页，就别判失败
                    if _is_home_after_pairing(driver):
                        force_print("✅ 收尾流程失败但页面已在首页，按成功处理")
                        result = "success"
                    else:
                        return "error", "配网成功后收尾步骤失败（Next/弹框/回Home）", None
            
            if result == "success":
                force_print("🎉 配网成功！")
                return "success", "配网成功", None
            elif result == "failed":
                force_print("❌ 配网失败，重置应用...")
                success, new_driver = reset_app_to_home(driver, device_config=device_config)
                if new_driver is not None:
                    driver = new_driver
                return "failed", "配网失败", new_driver
            else:
                force_print("⏰ 配网超时，重置应用...")
                success, new_driver = reset_app_to_home(driver, device_config=device_config)
                if new_driver is not None:
                    driver = new_driver
                return "timeout", "配网超时", new_driver
                
        except RuntimeError as e:
            if "UiAutomator2_CRASHED" in str(e) and device_config and recovery_attempt < max_recovery_attempts - 1:
                force_print(f"⚠️ UiAutomator2 崩溃，尝试重建 driver (第 {recovery_attempt + 1}/{max_recovery_attempts} 次)...")
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(3)
                new_driver = create_device_driver(device_config)
                if not new_driver:
                    return "error", "无法重建 Appium 会话", None
                force_print("✅ Driver 重建成功，重试配网流程...")
                driver = new_driver
                continue
            else:
                force_print(f"❌ 配网流程异常: {e}")
                try:
                    device_name = driver.capabilities.get('deviceName', 'unknown_device')
                    take_screenshot(driver, device_name, wifi_name, "pairing_error")
                except:
                    pass
                return "error", str(e), None
        except Exception as e:
            # 检查是否是崩溃错误
            if _is_driver_crashed_error(e) and device_config and recovery_attempt < max_recovery_attempts - 1:
                force_print(f"⚠️ UiAutomator2 崩溃，尝试重建 driver (第 {recovery_attempt + 1}/{max_recovery_attempts} 次)...")
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(3)
                new_driver = create_device_driver(device_config)
                if not new_driver:
                    return "error", "无法重建 Appium 会话", None
                force_print("✅ Driver 重建成功，重试配网流程...")
                driver = new_driver
                continue
            else:
                force_print(f"❌ 配网流程异常: {e}")
                try:
                    device_name = driver.capabilities.get('deviceName', 'unknown_device')
                    take_screenshot(driver, device_name, wifi_name, "pairing_error")
                except:
                    pass
                return "error", str(e), None
    
    # 如果所有恢复尝试都失败
    return "error", "UiAutomator2 崩溃且无法恢复", None

# ==================== 设备驱动管理 ====================

def check_appium_server(port):
    """检查Appium服务器是否运行（参考蓝牙配网脚本）"""
    try:
        import socket
        force_print(f"🔍 检查Appium服务器 (端口 {port}) 是否运行...")
        
        # 尝试连接Appium服务器的健康检查端点
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result == 0:
            # 端口开放，尝试访问Appium的状态端点
            try:
                import urllib.request
                url = f"http://127.0.0.1:{port}/status"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=3) as response:
                    if response.status == 200:
                        force_print(f"✅ Appium服务器 (端口 {port}) 运行正常")
                        return True
            except:
                pass
            
            force_print(f"⚠️ 端口 {port} 已开放，但可能不是Appium服务器")
            return False
        else:
            force_print(f"❌ Appium服务器 (端口 {port}) 未运行")
            force_print(f"📱 解决方案:")
            force_print(f"   1. 启动Appium服务器:")
            force_print(f"      appium -p {port}")
            force_print(f"   2. 或在后台运行:")
            force_print(f"      appium -p {port} > appium_{port}.log 2>&1 &")
            return False
            
    except Exception as e:
        force_print(f"⚠️ 检查Appium服务器失败: {e}")
        return False

def create_device_driver(device_config):
    """创建设备驱动（参考蓝牙配网脚本，添加更详细的错误处理）"""
    try:
        # 检查是否是 Android 设备
        platform = device_config.get('platform', 'android')
        if platform != 'android':
            force_print(f"⚠️ 跳过非 Android 设备: {device_config.get('description', 'unknown')} (平台: {platform})")
            return None
        
        # 检查必需的字段
        if 'app_package' not in device_config:
            force_print(f"❌ 设备配置缺少 app_package 字段: {device_config.get('description', 'unknown')}")
            return None
        
        if 'app_activity' not in device_config:
            force_print(f"❌ 设备配置缺少 app_activity 字段: {device_config.get('description', 'unknown')}")
            return None
        
        # 检查Appium服务器是否运行（参考蓝牙配网脚本）
        port = device_config.get('port', 4723)
        if not check_appium_server(port):
            force_print(f"❌ Appium服务器 (端口 {port}) 未运行，无法连接设备")
            force_print(f"📱 请先启动Appium服务器后再重试")
            return None
        
        from appium.options.android import UiAutomator2Options

        options = UiAutomator2Options()
        options.platform_name = 'Android'
        # 使用 udid 确保连接到正确的设备（即使多个设备同时连接）
        options.udid = device_config['device_name']  # device_name 实际是设备的 UDID
        options.device_name = device_config['device_name']  # 保留 device_name 用于兼容性
        options.platform_version = device_config['platform_version']
        options.app_package = device_config['app_package']
        options.app_activity = device_config['app_activity']
        options.automation_name = 'UiAutomator2'
        options.no_reset = True
        options.new_command_timeout = 300

        # 尝试两个 Appium URL（新版本可能不需要 /wd/hub）
        server_urls = [
            f"http://127.0.0.1:{device_config['port']}",
            f"http://127.0.0.1:{device_config['port']}/wd/hub"
        ]
        
        last_error = None
        for server_url in server_urls:
            try:
                force_print(f"🔗 尝试连接 Appium 服务器: {server_url}")
                driver = webdriver.Remote(server_url, options=options)
                
                # 验证实际连接的设备是否匹配配置
                try:
                    actual_device_name = driver.capabilities.get('deviceName', '')
                    expected_device_name = device_config.get('device_name', '')
                    actual_udid = driver.capabilities.get('udid', '')
                    
                    force_print(f"📱 配置的设备ID: {expected_device_name}")
                    force_print(f"📱 实际连接的设备ID: {actual_device_name}")
                    if actual_udid:
                        force_print(f"📱 实际连接的UDID: {actual_udid}")
                    
                    # 检查设备ID是否匹配
                    if actual_device_name and expected_device_name:
                        if actual_device_name != expected_device_name and actual_udid != expected_device_name:
                            force_print(f"⚠️ 警告：实际连接的设备ID ({actual_device_name}) 与配置的设备ID ({expected_device_name}) 不匹配！")
                            force_print(f"⚠️ 请检查 Appium 服务器端口 {device_config['port']} 是否正确映射到设备 {device_config['description']}")
                except Exception as verify_err:
                    force_print(f"⚠️ 设备验证失败: {verify_err}")
                
                force_print(f"✅ 设备 {device_config['description']} 连接成功")
                return driver
            except Exception as conn_err:
                last_error = conn_err
                err_msg = str(conn_err)
                force_print(f"⚠️ 连接 {server_url} 失败: {err_msg[:200]}")
                
                # 如果是资源未找到错误，尝试下一个URL
                if ("resource could not be found" in err_msg.lower() or
                    "not supported by the mapped resource" in err_msg.lower()):
                    force_print("🔁 尝试备用 URL...")
                    continue
                else:
                    # 其他错误（如连接拒绝），直接返回
                    break
        
        if last_error:
            error_msg = str(last_error)
            force_print(f"❌ 所有 Appium URL 尝试失败，最后错误: {error_msg[:200]}")
            
            # 提供更详细的错误信息和建议（参考蓝牙配网脚本）
            if "getprop: not found" in error_msg or "API level" in error_msg:
                force_print(f"💡 提示: 无法获取设备 API level")
                force_print(f"   可能的原因:")
                force_print(f"   1. 设备未正确连接或未授权")
                force_print(f"   2. 设备不是 Android 设备或处于异常状态（如恢复模式）")
                force_print(f"   3. Appium 服务器无法访问设备")
                force_print(f"   解决方案:")
                force_print(f"   1. 检查设备连接: adb devices")
                force_print(f"   2. 检查设备状态: adb -s {device_config.get('device_name', 'device')} get-state")
                force_print(f"   3. 验证设备是 Android 设备: adb -s {device_config.get('device_name', 'device')} shell getprop ro.build.version.sdk")
                force_print(f"   4. 如果设备未授权，请检查设备上的授权提示")
                force_print(f"   5. 重启 Appium 服务器: appium -p {device_config.get('port', 4723)}")
            elif "Connection refused" in error_msg:
                force_print(f"💡 提示: Appium服务器可能未启动或端口 {device_config.get('port', 4723)} 配置错误")
                force_print(f"   解决方案: 启动 Appium 服务器: appium -p {device_config.get('port', 4723)}")
            elif "404" in error_msg or "not found" in error_msg.lower():
                force_print(f"💡 提示: Appium服务器端点可能不正确，请检查服务器版本")
            elif "timeout" in error_msg.lower():
                force_print(f"💡 提示: 连接超时，请检查设备是否已连接并授权")
            elif "ANDROID_HOME" in error_msg or "ANDROID_SDK_ROOT" in error_msg:
                force_print(f"💡 提示: 需要设置 Android SDK 环境变量")
                force_print(f"   解决方案:")
                force_print(f"   1. 找到 Android SDK 安装路径（通常在 ~/Library/Android/sdk 或 ~/Android/Sdk）")
                force_print(f"   2. 设置环境变量:")
                force_print(f"      export ANDROID_HOME=~/Library/Android/sdk")
                force_print(f"      export PATH=$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools")
                force_print(f"   3. 重新启动 Appium 服务器（确保环境变量已设置）")
        return None

    except Exception as e:
        error_msg = str(e)
        force_print(f"❌ 创建设备驱动失败: {error_msg}")
        
        # 提供更详细的错误信息和建议
        if "getprop: not found" in error_msg or "API level" in error_msg:
            force_print(f"💡 提示: 无法获取设备 API level")
            force_print(f"   可能的原因:")
            force_print(f"   1. 设备未正确连接或未授权")
            force_print(f"   2. 设备不是 Android 设备或处于异常状态（如恢复模式）")
            force_print(f"   3. Appium 服务器无法访问设备")
            force_print(f"   解决方案:")
            force_print(f"   1. 检查设备连接: adb devices")
            force_print(f"   2. 检查设备状态: adb -s {device_config.get('device_name', 'device')} get-state")
            force_print(f"   3. 验证设备是 Android 设备: adb -s {device_config.get('device_name', 'device')} shell getprop ro.build.version.sdk")
            force_print(f"   4. 如果设备未授权，请检查设备上的授权提示")
            force_print(f"   5. 重启 Appium 服务器: appium -p {device_config.get('port', 4723)}")
        return None

# ==================== 多设备测试 ====================

def run_multi_device_test():
    """多设备/多路由器扫码配网测试入口（被主程序调用）"""
    cfg = load_device_config()
    if not cfg:
        force_print("❌ 未加载到 device_config.json")
        return
    
    device_cfgs = cfg.get("device_configs", {}) or {}
    wifi_cfgs = cfg.get("wifi_configs", []) or []
    test_cfg = cfg.get("test_config", {}) or {}
    loop_per_router = int(test_cfg.get("loop_count_per_router", 1))

    if not device_cfgs:
        force_print("❌ 未找到任何 Android 设备配置（device_configs）")
        return
    if not wifi_cfgs:
        force_print("❌ 未找到任何 WiFi 配置（wifi_configs）")
        return

    total = 0
    succ = 0
    fail = 0
    detailed_results = {}
    interrupted = False
    
    # 同步到全局，便于中断保存
    _global_test_data["test_config"] = test_cfg
    _global_test_data["detailed_results"] = detailed_results

    try:
        for dev_key, dev_cfg in device_cfgs.items():
            dev_name = dev_cfg.get("description", dev_cfg.get("device_name", dev_key))
            force_print(f"\n📱 当前测试设备: {dev_name}")
            force_print("-" * 60)

            driver = create_device_driver(dev_cfg)
            if not driver:
                force_print("❌ 该设备 driver 创建失败，跳过")
                continue
            
            if dev_name not in detailed_results:
                detailed_results[dev_name] = {"routers": {}}

            try:
                for wifi in wifi_cfgs:
                    name = wifi.get("name")
                    pwd = wifi.get("password")
                    if not name:
                        continue
                    force_print(f"\n📶 路由器: {name}")

                    if name not in detailed_results[dev_name]["routers"]:
                        detailed_results[dev_name]["routers"][name] = {"success": 0, "failure": 0, "rounds": []}

                    for i in range(loop_per_router):
                        force_print(f"\n🔄 第 {i+1}/{loop_per_router} 次测试")
                        total += 1
                        _global_test_data["total_tests"] = total

                        ts = datetime.now().strftime("%H:%M:%S")
                        res, msg, new_driver = single_pairing_flow(driver, name, pwd, device_config=dev_cfg)
                        if new_driver is not None:
                            driver = new_driver

                        detailed_results[dev_name]["routers"][name]["rounds"].append(
                            {"round": i + 1, "result": res, "message": msg, "timestamp": ts}
                        )

                        if res == "success":
                            succ += 1
                            detailed_results[dev_name]["routers"][name]["success"] += 1
                        else:
                            fail += 1
                            detailed_results[dev_name]["routers"][name]["failure"] += 1

                        _global_test_data["success_count"] = succ
                        _global_test_data["failure_count"] = fail
                        save_test_data_to_file()
                        
                        if i < loop_per_router - 1:
                            time.sleep(10)
                    
            except KeyboardInterrupt:
                interrupted = True
                raise
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass
    
    except KeyboardInterrupt:
        interrupted = True
        force_print("\n⚠️ 用户中断测试，正在生成报告...")
    finally:
        finalize_results(total, succ, fail, detailed_results, test_cfg, interrupted=interrupted)


def finalize_results(total_tests, success_count, failure_count, detailed_results, test_config, interrupted=False):
    """汇总测试结果并生成报告（模块化：common/2测试报告.py）"""
    try:
        import importlib.util
        import os

        script_dir = os.path.dirname(os.path.abspath(__file__))
        common_dir = os.path.join(os.path.dirname(script_dir), "common")
        module_file = os.path.join(common_dir, "2测试报告.py")
        if not os.path.exists(module_file):
            force_print(f"⚠️ 未找到测试报告模块: {module_file}，仅输出简单汇总")
            force_print(f"总测试次数: {total_tests}")
            force_print(f"成功次数: {success_count}")
            force_print(f"失败次数: {failure_count}")
            return

        spec = importlib.util.spec_from_file_location("p0022_test_report_module", module_file)
        if not spec or not spec.loader:
            raise RuntimeError("无法加载 2测试报告.py")

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        mod.finalize_results(
            total_tests=total_tests,
            success_count=success_count,
            failure_count=failure_count,
            detailed_results=detailed_results,
            test_config=test_config,
            platform="Android",
            network_method="1扫码配网",
            run_dir=RUN_DIR if 'RUN_DIR' in globals() else None,
            log_func=force_print,
            interrupted=interrupted,
        )
    except Exception as e:
        force_print(f"⚠️ 生成报告失败: {e}")
        force_print(f"总测试次数: {total_tests}")
        force_print(f"成功次数: {success_count}")
        force_print(f"失败次数: {failure_count}")


# ==================== 主程序 ====================

if __name__ == "__main__":
    force_print("🚀 启动Android扫码配网测试脚本")
    force_print("=" * 80)
    
    # 注册信号处理器
    signal.signal(signal.SIGTERM, emergency_save_and_exit)
    signal.signal(signal.SIGINT, emergency_save_and_exit)
    
    # 注册退出处理函数
    atexit.register(lambda: emergency_save_and_exit(signum=None, frame=None))
    
    try:
        run_multi_device_test()
    except KeyboardInterrupt:
        force_print("\n⚠️ 用户中断测试")
        emergency_save_and_exit()
    except Exception as e:
        force_print(f"\n❌ 测试异常: {e}")
        emergency_save_and_exit()
    finally:
        force_print("\n🏁 测试完成")

