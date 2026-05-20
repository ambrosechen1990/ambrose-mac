"""
截图与异常保护工具。

主要用途：
- 保存失败步骤截图
- 为步骤执行提供上下文管理和异常保护
- 供测试脚本统一记录失败现场
"""

import time
from pathlib import Path
from typing import Optional


def save_failure_screenshot(driver, step_name: str, run_dir: Optional[Path] = None) -> Optional[str]:
    """
    保存失败步骤的截图。
    
    Args:
        driver: WebDriver 实例
        step_name: 步骤名称
        run_dir: 报告目录（可选），如果提供则将截图保存到报告目录下的 screenshots 子目录
    
    Returns:
        截图文件路径（相对路径），如果保存失败则返回 None
    """
    try:
        timestamp = int(time.time())
        if run_dir:
            # 保存到报告目录下的 screenshots 子目录
            screenshots_dir = run_dir / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            filename = screenshots_dir / f"{step_name}_{timestamp}.png"
            driver.save_screenshot(str(filename))
            # 返回相对路径（相对于报告目录）
            relative_path = f"screenshots/{step_name}_{timestamp}.png"
            print(f"已保存{step_name}失败截图: {relative_path}")
            return relative_path
        else:
            # 兼容旧代码：保存到当前目录下的 screenshots 目录
            filename = f"screenshots/{step_name}_{timestamp}.png"
            driver.save_screenshot(filename)
            print(f"已保存{step_name}失败截图: {filename}")
            return filename
    except Exception as e:
        print(f"保存截图失败: {e}")
        return None


class ScreenshotContext:
    """截图上下文管理器，异常时自动截图。"""

    def __init__(self, driver, step_name: str, run_dir: Optional[Path] = None):
        self.driver = driver
        self.step_name = step_name
        self.run_dir = run_dir

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            save_failure_screenshot(self.driver, self.step_name, self.run_dir)
            return False
        return True


def safe_execute(driver, step_name: str, func, *args, run_dir: Optional[Path] = None, **kwargs):
    """安全执行函数，异常时自动截图并抛出。"""
    with ScreenshotContext(driver, step_name, run_dir):
        return func(*args, **kwargs)

