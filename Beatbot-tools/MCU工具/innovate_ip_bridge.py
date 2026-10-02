#!/usr/bin/env python3
"""Innovate IP bridge: TCP Innovate ASCII -> ROS /motor_control (no PC COM)."""
import os
import re
import socket
import subprocess
import sys
import threading
import time

HOST = "127.0.0.1"
PORT = 9998
LOG_PATH = "/data/innovate_ip_bridge.log"
PID_PATH = "/data/innovate_ip_bridge.pid"
PUBLISH_HZ = 25.0

os.environ.setdefault("HOME", "/")
os.environ.setdefault("ROS_LOG_DIR", "/data/log")
os.environ.setdefault("ROS_LOCALHOST_ONLY", "1")
_ld = os.environ.get("LD_LIBRARY_PATH", "")
_extra = [
    "/obd/lib",
    "/obd/network",
    "/obd/xingmai_robot_interfaces/lib",
    "/usr/lib",
    "/opt/ros/humble/lib",
]
os.environ["LD_LIBRARY_PATH"] = ":".join(_extra + ([_ld] if _ld else []))
os.environ.setdefault(
    "AMENT_PREFIX_PATH",
    "/obd/ros_component:/opt/ros/humble:/obd/xingmai_robot_interfaces",
)
sys.path[:0] = [
    "/opt/ros/humble/lib/python3.10/site-packages",
    "/opt/ros/humble/lib/python3.10/dist-packages",
    "/obd/xingmai_robot_interfaces/lib/python3.10/site-packages",
]

_lock = threading.Lock()
_setpoints = {}  # motor index -> velocity
_state = 2  # manual
_ros_ok = False
_pub_motor = None
_pub_state = []
_node = None
_rclpy = None


def log(msg):
    line = str(msg).rstrip() + "\n"
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line)
    except Exception:
        pass


def daemonize():
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    sys.stdin = open("/dev/null", "r")
    sys.stdout = open(LOG_PATH, "a", buffering=1)
    sys.stderr = open(LOG_PATH, "a", buffering=1)


def ensure_robot_main():
    """Start robot_main_node if missing (owns ttyS3 / soc_to_mcu)."""
    try:
        out = subprocess.check_output(["ps"], text=True, errors="replace")
    except Exception as e:
        log(f"ps fail: {e}")
        return False
    for line in out.splitlines():
        if "robot_main_node" in line and "get_thread_cpu" not in line and "grep" not in line:
            log(f"robot_main already up: {line.strip()[:120]}")
            return True
    log("starting robot_main_node")
    cmd = (
        "HOME=/ ROS_LOG_DIR=/data/log ROS_LOCALHOST_ONLY=1 "
        "LD_LIBRARY_PATH=/obd/lib:/obd/network:/obd/xingmai_robot_interfaces/lib:/usr/lib:/opt/ros/humble/lib "
        "AMENT_PREFIX_PATH=/obd/ros_component:/opt/ros/humble:/obd/xingmai_robot_interfaces "
        "nohup /obd/bin/robot_main_node /obd/bin/ --ros-args --disable-stdout-logs "
        ">/data/log/robot_main_manual.log 2>&1 &"
    )
    subprocess.call(["sh", "-c", cmd])
    for _ in range(25):
        time.sleep(0.4)
        try:
            out = subprocess.check_output(["ps"], text=True, errors="replace")
        except Exception:
            continue
        for line in out.splitlines():
            if "robot_main_node" in line and "get_thread_cpu" not in line:
                log("robot_main started")
                return True
    log("robot_main start failed")
    return False


def init_ros():
    global _ros_ok, _pub_motor, _pub_state, _node, _rclpy
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
        from xm_robot_interfaces.msg import MotorGroupCommand, MotorUnitCommand, SocStateControl

        _rclpy = rclpy
        rclpy.init()
        node = Node("innovate_ip_bridge")
        qos = QoSProfile(
            depth=20,
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            subs = node.get_subscriptions_info_by_topic("/motor_control")
            if subs:
                log(f"motor_control subs: {[s.node_name for s in subs]}")
                break
            time.sleep(0.4)
            try:
                rclpy.spin_once(node, timeout_sec=0.05)
            except Exception:
                pass
        else:
            log("WARN: /motor_control has no subscriber yet")

        _pub_motor = node.create_publisher(MotorGroupCommand, "/motor_control", qos)
        state_topics = [
            name
            for name, types in node.get_topic_names_and_types()
            if any("SocStateControl" in t for t in types)
        ]
        for t in (
            "/soc_control_state",
            "/soc_state_control",
            "/state_control",
            "/SOC_STATE_CONTROL",
        ):
            if t not in state_topics:
                state_topics.insert(0 if t == "/soc_control_state" else len(state_topics), t)
        _pub_state = [node.create_publisher(SocStateControl, t, qos) for t in state_topics]
        log(f"state pubs: {state_topics}")
        _node = node
        node._MotorGroupCommand = MotorGroupCommand
        node._MotorUnitCommand = MotorUnitCommand
        node._SocStateControl = SocStateControl
        _ros_ok = True
        log("ROS ready")
        return True
    except Exception as e:
        log(f"ROS init failed: {e}")
        _ros_ok = False
        return False


def apply_innovate(cmd: str):
    """Update setpoints from Innovate ASCII."""
    global _state
    c = cmd.strip()
    if not c:
        return "empty"

    m = re.match(r"SET\s+state\s+(-?\d+)\.?", c, re.I)
    if m:
        with _lock:
            _state = int(m.group(1))
        return f"state={_state}"

    if re.match(r"SET\s+stop", c, re.I):
        with _lock:
            _setpoints.clear()
            for i in range(8):
                _setpoints[i] = 0
            _state = 5
        return "estop"

    mapping = [
        (r"MV\s+wheel\s+motor\s+(-?\d+)\s+(-?\d+)\.", (0, 1)),
        (r"MV\s+water\s+pump\s+(-?\d+)\s+(-?\d+)\.", (2, 3)),
        (r"MV\s+prop\s+motor\s+(-?\d+)\s+(-?\d+)\.", (4, 5)),
        (r"MV\s+side\s+brush\s+(-?\d+)\s+(-?\d+)\.", (6, 7)),
    ]
    for pat, idxs in mapping:
        m = re.match(pat, c, re.I)
        if m:
            v0, v1 = int(m.group(1)), int(m.group(2))
            with _lock:
                _setpoints[idxs[0]] = v0
                _setpoints[idxs[1]] = v1
            return f"idx{idxs[0]}={v0},idx{idxs[1]}={v1}"

    m = re.match(r"MV\s+side\s+thruster\s+(-?\d+)\.", c, re.I)
    if m:
        v = int(m.group(1))
        with _lock:
            _setpoints[8] = v
        return f"idx8={v}"

    return "unmapped"


def publish_once():
    if not _ros_ok or _pub_motor is None or _node is None:
        return False
    MotorGroupCommand = _node._MotorGroupCommand
    MotorUnitCommand = _node._MotorUnitCommand
    SocStateControl = _node._SocStateControl
    with _lock:
        state = _state
        items = list(_setpoints.items())
    try:
        st = SocStateControl()
        st.state = int(state) & 0xFF
        st.set_time = 0
        for p in _pub_state:
            p.publish(st)
        if items:
            msg = MotorGroupCommand()
            msg.is_full_update = False
            msg.update_mask = 0xFF
            for idx, vel in items:
                u = MotorUnitCommand()
                u.index = int(idx) & 0xFF
                u.target_velocity = int(vel)
                u.target_acc = 0
                msg.commands.append(u)
            _pub_motor.publish(msg)
        _rclpy.spin_once(_node, timeout_sec=0.0)
        return True
    except Exception as e:
        log(f"publish err: {e}")
        return False


def publisher_loop():
    period = 1.0 / PUBLISH_HZ
    while True:
        publish_once()
        time.sleep(period)


def handle_line(line: str) -> str:
    cmd = line.strip()
    if not cmd:
        return ""
    info = apply_innovate(cmd)
    # ROS 可能还在初始化
    if not _ros_ok:
        for _ in range(40):
            if _ros_ok:
                break
            time.sleep(0.25)
    ok = publish_once()
    return f"ACK {cmd} | ros={'ok' if ok else 'fail'} {info}\r\n"


def client_loop(conn, addr):
    log(f"client {addr}")
    buf = ""
    try:
        conn.settimeout(0.5)
        while True:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break
            buf += data.decode("utf-8", errors="replace")
            while "\n" in buf or "\r" in buf:
                for sep in ("\r\n", "\n", "\r"):
                    if sep in buf:
                        line, buf = buf.split(sep, 1)
                        break
                else:
                    break
                resp = handle_line(line)
                if resp:
                    conn.sendall(resp.encode("utf-8", errors="replace"))
    except Exception as e:
        log(f"client err: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        log(f"client closed {addr}")


def main():
    try:
        with open(LOG_PATH, "w") as f:
            f.write("")
    except Exception:
        pass
    log(f"boot argv={sys.argv} pid={os.getpid()}")
    if "--daemon" in sys.argv:
        try:
            daemonize()
            log(f"daemonized pid={os.getpid()}")
        except Exception as e:
            log(f"daemonize skip: {e}")
    try:
        with open(PID_PATH, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    try:
        ensure_robot_main()
        # 先监听 TCP，避免 PC 端等待 ROS 初始化超时
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(4)
        log(f"listening on {HOST}:{PORT} pid={os.getpid()}")

        def ros_boot():
            try:
                init_ros()
                threading.Thread(target=publisher_loop, daemon=True).start()
                log(f"ros boot done ok={_ros_ok}")
            except Exception as e:
                log(f"ros boot err: {e}")

        threading.Thread(target=ros_boot, daemon=True).start()

        while True:
            conn, addr = srv.accept()
            threading.Thread(target=client_loop, args=(conn, addr), daemon=True).start()
    except Exception as e:
        log(f"fatal: {e}")
        raise


if __name__ == "__main__":
    main()
