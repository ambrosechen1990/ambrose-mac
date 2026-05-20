"""
邮箱生成工具。

主要用途：
- 生成注册流程使用的邮箱地址
- 维护邮箱计数配置
- 记录已使用过的特殊字符邮箱，避免重复使用
"""

import json
import random
from pathlib import Path


def _get_config_file() -> Path:
    """
    邮箱计数配置路径，位于 1共用脚本/data 下。
    若目录不存在则自动创建。
    """
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "email_counter_config.json"


def _get_used_special_char_emails_file() -> Path:
    """已用于注册流程的特殊字符邮箱列表（每行一个），位于 data 下。"""
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "used_special_char_registration_emails.txt"


def _load_used_special_char_emails() -> set[str]:
    path = _get_used_special_char_emails_file()
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _append_used_special_char_email(email: str) -> None:
    path = _get_used_special_char_emails_file()
    with open(path, "a", encoding="utf-8") as f:
        f.write(email.strip() + "\n")


def get_next_email() -> str:
    """获取包含特殊字符的邮箱地址。"""
    config_file = _get_config_file()

    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {
            "base_email": "1+2-3.4%5_68",
            "domain": "@163.com",
            "current_number": 7,
            "start_number": 7,
            "max_number": 999,
        }

    current_num = config["current_number"]
    if current_num > config["max_number"]:
        current_num = config["start_number"]

    email = f"{config['base_email']}{current_num}{config['domain']}"
    config["current_number"] = current_num + 1

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"📧 生成邮箱地址: {email}")
    return email


def get_next_unused_special_char_email() -> str:
    """
    获取未使用过的特殊字符邮箱。

    格式固定为：
    1+2-3.4%5_6 + 5位随机数字 + @163.com

    例如：
    1+2-3.4%5_612345@163.com

    返回前会先排除 data/used_special_char_registration_emails.txt
    中已记录的邮箱；本次返回的地址会立即追加到该文件，后续不再分配。
    """
    used = _load_used_special_char_emails()
    max_iterations = 200
    random_generator = random.SystemRandom()
    prefix = "1+2-3.4%5_6"
    domain = "@163.com"

    for _ in range(max_iterations):
        random_digits = f"{random_generator.randint(0, 99999):05d}"
        email = f"{prefix}{random_digits}{domain}"
        if email not in used:
            _append_used_special_char_email(email)
            print(f"📧 生成未使用过的特殊字符邮箱: {email}")
            return email

    raise RuntimeError(
        "随机生成多次后仍未找到未使用的特殊字符邮箱，请检查 used_special_char_registration_emails.txt。"
    )


def get_next_unsupported_email() -> str:
    """获取包含不支持特殊字符、且未被使用过的邮箱地址。"""
    config_file = _get_config_file()

    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {
            "base_email": "1+2-3.4%5_68",
            "domain": "@163.com",
            "current_number": 7,
            "start_number": 7,
            "max_number": 999,
        }

    current_num = config.get("unsupported_current_number", 7)
    start_num = config.get("unsupported_start_number", 7)
    max_num = config.get("unsupported_max_number", 999)
    if current_num > max_num:
        current_num = start_num

    email = f"1/2-3；4*5_6{current_num}@163.com"
    config["unsupported_current_number"] = current_num + 1
    config["unsupported_start_number"] = start_num
    config["unsupported_max_number"] = max_num

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"📧 生成不支持特殊字符邮箱地址: {email}")
    return email


def get_simple_email() -> str:
    """获取普通邮箱地址（无特殊字符）。"""
    config_file = _get_config_file()

    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {
            "base_email": "testuser",
            "domain": "@163.com",
            "current_number": 1,
            "start_number": 1,
            "max_number": 999,
        }

    current_num = config.get("simple_current_number", 1)
    email = f"testuser{current_num}{config['domain']}"
    config["simple_current_number"] = current_num + 1

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"📧 生成简单邮箱地址: {email}")
    return email
