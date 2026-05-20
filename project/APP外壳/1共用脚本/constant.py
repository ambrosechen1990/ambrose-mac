"""
历史常量与随机测试数据模块。

主要用途：
- 提供旧脚本仍在使用的邮箱、密码和随机字符串变量
- 兼容早期直接导入常量的测试脚本
- 为未迁移脚本保留基础测试数据来源
"""

import random
import string
import time


#邮箱名称和密码
email = "13402612115@gmail.com"
password = "Aa12345678"

# 获取随机字符串的函数，每次调用都会生成新的随机值
def get_random_letters(length=8):
    """生成指定长度的随机字母字符串"""
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))

def get_random_alphanumeric(length=20):
    """生成指定长度的随机字母+数字字符串"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

def get_random_with_special(length=50):
    """生成指定长度的随机字母+数字+特殊字符字符串"""
    return ''.join(random.choice(string.ascii_letters + string.digits + string.punctuation) for _ in range(length))

# 为了向后兼容，我们保留这些常量，但每次导入时会重新生成
# 随机数字8位数字
ran1 = get_random_letters(8)
# 生成一个由随机字母和数字组成的字符串，长度为20
ran2 = get_random_alphanumeric(20)
#包含字母、数字、特殊字符的随机字符串
ran3 = get_random_with_special(51)
#包含字母、数字、特殊字符的随机字符串
ran4 = get_random_with_special(50)
# 生成一个由随机字母组成的字符串，长度为80
ran5 = get_random_letters(80)
# 生成一个由随机字母+数字组成的字符串，长度20
ran6 = get_random_alphanumeric(20)

# 使用时间戳作为随机种子，确保每次运行生成不同的随机数
random.seed(int(time.time()))

