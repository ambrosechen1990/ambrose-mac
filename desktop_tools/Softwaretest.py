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

# 检查依赖包是否可用
def check_package(package_name, import_name=None):
    if import_name is None:
        import_name = package_name
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False

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
    try:
        import cv2
        print("✓ opencv-python 导入成功")
    except ImportError:
        print("⚠️ opencv-python 导入失败，轨迹线绘制功能将不可用")
else:
    print("⚠️ opencv-python 未安装，轨迹线绘制功能将不可用")

class TrajectoryLine:
    def __init__(self):
        # 检查cv2是否可用
        if cv2 is None:
            print("⚠️ 轨迹线绘制功能不可用，请安装 opencv-python")
            return
            
        # 固定视频帧大小和默认轨迹线宽度
        self.FRAME_WIDTH = 640
        self.FRAME_HEIGHT = 480
        self.TRACK_WIDTH = 40 # 默认轨迹线宽度
        
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
                # 仅在相关性较高时认为跟踪成功
                return max_val >= 0.35, self.bbox
            except Exception:
                return False, self.bbox
    
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

            frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))

            tracker = None
            init_box = None
            all_track_points = []
            current_track_points = []

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

            cv2.namedWindow("Tracking")
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
            # 获取多边形内的所有点
            points_inside_polygon = []
            for y in range(self.FRAME_HEIGHT):
                for x in range(self.FRAME_WIDTH):
                    if cv2.pointPolygonTest(contours[0], (x, y), False) >= 0:
                        points_inside_polygon.append((x, y))

            white_trail = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)

            print("按空格键选择要跟踪的目标，按 q 键退出")
            while True:
                frame_count += 1
                if not ret:
                    print("视频播放完毕或读取失败")
                    break

                bbox = None
                if tracker:
                    success, bbox = tracker.update(frame)
                    if success and bbox is not None:
                        x, y, w, h = [int(v) for v in bbox]
                        center_point = (int(x + w / 2), int(y + h / 2))
                        if not all_track_points or all_track_points[-1] != center_point:
                            current_track_points.append(center_point)
                            all_track_points.append(center_point)
                    elif success is False:
                        print("目标跟踪失败，请重新选择目标")
                        tracker = None

                overlay = frame.copy()
                track_layer = np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)

                # 显示多边形区域
                cv2.polylines(overlay, [np.array(polygon_points, np.int32)], isClosed=True, color=(0, 255, 255), thickness=2)

                # 先将轨迹绘制到独立图层，再按编辑区域裁剪，避免超出多边形的轨迹显示出来
                for i in range(1, len(all_track_points)):
                    if all_track_points[i - 1] and all_track_points[i]:
                        cv2.line(track_layer, all_track_points[i - 1], all_track_points[i], (0, 255, 0), self.TRACK_WIDTH)
                        cv2.line(white_trail, all_track_points[i - 1], all_track_points[i], (127, 127, 127), max(1, self.TRACK_WIDTH // 4))

                mask_3ch = cv2.merge([mask, mask, mask])
                masked_track_layer = cv2.bitwise_and(track_layer, mask_3ch)
                masked_white_trail = cv2.bitwise_and(white_trail, mask_3ch)
                overlay = cv2.add(overlay, masked_track_layer)

                # 叠加白色轨迹层
                track_overlay = cv2.add(overlay, masked_white_trail)

                if frame_count % 20 == 0:
                    covered_area = 0
                    for point in points_inside_polygon:
                        x, y = point
                        if masked_track_layer[y, x][1] == 255 and masked_track_layer[y, x][0] == 0 and masked_track_layer[y, x][2] == 0:
                            covered_area += 1
                    coverage_rate = (covered_area / polygon_area) * 100 if polygon_area > 0 else 0
                    
                # 显示进度条
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                progress = current_frame / total_frames if total_frames > 0 else 0

                progress_bar_width = int(self.FRAME_WIDTH * progress)
                cv2.rectangle(overlay, (0, self.FRAME_HEIGHT - 10), (self.FRAME_WIDTH, self.FRAME_HEIGHT), (50, 50, 50), -1)
                cv2.rectangle(overlay, (0, self.FRAME_HEIGHT - 10), (progress_bar_width, self.FRAME_HEIGHT), (0, 255, 0), -1)

                # 显示结果帧
                alpha = 0.3
                result_frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
                result_track_frame = cv2.addWeighted(track_overlay, alpha, frame, 1 - alpha, 0)
                coverage_text = f"Coverage: {coverage_rate:.2f}%"
                text_pos = (10, 30)
                text_font = cv2.FONT_HERSHEY_SIMPLEX
                text_scale = 0.8
                text_color = (0, 165, 255)  # 橘黄色（BGR）

                for canvas in (result_frame, result_track_frame):
                    cv2.putText(canvas, coverage_text, text_pos, text_font, text_scale, (0, 0, 0), 4, cv2.LINE_AA)
                    cv2.putText(canvas, coverage_text, text_pos, text_font, text_scale, text_color, 2, cv2.LINE_AA)

                cv2.imshow("Coverage", result_frame)
                cv2.imshow("Tracking", result_track_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord(' '):
                    init_box = cv2.selectROI("Select object", frame, fromCenter=False)
                    if any(init_box):
                        tracker = self.create_tracker()
                        if tracker is not None:
                            if tracker.init(frame, init_box):
                                x, y, w, h = [int(v) for v in init_box]
                                center_point = (int(x + w / 2), int(y + h / 2))
                                current_track_points = [center_point]
                                all_track_points.append(center_point)
                                print("目标选择完成，开始跟踪")
                            else:
                                tracker = None
                                print("无法初始化跟踪器，请重新选择目标")
                        else:
                            print("无法初始化跟踪器，请确保已安装 OpenCV contrib 模块")
                    cv2.destroyWindow("Select object")

                # 跟踪更新已提前到本轮开头，这里不再重复更新

                ret, frame = cap.read()
                if ret:
                    frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))

            cap.release()
            cv2.destroyAllWindows()

            if len(all_track_points) > 0:
                # 同时保存覆盖率图和带轨迹线的图，便于后续查看涂抹轨迹
                output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "picture")
                os.makedirs(output_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                coverage_output_path = os.path.join(output_dir, f"Coverage_rate_{timestamp}.png")
                track_output_path = os.path.join(output_dir, f"Coverage_track_{timestamp}.png")

                cv2.imwrite(coverage_output_path, result_frame)
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
            steps_str = '\n'.join([f"{i+1}、{s}" for i, s in enumerate(steps)]) if steps else ''
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
            expected_str = '\n'.join([f"{i+1}、{s}" for i, s in enumerate(expected)]) if expected else ''
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
            ws.append([case['用例集名称'], case['平台'], case['ID'], case['用例内容'], case['操作步骤'], case['期望结果']])
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
            steps_str = '\n'.join([f"{i+1}、{s}" for i, s in enumerate(steps)]) if steps else ''
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
            expected_str = '\n'.join([f"{i+1}、{s}" for i, s in enumerate(expected)]) if expected else ''
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
            ws.append([case['用例集名称'], case['平台'], case['ID'], case['用例内容'], case['操作步骤'], case['期望结果']])
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
        self.create_function_areas()

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
                frame = ttk.Frame(
                    self.main_frame,
                    relief='solid',
                    borderwidth=1
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
                    container = ttk.Frame(frame)
                    container.place(relx=0.5, rely=0.5, anchor='center')
                    icon_label = ttk.Label(
                        container,
                        text=func["icon"],
                        style='Icon.TLabel',
                        cursor='hand2'
                    )
                    icon_label.pack(pady=(0, 2))
                    name_label = ttk.Label(
                        container,
                        text=func["name"],
                        style='Function.TLabel',
                        cursor='hand2'
                    )
                    name_label.pack()
                    for widget in [frame, container, icon_label, name_label]:
                        widget.bind('<Button-1>', lambda e, cmd=func["command"]: cmd())
                    def on_enter(e, f=frame):
                        f.configure(relief='raised')
                    def on_leave(e, f=frame):
                        f.configure(relief='solid')
                    for widget in [frame, container, icon_label, name_label]:
                        widget.bind('<Enter>', on_enter)
                        widget.bind('<Leave>', on_leave)
                else:
                    # 空白占位
                    pass

    def mcu_tools(self):
        if cv2 is None:
            result = messagebox.askyesno("缺少依赖包", 
                "轨迹线绘制功能需要 opencv-python 包\n\n"
                "是否查看安装指南？")
            if result:
                self.show_install_guide("opencv-python", "轨迹线绘制")
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
                progress_label.config(text=f"处理中 ({i+1}/{len(items_to_process)}): {item_name}")
                status_label.config(text=f"正在处理: {item_type} - {item_name}")
                progress_window.update()
                
                print(f"处理中 ({i+1}/{len(items_to_process)}): {item_name}")
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

        ttk.Button(main_frame, text="导出用例", command=export_cases, style='Function.TButton').pack(pady=12, anchor='center')

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
                            if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_extract_dir, extracted_items[0])):
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
