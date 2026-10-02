#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口命令发送脚本
用于通过串口发送命令触发机器人热点

使用方法：
    python3 端口命令.py
    python3 端口命令.py --port /dev/tty.usbserial-1110 --baud 115200 --command "SET state 4"
"""

import serial
import time
import sys
import argparse
import os
import subprocess
import platform


def _find_processes_using_port(port):
    """查找占用串口的进程"""
    processes = []
    try:
        # macOS 使用 lsof
        if platform.system() == 'Darwin':
            result = subprocess.run(
                ['lsof', port],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # 跳过标题行
                    parts = line.split()
                    if len(parts) >= 2:
                        pid = parts[1]
                        # lsof 输出格式: COMMAND PID USER ... NAME
                        # 命令是第一部分，NAME 是最后一部分
                        cmd = parts[0]  # COMMAND 列
                        processes.append({'pid': pid, 'cmd': cmd})
        # Linux 使用 fuser 或 lsof
        elif platform.system() == 'Linux':
            # 尝试使用 fuser
            try:
                result = subprocess.run(
                    ['fuser', port],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    pids = result.stderr.strip().split()
                    for pid in pids:
                        if pid.isdigit():
                            # 获取进程命令
                            try:
                                cmd_result = subprocess.run(
                                    ['ps', '-p', pid, '-o', 'cmd='],
                                    capture_output=True,
                                    text=True,
                                    timeout=2
                                )
                                cmd = cmd_result.stdout.strip() if cmd_result.returncode == 0 else 'unknown'
                                processes.append({'pid': pid, 'cmd': cmd})
                            except:
                                processes.append({'pid': pid, 'cmd': 'unknown'})
            except FileNotFoundError:
                # 如果没有 fuser，尝试 lsof
                try:
                    result = subprocess.run(
                        ['lsof', port],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        lines = result.stdout.strip().split('\n')
                        for line in lines[1:]:
                            parts = line.split()
                            if len(parts) >= 2:
                                pid = parts[1]
                                # lsof 输出格式: COMMAND PID USER ... NAME
                                cmd = parts[0]  # COMMAND 列
                                processes.append({'pid': pid, 'cmd': cmd})
                except:
                    pass
    except Exception as e:
        pass  # 忽略错误，继续执行
    return processes


def _kill_processes_using_port(port):
    """尝试关闭占用串口的进程"""
    processes = _find_processes_using_port(port)
    if not processes:
        return False
    
    killed_count = 0
    for proc in processes:
        pid = proc['pid']
        cmd = proc.get('cmd', 'unknown')
        try:
            print(f"🔧 尝试关闭占用串口的进程: PID {pid} ({cmd})", file=sys.stderr)
            
            # 先尝试 SIGTERM（优雅关闭）
            try:
                result = subprocess.run(['kill', pid], timeout=2, check=False,
                                       capture_output=True, 
                                       stdout=subprocess.DEVNULL, 
                                       stderr=subprocess.DEVNULL)
                if result.returncode != 0:
                    # kill 命令失败，可能是权限问题或进程不存在
                    pass
                time.sleep(0.8)  # 等待进程退出
            except subprocess.TimeoutExpired:
                pass  # 如果超时，继续尝试 SIGKILL
            except Exception:
                pass  # 其他异常，继续尝试 SIGKILL
            
            # 检查进程是否还存在
            process_still_running = False
            try:
                result = subprocess.run(['ps', '-p', pid], 
                                      capture_output=True, 
                                      timeout=1, 
                                      check=False)
                if result.returncode == 0 and result.stdout.strip():
                    # 进程仍在运行
                    process_still_running = True
            except:
                # ps 命令失败，假设进程已关闭
                pass
            
            if process_still_running:
                # 如果进程仍在运行，强制关闭
                print(f"🔧 进程仍在运行，强制关闭: PID {pid}", file=sys.stderr)
                try:
                    subprocess.run(['kill', '-9', pid], timeout=2, check=False,
                                 capture_output=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                    time.sleep(0.5)
                except:
                    pass
            
            # 再次检查进程是否已关闭
            try:
                result = subprocess.run(['ps', '-p', pid], 
                                      capture_output=True, 
                                      timeout=1, 
                                      check=False)
                if result.returncode != 0 or not result.stdout.strip():
                    # 进程已关闭
                    killed_count += 1
                    print(f"✅ 成功关闭进程: PID {pid}", file=sys.stderr)
                else:
                    # 检查是否是 screen 会话
                    is_screen = False
                    try:
                        screen_result = subprocess.run(['ps', '-p', pid, '-o', 'comm='],
                                                    capture_output=True,
                                                    timeout=1,
                                                    check=False,
                                                    text=True)
                        if screen_result.returncode == 0:
                            comm = screen_result.stdout.strip().lower()
                            if 'screen' in comm:
                                is_screen = True
                                print(f"💡 检测到 screen 会话 (PID {pid})，尝试使用 screen -X quit 关闭...", file=sys.stderr)
                                try:
                                    # 尝试使用 screen -X quit 关闭会话
                                    subprocess.run(['screen', '-X', '-S', f'{pid}', 'quit'],
                                                 timeout=2, check=False,
                                                 capture_output=True,
                                                 stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.DEVNULL)
                                    time.sleep(1)
                                    # 再次检查
                                    check_result = subprocess.run(['ps', '-p', pid],
                                                                capture_output=True,
                                                                timeout=1,
                                                                check=False)
                                    if check_result.returncode != 0 or not check_result.stdout.strip():
                                        killed_count += 1
                                        print(f"✅ 通过 screen -X quit 成功关闭进程: PID {pid}", file=sys.stderr)
                                        continue
                                except:
                                    pass
                    except:
                        pass
                    
                    if not is_screen:
                        print(f"⚠️ 无法关闭进程: PID {pid}", file=sys.stderr)
                        print(f"   可能的原因：", file=sys.stderr)
                        print(f"   1. 需要 sudo 权限: sudo kill {pid}", file=sys.stderr)
                        print(f"   2. 进程属于其他用户", file=sys.stderr)
                        print(f"   3. 进程是系统进程", file=sys.stderr)
            except:
                # 如果检查失败，假设已关闭
                killed_count += 1
                print(f"✅ 已尝试关闭进程: PID {pid}", file=sys.stderr)
                
        except Exception as e:
            print(f"⚠️ 关闭进程失败 (PID {pid}): {e}", file=sys.stderr)
    
    if killed_count > 0:
        print(f"✅ 已处理 {killed_count} 个占用串口的进程", file=sys.stderr)
        time.sleep(1.5)  # 等待系统释放资源
        return True
    return False


def send_command(port='/dev/tty.usbserial-1110', baudrate=115200, command='SET state 4', retry_on_busy=True):
    """
    通过串口发送命令
    
    Args:
        port: 串口设备路径
        baudrate: 波特率
        command: 要发送的命令
    
    Returns:
        str: 成功返回包含"✅"的字符串，失败返回包含"❌"的字符串
    """
    response_str = ""
    
    # 首先尝试指定的端口（通常是 tty 设备）
    try:
        # 检查串口是否存在
        if not os.path.exists(port):
            msg = f"❌ 串口设备不存在: {port}"
            print(msg, file=sys.stderr)
            # 如果指定的是 tty 设备，尝试对应的 cu 设备
            if 'tty.usbserial' in port:
                cu_port = port.replace('tty.usbserial', 'cu.usbserial')
                if os.path.exists(cu_port):
                    print(f"💡 尝试使用对应的 cu 设备: {cu_port}", file=sys.stderr)
                    return send_command(cu_port, baudrate, command)
            return f"❌ {msg}"

        # 检查是否有读取权限
        if not os.access(port, os.R_OK):
            msg = f"❌ 串口设备无读取权限: {port}"
            print(msg, file=sys.stderr)
            print(f"💡 提示：可能需要使用 sudo 或添加用户到 dialout 组", file=sys.stderr)
            return f"❌ {msg}"

        # 打开串口（带重试机制）
        max_retries = 3
        retry_delay = 1
        ser = None
        
        for attempt in range(max_retries):
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=2  # 读超时2秒
                )
                break  # 成功打开，退出重试循环
            except serial.SerialException as e:
                if "Resource busy" in str(e) or "[Errno 16]" in str(e):
                    if attempt < max_retries - 1:
                        # 每次重试前都尝试关闭占用进程
                        if retry_on_busy:
                            print(f"⚠️ 串口被占用，尝试释放资源...", file=sys.stderr)
                            _kill_processes_using_port(port)
                            time.sleep(retry_delay)
                        else:
                            print(f"⏳ 等待串口释放 ({attempt + 1}/{max_retries})...", file=sys.stderr)
                            time.sleep(retry_delay)
                        continue
                    else:
                        # 最后一次尝试失败，抛出异常
                        raise
                else:
                    # 其他错误直接抛出
                    raise
        
        if ser is None:
            raise serial.SerialException(f"无法打开串口 {port}，已重试 {max_retries} 次")

        print(f"✅ 已连接 {port} @ {baudrate}bps")

        # 清空缓冲区
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # 发送命令（添加回车换行）
        full_command = command + '\r\n'
        ser.write(full_command.encode('utf-8'))
        print(f"📤 发送命令: {command}")

        # 等待并读取响应
        time.sleep(0.5)

        response = b''
        start_time = time.time()
        while time.time() - start_time < 3:  # 最多等3秒
            if ser.in_waiting > 0:
                response += ser.read(ser.in_waiting)
                time.sleep(0.1)
            else:
                time.sleep(0.05)

        if response:
            response_str = response.decode('utf-8', errors='ignore').strip()
            print(f"📥 收到响应: {response_str}")
        else:
            print("⚠️  未收到响应")
            response_str = "⚠️ 未收到响应"

        # 关闭串口
        ser.close()
        print("✅ 连接已关闭")
        return f"✅ 命令发送成功. 响应: {response_str}"

    except serial.SerialException as e:
        error_str = str(e)
        error_msg = f"❌ 串口错误: {e}"
        print(error_msg, file=sys.stderr)
        
        # 如果是资源占用错误，提供详细的解决建议
        if "Resource busy" in error_str or "[Errno 16]" in error_str:
            print(f"\n💡 串口被占用，可能的解决方案：", file=sys.stderr)
            
            # 查找占用进程
            processes = _find_processes_using_port(port)
            if processes:
                print(f"   发现以下进程占用串口：", file=sys.stderr)
                for proc in processes:
                    print(f"     - PID {proc['pid']}: {proc.get('cmd', 'unknown')}", file=sys.stderr)
                print(f"\n   可以手动关闭这些进程：", file=sys.stderr)
                for proc in processes:
                    print(f"     kill {proc['pid']}", file=sys.stderr)
            else:
                print(f"   未检测到占用进程，可能是系统锁定", file=sys.stderr)
            
            print(f"\n   其他解决方案：", file=sys.stderr)
            print(f"   1. 检查是否有 screen/minicom 等程序在使用串口", file=sys.stderr)
            print(f"   2. 等待几秒后重试", file=sys.stderr)
            print(f"   3. 重新插拔 USB 设备", file=sys.stderr)
            if platform.system() == 'Darwin':
                print(f"   4. 使用命令检查: lsof {port}", file=sys.stderr)
            elif platform.system() == 'Linux':
                print(f"   4. 使用命令检查: fuser {port} 或 lsof {port}", file=sys.stderr)
        
        # 如果使用的是 tty 设备，尝试对应的 cu 设备
        if 'tty.usbserial' in port:
            cu_port = port.replace('tty.usbserial', 'cu.usbserial')
            if os.path.exists(cu_port):
                print(f"💡 尝试使用对应的 cu 设备: {cu_port}", file=sys.stderr)
                try:
                    # 对于 cu 设备，也尝试自动关闭占用进程
                    return send_command(cu_port, baudrate, command, retry_on_busy=True)
                except:
                    pass
        
        return f"❌ {error_msg}"
    except KeyboardInterrupt:
        print("\n⏹️  用户中断", file=sys.stderr)
        if 'ser' in locals():
            try:
                ser.close()
            except Exception:
                pass
        return "❌ 用户中断"
    except Exception as e:
        error_msg = f"❌ 发生未知错误: {e}"
        print(error_msg, file=sys.stderr)
        return f"❌ {error_msg}"


if __name__ == "__main__":
    # 使用命令行参数
    parser = argparse.ArgumentParser(description='发送串口命令')
    parser.add_argument('--port', default='/dev/tty.usbserial-1110', help='串口设备')
    parser.add_argument('--baud', default=115200, type=int, help='波特率')
    parser.add_argument('--command', default='SET state 4', help='命令')

    args = parser.parse_args()
    result = send_command(args.port, args.baud, args.command)
    
    # 根据结果返回退出码
    if "❌" in result:
        sys.exit(1)
    sys.exit(0)
