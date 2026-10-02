# 脚本迁移工具

来源：`desktop_tools/apply_ios_sign_in_xpaths.py`、`migrate_comman_to_shared_scripts.py`

## 功能

| 脚本 | 作用 |
|------|------|
| `apply_ios_sign_in_xpaths.py` | 批量把 用例/登录/iOS 中的邮箱/密码定位改为 `ios_sign_in_locators_登录定位` XPath |
| `migrate_comman_to_shared_scripts.py` | 一次性把 Beatbot APP/用例 下脚本从 `comman` 改为 `common` |

路径已按本目录位置修正为仓库根 `iot/project/...`。

## 使用

在仓库根附近确认 `project/Beatbot APP` 存在后：

```bash
cd Beatbot-tools/脚本迁移工具
python3 apply_ios_sign_in_xpaths.py
python3 migrate_comman_to_shared_scripts.py
```

> 注意：迁移脚本会改写用例文件，建议先 git commit / 备份。
