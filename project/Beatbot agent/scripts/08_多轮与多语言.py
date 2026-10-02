#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多轮上下文与多语言测试。

目的：
  1. 多轮：第二轮用「它」这类指代追问，看 Agent 是否还记得上文说的是哪台机器
  2. 多语言：切到 English / 日本語 提问，看回答语言是否跟着切

用法:
  python3 scripts/08_多轮与多语言.py
  python3 scripts/08_多轮与多语言.py --product "Sora 10" --skip-lang
  python3 scripts/08_多轮与多语言.py --languages English
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

# 语言名 -> 期望识别出的语言代码（detect_language 只区分 zh / en）
LANGUAGE_EXPECT = {
    "English": "en",
    "中文": "zh",
}


def build_multiturn_cases(product: str) -> list[dict]:
    """同一会话内连续三轮，只有第一轮新建对话。"""
    return [
        {
            "id": "turn1-depth",
            "product": product,
            "question": f"{product} 的工作水深是多少？",
            "new_chat": True,
            "expect_keywords": [],
            "any_keywords": ["水深", "米", "m"],
            "check": "首轮应给出水深信息",
        },
        {
            "id": "turn2-pronoun",
            "product": product,
            "question": "它的续航大概多久？",
            "new_chat": False,
            "any_keywords": ["续航", "小时", "分钟", "电池", "电量"],
            "check": "用「它」指代，应仍在谈同一台机器的续航",
        },
        {
            "id": "turn3-recall",
            "product": product,
            "question": "把刚才说的工作水深再重复一遍，只说数字范围。",
            "new_chat": False,
            "any_keywords": ["米", "m", "水深"],
            "check": "应能回看上文，复述水深",
        },
    ]


def build_language_cases(product: str, languages: list[str]) -> list[dict]:
    cases = []
    for lang in languages:
        if lang == "English":
            question = f"What is the working water depth of {product}?"
        else:
            question = f"{product} 的工作水深是多少？"
        cases.append(
            {
                "id": f"lang-{lang}",
                "product": product,
                "question": question,
                "language": lang,
                "new_chat": True,
                "expect_language": LANGUAGE_EXPECT.get(lang, ""),
                "check": f"回答语言应为 {lang}",
            }
        )
    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Yard Agent 多轮上下文与多语言测试")
    p.add_argument("--product", default="", help="测试用产品名，默认取配置里第一个")
    p.add_argument("--languages", default="English", help="要验证的语言，逗号分隔")
    p.add_argument("--skip-multiturn", action="store_true", help="跳过多轮测试")
    p.add_argument("--skip-lang", action="store_true", help="跳过多语言测试")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--user-data-dir", default=str(BROWSER_PROFILE))
    p.add_argument("--out-dir", default=str(OUTPUT_DIR), help="运行目录的父目录")
    p.add_argument("--interval", type=float, default=4.0)
    p.add_argument("--retries", type=int, default=0, help="失败重试次数，默认 0")
    args = p.parse_args(argv)

    product = args.product.strip() or load_products()[0]
    languages = [s.strip() for s in args.languages.split(",") if s.strip()]

    cases: list[dict] = []
    if not args.skip_multiturn:
        cases.extend(build_multiturn_cases(product))
    if not args.skip_lang:
        cases.extend(build_language_cases(product, languages))
    if not cases:
        print("多轮与多语言都被跳过，无事可做。")
        return 2

    out_dir = new_run_dir(Path(__file__).stem, Path(args.out_dir))
    print(f"产品: {product}；用例 {len(cases)} 条（多轮保持同一会话）")

    with YardAgentClient(
        headed=not args.headless,
        timeout_sec=args.timeout,
        user_data_dir=args.user_data_dir,
    ) as client:
        results = run_cases(
            client,
            cases,
            language="中文",
            retries=args.retries,
            interval=args.interval,
            shot_dir=out_dir / "screenshots",
            shot_prefix="dialog",
        )

    rows = []
    details = []
    passed = 0
    for case, reply in results:
        ok, reason = judge(
            reply.answer,
            expect_keywords=case.get("expect_keywords"),
            any_keywords=case.get("any_keywords"),
            forbid_keywords=case.get("forbid_keywords"),
            expect_language=case.get("expect_language", ""),
        )
        passed += 1 if ok else 0
        rows.append(
            [
                case.get("id", ""),
                case.get("check", ""),
                "通过" if ok else "未通过",
                reason,
                reply.answer[:70],
            ]
        )
        details.append(
            {
                "id": case.get("id", ""),
                "question": case.get("question", ""),
                "check": case.get("check", ""),
                "note": case.get("check", ""),
                "kind": case.get("language", "中文"),
                "language": case.get("language", "中文"),
                "passed": ok,
                "result": "通过" if ok else "未通过",
                "reason": reason,
                "answer": reply.answer,
                "screenshot": reply.screenshot,
            }
        )

    total = len(results)
    summary = {
        "产品": product,
        "用例数": total,
        "通过": passed,
        "未通过": total - passed,
        "通过率": f"{passed}/{total}" + (f" ({passed / total:.0%})" if total else ""),
    }

    json_path, md_path, excel_path = write_report(
        out_dir,
        "dialog",
        title="Yard Agent 多轮上下文与多语言",
        summary=summary,
        headers=["用例", "检查点", "结果", "原因", "答案摘要"],
        rows=rows,
        details=details,
        excel_columns=STANDARD_COLUMNS,
    )

    print_summary("多轮与多语言", summary)
    failed = [d for d in details if not d["passed"]]
    if failed:
        print("\n未通过：")
        for d in failed:
            print(f"  - {d['id']}: {d['reason']}")
    print(f"\nExcel: {excel_path}")
    print(f"报告: {md_path}")
    print(f"明细: {json_path}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
