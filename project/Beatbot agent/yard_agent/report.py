# -*- coding: utf-8 -*-
"""测试结果落盘：JSON 明细 + Markdown 摘要。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .export import export_detail_excel


def _cell(value) -> str:
    s = str(value if value is not None else "")
    s = s.replace("|", "\\|").replace("\n", " ")
    return s


def write_report(
    out_dir: Path,
    stem: str,
    *,
    title: str,
    summary: dict,
    headers: list[str],
    rows: list[list],
    details: list[dict] | None = None,
    excel_columns: list[tuple[str, str]] | None = None,
) -> tuple[Path, Path, Path | None]:
    """在 out_dir（一次运行一个目录）里写 <stem>.json / .md，给了 excel_columns 时再写 .xlsx。

    返回 (json 路径, md 路径, excel 路径或 None)。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"

    json_path.write_text(
        json.dumps(
            {"title": title, "stamp": stamp, "summary": summary, "details": details or []},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    lines = [f"# {title}", "", f"生成时间: {stamp}", ""]
    for k, v in summary.items():
        lines.append(f"- {k}: {v}")
    lines.extend(["", "| " + " | ".join(headers) + " |"])
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    excel_path: Path | None = None
    if excel_columns and details:
        excel_path = export_detail_excel(
            details,
            out_dir / f"{stem}.xlsx",
            excel_columns,
            sheet_title=title[:28] or "测试记录",
        )

    return json_path, md_path, excel_path


def print_summary(title: str, summary: dict) -> None:
    print(f"\n==== {title} ====")
    for k, v in summary.items():
        print(f"{k}: {v}")
