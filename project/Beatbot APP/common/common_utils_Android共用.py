"""Android 平台用例与 common_utils_iOS共用 对齐：登出使用 logout_Android登出。"""
from email_utils_邮箱工具 import get_next_email, get_simple_email
from logout_Android登出 import check_and_logout
from screenshot_utils_截图工具 import ScreenshotContext, safe_execute, save_failure_screenshot
from report_utils_报告工具 import init_report, bind_logger_to_print, write_report

__all__ = [
    "get_next_email",
    "get_simple_email",
    "check_and_logout",
    "ScreenshotContext",
    "safe_execute",
    "save_failure_screenshot",
    "init_report",
    "bind_logger_to_print",
    "write_report",
]
