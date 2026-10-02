#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多产品批量问答测试（主回归）。

默认全量：每个产品跑完整题库；多个产品各开一个窗口，互不等，最后汇总报告。
题库默认读 config/测试题库.xlsx 的「功能测试库」工作表，在表尾追加行即可补题。

用法:
  python3 scripts/03_多产品批量问答.py
  python3 scripts/03_多产品批量问答.py --products "Sora 10,GT100"
  python3 scripts/03_多产品批量问答.py --windows 5   # 想同时开更多窗口时再加
  python3 scripts/03_多产品批量问答.py --library Agent行为库
  python3 scripts/03_多产品批量问答.py --resume
  python3 scripts/03_多产品批量问答.py --preview-questions
  python3 scripts/03_多产品批量问答.py --list-products
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yard_agent import (  # noqa: E402
    BROWSER_PROFILE,
    OUTPUT_DIR,
    generate_questions,
    question_pool,
    latest_run_dir,
    load_products,
    new_run_dir,
    parse_products,
    run_batch,
)
from yard_agent.parallel import run_parallel_products  # noqa: E402
from yard_agent.paths import PRODUCTS_XLSX, QUESTION_TEMPLATES_XLSX  # noqa: E402
from yard_agent.questions import resolve_templates_path  # noqa: E402


def _eta(total: int, interval: float) -> str:
    """按每题约 30s 估算总耗时。"""
    minutes = total * (30 + max(interval, 0)) / 60
    return f"{minutes / 60:.1f} 小时" if minutes >= 60 else f"{minutes:.0f} 分钟"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Yard Agent 多产品批量问答 / 导出 Excel")
    p.add_argument("--batch", action="store_true", help="（默认行为，保留兼容）批量测试并导出 Excel")
    p.add_argument(
        "--coverage",
        choices=("full", "split"),
        default="full",
        help="默认 full=每个产品跑完整题库；split=各产品分摊题库（仅需快速扫一遍时用）",
    )
    p.add_argument(
        "--per-product",
        type=int,
        default=None,
        help="每产品问题数；full 默认整个题库（传 0 也是），split 默认 80",
    )
    p.add_argument(
        "--products",
        default="",
        help='产品列表，逗号分隔；默认全部。例: "Sora 10,GT100"',
    )
    p.add_argument("--preview-questions", action="store_true", help="只打印生成的问题")
    p.add_argument("--list-products", action="store_true", help="列出产品")
    p.add_argument("--headed", action="store_true", default=True)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--user-data-dir", default=str(BROWSER_PROFILE))
    p.add_argument("--language", default="中文")
    p.add_argument(
        "--templates",
        default=str(QUESTION_TEMPLATES_XLSX),
        help="题库 Excel（默认 config/测试题库.xlsx）。在表里追加行即可补题",
    )
    p.add_argument(
        "--library",
        default="功能测试库",
        help="读取哪个工作表，默认「功能测试库」",
    )
    p.add_argument(
        "--type",
        default="",
        help="只跑指定问题类型，逗号分隔。例: 售后物流,故障排查",
    )
    p.add_argument("--out-dir", default=str(OUTPUT_DIR), help="运行目录的父目录")
    p.add_argument("--resume", action="store_true", help="接着上一次运行目录的 checkpoint.jsonl 续跑")
    p.add_argument("--resume-from", default="", help="指定续跑用的 checkpoint.jsonl")
    p.add_argument("--no-new-chat", action="store_true", help="关闭每产品切换时新建对话")
    p.add_argument("--new-chat-every", type=int, default=5, help="每 N 题新建对话，默认 5")
    p.add_argument("--retries", type=int, default=0, help="失败重试次数，默认 0（不重试，直接记失败）")
    p.add_argument("--retry-delay", type=float, default=3.0, help="重试等待秒数，默认 3")
    p.add_argument("--interval", type=float, default=4.0, help="题间隔秒数，默认 4")
    p.add_argument(
        "--windows",
        type=int,
        default=3,
        help="同时开着的窗口数，默认 3；多出来的产品自动排队",
    )
    p.add_argument("--serial", action="store_true", help="强制单窗口串行，不按产品开窗口")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    headed = not args.headless
    products = parse_products(args.products)

    if args.list_products:
        for name in load_products():
            print(f"- {name}")
        print(f"（来源: {PRODUCTS_XLSX}）")
        return 0

    coverage = args.coverage
    # full 不限量：0 会被出题函数解释成「整个题库」
    per_product = args.per_product
    if per_product is None:
        per_product = 0 if coverage == "full" else 80

    templates_path = Path(args.templates)
    if not templates_path.is_file():
        templates_path = resolve_templates_path()
    type_filter = [
        s.strip()
        for s in args.type.replace("，", ",").replace("、", ",").split(",")
        if s.strip()
    ]
    print(f"题库: {templates_path} / {args.library}" + (f" / 类型 {type_filter}" if type_filter else ""))

    pool = len(
        question_pool(
            args.language,
            path=templates_path,
            library=args.library,
            types=type_filter or None,
        )
    )
    each = pool if per_product <= 0 else per_product
    windows = 1 if args.serial else max(1, min(args.windows, len(products)))
    batches = math.ceil(len(products) / windows) if products else 1
    print(
        f"全量式：{len(products)} 个产品 × 每产品 {each} 题"
        if coverage == "full"
        else f"分布式：{len(products)} 个产品分摊题库，每产品 {each} 题"
    )
    if windows == 1:
        print(f"单窗口串行，约 {_eta(each * max(len(products), 1), args.interval)}")
    elif windows < len(products):
        print(
            f"最多同时 {windows} 个窗口，另有 {len(products) - windows} 个产品排队，"
            f"墙钟约 {_eta(each * batches, args.interval)}"
        )
    else:
        print(f"将开 {windows} 个窗口并行（互不等），墙钟约 {_eta(each, args.interval)}")

    if args.preview_questions:
        for i, p in enumerate(products):
            index = 0 if coverage == "full" else i
            qs = generate_questions(
                p,
                per_product,
                index=index,
                language=args.language,
                templates_path=templates_path,
                library=args.library,
                types=type_filter or None,
            )
            print(f"\n# {p} ({len(qs)})")
            for i, q in enumerate(qs, 1):
                print(f"{i:03d}. {q}")
        return 0

    script_name = Path(__file__).stem
    prev_run: Path | None = None
    resume_from: Path | None = None
    if args.resume_from:
        resume_from = Path(args.resume_from)
        prev_run = resume_from.parent if resume_from.is_file() else resume_from
    elif args.resume:
        # 必须在新建本轮目录之前找，否则「最近一次」会是刚建的空目录
        prev_run = latest_run_dir(script_name, Path(args.out_dir))
        resume_from = prev_run / "checkpoint.jsonl" if prev_run else None

    out_dir = new_run_dir(script_name, Path(args.out_dir))
    use_parallel = (not args.serial) and len(products) > 1

    if use_parallel:
        run_parallel_products(
            products=products,
            per_product=per_product,
            coverage=coverage,
            headed=headed,
            timeout=args.timeout,
            language=args.language,
            out_dir=out_dir,
            new_chat_each_product=not args.no_new_chat,
            resume=args.resume or bool(args.resume_from),
            prev_run=prev_run,
            retries=args.retries,
            retry_delay=args.retry_delay,
            interval=args.interval,
            new_chat_every=args.new_chat_every,
            windows=windows,
            profile_source=args.user_data_dir,
            templates_path=templates_path,
            library=args.library,
            types=type_filter or None,
        )
        return 0

    run_batch(
        products=products,
        per_product=per_product,
        coverage=coverage,
        headed=headed,
        timeout=args.timeout,
        user_data_dir=args.user_data_dir,
        language=args.language,
        out_dir=out_dir,
        new_chat_each_product=not args.no_new_chat,
        resume=args.resume or bool(args.resume_from),
        resume_from=resume_from,
        retries=args.retries,
        retry_delay=args.retry_delay,
        interval=args.interval,
        new_chat_every=args.new_chat_every,
        templates_path=templates_path,
        library=args.library,
        types=type_filter or None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
