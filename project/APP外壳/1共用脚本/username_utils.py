"""
用户名随机数据工具。

主要用途：
- 生成不同长度、不同字符类型的随机用户名
- 支持字母、数字、字母数字混合等场景
- 供注册与个人信息相关用例复用
"""

import random
import string


def ran1(length=60):
    """生成指定长度的随机字母用户名，默认 60 位。"""
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))


def ran2(length=50):
    """生成指定长度的随机数字用户名，默认 50 位。"""
    return ''.join(random.choice(string.digits) for _ in range(length))


def ran3(length=49):
    """生成指定长度的随机数字+字母混合用户名，默认 49 位。"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


def ran4(length=50):
    """生成指定长度的随机字母用户名"""
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))


def ran5(length=50):
    """生成指定长度的随机数字用户名"""
    return ''.join(random.choice(string.digits) for _ in range(length))


def ran6(length=50):
    """生成指定长度的随机数字+字母混合用户名"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

