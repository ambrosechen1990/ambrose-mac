"""pytest 配置：注入 APP外壳/1共用脚本 与项目根路径，便于导入 common_utils 等。"""
import sys
from pathlib import Path

# APP外壳 已取消 comman：共用逻辑在「1共用脚本」
_cur = Path(__file__).resolve().parent
_shared = None
for _ in range(24):
    _cand = _cur / "1共用脚本"
    if _cand.is_dir() and (_cand / "common_utils.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 APP外壳/1共用脚本（需包含 common_utils.py）")

# 获取项目根目录（project/APP外壳）
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent

# 将项目根目录添加到 Python 路径（在导入任何测试文件之前）
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def pytest_configure(config):
    """pytest 配置钩子 - 确保路径在导入测试文件之前设置"""
    # 再次确保路径已设置
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

