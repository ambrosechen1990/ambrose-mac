#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归对比：把本次批量结果与基线逐题 diff（离线，不开浏览器）。

目的：只看「变差的那几十题」，不用重读整份 Excel。

默认对比 output/ 下最近两次 03 批量的运行目录，不指定路径即可直接跑。

用法:
  python3 scripts/06_回归对比.py
  python3 scripts/06_回归对比.py --base output/<旧目录>/checkpoint.jsonl --new output/<新目录>/checkpoint.jsonl
  python3 scripts/06_回归对比.py --threshold 0.9
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yard_agent import (  # noqa: E402
    OUTPUT_DIR,
    new_run_dir,
    print_summary,
    run_dirs,
    similarity,
    write_report,
)
from yard_agent.style import is_transient_failure  # noqa: E402
from yard_agent.models import AgentReply  # noqa: E402


def load_checkpoint(path: Path) -> dict[str, dict]:
    """读取 checkpoint.jsonl，按 产品||问题 建索引；同题取最后一次。"""
    if not path.is_file():
        raise SystemExit(f"找不到结果文件: {path}")
    records: dict[str, dict] = {}
    # 文件可能被中断写入，容忍坏行
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = f"{obj.get('product', '')}||{obj.get('question', '')}"
            records[key] = obj
    return records


def is_failed(obj: dict) -> bool:
    reply = AgentReply(
        question=obj.get("question", ""),
        answer=obj.get("answer", ""),
        status=obj.get("status", ""),
    )
    return is_transient_failure(reply)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Yard Agent 回归对比")
    p.add_argument("--base", default="", help="基线 checkpoint.jsonl；留空取上上次批量运行目录")
    p.add_argument("--new", default="", help="本次 checkpoint.jsonl；留空取最近一次批量运行目录")
    p.add_argument("--threshold", type=float, default=0.85, help="答案相似度低于该值视为变化，默认 0.85")
    p.add_argument("--out-dir", default=str(OUTPUT_DIR), help="运行目录的父目录")
    p.add_argument("--show", type=int, default=20, help="控制台最多打印几条，默认 20")
    args = p.parse_args(argv)

    batch_runs = run_dirs("03_多产品批量问答", OUTPUT_DIR)
    base_path = Path(args.base) if args.base else None
    new_path = Path(args.new) if args.new else None
    if new_path is None and batch_runs:
        new_path = batch_runs[-1] / "checkpoint.jsonl"
    if base_path is None and len(batch_runs) >= 2:
        base_path = batch_runs[-2] / "checkpoint.jsonl"
    if base_path is None or new_path is None:
        print(
            "缺少对比对象：需要两轮批量结果。"
            "请先跑两次 03_多产品批量问答.py，或用 --base/--new 指定 checkpoint.jsonl。",
            file=sys.stderr,
        )
        return 2
    print(f"基线: {base_path}\n本次: {new_path}")

    base = load_checkpoint(base_path)
    new = load_checkpoint(new_path)

    base_keys = set(base)
    new_keys = set(new)
    common = base_keys & new_keys

    rows = []
    details = []
    counts = {"退化": 0, "改善": 0, "内容变化": 0, "新增": 0, "缺失": 0}

    for key in sorted(common):
        b, n = base[key], new[key]
        b_fail, n_fail = is_failed(b), is_failed(n)
        b_ans, n_ans = b.get("answer", ""), n.get("answer", "")
        sim = similarity(b_ans, n_ans)

        if not b_fail and n_fail:
            kind = "退化"
        elif b_fail and not n_fail:
            kind = "改善"
        elif sim < args.threshold:
            kind = "内容变化"
        else:
            continue

        counts[kind] += 1
        product, question = key.split("||", 1)
        rows.append([kind, product, question[:50], f"{sim:.2f}", n_ans[:60]])
        details.append(
            {
                "kind": kind,
                "product": product,
                "question": question,
                "similarity": round(sim, 3),
                "base_status": b.get("status", ""),
                "new_status": n.get("status", ""),
                "base_answer": b_ans,
                "new_answer": n_ans,
            }
        )

    for key in sorted(new_keys - base_keys):
        counts["新增"] += 1
        product, question = key.split("||", 1)
        rows.append(["新增", product, question[:50], "-", new[key].get("answer", "")[:60]])
        details.append({"kind": "新增", "product": product, "question": question})

    for key in sorted(base_keys - new_keys):
        counts["缺失"] += 1
        product, question = key.split("||", 1)
        rows.append(["缺失", product, question[:50], "-", ""])
        details.append({"kind": "缺失", "product": product, "question": question})

    # 退化排最前，方便先看要紧的
    order = {"退化": 0, "内容变化": 1, "缺失": 2, "新增": 3, "改善": 4}
    rows.sort(key=lambda r: order.get(r[0], 9))
    details.sort(key=lambda d: order.get(d["kind"], 9))

    summary = {
        "基线": f"{args.base}（{len(base)} 条）",
        "本次": f"{args.new}（{len(new)} 条）",
        "共同题目": len(common),
        "退化(成功→失败)": counts["退化"],
        "改善(失败→成功)": counts["改善"],
        "内容变化": counts["内容变化"],
        "新增": counts["新增"],
        "缺失": counts["缺失"],
        "相似度阈值": args.threshold,
    }

    json_path, md_path, excel_path = write_report(
        new_run_dir(Path(__file__).stem, Path(args.out_dir)),
        "regression",
        title="Yard Agent 回归对比",
        summary=summary,
        headers=["类型", "产品", "问题", "相似度", "本次答案摘要"],
        rows=rows,
        details=details,
        excel_columns=[
            ("类别", "product"),
            ("问题", "question"),
            ("本次答案", "new_answer"),
            ("结果", "kind"),
            ("相似度", "similarity"),
            ("基线答案", "base_answer"),
        ],
    )

    print_summary("回归对比", summary)
    if rows:
        print(f"\n差异明细（前 {min(args.show, len(rows))} 条）：")
        for r in rows[: args.show]:
            print(f"  [{r[0]}] {r[1]} | {r[2]}")
    else:
        print("\n无差异。")
    if excel_path:
        print(f"\nExcel: {excel_path}")
    print(f"报告: {md_path}")
    print(f"明细: {json_path}")
    return 1 if counts["退化"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
