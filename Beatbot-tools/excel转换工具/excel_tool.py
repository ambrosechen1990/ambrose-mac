#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel 转换工具（macOS）

合并两个原脚本的能力：
1. 一键处理 + 对比（excel_映射.py）
   - 选择新/旧表（xlsx/xls/csv），生成标准处理结果：
     最新用户数据 / 完整数据 / 设备统计 / 对比结果
2. Excel 转脚本名称（来自 excel_to_script_names.py）
   - 读取「ID用例名称」列，导出名单，并可选生成 pytest 脚本文件

用法：
  python3 excel_tool.py              # 启动 GUI
  python3 excel_tool.py --gui
  python3 excel_tool.py compare <新文件> <旧文件> [输出文件]
  python3 excel_tool.py scripts <Excel文件> [--column 列名] [--create-scripts] [--output-dir 目录]
"""

from __future__ import annotations

import os
import sys
import traceback
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


def _ui_font(size: int = 12, weight: str | None = None):
    family = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei"
    return (family, size, weight) if weight else (family, size)


class ExcelToolApp:
    """统一入口：页签1=Excel对比，页签2=Excel转脚本。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Excel 转换工具")
        self.root.geometry("920x720")
        self.root.minsize(800, 600)
        self._last_active_ensure_ts = 0.0  # 节流：避免频繁抢焦点导致闪烁

        title = tk.Label(root, text="Excel 转换工具", font=_ui_font(18, "bold"))
        title.pack(pady=(16, 4))
        tip = tk.Label(
            root,
            text="一键生成（四工作表）  ·  从用例表生成脚本名称/pytest 文件",
            font=_ui_font(10),
            fg="#666666",
        )
        tip.pack(pady=(0, 8))

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        # 保存引用用于切换页签时聚焦
        self.notebook = notebook

        self.tab_compare = ttk.Frame(notebook, padding=12)
        self.tab_scripts = ttk.Frame(notebook, padding=12)
        notebook.add(self.tab_compare, text="  一键处理对比  ")
        notebook.add(self.tab_scripts, text="  Excel 转脚本  ")

        self._build_compare_tab()
        self._build_scripts_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        # 当窗口重新获得焦点（从其他程序切回）时，也立刻抢焦点，提升首次点击稳定性
        self.root.bind("<FocusIn>", self._on_focus_in)
        # 初始化时不做额外抢焦点，避免 macOS 上频繁切焦导致闪烁

    def _ensure_active(self):
        """
        macOS 下窗口未激活时，偶发首次点击不触发 command。
        在按钮 command 内部再次抢焦点/置顶，提升点击稳定性。
        """
        try:
            # 节流：避免连续点击/切换页签/FocusIn 事件造成反复抢焦点而闪烁
            now = time.time()
            if now - self._last_active_ensure_ts < 0.4:
                return
            self._last_active_ensure_ts = now

            self.root.update_idletasks()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            # 某些环境不支持 -topmost
            pass

    def _soft_active(self):
        """
        点击按钮时尽量不做 focus_force（会影响 macOS 事件时序）。
        这里只做一个轻量刷新，保证 filedialog/messagebox 能正常进入事件循环。
        """
        try:
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def _on_tab_changed(self, _event=None):
        # 延后一点点，避免与 ttk/布局刷新时序冲突
        self.root.after(30, self._focus_current_tab)

    def _on_focus_in(self, _event=None):
        # 窗口从其他 App 切回后，稍后再把焦点落到当前页可交互控件
        self._ensure_active()
        self.root.after(40, self._focus_current_tab)

    def _focus_current_tab(self):
        """
        把焦点尽量给到当前页第一个交互控件，减少 macOS 首次点击才响应的问题。
        """
        try:
            current = self.notebook.nametowidget(self.notebook.select())
            def _walk(w):
                # 递归遍历控件树，找第一个匹配控件类型
                try:
                    for child in w.winfo_children():
                        yield child
                        yield from _walk(child)
                except tk.TclError:
                    return

            # 优先聚焦 Entry，再聚焦 Button；如果都没有则聚焦 tab 本身
            for w in _walk(current):
                if isinstance(w, tk.Entry):
                    w.focus_set()
                    return
            for w in _walk(current):
                if isinstance(w, tk.Button):
                    w.focus_set()
                    return
            current.focus_set()
        except Exception:
            # 聚焦失败不影响功能
            pass

    # ──────────────────── 页签1：一键处理对比 ────────────────────
    _TABLE_FILETYPES = [
        ("表格文件", "*.xlsx *.xlsm *.xls *.csv *.tsv"),
        ("Excel", "*.xlsx *.xlsm *.xls"),
        ("CSV", "*.csv *.tsv"),
        ("全部", "*.*"),
    ]

    def _build_compare_tab(self):
        f = self.tab_compare
        self.new_file = tk.StringVar()
        self.old_file = tk.StringVar()
        self.out_file = tk.StringVar()

        tk.Label(
            f,
            text="选择新/旧表格 → 一键生成：最新用户数据 · 完整数据 · 设备统计 · 对比结果",
            font=_ui_font(11),
        ).pack(anchor=tk.W)
        tk.Label(
            f,
            text="支持 xlsx / xlsm / xls / csv；输出留空则写入「日期处理结果/原文件名_处理结果.xlsx」",
            font=_ui_font(9),
            fg="#666666",
        ).pack(anchor=tk.W, pady=(2, 6))

        self._path_row(f, "新文件（最新数据）:", self.new_file, self._pick_new)
        self._path_row(f, "旧文件（对比基准）:", self.old_file, self._pick_old)
        self._path_row(f, "输出文件（可空=自动）:", self.out_file, self._pick_out, save=True)

        btn_bar = tk.Frame(f)
        btn_bar.pack(fill=tk.X, pady=10)
        tk.Button(
            btn_bar,
            text="一键生成",
            command=self._run_compare,
            font=_ui_font(12, "bold"),
            bg="#007AFF",
            fg="#000000",
            activebackground="#0062cc",
            activeforeground="#000000",
            padx=18, pady=6, cursor="hand2",
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_bar,
            text="清空日志",
            command=lambda: (self._soft_active(), self._clear_log(self.compare_log)),
        ).pack(
            side=tk.LEFT, padx=8
        )

        self.compare_log = scrolledtext.ScrolledText(f, height=18, font=("Menlo", 10))
        self.compare_log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self._log(
            self.compare_log,
            "选择新表（如地区 CSV）与旧表（历史处理结果或原始表）后，点击「一键生成」。\n",
        )

    def _pick_new(self):
        self._soft_active()
        self.root.update_idletasks()
        p = filedialog.askopenfilename(
            title="选择新表格（最新用户数据）",
            filetypes=self._TABLE_FILETYPES,
            parent=self.root,
        )
        if p:
            self.new_file.set(p)
            self._log(self.compare_log, f"新文件: {p}\n")

    def _pick_old(self):
        self._soft_active()
        self.root.update_idletasks()
        p = filedialog.askopenfilename(
            title="选择旧表格（对比基准）",
            filetypes=self._TABLE_FILETYPES,
            parent=self.root,
        )
        if p:
            self.old_file.set(p)
            self._log(self.compare_log, f"旧文件: {p}\n")

    def _pick_out(self):
        self._soft_active()
        self.root.update_idletasks()
        p = filedialog.asksaveasfilename(
            title="保存处理结果",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            parent=self.root,
        )
        if p:
            self.out_file.set(p)

    def _run_compare(self):
        self._soft_active()
        new_p = self.new_file.get().strip()
        old_p = self.old_file.get().strip()
        out_p = self.out_file.get().strip() or None
        if not new_p or not old_p:
            messagebox.showerror("提示", "请先选择新文件和旧文件")
            return
        if not os.path.exists(new_p) or not os.path.exists(old_p):
            messagebox.showerror("错误", "文件路径不存在")
            return
        try:
            from excel_映射 import one_click_process_and_compare

            self._log(self.compare_log, "\n" + "=" * 50 + "\n开始一键处理+对比...\n")
            self.root.update_idletasks()
            result = one_click_process_and_compare(new_p, old_p, out_p)
            if result:
                self._log(
                    self.compare_log,
                    f"✅ 完成\n📁 输出: {result}\n"
                    f"工作表顺序: 最新用户数据 → 完整数据 → 设备统计 → 对比结果\n",
                )
                messagebox.showinfo(
                    "完成",
                    f"处理结果已生成！\n\n"
                    f"① 最新用户数据\n② 完整数据\n③ 设备统计\n④ 对比结果\n\n"
                    f"输出：\n{result}",
                )
            else:
                self._log(self.compare_log, "❌ 处理失败\n")
                messagebox.showerror("失败", "处理失败，请查看日志")
        except Exception as e:
            self._log(self.compare_log, f"❌ {e}\n{traceback.format_exc()}\n")
            messagebox.showerror("错误", str(e))

    # ──────────────────── 页签2：转脚本 ────────────────────
    def _build_scripts_tab(self):
        f = self.tab_scripts
        self.script_excel = tk.StringVar()
        self.column_name = tk.StringVar(value="ID用例名称")
        self.sheet_name = tk.StringVar()
        self.script_outdir = tk.StringVar(value=str(HERE / "生成的脚本"))
        self.create_scripts = tk.BooleanVar(value=True)

        tk.Label(
            f, text="读取用例名称列，导出名单，并可生成 pytest 脚本文件", font=_ui_font(11)
        ).pack(anchor=tk.W)

        self._path_row(f, "Excel 文件:", self.script_excel, self._pick_script_excel)

        row = tk.Frame(f)
        row.pack(fill=tk.X, pady=4)
        tk.Label(row, text="列名:", width=18, anchor=tk.W).pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.column_name, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)

        row2 = tk.Frame(f)
        row2.pack(fill=tk.X, pady=4)
        tk.Label(row2, text="工作表(可空=首表):", width=18, anchor=tk.W).pack(side=tk.LEFT)
        tk.Entry(row2, textvariable=self.sheet_name, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._path_row(f, "脚本输出目录:", self.script_outdir, self._pick_script_outdir, directory=True)

        tk.Checkbutton(
            f, text="创建 .py 脚本文件（pytest 模板）", variable=self.create_scripts, font=_ui_font(11)
        ).pack(anchor=tk.W, pady=6)

        btn_bar = tk.Frame(f)
        btn_bar.pack(fill=tk.X, pady=6)
        tk.Button(
            btn_bar, text="开始转换", command=self._run_scripts,
            font=_ui_font(12, "bold"), bg="#007AFF", fg="#FFFFFF",
            activebackground="#0062cc", activeforeground="#FFFFFF",
            padx=18, pady=6, cursor="hand2",
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_bar,
            text="清空日志",
            command=lambda: (self._soft_active(), self._clear_log(self.script_log)),
        ).pack(
            side=tk.LEFT, padx=8
        )

        self.script_log = scrolledtext.ScrolledText(f, height=16, font=("Menlo", 10))
        self.script_log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self._log(self.script_log, "选择含「ID用例名称」列的 Excel，点击「开始转换」。\n")

    def _pick_script_excel(self):
        self._soft_active()
        self.root.update_idletasks()
        p = filedialog.askopenfilename(
            title="选择用例 Excel",
            filetypes=[("Excel", "*.xlsx *.xls"), ("全部", "*.*")],
            parent=self.root,
        )
        if p:
            self.script_excel.set(p)
            self._log(self.script_log, f"已选择: {p}\n")

    def _pick_script_outdir(self):
        self._soft_active()
        self.root.update_idletasks()
        p = filedialog.askdirectory(title="选择脚本输出目录", parent=self.root)
        if p:
            self.script_outdir.set(p)

    def _run_scripts(self):
        self._soft_active()
        excel = self.script_excel.get().strip()
        if not excel or not os.path.exists(excel):
            messagebox.showerror("提示", "请先选择有效的 Excel 文件")
            return
        column = self.column_name.get().strip() or "ID用例名称"
        sheet = self.sheet_name.get().strip() or None
        out_dir = self.script_outdir.get().strip() or str(HERE / "生成的脚本")
        try:
            from excel_to_script_names import (
                create_script_files,
                read_excel_column,
                save_script_names,
            )

            self._log(self.script_log, "\n" + "=" * 50 + "\n开始读取...\n")
            names = read_excel_column(excel, column, sheet)
            if not names:
                messagebox.showwarning("警告", "未读取到任何用例名称")
                return
            self._log(self.script_log, f"✅ 读取到 {len(names)} 个用例名称\n")

            list_path = os.path.join(out_dir, "script_names.txt")
            os.makedirs(out_dir, exist_ok=True)
            save_script_names(names, list_path)
            self._log(self.script_log, f"💾 名单已保存: {list_path}\n")

            created = []
            if self.create_scripts.get():
                created = create_script_files(names, out_dir)
                self._log(self.script_log, f"✅ 已创建 {len(created)} 个脚本到: {out_dir}\n")

            messagebox.showinfo(
                "完成",
                f"用例数量: {len(names)}\n"
                f"脚本文件: {len(created)}\n"
                f"名单: {list_path}\n"
                f"目录: {os.path.abspath(out_dir)}",
            )
        except Exception as e:
            self._log(self.script_log, f"❌ {e}\n{traceback.format_exc()}\n")
            messagebox.showerror("错误", str(e))

    # ──────────────────── 通用 UI ────────────────────
    def _path_row(self, parent, label, var, browse_cmd, save=False, directory=False):
        row = tk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        tk.Label(row, text=label, width=22, anchor=tk.W).pack(side=tk.LEFT)
        tk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        tk.Button(row, text="浏览...", command=browse_cmd, width=8).pack(side=tk.LEFT)

    @staticmethod
    def _log(widget, text: str):
        widget.insert(tk.END, text)
        widget.see(tk.END)

    @staticmethod
    def _clear_log(widget):
        widget.delete("1.0", tk.END)


def run_gui():
    if not GUI_AVAILABLE:
        print("需要 tkinter，请安装带 Tcl/Tk 的 Python")
        sys.exit(1)
    root = tk.Tk()
    ExcelToolApp(root)
    # macOS 上如果窗口尚未激活，可能会出现“首次点按钮不响应、需要再点一次”的体验问题。
    # 这里在主循环进入前后强制窗口置顶/聚焦，尽量避免首次点击才激活窗口。
    def _activate_window():
        try:
            root.update_idletasks()
            root.lift()
            root.focus_force()
        except tk.TclError:
            # 某些平台/旧 Tcl 版本不支持 -topmost
            pass

    root.after_idle(_activate_window)
    root.mainloop()


def run_cli(argv: list[str]) -> int:
    if not argv:
        run_gui()
        return 0

    cmd = argv[0]
    if cmd in ("--gui", "gui"):
        run_gui()
        return 0

    if cmd == "compare":
        if len(argv) < 3:
            print("用法: python excel_tool.py compare <新文件> <旧文件> [输出文件]")
            return 1
        from excel_映射 import one_click_process_and_compare

        new_f, old_f = argv[1], argv[2]
        out_f = argv[3] if len(argv) > 3 else None
        result = one_click_process_and_compare(new_f, old_f, out_f)
        return 0 if result else 1

    if cmd == "scripts":
        if len(argv) < 2:
            print(
                "用法: python excel_tool.py scripts <Excel> "
                "[--column 列名] [--sheet 表名] [--create-scripts] [--output-dir 目录]"
            )
            return 1
        from excel_to_script_names import (
            create_script_files,
            print_script_names,
            read_excel_column,
            save_script_names,
        )

        excel = argv[1]
        column = "ID用例名称"
        sheet = None
        create = False
        out_dir = str(HERE / "生成的脚本")
        i = 2
        while i < len(argv):
            if argv[i] == "--column" and i + 1 < len(argv):
                column = argv[i + 1]
                i += 2
            elif argv[i] == "--sheet" and i + 1 < len(argv):
                sheet = argv[i + 1]
                i += 2
            elif argv[i] == "--create-scripts":
                create = True
                i += 1
            elif argv[i] == "--output-dir" and i + 1 < len(argv):
                out_dir = argv[i + 1]
                i += 2
            else:
                i += 1
        names = read_excel_column(excel, column, sheet)
        print_script_names(names)
        os.makedirs(out_dir, exist_ok=True)
        save_script_names(names, os.path.join(out_dir, "script_names.txt"))
        if create:
            create_script_files(names, out_dir)
        return 0

    print(__doc__)
    return 1


def main():
    raise SystemExit(run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
