# -*- coding: utf-8 -*-
"""自主作答引导与脚注清理。"""

from __future__ import annotations

import re


def strip_citations(text: str) -> str:
    """去掉 Yard Agent 文末/文中的 FAQ 脚注引用。"""
    if not text:
        return text
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        s = line.strip()
        if re.match(r"^\[\d+\]\s*.+", s):
            continue
        if re.match(r"^(参考|来源|引用|References?|Sources?)\s*[:：]?\s*$", s, flags=re.I):
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\s*\[\d+\]", "", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


TRANSIENT_FAIL_MARKERS = (
    "本次查询暂时未能完成",
    "本次请求未完成",
    "请稍后再试",
    "暂时无法完成",
    "服务繁忙",
    "NETWORK_ERROR",
    "无法连接 Agent API",
    "同源代理",
    "[请求失败]",
    "disabled",
    "输入框仍为 disabled",
    "Timeout",
)


def is_transient_failure(reply) -> bool:
    """判断是否为可重试的失败（限流/超时/未完成等）。"""
    if reply.status in {"失败", "超时截取"}:
        return True
    answer = (reply.answer or "").strip()
    if answer.startswith("失败") or answer.startswith("[请求失败]"):
        return True
    return any(m in answer for m in TRANSIENT_FAIL_MARKERS)
