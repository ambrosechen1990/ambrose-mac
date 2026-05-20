"""Android 平台用例与 common_utils 对齐：登出使用 logout_android。"""
from email_utils import get_next_email, get_simple_email
from logout_android import check_and_logout
from screenshot_utils import ScreenshotContext, safe_execute, save_failure_screenshot
from report_utils import init_report, bind_logger_to_print, write_report

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
