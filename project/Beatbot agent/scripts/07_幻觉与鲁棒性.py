#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""幻觉与鲁棒性巡检：假型号、超纲问题、提示注入、越权、诱导编造。

目的：确认 Agent 在「答不上来」时会老实说，而不是编一个像样的答案。

探针集: config/robustness_probes.json

用法:
  python3 scripts/07_幻觉与鲁棒性.py
  python3 scripts/07_幻觉与鲁棒性.py --kind 幻觉,提示注入
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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

DEFAULT_PROBES = CONFIG_DIR / "robustness_probes.json"


def load_probes(path: Path, kinds: str) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"找不到探针集: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit(f"{path} 须为非空 JSON 数组")
    cases = [c for c in data if str(c.get("question", "")).strip()]
    if kinds.strip():
        wanted = {s.strip() for s in kinds.split(",") if s.strip()}
        cases = [c for c in cases if str(c.get("kind", "")) in wanted]
        if not cases:
            raise SystemExit(f"--kind 未匹配到探针: {sorted(wanted)}")
    # 每条探针独立开一段对话，避免上文影响判断
    for c in cases:
        c.setdefault("new_chat", True)
    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Yard Agent 幻觉与鲁棒性巡检")
    p.add_argument("--probes", default=str(DEFAULT_PROBES), help="探针集 JSON")
    p.add_argument("--kind", default="", help="只跑指定类别，逗号分隔（幻觉/超纲/提示注入/越权/安全）")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--user-data-dir", default=str(BROWSER_PROFILE))
    p.add_argument("--language", default="中文")
    p.add_argument("--out-dir", default=str(OUTPUT_DIR), help="运行目录的父目录")
    p.add_argument("--interval", type=float, default=4.0)
    p.add_argument("--retries", type=int, default=0, help="失败重试次数，默认 0")
    args = p.parse_args(argv)

    cases = load_probes(Path(args.probes), args.kind)
    out_dir = new_run_dir(Path(__file__).stem, Path(args.out_dir))
    print(f"探针集: {args.probes}；共 {len(cases)} 条")

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
            shot_prefix="robust",
        )

    rows = []
    details = []
    passed = 0
    by_kind: Counter[str] = Counter()
    fail_by_kind: Counter[str] = Counter()

    for case, reply in results:
        kind = case.get("kind", "未分类")
        ok, reason = judge(
            reply.answer,
            expect_keywords=case.get("expect_keywords"),
            any_keywords=case.get("any_keywords"),
            forbid_keywords=case.get("forbid_keywords"),
            expect_refusal=bool(case.get("expect_refusal")),
        )
        by_kind[kind] += 1
        if ok:
            passed += 1
        else:
            fail_by_kind[kind] += 1

        rows.append(
            [
                case.get("id", ""),
                kind,
                "通过" if ok else "风险",
                reason,
                reply.answer[:80],
            ]
        )
        details.append(
            {
                "id": case.get("id", ""),
                "kind": kind,
                "question": case.get("question", ""),
                "passed": ok,
                "result": "通过" if ok else "风险",
                "reason": reason,
                "answer": reply.answer,
                "status": reply.status,
                "screenshot": reply.screenshot,
                "note": case.get("note", ""),
            }
        )

    total = len(results)
    summary = {
        "探针数": total,
        "通过": passed,
        "风险": total - passed,
        "通过率": f"{passed}/{total}" + (f" ({passed / total:.0%})" if total else ""),
    }
    for kind, n in by_kind.items():
        summary[f"{kind}(风险/总)"] = f"{fail_by_kind.get(kind, 0)}/{n}"

    json_path, md_path, excel_path = write_report(
        out_dir,
        "robustness",
        title="Yard Agent 幻觉与鲁棒性巡检",
        summary=summary,
        headers=["探针", "类别", "结果", "原因", "答案摘要"],
        rows=rows,
        details=details,
        excel_columns=STANDARD_COLUMNS,
    )

    print_summary("鲁棒性巡检", summary)
    risky = [d for d in details if not d["passed"]]
    if risky:
        print("\n存在风险：")
        for d in risky:
            print(f"  - [{d['kind']}] {d['id']}: {d['reason']}")
    print(f"\nExcel: {excel_path}")
    print(f"报告: {md_path}")
    print(f"明细: {json_path}")
    return 0 if not risky else 1


if __name__ == "__main__":
    raise SystemExit(main())
