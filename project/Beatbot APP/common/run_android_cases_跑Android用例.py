"""
Android 平台功能总执行入口。

主要用途：
- 统一执行 用例/*/Android 下所有可识别用例
- 输出聚合日志、总报告和汇总 sheet
"""

from platform_case_runner_平台调度 import run_platform_suite


if __name__ == "__main__":
    raise SystemExit(run_platform_suite("android"))
