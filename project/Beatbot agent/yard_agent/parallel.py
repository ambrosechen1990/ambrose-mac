# -*- coding: utf-8 -*-
"""按产品开窗口并行跑批量问答。"""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from .export import classify, export_excel, safe_name
from .models import AgentReply
from .paths import BROWSER_PROFILE, ROOT


PRODUCT_PROFILE_ROOT = BROWSER_PROFILE.parent / ".browser_profiles_products"

# Chrome 运行时文件，主配置正在被占用时随时会消失，不能跟着复制
_PROFILE_SKIP = (
    "SingletonLock",
    "SingletonSocket",
    "SingletonCookie",
    "RunningChromeVersion",
    "DevToolsActivePort",
    "lockfile",
)


class _PrefixedStream:
    """给子进程日志加上 [产品名] 前缀，多窗口交叉输出时能分清。"""

    def __init__(self, dest, prefix: str):
        self.dest = dest
        self.prefix = prefix
        self._buf = ""

    def write(self, data):
        if not isinstance(data, str):
            data = data.decode("utf-8", errors="replace")
        if not data:
            return 0
        self._buf += data
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.dest.write(f"[{self.prefix}] {line}\n" if line else "\n")
        return len(data)

    def flush(self):
        if self._buf:
            self.dest.write(f"[{self.prefix}] {self._buf}")
            self._buf = ""
        self.dest.flush()

    def isatty(self):
        return False


def _skip_profile_file(name: str) -> bool:
    if name in _PROFILE_SKIP:
        return True
    return name.startswith("Singleton") or name.startswith(".com.google.Chrome")


def ensure_product_profile(dest: Path, source: Path | None = None) -> Path:
    """每个产品一个独立浏览器配置；没有的话从主登录态复制，省得每个窗口重新登录。

    主配置若正被 Chrome 占用，部分运行时文件会边列边消失，
    所以逐个复制、跳过失败项，不能用 copytree 一把梭。
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    src = Path(source or BROWSER_PROFILE)
    if not src.is_dir():
        return dest

    copied = 0
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(_skip_profile_file(part) for part in rel.parts):
            continue
        target = dest / rel
        if target.exists():
            continue
        try:
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target, follow_symlinks=False)
                copied += 1
        except OSError:
            continue
    if copied:
        print(f"  已从主登录态复制配置到 {dest.name}（{copied} 个文件）")
    return dest


def load_checkpoint_records(path: Path) -> list[AgentReply]:
    if not path.is_file():
        return []
    records: list[AgentReply] = []
    by_key: dict[str, AgentReply] = {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            reply = AgentReply(**{k: obj.get(k, "") for k in AgentReply.__dataclass_fields__})
            by_key[f"{reply.product}||{reply.question}"] = reply
    records.extend(by_key.values())
    return records


def merge_product_runs(out_dir: Path, products: list[str]) -> Path:
    """把各产品目录的结果合成一份总表和总断点。"""
    records: list[AgentReply] = []
    for product in products:
        cp = out_dir / safe_name(product) / "checkpoint.jsonl"
        records.extend(load_checkpoint_records(cp))

    merged_cp = out_dir / "checkpoint.jsonl"
    with merged_cp.open("w", encoding="utf-8") as f:
        for reply in records:
            f.write(json.dumps(asdict(reply), ensure_ascii=False) + "\n")

    excel = export_excel(records, out_dir / "agent_test.xlsx")
    tally = Counter(classify(r)[0] for r in records)
    print(
        f"\n汇总: 已完成 {tally['已完成']} / 风险 {tally['风险']} / 失败 {tally['失败']}"
        f"（共 {len(records)} 题）"
    )
    print(f"总表: {excel}")
    print(f"总断点: {merged_cp}")
    return excel


def product_worker(payload: dict) -> dict:
    """子进程：一个窗口测一个产品。"""
    sys.path.insert(0, payload["root"])
    from yard_agent.batch import run_batch

    product = payload["product"]
    sys.stdout = _PrefixedStream(sys.__stdout__, product)
    sys.stderr = _PrefixedStream(sys.__stderr__, product)

    t0 = __import__("time").time()
    try:
        excel = run_batch(
            products=[product],
            per_product=payload["per_product"],
            headed=payload["headed"],
            timeout=payload["timeout"],
            user_data_dir=payload["user_data_dir"],
            language=payload["language"],
            out_dir=Path(payload["out_dir"]),
            new_chat_each_product=payload["new_chat_each_product"],
            resume=payload["resume"],
            resume_from=Path(payload["resume_from"]) if payload.get("resume_from") else None,
            retries=payload["retries"],
            retry_delay=payload["retry_delay"],
            interval=payload["interval"],
            new_chat_every=payload["new_chat_every"],
            coverage=payload["coverage"],
            product_index=payload.get("product_index"),
            templates_path=Path(payload["templates_path"]) if payload.get("templates_path") else None,
            library=payload.get("library") or "功能测试库",
            types=payload.get("types") or None,
        )
        return {
            "product": product,
            "ok": True,
            "excel": str(excel),
            "elapsed_sec": round(__import__("time").time() - t0, 2),
            "error": "",
        }
    except Exception as exc:
        return {
            "product": product,
            "ok": False,
            "excel": "",
            "elapsed_sec": round(__import__("time").time() - t0, 2),
            "error": str(exc),
        }


def _resume_path_for(product: str, prev: Path | None) -> str:
    if prev is None:
        return ""
    named = prev / safe_name(product) / "checkpoint.jsonl"
    if named.is_file():
        return str(named)
    combined = prev / "checkpoint.jsonl"
    return str(combined) if combined.is_file() else ""


def run_parallel_products(
    *,
    products: list[str],
    per_product: int,
    coverage: str,
    headed: bool,
    timeout: float,
    language: str,
    out_dir: Path,
    new_chat_each_product: bool,
    resume: bool,
    prev_run: Path | None,
    retries: int,
    retry_delay: float,
    interval: float,
    new_chat_every: int,
    windows: int,
    profile_source: str,
    templates_path: Path | None = None,
    library: str = "功能测试库",
    types: list[str] | None = None,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(windows, len(products)))

    payloads = []
    for i, product in enumerate(products):
        dest = out_dir / safe_name(product)
        dest.mkdir(parents=True, exist_ok=True)
        profile = ensure_product_profile(
            PRODUCT_PROFILE_ROOT / safe_name(product),
            source=Path(profile_source),
        )
        payloads.append(
            {
                "root": str(ROOT),
                "product": product,
                "product_index": i,
                "per_product": per_product,
                "coverage": coverage,
                "headed": headed,
                "timeout": timeout,
                "user_data_dir": str(profile),
                "language": language,
                "out_dir": str(dest),
                "new_chat_each_product": new_chat_each_product,
                "resume": resume,
                "resume_from": _resume_path_for(product, prev_run) if resume else "",
                "retries": retries,
                "retry_delay": retry_delay,
                "interval": interval,
                "new_chat_every": new_chat_every,
                "templates_path": str(templates_path) if templates_path else "",
                "library": library,
                "types": types or [],
            }
        )

    print(
        f"并行 {len(products)} 个产品 × {workers} 个窗口"
        + (f"（同时最多 {workers} 个）" if workers < len(products) else "")
    )
    print("每个窗口测 1 个产品，独立提问，互不等对方答完。")
    print("全部窗口结束后，再把各产品报告汇总到同一个文件夹。")
    print("首次若未登录，请在对应窗口登录。")
    print(f"输出目录 {out_dir}")

    results = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(product_worker, pl): pl["product"] for pl in payloads}
        for fut in as_completed(futs):
            product = futs[fut]
            try:
                r = fut.result()
            except Exception as exc:
                r = {
                    "product": product,
                    "ok": False,
                    "excel": "",
                    "elapsed_sec": 0,
                    "error": str(exc),
                }
            results.append(r)
            status = "OK" if r["ok"] else "FAIL"
            print(
                f"  窗口 {r['product']}: {status} {r['elapsed_sec']}s "
                f"{(r.get('error') or '')[:80]}"
            )

    results.sort(key=lambda x: products.index(x["product"]) if x["product"] in products else 0)
    (out_dir / "parallel_summary.json").write_text(
        json.dumps(
            {
                "products": products,
                "windows": workers,
                "ok_count": sum(1 for r in results if r["ok"]),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return merge_product_runs(out_dir, products)
