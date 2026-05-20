#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 IOS/1登录 用例中邮箱、密码输入框改为 ios_sign_in_locators 中的 XPath。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LOGIN_DIR = Path(__file__).resolve().parents[1] / "project" / "APP外壳" / "3功能" / "1平台" / "IOS" / "1登录"

IMPORT_LINE = (
    "from ios_sign_in_locators import (\n"
    "    IOS_SIGN_IN_EMAIL_CONTAINER_XPATH,\n"
    "    IOS_SIGN_IN_PASSWORD_CONTAINER_XPATH,\n"
    "    IOS_SIGN_IN_EMAIL_TEXT_FIELD_XPATH,\n"
    "    IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH,\n"
    "    IOS_SIGN_IN_PASSWORD_TEXT_FIELD_XPATH,\n"
    ")\n"
)

EMAIL_LABEL_BLOCK = re.compile(
    r"email_label = WebDriverWait\(driver, \d+\)\.until\(\s*"
    r"EC\.element_to_be_clickable\(\(AppiumBy\.XPATH, '//XCUIElementTypeStaticText\[@name=\"Email\"\]'\)\)\s*"
    r"\)\s*"
    r"email_label\.click\(\)\s*"
    r"time\.sleep\([\d.]+\)\s*"
    r"(?:#[^\n]*\n\s*)*"
    r"email_input = WebDriverWait\(driver, \d+\)\.until\(\s*"
    r"EC\.element_to_be_clickable\(\(AppiumBy\.IOS_PREDICATE, 'type == \"XCUIElementTypeTextField\"'\)\)\s*"
    r"\)",
    re.MULTILINE,
)

PWD_LABEL_BLOCK = re.compile(
    r"password_label = WebDriverWait\(driver, \d+\)\.until\(\s*"
    r"EC\.element_to_be_clickable\(\(AppiumBy\.XPATH, '//XCUIElementTypeStaticText\[@name=\"Password\"\]'\)\)\s*"
    r"\)\s*"
    r"password_label\.click\(\)\s*"
    r"time\.sleep\([\d.]+\)\s*"
    r"(?:#[^\n]*\n\s*)*"
    r"password_input = WebDriverWait\(driver, \d+\)\.until\(\s*"
    r"EC\.element_to_be_clickable\(\(AppiumBy\.IOS_PREDICATE, 'type == \"XCUIElementTypeSecureTextField\"'\)\)\s*"
    r"\)",
    re.MULTILINE,
)

EMAIL_REPL = """email_input = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, IOS_SIGN_IN_EMAIL_CONTAINER_XPATH))
            )"""

PWD_REPL = """password_input = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((AppiumBy.XPATH, IOS_SIGN_IN_PASSWORD_CONTAINER_XPATH))
            )"""

COMMON_UTILS_IMPORT = re.compile(
    r"from common_utils import \(\n(?:.*\n)*?\)\n",
    re.MULTILINE,
)


def patch_file(path: Path) -> bool:
    if path.name in ("cases.py", "run_cases.py", "__init__.py"):
        return False
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if "IOS_SIGN_IN_EMAIL_CONTAINER_XPATH" in raw:
        return False
    if "XCUIElementTypeStaticText[@name=\"Email\"]" not in raw and "XCUIElementTypeTextField" not in raw:
        return False

    t = raw
    m = COMMON_UTILS_IMPORT.search(t)
    if not m:
        print(f"[skip no common_utils import] {path.name}", file=sys.stderr)
        return False
    insert_at = m.end()
    t = t[:insert_at] + IMPORT_LINE + t[insert_at:]

    t = EMAIL_LABEL_BLOCK.sub(EMAIL_REPL, t)
    t = PWD_LABEL_BLOCK.sub(PWD_REPL, t)

    t = t.replace(
        'driver.find_elements(AppiumBy.IOS_PREDICATE, \'type == "XCUIElementTypeTextField"\')',
        "driver.find_elements(AppiumBy.XPATH, IOS_SIGN_IN_EMAIL_CONTAINER_XPATH)",
    )
    t = t.replace(
        'driver.find_elements(AppiumBy.IOS_PREDICATE, \'type == "XCUIElementTypeSecureTextField"\')',
        "driver.find_elements(AppiumBy.XPATH, IOS_SIGN_IN_PASSWORD_CONTAINER_XPATH)",
    )

    t = t.replace(
        "EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, 'type == \"XCUIElementTypeTextField\"'))",
        "EC.presence_of_element_located((AppiumBy.XPATH, IOS_SIGN_IN_EMAIL_TEXT_FIELD_XPATH))",
    )
    t = t.replace(
        "EC.presence_of_element_located((AppiumBy.IOS_PREDICATE, 'type == \"XCUIElementTypeSecureTextField\"'))",
        "EC.presence_of_element_located((AppiumBy.XPATH, IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH))",
    )

    t = t.replace(
        "EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == \"XCUIElementTypeTextField\"'))",
        "EC.element_to_be_clickable((AppiumBy.XPATH, IOS_SIGN_IN_EMAIL_TEXT_FIELD_XPATH))",
    )
    t = t.replace(
        "EC.element_to_be_clickable((AppiumBy.IOS_PREDICATE, 'type == \"XCUIElementTypeSecureTextField\"'))",
        "EC.element_to_be_clickable((AppiumBy.XPATH, IOS_SIGN_IN_PASSWORD_SECURE_FIELD_XPATH))",
    )

    t = t.replace(
        "driver.find_element(AppiumBy.IOS_PREDICATE, 'type == \"XCUIElementTypeTextField\"')",
        "driver.find_element(AppiumBy.XPATH, IOS_SIGN_IN_PASSWORD_TEXT_FIELD_XPATH)",
    )

    if t != raw:
        path.write_text(t, encoding="utf-8")
        return True
    return False


def main() -> int:
    n = 0
    for p in sorted(LOGIN_DIR.glob("*.py")):
        if patch_file(p):
            print(p.name)
            n += 1
    print(f"patched {n} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
