#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全新 Android 蓝牙配网脚本（参考 iOS 脚本结构，调用 common 模块）

注意：
- 参考 iOS-2蓝牙配网.py 的结构，精简代码
- 调用 common/选择设备.py 和 common/选择WIFI.py 模块
- 目前以"单线程串行跑多设备 / 多路由"为目标
"""

import os
import sys
import json
import time
import logging
import subprocess
from datetime import datetime
from typing import Any

from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# P0025-V1：共用脚本在 1共用脚本/（旧版为 common/）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_P0025_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", ".."))
SHARED_SCRIPTS_DIR = os.path.join(_P0025_PROJECT_ROOT, "1共用脚本")

try:
    from report_utils import init_run_env
except ImportError:
    sys.path.insert(0, SHARED_SCRIPTS_DIR)
    from report_utils import init_run_env

# ==================== 日志与输出目录初始化 ====================

# 为 Android 配网任务创建本次运行的输出目录
RUN_DIR, LOG_FILE, SCREENSHOT_DIR = init_run_env(prefix="2蓝牙配网-Android")

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


# ==================== 导入 1共用脚本 模块 ====================

# 导入测试报告模块
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

# 导入独立的设备选择模块
select_device_from_module = None
try:
    import importlib.util

    device_selector_file = os.path.join(SHARED_SCRIPTS_DIR, "选择设备.py")
    if os.path.exists(device_selector_file):
        spec = importlib.util.spec_from_file_location("device_selector", device_selector_file)
        if spec and spec.loader:
            device_selector_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(device_selector_module)
            select_device_from_module = device_selector_module.select_device
            log("✅ 已加载独立设备选择模块: 选择设备.py")
    else:
        log(f"⚠️ 未找到独立设备选择模块: {device_selector_file}")
except Exception as e:
    log(f"⚠️ 无法加载独立设备选择模块: {e}")

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
        log(f"⚠️ 未找到 WiFi 选择模块: {wifi_setup_file}")
except Exception as e:
    log(f"⚠️ 无法加载 WiFi 选择模块: {e}")

# 导入重置应用模块
reset_app_module = None
try:
    import importlib.util

    reset_app_file = os.path.join(SHARED_SCRIPTS_DIR, "重置应用-Android.py")
    if os.path.exists(reset_app_file):
        spec = importlib.util.spec_from_file_location("重置应用", reset_app_file)
        if spec and spec.loader:
            重置应用 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(重置应用)
            reset_app_module = 重置应用
            log("✅ 已加载重置应用模块: 重置应用-Android.py")
    else:
        log(f"⚠️ 未找到重置应用模块: {reset_app_file}")
except Exception as e:
    log(f"⚠️ 无法加载重置应用模块: {e}")

# 导入配网结果模块
pairing_result_module = None
try:
    import importlib.util

    pairing_result_file = os.path.join(SHARED_SCRIPTS_DIR, "配网结果-Android.py")
    if os.path.exists(pairing_result_file):
        spec = importlib.util.spec_from_file_location("配网结果", pairing_result_file)
        if spec and spec.loader:
            配网结果 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(配网结果)
            pairing_result_module = 配网结果
            log("✅ 已加载配网结果模块: 配网结果-Android.py")
    else:
        log(f"⚠️ 未找到配网结果模块: {pairing_result_file}")
except Exception as e:
    log(f"⚠️ 无法加载配网结果模块: {e}")


# ==================== 公共工具 ==================== #

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
    只保留 platform == 'android' 的设备。
    """
    # 1. 环境变量
    env_path = os.environ.get("DEVICE_CONFIG_FILE")
    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log(f"✅ 从环境变量配置文件加载: {env_path}")
            return _filter_android_devices(cfg)
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
            return _filter_android_devices(cfg)
        except Exception as e:
            log(f"⚠️ 加载 1共用脚本 配置失败: {e}")

    # 3. 上级目录（向后兼容）
    parent_cfg = os.path.join(os.path.dirname(base_dir), "device_config.json")
    if os.path.exists(parent_cfg):
        try:
            with open(parent_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log(f"✅ 从上级目录加载配置: {parent_cfg}")
            return _filter_android_devices(cfg)
        except Exception as e:
            log(f"⚠️ 加载上级目录配置失败: {e}")

    # 4. 当前目录（向后兼容）
    local_cfg = os.path.join(base_dir, "device_config.json")
    if os.path.exists(local_cfg):
        try:
            with open(local_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log(f"✅ 从当前目录加载配置: {local_cfg}")
            return _filter_android_devices(cfg)
        except Exception as e:
            log(f"⚠️ 加载当前目录配置失败: {e}")

    log("❌ 未找到任何配置文件，请确认 device_config.json 是否存在")
    return None


def _filter_android_devices(config: dict) -> dict:
    """过滤出 Android 设备"""
    devs = config.get("device_configs", {})
    android_devs = {
        key: val for key, val in devs.items()
        if str(val.get("platform", "android")).lower() == "android"
    }
    config = dict(config)
    config["device_configs"] = android_devs
    return config


# ==================== 触发机器人热点 ==================== #

# 机器人热点触发方式（P0024-M0：串口screen触发）
SERIAL_PORT = os.environ.get("ROBOT_SERIAL_PORT", "/dev/tty.usbserial-1120")
SERIAL_BAUD = os.environ.get("ROBOT_SERIAL_BAUD", "115200")
SERIAL_TRIGGER_CMD = os.environ.get("ROBOT_SERIAL_CMD", "SET state 4")

def _find_available_serial_ports() -> list:
    """查找所有可用的串口设备（与 iOS 同类逻辑，提升端口选择鲁棒性）"""
    available_ports = []
    try:
        import glob

        tty_ports = glob.glob("/dev/tty.usbserial*") + glob.glob("/dev/tty.usbmodem*")
        cu_ports = glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*")

        all_ports = list(set(tty_ports + cu_ports))
        for port in all_ports:
            # 只要求读权限即可，serial 通常也能写；若不能写会在后续触发失败并报错
            if os.path.exists(port) and os.access(port, os.R_OK):
                available_ports.append(port)

        # 排序：优先 usbserial，其次其它
        available_ports.sort(key=lambda x: ("usbserial" not in x, x))
    except Exception:
        pass
    return available_ports


def _resolve_serial_port_for_hotspot() -> tuple[str | None, str]:
    """
    解析用于触发热点的串口路径。
    优先：环境变量 ROBOT_SERIAL_PORT（若可用）
    回退：从枚举列表中选一个可用端口
    """
    explicit = (os.environ.get("ROBOT_SERIAL_PORT") or "").strip()
    candidates = _find_available_serial_ports()

    # 1) 优先使用环境变量指定端口
    if explicit:
        if os.path.exists(explicit) and os.access(explicit, os.R_OK):
            return explicit, "环境变量 ROBOT_SERIAL_PORT"
        log(f"⚠️ ROBOT_SERIAL_PORT={explicit} 不存在或无读权限，改为自动枚举…")

    # 2) 兼容默认值（与旧逻辑保持一致）
    guess = SERIAL_PORT
    if os.path.exists(guess) and os.access(guess, os.R_OK):
        return guess, "默认/内置串口路径"

    # 3) 枚举选择：macOS 更偏好 /dev/cu.*（与 iOS 行为一致）
    if candidates:
        darwin = (os.uname().sysname.lower() == "darwin")
        if darwin:
            cu = sorted(p for p in candidates if p.startswith("/dev/cu."))
            if cu:
                return cu[0], "自动枚举（优先 cu.*）"
        return sorted(candidates)[0], "自动枚举（第一个可用端口）"

    return None, ""


def trigger_robot_hotspot() -> bool:
    """
    触发机器热点（P0024-M0：使用端口命令脚本）
    优先使用端口命令.py脚本，如果失败则回退到expect方式
    """
    log("📡 步骤1: 触发机器热点...")
    port, port_src = _resolve_serial_port_for_hotspot()
    baud = int(os.environ.get("ROBOT_SERIAL_BAUD", str(SERIAL_BAUD)))
    cmd = os.environ.get("ROBOT_SERIAL_CMD", SERIAL_TRIGGER_CMD)

    if not port:
        log("❌ 未找到可用串口，无法触发热点")
        return False

    log(f"📌 串口: {port}（{port_src}） / baud={baud} / cmd={cmd}")

    port_command_script = os.path.join(SHARED_SCRIPTS_DIR, "端口命令.py")
    normal_wait_s = int(os.environ.get("ROBOT_HOTSPOT_WAIT_SECONDS", "12"))
    reboot_wait_s = int(os.environ.get("ROBOT_HOTSPOT_REBOOT_WAIT_SECONDS", "35"))

    def _post_trigger_wait(output_text: str) -> None:
        text = (output_text or "").lower()
        reboot_markers = [
            "rst:0xc",
            "sw_cpu",
            "esp-rom:",
            "2nd stage bootloader",
            "loaded app from partition",
        ]
        has_reboot = any(m in text for m in reboot_markers)
        wait_s = reboot_wait_s if has_reboot else normal_wait_s
        if has_reboot:
            log(f"⏳ 检测到设备重启日志，热点拉起可能更慢，等待 {wait_s}s ...")
        else:
            log(f"⏳ 未检测到重启日志，等待热点稳定 {wait_s}s ...")
        time.sleep(wait_s)

    # 如果找到端口命令脚本，优先使用
    if os.path.exists(port_command_script):
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
                log(f"✅ 串口热点触发成功")
                _post_trigger_wait(f"{result.stdout}\n{result.stderr}")
                return True
            else:
                if result.stdout and result.stdout.strip():
                    log(f"⚠️ 端口命令脚本 stdout: {result.stdout.strip()}")
                if result.stderr and result.stderr.strip():
                    log(f"⚠️ 端口命令脚本 stderr: {result.stderr.strip()}")
                log(f"⚠️ 端口命令脚本触发失败，回退到expect方式...")
        except Exception as e:
            log(f"⚠️ 端口命令脚本执行异常: {e}，回退到expect方式...")
    else:
        log(f"⚠️ 未找到端口命令脚本: {port_command_script}，使用expect方式...")

    # 回退到expect方式（保留原有逻辑作为备用）
    log(f"🔌 使用expect方式触发热点（备用方案）...")
    try:
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
        script_path = '/tmp/android_serial_trigger_hotspot.exp'
        with open(script_path, 'w') as f:
            f.write(expect_script)
        os.chmod(script_path, 0o755)

        result = subprocess.run(
            ['expect', script_path],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            if result.stdout and result.stdout.strip():
                log(f"ℹ️ expect stdout: {result.stdout.strip()}")
            if result.stderr and result.stderr.strip():
                log(f"ℹ️ expect stderr: {result.stderr.strip()}")
            log(f"✅ 串口热点触发成功（expect方式）")
            _post_trigger_wait(f"{result.stdout}\n{result.stderr}")
            return True
        else:
            if result.stdout and result.stdout.strip():
                log(f"⚠️ expect stdout: {result.stdout.strip()}")
            if result.stderr and result.stderr.strip():
                log(f"⚠️ expect stderr: {result.stderr.strip()}")
            log(f"❌ expect方式触发失败")
        return False
    except Exception as e:
        log(f"❌ 所有触发方式都失败: {e}")
        return False


# ==================== Appium / driver ==================== #

def create_driver(dev_cfg: dict):
    """根据 device_config 为单个 Android 设备创建 Appium driver"""
    from appium.options.android import UiAutomator2Options

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name = dev_cfg["device_name"]
    options.platform_version = dev_cfg["platform_version"]
    options.app_package = dev_cfg["app_package"]
    if "app_activity" in dev_cfg:
        options.app_activity = dev_cfg["app_activity"]
    options.automation_name = "UiAutomator2"
    options.no_reset = True
    options.new_command_timeout = 300
    options.auto_launch = True

    if "udid" in dev_cfg:
        options.udid = dev_cfg["udid"]

    server_url = f"http://127.0.0.1:{dev_cfg['port']}"

    try:
        log(f"🔗 尝试连接 Appium 服务器: {server_url}")
        driver = webdriver.Remote(server_url, options=options)
        log(f"✅ 设备 {dev_cfg.get('description', dev_cfg['device_name'])} 连接成功")
        return driver
    except Exception as e:
        log(f"❌ 创建设备驱动失败: {e}")
        return None


def _is_session_terminated_error(err: Exception) -> bool:
    """判断是否为 Appium 会话失效错误。"""
    err_str = str(err).lower()
    return (
        "session is either terminated" in err_str or
        "invalidsessionid" in err_str or
        "nosuchdriver" in err_str or
        "a session is either terminated or not started" in err_str or
        "session not created" in err_str
    )


def reset_app_to_home(driver) -> tuple[bool, Any]:
    """重启 App 并尽量返回首页，返回 (success, driver_or_new_driver)。"""
    if reset_app_module:
        def get_adb_path_func():
            android_home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
            if android_home:
                adb_path = os.path.join(android_home, 'platform-tools', 'adb')
                if os.path.exists(adb_path):
                    return adb_path
            return 'adb'

        def check_is_on_home_page_func(drv):
            home_xpaths = [
                '(//android.widget.ImageView[@content-desc="add"])[2]',
                '//android.widget.ImageView[@content-desc="add"]',
                '//android.widget.TextView[contains(@text,"设备")]',
                '//android.widget.TextView[contains(@text,"Sora")]',
            ]
            for xp in home_xpaths:
                try:
                    elem = drv.find_element(AppiumBy.XPATH, xp)
                    if elem.is_displayed():
                        return True
                except Exception:
                    continue
            return False

        success, new_driver = reset_app_module.reset_app_to_home(
            driver,
            device_config=None,
            get_adb_path_func=get_adb_path_func,
            check_is_on_home_page_func=check_is_on_home_page_func,
            create_device_driver_func=None,
            is_driver_crashed_error_func=None,
            is_session_terminated_error_func=_is_session_terminated_error,
            log_func=log
        )
        if success and new_driver is not None and new_driver is not driver:
            log("♻️ reset_app_to_home 返回了新会话，已切换到 new_driver")
            return True, new_driver
        return success, driver

    log("⚠️ 重置应用模块未加载，使用内部实现")
    log("🔄 重置应用到首页...")
    try:
        caps = getattr(driver, "capabilities", {}) or {}
        app_package = caps.get("appPackage") or os.environ.get("ANDROID_APP_PACKAGE")
        if not app_package:
            log("⚠️ 无法获取 appPackage，跳过应用重启")
            return True, driver

        driver.terminate_app(app_package)
        time.sleep(2)
        driver.activate_app(app_package)
        time.sleep(3)

        home_xpaths = [
            '(//android.widget.ImageView[@content-desc="add"])[2]',
            '//android.widget.ImageView[@content-desc="add"]',
        ]
        for xp in home_xpaths:
            try:
                elem = driver.find_element(AppiumBy.XPATH, xp)
                if elem.is_displayed():
                    log(f"✅ 确认在首页: {xp}")
                    return True, driver
            except Exception:
                continue
        log("⚠️ 无法确认是否在首页，但应用已重启")
        return True, driver
    except Exception as e:
        log(f"⚠️ 重置应用失败: {e}")
        return False, driver


# ==================== 首页 add device ==================== #

def ensure_home_add_button(driver) -> bool:
    """确保首页有 add 按钮"""
    log("🔍 检查首页 add 按钮...")
    time.sleep(2)

    add_button_selectors = [
        '(//android.widget.ImageView[@content-desc="add"])[2]',  # 优先：第二个 add 按钮
        '//android.widget.ImageView[@content-desc="add"]',      # 第一个 add 按钮
        '//android.widget.ImageView[contains(@content-desc,"add")]',
        '//android.widget.Button[contains(@text,"Add")]',
        '//android.widget.Button[contains(@text,"添加")]',
    ]

    for selector in add_button_selectors:
        try:
            btn = driver.find_element(AppiumBy.XPATH, selector)
            if btn.is_displayed():
                # 验证元素位置和大小
                try:
                    location = btn.location
                    size = btn.size
                    if location['x'] >= 0 and location['y'] >= 0 and size['width'] > 0 and size['height'] > 0:
                        log(f"✅ 找到add按钮（选择器: {selector}）")
                        return True
                except Exception:
                    # 如果无法获取位置，也认为找到了
                    log(f"✅ 找到add按钮（选择器: {selector}）")
                    return True
        except Exception:
            continue

    log("⚠️ 未找到add按钮")
    return False


def _android_home_has_paired_device(driver) -> bool:
    """
    检查 Android 首页是否存在已配对设备（用于决定是否要先删除）。
    逻辑参考项目里扫码配网脚本：同时用“设备文案”和 more 按钮做双重判断。
    """
    device_indicators = [
        "//android.widget.TextView[contains(@text,'Sora')]",
        "//android.widget.TextView[contains(@text,'robot')]",
        "//android.widget.TextView[contains(@text,'设备')]",
        "//android.widget.TextView[contains(@text,'standby')]",
    ]
    for xp in device_indicators:
        try:
            elems = driver.find_elements(AppiumBy.XPATH, xp)
            if elems:
                for e in elems:
                    if e.is_displayed():
                        return True
        except Exception as e:
            if _is_session_terminated_error(e):
                raise RuntimeError(f"Appium 会话已失效: {e}") from e
            continue

    # more 按钮通常更稳定：可视即认为有设备可管理
    more_selectors = [
        '//android.widget.ImageView[@content-desc="more"]',
        '//android.widget.Button[@content-desc="more"]',
        '//android.view.View[@content-desc="more"]',
    ]
    for xp in more_selectors:
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            if el.is_displayed():
                return True
        except Exception as e:
            if _is_session_terminated_error(e):
                raise RuntimeError(f"Appium 会话已失效: {e}") from e
            continue

    # 兜底：你提供的“next”按钮出现时也视为存在可删除设备
    next_selectors = [
        '//android.widget.ImageView[@content-desc="next"]',
        '//android.widget.Button[@content-desc="next"]',
    ]
    for xp in next_selectors:
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            if el.is_displayed():
                return True
        except Exception as e:
            if _is_session_terminated_error(e):
                raise RuntimeError(f"Appium 会话已失效: {e}") from e
            continue
    return False


def delete_paired_device_android(driver) -> bool:
    """删除 Android 首页已配对设备（more -> Remove -> Confirm）"""
    log("🔧 检测到已配对设备，开始删除设备...")
    try:
        # 点击 more
        more_selectors = [
            '//android.widget.ImageView[@content-desc="more"]',
            '//android.widget.Button[@content-desc="more"]',
            '//android.view.View[@content-desc="more"]',
        ]
        more_button = None
        for selector in more_selectors:
            try:
                more_button = driver.find_element(AppiumBy.XPATH, selector)
                if more_button.is_displayed():
                    log(f"✅ 找到 more 按钮: {selector}")
                    break
            except Exception:
                continue
        if not more_button:
            log("⚠️ 未找到 more 按钮，可能没有已配对设备")
            return False

        more_button.click()
        time.sleep(2)

        # 点击 Remove
        remove_selectors = [
            '//android.widget.TextView[@text="Remove"]',
            '//android.widget.Button[@text="Remove"]',
            '//android.widget.TextView[contains(@text,"Remove")]',
        ]
        remove_button = None
        for selector in remove_selectors:
            try:
                remove_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if remove_button.is_displayed():
                    log(f"✅ 找到 Remove 按钮: {selector}")
                    break
            except Exception:
                continue
        if not remove_button:
            log("⚠️ 未找到 Remove 按钮")
            return False

        remove_button.click()
        time.sleep(2)

        # 点击 Confirm
        confirm_selectors = [
            '//android.widget.TextView[@text="Confirm"]',
            '//android.widget.Button[@text="Confirm"]',
            '//android.widget.TextView[contains(@text,"Confirm")]',
            '//android.widget.Button[contains(@text,"确认")]',
        ]
        confirm_button = None
        for selector in confirm_selectors:
            try:
                confirm_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if confirm_button.is_displayed():
                    log(f"✅ 找到 Confirm 按钮: {selector}")
                    break
            except Exception:
                continue
        if not confirm_button:
            log("⚠️ 未找到 Confirm 按钮")
            return False

        confirm_button.click()
        time.sleep(3)
        log("✅ 删除设备 Confirm 点击成功，等待页面刷新...")

        # 尝试重新激活应用，刷新首页状态
        try:
            app_package = driver.capabilities.get("appPackage")
            if app_package:
                driver.activate_app(app_package)
        except Exception:
            pass
        time.sleep(2)

        return True
    except Exception as e:
        log(f"❌ 删除设备失败: {e}")
        try:
            take_screenshot(driver, "delete_paired_device_fail")
        except Exception:
            pass
        return False


def cleanup_home_devices_android(driver) -> bool:
    """检测首页是否有设备，若有则删除。返回删除是否成功（不成功也可继续尝试）。"""
    try:
        has_paired = _android_home_has_paired_device(driver)
    except Exception as e:
        log(f"❌ 首页设备检测失败: {e}")
        return False

    if not has_paired:
        log("✅ 首页未检测到已配对设备，无需删除")
        return True

    log("⚠️ 首页已存在可删除设备，开始清理（more->Remove->Confirm）...")
    for i in range(2):
        ok = delete_paired_device_android(driver)
        if ok and not _android_home_has_paired_device(driver):
            log("✅ 删除已配对设备完成")
            return True
        if i < 1:
            log(f"⚠️ 第 {i+1}/2 次删除后仍检测到设备，重试...")
            time.sleep(2)

    # 最终要求：回到首页且 add 按钮出现
    if ensure_home_add_button(driver):
        log("✅ 清理完成：add 按钮已就绪")
        return True
    log("❌ 清理完成后仍未检测到 add 按钮，认为删除/返回可能未成功")
    try:
        take_screenshot(driver, "cleanup_home_devices_fail")
    except Exception:
        pass
    return False


def tap_add_device(driver) -> bool:
    """点击 add device 按钮"""
    log("📱 步骤2: 点击添加设备按钮...")
    # 优先使用第二个 add 按钮（根据用户提供的信息）
    add_button_selectors = [
        '(//android.widget.ImageView[@content-desc="add"])[2]',  # 优先：第二个 add 按钮
        '//android.widget.ImageView[@content-desc="add"]',      # 第一个 add 按钮
        '//android.widget.ImageView[contains(@content-desc,"add")]',
        '//android.widget.Button[contains(@text,"Add")]',
        '//android.widget.Button[contains(@text,"添加")]',
    ]

    for selector in add_button_selectors:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            if btn.is_displayed():
                btn.click()
                log(f"✅ 点击添加设备按钮成功（选择器: {selector}）")
                time.sleep(2)
                return True
        except Exception:
            continue

    log("❌ 点击添加设备按钮失败")
    take_screenshot(driver, "tap_add_device_fail")
    return False


# ==================== 设备选择 ==================== #

def pick_target_device(driver, target: dict) -> bool:
    """
    在设备选择列表中选择指定 SN 的设备
    优先调用 common/选择设备.py 中的独立模块
    """
    # 优先使用独立的设备选择模块
    if select_device_from_module:
        try:
            log("🔌 使用独立设备选择模块: common/选择设备.py")
            result = select_device_from_module(
                driver=driver,
                target_device_config=target,
                platform="android",
                log_func=log,
                screenshot_dir=SCREENSHOT_DIR,
            )
            if result:
                log("✅ 独立设备选择模块执行成功")
                return True
            log("⚠️ 独立设备选择模块执行失败")
        except Exception as e:
            log(f"⚠️ 调用独立设备选择模块失败: {e}，回退到内置函数")
            import traceback
            log(f"   详细错误: {traceback.format_exc()}")

    log("❌ 设备选择失败（模块未加载或执行失败）")
    return False


# ==================== WiFi 设置流程 ==================== #

def perform_wifi_setup(driver, wifi_name: str, wifi_pwd: str) -> bool:
    """整体 WiFi 设置步骤（调用 common/选择WIFI.py 模块）"""
    if wifi_setup_module:
        return wifi_setup_module.perform_wifi_setup(
            driver=driver,
            wifi_name=wifi_name,
            wifi_password=wifi_pwd,
            platform="android",
            log_func=log,
            screenshot_func=take_screenshot,
        )
    else:
        log("⚠️ WiFi 选择模块未加载，无法执行 WiFi 设置")
        return False


# ==================== 配网进度 & 结果 ==================== #


def handle_wifi_guide_page_after_wifi_next_android(driver: Any, timeout: int = 10) -> bool:
    """
    WiFi 设置完成后、进入配网进程前的 Android 引导页处理：
    1) 勾选：//android.widget.ImageView[@content-desc="checkbox"]
    2) 点击 Next：//android.widget.Button

    - 如果短等待时间内没找到 checkbox：认为没有引导页，返回 True（不阻断流程）
    - 如果找到 checkbox 但点击/Next 失败：返回 False
    """
    checkbox_xp = '//android.widget.ImageView[@content-desc="checkbox"]'
    next_btn_xp = '//android.widget.Button'

    # 短等待：只判断引导页是否出现
    try:
        checkbox = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((AppiumBy.XPATH, checkbox_xp))
        )
        if not checkbox or not checkbox.is_displayed():
            log("ℹ️ 未显示到配网引导页 checkbox，跳过该步骤")
            return True
    except Exception:
        log("ℹ️ 未出现配网引导页（checkbox 未找到），跳过该步骤")
        return True

    log("🧷 配网引导页：找到 checkbox，点击勾选...")
    try:
        checkbox.click()
        time.sleep(0.5)
    except Exception as e:
        log(f"❌ 配网引导页：点击 checkbox 失败: {e}")
        take_screenshot(driver, "wifi_guide_checkbox_fail")
        return False

    log("➡️ 配网引导页：点击 Next 按钮（//android.widget.Button）...")
    try:
        next_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, next_btn_xp))
        )
        next_btn.click()
        time.sleep(1.5)
        return True
    except Exception as e:
        log(f"❌ 配网引导页：点击 Button(Next) 失败: {e}")
        take_screenshot(driver, "wifi_guide_next_fail")
        return False

# ==================== 配网进度 & 结果 ==================== #

def wait_pairing_result(driver, target_dev: dict = None, timeout: int = 180) -> str:
    """等待配网结果：success / failed / timeout / success_need_next（优先使用 1共用脚本 配网结果模块）"""

    def is_home_func(drv):
        home_xpaths = [
            '//android.view.View[@content-desc="Home"]',
            '//android.widget.TextView[contains(@text,"AquaSense")]',
            '(//android.widget.ImageView[@content-desc="add"])[2]',
            '//android.widget.ImageView[@content-desc="add"]',
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
        return pairing_result_module.wait_for_pairing_result(
            driver,
            timeout=timeout,
            target_device_config=target_dev,
            is_home_func=is_home_func,
            log_func=log
        )

    log("⚠️ 配网结果模块未加载，使用内部实现")
    log("⏳ 步骤6: 等待配网结果...")
    start = time.time()
    dev_name = (target_dev or {}).get("device_name", "")
    dev_sn = str((target_dev or {}).get("device_sn", "")).strip()
    sn_digits = dev_sn.lstrip("Bb") if dev_sn else ""
    sn_with_b = f"B{sn_digits}" if sn_digits and not dev_sn.upper().startswith("B") else dev_sn

    while time.time() - start < timeout:
        try:
            try:
                pairing_text = driver.find_element(
                    AppiumBy.XPATH,
                    '//android.widget.TextView[@text="Pairing with your device"]'
                )
                if pairing_text.is_displayed():
                    log("🔄 配网进行中 ...")
                    time.sleep(5)
                    continue
            except Exception:
                pass

            # 优先按目标设备名/SN 判断成功，避免仅命中 "robot" 造成误判
            target_success_indicators = []
            if dev_name:
                target_success_indicators.extend([
                    f'//android.widget.TextView[@text="{dev_name}"]',
                    f'//android.widget.TextView[contains(@text,"{dev_name}")]',
                ])
            if dev_sn:
                target_success_indicators.extend([
                    f'//android.widget.TextView[contains(@text,"{dev_sn}")]',
                    f'//android.widget.TextView[contains(@text,"SN:{dev_sn}")]',
                    f'//android.widget.TextView[contains(@text,"SN: {dev_sn}")]',
                ])
            if sn_digits and sn_digits != dev_sn:
                target_success_indicators.extend([
                    f'//android.widget.TextView[contains(@text,"{sn_digits}")]',
                    f'//android.widget.TextView[contains(@text,"SN:{sn_digits}")]',
                    f'//android.widget.TextView[contains(@text,"SN: {sn_digits}")]',
                ])
            if sn_with_b and sn_with_b not in (dev_sn, sn_digits):
                target_success_indicators.extend([
                    f'//android.widget.TextView[contains(@text,"{sn_with_b}")]',
                    f'//android.widget.TextView[contains(@text,"SN:{sn_with_b}")]',
                    f'//android.widget.TextView[contains(@text,"SN: {sn_with_b}")]',
                ])

            matched_target = False
            for indicator in target_success_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, indicator)
                    if elem.is_displayed():
                        log(f"✅ 配网成功（命中目标设备）: {indicator}")
                        return "success"
                except Exception:
                    continue

            # 无 target 配置时，才使用弱信号成功条件（兼容旧行为）
            if not dev_name and not dev_sn:
                fallback_success_indicators = [
                    '//android.widget.ImageView[@content-desc="robot"]',
                    '//android.widget.TextView[contains(@text,"robot")]',
                    '//android.widget.TextView[contains(@text,"设备")]',
                ]
                for indicator in fallback_success_indicators:
                    try:
                        elem = driver.find_element(AppiumBy.XPATH, indicator)
                        if elem.is_displayed():
                            log(f"✅ 配网成功（弱信号）: {indicator}")
                            return "success"
                    except Exception:
                        continue

            failure_indicators = [
                '//android.widget.TextView[@text="Data transmitting failed."]',
                '//android.widget.TextView[contains(@text,"failed")]',
                '//android.widget.TextView[contains(@text,"失败")]',
            ]

            for indicator in failure_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, indicator)
                    if elem.is_displayed():
                        log(f"❌ 配网失败: {indicator}")
                        return "failed"
                except Exception:
                    continue

            time.sleep(3)
        except Exception as e:
            log(f"⚠️ 检查配网结果时出错: {e}")
            time.sleep(3)

    log("⏰ 配网超时")
    return "timeout"


# ==================== 单次配网流程 ==================== #

def run_single_flow(driver, wifi_name: str, wifi_pwd: str, target_dev: dict) -> tuple[str, str, Any]:
    """单次配网完整流程，返回 (result, message, driver)。"""
    log(f"\n🔄 开始单次配网流程（WiFi: {wifi_name}）")
    log("=" * 60)

    ok, driver = reset_app_to_home(driver)
    if not ok:
        # 关键：会话失效时必须让上层重建 driver，不能继续用坏会话
        try:
            driver.get_window_size()
        except Exception as e:
            if _is_session_terminated_error(e):
                log("❌ 检测到 Appium 会话已失效，需重建 driver")
                return "error", "DRIVER_SESSION_TERMINATED", driver
        log("⚠️ 应用重置失败，仍尝试继续")

    if not trigger_robot_hotspot():
        return "error", "触发机器热点失败", driver

    # 2) 检测首页是否有可删除设备：仅走 more->Remove->Confirm
    if not cleanup_home_devices_android(driver):
        return "error", "首页设备清理失败", driver

    add2_xpath = '(//android.widget.ImageView[@content-desc="add"])[2]'
    try:
        add2_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, add2_xpath))
        )
        if add2_btn.is_displayed():
            log(f"✅ 检测到 add2 按钮，点击进入设备选择页: {add2_xpath}")
            add2_btn.click()
            time.sleep(2)
        else:
            return "error", "add2 按钮不可见", driver
    except Exception as e:
        log(f"❌ 未找到/无法点击 add2 按钮，无法进入设备选择页: {e}")
        # 兜底：如果 add2 不在，用原有多选择器逻辑尝试一次
        if ensure_home_add_button(driver) and tap_add_device(driver):
            log("ℹ️ 走了 add 按钮兜底选择器，继续")
        else:
            return "error", "首页缺少 add2 按钮（且兜底失败）", driver

    if not pick_target_device(driver, target_dev):
        return "error", "设备选择失败", driver

    if not perform_wifi_setup(driver, wifi_name, wifi_pwd):
        return "error", "WiFi 设置失败", driver

    # WiFi 设置完成后：可能出现配网引导页（checkbox + Next），需要先完成引导页再进入配网进程
    if not handle_wifi_guide_page_after_wifi_next_android(driver, timeout=10):
        return "error", "配网引导页处理失败", driver

    result = wait_pairing_result(driver, target_dev)
    if result == "success":
        return "success", "配网成功", driver
    if result == "success_need_next":
        if pairing_result_module:
            def is_home_func(drv):
                home_xpaths = [
                    '//android.view.View[@content-desc="Home"]',
                    '//android.widget.TextView[contains(@text,"AquaSense")]',
                    '(//android.widget.ImageView[@content-desc="add"])[2]',
                    '//android.widget.ImageView[@content-desc="add"]',
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
                return "success", "配网成功", driver
            if is_home_func(driver):
                log("✅ 收尾流程失败但页面已在首页，按成功处理")
                return "success", "配网成功", driver
            return "error", "配网成功后收尾步骤失败（Next/弹框/回Home）", driver
        log("⚠️ 配网结果模块未加载，无法处理收尾流程")
        return "error", "配网成功后收尾步骤失败（模块未加载）", driver
    if result == "failed":
        return "failed", "配网失败", driver
    return "timeout", "配网超时", driver


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
            platform="Android",
            network_method="2蓝牙配网",
            run_dir=RUN_DIR,
            log_func=log,
            interrupted=interrupted,
        )
    else:
        log("\n⚠️ 测试报告模块未加载，仅输出简单汇总")
        log(f"总测试次数: {total_tests}")
        log(f"成功次数: {success_count}")
        log(f"失败次数: {failure_count}")
        log(f"📁 报告目录: {RUN_DIR}")


# ==================== 主入口：多设备 / 多路由 ==================== #

def main():
    log("🚀 启动全新 Android 蓝牙配网脚本")
    log("=" * 80)

    cfg = load_config()
    if not cfg:
        return

    device_cfgs = cfg.get("device_configs", {})
    wifi_cfgs = cfg.get("wifi_configs", [])
    test_cfg = cfg.get("test_config", {})
    loop_per_router = int(test_cfg.get("loop_count_per_router", 1))

    # 从配置文件读取目标设备配置
    target_dev = cfg.get("target_device")
    if not target_dev:
        log("❌ 未找到 target_device 配置")
        log("💡 请在 device_config.json 中添加 target_device 配置")
        return

    # 验证必需的配置项
    if not target_dev.get("device_sn"):
        log("❌ target_device.device_sn 未配置")
        return

    if not target_dev.get("device_name"):
        log("❌ target_device.device_name 未配置")
        return

    log(f"✅ 目标设备配置: {target_dev.get('device_name')} (SN: {target_dev.get('device_sn')})")
    log(f"📱 Android 设备数量: {len(device_cfgs)}")
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
                        retried_dead_session = False
                        while True:
                            res, msg, driver = run_single_flow(driver, name, pwd, target_dev)
                            if res == "error" and msg == "DRIVER_SESSION_TERMINATED" and not retried_dead_session:
                                log("♻️ 当前会话已失效，尝试重建 driver 并重试当前轮次...")
                                try:
                                    driver.quit()
                                except Exception:
                                    pass
                                driver = create_driver(dev_cfg)
                                if not driver:
                                    log("❌ 重建 driver 失败，当前轮次记为失败")
                                    res, msg = "error", "driver 重建失败"
                                    break
                                retried_dead_session = True
                                continue
                            break

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
    except Exception as e:
        log(f"\n❌ 脚本异常: {e}")
        import traceback
        log(f"详细错误: {traceback.format_exc()}")
