"""
跨平台同步用例“文件名”（iOS <-> Android）——名称复制工具（中文文件名）。

你们当前约定的用例文件名形态是：
  6位编号 + 中文描述 + .py
例如：
  102667验证正确账号+密码.py

本脚本用于：
- 从 source 平台的某个模块目录中读取所有符合编号规则的用例脚本文件名
- 在 target 平台对应模块目录下创建同样“中文描述”的占位脚本
- 同时把前缀 6 位编号按 target 侧“自动续号”或“指定起始编号”重新生成

注意：
- 这里做的是“复制名称 + 生成占位脚本”，不会复制原脚本内容
- 默认不会覆盖已存在文件，除非传 --overwrite

编号规则（默认）：
- iOS：以 10xxxx 开头（即 100000-109999 段），目标模块内按同前缀最大编号续号
- Android：以 20xxxx 开头（即 200000-209999 段），目标模块内按同前缀最大编号续号

用法示例：
  python sync_platform_case_names名称复制.py --from ios --to android --module 1登录
  python sync_platform_case_names名称复制.py --from ios --to android --module 2注册 --start-id 200001
  python sync_platform_case_names名称复制.py --from android --to ios --module 1登录 --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
import threading
import contextlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import tkinter as tk
from tkinter import messagebox, ttk


CASE_STEM_RE = re.compile(r"^(?P<case_id>\d{6})(?P<desc>.*)$")


@dataclass(frozen=True)
class CaseName:
    src_path: Path
    src_case_id: str
    desc: str  # includes leading separators/spaces if any; we preserve as-is


def _app_shell_root() -> Path:
    # .../APP外壳/1共用脚本/sync_platform_case_names名称复制.py -> .../APP外壳
    return Path(__file__).resolve().parent.parent


def _platform_root() -> Path:
    return _app_shell_root() / "3功能" / "1平台"


def _platform_dir_name(platform: str) -> str:
    p = platform.strip().lower()
    if p in {"ios", "i"}:
        return "IOS"
    if p in {"android", "a"}:
        return "Android"
    raise ValueError(f"不支持的平台: {platform}（仅支持 ios/android）")


def _discover_case_names(module_dir: Path) -> List[CaseName]:
    items: List[CaseName] = []
    for f in sorted(module_dir.rglob("*.py")):
        if f.name in {"run_cases.py", "cases.py", "conftest.py", "__init__.py"}:
            continue
        m = CASE_STEM_RE.match(f.stem)
        if not m:
            continue
        items.append(CaseName(src_path=f, src_case_id=m.group("case_id"), desc=m.group("desc")))
    items.sort(key=lambda x: (x.src_case_id, x.src_path.name))
    return items


def _existing_case_ids(module_dir: Path) -> List[int]:
    ids: List[int] = []
    if not module_dir.exists():
        return ids
    for f in module_dir.rglob("*.py"):
        m = CASE_STEM_RE.match(f.stem)
        if m:
            try:
                ids.append(int(m.group("case_id")))
            except Exception:
                pass
    return sorted(set(ids))


def _target_prefix(platform: str) -> str:
    """
    目标平台用例编号前缀（2 位）：
    - iOS: 10xxxx
    - Android: 20xxxx
    """
    p = platform.strip().lower()
    if p in {"ios", "i"}:
        return "10"
    if p in {"android", "a"}:
        return "20"
    raise ValueError(f"不支持的平台: {platform}（仅支持 ios/android）")


def _next_start_id(module_dir: Path, target_platform: str) -> int:
    """
    取目标平台在该模块下的“下一个起始编号”。
    规则：优先在目标模块里找同前缀(10/20)的最大编号续号；若不存在则从前缀段的 00001 开始。
    例如：
    - iOS: 100001 起
    - Android: 200001 起
    """
    prefix = _target_prefix(target_platform)
    ids = _existing_case_ids(module_dir)
    prefixed = [i for i in ids if str(i).zfill(6).startswith(prefix)]
    if prefixed:
        return max(prefixed) + 1
    return int(prefix + "0001")


def _format_case_id(n: int) -> str:
    return f"{n:06d}"


def _render_placeholder_test(case_id: str, src_case_id: str, desc: str, source_platform: str) -> str:
    safe_desc = desc.strip() or "(无描述)"
    return (
        f'"""{case_id}{desc}.py\n\n'
        "占位脚本：由 sync_platform_case_names名称复制.py 自动生成。\n\n"
        f"- 来源平台: {source_platform}\n"
        f"- 来源编号: {src_case_id}\n"
        f"- 用例描述: {safe_desc}\n"
        '"""\n\n'
        "import pytest\n\n\n"
        f"def test_{case_id}():\n"
        '    raise NotImplementedError("TODO: 请实现该用例脚本逻辑")\n\n\n'
        'if __name__ == "__main__":\n'
        '    pytest.main(["-s", __file__])\n'
    )


def _plan_sync(
    *,
    source_platform: str,
    target_platform: str,
    module: str,
    start_id: Optional[int],
) -> Tuple[Path, Path, List[Tuple[CaseName, str, Path]]]:
    platform_root = _platform_root()
    src_root = platform_root / _platform_dir_name(source_platform)
    dst_root = platform_root / _platform_dir_name(target_platform)
    src_module = src_root / module
    dst_module = dst_root / module

    if not src_module.exists():
        raise FileNotFoundError(f"未找到来源模块目录: {src_module}")

    cases = _discover_case_names(src_module)
    if not cases:
        raise RuntimeError(f"来源模块目录下未发现可识别用例脚本(6位编号前缀): {src_module}")

    sid = int(start_id) if start_id is not None else _next_start_id(dst_module, target_platform=target_platform)
    plan: List[Tuple[CaseName, str, Path]] = []
    for i, c in enumerate(cases):
        new_id = _format_case_id(sid + i)
        new_name = f"{new_id}{c.desc}.py"
        plan.append((c, new_id, dst_module / new_name))
    return src_module, dst_module, plan


def _sync(
    *,
    source_platform: str,
    target_platform: str,
    module: str,
    start_id: Optional[int],
    overwrite: bool,
    dry_run: bool,
) -> int:
    src_module, dst_module, plan = _plan_sync(
        source_platform=source_platform,
        target_platform=target_platform,
        module=module,
        start_id=start_id,
    )

    print(f"来源: {src_module}")
    print(f"目标: {dst_module}")
    print(f"计划创建: {len(plan)} 个文件")

    created = 0
    skipped = 0

    if not dry_run:
        dst_module.mkdir(parents=True, exist_ok=True)

    for c, new_id, dst_path in plan:
        if dst_path.exists() and not overwrite:
            skipped += 1
            print(f"SKIP(已存在): {dst_path.name}")
            continue

        print(f"CREATE: {dst_path.name}  <=  {c.src_path.name}")
        if dry_run:
            continue

        content = _render_placeholder_test(
            case_id=new_id,
            src_case_id=c.src_case_id,
            desc=c.desc,
            source_platform=_platform_dir_name(source_platform),
        )
        dst_path.write_text(content, encoding="utf-8")
        created += 1

    print(f"完成：created={created}, skipped={skipped}, dry_run={dry_run}")
    return 0


def _list_modules(platform: str) -> List[str]:
    """
    返回平台下可选“功能目录”（例如 1登录/2注册/3忘记密码）。
    这里按来源平台的一级目录列出，避免用户手动输入。
    """
    root = _platform_root() / _platform_dir_name(platform)
    if not root.exists():
        return []
    # 只暴露“功能目录”（通常以数字开头：1登录/2注册/3忘记密码），过滤 __pycache__ 等杂项
    dirs: List[str] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name.startswith(".") or name.startswith("_"):
            continue
        if not re.match(r"^\d+", name):
            continue
        dirs.append(name)
    dirs.sort()
    return dirs


class _GuiApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("名称复制（iOS/Android）")
        self.root.geometry("920x640")

        self.source_var = tk.StringVar(value="ios")
        self.target_var = tk.StringVar(value="android")
        self.module_var = tk.StringVar(value="")
        self.start_id_var = tk.StringVar(value="")
        self.overwrite_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._refresh_modules()

    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)

        top = ttk.LabelFrame(frm, text="参数", padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="从平台").grid(row=0, column=0, sticky="w")
        self.source_cb = ttk.Combobox(
            top, textvariable=self.source_var, values=["ios", "android"], width=12, state="readonly"
        )
        self.source_cb.grid(row=0, column=1, padx=(6, 18), sticky="w")
        self.source_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_modules())
        # macOS 下有时 <<ComboboxSelected>> 触发不及时，增加一次点击时刷新
        self.source_cb.bind("<Button-1>", lambda e: self._refresh_modules())

        ttk.Label(top, text="到平台").grid(row=0, column=2, sticky="w")
        self.target_cb = ttk.Combobox(
            top, textvariable=self.target_var, values=["ios", "android"], width=12, state="readonly"
        )
        self.target_cb.grid(row=0, column=3, padx=(6, 18), sticky="w")

        ttk.Label(top, text="功能目录").grid(row=0, column=4, sticky="w")
        # macOS 下 ttk.Combobox 在频繁切换时偶发卡顿；改为 Listbox 单选更顺滑
        module_box = ttk.Frame(top)
        module_box.grid(row=0, column=5, padx=(6, 18), sticky="w")
        self.module_lb = tk.Listbox(
            module_box,
            height=4,
            width=18,
            exportselection=False,
            activestyle="none",
        )
        self.module_lb.pack(side="left")
        module_sb = ttk.Scrollbar(module_box, command=self.module_lb.yview)
        module_sb.pack(side="right", fill="y")
        self.module_lb.configure(yscrollcommand=module_sb.set)
        self.module_lb.bind("<<ListboxSelect>>", lambda e: self._on_module_listbox_select())

        ttk.Label(top, text="起始编号(可选)").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.start_id_entry = ttk.Entry(top, textvariable=self.start_id_var, width=18)
        self.start_id_entry.grid(row=1, column=1, padx=(6, 18), sticky="w", pady=(10, 0))

        self.overwrite_ck = ttk.Checkbutton(top, text="覆盖已存在(--overwrite)", variable=self.overwrite_var)
        self.overwrite_ck.grid(row=1, column=2, columnspan=2, sticky="w", pady=(10, 0))

        self.dry_run_ck = ttk.Checkbutton(top, text="只预览不落盘(--dry-run)", variable=self.dry_run_var)
        self.dry_run_ck.grid(row=1, column=4, columnspan=2, sticky="w", pady=(10, 0))

        btns = ttk.Frame(top)
        btns.grid(row=2, column=0, columnspan=6, sticky="w", pady=(12, 0))
        self.run_btn = ttk.Button(btns, text="执行", command=self._on_run)
        self.run_btn.pack(side="left")
        ttk.Button(btns, text="清空日志", command=self._clear_log).pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(btns, textvariable=self.status_var).pack(side="left", padx=(14, 0))
        self.progress = ttk.Progressbar(btns, mode="indeterminate", length=180)
        self.progress.pack(side="left", padx=(10, 0))

        for i in range(6):
            top.grid_columnconfigure(i, weight=1 if i == 5 else 0)

        log_box = ttk.LabelFrame(frm, text="日志", padding=10)
        log_box.pack(fill="both", expand=True, pady=(10, 0))

        self.log = tk.Text(log_box, height=20, wrap="word")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_box, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

    def _append_log(self, s: str):
        self.log.insert("end", s + "\n")
        self.log.see("end")

    def _append_log_lines(self, s: str):
        # 尽量把输出按行写入，避免 Text 一次性插入超长字符串导致卡顿
        for line in (s or "").splitlines():
            if line.strip() == "":
                continue
            self._append_log(line)

    def _clear_log(self):
        self.log.delete("1.0", "end")

    def _refresh_modules(self):
        mods = _list_modules(self.source_var.get())
        # 重建 Listbox 内容
        try:
            self.module_lb.delete(0, "end")
            for m in mods:
                self.module_lb.insert("end", m)
        except Exception:
            pass

        if mods:
            # 默认选中第一个
            self.module_var.set(mods[0])
            try:
                self.module_lb.selection_clear(0, "end")
                self.module_lb.selection_set(0)
                self.module_lb.activate(0)
            except Exception:
                pass
        else:
            self.module_var.set("")
        self._on_module_changed()
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _on_module_listbox_select(self):
        try:
            sel = self.module_lb.curselection()
            if not sel:
                return
            idx = int(sel[0])
            val = self.module_lb.get(idx)
            self.module_var.set(val)
            self._on_module_changed()
        except Exception:
            pass

    def _on_module_changed(self):
        module = (self.module_var.get() or "").strip()
        if module:
            self.status_var.set(f"就绪（已选：{module}）")
        else:
            self.status_var.set("就绪（未选择功能目录）")

    def _parse_start_id(self) -> Optional[int]:
        raw = (self.start_id_var.get() or "").strip()
        if not raw:
            return None
        if not raw.isdigit():
            raise ValueError("起始编号必须是 6 位数字（例如 200001）")
        if len(raw) != 6:
            raise ValueError("起始编号必须是 6 位数字（例如 200001）")
        return int(raw)

    def _set_running(self, running: bool):
        state = "disabled" if running else "normal"
        self.run_btn.configure(state=state)
        self.source_cb.configure(state="disabled" if running else "readonly")
        self.target_cb.configure(state="disabled" if running else "readonly")
        try:
            self.module_lb.configure(state=("disabled" if running else "normal"))
        except Exception:
            pass
        self.start_id_entry.configure(state=state)
        self.overwrite_ck.configure(state=state)
        self.dry_run_ck.configure(state=state)
        self.status_var.set("执行中..." if running else "就绪")
        try:
            if running:
                self.root.configure(cursor="watch")
                self.progress.start(10)
            else:
                self.root.configure(cursor="")
                self.progress.stop()
        except Exception:
            pass

    def _on_run(self):
        src = self.source_var.get().strip().lower()
        dst = self.target_var.get().strip().lower()
        module = (self.module_var.get() or "").strip()

        if src == dst:
            messagebox.showerror("参数错误", "--from 和 --to 不能相同")
            return
        if not module:
            messagebox.showerror("参数错误", "请选择功能目录（例如 1登录/2注册/3忘记密码）")
            return

        try:
            start_id = self._parse_start_id()
        except Exception as e:
            messagebox.showerror("参数错误", str(e))
            return

        overwrite = bool(self.overwrite_var.get())
        dry_run = bool(self.dry_run_var.get())

        self._append_log(f"RUN: --from {src} --to {dst} --module {module}"
                         + (f" --start-id {start_id}" if start_id is not None else "")
                         + (" --overwrite" if overwrite else "")
                         + (" --dry-run" if dry_run else ""))
        self._set_running(True)

        class _TkWriter(io.TextIOBase):
            def __init__(self, post_line):
                self._post_line = post_line
                self._buf = ""

            def write(self, s: str) -> int:  # type: ignore[override]
                if not s:
                    return 0
                self._buf += s
                # 以换行符为边界推送到 GUI，避免半行输出
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    self._post_line(line)
                return len(s)

            def flush(self) -> None:  # type: ignore[override]
                if self._buf.strip():
                    self._post_line(self._buf)
                self._buf = ""

        def _worker():
            try:
                writer = _TkWriter(lambda line: self.root.after(0, lambda l=line: self._append_log(l)))
                # 把 _sync 内部 print 实时转到 GUI，避免“没反应”的错觉
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    _sync(
                        source_platform=src,
                        target_platform=dst,
                        module=module,
                        start_id=start_id,
                        overwrite=overwrite,
                        dry_run=dry_run,
                    )
                self.root.after(0, lambda: self._append_log("DONE"))
            except Exception as e:
                self.root.after(0, lambda: self._append_log(f"ERROR: {type(e).__name__}: {e}"))
                self.root.after(0, lambda: messagebox.showerror("执行失败", f"{type(e).__name__}: {e}"))
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_worker, daemon=True).start()

    def run(self):
        self.root.mainloop()


def main(argv: Optional[Iterable[str]] = None) -> int:
    # 直接双击/不带参数运行时：进入 GUI 模式
    if argv is None and len(sys.argv) == 1:
        _GuiApp().run()
        return 0

    ap = argparse.ArgumentParser(description="跨平台复制用例脚本名称，并在目标平台生成占位脚本")
    ap.add_argument("--from", dest="source", required=True, help="来源平台：ios / android")
    ap.add_argument("--to", dest="target", required=True, help="目标平台：ios / android")
    ap.add_argument("--module", required=True, help='模块目录名，例如："1登录" / "2注册" / "3忘记密码"')
    ap.add_argument(
        "--start-id",
        type=int,
        default=None,
        help="目标平台生成的新编号起始值（6位整数）。不传则按平台规则自动续号：iOS=10xxxx, Android=20xxxx。",
    )
    ap.add_argument("--overwrite", action="store_true", help="覆盖已存在的同名目标脚本文件")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不落盘创建文件")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.source.strip().lower() == args.target.strip().lower():
        raise SystemExit("--from 和 --to 不能相同")

    return _sync(
        source_platform=args.source,
        target_platform=args.target,
        module=args.module,
        start_id=args.start_id,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())

