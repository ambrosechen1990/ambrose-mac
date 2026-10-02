# 轨迹线增强工具

来源：`desktop_tools/test.py`（独立增强版轨迹绘制）

## 与主程序差异

| | 主程序「轨迹线绘制」 | 本工具 |
|--|---------------------|--------|
| 入口 | `主程序/Beatbot.py` 功能卡片 | 本目录独立运行 |
| 能力 | 与 Softtest-win 对齐的完整软测套件中的一环 | 侧重自动重锁定、防漂移、性能优化等增强跟踪逻辑 |

主程序已有轨迹线能力时，本工具可作为**实验/增强版**单独使用。

## 使用

```bash
cd Beatbot-tools/轨迹线增强工具
pip install opencv-python numpy openpyxl zstandard
python3 trajectory_enhanced.py
```

依赖与主程序类似：OpenCV、NumPy 等。
