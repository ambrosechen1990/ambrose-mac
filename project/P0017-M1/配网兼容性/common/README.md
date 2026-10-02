# 共用文件目录 (Common)

此目录包含所有配网兼容性测试脚本共用的工具和配置文件。

## 文件说明

### 配置文件
- **`device_config.json`**: 统一的设备配置文件，包含：
  - Android 和 iOS 设备配置
  - 路由器 WiFi 配置
  - 测试参数配置
  - 目标设备配置

### Python 工具模块
- **`excel_report_generator.py`**: Excel 测试报告生成器
  - 支持 Android 和 iOS 平台
  - 支持蓝牙配网、扫码配网、手动配网三种方式
  - 生成汇总表和详细数据表

- **`report_utils.py`**: 报告工具模块
  - `init_run_env()`: 初始化测试运行环境，创建输出目录
  - **报告保存规则**：自动识别当前项目目录（P0011、P0024 等），所有测试报告保存在当前项目目录下的 `reports` 文件夹
    - P0011 项目：`P0011/配网兼容性/reports/`
    - P0024 项目：`P0024/配网兼容性/reports/`

- **`clear_robot_logs.py`**: 清理机器人日志脚本
  - 清空 `/data/log` 目录
  - 删除 `/data` 目录下的旧日志包

- **`pack_robot_logs.py`**: 打包并拉取机器人日志脚本
  - 执行 `pack` 命令打包日志
  - 自动拉取最新的 tar.gz 日志包

## 使用方式

所有测试脚本会自动从 `common` 目录查找这些共用文件，查找优先级：

1. **配置文件 (`device_config.json`)**:
   - 环境变量 `DEVICE_CONFIG_FILE` 指定的文件
   - `common/device_config.json`（优先）
   - 各子目录下的 `device_config.json`（向后兼容）

2. **Python 模块**:
   - 脚本会自动将 `common` 目录添加到 `sys.path`
   - 如果找不到，会尝试从原位置查找（向后兼容）

## 目录结构

```
配网兼容性/
├── common/                    # 共用文件目录
│   ├── __init__.py
│   ├── device_config.json     # 统一配置文件
│   ├── excel_report_generator.py
│   ├── report_utils.py
│   ├── clear_robot_logs.py
│   ├── pack_robot_logs.py
│   └── README.md
├── 蓝牙配网/
│   ├── Android-蓝牙配网.py
│   └── IOS-蓝牙配网.py
├── 扫码配网/
│   ├── Android-扫码配网.py
│   └── IOS-扫码配网.py
├── start_appium.sh
├── stop_appium.sh
└── reports/                   # 统一报告目录（自动创建在当前项目目录下）
```

## 报告保存规则

所有测试报告均保存在**当前项目目录**下的 `reports` 文件夹：

- **P0011 项目**：`P0011/配网兼容性/reports/`
- **P0024 项目**：`P0024/配网兼容性/reports/`
- **其他项目**：`PXXXX/配网兼容性/reports/`

`report_utils.py` 会自动识别当前项目目录，无需手动配置。报告目录结构示例：

```
P0011/
└── 配网兼容性/
    └── reports/
        ├── 蓝牙配网-Android-2025年12月10日 101508/
        │   ├── bluetooth_pairing.log
        │   ├── screenshots/
        │   └── 蓝牙配网-Android-配网兼容性测试报告_20251210_101508.xlsx
        └── 扫码配网-iOS-2025年12月10日 102030/
            ├── bluetooth_pairing.log
            ├── screenshots/
            └── 扫码配网-iOS-配网兼容性测试报告_20251210_102030.xlsx
```

## 注意事项

- 所有脚本已更新为优先使用 `common` 目录中的文件
- 保留了向后兼容性，如果 `common` 目录中找不到文件，会尝试从原位置查找
- 建议统一使用 `common/device_config.json` 作为唯一配置文件源

