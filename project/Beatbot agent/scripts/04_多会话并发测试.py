#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多会话并发压测。

目的：多个独立浏览器配置并行提问，验证限流、输入框卡死、会话互相干扰。

用法:
  python3 scripts/04_多会话并发测试.py --sessions 3 --per-session 5
  python3 scripts/04_多会话并发测试.py --sessions 2 --products "Sora 10" --per-session 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _worker(payload: dict) -> dict:
    """子进程入口：独立 profile，跑一小批题。"""
    # 子进程内重新 import，避免 pickle 客户端
    sys.path.insert(0, payload["root"])
    from yard_agent.batch import run_batch
    from yard_agent.questions import parse_products

    session_id = payload["session_id"]
    out_dir = Path(payload["out_dir"]) / f"session_{session_id:02d}"
    profile = Path(payload["profile_root"]) / f"session_{session_id:02d}"
    products = parse_products(payload["products"])
    # 并发时每会话只跑指定产品切片，避免全部产品爆炸
    if payload.get("product_slice") is not None:
        products = [products[payload["product_slice"] % len(products)]]

    t0 = time.time()
    try:
        excel = run_batch(
            products=products,
            per_product=payload["per_session"],
            headed=payload["headed"],
            timeout=payload["timeout"],
            user_data_dir=str(profile),
            language=payload["language"],
            out_dir=out_dir,
            new_chat_each_product=True,
            resume=False,
            retries=payload["retries"],
            retry_delay=payload["retry_delay"],
            interval=payload["interval"],
            new_chat_every=payload["new_chat_every"],
            templates_path=Path(payload["templates_path"]) if payload.get("templates_path") else None,
            library=payload.get("library") or "功能测试库",
        )
        return {
            "session_id": session_id,
            "ok": True,
            "excel": str(excel),
            "elapsed_sec": round(time.time() - t0, 2),
            "error": "",
        }
    except Exception as exc:
        return {
            "session_id": session_id,
            "ok": False,
            "excel": "",
            "elapsed_sec": round(time.time() - t0, 2),
            "error": str(exc),
        }


def main(argv: list[str] | None = None) -> int:
    from yard_agent.paths import BROWSER_PROFILE, OUTPUT_DIR, QUESTION_TEMPLATES_XLSX, ROOT as YA_ROOT

    p = argparse.ArgumentParser(description="Yard Agent 多会话并发压测")
    p.add_argument("--sessions", type=int, default=3, help="并发会话数，默认 3")
    p.add_argument("--per-session", type=int, default=5, help="每会话题数，默认 5")
    p.add_argument("--products", default="", help="产品过滤，逗号分隔；默认用配置列表轮询")
    p.add_argument("--headless", action="store_true", help="无头（并发建议开，省资源）")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--language", default="中文")
    p.add_argument("--out-dir", default=str(OUTPUT_DIR), help="运行目录的父目录")
    p.add_argument("--profile-root", default=str(BROWSER_PROFILE.parent / ".browser_profiles_concurrent"))
    p.add_argument("--retries", type=int, default=0, help="失败重试次数，默认 0")
    p.add_argument("--retry-delay", type=float, default=3.0)
    p.add_argument("--interval", type=float, default=4.0)
    p.add_argument("--new-chat-every", type=int, default=5)
    args = p.parse_args(argv)

    if args.sessions < 1:
        print("sessions 须 >= 1", file=sys.stderr)
        return 2

    from yard_agent.paths import new_run_dir

    out_dir = new_run_dir(Path(__file__).stem, Path(args.out_dir))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = out_dir / "concurrent_summary.json"

    # 首会话建议 headed 方便登录复制；其余 headless
    # 为简单起见：全部跟随 --headless；用户可先冒烟登录各 profile
    payloads = []
    for i in range(args.sessions):
        payloads.append(
            {
                "root": str(YA_ROOT),
                "session_id": i + 1,
                "out_dir": str(out_dir),
                "profile_root": args.profile_root,
                "products": args.products,
                "product_slice": i,
                "per_session": args.per_session,
                "headed": not args.headless,
                "timeout": args.timeout,
                "language": args.language,
                "retries": args.retries,
                "retry_delay": args.retry_delay,
                "interval": args.interval,
                "new_chat_every": args.new_chat_every,
                "templates_path": str(QUESTION_TEMPLATES_XLSX),
                "library": "功能测试库",
            }
        )

    print(
        f"并发 {args.sessions} 会话 × 每会话 {args.per_session} 题；"
        f"输出 {out_dir}；profile {args.profile_root}"
    )
    print("提示: 各会话使用独立浏览器配置目录；首次请在窗口中登录。")

    results = []
    with ProcessPoolExecutor(max_workers=args.sessions) as ex:
        futs = {ex.submit(_worker, pl): pl["session_id"] for pl in payloads}
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                r = fut.result()
            except Exception as exc:
                r = {
                    "session_id": sid,
                    "ok": False,
                    "excel": "",
                    "elapsed_sec": 0,
                    "error": str(exc),
                }
            results.append(r)
            status = "OK" if r["ok"] else "FAIL"
            print(f"  session {r['session_id']}: {status} {r['elapsed_sec']}s {r.get('error','')[:80]}")

    results.sort(key=lambda x: x["session_id"])
    summary = {
        "stamp": stamp,
        "sessions": args.sessions,
        "per_session": args.per_session,
        "ok_count": sum(1 for r in results if r["ok"]),
        "results": results,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n汇总: {summary['ok_count']}/{args.sessions} 成功")
    print(f"写入: {summary_path}")
    return 0 if summary["ok_count"] == args.sessions else 1


if __name__ == "__main__":
    raise SystemExit(main())
