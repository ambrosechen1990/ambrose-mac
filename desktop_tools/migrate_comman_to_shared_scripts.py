#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移：APP外壳 下脚本从 comman 改为 1共用脚本（common_utils / common_utils_android）。"""
from __future__ import annotations

import sys
from pathlib import Path

# 仅迁移「3功能」下用例，避免误改 1共用脚本 等仅含 comman 字样的说明文本
ROOT = Path(__file__).resolve().parents[1] / "project" / "APP外壳" / "3功能"

SHARED_BLOCK = """
# APP外壳 已取消 comman：共用逻辑在「1共用脚本」
_cur = Path(__file__).resolve().parent
_shared = None
for _ in range(24):
    _cand = _cur / "1共用脚本"
    if _cand.is_dir() and (_cand / "common_utils.py").is_file():
        _shared = _cand
        _p = str(_shared.resolve())
        if _p not in sys.path:
            sys.path.insert(0, _p)
        break
    if _cur.parent == _cur:
        break
    _cur = _cur.parent
if not _shared:
    raise ImportError("未找到 APP外壳/1共用脚本（需包含 common_utils.py）")
""".strip(
    "\n"
)


def pick_module(path: Path) -> str:
    lower = [p.lower() for p in path.parts]
    return "common_utils_android" if "android" in lower else "common_utils"


def strip_comman_path_blocks(lines: list[str]) -> list[str]:
    """删除「# 动态查找并加入 comman」整段直到 ImportError 行之后。"""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("# 动态查找并加入 comman"):
            j = i + 1
            while j < len(lines):
                if lines[j].strip().startswith("raise ImportError"):
                    j += 1
                    # 跳过后续空行
                    while j < len(lines) and lines[j].strip() == "":
                        j += 1
                    break
                j += 1
            i = j
            continue
        out.append(line)
        i += 1
    return out


def migrate_text(path: Path, text: str) -> str:
    lines = text.splitlines(keepends=True)
    lines = strip_comman_path_blocks(lines)
    s = "".join(lines)

    s = s.replace("from comman.username_utils import", "from username_utils import")

    marker = "from comman import ("
    if marker in s:
        start = s.index(marker)
        depth = 0
        j = start + len(marker) - 1  # position of '('
        for k in range(j, len(s)):
            if s[k] == "(":
                depth += 1
            elif s[k] == ")":
                depth -= 1
                if depth == 0:
                    end = k + 1
                    inner = s[start + len("from comman import (") : k].strip()
                    mod = pick_module(path)
                    repl = f"from {mod} import (\n{inner}\n)"
                    s = s[:start] + repl + s[end:]
                    break

    if "_shared = None" not in s and "1共用脚本" not in s:
        needle = "from pathlib import Path"
        if needle in s:
            pos = s.index(needle) + len(needle)
            line_end = s.find("\n", pos)
            if line_end != -1:
                insert_at = line_end + 1
                prefix = s[:insert_at]
                if "import sys" not in prefix.split("from pathlib", 1)[0]:
                    prefix = prefix.replace("from pathlib import Path", "import sys\nfrom pathlib import Path", 1)
                    insert_at = len(prefix)
                s = prefix + "\n" + SHARED_BLOCK + "\n" + s[insert_at:]
        else:
            print(f"[WARN] 无 pathlib.Path，请手工处理: {path}", file=sys.stderr)

    elif "import sys" not in s[:800]:
        s = s.replace("from pathlib import Path", "import sys\nfrom pathlib import Path", 1)

    return s


def migrate_file(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if "comman" not in raw:
        return False
    new = migrate_text(path, raw)
    if new != raw:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> int:
    if not ROOT.is_dir():
        print(f"ROOT not found: {ROOT}", file=sys.stderr)
        return 1
    n = 0
    for p in ROOT.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            if migrate_file(p):
                n += 1
                print(p.relative_to(ROOT))
        except Exception as e:
            print(f"[ERR] {p}: {e}", file=sys.stderr)
    print(f"done, changed {n} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
