import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from datetime import datetime
import numpy as np
import logging
import atexit
import shutil
import tempfile
import tarfile
import zipfile
import re
import sys
import subprocess
import importlib.util
import time


# 检查依赖包是否可用
def check_package(package_name, import_name=None):
    if import_name is None:
        import_name = package_name
    return importlib.util.find_spec(import_name) is not None


# 检查必要的依赖包
print("正在检查依赖包...")
openpyxl_available = check_package("openpyxl")
zstandard_available = check_package("zstandard")
rarfile_available = check_package("rarfile")
cv2_available = check_package("cv2", "cv2")

print(f"依赖包状态:")
print(f"  openpyxl: {'✓ 已安装' if openpyxl_available else '✗ 未安装'}")
print(f"  zstandard: {'✓ 已安装' if zstandard_available else '✗ 未安装'}")
print(f"  rarfile: {'✓ 已安装' if rarfile_available else '✗ 未安装'}")
print(f"  opencv-python: {'✓ 已安装' if cv2_available else '✗ 未安装'}")
print("依赖包检查完成")

# 安全导入依赖包
openpyxl = None
Alignment = None
zstd = None
cv2 = None

if openpyxl_available:
    try:
        import openpyxl
        from openpyxl.styles import Alignment

        print("✓ openpyxl 导入成功")
    except ImportError:
        print("⚠️ openpyxl 导入失败，用例导出功能将不可用")
else:
    print("⚠️ openpyxl 未安装，用例导出功能将不可用")

if zstandard_available:
    try:
        import zstandard as zstd

        print("✓ zstandard 导入成功")
    except ImportError:
        print("⚠️ zstandard 导入失败，压缩包解压功能将不可用")
else:
    print("⚠️ zstandard 未安装，压缩包解压功能将不可用")

if cv2_available:
    print("✓ opencv-python 可用（将在使用轨迹线绘制时导入）")
else:
    print("⚠️ opencv-python 未安装，轨迹线绘制功能将不可用")


class TrajectoryLine:
    def __init__(self):
        # 检查cv2是否可用；实际 import 延迟到点击轨迹线绘制时，避免 macOS 启动阶段崩溃
        if not cv2_available:
            print("⚠️ 轨迹线绘制功能不可用，请安装 opencv-python")
            return

        # 处理/显示尺寸在打开视频时按屏幕与原始比例自适应计算
        self.FRAME_WIDTH = 640
        self.FRAME_HEIGHT = 480
        self.WINDOW_WIDTH = 640
        self.WINDOW_HEIGHT = 480
        self.TRACK_WIDTH = int(os.environ.get("TRAJECTORY_TRACK_WIDTH", "15"))
        self.CENTERLINE_WIDTH = int(os.environ.get("TRAJECTORY_CENTERLINE_WIDTH", str(max(1, self.TRACK_WIDTH // 5))))
        self.MANUAL_TRACK_WIDTH = "TRAJECTORY_TRACK_WIDTH" in os.environ
        self.MAX_JUMP_RATIO = float(os.environ.get("TRAJECTORY_MAX_JUMP_RATIO", "2.5"))
        self.MAX_LOST_FRAMES = int(os.environ.get("TRAJECTORY_MAX_LOST_FRAMES", "8"))
        # 自动重新锁定：目标远近变化/水面反光时模板分数会下降，阈值不能太死。
        self.REID_MATCH_THRESHOLD = float(os.environ.get("TRAJECTORY_REID_MATCH_THRESHOLD", "0.46"))
        self.REID_TEMPLATE_THRESHOLD = float(os.environ.get("TRAJECTORY_REID_TEMPLATE_THRESHOLD", "0.42"))
        self.REID_HIST_THRESHOLD = float(os.environ.get("TRAJECTORY_REID_HIST_THRESHOLD", "0.10"))
        self.REID_FEATURE_THRESHOLD = float(os.environ.get("TRAJECTORY_REID_FEATURE_THRESHOLD", "0.0"))
        # 默认信任 tracker 锁定的目标框，只用几何约束过滤明显漂移；身份校验作为弱辅助。
        self.ENABLE_STRICT_IDENTITY_CHECK = os.environ.get("TRAJECTORY_STRICT_IDENTITY_CHECK", "0").strip() == "1"
        self.TRACK_IDENTITY_THRESHOLD = float(os.environ.get("TRAJECTORY_TRACK_IDENTITY_THRESHOLD", "0.45"))
        self.TRACK_TEMPLATE_THRESHOLD = float(os.environ.get("TRAJECTORY_TRACK_TEMPLATE_THRESHOLD", "0.45"))
        self.TRACK_HIST_THRESHOLD = float(os.environ.get("TRAJECTORY_TRACK_HIST_THRESHOLD", "0.0"))
        self.TRACK_FEATURE_THRESHOLD = float(os.environ.get("TRAJECTORY_TRACK_FEATURE_THRESHOLD", "0.0"))
        self.IDENTITY_SOFT_MISMATCH_FRAMES = int(os.environ.get("TRAJECTORY_IDENTITY_SOFT_MISMATCH_FRAMES", "3"))
        self.BBOX_LOST_IDENTITY_THRESHOLD = float(os.environ.get("TRAJECTORY_BBOX_LOST_IDENTITY_THRESHOLD", "0.48"))
        self.BBOX_LOST_TEMPLATE_THRESHOLD = float(os.environ.get("TRAJECTORY_BBOX_LOST_TEMPLATE_THRESHOLD", "0.50"))
        self.BBOX_SIZE_MIN_RATIO = float(os.environ.get("TRAJECTORY_BBOX_SIZE_MIN_RATIO", "0.45"))
        self.BBOX_SIZE_MAX_RATIO = float(os.environ.get("TRAJECTORY_BBOX_SIZE_MAX_RATIO", "2.2"))
        self.MIN_POOL_OVERLAP_RATIO = float(os.environ.get("TRAJECTORY_MIN_POOL_OVERLAP_RATIO", "0.70"))
        self.REQUIRE_MOTION_IN_BBOX = os.environ.get("TRAJECTORY_REQUIRE_MOTION_IN_BBOX", "1").strip() == "1"
        self.MIN_BBOX_MOTION_RATIO = float(os.environ.get("TRAJECTORY_MIN_BBOX_MOTION_RATIO", "0.004"))
        self.MOTION_DIFF_THRESHOLD = int(os.environ.get("TRAJECTORY_MOTION_DIFF_THRESHOLD", "10"))
        # 目标不可见期间的真实路径未知，默认不自动补线，避免画出机器没走过的区域。
        self.CONNECT_REID_GAP = os.environ.get("TRAJECTORY_CONNECT_REID_GAP", "0").strip() == "1"
        # 目标不可见期间的真实覆盖无法确认，因此重连段默认只画中心轨迹，不计入绿色覆盖。
        self.RECONNECT_COVERAGE = os.environ.get("TRAJECTORY_RECONNECT_COVERAGE", "0").strip() == "1"
        self.MAX_RECONNECT_DISTANCE = float(os.environ.get("TRAJECTORY_MAX_RECONNECT_DISTANCE", "360"))
        self.RECONNECT_STEP_PX = float(os.environ.get("TRAJECTORY_RECONNECT_STEP_PX", "12"))
        # 目标短暂离开画面后自动重锁定；候选框需连续多帧确认，降低误锁水面/石头。
        self.AUTO_RELOCK = os.environ.get("TRAJECTORY_AUTO_RELOCK", "1").strip() == "1"
        self.PREDICTIVE_REID = os.environ.get("TRAJECTORY_PREDICTIVE_REID", "1").strip() == "1"
        self.PREDICTIVE_SEARCH_MARGIN = int(os.environ.get("TRAJECTORY_PREDICTIVE_SEARCH_MARGIN", "180"))
        self.MAX_PREDICT_FRAMES = int(os.environ.get("TRAJECTORY_MAX_PREDICT_FRAMES", "90"))
        self.REID_INTERVAL_FRAMES = int(os.environ.get("TRAJECTORY_REID_INTERVAL_FRAMES", "1"))
        self.REID_SEARCH_MARGIN = int(os.environ.get("TRAJECTORY_REID_SEARCH_MARGIN", "220"))
        # 丢失若干帧后在泳池区域内扩大搜索，解决目标从画面一侧消失、另一侧再出现的问题。
        self.REID_POOL_WIDE_AFTER_FRAMES = int(os.environ.get("TRAJECTORY_REID_POOL_WIDE_AFTER_FRAMES", "4"))
        self.REID_POOL_SEARCH_MARGIN = int(os.environ.get("TRAJECTORY_REID_POOL_SEARCH_MARGIN", "24"))
        # 全画面搜索默认仍关闭；仅在泳池区域搜索已足够覆盖大多数重现场景。
        self.REID_ALLOW_GLOBAL_SEARCH = os.environ.get("TRAJECTORY_REID_ALLOW_GLOBAL_SEARCH", "0").strip() == "1"
        self.REID_GLOBAL_AFTER_FRAMES = int(os.environ.get("TRAJECTORY_REID_GLOBAL_AFTER_FRAMES", "12"))
        self.USE_COLOR_BLOB_REID = os.environ.get("TRAJECTORY_USE_COLOR_BLOB_REID", "0").strip() == "1"
        self.REID_COLOR_BLOB_AFTER_FRAMES = int(os.environ.get("TRAJECTORY_REID_COLOR_BLOB_AFTER_FRAMES", "8"))
        self.MOTION_REID_AFTER_FRAMES = int(os.environ.get("TRAJECTORY_MOTION_REID_AFTER_FRAMES", "1"))
        self.CANDIDATE_CONFIRM_FRAMES = int(os.environ.get("TRAJECTORY_CANDIDATE_CONFIRM_FRAMES", "2"))
        self.CANDIDATE_CONFIRM_FRAMES_HIGH = int(os.environ.get("TRAJECTORY_CANDIDATE_CONFIRM_FRAMES_HIGH", "1"))
        self.RELOCK_GRACE_FRAMES = int(os.environ.get("TRAJECTORY_RELOCK_GRACE_FRAMES", "6"))
        self.INIT_GRACE_FRAMES = int(os.environ.get("TRAJECTORY_INIT_GRACE_FRAMES", "30"))
        # 至少连续有效跟踪这么多帧后，才允许自动重锁定，避免目标未出现时就误锁水面。
        self.MIN_ESTABLISHED_TRACK_FRAMES = int(os.environ.get("TRAJECTORY_MIN_ESTABLISHED_TRACK_FRAMES", "10"))
        self.NO_MOTION_RELEASE_FRAMES = int(os.environ.get("TRAJECTORY_NO_MOTION_RELEASE_FRAMES", "60"))
        self.DRIFT_RELEASE_FRAMES = int(os.environ.get("TRAJECTORY_DRIFT_RELEASE_FRAMES", "2"))
        self.REID_CANDIDATE_MATCH_THRESHOLD = float(os.environ.get("TRAJECTORY_REID_CANDIDATE_MATCH_THRESHOLD", "0.48"))
        self.REID_CANDIDATE_TEMPLATE_THRESHOLD = float(os.environ.get("TRAJECTORY_REID_CANDIDATE_TEMPLATE_THRESHOLD", "0.46"))
        self.REID_CANDIDATE_HIGH_SCORE = float(os.environ.get("TRAJECTORY_REID_CANDIDATE_HIGH_SCORE", "0.58"))
        self.REID_CANDIDATE_MIN_MOTION_RATIO = float(os.environ.get("TRAJECTORY_REID_CANDIDATE_MIN_MOTION_RATIO", "0.008"))
        self.CANDIDATE_IOU_THRESHOLD = float(os.environ.get("TRAJECTORY_CANDIDATE_IOU_THRESHOLD", "0.40"))
        self.CANDIDATE_CENTER_DISTANCE = float(os.environ.get("TRAJECTORY_CANDIDATE_CENTER_DISTANCE", "75"))
        self.CANDIDATE_MISS_TOLERANCE = int(os.environ.get("TRAJECTORY_CANDIDATE_MISS_TOLERANCE", "3"))
        self.MOTION_ACCUM_FRAMES = int(os.environ.get("TRAJECTORY_MOTION_ACCUM_FRAMES", "2"))
        self.COVERAGE_UPDATE_INTERVAL = int(os.environ.get("TRAJECTORY_COVERAGE_UPDATE_INTERVAL", "15"))
        self.COVERAGE_WINDOW_INTERVAL = int(os.environ.get("TRAJECTORY_COVERAGE_WINDOW_INTERVAL", "3"))
        self.RELOCK_LOG_INTERVAL = int(os.environ.get("TRAJECTORY_RELOCK_LOG_INTERVAL", "30"))
        self.IDENTITY_CHECK_INTERVAL = int(os.environ.get("TRAJECTORY_IDENTITY_CHECK_INTERVAL", "3"))
        self.SOFT_RELOCK_INTERVAL = int(os.environ.get("TRAJECTORY_SOFT_RELOCK_INTERVAL", "2"))
        self.MOTION_CHECK_INTERVAL = int(os.environ.get("TRAJECTORY_MOTION_CHECK_INTERVAL", "2"))
        self.SYNC_VIDEO_FPS = os.environ.get("TRAJECTORY_SYNC_VIDEO_FPS", "1").strip() == "1"
        self.MAX_PROCESS_WIDTH = int(os.environ.get("TRAJECTORY_MAX_PROCESS_WIDTH", "960"))
        self.FOOTPRINT_USE_CIRCLE = os.environ.get("TRAJECTORY_FOOTPRINT_USE_CIRCLE", "1").strip() == "1"
        self.REID_SCALE_FACTORS = [
            float(v.strip())
            for v in os.environ.get("TRAJECTORY_REID_SCALE_FACTORS", "0.75,0.9,1.0,1.15,1.3").split(",")
            if v.strip()
        ]
        self.IDENTITY_TEMPLATE_UPDATE_INTERVAL = int(os.environ.get("TRAJECTORY_TEMPLATE_UPDATE_INTERVAL", "12"))
        self.IDENTITY_MAX_TEMPLATES = int(os.environ.get("TRAJECTORY_MAX_TEMPLATES", "8"))
        self.ORB_FEATURES = int(os.environ.get("TRAJECTORY_ORB_FEATURES", "300"))
        # bbox 模式：目标框锁定后，直接根据运动中的 bbox 绘制 footprint 和中心线。
        # 这是当前泳池机器视频最直观稳定的模式，避免过度身份校验导致“不画”。
        self.TRACKING_MODE = os.environ.get("TRAJECTORY_TRACKING_MODE", "bbox").strip().lower()
        # 默认用“机器足迹”计算覆盖，避免粗线把机器没走过的区域也刷出来
        self.COVERAGE_MODE = os.environ.get("TRAJECTORY_COVERAGE_MODE", "footprint").strip().lower()
        self.FOOTPRINT_SCALE = float(os.environ.get("TRAJECTORY_FOOTPRINT_SCALE", "1.0"))
        self._source_video_size = (0, 0)

        # 设置日志文件夹路径
        self.LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
        os.makedirs(self.LOG_DIR, exist_ok=True)

        # 设置日志文件名称和路径
        log_file_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".log"
        log_file_path = os.path.join(self.LOG_DIR, log_file_name)

        # 配置日志记录
        logging.basicConfig(
            filename=log_file_path,
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        atexit.register(logging.shutdown)

    class TemplateTracker:
        """
        不依赖 OpenCV contrib 的简易模板跟踪器。
        使用初始 ROI 作为模板，在后续帧里做归一化模板匹配，
        适合作为 TrackerCSRT 不可用时的兜底方案。
        """

        def __init__(self):
            self.template = None
            self.bbox = None
            self.search_margin = 80
            self.match_threshold = float(os.environ.get("TRAJECTORY_TEMPLATE_TRACK_THRESHOLD", "0.55"))

        def init(self, frame, bbox):
            x, y, w, h = [int(v) for v in bbox]
            x = max(0, x)
            y = max(0, y)
            w = max(1, w)
            h = max(1, h)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            self.template = gray[y:y + h, x:x + w].copy()
            if self.template.size == 0:
                return False
            self.bbox = (x, y, w, h)
            return True

        def update(self, frame):
            if self.template is None or self.bbox is None:
                return False, self.bbox

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            x, y, w, h = self.bbox
            margin = self.search_margin
            x1 = max(0, x - margin)
            y1 = max(0, y - margin)
            x2 = min(gray.shape[1], x + w + margin)
            y2 = min(gray.shape[0], y + h + margin)
            search_img = gray[y1:y2, x1:x2]
            if search_img.shape[0] < h or search_img.shape[1] < w:
                search_img = gray
                x1 = 0
                y1 = 0

            try:
                res = cv2.matchTemplate(search_img, self.template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                top_left = (max_loc[0] + x1, max_loc[1] + y1)
                self.bbox = (top_left[0], top_left[1], w, h)
                # 仅在相关性较高时认为跟踪成功，避免目标丢失后漂到水面还继续画。
                return max_val >= self.match_threshold, self.bbox
            except Exception:
                return False, self.bbox

    def _get_screen_size(self) -> tuple[int, int]:
        """获取当前屏幕分辨率，用于自适应窗口大小。"""
        try:
            # 不在这里创建新的 tk.Tk()，否则 macOS 上可能与 OpenCV HighGUI 冲突
            root = tk._default_root
            if root is None:
                raise RuntimeError("tk root not initialized")
            w = int(root.winfo_screenwidth())
            h = int(root.winfo_screenheight())
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
        return (
            int(os.environ.get("TRAJECTORY_FALLBACK_SCREEN_WIDTH", "1920")),
            int(os.environ.get("TRAJECTORY_FALLBACK_SCREEN_HEIGHT", "1080")),
        )

    def _compute_fit_size(self, src_w: int, src_h: int) -> tuple[int, int]:
        """
        按视频原始宽高比等比缩放，适配屏幕（左右两个窗口并排）。
        避免把竖屏视频硬拉成 640x480 导致画面压扁。
        """
        src_w = max(1, int(src_w))
        src_h = max(1, int(src_h))

        # 允许手动指定处理尺寸（仍保持比例）
        env_w = os.environ.get("TRAJECTORY_FRAME_WIDTH", "").strip()
        env_h = os.environ.get("TRAJECTORY_FRAME_HEIGHT", "").strip()
        if env_w and env_h:
            target_w, target_h = int(env_w), int(env_h)
            scale = min(target_w / src_w, target_h / src_h)
            return max(1, int(src_w * scale)), max(1, int(src_h * scale))

        screen_w, screen_h = self._get_screen_size()
        margin_x = int(os.environ.get("TRAJECTORY_SCREEN_MARGIN_X", "60"))
        margin_y = int(os.environ.get("TRAJECTORY_SCREEN_MARGIN_Y", "100"))
        gap = int(os.environ.get("TRAJECTORY_WINDOW_GAP", "20"))

        max_each_w = (screen_w - margin_x * 2 - gap) // 2
        max_each_h = screen_h - margin_y * 2
        max_each_w = min(max_each_w, int(os.environ.get("TRAJECTORY_MAX_WINDOW_WIDTH", "900")))
        max_each_h = min(max_each_h, int(os.environ.get("TRAJECTORY_MAX_WINDOW_HEIGHT", "980")))

        scale = min(max_each_w / src_w, max_each_h / src_h, 1.0)
        min_scale = float(os.environ.get("TRAJECTORY_MIN_SCALE", "0.25"))
        scale = max(scale, min_scale)

        fit_w = max(1, int(src_w * scale))
        fit_h = max(1, int(src_h * scale))
        max_process_w = int(os.environ.get("TRAJECTORY_MAX_PROCESS_WIDTH", "960"))
        if fit_w > max_process_w > 0:
            cap_scale = max_process_w / fit_w
            fit_w = max(1, int(fit_w * cap_scale))
            fit_h = max(1, int(fit_h * cap_scale))
        return fit_w, fit_h

    def _configure_display_from_video(self, src_w: int, src_h: int) -> None:
        """根据视频原始尺寸配置处理帧、窗口和轨迹线粗细。"""
        self._source_video_size = (src_w, src_h)
        self.FRAME_WIDTH, self.FRAME_HEIGHT = self._compute_fit_size(src_w, src_h)

        env_win_w = os.environ.get("TRAJECTORY_WINDOW_WIDTH", "").strip()
        env_win_h = os.environ.get("TRAJECTORY_WINDOW_HEIGHT", "").strip()
        if env_win_w and env_win_h:
            self.WINDOW_WIDTH = int(env_win_w)
            self.WINDOW_HEIGHT = int(env_win_h)
        else:
            self.WINDOW_WIDTH = self.FRAME_WIDTH
            self.WINDOW_HEIGHT = self.FRAME_HEIGHT

        self.TRACK_WIDTH = int(os.environ.get("TRAJECTORY_TRACK_WIDTH", str(self.TRACK_WIDTH)))
        print(
            f"视频原始尺寸: {src_w}x{src_h} -> 显示尺寸: {self.FRAME_WIDTH}x{self.FRAME_HEIGHT} "
            f"(比例 {self.FRAME_WIDTH / src_w:.3f})"
        )

    def _calibrate_track_width_from_bbox(self, bbox) -> None:
        """
        用用户选中的机器 ROI 估算涂抹宽度。
        真实运动轨迹用细中心线；覆盖率用机器宽度对应的粗线。
        """
        if not bbox or not any(bbox):
            return
        if self.MANUAL_TRACK_WIDTH:
            print(f"使用手动设置的涂抹宽度: {self.TRACK_WIDTH}px")
            return
        _, _, w, h = [int(v) for v in bbox]
        roi_size = max(1, max(w, h))
        scale = float(os.environ.get("TRAJECTORY_BRUSH_SCALE", "1.0"))
        min_w = int(os.environ.get("TRAJECTORY_MIN_TRACK_WIDTH", "6"))
        max_w = int(os.environ.get("TRAJECTORY_MAX_TRACK_WIDTH", "160"))
        self.TRACK_WIDTH = max(min_w, min(max_w, int(roi_size * scale)))
        print(f"涂抹宽度已按机器 ROI 自动校准: {self.TRACK_WIDTH}px (ROI={w}x{h}, scale={scale})")

    def _create_feature_detector(self):
        """创建 ORB 特征点检测器。ORB 对目标远近导致的尺度变化更稳。"""
        try:
            return cv2.ORB_create(nfeatures=self.ORB_FEATURES)
        except Exception:
            return None

    def _extract_orb_descriptor(self, image):
        detector = self._create_feature_detector()
        if detector is None or image is None or image.size == 0:
            return None, 0
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            keypoints, descriptor = detector.detectAndCompute(gray, None)
            return descriptor, len(keypoints or [])
        except Exception:
            return None, 0

    def _feature_match_score(self, descriptors_list, crop) -> tuple[float, int]:
        """
        用 ORB 特征点判断是不是同一台设备。
        返回 0~1 的匹配分数和有效匹配数；ROI 很小时可能特征较少，此时仅作为辅助分。
        """
        if not descriptors_list or crop is None or crop.size == 0:
            return 0.0, 0
        crop_desc, crop_kp_count = self._extract_orb_descriptor(crop)
        if crop_desc is None or crop_kp_count == 0:
            return 0.0, 0

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        best_score = 0.0
        best_good = 0
        for base_desc in descriptors_list:
            if base_desc is None or len(base_desc) < 2 or len(crop_desc) < 2:
                continue
            try:
                matches = matcher.knnMatch(base_desc, crop_desc, k=2)
            except Exception:
                continue
            good = []
            for pair in matches:
                if len(pair) < 2:
                    continue
                m, n = pair
                if m.distance < 0.78 * n.distance:
                    good.append(m)
            norm = max(8, min(len(base_desc), len(crop_desc)))
            score = min(1.0, len(good) / norm)
            if score > best_score:
                best_score = score
                best_good = len(good)
        return best_score, best_good

    def _is_valid_track_point(self, center_point, bbox, last_point, contour) -> tuple[bool, str]:
        """
        防止目标丢失后漂移：点必须在编辑区域内，且相邻跳变不能异常过大。
        """
        if center_point is None:
            return False, "center_point 为空"

        x, y = center_point
        if x < 0 or y < 0 or x >= self.FRAME_WIDTH or y >= self.FRAME_HEIGHT:
            return False, "中心点超出画面"

        if contour is not None and cv2.pointPolygonTest(contour, (x, y), False) < 0:
            return False, "中心点离开绘制区域"

        if last_point is not None and bbox is not None:
            _, _, w, h = [int(v) for v in bbox]
            object_diag = max(10.0, (w * w + h * h) ** 0.5)
            max_jump = max(
                object_diag * self.MAX_JUMP_RATIO,
                float(os.environ.get("TRAJECTORY_MIN_MAX_JUMP_PX", "30")),
            )
            dx = x - last_point[0]
            dy = y - last_point[1]
            jump = (dx * dx + dy * dy) ** 0.5
            if jump > max_jump:
                return False, f"跳变过大 jump={jump:.1f}px > {max_jump:.1f}px"

        return True, ""

    def _get_contour_bbox(self, contour, margin: int = 0) -> tuple[int, int, int, int]:
        """返回轮廓外接矩形，用于在泳池区域内扩大重识别搜索范围。"""
        if contour is None:
            return 0, 0, self.FRAME_WIDTH, self.FRAME_HEIGHT
        x, y, w, h = cv2.boundingRect(contour)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(self.FRAME_WIDTH, x + w + margin)
        y2 = min(self.FRAME_HEIGHT, y + h + margin)
        return x1, y1, x2, y2

    def _extract_identity_features(self, frame, bbox):
        if frame is None or bbox is None or not any(bbox):
            return None
        x, y, w, h = [int(v) for v in bbox]
        x = max(0, x)
        y = max(0, y)
        w = max(1, min(w, self.FRAME_WIDTH - x))
        h = max(1, min(h, self.FRAME_HEIGHT - y))
        roi = frame[y:y + h, x:x + w]
        if roi.size == 0:
            return None

        gray_template = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        descriptor, keypoint_count = self._extract_orb_descriptor(roi)
        return {
            "template": gray_template,
            "hist": hist,
            "descriptor": descriptor,
            "keypoint_count": keypoint_count,
            "bbox": (x, y, w, h),
            "size": (w, h),
        }

    def _build_device_identity(self, frame, bbox, device_id: int, pool_search_bbox=None) -> dict | None:
        """
        第一次框选设备时建立“设备身份模板”。
        后续跟丢后用这个模板在泳池区域内重新识别同一个设备。
        """
        features = self._extract_identity_features(frame, bbox)
        if features is None:
            return None
        x, y, w, h = features["bbox"]
        identity = {
            "id": device_id,
            "templates": [features["template"]],
            "hists": [features["hist"]],
            "descriptors": [features["descriptor"]] if features.get("descriptor") is not None else [],
            "size": (w, h),
            "last_bbox": (x, y, w, h),
            "last_update_frame": 0,
            "grace_frames": 0,
            "lost_for_frames": 0,
        }
        if pool_search_bbox is not None:
            identity["pool_search_bbox"] = pool_search_bbox
        print(f"已建立设备ID={device_id} 的识别模板，ROI={w}x{h}, 特征点={features.get('keypoint_count', 0)}")
        return identity

    def _update_device_identity(self, frame, bbox, identity: dict, frame_count: int) -> None:
        """稳定跟踪时补充模板，适应光照/角度变化，减少中途丢轨。"""
        if not identity:
            return
        if frame_count - int(identity.get("last_update_frame", 0)) < self.IDENTITY_TEMPLATE_UPDATE_INTERVAL:
            return
        features = self._extract_identity_features(frame, bbox)
        if features is None:
            return

        identity["templates"].append(features["template"])
        identity["hists"].append(features["hist"])
        if features.get("descriptor") is not None:
            identity.setdefault("descriptors", []).append(features["descriptor"])
        if len(identity["templates"]) > self.IDENTITY_MAX_TEMPLATES:
            identity["templates"] = identity["templates"][-self.IDENTITY_MAX_TEMPLATES:]
            identity["hists"] = identity["hists"][-self.IDENTITY_MAX_TEMPLATES:]
            identity["descriptors"] = identity.get("descriptors", [])[-self.IDENTITY_MAX_TEMPLATES:]
        identity["last_bbox"] = features["bbox"]
        identity["size"] = features["size"]
        identity["last_update_frame"] = frame_count

    def _find_device_identity(self, frame, identity: dict, contour):
        """
        目标丢失后，使用模板匹配 + 颜色直方图校验找回同一个设备。
        找不到则返回 None，不画任何轨迹。
        """
        if frame is None or not identity:
            return None

        templates = identity.get("templates") or []
        hists = identity.get("hists") or []
        descriptors = identity.get("descriptors") or []
        if not templates or not hists:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        search_regions = []
        predicted_bbox = identity.get("predicted_bbox")
        if predicted_bbox:
            px, py, pw, ph = [int(v) for v in predicted_bbox]
            margin = self.PREDICTIVE_SEARCH_MARGIN
            x1 = max(0, px - margin)
            y1 = max(0, py - margin)
            x2 = min(self.FRAME_WIDTH, px + pw + margin)
            y2 = min(self.FRAME_HEIGHT, py + ph + margin)
            search_regions.append((x1, y1, x2, y2, "predicted"))

        last_bbox = identity.get("last_bbox")
        if last_bbox:
            lx, ly, lw, lh = [int(v) for v in last_bbox]
            margin = self.REID_SEARCH_MARGIN
            x1 = max(0, lx - margin)
            y1 = max(0, ly - margin)
            x2 = min(self.FRAME_WIDTH, lx + lw + margin)
            y2 = min(self.FRAME_HEIGHT, ly + lh + margin)
            search_regions.append((x1, y1, x2, y2, "local"))

        lost_for_frames = int(identity.get("lost_for_frames", 0))
        if lost_for_frames >= self.REID_POOL_WIDE_AFTER_FRAMES:
            pool_bbox = identity.get("pool_search_bbox")
            if pool_bbox:
                px1, py1, px2, py2 = pool_bbox
                search_regions.append((px1, py1, px2, py2, "pool"))

        allow_global = self.REID_ALLOW_GLOBAL_SEARCH and lost_for_frames >= self.REID_GLOBAL_AFTER_FRAMES
        if allow_global or not search_regions:
            search_regions.append((0, 0, self.FRAME_WIDTH, self.FRAME_HEIGHT, "global"))

        best = None
        best_score = -1.0
        for template in templates:
            if template is None or template.size == 0:
                continue
            base_h, base_w = template.shape[:2]
            for scale in self.REID_SCALE_FACTORS:
                w = max(8, int(base_w * scale))
                h = max(8, int(base_h * scale))
                if frame.shape[0] < h or frame.shape[1] < w:
                    continue
                scaled_template = cv2.resize(template, (w, h), interpolation=cv2.INTER_AREA)

                for rx1, ry1, rx2, ry2, region_name in search_regions:
                    search_gray = gray[ry1:ry2, rx1:rx2]
                    if search_gray.shape[0] < h or search_gray.shape[1] < w:
                        continue
                    try:
                        res = cv2.matchTemplate(search_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
                    except Exception:
                        continue

                    flat = res.ravel()
                    candidate_count = min(12, flat.size)
                    if candidate_count <= 0:
                        continue
                    candidate_indices = np.argpartition(flat, -candidate_count)[-candidate_count:]

                    for idx in candidate_indices:
                        cy, cx = np.unravel_index(idx, res.shape)
                        x = int(cx + rx1)
                        y = int(cy + ry1)
                        template_score = float(res[cy, cx])
                        center = (int(x + w / 2), int(y + h / 2))
                        if contour is not None and cv2.pointPolygonTest(contour, center, False) < 0:
                            continue

                        crop = frame[y:y + h, x:x + w]
                        if crop.size == 0:
                            continue
                        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
                        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                        hist_score = max(float(cv2.compareHist(base_hist, hist, cv2.HISTCMP_CORREL)) for base_hist in hists)
                        feature_score, good_matches = self._feature_match_score(descriptors, crop)
                        combined_score = (
                            template_score * 0.55
                            + max(0.0, hist_score) * 0.15
                            + feature_score * 0.30
                        )

                        if (
                                template_score >= self.REID_TEMPLATE_THRESHOLD
                                and hist_score >= self.REID_HIST_THRESHOLD
                                and feature_score >= self.REID_FEATURE_THRESHOLD
                                and combined_score > best_score
                        ):
                            best_score = combined_score
                            best = (
                                int(x), int(y), int(w), int(h), combined_score,
                                template_score, hist_score, feature_score, good_matches, region_name, scale
                            )

        if not best or best_score < self.REID_MATCH_THRESHOLD:
            return None
        x, y, w, h, combined_score, template_score, hist_score, feature_score, good_matches, region_name, scale = best
        print(
            f"设备ID={identity['id']} 重新识别成功: score={combined_score:.3f} "
            f"(template={template_score:.3f}, hist={hist_score:.3f}, "
            f"feature={feature_score:.3f}/{good_matches}, region={region_name}, scale={scale:.2f})"
        )
        return (x, y, w, h)

    def _score_bbox_against_identity(self, frame, bbox, identity: dict):
        """
        给当前跟踪框做身份校验。
        跟踪器可能漂到水面/背景，必须与最初框选设备的模板和颜色都足够相似才允许画轨迹。
        """
        if frame is None or bbox is None or not identity:
            return 0.0, 0.0, 0.0

        x, y, w, h = [int(v) for v in bbox]
        if w <= 0 or h <= 0:
            return 0.0, 0.0, 0.0
        x = max(0, x)
        y = max(0, y)
        w = min(w, self.FRAME_WIDTH - x)
        h = min(h, self.FRAME_HEIGHT - y)
        if w <= 0 or h <= 0:
            return 0.0, 0.0, 0.0

        crop = frame[y:y + h, x:x + w]
        templates = identity.get("templates") or []
        hists = identity.get("hists") or []
        descriptors = identity.get("descriptors") or []
        if crop.size == 0 or not templates or not hists:
            return 0.0, 0.0, 0.0, 0.0

        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        template_score = 0.0
        for template in templates:
            try:
                tmpl_h, tmpl_w = template.shape[:2]
                resized_crop = gray_crop
                if gray_crop.shape[:2] != (tmpl_h, tmpl_w):
                    resized_crop = cv2.resize(gray_crop, (tmpl_w, tmpl_h), interpolation=cv2.INTER_AREA)
                template_score = max(
                    template_score,
                    float(cv2.matchTemplate(resized_crop, template, cv2.TM_CCOEFF_NORMED)[0][0]),
                )
            except Exception:
                continue

        try:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
            hist_score = max(float(cv2.compareHist(base_hist, hist, cv2.HISTCMP_CORREL)) for base_hist in hists)
        except Exception:
            hist_score = 0.0

        feature_score, _ = self._feature_match_score(descriptors, crop)
        combined_score = (
            template_score * 0.55
            + max(0.0, hist_score) * 0.15
            + feature_score * 0.30
        )
        return combined_score, template_score, hist_score, feature_score

    def _bbox_mask_overlap_ratio(self, bbox, pool_mask) -> float:
        if bbox is None or pool_mask is None:
            return 1.0
        x, y, w, h = [int(v) for v in bbox]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(self.FRAME_WIDTH, x + max(1, w))
        y2 = min(self.FRAME_HEIGHT, y + max(1, h))
        if x2 <= x1 or y2 <= y1:
            return 0.0
        roi = pool_mask[y1:y2, x1:x2]
        return cv2.countNonZero(roi) / max(1, roi.size)

    def _bbox_motion_ratio(self, bbox, motion_mask) -> float:
        if bbox is None or motion_mask is None:
            return 1.0
        x, y, w, h = [int(v) for v in bbox]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(self.FRAME_WIDTH, x + max(1, w))
        y2 = min(self.FRAME_HEIGHT, y + max(1, h))
        if x2 <= x1 or y2 <= y1:
            return 0.0
        roi = motion_mask[y1:y2, x1:x2]
        return cv2.countNonZero(roi) / max(1, roi.size)

    def _is_bbox_still_target(
            self,
            frame,
            bbox,
            identity: dict,
            motion_mask=None,
            pool_mask=None,
            check_identity: bool = True,
    ) -> tuple[bool, str]:
        """
        bbox 模式下的丢失判定。
        tracker 有时目标离开后仍给出一个漂移框，必须用弱身份分 + 尺寸约束拦截。
        """
        if not identity or bbox is None:
            return True, ""

        x, y, w, h = [int(v) for v in bbox]
        base_w, base_h = identity.get("size", (w, h))
        base_area = max(1, int(base_w) * int(base_h))
        cur_area = max(1, w * h)
        area_ratio = cur_area / base_area
        if area_ratio < self.BBOX_SIZE_MIN_RATIO or area_ratio > self.BBOX_SIZE_MAX_RATIO:
            return False, f"目标框尺寸异常 area_ratio={area_ratio:.2f}"

        pool_overlap = self._bbox_mask_overlap_ratio(bbox, pool_mask)
        if pool_overlap < self.MIN_POOL_OVERLAP_RATIO:
            return False, f"目标框不在泳池区域内 overlap={pool_overlap:.2f}"

        grace_frames = int(identity.get("grace_frames", 0))
        need_motion = (
                self.REQUIRE_MOTION_IN_BBOX
                and motion_mask is not None
                and grace_frames <= 0
        )
        if need_motion:
            motion_ratio = self._bbox_motion_ratio(bbox, motion_mask)
            if motion_ratio < self.MIN_BBOX_MOTION_RATIO:
                return False, f"目标框内缺少运动 motion={motion_ratio:.4f}"

        if not check_identity:
            return True, ""

        identity_score, template_score, hist_score, feature_score = self._score_bbox_against_identity(
            frame, bbox, identity
        )
        if (
                identity_score < self.BBOX_LOST_IDENTITY_THRESHOLD
                or template_score < self.BBOX_LOST_TEMPLATE_THRESHOLD
        ):
            return (
                False,
                f"目标框疑似漂移 score={identity_score:.3f} "
                f"(template={template_score:.3f}, hist={hist_score:.3f}, feature={feature_score:.3f})",
            )
        return True, ""

    def _need_motion_mask(self, tracker, lost_frames: int, device_identities, active_device_id) -> bool:
        """仅在重锁定或需要运动校验时才计算帧差，减少每帧开销。"""
        if tracker is None or lost_frames > 0:
            return True
        if not self.REQUIRE_MOTION_IN_BBOX or active_device_id not in device_identities:
            return False
        identity = device_identities[active_device_id]
        if int(identity.get("grace_frames", 0)) > 0:
            return False
        return True

    def _validate_reid_candidate(self, frame, bbox, identity: dict, motion_mask=None, pool_mask=None) -> tuple[bool, str]:
        """自动重锁定候选必须同时满足身份相似、泳池区域和运动特征，过滤水面波纹误检。"""
        if frame is None or bbox is None or not identity:
            return False, "候选为空"

        bbox_valid, reason = self._is_bbox_still_target(frame, bbox, identity, motion_mask, pool_mask)
        if not bbox_valid and "缺少运动" not in reason:
            return False, reason

        if motion_mask is not None:
            motion_ratio = self._bbox_motion_ratio(bbox, motion_mask)
            if motion_ratio < self.REID_CANDIDATE_MIN_MOTION_RATIO:
                return False, f"候选区域运动不足 motion={motion_ratio:.4f}"

        identity_score, template_score, hist_score, feature_score = self._score_bbox_against_identity(
            frame, bbox, identity
        )
        if (
                identity_score < self.REID_CANDIDATE_MATCH_THRESHOLD
                or template_score < self.REID_CANDIDATE_TEMPLATE_THRESHOLD
        ):
            return (
                False,
                f"候选身份分数不足 score={identity_score:.3f} "
                f"(template={template_score:.3f}, hist={hist_score:.3f}, feature={feature_score:.3f})",
            )
        return True, ""

    def _bbox_in_search_region(self, bbox, identity: dict) -> bool:
        """候选是否落在预测/上次位置附近，用于分级快速确认。"""
        if bbox is None or not identity:
            return False
        x, y, w, h = [int(v) for v in bbox]
        cx, cy = x + w / 2, y + h / 2
        for key, margin in (("predicted_bbox", self.PREDICTIVE_SEARCH_MARGIN), ("last_bbox", self.REID_SEARCH_MARGIN)):
            ref = identity.get(key)
            if not ref:
                continue
            rx, ry, rw, rh = [int(v) for v in ref]
            if (
                    rx - margin <= cx <= rx + rw + margin
                    and ry - margin <= cy <= ry + rh + margin
            ):
                return True
        return False

    def _required_candidate_confirm_frames(self, identity_score: float, template_score: float, in_near_region: bool) -> int:
        """高置信度或预测区域内候选可更快确认，泳池远处候选仍保守。"""
        if (
                identity_score >= self.REID_CANDIDATE_HIGH_SCORE
                and template_score >= self.REID_CANDIDATE_TEMPLATE_THRESHOLD
        ):
            return self.CANDIDATE_CONFIRM_FRAMES_HIGH
        if in_near_region and identity_score >= self.REID_CANDIDATE_MATCH_THRESHOLD:
            return self.CANDIDATE_CONFIRM_FRAMES
        # 泳池远处再现的候选更保守，避免误锁水面。
        return self.CANDIDATE_CONFIRM_FRAMES + 1

    def _find_device_by_motion_blob(self, frame, identity: dict, contour, motion_mask=None, pool_mask=None):
        """
        运动优先重锁定：在泳池/预测区域内找与设备尺寸、颜色接近的运动块。
        比全图模板匹配更快，适合目标消失后再出现的场景。
        """
        if frame is None or not identity or motion_mask is None:
            return None

        lost_for_frames = int(identity.get("lost_for_frames", 0))
        established = int(identity.get("established_track_frames", 0))
        if lost_for_frames < self.MOTION_REID_AFTER_FRAMES or established < self.MIN_ESTABLISHED_TRACK_FRAMES:
            return None

        base_w, base_h = identity.get("size", (0, 0))
        if base_w <= 0 or base_h <= 0:
            return None
        base_area = max(1, int(base_w) * int(base_h))
        hists = identity.get("hists") or []
        if not hists:
            return None

        if pool_mask is not None:
            motion_roi = cv2.bitwise_and(motion_mask, pool_mask)
        else:
            motion_roi = motion_mask

        search_regions = []
        predicted_bbox = identity.get("predicted_bbox")
        if predicted_bbox:
            px, py, pw, ph = [int(v) for v in predicted_bbox]
            margin = self.PREDICTIVE_SEARCH_MARGIN
            search_regions.append((
                max(0, px - margin), max(0, py - margin),
                min(self.FRAME_WIDTH, px + pw + margin),
                min(self.FRAME_HEIGHT, py + ph + margin),
                "motion-predicted",
            ))
        last_bbox = identity.get("last_bbox")
        if last_bbox:
            lx, ly, lw, lh = [int(v) for v in last_bbox]
            margin = self.REID_SEARCH_MARGIN
            search_regions.append((
                max(0, lx - margin), max(0, ly - margin),
                min(self.FRAME_WIDTH, lx + lw + margin),
                min(self.FRAME_HEIGHT, ly + lh + margin),
                "motion-local",
            ))
        if lost_for_frames >= self.REID_POOL_WIDE_AFTER_FRAMES:
            pool_bbox = identity.get("pool_search_bbox")
            if pool_bbox:
                px1, py1, px2, py2 = pool_bbox
                search_regions.append((px1, py1, px2, py2, "motion-pool"))

        best = None
        best_score = -1.0
        kernel = np.ones((3, 3), np.uint8)
        for x1, y1, x2, y2, region_name in search_regions:
            roi_motion = motion_roi[y1:y2, x1:x2]
            if roi_motion.size == 0:
                continue
            merged = cv2.morphologyEx(roi_motion, cv2.MORPH_CLOSE, kernel, iterations=2)
            contours_found, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours_found:
                bx, by, bw, bh = cv2.boundingRect(c)
                if bw < 8 or bh < 8:
                    continue
                gx, gy = x1 + bx, y1 + by
                center = (int(gx + bw / 2), int(gy + bh / 2))
                if contour is not None and cv2.pointPolygonTest(contour, center, False) < 0:
                    continue
                area_ratio = (bw * bh) / base_area
                if area_ratio < self.BBOX_SIZE_MIN_RATIO or area_ratio > self.BBOX_SIZE_MAX_RATIO:
                    continue
                motion_ratio = self._bbox_motion_ratio((gx, gy, bw, bh), motion_mask)
                if motion_ratio < self.REID_CANDIDATE_MIN_MOTION_RATIO:
                    continue
                crop = frame[gy:gy + bh, gx:gx + bw]
                if crop.size == 0:
                    continue
                try:
                    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
                    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                    hist_score = max(float(cv2.compareHist(base_hist, hist, cv2.HISTCMP_CORREL)) for base_hist in hists)
                except Exception:
                    hist_score = 0.0
                identity_score, template_score, _, _ = self._score_bbox_against_identity(
                    frame, (gx, gy, bw, bh), identity
                )
                score = (
                    motion_ratio * 0.35
                    + max(0.0, hist_score) * 0.25
                    + identity_score * 0.40
                )
                if (
                        score > best_score
                        and hist_score >= self.REID_HIST_THRESHOLD
                        and identity_score >= self.REID_CANDIDATE_MATCH_THRESHOLD * 0.85
                ):
                    best_score = score
                    best = (gx, gy, bw, bh, score, motion_ratio, hist_score, identity_score, region_name)

        if not best:
            return None
        gx, gy, bw, bh, score, motion_ratio, hist_score, identity_score, region_name = best
        print(
            f"设备ID={identity['id']} 运动块重锁定: score={score:.3f} "
            f"(motion={motion_ratio:.3f}, hist={hist_score:.3f}, identity={identity_score:.3f}, region={region_name})"
        )
        return (gx, gy, bw, bh)

    def _try_reidentify_device(self, frame, identity: dict, contour, motion_mask=None, pool_mask=None, commit: bool = False):
        lost_for_frames = int(identity.get("lost_for_frames", 0))
        established = int(identity.get("established_track_frames", 0))

        bbox = None
        if motion_mask is not None:
            bbox = self._find_device_by_motion_blob(frame, identity, contour, motion_mask, pool_mask)
        if not bbox:
            bbox = self._find_device_identity(frame, identity, contour)
        use_color_blob = self.USE_COLOR_BLOB_REID or (
                lost_for_frames >= self.REID_COLOR_BLOB_AFTER_FRAMES
                and established >= self.MIN_ESTABLISHED_TRACK_FRAMES
        )
        if not bbox and use_color_blob:
            bbox = self._find_device_by_color_blob(frame, identity, contour, motion_mask, pool_mask)
        if not bbox:
            return None, None

        valid, reason = self._validate_reid_candidate(frame, bbox, identity, motion_mask, pool_mask)
        if not valid:
            return None, None

        x, y, w, h = [int(v) for v in bbox]
        center_point = (int(x + w / 2), int(y + h / 2))
        if commit:
            identity["last_bbox"] = (x, y, w, h)
            identity.pop("predicted_bbox", None)
            identity["lost_for_frames"] = 0
        return bbox, center_point

    def _find_device_by_color_blob(self, frame, identity: dict, contour, motion_mask=None, pool_mask=None):
        """
        模板匹配失败时的兜底：在绘制区域内找与设备颜色/尺寸接近的独立色块。
        适用于泳池里深色机器目标，解决目标重新出现但模板分数偏低导致无法自动锁定的问题。
        """
        if frame is None or not identity:
            return None

        base_w, base_h = identity.get("size", (0, 0))
        if base_w <= 0 or base_h <= 0:
            return None
        base_area = max(1, int(base_w) * int(base_h))

        # 搜索区域沿用 predicted/local/global 逻辑
        search_regions = []
        predicted_bbox = identity.get("predicted_bbox")
        if predicted_bbox:
            px, py, pw, ph = [int(v) for v in predicted_bbox]
            margin = self.PREDICTIVE_SEARCH_MARGIN
            search_regions.append((
                max(0, px - margin),
                max(0, py - margin),
                min(self.FRAME_WIDTH, px + pw + margin),
                min(self.FRAME_HEIGHT, py + ph + margin),
                "predicted-blob",
            ))
        last_bbox = identity.get("last_bbox")
        if last_bbox:
            lx, ly, lw, lh = [int(v) for v in last_bbox]
            margin = self.REID_SEARCH_MARGIN
            search_regions.append((
                max(0, lx - margin),
                max(0, ly - margin),
                min(self.FRAME_WIDTH, lx + lw + margin),
                min(self.FRAME_HEIGHT, ly + lh + margin),
                "local-blob",
            ))
        lost_for_frames = int(identity.get("lost_for_frames", 0))
        if lost_for_frames >= self.REID_POOL_WIDE_AFTER_FRAMES:
            pool_bbox = identity.get("pool_search_bbox")
            if pool_bbox:
                px1, py1, px2, py2 = pool_bbox
                search_regions.append((px1, py1, px2, py2, "pool-blob"))
        if self.REID_ALLOW_GLOBAL_SEARCH and lost_for_frames >= self.REID_GLOBAL_AFTER_FRAMES:
            search_regions.append((0, 0, self.FRAME_WIDTH, self.FRAME_HEIGHT, "global-blob"))

        hists = identity.get("hists") or []
        best = None
        best_score = -1.0
        for x1, y1, x2, y2, region_name in search_regions:
            roi = frame[y1:y2, x1:x2]
            if roi.size == 0:
                continue
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # 机器通常比泳池水面暗，用暗色阈值提候选；阈值较宽，后续再用颜色/尺寸过滤。
            _, binary = cv2.threshold(gray, 105, 255, cv2.THRESH_BINARY_INV)
            kernel = np.ones((3, 3), np.uint8)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
            contours_found, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in contours_found:
                bx, by, bw, bh = cv2.boundingRect(c)
                if bw < 8 or bh < 8:
                    continue
                gx, gy = x1 + bx, y1 + by
                center = (int(gx + bw / 2), int(gy + bh / 2))
                if contour is not None and cv2.pointPolygonTest(contour, center, False) < 0:
                    continue
                pool_overlap = self._bbox_mask_overlap_ratio((gx, gy, bw, bh), pool_mask)
                if pool_overlap < self.MIN_POOL_OVERLAP_RATIO:
                    continue
                if self.REQUIRE_MOTION_IN_BBOX and motion_mask is not None:
                    motion_ratio = self._bbox_motion_ratio((gx, gy, bw, bh), motion_mask)
                    if motion_ratio < self.MIN_BBOX_MOTION_RATIO:
                        continue

                area_ratio = (bw * bh) / base_area
                if area_ratio < self.BBOX_SIZE_MIN_RATIO or area_ratio > self.BBOX_SIZE_MAX_RATIO:
                    continue

                crop = frame[gy:gy + bh, gx:gx + bw]
                if crop.size == 0:
                    continue
                try:
                    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
                    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                    hist_score = max(float(cv2.compareHist(base_hist, hist, cv2.HISTCMP_CORREL)) for base_hist in hists)
                except Exception:
                    hist_score = 0.0

                size_score = max(0.0, 1.0 - abs(1.0 - area_ratio))
                score = hist_score * 0.7 + size_score * 0.3
                if score > best_score and hist_score >= self.REID_HIST_THRESHOLD:
                    best_score = score
                    best = (gx, gy, bw, bh, score, hist_score, area_ratio, region_name)

        if not best:
            return None
        gx, gy, bw, bh, score, hist_score, area_ratio, region_name = best
        print(
            f"设备ID={identity['id']} 颜色候选重新锁定: score={score:.3f} "
            f"(hist={hist_score:.3f}, area_ratio={area_ratio:.2f}, region={region_name})"
        )
        return (gx, gy, bw, bh)

    def _update_predicted_bbox(self, identity: dict, last_point, last_bbox, velocity, missing_frames: int, contour):
        """
        目标进入死角/离开画面后，不能绘制真实轨迹，但可以预测下一次出现位置，
        用预测位置提高自动重识别成功率。
        """
        if not self.PREDICTIVE_REID or not identity or last_point is None or last_bbox is None:
            return
        if missing_frames <= 0 or missing_frames > self.MAX_PREDICT_FRAMES:
            identity.pop("predicted_bbox", None)
            identity["lost_for_frames"] = missing_frames
            return

        _, _, w, h = [int(v) for v in last_bbox]
        vx, vy = velocity
        px = int(last_point[0] + vx * missing_frames - w / 2)
        py = int(last_point[1] + vy * missing_frames - h / 2)
        px = max(0, min(self.FRAME_WIDTH - w, px))
        py = max(0, min(self.FRAME_HEIGHT - h, py))
        center = (int(px + w / 2), int(py + h / 2))
        if contour is not None and cv2.pointPolygonTest(contour, center, False) < 0:
            # 预测点离开泳池区域时不要扩大误搜索。
            identity.pop("predicted_bbox", None)
            identity["lost_for_frames"] = missing_frames
            return
        identity["predicted_bbox"] = (px, py, w, h)
        identity["lost_for_frames"] = missing_frames

    def _draw_machine_footprint(self, canvas, bbox) -> None:
        """
        按机器当前外接框绘制真实经过区域。
        覆盖率只统计这些 footprint，不再用粗线连接中心点。
        """
        if bbox is None:
            return
        x, y, w, h = [int(v) for v in bbox]
        if w <= 0 or h <= 0:
            return

        cx = int(x + w / 2)
        cy = int(y + h / 2)
        # footprint 模式下，涂抹区域按用户设置的“涂抹轨迹宽度”绘制；
        # 这样机器没经过的区域不会被粗中心线补出来，宽度也可控。
        footprint_width = max(1, int(self.TRACK_WIDTH * self.FOOTPRINT_SCALE))
        sw = footprint_width
        sh = footprint_width
        x1 = max(0, int(cx - sw / 2))
        y1 = max(0, int(cy - sh / 2))
        x2 = min(self.FRAME_WIDTH - 1, int(cx + sw / 2))
        y2 = min(self.FRAME_HEIGHT - 1, int(cy + sh / 2))

        radius = max(1, footprint_width // 2)
        if self.FOOTPRINT_USE_CIRCLE:
            cv2.circle(canvas, (cx, cy), radius, (0, 255, 0), -1, lineType=cv2.LINE_8)
        else:
            axes = (max(1, (x2 - x1) // 2), max(1, (y2 - y1) // 2))
            cv2.ellipse(canvas, (cx, cy), axes, 0, 0, 360, (0, 255, 0), -1)

    def _compute_coverage_rate(self, masked_track_layer, pool_mask, polygon_area: int) -> float:
        """用向量化统计绿色覆盖像素，替代逐点遍历。"""
        if polygon_area <= 0 or masked_track_layer is None or pool_mask is None:
            return 0.0
        green = masked_track_layer[:, :, 1]
        covered_mask = (green == 255) & (masked_track_layer[:, :, 0] == 0) & (pool_mask > 0)
        return float(np.count_nonzero(covered_mask)) / polygon_area * 100.0

    def _draw_incremental_tracks(
            self,
            track_layer,
            white_trail,
            footprint_segments,
            track_segments,
            drawn_footprint_count: int,
            drawn_line_count: int,
    ) -> tuple[int, int]:
        """只绘制新增 footprint/中心线，避免每帧重绘全部历史导致卡顿。"""
        flat_footprints = []
        for footprints in footprint_segments:
            if footprints:
                flat_footprints.extend(footprints)

        for idx in range(drawn_footprint_count, len(flat_footprints)):
            if self.COVERAGE_MODE == "footprint":
                self._draw_machine_footprint(track_layer, flat_footprints[idx])
        drawn_footprint_count = len(flat_footprints)

        line_idx = 0
        for segment in track_segments:
            for i in range(1, len(segment)):
                if line_idx >= drawn_line_count and segment[i - 1] and segment[i]:
                    if self.COVERAGE_MODE == "line":
                        cv2.line(
                            track_layer, segment[i - 1], segment[i], (0, 255, 0), self.TRACK_WIDTH
                        )
                    cv2.line(
                        white_trail, segment[i - 1], segment[i], (127, 127, 127), self.CENTERLINE_WIDTH
                    )
                line_idx += 1
        drawn_line_count = line_idx
        return drawn_footprint_count, drawn_line_count

    def _build_reconnect_bridge(self, start_point, end_point, bbox, contour):
        """
        目标丢失后重新找回时，自动连接最后有效点和重新锁定点。
        距离过远或穿出绘制区域则不连接，避免生成明显错误线。
        """
        if not self.CONNECT_REID_GAP or start_point is None or end_point is None or bbox is None:
            return [], []

        dx = end_point[0] - start_point[0]
        dy = end_point[1] - start_point[1]
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= 1:
            return [], []
        if dist > self.MAX_RECONNECT_DISTANCE:
            print(f"重连距离过远，跳过自动连接: {dist:.1f}px > {self.MAX_RECONNECT_DISTANCE:.1f}px")
            return [], []

        _, _, w, h = [int(v) for v in bbox]
        steps = max(2, int(dist / max(1.0, self.RECONNECT_STEP_PX)))
        bridge_points = []
        bridge_footprints = []
        for idx in range(1, steps + 1):
            t = idx / steps
            x = int(start_point[0] + dx * t)
            y = int(start_point[1] + dy * t)
            if contour is not None and cv2.pointPolygonTest(contour, (x, y), False) < 0:
                print("重连线经过绘制区域外，跳过自动连接")
                return [], []
            bridge_points.append((x, y))
            if self.RECONNECT_COVERAGE:
                bridge_footprints.append((int(x - w / 2), int(y - h / 2), w, h))
        print(f"目标重新锁定，已自动连接断点: {len(bridge_points)} 个插值点")
        return bridge_points, bridge_footprints

    def _bbox_iou(self, a, b) -> float:
        """计算两个 bbox 的重叠比例，用于判断候选红框是否稳定。"""
        if not a or not b:
            return 0.0
        ax, ay, aw, ah = [int(v) for v in a]
        bx, by, bw, bh = [int(v) for v in b]
        ax2, ay2 = ax + aw, ay + ah
        bx2, by2 = bx + bw, by + bh
        ix1, iy1 = max(ax, bx), max(ay, by)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        union = max(1, aw * ah + bw * bh - inter)
        return inter / union

    def _bbox_center_distance(self, a, b) -> float:
        """候选框移动时 IoU 可能低，用中心点距离辅助判断是否仍是同一候选目标。"""
        if not a or not b:
            return 999999.0
        ax, ay, aw, ah = [int(v) for v in a]
        bx, by, bw, bh = [int(v) for v in b]
        ac = (ax + aw / 2, ay + ah / 2)
        bc = (bx + bw / 2, by + bh / 2)
        dx = ac[0] - bc[0]
        dy = ac[1] - bc[1]
        return (dx * dx + dy * dy) ** 0.5

    def _resize_frame(self, frame):
        """等比缩放到当前处理尺寸（与窗口一致）。"""
        if frame is None:
            return frame
        h, w = frame.shape[:2]
        if w == self.FRAME_WIDTH and h == self.FRAME_HEIGHT:
            return frame
        return cv2.resize(
            frame,
            (self.FRAME_WIDTH, self.FRAME_HEIGHT),
            interpolation=cv2.INTER_AREA if w > self.FRAME_WIDTH else cv2.INTER_LINEAR,
        )

    def _setup_cv_window(self, window_name: str, offset_x: int = 0, offset_y: int = 50) -> None:
        """统一 OpenCV 窗口分辨率与位置，保证左右两个视频框一样大。"""
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        cv2.moveWindow(window_name, offset_x, offset_y)

    def _calc_window_layout(self) -> tuple[int, int, int]:
        """根据屏幕计算 Coverage / Tracking 窗口位置。"""
        screen_w, _ = self._get_screen_size()
        margin_x = int(os.environ.get("TRAJECTORY_SCREEN_MARGIN_X", "60"))
        gap = int(os.environ.get("TRAJECTORY_WINDOW_GAP", "20"))
        window_y = int(os.environ.get("TRAJECTORY_WINDOW_Y", "50"))

        total_w = self.WINDOW_WIDTH * 2 + gap
        start_x = max(margin_x, (screen_w - total_w) // 2)
        coverage_x = int(os.environ.get("TRAJECTORY_COVERAGE_X", str(start_x)))
        tracking_x = int(
            os.environ.get("TRAJECTORY_TRACKING_X", str(coverage_x + self.WINDOW_WIDTH + gap))
        )
        return coverage_x, tracking_x, window_y

    def create_tracker(self):
        """创建跟踪器"""
        try:
            # 在 OpenCV 4.8.0.76 中使用 legacy 模块创建跟踪器
            return cv2.legacy.TrackerCSRT_create()
        except AttributeError:
            try:
                return cv2.TrackerCSRT_create()
            except AttributeError:
                print(f"当前 OpenCV 版本 {cv2.__version__} 不支持跟踪器功能")
                print("将使用模板匹配兜底跟踪（建议仍安装 OpenCV contrib 模块）")
                return self.TemplateTracker()

    def process_video(self, video_path):
        try:
            frame_count = 0
            coverage_rate = 0
            if not os.path.exists(video_path):
                print(f"视频文件 {video_path} 不存在")
                return

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"无法打开视频文件 {video_path}")
                return

            ret, frame = cap.read()
            if not ret:
                print("无法读取视频文件")
                return

            video_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            if video_fps <= 0 or video_fps > 120:
                video_fps = 30.0

            src_h, src_w = frame.shape[:2]
            meta_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or src_w
            meta_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or src_h
            self._configure_display_from_video(max(src_w, meta_w), max(src_h, meta_h))
            frame = self._resize_frame(frame)
            coverage_x, tracking_x, window_y = self._calc_window_layout()

            tracker = None
            init_box = None
            all_track_points = []
            track_segments = []
            active_track_points = None
            footprint_segments = []
            active_footprints = None
            lost_frames = 0
            established_track_frames = 0
            identity_mismatch_frames = 0
            last_valid_point = None
            last_valid_bbox = None
            last_velocity = (0.0, 0.0)
            missing_frames = 0
            candidate_bbox = None
            candidate_center = None
            candidate_hits = 0
            candidate_required_confirm = self.CANDIDATE_CONFIRM_FRAMES
            candidate_miss_frames = 0
            last_relock_log_frame = 0
            drawn_footprint_count = 0
            drawn_line_count = 0
            device_identities = {}
            active_device_id = None
            next_device_id = 1

            polygon_points = []  # 存储多边形的点
            drawing_polygon = True  # 标记是否在绘制多边形

            def on_mouse(event, x, y, flags, param):
                nonlocal drawing_polygon
                if drawing_polygon:
                    if event == cv2.EVENT_LBUTTONDOWN:
                        polygon_points.append((x, y))
                    elif event == cv2.EVENT_RBUTTONDOWN and len(polygon_points) > 2:
                        # 右键点击完成闭环
                        drawing_polygon = False

            # 左侧 Coverage、右侧 Tracking，播放时统一窗口分辨率
            self._setup_cv_window("Tracking", offset_x=tracking_x, offset_y=window_y)
            cv2.setMouseCallback("Tracking", on_mouse)

            print("请使用鼠标左键点击绘制多边形区域，右键完成绘制")
            # 绘制多边形区域
            while drawing_polygon:
                temp_frame = frame.copy()
                if len(polygon_points) > 1:
                    for i in range(1, len(polygon_points)):
                        cv2.line(temp_frame, polygon_points[i - 1], polygon_points[i], (0, 255, 255), 2)
                    if len(polygon_points) > 2:
                        cv2.line(temp_frame, polygon_points[-1], polygon_points[0], (0, 255, 255), 2)

                cv2.imshow("Tracking", temp_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') and len(polygon_points) > 2:
                    drawing_polygon = False

            if len(polygon_points) < 3:
                print("多边形区域无效，至少需要3个点")
                return

            # 创建多边形掩码
            mask = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH), dtype=np.uint8)
            cv2.fillPoly(mask, [np.array(polygon_points, np.int32)], 255)
            polygon_area = cv2.countNonZero(mask)

            # 找到多边形的轮廓
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            pool_search_bbox = self._get_contour_bbox(
                contours[0] if contours else None,
                margin=self.REID_POOL_SEARCH_MARGIN,
            )
            mask_3ch = cv2.merge([mask, mask, mask])
            polygon_np = np.array(polygon_points, np.int32)
            track_layer = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)
            white_trail = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)

            print("按空格键选择要跟踪的目标，按 q 键退出")
            windows_ready = False
            prev_gray_for_motion = None
            prev_motion_masks = []
            last_motion_mask = None
            result_frame = None
            result_track_frame = None
            while True:
                loop_start = time.perf_counter()
                frame_count += 1
                if not ret:
                    print("视频播放完毕或读取失败")
                    break

                need_motion = self._need_motion_mask(
                    tracker, lost_frames, device_identities, active_device_id
                )
                motion_mask = None
                current_gray_for_motion = None
                if need_motion:
                    if frame_count % self.MOTION_CHECK_INTERVAL == 0 or last_motion_mask is None:
                        current_gray_for_motion = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        if prev_gray_for_motion is not None:
                            frame_diff = cv2.absdiff(current_gray_for_motion, prev_gray_for_motion)
                            _, motion_mask = cv2.threshold(
                                frame_diff, self.MOTION_DIFF_THRESHOLD, 255, cv2.THRESH_BINARY
                            )
                            motion_kernel = np.ones((3, 3), np.uint8)
                            motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, motion_kernel, iterations=1)
                            if self.MOTION_ACCUM_FRAMES > 1:
                                prev_motion_masks.append(motion_mask)
                                if len(prev_motion_masks) > self.MOTION_ACCUM_FRAMES:
                                    prev_motion_masks.pop(0)
                                if len(prev_motion_masks) > 1:
                                    motion_mask = prev_motion_masks[0].copy()
                                    for older in prev_motion_masks[1:]:
                                        motion_mask = cv2.bitwise_or(motion_mask, older)
                            last_motion_mask = motion_mask
                        prev_gray_for_motion = current_gray_for_motion
                    else:
                        motion_mask = last_motion_mask

                bbox = None
                bbox_draw_state = "none"
                candidate_draw_bbox = candidate_bbox
                if tracker:
                    success, bbox = tracker.update(frame)
                    if success and bbox is not None:
                        x, y, w, h = [int(v) for v in bbox]
                        center_point = (int(x + w / 2), int(y + h / 2))
                        last_point = active_track_points[-1] if active_track_points else None
                        is_valid, reason = self._is_valid_track_point(
                            center_point, bbox, last_point, contours[0] if contours else None
                        )
                        if (
                                is_valid
                                and self.TRACKING_MODE == "bbox"
                                and active_device_id in device_identities
                        ):
                            deep_identity_check = (
                                    frame_count % self.IDENTITY_CHECK_INTERVAL == 0
                                    or lost_frames > 0
                                    or identity_mismatch_frames > 0
                            )
                            bbox_valid, bbox_reason = self._is_bbox_still_target(
                                frame,
                                bbox,
                                device_identities[active_device_id],
                                motion_mask,
                                mask,
                                check_identity=deep_identity_check,
                            )
                            if not bbox_valid:
                                identity_mismatch_frames += 1
                                reason = (
                                    f"{bbox_reason} "
                                    f"连续={identity_mismatch_frames}/{self.IDENTITY_SOFT_MISMATCH_FRAMES}"
                                )
                                # 当前帧已经疑似漂移，立刻跳过不画；连续多帧后停止 tracker。
                                is_valid = False
                        hard_invalid = not is_valid
                        if (
                                is_valid
                                and self.ENABLE_STRICT_IDENTITY_CHECK
                                and active_device_id in device_identities
                        ):
                            identity_score, template_score, hist_score, feature_score = self._score_bbox_against_identity(
                                frame, bbox, device_identities[active_device_id]
                            )
                            if (
                                    identity_score < self.TRACK_IDENTITY_THRESHOLD
                                    or template_score < self.TRACK_TEMPLATE_THRESHOLD
                                    or hist_score < self.TRACK_HIST_THRESHOLD
                                    or feature_score < self.TRACK_FEATURE_THRESHOLD
                            ):
                                identity_mismatch_frames += 1
                                reason = (
                                    f"设备身份不匹配 score={identity_score:.3f} "
                                    f"(template={template_score:.3f}, hist={hist_score:.3f}, feature={feature_score:.3f}) "
                                    f"连续={identity_mismatch_frames}/{self.IDENTITY_SOFT_MISMATCH_FRAMES}"
                                )
                                if identity_mismatch_frames >= self.IDENTITY_SOFT_MISMATCH_FRAMES:
                                    is_valid = False
                            else:
                                identity_mismatch_frames = 0
                        if is_valid:
                            candidate_bbox = None
                            candidate_center = None
                            candidate_hits = 0
                            candidate_required_confirm = self.CANDIDATE_CONFIRM_FRAMES
                            bbox_draw_state = "valid"
                            lost_frames = 0
                            established_track_frames += 1
                            identity_mismatch_frames = 0
                            missing_frames = 0
                            if active_device_id in device_identities:
                                device_identities[active_device_id]["established_track_frames"] = established_track_frames
                            if last_valid_point is not None:
                                last_velocity = (
                                    center_point[0] - last_valid_point[0],
                                    center_point[1] - last_valid_point[1],
                                )
                            last_valid_point = center_point
                            last_valid_bbox = (x, y, w, h)
                            if active_device_id in device_identities:
                                device_identities[active_device_id]["last_bbox"] = (x, y, w, h)
                                device_identities[active_device_id]["lost_for_frames"] = 0
                                grace_frames = int(device_identities[active_device_id].get("grace_frames", 0))
                                if grace_frames > 0:
                                    device_identities[active_device_id]["grace_frames"] = grace_frames - 1
                                self._update_device_identity(
                                    frame, (x, y, w, h), device_identities[active_device_id], frame_count
                                )
                            if active_track_points is None:
                                active_track_points = []
                                active_footprints = []
                                track_segments.append(active_track_points)
                                footprint_segments.append(active_footprints)
                            if not active_track_points or active_track_points[-1] != center_point:
                                active_track_points.append(center_point)
                                all_track_points.append(center_point)
                                active_footprints.append((x, y, w, h))
                        else:
                            bbox_draw_state = "invalid"
                            lost_frames += 1
                            missing_frames += 1
                            if active_device_id in device_identities:
                                self._update_predicted_bbox(
                                    device_identities[active_device_id],
                                    last_valid_point,
                                    last_valid_bbox,
                                    last_velocity,
                                    missing_frames,
                                    contours[0] if contours else None,
                                )
                            if hard_invalid and frame_count % self.RELOCK_LOG_INTERVAL == 0:
                                print(f"目标疑似丢失/漂移，已跳过该点：{reason}")
                            else:
                                print(f"设备身份连续不匹配，已停止绘制：{reason}")
                            is_no_motion = "缺少运动" in reason
                            if is_no_motion and established_track_frames < self.MIN_ESTABLISHED_TRACK_FRAMES:
                                # 目标可能尚未启动，保持 tracker 等待，不触发自动重识别。
                                pass
                            else:
                                if is_no_motion:
                                    release_after = self.NO_MOTION_RELEASE_FRAMES
                                elif established_track_frames >= self.MIN_ESTABLISHED_TRACK_FRAMES:
                                    release_after = self.DRIFT_RELEASE_FRAMES
                                else:
                                    release_after = max(2, self.MAX_LOST_FRAMES // 2)
                                if lost_frames >= release_after:
                                    if lost_frames == release_after:
                                        print("目标疑似丢失，开始自动重识别...")
                                    tracker = None
                                    active_track_points = None
                                    active_footprints = None
                                    identity_mismatch_frames = 0
                    elif success is False:
                        lost_frames += 1
                        missing_frames += 1
                        if active_device_id in device_identities:
                            self._update_predicted_bbox(
                                device_identities[active_device_id],
                                last_valid_point,
                                last_valid_bbox,
                                last_velocity,
                                missing_frames,
                                contours[0] if contours else None,
                            )
                        release_after = (
                            self.DRIFT_RELEASE_FRAMES
                            if established_track_frames >= self.MIN_ESTABLISHED_TRACK_FRAMES
                            else max(2, self.MAX_LOST_FRAMES // 2)
                        )
                        if (
                                lost_frames >= release_after
                                and established_track_frames >= self.MIN_ESTABLISHED_TRACK_FRAMES
                        ):
                            if lost_frames == release_after:
                                print("目标跟踪失败，开始自动重识别...")
                            tracker = None
                            active_track_points = None
                            active_footprints = None

                def attempt_auto_relock(soft: bool = False) -> None:
                    nonlocal tracker, candidate_bbox, candidate_center, candidate_hits
                    nonlocal candidate_required_confirm, candidate_draw_bbox, candidate_miss_frames
                    nonlocal active_track_points, active_footprints, lost_frames, missing_frames
                    nonlocal last_valid_point, last_valid_bbox, last_velocity, identity_mismatch_frames
                    nonlocal last_relock_log_frame, bbox, bbox_draw_state

                    if not self.AUTO_RELOCK or active_device_id not in device_identities:
                        return
                    if established_track_frames < self.MIN_ESTABLISHED_TRACK_FRAMES or last_valid_point is None:
                        return
                    if soft:
                        if tracker is None or lost_frames < 1:
                            return
                        if frame_count % self.SOFT_RELOCK_INTERVAL != 0:
                            return
                    elif tracker is not None:
                        return
                    if frame_count % self.REID_INTERVAL_FRAMES != 0:
                        return

                    missing_frames += 1
                    identity = device_identities[active_device_id]
                    self._update_predicted_bbox(
                        identity, last_valid_point, last_valid_bbox, last_velocity,
                        missing_frames, contours[0] if contours else None,
                    )
                    found_bbox, found_center = self._try_reidentify_device(
                        frame, identity, contours[0] if contours else None, motion_mask, mask, commit=False,
                    )
                    if found_bbox is None or found_center is None:
                        candidate_miss_frames += 1
                        if candidate_miss_frames > self.CANDIDATE_MISS_TOLERANCE:
                            candidate_bbox = None
                            candidate_center = None
                            candidate_hits = 0
                            candidate_draw_bbox = None
                        return

                    candidate_miss_frames = 0
                    identity_score, template_score, _, _ = self._score_bbox_against_identity(
                        frame, found_bbox, identity
                    )
                    in_near_region = self._bbox_in_search_region(found_bbox, identity)
                    candidate_required_confirm = self._required_candidate_confirm_frames(
                        identity_score, template_score, in_near_region
                    )
                    candidate_iou = self._bbox_iou(candidate_bbox, found_bbox) if candidate_bbox is not None else 0.0
                    candidate_distance = self._bbox_center_distance(candidate_bbox, found_bbox)
                    if (
                            candidate_bbox is not None
                            and (
                                candidate_iou >= self.CANDIDATE_IOU_THRESHOLD
                                or candidate_distance <= self.CANDIDATE_CENTER_DISTANCE
                            )
                    ):
                        candidate_hits += 1
                    else:
                        candidate_bbox = found_bbox
                        candidate_center = found_center
                        candidate_hits = 1
                    candidate_draw_bbox = candidate_bbox
                    if frame_count - last_relock_log_frame >= self.RELOCK_LOG_INTERVAL:
                        print(
                            f"发现候选目标红框：连续={candidate_hits}/{candidate_required_confirm}, "
                            f"score={identity_score:.3f}, near={in_near_region}, soft={soft}"
                        )
                        last_relock_log_frame = frame_count

                    if candidate_hits < candidate_required_confirm:
                        return

                    new_tracker = self.create_tracker()
                    if new_tracker is None or not new_tracker.init(frame, candidate_bbox):
                        return

                    tracker = new_tracker
                    cx, cy, cw, ch = [int(v) for v in candidate_bbox]
                    identity["last_bbox"] = (cx, cy, cw, ch)
                    identity.pop("predicted_bbox", None)
                    identity["lost_for_frames"] = 0
                    identity["grace_frames"] = self.RELOCK_GRACE_FRAMES
                    x, y, w, h = cx, cy, cw, ch
                    bbox = candidate_bbox
                    center_point = candidate_center
                    bbox_draw_state = "valid"

                    if soft:
                        if active_track_points is None:
                            active_track_points = []
                            active_footprints = []
                            track_segments.append(active_track_points)
                            footprint_segments.append(active_footprints)
                        if not active_track_points or active_track_points[-1] != center_point:
                            active_track_points.append(center_point)
                            all_track_points.append(center_point)
                            active_footprints.append((x, y, w, h))
                    else:
                        bridge_points, bridge_footprints = self._build_reconnect_bridge(
                            last_valid_point, center_point, (x, y, w, h), contours[0] if contours else None
                        )
                        active_track_points = []
                        active_footprints = []
                        if bridge_points and last_valid_point:
                            active_track_points.append(last_valid_point)
                            active_track_points.extend(bridge_points)
                            active_footprints.extend(bridge_footprints)
                        else:
                            active_track_points.append(center_point)
                            active_footprints.append((x, y, w, h))
                        track_segments.append(active_track_points)
                        footprint_segments.append(active_footprints)
                        all_track_points.append(center_point)

                    last_valid_point = center_point
                    last_valid_bbox = (x, y, w, h)
                    missing_frames = 0
                    last_velocity = (0.0, 0.0)
                    lost_frames = 0
                    identity_mismatch_frames = 0
                    candidate_bbox = None
                    candidate_center = None
                    candidate_hits = 0
                    candidate_required_confirm = self.CANDIDATE_CONFIRM_FRAMES
                    print(f"设备ID={active_device_id} 已自动找回，{'继续当前轨迹段' if soft else '开启新的轨迹段'}")

                if tracker and lost_frames >= 1:
                    attempt_auto_relock(soft=True)
                if not tracker:
                    attempt_auto_relock(soft=False)

                overlay = frame.copy()

                cv2.polylines(overlay, [polygon_np], isClosed=True, color=(0, 255, 255), thickness=2)
                if tracker and bbox is not None:
                    bx, by, bw, bh = [int(v) for v in bbox]
                    box_color = (255, 0, 0) if bbox_draw_state == "valid" else (0, 0, 255)
                    cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), box_color, 2)
                elif candidate_draw_bbox is not None:
                    bx, by, bw, bh = [int(v) for v in candidate_draw_bbox]
                    cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
                    cv2.putText(
                        overlay,
                        f"candidate {candidate_hits}/{candidate_required_confirm}",
                        (bx, max(20, by - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )

                drawn_footprint_count, drawn_line_count = self._draw_incremental_tracks(
                    track_layer, white_trail, footprint_segments, track_segments,
                    drawn_footprint_count, drawn_line_count,
                )

                masked_track_layer = cv2.bitwise_and(track_layer, mask_3ch)
                masked_white_trail = cv2.bitwise_and(white_trail, mask_3ch)
                overlay = cv2.add(overlay, masked_track_layer)
                track_overlay = cv2.add(overlay, masked_white_trail)

                if frame_count % self.COVERAGE_UPDATE_INTERVAL == 0:
                    coverage_rate = self._compute_coverage_rate(masked_track_layer, mask, polygon_area)

                # 显示进度条
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                progress = current_frame / total_frames if total_frames > 0 else 0

                progress_bar_width = int(self.FRAME_WIDTH * progress)
                cv2.rectangle(overlay, (0, self.FRAME_HEIGHT - 10), (self.FRAME_WIDTH, self.FRAME_HEIGHT), (50, 50, 50),
                              -1)
                cv2.rectangle(overlay, (0, self.FRAME_HEIGHT - 10), (progress_bar_width, self.FRAME_HEIGHT),
                              (0, 255, 0), -1)

                alpha = 0.3
                result_track_frame = cv2.addWeighted(track_overlay, alpha, frame, 1 - alpha, 0)
                coverage_text = f"Coverage: {coverage_rate:.2f}%"
                text_pos = (10, 30)
                text_font = cv2.FONT_HERSHEY_SIMPLEX
                text_scale = 0.8
                text_color = (0, 165, 255)
                cv2.putText(result_track_frame, coverage_text, text_pos, text_font, text_scale, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(result_track_frame, coverage_text, text_pos, text_font, text_scale, text_color, 2, cv2.LINE_AA)

                if not windows_ready:
                    self._setup_cv_window("Coverage", offset_x=coverage_x, offset_y=window_y)
                    self._setup_cv_window("Tracking", offset_x=tracking_x, offset_y=window_y)
                    windows_ready = True

                cv2.imshow("Tracking", result_track_frame)
                if frame_count % self.COVERAGE_WINDOW_INTERVAL == 0:
                    result_frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
                    cv2.putText(result_frame, coverage_text, text_pos, text_font, text_scale, (0, 0, 0), 4, cv2.LINE_AA)
                    cv2.putText(result_frame, coverage_text, text_pos, text_font, text_scale, text_color, 2, cv2.LINE_AA)
                    cv2.imshow("Coverage", result_frame)
                elif result_frame is None:
                    result_frame = result_track_frame

                elapsed_ms = (time.perf_counter() - loop_start) * 1000.0
                if self.SYNC_VIDEO_FPS:
                    wait_ms = max(1, int(1000.0 / video_fps - elapsed_ms))
                else:
                    wait_ms = 1
                key = cv2.waitKey(wait_ms) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord(' '):
                    self._setup_cv_window("Select object", offset_x=coverage_x,
                                          offset_y=window_y + self.WINDOW_HEIGHT + 30)
                    init_box = cv2.selectROI("Select object", frame, fromCenter=False)
                    if any(init_box):
                        # 如果已经有活动设备，手动重新框选时默认认为是同一台设备，
                        # 这样可把丢失前最后有效点与重新框选点自动连接起来。
                        if active_device_id is None:
                            active_device_id = next_device_id
                            next_device_id += 1
                        identity = self._build_device_identity(
                            frame, init_box, active_device_id, pool_search_bbox=pool_search_bbox
                        )
                        if identity is not None:
                            old_identity = device_identities.get(active_device_id)
                            if old_identity:
                                old_identity["templates"].extend(identity.get("templates", []))
                                old_identity["hists"].extend(identity.get("hists", []))
                                old_identity.setdefault("descriptors", []).extend(identity.get("descriptors", []))
                                old_identity["templates"] = old_identity["templates"][-self.IDENTITY_MAX_TEMPLATES:]
                                old_identity["hists"] = old_identity["hists"][-self.IDENTITY_MAX_TEMPLATES:]
                                old_identity["descriptors"] = old_identity.get("descriptors", [])[-self.IDENTITY_MAX_TEMPLATES:]
                                old_identity["size"] = identity.get("size", old_identity.get("size"))
                                old_identity["last_bbox"] = identity.get("last_bbox", old_identity.get("last_bbox"))
                                old_identity["pool_search_bbox"] = pool_search_bbox
                                old_identity["grace_frames"] = self.INIT_GRACE_FRAMES
                                old_identity["lost_for_frames"] = 0
                                old_identity["established_track_frames"] = established_track_frames
                            else:
                                identity["grace_frames"] = self.INIT_GRACE_FRAMES
                                identity["established_track_frames"] = 0
                                device_identities[active_device_id] = identity
                            established_track_frames = 0
                        tracker = self.create_tracker()
                        if tracker is not None:
                            if tracker.init(frame, init_box):
                                x, y, w, h = [int(v) for v in init_box]
                                center_point = (int(x + w / 2), int(y + h / 2))
                                self._calibrate_track_width_from_bbox(init_box)
                                bridge_points, bridge_footprints = self._build_reconnect_bridge(
                                    last_valid_point, center_point, (x, y, w, h), contours[0] if contours else None
                                )
                                active_track_points = []
                                active_footprints = []
                                if bridge_points and last_valid_point:
                                    active_track_points.append(last_valid_point)
                                    active_track_points.extend(bridge_points)
                                    active_footprints.extend(bridge_footprints)
                                else:
                                    active_track_points.append(center_point)
                                    active_footprints.append((x, y, w, h))
                                track_segments.append(active_track_points)
                                footprint_segments.append(active_footprints)
                                all_track_points.append(center_point)
                                last_valid_point = center_point
                                last_valid_bbox = (x, y, w, h)
                                missing_frames = 0
                                last_velocity = (0.0, 0.0)
                                lost_frames = 0
                                established_track_frames = 0
                                identity_mismatch_frames = 0
                                candidate_bbox = None
                                candidate_center = None
                                candidate_hits = 0
                                if active_device_id in device_identities:
                                    device_identities[active_device_id]["grace_frames"] = self.INIT_GRACE_FRAMES
                                    device_identities[active_device_id]["established_track_frames"] = 0
                                print(f"设备ID={active_device_id} 目标选择完成，开始跟踪")
                            else:
                                tracker = None
                                print("无法初始化跟踪器，请重新选择目标")
                        else:
                            print("无法初始化跟踪器，请确保已安装 OpenCV contrib 模块")
                    cv2.destroyWindow("Select object")

                # 跟踪更新已提前到本轮开头，这里不再重复更新

                ret, frame = cap.read()
                if ret:
                    frame = self._resize_frame(frame)

            cap.release()
            cv2.destroyAllWindows()

            if len(all_track_points) > 0:
                # 同时保存覆盖率图和带轨迹线的图，便于后续查看涂抹轨迹
                output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "picture")
                os.makedirs(output_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                coverage_output_path = os.path.join(output_dir, f"Coverage_rate_{timestamp}.png")
                track_output_path = os.path.join(output_dir, f"Coverage_track_{timestamp}.png")

                cv2.imwrite(coverage_output_path, result_frame if result_frame is not None else result_track_frame)
                cv2.imwrite(track_output_path, result_track_frame)
                print(f"覆盖率图像已保存至 {coverage_output_path}")
                print(f"轨迹图像已保存至 {track_output_path}")
            else:
                print("未检测到有效的轨迹线")

        except Exception as e:
            print(f"处理视频时出现错误: {str(e)}")
            cv2.destroyAllWindows()


class CaseExporter:
    def __init__(self):
        pass

    def export_cases_to_excel(self, folder, feature, output_excel, platform=None):
        folder = folder.strip()
        feature = feature.strip()
        output_excel = output_excel.strip()
        py_path = os.path.join(folder, feature, f'{feature}.py')
        print('绝对路径:', os.path.abspath(py_path))
        if not os.path.exists(py_path):
            print(f'未找到文件: {py_path}')
            return False

        # 平台优先用传入参数
        if not platform:
            platform = 'IOS' if os.path.basename(folder).startswith('iPhone') else 'Android'

        with open(py_path, encoding='utf-8') as f:
            content = f.read()

        import re
        cases = []
        for m in re.finditer(r'def (test_(\d+)).*?"""(.*?)"""(.*?)(?=def |$)', content, re.DOTALL):
            func_name = m.group(1)
            case_id = m.group(2)
            doc = m.group(3).strip()
            func_body = m.group(4)
            lines = [line.strip() for line in doc.split('\n') if line.strip()]
            name = lines[0] if lines else ''
            expected = []
            step_flag = False
            expect_flag = False
            steps = []
            for line in lines[1:]:
                if line.startswith('步骤') or line.startswith('步骤:'):
                    step_flag = True
                    expect_flag = False
                    continue
                if line.startswith('期望') or line.startswith('期望:'):
                    expect_flag = True
                    step_flag = False
                    continue
                if step_flag:
                    steps.append(line)
                if expect_flag:
                    expected.append(line)
            if not steps:
                steps = []
                for line in func_body.split('\n'):
                    line = line.strip()
                    if line.startswith('#'):
                        step_text = line.lstrip('#').strip()
                        if step_text:
                            steps.append(step_text)
                    elif 'click(' in line:
                        steps.append('点击按钮')
                    elif 'send_keys(' in line:
                        steps.append('输入内容')
            steps_str = '\n'.join([f"{i + 1}、{s}" for i, s in enumerate(steps)]) if steps else ''
            expected = []
            for line in func_body.split('\n'):
                line = line.strip()
                if line.startswith('#') and (('断言' in line) or ('期望' in line)):
                    exp_text = line.lstrip('#').strip()
                    if exp_text:
                        expected.append(exp_text)
            if not expected:
                for line in func_body.split('\n'):
                    line = line.strip()
                    if line.startswith('assert'):
                        expected.append(line)
            expected_str = '\n'.join([f"{i + 1}、{s}" for i, s in enumerate(expected)]) if expected else ''
            cases.append({
                '用例集名称': feature,
                '平台': platform,
                'ID': case_id,
                '用例内容': name,
                '操作步骤': steps_str,
                '期望结果': expected_str
            })

        # 写入Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = feature
        ws.append(['用例集名称', '平台', 'ID', '用例内容', '操作步骤', '期望结果'])
        for case in cases:
            ws.append(
                [case['用例集名称'], case['平台'], case['ID'], case['用例内容'], case['操作步骤'], case['期望结果']])
        for col in ws.columns:
            for cell in col:
                cell.alignment = Alignment(wrap_text=True, vertical='center')
        wb.save(output_excel)
        print(f'导出完成：{output_excel}')
        return True

    def export_cases_to_excel_by_file(self, py_path, output_excel, platform=None):
        if not os.path.exists(py_path):
            print(f'未找到文件: {py_path}')
            return False
        if not platform:
            platform = 'IOS' if 'iphone' in py_path.lower() else 'ANDROID'
        with open(py_path, encoding='utf-8') as f:
            content = f.read()
        import re
        cases = []
        for m in re.finditer(r'def (test_(\d+)).*?"""(.*?)"""(.*?)(?=def |$)', content, re.DOTALL):
            func_name = m.group(1)
            case_id = m.group(2)
            doc = m.group(3).strip()
            func_body = m.group(4)
            lines = [line.strip() for line in doc.split('\n') if line.strip()]
            name = lines[0] if lines else ''
            expected = []
            step_flag = False
            expect_flag = False
            steps = []
            for line in lines[1:]:
                if line.startswith('步骤') or line.startswith('步骤:'):
                    step_flag = True
                    expect_flag = False
                    continue
                if line.startswith('期望') or line.startswith('期望:'):
                    expect_flag = True
                    step_flag = False
                    continue
                if step_flag:
                    steps.append(line)
                if expect_flag:
                    expected.append(line)
            if not steps:
                steps = []
                for line in func_body.split('\n'):
                    line = line.strip()
                    if line.startswith('#'):
                        step_text = line.lstrip('#').strip()
                        if step_text:
                            steps.append(step_text)
                    elif 'click(' in line:
                        steps.append('点击按钮')
                    elif 'send_keys(' in line:
                        steps.append('输入内容')
            steps_str = '\n'.join([f"{i + 1}、{s}" for i, s in enumerate(steps)]) if steps else ''
            expected = []
            for line in func_body.split('\n'):
                line = line.strip()
                if line.startswith('#') and (('断言' in line) or ('期望' in line)):
                    exp_text = line.lstrip('#').strip()
                    if exp_text:
                        expected.append(exp_text)
            if not expected:
                for line in func_body.split('\n'):
                    line = line.strip()
                    if line.startswith('assert'):
                        expected.append(line)
            expected_str = '\n'.join([f"{i + 1}、{s}" for i, s in enumerate(expected)]) if expected else ''
            cases.append({
                '用例集名称': os.path.splitext(os.path.basename(py_path))[0],
                '平台': platform,
                'ID': case_id,
                '用例内容': name,
                '操作步骤': steps_str,
                '期望结果': expected_str
            })
        # 写入Excel
        import openpyxl
        from openpyxl.styles import Alignment
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = os.path.splitext(os.path.basename(py_path))[0]
        ws.append(['用例集名称', '平台', 'ID', '用例内容', '操作步骤', '期望结果'])
        for case in cases:
            ws.append(
                [case['用例集名称'], case['平台'], case['ID'], case['用例内容'], case['操作步骤'], case['期望结果']])
        for col in ws.columns:
            for cell in col:
                cell.alignment = Alignment(wrap_text=True, vertical='center')
        wb.save(output_excel)
        print(f'导出完成：{output_excel}')
        return True


class MainApplication:
    def __init__(self, root):
        self.root = root
        self.root.title("Beatbot软测工具")

        # 设置窗口大小为720P并允许调整
        self.root.geometry("1280x720")
        self.root.minsize(1024, 576)

        # 配置根窗口的网格权重
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 设置样式
        self.setup_styles()

        # 创建主框架
        self.main_frame = ttk.Frame(root)
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=20, pady=20)

        # 配置主框架的网格权重
        for i in range(2):  # 2行
            self.main_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):  # 4列
            self.main_frame.grid_columnconfigure(i, weight=1)

        # 创建轨迹线处理器实例
        self.trajectory = TrajectoryLine()

        # 创建用例导出器实例
        self.case_exporter = CaseExporter()

        # 创建功能区域
        self._function_busy = False
        self.create_function_areas()
        self.root.after(300, self._focus_main_window)

    def _focus_main_window(self):
        """让主窗口启动后主动获取焦点，减少 macOS 首次点击只激活窗口的问题。"""
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(100, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception:
            pass

    def setup_styles(self):
        style = ttk.Style()
        # 配置标签样式
        style.configure(
            'Icon.TLabel',
            font=('微软雅黑', 48),  # 大图标
            padding=10,
            anchor='center',  # 文本居中
            justify='center'  # 多行文本居中
        )
        style.configure(
            'Function.TLabel',
            font=('微软雅黑', 12, 'bold'),  # 功能名称字体
            padding=5,
            anchor='center',  # 文本居中
            justify='center'  # 多行文本居中
        )
        # 配置按钮样式
        style.configure(
            'Function.TButton',
            padding=10
        )

    def create_function_areas(self):
        # 2行4列布局，文件解析放到轨迹线绘制后面
        functions = [
            {"name": "轨迹线绘制", "command": self.mcu_tools, "row": 0, "column": 0, "icon": "📊"},
            {"name": "文件解析", "command": self.batch_bin_to_log_gui, "row": 0, "column": 1, "icon": "🗂️"},
            {"name": "用例导出", "command": self.case_export_gui, "row": 0, "column": 2, "icon": "📋"},
        ]
        # 配置主框架的网格权重为2行4列
        for i in range(2):
            self.main_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):
            self.main_frame.grid_columnconfigure(i, weight=1)
        # 创建功能按钮和空白占位
        for row in range(2):
            for col in range(4):
                func = next((f for f in functions if f["row"] == row and f["column"] == col), None)
                frame = tk.Frame(
                    self.main_frame,
                    relief='solid',
                    borderwidth=1,
                    bg="#f7f7f7",
                    cursor="hand2" if func else ""
                )
                frame.grid(
                    row=row,
                    column=col,
                    rowspan=1,
                    columnspan=1,
                    sticky=(tk.W, tk.E, tk.N, tk.S),
                    padx=8,
                    pady=8
                )
                if func:
                    container = tk.Frame(frame, bg="#f7f7f7", cursor="hand2")
                    container.place(relx=0.5, rely=0.5, anchor='center')
                    icon_label = tk.Label(
                        container,
                        text=func["icon"],
                        font=('微软雅黑', 48),
                        bg="#f7f7f7",
                        cursor='hand2'
                    )
                    icon_label.pack(pady=(0, 2))
                    name_label = tk.Label(
                        container,
                        text=func["name"],
                        font=('微软雅黑', 12, 'bold'),
                        bg="#f7f7f7",
                        cursor='hand2'
                    )
                    name_label.pack()

                    def set_card_style(f=frame, c=container, i=icon_label, n=name_label, bg="#f7f7f7", relief="solid"):
                        f.configure(bg=bg, relief=relief)
                        c.configure(bg=bg)
                        i.configure(bg=bg)
                        n.configure(bg=bg)

                    def run_command(cmd=func["command"], name=func["name"]):
                        if self._function_busy:
                            return
                        self._function_busy = True
                        try:
                            print(f"已点击功能：{name}")
                            self.root.update_idletasks()
                            cmd()
                        finally:
                            self._function_busy = False

                    def on_press(e, f=frame, c=container, i=icon_label, n=name_label, cmd=func["command"], name=func["name"]):
                        set_card_style(f, c, i, n, bg="#dbeafe", relief="sunken")
                        self.root.update_idletasks()
                        # 按下即安排执行，避免必须先点外框、再点内部控件才响应。
                        self.root.after(30, lambda: run_command(cmd, name))
                        return "break"

                    def on_release(e, f=frame, c=container, i=icon_label, n=name_label):
                        set_card_style(f, c, i, n, bg="#e8f2ff", relief="raised")
                        return "break"

                    def on_enter(e, f=frame, c=container, i=icon_label, n=name_label):
                        set_card_style(f, c, i, n, bg="#e8f2ff", relief="raised")

                    def on_leave(e, f=frame, c=container, i=icon_label, n=name_label):
                        set_card_style(f, c, i, n, bg="#f7f7f7", relief="solid")

                    for widget in [frame, container, icon_label, name_label]:
                        widget.bind('<ButtonPress-1>', on_press)
                        widget.bind('<ButtonRelease-1>', on_release)
                        widget.bind('<Enter>', on_enter)
                        widget.bind('<Leave>', on_leave)
                else:
                    # 空白占位
                    pass

    def _show_trajectory_width_dialog(self) -> bool:
        """打开轨迹线绘制前设置涂抹轨迹和实线轨迹宽度。"""
        dialog = tk.Toplevel(self.root)
        dialog.title("轨迹线参数设置")
        dialog.geometry("400x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)

        main = ttk.Frame(dialog, padding=18)
        main.pack(fill=tk.BOTH, expand=True)

        track_var = tk.StringVar(value=str(getattr(self.trajectory, "TRACK_WIDTH", 15)))
        center_default = max(1, int(getattr(self.trajectory, "TRACK_WIDTH", 15)) // 5)
        center_var = tk.StringVar(value=str(getattr(self.trajectory, "CENTERLINE_WIDTH", center_default)))
        result = {"ok": False, "closing": False}

        ttk.Label(main, text="涂抹轨迹宽度（默认 15）").grid(row=0, column=0, sticky="w", pady=(0, 8))
        track_entry = ttk.Entry(main, textvariable=track_var, width=12)
        track_entry.grid(row=0, column=1, sticky="e", pady=(0, 8))

        ttk.Label(main, text="实线轨迹宽度（默认涂抹的 1/5）").grid(row=1, column=0, sticky="w", pady=(0, 8))
        center_entry = ttk.Entry(main, textvariable=center_var, width=12)
        center_entry.grid(row=1, column=1, sticky="e", pady=(0, 8))

        hint = ttk.Label(
            main,
            text="说明：涂抹宽度控制绿色覆盖区域，实线宽度控制灰色中心轨迹。稳定跟踪后目标消失会自动重锁定（运动检测优先，高置信度更快确认）。",
            foreground="#666666",
            wraplength=350,
        )
        hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 14))

        def on_track_change(*_):
            try:
                width = int(track_var.get())
                if width > 0:
                    center_var.set(str(max(1, width // 5)))
            except Exception:
                pass

        # 用户手动编辑实线宽度后不再自动覆盖
        center_touched = {"value": False}

        def on_center_key(_):
            center_touched["value"] = True

        def on_track_key(_):
            if not center_touched["value"]:
                dialog.after(10, on_track_change)

        track_entry.bind("<KeyRelease>", on_track_key)
        center_entry.bind("<KeyRelease>", on_center_key)

        def confirm(event=None):
            if result["closing"]:
                return "break"
            try:
                track_width = int(track_var.get())
                center_width = int(center_var.get())
                if track_width <= 0 or center_width <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("输入错误", "轨迹宽度必须是大于 0 的整数。", parent=dialog)
                return "break"

            self.trajectory.TRACK_WIDTH = track_width
            self.trajectory.CENTERLINE_WIDTH = center_width
            self.trajectory.MANUAL_TRACK_WIDTH = True
            print(f"轨迹参数已设置：涂抹={track_width}px，实线={center_width}px")
            result["closing"] = True
            result["ok"] = True
            dialog.destroy()
            return "break"

        def cancel(event=None):
            if result["closing"]:
                return "break"
            result["closing"] = True
            result["ok"] = False
            dialog.destroy()
            return "break"

        button_frame = ttk.Frame(main)
        button_frame.grid(row=3, column=0, columnspan=2, sticky="e")
        cancel_btn = tk.Button(
            button_frame,
            text="取消",
            width=12,
            height=1,
            command=cancel,
            cursor="hand2",
            takefocus=True,
        )
        confirm_btn = tk.Button(
            button_frame,
            text="确定",
            width=12,
            height=1,
            command=confirm,
            cursor="hand2",
            takefocus=True,
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))
        confirm_btn.pack(side=tk.RIGHT)
        # macOS 上有时第一次点击只聚焦窗口，绑定按下事件可让按钮立即响应。
        confirm_btn.bind("<ButtonPress-1>", confirm)
        cancel_btn.bind("<ButtonPress-1>", cancel)

        main.columnconfigure(0, weight=1)
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.bind("<Return>", confirm)
        dialog.bind("<KP_Enter>", confirm)
        dialog.bind("<Escape>", cancel)

        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        x = root_x + (root_w - 400) // 2
        y = root_y + (root_h - 220) // 2
        dialog.geometry(f"400x220+{x}+{y}")

        dialog.update_idletasks()
        dialog.wait_visibility()
        dialog.lift()
        dialog.attributes("-topmost", True)
        dialog.after(150, lambda: dialog.attributes("-topmost", False))
        dialog.focus_force()
        track_entry.focus_force()

        self.root.wait_window(dialog)
        return result["ok"]

    def mcu_tools(self):
        global cv2
        if cv2 is None:
            if not cv2_available:
                result = messagebox.askyesno("缺少依赖包",
                                             "轨迹线绘制功能需要 opencv-python 包\n\n"
                                             "是否查看安装指南？")
                if result:
                    self.show_install_guide("opencv-python", "轨迹线绘制")
                return
            try:
                import cv2 as _cv2
                cv2 = _cv2
                print("✓ opencv-python 导入成功")
            except Exception as e:
                messagebox.showerror("OpenCV 导入失败", f"无法导入 opencv-python：\n{e}")
                return

        if not self._show_trajectory_width_dialog():
            return

        video_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("MP4 文件", "*.mp4"),
                ("AVI 文件", "*.avi"),
                ("MOV 文件", "*.mov"),
                ("MKV 文件", "*.mkv"),
                ("所有文件", "*.*")
            ]
        )
        if video_path:
            self.trajectory.process_video(video_path)

    def batch_bin_to_log_gui(self):
        # 选择包含压缩包和文件夹的目录
        folder_path = filedialog.askdirectory(title="请选择包含压缩包和文件夹的目录")
        if not folder_path:
            return

        # 扫描目录中的所有文件和文件夹
        items_to_process = []
        supported_extensions = ('.tar.gz', '.tgz', '.tar', '.zip', '.rar')

        print(f"扫描目录: {folder_path}")
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)

            # 检查是否是压缩包
            if os.path.isfile(item_path) and item.lower().endswith(supported_extensions):
                items_to_process.append(('archive', item_path))
                print(f"发现压缩包: {item}")

            # 检查是否是文件夹
            elif os.path.isdir(item_path):
                items_to_process.append(('folder', item_path))
                print(f"发现文件夹: {item}")

        if not items_to_process:
            messagebox.showinfo("提示", "在选择的目录中没有找到压缩包或文件夹")
            return

        # 显示处理进度
        progress_window = tk.Toplevel(self.root)
        progress_window.title("处理进度")
        progress_window.geometry("400x200")

        # Center window
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        win_w = 400
        win_h = 200
        x = root_x + (root_w - win_w) // 2
        y = root_y + (root_h - win_h) // 2
        progress_window.geometry(f'{win_w}x{win_h}+{x}+{y}')

        # 进度显示
        progress_label = ttk.Label(progress_window, text="准备开始处理...")
        progress_label.pack(pady=10)

        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=len(items_to_process))
        progress_bar.pack(fill='x', padx=20, pady=10)

        status_label = ttk.Label(progress_window, text="")
        status_label.pack(pady=5)

        total_converted_bins = 0
        all_copy_errors = []

        def process_items():
            nonlocal total_converted_bins, all_copy_errors

            for i, (item_type, item_path) in enumerate(items_to_process):
                # 更新进度
                progress_var.set(i + 1)
                item_name = os.path.basename(item_path)
                progress_label.config(text=f"处理中 ({i + 1}/{len(items_to_process)}): {item_name}")
                status_label.config(text=f"正在处理: {item_type} - {item_name}")
                progress_window.update()

                print(f"处理中 ({i + 1}/{len(items_to_process)}): {item_name}")
                converted_count, copy_errors = self.batch_convert_bin_to_log(item_path)
                total_converted_bins += converted_count
                all_copy_errors.extend(copy_errors)

            # 处理完成
            progress_window.destroy()

            summary_message = f"批量处理完成！\n\n总共转换了 {total_converted_bins} 个 .bin 文件。"
            if all_copy_errors:
                summary_message += "\n\n以下文件复制失败:\n"
                error_details = "\n".join([f"- {os.path.basename(f)}: {err}" for f, err in all_copy_errors])
                summary_message += error_details

            messagebox.showinfo("任务完成", summary_message)

        # 在新线程中处理，避免界面卡死
        import threading
        process_thread = threading.Thread(target=process_items)
        process_thread.daemon = True
        process_thread.start()

        progress_window.transient(self.root)
        progress_window.grab_set()
        self.root.wait_window(progress_window)

    def show_install_guide(self, package_name, feature_name):
        """显示安装指南"""
        guide_window = tk.Toplevel(self.root)
        guide_window.title(f"安装指南 - {feature_name}")
        guide_window.geometry("500x400")

        # Center window
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        win_w = 500
        win_h = 400
        x = root_x + (root_w - win_w) // 2
        y = root_y + (root_h - win_h) // 2
        guide_window.geometry(f'{win_w}x{win_h}+{x}+{y}')

        # 创建文本区域
        text_frame = ttk.Frame(guide_window)
        text_frame.pack(fill='both', expand=True, padx=20, pady=20)

        text_widget = tk.Text(text_frame, wrap='word', font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 安装指南内容
        guide_text = f"""安装指南 - {feature_name}

需要安装的包: {package_name}

方法一: 使用 pip 安装
1. 打开终端或命令提示符
2. 运行以下命令:
   pip install {package_name}

方法二: 使用 conda 安装 (如果使用 Anaconda)
1. 打开 Anaconda Prompt
2. 运行以下命令:
   conda install {package_name}

方法三: 在 Python 环境中安装
1. 激活您的 Python 虚拟环境
2. 运行: pip install {package_name}

安装完成后，请重启此程序。

常见问题:
- 如果提示权限错误，请使用: pip install --user {package_name}
- 如果网络较慢，可以使用国内镜像: pip install -i https://pypi.tuna.tsinghua.edu.cn/simple {package_name}
- 如果使用虚拟环境，请确保在正确的环境中安装

技术支持:
如果安装过程中遇到问题，请检查:
1. Python 版本是否兼容
2. 网络连接是否正常
3. pip 是否为最新版本 (pip install --upgrade pip)
"""

        text_widget.insert('1.0', guide_text)
        text_widget.config(state='disabled')  # 设置为只读

        # 关闭按钮
        ttk.Button(guide_window, text="关闭", command=guide_window.destroy).pack(pady=10)

        guide_window.transient(self.root)
        guide_window.grab_set()
        self.root.wait_window(guide_window)

    def case_export_gui(self):
        if openpyxl is None:
            result = messagebox.askyesno("缺少依赖包",
                                         "用例导出功能需要 openpyxl 包\n\n"
                                         "是否查看安装指南？")
            if result:
                self.show_install_guide("openpyxl", "用例导出")
            return

        export_window = tk.Toplevel(self.root)
        export_window.title("用例导出")
        export_window.geometry("420x260")

        # Center window
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        win_w = 420
        win_h = 260
        x = root_x + (root_w - win_w) // 2
        y = root_y + (root_h - win_h) // 2
        export_window.geometry(f'{win_w}x{win_h}+{x}+{y}')

        main_frame = ttk.Frame(export_window)
        main_frame.pack(fill='both', expand=True, padx=30, pady=20)

        # 选择py文件
        ttk.Label(main_frame, text="选择用例py文件:").pack(anchor='w')
        pyfile_var = tk.StringVar()
        pyfile_entry = ttk.Entry(main_frame, textvariable=pyfile_var, width=44)
        pyfile_entry.pack(fill='x', pady=(5, 10))

        def select_pyfile():
            pyfile = filedialog.askopenfilename(title="选择用例py文件", filetypes=[("Python文件", "*.py")])
            if pyfile:
                pyfile_var.set(pyfile)

        ttk.Button(main_frame, text="浏览py文件", command=select_pyfile).pack(anchor='w', pady=(0, 10))

        # 平台选择（记忆上次选择）
        if not hasattr(self, '_last_platform'):
            self._last_platform = 'IOS'
        ttk.Label(main_frame, text="平台:").pack(anchor='w', pady=(8, 0))
        platform_var = tk.StringVar(value=self._last_platform)
        platform_combo = ttk.Combobox(main_frame, textvariable=platform_var, values=['IOS', 'ANDROID'], width=10)
        platform_combo.pack(anchor='w', pady=(2, 12))

        def on_platform_change(event):
            self._last_platform = platform_var.get()

        platform_combo.bind('<<ComboboxSelected>>', on_platform_change)

        # 导出按钮直接居中显示
        def export_cases():
            pyfile = pyfile_var.get().strip()
            platform = platform_var.get().strip()
            if not pyfile or not os.path.isfile(pyfile):
                messagebox.showerror("错误", "请选择有效的py文件")
                return
            # 导出到桌面工具文件夹
            export_dir = os.path.dirname(os.path.abspath(__file__))
            file_base = os.path.splitext(os.path.basename(pyfile))[0]
            output_excel = os.path.join(export_dir, f"{file_base}.xlsx")
            try:
                # 直接用选中的py文件，不再拼接目录
                success = self.case_exporter.export_cases_to_excel_by_file(pyfile, output_excel, platform)
                if success:
                    messagebox.showinfo("成功", f"用例导出完成！\n文件保存为: {output_excel}")
                    export_window.destroy()
                else:
                    messagebox.showerror("错误", f"导出失败，请检查文件内容是否正确")
            except Exception as e:
                messagebox.showerror("错误", f"导出过程中出现错误:\n{str(e)}")

        ttk.Button(main_frame, text="导出用例", command=export_cases, style='Function.TButton').pack(pady=12,
                                                                                                     anchor='center')

        export_window.transient(self.root)
        export_window.grab_set()
        self.root.wait_window(export_window)

    def batch_convert_bin_to_log(self, item_path):
        if zstd is None:
            print("⚠️ 压缩包解压功能不可用，请安装 zstandard: pip install zstandard")
            return 0, []

        import os
        import tempfile
        import shutil
        import tarfile
        import zipfile
        try:
            import rarfile
        except ImportError:
            rarfile = None

        def extract_archive(archive_path, extract_to):
            if archive_path.endswith(('.tar.gz', '.tgz', '.tar')):
                with tarfile.open(archive_path, 'r:*') as tar:
                    tar.extractall(path=extract_to)
            elif archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(path=extract_to)
            elif archive_path.endswith('.rar') and rarfile is not None:
                with rarfile.RarFile(archive_path) as rar:
                    rar.extractall(path=extract_to)
            else:
                raise Exception(f'不支持的压缩包格式: {archive_path}')

        def is_archive_file(file_path):
            """判断文件是否为压缩包"""
            supported_extensions = ('.tar.gz', '.tgz', '.tar', '.zip', '.rar')
            return file_path.lower().endswith(supported_extensions)

        def recursive_extract_archives(directory):
            """递归解压目录中的所有压缩包"""
            extracted_count = 0
            for root, dirs, files in os.walk(directory):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    if is_archive_file(file_path):
                        print(f"发现嵌套压缩包: {file_path}")
                        try:
                            # 创建临时目录用于解压
                            temp_extract_dir = tempfile.mkdtemp(dir=root)
                            extract_archive(file_path, temp_extract_dir)

                            # 删除原压缩包
                            os.remove(file_path)

                            # 将解压的内容移动到原位置
                            extracted_items = os.listdir(temp_extract_dir)
                            if len(extracted_items) == 1 and os.path.isdir(
                                    os.path.join(temp_extract_dir, extracted_items[0])):
                                # 如果只有一个文件夹，直接移动其内容
                                single_dir = os.path.join(temp_extract_dir, extracted_items[0])
                                for item in os.listdir(single_dir):
                                    shutil.move(os.path.join(single_dir, item), root)
                                os.rmdir(single_dir)
                            else:
                                # 移动所有解压的文件到原位置
                                for item in extracted_items:
                                    shutil.move(os.path.join(temp_extract_dir, item), root)

                            # 删除临时目录
                            shutil.rmtree(temp_extract_dir)
                            extracted_count += 1
                            print(f"已解压: {filename}")

                        except Exception as e:
                            print(f"解压 {filename} 失败: {e}")
                            # 清理临时目录
                            if os.path.exists(temp_extract_dir):
                                shutil.rmtree(temp_extract_dir)
            return extracted_count

        # 判断是压缩包还是文件夹
        is_archive = is_archive_file(item_path)

        work_dir = item_path
        temp_dir = None
        if is_archive:
            temp_dir = tempfile.mkdtemp()
            extract_archive(item_path, temp_dir)
            work_dir = temp_dir

        # 递归解压工作目录中的所有压缩包
        print("开始递归解压压缩包...")
        total_extracted = recursive_extract_archives(work_dir)
        print(f"总共解压了 {total_extracted} 个压缩包")

        # 生成输出文件夹名称
        base_name = os.path.splitext(os.path.basename(item_path))[0] if is_archive else os.path.basename(item_path)
        new_folder = os.path.join(os.path.dirname(item_path), base_name + "_log")

        count = 0
        error_files = []

        # 遍历工作目录中的所有文件
        for root, dirs, files in os.walk(work_dir):
            rel_path = os.path.relpath(root, work_dir)
            target_dir = os.path.join(new_folder, rel_path) if rel_path != '.' else new_folder
            os.makedirs(target_dir, exist_ok=True)

            for filename in files:
                src_file = os.path.join(root, filename)
                if filename.lower().endswith('.bin'):
                    print(f"发现bin文件: {src_file}")
                    raw_file = os.path.join(target_dir, filename[:-4] + ".raw")
                    log_file = os.path.join(target_dir, filename[:-4] + ".log")
                    try:
                        hex_str = ''
                        with open(src_file, 'r', errors='ignore') as f_in:
                            for line in f_in:
                                line = line.strip()
                                if len(line) > 14:
                                    hex_str += line[14:]
                        hex_str = ''.join(filter(lambda c: c in '0123456789abcdefABCDEF', hex_str))
                        with open(raw_file, 'wb') as f_out:
                            f_out.write(bytes.fromhex(hex_str))

                        with open(raw_file, 'rb') as f:
                            data = f.read()
                        zstd_magic = b'\x28\xb5\x2f\xfd'
                        idx = 0
                        all_text = ''
                        while True:
                            idx = data.find(zstd_magic, idx)
                            if idx == -1:
                                break
                            next_idx = data.find(zstd_magic, idx + 4)
                            chunk = data[idx:next_idx] if next_idx != -1 else data[idx:]
                            try:
                                dctx = zstd.ZstdDecompressor()
                                decompressed = dctx.decompress(chunk)
                                all_text += decompressed.decode('utf-8', errors='replace')
                            except Exception as e:
                                print(f'解压第{idx}段失败: {e}')
                            idx = next_idx if next_idx != -1 else len(data)
                        with open(log_file, 'w', encoding='utf-8') as f_out:
                            f_out.write(all_text)
                        print(f"已生成log文件: {log_file}")
                        count += 1
                    except Exception as e:
                        print(f"转换{src_file}失败: {e}")
                    finally:
                        if os.path.exists(raw_file):
                            os.remove(raw_file)
                else:
                    # 复制非bin文件
                    if os.path.isfile(src_file):
                        dst_file = os.path.join(target_dir, filename)
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        try:
                            shutil.copy2(src_file, dst_file)
                        except Exception as e:
                            error_files.append((src_file, str(e)))

        if temp_dir:
            shutil.rmtree(temp_dir)

        print(f"处理完成: {item_path} -> {new_folder}")
        return count, error_files


if __name__ == "__main__":
    root = tk.Tk()
    app = MainApplication(root)
    root.mainloop()
