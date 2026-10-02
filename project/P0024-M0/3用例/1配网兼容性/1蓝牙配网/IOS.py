#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全新 iOS 蓝牙配网脚本（按最新流程图实现）

注意：
- 不复用旧版 IOS-IOS.py 的实现，仅参考相同业务流程。
- 目前以“单线程串行跑多设备 / 多路由”为目标，后续如需扩展可再拆分。
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

# P0025-V1：脚本在 3用例/1配网兼容性/1蓝牙配网/，共用脚本在仓库根下 1共用脚本/（旧工程曾用 common/）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_P0025_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", ".."))
SHARED_SCRIPTS_DIR = os.path.join(_P0025_PROJECT_ROOT, "1共用脚本")

# 尝试导入 report_utils（优先已安装路径，否则加入 1共用脚本）
try:
    from report_utils import init_run_env
except ImportError:
    sys.path.insert(0, SHARED_SCRIPTS_DIR)
    from report_utils import init_run_env

# ==================== 日志与输出目录初始化 ====================

# 为 iOS 配网任务创建本次运行的输出目录
RUN_DIR, LOG_FILE, SCREENSHOT_DIR = init_run_env(prefix="2蓝牙配网-iOS")

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

# 导入测试报告模块（在 log 函数定义之后）
test_report_module = None
try:
    import importlib.util
    test_report_file = os.path.join(SHARED_SCRIPTS_DIR, "测试报告.py")
    if not os.path.exists(test_report_file):
        test_report_file = os.path.join(SHARED_SCRIPTS_DIR, "2测试报告.py")
    if os.path.exists(test_report_file):
        spec = importlib.util.spec_from_file_location("测试报告", test_report_file)
        if spec and spec.loader:
            测试报告 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(测试报告)
            test_report_module = 测试报告
            log(f"✅ 已加载测试报告模块: {os.path.basename(test_report_file)}")
    else:
        log(f"⚠️ 未找到测试报告模块: {test_report_file}")
except Exception as e:
    log(f"⚠️ 无法加载测试报告模块: {e}")


# ==================== 导入独立的设备选择模块 ====================

# 导入独立的设备选择模块（在 log 函数定义之后）
select_device_from_module = None
try:
    # 由于文件名包含中文，使用 importlib 动态导入
    import importlib.util
    device_selector_file = os.path.join(SHARED_SCRIPTS_DIR, "选择设备.py")
    if os.path.exists(device_selector_file):
        spec = importlib.util.spec_from_file_location("device_selector", device_selector_file)
        if spec and spec.loader:
            device_selector_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(device_selector_module)
            # 使用模块中的 select_device 函数
            select_device_from_module = device_selector_module.select_device
            log("✅ 已加载独立设备选择模块: 选择设备.py")
        else:
            log("⚠️ 无法加载独立设备选择模块（spec 加载失败），将使用内置函数")
    else:
        log(f"⚠️ 未找到独立设备选择模块: {device_selector_file}，将使用内置函数")
except Exception as e:
    log(f"⚠️ 无法加载独立设备选择模块，将使用内置函数: {e}")

# 导入 WiFi 选择模块
wifi_setup_module = None
try:
    import importlib.util
    wifi_setup_file = os.path.join(SHARED_SCRIPTS_DIR, "选择WIFI.py")
    if os.path.exists(wifi_setup_file):
        spec = importlib.util.spec_from_file_location("wifi_setup", wifi_setup_file)
        if spec and spec.loader:
            wifi_setup_module_obj = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wifi_setup_module_obj)
            wifi_setup_module = wifi_setup_module_obj
            log("✅ 已加载 WiFi 选择模块: 选择WIFI.py")
    else:
        log(f"⚠️ 未找到 WiFi 选择模块: {wifi_setup_file}，将使用内置函数")
except Exception as e:
    log(f"⚠️ 无法加载 WiFi 选择模块，将使用内置函数: {e}")

# 导入重置应用模块
reset_app_module = None
try:
    import importlib.util
    reset_app_file = os.path.join(SHARED_SCRIPTS_DIR, "重置应用-iOS.py")
    if os.path.exists(reset_app_file):
        spec = importlib.util.spec_from_file_location("重置应用", reset_app_file)
        if spec and spec.loader:
            重置应用 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(重置应用)
            reset_app_module = 重置应用
            log("✅ 已加载重置应用模块: 重置应用-iOS.py")
    else:
        log(f"⚠️ 未找到重置应用模块: {reset_app_file}")
except Exception as e:
    log(f"⚠️ 无法加载重置应用模块: {e}")

# 导入删除设备模块
delete_device_module = None
try:
    import importlib.util
    delete_device_file = os.path.join(SHARED_SCRIPTS_DIR, "删除设备-iOS.py")
    if os.path.exists(delete_device_file):
        spec = importlib.util.spec_from_file_location("删除设备", delete_device_file)
        if spec and spec.loader:
            删除设备 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(删除设备)
            delete_device_module = 删除设备
            log("✅ 已加载删除设备模块: 删除设备-iOS.py")
    else:
        log(f"⚠️ 未找到删除设备模块: {delete_device_file}")
except Exception as e:
    log(f"⚠️ 无法加载删除设备模块: {e}")

# 导入配网结果模块
pairing_result_module = None
try:
    import importlib.util
    pairing_result_file = os.path.join(SHARED_SCRIPTS_DIR, "配网结果-iOS.py")
    if os.path.exists(pairing_result_file):
        spec = importlib.util.spec_from_file_location("配网结果", pairing_result_file)
        if spec and spec.loader:
            配网结果 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(配网结果)
            pairing_result_module = 配网结果
            log("✅ 已加载配网结果模块: 配网结果-iOS.py")
    else:
        log(f"⚠️ 未找到配网结果模块: {pairing_result_file}")
except Exception as e:
    log(f"⚠️ 无法加载配网结果模块: {e}")


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
    2. 1共用脚本 目录中的 device_config.json
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
    parent_cfg = os.path.join(os.path.dirname(base_dir), "device_config.json")
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

# 机器人热点：USB 串口路径（与 device_configs 里 Appium 的 TCP「port」不是一回事）
# 优先：环境变量 ROBOT_SERIAL_PORT > device_config.json test_config.robot_serial_port > 本默认值
SERIAL_PORT = os.environ.get("ROBOT_SERIAL_PORT", "/dev/tty.usbserial-1120")
SERIAL_BAUD = os.environ.get("ROBOT_SERIAL_BAUD", "115200")
SERIAL_TRIGGER_CMD = os.environ.get("ROBOT_SERIAL_CMD", "SET state 4")


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


def _find_available_serial_ports() -> list:
    """查找所有可用的串口设备"""
    available_ports = []
    try:
        # 查找 /dev/tty.* 和 /dev/cu.* 中的串口设备
        import glob
        tty_ports = glob.glob("/dev/tty.usbserial*") + glob.glob("/dev/tty.usbmodem*")
        cu_ports = glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*")
        
        all_ports = list(set(tty_ports + cu_ports))
        for port in all_ports:
            if os.path.exists(port) and os.access(port, os.R_OK):
                available_ports.append(port)
        
        # 排序，优先返回 usbserial
        available_ports.sort(key=lambda x: ('usbserial' not in x, x))
    except Exception as e:
        log(f"⚠️ 查找串口设备失败: {e}")
    return available_ports


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

    port_command_script = os.path.join(SHARED_SCRIPTS_DIR, "端口命令.py")

    # 如果找到端口命令脚本，优先使用
    if os.path.exists(port_command_script):
        log(f"📝 找到端口命令脚本: {port_command_script}")
        trigger_count = 1  # 端口命令脚本方式：触发 1 次即可
        success_count = 0
        
        for trigger_num in range(1, trigger_count + 1):
            try:
                log(f"🔌 第 {trigger_num}/{trigger_count} 次触发（使用端口命令脚本）...")
                
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
                    if result.stdout.strip():
                        log(f"ℹ️ 第 {trigger_num} 次触发输出: {result.stdout.strip()}")
                    log(f"✅ 第 {trigger_num} 次串口热点触发成功")
                    success_count += 1
                    
                    if trigger_num < trigger_count:
                        log(f"⏳ 等待 2 秒后触发第 {trigger_num + 1} 次...")
                        time.sleep(2)
                else:
                    output = result.stdout.strip()
                    error = result.stderr.strip()
                    log(f"⚠️ 第 {trigger_num} 次触发失败（返回码: {result.returncode}）")
                    if output:
                        log(f"   输出: {output}")
                    if error:
                        log(f"   错误: {error}")
                    
                    if trigger_num < trigger_count:
                        log(f"⏳ 等待 2 秒后继续触发第 {trigger_num + 1} 次...")
                        time.sleep(2)
            
            except subprocess.TimeoutExpired:
                log(f"⚠️ 第 {trigger_num} 次触发超时")
                if trigger_num < trigger_count:
                    time.sleep(2)
            except Exception as e:
                log(f"⚠️ 第 {trigger_num} 次触发异常: {e}")
                if trigger_num < trigger_count:
                    time.sleep(2)
        
        if success_count > 0:
            log(f"✅ 已完成 {trigger_count} 次串口热点触发（成功 {success_count} 次）")
            return True
        else:
            log(f"⚠️ 端口命令脚本触发失败，回退到expect方式...")
    else:
        log(f"⚠️ 未找到端口命令脚本: {port_command_script}，使用expect方式...")
    
    # 3. 回退到expect方式（保留原有逻辑作为备用）
    log(f"🔌 使用expect方式触发热点（备用方案）...")
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

            script_path = '/tmp/ios_serial_trigger_hotspot.exp'
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
                log(f"✅ 第 {trigger_num} 次串口热点触发成功（expect方式）")
                success_count += 1
                if trigger_num < trigger_count:
                    time.sleep(3)
            else:
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
    else:
        log(f"❌ 所有触发方式都失败")
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
        tcp_port = dev_cfg.get("port", "?")
        log(f"❌ 创建设备驱动失败: {last_err}")
        log(
            f"💡 这是 **Appium 服务 TCP 端口 {tcp_port}**（与 USB 串口无关）。"
            f" Connection refused 时请启动: appium --port {tcp_port}"
        )
    return None


def reset_app_to_home(driver, device_config: dict = None) -> bool:
    """重启 App 并尽量返回首页，如果有已配对设备则先删除（优先使用 common 模块）"""
    if reset_app_module:
        def has_paired_device_func(drv):
            return delete_device_module.has_paired_device(drv) if delete_device_module else False
        
        def remove_existing_device_func(drv):
            return delete_device_module.remove_existing_device(drv) if delete_device_module else False
        
        def home_has_add_button_func(drv):
            add_button_selectors = [
                '//XCUIElementTypeButton[@name="home add device"]',
                '//XCUIElementTypeButton[@name="home add"]',
                '//XCUIElementTypeButton[@name="Add"]',
            ]
            for selector in add_button_selectors:
                try:
                    btn = drv.find_element(AppiumBy.XPATH, selector)
                    if btn.is_displayed():
                        return True
                except Exception:
                    continue
            return False
        
        return reset_app_module.reset_app_to_home(
            driver,
            device_config=device_config,
            has_paired_device_func=has_paired_device_func,
            remove_existing_device_func=remove_existing_device_func,
            home_has_add_button_func=home_has_add_button_func,
            log_func=log
        )
    else:
        # 回退到内部实现
        log("⚠️ 重置应用模块未加载，使用内部实现")
    log("🔄 重置应用到首页...")
    try:
        caps = getattr(driver, "capabilities", {}) or {}
        bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
        if not bundle_id:
            log("⚠️ 无法获取 bundleId，跳过应用重启")
            return True

        driver.terminate_app(bundle_id)
        time.sleep(2)
        driver.activate_app(bundle_id)
        time.sleep(3)

        log("🔍 检查页面是否有已配对的设备...")
        if _has_paired_device(driver):
            log("⚠️ 检测到已配对设备，执行删除操作...")
            if not _remove_existing_device(driver):
                log("⚠️ 删除设备失败，但继续执行后续流程")
            else:
                log("✅ 已删除已配对设备")
                time.sleep(3)
        else:
            log("✅ 未检测到已配对设备，页面状态正常")

        if not _home_has_add_button(driver):
            log("⚠️ 首页没有 add 按钮，再次尝试删除设备...")
            if _has_paired_device(driver):
                if not _remove_existing_device(driver):
                    log("⚠️ 删除设备失败，但继续执行后续流程")
                else:
                    log("✅ 已删除已配对设备")
                    time.sleep(3)
            else:
                log("⚠️ 未检测到已配对设备，但也没有 add 按钮，可能是页面加载问题")

        home_xpaths = [
            '//XCUIElementTypeButton[@name="home add device"]',
            '//XCUIElementTypeButton[@name="home add"]',
            '//XCUIElementTypeStaticText[contains(@name,"AquaSense")]',
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
    """检查首页是否有add按钮，支持多种选择器"""
    add_button_selectors = [
        '//XCUIElementTypeButton[@name="home add device"]',  # 优先：完整名称
        '//XCUIElementTypeButton[@name="home add"]',
        '//XCUIElementTypeButton[@name="Add"]',
        '//XCUIElementTypeButton[contains(@name,"home add")]',
        '//XCUIElementTypeButton[contains(@name,"add")]',
        '//XCUIElementTypeButton[contains(@name,"Add")]',
        '//XCUIElementTypeButton[@name="+"]',
        '//XCUIElementTypeButton[contains(@label,"home add")]',
        '//XCUIElementTypeButton[contains(@label,"add")]',
        '//XCUIElementTypeButton[contains(@label,"Add")]',
    ]
    
    for selector in add_button_selectors:
        try:
            btn = driver.find_element(AppiumBy.XPATH, selector)
            if btn.is_displayed():
                log(f"✅ 找到add按钮（选择器: {selector}）")
                return True
        except Exception:
            continue
    
    return False


def _has_paired_device(driver) -> bool:
    """检查是否有已配对的设备（优先使用 common 模块）"""
    if delete_device_module:
        return delete_device_module.has_paired_device(driver)
    else:
        # 回退到内部实现
        device_button_indicators = [
            '//XCUIElementTypeButton[@name="device down unsel"]',
            '//XCUIElementTypeButton[contains(@name,"device down")]',
            '//XCUIElementTypeButton[@name="device down sel"]',
        ]

        for selector in device_button_indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, selector)
                if elem.is_displayed():
                    log(f"✅ 检测到已配对设备（设备下拉按钮: {selector}）")
                    return True
            except Exception:
                continue

        device_text_indicators = [
            '//XCUIElementTypeStaticText[contains(@name,"AquaSense")]',
            '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
            '//XCUIElementTypeStaticText[contains(@name,"设备")]',
            '//XCUIElementTypeStaticText[contains(@name,"robot")]',
            '//XCUIElementTypeStaticText[contains(@name,"standby")]',
        ]

        for selector in device_text_indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, selector)
                if elem.is_displayed():
                    text = elem.get_attribute("name") or ""
                    if "add" not in text.lower() and "添加" not in text:
                        log(f"✅ 检测到已配对设备（设备名称文本: {selector}, 文本: {text}）")
                        return True
            except Exception:
                continue

    return False


def _remove_existing_device(driver) -> bool:
    """执行删除已配对设备的一整套操作（优先使用 common 模块）"""
    if delete_device_module:
        def home_has_add_button_func(drv):
            add_button_selectors = [
                '//XCUIElementTypeButton[@name="home add device"]',
                '//XCUIElementTypeButton[@name="home add"]',
                '//XCUIElementTypeButton[@name="Add"]',
            ]
            for selector in add_button_selectors:
                try:
                    btn = drv.find_element(AppiumBy.XPATH, selector)
                    if btn.is_displayed():
                        return True
                except Exception:
                    continue
            return False
        
        return delete_device_module.remove_existing_device(
            driver,
            home_has_add_button_func=home_has_add_button_func,
            log_func=log
        )
    else:
        # 回退到内部实现
        log("⚠️ 删除设备模块未加载，使用内部实现")
    log("🔧 检测到首页没有 add device，尝试删除已配对设备...")
    
    # 先检查是否有已配对的设备
    if not _has_paired_device(driver):
        log("⚠️ 未检测到已配对设备，可能页面状态异常，尝试刷新页面...")
        # 尝试刷新页面
        try:
            size = driver.get_window_size()
            start_x = size['width'] // 2
            start_y = int(size['height'] * 0.2)
            end_y = int(size['height'] * 0.5)
            driver.swipe(start_x, start_y, start_x, end_y, 500)
            time.sleep(3)
        except:
            time.sleep(3)
        return True  # 即使没有设备，也返回True，让后续流程继续
    
    # 尝试多种设备下拉按钮选择器
    device_down_selectors = [
        '//XCUIElementTypeButton[@name="device down unsel"]',
        '//XCUIElementTypeButton[contains(@name,"device down")]',
        '//XCUIElementTypeButton[contains(@name,"down")]',
    ]
    
    device_down_clicked = False
    for selector in device_down_selectors:
        try:
            log(f"🔍 尝试设备下拉按钮: {selector}")
            elem = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            elem.click()
            log(f"✅ 点击设备下拉按钮成功: {selector}")
            device_down_clicked = True
            time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
            break
        except Exception as e:
            log(f"⚠️ 设备下拉按钮选择器失败: {selector} - {e}")
            continue
    
    if not device_down_clicked:
        log("⚠️ 无法点击设备下拉按钮，跳过删除操作")
        return False
    
    # 点击Remove按钮
    remove_selectors = [
        '//XCUIElementTypeStaticText[@name="Remove"]',
        '//XCUIElementTypeButton[@name="Remove"]',
        '//XCUIElementTypeStaticText[contains(@name,"Remove")]',
    ]
    
    remove_clicked = False
    for selector in remove_selectors:
        try:
            log(f"🔍 尝试Remove按钮: {selector}")
            elem = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            elem.click()
            log(f"✅ 点击Remove按钮成功: {selector}")
            remove_clicked = True
            time.sleep(2)  # 等待弹框出现
            break
        except Exception as e:
            log(f"⚠️ Remove按钮选择器失败: {selector} - {e}")
            continue
    
    if not remove_clicked:
        log("⚠️ 无法点击Remove按钮，跳过删除操作")
        return False
    
    # 点击Remove后，等待确认弹框出现，然后点击Confirm按钮
    log("⏳ 等待确认弹框出现...")
    time.sleep(1)  # 额外等待，确保弹框完全加载

    # 关键：这个弹框里你能看到两组 Cancel/Confirm，说明存在“重复元素/不同容器里的同名按钮”。
    # 仅凭 //Button[@name="Confirm"] 很容易点错。这里改为：先用弹框文案定位弹框容器，然后只在该容器内找 Confirm 按钮点击。
    def _find_remove_confirm_dialog_roots():
        roots = []
        msg_selectors = [
            # 你日志里的英文文案
            "//XCUIElementTypeStaticText[contains(@name,'After confirmation')]",
            "//XCUIElementTypeStaticText[contains(@name,'Confirm removal')]",
            # 兼容中文
            "//XCUIElementTypeStaticText[contains(@name,'删除')]",
            "//XCUIElementTypeStaticText[contains(@name,'确认')]",
        ]
        for xp in msg_selectors:
            try:
                elems = driver.find_elements(AppiumBy.XPATH, xp)
                for e in elems:
                    try:
                        if not e.is_displayed():
                            continue
                        # 向上找 1~4 层父节点作为“弹框容器候选”
                        cur = e
                        for _ in range(4):
                            try:
                                cur = cur.find_element(AppiumBy.XPATH, "..")
                            except Exception:
                                break
                            if cur and cur.is_displayed():
                                roots.append(cur)
                    except Exception:
                        continue
            except Exception:
                continue
        # 去重（按对象 id）
        uniq = []
        seen = set()
        for r in roots:
            try:
                rid = id(r)
                if rid not in seen:
                    uniq.append(r)
                    seen.add(rid)
            except Exception:
                continue
        return uniq

    def _truthy_attr(v) -> bool:
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "y")

    def _click_best_effort(e) -> bool:
        try:
            e.click()
            return True
        except Exception:
            pass
        try:
            loc = e.location
            size = e.size
            x = loc["x"] + size["width"] // 2
            y = loc["y"] + size["height"] // 2
            driver.tap([(x, y)], 100)
            return True
        except Exception:
            pass
        return False

    def _is_confirm_dialog_still_visible() -> bool:
        check_xps = [
            "//XCUIElementTypeStaticText[contains(@name,'After confirmation')]",
            "//XCUIElementTypeStaticText[contains(@name,'Confirm removal')]",
            "//XCUIElementTypeButton[@name='Confirm']",
            "//XCUIElementTypeStaticText[@name='Confirm']",
        ]
        for xp in check_xps:
            try:
                elems = driver.find_elements(AppiumBy.XPATH, xp)
                for e in elems:
                    try:
                        if e.is_displayed():
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    def _click_confirm_in_dialog() -> bool:
        roots = _find_remove_confirm_dialog_roots()
        if roots:
            log(f"✅ 基于弹框文案定位到 {len(roots)} 个弹框容器候选，优先在容器内点击 Confirm")
        else:
            log("⚠️ 未通过文案定位到弹框容器，将回退为全局查找 Confirm（可能点错）")
            roots = [None]  # 用 None 表示全局

        # 可能需要点两次（两组 Confirm）
        for click_round in range(1, 3):
            candidates = []
            for r in roots:
                try:
                    if r is None:
                        elems = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeButton[@name='Confirm']")
                    else:
                        elems = r.find_elements(AppiumBy.XPATH, ".//XCUIElementTypeButton[@name='Confirm']")
                    for e in elems:
                        try:
                            if not e.is_displayed():
                                continue
                            enabled = _truthy_attr(e.get_attribute("enabled"))
                            hittable = _truthy_attr(e.get_attribute("hittable"))
                            candidates.append((e, enabled, hittable))
                        except Exception:
                            continue
                except Exception:
                    continue

            # 兜底：如果容器内没找到 Button，再尝试容器内的 StaticText（但优先点其父）
            if not candidates:
                for r in roots:
                    try:
                        if r is None:
                            elems = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeStaticText[@name='Confirm']")
                        else:
                            elems = r.find_elements(AppiumBy.XPATH, ".//XCUIElementTypeStaticText[@name='Confirm']")
                        for e in elems:
                            try:
                                if not e.is_displayed():
                                    continue
                                # 尝试点父节点
                                p = e.find_element(AppiumBy.XPATH, "..")
                                if p and p.is_displayed():
                                    enabled = _truthy_attr(p.get_attribute("enabled"))
                                    hittable = _truthy_attr(p.get_attribute("hittable"))
                                    candidates.append((p, enabled, hittable))
                            except Exception:
                                continue
                    except Exception:
                        continue

            if not candidates:
                log("❌ 未找到 Confirm 候选（容器内/全局都没有）")
                return False

            # 排序：hittable 优先，其次 enabled
            candidates.sort(key=lambda item: (not item[2], not item[1]))

            e, enabled, hittable = candidates[0]
            log(f"✅ 删除弹框 Confirm 点击轮次 {click_round}/2：enabled={enabled} hittable={hittable}")
            if not _click_best_effort(e):
                log("⚠️ Confirm 点击失败，尝试下一个候选")
                if len(candidates) > 1:
                    for e2, en2, hi2 in candidates[1:3]:
                        if _click_best_effort(e2):
                            log(f"✅ 备用 Confirm 点击成功：enabled={en2} hittable={hi2}")
                            break
                time.sleep(1.5)
            else:
                time.sleep(1.5)

            # 如果弹框已消失，认为点击生效
            if not _is_confirm_dialog_still_visible():
                log("✅ 删除确认弹框已消失（Confirm 点击生效）")
                return True

            log("⚠️ Confirm 点击后弹框仍在，可能点到了错误按钮/需要点另一个 Confirm，继续下一轮点击")

        # 两轮点击后仍未消失
        return not _is_confirm_dialog_still_visible()

    # 0) 优先处理 iOS 原生 Alert（很多机型/版本的 Confirm 实际在 XCUIElementTypeAlert 里）
    try:
        alerts = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeAlert")
        visible_alerts = [a for a in alerts if a.is_displayed()]
        if visible_alerts:
            log("✅ 检测到 iOS Alert 弹框，优先在 Alert 内点击 Confirm")
            alert_confirm_selectors = [
                "//XCUIElementTypeAlert//XCUIElementTypeButton[@name='Confirm']",
                "//XCUIElementTypeAlert//XCUIElementTypeStaticText[@name='Confirm']",
                "//XCUIElementTypeAlert//XCUIElementTypeButton[contains(@name,'Confirm')]",
            ]
            clicked_in_alert = False
            for xp in alert_confirm_selectors:
                try:
                    elems = driver.find_elements(AppiumBy.XPATH, xp)
                    for e in elems:
                        if not e.is_displayed():
                            continue
                        try:
                            e.click()
                            clicked_in_alert = True
                            log(f"✅ 已在 Alert 内点击 Confirm: {xp}")
                            break
                        except Exception:
                            # tap 兜底
                            try:
                                loc = e.location
                                size = e.size
                                x = loc["x"] + size["width"] // 2
                                y = loc["y"] + size["height"] // 2
                                driver.tap([(x, y)], 100)
                                clicked_in_alert = True
                                log(f"✅ 已在 Alert 内 tap Confirm: {xp} (坐标: {x},{y})")
                                break
                            except Exception:
                                pass
                    if clicked_in_alert:
                        break
                except Exception:
                    continue

            if clicked_in_alert:
                log("✅ Alert Confirm 已点击，等待删除操作开始...")
                time.sleep(3)
            else:
                # 最终兜底：尝试 Alert API
                try:
                    alert = driver.switch_to.alert
                    _ = alert.text  # 触发读取，确认 alert 存在
                    alert.accept()
                    log("✅ 使用 driver.switch_to.alert.accept() 点击 Confirm/默认确认按钮")
                    time.sleep(3)
                except Exception:
                    log("⚠️ Alert 存在但未能通过 Alert API 点击，继续走普通页面 Confirm 查找")
    except Exception:
        pass

    # 0.5) 再用“弹框文案定位容器”的方式点击 Confirm（覆盖自定义弹框/重复元素场景）
    try:
        if _is_confirm_dialog_still_visible():
            if _click_confirm_in_dialog():
                log("✅ 已通过弹框容器方式点击 Confirm")
    except Exception as e:
        log(f"⚠️ 弹框容器 Confirm 点击异常（继续走后续兜底）: {e}")
    
    # 先尝试爬取当前页面元素，用于调试
    try:
        log("📋 爬取当前页面元素（用于调试）...")
        all_elements = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeStaticText | //XCUIElementTypeButton")
        visible_texts = []
        for elem in all_elements:
            try:
                if elem.is_displayed():
                    name = elem.get_attribute("name") or ""
                    if name:
                        visible_texts.append(name)
            except:
                continue
        log(f"📋 当前页面可见元素（前10个）: {visible_texts[:10]}")
    except Exception as e:
        log(f"⚠️ 爬取页面元素失败: {e}")
    
    # 点击Confirm按钮（优先使用用户建议的选择器，并确保点击正确的按钮）
    log("🔍 查找Confirm按钮...")
    confirm_clicked = False
    max_wait_attempts = 5  # 最多等待5次，每次1秒

    def _truthy_attr(v) -> bool:
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "y")

    def _elem_debug(e) -> str:
        try:
            n = e.get_attribute("name") or ""
            t = e.get_attribute("type") or ""
            lbl = e.get_attribute("label") or ""
            enabled = e.get_attribute("enabled")
            hittable = e.get_attribute("hittable")
            return f"type={t} name={n} label={lbl} enabled={enabled} hittable={hittable}"
        except Exception:
            return "elem_debug_failed"

    def _click_elem_best_effort(e) -> bool:
        try:
            e.click()
            return True
        except Exception:
            pass
        try:
            loc = e.location
            size = e.size
            x = loc["x"] + size["width"] // 2
            y = loc["y"] + size["height"] // 2
            driver.tap([(x, y)], 100)
            return True
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].click();", e)
            return True
        except Exception:
            pass
        # StaticText 兜底：点父节点（最多两级）
        try:
            p = e.find_element(AppiumBy.XPATH, "..")
            if p and p.is_displayed():
                try:
                    p.click()
                    return True
                except Exception:
                    # 再往上一层
                    pp = p.find_element(AppiumBy.XPATH, "..")
                    if pp and pp.is_displayed():
                        pp.click()
                        return True
        except Exception:
            pass
        return False

    def _alert_visible() -> bool:
        try:
            alerts = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeAlert")
            for a in alerts:
                try:
                    if a.is_displayed():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _wait_alert_disappear(timeout_sec: int = 6) -> bool:
        end = time.time() + timeout_sec
        while time.time() < end:
            if not _alert_visible():
                return True
            time.sleep(0.5)
        return not _alert_visible()

    for wait_attempt in range(max_wait_attempts):
        try:
            log(f"🔍 Confirm 查找轮次 {wait_attempt+1}/{max_wait_attempts}（优先 Alert Button）")

            # 按优先级收集候选：Alert Button > 普通 Button > StaticText
            candidate_xps = [
                "//XCUIElementTypeAlert//XCUIElementTypeButton[@name='Confirm']",
                "//XCUIElementTypeAlert//XCUIElementTypeButton[contains(@name,'Confirm')]",
                "//XCUIElementTypeAlert//XCUIElementTypeStaticText[@name='Confirm']",
                "//XCUIElementTypeButton[@name='Confirm']",
                "//XCUIElementTypeButton[contains(@name,'Confirm')]",
                "//XCUIElementTypeStaticText[@name='Confirm']",
            ]

            candidates = []
            for xp in candidate_xps:
                try:
                    elems = driver.find_elements(AppiumBy.XPATH, xp)
                    for e in elems:
                        try:
                            if not e.is_displayed():
                                continue
                            name = e.get_attribute("name") or ""
                            if "Cancel" in name or "取消" in name:
                                continue
                            if "Confirm" not in name and "确认" not in name:
                                continue
                            enabled = _truthy_attr(e.get_attribute("enabled"))
                            hittable = _truthy_attr(e.get_attribute("hittable"))
                            candidates.append((xp, e, enabled, hittable))
                        except Exception:
                            continue
                except Exception:
                    continue

            if not candidates:
                log("⚠️ 本轮未找到任何 Confirm 候选")
                if wait_attempt < max_wait_attempts - 1:
                    time.sleep(1)
                continue

            # 排序：先 hittable 再 enabled，再按 xpath 优先级（越靠前越优先）
            candidates.sort(key=lambda item: (not item[3], not item[2], candidate_xps.index(item[0])))

            # 逐个尝试点击，直到 Alert 消失（或确认按钮消失）
            for idx, (xp, e, enabled, hittable) in enumerate(candidates[:4], 1):
                log(f"✅ Confirm 候选#{idx}: xp={xp} enabled={enabled} hittable={hittable} {_elem_debug(e)}")
                if not enabled and not hittable:
                    continue

                if _click_elem_best_effort(e):
                    log(f"✅ 已点击 Confirm（候选#{idx}）")
                    time.sleep(1.5)
                    # 关键：如果当前是 Alert，必须等 Alert 消失才算“点到真的 Confirm”
                    if _alert_visible():
                        if _wait_alert_disappear(timeout_sec=8):
                            log("✅ Confirm 后 Alert 已消失（点击生效）")
                            confirm_clicked = True
                            break
                        else:
                            log("⚠️ Confirm 点击后 Alert 仍未消失，尝试下一个 Confirm 候选")
                            continue
                    else:
                        # 非 Alert 情况：认为点击已触发，进入后续删除验证
                        confirm_clicked = True
                        break

            if confirm_clicked:
                time.sleep(2)  # 等待删除动作进入异步流程
                break

            if wait_attempt < max_wait_attempts - 1:
                time.sleep(1)
        except Exception as e:
            log(f"⚠️ 查找/点击Confirm异常: {e}")
            if wait_attempt < max_wait_attempts - 1:
                time.sleep(1)
    
    if not confirm_clicked:
        log("❌ 无法点击Confirm按钮，删除操作可能未完成")
        # 尝试截图保存当前状态
        try:
            take_screenshot(driver, "confirm_button_not_found")
        except:
            pass
        return False
    
    log("✅ Confirm按钮已点击，等待删除操作完成...")
    
    # 等待删除操作完成（增加等待时间，确保删除真正完成）
    log("⏳ 等待设备删除操作完成...")
    time.sleep(8)  # 删除可能是异步的，适当延长
    
    # 额外验证：检查确认弹框是否已消失
    log("🔍 验证确认弹框是否已消失...")
    for check_attempt in range(3):
        try:
            confirm_dialog = driver.find_elements(
                AppiumBy.XPATH, 
                "//XCUIElementTypeStaticText[@name='Confirm'] | //XCUIElementTypeButton[@name='Confirm']"
            )
            visible_confirm = [e for e in confirm_dialog if e.is_displayed()]
            if not visible_confirm:
                log("✅ 确认弹框已消失")
                break
            else:
                log(f"⚠️ 确认弹框仍在显示（第 {check_attempt+1}/3 次检查），等待2秒...")
                time.sleep(2)
        except:
            break
    
    # 验证设备是否已真正删除（必须同时满足：没有已配对设备 AND 有add按钮）
    log("🔍 验证设备是否已删除...")
    max_verify_attempts = 7  # 删除+UI刷新可能更慢，增加验证次数
    device_deleted = False
    
    for verify_attempt in range(max_verify_attempts):
        # 必须同时满足两个条件：1. 没有已配对设备 2. 有add按钮
        has_paired = _has_paired_device(driver)
        has_add_button = _home_has_add_button(driver)
        
        log(f"🔍 第 {verify_attempt+1}/{max_verify_attempts} 次验证：已配对设备={has_paired}, add按钮={has_add_button}")
        
        if not has_paired and has_add_button:
            log("✅ 确认设备已删除（未检测到已配对设备 且 add按钮已出现）")
            device_deleted = True
            break
        elif has_paired and not has_add_button:
            log(f"⚠️ 设备仍在删除中（检测到已配对设备，但add按钮未出现）")
        elif has_paired and has_add_button:
            log(f"⚠️ 状态异常：同时检测到已配对设备和add按钮，可能是页面刷新问题")
        elif not has_paired and not has_add_button:
            log(f"⚠️ 状态异常：既没有已配对设备也没有add按钮，可能是页面加载问题")
        
        if verify_attempt < max_verify_attempts - 1:
            log(f"⏳ 等待3秒后重试...")
            time.sleep(3)
            # 尝试刷新页面
            try:
                size = driver.get_window_size()
                start_x = size['width'] // 2
                start_y = int(size['height'] * 0.2)
                end_y = int(size['height'] * 0.5)
                driver.swipe(start_x, start_y, start_x, end_y, 500)
                time.sleep(2)
            except Exception:
                time.sleep(2)

    if not device_deleted:
        log("❌ 验证失败：设备可能未完全删除")
        # 关键兜底：如果设备仍在，说明这次删除没生效，直接再尝试一次删除流程（最多 1 次，避免死循环）
        try:
            log("🔁 设备仍存在，尝试再次执行删除流程（兜底重试 1 次）...")
            # 轻量刷新页面，避免 stale UI
            caps = getattr(driver, "capabilities", {}) or {}
            bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
            if bundle_id:
                driver.activate_app(bundle_id)
                time.sleep(2)
            # 再走一遍：点下拉 -> Remove -> Confirm（复用当前函数逻辑的前半段）
            # 简单方式：递归调用一次，但要防止无限递归
            # 通过标记属性避免重复
            if not getattr(driver, "_delete_retry_once", False):
                setattr(driver, "_delete_retry_once", True)
                return _remove_existing_device(driver)
        except Exception as e:
            log(f"⚠️ 删除兜底重试异常: {e}")
        # 尝试强制刷新页面并重新验证
        try:
            caps = getattr(driver, "capabilities", {}) or {}
            bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
            if bundle_id:
                log("🔄 尝试重新激活应用以刷新页面...")
                driver.activate_app(bundle_id)
                time.sleep(3)
                # 再次验证
                has_paired = _has_paired_device(driver)
                has_add_button = _home_has_add_button(driver)
                if not has_paired and has_add_button:
                    log("✅ 重新激活后确认设备已删除")
                    device_deleted = True
                else:
                    log(f"⚠️ 重新激活后验证：已配对设备={has_paired}, add按钮={has_add_button}")
        except Exception as e:
            log(f"⚠️ 重新激活应用失败: {e}")
        
        if not device_deleted:
            log("❌ 设备删除验证失败，返回False")
            return False
    
    # 删除后刷新页面（确保页面状态更新）
    log("🔄 删除设备后刷新页面...")
    try:
        # 方法1: 尝试下拉刷新
        size = driver.get_window_size()
        start_x = size['width'] // 2
        start_y = int(size['height'] * 0.2)
        end_y = int(size['height'] * 0.5)
        driver.swipe(start_x, start_y, start_x, end_y, 500)
        time.sleep(2)
    except:
        # 方法2: 如果下拉刷新失败，简单等待页面自动刷新
        log("⚠️ 下拉刷新失败，等待页面自动刷新...")
        time.sleep(2)
    
    # 最终验证：再次检查是否有 add 按钮
    if _home_has_add_button(driver):
        log("✅ 页面刷新完成，add device按钮已出现")
        return True
    else:
        # 这里原先会“误判成功”，导致你看到日志说删了但实际没删。
        # 改为严格失败：没有 add 按钮意味着删除/刷新没有成功，需要上层重试或人工介入。
        log("❌ 页面刷新后仍未检测到 add 按钮，认为删除未成功")
        take_screenshot(driver, "delete_device_not_effective")
        return False


def ensure_home_add_button(driver) -> bool:
    """如果首页没有"home add"按钮则尝试删除已配对设备"""
    for attempt in range(3):
        log(f"🔁 检查首页 add 按钮（第 {attempt+1}/3 次）")
        if _home_has_add_button(driver):
            log("✅ add device 按钮已就绪")
            return True
        
        # 如果第一次检查失败，尝试删除设备
        if attempt == 0:
            if not _remove_existing_device(driver):
                return False
            # 删除设备后，等待页面刷新，然后再次检查
            log("⏳ 等待页面刷新后检查 add 按钮...")
            time.sleep(3)
        else:
            # 后续尝试：如果删除后仍然没有，等待更长时间
            log(f"⏳ 第 {attempt+1} 次检查，等待页面加载...")
            time.sleep(3)
    
    log("❌ 多次尝试后仍未找到 add 按钮")
    return False


def tap_add_device(driver) -> bool:
    """点击首页 add device 按钮，支持多种选择器"""
    log("📱 步骤2: 点击添加设备按钮...")
    
    add_button_selectors = [
        '//XCUIElementTypeButton[@name="home add device"]',  # 优先：完整名称
        '//XCUIElementTypeButton[@name="home add"]',
        '//XCUIElementTypeButton[@name="Add"]',
        '//XCUIElementTypeButton[contains(@name,"home add")]',
        '//XCUIElementTypeButton[contains(@name,"add")]',
        '//XCUIElementTypeButton[contains(@name,"Add")]',
        '//XCUIElementTypeButton[@name="+"]',
        '//XCUIElementTypeButton[contains(@label,"home add")]',
        '//XCUIElementTypeButton[contains(@label,"add")]',
        '//XCUIElementTypeButton[contains(@label,"Add")]',
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
                time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
                return True
        except Exception as e:
            log(f"⚠️ add按钮选择器失败: {selector} - {e}")
            continue
    
    log("❌ 所有add按钮选择器都失败")
    take_screenshot(driver, "tap_add_fail")
    return False


# ==================== 设备选择页面 ==================== #

def pick_target_device(driver, target: dict) -> bool:
    """
    在设备选择列表中选择指定 SN 的设备：
    - 点击 SN:0078 对应项
    - 点击 Add 按钮
    支持向下滑动查找设备
    
    注意：此函数现在优先调用 common/选择设备.py 中的独立模块
    """
    # 优先使用独立的设备选择模块
    if select_device_from_module:
        try:
            log("🔌 使用独立设备选择模块: common/选择设备.py")
            result = select_device_from_module(
                driver=driver,
                target_device_config=target,
                platform="ios",
                log_func=log,
                screenshot_dir=SCREENSHOT_DIR,
            )
            if result:
                log("✅ 独立设备选择模块执行成功")
                return True
            else:
                log("⚠️ 独立设备选择模块执行失败，回退到内置函数")
        except Exception as e:
            log(f"⚠️ 调用独立设备选择模块失败: {e}，回退到内置函数")
            import traceback
            log(f"   详细错误: {traceback.format_exc()}")
    
    # 回退到内置函数（保持向后兼容）
    log("🔄 使用内置设备选择函数...")
    return _pick_target_device_internal(driver, target)


def _pick_target_device_internal(driver, target: dict) -> bool:
    """
    内置设备选择函数（原 pick_target_device 的实现）
    在设备选择列表中选择指定 SN 的设备：
    - 点击 SN:0078 对应项
    - 点击 Add 按钮
    支持向下滑动查找设备
    """
    if not target:
        log("❌ target_device 配置为空，请在 device_config.json 中配置 target_device")
        return False
    
    dev_sn = target.get("device_sn")
    dev_name = target.get("device_name")
    
    if not dev_sn:
        log("❌ target_device.device_sn 未配置，请在 device_config.json 中配置 target_device.device_sn")
        return False
    
    if not dev_name:
        log("❌ target_device.device_name 未配置，请在 device_config.json 中配置 target_device.device_name")
        return False
    short_sn = dev_sn[1:] if dev_sn.lower().startswith("b") else dev_sn

    log(f"🔍 步骤3: 选择设备（{dev_name}, SN: {dev_sn}）...")

    import re
    
    # 等待页面加载完成，确保所有设备都显示出来
    log("⏳ 等待设备选择页面加载，确保所有设备都显示（10秒）...")
    time.sleep(10)

    # 多种设备选择器（按优先级排序）
    device_selectors = [
        f'(//XCUIElementTypeStaticText[@name="(SN:{short_sn})"])[1]',
        f'//XCUIElementTypeStaticText[@name="(SN:{short_sn})"]',
        f'//XCUIElementTypeStaticText[@name="(SN: {short_sn})"]',
        f'//XCUIElementTypeStaticText[contains(@name,"SN:{short_sn}")]',
        f'//XCUIElementTypeStaticText[contains(@name,"SN: {short_sn}")]',
        f'//XCUIElementTypeStaticText[contains(@name,"{short_sn}")]',
    ]
    
    add_btn_xpath = '//XCUIElementTypeButton[@name="Add"]'

    max_attempts = 3  # 最多尝试3次
    max_scrolls = 10  # 最多滑动10次
    
    for attempt in range(max_attempts):
        try:
            log(f"🔍 第{attempt + 1}次尝试选择设备...")
            
            # 等待页面加载
            if attempt == 0:
                log("⏳ 等待设备选择页面加载，确保所有设备都显示（10秒）...")
                time.sleep(10)
            else:
                time.sleep(2)
            
            # 优先使用精确匹配的选择器（按精确度排序）
            # 最高精度：同时包含设备名称和SN的选择器
            device_selectors = [
                # 最精确：同时包含设备名称和SN（完全匹配）
                f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"SN:{short_sn}")]',
                f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"SN: {short_sn}")]',
                f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"{short_sn}")]',
                # 精确：完全匹配 SN 格式（带括号）
                f'(//XCUIElementTypeStaticText[@name="(SN:{short_sn})"])[1]',
                f'//XCUIElementTypeStaticText[@name="(SN:{short_sn})"]',
                f'//XCUIElementTypeStaticText[@name="(SN: {short_sn})"]',
                # 精确匹配：包含完整 SN
                f'//XCUIElementTypeStaticText[contains(@name,"SN:{short_sn}")]',
                f'//XCUIElementTypeStaticText[contains(@name,"SN: {short_sn})"]',
                # 精确匹配：包含完整 SN（无前缀，但需要验证）
                f'//XCUIElementTypeStaticText[contains(@name,"{short_sn}")]',
            ]
            
            add_btn_xpath = '//XCUIElementTypeButton[@name="Add"]'
            dev_elem = None
            matched_text = None
            
            def _verify_device_element(elem, expected_sn, expected_name):
                """严格验证设备元素是否匹配目标设备（同时验证设备名称和SN）"""
                try:
                    # 获取元素文本
                    elem_text = elem.get_attribute("name") or elem.text or ""
                    log(f"🔍 验证设备元素文本: '{elem_text}'")
                    
                    # 首先验证文本中是否包含完整的 SN（简单但有效的检查）
                    if expected_sn not in elem_text and short_sn not in elem_text:
                        log(f"❌ SN不匹配: 期望包含 '{expected_sn}' 或 '{short_sn}'，实际文本: '{elem_text}'")
                        return False, None
                    
                    # 进一步验证：使用正则表达式确保是完整的 SN 匹配（不是部分匹配）
                    sn_patterns = [
                        rf'\(SN:\s*{re.escape(expected_sn)}\)',  # (SN:B0078) 或 (SN: B0078)
                        rf'\(SN:\s*{re.escape(short_sn)}\)',  # (SN:0078) 或 (SN: 0078)
                        rf'SN:\s*{re.escape(expected_sn)}',  # SN:B0078 或 SN: B0078
                        rf'SN:\s*{re.escape(short_sn)}',  # SN:0078 或 SN: 0078
                        rf'\b{re.escape(expected_sn)}\b',  # 完整SN号（单词边界）
                        rf'\b{re.escape(short_sn)}\b',  # 完整SN号（无B前缀）
                    ]
                    
                    sn_matched = False
                    matched_sn_pattern = None
                    for pattern in sn_patterns:
                        if re.search(pattern, elem_text, re.IGNORECASE):
                            sn_matched = True
                            matched_sn_pattern = pattern
                            log(f"✅ SN匹配成功: 模式 '{pattern}' 匹配文本 '{elem_text}'")
                            break
                    
                    if not sn_matched:
                        log(f"❌ SN正则验证失败: 期望包含 '{expected_sn}' 或 '{short_sn}'，实际文本: '{elem_text}'")
                        return False, None
                    
                    # 关键改进：同时验证设备名称，提高选择精度
                    # 尝试在元素本身、父元素、兄弟元素中查找设备名称
                    name_matched = False
                    name_match_context = ""
                    
                    # 1. 首先检查元素文本本身是否包含设备名称
                    if expected_name and expected_name.lower() in elem_text.lower():
                        name_matched = True
                        name_match_context = "元素文本本身"
                        log(f"✅ 设备名称匹配成功（{name_match_context}）: '{expected_name}' 在文本中")
                    else:
                        # 2. 检查父元素（通常是包含设备信息的容器）
                        try:
                            parent = elem.find_element(AppiumBy.XPATH, "..")
                            parent_text = parent.get_attribute("name") or parent.text or ""
                            if expected_name and expected_name.lower() in parent_text.lower():
                                name_matched = True
                                name_match_context = "父元素"
                                log(f"✅ 设备名称匹配成功（{name_match_context}）: '{expected_name}' 在父元素中")
                        except:
                            pass
                        
                        # 3. 如果父元素未匹配，检查兄弟元素（同一层级的其他元素）
                        if not name_matched:
                            try:
                                # 查找同一父元素下的所有兄弟元素
                                parent = elem.find_element(AppiumBy.XPATH, "..")
                                siblings = parent.find_elements(AppiumBy.XPATH, "./*")
                                for sibling in siblings:
                                    sibling_text = sibling.get_attribute("name") or sibling.text or ""
                                    if expected_name and expected_name.lower() in sibling_text.lower():
                                        name_matched = True
                                        name_match_context = "兄弟元素"
                                        log(f"✅ 设备名称匹配成功（{name_match_context}）: '{expected_name}' 在兄弟元素中")
                                        break
                            except:
                                pass
                        
                        # 4. 如果还是没找到，尝试查找附近的元素（使用 XPath 查找包含设备名称的相邻元素）
                        if not name_matched:
                            try:
                                # 查找同一层级或附近包含设备名称的元素
                                nearby_name_elem = driver.find_element(
                                    AppiumBy.XPATH,
                                    f'//XCUIElementTypeStaticText[contains(@name,"{expected_name}")]'
                                )
                                if nearby_name_elem:
                                    # 检查是否在同一个设备项中（通过检查父元素或位置）
                                    elem_location = elem.location
                                    name_elem_location = nearby_name_elem.location
                                    # 如果两个元素在垂直方向上接近（Y坐标差小于100），认为是同一设备
                                    if abs(elem_location['y'] - name_elem_location['y']) < 100:
                                        name_matched = True
                                        name_match_context = "附近元素"
                                        log(f"✅ 设备名称匹配成功（{name_match_context}）: '{expected_name}' 在附近元素中")
                            except:
                                pass
                    
                    # 如果设备名称未匹配，记录警告但继续（因为有些情况下设备名称可能不在同一元素中）
                    if not name_matched and expected_name:
                        log(f"⚠️ 设备名称未匹配: 期望 '{expected_name}'，但未在元素附近找到（SN已匹配，继续验证）")
                        # 如果SN匹配但名称不匹配，仍然返回True，但记录警告
                        # 这样可以处理设备名称显示在不同位置的UI情况
                    
                    # 最终验证：SN必须匹配，设备名称如果找到则必须匹配
                    if sn_matched:
                        if name_matched:
                            log(f"✅ 设备验证通过: SN匹配 + 设备名称匹配，文本: '{elem_text}'")
                        else:
                            log(f"✅ 设备验证通过: SN匹配（设备名称未找到但SN已确认），文本: '{elem_text}'")
                        return True, elem_text
                    else:
                        log(f"❌ 设备验证失败: SN未匹配")
                        return False, None
                    
                except Exception as e:
                    log(f"⚠️ 验证设备元素时出错: {e}")
                    import traceback
                    log(f"   详细错误: {traceback.format_exc()}")
                    return False, None
    
            # 首先尝试不滑动直接查找
            log("🔍 首先尝试直接查找设备（不滑动）...")
            for selector in device_selectors:
                try:
                    elements = driver.find_elements(AppiumBy.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            is_match, text = _verify_device_element(elem, dev_sn, dev_name)
                            if is_match:
                                dev_elem = elem
                                matched_text = text
                                log(f"✅ 直接找到并验证目标设备: {selector}")
                                log(f"   匹配文本: {text}")
                                break
                    if dev_elem:
                        break
                except:
                    continue
            
            # 如果直接查找失败，尝试查找所有设备并验证
            if not dev_elem:
                log("🔍 直接查找失败，查找所有设备元素进行验证...")
                try:
                    # 优先查找同时包含设备名称和SN的元素（提高精度）
                    priority_elements = []
                    try:
                        priority_elements = driver.find_elements(
                            AppiumBy.XPATH, 
                            f'//XCUIElementTypeStaticText[contains(@name,"{dev_name}") and contains(@name,"SN")]'
                        )
                        log(f"🔍 找到 {len(priority_elements)} 个同时包含设备名称和SN的元素（优先验证）")
                    except:
                        pass
                    
                    # 然后查找所有可能包含 SN 的设备元素
                    all_device_elements = driver.find_elements(
                        AppiumBy.XPATH, 
                        '//XCUIElementTypeStaticText[contains(@name,"SN")]'
                    )
                    
                    log(f"🔍 总共找到 {len(all_device_elements)} 个可能的设备元素")
                    
                    # 优先验证同时包含设备名称和SN的元素
                    for elem in priority_elements:
                        try:
                            if elem.is_displayed():
                                text = elem.get_attribute("name") or elem.text or ""
                                log(f"   优先检查设备（包含名称和SN）: {text}")
                                
                                # 验证：必须包含完整的 SN
                                if dev_sn in text or short_sn in text:
                                    # 进一步验证：确保是完整的 SN 匹配
                                    is_match, verified_text = _verify_device_element(elem, dev_sn, dev_name)
                                    if is_match:
                                        dev_elem = elem
                                        matched_text = verified_text
                                        log(f"✅ 验证通过，找到目标设备: {text}")
                                        break
                        except Exception as e:
                            log(f"⚠️ 检查优先设备元素时出错: {e}")
                            continue
                        if dev_elem:
                            break
                    
                    # 如果优先元素未找到，再验证所有包含SN的元素
                    if not dev_elem:
                        for elem in all_device_elements:
                            # 跳过已经在优先列表中验证过的元素
                            if elem in priority_elements:
                                continue
                            try:
                                if elem.is_displayed():
                                    text = elem.get_attribute("name") or elem.text or ""
                                    log(f"   检查设备: {text}")
                                    
                                    # 验证：必须包含完整的 SN
                                    if dev_sn in text or short_sn in text:
                                        # 进一步验证：确保是完整的 SN 匹配
                                        is_match, verified_text = _verify_device_element(elem, dev_sn, dev_name)
                                        if is_match:
                                            dev_elem = elem
                                            matched_text = verified_text
                                            log(f"✅ 验证通过，找到目标设备: {text}")
                                            break
                            except Exception as e:
                                log(f"⚠️ 检查设备元素时出错: {e}")
                                continue
                            if dev_elem:
                                break
                except Exception as e:
                    log(f"⚠️ 查找所有设备元素失败: {e}")
            
            # 如果仍然找不到，先向上滑动到顶部，然后双向滑动查找
            if not dev_elem:
                log("🔍 未找到设备，先向上滑动到顶部，然后双向滑动查找...")
                
                # 先向上滑动到顶部（确保从顶部开始查找）
                log("⬆️ 向上滑动到列表顶部...")
                for top_scroll in range(5):  # 最多向上滑动5次确保到顶部
                    try:
                        size = driver.get_window_size()
                        start_x = size['width'] // 2
                        start_y = int(size['height'] * 0.3)  # 从上方开始
                        end_y = int(size['height'] * 0.7)    # 向下滑动（向上滚动列表）
                        driver.swipe(start_x, start_y, start_x, end_y, 500)
                        time.sleep(1)
                    except:
                        try:
                            driver.execute_script('mobile: swipe', {
                                'direction': 'up'
                            })
                            time.sleep(1)
                        except:
                            break
                
                time.sleep(2)  # 等待列表稳定
                
                # 现在从顶部开始，先向下滑动查找
                log("⬇️ 从顶部开始向下滑动查找...")
                for scroll_attempt in range(max_scrolls):
                    log(f"🔍 第{scroll_attempt + 1}/{max_scrolls}次向下滑动查找设备...")
                    
                    # 每次滑动后尝试所有选择器
                    for selector in device_selectors:
                        try:
                            elements = driver.find_elements(AppiumBy.XPATH, selector)
                            for elem in elements:
                                if elem.is_displayed():
                                    is_match, text = _verify_device_element(elem, dev_sn, dev_name)
                                    if is_match:
                                        dev_elem = elem
                                        matched_text = text
                                        log(f"✅ 向下滑动后找到目标设备: {text}")
                                        break
                            if dev_elem:
                                break
                        except:
                            continue
                    
                    if dev_elem:
                        break
                    
                    # 向下滑动
                    try:
                        size = driver.get_window_size()
                        start_x = size['width'] // 2
                        start_y = int(size['height'] * 0.6)
                        end_y = int(size['height'] * 0.3)
                        driver.swipe(start_x, start_y, start_x, end_y, 500)
                        time.sleep(1.5)
                    except Exception as swipe_err:
                        try:
                            driver.execute_script('mobile: swipe', {
                                'direction': 'down'
                            })
                            time.sleep(1.5)
                        except:
                            log(f"⚠️ 滑动失败: {swipe_err}")
                            time.sleep(1)
    
                # 如果向下滑动没找到，尝试向上滑动查找
                if not dev_elem:
                    log("⬆️ 向下滑动未找到，尝试向上滑动查找...")
                    for scroll_attempt in range(max_scrolls):
                        log(f"🔍 第{scroll_attempt + 1}/{max_scrolls}次向上滑动查找设备...")
                        
                        # 每次滑动后尝试所有选择器
                        for selector in device_selectors:
                            try:
                                elements = driver.find_elements(AppiumBy.XPATH, selector)
                                for elem in elements:
                                    if elem.is_displayed():
                                        is_match, text = _verify_device_element(elem, dev_sn, dev_name)
                                        if is_match:
                                            dev_elem = elem
                                            matched_text = text
                                            log(f"✅ 向上滑动后找到目标设备: {text}")
                                            break
                                if dev_elem:
                                    break
                            except:
                                continue
                        
                        if dev_elem:
                            break
                        
                        # 向上滑动（向上滚动列表，即从下往上滑动）
                        try:
                            size = driver.get_window_size()
                            start_x = size['width'] // 2
                            start_y = int(size['height'] * 0.3)  # 从上方开始
                            end_y = int(size['height'] * 0.7)    # 向下滑动（向上滚动列表）
                            driver.swipe(start_x, start_y, start_x, end_y, 500)
                            time.sleep(1.5)
                        except Exception as swipe_err:
                            try:
                                driver.execute_script('mobile: swipe', {
                                    'direction': 'up'
                                })
                                time.sleep(1.5)
                            except:
                                log(f"⚠️ 滑动失败: {swipe_err}")
                                time.sleep(1)
            
            # 验证找到的设备
            if not dev_elem:
                log("❌ 未找到目标设备元素")
                if attempt < max_attempts - 1:
                    log("⏳ 等待2秒后重试...")
                    time.sleep(2)
                    continue
                else:
                    log(f"❌ 经过 {max_attempts} 次尝试，仍未找到目标设备 SN: {dev_sn}")
                    take_screenshot(driver, "pick_device_fail")
                    return False
            
            # 再次验证匹配的文本
            if matched_text and dev_sn not in matched_text and short_sn not in matched_text:
                log(f"❌ 验证失败：匹配的文本 '{matched_text}' 不包含目标 SN '{dev_sn}'")
                if attempt < max_attempts - 1:
                    log("⏳ 等待2秒后重试...")
                    time.sleep(2)
                    continue
                else:
                    return False
            
            # 点击前再次验证（确保元素仍然有效）
            try:
                log(f"🔍 点击前再次验证设备: '{matched_text}'")
                if not dev_elem.is_displayed():
                    log("❌ 设备元素已不可见，重新查找...")
                    if attempt < max_attempts - 1:
                        time.sleep(2)
                        continue
                    else:
                        return False
                
                # 再次获取文本验证
                current_text = dev_elem.get_attribute("name") or dev_elem.text or ""
                if dev_sn not in current_text and short_sn not in current_text:
                    log(f"❌ 点击前验证失败: 当前文本 '{current_text}' 不包含目标SN")
                    if attempt < max_attempts - 1:
                        time.sleep(2)
                        continue
                    else:
                        return False
                
                log(f"✅ 点击前验证通过，准备点击设备: '{current_text}'")
            except Exception as e:
                log(f"❌ 点击前验证失败: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                else:
                    return False
            
            # 点击找到的设备
            try:
                log(f"✅ 确认选择设备: {matched_text}")
                log("⏳ 等待元素完全加载后点击...")
                time.sleep(2)
                dev_elem.click()
                log(f"✅ 点击 SN 设备成功: {matched_text}")
                time.sleep(2)
            except Exception as e:
                log(f"❌ 点击设备失败: {e}")
                if attempt < max_attempts - 1:
                    take_screenshot(driver, "pick_device_click_fail")
                    time.sleep(2)
                    continue
                else:
                    take_screenshot(driver, "pick_device_click_fail")
                    return False

            # 选择完设备后点击 Add
            try:
                log("🔍 查找 Add 按钮...")
                for _ in range(3):
                    btn = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((AppiumBy.XPATH, add_btn_xpath))
                    )
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        log("✅ 点击 Add 按钮成功")
                        time.sleep(2)
                        return True
                    # 如果按钮暂不可点，稍等后重试
                    log("⚠️ Add 按钮暂不可点击，等待后重试")
                    time.sleep(2)
                log("❌ 多次尝试后 Add 按钮仍不可点击")
                take_screenshot(driver, "add_btn_disabled")
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                else:
                    return False
            except Exception as e:
                log(f"❌ 查找或点击 Add 按钮失败: {e}")
                take_screenshot(driver, "add_btn_error")
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                else:
                    return False
                    
        except Exception as e:
            log(f"❌ 第{attempt + 1}次选择设备失败: {e}")
            if attempt < max_attempts - 1:
                log("⏳ 等待3秒后重试...")
                time.sleep(3)
            else:
                return False
    
    return False


# ==================== 检测 Set up wifi 页面（参考 P0022-S1MAX IOS-2蓝牙配网） ==================== #


def _handle_agree_on_set_up_wifi(driver, timeout: int = 6) -> bool:
    """
    选择设备后进入 Set up Wi‑Fi 页面，可能出现 Agree 弹框，需要点击 Agree。
    未出现返回 False（不算失败）。
    """
    agree_selectors = [
        '//XCUIElementTypeButton[@name="Agree"]',
        '//XCUIElementTypeButton[contains(@name,"Agree")]',
        '//XCUIElementTypeStaticText[@name="Agree"]/..',
        '//XCUIElementTypeButton[contains(@label,"Agree")]',
    ]
    for selector in agree_selectors:
        try:
            agree_btn = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            if agree_btn.is_displayed():
                agree_btn.click()
                log(f"✅ Set up Wi‑Fi：已点击 Agree 按钮（选择器: {selector}）")
                time.sleep(1)
                return True
        except Exception:
            continue
    try:
        agree_elements = driver.find_elements(
            AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Agree")]'
        )
        for elem in agree_elements:
            try:
                if elem.is_displayed():
                    loc = elem.location
                    size = elem.size
                    cx = loc["x"] + size["width"] // 2
                    cy = loc["y"] + size["height"] // 2
                    log(f"💡 通过坐标点击 Agree 按钮: ({cx}, {cy})")
                    driver.tap([(cx, cy)], 100)
                    log("✅ 通过坐标点击 Agree 按钮成功")
                    time.sleep(1)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def wait_for_wifi_setup_page(driver, timeout: int = 15) -> bool:
    """
    等待进入 Set up wifi 页面（选择设备后），再执行「切换 WiFi」等高/低系统分支逻辑。
    与 P0022-S1MAX 蓝牙配网脚本一致。
    """
    log("⏳ 等待进入 Set up wifi 页面...")
    wifi_setup_indicators = [
        '//XCUIElementTypeButton[@name="pair net change wifi"]',
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeTextField',
        '//XCUIElementTypeStaticText[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeStaticText[contains(@name,"WIFI")]',
        '//XCUIElementTypeStaticText[contains(@name,"Set up")]',
        '//XCUIElementTypeButton[@name="Agree"]',
        '//XCUIElementTypeButton[contains(@name,"Agree")]',
    ]

    def _on_found(indicator: str) -> bool:
        log(f"✅ 已跳转到 WiFi 设置页面: {indicator}")
        time.sleep(1)
        if _handle_agree_on_set_up_wifi(driver, timeout=4):
            log("✅ 已处理 Agree 按钮，继续后续流程")
        else:
            log("ℹ️ 未检测到 Agree 按钮，可能已跳过或不存在")
        return True

    log("🔍 立即检查是否已经跳转到 WiFi 设置页面...")
    for indicator in wifi_setup_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                return _on_found(indicator)
        except Exception:
            continue

    start_time = time.time()
    check_interval = 1
    while time.time() - start_time < timeout:
        for indicator in wifi_setup_indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, indicator)
                if elem.is_displayed():
                    return _on_found(indicator)
            except Exception:
                continue
        time.sleep(check_interval)

    log("❌ 等待 Set up wifi 页面超时")
    take_screenshot(driver, "wait_wifi_setup_timeout")
    return False


# ==================== WiFi 设置流程 ====================

# ==================== WiFi 设置（已迁移到 common/选择WIFI.py） ==================== #

def perform_wifi_setup(driver, wifi_name: str, wifi_pwd: str) -> bool:
    """整体 WiFi 设置步骤（调用 common/选择WIFI.py 模块）"""
    if wifi_setup_module:
        return wifi_setup_module.perform_wifi_setup(
            driver=driver,
            wifi_name=wifi_name,
            wifi_password=wifi_pwd,
            platform="ios",
            log_func=log,
            screenshot_func=take_screenshot,
        )
    else:
        log("⚠️ WiFi 选择模块未加载，无法执行 WiFi 设置")
        return False


def handle_wifi_guide_page_before_pairing(driver, timeout: int = 10) -> bool:
    """
    WiFi 设置完成后，进入配网进程前可能出现引导页：
      1) 点击 //XCUIElementTypeButton[@name="pair net un sel"]
      2) 点击 //XCUIElementTypeButton[@name="Next"]

    返回：
    - True: 引导页不存在，或存在且已处理成功
    - False: 引导页出现但处理失败
    """
    checkbox_xp = '//XCUIElementTypeButton[@name="pair net un sel"]'
    next_xp = '//XCUIElementTypeButton[@name="Next"]'

    try:
        checkbox = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, checkbox_xp))
        )
        if not checkbox.is_displayed():
            log("ℹ️ 未检测到引导页勾选按钮，继续配网进程")
            return True
    except Exception:
        log("ℹ️ 未检测到引导页（pair net un sel），继续配网进程")
        return True

    log("🧭 检测到引导页，执行勾选并进入配网进程...")

    try:
        checkbox = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, checkbox_xp))
        )
        checkbox.click()
        log("✅ 引导页：已勾选 pair net un sel")
        time.sleep(1)
    except Exception as e:
        log(f"❌ 引导页：勾选 pair net un sel 失败: {e}")
        take_screenshot(driver, "guide_checkbox_click_fail")
        return False

    try:
        next_btn = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, next_xp))
        )
        next_btn.click()
        log("✅ 引导页：已点击 Next，进入配网进程页面")
        time.sleep(1)
        return True
    except Exception as e:
        log(f"❌ 引导页：点击 Next 失败: {e}")
        take_screenshot(driver, "guide_next_click_fail")
        return False


# ==================== 配网进度 & 结果 ==================== #

def wait_pairing_result(driver, target_dev: dict = None, timeout: int = 180) -> str:
    """等待配网结果：success / failed / timeout / success_need_next（优先使用 common 模块）"""

    def is_home_func(drv):
        home_xpaths = [
            '//XCUIElementTypeButton[@name="home add device"]',
            '//XCUIElementTypeButton[@name="home add"]',
            '//XCUIElementTypeStaticText[contains(@name,"AquaSense")]',
            '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
            '//XCUIElementTypeStaticText[contains(@name,"设备")]',
        ]
        for xp in home_xpaths:
            try:
                elem = drv.find_element(AppiumBy.XPATH, xp)
                if elem.is_displayed():
                    return True
            except Exception:
                continue
        return False

    if pairing_result_module:
        return pairing_result_module.wait_pairing_result(
            driver,
            timeout=timeout,
            target_device_config=target_dev,
            is_home_func=is_home_func,
            log_func=log,
        )

    # 回退到内部实现
    log("⚠️ 配网结果模块未加载，使用内部实现")
    log("⏳ 步骤6: 等待配网结果...")
    start = time.time()

    success_xpaths = [
        '//XCUIElementTypeStaticText[contains(@name,"设备")]',
    ]

    if target_dev and target_dev.get("device_name"):
        dev_name = target_dev.get("device_name")
        success_xpaths.insert(0, f'//XCUIElementTypeStaticText[@name="{dev_name}"]')
        if " " in dev_name:
            name_parts = dev_name.split()
            for part in name_parts:
                if len(part) > 2:
                    success_xpaths.insert(1, f'//XCUIElementTypeStaticText[contains(@name,"{part}")]')
                    break

    while time.time() - start < timeout:
        try:
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

            for xp in success_xpaths:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, xp)
                    if elem.is_displayed():
                        log(f"✅ 配网成功，新设备元素: {xp}")
                        return "success"
                except Exception:
                    continue

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


# ==================== 单次配网流程 ==================== #

def run_single_flow(driver, wifi_name: str, wifi_pwd: str, target_dev: dict) -> tuple[str, str]:
    """单次配网完整流程，返回 (result, message)"""
    log(f"\n🔄 开始单次配网流程（WiFi: {wifi_name}）")
    log("=" * 60)

    if not reset_app_to_home(driver, device_config=None):
        log("⚠️ 应用重置失败，仍尝试继续")

    if not trigger_robot_hotspot():
        return "error", "触发机器热点失败"

    if not ensure_home_add_button(driver):
        return "error", "首页缺少 add 按钮"

    if not tap_add_device(driver):
        return "error", "点击 add 按钮失败"

    if not pick_target_device(driver, target_dev):
        return "error", "设备选择失败"

    # 等待进入 Set up wifi 后再点「切换 WiFi」（与 P0022-S1MAX 一致，避免高系统跳转时机不对）
    if not wait_for_wifi_setup_page(driver, timeout=15):
        return "error", "未进入 Set up wifi 页面"

    if not perform_wifi_setup(driver, wifi_name, wifi_pwd):
        return "error", "WiFi 设置失败"

    # WiFi 设置后、进入配网进程前：处理可能出现的引导页（勾选 + Next）
    if not handle_wifi_guide_page_before_pairing(driver, timeout=10):
        return "error", "引导页处理失败"

    result = wait_pairing_result(driver, target_dev)
    if result == "success":
        return "success", "配网成功"
    if result == "success_need_next":
        # 处理配网成功后的收尾流程（Next -> Already paired -> 回首页）
        if pairing_result_module:
            def is_home_func(drv):
                home_xpaths = [
                    '//XCUIElementTypeButton[@name="home add device"]',
                    '//XCUIElementTypeButton[@name="home add"]',
                    '//XCUIElementTypeStaticText[contains(@name,"AquaSense")]',
                    '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
                    '//XCUIElementTypeStaticText[contains(@name,"设备")]',
                ]
                for xp in home_xpaths:
                    try:
                        elem = drv.find_element(AppiumBy.XPATH, xp)
                        if elem.is_displayed():
                            return True
                    except Exception:
                        continue
                return False
            
            if pairing_result_module.handle_post_pairing_success_flow(
                driver,
                timeout=35,
                is_home_func=is_home_func,
                log_func=log
            ):
                return "success", "配网成功"
            else:
                if is_home_func(driver):
                    log("✅ 收尾流程失败但页面已在首页，按成功处理")
                    return "success", "配网成功"
                else:
                    return "error", "配网成功后收尾步骤失败（Next/弹框/回Home）"
        else:
            log("⚠️ 配网结果模块未加载，无法处理收尾流程")
            return "error", "配网成功后收尾步骤失败（模块未加载）"
    if result == "failed":
        return "failed", "配网失败"
    return "timeout", "配网超时"


# ==================== 结果汇总和报告生成 ==================== #

def finalize_results(total_tests, success_count, failure_count, detailed_results, test_config, interrupted=False):
    """汇总测试结果并生成报告（调用 1共用脚本/测试报告.py 模块）"""
    if test_report_module:
        test_report_module.finalize_results(
            total_tests=total_tests,
            success_count=success_count,
            failure_count=failure_count,
            detailed_results=detailed_results,
            test_config=test_config,
            platform="iOS",
            network_method="2蓝牙配网",
            run_dir=RUN_DIR,
            log_func=log,
            interrupted=interrupted
        )
    else:
        # 回退到简单输出
        log("\n⚠️ 测试报告模块未加载，仅输出简单汇总")
        log(f"总测试次数: {total_tests}")
        log(f"成功次数: {success_count}")
        log(f"失败次数: {failure_count}")
        log(f"📁 报告目录: {RUN_DIR}")
        try:
            # 尝试从多个位置查找 excel_report_generator.py
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # 查找顺序：1. 1共用脚本 2. 旧 common 3. 当前脚本目录及子目录（向后兼容）
            search_paths = [
                os.path.join(SHARED_SCRIPTS_DIR, "excel_report_generator.py"),
                os.path.join(os.path.dirname(current_dir), "common", "excel_report_generator.py"),
                os.path.join(current_dir, "excel_report_generator.py"),
                os.path.join(current_dir, "IOS", "excel_report_generator.py"),
                os.path.join(os.path.dirname(current_dir), "excel_report_generator.py"),
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
                original_dir = os.getcwd()
                try:
                    # 切换到运行目录，让报告生成器保存到当前目录
                    os.chdir(str(RUN_DIR))
                    excel_file = create_network_compatibility_report(converted_results, platform="iOS", network_method="2蓝牙配网")
                finally:
                    os.chdir(original_dir)
                
                # 确保报告在运行目录中
                if excel_file and os.path.exists(excel_file):
                    excel_filename = os.path.basename(excel_file)
                    target_path = RUN_DIR / excel_filename
                    
                    # 如果文件不在运行目录，移动到运行目录
                    if os.path.abspath(excel_file) != str(target_path):
                        try:
                            import shutil
                            if os.path.exists(str(target_path)):
                                os.remove(str(target_path))  # 删除已存在的文件
                            shutil.move(excel_file, str(target_path))
                            log(f"✅ Excel报告已生成: {target_path}")
                        except Exception as e:
                            log(f"✅ Excel报告已生成: {excel_file} (移动到运行目录失败: {e})")
                    else:
                        log(f"✅ Excel报告已生成: {target_path}")
                else:
                    log(f"⚠️ Excel报告生成失败: 文件不存在")
            else:
                log(f"⚠️ 未找到 excel_report_generator.py，跳过Excel报告生成")
                log(f"   已搜索以下路径:")
                for path in search_paths:
                    log(f"     - {path}")
        except Exception as e:
            log(f"⚠️ Excel报告生成失败: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")


# ==================== 主入口：多设备 / 多路由 ==================== #

def main():
    log("🚀 启动全新 iOS 蓝牙配网脚本")
    log("=" * 80)

    cfg = load_config()
    if not cfg:
        return

    device_cfgs = cfg.get("device_configs", {})
    wifi_cfgs = cfg.get("wifi_configs", [])
    test_cfg = cfg.get("test_config", {})
    loop_per_router = int(test_cfg.get("loop_count_per_router", 1))

    # 机器人热点用 USB 串口（与每台手机的 Appium port 无关）
    _rsp = (test_cfg.get("robot_serial_port") or "").strip()
    if _rsp and not (os.environ.get("ROBOT_SERIAL_PORT") or "").strip():
        os.environ["ROBOT_SERIAL_PORT"] = _rsp
        log(f"📌 test_config.robot_serial_port → {_rsp}")
    _rsb = test_cfg.get("robot_serial_baud")
    if _rsb is not None and not os.environ.get("ROBOT_SERIAL_BAUD"):
        os.environ["ROBOT_SERIAL_BAUD"] = str(_rsb)

    # 从配置文件读取目标设备配置，如果没有配置则报错
    target_dev = cfg.get("target_device")
    if not target_dev:
        log("❌ 未找到 target_device 配置")
        log("💡 请在 device_config.json 中添加 target_device 配置，例如：")
        log('   "target_device": {')
        log('     "device_sn": "B0078",')
        log('     "device_name": "Sora 70",')
        log('     "description": "目标配网设备 - 机器人设备"')
        log('   }')
        return
    
    # 验证必需的配置项
    if not target_dev.get("device_sn"):
        log("❌ target_device.device_sn 未配置")
        log("💡 请在 device_config.json 的 target_device 中添加 device_sn 字段")
        return
    
    if not target_dev.get("device_name"):
        log("❌ target_device.device_name 未配置")
        log("💡 请在 device_config.json 的 target_device 中添加 device_name 字段")
        return
    
    log(f"✅ 目标设备配置: {target_dev.get('device_name')} (SN: {target_dev.get('device_sn')})")

    log(f"📱 iOS 设备数量: {len(device_cfgs)}")
    log(f"📶 路由器数量: {len(wifi_cfgs)}")
    log(f"🔁 每个路由器循环次数: {loop_per_router}")

    total = 0
    succ = 0
    fail = 0
    detailed_results = {}  # 详细测试结果
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
            
            # 初始化设备结果
            if device_name not in detailed_results:
                detailed_results[device_name] = {"routers": {}}
            
            try:
                for wifi in wifi_cfgs:
                    name = wifi["name"]
                    pwd = wifi["password"]
                    log(f"\n📶 路由器: {name}")
                    
                    # 初始化路由器结果
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
                        res, msg = run_single_flow(driver, name, pwd, target_dev)
                        
                        # 记录测试结果
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
        # 无论正常结束还是中断，都生成报告
        finalize_results(total, succ, fail, detailed_results, test_cfg, interrupted=interrupted)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n⚠️ 用户中断脚本")
        # 这里不需要额外处理，main() 的 finally 块会处理
    except Exception as e:
        log(f"\n❌ 脚本异常: {e}")
        import traceback
        log(f"详细错误: {traceback.format_exc()}")
