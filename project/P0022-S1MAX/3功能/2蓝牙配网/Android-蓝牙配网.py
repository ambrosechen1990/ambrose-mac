#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多设备/多路由器蓝牙配网测试脚本
支持多设备并行测试，每个设备配对对应路由器测试3次
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

# 尝试导入report_utils，优先从common目录导入
try:
    from report_utils import init_run_env
except ImportError:
    # 如果report_utils不在当前路径，尝试从common目录导入
    import os
    common_path = str(SCRIPT_DIR.parent / "common")
    sys.path.insert(0, common_path)
    from report_utils import init_run_env

# ==================== 配置和日志设置 ====================

# 初始化本次运行的输出目录（共用一个结构，后续 iOS 脚本也可调用）
RUN_DIR, LOG_FILE, SCREENSHOT_DIR = init_run_env(prefix="2蓝牙配网-Android")

# 配置日志：统一写入 bluetooth_pairing.log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)

# 截图目录使用公用的 SCREENSHOT_DIR
screenshot_dir = str(SCREENSHOT_DIR)
if not os.path.exists(screenshot_dir):
    os.makedirs(screenshot_dir)
logger = logging.getLogger(__name__)

# 全局步骤等待时间（秒）
STEP_DELAY_SECONDS = 2

# 机器人热点触发所需的设备ID，可通过环境变量覆盖
ROBOT_DEVICE_ID = os.environ.get('ROBOT_DEVICE_ID', '20080411')

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
        # 生成截图文件名：日期时间-设备名称-路由器名称-步骤名称.png
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}-{device_name}-{wifi_name}-{step_name}.png"
        filepath = os.path.join(screenshot_dir, filename)
        
        # 截图
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
    # 避免重复执行
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
                # finalize_results 可能还未定义，只保存数据
                force_print("⚠️ finalize_results 函数未定义，仅保存数据")
        force_print("✅ 测试数据已保存")
    except Exception as e:
        force_print(f"❌ 紧急保存失败: {e}")
    
    # 只在信号处理中调用 sys.exit，不在 atexit 中调用
    if signum is not None:
        sys.exit(0)

# ==================== 设备配置加载 ====================

def load_device_config():
    """加载设备配置文件（优先从环境变量读取，然后从统一配置文件读取，最后从当前目录读取）"""
    import os
    # 优先从环境变量读取（用于 Web 管理页面传递的临时配置）
    env_config_file = os.environ.get('DEVICE_CONFIG_FILE')
    if env_config_file and os.path.exists(env_config_file):
        try:
            with open(env_config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                force_print(f"✅ 从环境变量配置文件加载: {env_config_file}")
                return config
        except Exception as e:
            force_print(f"⚠️ 加载环境变量配置文件失败: {e}，尝试其他方式")
    
    # 优先尝试从 common 目录读取统一配置文件
    common_config_path = str(SCRIPT_DIR.parent / 'common' / 'device_config.json')
    
    if os.path.exists(common_config_path):
        try:
            with open(common_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                force_print(f"✅ 从 common 目录加载配置文件: {common_config_path}")
                # 过滤出 Android 设备
                filtered_config = config.copy()
                filtered_config['device_configs'] = {
                    k: v for k, v in config.get('device_configs', {}).items()
                    if v.get('platform', 'android') == 'android'
                }
                return filtered_config
        except Exception as e:
            force_print(f"⚠️ 加载 common 配置文件失败: {e}，尝试其他方式")
    
    # 尝试从上一级目录的统一配置文件读取（向后兼容）
    unified_config_path = str(SCRIPT_DIR.parent / 'device_config.json')
    
    if os.path.exists(unified_config_path):
        try:
            with open(unified_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 过滤出 Android 设备
                filtered_config = config.copy()
                filtered_config['device_configs'] = {
                    k: v for k, v in config.get('device_configs', {}).items()
                    if v.get('platform', 'android') == 'android'
                }
                return filtered_config
        except Exception as e:
            force_print(f"⚠️ 加载统一配置文件失败: {e}，尝试从当前目录读取")
    
    # 如果统一配置文件不存在，从当前目录读取（向后兼容）
    try:
        with open('device_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config
    except Exception as e:
        force_print(f"❌ 加载配置文件失败: {e}")
        return None

# ==================== 工具函数 ====================

def get_adb_path():
    """获取 ADB 完整路径"""
    import os
    # 首先检查环境变量
    android_home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    
    # 如果环境变量未设置，尝试自动查找
    if not android_home:
        possible_paths = [
            os.path.expanduser('~/Library/Android/sdk'),
            os.path.expanduser('~/Android/Sdk'),
            os.path.join(os.path.expanduser('~'), 'Library', 'Android', 'sdk'),
            '/usr/local/share/android-sdk',
            '/opt/android-sdk',
        ]
        
        for path in possible_paths:
            adb_path = os.path.join(path, 'platform-tools', 'adb')
            if os.path.exists(adb_path):
                android_home = path
                break
    
    if android_home:
        adb_path = os.path.join(android_home, 'platform-tools', 'adb')
        if os.path.exists(adb_path):
            return adb_path
    
    # 如果找不到，尝试直接使用 adb（假设在 PATH 中）
    return 'adb'

# ==================== 热点触发（共用脚本优先） ====================

def trigger_robot_hotspot():
    """触发机器热点（优先调用 common/hotspot_trigger.py，失败时回退到原 ROS2 expect 逻辑）"""
    force_print("📡 步骤1: 触发机器热点...")

    # 1. 优先使用 common/hotspot_trigger.py（S1MAX 公共触发脚本）
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../配网兼容性
        common_dir = os.path.join(base_dir, "common")
        if common_dir not in sys.path:
            sys.path.insert(0, common_dir)

        import hotspot_trigger  # type: ignore

        # 蓝牙配网原逻辑无 sleep，直接发 ROS2
        force_print("🔌 优先使用 common/hotspot_trigger.py 触发热点（sleep_before=0）...")
        ok = hotspot_trigger.trigger_hotspot(
            device_id=ROBOT_DEVICE_ID,
            sleep_before=0,
            log=force_print,
        )
        if ok:
            force_print("✅ common/hotspot_trigger.py 触发热点成功")
            return True
        force_print("⚠️ common/hotspot_trigger.py 触发失败，回退到内置 ROS2 expect 方式...")
    except Exception as e:
        force_print(f"⚠️ 调用 common/hotspot_trigger.py 失败，回退到内置 ROS2 expect 方式: {e}")

    # 2. 回退：保留原来的 adb+expect+ROS2 实现
    try:
        # 获取 adb 完整路径
        adb_path = get_adb_path()

        expect_script = f"""#!/usr/bin/expect -f
set timeout 60
spawn {adb_path} -s {ROBOT_DEVICE_ID} shell
expect {{
    -re "root@.*#" {{}}
    -re "# $" {{}}
}}
send "ros2 topic pub --once /USER_NET_INFO xm_robot_interfaces/msg/InternalIO '{{msg_content: AP}}'\\r"
expect {{
    -re "root@.*#" {{
        send "exit\\r"
    }}
    timeout {{
        exit 1
    }}
}}
expect eof
"""

        script_path = '/tmp/ros2_trigger_android.exp'
        with open(script_path, 'w') as f:
            f.write(expect_script)
        os.chmod(script_path, 0o755)

        result = subprocess.run(
            ['expect', script_path],
            capture_output=True,
            text=True,
            timeout=90
        )

        if result.returncode == 0:
            force_print("✅ ROS2消息发送成功")
            if result.stdout.strip():
                force_print(f"ℹ️ ROS2输出: {result.stdout.strip()}")
            return True

        force_print(f"❌ ROS2消息发送失败: {result.stderr.strip()}")
        return False

    except Exception as e:
        force_print(f"❌ 触发机器热点失败: {e}")
        return False

# ==================== 设备检测和删除 ====================

def check_add_device_button(driver):
    """检测首页是否有add device按钮"""
    try:
        # 等待页面加载
        time.sleep(3)
        
        force_print("🔍 开始检测add device按钮...")
        
        # 首先检查页面是否有已配对的设备（通过检查是否有 AquaSense / Sora / robot / 设备 文案）
        try:
            # 检查是否有已配对的设备（包括 AquaSense X、Sora、robot 等）
            device_elements = driver.find_elements(
                AppiumBy.XPATH,
                "//android.widget.TextView[contains(@text,'AquaSense') or contains(@text,'Sora') or contains(@text,'robot') or contains(@text,'设备')]"
            )
            if device_elements:
                force_print("🔍 检测到已配对设备，需要先删除")
                return False
        except:
            pass
        
        # 尝试多种选择器查找add device按钮
        selectors = [
            "//android.widget.ImageView[@content-desc='add']",
            "(//android.widget.ImageView[@content-desc='add'])[2]",
            "//android.widget.Button[contains(@text,'Add')]",
            "//android.widget.Button[contains(@text,'添加')]",
            "//android.widget.ImageView[contains(@content-desc,'add')]"
        ]
        
        for i, selector in enumerate(selectors, 1):
            try:
                force_print(f"🔍 尝试选择器 {i}: {selector}")
                element = driver.find_element(AppiumBy.XPATH, selector)
                if element.is_displayed():
                    # 额外检查：确保元素真的可见且可点击
                    try:
                        # 尝试获取元素的位置和大小
                        location = element.location
                        size = element.size
                        force_print(f"🔍 元素位置: {location}, 大小: {size}")
                        
                        # 检查元素是否真的在屏幕可见区域
                        if location['x'] >= 0 and location['y'] >= 0 and size['width'] > 0 and size['height'] > 0:
                            force_print("✅ 找到真正可见的add device按钮")
                            return True
                        else:
                            force_print(f"⚠️ 元素位置异常: {location}, {size}")
                    except Exception as e:
                        force_print(f"⚠️ 检查元素位置失败: {e}")
                        continue
                else:
                    force_print(f"⚠️ 找到元素但不可见: {selector}")
            except Exception as e:
                # 如果检测到 UiAutomator2 崩溃，抛出特殊异常
                if _is_driver_crashed_error(e):
                    force_print(f"⚠️ 检测到 UiAutomator2 崩溃: {str(e)[:100]}")
                    raise RuntimeError("UiAutomator2_CRASHED") from e
                force_print(f"⚠️ 选择器 {i} 失败: {str(e)[:50]}...")
                continue
        
        force_print("❌ 未找到add device按钮，需要执行删除操作")
        return False
        
    except RuntimeError as e:
        if "UiAutomator2_CRASHED" in str(e):
            raise
        force_print(f"❌ 检测add device按钮失败: {e}")
        return False
    except Exception as e:
        if _is_driver_crashed_error(e):
            force_print(f"⚠️ 检测到 UiAutomator2 崩溃: {str(e)[:100]}")
            raise RuntimeError("UiAutomator2_CRASHED") from e
        force_print(f"❌ 检测add device按钮失败: {e}")
        return False

def delete_paired_device(driver):
    """删除已配对的设备，删除后确保返回到首页"""
    force_print("🔧 开始删除已配对设备...")
    try:
        # 点击more按钮
        more_button = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="more"]')
        more_button.click()
        force_print("✅ 点击more按钮")
        time.sleep(2)
        
        # 点击Remove按钮
        remove_button = driver.find_element(AppiumBy.XPATH, '//android.widget.TextView[@text="Remove"]')
        remove_button.click()
        force_print("✅ 点击Remove按钮")
        time.sleep(2)
        
        # 点击确认按钮
        confirm_button = driver.find_element(AppiumBy.XPATH, '//android.widget.TextView[@text="Confirm"]')
        confirm_button.click()
        force_print("✅ 点击确认按钮")
        time.sleep(3)
        
        # 删除后，确保返回到首页
        force_print("🔄 删除设备后，确保返回到首页...")
        max_back_attempts = 5
        for i in range(max_back_attempts):
            # 检查是否已经在首页
            if check_is_on_home_page(driver):
                force_print("✅ 已在应用首页")
                time.sleep(2)  # 等待页面完全稳定
                return True
            
            # 如果不在首页，尝试按返回键
            force_print(f"⚠️ 不在首页，尝试按返回键返回 (第 {i+1}/{max_back_attempts} 次)...")
            try:
                driver.press_keycode(4)  # 返回键
                time.sleep(2)
            except Exception as e:
                force_print(f"⚠️ 按返回键失败: {e}")
            
            # 再次检查是否在首页
            if check_is_on_home_page(driver):
                force_print("✅ 已返回到应用首页")
                time.sleep(2)  # 等待页面完全稳定
                return True
        
        # 如果多次尝试后仍不在首页，尝试重置应用
        force_print("⚠️ 多次按返回键后仍未在首页，尝试重置应用...")
        if reset_app_to_home(driver):
            force_print("✅ 通过重置应用返回到首页")
            return True
        else:
            force_print("⚠️ 重置应用失败，但设备已删除")
            return True  # 即使重置失败，设备已删除，返回True继续执行
        
    except Exception as e:
        force_print(f"❌ 删除设备失败: {e}")
        return False

def _is_driver_crashed_error(err):
    """检测是否是 UiAutomator2 崩溃错误"""
    if not err:
        return False
    err_str = str(err).lower()
    return ('instrumentation process is not running' in err_str or 
            'cannot be proxied' in err_str or
            'crashed' in err_str)

def check_is_on_home_page(driver):
    """检查是否在应用首页"""
    try:
        home_indicators = [
            '//android.widget.ImageView[@content-desc="add"]',
            '//android.widget.TextView[contains(@text,"设备")]',
            '//android.widget.TextView[contains(@text,"Sora")]',
            '//android.widget.TextView[contains(@text,"robot")]'
        ]
        
        for indicator in home_indicators:
            try:
                element = driver.find_element(AppiumBy.XPATH, indicator)
                if element.is_displayed():
                    return True
            except Exception as e:
                # 如果检测到 UiAutomator2 崩溃，抛出特殊异常
                if _is_driver_crashed_error(e):
                    force_print(f"⚠️ 检测到 UiAutomator2 崩溃: {str(e)[:100]}")
                    raise RuntimeError("UiAutomator2_CRASHED") from e
                continue
        return False
    except RuntimeError as e:
        if "UiAutomator2_CRASHED" in str(e):
            raise
        return False
    except Exception as e:
        if _is_driver_crashed_error(e):
            force_print(f"⚠️ 检测到 UiAutomator2 崩溃: {str(e)[:100]}")
            raise RuntimeError("UiAutomator2_CRASHED") from e
        return False

def ensure_add_device_button(driver):
    """确保首页有add device按钮，如果没有则删除设备"""
    max_attempts = 3
    
    force_print("🔍 开始检查首页状态...")
    
    # 首先检查是否在首页，如果不在则切换到首页
    try:
        if not check_is_on_home_page(driver):
            force_print("⚠️ 当前不在应用首页，切换到首页...")
            try:
                # 尝试按返回键返回首页
                for _ in range(3):
                    driver.press_keycode(4)  # 返回键
                    time.sleep(1)
                
                # 等待页面加载
                time.sleep(2)
                
                # 再次检查是否在首页
                if check_is_on_home_page(driver):
                    force_print("✅ 已切换到应用首页")
                else:
                    force_print("⚠️ 按返回键后仍未在首页，尝试重置应用...")
                    # 如果返回键无效，尝试重置应用
                    reset_app_to_home(driver)
            except RuntimeError as e:
                if "UiAutomator2_CRASHED" in str(e):
                    raise
                force_print(f"⚠️ 切换首页失败: {e}，尝试重置应用...")
                reset_app_to_home(driver)
            except Exception as e:
                if _is_driver_crashed_error(e):
                    raise RuntimeError("UiAutomator2_CRASHED") from e
                force_print(f"⚠️ 切换首页失败: {e}，尝试重置应用...")
                reset_app_to_home(driver)
    except RuntimeError as e:
        if "UiAutomator2_CRASHED" in str(e):
            raise
    
    # 首先检查页面是否有已配对的设备（首页已有 AquaSense X / Sora / robot 等）
    try:
        # 检查是否有 AquaSense / Sora / robot / 设备 / standby 等指示
        device_indicators = [
            "//android.widget.TextView[contains(@text,'AquaSense')]",
            "//android.widget.TextView[contains(@text,'Sora')]",
            "//android.widget.TextView[contains(@text,'robot')]",
            "//android.widget.TextView[contains(@text,'设备')]",
            "//android.widget.TextView[contains(@text,'standby')]"
        ]
        
        has_paired_device = False
        for indicator in device_indicators:
            try:
                elements = driver.find_elements(AppiumBy.XPATH, indicator)
                if elements:
                    force_print(f"🔍 检测到已配对设备指示器: {indicator}")
                    has_paired_device = True
                    break
            except Exception as e:
                if _is_driver_crashed_error(e):
                    raise RuntimeError("UiAutomator2_CRASHED") from e
                continue
        
        if has_paired_device:
            force_print("🔍 检测到已配对设备，需要先删除")
        else:
            force_print("🔍 未检测到已配对设备")
    except RuntimeError as e:
        if "UiAutomator2_CRASHED" in str(e):
            raise
        force_print(f"⚠️ 检查已配对设备失败: {e}")
    except Exception as e:
        if _is_driver_crashed_error(e):
            raise RuntimeError("UiAutomator2_CRASHED") from e
        force_print(f"⚠️ 检查已配对设备失败: {e}")
    
    for attempt in range(max_attempts):
        force_print(f"🔍 第{attempt + 1}次检查add device按钮...")
        
        # 每次检查前，先确认是否在首页
        try:
            if not check_is_on_home_page(driver):
                force_print("⚠️ 不在首页，切换到首页...")
                try:
                    for _ in range(3):
                        driver.press_keycode(4)  # 返回键
                        time.sleep(1)
                    time.sleep(2)
                except Exception as e:
                    if _is_driver_crashed_error(e):
                        raise RuntimeError("UiAutomator2_CRASHED") from e
        except RuntimeError as e:
            if "UiAutomator2_CRASHED" in str(e):
                raise
            pass
        
        # 检查是否有add device按钮
        try:
            has_add_button = check_add_device_button(driver)
        except Exception as e:
            if _is_driver_crashed_error(e):
                raise RuntimeError("UiAutomator2_CRASHED") from e
            has_add_button = False
        
        if has_add_button:
            force_print("✅ 找到add device按钮，可以开始配网")
            return True
        
        force_print("🔧 未找到add device按钮，需要执行删除操作")
        force_print("🔍 检查是否有more按钮...")
        
        # 检查是否有more按钮（表示有已配对的设备）
        try:
            more_button = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="more"]')
            if more_button.is_displayed():
                force_print("✅ 找到more按钮，开始删除设备...")
                if delete_paired_device(driver):
                    force_print("✅ 设备删除完成，已返回到首页")
                    # 删除设备函数内部已经确保返回到首页，这里只需要等待页面稳定
                    time.sleep(3)
                    # 再次确认在首页
                    if not check_is_on_home_page(driver):
                        force_print("⚠️ 删除后未在首页，尝试重置应用...")
                        reset_app_to_home(driver)
                        time.sleep(2)
                else:
                    force_print("❌ 删除设备失败")
                    return False
            else:
                force_print("❌ 未找到more按钮，无法删除设备")
                return False
        except Exception as e:
            # 如果检测到 UiAutomator2 崩溃，抛出特殊异常
            if _is_driver_crashed_error(e):
                force_print(f"⚠️ 检测到 UiAutomator2 崩溃: {str(e)[:100]}")
                raise RuntimeError("UiAutomator2_CRASHED") from e
            force_print(f"❌ 检查more按钮失败: {e}")
            # 如果找不到more按钮，可能是页面不在首页，尝试返回首页
            if attempt < max_attempts - 1:
                force_print("⚠️ 尝试返回首页后重试...")
                try:
                    for _ in range(3):
                        driver.press_keycode(4)  # 返回键
                        time.sleep(1)
                    time.sleep(2)
                except Exception as press_err:
                    if _is_driver_crashed_error(press_err):
                        raise RuntimeError("UiAutomator2_CRASHED") from press_err
                    pass
                continue
            return False
    
    force_print("❌ 经过多次尝试，仍无法找到add device按钮")
    return False

# ==================== 设备选择 ====================

def click_add_device_button(driver):
    """点击添加设备按钮"""
    force_print("📱 步骤2: 点击添加设备按钮...")
    try:
        # 优先使用第二个add按钮
        add_button = driver.find_element(AppiumBy.XPATH, '(//android.widget.ImageView[@content-desc="add"])[2]')
        add_button.click()
        force_print("✅ 点击添加设备按钮成功")
        time.sleep(3)
        return True
    except:
        # 如果第二个按钮不存在，尝试第一个
        try:
            add_button = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="add"]')
            add_button.click()
            force_print("✅ 点击添加设备按钮成功")
            time.sleep(3)
            return True
        except Exception as e:
            force_print(f"❌ 点击添加设备按钮失败: {e}")
            return False

def select_device(driver, target_device_config):
    """选择设备（模块化）：优先调用 common/选择设备.py（参考 P0024-M0 方案）"""
    try:
        import importlib.util
        from pathlib import Path

        script_dir = os.path.dirname(os.path.abspath(__file__))
        common_dir = os.path.join(os.path.dirname(script_dir), "common")
        module_file = os.path.join(common_dir, "选择设备.py")
        if not os.path.exists(module_file):
            force_print(f"❌ 未找到 common/选择设备.py: {module_file}")
            return False

        spec = importlib.util.spec_from_file_location("p0022_select_device_module", module_file)
        if not spec or not spec.loader:
            force_print("❌ 无法加载 common/选择设备.py（spec 为空）")
            return False

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        force_print("🔌 使用独立设备选择模块: common/选择设备.py")

        try:
            sdir = Path(screenshot_dir)
        except Exception:
            sdir = None

        return bool(
            mod.select_device(
                driver=driver,
                target_device_config=target_device_config,
                platform="android",
                log_func=force_print,
                screenshot_dir=sdir,
            )
        )
    except Exception as e:
        force_print(f"❌ 调用 common/选择设备.py 失败: {e}")
        return False

# ==================== WiFi设置 ====================

def wait_for_wifi_setup_page(driver, timeout=15, app_package=None):
    """等待进入WiFi设置页面，可选校验当前包名，防止停留在系统页"""
    indicators = [
        '//android.widget.TextView[@text="Set Up Wi-Fi"]',
        '//android.view.View[@content-desc="password"]',
        '//android.widget.EditText[@hint="Password"]',
        '//android.widget.Button[contains(@text,"Next")]',
        '//android.widget.ImageView[@content-desc="switch"]'
    ]
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        # 如果提供了 app_package，确保当前前台包名正确（避免误判为系统WiFi页面）
        if app_package:
            try:
                if driver.current_package and driver.current_package != app_package:
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
    截图给出的 XPath:
      //android.widget.TextView[@text="Agree"]
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


def handle_wifi_guide_page_after_password(driver, timeout=10):
    """
    Set up Wi-Fi 页面输入密码后点击 Next，可能进入引导页，需要：
      1) 勾选: //android.widget.ImageView[@content-desc="checkbox"]
      2) 点击 Next: //android.widget.Button
    """
    try:
        checkbox = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="checkbox"]'))
        )
        if checkbox and checkbox.is_displayed():
            try:
                checkbox.click()
                force_print("✅ 引导页：已勾选 checkbox")
                time.sleep(0.6)
            except Exception as e:
                force_print(f"⚠️ 引导页：勾选 checkbox 失败: {e}")

            # 点击引导页 Next（按钮文本可能是 Next/下一步，也可能无文本，先按 XPath）
            try:
                next_btn = WebDriverWait(driver, 6).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, "//android.widget.Button"))
                )
                next_btn.click()
                force_print("✅ 引导页：已点击 Next 按钮")
                time.sleep(1.5)
                return True
            except Exception as e:
                force_print(f"⚠️ 引导页：点击 Next 失败: {e}")
                return False
    except Exception:
        # 未出现引导页
        return False


def handle_post_pairing_success_flow(driver, timeout=35):
    """
    配网成功后停留在当前页，出现 Next 按钮：
      1) 点击 Next: //android.widget.Button
      2) 出现绑定弹框/页面，点击“已绑定”
      3) 跳转首页，出现 AquaSense X + Home:
         - //android.view.View[@content-desc="Home"]
         - Text contains 'AquaSense'
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

    # 2) 绑定确认：你截图中为英文弹框 Pairing，左侧按钮是 Already paired
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
    ]

    def _click_leftmost_button_fallback(wait_seconds: int = 12) -> bool:
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
            # 强兜底：使用你提供的绝对 XPath（多变体）
            absolute_candidates = [
                "/android.view.ViewGroup/android.view.View/android.view.View/android.view.View/android.view.View[1]/android.widget.Button",
                "/android.view.ViewGroup/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.widget.Button",
                "(//android.widget.Button)[1]",
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
            force_print("❌ 绑定弹框：未找到可点击的“Already paired/已绑定”按钮")
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
        time.sleep(1)

    force_print("❌ 未在超时内确认回到首页（AquaSense + Home 未同时出现）")
    return False


def setup_wifi(driver, wifi_name, wifi_password):
    """设置 WiFi（模块化）：调用 common/选择WIFI.py，保留 Agree/引导页逻辑"""
    force_print(f"📶 步骤4: 设置WiFi ({wifi_name})...")

    # 可能会有 Agree 弹框
    try:
        handle_agree_popup(driver, timeout=3)
    except Exception:
        pass

    try:
        import importlib.util

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
                dname = drv.capabilities.get("deviceName", "unknown_device")
            except Exception:
                dname = "unknown_device"
            try:
                take_screenshot(drv, dname, wifi_name, prefix)
            except Exception:
                pass

        app_package = None
        try:
            app_package = driver.capabilities.get("appPackage")
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

        # Next 后可能出现引导页：checkbox + Next
        try:
            handled_guide = handle_wifi_guide_page_after_password(driver, timeout=10)
            if handled_guide:
                force_print("ℹ️ 已完成引导页操作，继续后续配网流程")
        except Exception:
            pass

        time.sleep(2)
        force_print("✅ WiFi设置完成（模块）")
        return True
        
    except Exception as e:
        force_print(f"❌ 设置WiFi失败: {e}")
        try:
            device_name = driver.capabilities.get('deviceName', 'unknown_device')
            take_screenshot(driver, device_name, wifi_name, "wifi_setup_failed")
        except Exception:
            pass
        return False


# ==================== 灯效设置 ====================

def setup_light_effect(driver):
    """设置灯效（新版本已取消此功能，直接跳过）"""
    force_print("💡 步骤5: 设置灯效...")
    force_print("ℹ️  新版本已取消灯效选择页面，跳过此步骤")
    # 新版本不再需要设置灯效，直接返回成功
    return True

# ==================== 配网结果验证 ====================

def _is_home_after_pairing(driver, target_device_config=None) -> bool:
    """
    通过页面元素判断是否已回到首页/第一阶段配网完成。
    经验判定（按你截图/实际页面）：
    - 存在 Home tab: //android.view.View[@content-desc="Home"]
    - 且存在 AquaSense 文案（或目标设备 SN/名称）
    """
    try:
        # 先用“首页强特征”判定：add 按钮出现，基本可认为已回首页
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

        # 其次再结合 Home tab + AquaSense/目标设备信息（用于部分首页没有 add 的场景）
        home_el = driver.find_elements(AppiumBy.XPATH, '//android.view.View[@content-desc="Home"]')
        if not any(e.is_displayed() for e in home_el):
            return False

        # 1) AquaSense 文案
        aqua_els = driver.find_elements(AppiumBy.XPATH, '//android.widget.TextView[contains(@text,"AquaSense")]')
        if any(e.is_displayed() for e in aqua_els):
            return True

        # 2) 目标设备名称/SN（可选）
        if target_device_config:
            sn = (target_device_config.get("device_sn") or "").strip()
            name = (target_device_config.get("device_name") or "").strip()
            if sn:
                sn_els = driver.find_elements(AppiumBy.XPATH, f'//android.widget.TextView[contains(@text,"{sn}")]')
                if any(e.is_displayed() for e in sn_els):
                    return True
            if name:
                name_els = driver.find_elements(AppiumBy.XPATH, f'//android.widget.TextView[contains(@text,"{name}")]')
                if any(e.is_displayed() for e in name_els):
                    return True
    except Exception:
        return False

    return False


def wait_for_pairing_result(driver, timeout=180, target_device_config=None):
    """等待配网结果"""
    force_print("⏳ 步骤6: 等待配网结果...")
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < timeout:
        try:
            check_count += 1
            force_print(f"🔍 第{check_count}次检查配网状态...")

            # 关键优化：优先用页面信息判断是否已回到首页（第一阶段配网完成）
            if _is_home_after_pairing(driver, target_device_config=target_device_config):
                force_print("✅ 页面判定：已回到首页（Home + AquaSense/目标设备信息），认为配网完成")
                return "success"
            
            # 检查是否在配网进程页面
            try:
                pairing_text = driver.find_element(AppiumBy.XPATH, '//android.widget.TextView[@text="Pairing with your device"]')
                if pairing_text.is_displayed():
                    force_print("🔄 配网进行中...")
                    time.sleep(5)
                    continue
            except:
                force_print("🔍 未找到配网进程文本，继续检查其他状态...")
            
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
            
            # 检查是否配对成功（首页出现新设备）
            try:
                success_indicators = [
                    '//android.widget.ImageView[@content-desc="robot"]',
                    '//android.widget.TextView[contains(@text,"robot")]',
                    '//android.widget.TextView[contains(@text,"设备")]',
                    '//android.widget.TextView[contains(@text,"Sora")]'
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
            # 截图给出的 XPath: //android.widget.Button
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
                if any(b.is_displayed() for b in btns) and not _is_home_after_pairing(driver, target_device_config=target_device_config):
                    force_print("✅ 检测到页面存在可见 Button（可能是成功页 Next），进入收尾流程判定")
                    return "success_need_next"
            except Exception:
                pass
            
            # 检查当前页面状态
            try:
                current_activity = driver.current_activity
                force_print(f"🔍 当前页面: {current_activity}")
            except:
                pass
            
            time.sleep(3)
            
        except Exception as e:
            force_print(f"🔍 检查配网状态异常: {e}")
            time.sleep(3)
    
    force_print("⏰ 配网超时（3分钟）")
    return "timeout"

# ==================== 蓝牙控制功能 ====================

def restart_bluetooth(driver):
    """重启手机蓝牙，确保蓝牙环境初始化"""
    force_print("🔄 重启手机蓝牙...")
    try:
        device_name = driver.capabilities.get('deviceName', 'unknown_device')
        adb_path = get_adb_path()
        
        # 关闭蓝牙
        force_print("📴 关闭蓝牙...")
        disable_result = subprocess.run(
            [adb_path, '-s', device_name, 'shell', 'svc', 'bluetooth', 'disable'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if disable_result.returncode == 0:
            force_print("✅ 蓝牙已关闭")
        else:
            # 尝试备用方法
            force_print("⚠️ 使用备用方法关闭蓝牙...")
            subprocess.run(
                [adb_path, '-s', device_name, 'shell', 'settings', 'put', 'global', 'bluetooth_on', '0'],
                capture_output=True,
                text=True,
                timeout=10
            )
            force_print("✅ 蓝牙已关闭（备用方法）")
        
        # 等待蓝牙完全关闭
        time.sleep(3)
        
        # 开启蓝牙
        force_print("📶 开启蓝牙...")
        enable_result = subprocess.run(
            [adb_path, '-s', device_name, 'shell', 'svc', 'bluetooth', 'enable'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if enable_result.returncode == 0:
            force_print("✅ 蓝牙已开启")
        else:
            # 尝试备用方法
            force_print("⚠️ 使用备用方法开启蓝牙...")
            subprocess.run(
                [adb_path, '-s', device_name, 'shell', 'settings', 'put', 'global', 'bluetooth_on', '1'],
                capture_output=True,
                text=True,
                timeout=10
            )
            force_print("✅ 蓝牙已开启（备用方法）")
        
        # 等待蓝牙完全启动
        force_print("⏳ 等待蓝牙初始化完成...")
        time.sleep(5)
        
        force_print("✅ 蓝牙重启完成")
        return True
        
    except Exception as e:
        force_print(f"⚠️ 重启蓝牙失败: {e}")
        force_print("⚠️ 继续执行，但蓝牙可能未正确初始化")
        return False

# ==================== 应用重置功能 ====================

def reset_app_to_home(driver):
    """重置应用到首页"""
    force_print("🔄 重置应用到首页...")
    try:
        # 方法1: 使用Appium的terminate_app和activate_app
        driver.terminate_app(driver.capabilities['appPackage'])
        time.sleep(3)
        driver.activate_app(driver.capabilities['appPackage'])
        time.sleep(5)
        
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
        
        force_print("✅ 应用重置成功")
        return True
        
    except RuntimeError as e:
        if "UiAutomator2_CRASHED" in str(e):
            raise
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
        return True
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

def single_pairing_flow(driver, wifi_name, wifi_password, target_device_config, device_config=None):
    """单次配网流程"""
    force_print(f"\n🔄 开始单次配网流程 (WiFi: {wifi_name})")
    force_print("=" * 60)
    
    max_recovery_attempts = 2  # 最多尝试恢复2次
    
    for recovery_attempt in range(max_recovery_attempts):
        try:
            # 步骤0: 重置应用到首页
            force_print("🔄 重置应用到首页...")
            try:
                if not reset_app_to_home(driver):
                    force_print("⚠️ 应用重置失败，但继续执行")
            except RuntimeError as e:
                if "UiAutomator2_CRASHED" in str(e) and device_config and recovery_attempt < max_recovery_attempts - 1:
                    force_print(f"⚠️ UiAutomator2 崩溃，尝试重建 driver (第 {recovery_attempt + 1}/{max_recovery_attempts} 次)...")
                    try:
                        driver.quit()
                    except:
                        pass
                    time.sleep(3)
                    driver = create_device_driver(device_config)
                    if not driver:
                        return "error", "无法重建 Appium 会话"
                    force_print("✅ Driver 重建成功，重试配网流程...")
                    continue
                else:
                    raise
            wait_after_step("应用重置")
            
            # 步骤1: 触发机器热点
            if not trigger_robot_hotspot():
                return "error", "触发机器热点失败"
            wait_after_step("触发机器热点")
            
            # 步骤2: 确保有add device按钮
            try:
                if not ensure_add_device_button(driver):
                    return "error", "无法找到add device按钮"
            except RuntimeError as e:
                if "UiAutomator2_CRASHED" in str(e) and device_config and recovery_attempt < max_recovery_attempts - 1:
                    force_print(f"⚠️ UiAutomator2 崩溃，尝试重建 driver (第 {recovery_attempt + 1}/{max_recovery_attempts} 次)...")
                    try:
                        driver.quit()
                    except:
                        pass
                    time.sleep(3)
                    driver = create_device_driver(device_config)
                    if not driver:
                        return "error", "无法重建 Appium 会话"
                    force_print("✅ Driver 重建成功，重试配网流程...")
                    continue
                else:
                    return "error", f"UiAutomator2 崩溃: {str(e)[:100]}"
            wait_after_step("确认首页add按钮")
        
            # 步骤3: 点击添加设备按钮
            if not click_add_device_button(driver):
                return "error", "点击添加设备按钮失败"
            wait_after_step("点击添加设备按钮")
            
            # 步骤4: 选择设备
            if not select_device(driver, target_device_config):
                return "error", "选择设备失败"
            wait_after_step("选择目标设备")

            # 选择设备跳转到 Set up Wi-Fi 页面时，可能出现 Agree 弹框
            handle_agree_popup(driver, timeout=6)
            
            # 步骤5: 设置WiFi
            if not setup_wifi(driver, wifi_name, wifi_password):
                return "error", "设置WiFi失败"
            wait_after_step("设置WiFi")
            
            # 步骤6: 设置灯效
            if not setup_light_effect(driver):
                return "error", "设置灯效失败"
            wait_after_step("灯效设置")
            
            # 步骤7: 等待配网结果
            result = wait_for_pairing_result(driver, target_device_config=target_device_config)

            # 新流程：成功页需要点击 Next -> 配对弹框确认 -> 回到 Home
            if result == "success_need_next":
                force_print("ℹ️ 检测到成功页 Next，需要完成收尾跳转首页...")
                if handle_post_pairing_success_flow(driver, timeout=45):
                    result = "success"
                else:
                    # 再兜底：如果其实已经回到首页，就别判失败
                    if _is_home_after_pairing(driver, target_device_config=target_device_config):
                        force_print("✅ 收尾流程失败但页面已在首页，按成功处理")
                        result = "success"
                    else:
                        return "error", "配网成功后收尾步骤失败（Next/弹框/回Home）"
            
            # 步骤8: 重启蓝牙，确保蓝牙环境初始化
            force_print("🔄 配网流程结束，重启蓝牙以初始化环境...")
            restart_bluetooth(driver)
            wait_after_step("蓝牙重启", seconds=2)
            
            if result == "success":
                force_print("🎉 配网成功！")
                return "success", "配网成功"
            elif result == "failed":
                force_print("❌ 配网失败，重置应用...")
                reset_app_to_home(driver)
                return "failed", "配网失败"
            else:
                force_print("⏰ 配网超时，重置应用...")
                reset_app_to_home(driver)
                return "timeout", "配网超时"
            
        except RuntimeError as e:
            if "UiAutomator2_CRASHED" in str(e) and device_config and recovery_attempt < max_recovery_attempts - 1:
                force_print(f"⚠️ UiAutomator2 崩溃，尝试重建 driver (第 {recovery_attempt + 1}/{max_recovery_attempts} 次)...")
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(3)
                driver = create_device_driver(device_config)
                if not driver:
                    return "error", "无法重建 Appium 会话"
                force_print("✅ Driver 重建成功，重试配网流程...")
                continue
            else:
                force_print(f"❌ 配网流程异常: {e}")
                try:
                    device_name = driver.capabilities.get('deviceName', 'unknown_device')
                    take_screenshot(driver, device_name, wifi_name, "pairing_error")
                except:
                    pass
                return "error", str(e)
        except Exception as e:
            # 检查是否是崩溃错误
            if _is_driver_crashed_error(e) and device_config and recovery_attempt < max_recovery_attempts - 1:
                force_print(f"⚠️ UiAutomator2 崩溃，尝试重建 driver (第 {recovery_attempt + 1}/{max_recovery_attempts} 次)...")
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(3)
                driver = create_device_driver(device_config)
                if not driver:
                    return "error", "无法重建 Appium 会话"
                force_print("✅ Driver 重建成功，重试配网流程...")
                continue
            else:
                force_print(f"❌ 配网流程异常: {e}")
                # 截图保存异常状态
                try:
                    device_name = driver.capabilities.get('deviceName', 'unknown_device')
                    take_screenshot(driver, device_name, wifi_name, "pairing_error")
                except:
                    pass
                return "error", str(e)
    
    # 如果所有恢复尝试都失败
    return "error", "UiAutomator2 崩溃且无法恢复"

# ==================== 设备驱动管理 ====================

def check_appium_server(port):
    """检查Appium服务器是否运行"""
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
    """创建设备驱动"""
    try:
        from appium.options.android import UiAutomator2Options
        
        device_name = device_config['device_name']
        port = device_config['port']
        
        # 检查Appium服务器是否运行
        if not check_appium_server(port):
            force_print(f"❌ Appium服务器 (端口 {port}) 未运行，无法连接设备")
            force_print(f"📱 请先启动Appium服务器后再重试")
            return None
        
        force_print(f"🔗 正在连接Appium服务器 (端口 {port})...")
        force_print(f"📱 设备名称: {device_name}")
        force_print(f"📦 应用包名: {device_config['app_package']}")
        
        # 尝试连接，如果 Activity 不存在则尝试不指定 Activity
        app_activity = device_config.get('app_activity', '')
        max_attempts = 2 if app_activity else 1
        
        for attempt in range(max_attempts):
            try:
                options = UiAutomator2Options()
                # 使用 set_capability 方法设置配置，兼容性更好
                options.set_capability('platformName', 'Android')
                # 使用 udid 而不是 deviceName，更准确
                options.set_capability('udid', device_name)
                options.set_capability('deviceName', device_name)  # 保留 deviceName 以兼容性
                options.set_capability('platformVersion', device_config['platform_version'])
                options.set_capability('appPackage', device_config['app_package'])
                
                # 第一次尝试：使用配置的 Activity
                # 第二次尝试：不指定 Activity，让 Appium 自动启动
                if attempt == 0 and app_activity:
                    options.set_capability('appActivity', app_activity)
                    force_print(f"🎯 应用Activity: {app_activity}")
                else:
                    force_print(f"🎯 应用Activity: (自动检测)")
                
                options.set_capability('automationName', 'UiAutomator2')
                options.set_capability('noReset', True)
                options.set_capability('newCommandTimeout', 300)
                # 添加自动启动应用的选项
                options.set_capability('autoLaunch', True)
                
                driver = webdriver.Remote(
                    f"http://127.0.0.1:{port}",
                    options=options
                )
                
                # 验证 driver 是否成功创建（检查 session_id）
                if hasattr(driver, 'session_id') and driver.session_id:
                    force_print(f"✅ 设备 {device_config['description']} 连接成功")
                    return driver
                else:
                    raise Exception("Driver 创建失败：未获得有效的 session_id")
                
            except Exception as e:
                error_msg = str(e)
                force_print(f"🔍 尝试 {attempt + 1}/{max_attempts} 失败: {error_msg[:200]}...")
                
                # 检查是否是 Activity 相关的错误（多种可能的错误信息格式）
                is_activity_error = (
                    "Activity" in error_msg or 
                    "does not exist" in error_msg or 
                    ("Cannot start" in error_msg and "application" in error_msg) or
                    "Activity class" in error_msg or
                    "Activity name" in error_msg
                )
                
                # 如果是 Activity 不存在的错误，且是第一次尝试，则重试不指定 Activity
                if attempt == 0 and max_attempts > 1 and is_activity_error:
                    force_print(f"⚠️  检测到 Activity 错误，尝试不指定 Activity 自动启动应用...")
                    time.sleep(2)  # 短暂等待后重试
                    continue
                elif attempt < max_attempts - 1:
                    # 还有其他尝试机会，继续
                    continue
                else:
                    # 所有尝试都失败了，抛出异常让外层处理
                    raise
        
    except Exception as e:
        error_msg = str(e)
        force_print(f"❌ 创建设备驱动失败: {error_msg}")
        
        # 提供更详细的错误信息和建议
        if "Connection refused" in error_msg:
            force_print(f"💡 提示: Appium服务器可能未启动或端口 {port} 配置错误")
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
            force_print(f"   4. 或者使用启动脚本: ./start_appium.sh")
        elif "Activity class" in error_msg and "does not exist" in error_msg:
            force_print(f"💡 提示: Activity 类不存在")
            force_print(f"   可能的原因:")
            force_print(f"   1. 应用未安装到设备上")
            force_print(f"   2. Activity 路径不正确")
            force_print(f"   3. 应用包名或 Activity 名称已更改")
            force_print(f"   解决方案:")
            force_print(f"   1. 检查应用是否已安装: adb -s {device_config.get('device_name', 'device')} shell pm list packages | grep {device_config.get('app_package', 'com.testdemo.tech')}")
            force_print(f"   2. 如果应用已安装，检查正确的 Activity:")
            force_print(f"      adb -s {device_config.get('device_name', 'device')} shell dumpsys package {device_config.get('app_package', 'com.testdemo.tech')} | grep -A 5 'android.intent.action.MAIN'")
            force_print(f"   3. 或者尝试不指定 Activity，让 Appium 自动启动应用")
            force_print(f"   4. 检查设备 ID 是否正确（当前配置: {device_config.get('device_name', 'unknown')}）")
        elif "Cannot start" in error_msg and "application" in error_msg:
            force_print(f"💡 提示: 无法启动应用")
            force_print(f"   可能的原因:")
            force_print(f"   1. 应用未安装")
            force_print(f"   2. Activity 路径错误")
            force_print(f"   3. 设备 ID 不匹配（检查 adb devices 确认正确的设备 ID）")
            force_print(f"   解决方案:")
            force_print(f"   1. 运行 'adb devices' 查看已连接的设备")
            force_print(f"   2. 确认 device_config.json 中的 device_name 与实际的设备 ID 匹配")
            force_print(f"   3. 确认应用已安装: adb -s {device_config.get('device_name', 'device')} shell pm list packages | grep {device_config.get('app_package', 'com.testdemo.tech')}")
        
        return None

# ==================== 多设备测试 ====================

def finalize_results(total_tests, success_count, failure_count, detailed_results, test_config, interrupted=False):
    """汇总测试结果并生成报告"""
    force_print("\n" + "=" * 80)
    if interrupted:
        force_print("⚠️ 用户中断测试，已保存截至目前的测试数据")
    force_print("📊 测试结果汇总")
    force_print("=" * 80)
    force_print(f"总测试次数: {total_tests}")
    force_print(f"成功次数: {success_count}")
    force_print(f"失败次数: {failure_count}")
    force_print(f"成功率: {success_count/total_tests*100:.1f}%" if total_tests > 0 else "成功率: 0%")

    # 分设备/路由器详细汇总（仅展示已测试的数据）
    force_print("\n🔎 分设备/路由器明细：")
    has_data = False
    for device_name, routers in detailed_results.items():
        # 仅统计有数据的设备
        valid_routers = {r: stats for r, stats in routers.items() if stats.get('success', 0) + stats.get('failure', 0) > 0}
        if not valid_routers:
            continue
        has_data = True
        force_print(f"\n📱 设备: {device_name}")
        for router_name, stats in valid_routers.items():
            force_print(f"  📶 路由器: {router_name}  成功: {stats['success']}  失败: {stats['failure']}")
            failed_rounds = [r for r in stats['rounds'] if r['result'] != 'success']
            if failed_rounds:
                for fr in failed_rounds:
                    timestamp = fr.get('timestamp', '未知时间')
                    force_print(f"    ❌ 轮次#{fr['round']} 结果: {fr['result']}  原因: {fr['message']}  时间: {timestamp}")
            else:
                force_print("    ✅ 全部成功")
    
    if not has_data:
        force_print("⚠️ 没有可汇总的测试数据")
    
    # 检查成功率阈值
    success_rate = success_count / total_tests if total_tests > 0 else 0
    if total_tests > 0:
        if success_rate >= test_config['success_rate_threshold']:
            force_print(f"✅ 测试通过！成功率 {success_rate*100:.1f}% 达到阈值 {test_config['success_rate_threshold']*100:.1f}%")
        else:
            force_print(f"❌ 测试失败！成功率 {success_rate*100:.1f}% 未达到阈值 {test_config['success_rate_threshold']*100:.1f}%")
    else:
        force_print("⚠️ 因未执行任何测试，无法计算成功率")
    
    # 仅在有数据时生成报告
    if has_data:
        try:
            # 尝试从 common 目录导入 excel_report_generator
            import sys
            import os
            common_path = str(SCRIPT_DIR.parent / "common")
            if common_path not in sys.path:
                sys.path.insert(0, common_path)
            from excel_report_generator import create_network_compatibility_report
            force_print("\n📊 生成Excel测试报告...")

            # 适配 excel_report_generator 预期的数据结构：
            #   { device_name: { "routers": { router_name: { rounds: {round_num: {...}} } } } }
            # 当前 detailed_results 结构为：
            #   { device_name: { router_name: { success/failure/rounds: [{round, result, message, ...}] } } }
            excel_results = {}
            for device_name, routers in detailed_results.items():
                excel_routers = {}
                for router_name, router_data in routers.items():
                    # 将 rounds 列表转换为字典格式
                    rounds_list = router_data.get('rounds', [])
                    rounds_dict = {}
                    for round_item in rounds_list:
                        round_num = round_item.get('round', 0)
                        # 移除 'round' 键，因为 round_num 已经作为字典的 key
                        round_data = {k: v for k, v in round_item.items() if k != 'round'}
                        rounds_dict[round_num] = round_data
                    
                    excel_routers[router_name] = {
                        'success': router_data.get('success', 0),
                        'failure': router_data.get('failure', 0),
                        'rounds': rounds_dict
                    }
                excel_results[device_name] = {"routers": excel_routers}

            excel_file = create_network_compatibility_report(
                excel_results,
                platform="Android", 
                network_method="2蓝牙配网",
                output_dir=str(RUN_DIR)
            )
            if excel_file:
                force_print(f"✅ Excel报告已生成: {excel_file}")
                force_print(f"📁 报告目录: {RUN_DIR}")
            else:
                force_print(f"⚠️ Excel报告生成失败，但报告目录为: {RUN_DIR}")
        except Exception as e:
            force_print(f"⚠️ Excel报告生成失败: {e}")
            force_print(f"📁 报告目录: {RUN_DIR}")
            force_print(f"💡 提示: 测试数据已保存在上述目录中，可以手动查看日志文件")
            import traceback
            force_print(f"详细错误: {traceback.format_exc()}")
    else:
        force_print("⚠️ 无测试数据，跳过Excel报告生成")


def run_multi_device_test():
    """运行多设备测试（支持中途终止并保留已完成结果）"""
    force_print("🚀 开始多设备/多路由器蓝牙配网测试")
    force_print("=" * 80)
    
    # 检查是否有未完成的测试数据
    saved_data = load_test_data_from_file()
    if saved_data:
        force_print("⚠️ 检测到未完成的测试数据，是否恢复？")
        force_print(f"   上次测试时间: {saved_data.get('timestamp', '未知')}")
        force_print(f"   已完成测试: {saved_data.get('total_tests', 0)} 次")
        force_print(f"   成功: {saved_data.get('success_count', 0)} 次")
        force_print(f"   失败: {saved_data.get('failure_count', 0)} 次")
        force_print("   提示: 将使用新的测试配置继续，旧数据已保存")
    
    config = load_device_config()
    if not config:
        return
    
    device_configs = config['device_configs']
    wifi_configs = config['wifi_configs']
    test_config = config['test_config']
    target_device_config = config.get('target_device', {
        'device_sn': 'B0078',
        'device_name': 'Sora 70',
        'description': '目标配网设备 - 机器人设备'
    })
    
    force_print(f"📱 设备数量: {len(device_configs)}")
    force_print(f"📶 路由器数量: {len(wifi_configs)}")
    force_print(f"🔄 每个路由器测试次数: {test_config['loop_count_per_router']}")
    
    total_tests = 0
    success_count = 0
    failure_count = 0
    detailed_results = {}
    interrupted = False
    
    # 初始化全局测试数据
    _global_test_data['total_tests'] = total_tests
    _global_test_data['success_count'] = success_count
    _global_test_data['failure_count'] = failure_count
    _global_test_data['detailed_results'] = detailed_results
    _global_test_data['test_config'] = test_config
    _global_test_data['interrupted'] = interrupted
    
    try:
        for device_name, device_config in device_configs.items():
            force_print(f"\n📱 设备: {device_config['description']}")
            force_print("=" * 60)
            
            driver = create_device_driver(device_config)
            if not driver:
                force_print(f"❌ 设备 {device_name} 连接失败，跳过")
                continue
            
            try:
                device_results = {}
                # 遍历每个路由器
                for wifi_config in wifi_configs:
                    force_print(f"\n📶 路由器: {wifi_config['name']}")
                    force_print("-" * 40)
                    
                    if wifi_config['name'] not in device_results:
                        device_results[wifi_config['name']] = {
                            'success': 0,
                            'failure': 0,
                            'rounds': []
                        }
                    
                    for test_round in range(test_config['loop_count_per_router']):
                        force_print(f"\n🔄 第 {test_round + 1}/{test_config['loop_count_per_router']} 次测试")
                        
                        if test_round > 0:
                            force_print("🔄 重置应用准备下一次测试...")
                            reset_app_to_home(driver)
                            time.sleep(3)
                        
                        result, message = single_pairing_flow(
                            driver,
                            wifi_config['name'],
                            wifi_config['password'],
                            target_device_config,
                            device_config=device_config
                        )
                        
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
                            device_results[wifi_config['name']]['success'] += 1
                        else:
                            failure_count += 1
                            force_print(f"❌ 测试失败: {message}")
                            device_results[wifi_config['name']]['failure'] += 1
                        
                        device_results[wifi_config['name']]['rounds'].append(round_record)
                        
                        # 更新全局测试数据
                        _global_test_data['total_tests'] = total_tests
                        _global_test_data['success_count'] = success_count
                        _global_test_data['failure_count'] = failure_count
                        _global_test_data['detailed_results'] = {**detailed_results, device_name: device_results}
                        _global_test_data['test_config'] = test_config
                        
                        # 定期保存测试数据到文件（每次测试后）
                        save_test_data_to_file()
                        
                        if result == "error" and "用户中断" in message:
                            raise KeyboardInterrupt
                        
                        if test_round < test_config['loop_count_per_router'] - 1:
                            force_print("⏳ 等待10秒后进行下一次测试...")
                            time.sleep(10)
                    
                    if wifi_config != wifi_configs[-1]:
                        force_print("🔄 切换到下一个路由器，重置应用...")
                        reset_app_to_home(driver)
                        time.sleep(3)
                
                detailed_results[device_name] = device_results
            
            except KeyboardInterrupt:
                interrupted = True
                force_print("\n⚠️ 用户中断当前设备测试，已保存已完成的数据")
                detailed_results[device_name] = device_results
                raise
            except Exception as e:
                force_print(f"❌ 设备 {device_name} 测试异常: {e}")
                detailed_results[device_name] = device_results
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
    force_print("🚀 启动Android蓝牙配网测试脚本")
    force_print("=" * 80)
    
    # 注册信号处理器（捕获 SIGTERM，SIGKILL 无法捕获）
    signal.signal(signal.SIGTERM, emergency_save_and_exit)
    signal.signal(signal.SIGINT, emergency_save_and_exit)  # Ctrl+C
    
    # 注册退出处理函数（在程序正常退出时也会执行，但不调用 sys.exit）
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
