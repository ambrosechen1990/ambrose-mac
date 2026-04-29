# Web 管理平台

这是一个独立的 Web 管理平台，用于管理蓝牙配网测试。

## 目录说明

Web 管理平台位于独立的 `web_management` 文件夹中，与测试项目目录 `蓝牙配网兼容性` 分离。

## 快速启动

```bash
cd web_management
./start_web.sh
```

然后访问：http://localhost:5000

## 文件说明

- `web_app.py` - Flask Web 应用主文件
- `templates/index.html` - 前端页面
- `requirements_web.txt` - Python 依赖
- `start_web.sh` - 启动脚本
- `README_WEB.md` - 详细使用说明

## 注意事项

Web 应用会自动访问 `project/P0011/配网兼容性/蓝牙配网兼容性` 目录，读取配置文件和执行测试脚本。

Web 管理平台位于 `iot/web_management/`，与 `reports/` 和 `tools/` 目录同级。

