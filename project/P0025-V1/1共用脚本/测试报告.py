#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试报告生成模块

3功能：
- 汇总测试结果并生成 Excel 报告
- 支持正常结束和中断情况下的报告生成
- 统一处理不同脚本的数据格式差异
"""

import os
import sys
from pathlib import Path
from typing import Callable, Optional, Dict, Any


def finalize_results(
    total_tests: int,
    success_count: int,
    failure_count: int,
    detailed_results: Dict[str, Any],
    test_config: Dict[str, Any],
    platform: str,
    network_method: str,
    run_dir: Path,
    log_func: Callable[[str], None] = print,
    interrupted: bool = False
) -> None:
    """
    汇总测试结果并生成报告
    
    Args:
        total_tests: 总测试次数
        success_count: 成功次数
        failure_count: 失败次数
        detailed_results: 详细测试结果，格式为：
            {
                device_name: {
                    "routers": {  # iOS 格式
                        router_name: {
                            "success": int,
                            "failure": int,
                            "rounds": [{round, result, message, ...}] 或 {round_num: {...}}
                        }
                    }
                }
            }
            或
            {
                device_name: {  # Android 格式
                    router_name: {
                        "success": int,
                        "failure": int,
                        "rounds": [{round, result, message, ...}]
                    }
                }
            }
        test_config: 测试配置，包含 success_rate_threshold 等
        platform: 平台名称，"Android" 或 "iOS"
        network_method: 配网方式，"2蓝牙配网"、"1扫码配网" 等
        run_dir: 运行目录（报告保存目录）
        log_func: 日志输出函数，默认为 print
        interrupted: 是否中断
    """
    log_func("\n" + "=" * 80)
    if interrupted:
        log_func("⚠️ 用户中断测试，已保存截至目前的测试数据")
    log_func("📊 测试结果汇总")
    log_func("=" * 80)
    log_func(f"总测试次数: {total_tests}")
    log_func(f"成功次数: {success_count}")
    log_func(f"失败次数: {failure_count}")
    if total_tests > 0:
        log_func(f"成功率: {success_count/total_tests*100:.1f}%")
    else:
        log_func("成功率: 0%")

    # 统一数据格式：转换为标准格式
    # 标准格式：{ device_name: { "routers": { router_name: { success, failure, rounds: {...} } } } }
    standardized_results = _standardize_results(detailed_results)
    
    # 分设备/路由器详细汇总
    log_func("\n🔎 分设备/路由器明细：")
    has_data = False
    for device_name, device_data in standardized_results.items():
        routers = device_data.get("routers", {})
        # 仅统计有数据的路由器
        valid_routers = {
            r: stats for r, stats in routers.items() 
            if stats.get('success', 0) + stats.get('failure', 0) > 0
        }
        if not valid_routers:
            continue
        has_data = True
        log_func(f"\n📱 设备: {device_name}")
        for router_name, stats in valid_routers.items():
            log_func(f"  📶 路由器: {router_name}  成功: {stats.get('success', 0)}  失败: {stats.get('failure', 0)}")
            
            # 处理 rounds（可能是列表或字典）
            rounds = stats.get('rounds', [])
            if isinstance(rounds, dict):
                # 如果是字典，转换为列表以便遍历
                rounds = [{"round": k, **v} for k, v in rounds.items()]
            
            failed_rounds = [r for r in rounds if r.get('result') != 'success']
            if failed_rounds:
                for fr in failed_rounds:
                    timestamp = fr.get('timestamp', '未知时间')
                    round_num = fr.get('round', '?')
                    result = fr.get('result', '?')
                    message = fr.get('message', '?')
                    log_func(f"    ❌ 轮次#{round_num} 结果: {result}  原因: {message}  时间: {timestamp}")
            else:
                log_func("    ✅ 全部成功")
    
    if not has_data:
        log_func("⚠️ 没有可汇总的测试数据")
    
    # 检查成功率阈值
    success_rate = success_count / total_tests if total_tests > 0 else 0
    if total_tests > 0:
        threshold = test_config.get('success_rate_threshold', 0.8)
        if success_rate >= threshold:
            log_func(f"✅ 测试通过！成功率 {success_rate*100:.1f}% 达到阈值 {threshold*100:.1f}%")
        else:
            log_func(f"❌ 测试失败！成功率 {success_rate*100:.1f}% 未达到阈值 {threshold*100:.1f}%")
    else:
        log_func("⚠️ 因未执行任何测试，无法计算成功率")
    
    # 仅在有数据时生成报告
    if has_data:
        try:
            # 导入 excel_report_generator
            current_file = Path(__file__).resolve()
            common_dir = current_file.parent
            excel_gen_path = common_dir / "excel_report_generator.py"
            
            if not excel_gen_path.exists():
                # 尝试其他位置
                search_paths = [
                    common_dir / "excel_report_generator.py",
                    common_dir.parent / "1共用脚本" / "excel_report_generator.py",
                    common_dir.parent / "common" / "excel_report_generator.py",
                ]
                for path in search_paths:
                    if path.exists():
                        excel_gen_path = path
                        break
            
            if excel_gen_path.exists():
                # 将 excel_report_generator 所在目录添加到 sys.path
                excel_gen_dir = str(excel_gen_path.parent)
                if excel_gen_dir not in sys.path:
                    sys.path.insert(0, excel_gen_dir)
                
                from excel_report_generator import create_network_compatibility_report
                log_func("\n📊 生成Excel测试报告...")
                
                # 转换为 Excel 报告生成器期望的格式
                excel_results = _convert_to_excel_format(standardized_results)
                
                # 生成报告
                excel_file = create_network_compatibility_report(
                    excel_results,
                    platform=platform,
                    network_method=network_method,
                    output_dir=str(run_dir)
                )
                
                if excel_file:
                    log_func(f"✅ Excel报告已生成: {excel_file}")
                    log_func(f"📁 报告目录: {run_dir}")
                else:
                    log_func(f"⚠️ Excel报告生成失败，但报告目录为: {run_dir}")
            else:
                log_func(f"⚠️ 未找到 excel_report_generator.py，跳过Excel报告生成")
                log_func(f"📁 报告目录: {run_dir}")
        except Exception as e:
            log_func(f"⚠️ Excel报告生成失败: {e}")
            log_func(f"📁 报告目录: {run_dir}")
            log_func(f"💡 提示: 测试数据已保存在上述目录中，可以手动查看日志文件")
            import traceback
            log_func(f"详细错误: {traceback.format_exc()}")
    else:
        log_func("⚠️ 无测试数据，跳过Excel报告生成")


def _standardize_results(detailed_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    统一数据格式，将不同脚本的数据格式转换为标准格式
    
    标准格式：
    {
        device_name: {
            "routers": {
                router_name: {
                    "success": int,
                    "failure": int,
                    "rounds": {round_num: {result, message, ...}}
                }
            }
        }
    }
    """
    standardized = {}
    
    for device_name, device_data in detailed_results.items():
        standardized[device_name] = {"routers": {}}
        
        # 判断数据格式：iOS 格式有 "routers" 键，Android 格式直接是 router_name
        if "routers" in device_data:
            # iOS 格式
            routers = device_data["routers"]
        else:
            # Android 格式：device_data 本身就是 routers
            routers = device_data
        
        for router_name, router_data in routers.items():
            standardized[device_name]["routers"][router_name] = {
                "success": router_data.get("success", 0),
                "failure": router_data.get("failure", 0),
                "rounds": {}
            }
            
            # 处理 rounds：可能是列表或字典
            rounds = router_data.get("rounds", [])
            if isinstance(rounds, list):
                # 列表格式：转换为字典
                for round_item in rounds:
                    round_num = round_item.get("round")
                    if round_num is not None:
                        # 移除 'round' 键，因为 round_num 已经作为字典的 key
                        round_data = {k: v for k, v in round_item.items() if k != 'round'}
                        standardized[device_name]["routers"][router_name]["rounds"][round_num] = round_data
            elif isinstance(rounds, dict):
                # 已经是字典格式，直接复制
                standardized[device_name]["routers"][router_name]["rounds"] = rounds.copy()
    
    return standardized


def _convert_to_excel_format(standardized_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    转换为 Excel 报告生成器期望的格式
    
    Excel 格式：
    {
        device_name: {
            "routers": {
                router_name: {
                    "success": int,
                    "failure": int,
                    "rounds": {round_num: {result, message}}
                }
            }
        }
    }
    """
    excel_results = {}
    
    for device_name, device_data in standardized_results.items():
        excel_results[device_name] = {"routers": {}}
        routers = device_data.get("routers", {})
        
        for router_name, router_data in routers.items():
            excel_results[device_name]["routers"][router_name] = {
                "success": router_data.get("success", 0),
                "failure": router_data.get("failure", 0),
                "rounds": {}
            }
            
            # 处理 rounds，确保格式正确
            rounds = router_data.get("rounds", {})
            if isinstance(rounds, dict):
                for round_num, round_data in rounds.items():
                    # 只保留 result 和 message
                    excel_results[device_name]["routers"][router_name]["rounds"][round_num] = {
                        "result": round_data.get("result", ""),
                        "message": round_data.get("message", "")
                    }
    
    return excel_results


if __name__ == "__main__":
    # 测试代码
    test_results = {
        "device1": {
            "routers": {
                "router1": {
                    "success": 2,
                    "failure": 1,
                    "rounds": [
                        {"round": 1, "result": "success", "message": ""},
                        {"round": 2, "result": "success", "message": ""},
                        {"round": 3, "result": "failed", "message": "连接超时"}
                    ]
                }
            }
        }
    }
    
    test_config = {
        "success_rate_threshold": 0.8
    }
    
    run_dir = Path("/tmp/test_reports")
    run_dir.mkdir(parents=True, exist_ok=True)
    
    finalize_results(
        total_tests=3,
        success_count=2,
        failure_count=1,
        detailed_results=test_results,
        test_config=test_config,
        platform="Android",
        network_method="2蓝牙配网",
        run_dir=run_dir,
        log_func=print,
        interrupted=False
    )
