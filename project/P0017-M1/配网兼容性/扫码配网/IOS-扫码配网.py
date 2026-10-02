#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iOS 扫码配网脚本（根据流程图实现）

流程：
1. 重置机器，不清除数据
2. 触发机器热点
3. 检查页面有没有add device，没有则删除设备
4. 设备选择页面，使用摄像头扫描二维码
5. WIFI配置（切换WIFI、输入密码）
6. 配网引导页（点击Next）
7. connect device hotspot页面（点击Connect和Join）
8. 配网进程页面（等待3min）
9. 配网结果（成功/失败）
"""

import os
import sys
import json
import time
import logging
import subprocess
from datetime import datetime

from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 尝试导入report_utils，如果不存在则使用默认路径
try:
    from report_utils import init_run_env
except ImportError:
    # 如果report_utils不在当前路径，尝试从common目录导入
    common_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common")
    sys.path.insert(0, common_path)
    try:
        from report_utils import init_run_env
    except ImportError:
        # 如果还是找不到，尝试从蓝牙配网目录导入（向后兼容）
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "2蓝牙配网"))
        from report_utils import init_run_env

# ==================== 日志与输出目录初始化 ====================

# 为 iOS 扫码配网任务创建本次运行的输出目录
RUN_DIR, LOG_FILE, SCREENSHOT_DIR = init_run_env(prefix="1扫码配网-iOS")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)


def log(msg: str) -> None:
    """统一日志输出"""
    print(msg, flush=True)
    logger.info(msg)


# ==================== 公共工具 ==================== #

def _find_android_home() -> str | None:
    """尝试在常见位置查找 ANDROID_HOME"""
    env_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if env_home:
        return env_home

    candidates = [
        os.path.expanduser("~/Library/Android/sdk"),
        os.path.expanduser("~/Android/Sdk"),
        "/usr/local/share/android-sdk",
        "/opt/android-sdk",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def get_adb_path() -> str:
    """获取 adb 完整路径，找不到则退回 'adb'"""
    home = _find_android_home()
    if home:
        adb = os.path.join(home, "platform-tools", "adb")
        if os.path.exists(adb):
            return adb
    return "adb"


def take_screenshot(driver, prefix: str) -> None:
    """简单截图，用于问题排查，保存到本次运行的 screenshots 目录"""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{prefix}_{ts}.png"
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        filepath = SCREENSHOT_DIR / filename
        driver.save_screenshot(str(filepath))
        log(f"📸 截图已保存: {filepath}")
    except Exception as e:
        log(f"⚠️ 截图失败: {e}")


# ==================== 配置加载 ==================== #

def load_config() -> dict | None:
    """
    加载设备 / 路由器配置。
    优先级：
    1. 环境变量 DEVICE_CONFIG_FILE 指定的文件
    2. common 目录中的 device_config.json
    3. 上级目录中的 device_config.json（向后兼容）
    4. 当前目录下的 device_config.json（向后兼容）
    只保留 platform == 'ios' 的设备。
    """
    # 1. 环境变量
    env_path = os.environ.get("DEVICE_CONFIG_FILE")
    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log(f"✅ 从环境变量配置文件加载: {env_path}")
            return _filter_ios_devices(cfg)
        except Exception as e:
            log(f"⚠️ 加载环境变量配置文件失败: {e}")

    # 2. common 目录（优先）
    base_dir = os.path.dirname(os.path.abspath(__file__))
    common_cfg = os.path.join(os.path.dirname(base_dir), "common", "device_config.json")
    if os.path.exists(common_cfg):
        try:
            with open(common_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log(f"✅ 从 common 目录加载配置: {common_cfg}")
            return _filter_ios_devices(cfg)
        except Exception as e:
            log(f"⚠️ 加载 common 配置失败: {e}")

    # 3. 上级目录（向后兼容）
    parent_cfg = os.path.join(os.path.dirname(base_dir), "2蓝牙配网", "device_config.json")
    if os.path.exists(parent_cfg):
        try:
            with open(parent_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log(f"✅ 从上级目录加载配置: {parent_cfg}")
            return _filter_ios_devices(cfg)
        except Exception as e:
            log(f"⚠️ 加载上级目录配置失败: {e}")

    # 4. 当前目录（向后兼容）
    local_cfg = os.path.join(base_dir, "device_config.json")
    if os.path.exists(local_cfg):
        try:
            with open(local_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log(f"✅ 从当前目录加载配置: {local_cfg}")
            return _filter_ios_devices(cfg)
        except Exception as e:
            log(f"⚠️ 加载当前目录配置失败: {e}")

    log("❌ 未找到任何配置文件，请确认 device_config.json 是否存在")
    return None


def _filter_ios_devices(config: dict) -> dict:
    """过滤出 iOS 设备"""
    devs = config.get("device_configs", {})
    ios_devs = {
        key: val for key, val in devs.items()
        if str(val.get("platform", "ios")).lower() == "ios"
    }
    config = dict(config)
    config["device_configs"] = ios_devs
    return config


def _bundle_id_from_config(dev_cfg: dict) -> str | None:
    return dev_cfg.get("bundle_id") or dev_cfg.get("app_package")


# ==================== 触发机器人热点 ==================== #

# 机器人热点触发配置（P0024-M0：串口触发）
# 可通过环境变量覆盖
SERIAL_PORT = os.environ.get("ROBOT_SERIAL_PORT", "/dev/tty.usbserial-120")
SERIAL_BAUD = int(os.environ.get("ROBOT_SERIAL_BAUD", "115200"))
SERIAL_TRIGGER_CMD = os.environ.get("ROBOT_SERIAL_CMD", "SET state 4")

# 向后兼容：机器人热点触发所需的设备ID（已废弃，改用串口方式）
ROBOT_DEVICE_ID = os.environ.get("ROBOT_DEVICE_ID", "galaxy_p0001")


def trigger_robot_hotspot() -> bool:
    """
    触发机器热点（P0024-M0：使用端口命令脚本）
    优先使用 common/端口命令.py 模块
    """
    log("📡 步骤1: 触发机器热点...")
    
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
                log(f"✅ 已加载端口命令模块: 端口命令.py")
        else:
            log(f"⚠️ 未找到端口命令模块: {port_command_file}")
    except Exception as e:
        log(f"⚠️ 无法加载端口命令模块: {e}")
    
    # 优先使用端口命令模块
    if port_command_module:
        try:
            port = SERIAL_PORT
            baud = SERIAL_BAUD
            cmd = SERIAL_TRIGGER_CMD
            
            log(f"🔌 使用端口命令模块触发热点: {port} @ {baud}bps -> {cmd}")
            
            # 调用 send_command 函数
            result = port_command_module.send_command(
                port=port,
                baudrate=baud,
                command=cmd,
                retry_on_busy=True
            )
            
            if "✅" in result:
                log("✅ 端口命令模块触发热点成功")
                return True
            else:
                log(f"❌ 端口命令模块触发热点失败: {result}")
                return False
                
        except Exception as e:
            log(f"❌ 调用端口命令模块失败: {e}")
            # 继续尝试备用方式
    else:
        log("⚠️ 端口命令模块未加载，尝试备用方式...")
    
    # 备用方式：使用 subprocess 直接调用端口命令脚本
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        common_dir = os.path.join(os.path.dirname(script_dir), "common")
        port_command_script = os.path.join(common_dir, "端口命令.py")
        
        if os.path.exists(port_command_script):
            log(f"📝 使用端口命令脚本: {port_command_script}")
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
                    log(f"ℹ️ 端口命令输出: {result.stdout.strip()}")
                log("✅ 端口命令脚本触发热点成功")
                return True
            else:
                output = result.stdout.strip()
                error = result.stderr.strip()
                log(f"❌ 端口命令脚本失败（返回码: {result.returncode}）")
                if output:
                    log(f"   输出: {output}")
                if error:
                    log(f"   错误: {error}")
                return False
        else:
            log(f"❌ 未找到端口命令脚本: {port_command_script}")
            return False
            
    except Exception as e:
        log(f"❌ 调用端口命令脚本失败: {e}")
        return False


# ==================== Appium / driver ==================== #

def create_driver(dev_cfg: dict):
    """根据 device_config 为单个 iOS 设备创建 Appium driver"""
    from appium.options.ios import XCUITestOptions

    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.device_name = dev_cfg["device_name"]
    options.platform_version = dev_cfg["platform_version"]
    options.bundle_id = _bundle_id_from_config(dev_cfg)
    options.automation_name = "XCUITest"
    options.no_reset = True
    options.new_command_timeout = 300

    if "udid" in dev_cfg:
        options.udid = dev_cfg["udid"]

    server_urls = [
        f"http://127.0.0.1:{dev_cfg['port']}",
        f"http://127.0.0.1:{dev_cfg['port']}/wd/hub",
    ]

    last_err = None
    for url in server_urls:
        try:
            log(f"🔗 尝试连接 Appium 服务器: {url}")
            driver = webdriver.Remote(url, options=options)
            log(f"✅ 设备 {dev_cfg.get('description', dev_cfg['device_name'])} 连接成功")
            return driver
        except Exception as e:
            last_err = e
            log(f"⚠️ 连接 {url} 失败: {e}")
    if last_err:
        log(f"❌ 创建设备驱动失败: {last_err}")
    return None


def reset_app_to_home(driver) -> bool:
    """重置机器，不清除数据"""
    log("🔄 重置应用到首页（不清除数据）...")
    try:
        caps = getattr(driver, "capabilities", {}) or {}
        bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
        if not bundle_id:
            log("⚠️ 无法获取 bundleId，跳过应用重启")
            return True

        driver.terminate_app(bundle_id)
        time.sleep(2)
        driver.activate_app(bundle_id)
        time.sleep(2)

        # 简单检查首页特征
        home_xpaths = [
            '//XCUIElementTypeButton[@name="home add"]',
            '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
            '//XCUIElementTypeStaticText[contains(@name,"设备")]',
        ]
        for xp in home_xpaths:
            try:
                elem = driver.find_element(AppiumBy.XPATH, xp)
                if elem.is_displayed():
                    log(f"✅ 确认在首页: {xp}")
                    return True
            except Exception:
                continue
        log("⚠️ 无法确认是否在首页，但应用已重启")
        return True
    except Exception as e:
        log(f"⚠️ 重置应用失败: {e}")
        return False


# ==================== 首页 add device / 删除设备 ==================== #

def _home_has_add_button(driver) -> bool:
    """检查首页是否有home add按钮（严格匹配，只检查首页的add按钮）"""
    # 优先检查"home add"按钮（这是首页特有的按钮）
    add_button_selectors = [
        '//XCUIElementTypeButton[@name="home add"]',  # 首页特有的add按钮
        '//XCUIElementTypeButton[@name="Add"]',  # 备用选择器
        '//XCUIElementTypeButton[contains(@name,"add")]',  # 更宽泛的选择器（最后使用）
    ]
    
    for selector in add_button_selectors:
        try:
            btn = driver.find_element(AppiumBy.XPATH, selector)
            if btn.is_displayed():
                # 如果是宽泛的选择器，需要额外验证是否在首页
                if 'contains' in selector:
                    # 检查是否在首页（通过检查是否有设备列表或其他首页特征）
                    try:
                        # 如果找到设备列表页面特征，说明不在首页
                        device_list = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeStaticText[contains(@name,"(SN:")]')
                        if device_list.is_displayed():
                            log(f"⚠️ 找到add按钮，但在设备列表页面，不是首页: {selector}")
                            continue
                    except:
                        # 没有找到设备列表，可能在首页
                        pass
                
                log(f"✅ 找到add按钮（选择器: {selector}）")
                return True
        except Exception:
            continue
    
    return False


def _has_paired_device(driver) -> bool:
    """检查是否有已配对的设备（参考IOS-2蓝牙配网.py）"""
    device_indicators = [
        '//XCUIElementTypeButton[@name="device down unsel"]',
        '//XCUIElementTypeButton[contains(@name,"device down")]',
        '//XCUIElementTypeButton[contains(@name,"device")]',
        '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
        '//XCUIElementTypeStaticText[contains(@name,"设备")]',
    ]
    
    for selector in device_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, selector)
            if elem.is_displayed():
                log(f"✅ 检测到已配对设备（选择器: {selector}）")
                return True
        except Exception:
            continue
    
    return False


def _remove_existing_device(driver) -> bool:
    """执行删除已配对设备的一整套操作（参考IOS-2蓝牙配网.py）"""
    log("🔧 开始删除已配对设备...")
    
    # 先检查是否有已配对的设备
    if not _has_paired_device(driver):
        log("⚠️ 未检测到已配对设备，可能页面状态异常，尝试刷新页面...")
        try:
            # 参考蓝牙配网：使用activate_app刷新页面
            caps = getattr(driver, "capabilities", {}) or {}
            bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
            if bundle_id:
                driver.activate_app(bundle_id)
                time.sleep(2)
            else:
                # 如果没有bundle_id，使用swipe刷新
                size = driver.get_window_size()
                start_x = size['width'] // 2
                start_y = int(size['height'] * 0.2)
                end_y = int(size['height'] * 0.5)
                driver.swipe(start_x, start_y, start_x, end_y, 500)
                time.sleep(3)
        except:
            time.sleep(3)
        return True
    
    # 参考蓝牙配网：使用步骤列表方式执行删除操作
    steps = [
        ('//XCUIElementTypeButton[@name="device down unsel"]', "点击设备下拉按钮"),
        ('//XCUIElementTypeStaticText[@name="Remove"]', "点击Remove按钮"),
        ('//XCUIElementTypeButton[@name="Confirm"]', "点击Confirm按钮")
    ]
    
    for xpath, desc in steps:
        try:
            log(f"🔍 {desc} ({xpath})")
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xpath))
            )
            element.click()
            time.sleep(1.5)  # 参考蓝牙配网的等待时间
        except Exception as e:
            log(f"❌ {desc}失败: {e}")
            return False
    
    # 参考蓝牙配网：使用activate_app刷新页面，确保按钮状态更新
    log("🔄 刷新首页状态...")
    try:
        caps = getattr(driver, "capabilities", {}) or {}
        bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
        if bundle_id:
            driver.activate_app(bundle_id)
            time.sleep(2)
        else:
            # 如果没有bundle_id，使用swipe刷新
            size = driver.get_window_size()
            start_x = size['width'] // 2
            start_y = int(size['height'] * 0.2)
            end_y = int(size['height'] * 0.5)
            driver.swipe(start_x, start_y, start_x, end_y, 500)
            time.sleep(3)
    except Exception as e:
        log(f"⚠️ 刷新页面失败: {e}")
        time.sleep(2)
    
    return True


def ensure_home_add_button(driver) -> bool:
    """
    检测首页有没有add按钮，如果有的话，直接返回；没有的话，执行删除设备操作
    参考IOS-2蓝牙配网.py的ensure_home_add_button逻辑
    流程：
    1. 先检查首页是否有"home add"按钮（严格匹配）
    2. 如果有，直接返回True
    3. 如果没有，检查是否有已配对设备
    4. 如果有已配对设备，先删除设备，然后刷新页面
    5. 循环检查，直至出现home add按钮
    """
    for attempt in range(3):
        log(f"🔁 检查首页 add 按钮（第 {attempt+1}/3 次）")
        
        # 先检查是否有home add按钮（严格匹配，只检查首页的add按钮）
        if _home_has_add_button(driver):
            log("✅ add device 按钮已就绪")
            return True
        
        # 如果第一次检查失败，检查是否有已配对设备，如果有则删除
        if attempt == 0:
            # 检查是否有已配对设备
            if _has_paired_device(driver):
                log("✅ 检测到首页有设备，先执行删除设备操作...")
                if not _remove_existing_device(driver):
                    log("⚠️ 删除设备失败")
                    return False
                # 删除设备后，等待页面刷新，然后再次检查
                log("⏳ 等待页面刷新后检查 add 按钮...")
                time.sleep(3)
            else:
                log("⚠️ 未找到 add 按钮，且未检测到已配对设备，等待页面加载...")
                time.sleep(3)
        else:
            # 后续尝试：如果删除后仍然没有，等待更长时间
            log(f"⏳ 第 {attempt+1} 次检查，等待页面加载...")
            time.sleep(3)
    
    log("❌ 多次尝试后仍未找到 add 按钮")
    take_screenshot(driver, "add_button_not_found")
    return False


def tap_add_device(driver) -> bool:
    """点击首页 add device 按钮"""
    log("📱 步骤2: 点击添加设备按钮...")
    
    add_button_selectors = [
        '//XCUIElementTypeButton[@name="home add"]',
        '//XCUIElementTypeButton[@name="Add"]',
        '//XCUIElementTypeButton[contains(@name,"add")]',
        '//XCUIElementTypeButton[@name="+"]',
    ]
    
    for selector in add_button_selectors:
        try:
            log(f"🔍 尝试add按钮选择器: {selector}")
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            if btn.is_displayed():
                btn.click()
                log(f"✅ 点击添加设备按钮成功（选择器: {selector}）")
                time.sleep(2)
                return True
        except Exception as e:
            log(f"⚠️ add按钮选择器失败: {selector} - {e}")
            continue
    
    log("❌ 所有add按钮选择器都失败")
    take_screenshot(driver, "tap_add_fail")
    return False


# ==================== 设备选择页面 - 扫码 ==================== #

def scan_qr_code(driver) -> bool:
    """
    设备选择页面，使用摄像头扫描二维码
    - 扫描成功：跳转WIFI设置页面
    - 未扫到码：停留超过1min，配网失败
    """
    log("📷 步骤3: 使用摄像头扫描二维码...")
    
    # 等待进入设备选择页面（扫码页面）
    log("⏳ 等待进入扫码页面...")
    time.sleep(3)
    
    # 检查是否在扫码页面（通常会有摄像头权限提示或扫码界面）
    scan_page_indicators = [
        '//XCUIElementTypeAlert',
        '//XCUIElementTypeButton[contains(@name,"允许")]',
        '//XCUIElementTypeButton[contains(@name,"Allow")]',
        '//XCUIElementTypeButton[contains(@name,"相机")]',
        '//XCUIElementTypeButton[contains(@name,"Camera")]',
    ]
    
    # 处理摄像头权限提示
    for indicator in scan_page_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                log("✅ 检测到摄像头权限提示，尝试允许...")
                allow_buttons = [
                    '//XCUIElementTypeButton[contains(@name,"允许")]',
                    '//XCUIElementTypeButton[contains(@name,"Allow")]',
                    '//XCUIElementTypeButton[contains(@name,"好")]',
                    '//XCUIElementTypeButton[contains(@name,"OK")]',
                ]
                for btn_selector in allow_buttons:
                    try:
                        btn = driver.find_element(AppiumBy.XPATH, btn_selector)
                        if btn.is_displayed():
                            btn.click()
                            log(f"✅ 点击允许按钮: {btn_selector}")
                            time.sleep(2)
                            break
                    except:
                        continue
                break
        except:
            continue
    
    # 先检查是否已经跳转到WiFi设置页面（可能已经扫描成功）
    wifi_setup_indicators = [
        '//XCUIElementTypeButton[@name="pair net change wifi"]',
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeTextField',
        '//XCUIElementTypeStaticText[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeStaticText[contains(@name,"WIFI")]',
    ]
    
    log("🔍 检查是否已经跳转到WiFi设置页面...")
    for indicator in wifi_setup_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                log(f"✅ 已经跳转到WiFi设置页面，扫描成功: {indicator}")
                time.sleep(2)
                return True
        except:
            continue
    
    # 如果还没有跳转到WiFi设置页面，点击扫描框（如果设备出现，扫描框会被覆盖，无法扫描二维码）
    log("🔍 点击扫描框，确保扫描框可见...")
    
    # 先等待页面完全加载
    time.sleep(2)
    
    scan_frame_selectors = [
        # 用户提供的精确XPath
        '//XCUIElementTypeApplication[@name="Beatbot"]/XCUIElementTypeWindow[1]/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther/XCUIElementTypeOther[1]/XCUIElementTypeOther[2]',
        # 通过扫描相关的图像元素定位父容器
        '//XCUIElementTypeImage[@name="scan_top_left"]/..',
        '//XCUIElementTypeImage[@name="scan_top_right"]/..',
        '//XCUIElementTypeImage[@name="scan_bottom_left"]/..',
        '//XCUIElementTypeImage[@name="scan_bottom_right"]/..',
        # 通过扫描相关的图像元素定位
        '//XCUIElementTypeImage[contains(@name,"scan")]',
        # 通用选择器
        '//XCUIElementTypeOther[contains(@name,"scan")]',
        '//XCUIElementTypeOther[contains(@name,"Scan")]',
        '//XCUIElementTypeOther[contains(@name,"扫描")]',
    ]
    
    scan_frame_clicked = False
    for selector in scan_frame_selectors:
        try:
            log(f"🔍 尝试扫描框选择器: {selector[:80]}...")
            scan_frame = WebDriverWait(driver, 8).until(  # 增加等待时间到8秒
                EC.presence_of_element_located((AppiumBy.XPATH, selector))
            )
            # 检查元素是否可见和可点击
            if scan_frame.is_displayed():
                try:
                    # 尝试标准点击
                    scan_frame.click()
                    log(f"✅ 点击扫描框成功（选择器: {selector[:50]}...）")
                    time.sleep(2)  # 等待扫描框激活
                    scan_frame_clicked = True
                    break
                except Exception as click_err:
                    log(f"⚠️ 标准点击失败，尝试强制点击: {click_err}")
                    try:
                        # 尝试JavaScript点击
                        driver.execute_script("arguments[0].click();", scan_frame)
                        log(f"✅ 强制点击扫描框成功")
                        time.sleep(2)
                        scan_frame_clicked = True
                        break
                    except Exception as js_err:
                        log(f"⚠️ 强制点击也失败: {js_err}")
                        continue
        except Exception as e:
            log(f"⚠️ 扫描框选择器失败: {str(e)[:80]}")
            continue
    
    # 如果所有选择器都失败，尝试通过坐标点击扫描区域中心
    if not scan_frame_clicked:
        log("⚠️ 未找到扫描框元素，尝试通过坐标点击扫描区域中心...")
        try:
            # 获取屏幕尺寸
            size = driver.get_window_size()
            screen_width = size['width']
            screen_height = size['height']
            
            # 扫描区域通常在屏幕上半部分，点击中心位置
            # 根据图片描述，扫描区域在顶部，设备列表在底部
            scan_center_x = screen_width // 2
            scan_center_y = int(screen_height * 0.3)  # 屏幕上方30%的位置
            
            log(f"🔍 点击扫描区域中心坐标: ({scan_center_x}, {scan_center_y})")
            driver.tap([(scan_center_x, scan_center_y)], 100)  # 点击并按住100ms
            log("✅ 通过坐标点击扫描区域成功")
            time.sleep(2)
            scan_frame_clicked = True
        except Exception as coord_err:
            log(f"⚠️ 坐标点击失败: {coord_err}")
    
    if not scan_frame_clicked:
        log("⚠️ 未找到扫描框，可能已经跳转到其他页面，继续检查...")
        # 再次检查是否已经跳转到WiFi设置页面
        for indicator in wifi_setup_indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, indicator)
                if elem.is_displayed():
                    log(f"✅ 已跳转到WiFi设置页面: {indicator}")
                    time.sleep(2)
                    return True
            except:
                continue
        time.sleep(2)
    
    # 等待扫描结果，最多等待1分钟
    log("⏳ 等待扫描二维码结果（最多60秒）...")
    start_time = time.time()
    timeout = 60  # 1分钟超时
    
    wifi_setup_indicators = [
        '//XCUIElementTypeButton[@name="pair net change wifi"]',
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeTextField',
    ]
    
    while time.time() - start_time < timeout:
        # 检查是否已跳转到WIFI设置页面
        for indicator in wifi_setup_indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, indicator)
                if elem.is_displayed():
                    log(f"✅ 扫描成功，已跳转到WIFI设置页面: {indicator}")
                    time.sleep(2)
                    return True
            except:
                continue
        
        # 检查是否还在扫码页面（如果还在，继续等待）
        time.sleep(2)
    
    log("❌ 扫描超时（超过1分钟），未扫到码，本次配网失败")
    take_screenshot(driver, "scan_qr_timeout")
    return False


# ==================== WiFi 设置流程 ====================

def _enter_wifi_list_page(driver) -> bool:
    """从 App 内点击"切换 WiFi"进入系统 WiFi 列表"""
    log("📶 步骤4: 进入系统 WiFi 页面...")
    try:
        btn = driver.find_element(
            AppiumBy.XPATH, '//XCUIElementTypeButton[@name="pair net change wifi"]'
        )
        btn.click()
        log("✅ 点击切换 WiFi 按钮成功")
        time.sleep(2)
    except Exception as e:
        log(f"❌ 点击切换 WiFi 按钮失败: {e}")
        take_screenshot(driver, "click_change_wifi_fail")
        return False

    # 验证是否已经在系统 WiFi / 设置页面
    indicators = [
        '//XCUIElementTypeNavigationBar[@name="Settings"]',
        '//XCUIElementTypeStaticText[@name="WLAN"]',
        '//XCUIElementTypeButton[@name="WLAN"]',
    ]
    for i in range(6):
        for xp in indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, xp)
                if elem.is_displayed():
                    log(f"✅ 检测到 iOS 设置页面元素: {xp}")
                    return True
            except Exception:
                continue
        time.sleep(2)
    log("⚠️ 未明显检测到 iOS 系统 WiFi 页面，后续仍按 WiFi 列表处理")
    return True


def _select_wifi_in_settings(driver, ssid: str) -> bool:
    """在 iOS 系统 WiFi 设置页面选择指定 SSID"""
    log(f"🔍 在系统 WiFi 列表中寻找: {ssid}")
    max_scroll = 10
    
    selectors = [
        f'//XCUIElementTypeCell[contains(@name,"{ssid}")]',
        f'//XCUIElementTypeStaticText[@name="{ssid}"]',
        f'//XCUIElementTypeStaticText[contains(@name,"{ssid}")]',
    ]
    
    wifi_cell = None
    
    # 首先尝试直接查找
    log("🔍 首先尝试直接查找 WiFi（不滑动）...")
    for xp in selectors:
        try:
            wifi_cell = driver.find_element(AppiumBy.XPATH, xp)
            if wifi_cell.is_displayed():
                log(f"✅ 直接找到 WiFi 元素: {xp}")
                wifi_cell.click()
                log(f"✅ 已点击 WiFi: {ssid}")
                time.sleep(2)
                return True
        except Exception:
            continue
    
    # 如果直接查找失败，向下滑动查找
    if not wifi_cell:
        log("🔍 直接查找失败，开始向下滑动查找 WiFi...")
        for i in range(max_scroll):
            log(f"🔍 第 {i+1}/{max_scroll} 次向下滚动寻找 WiFi...")
            
            for xp in selectors:
                try:
                    wifi_cell = driver.find_element(AppiumBy.XPATH, xp)
                    if wifi_cell.is_displayed():
                        log(f"✅ 向下滑动后找到 WiFi 元素: {xp}")
                        break
                except Exception:
                    continue
            
            if wifi_cell and wifi_cell.is_displayed():
                wifi_cell.click()
                log(f"✅ 已点击 WiFi: {ssid}")
                time.sleep(2)
                return True
            
            # 向下滑动
            try:
                size = driver.get_window_size()
                start_x = size['width'] // 2
                start_y = int(size['height'] * 0.6)
                end_y = int(size['height'] * 0.3)
                driver.swipe(start_x, start_y, start_x, end_y, 500)
                time.sleep(2)
            except Exception as e:
                log(f"⚠️ 向下滑动失败: {e}")
                time.sleep(2)
    
    # 如果向下滑动未找到，尝试向上滑动查找
    if not wifi_cell:
        log("🔍 向下滑动未找到 WiFi，开始向上滑动查找 WiFi...")
        for i in range(max_scroll):
            log(f"🔍 向上滑动查找 WiFi（第 {i+1}/{max_scroll} 次）...")
            
            for xp in selectors:
                try:
                    wifi_cell = driver.find_element(AppiumBy.XPATH, xp)
                    if wifi_cell.is_displayed():
                        log(f"✅ 向上滑动后找到 WiFi 元素: {xp}")
                        break
                except Exception:
                    continue
            
            if wifi_cell and wifi_cell.is_displayed():
                wifi_cell.click()
                log(f"✅ 已点击 WiFi: {ssid}")
                time.sleep(2)
                return True
            
            # 向上滑动
            try:
                size = driver.get_window_size()
                start_x = size['width'] // 2
                start_y = int(size['height'] * 0.3)
                end_y = int(size['height'] * 0.6)
                driver.swipe(start_x, start_y, start_x, end_y, 500)
                time.sleep(2)
            except Exception as e:
                log(f"⚠️ 向上滑动失败: {e}")
                time.sleep(2)
    
    log(f"❌ 经过向下和向上各 {max_scroll} 次滑动，仍未找到 WiFi: {ssid}")
    take_screenshot(driver, "wifi_not_found")
    return False


def _back_to_app_wifi_page(driver) -> bool:
    """从系统设置回到 App 的 WiFi 密码输入页面"""
    log("🔄 通过后台切换返回 App WiFi 页面...")
    try:
        caps = getattr(driver, "capabilities", {}) or {}
        bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
        if not bundle_id:
            raise RuntimeError("bundleId 未配置")
        driver.activate_app(bundle_id)
        time.sleep(2)
        log("✅ 已返回 App")
        return True
    except Exception as e:
        log(f"⚠️ 返回 App 失败: {e}")
        return False


def _locate_password_field(driver):
    """定位 WiFi 密码输入框"""
    log("🔍 定位 WiFi 密码输入框...")
    selectors = [
        '//XCUIElementTypeSecureTextField',
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeSecureTextField[@placeholder="Wi-Fi Password"]',
        '//XCUIElementTypeSecureTextField[contains(@placeholder,"Password")]',
    ]
    last_err = None
    for i, xp in enumerate(selectors, 1):
        try:
            log(f"🔍 尝试密码框选择器 {i}: {xp}")
            field = WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xp))
            )
            if field.is_displayed():
                log(f"✅ 找到密码框（选择器 {i}）")
                return field
        except Exception as e:
            last_err = e
            log(f"  ⚠️ 选择器 {i} 失败: {e}")
    log(f"❌ 未找到密码输入框: {last_err}")
    take_screenshot(driver, "pwd_field_not_found")
    return None


def _input_wifi_password(driver, password: str) -> bool:
    """
    按最新要求输入 WiFi 密码：
    - 不再依赖读取当前内容，也不再点击"眼睛"按钮
    - 无论密码框中原来是什么，统一用连续退格清空，然后重新输入 device_config.json 中的密码
    """
    field = _locate_password_field(driver)
    if field is None:
        return False

    # 先点击密码框获取焦点
    try:
        field.click()
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
    except Exception as e:
        log(f"⚠️ 点击密码框失败: {e}")
    
    # 不判断当前内容，直接用退格键"暴力清空"
    log("🧹 使用连续退格清除密码框中的所有内容（不判断原内容）...")
    try:
        # 重新定位密码框，避免stale element
        field = _locate_password_field(driver)
        if field is None:
            return False
        field.click()
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
        field.send_keys("\b" * 50)  # 多发一些退格，确保清空
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
    except Exception as e:
        log(f"⚠️ 连续退格清除时出错（继续尝试输入新密码）: {e}")
        # 如果清除失败，尝试重新定位密码框
        field = _locate_password_field(driver)
        if field is None:
            return False

    # 统一输入新密码（来自 device_config.json）
    log(f"🔍 输入 WiFi 密码（来自 device_config.json）: {password}")
    try:
        # 再次重新定位密码框，确保元素是最新的
        field = _locate_password_field(driver)
        if field is None:
            return False
        field.click()
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
        field.send_keys(password)
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
        # iOS SecureTextField 出于安全考虑，value 可能为空或返回密文，所以不强校验
        try:
            v = field.get_attribute("value")
            log(f"✅ WiFi 密码输入完成（调试信息，当前 value: '{v}'）")
        except Exception:
            log("✅ WiFi 密码输入完成（无法读取 value，为正常安全行为）")
        return True
    except Exception as e:
        log(f"❌ WiFi 密码输入失败: {e}")
        take_screenshot(driver, "pwd_input_fail")
        return False


def perform_wifi_setup(driver, wifi_name: str, wifi_pwd: str) -> bool:
    """整体 WiFi 设置步骤"""
    if not _enter_wifi_list_page(driver):
        return False
    if not _select_wifi_in_settings(driver, wifi_name):
        return False
    if not _back_to_app_wifi_page(driver):
        return False
    
    if not _input_wifi_password(driver, wifi_pwd):
        return False

    # 关闭键盘：点击 Done，再点击 Next
    log("⌨️ 点击键盘 Done 按钮，然后点击 Next 按钮...")
    
    done_clicked = False
    done_selectors = [
        '//XCUIElementTypeButton[@name="Done"]',
        '//XCUIElementTypeButton[contains(@name,"Done")]',
    ]

    for i, xp in enumerate(done_selectors, 1):
        try:
            log(f"🔍 尝试 Done 按钮选择器 {i}: {xp}")
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            if btn.is_displayed():
                btn.click()
                log(f"✅ 点击 Done 按钮成功（选择器 {i}）")
                time.sleep(2)
                done_clicked = True
                break
        except Exception as e:
            log(f"  ⚠️ Done 按钮选择器 {i} 失败: {e}")
            continue

    if not done_clicked:
        log("⚠️ 未找到 Done 按钮，尝试使用 hide_keyboard")
        try:
            driver.hide_keyboard()
            time.sleep(2)
        except Exception as e:
            log(f"⚠️ hide_keyboard 也失败: {e}")

    # 步骤1: 清除密码后点击next按钮，进入配网引导页
    log("✅ 步骤1: 点击Next按钮，进入配网引导页...")
    try:
        next_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]')
            )
        )
        next_btn.click()
        log("✅ 已点击 Next 按钮，等待进入配网引导页...")
        time.sleep(3)  # 等待页面跳转到配网引导页
        log("✅ WiFi设置完成，已进入配网引导页")
        return True
    except Exception as e:
        log(f"❌ 点击 Next 按钮失败: {e}")
        take_screenshot(driver, "next_btn_fail")
        return False


# ==================== 配网引导页 ====================

def handle_pairing_guide(driver) -> bool:
    """步骤2.1: 配网引导页点击Next按钮，进入connect robot hotspot页面"""
    log("📋 步骤2.1: 配网引导页点击Next按钮，进入connect robot hotspot页面...")
    
    try:
        # 等待页面稳定加载
        time.sleep(2)
        
        next_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]')
            )
        )
        next_btn.click()
        log("✅ 已点击配网引导页Next按钮，等待进入connect robot hotspot页面...")
        time.sleep(3)  # 等待页面跳转到connect robot hotspot页面
        log("✅ 已进入connect robot hotspot页面")
        return True
    except Exception as e:
        log(f"❌ 点击配网引导页Next按钮失败: {e}")
        take_screenshot(driver, "pairing_guide_next_fail")
        return False


# ==================== connect device hotspot页面 ====================

def handle_connect_hotspot(driver) -> bool:
    """
    步骤2.2: connect robot hotspot页面处理
    流程：
    1. 点击按钮：//XCUIElementTypeButton[@name="Connect Robot Hotspot"]
    2. 页面跳出系统弹框，点击Join按钮
    3. 进入配网进程
    """
    log("📡 步骤2.2: 处理connect robot hotspot页面...")
    
    # 等待页面稳定加载
    log("⏳ 等待connect robot hotspot页面加载...")
    time.sleep(3)
    
    # 步骤2.2-1: 点击Connect Robot Hotspot按钮
    log("🔍 步骤2.2-1: 点击Connect Robot Hotspot按钮...")
    try:
        connect_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Connect Robot Hotspot"]'))
        )
        connect_btn.click()
        log("✅ 已点击Connect Robot Hotspot按钮，等待系统弹框出现...")
        time.sleep(3)  # 等待系统弹框出现
    except Exception as e:
        log(f"❌ 点击Connect Robot Hotspot按钮失败: {e}")
        take_screenshot(driver, "connect_robot_hotspot_btn_fail")
        return False
    
    # 步骤2.2-2: 点击系统弹框的Join按钮
    log("🔍 步骤2.2-2: 点击系统弹框的Join按钮...")
    
    # 先等待Alert弹窗出现
    log("⏳ 等待系统Alert弹窗出现...")
    time.sleep(5)  # 等待Alert完全加载
    
    # 使用iOS原生的Alert处理API（最有效的方法）
    log("🔍 使用iOS原生Alert处理...")
    try:
        alert = driver.switch_to.alert
        alert_text = alert.text
        log(f"✅ 检测到Alert文本: {alert_text}")
        if "Join" in alert_text or "加入" in alert_text or "Wants to Join" in alert_text:
            alert.accept()  # 接受Alert（相当于点击Join）
            log("✅ 通过Alert API点击Join成功，进入配网进程...")
            time.sleep(3)  # 等待进入配网进程页面
            return True
        else:
            log(f"⚠️ Alert文本不包含Join，文本内容: {alert_text}")
            # 即使文本不匹配，也尝试接受
            alert.accept()
            log("✅ 已接受Alert，进入配网进程...")
            time.sleep(3)
            return True
    except AttributeError:
        log("❌ driver.switch_to.alert 不支持，可能需要其他方式")
        return False
    except Exception as alert_err:
        log(f"❌ Alert API失败: {alert_err}")
        return False


# ==================== 配网进度 & 结果 ====================

def wait_pairing_result(driver, timeout: int = 180) -> str:
    """
    等待配网结果：success / failed / timeout
    先确认是否在配网页面（检查是否有"Pairing with your device (1/2)"）
    """
    log("⏳ 步骤7: 等待配网结果...")
    
    # 先确认是否在配网页面
    log("🔍 确认是否在配网页面...")
    pairing_indicator = '//XCUIElementTypeStaticText[@name="Pairing with your device (1/2)"]'
    
    try:
        elem = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.XPATH, pairing_indicator))
        )
        if elem.is_displayed():
            log("✅ 确认在配网页面")
    except Exception as e:
        log(f"⚠️ 未检测到配网页面指示器，但继续等待配网结果: {e}")
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            # 进度条页面
            try:
                txt = driver.find_element(
                    AppiumBy.XPATH,
                    '//XCUIElementTypeStaticText[@name="Pairing with your device (1/2)"]',
                )
                if txt.is_displayed():
                    log("🔄 配网进行中 ...")
                    time.sleep(5)
                    continue
            except Exception:
                pass

            # 成功：首页出现新设备
            success_xpaths = [
                '//XCUIElementTypeStaticText[@name="Sora 70"]',
                '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
                '//XCUIElementTypeStaticText[contains(@name,"设备")]',
            ]
            for xp in success_xpaths:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, xp)
                    if elem.is_displayed():
                        log(f"✅ 配网成功，新设备元素: {xp}")
                        return "success"
                except Exception:
                    continue

            # 失败文案
            fail_xpaths = [
                '//XCUIElementTypeStaticText[@name="Data transmitting failed."]',
                '//XCUIElementTypeStaticText[contains(@name,"failed")]',
                '//XCUIElementTypeStaticText[contains(@name,"失败")]',
            ]
            for xp in fail_xpaths:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, xp)
                    if elem.is_displayed():
                        log(f"❌ 配网失败，失败元素: {xp}")
                        return "failed"
                except Exception:
                    continue

            time.sleep(3)
        except Exception as e:
            log(f"⚠️ 检查配网状态异常: {e}")
            time.sleep(3)
    log("⏰ 配网超时（超过 3 分钟）")
    return "timeout"


# ==================== 单次配网流程 ====================

def run_single_flow(driver, wifi_name: str, wifi_pwd: str) -> tuple[str, str]:
    """单次扫码配网完整流程，返回 (result, message)"""
    log(f"\n🔄 开始单次扫码配网流程（WiFi: {wifi_name}）")
    log("=" * 60)

    if not reset_app_to_home(driver):
        log("⚠️ 应用重置失败，仍尝试继续")

    if not trigger_robot_hotspot():
        return "error", "触发机器热点失败"

    if not ensure_home_add_button(driver):
        return "error", "首页缺少 add 按钮"

    if not tap_add_device(driver):
        return "error", "点击 add 按钮失败"

    if not scan_qr_code(driver):
        return "error", "扫描二维码失败或超时"

    if not perform_wifi_setup(driver, wifi_name, wifi_pwd):
        return "error", "WiFi 设置失败"

    if not handle_pairing_guide(driver):
        return "error", "配网引导页处理失败"

    if not handle_connect_hotspot(driver):
        return "error", "connect hotspot处理失败"

    result = wait_pairing_result(driver)
    if result == "success":
        return "success", "配网成功"
    if result == "failed":
        return "failed", "配网失败"
    return "timeout", "配网超时"


# ==================== 结果汇总和报告生成 ====================

def finalize_results(total_tests, success_count, failure_count, detailed_results, test_config, interrupted=False):
    """汇总测试结果并生成报告"""
    log("\n" + "=" * 80)
    if interrupted:
        log("⚠️ 用户中断测试，已保存截至目前的测试数据")
    log("📊 测试结果汇总")
    log("=" * 80)
    log(f"总测试次数: {total_tests}")
    log(f"成功次数: {success_count}")
    log(f"失败次数: {failure_count}")
    if total_tests > 0:
        log(f"成功率: {success_count/total_tests*100:.1f}%")
    else:
        log("成功率: 0%")
    
    # 分设备/路由器详细汇总
    log("\n🔎 分设备/路由器明细：")
    has_data = False
    for device_name, device_data in detailed_results.items():
        routers = device_data.get("routers", {})
        valid_routers = {r: stats for r, stats in routers.items() if stats.get('success', 0) + stats.get('failure', 0) > 0}
        if not valid_routers:
            continue
        has_data = True
        log(f"\n📱 设备: {device_name}")
        for router_name, stats in valid_routers.items():
            log(f"  📶 路由器: {router_name}  成功: {stats.get('success', 0)}  失败: {stats.get('failure', 0)}")
            failed_rounds = [r for r in stats.get('rounds', []) if r.get('result') != 'success']
            if failed_rounds:
                for fr in failed_rounds:
                    timestamp = fr.get('timestamp', '未知时间')
                    log(f"    ❌ 轮次#{fr.get('round', '?')} 结果: {fr.get('result', '?')}  原因: {fr.get('message', '?')}  时间: {timestamp}")
            else:
                log("    ✅ 全部成功")
    
    if not has_data:
        log("⚠️ 没有可汇总的测试数据")
    
    # 生成Excel报告
    if has_data:
        try:
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # 尝试从多个位置查找 excel_report_generator.py
            # 查找顺序：1. common 目录 2. 当前目录 3. 蓝牙配网目录（向后兼容）
            search_paths = [
                os.path.join(os.path.dirname(current_dir), "common", "excel_report_generator.py"),
                os.path.join(current_dir, "excel_report_generator.py"),
                os.path.join(current_dir, "IOS", "excel_report_generator.py"),
                os.path.join(os.path.dirname(current_dir), "2蓝牙配网", "excel_report_generator.py"),
                os.path.join(os.path.dirname(current_dir), "2蓝牙配网", "IOS", "excel_report_generator.py"),
            ]
            
            excel_gen_path = None
            for path in search_paths:
                if os.path.exists(path):
                    excel_gen_path = path
                    log(f"✅ 找到 excel_report_generator.py: {path}")
                    break
            
            if excel_gen_path and os.path.exists(excel_gen_path):
                sys.path.insert(0, os.path.dirname(excel_gen_path))
                from excel_report_generator import create_network_compatibility_report
                
                log("\n📊 生成Excel测试报告...")
                
                # 转换数据结构：将 rounds 从列表格式转换为字典格式
                # excel_report_generator 期望 rounds 是字典 {round_number: {result, message}}
                converted_results = {}
                for device_name, device_data in detailed_results.items():
                    converted_results[device_name] = {"routers": {}}
                    for router_name, router_data in device_data["routers"].items():
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
                
                # 临时修改报告保存目录为 RUN_DIR
                # 直接传入 RUN_DIR，报告将保存到 reports 目录
                excel_file = create_network_compatibility_report(
                    converted_results, 
                    platform="iOS", 
                    network_method="1扫码配网",
                    output_dir=str(RUN_DIR) if RUN_DIR else None
                )
                log(f"✅ Excel报告已生成: {excel_file}")
            else:
                log(f"⚠️ 未找到 excel_report_generator.py，跳过Excel报告生成")
                log(f"   已搜索以下路径:")
                for path in search_paths:
                    log(f"     - {path}")
        except Exception as e:
            log(f"⚠️ Excel报告生成失败: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
    else:
        log("⚠️ 无测试数据，跳过Excel报告生成")


# ==================== 主入口：多设备 / 多路由 ====================

def main():
    log("🚀 启动 iOS 扫码配网脚本")
    log("=" * 80)

    cfg = load_config()
    if not cfg:
        return

    device_cfgs = cfg.get("device_configs", {})
    wifi_cfgs = cfg.get("wifi_configs", [])
    test_cfg = cfg.get("test_config", {})
    loop_per_router = int(test_cfg.get("loop_count_per_router", 1))

    log(f"📱 iOS 设备数量: {len(device_cfgs)}")
    log(f"📶 路由器数量: {len(wifi_cfgs)}")
    log(f"🔁 每个路由器循环次数: {loop_per_router}")

    total = 0
    succ = 0
    fail = 0
    detailed_results = {}
    interrupted = False

    try:
        for dev_key, dev_cfg in device_cfgs.items():
            device_name = dev_cfg.get('description', dev_cfg['device_name'])
            log(f"\n📱 当前测试设备: {device_name}")
            log("-" * 60)
            
            driver = create_driver(dev_cfg)
            if not driver:
                log("❌ 该设备 driver 创建失败，跳过")
                continue
            
            if device_name not in detailed_results:
                detailed_results[device_name] = {"routers": {}}
            
            try:
                for wifi in wifi_cfgs:
                    name = wifi["name"]
                    pwd = wifi["password"]
                    log(f"\n📶 路由器: {name}")
                    
                    if name not in detailed_results[device_name]["routers"]:
                        detailed_results[device_name]["routers"][name] = {
                            "success": 0,
                            "failure": 0,
                            "rounds": []
                        }
                    
                    for i in range(loop_per_router):
                        log(f"\n🔄 第 {i+1}/{loop_per_router} 次测试")
                        total += 1
                        
                        test_timestamp = datetime.now().strftime("%H:%M:%S")
                        res, msg = run_single_flow(driver, name, pwd)
                        
                        round_record = {
                            "round": i + 1,
                            "result": res,
                            "message": msg,
                            "timestamp": test_timestamp
                        }
                        detailed_results[device_name]["routers"][name]["rounds"].append(round_record)
                        
                        if res == "success":
                            succ += 1
                            detailed_results[device_name]["routers"][name]["success"] += 1
                            log(f"✅ 测试成功: {msg}")
                        else:
                            fail += 1
                            detailed_results[device_name]["routers"][name]["failure"] += 1
                            log(f"❌ 测试失败: {msg}")
                        
                        if i < loop_per_router - 1:
                            log("⏳ 等待 10 秒后进行下一次测试...")
                            time.sleep(10)
            except KeyboardInterrupt:
                interrupted = True
                log("\n⚠️ 用户中断当前设备测试，已保存已完成的数据")
                raise
            except Exception as e:
                log(f"❌ 设备 {device_name} 测试异常: {e}")
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass
    
    except KeyboardInterrupt:
        interrupted = True
        log("\n⚠️ 用户中断测试，正在生成报告...")
    except Exception as e:
        log(f"\n❌ 测试异常: {e}")
        import traceback
        log(f"详细错误: {traceback.format_exc()}")
    finally:
        finalize_results(total, succ, fail, detailed_results, test_cfg, interrupted=interrupted)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n⚠️ 用户中断脚本")
    except Exception as e:
        log(f"\n❌ 脚本异常: {e}")
        import traceback
        log(f"详细错误: {traceback.format_exc()}")

