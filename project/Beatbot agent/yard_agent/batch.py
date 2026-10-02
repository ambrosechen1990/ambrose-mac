# -*- coding: utf-8 -*-
"""批量问答主流程。"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .client import YardAgentClient
from .export import classify, export_excel, safe_name
from .models import AgentReply
from .questions import generate_all_questions, question_pool
from .runner import ask_with_retry
from .style import is_transient_failure


def run_batch(
    *,
    products: list[str],
    per_product: int,
    headed: bool,
    timeout: float,
    user_data_dir: str,
    language: str,
    out_dir: Path,
    new_chat_each_product: bool,
    resume: bool,
    resume_from: Path | None = None,
    retries: int = 0,
    retry_delay: float = 3.0,
    interval: float = 4.0,
    new_chat_every: int = 5,
    coverage: str = "split",
    product_index: int | None = None,
    templates_path: Path | None = None,
    library: str = "功能测试库",
    types: list[str] | None = None,
) -> Path:
    out_dir = Path(out_dir)
    shot_dir = out_dir / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = out_dir / "checkpoint.jsonl"
    excel_path = out_dir / "agent_test.xlsx"

    jobs = generate_all_questions(
        products,
        per_product,
        language=language,
        coverage=coverage,
        product_index=product_index,
        templates_path=templates_path,
        library=library,
        types=types,
    )
    done_keys: set[str] = set()
    records: list[AgentReply] = []

    # 续跑时读上一轮运行目录的断点，本轮仍写自己的 checkpoint
    prev = Path(resume_from) if resume_from else checkpoint
    if resume and prev.is_file():
        # 同一题可能有多条记录（失败后重跑），以最后一条为准
        by_key: dict[str, dict] = {}
        with prev.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                by_key[f"{obj.get('product')}||{obj.get('question')}"] = obj

        will_retry = 0
        for key, obj in by_key.items():
            reply = AgentReply(**{k: obj.get(k, "") for k in AgentReply.__dataclass_fields__})
            # 失败的题不算完成，留给本轮重跑
            if is_transient_failure(reply):
                will_retry += 1
                continue
            done_keys.add(key)
            records.append(reply)
        print(f"已从 {prev} 恢复 {len(records)} 条成功记录；{will_retry} 条失败题目将重跑…")
        if prev.resolve() != checkpoint.resolve():
            # 把上一轮的成功记录并进本轮断点，避免再次中断续跑时丢结果
            with checkpoint.open("a", encoding="utf-8") as f:
                for reply in records:
                    f.write(json.dumps(asdict(reply), ensure_ascii=False) + "\n")
    elif resume:
        print("未找到可用断点，按全量执行。")

    pending = [(p, q) for p, q in jobs if f"{p}||{q}" not in done_keys]
    # 去掉产品名后比较，能看出各产品问的是不是同一批题
    distinct = len({q.replace(p, "{p}") for p, q in jobs})
    each = len(jobs) // len(products) if products else 0
    print(
        f"计划: {len(products)} 产品 × {each} 题 = {len(jobs)}；"
        f"待跑 {len(pending)}；输出目录 {out_dir}"
    )
    pool_size = len(question_pool(language, path=templates_path, library=library, types=types))
    if coverage == "full":
        print(f"覆盖方式: full — 每个产品都问同一批 {each} 道题，可横向对比各产品表现")
    else:
        print(f"覆盖方式: split — 各产品取题库的不同片段，合计 {distinct} 条不同问题")
        if len(jobs) > pool_size and products:
            print(
                f"提示: 题库共 {pool_size} 条模板，要出 {len(jobs)} 题，"
                f"有 {len(jobs) - pool_size} 题会与别的产品重复；"
                f"每产品 ≤ {pool_size // len(products)} 题可完全不重复"
            )
    print(
        f"稳定性: 失败重试={retries}，题间隔={interval}s，"
        f"每 {new_chat_every} 题新建对话"
    )
    # 按实测每题约 30s 回答估算，让人一眼知道这轮要跑多久
    eta_min = len(pending) * (30 + max(interval, 0)) / 60
    eta = f"{eta_min / 60:.1f} 小时" if eta_min >= 60 else f"{eta_min:.0f} 分钟"
    print(f"预计耗时约 {eta}（中途 Ctrl-C 可停，下次加 --resume 续跑）")

    with YardAgentClient(
        headed=headed,
        timeout_sec=timeout,
        user_data_dir=user_data_dir,
    ) as client:
        current_product = None
        questions_in_chat = 0
        for i, (product, question) in enumerate(pending, start=1):
            need_new = False
            if new_chat_each_product and product != current_product:
                need_new = True
                current_product = product
                questions_in_chat = 0
                print(f"\n==== 产品: {product} ====")
            elif new_chat_every > 0 and questions_in_chat >= new_chat_every:
                need_new = True
                questions_in_chat = 0
                print(f"  (已满 {new_chat_every} 题，新建对话)")

            if need_new:
                client.new_chat()
                time.sleep(0.8)

            print(f"[{i}/{len(pending)}] {product} | {question}")

            def _on_retry() -> None:
                nonlocal questions_in_chat
                try:
                    client.recover_composer()
                except Exception:
                    client.new_chat()
                questions_in_chat = 0

            reply = ask_with_retry(
                client,
                question,
                language=language,
                retries=retries,
                retry_delay=retry_delay,
                on_retry=_on_retry,
            )
            reply.product = product

            stamp = datetime.now().strftime("%H%M%S")
            shot_name = f"{safe_name(product)}_{len(records)+1:04d}_{stamp}.png"
            try:
                reply.screenshot = client.screenshot(shot_dir / shot_name)
            except Exception as exc:
                reply.screenshot = f"(截图失败: {exc})"

            records.append(reply)
            questions_in_chat += 1
            with checkpoint.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(reply), ensure_ascii=False) + "\n")

            result, _ = classify(reply)
            print(
                f"  -> {result} {reply.elapsed_sec}s | "
                f"截图: {Path(reply.screenshot).name}"
            )

            if interval > 0 and i < len(pending):
                time.sleep(interval)

    tally = Counter(classify(r)[0] for r in records)
    print(
        f"\n结果: 已完成 {tally['已完成']} / 风险 {tally['风险']} / 失败 {tally['失败']}"
        f"（共 {len(records)} 题）"
    )
    print("  风险 = Agent 回了但答不上来（资料不足类）；失败 = 没取到回复")

    path = export_excel(records, excel_path)
    print(f"测试完成，Excel: {path}")
    print(f"断点文件: {checkpoint}")
    return path
