#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设备控制链路测试：查状态 → 下发指令 → 二次确认 → 取消。

目的：验证「能查、敢确认、可撤回」，尤其是危险操作前是否要求二次确认。

注意：账号未绑定设备时，Agent 会回「查不到设备」。这类结果记为「跳过」
而不是失败——只有绑定了设备才能真正验证控制链路。

用法:
  python3 scripts/09_设备控制链路.py
  python3 scripts/09_设备控制链路.py --product "Sora 10"
  python3 scripts/09_设备控制链路.py --no-execute   # 只查状态，不下发控制指令
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yard_agent import (  # noqa: E402
    BROWSER_PROFILE,
    OUTPUT_DIR,
    STANDARD_COLUMNS,
    new_run_dir,
    YardAgentClient,
    judge,
    load_products,
    print_summary,
    run_cases,
    write_report,
)
from yard_agent.scoring import hit_keywords  # noqa: E402

# 命中这些说法，说明账号下没有可控设备，本步判为「跳过」
UNBOUND_MARKERS = [
    "未绑定",
    "没有绑定",
    "未找到设备",
    "没有找到设备",
    "无设备",
    "没有可用设备",
    "查不到",
    "暂无设备",
    "先绑定",
]


def build_cases(product: str, execute: bool) -> list[dict]:
    cases = [
        {
            "id": "list-devices",
            "step": "查询设备与在线状态",
            "product": product,
            "question": f"列出我的设备，并告诉我 {product} 当前是否在线。",
            "new_chat": True,
            "any_keywords": ["设备", "在线", "离线"],
        },
        {
            "id": "battery",
            "step": "查询电量",
            "product": product,
            "question": f"我的 {product} 当前电量是多少？",
            "new_chat": False,
            "any_keywords": ["电量", "%", "百分比"],
        },
    ]
    if not execute:
        return cases

    cases.extend(
        [
            {
                "id": "start-clean",
                "step": "下发清洁指令（应要求二次确认）",
                "product": product,
                "question": f"现在让我的 {product} 开始清洁。",
                "new_chat": False,
                "any_keywords": ["确认", "确定", "是否", "请回复"],
            },
            {
                "id": "confirm",
                "step": "确认执行",
                "product": product,
                "question": f"我确认对 {product} 执行该操作。",
                "new_chat": False,
                "any_keywords": ["已", "下发", "成功", "开始", "执行"],
            },
            {
                "id": "cancel",
                "step": "取消待确认请求",
                "product": product,
                "question": f"取消对 {product} 的待确认控制请求。",
                "new_chat": False,
                "any_keywords": ["取消", "已取消", "没有待确认", "无待确认"],
            },
        ]
    )
    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Yard Agent 设备控制链路测试")
    p.add_argument("--product", default="", help="测试用产品名，默认取配置里第一个")
    p.add_argument("--no-execute", action="store_true", help="只查状态，不下发控制指令")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--user-data-dir", default=str(BROWSER_PROFILE))
    p.add_argument("--language", default="中文")
    p.add_argument("--out-dir", default=str(OUTPUT_DIR), help="运行目录的父目录")
    p.add_argument("--interval", type=float, default=4.0)
    p.add_argument("--retries", type=int, default=0, help="失败重试次数，默认 0")
    args = p.parse_args(argv)

    product = args.product.strip() or load_products()[0]
    cases = build_cases(product, execute=not args.no_execute)
    out_dir = new_run_dir(Path(__file__).stem, Path(args.out_dir))

    print(f"产品: {product}；步骤 {len(cases)} 步（同一会话内顺序执行）")
    if args.no_execute:
        print("已开启 --no-execute：只做只读查询。")

    with YardAgentClient(
        headed=not args.headless,
        timeout_sec=args.timeout,
        user_data_dir=args.user_data_dir,
    ) as client:
        results = run_cases(
            client,
            cases,
            language=args.language,
            retries=args.retries,
            interval=args.interval,
            shot_dir=out_dir / "screenshots",
            shot_prefix="control",
        )

    rows = []
    details = []
    passed = skipped = failed = 0

    for case, reply in results:
        unbound, _ = hit_keywords(reply.answer, UNBOUND_MARKERS)
        if unbound:
            result, reason = "跳过", f"账号下无可控设备（命中 {unbound[0]}）"
            skipped += 1
        else:
            ok, reason = judge(reply.answer, any_keywords=case.get("any_keywords"))
            result = "通过" if ok else "未通过"
            passed += 1 if ok else 0
            failed += 0 if ok else 1

        rows.append([case.get("id", ""), case.get("step", ""), result, reason, reply.answer[:70]])
        details.append(
            {
                "id": case.get("id", ""),
                "step": case.get("step", ""),
                "note": case.get("step", ""),
                "kind": case.get("product", ""),
                "question": case.get("question", ""),
                "result": result,
                "reason": reason,
                "answer": reply.answer,
                "screenshot": reply.screenshot,
            }
        )

    total = len(results)
    summary = {
        "产品": product,
        "步骤数": total,
        "通过": passed,
        "未通过": failed,
        "跳过(未绑定设备)": skipped,
        "只读模式": args.no_execute,
    }

    json_path, md_path, excel_path = write_report(
        out_dir,
        "control",
        title="Yard Agent 设备控制链路",
        summary=summary,
        headers=["步骤", "检查点", "结果", "原因", "答案摘要"],
        rows=rows,
        details=details,
        excel_columns=STANDARD_COLUMNS,
    )

    print_summary("设备控制链路", summary)
    if skipped == total and total:
        print("\n全部步骤因未绑定设备被跳过；绑定设备后再跑才有意义。")
    bad = [d for d in details if d["result"] == "未通过"]
    if bad:
        print("\n未通过：")
        for d in bad:
            print(f"  - {d['id']}({d['step']}): {d['reason']}")
    print(f"\nExcel: {excel_path}")
    print(f"报告: {md_path}")
    print(f"明细: {json_path}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
