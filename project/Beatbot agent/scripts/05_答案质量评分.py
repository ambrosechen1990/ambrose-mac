#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""答案质量评分：拿标准答案集跑一遍，自动判分。

目的：把「人工翻 Excel」变成「只看未通过的几条」。

标准答案集: config/qa_baseline.json，每条支持字段：
  question         必填
  expect_keywords  必须全部出现
  any_keywords     至少命中一个
  forbid_keywords  不得出现
  expect_refusal   期望明确拒答

用法:
  python3 scripts/05_答案质量评分.py
  python3 scripts/05_答案质量评分.py --baseline config/qa_baseline.json --repeat 1
  python3 scripts/05_答案质量评分.py --only sora10-depth,sora10-dimensions
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
    BROWSER_PROFILE,
    OUTPUT_DIR,
    STANDARD_COLUMNS,
    new_run_dir,
    YardAgentClient,
    judge,
    print_summary,
    run_cases,
    write_report,
)
from yard_agent.paths import CONFIG_DIR  # noqa: E402

DEFAULT_BASELINE = CONFIG_DIR / "qa_baseline.json"


def load_baseline(path: Path, only: str) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"找不到标准答案集: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit(f"{path} 须为非空 JSON 数组")
    cases = [c for c in data if str(c.get("question", "")).strip()]
    if only.strip():
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        cases = [c for c in cases if str(c.get("id", "")) in wanted]
        if not cases:
            raise SystemExit(f"--only 未匹配到用例: {sorted(wanted)}")
    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Yard Agent 答案质量评分")
    p.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="标准答案集 JSON")
    p.add_argument("--only", default="", help="只跑指定用例 id，逗号分隔")
    p.add_argument("--repeat", type=int, default=1, help="每题重复次数，>1 可顺带看一致性")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--user-data-dir", default=str(BROWSER_PROFILE))
    p.add_argument("--language", default="中文")
    p.add_argument("--out-dir", default=str(OUTPUT_DIR), help="运行目录的父目录")
    p.add_argument("--interval", type=float, default=4.0)
    p.add_argument("--retries", type=int, default=0, help="失败重试次数，默认 0")
    args = p.parse_args(argv)

    base_cases = load_baseline(Path(args.baseline), args.only)
    repeat = max(1, args.repeat)

    cases: list[dict] = []
    for case in base_cases:
        for r in range(1, repeat + 1):
            c = dict(case)
            c["run_index"] = r
            c["id"] = f"{case.get('id', 'case')}#{r}" if repeat > 1 else case.get("id", "case")
            cases.append(c)

    out_dir = new_run_dir(Path(__file__).stem, Path(args.out_dir))
    print(f"标准答案集: {args.baseline}；用例 {len(base_cases)} × 重复 {repeat} = {len(cases)}")

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
            shot_prefix="quality",
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
            expect_refusal=bool(case.get("expect_refusal")),
        )
        passed += 1 if ok else 0
        rows.append(
            [
                case.get("id", ""),
                case.get("product", ""),
                "通过" if ok else "未通过",
                reason,
                reply.answer[:80],
            ]
        )
        details.append(
            {
                "id": case.get("id", ""),
                "kind": case.get("product", ""),
                "product": case.get("product", ""),
                "question": case.get("question", ""),
                "passed": ok,
                "result": "通过" if ok else "未通过",
                "reason": reason,
                "status": reply.status,
                "elapsed_sec": reply.elapsed_sec,
                "answer": reply.answer,
                "screenshot": reply.screenshot,
                "note": case.get("note", ""),
            }
        )

    total = len(results)
    rate = f"{passed}/{total}" + (f" ({passed / total:.0%})" if total else "")
    summary = {"用例数": total, "通过": passed, "未通过": total - passed, "通过率": rate}

    json_path, md_path, excel_path = write_report(
        out_dir,
        "quality",
        title="Yard Agent 答案质量评分",
        summary=summary,
        headers=["用例", "产品", "结果", "原因", "答案摘要"],
        rows=rows,
        details=details,
        excel_columns=STANDARD_COLUMNS,
    )

    print_summary("质量评分", summary)
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
