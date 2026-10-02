# Beatbot APP

Beatbot App 账号与外壳功能的自动化用例。按**功能模块**组织，Android / iOS 分开放。

```
Beatbot APP/
  common/            共用脚本（英文_中文）
  测试报告/          运行产物（platform / client）
  用例/
    <模块>/
      Android/
      iOS/
```

## 用例模块

| 模块 | 说明 |
| --- | --- |
| 登录 | 邮箱密码登录、协议勾选、明文/清空 |
| 注册 | 国家、邮箱、密码规则、用户名 |
| 忘记密码 | 未登录找回密码（验证码、新密码） |
| 修改密码 | 已登录，账号与安全里改密 |
| 账号与安全 | 账号与安全页展示、所在地 |
| 退出登录 | 退出确认与重新登录 |
| 账号注销 | 注销与取消 |
| 个人资料 | 头像等（目前主要 iOS） |
| 泳池信息 | 名称、形状、面积、水深（目前主要 iOS） |
| FAQ | 帮助中心文案校验（`FAQ/Android.py`、`FAQ/iOS.py`） |
| 说明书 | 说明书文案（`说明书/iOS.py`） |
| 埋点 | 大数据埋点占位 |
| 隐私政策用户协议 | 占位，待补脚本 |

原先「3忘记密码」是登录前找回；「7忘记密码」是登录后修改，已拆成 **忘记密码** / **修改密码**。

## common 脚本

文件名采用 **英文_中文**（Python 模块名不能含空格）。用例会向上查找 `common`（含 `common_utils_iOS共用.py` / `common_utils_Android共用.py`），与目录深度无关。

| 文件 | 用途 |
| --- | --- |
| `common_utils_iOS共用.py` | iOS 用例聚合入口（邮箱、登出、截图、报告） |
| `common_utils_Android共用.py` | Android 用例聚合入口 |
| `client_客户端.py` | 勾选模块后跑编号用例的图形客户端 |
| `platform_case_runner_平台调度.py` | 按平台递归执行编号用例 |
| `run_ios_cases_跑iOS用例.py` | iOS 总入口（薄封装） |
| `run_android_cases_跑Android用例.py` | Android 总入口（薄封装） |
| `logout_iOS登出.py` / `logout_Android登出.py` | 平台登出 |
| `gmail_otp_utils_iOS验证码.py` / `gmail_otp_utils_Android验证码.py` | 验证码 |
| `language_switch_iOS语言切换.py` / `language_switch_Android语言切换.py` | FAQ/说明书切语言 |
| `ios_sign_in_helpers_登录辅助.py` / `ios_sign_in_locators_登录定位.py` | iOS 登录定位 |
| `email_utils_邮箱工具.py` / `username_utils_用户名工具.py` | 测试账号生成 |
| `screenshot_utils_截图工具.py` / `report_utils_报告工具.py` | 失败截图与报告 |
| `constant_常量.py` | Gmail 凭据回退（优先环境变量） |
| `sync_case_names_跨平台复制用例名.py` | 跨平台复制用例文件名 |
| `create_case_names_脚本名称生成.py` | 按编号批量生成占位脚本 |
| `devices_设备列表.json` | 设备、FAQ 设备、文案库文件名 |
| `copywriting_library_文案库.xlsx` | FAQ/说明书文案库 |
| `data/` | 邮箱计数等运行数据，不是脚本 |

## 怎么跑

```bash
# 图形客户端（勾选模块后跑带 6 位编号的脚本）
python3 "project/Beatbot APP/common/client_客户端.py"

# 跑某一平台全部编号用例
python3 "project/Beatbot APP/common/run_ios_cases_跑iOS用例.py"
python3 "project/Beatbot APP/common/run_android_cases_跑Android用例.py"

# 跨平台复制用例文件名
python3 "project/Beatbot APP/common/sync_case_names_跨平台复制用例名.py" --from ios --to android --module 登录 --dry-run
```

FAQ / 说明书不走编号调度，直接运行对应 `用例/FAQ`、`用例/说明书` 脚本。
