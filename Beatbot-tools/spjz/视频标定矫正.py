# -*- coding: utf-8 -*-
"""
泳池监控视频标定与鸟瞰矫正（macOS 版）。

两步流程：
1. 先用鱼眼/针孔内参加去畸变（单应性无法消除桶形畸变）
2. 在去畸变后的图上点选标志，再计算单应性并导出鸟瞰视频

画质：把「去畸变 + 透视变换」合成一次 remap，避免二次插值发糊。

依赖：Python3 + opencv-python + Pillow + numpy；导出 mp4 建议 brew install ffmpeg
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

IS_MAC = sys.platform == "darwin"

# macOS Tk 不认 Windows 的「*.mp4;*.avi」分号写法，会导致扩展名全灰不可选。
# 空格分隔多个通配符，并单独列出常见格式 +「所有文件」。
IMAGE_FILETYPES = [
    ("图像", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
    ("PNG", "*.png"),
    ("JPEG", "*.jpg *.jpeg"),
    ("所有文件", "*.*"),
]
VIDEO_FILETYPES = [
    ("视频", "*.mp4 *.avi *.mkv *.mov *.m4v *.wmv *.flv *.webm *.ts *.m2ts *.mpeg *.mpg *.3gp"),
    ("MP4", "*.mp4 *.m4v"),
    ("MOV", "*.mov"),
    ("AVI", "*.avi"),
    ("MKV", "*.mkv"),
    ("所有文件", "*.*"),
]
YAML_FILETYPES = [
    ("YAML", "*.yaml *.yml"),
    ("所有文件", "*.*"),
]
CALIB_FILETYPES = [
    ("标定文件", "*.json *.xml"),
    ("所有文件", "*.*"),
]


def _ensure_mac_path() -> None:
    """把 Homebrew ffmpeg 等常见路径加入 PATH，方便打包/IDE 启动时也能找到。"""
    if not IS_MAC:
        return
    extras = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/opt/homebrew/sbin",
        "/usr/local/sbin",
    ]
    parts = os.environ.get("PATH", "").split(":")
    for p in extras:
        if p and p not in parts and os.path.isdir(p):
            parts.insert(0, p)
    os.environ["PATH"] = ":".join(parts)


def _ui_font(size: int = 12, weight: str | None = None):
    family = "PingFang SC" if IS_MAC else "Microsoft YaHei"
    return (family, size, weight) if weight else (family, size)


def _subprocess_kwargs() -> dict:
    """Windows 隐藏控制台；macOS/Linux 无此标志。"""
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flag} if flag else {}


# calib_H.py 默认鱼眼内参（主点约在画面中心，对应标定分辨率约 2847x1612）
DEFAULT_K = np.array(
    [
        [2168.015490906, 0.0, 1423.359181809],
        [0.0, 2183.618386919, 805.947791672],
        [0.0, 0.0, 1.0],
    ],
    dtype=np.float32,
)
DEFAULT_D_FISHEYE = np.array(
    [-0.426952297, 0.539241845, -0.598249736, 0.314336666],
    dtype=np.float32,
)
DEFAULT_CALIB_SIZE = (2847, 1612)

# calib_H.py 里注释掉的针孔模型
STANDARD_K = np.array(
    [
        [2863.520197749079, 0.0, 1957.086888717042],
        [0.0, 2866.599104954735, 1084.060765179607],
        [0.0, 0.0, 1.0],
    ],
    dtype=np.float32,
)
STANDARD_D = np.array(
    [-0.6262791876768283, 0.4569915881957762, -0.0008166441745077962, -0.0007645075151236271, -0.1572229855125919],
    dtype=np.float32,
)
STANDARD_CALIB_SIZE = (3914, 2168)

B8_WORLD_POINTS = [
    ("点1 左上", 1.86, 0.87),
    ("点2 右上", 8.85, 0.00),
    ("点3 右下", 11.56, 1.03),
    ("点4 左下", 2.12, 6.82),
    ("点5", 7.01, 6.82),
    ("点6", 8.78, 6.51),
]

DEFAULT_WORLD_POINTS = [
    ("标志1 左上", 0.00, 0.00),
    ("标志2 右上", 10.00, 0.00),
    ("标志3 右下", 10.00, 8.00),
    ("标志4 左下", 0.00, 8.00),
]

POINT_COLORS = [
    "#e74c3c",
    "#2ecc71",
    "#3498db",
    "#f39c12",
    "#9b59b6",
    "#1abc9c",
    "#e67e22",
    "#34495e",
]


def imread_unicode(path):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_unicode(path, img):
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        return False
    buf.tofile(path)
    return True


def open_video_capture(path):
    """打开视频；macOS 优先 AVFoundation，失败再回退并尝试拷贝到临时目录。"""
    backends = []
    if IS_MAC and hasattr(cv2, "CAP_AVFOUNDATION"):
        backends.append(cv2.CAP_AVFOUNDATION)
    backends.append(cv2.CAP_ANY)

    for backend in backends:
        try:
            cap = cv2.VideoCapture(path, backend)
        except Exception:
            cap = cv2.VideoCapture(path)
        if cap is not None and cap.isOpened():
            return cap, None

    tmp = os.path.join(tempfile.gettempdir(), f"_calib_src{os.path.splitext(path)[1] or '.mp4'}")
    try:
        shutil.copy2(path, tmp)
    except OSError:
        return None, None
    for backend in backends:
        try:
            cap = cv2.VideoCapture(tmp, backend)
        except Exception:
            cap = cv2.VideoCapture(tmp)
        if cap is not None and cap.isOpened():
            return cap, tmp
    return None, tmp


def parse_matrix_3x3(values):
    return np.array(values, dtype=np.float32).reshape(3, 3)


def scale_camera_matrix(k, from_size, to_size):
    """内参随分辨率等比缩放，与 calib_H 在不同分辨率视频上保持一致。"""
    from_w, from_h = from_size
    to_w, to_h = to_size
    if from_w <= 0 or from_h <= 0:
        return k.copy()
    sx = float(to_w) / float(from_w)
    sy = float(to_h) / float(from_h)
    k2 = k.copy()
    k2[0, 0] *= sx
    k2[0, 2] *= sx
    k2[1, 1] *= sy
    k2[1, 2] *= sy
    return k2


def prepare_undistort(k, d, image_size, method, balance=1.0):
    """
    与 calib_H.py / find_world_pt.py 相同：
    fisheye: estimateNewCameraMatrixForUndistortRectify + initUndistortRectifyMap
    standard: getOptimalNewCameraMatrix + initUndistortRectifyMap
    返回 (new_K, map1, map2)，method=none 时全为 None。
    """
    if method == "none":
        return None, None, None

    w, h = image_size
    if method == "fisheye":
        new_k = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
            k, d, (w, h), np.eye(3), balance=float(balance)
        )
        map1, map2 = cv2.fisheye.initUndistortRectifyMap(
            k, d, np.eye(3), new_k, (w, h), cv2.CV_32FC1
        )
        return new_k, map1, map2

    new_k, _ = cv2.getOptimalNewCameraMatrix(k, d, (w, h), 1, (w, h))
    map1, map2 = cv2.initUndistortRectifyMap(k, d, None, new_k, (w, h), cv2.CV_32FC1)
    return new_k, map1, map2


def remap_undistort(img, map1, map2):
    if map1 is None or map2 is None:
        return img
    return cv2.remap(img, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def compute_dst_geometry(world_pts_m, pixel_scale, margin_x=0.5, margin_y=0.5):
    pts = np.asarray(world_pts_m, dtype=np.float32) * float(pixel_scale)
    min_xy = pts.min(axis=0)
    margin = np.array([margin_x, margin_y], dtype=np.float32) * float(pixel_scale)
    shifted = pts - min_xy + margin
    dst_w = int(np.ceil(float(shifted[:, 0].max()) + margin[0]))
    dst_h = int(np.ceil(float(shifted[:, 1].max()) + margin[1]))
    dst_w = max(dst_w, 64)
    dst_h = max(dst_h, 64)
    dst_w += dst_w % 2
    dst_h += dst_h % 2
    return shifted, dst_w, dst_h


def suggest_pixel_scale(image_pts, world_pts):
    """用选点间距估算原图等效比例，避免 100px/m 把画面压糊。"""
    img = np.asarray(image_pts, dtype=np.float64)
    wld = np.asarray(world_pts, dtype=np.float64)
    scales = []
    for i in range(len(img)):
        for j in range(i + 1, len(img)):
            d_m = np.linalg.norm(wld[i] - wld[j])
            if d_m < 0.2:
                continue
            d_px = np.linalg.norm(img[i] - img[j])
            scales.append(d_px / d_m)
    if not scales:
        return 100.0
    return float(np.median(scales))


def build_bev_maps(H, dst_size, undist_map1=None, undist_map2=None, src_size=None):
    """
    合成「去畸变 + 单应性」的一次采样表：
    鸟瞰像素 -> 去畸变坐标(H^-1) -> 原始鱼眼像素(undistort map)
    视频导出时只 remap 一次，减少发糊。
    """
    dst_w, dst_h = int(dst_size[0]), int(dst_size[1])
    yy, xx = np.indices((dst_h, dst_w), dtype=np.float32)
    ones = np.ones_like(xx)
    dst_hom = np.stack([xx.ravel(), yy.ravel(), ones.ravel()], axis=0)
    undist_hom = np.linalg.inv(H).astype(np.float32) @ dst_hom
    undist_hom /= undist_hom[2:3, :]
    ux = undist_hom[0, :].reshape(dst_h, dst_w).astype(np.float32)
    uy = undist_hom[1, :].reshape(dst_h, dst_w).astype(np.float32)

    if undist_map1 is None or undist_map2 is None:
        return ux, uy

    map_x = cv2.remap(undist_map1, ux, uy, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    map_y = cv2.remap(undist_map2, ux, uy, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return map_x, map_y


def scale_homography_for_src(H, from_size, to_size):
    """标定图与视频分辨率不同时，把 H 变到视频坐标系，避免先缩小视频再变换。"""
    sx = float(from_size[0]) / float(to_size[0])
    sy = float(from_size[1]) / float(to_size[1])
    s = np.array([[sx, 0.0, 0.0], [0.0, sy, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    return (H.astype(np.float64) @ s).astype(np.float64)


def ffmpeg_available():
    _ensure_mac_path()
    candidates = ["ffmpeg"]
    if IS_MAC:
        candidates = [
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "ffmpeg",
        ]
    for bin_path in candidates:
        try:
            r = subprocess.run(
                [bin_path, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_subprocess_kwargs(),
            )
            if r.returncode == 0:
                return bin_path if os.path.isabs(bin_path) else "ffmpeg"
        except OSError:
            continue
    return None


FFMPEG_BIN = None


def get_ffmpeg_bin():
    global FFMPEG_BIN
    if FFMPEG_BIN is None:
        FFMPEG_BIN = ffmpeg_available() or "ffmpeg"
    return FFMPEG_BIN


def even_size(size):
    w, h = int(size[0]), int(size[1])
    return w + (w % 2), h + (h % 2)


class FFmpegWriter:
    def __init__(self, path, fps, size, encoder="libx264"):
        w, h = even_size(size)
        self.size = (w, h)
        self.path = path
        self._err = []
        cmd = [
            get_ffmpeg_bin(),
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{w}x{h}",
            "-r",
            f"{max(float(fps), 1.0):.3f}",
            "-i",
            "-",
            "-an",
        ]
        if encoder == "libx264":
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "mpeg4", "-q:v", "5"]
        cmd.append(path)
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **_subprocess_kwargs(),
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self):
        try:
            for line in self.proc.stderr:
                text = line.decode("utf-8", errors="ignore").strip()
                if text:
                    self._err.append(text)
        except Exception:
            pass

    def write(self, frame):
        if frame.shape[1] != self.size[0] or frame.shape[0] != self.size[1]:
            frame = cv2.resize(frame, self.size, interpolation=cv2.INTER_LINEAR)
        frame = np.ascontiguousarray(frame)
        if self.proc.poll() is not None:
            raise OSError(22, self.last_error() or "ffmpeg 已退出")
        try:
            self.proc.stdin.write(frame.tobytes())
        except OSError as exc:
            raise OSError(exc.errno, f"{exc.strerror}; ffmpeg: {self.last_error()}") from exc

    def last_error(self):
        return " | ".join(self._err[-6:]) if self._err else ""

    def isOpened(self):
        return self.proc.poll() is None

    def release(self):
        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
        try:
            self.proc.wait(timeout=60)
        except Exception:
            self.proc.kill()


def open_cv_writer(path, fps, size):
    w, h = even_size(size)
    ext = os.path.splitext(path)[1].lower()
    codecs = [("MJPG", ".avi")] if ext == ".avi" else [("mp4v", ".mp4"), ("MJPG", ".avi")]
    for fourcc_name, prefer_ext in codecs:
        trial = path if path.lower().endswith(prefer_ext) else os.path.splitext(path)[0] + prefer_ext
        writer = cv2.VideoWriter(trial, cv2.VideoWriter_fourcc(*fourcc_name), fps, (w, h))
        if writer.isOpened():
            return writer, trial
        writer.release()
    return None, path


def open_video_writer(path, fps, size):
    """先写到纯英文临时路径，避免 Windows 中文路径导致 Errno 22。"""
    size = even_size(size)
    tmp_dir = tempfile.gettempdir()

    if ffmpeg_available():
        tmp_mp4 = os.path.join(tmp_dir, "bev_export_tmp.mp4")
        dest = os.path.splitext(path)[0] + ".mp4"
        for encoder in ("libx264", "mpeg4"):
            try:
                writer = FFmpegWriter(tmp_mp4, fps, size, encoder=encoder)
                if writer.isOpened():
                    return writer, tmp_mp4, dest
            except Exception:
                continue

    tmp_avi = os.path.join(tmp_dir, "bev_export_tmp.avi")
    writer, actual = open_cv_writer(tmp_avi, fps, size)
    if writer is not None and writer.isOpened():
        return writer, actual, os.path.splitext(path)[0] + os.path.splitext(actual)[1]

    writer, actual = open_cv_writer(path, fps, size)
    if writer is not None and writer.isOpened():
        return writer, actual, None

    raise RuntimeError("无法创建视频写入器。请改存为 .avi，或安装带 libx264 的 ffmpeg。")


class VideoCalibApp:
    def __init__(self, root):
        self.root = root
        self.root.title("视频标定矫正 (macOS) - 先去畸变，再单应性")
        self.root.geometry("1400x900")
        self.root.minsize(1140, 740)

        self.raw_image = None
        self.work_image = None
        self.display_image = None
        self.photo = None
        self.loupe_photo = None

        self.image_path = None
        self.video_path = None
        self.temp_video = None

        self.scale_factor = 1.0
        self.canvas_w = 1
        self.canvas_h = 1
        self.image_points = []

        self.H = None
        self.dst_width = 0
        self.dst_height = 0
        self.dst_points = None
        self.preview_image = None
        self.bev_map_x = None
        self.bev_map_y = None

        self.K = DEFAULT_K.copy()
        self.D = DEFAULT_D_FISHEYE.copy()
        self.new_K = None
        self.undist_map1 = None
        self.undist_map2 = None

        self.undistort_method = tk.StringVar(value="fisheye")
        self.pixel_scale = tk.StringVar(value="100")
        self.margin_x = tk.StringVar(value="0.5")
        self.margin_y = tk.StringVar(value="0.5")
        self.balance = tk.StringVar(value="1.0")
        self.calib_w = tk.StringVar(value=str(DEFAULT_CALIB_SIZE[0]))
        self.calib_h = tk.StringVar(value=str(DEFAULT_CALIB_SIZE[1]))
        self.auto_scale_k = tk.BooleanVar(value=True)
        self.show_raw = tk.BooleanVar(value=False)

        self.processing = False
        self.cancel_flag = False
        self._img_offset = (0, 0)
        self._last_frame_size = None
        self._redraw_after = None
        self._redraw_busy = False
        self._loupe_after = None
        self._loupe_pending = None
        self._last_canvas_xy = None

        self._build_ui()
        self._load_world_preset(DEFAULT_WORLD_POINTS)
        self._set_status("请打开视频。必须先去畸变（鱼眼），泳池边沿变直后再点选标志。")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # macOS：打开后主动抢焦点，避免必须先点标题栏才能点按钮
        self.root.after(50, self._activate_window)
        self.root.bind("<FocusIn>", lambda _e: None, add="+")
        self.root.bind("<Button-1>", self._on_root_button, add="+")

    def _activate_window(self, _event=None):
        try:
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def _on_root_button(self, _event=None):
        """任意点击先激活本窗，避免 macOS 首次点击被系统吞掉。"""
        try:
            if self.root.focus_displayof() is None:
                self._activate_window()
        except tk.TclError:
            self._activate_window()

    def _btn(self, parent, text, command, **pack_kw):
        """创建按钮：macOS 用 Button-1 直接触发，不必先点顶栏激活。"""
        btn = ttk.Button(parent, text=text)

        def _fire(_event=None, cmd=command):
            self._activate_window()
            try:
                cmd()
            except Exception as exc:
                messagebox.showerror("操作失败", str(exc))
            return "break"

        if IS_MAC:
            btn.configure(command=lambda: None)
            btn.bind("<Button-1>", _fire)
        else:
            btn.configure(command=command)
        if pack_kw:
            btn.pack(**pack_kw)
        return btn

    def _build_ui(self):
        style = ttk.Style()
        # macOS 用 aqua；Windows 才有 vista
        preferred = "aqua" if IS_MAC else "vista"
        if preferred in style.theme_names():
            style.theme_use(preferred)
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        try:
            style.configure(".", font=_ui_font(12))
            style.configure("TButton", font=_ui_font(12))
            style.configure("TLabel", font=_ui_font(12))
        except tk.TclError:
            pass

        top = ttk.Frame(self.root, padding=(8, 6))
        top.pack(fill=tk.X)

        self._btn(top, "打开图片", self.open_image, side=tk.LEFT, padx=3)
        self._btn(top, "打开视频", self.open_video, side=tk.LEFT, padx=3)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(top, text="去畸变:").pack(side=tk.LEFT)
        method = ttk.Combobox(
            top,
            textvariable=self.undistort_method,
            values=["fisheye", "standard", "none"],
            width=10,
            state="readonly",
        )
        method.pack(side=tk.LEFT, padx=3)
        method.bind("<<ComboboxSelected>>", lambda _e: self._refresh_work_image())
        ttk.Label(top, text="balance:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.balance, width=5).pack(side=tk.LEFT, padx=2)
        self._btn(top, "应用去畸变", self._refresh_work_image, side=tk.LEFT, padx=3)
        self._btn(top, "加载相机YAML", self.load_camera_yaml, side=tk.LEFT, padx=3)

        top2 = ttk.Frame(self.root, padding=(8, 0, 8, 6))
        top2.pack(fill=tk.X)
        ttk.Checkbutton(top2, text="按当前画面缩放内参", variable=self.auto_scale_k, command=self._refresh_work_image).pack(
            side=tk.LEFT
        )
        ttk.Label(top2, text="内参标定分辨率:").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Entry(top2, textvariable=self.calib_w, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(top2, text="x").pack(side=tk.LEFT)
        ttk.Entry(top2, textvariable=self.calib_h, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(top2, text="比例 px/m:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(top2, textvariable=self.pixel_scale, width=7).pack(side=tk.LEFT, padx=3)
        self._btn(top2, "按选点自动比例", self.auto_pixel_scale, side=tk.LEFT, padx=3)
        ttk.Label(top2, text="边距X:").pack(side=tk.LEFT)
        ttk.Entry(top2, textvariable=self.margin_x, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(top2, text="边距Y:").pack(side=tk.LEFT)
        ttk.Entry(top2, textvariable=self.margin_y, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(top2, text="显示原始鱼眼(仅对照)", variable=self.show_raw, command=self.redraw_canvas).pack(
            side=tk.LEFT, padx=8
        )
        self._btn(top2, "加载标定", self.load_calib, side=tk.LEFT, padx=3)
        self._btn(top2, "保存标定", self.save_calib, side=tk.LEFT, padx=3)

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        left = ttk.Frame(body, padding=4)
        body.add(left, weight=0)

        ttk.Label(left, text="世界坐标（米，与点击顺序一一对应）").pack(anchor=tk.W)
        ttk.Label(
            left,
            text="点选必须在去畸变后的画面上进行。若池边仍明显外鼓，说明内参与当前分辨率不匹配。",
            wraplength=330,
            foreground="#555",
        ).pack(anchor=tk.W, pady=(0, 6))

        cols = ("idx", "name", "x", "y", "ix", "iy")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        headings = {"idx": "#", "name": "名称", "x": "X(m)", "y": "Y(m)", "ix": "图像X", "iy": "图像Y"}
        widths = {"idx": 36, "name": 90, "x": 60, "y": 60, "ix": 60, "iy": 60}
        for key in cols:
            self.tree.heading(key, text=headings[key])
            self.tree.column(key, width=widths[key], anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self._edit_tree_cell)

        edit_row = ttk.Frame(left)
        edit_row.pack(fill=tk.X, pady=6)
        self._btn(edit_row, "添加点", self.add_world_point, side=tk.LEFT, padx=2)
        self._btn(edit_row, "删除点", self.delete_world_point, side=tk.LEFT, padx=2)
        self._btn(edit_row, "矩形4点", self.make_rect_points, side=tk.LEFT, padx=2)
        self._btn(edit_row, "B8六点", lambda: self._load_world_preset(B8_WORLD_POINTS), side=tk.LEFT, padx=2)

        action = ttk.Frame(left)
        action.pack(fill=tk.X, pady=(8, 0))
        self._btn(action, "撤销上一点", self.undo_point, fill=tk.X, pady=2)
        self._btn(action, "清除图像点", self.clear_image_points, fill=tk.X, pady=2)
        self._btn(action, "计算单应性并预览", self.calibrate, fill=tk.X, pady=2)
        self._btn(action, "矫正视频并导出", self.rectify_video, fill=tk.X, pady=2)
        self._btn(action, "停止导出", self.stop_processing, fill=tk.X, pady=2)

        right = ttk.Frame(body)
        body.add(right, weight=1)
        self.view_label = ttk.Label(right, text="当前：未加载", foreground="#0a7")
        self.view_label.pack(anchor=tk.W, pady=(0, 4))
        self.canvas_frame = ttk.Frame(right)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.canvas_frame, bg="#1e1e1e", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Button-3>", lambda _e: self.undo_point())
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Leave>", self._hide_loupe)
        # 防抖：避免 Configure ↔ 改 canvas 尺寸 互相触发导致卡顿
        self.canvas_frame.bind("<Configure>", self._schedule_redraw)
        self.loupe = tk.Label(self.canvas, bd=1, relief=tk.SOLID, bg="white")
        # 放大镜是 canvas 子控件，会挡住点击；转发到取景点并标记
        self.loupe.bind("<Button-1>", self.on_canvas_click)
        self.loupe.bind("<Button-3>", lambda _e: self.undo_point())
        self._last_canvas_xy = None

        bottom = ttk.Frame(self.root, padding=(8, 2, 8, 6))
        bottom.pack(fill=tk.X)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill=tk.X)
        self.status = ttk.Label(bottom, text="", anchor=tk.W)
        self.status.pack(fill=tk.X, pady=(3, 0))

    def _set_status(self, text):
        self.status.config(text=text)

    def _schedule_redraw(self, _event=None):
        """窗口尺寸变化时防抖重绘，打断 Configure 反馈环。"""
        if self._redraw_busy:
            return
        if self._redraw_after is not None:
            try:
                self.root.after_cancel(self._redraw_after)
            except Exception:
                pass
        self._redraw_after = self.root.after(60, self._debounced_redraw)

    def _debounced_redraw(self):
        self._redraw_after = None
        try:
            fw = max(self.canvas_frame.winfo_width(), 100)
            fh = max(self.canvas_frame.winfo_height(), 100)
        except tk.TclError:
            return
        if self._last_frame_size == (fw, fh) and self.photo is not None:
            return
        self._last_frame_size = (fw, fh)
        self.redraw_canvas()

    def _on_close(self):
        self.cancel_flag = True
        self._cleanup_temp()
        self.root.destroy()

    def _cleanup_temp(self):
        if self.temp_video and os.path.exists(self.temp_video):
            try:
                os.remove(self.temp_video)
            except OSError:
                pass
            self.temp_video = None

    def _calib_size(self):
        try:
            return int(self.calib_w.get()), int(self.calib_h.get())
        except ValueError as exc:
            raise ValueError("内参标定分辨率必须是整数。") from exc

    def _active_k(self, image_size):
        k = self.K.copy()
        if self.auto_scale_k.get():
            k = scale_camera_matrix(k, self._calib_size(), image_size)
        return k

    def _load_world_preset(self, preset):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, (name, x, y) in enumerate(preset, start=1):
            self.tree.insert("", tk.END, values=(i, name, f"{x:.2f}", f"{y:.2f}", "", ""))
        self.image_points = []
        self.H = None
        self._redraw_overlays()

    def add_world_point(self):
        idx = len(self.tree.get_children()) + 1
        self.tree.insert("", tk.END, values=(idx, f"标志{idx}", "0.00", "0.00", "", ""))
        self._reindex_tree()

    def delete_world_point(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先在表格中选中要删除的点。")
            return
        for item in selected:
            self.tree.delete(item)
        self._reindex_tree()
        self.image_points = []
        self._sync_image_points_to_tree()
        self._redraw_overlays()
        self.H = None

    def _reindex_tree(self):
        rows = [self.tree.item(item, "values") for item in self.tree.get_children()]
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, row in enumerate(rows, start=1):
            vals = list(row)
            vals[0] = i
            self.tree.insert("", tk.END, values=vals)

    def make_rect_points(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("矩形四点")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        ttk.Label(dialog, text="长度 X (米):").grid(row=0, column=0, padx=8, pady=6, sticky=tk.W)
        len_var = tk.StringVar(value="10.00")
        ttk.Entry(dialog, textvariable=len_var, width=10).grid(row=0, column=1, padx=8, pady=6)
        ttk.Label(dialog, text="宽度 Y (米):").grid(row=1, column=0, padx=8, pady=6, sticky=tk.W)
        wid_var = tk.StringVar(value="8.00")
        ttk.Entry(dialog, textvariable=wid_var, width=10).grid(row=1, column=1, padx=8, pady=6)

        def apply():
            try:
                length = float(len_var.get())
                width = float(wid_var.get())
            except ValueError:
                messagebox.showerror("错误", "请输入有效数字。")
                return
            self._load_world_preset(
                [
                    ("标志1 左上", 0.0, 0.0),
                    ("标志2 右上", length, 0.0),
                    ("标志3 右下", length, width),
                    ("标志4 左下", 0.0, width),
                ]
            )
            dialog.destroy()

        ttk.Button(dialog, text="生成", command=apply).grid(row=2, column=0, columnspan=2, pady=8)

    def _edit_tree_cell(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col_index = int(self.tree.identify_column(event.x).replace("#", "")) - 1
        if col_index not in (1, 2, 3):
            return
        item = self.tree.identify_row(event.y)
        bbox = self.tree.bbox(item, f"#{col_index + 1}") if item else None
        if not item or not bbox:
            return
        values = list(self.tree.item(item, "values"))
        editor = ttk.Entry(self.tree)
        editor.insert(0, values[col_index])
        editor.select_range(0, tk.END)
        editor.focus()
        editor.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])

        def save(_e=None):
            values[col_index] = editor.get()
            self.tree.item(item, values=values)
            editor.destroy()
            self.H = None

        editor.bind("<Return>", save)
        editor.bind("<FocusOut>", save)

    def _world_rows(self):
        rows = []
        for item in self.tree.get_children():
            vals = self.tree.item(item, "values")
            rows.append({"name": str(vals[1]), "x": float(vals[2]), "y": float(vals[3]), "ix": vals[4], "iy": vals[5]})
        return rows

    def _sync_image_points_to_tree(self):
        for i, item in enumerate(self.tree.get_children()):
            vals = list(self.tree.item(item, "values"))
            if i < len(self.image_points):
                vals[4] = str(self.image_points[i][0])
                vals[5] = str(self.image_points[i][1])
            else:
                vals[4] = ""
                vals[5] = ""
            self.tree.item(item, values=vals)

    def open_image(self):
        path = filedialog.askopenfilename(
            title="选择标定图片",
            filetypes=IMAGE_FILETYPES,
        )
        if not path:
            return
        img = imread_unicode(path)
        if img is None:
            messagebox.showerror("错误", f"无法读取图片:\n{path}")
            return
        self.image_path = path
        self.raw_image = img
        self.image_points = []
        self.H = None
        self._refresh_work_image()

    def open_video(self):
        path = filedialog.askopenfilename(
            title="选择视频（使用第一帧标定）",
            filetypes=VIDEO_FILETYPES,
        )
        if not path:
            return
        self._cleanup_temp()
        cap, tmp = open_video_capture(path)
        if cap is None:
            messagebox.showerror("错误", f"无法打开视频:\n{path}")
            return
        ok, frame = cap.read()
        cap.release()
        if tmp:
            self.temp_video = tmp
        if not ok or frame is None:
            messagebox.showerror("错误", "无法读取视频第一帧。")
            return
        self.video_path = path
        self.image_path = None
        self.raw_image = frame
        self.image_points = []
        self.H = None
        self._refresh_work_image()

    def load_camera_yaml(self):
        path = filedialog.askopenfilename(
            title="选择 camera_params.yaml",
            filetypes=YAML_FILETYPES,
        )
        if not path:
            return
        try:
            import yaml
        except ImportError:
            messagebox.showerror("错误", "未安装 PyYAML，请先执行: pip install pyyaml")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            self.K = parse_matrix_3x3(config["camera_matrix"])
            self.D = np.array(config["distortion_coefficients"], dtype=np.float32)
            method = config.get("undistort_method", "fisheye")
            self.undistort_method.set(method if method in ("none", "fisheye", "standard") else "fisheye")
            if "calib_width" in config and "calib_height" in config:
                self.calib_w.set(str(int(config["calib_width"])))
                self.calib_h.set(str(int(config["calib_height"])))
            else:
                self.calib_w.set(str(int(round(float(self.K[0, 2]) * 2))))
                self.calib_h.set(str(int(round(float(self.K[1, 2]) * 2))))
            self._refresh_work_image()
        except Exception as exc:
            messagebox.showerror("错误", f"读取相机参数失败:\n{exc}")

    def _refresh_work_image(self):
        if self.raw_image is None:
            return
        method = self.undistort_method.get()
        h, w = self.raw_image.shape[:2]
        try:
            balance = float(self.balance.get())
            k = self._active_k((w, h))
            self.new_K, self.undist_map1, self.undist_map2 = prepare_undistort(
                k, self.D, (w, h), method, balance=balance
            )
            self.work_image = remap_undistort(self.raw_image, self.undist_map1, self.undist_map2)
        except Exception as exc:
            messagebox.showerror("去畸变失败", str(exc))
            self.work_image = self.raw_image.copy()
            self.undist_map1 = self.undist_map2 = self.new_K = None

        self.image_points = []
        self.H = None
        self.bev_map_x = self.bev_map_y = None
        self._sync_image_points_to_tree()
        self.redraw_canvas()
        if method == "none":
            self.view_label.config(text=f"当前：原始画面 {w}x{h}（未去畸变，池边会保持弯曲）", foreground="#c0392b")
            self._set_status("未去畸变。单应性只能做透视变换，消不掉鱼眼弯曲。请改回 fisheye。")
        else:
            self.view_label.config(text=f"当前：已去畸变 {w}x{h}  方法={method}  请确认池边已变直后再点选", foreground="#0a7")
            self._set_status(f"已按 calib_H 方式去畸变。画面 {w}x{h}。若边沿仍鼓，勾选「按当前画面缩放内参」或核对标定分辨率。")

    def redraw_canvas(self):
        src = self.raw_image if (self.show_raw.get() and self.raw_image is not None) else self.work_image
        if src is None:
            return
        self._redraw_busy = True
        try:
            # 用 canvas 实际尺寸计算，与 event.x/y 坐标系一致
            self.canvas.update_idletasks()
            frame_w = max(self.canvas.winfo_width(), 100)
            frame_h = max(self.canvas.winfo_height(), 100)
            h, w = src.shape[:2]
            scale = min(frame_w / w, frame_h / h, 1.0) or 1.0
            self.scale_factor = scale
            self.canvas_w = max(int(w * scale), 1)
            self.canvas_h = max(int(h * scale), 1)
            # 不改 canvas 控件宽高，避免触发 Configure 死循环；图像居中绘制
            ox = max((frame_w - self.canvas_w) // 2, 0)
            oy = max((frame_h - self.canvas_h) // 2, 0)
            self._img_offset = (ox, oy)
            resized = cv2.resize(src, (self.canvas_w, self.canvas_h), interpolation=cv2.INTER_AREA)
            self.display_image = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            self.photo = ImageTk.PhotoImage(Image.fromarray(self.display_image))
            self.canvas.delete("all")
            self.canvas.create_image(ox, oy, anchor=tk.NW, image=self.photo, tags="bg")
            if not self.show_raw.get():
                self._redraw_overlays()
            self._last_frame_size = (frame_w, frame_h)
        finally:
            self._redraw_busy = False

    def _event_to_canvas_xy(self, event):
        """统一把 canvas / 放大镜上的点击换算为 canvas 坐标。"""
        if event.widget is self.loupe:
            # 优先用光标在画面上的取景点（放大镜十字中心），避免点在镜面上坐标偏移
            if self._last_canvas_xy is not None:
                return self._last_canvas_xy
            return self.loupe.winfo_x() + event.x, self.loupe.winfo_y() + event.y
        return event.x, event.y

    def _redraw_overlays(self):
        self.canvas.delete("mark")
        if self.scale_factor <= 0:
            return
        ox, oy = self._img_offset
        for i, (x, y) in enumerate(self.image_points):
            sx = int(x * self.scale_factor) + ox
            sy = int(y * self.scale_factor) + oy
            color = POINT_COLORS[i % len(POINT_COLORS)]
            self.canvas.create_oval(sx - 6, sy - 6, sx + 6, sy + 6, outline=color, width=2, tags="mark")
            self.canvas.create_text(
                sx + 10, sy - 10, text=str(i + 1), fill=color, font=_ui_font(12, "bold"), tags="mark"
            )
            if i > 0:
                px, py = self.image_points[i - 1]
                self.canvas.create_line(
                    int(px * self.scale_factor) + ox,
                    int(py * self.scale_factor) + oy,
                    sx,
                    sy,
                    fill=color,
                    width=2,
                    tags="mark",
                )
        needed = len(self.tree.get_children())
        if needed and self.work_image is not None and not self.show_raw.get():
            self._set_status(f"已选择 {len(self.image_points)}/{needed} 个标志。请在去畸变画面上点选。")

    def on_canvas_click(self, event):
        if self.work_image is None:
            return
        if self.show_raw.get():
            messagebox.showinfo("提示", "当前在对照原图。请取消「显示原始鱼眼」后再点选，必须点在去畸变图上。")
            return
        needed = len(self.tree.get_children())
        if needed < 4:
            messagebox.showwarning("提示", "至少需要 4 个世界坐标点。")
            return
        if len(self.image_points) >= needed:
            messagebox.showinfo("提示", "点数已满。如需重选，请先撤销或清除。")
            return
        if self.scale_factor <= 0:
            return
        cx, cy = self._event_to_canvas_xy(event)
        ox, oy = self._img_offset
        x = int(round((cx - ox) / self.scale_factor))
        y = int(round((cy - oy) / self.scale_factor))
        h, w = self.work_image.shape[:2]
        # 轻微越界时钳制，避免静默丢点（原先直接 return 导致「点了没反应」）
        if x < -2 or y < -2 or x >= w + 2 or y >= h + 2:
            return
        x = min(max(x, 0), w - 1)
        y = min(max(y, 0), h - 1)
        self.image_points.append((x, y))
        self._sync_image_points_to_tree()
        self._hide_loupe()
        self._redraw_overlays()
        self.H = None

    def on_canvas_motion(self, event):
        if self.display_image is None:
            return
        self._last_canvas_xy = (event.x, event.y)
        # 放大镜节流，避免每次鼠标移动都生成 PhotoImage 导致卡顿
        self._loupe_pending = (event.x, event.y)
        if self._loupe_after is not None:
            return
        self._loupe_after = self.root.after(50, self._update_loupe)

    def _update_loupe(self):
        self._loupe_after = None
        if self._loupe_pending is None or self.display_image is None:
            return
        event_x, event_y = self._loupe_pending
        ox, oy = self._img_offset
        lx = event_x - ox
        ly = event_y - oy
        if not (0 <= lx < self.canvas_w and 0 <= ly < self.canvas_h):
            self._hide_loupe()
            return
        box, zoom = 56, 3
        x1 = max(lx - box // (2 * zoom), 0)
        y1 = max(ly - box // (2 * zoom), 0)
        x2 = min(x1 + box // zoom, self.display_image.shape[1])
        y2 = min(y1 + box // zoom, self.display_image.shape[0])
        patch = self.display_image[y1:y2, x1:x2]
        if patch.size == 0:
            return
        patch = cv2.resize(patch, (box * 2, box * 2), interpolation=cv2.INTER_NEAREST)
        cv2.drawMarker(patch, (patch.shape[1] // 2, patch.shape[0] // 2), (255, 0, 0), cv2.MARKER_CROSS, 16, 1)
        self.loupe_photo = ImageTk.PhotoImage(Image.fromarray(patch))
        self.loupe.config(image=self.loupe_photo)
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        loupe_w, loupe_h = box * 2, box * 2
        # 避开光标落点：上方不够就放到下方，右侧不够就放到左侧（顶边标志点尤其重要）
        if event_x + 18 + loupe_w <= cw:
            place_x = event_x + 18
        else:
            place_x = max(event_x - loupe_w - 18, 0)
        if event_y - loupe_h - 18 >= 4:
            place_y = event_y - loupe_h - 18
        else:
            place_y = min(event_y + 18, max(ch - loupe_h - 4, 0))
        self.loupe.place(x=place_x, y=place_y)

    def _hide_loupe(self, _event=None):
        self.loupe.place_forget()

    def undo_point(self):
        if not self.image_points:
            return
        self.image_points.pop()
        self._sync_image_points_to_tree()
        self._redraw_overlays()
        self.H = None

    def clear_image_points(self):
        self.image_points = []
        self._sync_image_points_to_tree()
        self._redraw_overlays()
        self.H = None

    def auto_pixel_scale(self):
        rows = self._world_rows()
        if len(self.image_points) != len(rows) or len(rows) < 2:
            messagebox.showwarning("提示", "请先点齐全部标志，再估算比例。")
            return
        world = [(r["x"], r["y"]) for r in rows]
        scale = suggest_pixel_scale(self.image_points, world)
        self.pixel_scale.set(f"{scale:.1f}")
        self.H = None
        self._set_status(f"已按选点间距设置比例为 {scale:.1f} px/m，可避免鸟瞰图被压小发糊。")

    def _read_scale_margin(self):
        scale = float(self.pixel_scale.get())
        mx = float(self.margin_x.get())
        my = float(self.margin_y.get())
        if scale <= 0:
            raise ValueError("比例必须大于 0。")
        return scale, mx, my

    def calibrate(self):
        if self.work_image is None:
            messagebox.showwarning("提示", "请先打开图片或视频。")
            return
        if self.undistort_method.get() == "none":
            if not messagebox.askyesno("未去畸变", "当前未去畸变，导出后池边仍会弯曲。是否仍要只用单应性？"):
                return
        rows = self._world_rows()
        if len(rows) < 4:
            messagebox.showwarning("提示", "至少需要 4 个世界坐标点。")
            return
        if len(self.image_points) != len(rows):
            messagebox.showwarning("提示", f"请点选全部 {len(rows)} 个标志。当前 {len(self.image_points)} 个。")
            return
        try:
            scale, mx, my = self._read_scale_margin()
            world = [(row["x"], row["y"]) for row in rows]
            native = suggest_pixel_scale(self.image_points, world)
            if scale < native * 0.7:
                if messagebox.askyesno(
                    "比例偏低",
                    f"当前 {scale:.1f} px/m，选点对应约 {native:.1f} px/m。\n"
                    "比例过低会把鸟瞰图缩小发糊。是否改用自动比例？",
                ):
                    scale = native
                    self.pixel_scale.set(f"{scale:.1f}")

            dst_pts, dst_w, dst_h = compute_dst_geometry(world, scale, mx, my)
            src = np.array(self.image_points, dtype=np.float32)
            H, mask = cv2.findHomography(src, dst_pts, method=0)
            if H is None:
                raise RuntimeError("findHomography 失败。")
            inliers = int(mask.sum()) if mask is not None else len(rows)
            self.bev_map_x, self.bev_map_y = build_bev_maps(
                H, (dst_w, dst_h), self.undist_map1, self.undist_map2
            )
            bird = cv2.remap(
                self.raw_image,
                self.bev_map_x,
                self.bev_map_y,
                interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
            )
        except Exception as exc:
            messagebox.showerror("标定失败", str(exc))
            return

        self.H = H
        self.dst_points = dst_pts
        self.dst_width = dst_w
        self.dst_height = dst_h
        self.preview_image = bird
        self._show_preview(bird)
        self._set_status(f"标定完成。内点 {inliers}/{len(rows)}，鸟瞰 {dst_w}x{dst_h}，比例 {scale:.1f} px/m。")

    def _show_preview(self, bird):
        win = tk.Toplevel(self.root)
        win.title("鸟瞰预览（一次 remap）")
        max_w, max_h = 1100, 800
        h, w = bird.shape[:2]
        scale = min(max_w / w, max_h / h, 1.0)
        show = cv2.resize(bird, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        if self.dst_points is not None:
            for i, (x, y) in enumerate(self.dst_points):
                px, py = int(x * scale), int(y * scale)
                cv2.circle(show, (px, py), 6, (0, 0, 255), 2)
                cv2.putText(show, str(i + 1), (px + 8, py - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        rgb = cv2.cvtColor(show, cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        label = ttk.Label(win, image=photo)
        label.image = photo
        label.pack(padx=8, pady=8)
        ttk.Label(win, text="请检查池边是否变直。若仍弯曲，回到主窗口确认已去畸变且池边已直，再重新点选。").pack(pady=(0, 8))

    def save_calib(self):
        if self.H is None:
            messagebox.showwarning("提示", "请先完成标定。")
            return
        default_name = "bird_eye_params.xml"
        if self.video_path:
            default_name = f"bird_eye_params_{os.path.splitext(os.path.basename(self.video_path))[0]}.xml"
        path = filedialog.asksaveasfilename(
            title="保存标定参数",
            defaultextension=".xml",
            initialfile=default_name,
            filetypes=[("OpenCV XML", "*.xml"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            cv_file = cv2.FileStorage(path, cv2.FILE_STORAGE_WRITE)
            cv_file.write("H", self.H)
            cv_file.write("dst_width", int(self.dst_width))
            cv_file.write("dst_height", int(self.dst_height))
            cv_file.release()
            sidecar = os.path.splitext(path)[0] + ".json"
            h, w = self.raw_image.shape[:2] if self.raw_image is not None else (0, 0)
            payload = {
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "image_path": self.image_path,
                "video_path": self.video_path,
                "undistort_method": self.undistort_method.get(),
                "balance": float(self.balance.get()),
                "auto_scale_k": self.auto_scale_k.get(),
                "calib_width": int(self.calib_w.get()),
                "calib_height": int(self.calib_h.get()),
                "image_width": w,
                "image_height": h,
                "pixel_scale": float(self.pixel_scale.get()),
                "margin_x": float(self.margin_x.get()),
                "margin_y": float(self.margin_y.get()),
                "dst_width": int(self.dst_width),
                "dst_height": int(self.dst_height),
                "camera_matrix": self.K.reshape(-1).tolist(),
                "distortion_coefficients": self.D.reshape(-1).tolist(),
                "image_points": self.image_points,
                "world_points": [{"name": r["name"], "x": r["x"], "y": r["y"]} for r in self._world_rows()],
            }
            with open(sidecar, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._set_status(f"已保存: {path}")
            messagebox.showinfo("保存成功", f"已写入:\n{path}\n{sidecar}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def load_calib(self):
        path = filedialog.askopenfilename(
            title="加载标定 JSON 或 XML",
            filetypes=CALIB_FILETYPES,
        )
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.undistort_method.set(data.get("undistort_method", "fisheye"))
                self.pixel_scale.set(str(data.get("pixel_scale", 100)))
                self.margin_x.set(str(data.get("margin_x", 0.5)))
                self.margin_y.set(str(data.get("margin_y", 0.5)))
                self.balance.set(str(data.get("balance", 1.0)))
                self.auto_scale_k.set(bool(data.get("auto_scale_k", True)))
                if data.get("calib_width"):
                    self.calib_w.set(str(data["calib_width"]))
                    self.calib_h.set(str(data["calib_height"]))
                if data.get("camera_matrix"):
                    self.K = parse_matrix_3x3(data["camera_matrix"])
                if data.get("distortion_coefficients"):
                    self.D = np.array(data["distortion_coefficients"], dtype=np.float32)
                world = [(p["name"], p["x"], p["y"]) for p in data.get("world_points", [])]
                if world:
                    self._load_world_preset(world)
                if self.raw_image is not None:
                    self._refresh_work_image()
                self.image_points = [tuple(p) for p in data.get("image_points", [])]
                self._sync_image_points_to_tree()
                xml_path = os.path.splitext(path)[0] + ".xml"
                if os.path.exists(xml_path):
                    self._load_xml_H(xml_path)
                self.redraw_canvas()
            else:
                self._load_xml_H(path)
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

    def _load_xml_H(self, path):
        cv_file = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
        H = cv_file.getNode("H").mat()
        dst_w = int(cv_file.getNode("dst_width").real())
        dst_h = int(cv_file.getNode("dst_height").real())
        cv_file.release()
        if H is None:
            raise RuntimeError("XML 中没有有效的 H 矩阵。")
        self.H = H
        self.dst_width = dst_w
        self.dst_height = dst_h
        if self.raw_image is not None:
            self.bev_map_x, self.bev_map_y = build_bev_maps(
                H, (dst_w, dst_h), self.undist_map1, self.undist_map2
            )
            self.preview_image = cv2.remap(
                self.raw_image, self.bev_map_x, self.bev_map_y, interpolation=cv2.INTER_LINEAR
            )
            self._show_preview(self.preview_image)

    def stop_processing(self):
        if self.processing:
            self.cancel_flag = True
            self._set_status("正在停止导出...")

    def rectify_video(self):
        if self.H is None:
            messagebox.showwarning("提示", "请先完成标定，或加载已有 XML。")
            return
        if self.processing:
            messagebox.showinfo("提示", "正在导出，请稍候。")
            return
        path = self.video_path
        if not path or not os.path.exists(path):
            path = filedialog.askopenfilename(
                title="选择要矫正的视频",
                filetypes=VIDEO_FILETYPES,
            )
            if not path:
                return
            self.video_path = path

        default_out = os.path.splitext(path)[0] + "_bev.mp4"
        out_path = filedialog.asksaveasfilename(
            title="保存矫正后的视频",
            defaultextension=".mp4",
            initialfile=os.path.basename(default_out),
            filetypes=[("MP4", "*.mp4"), ("AVI", "*.avi"), ("所有文件", "*.*")],
        )
        if not out_path:
            return

        self.processing = True
        self.cancel_flag = False
        self.progress.config(value=0)
        threading.Thread(target=self._rectify_worker, args=(path, out_path), daemon=True).start()

    def _rectify_worker(self, src_path, out_path):
        cap = None
        writer = None
        tmp_src = None
        try:
            cap, tmp_src = open_video_capture(src_path)
            if cap is None:
                raise RuntimeError(f"无法打开视频: {src_path}")

            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            if fps <= 1e-3:
                fps = 25.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            method = self.undistort_method.get()
            dst_size = even_size((int(self.dst_width), int(self.dst_height)))
            self.dst_width, self.dst_height = dst_size

            k = self._active_k((src_w, src_h))
            _new_k, u_map1, u_map2 = prepare_undistort(
                k, self.D, (src_w, src_h), method, balance=float(self.balance.get())
            )

            H = self.H
            calib_size = None
            if self.work_image is not None:
                ch, cw = self.work_image.shape[:2]
                calib_size = (cw, ch)
                if (cw, ch) != (src_w, src_h):
                    H = scale_homography_for_src(self.H, (cw, ch), (src_w, src_h))

            map_x, map_y = build_bev_maps(H, dst_size, u_map1, u_map2, src_size=(src_w, src_h))

            writer, actual_path, final_path = open_video_writer(out_path, fps, dst_size)
            if not writer.isOpened():
                raise RuntimeError("无法创建视频写入器。")

            idx = 0
            while True:
                if self.cancel_flag:
                    raise RuntimeError("用户取消导出。")
                ok, frame = cap.read()
                if not ok:
                    break
                if frame.shape[1] != src_w or frame.shape[0] != src_h:
                    frame = cv2.resize(frame, (src_w, src_h), interpolation=cv2.INTER_LINEAR)
                bird = cv2.remap(frame, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                if bird.shape[1] != dst_size[0] or bird.shape[0] != dst_size[1]:
                    bird = cv2.resize(bird, dst_size, interpolation=cv2.INTER_LINEAR)
                writer.write(np.ascontiguousarray(bird))
                idx += 1
                if total > 0 and idx % 5 == 0:
                    percent = min(100.0, idx * 100.0 / total)
                    self.root.after(0, self._update_progress, percent, idx, total)

            writer.release()
            writer = None
            cap.release()
            cap = None

            if final_path and actual_path != final_path:
                dest_dir = os.path.dirname(final_path)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                if os.path.exists(final_path):
                    os.remove(final_path)
                shutil.move(actual_path, final_path)
                saved = final_path
            else:
                saved = actual_path

            preview = None
            if self.preview_image is not None:
                preview_path = os.path.splitext(saved)[0] + "_preview.png"
                imwrite_unicode(preview_path, self.preview_image)
                preview = preview_path
            self.root.after(0, self._on_rectify_done, saved, idx, preview, calib_size, (src_w, src_h))
        except Exception as exc:
            self.root.after(0, self._on_rectify_error, str(exc))
        finally:
            if writer is not None:
                writer.release()
            if cap is not None:
                cap.release()
            if tmp_src and os.path.exists(tmp_src) and tmp_src != src_path:
                try:
                    os.remove(tmp_src)
                except OSError:
                    pass

    def _update_progress(self, percent, idx, total):
        self.progress.config(value=percent)
        self._set_status(f"正在矫正视频: {idx}/{total} 帧 ({percent:.1f}%)")

    def _on_rectify_done(self, saved, frames, preview, calib_size, video_size):
        self.processing = False
        self.progress.config(value=100)
        extra = f"\n预览图: {preview}" if preview else ""
        size_note = ""
        if calib_size and calib_size != video_size:
            size_note = f"\n标定分辨率 {calib_size} 与视频 {video_size} 不同，已自动缩放 H。"
        self._set_status(f"导出完成: {saved}，共 {frames} 帧。")
        messagebox.showinfo("导出完成", f"已保存:\n{saved}\n帧数: {frames}{extra}{size_note}")

    def _on_rectify_error(self, msg):
        self.processing = False
        self.progress.config(value=0)
        self._set_status(f"导出失败: {msg}")
        messagebox.showinfo("已停止", msg) if "取消" in msg else messagebox.showerror("导出失败", msg)


_embedded_win = None
_embedded_app = None


def open_video_calib_tool(parent=None):
    """供主程序嵌入调用：以独立子窗口打开视频标定矫正（已打开则前置）。

    不使用 transient：transient 会把子窗永远压在主窗之上，导致主界面
    其它功能弹窗（如轨迹参数）被挡住，看起来像「只能开一个功能」。
    """
    global _embedded_win, _embedded_app
    _ensure_mac_path()

    if _embedded_win is not None:
        try:
            if _embedded_win.winfo_exists():
                _embedded_win.lift()
                _embedded_win.focus_force()
                return _embedded_app
        except tk.TclError:
            _embedded_win = None
            _embedded_app = None

    win = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
    app = VideoCalibApp(win)
    # 独立窗口：可与主界面其它功能并行；略偏移避免完全盖住主窗
    # （须在 VideoCalibApp 初始化之后设置，否则会被其 geometry 覆盖）
    try:
        win.geometry("1400x900+60+40")
        win.lift()
        win.focus_force()
        if IS_MAC:
            win.attributes("-topmost", True)
            win.after(200, lambda: win.attributes("-topmost", False))
    except tk.TclError:
        pass

    def _on_destroy(event, w=win):
        global _embedded_win, _embedded_app
        if event.widget is w:
            _embedded_win = None
            _embedded_app = None

    win.bind("<Destroy>", _on_destroy)
    _embedded_win = win
    _embedded_app = app

    try:
        win.update_idletasks()
        win.lift()
        win.focus_force()
    except tk.TclError:
        pass
    return app


def main():
    _ensure_mac_path()
    root = tk.Tk()
    VideoCalibApp(root)
    if IS_MAC:
        try:
            root.update_idletasks()
            root.lift()
            root.attributes("-topmost", True)
            root.after(200, lambda: root.attributes("-topmost", False))
            root.focus_force()
        except tk.TclError:
            pass
    root.mainloop()


if __name__ == "__main__":
    main()
