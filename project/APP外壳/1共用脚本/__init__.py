"""
共用脚本包入口。

主要用途：
- 对外统一暴露常用共用函数
- 根据平台自动选择登出实现
- 方便业务脚本通过包方式导入基础能力
"""

from .email_utils import get_next_email, get_simple_email
from .logout_ios import check_and_logout as check_and_logout_ios
from .logout_android import check_and_logout as check_and_logout_android
from .screenshot_utils import ScreenshotContext, safe_execute, save_failure_screenshot
from .report_utils import init_report, bind_logger_to_print, write_report


def check_and_logout(driver):
    """
    智能登出函数：根据driver的平台自动选择iOS或Android版本的登出函数
    
    Args:
        driver: WebDriver实例
    """
    try:
        # 获取平台信息
        caps = driver.capabilities
        platform_name = caps.get("platformName", "").lower()
        
        # 根据平台选择对应的登出函数
        if platform_name == "android":
            return check_and_logout_android(driver)
        elif platform_name == "ios":
            return check_and_logout_ios(driver)
        else:
            # 如果无法确定平台，尝试根据其他特征判断
            # Android通常有appPackage，iOS通常有bundleId
            if "appPackage" in caps:
                return check_and_logout_android(driver)
            elif "bundleId" in caps or "CFBundleIdentifier" in str(caps):
                return check_and_logout_ios(driver)
            else:
                # 默认尝试Android（因为当前主要是Android测试）
                print("    [登出] ⚠️ 无法确定平台，默认使用Android登出流程")
                return check_and_logout_android(driver)
    except Exception as e:
        print(f"    [登出] ❌ 选择登出函数时出错: {e}")
        # 如果出错，尝试使用Android版本作为备用
        print("    [登出] ⚠️ 使用Android登出流程作为备用")
        return check_and_logout_android(driver)


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
