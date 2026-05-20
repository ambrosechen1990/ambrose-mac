#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Excel文件对比工具 - 独立入口
用于对比两个Excel文件，找出新增型号和数量增加的型号
"""

import sys
import os

# 添加当前目录到路径，以便导入excel_processor
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from excel_processor import main_compare, compare_two_excel_files

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        # 命令行模式
        new_file = sys.argv[1]
        old_file = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else None
        
        print("🔍 Excel文件对比工具")
        print("=" * 50)
        print(f"📄 新文件: {new_file}")
        print(f"📄 旧文件: {old_file}")
        if output_file:
            print(f"💾 输出文件: {output_file}")
        else:
            print(f"💾 输出文件: 覆盖新文件")
        print("=" * 50)
        
        result = compare_two_excel_files(new_file, old_file, output_file)
        if result:
            print(f"\n🎉 对比完成！")
            print(f"📁 输出文件: {result}")
            print("\n✅ 请打开文件查看'对比结果'工作表")
        else:
            print("\n💥 对比失败!")
            sys.exit(1)
    else:
        # GUI模式
        print("🔍 Excel文件对比工具 - GUI模式")
        print("=" * 50)
        print("如果没有提供命令行参数，将启动GUI界面")
        print("命令行用法: python excel_compare.py <新文件> <旧文件> [输出文件]")
        print("=" * 50)
        main_compare()

