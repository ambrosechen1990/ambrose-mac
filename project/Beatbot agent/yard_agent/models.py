# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentReply:
    question: str
    answer: str
    status: str = ""
    elapsed_sec: float = 0.0
    raw_blocks: list[str] = field(default_factory=list)
    screenshot: str = ""
    product: str = ""
    date: str = ""
