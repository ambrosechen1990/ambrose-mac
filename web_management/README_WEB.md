# 软件自动化测试管理 Web 平台

## 功能特性

### 蓝牙配网测试
- ✅ **一键启动/停止 Appium 端口**：自动从 `device_config.json` 读取端口配置
- ✅ **测试手机选择**：支持全选/单选，从配置文件读取设备信息
- ✅ **路由器选择**：支持全选/单选，从配置文件读取路由器信息
- ✅ **测试配置**：可设置测试次数（默认3次），支持启动前清除机器日志
- ✅ **一键启动测试**：自动执行测试流程，包括：
  - 清除机器人日志（可选）
  - 执行 Android/iOS 配网测试
  - 打包并拉取机器人日志
  - 收集测试报告和日志到统一目录
- ✅ **实时日志查看**：流式显示测试执行日志
- ✅ **测试任务管理**：查看历史任务、下载测试结果

### 其他模块（待开发）
- 功能测试
- 性能测试
- 测试工具

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境（可选但推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements_web.txt
```

### 2. 启动 Web 服务

```bash
# 方式1: 使用启动脚本（推荐）
./start_web.sh

# 方式2: 直接运行
python3 web_app.py
```

### 3. 访问 Web 界面

打开浏览器访问：http://localhost:5000

## 使用说明

### 蓝牙配网测试流程

1. **启动 Appium 端口**
   - 点击"一键启动 Appium 端口"按钮
   - 系统会自动从 `Android/device_config.json` 和 `IOS/device_config.json` 读取端口配置并启动

2. **选择测试平台**
   - 选择 Android 或 iOS 平台

3. **选择测试设备**
   - 可以全选或单独选择测试手机
   - 设备信息来自 `device_config.json`

4. **选择路由器**
   - 可以全选或单独选择路由器
   - 路由器信息来自 `device_config.json`

5. **配置测试参数**
   - 设置测试次数（默认3次）
   - 选择是否在启动前清除机器日志

6. **启动测试**
   - 点击"一键启动测试"按钮
   - 系统会：
     - 创建任务目录（`reports/task_xxx`）
     - 清除机器人日志（如果启用）
     - 执行测试脚本
     - 打包并拉取机器人日志
     - 收集测试报告和日志

7. **查看测试日志**
   - 测试启动后会自动显示实时日志
   - 可以点击"一键停止测试"按钮停止正在运行的任务

8. **下载测试结果**
   - 在"测试工具"标签页查看所有历史任务
   - 点击"下载结果"按钮下载测试报告和日志（打包为 zip）

## 目录结构

```
iot/
├── web_management/          # Web 管理平台（与 reports/tools 同级）
│   ├── web_app.py          # Web 应用主文件
│   ├── templates/
│   │   └── index.html      # 前端页面
│   ├── requirements_web.txt # Python 依赖
│   ├── start_web.sh        # 启动脚本
│   └── README_WEB.md       # 使用说明
├── reports/                # 测试报告目录
├── tools/                  # 工具目录
└── project/
    └── P0011/
        └── 配网兼容性/
            └── 蓝牙配网兼容性/  # 测试项目目录
    ├── clear_robot_logs.py  # 清除机器人日志脚本
    ├── pack_robot_logs.py   # 打包机器人日志脚本
    ├── Android/
    │   ├── device_config.json   # Android 设备配置
    │   └── Android-蓝牙配网.py  # Android 测试脚本
    ├── IOS/
    │   ├── device_config.json   # iOS 设备配置
    │   └── IOS-蓝牙配网.py      # iOS 测试脚本
    └── reports/            # 测试结果目录
        └── task_xxx/       # 每个任务的独立目录
            ├── test.log    # 测试日志
            ├── *.xlsx      # 测试报告
            └── *.tar.gz    # 机器人日志包
```

## API 接口

### 获取配置
- `GET /api/config/<platform>` - 获取设备配置（android/ios）

### Appium 管理
- `POST /api/appium/start` - 启动 Appium 端口
- `POST /api/appium/stop` - 停止 Appium 端口

### 测试任务
- `POST /api/test/start` - 启动测试任务
- `POST /api/test/stop/<task_id>` - 停止测试任务
- `GET /api/test/status/<task_id>` - 获取任务状态
- `GET /api/test/log/<task_id>` - 获取测试日志（流式）
- `GET /api/test/list` - 列出所有任务
- `GET /api/test/download/<task_id>` - 下载测试结果

## 注意事项

1. **Appium 服务器**：确保已安装 Appium 和相应的驱动（uiautomator2、xcuitest）
2. **ADB 路径**：确保 ADB 在系统 PATH 中，或设置 `ANDROID_HOME` 环境变量
3. **机器人设备**：确保机器人设备已连接，默认设备ID为 `galaxy_p0001`，可通过环境变量 `ROBOT_DEVICE_ID` 修改
4. **端口占用**：默认 Web 服务运行在 5000 端口，确保端口未被占用

## 故障排除

### Web 服务无法启动
- 检查 Python 版本（需要 Python 3.7+）
- 检查依赖是否安装完整：`pip install -r requirements_web.txt`
- 检查端口 5000 是否被占用

### Appium 启动失败
- 检查 `device_config.json` 配置是否正确
- 检查端口是否已被占用
- 检查 Appium 是否已安装：`appium --version`

### 测试任务执行失败
- 检查测试脚本是否存在
- 检查设备是否已连接
- 查看任务日志文件：`reports/task_xxx/test.log`

## 开发计划

- [ ] 功能测试模块
- [ ] 性能测试模块
- [ ] 测试报告可视化
- [ ] 测试任务调度
- [ ] 邮件通知功能

