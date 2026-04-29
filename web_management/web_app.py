#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
软件自动化测试管理 Web 应用
提供蓝牙配网的 Web 管理界面
"""

import os
import json
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 项目根目录（指向蓝牙配网兼容性目录）
BASE_DIR = Path(__file__).parent.parent / "project" / "P0011-M1PRO" / "配网兼容性" / "2蓝牙配网"
ANDROID_DIR = BASE_DIR / "Android"
IOS_DIR = BASE_DIR / "IOS"
REPORTS_DIR = BASE_DIR / "reports"

# 测试任务状态
test_tasks = {}
task_lock = threading.Lock()

# 机器人设备ID
ROBOT_DEVICE_ID = os.environ.get("ROBOT_DEVICE_ID", "galaxy_p0001")


def load_config(platform="android"):
    """加载设备配置文件（优先从统一配置文件读取，否则从各自目录读取）"""
    # 优先尝试从统一配置文件读取
    unified_config_file = BASE_DIR / "device_config.json"
    
    if unified_config_file.exists():
        try:
            with open(unified_config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 过滤出指定平台的设备
                if platform:
                    filtered_config = config.copy()
                    filtered_config['device_configs'] = {
                        k: v for k, v in config.get('device_configs', {}).items()
                        if v.get('platform', 'android' if platform == 'android' else 'ios') == platform
                    }
                    return filtered_config
                return config
        except Exception as e:
            print(f"加载统一配置文件失败: {e}，尝试从各自目录读取")
    
    # 如果统一配置文件不存在，从各自目录读取（向后兼容）
    config_file = ANDROID_DIR / "device_config.json" if platform == "android" else IOS_DIR / "device_config.json"
    
    if not config_file.exists():
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return None


def get_adb_path():
    """获取 adb 路径"""
    env_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    candidates = []
    if env_home:
        candidates.append(Path(env_home) / "platform-tools" / "adb")
    candidates.extend(
        Path(p) / "platform-tools" / "adb"
        for p in [
            "~/Library/Android/sdk",
            "~/Android/Sdk",
            "/usr/local/share/android-sdk",
            "/opt/android-sdk",
        ]
    )
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.exists():
            return str(candidate)
    return "adb"


@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')


@app.route('/api/config/<platform>')
def get_config(platform):
    """获取配置文件"""
    config = load_config(platform)
    if not config:
        return jsonify({"error": "配置文件不存在"}), 404
    
    # 格式化返回数据
    devices = []
    for key, device in config.get('device_configs', {}).items():
        devices.append({
            "id": key,
            "name": device.get('description', key),
            "port": device.get('port'),
            "device_name": device.get('device_name') or device.get('udid', ''),
            "platform_version": device.get('platform_version', ''),
        })
    
    routers = config.get('wifi_configs', [])
    test_config = config.get('test_config', {})
    
    return jsonify({
        "devices": devices,
        "routers": routers,
        "test_config": test_config,
        "target_device": config.get('target_device', {})
    })


@app.route('/api/appium/start', methods=['POST'])
def start_appium():
    """一键启动 Appium 端口"""
    try:
        data = request.json or {}
        platforms = data.get('platforms', ['android', 'ios'])
        specified_ports = data.get('ports', [])
        
        # 如果指定了端口，使用指定的端口；否则收集所有端口
        if specified_ports:
            ports = [int(p) for p in specified_ports]
        else:
            ports = []
            for platform in platforms:
                config = load_config(platform)
                if config:
                    for device in config.get('device_configs', {}).values():
                        port = device.get('port')
                        if port:
                            ports.append(port)
        
        if not ports:
            return jsonify({"error": "未找到配置的端口"}), 400
        
        # 去重
        ports = sorted(set(ports))
        
        # 设置 Android SDK 环境变量（如果需要）
        env = os.environ.copy()
        
        # 查找 Android SDK
        android_sdk_paths = [
            os.path.expanduser("~/Library/Android/sdk"),
            os.path.expanduser("~/Android/Sdk"),
            "/usr/local/share/android-sdk",
            "/opt/android-sdk"
        ]
        
        android_sdk_path = None
        if env.get('ANDROID_HOME'):
            android_sdk_path = env['ANDROID_HOME']
        elif env.get('ANDROID_SDK_ROOT'):
            android_sdk_path = env['ANDROID_SDK_ROOT']
        else:
            for path in android_sdk_paths:
                if os.path.isdir(path) and os.path.isdir(os.path.join(path, 'platform-tools')):
                    android_sdk_path = path
                    break
        
        if android_sdk_path:
            env['ANDROID_HOME'] = android_sdk_path
            env['ANDROID_SDK_ROOT'] = android_sdk_path
            env['PATH'] = f"{android_sdk_path}/platform-tools:{android_sdk_path}/tools:{env.get('PATH', '')}"
        
        # 直接启动 Appium 服务器
        started = []
        failed = []
        
        for port in ports:
            try:
                # 先停止可能存在的进程
                try:
                    # 使用 lsof 找到占用端口的进程
                    lsof_result = subprocess.run(
                        ['lsof', '-ti', f':{port}'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if lsof_result.returncode == 0 and lsof_result.stdout.strip():
                        pids = lsof_result.stdout.strip().split('\n')
                        for pid in pids:
                            if pid and pid.strip():
                                subprocess.run(['kill', '-9', pid.strip()], 
                                             capture_output=True, timeout=2)
                    time.sleep(0.5)
                except:
                    # 备用方法：使用 pkill
                    subprocess.run(['pkill', '-f', f'appium.*-p\\s+{port}'], 
                                capture_output=True, timeout=2)
                    time.sleep(0.5)
                
                # 启动新的 Appium 服务器
                log_file = f"/tmp/appium_{port}.log"
                # 使用追加模式，保留之前的日志
                log_fd = open(log_file, 'a')
                process = subprocess.Popen(
                    ['appium', '-p', str(port)],
                    stdout=log_fd,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True
                )
                # 不关闭文件，让 Appium 进程继续写入
                # 文件描述符会被子进程继承，即使父进程关闭文件，子进程仍可写入
                
                # 等待一下让进程启动
                time.sleep(2)
                
                # 检查进程是否还在运行
                if process.poll() is None:
                    # 检查端口是否真的启动了
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex(('127.0.0.1', port))
                    sock.close()
                    
                    if result == 0:
                        # 尝试访问 Appium 状态端点
                        try:
                            import urllib.request
                            url = f"http://127.0.0.1:{port}/status"
                            req = urllib.request.Request(url)
                            with urllib.request.urlopen(req, timeout=3) as response:
                                if response.status == 200:
                                    started.append(port)
                                else:
                                    failed.append(port)
                        except:
                            # 端口开放但可能还没完全启动，再等一会儿
                            time.sleep(2)
                            try:
                                import urllib.request
                                url = f"http://127.0.0.1:{port}/status"
                                req = urllib.request.Request(url)
                                with urllib.request.urlopen(req, timeout=3) as response:
                                    if response.status == 200:
                                        started.append(port)
                                    else:
                                        failed.append(port)
                            except:
                                failed.append(port)
                    else:
                        failed.append(port)
                else:
                    failed.append(port)
                    
            except Exception as e:
                print(f"启动端口 {port} 失败: {e}")
                failed.append(port)
        
        if failed:
            return jsonify({
                "success": True,
                "message": f"已启动端口: {', '.join(map(str, started))}，部分端口启动失败: {', '.join(map(str, failed))}",
                "ports": started,
                "failed_ports": failed
            })
        else:
            return jsonify({
                "success": True,
                "message": f"已启动 Appium 端口: {', '.join(map(str, started))}",
                "ports": started
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/appium/stop', methods=['POST'])
def stop_appium():
    """一键停止 Appium 端口"""
    try:
        data = request.json or {}
        specified_ports = data.get('ports', [])
        
        # 如果指定了端口，使用指定的端口；否则收集所有端口
        if specified_ports:
            ports = [int(p) for p in specified_ports]
        else:
            ports = []
            for platform in ['android', 'ios']:
                config = load_config(platform)
                if config:
                    for device in config.get('device_configs', {}).values():
                        port = device.get('port')
                        if port:
                            ports.append(port)
        
        if not ports:
            return jsonify({"error": "未找到配置的端口"}), 400
        
        # 去重
        ports = sorted(set(ports))
        
        # 停止 Appium 进程
        stopped = []
        failed = []
        
        for port in ports:
            try:
                port_stopped = False
                
                # 方法1: 使用 lsof 找到占用端口的进程并杀死（最可靠）
                try:
                    lsof_result = subprocess.run(
                        ['lsof', '-ti', f':{port}'],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    if lsof_result.returncode == 0 and lsof_result.stdout.strip():
                        pids = lsof_result.stdout.strip().split('\n')
                        for pid in pids:
                            if pid and pid.strip():
                                try:
                                    # 先尝试优雅停止
                                    subprocess.run(['kill', pid.strip()], 
                                                 capture_output=True, timeout=2)
                                    time.sleep(0.3)
                                    # 如果还在运行，强制杀死
                                    subprocess.run(['kill', '-9', pid.strip()], 
                                                 capture_output=True, timeout=2)
                                except:
                                    pass
                except Exception as e:
                    print(f"lsof 方法失败 (端口 {port}): {e}")
                
                # 方法2: 使用 pkill 匹配端口（备用方法）
                try:
                    # 尝试多种匹配模式
                    patterns = [
                        f'appium.*-p {port}',
                        f'appium.*--port {port}',
                        f'appium.*port.*{port}'
                    ]
                    for pattern in patterns:
                        subprocess.run(
                            ['pkill', '-f', pattern],
                            capture_output=True,
                            timeout=2
                        )
                except:
                    pass
                
                # 等待一下让进程完全退出
                time.sleep(1)
                
                # 验证端口是否真的关闭了
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                
                if result != 0:  # 端口已关闭
                    stopped.append(port)
                    port_stopped = True
                else:
                    # 端口仍然开放，可能不是 Appium 占用，或者进程还没退出
                    # 再尝试一次强制杀死
                    try:
                        lsof_result = subprocess.run(
                            ['lsof', '-ti', f':{port}'],
                            capture_output=True,
                            text=True,
                            timeout=2
                        )
                        if lsof_result.returncode == 0 and lsof_result.stdout.strip():
                            pids = lsof_result.stdout.strip().split('\n')
                            for pid in pids:
                                if pid and pid.strip():
                                    subprocess.run(['kill', '-9', pid.strip()], 
                                                 capture_output=True, timeout=2)
                            time.sleep(0.5)
                            # 再次验证
                            sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock2.settimeout(1)
                            result2 = sock2.connect_ex(('127.0.0.1', port))
                            sock2.close()
                            if result2 != 0:
                                stopped.append(port)
                                port_stopped = True
                    except:
                        pass
                    
                    if not port_stopped:
                        failed.append(port)
            except Exception as e:
                print(f"停止端口 {port} 失败: {e}")
                failed.append(port)
        
        if failed:
            return jsonify({
                "success": True,
                "message": f"已停止端口: {', '.join(map(str, stopped))}，部分端口停止失败: {', '.join(map(str, failed))}",
                "ports": stopped,
                "failed_ports": failed
            })
        else:
            return jsonify({
                "success": True,
                "message": f"已停止 Appium 端口: {', '.join(map(str, stopped))}",
                "ports": stopped
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/appium/status/<int:port>')
def get_appium_status(port):
    """检查单个 Appium 端口状态"""
    try:
        import socket
        import urllib.request
        
        # 检查端口是否开放
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result == 0:
            # 端口开放，尝试访问 Appium 状态端点
            try:
                url = f"http://127.0.0.1:{port}/status"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        return jsonify({"status": "running"})
            except:
                # 端口开放但 Appium 可能未完全启动
                return jsonify({"status": "starting"})
        
        return jsonify({"status": "stopped"})
        
    except Exception as e:
        return jsonify({"status": "stopped", "error": str(e)})


@app.route('/api/appium/log/<int:port>')
def get_appium_log(port):
    """获取指定端口的 Appium 日志内容（尾部若干行）"""
    try:
        log_file = Path(f"/tmp/appium_{port}.log")
        if not log_file.exists():
            return jsonify({"content": ""})

        # 读取文件尾部内容，避免一次性读太大
        max_bytes = 50_000  # 大约几百行
        with open(log_file, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size > max_bytes:
                f.seek(-max_bytes, os.SEEK_END)
            else:
                f.seek(0)
            data = f.read().decode('utf-8', errors='ignore')

        return jsonify({"content": data})
    except Exception as e:
        return jsonify({"content": "", "error": str(e)}), 500


@app.route('/api/test/start', methods=['POST'])
def start_test():
    """启动测试任务"""
    try:
        data = request.json
        selected_devices = data.get('devices', [])
        selected_routers = data.get('routers', [])
        test_count = data.get('test_count', 3)
        platforms = data.get('platforms', ['android'])
        clear_logs = data.get('clear_logs', True)
        
        if not selected_devices or not selected_routers:
            return jsonify({"error": "请选择设备和路由器"}), 400
        
        # 生成任务ID
        task_id = f"task_{int(time.time())}"
        
        # 创建任务目录
        task_dir = REPORTS_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存任务配置
        task_config = {
            "task_id": task_id,
            "devices": selected_devices,
            "devices_by_platform": data.get('devices_by_platform', {}),
            "routers": selected_routers,
            "test_count": test_count,
            "platforms": platforms,
            "start_time": datetime.now().isoformat(),
            "status": "running",
            "task_dir": str(task_dir)
        }
        
        with task_lock:
            test_tasks[task_id] = task_config
        
        # 在后台线程中执行测试
        thread = threading.Thread(
            target=run_test_task,
            args=(task_id, task_config, clear_logs),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "success": True,
            "task_id": task_id,
            "message": "测试任务已启动"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_test_task(task_id, task_config, clear_logs):
    """执行测试任务"""
    try:
        task_dir = Path(task_config['task_dir'])
        log_file = task_dir / "test.log"
        
        # 更新任务状态为运行中
        with task_lock:
            if task_id in test_tasks:
                test_tasks[task_id]['status'] = 'running'
        
        # 1. 清除机器人日志
        if clear_logs:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now()}] 开始清除机器人日志...\n")
                f.flush()
            
            clear_cmd = [
                'python3',
                str(BASE_DIR / 'clear_robot_logs.py'),
                '--device', ROBOT_DEVICE_ID,
                '--quiet'
            ]
            subprocess.run(clear_cmd, stdout=open(log_file, 'a'), stderr=subprocess.STDOUT)
        
        # 2. 执行测试脚本
        for platform in task_config['platforms']:
            script_dir = ANDROID_DIR if platform == 'android' else IOS_DIR
            script_name = "Android-IOS.py" if platform == 'android' else "IOS-IOS.py"
            script_path = script_dir / script_name
            
            if script_path.exists():
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now()}] 开始执行 {platform} 测试...\n")
                    f.flush()
                
                # 创建临时配置文件，只包含选中的设备和路由器
                temp_config_file = task_dir / f"device_config_{platform}.json"
                create_temp_config(temp_config_file, task_config, platform)
                
                # 设置环境变量，让脚本使用临时配置文件
                env = os.environ.copy()
                env['DEVICE_CONFIG_FILE'] = str(temp_config_file)
                
                # 运行测试脚本
                result = subprocess.run(
                    ['python3', str(script_path)],
                    cwd=str(script_dir),
                    stdout=open(log_file, 'a'),
                    stderr=subprocess.STDOUT,
                    env=env,
                    timeout=3600  # 1小时超时
                )
                
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now()}] {platform} 测试完成，退出码: {result.returncode}\n")
                    f.flush()
        
        # 3. 打包机器人日志
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] 开始打包机器人日志...\n")
        
        pack_cmd = [
            'python3',
            str(BASE_DIR / 'pack_robot_logs.py'),
            '--device', ROBOT_DEVICE_ID,
            '--dest', str(task_dir),
            '--quiet'
        ]
        subprocess.run(pack_cmd, stdout=open(log_file, 'a'), stderr=subprocess.STDOUT)
        
        # 4. 收集测试报告和日志
        collect_reports(task_dir, task_config['platforms'])
        
        # 更新任务状态
        with task_lock:
            if task_id in test_tasks:
                test_tasks[task_id]['status'] = 'completed'
                test_tasks[task_id]['end_time'] = datetime.now().isoformat()
        
    except Exception as e:
        with task_lock:
            if task_id in test_tasks:
                test_tasks[task_id]['status'] = 'failed'
                test_tasks[task_id]['error'] = str(e)
                test_tasks[task_id]['end_time'] = datetime.now().isoformat()


def create_temp_config(temp_config_file, task_config, platform):
    """创建临时配置文件，只包含选中的设备和路由器"""
    try:
        # 加载原始配置
        original_config = load_config(platform)
        if not original_config:
            raise ValueError(f"无法加载 {platform} 配置")
        
        # 创建新的配置
        new_config = {
            'device_configs': {},
            'wifi_configs': task_config.get('routers', []),
            'target_device': original_config.get('target_device', {}),
            'test_config': {
                'loop_count_per_router': task_config.get('test_count', 3),
                'timeout_seconds': original_config.get('test_config', {}).get('timeout_seconds', 180),
                'success_rate_threshold': original_config.get('test_config', {}).get('success_rate_threshold', 0.8)
            }
        }
        
        # 只包含选中的设备
        devices_by_platform = task_config.get('devices_by_platform', {})
        selected_devices = devices_by_platform.get(platform, [])
        
        original_device_configs = original_config.get('device_configs', {})
        for device_id in selected_devices:
            if device_id in original_device_configs:
                new_config['device_configs'][device_id] = original_device_configs[device_id]
        
        # 保存临时配置文件
        with open(temp_config_file, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"创建临时配置文件失败: {e}")
        return False


def collect_reports(task_dir, platforms):
    """收集测试报告和日志到任务目录"""
    for platform in platforms:
        platform_dir = ANDROID_DIR if platform == 'android' else IOS_DIR
        
        # 复制报告
        reports_dir = platform_dir / "reports"
        if reports_dir.exists():
            for report_file in reports_dir.glob("*.xlsx"):
                # 只复制最新的报告
                if report_file.stat().st_mtime > (time.time() - 3600):  # 1小时内
                    import shutil
                    shutil.copy2(report_file, task_dir / report_file.name)
        
        # 复制日志
        log_file = platform_dir / f"{platform}_bluetooth_pairing.log"
        if log_file.exists():
            import shutil
            shutil.copy2(log_file, task_dir / f"{platform}_bluetooth_pairing.log")


@app.route('/api/test/stop/<task_id>', methods=['POST'])
def stop_test(task_id):
    """停止测试任务"""
    try:
        with task_lock:
            if task_id not in test_tasks:
                return jsonify({"error": "任务不存在"}), 404
            
            task = test_tasks[task_id]
            if task['status'] != 'running':
                return jsonify({"error": "任务未在运行"}), 400
            
            # 发送停止信号
            # 这里需要实现停止逻辑
            task['status'] = 'stopped'
            task['end_time'] = datetime.now().isoformat()
        
        return jsonify({
            "success": True,
            "message": "测试任务已停止"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/test/status/<task_id>')
def get_test_status(task_id):
    """获取测试任务状态"""
    with task_lock:
        if task_id not in test_tasks:
            return jsonify({"error": "任务不存在"}), 404
        
        task = test_tasks[task_id].copy()
        
        # 读取日志文件大小
        task_dir = Path(task.get('task_dir', ''))
        if task_dir.exists():
            log_file = task_dir / "test.log"
            if log_file.exists():
                task['log_size'] = log_file.stat().st_size
        
        return jsonify(task)


@app.route('/api/test/log/<task_id>')
def get_test_log(task_id):
    """获取测试日志（流式输出）"""
    task_dir = REPORTS_DIR / task_id
    log_file = task_dir / "test.log"
    
    if not log_file.exists():
        return jsonify({"error": "日志文件不存在"}), 404
    
    def generate():
        with open(log_file, 'r', encoding='utf-8') as f:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                yield line
    
    return Response(generate(), mimetype='text/plain')


@app.route('/api/test/list')
def list_tests():
    """列出所有测试任务"""
    with task_lock:
        tasks = list(test_tasks.values())
        # 按开始时间倒序排列
        tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        return jsonify({"tasks": tasks})


@app.route('/api/test/download/<task_id>')
def download_test(task_id):
    """下载测试结果（打包为zip）"""
    task_dir = REPORTS_DIR / task_id
    
    if not task_dir.exists():
        return jsonify({"error": "任务目录不存在"}), 404
    
    # 创建zip文件
    import zipfile
    import tempfile
    
    zip_path = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    zip_path.close()
    
    with zipfile.ZipFile(zip_path.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in task_dir.rglob('*'):
            if file_path.is_file():
                zipf.write(file_path, file_path.relative_to(task_dir))
    
    return send_file(
        zip_path.name,
        as_attachment=True,
        download_name=f"test_results_{task_id}.zip",
        mimetype='application/zip'
    )


# 功能测试相关API
PROJECT_BASE_DIR = Path(__file__).parent.parent / "project"


def parse_testcase_file(test_file):
    """解析测试用例文件，提取操作步骤和期望结果"""
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        steps = ""
        expected = ""
        
        # 查找test函数的定义，然后提取它的docstring
        # 匹配 def test_xxx(...): 后面的docstring（支持三引号）
        # 先尝试匹配三双引号
        test_function_pattern_double = r'def\s+test_\d+[^:]*:\s*\n\s*"""(.*?)"""'
        match = re.search(test_function_pattern_double, content, re.DOTALL)
        if not match:
            # 如果没找到，尝试三单引号
            test_function_pattern_single = r"def\s+test_\d+[^:]*:\s*\n\s*'''(.*?)'''"
            match = re.search(test_function_pattern_single, content, re.DOTALL)
        
        docstring = None
        if match:
            docstring = match.group(1).strip()
        
        if docstring:
            lines = docstring.split('\n')
            # 过滤掉空行和只包含空白的行，但保留原始格式
            processed_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped:
                    processed_lines.append(line)  # 保留原始缩进
            
            # 跳过第一行（通常是用例ID和名称）
            if processed_lines:
                processed_lines = processed_lines[1:]
            
            # 查找"期望结果"或"预期结果"分隔符
            expected_start = -1
            for i, line in enumerate(processed_lines):
                stripped = line.strip()
                if '期望结果' in stripped or '预期结果' in stripped or 'Expected' in stripped:
                    expected_start = i
                    break
            
            if expected_start > 0:
                # 操作步骤是期望结果之前的所有行
                steps_lines = processed_lines[:expected_start]
                # 期望结果是期望结果之后的所有行
                expected_lines = processed_lines[expected_start + 1:]
            else:
                # 没有明确分隔符，全部作为操作步骤
                steps_lines = processed_lines
                expected_lines = []
            
            # 格式化操作步骤（保留编号列表格式和缩进）
            if steps_lines:
                steps = '\n'.join(steps_lines)
                # 清理多余的空白行
                steps = re.sub(r'\n{3,}', '\n\n', steps)
            
            # 格式化期望结果
            if expected_lines:
                expected = '\n'.join(expected_lines)
                expected = re.sub(r'\n{3,}', '\n\n', expected)
        
        return steps, expected
    except Exception as e:
        print(f"解析测试用例文件失败 {test_file}: {e}")
        return "", ""


@app.route('/api/functional/projects')
def get_functional_projects():
    """获取功能测试项目列表（只返回APP(new)项目）"""
    try:
        projects = []
        if PROJECT_BASE_DIR.exists():
            # 只返回APP(new)项目
            app_dir = PROJECT_BASE_DIR / "APP(new)"
            if app_dir.exists() and app_dir.is_dir():
                # 检查是否有平台目录
                platform_dir = app_dir / "平台"
                if platform_dir.exists():
                    projects.append({
                        "id": "APP(new)",
                        "name": "APP(new)"
                    })
        return jsonify({"projects": projects})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/functional/modules/<project_id>')
def get_functional_modules(project_id):
    """获取指定项目的功能模块列表（区分平台）"""
    try:
        project_dir = PROJECT_BASE_DIR / project_id
        if not project_dir.exists():
            return jsonify({"error": "项目不存在"}), 404
        
        modules = {
            "android": [],
            "ios": []
        }
        
        # 处理APP(new)项目结构：项目/平台/Android或IOS/模块/
        platform_dir = project_dir / "平台"
        if platform_dir.exists():
            android_dir = platform_dir / "Android"
            ios_dir = platform_dir / "IOS"
            
            if android_dir.exists():
                for item in android_dir.iterdir():
                    if item.is_dir() and not item.name.startswith('_'):
                        modules["android"].append({
                            "id": item.name,
                            "name": item.name,
                            "path": str(item.relative_to(PROJECT_BASE_DIR))
                        })
            
            if ios_dir.exists():
                for item in ios_dir.iterdir():
                    if item.is_dir() and not item.name.startswith('_'):
                        modules["ios"].append({
                            "id": item.name,
                            "name": item.name,
                            "path": str(item.relative_to(PROJECT_BASE_DIR))
                        })
        
        # 处理P0011项目结构：项目/功能测试用例/android或ios/模块.py
        functional_dir = project_dir / "功能测试用例"
        if functional_dir.exists():
            android_dir = functional_dir / "android"
            ios_dir = functional_dir / "ios"
            
            if android_dir.exists():
                for item in android_dir.iterdir():
                    if item.is_file() and item.suffix == '.py' and not item.name.startswith('_'):
                        module_name = item.stem
                        modules["android"].append({
                            "id": module_name,
                            "name": module_name,
                            "path": str(item.relative_to(PROJECT_BASE_DIR))
                        })
            
            if ios_dir.exists():
                for item in ios_dir.iterdir():
                    if item.is_file() and item.suffix == '.py' and not item.name.startswith('_'):
                        module_name = item.stem
                        modules["ios"].append({
                            "id": module_name,
                            "name": module_name,
                            "path": str(item.relative_to(PROJECT_BASE_DIR))
                        })
        
        # 处理P0007项目结构：项目/设备/testcases/模块/
        for device_dir in project_dir.iterdir():
            if device_dir.is_dir() and device_dir.name.startswith('test_'):
                testcases_dir = device_dir / "testcases"
                if testcases_dir.exists():
                    for module_dir in testcases_dir.iterdir():
                        if module_dir.is_dir() and not module_dir.name.startswith('_'):
                            # 根据设备名称判断平台
                            device_name = device_dir.name.lower()
                            platform = "ios" if "iphone" in device_name else "android"
                            
                            modules[platform].append({
                                "id": f"{device_dir.name}_{module_dir.name}",
                                "name": f"{device_dir.name}/{module_dir.name}",
                                "path": str(module_dir.relative_to(PROJECT_BASE_DIR))
                            })
        
        return jsonify({"modules": modules})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/functional/devices/<platform>')
def get_functional_devices(platform):
    """获取指定平台的设备型号列表（只返回指定设备）"""
    try:
        devices = []
        
        # 从蓝牙配网配置中获取设备列表
        config = load_config(platform)
        if config:
            # 定义允许的设备ID
            allowed_devices = {
                'android': ['galaxy_s24_ultra'],
                'ios': ['iPhone 16 pro max']
            }
            
            allowed_ids = allowed_devices.get(platform, [])
            
            for key, device in config.get('device_configs', {}).items():
                device_platform = device.get('platform', 'android' if platform == 'android' else 'ios')
                # 只返回指定平台的设备，且设备ID在允许列表中
                if device_platform == platform and key in allowed_ids:
                    # 格式化设备名称
                    device_name = device.get('description', key)
                    if platform == 'android' and key == 'galaxy_s24_ultra':
                        device_name = 'Galaxy S24 Ultra'
                    elif platform == 'ios' and key == 'iPhone 16 pro max':
                        device_name = 'iPhone 16 pro max'
                    
                    devices.append({
                        "id": key,
                        "name": device_name,
                        "device_name": device.get('device_name') or device.get('udid', ''),
                        "platform_version": device.get('platform_version', ''),
                    })
        
        return jsonify({"devices": devices})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/functional/testcases/<project_id>')
def get_functional_testcases(project_id):
    """获取指定项目的测试用例列表（按模块分组）"""
    try:
        import re
        # re模块已在函数内导入，parse_testcase_file函数中也会使用
        project_dir = PROJECT_BASE_DIR / project_id
        if not project_dir.exists():
            return jsonify({"error": "项目不存在"}), 404
        
        modules = {}
        total_count = 0
        
        # 处理APP(new)项目结构：项目/平台/Android或IOS/模块/测试用例.py
        platform_dir = project_dir / "平台"
        if platform_dir.exists():
            android_dir = platform_dir / "Android"
            ios_dir = platform_dir / "IOS"
            
            for platform_name, platform_path in [("android", android_dir), ("ios", ios_dir)]:
                if platform_path.exists():
                    for module_dir in platform_path.iterdir():
                        if module_dir.is_dir() and not module_dir.name.startswith('_'):
                            module_name = module_dir.name
                            if module_name not in modules:
                                modules[module_name] = {"android": [], "ios": []}
                            
                            # 扫描测试用例文件
                            for test_file in module_dir.glob("*.py"):
                                if test_file.name.startswith('_') or test_file.name == 'conftest.py':
                                    continue
                                
                                # 从文件名提取ID和用例名称
                                # 格式：102025验证注册时邮箱显示包含不支持的特殊字符.py
                                match = re.match(r'^(\d+)(.*)\.py$', test_file.name)
                                if match:
                                    case_id = match.group(1)
                                    case_name = match.group(2) or test_file.stem
                                    
                                    # 解析脚本文件，提取操作步骤和期望结果
                                    steps, expected = parse_testcase_file(test_file)
                                    
                                    modules[module_name][platform_name].append({
                                        "id": case_id,
                                        "name": case_name,
                                        "file": test_file.name,
                                        "path": str(test_file.relative_to(PROJECT_BASE_DIR)),
                                        "steps": steps,
                                        "expected": expected
                                    })
                                    total_count += 1
        
        # 处理P0007项目结构：项目/设备/testcases/模块/测试用例.py
        for device_dir in project_dir.iterdir():
            if device_dir.is_dir() and device_dir.name.startswith('test_'):
                testcases_dir = device_dir / "testcases"
                if testcases_dir.exists():
                    for module_dir in testcases_dir.iterdir():
                        if module_dir.is_dir() and not module_dir.name.startswith('_'):
                            module_name = module_dir.name
                            device_name = device_dir.name.lower()
                            platform = "ios" if "iphone" in device_name else "android"
                            
                            if module_name not in modules:
                                modules[module_name] = {"android": [], "ios": []}
                            
                            # 扫描测试用例文件
                            for test_file in module_dir.glob("*.py"):
                                if test_file.name.startswith('_') or test_file.name == 'conftest.py':
                                    continue
                                
                                # 从文件名提取ID和用例名称
                                # 格式：test_100001.py 或 1登录.py
                                file_stem = test_file.stem
                                if file_stem.startswith('test_'):
                                    case_id = file_stem.replace('test_', '')
                                    case_name = file_stem
                                else:
                                    case_id = file_stem
                                    case_name = file_stem
                                
                                # 解析脚本文件，提取操作步骤和期望结果
                                steps, expected = parse_testcase_file(test_file)
                                
                                modules[module_name][platform].append({
                                    "id": case_id,
                                    "name": case_name,
                                    "file": test_file.name,
                                    "path": str(test_file.relative_to(PROJECT_BASE_DIR)),
                                    "steps": steps,
                                    "expected": expected
                                })
                                total_count += 1
        
        return jsonify({
            "modules": modules,
            "total_count": total_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 功能测试任务管理
functional_test_tasks = {}
functional_test_lock = threading.Lock()


@app.route('/api/functional/test/start', methods=['POST'])
def start_functional_test():
    """启动功能测试任务"""
    try:
        data = request.json
        project_id = data.get('project')
        android_device = data.get('android_device')
        ios_device = data.get('ios_device')
        testcase_ids = data.get('modules', [])  # 格式: [{"id": "102205", "module": "2注册"}, ...]
        firmware = data.get('firmware', '')
        shell = data.get('shell', '')
        plugin = data.get('plugin', '')
        
        if not project_id:
            return jsonify({"error": "请选择项目"}), 400
        
        if not android_device and not ios_device:
            return jsonify({"error": "请至少选择一个设备"}), 400
        
        if not testcase_ids:
            return jsonify({"error": "请至少选择一个测试用例"}), 400
        
        # 生成任务ID
        task_id = f"functional_{int(time.time())}"
        
        # 创建任务配置
        task_config = {
            "task_id": task_id,
            "project_id": project_id,
            "android_device": android_device,
            "ios_device": ios_device,
            "testcase_ids": testcase_ids,
            "firmware": firmware,
            "shell": shell,
            "plugin": plugin,
            "start_time": datetime.now().isoformat(),
            "status": "running"
        }
        
        with functional_test_lock:
            functional_test_tasks[task_id] = task_config
        
        # 在后台线程中执行测试
        thread = threading.Thread(
            target=run_functional_test_task,
            args=(task_id, task_config),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "success": True,
            "task_id": task_id,
            "message": "功能测试任务已启动"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_functional_test_task(task_id, task_config):
    """执行功能测试任务"""
    try:
        project_id = task_config['project_id']
        project_dir = PROJECT_BASE_DIR / project_id
        
        # 收集要执行的测试文件路径
        test_files = []
        print(f"开始查找测试文件，用例数量: {len(task_config['testcase_ids'])}")
        
        for testcase_info in task_config['testcase_ids']:
            case_id = testcase_info.get('id')
            module_name = testcase_info.get('module', '').strip()
            
            if not case_id:
                print(f"跳过无效用例: {testcase_info}")
                continue
            
            print(f"查找用例: ID={case_id}, 模块='{module_name}' (长度: {len(module_name)})")
            
            # 如果模块名为空，尝试从所有模块中查找
            if not module_name:
                print(f"警告: 用例 {case_id} 的模块名为空，将在所有模块中查找")
            
            # 查找测试文件
            platform_dir = project_dir / "平台"
            if not platform_dir.exists():
                print(f"平台目录不存在: {platform_dir}")
                continue
            
            # 根据选择的设备确定平台
            selected_platform = None
            if task_config.get('ios_device'):
                selected_platform = 'IOS'
            elif task_config.get('android_device'):
                selected_platform = 'Android'
            
            print(f"选择的平台: {selected_platform}")
            
            # 如果确定了平台，只查找该平台的测试文件
            platforms_to_check = [selected_platform] if selected_platform else ['Android', 'IOS']
            
            found_file = False
            for platform_name in platforms_to_check:
                if not platform_name:
                    continue
                platform_path = platform_dir / platform_name
                if not platform_path.exists():
                    print(f"平台路径不存在: {platform_path}")
                    continue
                
                # 如果模块名为空，在所有模块目录中查找
                if not module_name:
                    print(f"模块名为空，在所有模块中查找用例 {case_id}")
                    # 遍历所有模块目录
                    for module_dir in platform_path.iterdir():
                        if module_dir.is_dir() and not module_dir.name.startswith('_'):
                            pattern = f"{case_id}*.py"
                            matching_files = list(module_dir.glob(pattern))
                            for test_file in matching_files:
                                if not test_file.name.startswith('_'):
                                    test_files.append(str(test_file.absolute()))
                                    print(f"添加测试文件: {test_file.absolute()}")
                                    found_file = True
                                    break
                            if found_file:
                                break
                else:
                    # 在指定模块目录中查找
                    module_path = platform_path / module_name
                    if not module_path.exists():
                        print(f"模块路径不存在: {module_path}")
                        continue
                    
                    # 查找匹配的测试文件
                    pattern = f"{case_id}*.py"
                    print(f"在 {module_path} 中查找模式: {pattern}")
                    matching_files = list(module_path.glob(pattern))
                    print(f"找到 {len(matching_files)} 个匹配文件")
                    
                    for test_file in matching_files:
                        if not test_file.name.startswith('_'):
                            test_files.append(str(test_file.absolute()))
                            print(f"添加测试文件: {test_file.absolute()}")
                            found_file = True
                            break
                
                if found_file:
                    break
            
            if not found_file:
                print(f"警告: 未找到用例 {case_id} 的测试文件 (模块: {module_name}, 平台: {selected_platform})")
        
        print(f"总共找到 {len(test_files)} 个测试文件")
        
        if not test_files:
            with functional_test_lock:
                if task_id in functional_test_tasks:
                    functional_test_tasks[task_id]['status'] = 'failed'
                    functional_test_tasks[task_id]['error'] = '未找到测试文件'
            return
        
        # 确定使用的设备和端口
        device_port = None
        platform = None
        
        if task_config.get('ios_device'):
            # 从设备ID获取端口（从managedPorts映射）
            device_id = task_config['ios_device']
            # 查找对应的端口
            device_port_map = {
                'iphone_15': 4735,
                'iphone_16_pro_max': 4736,
                'iphone_13_mini': 4737
            }
            device_port = device_port_map.get(device_id, 4736)
            platform = 'ios'
        elif task_config.get('android_device'):
            device_id = task_config['android_device']
            device_port_map = {
                'google_pixel_9_pro': 4725,
                'galaxy_s24_ultra': 4726,
                'galaxy_s10': 4727,
                'google_pixel_7_pro': 4728,
                'one_plus_11': 4729
            }
            device_port = device_port_map.get(device_id, 4725)
            platform = 'android'
        
        if not device_port:
            with functional_test_lock:
                if task_id in functional_test_tasks:
                    functional_test_tasks[task_id]['status'] = 'failed'
                    functional_test_tasks[task_id]['error'] = '无法确定设备端口'
            return
        
        # 构建pytest命令
        # 使用项目根目录作为工作目录（PROJECT_BASE_DIR的父目录，即iot目录）
        project_path = str(PROJECT_BASE_DIR.parent)
        
        # 将测试文件路径转换为相对于工作目录（iot目录）的路径
        # 因为工作目录是 iot，而文件在 project/APP(new)/...，所以需要加上 project/ 前缀
        relative_test_files = []
        for test_file in test_files:
            # test_file 是绝对路径，需要转换为相对于工作目录（iot）的路径
            test_path = Path(test_file)
            if test_path.is_absolute():
                try:
                    # 先转换为相对于PROJECT_BASE_DIR（project目录）的路径
                    relative_to_project = test_path.relative_to(PROJECT_BASE_DIR)
                    # 然后加上 project/ 前缀，因为工作目录是 iot
                    relative_path = Path('project') / relative_to_project
                    relative_path_str = str(relative_path)
                    relative_test_files.append(relative_path_str)
                    print(f"路径转换: {test_file} -> {relative_path_str}")
                except ValueError as e:
                    print(f"路径转换失败: {test_file}, 错误: {e}")
                    # 如果无法转换为相对路径，尝试直接相对于project_path
                    try:
                        relative_path = test_path.relative_to(project_path)
                        # 确保路径包含 project/ 前缀
                        if not str(relative_path).startswith('project/'):
                            relative_path = Path('project') / relative_path
                        relative_test_files.append(str(relative_path))
                        print(f"使用备用路径转换: {test_file} -> {relative_path}")
                    except ValueError:
                        # 如果还是无法转换，尝试从绝对路径中提取
                        if 'project/' in str(test_file):
                            # 从绝对路径中提取 project/ 之后的部分
                            parts = Path(test_file).parts
                            try:
                                project_idx = parts.index('project')
                                relative_path = Path('project') / Path(*parts[project_idx+1:])
                                relative_test_files.append(str(relative_path))
                                print(f"从绝对路径提取: {test_file} -> {relative_path}")
                            except ValueError:
                                relative_test_files.append(test_file)
                                print(f"使用绝对路径: {test_file}")
                        else:
                            relative_test_files.append(test_file)
                            print(f"使用绝对路径: {test_file}")
            else:
                # 如果已经是相对路径，检查是否需要添加 project/ 前缀
                if not str(test_file).startswith('project/'):
                    relative_test_files.append(f'project/{test_file}')
                else:
                    relative_test_files.append(test_file)
        
        # 确保所有路径都有 project/ 前缀
        final_test_files = []
        for test_file in relative_test_files:
            if not str(test_file).startswith('project/'):
                final_test_file = f'project/{test_file}'
                print(f"添加project前缀: {test_file} -> {final_test_file}")
                final_test_files.append(final_test_file)
            else:
                final_test_files.append(test_file)
        relative_test_files = final_test_files
        
        # 构建pytest命令，指定要运行的测试文件
        # 使用系统python3而不是虚拟环境的python3（因为pytest可能安装在系统环境中）
        import shutil
        python3_path = shutil.which('python3') or '/usr/bin/python3'
        pytest_cmd = [python3_path, '-m', 'pytest']
        print(f"使用Python路径: {python3_path}")
        pytest_cmd.extend(relative_test_files)
        pytest_cmd.extend(['-v', '--tb=short', '-s'])  # -s 显示print输出
        
        # 设置Appium服务器地址（通过环境变量）
        env = os.environ.copy()
        env['APPIUM_PORT'] = str(device_port)
        # 设置Appium服务器URL
        env['APPIUM_URL'] = f'http://127.0.0.1:{device_port}'
        
        # 执行pytest
        print(f"执行pytest命令: {' '.join(pytest_cmd)}")
        print(f"工作目录: {project_path}")
        print(f"Appium端口: {device_port}")
        print(f"测试文件数量: {len(relative_test_files)}")
        print(f"测试文件列表: {relative_test_files}")
        
        # 检查测试文件是否存在
        for test_file in relative_test_files:
            test_path = Path(project_path) / test_file
            print(f"检查文件: {test_file} -> {test_path} (存在: {test_path.exists()})")
            if not test_path.exists():
                error_msg = f"测试文件不存在: {test_file} (完整路径: {test_path})"
                print(error_msg)
                # 尝试查找实际文件位置
                actual_path = PROJECT_BASE_DIR / test_file.replace('project/', '') if test_file.startswith('project/') else PROJECT_BASE_DIR / test_file
                if actual_path.exists():
                    print(f"实际文件位置: {actual_path}")
                    # 更新路径
                    relative_test_files = [str(actual_path.relative_to(project_path)) if f == test_file else f for f in relative_test_files]
                    print(f"更新后的路径: {relative_test_files[relative_test_files.index(test_file) if test_file in relative_test_files else 0]}")
                else:
                    with functional_test_lock:
                        if task_id in functional_test_tasks:
                            functional_test_tasks[task_id]['status'] = 'failed'
                            functional_test_tasks[task_id]['error'] = error_msg
                            functional_test_tasks[task_id]['end_time'] = datetime.now().isoformat()
                    return
        
        process = subprocess.Popen(
            pytest_cmd,
            cwd=project_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # 等待测试完成
        stdout, _ = process.communicate()
        
        print(f"pytest执行完成，返回码: {process.returncode}")
        print(f"输出长度: {len(stdout)} 字符")
        if stdout:
            print(f"输出前500字符: {stdout[:500]}")
        
        # 更新任务状态
        with functional_test_lock:
            if task_id in functional_test_tasks:
                if process.returncode == 0:
                    functional_test_tasks[task_id]['status'] = 'completed'
                else:
                    functional_test_tasks[task_id]['status'] = 'failed'
                    # 如果输出为空，添加错误信息
                    if not stdout or len(stdout.strip()) == 0:
                        functional_test_tasks[task_id]['error'] = f'pytest执行失败，返回码: {process.returncode}，但无输出信息'
                functional_test_tasks[task_id]['end_time'] = datetime.now().isoformat()
                functional_test_tasks[task_id]['output'] = stdout
                functional_test_tasks[task_id]['returncode'] = process.returncode
        
    except Exception as e:
        with functional_test_lock:
            if task_id in functional_test_tasks:
                functional_test_tasks[task_id]['status'] = 'failed'
                functional_test_tasks[task_id]['error'] = str(e)


@app.route('/api/functional/test/status/<task_id>')
def get_functional_test_status(task_id):
    """获取功能测试任务状态"""
    try:
        with functional_test_lock:
            task = functional_test_tasks.get(task_id)
            if not task:
                return jsonify({"error": "任务不存在"}), 404
            return jsonify(task)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/functional/test/stop/<task_id>', methods=['POST'])
def stop_functional_test(task_id):
    """停止功能测试任务"""
    try:
        with functional_test_lock:
            if task_id in functional_test_tasks:
                functional_test_tasks[task_id]['status'] = 'stopped'
                return jsonify({"success": True, "message": "测试任务已停止"})
            return jsonify({"error": "任务不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/list')
def list_all_tasks():
    """获取所有任务列表（功能测试 + 性能测试）"""
    try:
        all_tasks = []
        
        # 获取功能测试任务
        with functional_test_lock:
            for task_id, task in functional_test_tasks.items():
                all_tasks.append({
                    "task_id": task_id,
                    "type": "功能测试",
                    "project_id": task.get('project_id', ''),
                    "status": task.get('status', 'unknown'),
                    "start_time": task.get('start_time', ''),
                    "end_time": task.get('end_time', ''),
                    "android_device": task.get('android_device', ''),
                    "ios_device": task.get('ios_device', ''),
                    "testcase_count": len(task.get('testcase_ids', [])),
                    "error": task.get('error', '')
                })
        
        # 获取性能测试任务
        with task_lock:
            for task_id, task in test_tasks.items():
                all_tasks.append({
                    "task_id": task_id,
                    "type": "性能测试",
                    "platforms": task.get('platforms', []),
                    "devices": task.get('devices', []),
                    "status": task.get('status', 'unknown'),
                    "start_time": task.get('start_time', ''),
                    "end_time": task.get('end_time', ''),
                    "error": task.get('error', '')
                })
        
        # 按开始时间倒序排列
        all_tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        
        return jsonify({"tasks": all_tasks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/functional/test/reports')
def get_functional_test_reports():
    """获取功能测试报告列表"""
    try:
        reports = []
        
        with functional_test_lock:
            for task_id, task in functional_test_tasks.items():
                if task.get('status') in ['completed', 'failed']:
                    reports.append({
                        "task_id": task_id,
                        "type": "功能测试",
                        "project_id": task.get('project_id', ''),
                        "status": task.get('status', ''),
                        "start_time": task.get('start_time', ''),
                        "end_time": task.get('end_time', ''),
                        "android_device": task.get('android_device', ''),
                        "ios_device": task.get('ios_device', ''),
                        "testcase_count": len(task.get('testcase_ids', [])),
                        "output": task.get('output', '')[:500] if task.get('output') else ''  # 只返回前500字符
                    })
        
        # 按结束时间倒序排列
        reports.sort(key=lambda x: x.get('end_time', ''), reverse=True)
        
        return jsonify({"reports": reports})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # 确保 reports 目录存在
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    host = os.environ.get('WEB_APP_HOST', '0.0.0.0')
    port = int(os.environ.get('WEB_APP_PORT', '5000'))
    debug_env = os.environ.get('WEB_APP_DEBUG', 'true').lower()
    debug = debug_env in ('1', 'true', 'yes', 'on')
    
    app.run(host=host, port=port, debug=debug)

