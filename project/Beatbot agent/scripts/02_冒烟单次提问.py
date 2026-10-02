#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟：单次向 Yard Agent 提问并打印答案。

目的：验证登录态、页面可问、答案抓取是否正常（不做批量）。

用法:
  python3 scripts/02_冒烟单次提问.py "Sora 10 的工作水深是多少？"
  python3 scripts/02_冒烟单次提问.py --interactive
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yard_agent import BROWSER_PROFILE, YardAgentClient  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Yard Agent 冒烟单次提问")
    p.add_argument("question", nargs="?", help="要问的问题")
    p.add_argument("-q", "--question-flag", dest="question_flag")
    p.add_argument("--interactive", action="store_true", help="交互多轮提问")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--user-data-dir", default=str(BROWSER_PROFILE))
    p.add_argument("--language", default="中文")
    p.add_argument("--save-json", default="")
    args = p.parse_args(argv)

    headed = not args.headless
    q = args.question_flag or args.question

    if not args.interactive and not q:
        p.print_help()
        print('\n示例:\n  python3 scripts/02_冒烟单次提问.py "Sora 10 的工作水深是多少？"')
        return 2

    with YardAgentClient(
        headed=headed,
        timeout_sec=args.timeout,
        user_data_dir=args.user_data_dir,
    ) as client:
        if args.interactive:
            print("交互模式：输入问题回车；空行/quit 退出")
            while True:
                try:
                    text = input("你: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not text or text.lower() in {"q", "quit", "exit"}:
                    break
                r = client.ask(text, language=args.language)
                print(f"\nYard Agent ({r.status}):\n{r.answer}\n")
            return 0

        r = client.ask(q, language=args.language)
        print(f"状态: {r.status} ({r.elapsed_sec}s)")
        print(r.answer)
        if args.save_json:
            Path(args.save_json).write_text(
                json.dumps(asdict(r), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
