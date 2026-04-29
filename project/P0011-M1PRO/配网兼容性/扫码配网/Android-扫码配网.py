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

# 机器人热点触发配置（P0024-M0：串口触发）
# 可通过环境变量覆盖
SERIAL_PORT = os.environ.get("ROBOT_SERIAL_PORT", "/dev/tty.usbserial-120")
SERIAL_BAUD = int(os.environ.get("ROBOT_SERIAL_BAUD", "115200"))
SERIAL_TRIGGER_CMD = os.environ.get("ROBOT_SERIAL_CMD", "SET state 4")

# 向后兼容：机器人热点触发所需的设备ID（已废弃，改用串口方式）
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

# ==================== ROS2消息触发 ====================

def trigger_robot_hotspot():
    """
    触发机器热点（P0024-M0：使用端口命令脚本）
    优先使用 common/端口命令.py 模块
    """
    force_print("📡 步骤1: 触发机器热点...")
    
    # 导入端口命令模块
    port_command_module = None
    try:
        import importlib.util
        script_dir = os.path.dirname(os.path.abspath(__file__))
        common_dir = os.path.join(os.path.dirname(script_dir), "common")
        port_command_file = os.path.join(common_dir, "端口命令.py")
        
        if os.path.exists(port_command_file):
            spec = importlib.util.spec_from_file_location("端口命令", port_command_file)
            if spec and spec.loader:
                端口命令 = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(端口命令)
                port_command_module = 端口命令
                force_print(f"✅ 已加载端口命令模块: 端口命令.py")
        else:
            force_print(f"⚠️ 未找到端口命令模块: {port_command_file}")
    except Exception as e:
        force_print(f"⚠️ 无法加载端口命令模块: {e}")
    
    # 优先使用端口命令模块
    if port_command_module:
        try:
            port = SERIAL_PORT
            baud = SERIAL_BAUD
            cmd = SERIAL_TRIGGER_CMD
            
            force_print(f"🔌 使用端口命令模块触发热点: {port} @ {baud}bps -> {cmd}")
            
            # 调用 send_command 函数
            result = port_command_module.send_command(
                port=port,
                baudrate=baud,
                command=cmd,
                retry_on_busy=True
            )
            
            if "✅" in result:
                force_print("✅ 端口命令模块触发热点成功")
                return True
            else:
                force_print(f"❌ 端口命令模块触发热点失败: {result}")
                return False
                
        except Exception as e:
            force_print(f"❌ 调用端口命令模块失败: {e}")
            # 继续尝试备用方式
    else:
        force_print("⚠️ 端口命令模块未加载，尝试备用方式...")
    
    # 备用方式：使用 subprocess 直接调用端口命令脚本
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        common_dir = os.path.join(os.path.dirname(script_dir), "common")
        port_command_script = os.path.join(common_dir, "端口命令.py")
        
        if os.path.exists(port_command_script):
            force_print(f"📝 使用端口命令脚本: {port_command_script}")
            result = subprocess.run(
                [sys.executable, port_command_script,
                 '--port', SERIAL_PORT,
                 '--baud', str(SERIAL_BAUD),
                 '--command', SERIAL_TRIGGER_CMD],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                if result.stdout.strip():
                    force_print(f"ℹ️ 端口命令输出: {result.stdout.strip()}")
                force_print("✅ 端口命令脚本触发热点成功")
                return True
            else:
                output = result.stdout.strip()
                error = result.stderr.strip()
                force_print(f"❌ 端口命令脚本失败（返回码: {result.returncode}）")
                if output:
                    force_print(f"   输出: {output}")
                if error:
                    force_print(f"   错误: {error}")
                return False
        else:
            force_print(f"❌ 未找到端口命令脚本: {port_command_script}")
            return False
            
    except Exception as e:
        force_print(f"❌ 调用端口命令脚本失败: {e}")
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
    """使用摄像头扫描二维码"""
    force_print("📷 步骤3: 使用摄像头扫描二维码...")
    try:
        # 等待扫码页面出现
        time.sleep(3)
        
        # 检查是否已经跳转到WIFI设置页面（扫码成功）
        wifi_setup_indicators = [
            '//android.widget.TextView[contains(@text,"Wi-Fi")]',
            '//android.widget.TextView[contains(@text,"WiFi")]',
            '//android.widget.EditText[@hint*="密码"]',
            '//android.widget.EditText[@hint*="Password"]',
            '//android.widget.TextView[@text="Set Up Wi-Fi"]',
            '//android.view.View[@content-desc="switch"]'
        ]
        
        for indicator in wifi_setup_indicators:
            try:
                element = driver.find_element(AppiumBy.XPATH, indicator)
                if element.is_displayed():
                    force_print("✅ 扫码成功，已跳转到WIFI设置页面")
                    return True
            except:
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
                            time.sleep(2)
                            clicked = True
                            break
                        except Exception as click_err:
                            force_print(f"⚠️ 点击失败，尝试强制点击: {click_err}")
                            try:
                                driver.execute_script("arguments[0].click();", add_device_element)
                                force_print("✅ 强制点击Add Device位置成功")
                                time.sleep(2)
                                clicked = True
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
        
        # 再次检查是否已经跳转到WIFI设置页面（可能在点击过程中已扫码成功）
        for indicator in wifi_setup_indicators:
            try:
                element = driver.find_element(AppiumBy.XPATH, indicator)
                if element.is_displayed():
                    force_print("✅ 扫码成功，已跳转到WIFI设置页面")
                    return True
            except:
                continue
        
        # 如果还在扫码页面，等待扫码完成
        force_print("⏳ 等待扫码完成...")
        max_wait = 60  # 最多等待60秒
        start_time = time.time()
        check_interval = 3  # 每3秒检查一次
        click_attempted = False  # 标记是否已尝试点击恢复
        
        while time.time() - start_time < max_wait:
            # 检查是否已跳转到WIFI设置页面
            for indicator in wifi_setup_indicators:
                try:
                    element = driver.find_element(AppiumBy.XPATH, indicator)
                    if element.is_displayed():
                        force_print(f"✅ 扫码成功，已跳转到WIFI设置页面: {indicator}")
                        return True
                except:
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
                                                    time.sleep(2)
                                                    # 点击后立即检查是否已跳转到WIFI设置页面
                                                    for indicator in wifi_setup_indicators:
                                                        try:
                                                            check_element = driver.find_element(AppiumBy.XPATH, indicator)
                                                            if check_element.is_displayed():
                                                                force_print(f"✅ 点击后扫码成功，已跳转到WIFI设置页面: {indicator}")
                                                                return True
                                                        except:
                                                            continue
                                                    recovery_success = True
                                                    clicked_this_selector = True
                                                    break
                                                except Exception as click_err:
                                                    force_print(f"⚠️ 点击失败，尝试强制点击: {str(click_err)[:50]}")
                                                    try:
                                                        driver.execute_script("arguments[0].click();", recovery_element)
                                                        force_print("✅ 强制点击成功")
                                                        time.sleep(2)
                                                        for indicator in wifi_setup_indicators:
                                                            try:
                                                                check_element = driver.find_element(AppiumBy.XPATH, indicator)
                                                                if check_element.is_displayed():
                                                                    force_print(f"✅ 强制点击后扫码成功，已跳转到WIFI设置页面: {indicator}")
                                                                    return True
                                                            except:
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
                                                    time.sleep(2)
                                                    for indicator in wifi_setup_indicators:
                                                        try:
                                                            check_element = driver.find_element(AppiumBy.XPATH, indicator)
                                                            if check_element.is_displayed():
                                                                force_print(f"✅ 点击后扫码成功，已跳转到WIFI设置页面: {indicator}")
                                                                return True
                                                        except:
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
            
            time.sleep(check_interval)
        
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

def setup_wifi(driver, wifi_name, wifi_password):
    """设置WiFi"""
    force_print(f"📶 步骤4: 设置WiFi ({wifi_name})...")
    try:
        # 无论是否在WiFi设置页面，都需要点击切换WiFi按钮来进入系统WiFi列表
        force_print("🔍 点击切换WiFi按钮，进入系统WiFi列表...")
        change_wifi_selectors = [
            '//android.view.View[@content-desc="switch"]',  # 最新的元素定位（优先）
            '//android.view.View[@content-desc="switch"]/..',  # switch的父元素（可能可点击）
            '//android.widget.Button[contains(@text,"切换")]',
            '//android.widget.Button[contains(@text,"Change")]',
            '//android.widget.Button[contains(@text,"WiFi")]',
            '//android.widget.Button[contains(@text,"Wi-Fi")]',
            '//android.view.View[@content-desc*="change"]',
            '//android.view.View[@content-desc*="wifi"]',
            '//android.view.View[@content-desc*="switch"]',  # 包含switch的备用选择器
        ]
        
        change_wifi_clicked = False
        for selector in change_wifi_selectors:
            try:
                change_wifi_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                change_wifi_button.click()
                force_print(f"✅ 点击切换wifi按钮成功（选择器: {selector}）")
                time.sleep(3)
                change_wifi_clicked = True
                break
            except Exception as e:
                force_print(f"⚠️ 选择器失败: {selector} - {str(e)[:50]}")
                continue
        
        if not change_wifi_clicked:
            force_print("⚠️ 未找到切换wifi按钮，尝试继续执行...")
        else:
            # 等待进入系统WiFi页面
            force_print("⏳ 等待进入系统WiFi页面...")
            time.sleep(2)
        
        # 寻找WiFi网络（参考蓝牙配网的实现）
        force_print(f"🔍 寻找WiFi: {wifi_name}")
        
        # 等待WiFi列表加载
        time.sleep(3)
        
        # 多种WiFi选择器（按优先级排序，参考蓝牙配网）
        wifi_selectors = [
            # 精确匹配
            f'//android.widget.TextView[@text="{wifi_name}"]',
            # 包含匹配（用于系统WiFi设置页面）
            f'//android.widget.TextView[contains(@text, "{wifi_name}")]',
            # 通过父容器查找（系统WiFi列表项通常是可点击的容器）
            f'//android.view.View[.//android.widget.TextView[@text="{wifi_name}"]]',
            f'//android.view.View[.//android.widget.TextView[contains(@text, "{wifi_name}")]]',
            # 通过LinearLayout查找
            f'//android.widget.LinearLayout[.//android.widget.TextView[@text="{wifi_name}"]]',
            f'//android.widget.LinearLayout[.//android.widget.TextView[contains(@text, "{wifi_name}")]]',
            # 通过RelativeLayout查找
            f'//android.widget.RelativeLayout[.//android.widget.TextView[@text="{wifi_name}"]]',
            f'//android.widget.RelativeLayout[.//android.widget.TextView[contains(@text, "{wifi_name}")]]',
            # 通过FrameLayout查找
            f'//android.widget.FrameLayout[.//android.widget.TextView[@text="{wifi_name}"]]',
            f'//android.widget.FrameLayout[.//android.widget.TextView[contains(@text, "{wifi_name}")]]',
            # 部分匹配（作为最后手段）
            f'//android.widget.TextView[contains(@text, "{wifi_name.split("_")[0] if "_" in wifi_name else wifi_name}")]',
        ]
        
        wifi_found = False
        max_scrolls = 15  # 增加滚动次数
        
        # 首先尝试不滚动直接查找
        force_print("🔍 首先尝试直接查找WiFi（不滚动）...")
        for selector in wifi_selectors:
            try:
                elements = driver.find_elements(AppiumBy.XPATH, selector)
                for elem in elements:
                    try:
                        if elem.is_displayed():
                            text = elem.text
                            force_print(f"🔍 找到元素，文本: {text}")
                            # 验证是否匹配目标WiFi
                            if wifi_name in text or text == wifi_name:
                                # 尝试点击元素本身
                                try:
                                    elem.click()
                                    force_print(f"✅ 直接找到并点击WiFi: {wifi_name}")
                                    wifi_found = True
                                    break
                                except:
                                    # 如果元素不可点击，尝试点击父容器
                                    try:
                                        parent = elem.find_element(AppiumBy.XPATH, './..')
                                        parent.click()
                                        force_print(f"✅ 通过父容器点击WiFi: {wifi_name}")
                                        wifi_found = True
                                        break
                                    except:
                                        continue
                    except:
                        continue
                if wifi_found:
                    break
            except Exception as e:
                force_print(f"⚠️ 选择器失败: {str(e)[:100]}")
                continue
        
        # 如果直接查找失败，尝试滚动查找
        if not wifi_found:
            force_print("🔍 直接查找失败，开始滚动查找...")
            for scroll_attempt in range(max_scrolls):
                force_print(f"🔍 第{scroll_attempt + 1}/{max_scrolls}次滚动寻找WiFi...")
                
                # 每次滚动后尝试所有选择器
                for selector in wifi_selectors:
                    try:
                        elements = driver.find_elements(AppiumBy.XPATH, selector)
                        for elem in elements:
                            try:
                                if elem.is_displayed():
                                    text = elem.text
                                    # 验证是否匹配目标WiFi
                                    if wifi_name in text or text == wifi_name:
                                        try:
                                            elem.click()
                                            force_print(f"✅ 找到并点击WiFi: {wifi_name} (文本: {text})")
                                            wifi_found = True
                                            break
                                        except:
                                            # 尝试点击父容器
                                            try:
                                                parent = elem.find_element(AppiumBy.XPATH, './..')
                                                parent.click()
                                                force_print(f"✅ 通过父容器点击WiFi: {wifi_name}")
                                                wifi_found = True
                                                break
                                            except:
                                                continue
                            except:
                                continue
                        if wifi_found:
                            break
                    except:
                        continue
                
                if wifi_found:
                    break
                
                # 向上滑动（改进滑动方法，参考蓝牙配网）
                try:
                    # 方法1: 使用swipe
                    size = driver.get_window_size()
                    start_x = size['width'] // 2
                    start_y = int(size['height'] * 0.7)
                    end_y = int(size['height'] * 0.3)
                    driver.swipe(start_x, start_y, start_x, end_y, 500)
                    time.sleep(1.5)
                except Exception as swipe_err:
                    try:
                        # 方法2: 使用scroll
                        driver.execute_script("mobile: scroll", {"direction": "up"})
                        time.sleep(1.5)
                    except:
                        try:
                            # 方法3: 使用flick
                            size = driver.get_window_size()
                            start_x = size['width'] // 2
                            start_y = int(size['height'] * 0.7)
                            end_y = int(size['height'] * 0.3)
                            driver.flick(start_x, start_y, start_x, end_y)
                            time.sleep(1.5)
                        except:
                            force_print("⚠️ 所有滑动方法都失败，继续尝试")
                            time.sleep(1)
        
        if not wifi_found:
            force_print(f"❌ 未找到WiFi: {wifi_name}")
            # 打印当前页面所有可见的WiFi名称用于调试
            try:
                force_print("🔍 当前页面可见的WiFi列表（用于调试）:")
                all_wifi_texts = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView')
                visible_wifis = []
                for text_elem in all_wifi_texts:
                    try:
                        if text_elem.is_displayed():
                            text = text_elem.text
                            if text and len(text) > 0 and text not in visible_wifis:
                                visible_wifis.append(text)
                    except:
                        continue
                for wifi in visible_wifis[:20]:  # 只显示前20个
                    force_print(f"  - {wifi}")
            except Exception as e:
                force_print(f"⚠️ 无法获取WiFi列表: {e}")
            # 尝试截图以便调试
            try:
                take_screenshot(driver, "unknown", wifi_name, "wifi_not_found")
            except:
                pass
            return False
        
        # 检测是否是 OnePlus 设备
        device_name = driver.capabilities.get('deviceName', '').lower()
        is_oneplus = 'oneplus' in device_name or '1+' in device_name or 'oplus' in device_name
        
        # 辅助函数：精确匹配 Set Up Wi-Fi 文本
        def _check_set_up_wifi_text(drv):
            try:
                el = drv.find_element(AppiumBy.XPATH, '//android.widget.TextView[@text="Set Up Wi-Fi"]')
                return el.is_displayed()
            except:
                return False
        
        # OnePlus 设备需要额外等待和操作
        if is_oneplus:
            force_print("📱 检测到 OnePlus 设备，等待 WiFi 连接页面加载...")
            time.sleep(5)  # OnePlus 需要更长的等待时间
            
            # 尝试点击"连接"或"确定"按钮（OnePlus 系统 WiFi 页面）
            connect_selectors = [
                '//android.widget.Button[@text="连接"]',
                '//android.widget.Button[@text="Connect"]',
                '//android.widget.Button[contains(@text,"连接")]',
                '//android.widget.Button[contains(@text,"Connect")]',
                '//android.widget.Button[@resource-id="android:id/button1"]',
                '//android.widget.Button[@resource-id="android:id/button2"]',
            ]
            
            for selector in connect_selectors:
                try:
                    connect_btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                    )
                    if connect_btn.is_displayed():
                        connect_btn.click()
                        force_print(f"✅ 点击连接按钮成功: {selector}")
                        time.sleep(3)
                        break
                except:
                    continue
        else:
            time.sleep(3)
        
        # 先判断是否已回到APP的WiFi设置页（参考蓝牙配网）
        try:
            app_wifi_indicators = [
                '//android.widget.TextView[@text="Set Up Wi-Fi"]',
                '//android.view.View[@content-desc="password"]',
                '//android.widget.EditText[@text="••••••••••"]'
            ]
            in_app_wifi = False
            for indicator in app_wifi_indicators:
                try:
                    el = driver.find_element(AppiumBy.XPATH, indicator)
                    if el.is_displayed():
                        in_app_wifi = True
                        break
                except:
                    continue
            if in_app_wifi:
                force_print("✅ 已在APP的WiFi设置页")
            else:
                force_print("⚠️ 仍在系统WiFi页面，准备通过后台切换返回到APP")
        except:
            in_app_wifi = False

        # 返回WiFi设置页面：优先使用后台切换APP，如果未检测到WiFi页面则循环点击左上角返回按钮
        if not in_app_wifi:
            force_print("🔙 通过后台切换返回到APP的Set up Wi-Fi页面...")
            app_package = driver.capabilities.get('appPackage')
            
            # 方法1: 优先使用 activate_app 切换到APP
            if app_package:
                try:
                    force_print(f"📱 激活APP: {app_package}")
                    driver.activate_app(app_package)
                    time.sleep(3)  # 等待APP完全激活
                    force_print("✅ 通过后台切换激活APP成功")
                except Exception as e:
                    force_print(f"⚠️ activate_app 失败: {e}")
            
            # 验证是否已回到APP的WiFi设置页
            if wait_for_wifi_setup_page(driver, timeout=6, app_package=app_package):
                force_print("✅ 通过后台切换成功返回到APP的Set up Wi-Fi页面")
                in_app_wifi = True
            else:
                # 方法2: 如果后台切换后未检测到WiFi设置页，最多点击2次左上角返回按钮，每次后检测
                force_print("⚠️ 后台切换后未检测到WiFi设置页，尝试点击左上角返回按钮（最多2次）...")
                back_selectors = [
                    '//android.widget.ImageButton[@content-desc="Navigate up"]',
                    '//android.widget.ImageButton[@content-desc="Back"]',
                    '//android.widget.ImageButton[contains(@content-desc,"返回")]',
                    '//android.view.View[@content-desc="Navigate up"]',
                    '//android.widget.Button[contains(@text,"Back")]'
                ]
                
                for attempt in range(2):
                    force_print(f"🔄 第 {attempt + 1}/2 次尝试返回...")
                    clicked_back = False
                    for selector in back_selectors:
                        try:
                            back_btn = WebDriverWait(driver, 2).until(
                                EC.presence_of_element_located((AppiumBy.XPATH, selector))
                            )
                            if back_btn.is_displayed():
                                back_btn.click()
                                force_print(f"↩️ 点击左上角返回按钮成功 ({selector})")
                                time.sleep(2)
                                clicked_back = True
                                break
                        except:
                            continue
                    if not clicked_back:
                        try:
                            driver.press_keycode(4)
                            force_print("↩️ 使用物理返回键")
                            time.sleep(2)
                            clicked_back = True
                        except Exception as key_err:
                            force_print(f"⚠️ 物理返回键失败: {key_err}")
                    
                    # 检测是否已回到Set up Wi-Fi页面（包含精确匹配）
                    if wait_for_wifi_setup_page(driver, timeout=4, app_package=app_package) or _check_set_up_wifi_text(driver):
                        force_print("✅ 已成功返回到APP的Set up Wi-Fi页面")
                        in_app_wifi = True
                        break
                    else:
                        force_print("⚠️ 返回后仍未检测到WiFi设置页，继续尝试...")
                
                # 保留原有更全面的返回逻辑作为兜底（OnePlus 设备可多尝试）
                if not in_app_wifi:
                    force_print("⚠️ 前两次返回未成功，继续使用扩展返回尝试...")
                    max_back_attempts = 8 if is_oneplus else 5
                    for attempt in range(max_back_attempts):
                        force_print(f"🔄 扩展尝试返回 {attempt + 1}/{max_back_attempts} ...")
                        clicked_back = False
                        for selector in back_selectors:
                            try:
                                back_btn = WebDriverWait(driver, 2).until(
                                    EC.presence_of_element_located((AppiumBy.XPATH, selector))
                                )
                                if back_btn.is_displayed():
                                    back_btn.click()
                                    force_print(f"↩️ 点击左上角返回按钮成功 ({selector})")
                                    time.sleep(2)
                                    clicked_back = True
                                    break
                            except:
                                continue
                        if not clicked_back:
                            try:
                                driver.press_keycode(4)
                                force_print("↩️ 使用物理返回键")
                                time.sleep(2)
                                clicked_back = True
                            except Exception as key_err:
                                force_print(f"⚠️ 物理返回键失败: {key_err}")
                        if clicked_back:
                            wait_timeout = 8 if is_oneplus else 5
                            if wait_for_wifi_setup_page(driver, timeout=wait_timeout, app_package=app_package) or _check_set_up_wifi_text(driver):
                                force_print("✅ 已成功返回到APP的Set up Wi-Fi页面")
                                in_app_wifi = True
                                break
                            else:
                                force_print("⚠️ 返回后仍未检测到WiFi设置页，继续尝试...")
                        else:
                            force_print("⚠️ 本次尝试未找到可点击的返回按钮")
                
                # 如果所有尝试都失败
                if not in_app_wifi:
                    force_print("❌ 多次尝试后仍无法返回到APP的Set up Wi-Fi页面")
        
        # 如果检测到 WiFi 设置页面，但不确定是否完全加载，等待一下
        if in_app_wifi:
            force_print("⏳ 等待 WiFi 设置页面完全加载...")
            time.sleep(3)  # 给页面更多时间加载
            # 再次确认是否在 WiFi 设置页面
            if not wait_for_wifi_setup_page(driver, timeout=3, app_package=app_package):
                force_print("⚠️ 页面状态不稳定，尝试再次返回...")
                try:
                    driver.press_keycode(4)  # 返回键
                    time.sleep(2)
                    driver.press_keycode(4)  # 再次返回
                    time.sleep(2)
                    if wait_for_wifi_setup_page(driver, timeout=5, app_package=app_package):
                        force_print("✅ 重新返回后确认在 WiFi 设置页面")
                        in_app_wifi = True
                    else:
                        force_print("⚠️ 重新返回后仍未在 WiFi 设置页面")
                        in_app_wifi = False
                except:
                    pass
        
        # 输入密码（参考蓝牙配网的实现）
        force_print("🔍 定位密码输入框...")

        # 多种密码输入框选择器（参考蓝牙配网）
        password_selectors = [
            '//android.view.View[@content-desc="password"]/preceding-sibling::android.widget.EditText',
            "//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.widget.EditText",
            '//android.widget.EditText[@text="••••••••••"]/android.view.View[2]',
            '//android.widget.EditText[@text="••••••••••"]',
            "//android.widget.EditText[2]",
            "//android.widget.EditText[1]",
            "//android.widget.EditText",
            "//android.widget.EditText[@hint='Password']",
            "//android.widget.EditText[@hint='密码']",
            "//android.widget.EditText[@hint='password']"
        ]

        password_field = None
        # OnePlus 设备需要更长的等待时间
        wait_timeout = 5 if is_oneplus else 3
        for i, selector in enumerate(password_selectors):
            try:
                force_print(f"🔍 尝试密码选择器 {i + 1}: {selector}")
                password_field = WebDriverWait(driver, wait_timeout).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                force_print(f"✅ 找到密码输入框，使用选择器 {i + 1}")
                break
            except Exception as e:
                force_print(f"⚠️ 密码选择器 {i + 1} 失败: {e}")
                continue

        if password_field is None:
            force_print("❌ 未找到密码输入框")
            # 如果检测到 WiFi 设置页面但找不到密码框，尝试再次激活 APP(new)
            if in_app_wifi:
                force_print("⚠️ 检测到 WiFi 设置页面但找不到密码框，尝试再次激活 APP(new)...")
                try:
                    app_package = driver.capabilities.get('appPackage')
                    if app_package:
                        driver.activate_app(app_package)
                        time.sleep(3)
                        # 再次尝试查找密码框
                        for i, selector in enumerate(password_selectors[:5]):  # 只尝试前5个选择器
                            try:
                                password_field = WebDriverWait(driver, 3).until(
                                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                                )
                                force_print(f"✅ 重新激活后找到密码输入框，使用选择器 {i + 1}")
                                break
                            except:
                                continue
                except Exception as e:
                    force_print(f"⚠️ 重新激活 APP(new) 失败: {e}")
            
            if password_field is None:
                # 尝试截图以便调试
                try:
                    take_screenshot(driver, "unknown", wifi_name, "password_field_not_found")
                except:
                    pass
                return False

        # 清除密码框中的现有内容（参考蓝牙配网）
        force_print("🧹 清除密码框中的现有内容...")
        try:
            password_field.clear()
            time.sleep(0.5)
        except:
            force_print("⚠️ 清除密码失败，尝试其他方法...")
            try:
                password_field.click()
                time.sleep(0.3)
                # 连续删除键清空
                for _ in range(20):
                    driver.press_keycode(67)
                time.sleep(0.5)
            except:
                force_print("⚠️ 备用清除方法也失败")

        # 输入WiFi密码
        force_print(f"🔑 输入WiFi密码: {wifi_password}")
        try:
            password_field.send_keys(wifi_password)
            time.sleep(1)
            force_print("✅ 密码输入完成")
        except Exception as e:
            force_print(f"❌ 密码输入失败: {e}")
            return False

        # 步骤1: 清除密码后点击next按钮，进入配网引导页
        force_print("✅ 步骤1: 点击next按钮，进入配网引导页...")
        try:
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
            )
            next_button.click()
            force_print("✅ 已点击 Next 按钮，等待进入配网引导页...")
            time.sleep(3)  # 等待页面跳转到配网引导页
            force_print("✅ WiFi设置完成，已进入配网引导页")
            return True
        except Exception as e:
            force_print(f"❌ 点击Next按钮失败: {e}")
            return False
        
    except Exception as e:
        force_print(f"❌ 设置WiFi失败: {e}")
        take_screenshot(driver, "unknown", wifi_name, "wifi_setup_failed")
        return False

def click_guide_next(driver):
    """步骤2: 配网引导页点击next按钮，进入connect robot hotspot页面"""
    force_print("📖 步骤2: 配网引导页点击Next按钮，进入connect robot hotspot页面...")
    try:
        # 等待页面稳定加载
        time.sleep(2)
        
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.Button'))
        )
        next_button.click()
        force_print("✅ 已点击配网引导页Next按钮，等待进入connect robot hotspot页面...")
        time.sleep(3)  # 等待页面跳转到connect robot hotspot页面
        force_print("✅ 已进入connect robot hotspot页面")
        return True
    except Exception as e:
        # 检查是否是 UiAutomator2 崩溃
        if _is_driver_crashed_error(e):
            force_print(f"❌ UiAutomator2 崩溃: {e}")
            raise RuntimeError("UiAutomator2_CRASHED") from e
        force_print(f"❌ 点击配网引导页Next按钮失败: {e}")
        return False

def connect_device_hotspot(driver, device_config=None):
    """
    步骤3: connect robot hotspot页面处理
    流程：
    1. 点击按钮：//android.widget.Button，跳出弹框
    2. 点击confirm：//android.widget.TextView[@text="Confirm"]
    3. 跳出系统弹框，点击：//android.widget.Button[@resource-id="android:id/button1"]
    4. 进入配网进程
    """
    force_print("📡 步骤3: 处理connect robot hotspot页面...")
    try:
        # 首先确保会话有效
        driver, is_new = ensure_valid_session(driver, device_config)
        if driver is None:
            return False
        if is_new:
            time.sleep(3)  # 重建后等待页面加载
        
        # 等待页面稳定加载
        force_print("⏳ 等待connect robot hotspot页面加载...")
        time.sleep(3)
        
        # 步骤3-1: 点击按钮，跳出弹框
        force_print("🔍 步骤3-1: 点击按钮，跳出弹框...")
        try:
            button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.Button'))
            )
            button.click()
            force_print("✅ 已点击按钮，等待弹框出现...")
            time.sleep(3)  # 等待弹框出现
        except Exception as e:
            force_print(f"❌ 点击按钮失败: {e}")
            take_screenshot(driver, "unknown", "unknown", "connect_button_click_fail")
            return False
        
        # 步骤3-2: 点击confirm按钮
        force_print("🔍 步骤3-2: 点击Confirm按钮...")
        try:
            confirm_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.TextView[@text="Confirm"]'))
            )
            if confirm_button and confirm_button.is_displayed():
                confirm_button.click()
                force_print("✅ 已点击Confirm按钮，等待页面跳转...")
                time.sleep(3)  # 等待页面跳转
            else:
                force_print("❌ 未找到 Confirm 按钮")
                take_screenshot(driver, "unknown", "unknown", "confirm_button_not_found")
                return False
        except Exception as e:
            force_print(f"❌ 点击Confirm按钮失败: {e}")
            take_screenshot(driver, "unknown", "unknown", "confirm_button_click_fail")
            return False
        
        # 检测是否是 OnePlus 11 设备（提前检测，用于决定后续流程）
        device_name = ""
        try:
            device_name = (driver.capabilities.get("deviceName") or driver.capabilities.get("device_name") or "")
        except Exception:
            device_name = ""
        is_oneplus = "oneplus" in str(device_name).lower() or "1+11" in str(device_name).lower() or "oplus" in str(device_name).lower()
        
        # 额外检测：通过当前包名判断是否已进入系统 WiFi 设置页面（OnePlus 11 的特征）
        try:
            current_package = driver.current_package
            if current_package and "wirelesssettings" in current_package.lower():
                force_print(f"📱 检测到系统 WiFi 设置页面（包名: {current_package}），按 OnePlus 11 热点列表流程处理...")
                is_oneplus = True
        except Exception:
            pass

        if is_oneplus:
            force_print(f"📱 检测到 OnePlus 11/OPLUS 机型（deviceName={device_name}），按 OnePlus 11 热点列表流程处理...")
            # 步骤3-3: 点击热点列表中的特定项进入配网页面
            force_print("🔍 步骤3-3: 点击热点列表项进入配网页面...")
            try:
                # 等待 WLAN 页面完全加载
                force_print("⏳ 等待 WLAN 页面加载...")
                time.sleep(3)
                
                # 优先使用精确的XPath定位热点列表项
                hotspot_item_xpath = '//androidx.recyclerview.widget.RecyclerView[@resource-id="com.oplus.wirelesssettings:id/recycler_view"]/android.widget.LinearLayout[3]/android.widget.FrameLayout'
                
                try:
                    hotspot_item = WebDriverWait(driver, 15).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, hotspot_item_xpath))
                    )
                    if hotspot_item and hotspot_item.is_displayed():
                        hotspot_item.click()
                        force_print("✅ OnePlus 11：已点击热点列表第3项，等待进入配网页面...")
                        time.sleep(3)  # 等待进入配网页面
                        return True
                    else:
                        force_print("❌ 未找到热点列表项（元素不可见）")
                        take_screenshot(driver, "unknown", "unknown", "hotspot_item_not_visible")
                except Exception as e:
                    force_print(f"⚠️ 精确XPath失败: {e}，尝试备用方案...")
                
                # 备用方案1: 尝试点击RecyclerView中的第3个LinearLayout
                try:
                    backup_xpath = '//androidx.recyclerview.widget.RecyclerView[@resource-id="com.oplus.wirelesssettings:id/recycler_view"]/android.widget.LinearLayout[3]'
                    force_print(f"🔍 尝试备用方案1: {backup_xpath}")
                    backup_item = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, backup_xpath))
                    )
                    if backup_item and backup_item.is_displayed():
                        backup_item.click()
                        force_print("✅ 使用备用方案1点击热点列表项成功")
                        time.sleep(3)
                        return True
                except Exception as backup_err:
                    force_print(f"⚠️ 备用方案1也失败: {backup_err}")
                
                # 备用方案2: 尝试通过文本查找热点（如果热点名称已知）
                try:
                    # 尝试查找包含 "robot" 或设备相关的热点名称
                    hotspot_text_xpaths = [
                        '//android.widget.TextView[contains(@text,"robot")]',
                        '//android.widget.TextView[contains(@text,"Robot")]',
                        '//android.widget.TextView[contains(@text,"ROBOT")]',
                    ]
                    for text_xpath in hotspot_text_xpaths:
                        try:
                            text_elem = driver.find_element(AppiumBy.XPATH, text_xpath)
                            if text_elem.is_displayed():
                                # 尝试点击其父容器
                                parent = text_elem.find_element(AppiumBy.XPATH, './ancestor::android.widget.LinearLayout[1]')
                                if parent:
                                    parent.click()
                                    force_print(f"✅ 通过文本定位点击热点成功: {text_xpath}")
                                    time.sleep(3)
                                    return True
                        except:
                            continue
                except Exception as backup2_err:
                    force_print(f"⚠️ 备用方案2也失败: {backup2_err}")
                
                # 所有方案都失败
                force_print("❌ OnePlus 11：所有热点点击方案都失败")
                take_screenshot(driver, "unknown", "unknown", "hotspot_item_click_failed")
                return False
                
            except Exception as e:
                force_print(f"❌ OnePlus 11：点击热点列表项异常: {e}")
                take_screenshot(driver, "unknown", "unknown", "hotspot_item_exception")
                return False

        # 非 OnePlus 11：点击系统弹框的连接按钮，进入配网进程
        force_print("🔍 步骤3-3: 点击系统弹框的连接按钮，进入配网进程...")
        try:
            connect_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.Button[@resource-id="android:id/button1"]'))
            )
            if connect_button and connect_button.is_displayed():
                connect_button.click()
                force_print("✅ 已点击系统弹框连接按钮，进入配网进程...")
                time.sleep(3)  # 等待进入配网进程页面
                return True
            else:
                force_print("❌ 未找到系统弹框连接按钮")
                take_screenshot(driver, "unknown", "unknown", "system_connect_button_not_found")
                return False
        except Exception as e:
            force_print(f"❌ 点击系统弹框连接按钮失败: {e}")
            take_screenshot(driver, "unknown", "unknown", "system_connect_button_click_fail")
            return False
        
    except Exception as e:
        # 检查是否是会话失效
        if _is_session_terminated_error(e) and device_config:
            force_print(f"⚠️ 连接设备热点时会话失效: {e}")
            driver, _ = ensure_valid_session(driver, device_config)
            if driver is None:
                return False
            # 重试一次
            force_print("🔄 会话重建后重试连接设备热点...")
            return connect_device_hotspot(driver, device_config)
        
        force_print(f"❌ 连接设备热点失败: {e}")
        # 尝试截图以便调试
        try:
            take_screenshot(driver, "unknown", "unknown", "connect_hotspot_failed")
        except:
            pass
        return False

def _is_home_after_pairing(driver):
    """
    通过页面元素判断是否已回到首页/第一阶段配网完成
    经验判定：
    - 存在 add 按钮（首页强特征）
    - 或存在 Home tab + AquaSense/设备信息
    """
    try:
        # 先用"首页强特征"判定：add 按钮出现，基本可认为已回首页
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

        # 其次再结合 Home tab + AquaSense/设备信息（用于部分首页没有 add 的场景）
        home_el = driver.find_elements(AppiumBy.XPATH, '//android.view.View[@content-desc="Home"]')
        if not any(e.is_displayed() for e in home_el):
            return False

        # 1) AquaSense 文案
        aqua_els = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView[contains(@text,"AquaSense")]')
        if any(e.is_displayed() for e in aqua_els):
            return True

        # 2) Sora/设备信息（作为备选）
        device_indicators = [
            '//android.widget.TextView[contains(@text,"Sora")]',
            '//android.widget.TextView[contains(@text,"设备")]',
            '//android.widget.TextView[contains(@text,"robot")]'
        ]
        for xp in device_indicators:
            try:
                els = driver.find_elements(AppiumBy.XPATH, xp)
                if any(e.is_displayed() for e in els):
                    return True
            except Exception:
                continue
    except Exception:
        return False

    return False


def handle_post_pairing_success_flow(driver, timeout=35):
    """
    配网成功后停留在当前页，出现 Next 按钮：
      1) 点击 Next: //android.widget.Button
      2) 出现绑定弹框/页面，点击"已绑定"/"Already paired"
      3) 跳转首页，出现 AquaSense + Home
    """
    # 1) 点击成功页 Next
    try:
        next_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
        )
        next_btn.click()
        force_print("✅ 成功页：已点击 Next")
        time.sleep(1.2)
    except Exception as e:
        force_print(f"❌ 成功页：未能点击 Next: {e}")
        return False

    # 2) 绑定确认：弹框中的"Already paired"/"已绑定"按钮
    bound_text_xpaths = [
        # 英文
        '//android.widget.Button[contains(@text,"Already paired")]',
        '//android.widget.TextView[contains(@text,"Already paired")]/ancestor::android.widget.Button[1]',
        '//android.widget.TextView[contains(@text,"Already")]/ancestor::android.widget.Button[1]',
        # 中文（兼容其他语言包）
        '//android.widget.Button[contains(@text,"已绑定")]',
        '//android.widget.TextView[contains(@text,"已绑定")]/ancestor::android.widget.Button[1]',
        '//android.widget.Button[contains(@text,"已配对")]',
        '//android.widget.TextView[contains(@text,"已配对")]/ancestor::android.widget.Button[1]',
        # Confirm 按钮（备用）
        '//android.widget.Button[@text="Confirm"]',
        '//android.widget.TextView[@text="Confirm"]',
    ]

    def _click_leftmost_button_fallback(wait_seconds: int = 12):
        """兜底：弹框按钮文本可能取不到，取可见按钮中最左侧一个点击（通常是 Already paired）"""
        end = time.time() + wait_seconds
        while time.time() < end:
            try:
                btns = driver.find_elements(AppiumBy.XPATH, "//android.widget.Button")
                visible = []
                for b in btns:
                    try:
                        if b.is_displayed():
                            visible.append(b)
                    except Exception:
                        continue
                if len(visible) >= 1:
                    # 取最左侧（center x 最小）
                    def _center_x(el):
                        try:
                            r = el.rect
                            return float(r.get("x", 0)) + float(r.get("width", 0)) / 2.0
                        except Exception:
                            return 999999.0

                    visible.sort(key=_center_x)
                    visible[0].click()
                    force_print("✅ 绑定弹框：已点击左侧按钮(兜底：最左 Button)")
                    return True
            except Exception:
                pass
            time.sleep(0.6)
        return False

    try:
        clicked = False

        # 先等弹框/按钮出现（避免 Next 后立刻找不到）
        time.sleep(1.2)

        for xp in bound_text_xpaths:
            try:
                el = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp)))
                el.click()
                force_print(f"✅ 绑定弹框：已点击确认按钮 ({xp})")
                clicked = True
                time.sleep(1.5)
                break
            except Exception:
                continue

        if not clicked:
            # 强兜底：使用绝对 XPath（多变体）
            absolute_candidates = [
                "(//android.widget.Button)[1]",
                "(//android.widget.Button)[2]",
            ]
            for xp in absolute_candidates:
                try:
                    el = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp)))
                    el.click()
                    force_print(f"✅ 绑定弹框：已点击确认按钮(兜底 XPath) {xp}")
                    clicked = True
                    time.sleep(1.5)
                    break
                except Exception:
                    continue

        if not clicked:
            # 最终兜底：点最左侧按钮
            if _click_leftmost_button_fallback(wait_seconds=12):
                clicked = True
                time.sleep(1.5)

        if not clicked:
            force_print("❌ 绑定弹框：未找到可点击的'Already paired/已绑定'按钮")
            return False
    except Exception as e:
        force_print(f"❌ 绑定弹框：未能点击确认按钮: {e}")
        return False

    # 3) 校验回到首页
    home_xpath = '//android.view.View[@content-desc="Home"]'
    aquasense_xpath = '//android.widget.TextView[contains(@text,"AquaSense")]'
    start = time.time()
    while time.time() - start < timeout:
        try:
            home_el = driver.find_element(AppiumBy.XPATH, home_xpath)
            aqua_el = driver.find_element(AppiumBy.XPATH, aquasense_xpath)
            if home_el.is_displayed() and aqua_el.is_displayed():
                force_print("✅ 已回到首页（检测到 AquaSense + Home）")
                return True
        except Exception:
            pass
        # 也检查是否已经有 add 按钮（更宽松的判定）
        if _is_home_after_pairing(driver):
            force_print("✅ 已回到首页（检测到 add 按钮或设备信息）")
            return True
        time.sleep(1)

    force_print("❌ 未在超时内确认回到首页")
    return False


def wait_for_pairing_result(driver, timeout=180):
    """
    等待配网结果（增强版，避免误判超时）
    返回: "success", "failed", "timeout", "success_need_next"
    """
    force_print("⏳ 步骤7: 等待配网结果...")
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < timeout:
        try:
            check_count += 1
            force_print(f"🔍 第{check_count}次检查配网状态...")
            
            # 关键优化：优先用页面信息判断是否已回到首页（第一阶段配网完成）
            if _is_home_after_pairing(driver):
                force_print("✅ 页面判定：已回到首页（Home + AquaSense/设备信息），认为配网完成")
                return "success"
            
            # 检查是否在配网进程页面
            try:
                pairing_text = driver.find_element(AppiumBy.XPATH, '//android.widget.TextView[@text="Pairing with your device"]')
                if pairing_text.is_displayed():
                    force_print("🔄 配网进行中...")
                    time.sleep(5)
                    continue
            except:
                pass
            
            # 检查是否配对失败
            try:
                failure_indicators = [
                    '//android.widget.TextView[@text="Data transmitting failed."]',
                    '//android.widget.TextView[contains(@text,"failed")]',
                    '//android.widget.TextView[contains(@text,"失败")]',
                    '//android.widget.TextView[contains(@text,"error")]'
                ]
                
                for indicator in failure_indicators:
                    try:
                        error_text = driver.find_element(AppiumBy.XPATH, indicator)
                        if error_text.is_displayed():
                            force_print(f"❌ 配网失败: {indicator}")
                            return "failed"
                    except:
                        continue
            except Exception as e:
                force_print(f"🔍 检查失败状态时出错: {e}")
            
            # 检查是否配对成功（首页出现新设备）- 多个指示器
            try:
                success_indicators = [
                    '//android.widget.ImageView[@content-desc="robot"]',
                    '//android.widget.TextView[contains(@text,"robot")]',
                    '//android.widget.TextView[contains(@text,"设备")]',
                    '//android.widget.TextView[contains(@text,"Sora")]',
                    '//android.widget.TextView[contains(@text,"AquaSense")]',
                ]
                
                for indicator in success_indicators:
                    try:
                        new_device = driver.find_element(AppiumBy.XPATH, indicator)
                        if new_device.is_displayed():
                            force_print(f"✅ 配网成功！设备已添加到首页: {indicator}")
                            return "success"
                    except:
                        continue
            except Exception as e:
                force_print(f"🔍 检查成功状态时出错: {e}")
            
            # 新流程：配网成功后不直接回首页，而是停留在成功页，出现 Next 按钮
            # 为避免误判，尽量校验按钮文本包含 Next/下一步
            try:
                btns = driver.find_elements(AppiumBy.XPATH, "//android.widget.Button")
                for b in btns:
                    try:
                        if not b.is_displayed():
                            continue
                        t = (b.text or "").strip()
                        if not t:
                            try:
                                t = (b.get_attribute("text") or b.get_attribute("content-desc") or "").strip()
                            except Exception:
                                t = ""
                        if any(k.lower() in (t or "").lower() for k in ["next", "下一步", "下一页", "继续"]):
                            force_print(f"✅ 检测到成功页 Next 按钮（{t}），需要后续点击完成收尾")
                            return "success_need_next"
                    except Exception:
                        continue
                # 兜底：有些机型 Next 按钮可能无文本，但会停留在成功页且首页(Home)不出现
                if any(b.is_displayed() for b in btns) and not _is_home_after_pairing(driver):
                    force_print("✅ 检测到页面存在可见 Button（可能是成功页 Next），进入收尾流程判定")
                    return "success_need_next"
            except Exception:
                pass
            
            time.sleep(3)
            
        except Exception as e:
            force_print(f"🔍 检查配网状态异常: {e}")
            time.sleep(3)
    
    force_print("⏰ 配网超时（3分钟）")
    return "timeout"

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
            
            # 步骤6: 点击配网引导页Next按钮
            try:
                if not click_guide_next(driver):
                    return "error", "点击配网引导页Next按钮失败", None
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
            wait_after_step("配网引导页")
            
            # 步骤7: 连接设备热点
            if not connect_device_hotspot(driver, device_config):
                return "error", "连接设备热点失败", None
            wait_after_step("连接设备热点")
            
            # 步骤8: 等待配网结果
            result = wait_for_pairing_result(driver)
            
            # 新流程：成功页需要点击 Next -> 绑定弹框确认 -> 回到 Home（参考 Android-1+11.py）
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

def create_device_driver(device_config):
    """创建设备驱动"""
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
            force_print(f"❌ 所有 Appium URL 尝试失败，最后错误: {str(last_error)[:200]}")
        return None

    except Exception as e:
        force_print(f"❌ 创建设备驱动失败: {e}")
        return None

# ==================== 多设备测试 ====================

def finalize_results(total_tests, success_count, failure_count, detailed_results, test_config, interrupted=False):
    """汇总测试结果并生成报告（参考蓝牙配网的报告生成逻辑）"""
    force_print("\n" + "=" * 80)
    if interrupted:
        force_print("⚠️ 用户中断测试，已保存截至目前的测试数据")
    force_print("📊 测试结果汇总")
    force_print("=" * 80)
    force_print(f"总测试次数: {total_tests}")
    force_print(f"成功次数: {success_count}")
    force_print(f"失败次数: {failure_count}")
    if total_tests > 0:
        force_print(f"成功率: {success_count/total_tests*100:.1f}%")
    else:
        force_print("成功率: 0%")
    
    # 分设备/路由器详细汇总
    force_print("\n🔎 分设备/路由器明细：")
    has_data = False
    for device_name, device_data in detailed_results.items():
        routers = device_data.get("routers", {})
        valid_routers = {r: stats for r, stats in routers.items() if stats.get('success', 0) + stats.get('failure', 0) > 0}
        if not valid_routers:
            continue
        has_data = True
        force_print(f"\n📱 设备: {device_name}")
        for router_name, stats in valid_routers.items():
            force_print(f"  📶 路由器: {router_name}  成功: {stats.get('success', 0)}  失败: {stats.get('failure', 0)}")
            failed_rounds = [r for r in stats.get('rounds', []) if r.get('result') != 'success']
            if failed_rounds:
                for fr in failed_rounds:
                    timestamp = fr.get('timestamp', '未知时间')
                    force_print(f"    ❌ 轮次#{fr.get('round', '?')} 结果: {fr.get('result', '?')}  原因: {fr.get('message', '?')}  时间: {timestamp}")
            else:
                force_print("    ✅ 全部成功")
    
    if not has_data:
        force_print("⚠️ 没有可汇总的测试数据")
    
    # 生成Excel报告
    if has_data:
        try:
            import sys
            import os
            current_dir = str(SCRIPT_DIR)
            
            # 尝试从多个位置查找 excel_report_generator.py
            # 查找顺序：1. common 目录 2. 当前目录 3. 蓝牙配网目录（向后兼容）
            search_paths = [
                os.path.join(os.path.dirname(current_dir), "common", "excel_report_generator.py"),
                os.path.join(current_dir, "excel_report_generator.py"),
                os.path.join(os.path.dirname(current_dir), "2蓝牙配网", "excel_report_generator.py"),
                os.path.join(os.path.dirname(current_dir), "2蓝牙配网", "IOS", "excel_report_generator.py"),
            ]
            
            excel_gen_path = None
            for path in search_paths:
                if os.path.exists(path):
                    excel_gen_path = path
                    force_print(f"✅ 找到 excel_report_generator.py: {path}")
                    break
            
            if excel_gen_path and os.path.exists(excel_gen_path):
                sys.path.insert(0, os.path.dirname(excel_gen_path))
                from excel_report_generator import create_network_compatibility_report
                
                force_print("\n📊 生成Excel测试报告...")
                
                # 转换数据结构：将 rounds 从列表格式转换为字典格式
                # excel_report_generator 期望 rounds 是字典 {round_number: {result, message}}
                converted_results = {}
                for device_name, device_data in detailed_results.items():
                    converted_results[device_name] = {"routers": {}}
                    for router_name, router_data in device_data.get("routers", {}).items():
                        converted_results[device_name]["routers"][router_name] = {
                            "success": router_data.get("success", 0),
                            "failure": router_data.get("failure", 0),
                            "rounds": {}
                        }
                        # 将列表格式的 rounds 转换为字典格式
                        if "rounds" in router_data and isinstance(router_data["rounds"], list):
                            for round_item in router_data["rounds"]:
                                round_num = round_item.get("round")
                                if round_num:
                                    converted_results[device_name]["routers"][router_name]["rounds"][round_num] = {
                                        "result": round_item.get("result", ""),
                                        "message": round_item.get("message", "")
                                    }
                        elif "rounds" in router_data and isinstance(router_data["rounds"], dict):
                            # 如果已经是字典格式，直接复制
                            converted_results[device_name]["routers"][router_name]["rounds"] = router_data["rounds"]
                
                # 直接传入 RUN_DIR，报告将保存到 reports 目录
                excel_file = create_network_compatibility_report(
                    converted_results, 
                    platform="Android", 
                    network_method="1扫码配网",
                    output_dir=str(RUN_DIR) if RUN_DIR else None
                )
                force_print(f"✅ Excel报告已生成: {excel_file}")
            else:
                force_print(f"⚠️ 未找到 excel_report_generator.py，跳过Excel报告生成")
                force_print(f"   已搜索以下路径:")
                for path in search_paths:
                    force_print(f"     - {path}")
        except Exception as e:
            force_print(f"⚠️ Excel报告生成失败: {e}")
            import traceback
            force_print(f"详细错误: {traceback.format_exc()}")
    else:
        force_print("⚠️ 无测试数据，跳过Excel报告生成")

def run_multi_device_test():
    """运行多设备测试"""
    force_print("🚀 开始Android多设备/多路由器扫码配网测试")
    force_print("=" * 80)
    
    config = load_device_config()
    if not config:
        return
    
    device_configs = config['device_configs']
    wifi_configs = config['wifi_configs']
    test_config = config['test_config']
    
    force_print(f"📱 设备数量: {len(device_configs)}")
    force_print(f"📶 路由器数量: {len(wifi_configs)}")
    force_print(f"🔄 每个路由器测试次数: {test_config['loop_count_per_router']}")
    
    total_tests = 0
    success_count = 0
    failure_count = 0
    detailed_results = {}
    interrupted = False
    
    # 记录所有测试的设备列表，用于最后统一打开蓝牙
    tested_devices = []
    
    try:
        for device_name, device_config in device_configs.items():
            force_print(f"\n📱 设备: {device_config['description']}")
            force_print("=" * 60)
            
            # 测试前关闭当前设备的蓝牙
            device_udid = device_config.get('device_name', device_name)
            if disable_bluetooth(device_udid):
                tested_devices.append(device_udid)
            else:
                force_print(f"⚠️ 关闭蓝牙失败，但继续测试")
                # 即使关闭失败，也记录设备ID，以便最后尝试打开
                if device_udid not in tested_devices:
                    tested_devices.append(device_udid)
            
            detailed_results[device_name] = {'routers': {}}
            driver = create_device_driver(device_config)
            if not driver:
                force_print(f"❌ 设备 {device_name} 连接失败，跳过")
                # 即使连接失败，也确保设备ID已记录，以便最后打开蓝牙
                if device_udid not in tested_devices:
                    tested_devices.append(device_udid)
                continue
            
            try:
                for wifi_config in wifi_configs:
                    force_print(f"\n📶 路由器: {wifi_config['name']}")
                    force_print("-" * 40)
                    
                    if wifi_config['name'] not in detailed_results[device_name]['routers']:
                        detailed_results[device_name]['routers'][wifi_config['name']] = {
                            'success': 0,
                            'failure': 0,
                            'rounds': []
                        }
                    
                    for test_round in range(test_config['loop_count_per_router']):
                        force_print(f"\n🔄 第 {test_round + 1}/{test_config['loop_count_per_router']} 次测试")
                        
                        if test_round > 0:
                            force_print("🔄 重置应用准备下一次测试...")
                            success, new_driver = reset_app_to_home(driver, device_config=device_config)
                            if new_driver is not None:
                                driver = new_driver
                                force_print("🔄 更新 driver 引用（driver 已重建）")
                            time.sleep(3)
                        
                        result, message, new_driver = single_pairing_flow(
                            driver,
                            wifi_config['name'],
                            wifi_config['password'],
                            device_config=device_config  # 传递 device_config 以支持崩溃恢复
                        )
                        
                        # 如果 driver 被重建，更新 driver 引用
                        if new_driver is not None:
                            force_print("🔄 更新 driver 引用（driver 已重建）")
                            driver = new_driver
                        
                        total_tests += 1
                        test_timestamp = datetime.now().strftime("%H:%M:%S")
                        
                        round_record = {
                            'round': test_round + 1,
                            'result': result,
                            'message': message,
                            'timestamp': test_timestamp
                        }
                        
                        if result == "success":
                            success_count += 1
                            force_print(f"✅ 测试成功: {message}")
                            detailed_results[device_name]['routers'][wifi_config['name']]['success'] += 1
                        else:
                            failure_count += 1
                            force_print(f"❌ 测试失败: {message}")
                            detailed_results[device_name]['routers'][wifi_config['name']]['failure'] += 1
                        
                        detailed_results[device_name]['routers'][wifi_config['name']]['rounds'].append(round_record)
                        
                        # 更新全局测试数据
                        _global_test_data['total_tests'] = total_tests
                        _global_test_data['success_count'] = success_count
                        _global_test_data['failure_count'] = failure_count
                        _global_test_data['detailed_results'] = detailed_results
                        _global_test_data['test_config'] = test_config
                        
                        # 定期保存测试数据到文件
                        save_test_data_to_file()
                        
                        if test_round < test_config['loop_count_per_router'] - 1:
                            force_print("⏳ 等待10秒后进行下一次测试...")
                            time.sleep(10)
                    
                    if wifi_config != wifi_configs[-1]:
                        force_print("🔄 切换到下一个路由器，重置应用...")
                        reset_app_to_home(driver)
                        time.sleep(3)
            
            finally:
                try:
                    driver.quit()
                    force_print(f"✅ 设备 {device_name} 连接已关闭")
                except:
                    pass
    
    except KeyboardInterrupt:
        interrupted = True
        _global_test_data['interrupted'] = True
        force_print("\n⚠️ 用户中断测试，正在保存已完成的数据...")
    finally:
        # 所有设备测试完成后，统一打开蓝牙
        if tested_devices:
            force_print("\n📱 所有设备测试完成，统一打开蓝牙...")
            force_print("=" * 60)
            for device_udid in tested_devices:
                enable_bluetooth(device_udid)
            force_print("✅ 所有设备的蓝牙已打开")
        
        # 更新全局数据
        _global_test_data['total_tests'] = total_tests
        _global_test_data['success_count'] = success_count
        _global_test_data['failure_count'] = failure_count
        _global_test_data['detailed_results'] = detailed_results
        _global_test_data['interrupted'] = interrupted
        
        # 保存到文件
        save_test_data_to_file()
        
        # 生成报告
        finalize_results(total_tests, success_count, failure_count, detailed_results, test_config, interrupted)
        
        # 清理临时文件（如果测试正常完成）
        if not interrupted:
            cleanup_temp_file()

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

