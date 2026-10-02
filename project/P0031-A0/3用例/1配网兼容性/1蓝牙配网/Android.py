#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0031-A0 Android 蓝牙配网脚本（Android1）

步骤与关键元素：
  0) 强制 Kill App 后回首页
  1) 串口触发热点：SET state 4（连调端口命令 2 次，对齐 Android.py）
  2) 首页若有已配设备：more → Remove → Confirm
  3) 点击 add2
  4) 选择目标设备并 Add
  5) Set Up Wi-Fi（选择WIFI.py）
  6) 等待配网结果

稳定性：
  - 识别 instrumentation / session 失效并重建
  - 先触发热点再清理首页，避免清理操作占掉 BLE 广播窗口
  - 选设备失败（BLE 未上线）：多轮强恢复（Kill → 重启机器.py → 加长热点等待 → 再选）
  - WiFi：SSID 大小写不敏感 / 别名 / 可见网络 dump / 双向滚动+扫描刷新
  - 开测前 / 每轮配网后 / BLE 未上线恢复：串口 SET reset（重启机器.py）
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ---------------------------------------------------------------------------
# 路径 / 环境
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", ".."))
SHARED_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "1共用脚本")

try:
    from report_utils import init_run_env
except ImportError:
    sys.path.insert(0, SHARED_SCRIPTS_DIR)
    from report_utils import init_run_env

RUN_DIR, LOG_FILE, SCREENSHOT_DIR = init_run_env(prefix="2蓝牙配网-Android")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def log(msg: str) -> None:
    print(msg, flush=True)
    logger.info(msg)


# ---------------------------------------------------------------------------
# 动态加载 1共用脚本
# ---------------------------------------------------------------------------
def _load_py_module(filename: str, module_name: str):
    path = os.path.join(SHARED_SCRIPTS_DIR, filename)
    if not os.path.exists(path):
        log(f"⚠️ 未找到模块文件: {path}")
        return None
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        log(f"✅ 已加载模块: {filename}")
        return mod
    except Exception as e:
        log(f"⚠️ 加载模块失败 {filename}: {e}")
        return None


test_report_module = _load_py_module("测试报告.py", "测试报告")
_device_sel_mod = _load_py_module("选择设备.py", "device_selector")
select_device_from_module = getattr(_device_sel_mod, "select_device", None) if _device_sel_mod else None
wifi_setup_module = _load_py_module("选择WIFI.py", "wifi_setup")
reset_app_module = _load_py_module("重置应用-Android.py", "重置应用")
pairing_result_module = _load_py_module("配网结果-Android.py", "配网结果")
_reboot_mod = _load_py_module("重启机器.py", "重启机器")
reboot_robot_fn = getattr(_reboot_mod, "reboot_robot", None) if _reboot_mod else None

# 串口默认（可被 device_config.test_config / 环境变量覆盖）
SERIAL_PORT = os.environ.get("ROBOT_SERIAL_PORT", "/dev/cu.usbserial-1130")
SERIAL_BAUD = int(os.environ.get("ROBOT_SERIAL_BAUD", "115200"))
SERIAL_TRIGGER_CMD = os.environ.get("ROBOT_SERIAL_CMD", "SET state 4")

# 关键元素
XP_ADD2 = '(//android.widget.ImageView[@content-desc="add"])[2]'
XP_ADD = '//android.widget.ImageView[@content-desc="add"]'
XP_MORE = '//android.widget.ImageView[@content-desc="more"]'
XP_CHECKBOX = '//android.widget.ImageView[@content-desc="checkbox"]'
XP_BUTTON = "//android.widget.Button"
XP_PAIRING = '//android.widget.TextView[@text="Pairing with your device"]'


def call_reboot_robot(test_cfg: dict, wait_seconds: int, reason: str) -> None:
    """串口 SET reset 重启机器并等待。"""
    log(f"\n🔄 {reason}")
    if reboot_robot_fn:
        reboot_robot_fn(
            port=(
                os.environ.get("ROBOT_SERIAL_PORT")
                or test_cfg.get("robot_serial_port")
            ),
            baud=int(
                os.environ.get("ROBOT_SERIAL_BAUD")
                or test_cfg.get("robot_serial_baud")
                or 115200
            ),
            wait_seconds=wait_seconds,
            log_func=log,
        )
    else:
        log(f"⚠️ 未加载重启机器模块，仅等待 {wait_seconds}s 后继续...")
        time.sleep(wait_seconds)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def take_screenshot(driver, prefix: str) -> None:
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / f"screenshot_{prefix}_{ts}.png"
        driver.save_screenshot(str(path))
        log(f"📸 截图: {path}")
    except Exception as e:
        log(f"⚠️ 截图失败: {e}")


def _is_session_terminated_error(err: Exception) -> bool:
    s = str(err).lower()
    markers = (
        "session is either terminated",
        "invalidsessionid",
        "nosuchdriver",
        "a session is either terminated or not started",
        "session not created",
        "instrumentation process is not running",
        "instrumentation process",
        "cannot be proxied to uiautomator2",
        "uiautomator2 server",
        "could not proxy command",
        "proxying to the instrumentation",
        "socket hang up",
        "econnreset",
        "connection refused",
    )
    return any(m in s for m in markers)


def _driver_session_alive(driver) -> bool:
    if driver is None:
        return False
    if getattr(driver, "_ua2_session_dead", False):
        return False
    try:
        _ = driver.current_package
        return True
    except Exception as e:
        if _is_session_terminated_error(e):
            try:
                setattr(driver, "_ua2_session_dead", True)
            except Exception:
                pass
            return False
        try:
            driver.get_window_size()
            return True
        except Exception as e2:
            dead = _is_session_terminated_error(e2)
            if dead:
                try:
                    setattr(driver, "_ua2_session_dead", True)
                except Exception:
                    pass
            return not dead


def _mark_driver_session_dead(driver) -> None:
    if driver is None:
        return
    try:
        setattr(driver, "_ua2_session_dead", True)
    except Exception:
        pass


def _click_xpath(driver, xpath: str, timeout: float = 8, desc: str = "") -> bool:
    label = desc or xpath
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((AppiumBy.XPATH, xpath))
        )
        el.click()
        log(f"✅ 点击成功: {label}")
        return True
    except Exception as e:
        log(f"⚠️ 点击失败 [{label}]: {e}")
        if _is_session_terminated_error(e):
            raise RuntimeError(f"Appium 会话已失效: {e}") from e
        return False


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
def _filter_android_devices(config: dict) -> dict:
    devices = config.get("device_configs") or {}
    filtered = {}
    for key, cfg in devices.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("enabled") is False:
            continue
        platform = str(cfg.get("platform", "")).lower()
        if platform and platform != "android":
            continue
        if cfg.get("app_package") or platform == "android":
            filtered[key] = cfg
    config = dict(config)
    config["device_configs"] = filtered
    return config


def _list_adb_online_serials() -> set[str]:
    online: set[str] = set()
    try:
        r = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                online.add(parts[0].strip())
    except Exception as e:
        log(f"⚠️ 读取 adb devices 失败: {e}")
    return online


def _select_android_devices_for_run(device_cfgs: dict, test_cfg: dict) -> list[tuple[str, dict]]:
    """
    选出本次要跑的 Android 设备：
      1) 先看 adb 在线（默认开启）
      2) 再严格按 device_config.json 中的声明顺序执行
    """
    whitelist = test_cfg.get("active_android_devices")
    candidates: list[tuple[str, dict]] = []
    if whitelist:
        for name in whitelist:
            if name in device_cfgs:
                candidates.append((name, device_cfgs[name]))
            else:
                log(f"⚠️ active_android_devices 中未找到设备配置: {name}")
    else:
        candidates = list(device_cfgs.items())

    only_online = str(
        os.environ.get(
            "ONLY_ONLINE_ADB_DEVICES",
            str(test_cfg.get("only_online_adb_devices", True)),
        )
    ).lower() not in ("0", "false", "no")

    online = _list_adb_online_serials() if only_online else set()
    if only_online:
        log(f"📌 先看在线 adb 设备: {', '.join(sorted(online)) or '(无)'}")
        if not online:
            log("⚠️ adb 未检测到在线设备；将按配置顺序尝试全部候选设备")
            only_online = False

    selected: list[tuple[str, dict]] = []
    seen_serials: set[str] = set()
    for key, cfg in candidates:
        serial = (cfg.get("udid") or cfg.get("device_name") or "").strip()
        desc = cfg.get("description", key)
        if whitelist is not None and key not in set(whitelist):
            log(f"⏭️ 不在白名单，跳过 ({desc})")
            continue
        if only_online and serial and serial not in online:
            log(f"⏭️ 未在线，跳过 ({desc} / {serial})")
            continue
        if serial and serial in seen_serials:
            log(f"⏭️ 序列号重复，跳过重复配置 ({desc} / {serial} / key={key})")
            continue
        if serial:
            seen_serials.add(serial)
        selected.append((key, cfg))

    if selected:
        names = [c.get("description", k) for k, c in selected]
        log(f"✅ 本次测试顺序（在线 ∩ 配置顺序，共 {len(selected)} 台）: {', '.join(names)}")
    else:
        log("⚠️ 没有可测试的 Android 设备（在线过滤/白名单后为空）")
        log("💡 请确认 USB 已连接，且 device_name/udid 与 adb devices 序列号一致")
    return selected


def load_config() -> dict | None:
    """
    加载设备 / 路由器配置。
    优先级：环境变量 → 1共用脚本 → 上级目录 → 当前目录
    """
    candidates = []
    env_path = os.environ.get("DEVICE_CONFIG_FILE")
    if env_path:
        candidates.append(("环境变量", env_path))
    candidates.extend(
        [
            ("1共用脚本", os.path.join(SHARED_SCRIPTS_DIR, "device_config.json")),
            ("上级目录", os.path.join(os.path.dirname(_SCRIPT_DIR), "device_config.json")),
            ("当前目录", os.path.join(_SCRIPT_DIR, "device_config.json")),
        ]
    )
    for label, path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = _filter_android_devices(json.load(f))
            log(f"✅ 从 {label} 加载配置: {path}")
            return cfg
        except Exception as e:
            log(f"⚠️ 加载 {label} 配置失败: {e}")
    log("❌ 未找到任何配置文件，请确认 device_config.json 是否存在")
    return None


# ---------------------------------------------------------------------------
# 串口热点（对齐 Android.py：外层连调 2 次端口命令，不传 --repeat/--settle）
# ---------------------------------------------------------------------------
def _find_available_serial_ports() -> list[str]:
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

    if explicit:
        if os.path.exists(explicit) and os.access(explicit, os.R_OK):
            return explicit, "环境变量 ROBOT_SERIAL_PORT"
        # macOS：tty ↔ cu 互换再试
        alt = ""
        if "tty.usbserial" in explicit:
            alt = explicit.replace("tty.usbserial", "cu.usbserial")
        elif "cu.usbserial" in explicit:
            alt = explicit.replace("cu.usbserial", "tty.usbserial")
        if alt and os.path.exists(alt) and os.access(alt, os.R_OK):
            return alt, "环境变量 ROBOT_SERIAL_PORT（tty/cu 互换）"
        log(f"⚠️ ROBOT_SERIAL_PORT={explicit} 不存在或无读权限，改为自动枚举…")

    guess = SERIAL_PORT
    if guess and os.path.exists(guess) and os.access(guess, os.R_OK):
        return guess, "默认/内置串口路径"

    if candidates:
        darwin = sys.platform == "darwin"
        if darwin:
            cu = sorted(p for p in candidates if p.startswith("/dev/cu."))
            if cu:
                return cu[0], "自动枚举（优先 cu.*）"
        return sorted(candidates)[0], "自动枚举（第一个可用端口）"

    return None, ""


def trigger_robot_hotspot(
    driver: Any = None,
    settle_wait_s: int | None = None,
) -> bool:
    """
    触发机器热点（原方案）：
      - 调用 端口命令.py 连续 2 次（该脚本不支持 --repeat/--settle，勿传）
      - 失败再回退 expect
      - 默认热点稳定等待 12s；串口输出含复位特征时用 35s
      - settle_wait_s：强制覆盖稳定等待（BLE 恢复路径可加长）
      - 等待期间分段亮屏/探活，降低 UA2 空闲崩溃
    """
    log("📡 步骤1: 触发机器热点...")
    port, port_src = _resolve_serial_port_for_hotspot()
    baud = int(os.environ.get("ROBOT_SERIAL_BAUD", str(SERIAL_BAUD)))
    cmd = os.environ.get("ROBOT_SERIAL_CMD", SERIAL_TRIGGER_CMD)
    udid = _driver_udid(driver) if driver is not None else None

    if not port:
        log("❌ 未找到可用串口，无法触发热点")
        return False

    log(f"📌 串口: {port}（{port_src}） / baud={baud} / cmd={cmd}")

    port_command_script = os.path.join(SHARED_SCRIPTS_DIR, "端口命令.py")
    normal_wait_s = int(os.environ.get("ROBOT_HOTSPOT_WAIT_SECONDS", "12"))
    reboot_wait_s = int(os.environ.get("ROBOT_HOTSPOT_REBOOT_WAIT_SECONDS", "35"))

    def _post_trigger_wait(output_text: str) -> None:
        if settle_wait_s is not None and int(settle_wait_s) > 0:
            wait_s = int(settle_wait_s)
            log(f"⏳ BLE 恢复/指定等待：热点稳定 {wait_s}s ...")
            _idle_wait_keep_alive(wait_s, udid=udid, driver=driver)
            return
        text = (output_text or "").lower()
        reboot_markers = (
            "rst:0xc",
            "sw_cpu",
            "esp-rom:",
            "2nd stage bootloader",
            "loaded app from partition",
            "set reset",
            "enter mode init",
        )
        has_reboot = any(m in text for m in reboot_markers)
        wait_s = reboot_wait_s if has_reboot else normal_wait_s
        if has_reboot:
            log(f"⏳ 检测到设备重启/复位日志，热点拉起可能更慢，等待 {wait_s}s ...")
        else:
            log(f"⏳ 未检测到重启日志，等待热点稳定 {wait_s}s ...")
        _idle_wait_keep_alive(wait_s, udid=udid, driver=driver)

    if os.path.exists(port_command_script):
        log(f"📝 找到端口命令脚本: {port_command_script}")
        try:
            # 连续触发 2 次：上一轮配网/reset 后机器人可能仍未进广播态
            # 注意：P0031 端口命令.py 仅支持 --port/--baud/--command
            trigger_times = int(os.environ.get("ROBOT_HOTSPOT_TRIGGER_TIMES", "2"))
            success_count = 0
            last_out = ""
            for t in range(1, max(1, trigger_times) + 1):
                log(f"🔌 第 {t}/{trigger_times} 次串口触发热点...")
                result = subprocess.run(
                    [
                        sys.executable,
                        port_command_script,
                        "--port",
                        port,
                        "--baud",
                        str(baud),
                        "--command",
                        cmd,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                last_out = f"{result.stdout}\n{result.stderr}"
                if result.returncode == 0:
                    success_count += 1
                    if result.stdout and result.stdout.strip():
                        log(f"ℹ️ 第 {t} 次 stdout: {result.stdout.strip()}")
                    log(f"✅ 第 {t} 次串口热点触发成功")
                else:
                    if result.stderr and result.stderr.strip():
                        log(f"⚠️ 第 {t} 次 stderr: {result.stderr.strip()}")
                    if result.stdout and result.stdout.strip():
                        log(f"⚠️ 第 {t} 次 stdout: {result.stdout.strip()}")
                    log(f"⚠️ 第 {t} 次端口命令触发失败（返回码 {result.returncode}）")
                if t < trigger_times:
                    time.sleep(2)

            if success_count > 0:
                log(f"✅ 串口热点触发完成（成功 {success_count}/{trigger_times} 次）")
                _post_trigger_wait(last_out)
                return True
            log("⚠️ 端口命令脚本触发全部失败，回退到 expect...")
        except subprocess.TimeoutExpired:
            log("⚠️ 端口命令脚本超时，回退到 expect...")
        except Exception as e:
            log(f"⚠️ 端口命令脚本执行异常: {e}，回退到 expect...")
    else:
        log(f"⚠️ 未找到端口命令脚本: {port_command_script}，使用 expect...")

    # expect 兜底
    try:
        log("🔌 使用 expect 方式触发热点（备用方案）...")
        exp = (
            "#!/usr/bin/expect -f\n"
            "set timeout 40\n"
            "log_user 0\n"
            f"spawn screen {port} {baud}\n"
            "sleep 3\n"
            'send "\\r"\n'
            "sleep 2\n"
            f'send "{cmd}\\r"\n'
            "sleep 3\n"
            f'send "{cmd}\\r"\n'
            "sleep 3\n"
            'send "\\x01d"\n'
            "sleep 1\n"
            "expect eof\n"
        )
        exp_path = "/tmp/android_serial_trigger_hotspot.exp"
        with open(exp_path, "w", encoding="utf-8") as f:
            f.write(exp)
        os.chmod(exp_path, 0o755)
        result = subprocess.run(
            ["expect", exp_path], capture_output=True, text=True, timeout=60
        )
        out = f"{result.stdout}\n{result.stderr}"
        if result.returncode == 0:
            if result.stdout and result.stdout.strip():
                log(f"ℹ️ expect stdout: {result.stdout.strip()}")
            if result.stderr and result.stderr.strip():
                log(f"ℹ️ expect stderr: {result.stderr.strip()}")
            log("✅ 串口热点触发成功（expect方式）")
            _post_trigger_wait(out)
            return True
        log("❌ expect方式触发失败")
        if result.stderr and result.stderr.strip():
            log(f"⚠️ expect stderr: {result.stderr.strip()}")
        return False
    except Exception as e:
        log(f"❌ 所有触发方式都失败: {e}")
        return False


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def create_driver(dev_cfg: dict):
    """根据 device_config 为单个 Android 设备创建 Appium driver"""
    try:
        from appium.options.android import UiAutomator2Options

        udid = (dev_cfg.get("udid") or dev_cfg.get("device_name") or "").strip()
        # USB 掉线后先等回来，再唤醒 + 保亮屏
        if not _wait_adb_device_online(udid or None, timeout=60):
            log(f"❌ adb 设备未上线，无法创建 driver: {udid or '(default)'}")
            return None
        _ensure_device_awake(udid or None)
        _keep_screen_on_for_test(udid or None)

        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.device_name = dev_cfg["device_name"]
        options.platform_version = str(dev_cfg.get("platform_version", ""))
        options.app_package = dev_cfg["app_package"]
        options.app_activity = dev_cfg["app_activity"]
        options.automation_name = "UiAutomator2"
        options.no_reset = True
        options.new_command_timeout = 300
        options.set_capability("autoLaunch", True)
        # 降低隐式等待，避免 UA2 已挂时每个 find 卡很久
        options.set_capability("settings[waitForIdleTimeout]", 100)
        if udid:
            options.udid = udid

        url = f"http://127.0.0.1:{dev_cfg['port']}"
        log(f"🔗 尝试连接 Appium 服务器: {url}")
        driver = webdriver.Remote(url, options=options)
        try:
            driver.implicitly_wait(0)
        except Exception:
            pass
        log(f"✅ 设备 {dev_cfg.get('description', dev_cfg['device_name'])} 连接成功")
        return driver
    except Exception as e:
        log(f"❌ 创建设备驱动失败: {e}")
        return None


def _rebuild_driver(old_driver, dev_cfg: dict):
    udid = (dev_cfg.get("udid") or dev_cfg.get("device_name") or "").strip()
    try:
        if old_driver is not None:
            old_driver.quit()
    except Exception:
        pass
    log("♻️ 重建 Appium driver 前等待 adb 设备在线...")
    _wait_adb_device_online(udid or None, timeout=60)
    time.sleep(2)
    return create_driver(dev_cfg)


# ---------------------------------------------------------------------------
# App 重置 / 首页
# ---------------------------------------------------------------------------
def _driver_udid(driver) -> str:
    """从 capabilities 取设备序列号，供 adb -s 使用。"""
    try:
        caps = driver.capabilities or {}
    except Exception:
        return ""
    for key in ("udid", "deviceUDID", "deviceName"):
        val = str(caps.get(key) or "").strip()
        if val:
            return val
    return ""


def _adb_base(udid: str | None = None) -> list[str]:
    base = ["adb"]
    if udid:
        base += ["-s", udid]
    return base


def _adb_shell(udid: str | None, *args: str, timeout: float = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        _adb_base(udid) + ["shell", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _wait_adb_device_online(udid: str | None, timeout: float = 45) -> bool:
    """
    USB 偶发掉线（日志里出现 adb: device not found）时，等设备重新 online。
    """
    if not udid:
        # 无 udid 时等任意设备
        try:
            r = subprocess.run(
                ["adb", "wait-for-device"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return r.returncode == 0
        except Exception as e:
            log(f"⚠️ 等待 adb 设备超时/失败: {e}")
            return False

    end = time.time() + timeout
    while time.time() < end:
        online = _list_adb_online_serials()
        if udid in online:
            return True
        # 触发一次系统侧等待
        try:
            subprocess.run(
                ["adb", "-s", udid, "wait-for-device"],
                capture_output=True,
                text=True,
                timeout=min(8, max(1, end - time.time())),
            )
        except Exception:
            pass
        time.sleep(1.5)
    log(f"⚠️ 等待 adb 设备上线超时: {udid}")
    return False


def _idle_wait_keep_alive(
    wait_s: float,
    udid: str | None = None,
    driver: Any = None,
) -> None:
    """长等待分段执行：期间亮屏 + 轻探活，降低息屏/UA2 空闲崩溃概率。"""
    if wait_s <= 0:
        return
    end = time.time() + wait_s
    while time.time() < end:
        chunk = min(4.0, end - time.time())
        if chunk <= 0:
            break
        time.sleep(chunk)
        if udid:
            try:
                _ensure_device_awake(udid, log_ok=False)
            except Exception:
                pass
        if driver is not None and not getattr(driver, "_ua2_session_dead", False):
            try:
                _ = driver.current_package
            except Exception as e:
                if _is_session_terminated_error(e):
                    _mark_driver_session_dead(driver)
                    log("⚠️ 等待期间检测到 UA2/会话已失效")
                    return


def _ensure_device_awake(udid: str | None = None, log_ok: bool = True) -> None:
    """
    唤醒息屏并尽量解除锁屏，避免冷启动 App 打不开。
    不依赖是否已设密码：无密码时 dismiss-keyguard / 上滑即可。
    """
    try:
        # 亮屏
        _adb_shell(udid, "input", "keyevent", "KEYCODE_WAKEUP")
        time.sleep(0.3)
        # 部分机型需要再按一次电源或 MENU
        _adb_shell(udid, "input", "keyevent", "KEYCODE_MENU")
        time.sleep(0.2)
        # 尝试解除无密码锁屏（Android 高版本可能无效，忽略错误）
        try:
            _adb_shell(udid, "wm", "dismiss-keyguard")
        except Exception:
            pass
        try:
            # 上滑解锁（常见锁屏手势）
            size = _adb_shell(udid, "wm", "size")
            out = (size.stdout or "").strip()
            # Physical size: 1080x2340
            w, h = 1080, 2340
            if "x" in out:
                part = out.split(":")[-1].strip()
                if "x" in part:
                    ws, hs = part.split("x", 1)
                    w, h = int(ws.strip()), int(hs.strip())
            x = w // 2
            _adb_shell(
                udid,
                "input",
                "swipe",
                str(x),
                str(int(h * 0.78)),
                str(x),
                str(int(h * 0.28)),
                "300",
            )
        except Exception:
            pass
        if log_ok:
            log("💡 已尝试唤醒屏幕 / 解除锁屏")
    except Exception as e:
        log(f"⚠️ 唤醒屏幕失败（可手动点亮手机）: {e}")


def _keep_screen_on_for_test(udid: str | None = None) -> None:
    """
    测试期间尽量保持亮屏：USB 连接时 stayon + 拉长自动息屏时间。
    注：测试结束后不会自动恢复系统原超时（实验室机可接受）。
    """
    try:
        # USB 供电时保持亮屏（最有效）
        r1 = _adb_shell(udid, "svc", "power", "stayon", "true")
        # 自动息屏 30 分钟（毫秒）
        r2 = _adb_shell(udid, "settings", "put", "system", "screen_off_timeout", "1800000")
        # 打开「充电时保持唤醒」（部分机型开发者选项对应项）
        r3 = _adb_shell(udid, "settings", "put", "global", "stay_on_while_plugged_in", "3")
        ok = (r1.returncode == 0) or (r2.returncode == 0) or (r3.returncode == 0)
        if ok:
            log("💡 已设置测试期保亮屏（USB stayon + 息屏超时 30min）")
        else:
            log("⚠️ 保亮屏设置可能未生效，请确认手机 USB 调试授权")
    except Exception as e:
        log(f"⚠️ 保亮屏设置失败: {e}")


def _adb_force_stop_app(udid: str, package: str) -> bool:
    """
    强制杀死 App（比 terminate_app 更彻底）。
    无论当前在哪个界面，am force-stop 都会清掉进程。
    """
    if not package:
        return False
    base = _adb_base(udid)
    cmds = [
        base + ["shell", "am", "force-stop", package],
        base + ["shell", "am", "kill", package],
    ]
    ok_any = False
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                ok_any = True
            else:
                # force-stop 即使进程不存在也常返回 0；非 0 仍记录
                err = (r.stderr or r.stdout or "").strip()
                if err:
                    log(f"⚠️ {' '.join(cmd)} → {err[:120]}")
        except Exception as e:
            log(f"⚠️ adb 杀进程失败 ({' '.join(cmd)}): {e}")
    return ok_any


def _adb_launch_app(udid: str, package: str, activity: str | None = None) -> bool:
    """用 adb 冷启动 App（启动前先唤醒屏幕）。"""
    if not package:
        return False
    _ensure_device_awake(udid, log_ok=False)
    base = _adb_base(udid)
    try:
        if activity:
            act = activity.strip()
            if "/" in act:
                comp = act
            elif act.startswith("."):
                comp = f"{package}/{act}"
            elif act.startswith(package):
                comp = f"{package}/{act}"
            else:
                comp = f"{package}/{act}"
            cmd = base + ["shell", "am", "start", "-W", "-n", comp]
        else:
            cmd = base + [
                "shell",
                "monkey",
                "-p",
                package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            return True
        log(f"⚠️ adb 启动失败: {(r.stderr or r.stdout or '')[:160]}")
        return False
    except Exception as e:
        log(f"⚠️ adb 启动异常: {e}")
        return False


def _wait_for_add_button(driver, timeout: float = 20) -> bool:
    """冷启动后以 add / add2 出现为准，确认已到首页。"""
    end = time.time() + timeout
    while time.time() < end:
        for xp in (XP_ADD2, XP_ADD, '//android.widget.ImageView[contains(@content-desc,"add")]'):
            try:
                el = driver.find_element(AppiumBy.XPATH, xp)
                if el.is_displayed():
                    log(f"✅ 确认在首页（检测到 add）: {xp}")
                    return True
            except Exception as e:
                if _is_session_terminated_error(e):
                    raise
        time.sleep(0.8)
    return False


def _is_on_home(driver) -> bool:
    """首页判断：优先 add 按钮；文案仅作弱信号。"""
    for xp in (XP_ADD2, XP_ADD, '//android.widget.ImageView[contains(@content-desc,"add")]'):
        try:
            el = driver.find_element(AppiumBy.XPATH, xp)
            if el.is_displayed():
                return True
        except Exception as e:
            if _is_session_terminated_error(e):
                raise
    return False


def reset_app_to_home(driver) -> tuple[bool, Any]:
    """
    无论 App 当前在哪个界面：强制 kill → 再冷启动进首页。
    使用 adb am force-stop（比 Appium terminate_app 更彻底）。
    """
    log("🔄 强制 Kill App 后重新进入（不依赖当前界面）...")
    try:
        caps = driver.capabilities or {}
        pkg = caps.get("appPackage") or caps.get("appPackageName")
        activity = caps.get("appActivity")
        udid = _driver_udid(driver)
        if not pkg:
            log("⚠️ 无法获取 appPackage，跳过应用重启")
            return _wait_for_add_button(driver, timeout=5), driver

        # 0) 等 adb 在线 + 唤醒，否则 force-stop / 冷启动经常打不开
        if not _wait_adb_device_online(udid or None, timeout=30):
            log("❌ 重置应用前 adb 设备不在线")
            _mark_driver_session_dead(driver)
            return False, driver
        _ensure_device_awake(udid)

        # 1) Appium terminate（尽力）；失败不致命
        try:
            driver.terminate_app(pkg)
        except Exception:
            pass
        time.sleep(0.4)

        # 2) adb force-stop 一次即可（连杀两次更容易拖垮 UA2）
        log(f"🔪 adb force-stop: {pkg} (udid={udid or 'default'})")
        _adb_force_stop_app(udid, pkg)
        time.sleep(1.2)

        # 3) 冷启动：先 adb，再 activate_app 兜底
        launched = _adb_launch_app(udid, pkg, activity)
        if not launched:
            if not _wait_adb_device_online(udid or None, timeout=20):
                log("❌ 冷启动失败且 adb 掉线")
                _mark_driver_session_dead(driver)
                return False, driver
            try:
                driver.activate_app(pkg)
                launched = True
                log("✅ 已用 activate_app 拉起应用")
            except Exception as e:
                log(f"⚠️ activate_app 失败: {e}")
                if _is_session_terminated_error(e) or (
                    "device" in str(e).lower() and "not found" in str(e).lower()
                ):
                    _mark_driver_session_dead(driver)
                    return False, driver
        else:
            log("✅ 已用 adb 冷启动应用")
            # 给 UA2 一点恢复时间，再 activate（避免立刻 find 撞上崩溃中的 instrumentation）
            time.sleep(2.0)
            try:
                driver.activate_app(pkg)
            except Exception:
                pass

        time.sleep(2.5)

        # 4) 必须以 add 出现为准；失败再杀一次重开
        # 冷启动后偶发 UA2 instrumentation 已挂，需识别并交给外层重建 session
        try:
            if _wait_for_add_button(driver, timeout=18):
                return True, driver
        except Exception as e:
            if _is_session_terminated_error(e):
                log(f"❌ 冷启动后查找 add 时 UA2 已失效: {e}")
                _mark_driver_session_dead(driver)
                return False, driver
            raise

        log("⚠️ 首次冷启动后未见到 add，再次强制 Kill 并重开...")
        _ensure_device_awake(udid)
        _adb_force_stop_app(udid, pkg)
        time.sleep(1.5)
        _adb_launch_app(udid, pkg, activity)
        try:
            driver.activate_app(pkg)
        except Exception as e:
            if _is_session_terminated_error(e):
                log(f"❌ activate_app 时 UA2 已失效: {e}")
                _mark_driver_session_dead(driver)
                return False, driver
        time.sleep(4.0)
        try:
            if _wait_for_add_button(driver, timeout=20):
                return True, driver
        except Exception as e:
            if _is_session_terminated_error(e):
                log(f"❌ 二次冷启动后查找 add 时 UA2 已失效: {e}")
                _mark_driver_session_dead(driver)
                return False, driver
            raise

        log("⚠️ 无法确认首页 add 按钮，但已强制重启应用")
        try:
            take_screenshot(driver, "reset_app_no_add")
        except Exception as e:
            if _is_session_terminated_error(e):
                _mark_driver_session_dead(driver)
                return False, driver
        return False, driver
    except Exception as e:
        if _is_session_terminated_error(e):
            log(f"❌ 重置应用时会话失效: {e}")
            _mark_driver_session_dead(driver)
            return False, driver
        log(f"⚠️ 重置应用异常: {e}")
        return False, driver

def ensure_home_add_button(driver) -> bool:
    log("🔍 检查首页 add 按钮...")
    if _wait_for_add_button(driver, timeout=8):
        return True
    log("⚠️ 未找到add按钮")
    return False


# ---------------------------------------------------------------------------
# 首页清理
# ---------------------------------------------------------------------------
def _android_home_has_paired_device(driver) -> bool:
    """
    是否存在可删除的已配设备。
    若首页 add 已可见且没有 more，视为无设备（避免误判文案）。
    """
    # more 是删除入口，最可靠
    more_selectors = [
        XP_MORE,
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

    # 有 add、无 more → 通常是空首页，不算已配设备
    try:
        if _is_on_home(driver):
            return False
    except Exception:
        pass

    indicators = [
        "//android.widget.TextView[contains(@text,'Sora')]",
        "//android.widget.TextView[contains(@text,'robot')]",
        "//android.widget.TextView[contains(@text,'standby')]",
    ]
    for xp in indicators:
        try:
            for e in driver.find_elements(AppiumBy.XPATH, xp):
                if e.is_displayed():
                    return True
        except Exception as e:
            if _is_session_terminated_error(e):
                raise RuntimeError(f"Appium 会话已失效: {e}") from e
    return False


def delete_paired_device_android(driver) -> bool:
    """more → Remove → Confirm"""
    log("🔧 检测到已配对设备，开始删除设备...")
    try:
        more_selectors = [
            XP_MORE,
            '//android.widget.Button[@content-desc="more"]',
            '//android.view.View[@content-desc="more"]',
        ]
        more = None
        for xp in more_selectors:
            try:
                el = driver.find_element(AppiumBy.XPATH, xp)
                if el.is_displayed():
                    more = el
                    log(f"✅ 找到 more 按钮: {xp}")
                    break
            except Exception:
                continue
        if not more:
            log("⚠️ 未找到 more 按钮，可能没有已配对设备")
            return False
        more.click()
        time.sleep(1.2)

        remove_selectors = [
            '//android.widget.TextView[@text="Remove"]',
            '//android.widget.Button[@text="Remove"]',
            '//android.widget.TextView[contains(@text,"Remove")]',
            '//android.widget.TextView[contains(@text,"删除")]',
            '//android.widget.Button[contains(@text,"删除")]',
        ]
        remove = None
        for xp in remove_selectors:
            try:
                el = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp)))
                remove = el
                log(f"✅ 找到 Remove 按钮: {xp}")
                break
            except Exception:
                continue
        if not remove:
            log("⚠️ 未找到 Remove 按钮")
            return False
        remove.click()
        time.sleep(1.0)

        confirm_selectors = [
            '//android.widget.Button[@text="Confirm"]',
            '//android.widget.TextView[@text="Confirm"]',
            '//android.widget.Button[contains(@text,"Confirm")]',
            '//android.widget.Button[@text="确认"]',
            '//android.widget.Button[contains(@text,"确认")]',
            '//android.widget.Button[@resource-id="android:id/button1"]',
        ]
        confirm = None
        for xp in confirm_selectors:
            try:
                el = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((AppiumBy.XPATH, xp)))
                confirm = el
                log(f"✅ 找到 Confirm 按钮: {xp}")
                break
            except Exception:
                continue
        if not confirm:
            log("⚠️ 未找到 Confirm 按钮")
            return False
        confirm.click()
        log("✅ 删除设备 Confirm 点击成功，等待页面刷新...")
        time.sleep(2.5)
        pkg = driver.capabilities.get("appPackage")
        if pkg:
            try:
                driver.activate_app(pkg)
            except Exception:
                pass
        return True
    except Exception as e:
        log(f"❌ 删除设备失败: {e}")
        take_screenshot(driver, "delete_paired_device_fail")
        if _is_session_terminated_error(e):
            raise
        return False


def cleanup_home_devices_android(driver) -> bool:
    try:
        has_paired = _android_home_has_paired_device(driver)
    except Exception as e:
        log(f"❌ 首页设备检测失败: {e}")
        if _is_session_terminated_error(e) or "会话已失效" in str(e):
            raise
        return False

    if not has_paired:
        # 仍确认 add 在；不在则强制 Kill 再进
        if ensure_home_add_button(driver):
            log("✅ 首页未检测到已配对设备，无需删除")
            return True
        log("⚠️ 未见已配设备，但也没有 add，强制 Kill App 后重进...")
        ok, _ = reset_app_to_home(driver)
        return bool(ok and ensure_home_add_button(driver))

    log("⚠️ 首页已存在可删除设备，开始清理（more->Remove->Confirm）...")
    for i in range(2):
        ok = delete_paired_device_android(driver)
        if ok and not _android_home_has_paired_device(driver):
            log("✅ 删除已配对设备完成")
            return True
        if i < 1:
            log(f"⚠️ 第 {i + 1}/2 次删除后仍检测到设备，重试...")
            time.sleep(2)

    if ensure_home_add_button(driver):
        log("✅ 清理完成：add 按钮已就绪")
        return True

    # more 找不到 / 删除失败时：强制 Kill 再进，避免卡在半屏
    log("⚠️ 清理未完成且无 add，强制 Kill App 后重新进入再检测...")
    ok, _ = reset_app_to_home(driver)
    if not ok:
        take_screenshot(driver, "cleanup_home_devices_fail")
        return False

    if _android_home_has_paired_device(driver):
        log("⚠️ Kill 后仍有已配设备，再删一次...")
        delete_paired_device_android(driver)

    if ensure_home_add_button(driver):
        log("✅ 强制 Kill 后首页 add 已就绪")
        return True

    log("❌ 清理完成后仍未检测到 add 按钮")
    take_screenshot(driver, "cleanup_home_devices_fail")
    return False


# ---------------------------------------------------------------------------
# 进入选设备 / 选设备 / WiFi / 结果
# ---------------------------------------------------------------------------
def tap_add_device(driver) -> bool:
    log("📱 步骤2: 点击添加设备按钮...")
    for xp in (XP_ADD2, XP_ADD, '//android.widget.ImageView[contains(@content-desc,"add")]',
               '//android.widget.Button[contains(@text,"Add")]',
               '//android.widget.Button[contains(@text,"添加")]'):
        if _click_xpath(driver, xp, timeout=5, desc=xp):
            time.sleep(2)
            return True
    take_screenshot(driver, "tap_add_device_fail")
    return False


def click_home_add2(driver) -> bool:
    """首页点击 add2（含兜底）。"""
    try:
        if _click_xpath(driver, XP_ADD2, timeout=8, desc="add2"):
            time.sleep(2)
            return True
        if ensure_home_add_button(driver) and tap_add_device(driver):
            log("ℹ️ 走了 add 按钮兜底选择器，继续")
            return True
        return False
    except RuntimeError as e:
        if "会话已失效" in str(e):
            raise
        raise


def pick_target_device(driver, target: dict) -> bool:
    if not select_device_from_module:
        log("❌ 设备选择模块未加载")
        return False
    log("🔌 使用独立设备选择模块: 选择设备.py")
    try:
        ok = select_device_from_module(
            driver=driver,
            target_device_config=target,
            platform="android",
            log_func=log,
            screenshot_dir=SCREENSHOT_DIR,
        )
        if ok:
            log("✅ 独立设备选择模块执行成功")
            return True
        log("❌ 设备选择失败")
        return False
    except Exception as e:
        log(f"❌ 设备选择异常: {e}")
        if _is_session_terminated_error(e):
            raise
        return False


def recover_hotspot_and_pick(
    driver,
    target_dev: dict,
    test_cfg: dict | None = None,
    reboot_wait_s: int | None = None,
) -> tuple[bool, Any]:
    """
    BLE 未上线 / 选设备失败后，多轮升级强恢复：
      每轮：Kill → 重启机器.py（SET reset，等待递增）→ SET state 4（加长稳定等待）
           → 清理 → add2 → 再选。
    覆盖「串口 OK 但 App 列表空 / 只有其它 SN」的偶发广播失败。
    """
    cfg = test_cfg or {}
    base_wait = int(
        reboot_wait_s
        if reboot_wait_s is not None
        else os.environ.get(
            "ROBOT_REBOOT_WAIT_SECONDS",
            str(cfg.get("robot_reboot_wait_seconds", 30)),
        )
    )
    max_rounds = int(
        os.environ.get(
            "ROBOT_BLE_RECOVER_ROUNDS",
            str(cfg.get("robot_ble_recover_rounds", 3)),
        )
    )
    hotspot_settle = int(
        os.environ.get(
            "ROBOT_BLE_RECOVER_HOTSPOT_WAIT",
            str(cfg.get("robot_ble_recover_hotspot_wait_seconds", 22)),
        )
    )
    escalate_s = int(
        os.environ.get(
            "ROBOT_BLE_RECOVER_ESCALATE_SECONDS",
            str(cfg.get("robot_ble_recover_escalate_seconds", 15)),
        )
    )
    max_rounds = max(1, max_rounds)

    log(
        f"♻️ 目标设备未出现在列表（BLE 未上线），"
        f"最多 {max_rounds} 轮强恢复（Kill → 重启机器.py → 热点{hotspot_settle}s → 再选）..."
    )

    for round_i in range(1, max_rounds + 1):
        wait_s = base_wait + (round_i - 1) * max(0, escalate_s)
        log(f"♻️ BLE 强恢复第 {round_i}/{max_rounds} 轮（reset 等待 {wait_s}s）...")

        ok, driver = reset_app_to_home(driver)
        if not ok and not _driver_session_alive(driver):
            return False, driver

        call_reboot_robot(
            cfg,
            wait_s,
            f"BLE 未上线恢复[{round_i}/{max_rounds}]：重启机器脚本 SET reset，"
            f"等待 {wait_s}s 后再拉热点",
        )

        if not trigger_robot_hotspot(driver, settle_wait_s=hotspot_settle):
            if not _driver_session_alive(driver):
                return False, driver
            log(f"⚠️ 第 {round_i} 轮热点触发失败，继续下一轮恢复...")
            continue

        if not _driver_session_alive(driver):
            return False, driver

        try:
            if not cleanup_home_devices_android(driver):
                if not _driver_session_alive(driver):
                    return False, driver
                log("⚠️ 恢复重试时首页清理失败，仍尝试点击 add2")
        except Exception as e:
            if _is_session_terminated_error(e) or not _driver_session_alive(driver):
                return False, driver
            log(f"⚠️ 恢复重试清理异常: {e}")

        if not click_home_add2(driver):
            ok, driver = reset_app_to_home(driver)
            if not (ok and click_home_add2(driver)):
                if not _driver_session_alive(driver):
                    return False, driver
                log(f"⚠️ 第 {round_i} 轮未能进入选设备页，继续下一轮恢复...")
                continue

        if pick_target_device(driver, target_dev):
            log(f"✅ BLE 强恢复第 {round_i}/{max_rounds} 轮成功选到目标设备")
            return True, driver

        if not _driver_session_alive(driver):
            return False, driver
        log(f"⚠️ 第 {round_i}/{max_rounds} 轮仍未扫到目标 SN，继续升级恢复...")

    log(f"❌ BLE 强恢复 {max_rounds} 轮后仍未选到目标设备")
    return False, driver


def perform_wifi_setup(
    driver,
    wifi_name: str,
    wifi_pwd: str,
    wifi_aliases: list | None = None,
) -> bool:
    if not wifi_setup_module:
        log("⚠️ WiFi 选择模块未加载，无法执行 WiFi 设置")
        return False

    aliases = [a for a in (wifi_aliases or []) if a]
    kwargs = dict(
        driver=driver,
        wifi_name=wifi_name,
        wifi_password=wifi_pwd,
        platform="android",
        log_func=log,
        screenshot_func=take_screenshot,
    )
    # 新版选择WIFI 支持 aliases；旧签名则忽略
    try:
        return wifi_setup_module.perform_wifi_setup(**kwargs, wifi_aliases=aliases)
    except TypeError:
        return wifi_setup_module.perform_wifi_setup(**kwargs)


def handle_wifi_guide_page_after_wifi_next_android(driver: Any, timeout: int = 3) -> bool:
    """兜底：若仍停在 checkbox 页，再补一轮 checkbox + Next。"""
    try:
        checkbox = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((AppiumBy.XPATH, XP_CHECKBOX))
        )
        if not checkbox or not checkbox.is_displayed():
            log("ℹ️ 未显示到配网引导页 checkbox，继续配网进程")
            return True
    except Exception:
        log("ℹ️ 未出现配网引导页（checkbox 未找到），继续配网进程")
        return True

    log("🧷 引导页仍在：勾选 checkbox...")
    if not _click_xpath(driver, XP_CHECKBOX, timeout=6, desc="checkbox"):
        take_screenshot(driver, "wifi_guide_checkbox_fail")
        return False
    time.sleep(0.8)
    log("➡️ 引导页：点击 Next（//android.widget.Button）...")
    if not _click_xpath(driver, XP_BUTTON, timeout=8, desc="Next Button"):
        take_screenshot(driver, "wifi_guide_next_fail")
        return False
    time.sleep(1.5)
    log("✅ 引导页：已点击 Next，进入配网进程")
    return True


def wait_pairing_result(driver, target_dev: dict | None = None, timeout: int = 180) -> str:
    def is_home_func(drv):
        return _is_on_home(drv)

    if pairing_result_module and hasattr(pairing_result_module, "wait_for_pairing_result"):
        return pairing_result_module.wait_for_pairing_result(
            driver,
            timeout=timeout,
            target_device_config=target_dev,
            is_home_func=is_home_func,
            log_func=log,
        )

    log("⚠️ 配网结果模块未加载，使用内部实现")
    log(f"⏳ 步骤6: 等待配网结果（超时 {timeout}s）...")
    start = time.time()
    last_heartbeat = start
    dev_name = (target_dev or {}).get("device_name", "")
    dev_sn = str((target_dev or {}).get("device_sn", "")).strip()
    sn_digits = dev_sn.lstrip("Bb") if dev_sn else ""

    while time.time() - start < timeout:
        try:
            now = time.time()
            if now - last_heartbeat >= 30:
                elapsed = int(now - start)
                log(f"⏳ 配网仍在进行中... 已等待 {elapsed}s / {timeout}s")
                last_heartbeat = now

            try:
                if is_home_func(driver):
                    # 首页若出现目标设备名/SN 也算成功
                    for xp in (
                        ([f'//android.widget.TextView[@text="{dev_name}"]'] if dev_name else [])
                        + ([f'//android.widget.TextView[contains(@text,"{dev_sn}")]'] if dev_sn else [])
                    ):
                        try:
                            el = driver.find_element(AppiumBy.XPATH, xp)
                            if el.is_displayed():
                                log(f"✅ 配网成功（已回首页且命中设备）: {xp}")
                                return "success"
                        except Exception:
                            pass
            except Exception as e:
                if _is_session_terminated_error(e):
                    raise

            try:
                pairing = driver.find_element(AppiumBy.XPATH, XP_PAIRING)
                if pairing.is_displayed():
                    log("🔄 配网进行中 ...")
                    time.sleep(5)
                    continue
            except Exception as e:
                if _is_session_terminated_error(e):
                    raise

            success_xps = []
            if dev_name:
                success_xps += [
                    f'//android.widget.TextView[@text="{dev_name}"]',
                    f'//android.widget.TextView[contains(@text,"{dev_name}")]',
                ]
            if dev_sn:
                success_xps += [
                    f'//android.widget.TextView[contains(@text,"{dev_sn}")]',
                    f'//android.widget.TextView[contains(@text,"SN:{dev_sn}")]',
                    f'//android.widget.TextView[contains(@text,"SN: {dev_sn}")]',
                ]
            if sn_digits and sn_digits != dev_sn:
                success_xps += [
                    f'//android.widget.TextView[contains(@text,"{sn_digits}")]',
                    f'//android.widget.TextView[contains(@text,"SN:{sn_digits}")]',
                ]

            for xp in success_xps:
                try:
                    el = driver.find_element(AppiumBy.XPATH, xp)
                    if el.is_displayed():
                        log(f"✅ 配网成功（命中目标设备）: {xp}")
                        return "success"
                except Exception as e:
                    if _is_session_terminated_error(e):
                        raise

            for xp in (
                '//android.widget.TextView[@text="Data transmitting failed."]',
                '//android.widget.TextView[contains(@text,"failed")]',
                '//android.widget.TextView[contains(@text,"失败")]',
                '//android.widget.TextView[contains(@text,"Unable to")]',
                '//android.widget.TextView[contains(@text,"timeout")]',
            ):
                try:
                    el = driver.find_element(AppiumBy.XPATH, xp)
                    if el.is_displayed():
                        log(f"❌ 配网失败: {xp}")
                        return "failed"
                except Exception as e:
                    if _is_session_terminated_error(e):
                        raise

            time.sleep(3)
        except Exception as e:
            if _is_session_terminated_error(e) or "会话已失效" in str(e):
                raise
            log(f"⚠️ 检查配网结果时出错: {e}")
            time.sleep(3)

    log("⏰ 配网超时")
    take_screenshot(driver, "pairing_timeout")
    return "timeout"


# ---------------------------------------------------------------------------
# 单次流程
# ---------------------------------------------------------------------------
def run_single_flow(
    driver,
    wifi_name: str,
    wifi_pwd: str,
    target_dev: dict,
    timeout_s: int = 180,
    wifi_aliases: list | None = None,
    test_cfg: dict | None = None,
    reboot_wait_s: int | None = None,
) -> tuple[str, str, Any]:
    """
    单次配网完整流程（原方案顺序）：
      重置 App → 触发热点 → 清理首页 → add2 → 选设备 → WiFi → 结果
    先拉热点再清理，避免清理操作占掉 BLE 广播窗口。
    BLE 未上线时走重启机器.py 完整复位后再选。
    """
    log(f"\n🔄 开始单次配网流程（WiFi: {wifi_name}）")
    log("=" * 60)

    try:
        ok, driver = reset_app_to_home(driver)
        # UA2 instrumentation 崩溃后，current_package 偶发仍通，但找元素必挂：
        # 只要重置失败且标记了 session dead，一律重建，禁止「仍尝试继续」
        if not ok and not _driver_session_alive(driver):
            log("❌ 检测到 Appium/UiAutomator2 会话已失效，需重建 driver 后重试本轮")
            return "error", "DRIVER_SESSION_TERMINATED", driver
        if not ok:
            # 二次探活（强制走 find 相关能力），避免误判仍存活
            try:
                _ = driver.get_window_size()
            except Exception as e:
                if _is_session_terminated_error(e):
                    _mark_driver_session_dead(driver)
                    log("❌ 重置失败且窗口探测确认 UA2 已挂，重建 driver")
                    return "error", "DRIVER_SESSION_TERMINATED", driver
            log("⚠️ 应用重置未确认到首页 add，仍尝试继续（会话仍存活）")
        # 先触发热点，再清首页（原方案）
        if not trigger_robot_hotspot(driver):
            return "error", "触发机器热点失败", driver

        if not _driver_session_alive(driver):
            log("❌ 热点触发后检测到 Appium/UiAutomator2 已失效，需重建 driver 后重试")
            return "error", "DRIVER_SESSION_TERMINATED", driver

        try:
            if not cleanup_home_devices_android(driver):
                if not _driver_session_alive(driver):
                    return "error", "DRIVER_SESSION_TERMINATED", driver
                return "error", "首页设备清理失败", driver
        except Exception as e:
            if _is_session_terminated_error(e) or not _driver_session_alive(driver):
                log(f"❌ 首页清理异常且会话失效: {e}")
                return "error", "DRIVER_SESSION_TERMINATED", driver
            raise

        try:
            if not click_home_add2(driver):
                if not _driver_session_alive(driver):
                    return "error", "DRIVER_SESSION_TERMINATED", driver
                # 热点等待期间 App 可能被系统切走：Kill 回首页再点一次
                log("♻️ 未找到 add2，强制 Kill 回首页后重试点击...")
                ok, driver = reset_app_to_home(driver)
                if ok and click_home_add2(driver):
                    pass
                else:
                    if not _driver_session_alive(driver):
                        return "error", "DRIVER_SESSION_TERMINATED", driver
                    return "error", "首页缺少 add2 按钮（且兜底失败）", driver
        except RuntimeError as e:
            if "会话已失效" in str(e):
                return "error", "DRIVER_SESSION_TERMINATED", driver
            raise

        if not pick_target_device(driver, target_dev):
            if not _driver_session_alive(driver):
                return "error", "DRIVER_SESSION_TERMINATED", driver
            ok_pick, driver = recover_hotspot_and_pick(
                driver,
                target_dev,
                test_cfg=test_cfg,
                reboot_wait_s=reboot_wait_s,
            )
            if not ok_pick:
                if not _driver_session_alive(driver):
                    return "error", "DRIVER_SESSION_TERMINATED", driver
                return "error", "设备选择失败", driver

        if not perform_wifi_setup(driver, wifi_name, wifi_pwd, wifi_aliases=wifi_aliases):
            if not _driver_session_alive(driver):
                return "error", "DRIVER_SESSION_TERMINATED", driver
            return "error", "WiFi 设置失败", driver

        # 系统 WiFi 返回后会话更容易挂，再探活一次
        if not _driver_session_alive(driver):
            log("❌ WiFi 设置后会话失效")
            return "error", "DRIVER_SESSION_TERMINATED", driver

        if not handle_wifi_guide_page_after_wifi_next_android(driver, timeout=3):
            return "error", "配网引导页处理失败", driver

        result = wait_pairing_result(driver, target_dev, timeout=timeout_s)
        if result == "success":
            return "success", "配网成功", driver
        if result == "success_need_next":
            if pairing_result_module and hasattr(pairing_result_module, "handle_post_pairing_success_flow"):
                if pairing_result_module.handle_post_pairing_success_flow(
                    driver, timeout=35, is_home_func=_is_on_home, log_func=log
                ):
                    return "success", "配网成功", driver
                if _is_on_home(driver):
                    log("✅ 收尾流程失败但页面已在首页，按成功处理")
                    return "success", "配网成功", driver
                return "error", "配网成功后收尾步骤失败（Next/弹框/回Home）", driver
            log("⚠️ 配网结果模块未加载，无法处理收尾流程")
            return "error", "配网成功后收尾步骤失败（模块未加载）", driver
        if result == "failed":
            return "failed", "配网失败", driver
        return "timeout", "配网超时", driver

    except Exception as e:
        if _is_session_terminated_error(e) or "会话已失效" in str(e):
            log(f"❌ 流程中会话失效: {e}")
            return "error", "DRIVER_SESSION_TERMINATED", driver
        log(f"❌ 单次流程异常: {e}")
        return "error", str(e), driver


# ---------------------------------------------------------------------------
# 报告 / main
# ---------------------------------------------------------------------------
def finalize_results(total_tests, success_count, failure_count, detailed_results, test_config, interrupted=False):
    if test_report_module and hasattr(test_report_module, "finalize_results"):
        test_report_module.finalize_results(
            total_tests=total_tests,
            success_count=success_count,
            failure_count=failure_count,
            detailed_results=detailed_results,
            test_config=test_config,
            platform="Android",
            network_method="蓝牙配网",
            run_dir=RUN_DIR,
            log_func=log,
            interrupted=interrupted,
        )
        return
    rate = (success_count / total_tests) if total_tests else 0
    log("\n" + "=" * 60)
    log(f"📊 测试汇总: 总={total_tests} 成功={success_count} 失败={failure_count} 成功率={rate:.1%}")
    if interrupted:
        log("⚠️ 测试被中断")
    log("=" * 60)


def main():
    log("🚀 启动 P0031-A0 Android 蓝牙配网脚本（Android1）")
    log("=" * 80)

    cfg = load_config()
    if not cfg:
        return

    device_cfgs = cfg.get("device_configs", {})
    wifi_cfgs = cfg.get("wifi_configs", [])
    test_cfg = cfg.get("test_config", {})
    loop_per_router = int(test_cfg.get("loop_count_per_router", 1))
    timeout_s = int(test_cfg.get("timeout_seconds", 180))

    _rsp = (test_cfg.get("robot_serial_port") or "").strip()
    if _rsp and not (os.environ.get("ROBOT_SERIAL_PORT") or "").strip():
        os.environ["ROBOT_SERIAL_PORT"] = _rsp
        log(f"📌 test_config.robot_serial_port → {_rsp}")
    _rsb = test_cfg.get("robot_serial_baud")
    if _rsb is not None and not os.environ.get("ROBOT_SERIAL_BAUD"):
        os.environ["ROBOT_SERIAL_BAUD"] = str(_rsb)

    target_dev = cfg.get("target_device")
    if not target_dev or not target_dev.get("device_sn") or not target_dev.get("device_name"):
        log("❌ target_device 配置不完整（需要 device_sn / device_name）")
        return

    device_items = _select_android_devices_for_run(device_cfgs, test_cfg)
    log(f"✅ 目标设备: {target_dev.get('device_name')} (SN: {target_dev.get('device_sn')})")
    log(f"📱 待测 Android: {len(device_items)}")
    log(f"📶 路由器数量: {len(wifi_cfgs)}")
    log(f"🔁 每路由器循环: {loop_per_router}")

    reboot_wait_s = int(
        os.environ.get(
            "ROBOT_REBOOT_WAIT_SECONDS",
            str(test_cfg.get("robot_reboot_wait_seconds", 30)),
        )
    )
    log(
        f"🔄 重启策略: 开测前一次 + 每轮配网后 + BLE未上线最多"
        f"{int(os.environ.get('ROBOT_BLE_RECOVER_ROUNDS', str(test_cfg.get('robot_ble_recover_rounds', 3))))}"
        f"轮强恢复 → 重启机器.py（SET reset）→ 等待 {reboot_wait_s}s 起递增"
        f"（切换路由/手机不额外重启）"
    )

    if not device_items:
        log("❌ 无可用 Android 设备，结束")
        return

    # 正式开测前先串口重启一次
    call_reboot_robot(
        test_cfg,
        reboot_wait_s,
        "测试开始前：串口重启机器，等待就绪后再开测",
    )

    total = succ = fail = 0
    detailed_results: dict = {}
    interrupted = False

    try:
        for dev_idx, (dev_key, dev_cfg) in enumerate(device_items):
            device_name = dev_cfg.get("description", dev_cfg["device_name"])
            log(f"\n📱 当前测试设备: {device_name} ({dev_idx + 1}/{len(device_items)})")
            log("-" * 60)

            driver = create_driver(dev_cfg)
            if not driver:
                log("❌ 该设备 driver 创建失败，跳过")
                continue

            detailed_results.setdefault(device_name, {"routers": {}})

            try:
                for wifi_idx, wifi in enumerate(wifi_cfgs):
                    name = wifi["name"]
                    pwd = wifi["password"]
                    log(f"\n📶 路由器: {name} ({wifi_idx + 1}/{len(wifi_cfgs)})")

                    detailed_results[device_name]["routers"].setdefault(
                        name, {"success": 0, "failure": 0, "rounds": []}
                    )

                    for i in range(loop_per_router):
                        log(f"\n🔄 第 {i + 1}/{loop_per_router} 次测试")
                        total += 1
                        test_timestamp = datetime.now().strftime("%H:%M:%S")
                        session_retries = 0
                        max_session_retries = int(
                            os.environ.get(
                                "APPIUM_SESSION_RETRIES",
                                str(test_cfg.get("appium_session_retries", 3)),
                            )
                        )
                        wifi_aliases = wifi.get("aliases") or wifi.get("ssid_aliases") or []

                        while True:
                            if not _driver_session_alive(driver):
                                log("♻️ 开测前会话失效，重建 driver...")
                                driver = _rebuild_driver(driver, dev_cfg)
                                if not driver:
                                    res, msg = "error", "driver 重建失败"
                                    break

                            res, msg, driver = run_single_flow(
                                driver,
                                name,
                                pwd,
                                target_dev,
                                timeout_s=timeout_s,
                                wifi_aliases=wifi_aliases,
                                test_cfg=test_cfg,
                                reboot_wait_s=reboot_wait_s,
                            )

                            if (
                                res == "error"
                                and msg == "DRIVER_SESSION_TERMINATED"
                                and session_retries < max_session_retries
                            ):
                                session_retries += 1
                                log(
                                    f"♻️ 会话失效，重建 driver 并重试本轮"
                                    f"（{session_retries}/{max_session_retries}）..."
                                )
                                driver = _rebuild_driver(driver, dev_cfg)
                                if not driver:
                                    res, msg = "error", "driver 重建失败"
                                    break
                                continue
                            break

                        detailed_results[device_name]["routers"][name]["rounds"].append(
                            {
                                "round": i + 1,
                                "result": res,
                                "message": msg,
                                "timestamp": test_timestamp,
                            }
                        )
                        if res == "success":
                            succ += 1
                            detailed_results[device_name]["routers"][name]["success"] += 1
                            log(f"✅ 测试成功: {msg}")
                        else:
                            fail += 1
                            detailed_results[device_name]["routers"][name]["failure"] += 1
                            log(f"❌ 测试失败: {msg}")

                        # 每轮结束后再探活，避免带着死会话进入下一轮
                        if not _driver_session_alive(driver):
                            log("♻️ 本轮结束后会话已失效，预先重建以备下一轮")
                            driver = _rebuild_driver(driver, dev_cfg)

                        # 每轮配网后重启机器；整次测试最后一轮不再重启
                        is_last_round = (
                            i >= loop_per_router - 1
                            and wifi_idx >= len(wifi_cfgs) - 1
                            and dev_idx >= len(device_items) - 1
                        )
                        if not is_last_round:
                            call_reboot_robot(
                                test_cfg,
                                reboot_wait_s,
                                f"本轮配网结束，串口重启机器后继续下一轮（等待 {reboot_wait_s}s）",
                            )

            except KeyboardInterrupt:
                interrupted = True
                log("\n⚠️ 用户中断当前设备测试")
                raise
            except Exception as e:
                log(f"❌ 设备 {device_name} 测试异常: {e}")
            finally:
                try:
                    if driver:
                        driver.quit()
                except Exception:
                    pass

    except KeyboardInterrupt:
        interrupted = True
        log("\n⚠️ 用户中断测试，正在生成报告...")
    except Exception as e:
        log(f"\n❌ 测试异常: {e}")
        import traceback

        log(traceback.format_exc())
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

        log(traceback.format_exc())
