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

# 尝试导入report_utils，优先从common目录导入
try:
    from report_utils import init_run_env
except ImportError:
    # 如果report_utils不在当前路径，尝试从common目录导入
    import os
    common_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common")
    sys.path.insert(0, common_path)
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

ROBOT_DEVICE_ID = os.environ.get("ROBOT_DEVICE_ID", "galaxy_p0001")


def trigger_robot_hotspot() -> bool:
    """
    触发机器人热点：
    adb -s galaxy_p0001 shell
    ros2 topic pub --once /USER_NET_INFO xm_robot_interfaces/msg/InternalIO '{msg_content: AP}'
    """
    log("📡 步骤1: 触发机器热点...")
    adb = get_adb_path()
    script = f"""#!/usr/bin/expect -f
set timeout 60
spawn {adb} -s {ROBOT_DEVICE_ID} shell
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
    path = "/tmp/ios_bt_hotspot.exp"
    try:
        with open(path, "w") as f:
            f.write(script)
        os.chmod(path, 0o755)

        result = subprocess.run(
            ["expect", path],
            capture_output=True,
            text=True,
            timeout=90
        )
        if result.returncode == 0:
            log("✅ ROS2 消息发送成功")
            if result.stdout.strip():
                log("ℹ️ ROS2 输出:\n" + result.stdout.strip())
            return True
        log("❌ ROS2 消息发送失败: " + result.stderr.strip())
        return False
    except Exception as e:
        log(f"❌ 触发机器热点失败: {e}")
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
    """重启 App 并尽量返回首页，如果有已配对设备则先删除"""
    log("🔄 重置应用到首页...")
    try:
        caps = getattr(driver, "capabilities", {}) or {}
        bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
        if not bundle_id:
            log("⚠️ 无法获取 bundleId，跳过应用重启")
            return True

        driver.terminate_app(bundle_id)
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
        driver.activate_app(bundle_id)
        time.sleep(3)  # 等待应用启动和页面加载完成

        # 检查是否有已配对的设备，如果有则删除
        log("🔍 检查页面是否有已配对的设备...")
        if _has_paired_device(driver):
            log("⚠️ 检测到已配对设备，执行删除操作...")
            if not _remove_existing_device(driver):
                log("⚠️ 删除设备失败，但继续执行后续流程")
            else:
                log("✅ 已删除已配对设备")
                # 删除后等待页面刷新
                time.sleep(3)
        else:
            log("✅ 未检测到已配对设备，页面状态正常")

        # 检查首页是否有 add 按钮，如果没有则尝试删除设备（双重检查）
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
    """检查首页是否有add按钮，支持多种选择器"""
    add_button_selectors = [
        '//XCUIElementTypeButton[@name="home add"]',
        '//XCUIElementTypeButton[@name="Add"]',
        '//XCUIElementTypeButton[contains(@name,"add")]',
        '//XCUIElementTypeButton[contains(@name,"Add")]',
        '//XCUIElementTypeButton[@name="+"]',
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
    """检查是否有已配对的设备"""
    device_indicators = [
        '//XCUIElementTypeButton[@name="device down unsel"]',
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
    """执行删除已配对设备的一整套操作"""
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
            time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
            break
        except Exception as e:
            log(f"⚠️ Remove按钮选择器失败: {selector} - {e}")
            continue
    
    if not remove_clicked:
        log("⚠️ 无法点击Remove按钮，跳过删除操作")
        return False
    
    # 点击Confirm按钮
    confirm_selectors = [
        '//XCUIElementTypeButton[@name="Confirm"]',
        '//XCUIElementTypeStaticText[@name="Confirm"]',
        '//XCUIElementTypeButton[contains(@name,"Confirm")]',
        '//XCUIElementTypeButton[contains(@name,"确认")]',
    ]
    
    confirm_clicked = False
    for selector in confirm_selectors:
        try:
            log(f"🔍 尝试Confirm按钮: {selector}")
            elem = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            elem.click()
            log(f"✅ 点击Confirm按钮成功: {selector}")
            confirm_clicked = True
            time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
            break
        except Exception as e:
            log(f"⚠️ Confirm按钮选择器失败: {selector} - {e}")
            continue
    
    if not confirm_clicked:
        log("⚠️ 无法点击Confirm按钮，但继续执行刷新操作")
    
    # 删除后刷新页面2次（不重置应用，避免网速问题导致加载失败）
    log("🔄 删除设备后刷新页面（第1次）...")
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
    
    log("🔄 刷新页面（第2次）...")
    try:
        # 再次尝试下拉刷新
        size = driver.get_window_size()
        start_x = size['width'] // 2
        start_y = int(size['height'] * 0.2)
        end_y = int(size['height'] * 0.5)
        driver.swipe(start_x, start_y, start_x, end_y, 500)
        time.sleep(2)
    except:
        # 如果下拉刷新失败，简单等待
        time.sleep(2)
    
    log("✅ 页面刷新完成，等待add device按钮出现...")
    return True


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
        '//XCUIElementTypeButton[@name="home add"]',
        '//XCUIElementTypeButton[@name="Add"]',
        '//XCUIElementTypeButton[contains(@name,"add")]',
        '//XCUIElementTypeButton[contains(@name,"Add")]',
        '//XCUIElementTypeButton[@name="+"]',
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


# ==================== WiFi 设置流程 ==================== #

def _enter_wifi_list_page(driver) -> bool:
    """从 App 内点击“切换 WiFi”进入系统 WiFi 列表"""
    log("📶 步骤4: 进入系统 WiFi 页面...")
    try:
        btn = driver.find_element(
            AppiumBy.XPATH, '//XCUIElementTypeButton[@name="pair net change wifi"]'
        )
        btn.click()
        log("✅ 点击切换 WiFi 按钮成功")
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
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
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
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
    
    # 首先尝试直接查找（不滑动）
    log("🔍 首先尝试直接查找 WiFi（不滑动）...")
    for xp in selectors:
        try:
            wifi_cell = driver.find_element(AppiumBy.XPATH, xp)
            if wifi_cell.is_displayed():
                log(f"✅ 直接找到 WiFi 元素: {xp}")
                wifi_cell.click()
                log(f"✅ 已点击 WiFi: {ssid}")
                time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
                return True
        except Exception:
            continue
    
    # 如果直接查找失败，向下滑动查找（显示列表下方内容）
    if not wifi_cell:
        log("🔍 直接查找失败，开始向下滑动查找 WiFi...")
        for i in range(max_scroll):
            log(f"🔍 第 {i+1}/{max_scroll} 次向下滚动寻找 WiFi...")
            
            # 尝试所有选择器
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
            time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
            return True
            
        # 向下滑动（从下往上滑动手指，显示列表下方内容）
        try:
            size = driver.get_window_size()
            start_x = size['width'] // 2
            start_y = int(size['height'] * 0.6)
            end_y = int(size['height'] * 0.3)
            driver.swipe(start_x, start_y, start_x, end_y, 500)
            time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
        except Exception as e:
            log(f"⚠️ 向下滑动失败: {e}")
            time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
    
    # 如果向下滑动未找到，尝试向上滑动查找（显示列表上方内容）
    if not wifi_cell:
        log("🔍 向下滑动未找到 WiFi，开始向上滑动查找 WiFi...")
        for i in range(max_scroll):
            log(f"🔍 向上滑动查找 WiFi（第 {i+1}/{max_scroll} 次）...")
            
            # 尝试所有选择器
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
                time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
                return True
            
            # 向上滑动（从上往下滑动手指，显示列表上方内容）
            try:
                size = driver.get_window_size()
                start_x = size['width'] // 2
                start_y = int(size['height'] * 0.3)
                end_y = int(size['height'] * 0.6)
                driver.swipe(start_x, start_y, start_x, end_y, 500)
                time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
            except Exception as e:
                log(f"⚠️ 向上滑动失败: {e}")
                time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
    
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
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
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
    - 不再依赖读取当前内容，也不再点击“眼睛”按钮
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
        field.click()
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
        field.send_keys("\b" * 50)  # 多发一些退格，确保清空
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
    except Exception as e:
        log(f"⚠️ 连续退格清除时出错（继续尝试输入新密码）: {e}")

    # 统一输入新密码（来自 device_config.json）
    log(f"🔍 输入 WiFi 密码（来自 device_config.json）: {password}")
    try:
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


def _verify_wifi_name(driver, wifi_name: str) -> bool:
    """验证返回App后WiFi名称是否正确更新"""
    log(f"🔍 验证WiFi名称是否正确更新为: {wifi_name}...")
    wifi_name_verified = False
    max_verification_attempts = 5
    
    for attempt in range(1, max_verification_attempts + 1):
        try:
            # 查找WiFi名称输入框（TextField，不是SecureTextField）
            wifi_name_selectors = [
                f'//XCUIElementTypeTextField[@value="{wifi_name}"]',
                f'//XCUIElementTypeTextField[contains(@value,"{wifi_name}")]',
                f'//XCUIElementTypeStaticText[@name="{wifi_name}"]',
                f'//XCUIElementTypeStaticText[contains(@name,"{wifi_name}")]',
                '//XCUIElementTypeTextField',  # 通用TextField，然后检查value
            ]
            
            wifi_name_field = None
            for selector in wifi_name_selectors:
                try:
                    wifi_name_field = driver.find_element(AppiumBy.XPATH, selector)
                    if wifi_name_field.is_displayed():
                        # 获取当前显示的WiFi名称
                        current_wifi_value = wifi_name_field.get_attribute("value") or wifi_name_field.get_attribute("name") or wifi_name_field.text or ""
                        log(f"🔍 第{attempt}次验证 - 当前WiFi名称: '{current_wifi_value}'")
                        
                        # 检查是否匹配目标WiFi名称
                        if wifi_name.lower() in current_wifi_value.lower() or current_wifi_value.lower() in wifi_name.lower():
                            wifi_name_verified = True
                            log(f"✅ WiFi名称验证成功: '{current_wifi_value}' 匹配目标 '{wifi_name}'")
                            break
                except:
                    continue
            
            if wifi_name_verified:
                break
            
            # 如果未验证成功，等待一段时间后重试
            if attempt < max_verification_attempts:
                log(f"⚠️ WiFi名称未更新，等待2秒后重试 ({attempt}/{max_verification_attempts})...")
                time.sleep(2)
            else:
                log(f"⚠️ WiFi名称验证失败，已尝试{max_verification_attempts}次")
                log("🔄 尝试重新进入系统WiFi设置页面，重新选择WiFi...")
                try:
                    caps = getattr(driver, "capabilities", {}) or {}
                    bundle_id = caps.get("bundleId") or os.environ.get("IOS_BUNDLE_ID")
                    
                    # 重新点击切换WiFi按钮，进入系统设置
                    change_wifi_button = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeButton[@name="pair net change wifi"]')
                    change_wifi_button.click()
                    time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
                    
                    # 重新进入WiFi列表页面
                    wifi_list_selectors = [
                        '//XCUIElementTypeButton[@name="WLAN"]',
                        '//XCUIElementTypeStaticText[@name="WLAN"]',
                        '//XCUIElementTypeCell[contains(@name,"WLAN")]',
                    ]
                    for selector in wifi_list_selectors:
                        try:
                            wifi_list_element = driver.find_element(AppiumBy.XPATH, selector)
                            if wifi_list_element.is_displayed() and wifi_list_element.is_enabled():
                                wifi_list_element.click()
                                time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
                                break
                        except:
                            continue
                    
                    # 重新选择WiFi
                    wifi_cell = None
                    wifi_selectors = [
                        f'//XCUIElementTypeCell[contains(@name, "{wifi_name}")]',
                        f'//XCUIElementTypeCell[@name="{wifi_name}, Secure network, Signal strength 3 of 3 bars"]/XCUIElementTypeOther[1]/XCUIElementTypeOther',
                        f'//XCUIElementTypeStaticText[contains(@name, "{wifi_name}")]',
                    ]
                    for selector in wifi_selectors:
                        try:
                            wifi_cell = driver.find_element(AppiumBy.XPATH, selector)
                            if wifi_cell.is_displayed():
                                wifi_cell.click()
                                log(f"✅ 重新选择WiFi: {wifi_name}")
                                time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
                                break
                        except:
                            continue
                    
                    # 返回App
                    if bundle_id:
                        driver.activate_app(bundle_id)
                        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
                        log("✅ 已重新选择WiFi并返回App，等待WiFi名称更新...")
                        
                        # 再次验证WiFi名称（只验证一次）
                        try:
                            wifi_name_field = driver.find_element(AppiumBy.XPATH, f'//XCUIElementTypeTextField[contains(@value,"{wifi_name}")]')
                            current_wifi_value = wifi_name_field.get_attribute("value") or ""
                            if wifi_name.lower() in current_wifi_value.lower():
                                wifi_name_verified = True
                                log(f"✅ 重新选择后WiFi名称验证成功: '{current_wifi_value}'")
                        except:
                            pass
                            
                except Exception as refresh_err:
                    log(f"⚠️ 重新选择WiFi失败: {refresh_err}")
                    
        except Exception as e:
            log(f"⚠️ WiFi名称验证过程出错: {e}")
            if attempt < max_verification_attempts:
                time.sleep(2)
    
    if not wifi_name_verified:
        log(f"⚠️ WiFi名称验证失败，但继续执行密码输入（目标WiFi: {wifi_name}）")
        log("💡 提示：如果配网失败，可能是WiFi名称未正确更新导致的")
    
    return wifi_name_verified


def perform_wifi_setup(driver, wifi_name: str, wifi_pwd: str) -> bool:
    """整体 WiFi 设置步骤"""
    if not _enter_wifi_list_page(driver):
        return False
    if not _select_wifi_in_settings(driver, wifi_name):
        return False
    if not _back_to_app_wifi_page(driver):
        return False
    
    # 验证WiFi名称是否正确更新
    _verify_wifi_name(driver, wifi_name)
    
    if not _input_wifi_password(driver, wifi_pwd):
        return False

    # 关闭键盘：先点击 Done，再点击 Next（符合手动操作顺序）
    log("⌨️ 先点击键盘 Done 按钮，再点击 Next 按钮...")

    done_clicked = False
    done_selectors = [
        '//XCUIElementTypeButton[@name="Done"]',
        '//XCUIElementTypeButton[contains(@name,"Done")]',
        '//XCUIElementTypeButton[@name="完成"]',
        '//XCUIElementTypeButton[contains(@name,"完成")]',
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
                time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
                done_clicked = True
                break
        except Exception as e:
            log(f"  ⚠️ Done 按钮选择器 {i} 失败: {e}")
            continue

    if not done_clicked:
        log("⚠️ 未找到 Done 按钮，尝试使用 hide_keyboard 隐藏键盘")
        try:
            driver.hide_keyboard()
            log("✅ 使用 hide_keyboard 隐藏键盘成功")
            time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
        except Exception as e:
            log(f"⚠️ hide_keyboard 也失败: {e}，继续尝试点击 Next")

    # 再点击 Next 按钮
    try:
        next_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]')
            )
        )
        next_btn.click()
        log("✅ 点击 Next 按钮成功")
        time.sleep(2)  # 每个操作后等待2秒，确保页面切换完成
        return True
    except Exception as e:
        log(f"❌ 点击 Next 按钮失败: {e}")
        take_screenshot(driver, "next_btn_fail")
        return False


# ==================== 配网进度 & 结果 ==================== #

def wait_pairing_result(driver, target_dev: dict = None, timeout: int = 180) -> str:
    """等待配网结果：success / failed / timeout"""
    log("⏳ 步骤6: 等待配网结果...")
    start = time.time()
    
    # 构建成功检查的XPath（使用配置的设备名称）
    success_xpaths = [
        '//XCUIElementTypeStaticText[contains(@name,"设备")]',  # 通用：包含"设备"的文本
    ]
    
    if target_dev and target_dev.get("device_name"):
        dev_name = target_dev.get("device_name")
        # 添加精确匹配和包含匹配
        success_xpaths.insert(0, f'//XCUIElementTypeStaticText[@name="{dev_name}"]')
        # 如果设备名称包含空格，也尝试部分匹配
        if " " in dev_name:
            name_parts = dev_name.split()
            for part in name_parts:
                if len(part) > 2:  # 只使用长度大于2的部分
                    success_xpaths.insert(1, f'//XCUIElementTypeStaticText[contains(@name,"{part}")]')
                    break
    
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

            # 成功：首页出现新设备（使用动态生成的XPath）
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


# ==================== 单次配网流程 ==================== #

def run_single_flow(driver, wifi_name: str, wifi_pwd: str, target_dev: dict) -> tuple[str, str]:
    """单次配网完整流程，返回 (result, message)"""
    log(f"\n🔄 开始单次配网流程（WiFi: {wifi_name}）")
    log("=" * 60)

    if not reset_app_to_home(driver):
        log("⚠️ 应用重置失败，仍尝试继续")

    if not trigger_robot_hotspot():
        return "error", "触发机器热点失败"

    if not ensure_home_add_button(driver):
        return "error", "首页缺少 add 按钮"

    if not tap_add_device(driver):
        return "error", "点击 add 按钮失败"

    if not pick_target_device(driver, target_dev):
        return "error", "设备选择失败"

    if not perform_wifi_setup(driver, wifi_name, wifi_pwd):
        return "error", "WiFi 设置失败"

    result = wait_pairing_result(driver, target_dev)
    if result == "success":
        return "success", "配网成功"
    if result == "failed":
        return "failed", "配网失败"
    return "timeout", "配网超时"


# ==================== 结果汇总和报告生成 ==================== #

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
        # 仅统计有数据的路由器
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
            # 尝试从多个位置查找 excel_report_generator.py
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # 查找顺序：1. common 目录 2. 当前目录 3. IOS子目录 4. 上级目录（向后兼容）
            search_paths = [
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
    else:
        log("⚠️ 无测试数据，跳过Excel报告生成")


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
