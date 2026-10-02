# Excel 转换工具（合并版）

将 `desktop_tools/excel` 下两个独立脚本合并为同一入口：

| 原脚本 | 功能 | 合并后位置 |
|--------|------|------------|
| `excel_compare.py` / `excel_映射.py` | 一键处理新/旧表，生成四工作表处理结果 | GUI 页签「一键处理对比」 |
| `excel_to_script_names.py` | 读取「ID用例名称」并生成脚本 | GUI 页签「Excel 转脚本」 |

## 一键处理对比

选择**新表**（最新原始用户数据）与**旧表**（历史处理结果或原始表），生成：

1. **最新用户数据** — 新表原始内容
2. **完整数据** — 映射后的完整明细
3. **设备统计** — 机型/厂家/系统统计
4. **对比结果** — 相对旧表的新增与增量型号

支持格式：`.xlsx` / `.xlsm` / `.xls` / `.csv` / `.tsv`。输出留空时写入「`日期处理结果/原文件名_处理结果.xlsx`」。

## 目录

```
excel转换工具/
├── excel_tool.py              # 统一入口（推荐）
├── excel_映射.py              # 处理 + 对比
├── excel_to_script_names.py   # 转脚本依赖
├── requirements.txt
├── run_excel_tool.command     # 双击启动
└── README.md
```

## 使用

### GUI（推荐）

```bash
cd Beatbot-tools/excel转换工具
./run_excel_tool.command
# 或
python3 excel_tool.py
```

### 命令行

```bash
# 一键处理 + 对比
python3 excel_tool.py compare 新.csv 旧.xlsx [输出.xlsx]

# 转脚本
python3 excel_tool.py scripts 用例.xlsx --create-scripts --output-dir ./生成的脚本
```

## 依赖

```bash
pip install openpyxl
# 可选：读取旧版 .xls
pip install pandas xlrd
```
