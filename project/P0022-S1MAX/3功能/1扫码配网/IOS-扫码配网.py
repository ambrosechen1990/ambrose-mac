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
    if common_path not in sys.path:
        sys.path.insert(0, common_path)
    try:
        from report_utils import init_run_env
    except ImportError:
        # 如果还是找不到，尝试从蓝牙配网目录导入（向后兼容）
        bt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "2蓝牙配网")
        if bt_path not in sys.path:
            sys.path.insert(0, bt_path)
        from report_utils import init_run_env

# 统一从 common 引入 S1MAX 公共工具
try:
    from config_loader import load_s1max_config
    from result_utils import finalize_results as common_finalize_results
except Exception:
    # 如果直接导入失败，再显式把 common 加到 sys.path 后重试一次
    _common_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common")
    if _common_dir not in sys.path:
        sys.path.insert(0, _common_dir)
    from config_loader import load_s1max_config
    from result_utils import finalize_results as common_finalize_results

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

ROBOT_DEVICE_ID = os.environ.get("ROBOT_DEVICE_ID", "20080411")


def trigger_robot_hotspot() -> bool:
    """
    触发机器人热点：
    - 优先调用 common/hotspot_trigger.py（S1MAX 公用脚本）
    - 失败时回退到原 adb+expect+ROS2 方式
    """
    log("📡 步骤1: 触发机器热点...")

    # 1. 优先使用 common/hotspot_trigger.py
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../配网兼容性
        common_dir = os.path.join(base_dir, "common")
        if common_dir not in sys.path:
            sys.path.insert(0, common_dir)

        import hotspot_trigger  # type: ignore

        # 1扫码配网：优化等待时间，从10秒减少到5秒（热点启动通常更快）
        log("🔌 优先使用 common/hotspot_trigger.py 触发热点（sleep_before=5）...")
        ok = hotspot_trigger.trigger_hotspot(
            device_id=ROBOT_DEVICE_ID,
            sleep_before=5,  # 优化：从10秒减少到5秒
            log=log,
        )
        if ok:
            log("✅ common/hotspot_trigger.py 触发热点成功")
            return True
        log("⚠️ common/hotspot_trigger.py 触发失败，回退到原 ROS2 expect 方式...")
    except Exception as e:
        log(f"⚠️ 调用 common/hotspot_trigger.py 失败，回退到原 ROS2 expect 方式: {e}")

    # 2. 回退：保留原来的 adb+expect+ROS2 实现
    adb = get_adb_path()
    script = f"""#!/usr/bin/expect -f
set timeout 60
spawn {adb} -s {ROBOT_DEVICE_ID} shell
expect {{
    -re "root@.*#" {{}}
    -re "# $" {{}}
}}
send "sleep 5\\r"
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
    path = "/tmp/ios_qr_hotspot.exp"
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

    # 可选：为每台真机指定单独的 WDA 端口，避免 8100 冲突
    # 在 common/device_config.json 里配置：
    #   "wda_local_port": 8101   或  "wdaLocalPort": 8101
    wda_local_port = dev_cfg.get("wda_local_port") or dev_cfg.get("wdaLocalPort")
    if wda_local_port:
        try:
            wda_local_port = int(wda_local_port)
            options.set_capability("wdaLocalPort", wda_local_port)
            log(f"🧩 为设备 {dev_cfg.get('device_name')} 设置 wdaLocalPort={wda_local_port}")
        except Exception as e:
            log(f"⚠️ 解析 wdaLocalPort 失败，将使用默认 8100: {e}")

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
        time.sleep(1)  # 优化：从2秒减少到1秒
        driver.activate_app(bundle_id)
        time.sleep(1)  # 优化：从2秒减少到1秒

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
            time.sleep(1)  # 优化：从1.5秒减少到1秒
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
                time.sleep(2)  # 优化：从3秒减少到2秒
            else:
                log("⚠️ 未找到 add 按钮，且未检测到已配对设备，等待页面加载...")
                time.sleep(2)  # 优化：从3秒减少到2秒
        else:
            # 后续尝试：如果删除后仍然没有，等待更长时间
            log(f"⏳ 第 {attempt+1} 次检查，等待页面加载...")
            time.sleep(2)  # 优化：从3秒减少到2秒
    
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
                time.sleep(1)  # 优化：从2秒减少到1秒
                return True
        except Exception as e:
            log(f"⚠️ add按钮选择器失败: {selector} - {e}")
            continue
    
    log("❌ 所有add按钮选择器都失败")
    take_screenshot(driver, "tap_add_fail")
    return False


# ==================== 设备选择页面 - 扫码 ==================== #

def _handle_agree_on_set_up_wifi(driver, timeout: int = 6) -> bool:
    """
    扫码成功进入 Set up Wi‑Fi 页面后，可能出现 Agree 弹框，需要点击：
      //XCUIElementTypeButton[@name="Agree"]
    - 出现则点击并返回 True
    - 未出现返回 False（不算失败）
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
                time.sleep(1)  # 优化：从1.5秒减少到1秒
                return True
        except Exception as e:
            continue
    
    # 如果所有选择器都失败，尝试通过坐标点击（作为最后手段）
    try:
        # 尝试查找包含 "Agree" 文本的元素
        agree_elements = driver.find_elements(AppiumBy.XPATH, '//XCUIElementTypeButton[contains(@name,"Agree")]')
        if agree_elements:
            for elem in agree_elements:
                try:
                    if elem.is_displayed():
                        location = elem.location
                        size = elem.size
                        center_x = location['x'] + size['width'] // 2
                        center_y = location['y'] + size['height'] // 2
                        log(f"💡 通过坐标点击 Agree 按钮: ({center_x}, {center_y})")
                        driver.tap([(center_x, center_y)], 100)
                        log("✅ 通过坐标点击 Agree 按钮成功")
                        time.sleep(1)  # 优化：从1.5秒减少到1秒
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    
    return False


def scan_qr_code(driver) -> bool:
    """
    设备选择页面，使用摄像头扫描二维码
    - 扫描成功：跳转WIFI设置页面
    - 未扫到码：停留超过1min，配网失败
    """
    log("📷 步骤3: 使用摄像头扫描二维码...")
    
    # 等待进入设备选择页面（扫码页面）- 优化：减少等待时间
    log("⏳ 等待进入扫码页面...")
    time.sleep(1.5)  # 优化：从3秒减少到1.5秒
    
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
                            time.sleep(1)  # 优化：从2秒减少到1秒
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
        '//XCUIElementTypeStaticText[contains(@name,"Set up")]',
        '//XCUIElementTypeButton[@name="Agree"]',  # Agree 按钮出现也说明已跳转到 WiFi 设置页面
        '//XCUIElementTypeButton[contains(@name,"Agree")]',
    ]
    
    log("🔍 检查是否已经跳转到WiFi设置页面...")
    for indicator in wifi_setup_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                log(f"✅ 已经跳转到WiFi设置页面，扫描成功: {indicator}")
                time.sleep(1)  # 优化：从2秒减少到1秒
                # Set up Wi‑Fi 页面可能出现 Agree 弹框，立即处理
                if _handle_agree_on_set_up_wifi(driver, timeout=4):  # 优化：从6秒减少到4秒
                    log("✅ 已处理 Agree 按钮，继续后续流程")
                else:
                    log("ℹ️ 未检测到 Agree 按钮，可能已跳过或不存在")
                return True
        except:
            continue
    
    # 检查是否有设备列表遮挡扫码框，如果有则点击 "Add Robot" 隐藏设备列表
    log("🔍 检查是否有设备列表遮挡扫码框...")
    device_list_indicators = [
        '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
        '//XCUIElementTypeStaticText[contains(@name,"SN:")]',
        '//XCUIElementTypeButton[@name="Add"]',
        '//XCUIElementTypeStaticText[@name="Add Robot"]',
    ]
    
    has_device_list = False
    for indicator in device_list_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                log(f"✅ 检测到设备列表元素: {indicator}")
                has_device_list = True
                break
        except:
            continue
    
    # 如果检测到设备列表，快速尝试点击 "Add Robot" 来隐藏设备列表，露出扫码框
    if has_device_list:
        log("🔄 检测到设备列表可能遮挡扫码框，快速尝试点击 'Add Robot' 隐藏设备列表...")
        
        # 策略1: 快速尝试几个关键XPath选择器（减少超时时间）
        add_robot_selectors = [
            '//XCUIElementTypeStaticText[@name="Add Robot"]',
            '//XCUIElementTypeButton[@name="Add Robot"]',
            '//XCUIElementTypeNavigationBar//XCUIElementTypeStaticText[@name="Add Robot"]',
        ]
        
        add_robot_clicked = False
        for selector in add_robot_selectors:
            try:
                # 快速查找，不等待
                elements = driver.find_elements(AppiumBy.XPATH, selector)
                for elem in elements:
                    if elem.is_displayed() and elem.is_enabled():
                        elem.click()
                        log(f"✅ 点击 'Add Robot' 成功: {selector}")
                        time.sleep(0.5)  # 优化：从1秒减少到0.5秒
                        add_robot_clicked = True
                        break
                if add_robot_clicked:
                    break
            except Exception:
                continue
        
        # 策略2: 如果快速查找失败，直接通过坐标点击导航栏（不遍历所有元素）
        if not add_robot_clicked:
            log("🔍 快速查找失败，直接通过坐标点击导航栏...")
            try:
                # 优先查找NavigationBar的位置
                nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
                if nav_bars:
                    for nav_bar in nav_bars:
                        try:
                            if nav_bar.is_displayed():
                                location = nav_bar.location
                                size = nav_bar.size
                                center_x = location['x'] + size['width'] // 2
                                center_y = location['y'] + size['height'] // 2
                                log(f"💡 点击导航栏中心坐标: ({center_x}, {center_y})")
                                driver.tap([(center_x, center_y)], 100)
                                log(f"✅ 通过坐标点击导航栏中心成功")
                                time.sleep(0.5)  # 优化：从1秒减少到0.5秒
                                add_robot_clicked = True
                                break
                        except Exception:
                            continue
                else:
                    # 如果没有找到NavigationBar，点击屏幕顶部中心位置
                    size = driver.get_window_size()
                    center_x = size['width'] // 2
                    center_y = 50
                    log(f"💡 点击屏幕顶部中心坐标: ({center_x}, {center_y})")
                    driver.tap([(center_x, center_y)], 100)
                    log(f"✅ 通过坐标点击屏幕顶部中心成功")
                    time.sleep(0.5)  # 优化：从1秒减少到0.5秒
                    add_robot_clicked = True
            except Exception as coord_err:
                log(f"⚠️ 坐标点击失败: {coord_err}")
        
        if not add_robot_clicked:
            log("⚠️ 未找到 'Add Robot' 元素，继续执行...")
    
    # 如果还没有跳转到WiFi设置页面，快速点击扫描框（优化：减少等待时间）
    log("🔍 快速点击扫描框，确保扫描框可见...")
    
    # 优化：减少等待时间
    time.sleep(0.5)  # 优化：从1秒减少到0.5秒
    
    # 只尝试最关键的几个选择器，快速失败
    scan_frame_selectors = [
        # 通过扫描相关的图像元素定位（最可靠）
        '//XCUIElementTypeImage[@name="scan_top_left"]/..',
        '//XCUIElementTypeImage[@name="scan_bottom_right"]/..',
        '//XCUIElementTypeImage[contains(@name,"scan")]',
    ]
    
    scan_frame_clicked = False
    for selector in scan_frame_selectors:
        try:
            # 快速查找，不等待
            elements = driver.find_elements(AppiumBy.XPATH, selector)
            for elem in elements:
                if elem.is_displayed():
                    try:
                        elem.click()
                        log(f"✅ 点击扫描框成功: {selector[:50]}...")
                        time.sleep(0.5)  # 优化：从1秒减少到0.5秒
                        scan_frame_clicked = True
                        break
                    except Exception:
                        continue
            if scan_frame_clicked:
                break
        except Exception:
            continue
    
    # 如果快速查找失败，直接通过坐标点击扫描区域中心（不浪费时间）
    if not scan_frame_clicked:
        log("💡 快速查找失败，直接通过坐标点击扫描区域中心...")
        try:
            size = driver.get_window_size()
            scan_center_x = size['width'] // 2
            scan_center_y = int(size['height'] * 0.3)  # 屏幕上方30%的位置
            log(f"💡 点击扫描区域中心坐标: ({scan_center_x}, {scan_center_y})")
            driver.tap([(scan_center_x, scan_center_y)], 100)
            log("✅ 通过坐标点击扫描区域成功")
            time.sleep(0.5)  # 优化：从1秒减少到0.5秒
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
                    time.sleep(1)  # 优化：从2秒减少到1秒
                    # Set up Wi‑Fi 页面可能出现 Agree 弹框，立即处理
                    if _handle_agree_on_set_up_wifi(driver, timeout=4):  # 优化：从6秒减少到4秒
                        log("✅ 已处理 Agree 按钮，继续后续流程")
                    else:
                        log("ℹ️ 未检测到 Agree 按钮，可能已跳过或不存在")
                    return True
            except:
                continue
        time.sleep(1)  # 优化：从2秒减少到1秒
    
    # 等待扫描结果，最多等待1分钟
    log("⏳ 等待扫描二维码结果（最多60秒）...")
    start_time = time.time()
    timeout = 60  # 1分钟超时
    
    # 统一的 WiFi 设置页面指示器（与初始检查保持一致，并增加更多可能）
    wifi_setup_indicators = [
        '//XCUIElementTypeButton[@name="pair net change wifi"]',
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeTextField',
        '//XCUIElementTypeStaticText[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeStaticText[contains(@name,"WIFI")]',
        '//XCUIElementTypeStaticText[contains(@name,"Set up")]',
        '//XCUIElementTypeButton[@name="Agree"]',  # Agree 按钮出现也说明已跳转到 WiFi 设置页面
        '//XCUIElementTypeButton[contains(@name,"Agree")]',
    ]
    
    while time.time() - start_time < timeout:
        # 检查是否已跳转到WIFI设置页面
        for indicator in wifi_setup_indicators:
            try:
                elem = driver.find_element(AppiumBy.XPATH, indicator)
                if elem.is_displayed():
                    log(f"✅ 扫描成功，已跳转到WIFI设置页面: {indicator}")
                    time.sleep(1)  # 优化：从2秒减少到1秒
                    # Set up Wi‑Fi 页面可能出现 Agree 弹框，立即处理
                    if _handle_agree_on_set_up_wifi(driver, timeout=4):  # 优化：从6秒减少到4秒
                        log("✅ 已处理 Agree 按钮，继续后续流程")
                    else:
                        log("ℹ️ 未检测到 Agree 按钮，可能已跳过或不存在")
                    return True
            except:
                continue
        
        # 检查是否还在扫码页面（如果还在，继续等待）- 优化：减少检查间隔
        time.sleep(1)  # 优化：从2秒减少到1秒
    
    log("❌ 扫描超时（超过1分钟），未扫到码，本次配网失败")
    take_screenshot(driver, "scan_qr_timeout")
    return False


# ==================== WiFi 设置流程 ====================

def _handle_light_checkbox_after_wifi_next(driver, timeout: int = 8) -> bool | None:
    """
    iOS 1扫码配网：Wi‑Fi 密码页点击 Next 后，可能出现中间页（灯显勾选 + 下一步）
    需要依次点击：
      1) //XCUIElementTypeButton[@name="pair net un sel"]
      2) //XCUIElementTypeButton[@name="Next"]

    返回：
    - None：未出现该页面（不算失败）
    - True：已处理完成
    - False：页面出现但处理失败（应视为失败）
    """
    checkbox_xp = '//XCUIElementTypeButton[@name="pair net un sel"]'
    next_xp = '//XCUIElementTypeButton[@name="Next"]'

    # 先快速判断是否出现 checkbox
    try:
        checkbox = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, checkbox_xp))
        )
        if not checkbox.is_displayed():
            return None
    except Exception:
        return None

    log("ℹ️ 检测到灯显勾选页，开始勾选并点击下一步...")
    try:
        checkbox = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, checkbox_xp))
        )
        checkbox.click()
        log("✅ 灯显勾选页：已点击 pair net un sel")
        time.sleep(1)  # 优化：从1.5秒减少到1秒
    except Exception as e:
        log(f"❌ 灯显勾选页：点击 pair net un sel 失败: {e}")
        take_screenshot(driver, "light_checkbox_click_fail")
        return False

    try:
        next_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, next_xp))
        )
        next_btn.click()
        log("✅ 灯显勾选页：已点击 Next")
        time.sleep(1)  # 优化：从2秒减少到1秒
        return True
    except Exception as e:
        log(f"❌ 灯显勾选页：点击 Next 失败: {e}")
        take_screenshot(driver, "light_next_click_fail")
        return False


def _detect_current_page(driver) -> str:
    """
    检测当前页面类型（参考 P0024-M0 蓝牙配网脚本）
    返回: "wifi_list" (WiFi列表页面), "settings_apps" (系统设置Apps页面), 
          "wifi_password" (WiFi密码输入页面), "unknown" (未知页面)
    """
    # 先检测是否在WiFi密码输入页面（可能直接跳转到这里）
    wifi_password_indicators = [
        '//XCUIElementTypeSecureTextField[@value="Wi-Fi Password"]',
        '//XCUIElementTypeSecureTextField[@placeholder="Wi-Fi Password"]',
        '//XCUIElementTypeSecureTextField[contains(@placeholder,"Password")]',
        '//XCUIElementTypeStaticText[contains(@name,"Wi-Fi Password")]',
        '//XCUIElementTypeButton[@name="Next"]',  # 如果有Next按钮，可能在密码输入页面
    ]
    for indicator in wifi_password_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                log(f"✅ 检测到WiFi密码输入页面: {indicator}")
                return "wifi_password"
        except Exception:
            continue
    
    # 检测是否在WiFi列表页面（优先检测中文"无线局域网"）
    wifi_list_indicators = [
        '//XCUIElementTypeNavigationBar[@name="无线局域网"]',  # 中文系统
        '//XCUIElementTypeNavigationBar[@name="Settings"]',  # 英文系统
        '//XCUIElementTypeStaticText[@name="无线局域网"]',  # 中文系统
        '//XCUIElementTypeStaticText[@name="WLAN"]',  # 英文系统
        '//XCUIElementTypeButton[@name="WLAN"]',
        '//XCUIElementTypeCell[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeStaticText[contains(@name,"Wi-Fi")]',
        '//XCUIElementTypeTable',  # WiFi列表通常是Table
        '//XCUIElementTypeCell[contains(@name,"ASUS")]',  # 常见的WiFi名称
        '//XCUIElementTypeCell[contains(@name,"TP-Link")]',
    ]
    for indicator in wifi_list_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                # 进一步确认：检查是否有NavigationBar且包含Settings
                try:
                    nav_bar = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeNavigationBar[@name="Settings"]')
                    if nav_bar.is_displayed():
                        log(f"✅ 检测到WiFi列表页面: {indicator}")
                        return "wifi_list"
                except:
                    # 如果没有NavigationBar，但找到了WiFi相关元素，也可能是WiFi列表
                    if "Wi-Fi" in indicator or "WLAN" in indicator:
                        log(f"✅ 检测到WiFi列表页面（无NavigationBar）: {indicator}")
                        return "wifi_list"
        except Exception:
            continue
    
    # 检测是否在系统设置Apps页面（高系统会跳转到这里）
    settings_apps_indicators = [
        '//XCUIElementTypeStaticText[@name="Apps"]',
        '//XCUIElementTypeStaticText[@name="App Store"]',
        '//XCUIElementTypeStaticText[@name="Beatbot"]',
        '//XCUIElementTypeStaticText[@name="Calculator"]',
        '//XCUIElementTypeStaticText[@name="Calendar"]',
        '//XCUIElementTypeStaticText[@name="Default Apps"]',
    ]
    for indicator in settings_apps_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, indicator)
            if elem.is_displayed():
                # 进一步确认：如果有Apps标题或App列表，确认是Apps页面
                try:
                    apps_title = driver.find_element(AppiumBy.XPATH, '//XCUIElementTypeStaticText[@name="Apps"]')
                    if apps_title.is_displayed():
                        log(f"✅ 检测到系统设置Apps页面（高系统）: {indicator}")
                        return "settings_apps"
                except:
                    # 如果没有Apps标题，但找到了其他Apps页面特征，也可能是Apps页面
                    log(f"✅ 检测到可能是系统设置Apps页面: {indicator}")
                    return "settings_apps"
        except Exception:
            continue
    
    # 如果都检测不到，快速检查NavigationBar名称
    try:
        nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
        if nav_bars:
            for nav in nav_bars:
                try:
                    nav_name = nav.get_attribute("name") or ""
                    # 如果NavigationBar名称包含"无线局域网"或"WLAN"，认为是WiFi列表页面
                    if "无线局域网" in nav_name or "WLAN" in nav_name or nav_name == "Settings":
                        log(f"✅ 通过NavigationBar名称检测到WiFi列表页面: {nav_name}")
                        return "wifi_list"
                except:
                    pass
    except:
        pass
    
    log("⚠️ 无法确定当前页面类型")
    return "unknown"


def _click_back_button(driver) -> bool:
    """点击左上角返回按钮（参考 P0024-M0 蓝牙配网脚本）"""
    log("🔙 点击左上角返回按钮...")
    back_button_selectors = [
        '//XCUIElementTypeButton[@name="Back"]',
        '//XCUIElementTypeButton[@name="返回"]',
        '//XCUIElementTypeNavigationBar/XCUIElementTypeButton[1]',
        '//XCUIElementTypeButton[contains(@name,"Back")]',
    ]
    
    for selector in back_button_selectors:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            if btn.is_displayed():
                btn.click()
                log(f"✅ 点击返回按钮成功: {selector}")
                time.sleep(1)  # 优化：从2秒减少到1秒
                return True
        except Exception as e:
            log(f"⚠️ 返回按钮选择器失败: {selector} - {e}")
            continue
    
    # 如果找不到返回按钮，尝试使用driver.back()
    try:
        log("⚠️ 未找到返回按钮，尝试使用driver.back()...")
        driver.back()
        time.sleep(1)  # 优化：从2秒减少到1秒
        log("✅ 使用driver.back()成功")
        return True
    except Exception as e:
        log(f"❌ driver.back()也失败: {e}")
        return False


def _enter_wifi_list_page(driver) -> bool:
    """
    从 App 内点击"切换 WiFi"进入系统 WiFi 列表（参考 P0024-M0 蓝牙配网脚本）
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
        time.sleep(1.5)  # 优化：从3秒减少到1.5秒
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
        log("🔄 检测到高系统：在系统设置Apps页面，需要返回后进入WLAN页面...")
        
        # 4.1 点击左上角返回按钮
        if not _click_back_button(driver):
            log("⚠️ 点击返回按钮失败，尝试继续...")
        
        # 4.2 等待页面加载 - 优化：减少等待时间
        time.sleep(1)  # 优化：从2秒减少到1秒
        
        # 4.3 查找并点击WLAN按钮（com.apple.settings.wifi）
        log("🔍 查找WLAN按钮（com.apple.settings.wifi）...")
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
                btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if btn.is_displayed():
                    btn.click()
                    log(f"✅ 点击WLAN按钮成功: {selector}")
                    time.sleep(1.5)  # 优化：从3秒减少到1.5秒
                    wlan_clicked = True
                    break
            except Exception as e:
                log(f"⚠️ WLAN按钮选择器失败: {selector} - {e}")
                continue
        
        if not wlan_clicked:
            log("⚠️ 未找到WLAN按钮，可能已经在WiFi列表页面或页面结构不同")
            # 再次检测页面类型
            page_type = _detect_current_page(driver)
            if page_type == "wifi_list":
                log("✅ 检测到已在WiFi列表页面")
                return True
        
        # 4.4 再次检测是否成功进入WiFi列表页面 - 优化：减少等待时间
        time.sleep(1)  # 优化：从2秒减少到1秒
        page_type = _detect_current_page(driver)
        if page_type == "wifi_list":
            log("✅ 成功进入WiFi列表页面")
            return True
        else:
            log(f"⚠️ 点击WLAN按钮后，页面类型仍为: {page_type}")
            take_screenshot(driver, "wifi_list_not_found")
            # 即使检测失败，也尝试继续执行，可能页面结构有变化
    
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
                except:
                    continue
        except:
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
                except:
                    pass
        except:
            pass
        
        # 策略3: 重试检测 - 优化：减少等待时间
        for i in range(2):
            log(f"⏳ 等待页面加载后再次检测（{i+1}/2）...")
            time.sleep(1)  # 优化：从2秒减少到1秒
            page_type = _detect_current_page(driver)
            if page_type == "wifi_list":
                log("✅ 等待后检测到WiFi列表页面")
                return True
            elif page_type == "wifi_password":
                log("✅ 等待后检测到WiFi密码输入页面")
                return True
            elif page_type == "settings_apps":
                log("⚠️ 等待后检测到Apps页面，快速处理...")
                # 快速处理Apps页面
                if _click_back_button(driver):
                    time.sleep(1)
                    # 尝试查找WLAN按钮
                    try:
                        wlan_btn = driver.find_element(
                            AppiumBy.XPATH, '//XCUIElementTypeButton[@name="com.apple.settings.wifi"]'
                        )
                        if wlan_btn.is_displayed():
                            wlan_btn.click()
                            time.sleep(2)
                            return True
                    except:
                        pass
    
    # 6. 最终验证：检查是否在WiFi列表页面
    log("🔍 最终验证是否在WiFi列表页面...")
    final_indicators = [
        '//XCUIElementTypeNavigationBar[@name="无线局域网"]',  # 中文系统（优先）
        '//XCUIElementTypeNavigationBar[@name="Settings"]',  # 英文系统
        '//XCUIElementTypeStaticText[@name="WLAN"]',
        '//XCUIElementTypeButton[@name="WLAN"]',
    ]
    for xp in final_indicators:
        try:
            elem = driver.find_element(AppiumBy.XPATH, xp)
            if elem.is_displayed():
                log(f"✅ 最终检测到 iOS WiFi 设置页面元素: {xp}")
                return True
        except Exception:
            continue

    # 如果标准检测失败，检查NavigationBar名称
    try:
        nav_bars = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeNavigationBar")
        for nav in nav_bars:
            try:
                nav_name = nav.get_attribute("name") or ""
                if "无线局域网" in nav_name or "WLAN" in nav_name or nav_name == "Settings":
                    log(f"✅ 通过NavigationBar快速检测到WiFi列表页面: {nav_name}")
                    return True
            except Exception:
                pass
    except Exception:
        pass
    
    log("⚠️ 未明显检测到 iOS 系统 WiFi 页面，但继续执行后续步骤")
    return True  # 即使检测失败，也返回True继续执行，避免阻塞流程


def _select_wifi_in_settings(driver, ssid: str) -> bool:
    """在 iOS 系统 WiFi 设置页面选择指定 SSID"""
    log(f"🔍 在系统 WiFi 列表中寻找: {ssid}")
    max_scroll = 10
    
    # 优化：优先使用精确匹配，避免匹配到包含SSID的其他WiFi（如"ASUS_5G"）
    selectors = [
        # 最精确：完全匹配SSID的Cell（优先）
        f'//XCUIElementTypeCell[@name="{ssid}"]',
        # 精确匹配SSID的StaticText
        f'//XCUIElementTypeStaticText[@name="{ssid}"]',
        # 包含匹配（作为备选，但会验证）
        f'//XCUIElementTypeCell[contains(@name,"{ssid}")]',
        f'//XCUIElementTypeStaticText[contains(@name,"{ssid}")]',
    ]
    
    def _truthy_attr(v) -> bool:
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "y")

    def _is_hittable(el) -> bool:
        try:
            return _truthy_attr(el.get_attribute("hittable"))
        except Exception:
            return False

    def _match_cell_name(xp: str, cell_name: str) -> bool:
        """
        统一的“避免误选”匹配策略：
        - 精确匹配：@name="{ssid}" 直接通过
        - contains 匹配：要求 cell_name 与 ssid 完全相等，或以 ssid 开头并紧跟分隔符（空格/逗号/括号）
        """
        if "@name=\"" in xp and f'"{ssid}"' in xp:
            return True
        if "contains" in xp:
            return (
                cell_name == ssid
                or cell_name.startswith(ssid + " ")
                or cell_name.startswith(ssid + ",")
                or cell_name.startswith(ssid + "(")
            )
        return ssid in cell_name

    def _find_candidate_hittable() -> tuple[object | None, str, str]:
        """
        返回： (element_or_none, matched_xpath, element_name)
        只返回 hittable 的元素，避免"找到了但点不到/没反应"。
        """
        for xp in selectors:
            try:
                elems = driver.find_elements(AppiumBy.XPATH, xp)
                for el in elems:
                    try:
                        if not el.is_displayed():
                            continue
                        name = el.get_attribute("name") or ""
                        if not _match_cell_name(xp, name):
                            continue
                        if not _is_hittable(el):
                            continue
                        return el, xp, name
                    except Exception:
                        continue
            except Exception:
                continue
        return None, "", ""

    def _swipe(direction: str) -> None:
        """direction: 'down'（列表向下滚动，手指上滑） / 'up'（列表向上滚动，手指下滑）"""
        try:
            size = driver.get_window_size()
            x = size["width"] // 2
            if direction == "down":
                # 手指从下往上：列表向下滚动
                start_y = int(size["height"] * 0.75)
                end_y = int(size["height"] * 0.25)
            else:
                # 手指从上往下：列表向上滚动
                start_y = int(size["height"] * 0.25)
                end_y = int(size["height"] * 0.75)
            driver.swipe(x, start_y, x, end_y, 450)
            time.sleep(0.8)
        except Exception as e:
            log(f"⚠️ 滑动失败（{direction}）: {e}")
            time.sleep(0.8)
    
    # 1) 先尝试不滑动：只要能找到 hittable 的目标 WiFi，就点击
    log("🔍 首先尝试直接查找 WiFi（不滑动，要求 hittable=true）...")
    el, xp, name = _find_candidate_hittable()
    if el is not None:
        try:
            log(f"✅ 找到可点击 WiFi：xp={xp} name='{name}'（hittable=true），准备点击")
            el.click()
            time.sleep(1.2)
            return True
        except Exception as e:
            log(f"⚠️ 点击 WiFi 失败（将进入滑动查找）: {e}")

    # 2) 向下滑动查找（你在手机上会看到列表滚动）
    log("🔽 直接查找未命中可点击 WiFi，开始向下滑动查找...")
    for i in range(max_scroll):
        log(f"🔽 向下滑动查找 WiFi（第 {i+1}/{max_scroll} 次）")
        el, xp, name = _find_candidate_hittable()
        if el is not None:
            log(f"✅ 找到可点击 WiFi：xp={xp} name='{name}'（hittable=true），准备点击")
            el.click()
            time.sleep(1.2)
            return True
        _swipe("down")

    # 3) 向上滑动回找（防止目标在更上方）
    log("🔼 向下滑动未命中，开始向上滑动回找 WiFi...")
    for i in range(max_scroll):
        log(f"🔼 向上滑动查找 WiFi（第 {i+1}/{max_scroll} 次）")
        el, xp, name = _find_candidate_hittable()
        if el is not None:
            log(f"✅ 找到可点击 WiFi：xp={xp} name='{name}'（hittable=true），准备点击")
            el.click()
            time.sleep(1.2)
            return True
        _swipe("up")
    
    log(f"❌ 向下/向上滑动各 {max_scroll} 次后，仍未找到可点击 WiFi: {ssid}")
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
        time.sleep(1)  # 优化：从2秒减少到1秒
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
        time.sleep(1)  # 优化：从2秒减少到1秒
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
        time.sleep(0.5)  # 优化：从2秒减少到0.5秒
        field.send_keys("\b" * 50)  # 多发一些退格，确保清空
        time.sleep(0.5)  # 优化：从2秒减少到0.5秒
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
        time.sleep(0.5)  # 优化：从2秒减少到0.5秒
        field.send_keys(password)
        time.sleep(1)  # 优化：从2秒减少到1秒
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


def _verify_wifi_name_after_selection(driver, wifi_name: str) -> bool:
    """返回App后验证WiFi名称是否正确更新"""
    log(f"🔍 验证WiFi名称是否正确更新为: {wifi_name}...")
    
    # 查找WiFi名称显示元素（通常是TextField或StaticText）
    wifi_name_selectors = [
        f'//XCUIElementTypeTextField[@value="{wifi_name}"]',
        f'//XCUIElementTypeTextField[contains(@value,"{wifi_name}")]',
        f'//XCUIElementTypeStaticText[@name="{wifi_name}"]',
        f'//XCUIElementTypeStaticText[contains(@name,"{wifi_name}")]',
    ]
    
    for attempt in range(3):
        try:
            for selector in wifi_name_selectors:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, selector)
                    if elem.is_displayed():
                        current_value = elem.get_attribute("value") or elem.get_attribute("name") or ""
                        if wifi_name.lower() in current_value.lower() or current_value.lower() in wifi_name.lower():
                            log(f"✅ WiFi名称验证成功: '{current_value}' 匹配目标 '{wifi_name}'")
                            return True
                except:
                    continue
            
            if attempt < 2:
                log(f"⚠️ WiFi名称验证失败（第 {attempt+1}/3 次），等待1秒后重试...")
                time.sleep(1)
        except Exception as e:
            log(f"⚠️ WiFi名称验证异常: {e}")
            if attempt < 2:
                time.sleep(1)
    
    log(f"⚠️ WiFi名称验证失败，但继续执行（目标WiFi: {wifi_name}）")
    log("💡 提示：如果后续配网失败，可能是WiFi选择不正确导致的")
    return False  # 验证失败，但不阻塞流程


def perform_wifi_setup(driver, wifi_name: str, wifi_pwd: str) -> bool:
    """整体 WiFi 设置步骤"""
    if not _enter_wifi_list_page(driver):
        return False
    if not _select_wifi_in_settings(driver, wifi_name):
        return False
    if not _back_to_app_wifi_page(driver):
        return False
    
    # 验证WiFi名称是否正确更新
    _verify_wifi_name_after_selection(driver, wifi_name)
    
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
                time.sleep(1)  # 优化：从2秒减少到1秒
                done_clicked = True
                break
        except Exception as e:
            log(f"  ⚠️ Done 按钮选择器 {i} 失败: {e}")
            continue

    if not done_clicked:
        log("⚠️ 未找到 Done 按钮，尝试使用 hide_keyboard")
        try:
            driver.hide_keyboard()
            time.sleep(1)  # 优化：从2秒减少到1秒
        except Exception as e:
            log(f"⚠️ hide_keyboard 也失败: {e}")

    # 点击 Next 按钮
    try:
        next_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]')
            )
        )
        next_btn.click()
        log("✅ 点击 Next 按钮成功")
        time.sleep(1)  # 优化：从2秒减少到1秒
        # Next 后可能出现“灯显勾选页”（pair net un sel + Next）
        handled = _handle_light_checkbox_after_wifi_next(driver, timeout=10)
        if handled is False:
            return False
        return True
    except Exception as e:
        log(f"❌ 点击 Next 按钮失败: {e}")
        take_screenshot(driver, "next_btn_fail")
        return False


# ==================== 配网引导页 ====================

def handle_pairing_guide(driver) -> bool:
    """配网引导页：点击Next按钮（两次）"""
    log("📋 步骤5: 处理配网引导页...")
    
    # 检查是否已经跳转到connect device hotspot页面
    connect_hotspot_indicators = [
        '//XCUIElementTypeButton[@name="Connect"]',
        '//XCUIElementTypeButton[contains(@name,"Connect")]',
        '//XCUIElementTypeButton[contains(@name,"连接")]',
        '//XCUIElementTypeButton[@name="Join"]',
        '//XCUIElementTypeButton[contains(@name,"Join")]',
        '//XCUIElementTypeStaticText[contains(@name,"hotspot")]',
        '//XCUIElementTypeStaticText[contains(@name,"Hotspot")]',
    ]
    
    for i in range(2):
        log(f"🔍 点击Next按钮（第 {i+1}/2 次）...")
        try:
            next_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (AppiumBy.XPATH, '//XCUIElementTypeButton[@name="Next"]')
                )
            )
            next_btn.click()
            log(f"✅ 点击 Next 按钮成功（第 {i+1}/2 次）")
            time.sleep(1)  # 优化：从2秒减少到1秒
        except Exception as e:
            log(f"⚠️ 点击 Next 按钮失败（第 {i+1}/2 次）: {e}")
            
            # 检查是否已经跳转到connect device hotspot页面
            log("🔍 检查是否已经跳转到connect device hotspot页面...")
            for indicator in connect_hotspot_indicators:
                try:
                    elem = driver.find_element(AppiumBy.XPATH, indicator)
                    if elem.is_displayed():
                        log(f"✅ 已经跳转到connect device hotspot页面: {indicator}")
                        log("✅ 配网引导页处理完成，继续执行connect hotspot步骤...")
                        return True
                except:
                    continue
            
            # 如果第一次失败，可能不在引导页，继续执行
            if i == 0:
                log("⚠️ 可能不在配网引导页，继续执行...")
                return True
            
            # 如果第二次失败，且没有跳转到connect hotspot页面，返回False
            log("⚠️ 未找到Next按钮，且未检测到connect hotspot页面")
            return False
    
    return True


# ==================== connect device hotspot页面 ====================

def handle_connect_hotspot(driver) -> bool:
    """connect device hotspot页面：点击Connect和Join按钮"""
    log("📡 步骤6: 处理connect device hotspot页面...")
    
    # 点击Connect按钮
    log("🔍 点击Connect按钮...")
    connect_selectors = [
        '//XCUIElementTypeButton[@name="Connect"]',
        '//XCUIElementTypeButton[contains(@name,"Connect")]',
        '//XCUIElementTypeButton[contains(@name,"连接")]',
    ]
    
    connect_clicked = False
    for selector in connect_selectors:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, selector))
            )
            if btn.is_displayed():
                btn.click()
                log(f"✅ 点击 Connect 按钮成功: {selector}")
                time.sleep(1)  # 优化：从2秒减少到1秒
                connect_clicked = True
                break
        except Exception as e:
            log(f"⚠️ Connect按钮选择器失败: {selector} - {e}")
            continue
    
    if not connect_clicked:
        log("⚠️ 未找到Connect按钮，可能不在connect hotspot页面")
        return True  # 继续执行，可能已经自动连接
    
    # 点击Join按钮（在系统Alert弹窗中）
    log("🔍 点击Join按钮（系统Alert弹窗）...")
    
    # 先等待Alert弹窗出现 - 优化：减少等待时间
    log("⏳ 等待系统Alert弹窗出现...")
    time.sleep(2)  # 优化：从5秒减少到2秒
    
    # 使用iOS原生的Alert处理API（最有效的方法）
    log("🔍 使用iOS原生Alert处理...")
    try:
        alert = driver.switch_to.alert
        alert_text = alert.text
        log(f"✅ 检测到Alert文本: {alert_text}")
        if "Join" in alert_text or "加入" in alert_text or "Wants to Join" in alert_text:
            alert.accept()  # 接受Alert（相当于点击Join）
            log("✅ 通过Alert API点击Join成功")
            time.sleep(1)  # 优化：从2秒减少到1秒
        else:
            log(f"⚠️ Alert文本不包含Join，文本内容: {alert_text}")
    except AttributeError:
        log("❌ driver.switch_to.alert 不支持，可能需要其他方式")
        return False
    except Exception as alert_err:
        log(f"❌ Alert API失败: {alert_err}")
        return False
    
    return True


# ==================== 配网进度 & 结果 ====================

def _is_home_after_pairing(driver) -> bool:
    """
    通过页面元素判断是否已回到首页/第一阶段配网完成（iOS 版本）
    经验判定：
    - 存在 Home tab: //XCUIElementTypeButton[@name="home add"] 或 home add device
    - 且存在 AquaSense/Sora 文案或设备信息
    """
    try:
        # 先用"首页强特征"判定：home add 按钮出现，基本可认为已回首页
        add_candidates = [
            '//XCUIElementTypeButton[@name="home add"]',
            '//XCUIElementTypeButton[@name="home add device"]',
        ]
        for xp in add_candidates:
            try:
                els = driver.find_elements(AppiumBy.XPATH, xp)
                if any(e.is_displayed() for e in els):
                    return True
            except Exception:
                continue

        # 其次再结合 AquaSense/Sora/设备信息（用于部分首页没有 add 的场景）
        device_indicators = [
            '//XCUIElementTypeStaticText[contains(@name,"AquaSense")]',
            '//XCUIElementTypeStaticText[contains(@name,"Sora")]',
            '//XCUIElementTypeStaticText[contains(@name,"设备")]',
        ]
        for xp in device_indicators:
            try:
                els = driver.find_elements(AppiumBy.XPATH, xp)
                if any(e.is_displayed() for e in els):
                    # 同时检查是否有 home add 按钮
                    for add_xp in add_candidates:
                        try:
                            add_els = driver.find_elements(AppiumBy.XPATH, add_xp)
                            if any(e.is_displayed() for e in add_els):
                                return True
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception:
        return False

    return False


def wait_pairing_result(driver, timeout: int = 180) -> str:
    """
    等待配网结果：success / failed / timeout / success_need_next
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
            # 关键优化：优先用页面信息判断是否已回到首页（第一阶段配网完成）
            if _is_home_after_pairing(driver):
                log("✅ 页面判定：已回到首页（home add + AquaSense/Sora），认为配网完成")
                return "success"
            
            # 进度条页面
            try:
                txt = driver.find_element(
                    AppiumBy.XPATH,
                    '//XCUIElementTypeStaticText[@name="Pairing with your device (1/2)"]',
                )
                if txt.is_displayed():
                    log("🔄 配网进行中 ...")
                    time.sleep(3)  # 优化：从5秒减少到3秒
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

            # 新流程：配网成功后不直接回首页，而是停留在成功页，出现 Next 按钮
            # 为避免误判，尽量校验按钮文本包含 Next/下一步
            try:
                btns = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeButton[@name='Next']")
                for b in btns:
                    try:
                        if not b.is_displayed():
                            continue
                        # iOS 按钮通常通过 name 属性获取文本
                        btn_name = b.get_attribute("name") or ""
                        if any(k.lower() in btn_name.lower() for k in ["next", "下一步", "下一页", "继续"]):
                            log(f"✅ 检测到成功页 Next 按钮（{btn_name}），需要后续点击完成收尾")
                            return "success_need_next"
                    except Exception:
                        continue
                
                # 兜底：有些机型 Next 按钮可能无文本，但会停留在成功页且首页不出现
                all_btns = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeButton")
                if any(b.is_displayed() for b in all_btns) and not _is_home_after_pairing(driver):
                    log("✅ 检测到页面存在可见 Button（可能是成功页 Next），进入收尾流程判定")
                    return "success_need_next"
            except Exception:
                pass

            time.sleep(2)  # 优化：从3秒减少到2秒
        except Exception as e:
            log(f"⚠️ 检查配网状态异常: {e}")
            time.sleep(2)  # 优化：从3秒减少到2秒
    log("⏰ 配网超时（超过 3 分钟）")
    return "timeout"


def handle_post_pairing_success_flow(driver, timeout: int = 35) -> bool:
    """
    iOS 配网成功后停留在当前页，出现 Next 按钮：
      1) 点击 Next: //XCUIElementTypeButton[@name="Next"]
      2) 出现绑定弹框/页面，点击"已绑定"/"Already paired"
      3) 跳转首页，出现 home add + AquaSense/Sora
    """
    # 1) 点击成功页 Next
    try:
        next_selectors = [
            '//XCUIElementTypeButton[@name="Next"]',
            '//XCUIElementTypeButton[contains(@name,"Next")]',
            '//XCUIElementTypeButton[contains(@name,"下一步")]',
            '//XCUIElementTypeButton[contains(@name,"继续")]',
        ]
        next_clicked = False
        for selector in next_selectors:
            try:
                next_btn = WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable((AppiumBy.XPATH, selector))
                )
                if next_btn.is_displayed():
                    next_btn.click()
                    log(f"✅ 成功页：已点击 Next（选择器: {selector}）")
                    time.sleep(1)  # 优化：从1.5秒减少到1秒
                    next_clicked = True
                    break
            except Exception:
                continue
        
        if not next_clicked:
            log("❌ 成功页：未能点击 Next")
            return False
    except Exception as e:
        log(f"❌ 成功页：未能点击 Next: {e}")
        return False

    # 2) 绑定确认：弹框中的"Already paired"/"已绑定"按钮
    bound_text_xpaths = [
        # 英文
        '//XCUIElementTypeButton[@name="Already paired"]',
        '//XCUIElementTypeButton[contains(@name,"Already paired")]',
        '//XCUIElementTypeButton[contains(@name,"Already")]',
        '//XCUIElementTypeStaticText[@name="Already paired"]/..',
        # 中文（兼容其他语言包）
        '//XCUIElementTypeButton[@name="已绑定"]',
        '//XCUIElementTypeButton[contains(@name,"已绑定")]',
        '//XCUIElementTypeButton[contains(@name,"已配对")]',
        '//XCUIElementTypeStaticText[@name="已绑定"]/..',
    ]

    def _click_leftmost_button_fallback(wait_seconds: int = 12) -> bool:
        """兜底：弹框按钮文本可能取不到，取可见按钮中最左侧一个点击（通常是 Already paired）"""
        end = time.time() + wait_seconds
        while time.time() < end:
            try:
                btns = driver.find_elements(AppiumBy.XPATH, "//XCUIElementTypeButton")
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
                            location = el.location
                            size = el.size
                            return float(location.get("x", 0)) + float(size.get("width", 0)) / 2.0
                        except Exception:
                            return 999999.0
                    visible.sort(key=_center_x)
                    visible[0].click()
                    log("✅ 绑定弹框：已点击左侧按钮(兜底：最左 Button)")
                    time.sleep(1)  # 优化：从1.5秒减少到1秒
                    return True
            except Exception:
                pass
            time.sleep(0.6)
        return False

    try:
        clicked = False

        # 先等弹框/按钮出现（避免 Next 后立刻找不到）
        time.sleep(1.5)

        for xp in bound_text_xpaths:
            try:
                el = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp)))
                if el.is_displayed():
                    el.click()
                    log(f"✅ 绑定弹框：已点击确认按钮 ({xp})")
                    clicked = True
                    time.sleep(1)  # 优化：从1.5秒减少到1秒
                    break
            except Exception:
                continue

        if not clicked:
            # 最终兜底：点最左侧按钮
            if _click_leftmost_button_fallback(wait_seconds=12):
                clicked = True
                time.sleep(1.5)

        if not clicked:
            log("❌ 绑定弹框：未找到可点击的'Already paired/已绑定'按钮")
            return False
    except Exception as e:
        log(f"❌ 绑定弹框：未能点击确认按钮: {e}")
        return False

    # 3) 校验回到首页
    log("🔍 验证是否回到首页...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            if _is_home_after_pairing(driver):
                log("✅ 已回到首页（检测到 home add + AquaSense/Sora）")
                return True
        except Exception:
            pass
        time.sleep(1)

    log("❌ 未在超时内确认回到首页（home add + AquaSense/Sora 未同时出现）")
    return False


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
    
    # 新流程：成功页需要点击 Next -> 配对弹框确认 -> 回到 Home
    if result == "success_need_next":
        log("ℹ️ 检测到成功页 Next，需要完成收尾跳转首页...")
        if handle_post_pairing_success_flow(driver, timeout=45):
            result = "success"
        else:
            # 再兜底：如果其实已经回到首页，就别判失败
            if _is_home_after_pairing(driver):
                log("✅ 收尾流程失败但页面已在首页，按成功处理")
                result = "success"
            else:
                return "error", "配网成功后收尾步骤失败（Next/弹框/回Home）"
    
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

