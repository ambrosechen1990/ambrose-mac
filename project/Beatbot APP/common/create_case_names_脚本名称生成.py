# -*- coding: utf-8 -*-
"""
用例脚本批量生成 — Tkinter 图形界面

从 Excel/CSV 按用例编号匹配名称，在指定目录批量生成「编号+用例名称.py」占位脚本。

运行：
  python3 "project/Beatbot APP/common/create_case_names_脚本名称生成.py"

读 .xlsx 需安装：pip install openpyxl
"""

from __future__ import annotations

import csv
import re
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any


# --- 核心逻辑 ---


@dataclass(frozen=True)
class CaseRow:
    case_id: str
    case_name: str


def _split_id_and_name_from_cell(v: Any) -> tuple[str | None, str | None]:
    """
    支持单元格内为「100173验证xxx」这种格式：
    - 提取前缀编号作为 case_id
    - 剩余文本作为 case_name（去首尾空格）
    """
    if v is None:
        return None, None
    s = str(v).strip()
    if not s:
        return None, None
    m = re.match(r"^\s*(\d{3,})\s*(.*)\s*$", s)
    if not m:
        return None, None
    cid = m.group(1)
    rest = (m.group(2) or "").strip()
    return cid, (rest or None)


def _norm_case_id(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = re.search(r"\d{3,}", s)
    return m.group(0) if m else None


def _norm_case_name(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _safe_filename(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[\/\\:\*\?\"<>\|]", "_", s)
    return s[:180].strip()


def _read_csv_cases(path: Path) -> list[CaseRow]:
    rows: list[CaseRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for r in reader:
            if not r:
                continue
            # 常见：单列里就是「编号+用例名称」
            if len(r) == 1:
                cid, rest = _split_id_and_name_from_cell(r[0])
                if cid and rest:
                    rows.append(CaseRow(case_id=cid, case_name=rest))
                    continue
            cid = _norm_case_id(r[0]) if len(r) >= 1 else None
            name = _norm_case_name(r[1]) if len(r) >= 2 else None
            if cid and name:
                rows.append(CaseRow(case_id=cid, case_name=name))
                continue
            cid2 = None
            for cell in r:
                cid2 = _norm_case_id(cell)
                if cid2:
                    break
            if not cid2:
                continue
            name2 = None
            for cell in r:
                t = _norm_case_name(cell)
                if t and not _norm_case_id(t):
                    name2 = t
                    break
            if not name2:
                # 兜底：尝试从某个单元格直接拆「编号+名称」
                for cell in r:
                    cid3, rest3 = _split_id_and_name_from_cell(cell)
                    if cid3 == cid2 and rest3:
                        name2 = rest3
                        break
            if cid2 and name2:
                rows.append(CaseRow(case_id=cid2, case_name=name2))
    return rows


def _read_xlsx_cases(path: Path, sheet_name: str | None = None) -> list[CaseRow]:
    try:
        import openpyxl  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "未检测到 openpyxl，无法读取 .xlsx/.xlsm。\n"
            "请先安装：pip install openpyxl\n"
            f"原始错误: {e}"
        ) from e

    wb = openpyxl.load_workbook(path, data_only=True)
    sheets = [wb[sheet_name]] if sheet_name and sheet_name in wb.sheetnames else wb.worksheets
    out: list[CaseRow] = []
    for ws in sheets:
        for row in ws.iter_rows(values_only=True):
            if not row:
                continue
            # 常见：第一列就是「编号+用例名称」，且没有第二列
            if len(row) == 1:
                cid, rest = _split_id_and_name_from_cell(row[0])
                if cid and rest:
                    out.append(CaseRow(case_id=cid, case_name=rest))
                    continue
            cid = _norm_case_id(row[0]) if len(row) >= 1 else None
            name = _norm_case_name(row[1]) if len(row) >= 2 else None
            if cid and name:
                out.append(CaseRow(case_id=cid, case_name=name))
                continue
            cid2 = None
            for cell in row:
                cid2 = _norm_case_id(cell)
                if cid2:
                    break
            if not cid2:
                continue
            name2 = None
            for cell in row:
                t = _norm_case_name(cell)
                if t and not _norm_case_id(t):
                    name2 = t
                    break
            if not name2:
                for cell in row:
                    cid3, rest3 = _split_id_and_name_from_cell(cell)
                    if cid3 == cid2 and rest3:
                        name2 = rest3
                        break
            if cid2 and name2:
                out.append(CaseRow(case_id=cid2, case_name=name2))
    return out


def load_cases(source_path: Path, sheet_name: str | None = None) -> dict[str, str]:
    ext = source_path.suffix.lower()
    if ext == ".csv":
        rows = _read_csv_cases(source_path)
    elif ext in {".xlsx", ".xlsm"}:
        rows = _read_xlsx_cases(source_path, sheet_name=sheet_name)
    else:
        raise ValueError(f"不支持的文件类型: {ext}（仅支持 .xlsx/.xlsm/.csv）")

    m: dict[str, str] = {}
    for r in rows:
        if r.case_id and r.case_name:
            m[r.case_id] = r.case_name
    return m


def load_case_names_in_order(source_path: Path, sheet_name: str | None = None) -> list[str]:
    """
    当表格里没有「用例编号」列时，按行顺序提取「用例名称」：
    - 常见：只有一列「用例名称」
    - 或者两列：第一列编号、第二列名称（也可提取名称）
    """
    ext = source_path.suffix.lower()
    names: list[str] = []

    def _maybe_add_name(v: Any) -> None:
        t = _norm_case_name(v)
        if not t:
            return
        low = t.strip().lower()
        # 跳过表头
        if low in {"用例名称", "case name", "casename", "name"}:
            return
        # 跳过纯数字
        if _norm_case_id(t):
            return
        names.append(t)

    def _norm_header(v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def _find_case_name_col_idx(cells: list[Any]) -> int | None:
        """
        优先按表头定位“用例名称”列（支持：用例名称 / Case Name 等）。
        返回列索引（0-based）。
        """
        for i, c in enumerate(cells):
            h = _norm_header(c)
            if not h:
                continue
            if h == "用例名称":
                return i
        for i, c in enumerate(cells):
            h = _norm_header(c).lower()
            if not h:
                continue
            if "用例名称" in h or h in {"case name", "casename", "name"}:
                return i
        return None

    if ext == ".csv":
        with source_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header_idx: int | None = None
            header_found = False
            for r in reader:
                if not r:
                    continue
                if not header_found:
                    header_idx = _find_case_name_col_idx(list(r))
                    header_found = True
                    # 如果这一行是表头，跳过
                    if header_idx is not None:
                        continue
                # 优先：第二列
                if header_idx is not None and header_idx < len(r):
                    _maybe_add_name(r[header_idx])
                    continue
                if len(r) >= 2 and _norm_case_name(r[1]):
                    _maybe_add_name(r[1])
                    continue
                # 其次：单列
                if len(r) == 1:
                    cid, rest = _split_id_and_name_from_cell(r[0])
                    if cid and rest:
                        names.append(rest)
                    else:
                        _maybe_add_name(r[0])
                    continue
                # 兜底：找第一格非数字文本
                for cell in r:
                    if _norm_case_name(cell) and not _norm_case_id(cell):
                        _maybe_add_name(cell)
                        break
    elif ext in {".xlsx", ".xlsm"}:
        try:
            import openpyxl  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "未检测到 openpyxl，无法读取 .xlsx/.xlsm。\n"
                "请先安装：pip install openpyxl\n"
                f"原始错误: {e}"
            ) from e

        wb = openpyxl.load_workbook(source_path, data_only=True)
        sheets = [wb[sheet_name]] if sheet_name and sheet_name in wb.sheetnames else wb.worksheets
        for ws in sheets:
            header_idx: int | None = None
            header_row_num: int | None = None
            # 在前 30 行内找表头
            for rn, row in enumerate(ws.iter_rows(values_only=True), start=1):
                if rn > 30:
                    break
                if not row:
                    continue
                header_idx = _find_case_name_col_idx(list(row))
                if header_idx is not None:
                    header_row_num = rn
                    break
            for row in ws.iter_rows(values_only=True):
                if not row:
                    continue
                # 若找到了表头，则只读“用例名称”列，且跳过表头行
                if header_idx is not None:
                    # 这里无法直接拿到当前行号，只能用“表头内容匹配”跳过
                    if header_idx < len(row) and _norm_header(row[header_idx]) == "用例名称":
                        continue
                    if header_idx < len(row):
                        _maybe_add_name(row[header_idx])
                        continue
                # 两列：优先第二列当名称
                if len(row) >= 2 and _norm_case_name(row[1]):
                    _maybe_add_name(row[1])
                    continue
                # 单列：尝试拆「编号+名称」，否则直接当名称
                if len(row) == 1:
                    cid, rest = _split_id_and_name_from_cell(row[0])
                    if cid and rest:
                        names.append(rest)
                    else:
                        _maybe_add_name(row[0])
                    continue
                # 兜底：找第一格非数字文本
                for cell in row:
                    if _norm_case_name(cell) and not _norm_case_id(cell):
                        _maybe_add_name(cell)
                        break
    else:
        raise ValueError(f"不支持的文件类型: {ext}（仅支持 .xlsx/.xlsm/.csv）")

    return names


def _parse_range(start_id: int, end_or_count: str) -> tuple[int, int]:
    s = end_or_count.strip()
    if not s:
        raise ValueError("结束编号/数量不能为空")
    if s.startswith("+"):
        count = int(s[1:])
        if count <= 0:
            raise ValueError("数量必须 > 0")
        return start_id, start_id + count - 1
    end_id = int(s)
    if end_id < start_id:
        raise ValueError("结束编号不能小于起始编号")
    return start_id, end_id


def parse_import_count(count_s: str) -> int:
    s = count_s.strip()
    if not s:
        raise ValueError("导入数量不能为空")
    if not re.fullmatch(r"\d+", s):
        raise ValueError("导入数量必须是正整数")
    count = int(s)
    if count <= 0:
        raise ValueError("导入数量必须 > 0")
    return count


def _default_target_dir() -> str:
    # 默认指向 iOS 平台用例根目录，便于再向下选择具体模块目录
    return str(Path(__file__).resolve().parents[1] / "用例" / "登录" / "iOS")


def parse_start_id(start_id_s: str) -> int:
    m = re.search(r"\d+", start_id_s.strip())
    if not m:
        raise ValueError("起始编号中未找到有效数字")
    return int(m.group(0))


@dataclass(frozen=True)
class BatchResult:
    target_dir: Path
    start_id: int
    end_id: int
    case_map_size: int
    created: tuple[Path, ...]
    total_in_range: int

    @property
    def skipped_count(self) -> int:
        return self.total_in_range - len(self.created)


def generate_files(
    *,
    case_map: dict[str, str],
    start_id: int,
    end_id: int,
    target_dir: Path,
    overwrite: bool = False,
) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    for cid in range(start_id, end_id + 1):
        cid_str = str(cid)
        name = case_map.get(cid_str) or f"{cid_str}用例名称未找到"
        # 避免 name 本身已包含编号（如「100173验证xxx」）时再次拼接
        if name.startswith(cid_str):
            filename = _safe_filename(f"{name}.py")
        else:
            filename = _safe_filename(f"{cid_str}{name}.py")
        path = target_dir / filename

        if path.exists() and not overwrite:
            continue

        title = name if name.startswith(cid_str) else f"{cid_str} {name}"
        content = (
            "# -*- coding: utf-8 -*-\n"
            '"""\n'
            f"{title}\n"
            '"""\n'
            "\n"
            "import pytest\n"
            "\n"
            "\n"
            f"def test_{cid_str}():\n"
            "    assert True\n"
        )
        path.write_text(content, encoding="utf-8")
        created.append(path)

    return created


def run_batch(
    *,
    source_path: Path,
    sheet_name: str | None,
    start_id: int,
    end_or_count: str,
    target_dir: Path,
    overwrite: bool = False,
) -> BatchResult:
    start_id, end_id = _parse_range(start_id, end_or_count)
    case_map = load_cases(source_path, sheet_name=sheet_name)
    if not case_map:
        raise ValueError("未从数据源解析到任何（用例编号，用例名称）")
    created = generate_files(
        case_map=case_map,
        start_id=start_id,
        end_id=end_id,
        target_dir=target_dir,
        overwrite=overwrite,
    )
    return BatchResult(
        target_dir=target_dir,
        start_id=start_id,
        end_id=end_id,
        case_map_size=len(case_map),
        created=tuple(created),
        total_in_range=end_id - start_id + 1,
    )


def run_batch_by_count(
    *,
    source_path: Path,
    sheet_name: str | None,
    start_id: int,
    import_count: int,
    target_dir: Path,
    overwrite: bool = False,
) -> BatchResult:
    if import_count <= 0:
        raise ValueError("导入数量必须 > 0")
    end_id = start_id + import_count - 1
    case_map = load_cases(source_path, sheet_name=sheet_name)
    # 若表格没有编号列，则按行顺序取名称，按起始编号顺序生成
    if not case_map:
        names = load_case_names_in_order(source_path, sheet_name=sheet_name)
        if not names:
            raise ValueError("未从数据源解析到任何（用例编号，用例名称/名称列表）")
        if len(names) < import_count:
            raise ValueError(
                f"数据源名称数量不足：需要 {import_count}，实际仅 {len(names)}（请检查是否包含表头/空行）"
            )
        case_map = {str(start_id + i): names[i] for i in range(import_count)}

    created = generate_files(
        case_map=case_map,
        start_id=start_id,
        end_id=end_id,
        target_dir=target_dir,
        overwrite=overwrite,
    )
    return BatchResult(
        target_dir=target_dir,
        start_id=start_id,
        end_id=end_id,
        case_map_size=len(case_map),
        created=tuple(created),
        total_in_range=end_id - start_id + 1,
    )


def run_batch_all_names(
    *,
    source_path: Path,
    sheet_name: str | None,
    start_id: int,
    target_dir: Path,
    overwrite: bool = False,
) -> BatchResult:
    """
    从表格按行顺序读取“用例名称”，并从 start_id 起顺序生成全部脚本。
    适用于表格没有用例编号列的场景（常见：只导出“用例名称”一列）。
    """
    names = load_case_names_in_order(source_path, sheet_name=sheet_name)
    if not names:
        raise ValueError("未从数据源解析到任何用例名称")
    end_id = start_id + len(names) - 1
    case_map = {str(start_id + i): names[i] for i in range(len(names))}
    created = generate_files(
        case_map=case_map,
        start_id=start_id,
        end_id=end_id,
        target_dir=target_dir,
        overwrite=overwrite,
    )
    return BatchResult(
        target_dir=target_dir,
        start_id=start_id,
        end_id=end_id,
        case_map_size=len(names),
        created=tuple(created),
        total_in_range=len(names),
    )

# --- Tkinter 界面 ---


class CaseScriptGeneratorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("用例脚本批量生成")
        self.minsize(640, 520)
        self._is_busy = False
        self._build_ui()
        self._set_defaults()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        # macOS 上更稳定的焦点行为
        self.bind_all("<Button-1>", lambda _e: None)

        ttk.Label(frm, text="Excel / CSV 数据源").grid(row=0, column=0, sticky=tk.W, **pad)
        row_src = ttk.Frame(frm)
        row_src.grid(row=0, column=1, sticky=tk.EW, **pad)
        frm.columnconfigure(1, weight=1)
        self.var_source = tk.StringVar()
        ent_src = ttk.Entry(row_src, textvariable=self.var_source)
        ent_src.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ent_src.bind("<Button-1>", lambda _e: ent_src.focus_set())
        self.btn_pick_source = ttk.Button(row_src, text="浏览…", command=self._pick_source, width=8)
        self.btn_pick_source.pack(
            side=tk.LEFT, padx=(6, 0)
        )

        ttk.Label(frm, text="Sheet 名（xlsx，可选）").grid(row=1, column=0, sticky=tk.W, **pad)
        self.var_sheet = tk.StringVar()
        ent_sheet = ttk.Entry(frm, textvariable=self.var_sheet)
        ent_sheet.grid(row=1, column=1, sticky=tk.EW, **pad)
        ent_sheet.bind("<Button-1>", lambda _e: ent_sheet.focus_set())
        ttk.Label(frm, text="留空 = 遍历所有 sheet", foreground="#666").grid(
            row=2, column=1, sticky=tk.W, padx=10, pady=(0, 4)
        )

        ttk.Label(frm, text="起始用例编号").grid(row=3, column=0, sticky=tk.W, **pad)
        self.var_start = tk.StringVar()
        ent_start = ttk.Entry(frm, textvariable=self.var_start, width=24)
        ent_start.grid(row=3, column=1, sticky=tk.W, **pad)
        ent_start.bind("<Button-1>", lambda _e: ent_start.focus_set())

        ttk.Label(frm, text="导入数量").grid(row=4, column=0, sticky=tk.W, **pad)
        ttk.Label(frm, text="自动获取（按表格行数）", foreground="#666").grid(
            row=4, column=1, sticky=tk.W, **pad
        )
        ttk.Label(frm, text="提示：会按“用例名称”列从上到下全部生成", foreground="#666").grid(
            row=5, column=1, sticky=tk.W, padx=10, pady=(0, 4)
        )

        ttk.Label(frm, text="生成目录").grid(row=6, column=0, sticky=tk.W, **pad)
        row_tgt = ttk.Frame(frm)
        row_tgt.grid(row=6, column=1, sticky=tk.EW, **pad)
        self.var_target = tk.StringVar()
        ent_target = ttk.Entry(row_tgt, textvariable=self.var_target)
        ent_target.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ent_target.bind("<Button-1>", lambda _e: ent_target.focus_set())
        self.btn_pick_target = ttk.Button(row_tgt, text="浏览…", command=self._pick_target, width=8)
        self.btn_pick_target.pack(
            side=tk.LEFT, padx=(6, 0)
        )

        self.var_overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="覆盖已存在的同名文件", variable=self.var_overwrite).grid(
            row=7, column=1, sticky=tk.W, **pad
        )

        row_btn = ttk.Frame(frm)
        row_btn.grid(row=8, column=0, columnspan=2, pady=(8, 4))
        self.btn_generate = ttk.Button(row_btn, text="生成脚本", command=self._on_generate)
        self.btn_generate.pack(side=tk.LEFT, padx=4)
        self.btn_clear_log = ttk.Button(row_btn, text="清空日志", command=self._clear_log)
        self.btn_clear_log.pack(side=tk.LEFT, padx=4)

        ttk.Label(frm, text="运行日志").grid(row=9, column=0, sticky=tk.NW, padx=10, pady=6)
        self.log = scrolledtext.ScrolledText(frm, height=14, wrap=tk.WORD, font=("Menlo", 11))
        self.log.grid(row=9, column=1, sticky=tk.NSEW, padx=10, pady=6)
        frm.rowconfigure(9, weight=1)

        self.status = ttk.Label(frm, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status.grid(row=10, column=0, columnspan=2, sticky=tk.EW, padx=10, pady=(0, 8))

    def _set_defaults(self) -> None:
        self.var_target.set(_default_target_dir())

    def _append_log(self, msg: str) -> None:
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def _clear_log(self) -> None:
        self.log.delete("1.0", tk.END)
        self.status.config(text="日志已清空")

    def _pick_source(self) -> None:
        if self._is_busy:
            return
        # 用 after 调度，避免 macOS 偶发“按钮无响应”
        self.after(10, self._pick_source_impl)

    def _pick_source_impl(self) -> None:
        try:
            path = filedialog.askopenfilename(
                title="选择 Excel 或 CSV",
                initialdir=self.var_target.get().strip() or _default_target_dir(),
                filetypes=[
                    ("表格文件", "*.xlsx *.xlsm *.csv"),
                    ("Excel", "*.xlsx *.xlsm"),
                    ("CSV", "*.csv"),
                    ("所有文件", "*.*"),
                ],
            )
            if path:
                self.var_source.set(path)
        except Exception as e:
            messagebox.showerror("打开文件失败", str(e))

    def _pick_target(self) -> None:
        if self._is_busy:
            return
        self.after(10, self._pick_target_impl)

    def _pick_target_impl(self) -> None:
        try:
            path = filedialog.askdirectory(
                title="选择脚本生成目录",
                initialdir=self.var_target.get().strip() or _default_target_dir(),
            )
            if path:
                self.var_target.set(path)
        except Exception as e:
            messagebox.showerror("选择目录失败", str(e))

    def _set_busy(self, busy: bool) -> None:
        self._is_busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for w in (self.btn_generate, self.btn_clear_log, self.btn_pick_source, self.btn_pick_target):
            try:
                w.configure(state=state)
            except Exception:
                pass
        self.status.config(text="正在生成…" if busy else "就绪")

    def _on_generate(self) -> None:
        if self._is_busy:
            return
        src = self.var_source.get().strip()
        if not src:
            messagebox.showwarning("提示", "请选择或填写 Excel/CSV 数据源路径")
            return

        src_path = Path(src).expanduser().resolve()
        if not src_path.exists():
            messagebox.showerror("错误", f"数据源不存在:\n{src_path}")
            return

        start_s = self.var_start.get().strip()
        if not start_s:
            messagebox.showwarning("提示", "请填写起始用例编号")
            return

        target_s = self.var_target.get().strip()
        if not target_s:
            messagebox.showwarning("提示", "请选择生成目录")
            return

        sheet = self.var_sheet.get().strip() or None
        target_dir = Path(target_s).expanduser().resolve()
        overwrite = bool(self.var_overwrite.get())

        try:
            start_id = parse_start_id(start_s)
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return

        self._set_busy(True)

        def _worker():
            try:
                result = run_batch_all_names(
                    source_path=src_path,
                    sheet_name=sheet,
                    start_id=start_id,
                    target_dir=target_dir,
                    overwrite=overwrite,
                )
                self.after(0, lambda: self._on_generate_success(result, overwrite))
            except Exception as e:
                self.after(0, lambda: self._on_generate_failed(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_generate_failed(self, e: Exception) -> None:
        self._set_busy(False)
        self.status.config(text="生成失败")
        messagebox.showerror("生成失败", str(e))
        self._append_log(f"❌ 失败: {e}")

    def _on_generate_success(self, result: BatchResult, overwrite: bool) -> None:
        self._set_busy(False)
        created = list(result.created)
        self._append_log("=" * 48)
        self._append_log(f"✅ 完成 — {result.target_dir}")
        self._append_log(f"编号区间: {result.start_id} ~ {result.end_id}")
        self._append_log(f"用例名称数量: {result.case_map_size}")
        self._append_log(f"应处理: {result.total_in_range} 个")
        self._append_log(f"实际创建/覆盖: {len(created)} 个")
        if result.skipped_count > 0 and not overwrite:
            self._append_log(f"跳过（已存在）: {result.skipped_count} 个")

        if created:
            self._append_log("生成文件:")
            for p in created:
                self._append_log(f"  · {p.name}")
        else:
            self._append_log("（未写入新文件：可能均已存在且未勾选覆盖）")

        summary = f"已生成 {len(created)} 个文件"
        if result.skipped_count > 0 and not overwrite:
            summary += f"，跳过 {result.skipped_count} 个"
        self.status.config(text=summary)
        messagebox.showinfo("完成", summary)


def main() -> int:
    app = CaseScriptGeneratorApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
