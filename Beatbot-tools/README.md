# Beatbot-tools

从 `Softwaretest-win` 迁移并适配 **macOS** 的 Beatbot 软测工具。功能与 Windows 版对齐。

> 原目录名 `Softwaretest-mac` 已更名为 `Beatbot-tools`。

## 功能

主程序：

- 轨迹线绘制 / 池壁轨迹线绘制
- 日志解析、日志打包下载、日志一键删除（ADB）
- MCU 工具（Innovate 串口调试）
- 串口调试助手
- 使用帮助

从 `desktop_tools` 迁入的独立工具：

- **excel转换工具/**：Excel 对比 + 用例转脚本
- **LAgent屏幕控制/**：亮屏关 LAgent / 熄屏开 LAgent
- **脚本迁移工具/**：iOS 登录 XPath 替换、comman→共用脚本迁移
- **轨迹线增强工具/**：独立增强版轨迹跟踪（`test.py`）

## 快速开始

### 方式一：双击运行（源码）

1. 安装依赖（首次）:
   ```bash
   brew install tesseract android-platform-tools
   ```
2. 双击 `run_Beatbot_tools.command`  
   （若无法打开：`chmod +x run_Beatbot_tools.command && xattr -dr com.apple.quarantine run_Beatbot_tools.command`）

### 方式二：命令行

```bash
cd Beatbot-tools
python3 -m venv .venv_run
source .venv_run/bin/activate
pip install -r requirements.txt
cd 主程序
python Beatbot.py
```

### 方式三：打包成 .app

```bash
# 或双击 build_app_mac.command
python3 工具脚本/打包脚本_mac.py
```

产物在 `dist/Beatbot软测工具.app`，可拷贝到其他 **同架构** Mac 双击使用。

## 与 Windows 版的主要差异

| 项目 | Windows | macOS |
|------|---------|-------|
| 输出目录 | `D:\dist` | `~/Documents/BeatbotDist` |
| 文件锁 | `msvcrt` | `fcntl` |
| UI 字体 | 微软雅黑 | PingFang SC |
| 串口名 | `COM3` | `/dev/cu.usbserial*` 等 |
| OCR | 安装包 + PATH | `brew install tesseract` |
| ADB | 手动装 platform-tools | `brew install android-platform-tools` |
| 打包 | `.exe` | `.app` |

可用环境变量：

- `BEATBOT_DIST`：自定义 Excel/日志输出目录
- `ADB_PATH`：指定 adb 路径
- `TESSERACT_CMD`：指定 tesseract 路径

## 目录结构

```
Beatbot-tools/
├── 主程序/Beatbot.py            # 主入口（推荐）
├── 主程序/Beatbot-test.py       # 测试入口
├── 主程序/platform_compat.py    # macOS 兼容层（勿删）
├── 主程序/老版/Softwaretest.py  # 旧入口归档
├── 串口工具/
├── MCU工具/
├── excel转换工具/               # Excel 对比 / 转脚本
├── 脚本迁移工具/
├── 轨迹线增强工具/
├── 工具脚本/打包脚本_mac.py
├── requirements.txt
├── run_Beatbot_tools.command
└── build_app_mac.command
```

## 说明

- 源码运行与打包运行均依赖本机已安装的 `tesseract` / `adb`（打包不会把系统二进制打进 .app）。
- 串口调试 / MCU 工具通过动态加载同仓库脚本；请勿同时占用同一物理串口。
