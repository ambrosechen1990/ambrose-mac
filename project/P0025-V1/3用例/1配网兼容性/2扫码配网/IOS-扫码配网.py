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

# P0025-V1：脚本在 3用例/1配网兼容性/2扫码配网/，共用脚本在项目根下 1共用脚本/
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_P0025_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", ".."))
SHARED_SCRIPTS_DIR = os.path.join(_P0025_PROJECT_ROOT, "1共用脚本")

# 尝试导入 report_utils（优先 1共用脚本，其次兼容旧路径）
try:
    from report_utils import init_run_env
except ImportError:
    sys.path.insert(0, SHARED_SCRIPTS_DIR)
    try:
        from report_utils import init_run_env
    except ImportError:
        common_path = os.path.join(os.path.dirname(_SCRIPT_DIR), "common")
        sys.path.insert(0, common_path)
        try:
            from report_utils import init_run_env
        except ImportError:
            sys.path.insert(0, os.path.join(os.path.dirname(_SCRIPT_DIR), "2蓝牙配网"))
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

    # 2. 1共用脚本 目录（优先）
    base_dir = os.path.dirname(os.path.abspath(__file__))
    shared_cfg = os.path.join(SHARED_SCRIPTS_DIR, "device_config.json")
    if os.path.exists(shared_cfg):
        try:
            with open(shared_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log(f"✅ 从 1共用脚本 加载配置: {shared_cfg}")
            return _filter_ios_devices(cfg)
        except Exception as e:
            log(f"⚠️ 加载 1共用脚本 配置失败: {e}")

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
SERIAL_PORT = os.environ.get("ROBOT_SERIAL_PORT", "/dev/tty.usbserial-1120")
SERIAL_BAUD = os.environ.get("ROBOT_SERIAL_BAUD", "115200")
SERIAL_TRIGGER_CMD = os.environ.get("ROBOT_SERIAL_CMD", "SET state 4")

# 向后兼容：机器人热点触发所需的设备ID（已废弃，改用串口方式）
ROBOT_DEVICE_ID = os.environ.get("ROBOT_DEVICE_ID", "galaxy_p0001")


def _find_available_serial_ports() -> list:
    """查找所有可用的串口设备"""
    available_ports = []
    try:
        import glob

        tty_ports = glob.glob("/dev/tty.usbserial*") + glob.glob("/dev/tty.usbmodem*")
        cu_ports = glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*")

        all_ports = list(set(tty_ports + cu_ports))
        for port in all_ports:
            if os.path.exists(port) and os.access(port, os.R_OK):
                available_ports.append(port)

        available_ports.sort(key=lambda x: ("usbserial" not in x, x))
    except Exception as e:
        log(f"⚠️ 查找串口设备失败: {e}")
    return available_ports


def _resolve_serial_port_for_hotspot() -> tuple:
    """
    解析用于触发热点的 USB 串口路径。
    优先级：ROBOT_SERIAL_PORT（存在且可读） > 内置默认 tty 路径 > 自动枚举（macOS 优先 /dev/cu.*）。
    返回 (path_or_None, 说明字符串)。
    """
    import platform

    def _pick_from_list(ports: list) -> str | None:
        if not ports:
            return None
        if platform.system() == "Darwin":
            cu = sorted(p for p in ports if p.startswith("/dev/cu."))
            if cu:
                return cu[0]
        tty_usb = sorted(
            p for p in ports if "/tty." in p and ("usbserial" in p or "usbmodem" in p)
        )
        if tty_usb:
            return tty_usb[0]
        return sorted(ports)[0]

    explicit = (os.environ.get("ROBOT_SERIAL_PORT") or "").strip()
    candidates = _find_available_serial_ports()

    if explicit:
        if os.path.exists(explicit) and os.access(explicit, os.R_OK):
            return explicit, "环境变量 ROBOT_SERIAL_PORT"
        log(f"⚠️ ROBOT_SERIAL_PORT={explicit} 不存在或无读权限，改为自动检测本机串口…")
        picked = _pick_from_list(candidates)
        if picked:
            return picked, "自动检测（环境变量指定端口不可用）"
        return None, ""

    guess = SERIAL_PORT
    if os.path.exists(guess) and os.access(guess, os.R_OK):
        return guess, "默认/内置路径"

    picked = _pick_from_list(candidates)
    if picked:
        return picked, "自动检测（默认路径不存在）"
    return None, ""


def trigger_robot_hotspot() -> bool:
    """
    触发机器热点（P0024-M0：使用端口命令脚本）
    优先使用端口命令.py脚本，如果失败则回退到expect方式
    """
    log("📡 步骤1: 触发机器热点（USB 串口；与 Appium TCP port 无关）…")
    port, port_src = _resolve_serial_port_for_hotspot()
    baud = int(os.environ.get("ROBOT_SERIAL_BAUD", str(SERIAL_BAUD)))
    cmd = os.environ.get("ROBOT_SERIAL_CMD", SERIAL_TRIGGER_CMD)

    if not port:
        log("❌ 未找到可用 USB 串口，无法触发热点")
        return False
    log(f"📌 串口: {port}（{port_src}）")

    candidate_scripts = [
        os.path.join(SHARED_SCRIPTS_DIR, "端口命令.py"),
        os.path.join(os.path.dirname(_SCRIPT_DIR), "common", "端口命令.py"),
        os.path.join(os.path.dirname(_SCRIPT_DIR), "2蓝牙配网", "端口命令.py"),
    ]
    port_command_script = next((p for p in candidate_scripts if os.path.exists(p)), "")

    if port_command_script:
        log(f"📝 找到端口命令脚本: {port_command_script}")
        try:
            result = subprocess.run(
                [sys.executable, port_command_script,
                 '--port', port,
                 '--baud', str(baud),
                 '--command', cmd],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                if result.stdout and result.stdout.strip():
                    log(f"ℹ️ 端口命令脚本 stdout: {result.stdout.strip()}")
                if result.stderr and result.stderr.strip():
                    log(f"ℹ️ 端口命令脚本 stderr: {result.stderr.strip()}")
                log("✅ 串口热点触发成功")
                return True
            else:
                if result.stdout and result.stdout.strip():
                    log(f"⚠️ 端口命令脚本 stdout: {result.stdout.strip()}")
                if result.stderr and result.stderr.strip():
                    log(f"⚠️ 端口命令脚本 stderr: {result.stderr.strip()}")
                log("⚠️ 端口命令脚本触发失败，回退到expect方式...")
        except Exception as e:
            log(f"⚠️ 端口命令脚本执行异常: {e}，回退到expect方式...")
    else:
        log("⚠️ 未找到端口命令脚本，使用expect方式...")

    log("🔌 使用expect方式触发热点（备用方案）...")
    trigger_count = 2
    success_count = 0

    for trigger_num in range(1, trigger_count + 1):
        try:
            log(f"🔌 第 {trigger_num}/{trigger_count} 次触发（expect方式）...")

            expect_script = f"""#!/usr/bin/expect -f
set timeout 40
log_user 0
spawn screen {port} {baud}
sleep 3
send "\\r"
sleep 2
send "{cmd}\\r"
sleep 3
send "{cmd}\\r"
sleep 3
send "\\x01d"
sleep 1
expect eof
"""

            script_path = '/tmp/ios_qr_serial_trigger_hotspot.exp'
            try:
                with open(script_path, 'w') as f:
                    f.write(expect_script)
                os.chmod(script_path, 0o755)
            except Exception as e:
                log(f"❌ 生成expect脚本失败: {e}")
                continue

            result = subprocess.run(
                ['expect', script_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                if result.stdout and result.stdout.strip():
                    log(f"ℹ️ expect stdout: {result.stdout.strip()}")
                if result.stderr and result.stderr.strip():
                    log(f"ℹ️ expect stderr: {result.stderr.strip()}")
                log(f"✅ 第 {trigger_num} 次串口热点触发成功（expect方式）")
                success_count += 1
                if trigger_num < trigger_count:
                    time.sleep(3)
            else:
                if result.stdout and result.stdout.strip():
                    log(f"⚠️ expect stdout: {result.stdout.strip()}")
                if result.stderr and result.stderr.strip():
                    log(f"⚠️ expect stderr: {result.stderr.strip()}")
                log(f"⚠️ 第 {trigger_num} 次触发失败（expect方式）")
                if trigger_num < trigger_count:
                    time.sleep(3)

        except Exception as e:
            log(f"⚠️ 第 {trigger_num} 次触发异常: {e}")
            if trigger_num < trigger_count:
                time.sleep(3)

    if success_count > 0:
        log(f"✅ 已完成 {trigger_count} 次串口热点触发（成功 {success_count} 次）")
        return True

    log("❌ 所有触发方式都失败")
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
            '//XCUIElementTypeStaticText[contains(@name,"iSkim")]',
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
    检测首页状态并确保有add按钮
    新流程：
    1. 先检查首页是否有 device down unsel 按钮
    2. 如果有，执行删除设备操作
    3. 如果没有，查找页面的 add 按钮
    4. 循环检查，直至出现home add按钮
    """
    for attempt in range(3):
        log(f"🔁 检查首页状态（第 {attempt+1}/3 次）")
        
        # 步骤1: 先检查是否有 device down unsel 按钮
        try:
            device_down_btn = driver.find_element(
                AppiumBy.XPATH, 
                '//XCUIElementTypeButton[@name="device down unsel"]'
            )
            if device_down_btn.is_displayed():
                log("✅ 检测到 device down unsel 按钮，执行删除设备操作...")
                if not _remove_existing_device(driver):
                    log("⚠️ 删除设备失败")
                    if attempt < 2:
                        time.sleep(3)
                        continue
                    return False
                # 删除设备后，等待页面刷新，然后再次检查
                log("⏳ 等待页面刷新后检查 add 按钮...")
                time.sleep(3)
                # 删除后继续循环，检查是否有 add 按钮
                continue
        except Exception:
            # 没有找到 device down unsel 按钮，继续检查 add 按钮
            log("ℹ️ 未找到 device down unsel 按钮，检查 add 按钮...")
        
        # 步骤2: 检查是否有home add按钮（严格匹配，只检查首页的add按钮）
        if _home_has_add_button(driver):
            log("✅ add device 按钮已就绪")
            return True
        
        # 如果第一次检查失败，等待页面加载
        if attempt == 0:
            log("⚠️ 未找到 add 按钮，等待页面加载...")
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


def handle_permission_popup(driver) -> bool:
    """
    处理权限请求弹框（当蓝牙关闭时会出现）
    流程：
    1. 检测页面是否有权限请求弹框
    2. 如果有，点击 Cancel 按钮
    3. 继续扫码配网流程
    """
    log("🔍 检测权限请求弹框...")
    
    # 等待弹框出现（如果存在）
    time.sleep(2)
    
    # 检测权限弹框的特征元素
    permission_popup_indicators = [
        '//XCUIElementTypeButton[@name="Cancel"]',
        '//XCUIElementTypeButton[@name="Confirm"]',
        '//XCUIElementTypeStaticText[contains(@name,"permissions")]',
        '//XCUIElementTypeStaticText[contains(@name,"permission")]',
        '//XCUIElementTypeStaticText[contains(@name,"Bluetooth")]',
    ]
    
    popup_found = False
    for indicator in permission_popup_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                log(f"✅ 检测到权限请求弹框（指示器: {indicator}）")
                popup_found = True
                break
        except Exception:
            continue
    
    if not popup_found:
        log("ℹ️ 未检测到权限请求弹框，继续扫码配网流程")
        return True
    
    # 如果检测到弹框，点击 Cancel 按钮
    log("🔍 点击 Cancel 按钮关闭权限弹框...")
    cancel_selectors = [
        '//XCUIElementTypeButton[@name="Cancel"]',
        '//XCUIElementTypeButton[contains(@name,"Cancel")]',
        '//XCUIElementTypeButton[contains(@name,"取消")]',
    ]
    
    cancel_clicked = False
    for selector in cancel_selectors:
        try:
            cancel_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            if cancel_btn.is_displayed():
                cancel_btn.click()
                log(f"✅ 点击 Cancel 按钮成功（选择器: {selector}）")
                time.sleep(2)
                cancel_clicked = True
                break
        except Exception as e:
            log(f"⚠️ Cancel按钮选择器失败: {selector} - {e}")
            continue
    
    if not cancel_clicked:
        log("⚠️ 未找到 Cancel 按钮，尝试其他方式关闭弹框...")
        # 尝试点击弹框外部区域或使用返回键
        try:
            # 尝试按返回键
            driver.back()
            time.sleep(2)
            log("✅ 使用返回键关闭弹框")
        except Exception as e:
            log(f"⚠️ 返回键也失败: {e}")
            take_screenshot(driver, "permission_popup_close_fail")
            return False
    
    # 再次检测弹框是否已关闭
    time.sleep(1)
    popup_still_exists = False
    for indicator in permission_popup_indicators[:2]:  # 只检查按钮
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                popup_still_exists = True
                break
        except Exception:
            continue
    
    if popup_still_exists:
        log("⚠️ 弹框仍然存在，尝试再次关闭...")
        # 再次尝试点击 Cancel
        for selector in cancel_selectors:
            try:
                cancel_btn = driver.find_element(AppiumBy.XPATH, selector)
                if cancel_btn.is_displayed():
                    cancel_btn.click()
                    time.sleep(2)
                    log("✅ 再次点击 Cancel 按钮成功")
                    break
            except Exception:
                continue
    
    log("✅ 权限弹框处理完成，继续扫码配网流程")
    return True


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
    
    # 如果还没有跳转到WiFi设置页面，使用坐标点击的方式尽量“唤出/点中”扫码框
    log("🔍 点击扫描框（主要使用坐标点击），确保扫描框可见...")
    time.sleep(2)  # 等待页面稳定

    # 固定多个候选坐标（相对屏幕比例），在实际运行中效果最好的是第一个位置
    try:
        size = driver.get_window_size()
        screen_width = size["width"]
        screen_height = size["height"]

        scan_positions = [
            (screen_width // 2, int(screen_height * 0.25)),  # 经验位置1：效果最好
            (screen_width // 2, int(screen_height * 0.3)),
            (screen_width // 2, int(screen_height * 0.35)),
        ]

        for idx, (x, y) in enumerate(scan_positions, start=1):
            try:
                log(f"🔍 尝试扫描区域坐标 {idx}/{len(scan_positions)}: ({x}, {y})")
                driver.tap([(x, y)], 150)
                time.sleep(1.5)

                # 每次点击后立即检查是否已进入 WiFi 设置页面
                for indicator in wifi_setup_indicators:
                    try:
                        elem = driver.find_element(AppiumBy.XPATH, indicator)
                        if elem.is_displayed():
                            log(f"✅ 通过坐标点击扫描区域成功，已跳转到WiFi设置页面: {indicator}")
                            time.sleep(2)
                            return True
                    except Exception:
                        continue
            except Exception as e:
                log(f"⚠️ 坐标点击 ({x},{y}) 失败: {e}")
                continue
    except Exception as e:
        log(f"⚠️ 获取屏幕尺寸或坐标点击异常: {e}")
    
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

def _detect_current_page(driver) -> str:
    """
    检测 iOS 当前页面类型
    返回: "wifi_list", "settings_apps", "wifi_password", "unknown"
    """
    # 1. WiFi 列表页面
    wifi_list_indicators = [
        '//XCUIElementTypeNavigationBar[@name="无线局域网"]',
        '//XCUIElementTypeNavigationBar[@name="Settings"]',
        '//XCUIElementTypeStaticText[@name="WLAN"]',
        '//XCUIElementTypeButton[@name="WLAN"]',
    ]
    for xp in wifi_list_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                return "wifi_list"
        except Exception:
            continue
    
    # 检查 NavigationBar
    try:
        nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
        for nav in nav_bars:
            try:
                nav_name = nav.get_attribute("name") or ""
                if "无线局域网" in nav_name or "WLAN" in nav_name:
                    return "wifi_list"
            except Exception:
                pass
    except Exception:
        pass
    
    # 2. 系统设置 Apps 页面（高系统版本）
    apps_indicators = [
        '//XCUIElementTypeNavigationBar[@name="Apps"]',
        '//XCUIElementTypeStaticText[@name="Apps"]',
        '//XCUIElementTypeButton[@name="Apps"]',
        '//XCUIElementTypeCell[@name="Apps"]',
        '//XCUIElementTypeStaticText[contains(@name,"Apps")]',
    ]
    # 检查NavigationBar
    try:
        nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
        for nav in nav_bars:
            try:
                nav_name = nav.get_attribute("name") or ""
                if "Apps" in nav_name:
                    return "settings_apps"
            except Exception:
                pass
    except Exception:
        pass
    
    for xp in apps_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                    return "settings_apps"
        except Exception:
            continue
    
    # 增强检测：检查页面上的所有可见文本，看是否包含"Apps"
    try:
        all_text_elements = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeStaticText | //XCUIElementTypeButton | //XCUIElementTypeCell")
        for elem in all_text_elements:
            try:
                if not elem.is_displayed():
                    continue
                text = elem.get_attribute("name") or elem.get_attribute("label") or ""
                if text and "Apps" in text:
                    log(f"🔍 通过文本检测到Apps页面: {text[:50]}")
                    return "settings_apps"
            except Exception:
                continue
    except Exception:
        pass
    
    # 增强检测：如果页面有返回按钮，且不是WiFi列表页面，可能是Apps页面
    # 检查是否有返回按钮
    try:
        back_buttons = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Back"] | //XCUIElementTypeButton[contains(@name,"返回")]')
        has_back_button = False
        for btn in back_buttons:
            try:
                if btn.is_displayed():
                    has_back_button = True
                    break
            except Exception:
                continue
        
        # 如果有返回按钮，且不是WiFi列表页面，可能是Apps页面
        if has_back_button:
            # 检查是否在系统设置中（通过检查是否有Settings相关的元素）
            settings_indicators = [
                '//XCUIElementTypeNavigationBar[contains(@name,"Settings")]',
                '//XCUIElementTypeStaticText[contains(@name,"Settings")]',
            ]
            is_in_settings = False
            for xp in settings_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, xp)
                    if elem.is_displayed():
                        is_in_settings = True
                        break
                except Exception:
                    continue
            
            if is_in_settings:
                # 在系统设置中，有返回按钮，但不是WiFi列表，很可能是Apps页面
                log("🔍 通过返回按钮+系统设置检测，可能是Apps页面")
                return "settings_apps"
    except Exception:
        pass
    
    # 3. WiFi 密码输入页面（App 内）
    wifi_password_indicators = [
        '//XCUIElementTypeButton[@name="pair net change wifi"]',
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeButton[@name="Next"]',
    ]
    for xp in wifi_password_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                return "wifi_password"
        except Exception:
            continue
    
    return "unknown"


def _click_back_button(driver) -> bool:
    """点击 iOS 返回按钮"""
    back_selectors = [
        '//XCUIElementTypeButton[@name="Back"]',
        '//XCUIElementTypeButton[contains(@name,"返回")]',
        '//XCUIElementTypeNavigationBar//XCUIElementTypeButton[1]',
    ]
    for selector in back_selectors:
        try:
            btn = driver.find_element(AppiumBy.XPATH, selector)
            if btn.is_displayed():
                btn.click()
                log("✅ 点击返回按钮成功")
                return True
        except Exception:
            continue
    # 尝试使用 driver.back()
    try:
        driver.back()
        log("✅ 使用 driver.back() 返回成功")
        return True
    except Exception:
        return False


def _enter_wifi_list_page(driver) -> bool:
    """
    从 App 内点击"切换 WiFi"进入系统 WiFi 列表
    处理新旧系统差异：
    - 高系统：点击后跳转到系统设置Apps页面，需要返回后点击WLAN按钮
    - 老系统：点击后直接跳转到WiFi列表页面
    """
    log("📶 步骤4: 进入系统 WiFi 页面...")
    
    # 1. 点击切换WiFi按钮
    try:
        btn = driver.find_element(
            AppiumBy.XPATH, '//XCUIElementTypeButton[@name="pair net change wifi"]'
        )
        btn.click()
        log("✅ 点击切换 WiFi 按钮成功")
        time.sleep(3)
    except Exception as e:
        log(f"❌ 点击切换 WiFi 按钮失败: {e}")
        take_screenshot(driver, "click_change_wifi_fail")
        return False
    
    # 2. 检测当前页面类型
    log("🔍 检测页面类型...")
    page_type = None
    for attempt in range(2):
        page_type = _detect_current_page(driver)
        log(f"📄 第 {attempt+1}/2 次检测，当前页面类型: {page_type}")
        
        # 如果是unknown，输出调试信息
        if page_type == "unknown":
            log("🔍 页面类型为unknown，输出调试信息...")
            try:
                # 检查NavigationBar
                nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
                visible_navs = []
                for nav in nav_bars:
                    try:
                        if nav.is_displayed():
                            nav_name = nav.get_attribute("name") or ""
                            visible_navs.append(nav_name)
                    except Exception:
                        continue
                if visible_navs:
                    log(f"   可见的NavigationBar: {visible_navs}")
                
                # 检查前10个可见文本元素
                text_elems = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeStaticText | //XCUIElementTypeButton")
                visible_texts = []
                for elem in text_elems[:20]:  # 只检查前20个
                    try:
                        if elem.is_displayed():
                            text = elem.get_attribute("name") or elem.get_attribute("label") or ""
                            if text:
                                visible_texts.append(text[:30])  # 只取前30个字符
                    except Exception:
                        continue
                if visible_texts:
                    log(f"   可见文本元素（前10个）: {visible_texts[:10]}")
            except Exception as e:
                log(f"   调试信息获取失败: {e}")
        
        if page_type != "unknown":
            break
        if attempt < 1:
            log(f"⏳ 等待页面加载（{attempt+1}/2）...")
            time.sleep(2)
    
    log(f"📄 最终页面类型: {page_type}")
    
    # 3. 如果已经在WiFi列表页面，直接返回成功
    if page_type == "wifi_list":
        log("✅ 已在WiFi列表页面，无需额外操作")
        return True
    
    # 3.1 如果直接跳转到WiFi密码输入页面（某些系统可能跳过WiFi列表）
    if page_type == "wifi_password":
        log("✅ 检测到直接跳转到WiFi密码输入页面，跳过WiFi列表选择步骤")
        return True
    
    # 4. 如果在系统设置Apps页面（高系统），需要特殊处理
    if page_type == "settings_apps":
        log("🔄 检测到高系统：在系统设置Apps页面，执行以下步骤：")
        log("   步骤1: 点击左上角返回按钮")
        log("   步骤2: 点击WLAN按钮")
        log("   步骤3: 进入WLAN页面，选择WiFi")
        
        # 4.1 点击左上角返回按钮
        log("📱 步骤4.1: 点击左上角返回按钮...")
        back_clicked = _click_back_button(driver)
        if not back_clicked:
            log("❌ 点击返回按钮失败，无法继续")
            take_screenshot(driver, "back_button_fail")
            return False
        
        # 4.2 等待页面加载，并验证是否成功返回
        log("⏳ 等待页面加载（返回后）...")
        time.sleep(3)
        
        # 验证是否成功返回（不应该还在Apps页面）
        current_page = _detect_current_page(driver)
        if current_page == "settings_apps":
            log("⚠️ 返回后仍在Apps页面，尝试再次返回...")
            if not _click_back_button(driver):
                log("❌ 再次返回失败")
                return False
            time.sleep(2)
            current_page = _detect_current_page(driver)
        
        log(f"📄 返回后页面类型: {current_page}")
        
        # 4.3 查找并点击WLAN按钮（com.apple.settings.wifi）
        log("📱 步骤4.2: 查找并点击WLAN按钮...")
        wlan_button_selectors = [
            '//XCUIElementTypeButton[@name="com.apple.settings.wifi"]',
            '//XCUIElementTypeButton[@name="WLAN"]',
            '//XCUIElementTypeStaticText[@name="WLAN"]',
            '//XCUIElementTypeCell[@name="WLAN"]',
            '//XCUIElementTypeButton[contains(@name,"WLAN")]',
            '//XCUIElementTypeButton[contains(@name,"Wi-Fi")]',
        ]
        
        wlan_clicked = False
        for selector in wlan_button_selectors:
            try:
                log(f"🔍 尝试WLAN按钮选择器: {selector}")
                btn = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if btn.is_displayed():
                    btn.click()
                    log(f"✅ 点击WLAN按钮成功: {selector}")
                    time.sleep(3)
                    wlan_clicked = True
                    break
            except Exception as e:
                log(f"⚠️ WLAN按钮选择器失败: {selector} - {str(e)[:100]}")
                continue
        
        if not wlan_clicked:
            log("❌ 未找到WLAN按钮，无法进入WLAN页面")
            take_screenshot(driver, "wlan_button_not_found")
            # 再次检测页面类型，看是否已经意外进入WiFi列表
            page_type = _detect_current_page(driver)
            if page_type == "wifi_list":
                log("✅ 意外检测到已在WiFi列表页面")
                return True
            return False
        
        # 4.4 再次检测是否成功进入WiFi列表页面
        log("📱 步骤4.3: 验证是否成功进入WLAN页面...")
        time.sleep(2)
        page_type = _detect_current_page(driver)
        log(f"📄 点击WLAN按钮后页面类型: {page_type}")
        
        if page_type == "wifi_list":
            log("✅ 成功进入WiFi列表页面，可以开始选择WiFi")
            return True
        else:
            log(f"⚠️ 点击WLAN按钮后，页面类型仍为: {page_type}，不是wifi_list")
            take_screenshot(driver, "wifi_list_not_found_after_wlan")
            # 即使检测失败，也尝试继续（向后兼容）
            log("⚠️ 但继续执行后续步骤（向后兼容）")
            return True
    
    # 5. 如果页面类型未知，尝试多种策略
    if page_type == "unknown":
        log("⚠️ 页面类型未知，尝试多种策略...")
        
        # 策略1: 检查是否在App内（可能已经返回App）
        try:
            app_indicators = [
                '//XCUIElementTypeButton[@name="pair net change wifi"]',
                '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
                '//XCUIElementTypeButton[@name="Next"]',
            ]
            for indicator in app_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, indicator)
                    if elem.is_displayed():
                        log(f"✅ 检测到已返回App内（可能是WiFi密码输入页面）: {indicator}")
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        
        # 策略2: 检查NavigationBar
        try:
            nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
            for nav in nav_bars:
                try:
                    nav_name = nav.get_attribute("name") or ""
                    if "无线局域网" in nav_name or "WLAN" in nav_name:
                        log(f"✅ 通过NavigationBar快速检测到WiFi列表页面: {nav_name}")
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        
        # 策略3: 检查是否是Apps页面（可能检测失败）- 使用更主动的检测方法
        log("🔍 策略3: 检查是否是Apps页面（可能检测失败）...")
        
        # 方法1: 检查所有可见文本元素
        is_apps_page = False
        try:
            all_text_elements = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeStaticText | //XCUIElementTypeButton | //XCUIElementTypeCell | //XCUIElementTypeNavigationBar")
            for elem in all_text_elements:
                try:
                    if not elem.is_displayed():
                        continue
                    text = elem.get_attribute("name") or elem.get_attribute("label") or ""
                    if text and "Apps" in text:
                        log(f"✅ 通过策略3（文本检测）检测到Apps页面: {text[:50]}")
                        is_apps_page = True
                        break
                except Exception:
                    continue
        except Exception:
            pass
        
        # 方法2: 检查NavigationBar
        if not is_apps_page:
            try:
                nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
                for nav in nav_bars:
                    try:
                        if not nav.is_displayed():
                            continue
                        nav_name = nav.get_attribute("name") or ""
                        if "Apps" in nav_name:
                            log(f"✅ 通过策略3（NavigationBar）检测到Apps页面: {nav_name}")
                            is_apps_page = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        
        # 方法3: 检查是否有返回按钮且在系统设置中
        if not is_apps_page:
            try:
                back_buttons = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Back"] | //XCUIElementTypeButton[contains(@name,"返回")]')
                has_back = False
                for btn in back_buttons:
                    try:
                        if btn.is_displayed():
                            has_back = True
                            break
                    except Exception:
                        continue
                
                if has_back:
                    # 检查是否在系统设置中
                    settings_check = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeNavigationBar[contains(@name,"Settings")]')
                    visible_settings = [s for s in settings_check if s.is_displayed()]
                    if visible_settings:
                        log("✅ 通过策略3（返回按钮+系统设置）检测到可能是Apps页面")
                        is_apps_page = True
            except Exception:
                pass
        
        if is_apps_page:
            log("🔄 在unknown情况下检测到Apps页面，执行高系统处理流程...")
            # 执行与settings_apps相同的处理流程
            if not _click_back_button(driver):
                log("❌ 点击返回按钮失败")
                return False
            time.sleep(3)
            
            # 点击WLAN按钮
            wlan_selectors = [
                '//XCUIElementTypeButton[@name="com.apple.settings.wifi"]',
                '//XCUIElementTypeButton[@name="WLAN"]',
            ]
            wlan_clicked = False
            for selector in wlan_selectors:
                try:
                    btn = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                    )
                    if btn.is_displayed():
                        btn.click()
                        log(f"✅ 点击WLAN按钮成功: {selector}")
                        time.sleep(3)
                        wlan_clicked = True
                        break
                except Exception:
                    continue
            
            if wlan_clicked:
                page_type = _detect_current_page(driver)
                if page_type == "wifi_list":
                    log("✅ 成功进入WiFi列表页面")
                    return True
        
        # 策略4: 重试检测
        for i in range(2):
            log(f"⏳ 等待页面加载后再次检测（{i+1}/2）...")
            time.sleep(2)
            page_type = _detect_current_page(driver)
            if page_type == "wifi_list":
                log("✅ 等待后检测到WiFi列表页面")
                return True
            elif page_type == "wifi_password":
                log("✅ 等待后检测到WiFi密码输入页面")
                return True
            elif page_type == "settings_apps":
                # 如果检测到Apps页面，重新处理
                log("🔄 等待后检测到Apps页面，重新处理...")
                if _click_back_button(driver):
                    time.sleep(3)
                    # 尝试点击WLAN按钮
                    for selector in ['//XCUIElementTypeButton[@name="com.apple.settings.wifi"]',
                                     '//XCUIElementTypeButton[@name="WLAN"]']:
                        try:
                            btn = WebDriverWait(driver, 8).until(
                                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                            )
                            if btn.is_displayed():
                                btn.click()
                                log(f"✅ 点击WLAN按钮成功: {selector}")
                                time.sleep(3)
                                if _detect_current_page(driver) == "wifi_list":
                                    log("✅ 成功进入WiFi列表页面")
                                    return True
                        except Exception:
                            continue

        log("⚠️ 未明显检测到 iOS 系统 WiFi 页面，后续仍按 WiFi 列表处理")
        return True
    
    # 默认返回True（向后兼容）
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
    
    # 首先尝试直接查找（仅在元素可见时认为成功；否则视为未找到，进入滑动逻辑）
    log("🔍 首先尝试直接查找 WiFi（不滑动）...")
    for xp in selectors:
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            if el.is_displayed():
                wifi_cell = el
                log(f"✅ 直接找到 WiFi 元素: {xp}")
                wifi_cell.click()
                log(f"✅ 已点击 WiFi: {ssid}")
                time.sleep(2)
                return True
        except Exception:
            continue
    
    # 如果直接查找失败或只找到不可见元素，向下滑动查找
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

    # 在清除密码后、点击Next前触发机器热点
    if not trigger_robot_hotspot():
        log("❌ 触发机器热点失败")
        return False

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
    """步骤2.1: 配网引导页：勾选 checkbox 后点击 Next，进入 connect robot hotspot 页面"""
    log("📋 步骤2.1: 配网引导页处理（checkbox + Next）进入 connect robot hotspot 页面...")
    try:
        # 等待页面稳定加载
        time.sleep(2)

        checkbox_xp = '//XCUIElementTypeButton[@name="pair net un sel"]'
        next_xp = '//XCUIElementTypeButton[@name="Next"]'

        def _dismiss_ios_save_password_popup() -> None:
            """
            iOS 可能弹出“保存密码？”系统弹框，挡住引导页元素。
            优先点“以后/Not Now”，失败不阻断主流程。
            """
            popup_btns = [
                '//XCUIElementTypeButton[@name="以后"]',
                '//XCUIElementTypeButton[@name="Not Now"]',
                '//XCUIElementTypeButton[@name="稍后"]',
                '//XCUIElementTypeButton[@name="取消"]',
                '//XCUIElementTypeButton[@name="Cancel"]',
                # 兜底：有些系统文案可能不同，但弹框标题含“保存密码”
                '//XCUIElementTypeAlert//XCUIElementTypeButton[1]',
            ]
            for xp in popup_btns:
                try:
                    btn = WebDriverWait(driver, 1).until(
                        EC.element_to_be_clickable((AppiumBy.XPATH, xp))
                    )
                    btn.click()
                    log(f"ℹ️ 检测到并已关闭“保存密码”弹框: {xp}")
                    time.sleep(0.8)
                    return
                except Exception:
                    continue

        # 先尝试处理一次“保存密码”弹框，避免遮挡后续操作
        _dismiss_ios_save_password_popup()

        # 1) 先尝试点击引导页 checkbox（蓝牙 iOS 参考逻辑）
        try:
            checkbox = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((AppiumBy.XPATH, checkbox_xp))
            )
            if checkbox.is_displayed():
                log("🧭 检测到配网引导页 checkbox，先勾选...")
                checkbox = WebDriverWait(driver, 6).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, checkbox_xp))
                )
                checkbox.click()
                time.sleep(1)
                log("✅ 引导页：已勾选 checkbox")
        except Exception:
            log("ℹ️ 未检测到配网引导页 checkbox，继续点击 Next")

        # 点击 Next 前再尝试关闭一次可能迟到出现的弹框
        _dismiss_ios_save_password_popup()

        # 2) 再点击 Next
        next_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, next_xp))
        )
        log("➡️ 配网引导页：点击 Next...")
        next_btn.click()
        log("✅ 已点击配网引导页 Next 按钮，等待进入connect robot hotspot页面...")
        time.sleep(3)  # 等待页面跳转到connect robot hotspot页面
        log("✅ 已进入connect robot hotspot页面")
        return True
    except Exception as e:
        log(f"❌ 配网引导页处理失败（checkbox/Next）: {e}")
        take_screenshot(driver, "pairing_guide_checkbox_next_fail")
        return False


# ==================== connect device hotspot页面 ====================

def handle_connect_hotspot(driver) -> bool:
    """
    步骤2.2: connect robot hotspot页面处理
    需求回退版本：
    1) 仅点击 Connect Robot Hotspot
    2) 系统弹窗不做处理（由系统/后续页面自己处理）
    3) 直接进入 wait_pairing_result
    """
    log("📡 步骤2.2: 处理connect robot hotspot页面...")

    log("⏳ 等待connect robot hotspot页面加载...")
    time.sleep(3)

    selectors = [
        '//XCUIElementTypeButton[@name="Connect Robot Hotspot"]',
        '//XCUIElementTypeButton[contains(@name,"Connect")]',
        '//XCUIElementTypeButton[contains(@name,"Hotspot")]',
    ]
    last_err = None

    for xp in selectors:
        try:
            log(f"🔍 尝试 Connect 按钮选择器: {xp}")
            connect_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, xp))
            )
            connect_btn.click()
            log("✅ 已点击 Connect Robot Hotspot，后续交给 wait_pairing_result 处理")
            time.sleep(2)
            return True
        except Exception as e:
            last_err = e
            continue

    log(f"❌ 点击Connect Robot Hotspot按钮失败: {last_err}")
    take_screenshot(driver, "connect_robot_hotspot_btn_fail")
    return False


# ==================== 配网进度 & 结果 ====================

def wait_pairing_result(driver, timeout: int = 180) -> str:
    """
    等待配网结果：success / failed / timeout
    先确认是否在配网页面（检查是否有"Pairing with your device (1/2)"）
    """
    log("⏳ 步骤7: 等待配网结果...")
    
    # 强化成功判定：有些机型/网络情况下不会出现 "Pairing with your device (1/2)"
    def _is_home_after_pairing(drv) -> bool:
        home_xpaths = [
            '//XCUIElementTypeButton[@name="home add device"]',
            '//XCUIElementTypeButton[@name="home add"]',
            # 首页信息（不同语言包/版本名称可能不同）
            '//XCUIElementTypeStaticText[contains(@name,"AquaSense")]',
            '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
            '//XCUIElementTypeStaticText[contains(@name,"设备")]',
            '//XCUIElementTypeStaticText[contains(@name,"robot")]',
        ]
        for xp in home_xpaths:
            try:
                elem = drv.find_element(AppiumBy.XPATH, xp)
                if elem.is_displayed():
                    return True
            except Exception:
                continue
        return False
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            # 优先：回首页（很多情况下配网成功后直接展示首页/设备列表）
            if _is_home_after_pairing(driver):
                log("✅ 配网成功（回到首页/首页强特征命中）")
                return "success"

            # 配网进行中页面（可选）
            try:
                pairing_indicator = '//XCUIElementTypeStaticText[@name="Pairing with your device (1/2)"]'
                txt = driver.find_element(AppiumBy.XPATH, pairing_indicator)
                if txt.is_displayed():
                    log("🔄 配网进行中 ...")
                    time.sleep(5)
                    continue
            except Exception:
                # 找不到进度文案不代表失败，继续等成功/失败特征
                pass

            # 成功：首页出现新设备
            success_xpaths = [
                '//XCUIElementTypeStaticText[@name="iSkim"]',
                '//XCUIElementTypeStaticText[contains(@name,"iSkim")]',
                '//XCUIElementTypeStaticText[contains(@name,"设备")]',
                # 兼容某些机型：直接显示设备名/序列号片段
                '//XCUIElementTypeStaticText[contains(@name,"iSkim")]',
                '//XCUIElementTypeStaticText[contains(@name,"0053")]',
                '//XCUIElementTypeStaticText[contains(@name,"Beatbot")]',
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

    if not ensure_home_add_button(driver):
        return "error", "首页缺少 add 按钮"

    if not tap_add_device(driver):
        return "error", "点击 add 按钮失败"

    # 处理权限请求弹框（当蓝牙关闭时会出现）
    if not handle_permission_popup(driver):
        log("⚠️ 权限弹框处理失败，但继续尝试扫码配网")

    if not scan_qr_code(driver):
        return "error", "扫描二维码失败或超时"

    if not perform_wifi_setup(driver, wifi_name, wifi_pwd):
        return "error", "WiFi 设置失败"

    if not handle_pairing_guide(driver):
        return "error", "配网引导页处理失败"

    # 按新流程：配网引导页后直接进入配网进程，不再处理 connect hotspot 页面
    log("ℹ️ 新流程：引导页完成后直接进入配网结果等待（跳过 connect hotspot 处理）")

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
        if total_tests > 0 and detailed_results:
            log("⚠️ 没有可汇总的测试数据（可能中断在进行中），仍将尝试生成报告占位文件")
        else:
            log("⚠️ 没有可汇总的测试数据")
    
    # 生成Excel报告
    # 兼容：
    # - driver 创建失败会导致 total_tests==0 / detailed_results 为空，但你仍希望落一份报告文件便于留痕排查
    # - 中断发生在单轮内部时，success/failure 仍为 0，也希望能产出占位报告
    should_generate_excel = True
    if should_generate_excel:
        try:
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # 尝试从多个位置查找 excel_report_generator.py
            # 查找顺序：1. 1共用脚本 2. common 目录 3. 当前目录 4. 蓝牙配网目录（向后兼容）
            search_paths = [
                os.path.join(SHARED_SCRIPTS_DIR, "excel_report_generator.py"),
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
                
                # 报告统一保存到 P0025-V1/2测试报告（对齐当前项目规则）
                report_output_dir = os.path.join(_P0025_PROJECT_ROOT, "2测试报告")
                excel_file = create_network_compatibility_report(
                    converted_results or {},
                    platform="iOS", 
                    network_method="1扫码配网",
                    output_dir=str(report_output_dir)
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

