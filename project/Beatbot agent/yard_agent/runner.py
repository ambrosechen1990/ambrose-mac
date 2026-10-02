# -*- coding: utf-8 -*-
"""带重试的提问、用例序列执行。"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from .client import YardAgentClient
from .export import safe_name
from .models import AgentReply
from .style import is_transient_failure, strip_citations


def ask_with_retry(
    client: YardAgentClient,
    question: str,
    *,
    language: str = "中文",
    retries: int = 0,
    retry_delay: float = 3.0,
    on_retry: Optional[Callable[[], None]] = None,
) -> AgentReply:
    """提问；遇到限流/输入框卡死等临时失败时自动恢复并重试。"""
    attempts = max(1, retries + 1)
    reply: AgentReply | None = None

    for attempt in range(1, attempts + 1):
        try:
            reply = client.ask(question, language=language)
        except Exception as exc:
            reply = AgentReply(
                question=question,
                answer=f"[请求失败] {exc}",
                status="失败",
                date=datetime.now().strftime("%Y/%m/%d"),
            )
        if not is_transient_failure(reply):
            break
        if attempt < attempts:
            print(
                f"  !! 暂失败({reply.status})，{retry_delay}s 后重试 "
                f"{attempt}/{attempts - 1}…"
            )
            if on_retry is not None:
                on_retry()
            else:
                try:
                    client.recover_composer()
                except Exception:
                    client.new_chat()
            time.sleep(retry_delay)

    assert reply is not None
    reply.answer = strip_citations(reply.answer)
    if not reply.date:
        reply.date = datetime.now().strftime("%Y/%m/%d")
    return reply


def run_cases(
    client: YardAgentClient,
    cases: Iterable[dict],
    *,
    language: str = "中文",
    retries: int = 0,
    retry_delay: float = 3.0,
    interval: float = 4.0,
    shot_dir: Optional[Path] = None,
    shot_prefix: str = "case",
) -> list[tuple[dict, AgentReply]]:
    """按顺序执行用例。

    用例支持的字段：
      question       必填，要问的内容
      id / product   仅用于命名与报告
      new_chat       True 时提问前先新建对话（多轮场景设为 False 保持上下文）
      language       覆盖默认回答语言
    """
    cases = list(cases)
    results: list[tuple[dict, AgentReply]] = []

    for i, case in enumerate(cases, start=1):
        question = case.get("question", "").strip()
        if not question:
            continue
        if case.get("new_chat", True):
            client.new_chat()
            time.sleep(0.8)

        label = case.get("id") or case.get("product") or f"case{i}"
        print(f"[{i}/{len(cases)}] {label} | {question}")

        reply = ask_with_retry(
            client,
            question,
            language=case.get("language") or language,
            retries=retries,
            retry_delay=retry_delay,
        )
        reply.product = case.get("product", "")

        if shot_dir is not None:
            stamp = datetime.now().strftime("%H%M%S")
            name = f"{shot_prefix}_{safe_name(str(label))}_{i:03d}_{stamp}.png"
            try:
                reply.screenshot = client.screenshot(Path(shot_dir) / name)
            except Exception as exc:
                reply.screenshot = f"(截图失败: {exc})"

        results.append((case, reply))
        print(f"  -> {reply.status} {reply.elapsed_sec}s")

        if interval > 0 and i < len(cases):
            time.sleep(interval)

    return results
