from __future__ import annotations

import logging
import os
import platform
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from .controller import ProjectController
from .errors import UIProjectError
from .logging_utils import LOGGER_NAME
from .presentation import build_project_overview, case_tree_counts, filter_case_tree
from .runtime import app_metadata
from .source_preview import preview_models, preview_msi, preview_spf
from .status import ConfigStatus, GenerationStatus, status_label
from .theme import BACKGROUND, FAIL, MUTED, PANEL, PASS, WARNING, apply_modern_style
from .ui_text import TEXT, TOOLTIPS
from .widgets import PathField, ScrollableFrame, Tooltip


class IBISApplicationView(tk.Tk):
    """Cross-platform Tk shell; project decisions remain in headless services."""

    def __init__(self, controller: ProjectController, smoke_test: bool = False):
        super().__init__()
        self.controller = controller
        self.metadata = app_metadata()
        self.ui_font = apply_modern_style(self)
        self.title(f"IBIS Automation {self.metadata.version} — IBIS 自动化配置工具")
        self.geometry("1366x768")
        self.minsize(1024, 680)
        self.configure(background=BACKGROUND)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tree_modules: dict[str, str] = {}
        self._selected_module: str | None = None
        self._loading_form = False
        self._module_vars: dict[str, tk.StringVar] = {}
        self._root_vars: dict[str, tk.StringVar] = {}
        self._template_vars: dict[str, tk.StringVar] = {}
        self._template_display_ids: dict[str, dict[str, str | None]] = {}
        self.smoke_error: str | None = None
        self._content = ttk.Frame(self)
        self._content.pack(fill="both", expand=True)
        self._show_main() if self.controller.project else self._show_start()
        if smoke_test:
            self.after(400, self._run_smoke_test)

    def _run_smoke_test(self) -> None:
        """Exercise the real main window layout before CI auto-closes it."""
        try:
            self.update_idletasks()
            if not self.controller.project:
                raise RuntimeError("GUI Smoke 未加载项目")
            if not self.status_message.winfo_ismapped():
                raise RuntimeError("固定底部操作栏不可见")
            bbox = self.config_scroll.canvas.bbox("all")
            if not bbox or bbox[3] - bbox[1] <= self.config_scroll.canvas.winfo_height():
                raise RuntimeError("Config 长表单未形成可滚动区域")
            before = self.config_scroll.canvas.yview()
            self.config_scroll.canvas.yview_moveto(1.0)
            self.update_idletasks()
            if self.config_scroll.canvas.yview() == before:
                raise RuntimeError("Config 纵向滚动无效")
            self.config_scroll.canvas.yview_moveto(0.0)
            if not self.template_drv_combo.cget("values"):
                raise RuntimeError("T2B DRV 模板下拉框未加载")
            if not self.msi_tree.get_children() or not self.spf_tree.get_children() or not self.model_tree.get_children():
                raise RuntimeError("MSI/SPF/Model 只读预览未加载")
        except Exception as exc:
            self.smoke_error = str(exc)
        finally:
            self.destroy()

    def _clear(self) -> None:
        for child in self._content.winfo_children():
            child.destroy()

    def _show_start(self) -> None:
        self._clear()
        toolbar = ttk.Frame(self._content, padding=(16, 10), style="Toolbar.TFrame")
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="IBIS Automation", style="Title.TLabel", background=PANEL).pack(side="left")
        ttk.Label(toolbar, text="未打开项目", style="StatusDirty.TLabel", background=PANEL).pack(side="left", padx=16)
        for key, command, primary in (
            ("open_project", self._open_project, False),
            ("import_config", self._import_excel, True),
            ("new_project", self._new_project, False),
        ):
            button = ttk.Button(toolbar, text=TEXT[key], command=command, style="Primary.TButton" if primary else "Secondary.TButton")
            button.pack(side="right", padx=3)
            Tooltip(button, TOOLTIPS[key])

        scrolling = ScrollableFrame(self._content)
        scrolling.pack(fill="both", expand=True, padx=16, pady=12)
        panel = scrolling.body
        ttk.Label(panel, text="项目首页", style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text=TEXT.get("app_subtitle", ""), foreground=MUTED).pack(anchor="w", pady=(3, 18))
        card = ttk.LabelFrame(panel, text="开始使用", padding=18, style="Card.TLabelframe")
        card.pack(fill="x", pady=(0, 12))
        ttk.Label(card, text="请选择一种方式开始：新建项目、只读导入 Config Excel，或打开已经保存的项目。", style="Panel.TLabel").pack(anchor="w")
        actions = ttk.Frame(card, style="Panel.TFrame")
        actions.pack(anchor="w", pady=(14, 0))
        for key, command in (("new_project", self._new_project), ("import_config", self._import_excel), ("open_project", self._open_project)):
            button = ttk.Button(actions, text=TEXT[key], command=command, style="Primary.TButton" if key == "import_config" else "Secondary.TButton")
            button.pack(side="left", padx=(0, 8))
            Tooltip(button, TOOLTIPS[key])

        recent = ttk.LabelFrame(panel, text="最近项目", padding=12, style="Card.TLabelframe")
        recent.pack(fill="both", expand=True, pady=(0, 12))
        self.start_recent_tree = self._tree_with_scrollbars(
            recent,
            ("name", "source", "updated", "status"),
            ("项目名称", "来源 Config Excel", "最近修改", "项目状态"),
            (220, 390, 190, 140),
        )
        self.start_recent_tree.bind("<Double-1>", lambda _event: self._open_selected_recent(self.start_recent_tree))
        self._populate_recent_tree(self.start_recent_tree)
        recent_actions = ttk.Frame(recent, style="Panel.TFrame")
        recent_actions.pack(fill="x", pady=(6, 0))
        ttk.Button(
            recent_actions,
            text=TEXT["delete_project"],
            command=lambda: self._delete_selected_project(self.start_recent_tree),
        ).pack(side="right")
        ttk.Button(
            recent_actions,
            text=TEXT["remove_recent"],
            command=lambda: self._remove_selected_recent(self.start_recent_tree),
        ).pack(side="right", padx=(0, 8))
        ttk.Button(
            recent_actions,
            text="打开项目",
            command=lambda: self._open_selected_recent(self.start_recent_tree),
            style="Primary.TButton",
        ).pack(side="right", padx=(0, 8))

        guide = ttk.LabelFrame(panel, text="工程师工作流程", padding=12, style="Card.TLabelframe")
        guide.pack(fill="x")
        ttk.Label(
            guide,
            text="① 导入或新建项目  →  ② 检查输入文件  →  ③ 修改并保存项目  →  ④ 选择 T2B 模板  →  ⑤ 编辑/管理工作模板（UI-3）  →  ⑥ 生成文件（UI-4）  →  ⑦ 查看结果（UI-4）",
            style="Panel.TLabel",
            wraplength=1050,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(panel, text="本阶段不会执行真实 T2B、LSF 或 C_comp_view。", foreground=MUTED).pack(anchor="w", pady=(12, 0))
        ttk.Label(
            panel,
            text=f"软件版本 {self.metadata.version} · Commit {self.metadata.short_commit} · 平台 {self.metadata.platform}",
            foreground=MUTED,
        ).pack(anchor="w", pady=(6, 0))

    def _show_main(self) -> None:
        self._clear()
        self._build_topbar()
        self._build_bottom()
        body = ttk.Panedwindow(self._content, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=(4, 6))
        left = ttk.Frame(body, padding=8, style="Panel.TFrame")
        right = ttk.Frame(body, padding=(8, 4))
        body.add(left, weight=1)
        body.add(right, weight=4)
        self.main_paned = body
        self._build_tree(left)
        self._build_tabs(right)
        self._refresh_all()

    def _build_topbar(self) -> None:
        bar = ttk.Frame(self._content, padding=(12, 9), style="Toolbar.TFrame")
        bar.pack(fill="x")
        home = ttk.Button(bar, text=TEXT["home"], command=self._go_home, style="Secondary.TButton")
        home.pack(side="left", padx=(0, 10))
        Tooltip(home, TOOLTIPS["home"])
        self.project_label = ttk.Label(bar, text="", style="Panel.TLabel", font=(self.ui_font, 11, "bold"))
        self.project_label.pack(side="left")
        self.state_label = ttk.Label(bar, text="", style="StatusSaved.TLabel", background=PANEL)
        self.state_label.pack(side="left", padx=16)
        for key, command, primary in (
            ("about", self._show_about, False),
            ("advanced", self._open_advanced_settings, False),
            ("save_config", self._save, True),
            ("close_project", self._close_current_project, False),
            ("open_project", self._open_project, False),
            ("import_config", self._import_excel, False),
            ("new_project", self._new_project, False),
        ):
            button = ttk.Button(bar, text=TEXT[key], command=command, style="Primary.TButton" if primary else "Secondary.TButton")
            button.pack(side="right", padx=3)
            if key in TOOLTIPS:
                Tooltip(button, TOOLTIPS[key])

    def _build_bottom(self) -> None:
        bar = ttk.Frame(self._content, padding=(12, 8), style="Toolbar.TFrame")
        bar.pack(side="bottom", fill="x")
        self.status_message = ttk.Label(bar, text="就绪", style="Panel.TLabel")
        self.status_message.pack(side="left", fill="x", expand=True)
        ttk.Label(bar, text="当前生成状态：未生成（生成功能将在 UI-4 开放）", style="Panel.TLabel", foreground=MUTED).pack(side="right")

    def _build_tree(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="IO Top / Case 任务树", style="Panel.TLabel", font=(self.ui_font, 10, "bold")).pack(anchor="w")
        search = ttk.Frame(parent, style="Panel.TFrame")
        search.pack(fill="x", pady=(8, 5))
        ttk.Label(search, text="搜索", style="Panel.TLabel").pack(side="left")
        self.tree_search_var = tk.StringVar()
        entry = ttk.Entry(search, textvariable=self.tree_search_var)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.tree_search_var.trace_add("write", lambda *_args: self._refresh_tree())
        self.tree_summary = ttk.Label(parent, text="", style="Panel.TLabel", foreground=MUTED)
        self.tree_summary.pack(anchor="w", pady=(0, 5))

        holder = ttk.Frame(parent, style="Panel.TFrame")
        holder.pack(fill="both", expand=True)
        self.case_tree = ttk.Treeview(holder, columns=("kind", "state"), show="tree headings", selectmode="browse")
        self.case_tree.heading("#0", text="IO Top / 方向 / Ron")
        self.case_tree.heading("kind", text="类型")
        self.case_tree.heading("state", text="状态")
        self.case_tree.column("#0", width=230, minwidth=150, stretch=True)
        self.case_tree.column("kind", width=70, minwidth=55, stretch=False)
        self.case_tree.column("state", width=105, minwidth=80, stretch=False)
        ybar = ttk.Scrollbar(holder, orient="vertical", command=self.case_tree.yview)
        xbar = ttk.Scrollbar(holder, orient="horizontal", command=self.case_tree.xview)
        self.case_tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.case_tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.case_tree.bind("<<TreeviewSelect>>", self._tree_selected)
        ttk.Label(
            parent,
            text="层级：IO Top → DRV/RCV → Ron\n任务勾选与生成将在 UI-4 开放",
            style="Panel.TLabel",
            foreground=MUTED,
        ).pack(anchor="w", pady=(6, 0))

    def _build_tabs(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        self.home_tab = ttk.Frame(self.notebook, padding=8)
        self.config_tab = ttk.Frame(self.notebook)
        self.files_tab = ttk.Frame(self.notebook, padding=8)
        self.t2b_tab = ttk.Frame(self.notebook, padding=8)
        self.results_tab = ttk.Frame(self.notebook, padding=24)
        self.monitor_tab = ttk.Frame(self.notebook, padding=24)
        self.log_tab = ttk.Frame(self.notebook, padding=8)
        for tab, title in (
            (self.home_tab, TEXT["home"]),
            (self.config_tab, TEXT["config"]),
            (self.files_tab, TEXT["input_files"]),
            (self.t2b_tab, TEXT["t2b_templates"]),
            (self.results_tab, TEXT["results"]),
            (self.monitor_tab, TEXT["monitor"]),
            (self.log_tab, TEXT["log"]),
        ):
            self.notebook.add(tab, text=title)
        home_header = ttk.Frame(self.home_tab)
        home_header.pack(fill="x", pady=(0, 8))
        ttk.Label(home_header, text="项目总览", style="Title.TLabel").pack(side="left")
        input_button = ttk.Button(home_header, text=TEXT["input_check"], command=self._go_input_files, style="Primary.TButton")
        input_button.pack(side="right")
        Tooltip(input_button, TOOLTIPS["input_check"])
        self.overview_text = self._text_with_scrollbars(self.home_tab, wrap="word", readonly=True)
        self._build_config_tab()
        self._build_files_tab()
        self._build_t2b_tab()
        ttk.Label(
            self.results_tab,
            text="生成结果将在 UI-4 开放。当前所有 Case 的生成状态保持“未生成”，不会根据 Config 存在而显示通过。",
            justify="left",
            wraplength=800,
        ).pack(anchor="nw")
        ttk.Label(
            self.monitor_tab,
            text="任务监控将在 UI-4 开放。当前不会创建等待中、生成中或通过等虚假任务状态。\n本页不会执行真实 T2B、LSF 或仿真。",
            justify="left",
        ).pack(anchor="nw")
        self.log_text = self._text_with_scrollbars(self.log_tab, wrap="word", readonly=True)

    def _text_with_scrollbars(self, parent: tk.Misc, wrap: str = "none", readonly: bool = False) -> tk.Text:
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        text = tk.Text(holder, wrap=wrap, font=("TkFixedFont", 10) if wrap == "none" else (self.ui_font, 10), padx=8, pady=8)
        ybar = ttk.Scrollbar(holder, orient="vertical", command=text.yview)
        xbar = ttk.Scrollbar(holder, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        text.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        if wrap == "none":
            xbar.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        if readonly:
            text.configure(state="disabled")
        return text

    def _build_config_tab(self) -> None:
        scrolling = ScrollableFrame(self.config_tab)
        scrolling.pack(fill="both", expand=True)
        self.config_scroll = scrolling
        parent = scrolling.body

        ttk.Label(parent, text="管理当前 IO Top 的 Ron、Voltage、Timing 及其他生成参数。", foreground=MUTED).pack(fill="x", pady=(0, 8))
        paths = ttk.LabelFrame(parent, text="第 1 节 — 项目与路径", padding=10, style="Card.TLabelframe")
        paths.pack(fill="x", pady=(0, 8))
        for row, name in enumerate(("model", "msi", "spf")):
            ttk.Label(paths, text=f"{name.upper()} Root", style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            variable = tk.StringVar()
            field = PathField(paths, variable, lambda key=name: self._root_changed(key), f"选择 {name.upper()} Root")
            field.grid(row=row, column=1, sticky="ew", pady=4)
            self._root_vars[name] = variable
        paths.columnconfigure(1, weight=1)
        ttk.Label(
            paths,
            text="T2B 模板通过“T2B 模板”页面进行选择。",
            style="Panel.TLabel",
            foreground=MUTED,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(7, 0))

        summary = ttk.LabelFrame(parent, text="第 3.1 / 3.2 节 — Corner / Voltage（只读预览）", padding=10, style="Card.TLabelframe")
        summary.pack(fill="x", pady=(0, 8))
        summary_holder = ttk.Frame(summary, style="Panel.TFrame")
        summary_holder.pack(fill="x")
        self.corner_summary = ttk.Treeview(summary_holder, columns=("max", "typ", "min"), show="tree headings", height=7)
        self.corner_summary.heading("#0", text="参数")
        for name in ("max", "typ", "min"):
            self.corner_summary.heading(name, text=name.upper())
            self.corner_summary.column(name, width=120, anchor="center")
        self.corner_summary.column("#0", width=210)
        ybar = ttk.Scrollbar(summary_holder, orient="vertical", command=self.corner_summary.yview)
        xbar = ttk.Scrollbar(summary_holder, orient="horizontal", command=self.corner_summary.xview)
        self.corner_summary.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.corner_summary.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        summary_holder.columnconfigure(0, weight=1)

        module = ttk.LabelFrame(parent, text="第 2 节 — 模块 / 方向 / Ron / T2B 动态参数", padding=10, style="Card.TLabelframe")
        module.pack(fill="x", pady=(0, 8))
        fields = (
            ("name", "模块", "readonly"),
            ("generate_type", "生成类型", "combo"),
            ("impedances", "Ron（逗号分隔）", "entry"),
            ("ibis_io_voltage_domain", "IBIS IO Voltage Domain", "domain"),
            ("ibis_vih_voltage_domain", "IBIS VIH Voltage Domain", "domain"),
            ("tr.MAX", "Tr MAX", "entry"),
            ("tr.TYP", "Tr TYP", "entry"),
            ("tr.MIN", "Tr MIN", "entry"),
            ("tf.MAX", "Tf MAX", "entry"),
            ("tf.TYP", "Tf TYP", "entry"),
            ("tf.MIN", "Tf MIN", "entry"),
        )
        self._module_widgets: dict[str, tuple[tk.Widget, str]] = {}
        for row, (key, label, kind) in enumerate(fields):
            ttk.Label(module, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            variable = tk.StringVar()
            if kind == "combo":
                widget = ttk.Combobox(module, textvariable=variable, values=("DRV", "RCV", "BOTH"), state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda _event, field=key: self._module_changed(field, refresh_tree=True))
            elif kind == "domain":
                widget = ttk.Combobox(module, textvariable=variable, state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda _event, field=key: self._module_changed(field))
            else:
                widget = ttk.Entry(module, textvariable=variable, state="readonly" if kind == "readonly" else "normal")
                if kind != "readonly":
                    widget.bind("<KeyRelease>", lambda _event, field=key: self._module_changed(field))
                    if key == "impedances":
                        widget.bind("<FocusOut>", lambda _event: self._refresh_tree())
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            self._module_vars[key] = variable
            self._module_widgets[key] = (widget, kind)
            if kind == "domain":
                setattr(widget, "_ibis_domain_widget", True)
        module.columnconfigure(1, weight=1)
        self.module_notice = ttk.Label(
            module,
            text="请选择左侧 IO Top。DRV+RCV 应使用单行生成类型=BOTH；完整第 1–10 节编辑由 UI-2 实现。",
            style="Panel.TLabel",
            foreground=MUTED,
        )
        self.module_notice.grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))

        future = ttk.LabelFrame(parent, text="第 3.3–10 节 — 扩展配置分区", padding=10, style="Card.TLabelframe")
        future.pack(fill="x", pady=(0, 8))
        rows = (
            ("3.3 Calibration", "只读保留；UI-2 编辑"),
            ("3.4 SPF Match", "输入文件页提供只读匹配预览"),
            ("4 仿真选项", "只读保留；UI-2 编辑"),
            ("5 IBIS Pin Mapping", "只读保留；UI-2 编辑"),
            ("6 CKT Append", "只读保留；UI-2 编辑"),
            ("7 T2B Template Mapping", "在“T2B 模板”页选择并随项目保存"),
            ("8 Signal Override", "只读保留；UI-2 编辑"),
            ("9 MSI Attribute Override", "只读保留；UI-2 编辑"),
            ("10 MSI Mapping", "输入文件页提供只读来源预览"),
        )
        for row, (name, state) in enumerate(rows):
            ttk.Label(future, text=name, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(future, text=state, style="Panel.TLabel", foreground=MUTED).grid(row=row, column=1, sticky="w", padx=(20, 0), pady=2)

    def _build_t2b_tab(self) -> None:
        header = ttk.LabelFrame(self.t2b_tab, text="模块级 T2B Template Mapping", padding=10, style="Card.TLabelframe")
        header.pack(fill="x", pady=(0, 8))
        self.template_module_label = ttk.Label(header, text="当前模块：未选择")
        self.template_module_label.grid(row=0, column=0, sticky="w")
        self.template_topology_label = ttk.Label(header, text="拓扑：—")
        self.template_topology_label.grid(row=0, column=1, sticky="w", padx=(24, 0))
        self.template_generate_label = ttk.Label(header, text="生成类型：—")
        self.template_generate_label.grid(row=0, column=2, sticky="w", padx=(24, 0))
        self.template_root_label = ttk.Label(header, text="", foreground=MUTED)
        self.template_root_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))

        self.template_rows: dict[str, ttk.Frame] = {}
        for row_index, direction in enumerate(("DRV", "RCV"), 2):
            row = ttk.Frame(header, style="Panel.TFrame")
            row.grid(row=row_index, column=0, columnspan=3, sticky="ew", pady=(8, 0))
            self.template_rows[direction] = row
            ttk.Label(row, text=f"{direction} T2B 模板：", style="Panel.TLabel", width=17).pack(side="left")
            variable = tk.StringVar()
            self._template_vars[direction] = variable
            combo = ttk.Combobox(row, textvariable=variable, state="readonly", width=38)
            combo.pack(side="left", fill="x", expand=True)
            combo.bind("<<ComboboxSelected>>", lambda _event, item=direction: self._template_changed(item))
            setattr(self, f"template_{direction.casefold()}_combo", combo)
            source_label = ttk.Label(row, text="", foreground=MUTED, width=22)
            source_label.pack(side="left", padx=(10, 4))
            setattr(self, f"template_{direction.casefold()}_source", source_label)
            ttk.Button(row, text=f"查看 {direction} 模板", command=lambda item=direction: self._preview_direction_template(item)).pack(side="right")
        header.columnconfigure(0, weight=1)

        preview = ttk.LabelFrame(self.t2b_tab, text="只读 Template Preview", padding=6, style="Card.TLabelframe")
        preview.pack(fill="both", expand=True)
        self.template_text = self._text_with_scrollbars(preview, wrap="none", readonly=True)
        ttk.Label(
            self.t2b_tab,
            text="当前选择按 Module + Direction 保存到 ProjectStore。完整工作模板编辑、历史和模板库将在 UI-3 实现。",
            foreground=MUTED,
        ).pack(fill="x", pady=(6, 0))

    def _build_files_tab(self) -> None:
        ttk.Label(
            self.files_tab,
            text="检查各模块使用的 MSI 信号表、SPF 网表和模型文件。匹配成功不代表 IBIS 已生成通过。",
            foreground=MUTED,
        ).pack(fill="x", pady=(0, 8))
        toolbar = ttk.Frame(self.files_tab)
        toolbar.pack(fill="x", pady=(0, 6))
        refresh = ttk.Button(toolbar, text="刷新输入检查", style="Primary.TButton", command=self._refresh_sources)
        refresh.pack(side="left")
        Tooltip(refresh, "刷新输入检查：重新扫描 MSI、SPF 和 Model Root，不修改任何源文件。")
        self.source_summary = ttk.Label(toolbar, text="", foreground=MUTED)
        self.source_summary.pack(side="left", padx=12)
        notebook = ttk.Notebook(self.files_tab)
        notebook.pack(fill="both", expand=True)
        self.input_notebook = notebook
        msi_tab = ttk.Frame(notebook, padding=8)
        spf_tab = ttk.Frame(notebook, padding=8)
        model_tab = ttk.Frame(notebook, padding=8)
        notebook.add(msi_tab, text="MSI 信号表")
        notebook.add(spf_tab, text="SPF 网表")
        notebook.add(model_tab, text="Model Library")

        msi_head = ttk.Frame(msi_tab)
        msi_head.pack(fill="x", pady=(0, 6))
        self.msi_summary = ttk.Label(msi_head, text="")
        self.msi_summary.pack(side="left", fill="x", expand=True)
        ttk.Button(msi_head, text="查看 MSI 目录", command=lambda: self._open_root_directory("msi")).pack(side="right", padx=3)
        self.msi_details_button = ttk.Button(msi_head, text="查看扫描详情", command=self._toggle_msi_details)
        self.msi_details_button.pack(side="right", padx=3)
        self.msi_tree = self._tree_with_scrollbars(
            msi_tab,
            ("module", "file", "sheet", "pin", "status", "message"),
            ("IO Top", "MSI 文件", "Sheet", "PIN_NAME Column", "状态", "说明"),
            (150, 210, 150, 160, 90, 320),
        )
        self.msi_detail_holder = ttk.LabelFrame(msi_tab, text="Excel / Sheet 扫描详情", padding=6)
        self.msi_detail_tree = self._tree_with_scrollbars(
            self.msi_detail_holder,
            ("file", "sheet", "pin", "status", "path"),
            ("Excel 文件", "Sheet", "PIN_NAME 候选列", "状态", "完整路径 / 说明"),
            (210, 170, 190, 90, 460),
        )
        self._msi_details_visible = False

        spf_head = ttk.Frame(spf_tab)
        spf_head.pack(fill="x", pady=(0, 6))
        self.spf_summary = ttk.Label(spf_head, text="")
        self.spf_summary.pack(side="left", fill="x", expand=True)
        ttk.Button(spf_head, text="查看 SPF 目录", command=lambda: self._open_root_directory("spf")).pack(side="right", padx=3)
        self.spf_tree = self._tree_with_scrollbars(
            spf_tab,
            ("module", "corner", "status", "top", "pins", "path", "message"),
            ("IO Top", "Corner", "状态", "TOP_SUBCKT", "Pin 数量", "SPF 文件", "说明"),
            (150, 70, 80, 170, 55, 400, 300),
        )

        model_head = ttk.Frame(model_tab)
        model_head.pack(fill="x", pady=(0, 6))
        self.model_summary = ttk.Label(model_head, text="")
        self.model_summary.pack(side="left", fill="x", expand=True)
        ttk.Button(model_head, text="查看 Model 目录", command=lambda: self._open_root_directory("model")).pack(side="right", padx=3)
        self.model_tree = self._tree_with_scrollbars(
            model_tab,
            ("file", "type", "status", "path", "message"),
            ("必需模型文件", "SPICE 类型", "状态", "完整路径", "说明"),
            (180, 120, 90, 500, 240),
        )
        ttk.Label(
            model_tab,
            text="这里只检查必需模型文件是否存在；未执行完整仿真或电气模型校验。",
            foreground=WARNING,
        ).pack(fill="x", pady=(6, 0))

    def _msi_tree_with_scrollbars(self, parent: tk.Misc) -> ttk.Treeview:
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        columns = ("sheet", "pin", "status", "message")
        tree = ttk.Treeview(holder, columns=columns, show="tree headings", selectmode="browse")
        tree.heading("#0", text="MSI File / Module")
        tree.column("#0", width=230, minwidth=130, stretch=True)
        for column, heading, width in zip(columns, ("Sheet", "Pin Name Column", "状态", "说明"), (170, 160, 80, 360)):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=50, stretch=column == "message")
        ybar = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(holder, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        tree.tag_configure("PASS", background="#e8f7ef")
        tree.tag_configure("WARNING", background="#fff4e8")
        tree.tag_configure("ERROR", background="#fff0f0")
        return tree

    def _tree_with_scrollbars(self, parent: tk.Misc, columns: tuple[str, ...], headings: tuple[str, ...], widths: tuple[int, ...]) -> ttk.Treeview:
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        tree = ttk.Treeview(holder, columns=columns, show="headings", selectmode="browse")
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=50, stretch=column in {"file", "path", "message"})
        ybar = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(holder, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        tree.tag_configure("PASS", background="#e8f7ef")
        tree.tag_configure("WARNING", background="#fff4e8")
        tree.tag_configure("ERROR", background="#fff0f0")
        return tree

    def _refresh_all(self) -> None:
        self._refresh_status()
        self._refresh_tree()
        self._refresh_overview()
        self._refresh_config()
        self._refresh_t2b()
        self._refresh_sources()

    def _refresh_status(self) -> None:
        project = self.controller.project
        if not project:
            return
        self.project_label.configure(text=f"当前项目：{project.name}")
        state = self.controller.config_status or ConfigStatus.UNMODIFIED
        style = "StatusError.TLabel" if state == ConfigStatus.ERROR else ("StatusDirty.TLabel" if state == ConfigStatus.DIRTY else "StatusSaved.TLabel")
        self.state_label.configure(text=status_label(state), style=style, background=PANEL)

    def _refresh_tree(self) -> None:
        if not hasattr(self, "case_tree"):
            return
        raw_tree = self.controller.case_tree()
        modules, cases = case_tree_counts(raw_tree)
        visible = filter_case_tree(raw_tree, self.tree_search_var.get())
        self.tree_summary.configure(text=f"模块 {modules} · Case {cases} · 当前显示 {len(visible)} 个模块")
        self.case_tree.delete(*self.case_tree.get_children())
        self._tree_modules.clear()
        first_module_id: str | None = None
        for module_index, module in enumerate(visible):
            module_id = f"module:{module_index}"
            first_module_id = first_module_id or module_id
            self.case_tree.insert("", "end", module_id, text=str(module["module"]), values=("IO Top", "已配置"), open=True)
            self._tree_modules[module_id] = str(module["module"])
            for direction_index, direction in enumerate(module["directions"]):
                direction_id = f"{module_id}:direction:{direction_index}"
                self.case_tree.insert(module_id, "end", direction_id, text=str(direction["direction"]), values=("方向", "已配置"), open=True)
                self._tree_modules[direction_id] = str(module["module"])
                for ron_index, ron in enumerate(direction["rons"]):
                    case_id = f"{direction_id}:ron:{ron_index}"
                    self.case_tree.insert(direction_id, "end", case_id, text=f"{ron}Ω", values=("Ron", status_label(GenerationStatus.NOT_GENERATED)))
                    self._tree_modules[case_id] = str(module["module"])
        visible_names = {str(item["module"]) for item in visible}
        if self._selected_module not in visible_names:
            self._selected_module = self._tree_modules.get(first_module_id) if first_module_id else None
        if self._selected_module:
            target = next((item for item, name in self._tree_modules.items() if name == self._selected_module and item.count(":") == 1), None)
            if target:
                self.case_tree.selection_set(target)
                self.case_tree.focus(target)

    def _refresh_overview(self) -> None:
        project = self.controller.project
        config = self.controller.active_config
        source = project.source_excel.path if project and project.source_excel else "无（UI Mode）"
        try:
            template_root = self.controller.effective_template_root()
            template_source = "外部覆盖" if self.controller.template_override().strip() else "软件内置"
        except UIProjectError as exc:
            template_root = Path(f"错误 [{exc.code}] {exc}")
            template_source = "不可用"
        msi = preview_msi(config)
        spf = preview_spf(config)
        models = preview_models(config)
        overview = build_project_overview(config, self.controller.config_status or ConfigStatus.UNMODIFIED, msi, spf, models)
        steps = (
            ("① 导入或新建项目", True, ""),
            ("② 检查输入文件", overview.inputs_ready, ""),
            ("③ 修改并保存项目", self.controller.config_status == ConfigStatus.SAVED, ""),
            ("④ 选择 T2B 模板", True, "本阶段已开放"),
            ("⑤ 编辑/管理工作模板", False, "暂未开放（UI-3）"),
            ("⑥ 生成文件", False, "暂未开放（UI-4）"),
            ("⑦ 查看结果", False, "暂未开放（UI-4）"),
        )
        lines = [
            f"项目名称：{project.name if project else ''}",
            f"项目 ID：{project.project_id if project else ''}",
            f"项目模式：{'Excel 导入' if project and project.mode == 'excel' else 'UI 新建'}",
            f"来源 Config Excel（只读）：{source}",
            f"配置状态：{overview.config_status}",
            "",
            "项目概要",
            f"  IO Top：{overview.io_top_count}",
            f"  DRV/RCV 分支：{overview.branch_count}",
            f"  Case：{overview.case_count}（生成状态均为“未生成”）",
            f"  MSI 匹配：{overview.msi_matched}/{overview.msi_total}",
            f"  SPF Corner 匹配：{overview.spf_matched}/{overview.spf_total}",
            f"  Model 必需文件：{overview.model_files_found}/{overview.model_files_total}（仅存在性检查）",
            "",
            f"当前工作阶段：{overview.current_stage}",
            f"推荐下一步：{overview.recommended_action}",
            "",
            "工作流程",
            *[f"  {'✓' if complete else '○'} {name}{f' — {note}' if note else ''}" for name, complete, note in steps],
            "",
            "输入路径",
            *[f"  {name.upper()} Root：{config.get('roots', {}).get(name, '') or '(未设置)'}" for name in ("model", "msi", "spf")],
            f"  T2B 母模板（{template_source}）：{template_root}",
            "",
            f"Voltage Domain：{', '.join(config.get('voltage_order', [])) or '(未设置)'}",
            "",
            "阶段边界：Excel 双向写回和 MSI Merge 属于 UI-2；T2B 工作模板编辑与历史库属于 UI-3；生成与监控属于 UI-4。",
        ]
        invalid_roots = self.controller.invalid_roots()
        if invalid_roots:
            lines.extend(["", "警告：以下 Root 在当前电脑上无效，请修正后点击“保存项目”：", *[f"  {name.upper()}：{value or '(未设置)'}" for name, value in invalid_roots.items()]])
        self._set_readonly_text(self.overview_text, "\n".join(lines))

    @staticmethod
    def _set_readonly_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _refresh_config(self) -> None:
        config = self.controller.active_config
        self._loading_form = True
        try:
            for name, variable in self._root_vars.items():
                variable.set(config.get("roots", {}).get(name, ""))
            self.corner_summary.delete(*self.corner_summary.get_children())
            corners = config.get("corners", {})
            self.corner_summary.insert("", "end", text="Process", values=tuple(corners.get(name, {}).get("process", "") for name in ("MAX", "TYP", "MIN")))
            self.corner_summary.insert("", "end", text="Temperature", values=tuple(corners.get(name, {}).get("temperature", "") for name in ("MAX", "TYP", "MIN")))
            for domain in config.get("voltage_order", []):
                self.corner_summary.insert("", "end", text=domain, values=tuple(corners.get(name, {}).get("voltages", {}).get(domain, "") for name in ("MAX", "TYP", "MIN")))
            for widget, _kind in self._module_widgets.values():
                if getattr(widget, "_ibis_domain_widget", False):
                    widget.configure(values=tuple(config.get("voltage_order", [])))
            if self._selected_module:
                self._load_module_form(self._selected_module)
            else:
                self._clear_module_form()
        finally:
            self._loading_form = False
        if self.controller.invalid_roots():
            self.status_message.configure(text="警告：Model/MSI/SPF Root 在当前电脑上失效，请重新指定后保存项目。", foreground=WARNING)

    def _clear_module_form(self) -> None:
        for variable in self._module_vars.values():
            variable.set("")
        for widget, _kind in self._module_widgets.values():
            widget.configure(state="disabled")

    def _load_module_form(self, name: str) -> None:
        module = self.controller.module(name)
        for widget, kind in self._module_widgets.values():
            widget.configure(state="readonly" if kind in {"readonly", "combo", "domain"} else "normal")
        self._module_vars["name"].set(module["name"])
        self._module_vars["generate_type"].set(module["generate_type"])
        self._module_vars["impedances"].set(", ".join(str(value) for value in module["impedances"]))
        self._module_vars["ibis_io_voltage_domain"].set(module["ibis_io_voltage_domain"])
        self._module_vars["ibis_vih_voltage_domain"].set(module["ibis_vih_voltage_domain"])
        for family in ("tr", "tf"):
            for corner in ("MAX", "TYP", "MIN"):
                self._module_vars[f"{family}.{corner}"].set(module[family][corner])

    def _refresh_t2b(self) -> None:
        config = self.controller.active_config
        try:
            templates = self.controller.templates.list_templates(config)
            source = "外部覆盖" if self.controller.templates.using_override(config) else "软件内置只读资源"
            self.template_root_label.configure(text=f"模板 Root：{templates[0].path.parent}（{source}）", foreground=PASS)
            if not self._selected_module:
                self.template_module_label.configure(text="当前模块：未选择")
                self.template_topology_label.configure(text="拓扑：—")
                self.template_generate_label.configure(text="生成类型：—")
                for row in self.template_rows.values():
                    row.grid_remove()
                self._set_readonly_text(self.template_text, "请从左侧任务树选择一个 IO Top。")
                return
            module = self.controller.module(self._selected_module)
            selection = self.controller.template_selection(self._selected_module)
            generate_type = str(module.get("generate_type", "")).upper()
            self.template_module_label.configure(text=f"当前模块：{self._selected_module}")
            self.template_topology_label.configure(text=f"拓扑：{selection.get('topology') or '无法确定'}")
            self.template_generate_label.configure(text=f"生成类型：{generate_type}")
            active_directions = {"DRV", "RCV"} if generate_type == "BOTH" else {generate_type}
            first_active: str | None = None
            for direction in ("DRV", "RCV"):
                row = self.template_rows[direction]
                if direction not in active_directions:
                    row.grid_remove()
                    continue
                row.grid()
                first_active = first_active or direction
                summary = self.controller.templates.selection_summary(config, self._selected_module, direction)
                auto_label = f"自动（{summary['display_name']}）" if summary["template_id"] else "自动（无法自动匹配）"
                display_ids: dict[str, str | None] = {auto_label: None}
                for item in self.controller.templates.selectable(direction):
                    display_ids[item.display_name] = item.template_id
                self._template_display_ids[direction] = display_ids
                combo = getattr(self, f"template_{direction.casefold()}_combo")
                combo.configure(values=tuple(display_ids))
                choice = selection[f"{direction.casefold()}_template"]
                selected_id = choice.get("template_id") if choice.get("mode") == "manual" else None
                selected_display = next((label for label, value in display_ids.items() if value == selected_id), auto_label)
                self._template_vars[direction].set(selected_display)
                source_label = getattr(self, f"template_{direction.casefold()}_source")
                source_label.configure(text=f"来源：{summary['source']}", foreground=PASS if summary["template_id"] else FAIL)
                Tooltip(combo, f"当前有效模板：{summary['path'] or '无法自动匹配'}")
            if first_active:
                self._preview_direction_template(first_active)
        except UIProjectError as exc:
            self.template_root_label.configure(text=f"错误 [{exc.code}]：{exc}", foreground=FAIL)
            self._set_readonly_text(self.template_text, f"错误 [{exc.code}]：{exc}")

    def _template_changed(self, direction: str) -> None:
        if self._loading_form or not self._selected_module:
            return
        try:
            display = self._template_vars[direction].get()
            template_id = self._template_display_ids.get(direction, {}).get(display)
            self.controller.update_template(self._selected_module, direction, template_id)
            self._refresh_status()
            self._refresh_overview()
            self._refresh_t2b()
        except UIProjectError as exc:
            self._show_error(exc)

    def _preview_direction_template(self, direction: str) -> None:
        if not self._selected_module:
            return
        try:
            summary = self.controller.templates.selection_summary(self.controller.active_config, self._selected_module, direction)
            if not summary["template_id"]:
                content = f"错误 [PROJECT_TEMPLATE_AUTO_UNRESOLVED]：{self._selected_module} {direction} 无法自动匹配，请手工选择。"
            else:
                content = self.controller.templates.read_id(self.controller.active_config, summary["template_id"])
        except UIProjectError as exc:
            content = f"错误 [{exc.code}]：{exc}"
        self._set_readonly_text(self.template_text, content)

    def _refresh_sources(self) -> None:
        config = self.controller.active_config
        self.msi_tree.delete(*self.msi_tree.get_children())
        self.msi_detail_tree.delete(*self.msi_detail_tree.get_children())
        self.spf_tree.delete(*self.spf_tree.get_children())
        self.model_tree.delete(*self.model_tree.get_children())
        msi = preview_msi(config)
        for item in msi.modules:
            display_status = "已匹配" if item.status == "PASS" else "匹配失败"
            self.msi_tree.insert(
                "",
                "end",
                values=(item.module, item.file, item.sheet, item.pin_column, display_status, item.message),
                tags=(item.status,),
            )
        for item in msi.sheets:
            internal = "ERROR" if item.error else "PASS"
            self.msi_detail_tree.insert(
                "",
                "end",
                values=(item.file.name, item.sheet, ", ".join(item.pin_columns), "错误" if item.error else "已发现", item.error or str(item.file)),
                tags=(internal,),
            )
        spf = preview_spf(config)
        for item in spf.matches:
            display_status = "匹配失败" if item.status == "ERROR" else ("警告" if item.status == "WARNING" else "已匹配")
            self.spf_tree.insert("", "end", values=(item.module, item.corner, display_status, item.top_subckt, item.pin_count or "", item.path, item.message), tags=(item.status,))
        models = preview_models(config)
        for item in models.files:
            internal = "PASS" if item.status == "FOUND" else "ERROR"
            self.model_tree.insert(
                "",
                "end",
                values=(item.filename, models.spice_type, "已发现" if item.status == "FOUND" else "错误", item.path, item.message),
                tags=(internal,),
            )
        msi_errors = sum(item.status == "ERROR" for item in msi.modules)
        spf_errors = sum(item.status == "ERROR" for item in spf.matches)
        model_errors = sum(item.status == "ERROR" for item in models.files)
        msi_matches = len(msi.modules) - msi_errors
        spf_matches = len(spf.matches) - spf_errors
        model_found = len(models.files) - model_errors
        self.msi_summary.configure(
            text=f"MSI Root：{msi.root}    Excel {len(msi.files)}    Sheet {len(msi.sheets)}    IO Top {len(msi.modules)}    已匹配 {msi_matches} / 失败 {msi_errors}",
            foreground=FAIL if msi_errors else PASS,
        )
        self.spf_summary.configure(
            text=f"SPF Root：{spf.root}    Corner {len(spf.matches)}    已匹配 {spf_matches} / 失败 {spf_errors}",
            foreground=FAIL if spf_errors else PASS,
        )
        self.model_summary.configure(
            text=f"Model Root：{models.root}    SPICE 类型 {models.spice_type}    必需文件 {model_found}/{len(models.files)}",
            foreground=FAIL if model_errors else PASS,
        )
        self.source_summary.configure(
            text=f"MSI 匹配失败 {msi_errors} · SPF 匹配失败 {spf_errors} · Model 缺失 {model_errors}",
            foreground=FAIL if msi_errors or spf_errors or model_errors else PASS,
        )
        self._source_reports = (msi, spf, models)

    def _toggle_msi_details(self) -> None:
        if self._msi_details_visible:
            self.msi_detail_holder.pack_forget()
            self.msi_details_button.configure(text="查看扫描详情")
        else:
            self.msi_detail_holder.pack(fill="both", expand=True, pady=(8, 0))
            self.msi_details_button.configure(text="收起扫描详情")
        self._msi_details_visible = not self._msi_details_visible

    def _go_home(self) -> None:
        if hasattr(self, "notebook") and hasattr(self, "home_tab"):
            self._refresh_overview()
            self.notebook.select(self.home_tab)

    def _go_input_files(self) -> None:
        self._refresh_sources()
        self.notebook.select(self.files_tab)

    def _show_about(self) -> None:
        runtime = "Windows EXE" if self.metadata.frozen else "Python 源码"
        messagebox.showinfo(
            "关于软件",
            (
                "IBIS Automation\n\n"
                f"软件版本：{self.metadata.version}\n"
                f"Git Commit：{self.metadata.git_commit}\n"
                f"运行平台：{self.metadata.platform}\n"
                f"运行方式：{runtime}\n"
                f"项目 Workspace：{self.controller.store.workspace}"
            ),
            parent=self,
        )

    def _open_root_directory(self, name: str) -> None:
        raw = str(self.controller.active_config.get("roots", {}).get(name, "")).strip()
        path = Path(raw).expanduser() if raw else Path()
        if not raw or not path.is_dir():
            messagebox.showwarning("目录不可用", f"{name.upper()} Root 不存在，请先在参数配置中重新指定。", parent=self)
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except (OSError, subprocess.SubprocessError) as exc:
            self.clipboard_clear()
            self.clipboard_append(str(path.resolve()))
            messagebox.showwarning("无法打开目录", f"系统无法打开目录，完整路径已复制到剪贴板：\n{path}\n\n{exc}", parent=self)

    def _populate_recent_tree(self, tree: ttk.Treeview) -> None:
        tree.delete(*tree.get_children())
        records = self.controller.recent_projects()
        for record in records:
            tree.insert(
                "",
                "end",
                iid=record.project_id,
                values=(record.name, record.source_excel, record.updated_at or record.last_opened or "未知", record.status),
                tags=("PASS" if record.available else "ERROR",),
            )
        if not records:
            tree.insert("", "end", iid="recent:none", values=("暂无最近项目", "", "", ""))

    def _open_selected_recent(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            return
        if not self._confirm_leave_current():
            return
        project_id = selection[0]
        if project_id == "recent:none":
            return
        try:
            self.controller.load_project(project_id)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._selected_module = None
        self._show_main()

    def _selected_recent_record(self, tree: ttk.Treeview):
        selection = tree.selection()
        if not selection or selection[0] == "recent:none":
            return None
        return next(
            (item for item in self.controller.recent_projects() if item.project_id == selection[0]),
            None,
        )

    def _remove_selected_recent(self, tree: ttk.Treeview, parent: tk.Misc | None = None) -> None:
        record = self._selected_recent_record(tree)
        if record is None:
            return
        if not messagebox.askyesno(
            "从列表移除",
            f"确定从最近项目列表中移除“{record.name}”吗？\n\n"
            "这不会删除项目文件，也不会删除 Config Excel、MSI、SPF 或 Model。",
            parent=parent or self,
        ):
            return
        try:
            self.controller.remove_recent(record.project_id)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._populate_recent_tree(tree)

    def _delete_selected_project(self, tree: ttk.Treeview, parent: tk.Misc | None = None) -> None:
        record = self._selected_recent_record(tree)
        if record is None:
            return
        if not record.available:
            messagebox.showinfo(
                "项目文件不存在",
                "该项目文件已经不存在，可以使用“从列表移除”清理这条记录。",
                parent=parent or self,
            )
            return
        active = self.controller.project
        if active is not None and active.project_id == record.project_id:
            messagebox.showinfo(
                "请先关闭项目",
                "当前项目正在打开，请先关闭项目，再从项目首页删除。",
                parent=parent or self,
            )
            return
        confirmed = messagebox.askyesno(
            "删除项目",
            f"确定删除项目“{record.name}”吗？\n\n"
            "项目会从 IBIS Automation 工作区移入回收区，可用于恢复。\n"
            "不会删除原始 Config Excel、MSI、SPF、Model 等输入文件。",
            parent=parent or self,
        )
        if not confirmed:
            return
        try:
            trash_path = self.controller.delete_project(record.project_id)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._populate_recent_tree(tree)
        messagebox.showinfo(
            "项目已删除",
            f"项目“{record.name}”已移入软件回收区。\n\n回收位置：\n{trash_path}",
            parent=parent or self,
        )

    def _open_project(self) -> None:
        win = tk.Toplevel(self)
        win.title("打开项目")
        win.geometry("980x460")
        win.minsize(760, 360)
        win.transient(self)
        win.grab_set()
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="打开项目", style="Title.TLabel").pack(anchor="w", pady=(0, 10))
        tree = self._tree_with_scrollbars(
            body,
            ("name", "source", "updated", "status"),
            ("项目名称", "来源 Config Excel", "最近修改", "项目状态"),
            (210, 390, 190, 140),
        )
        self._populate_recent_tree(tree)

        def open_selected(_event=None) -> None:
            selection = tree.selection()
            if not selection or selection[0] == "recent:none":
                return
            if not self._confirm_leave_current():
                return
            try:
                self.controller.load_project(selection[0])
            except UIProjectError as exc:
                self._show_error(exc)
                return
            win.destroy()
            self._selected_module = None
            self._show_main()
            self._log(f"打开项目：{self.controller.project.name}")

        tree.bind("<Double-1>", open_selected)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="浏览项目文件……", command=lambda: (win.destroy(), self._browse_project_file())).pack(side="left")
        ttk.Button(
            buttons,
            text=TEXT["remove_recent"],
            command=lambda: self._remove_selected_recent(tree, win),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            buttons,
            text=TEXT["delete_project"],
            command=lambda: self._delete_selected_project(tree, win),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="取消", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="打开", command=open_selected, style="Primary.TButton").pack(side="right", padx=(0, 8))

    def _browse_project_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="浏览项目文件",
            filetypes=(("IBIS 项目配置", "project.json"), ("JSON 文件", "*.json")),
        )
        if not path:
            return
        if not self._confirm_leave_current():
            return
        try:
            self.controller.open_project_file(Path(path))
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._selected_module = None
        self._show_main()
        self._log(f"打开项目：{path}")

    def _tree_selected(self, _event=None) -> None:
        selection = self.case_tree.selection()
        if not selection:
            return
        module = self._tree_modules.get(selection[0])
        if not module:
            return
        changed = module != self._selected_module
        self._selected_module = module
        self._loading_form = True
        try:
            self._load_module_form(module)
        finally:
            self._loading_form = False
        if changed:
            self._refresh_t2b()

    def _module_changed(self, field: str, refresh_tree: bool = False) -> None:
        if self._loading_form or not self._selected_module:
            return
        try:
            self.controller.update_module(self._selected_module, field, self._module_vars[field].get())
        except UIProjectError as exc:
            self.status_message.configure(text=f"错误 [{exc.code}]：{exc}", foreground=FAIL)
            return
        self._refresh_status()
        if refresh_tree:
            self._refresh_tree()
        if field == "generate_type":
            self._refresh_t2b()

    def _root_changed(self, name: str) -> None:
        if self._loading_form:
            return
        try:
            self.controller.update_root(name, self._root_vars[name].get())
            self._refresh_status()
            self._refresh_overview()
            self._refresh_sources()
        except UIProjectError as exc:
            self._show_error(exc)

    def _open_advanced_settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("IBIS Automation — 高级设置")
        win.geometry("860x260")
        win.minsize(700, 230)
        win.transient(self)
        win.grab_set()
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="外部模板资源目录（高级）", font=(self.ui_font, 10, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="仅用于加载自定义模板资源。普通项目无需设置。留空时使用软件内置模板。",
            foreground=MUTED,
        ).pack(anchor="w", pady=(4, 10))
        variable = tk.StringVar(value=self.controller.template_override())
        row = ttk.Frame(body)
        row.pack(fill="x")

        def update_override() -> None:
            try:
                self.controller.update_root("template", variable.get())
                effective.configure(text=f"当前生效：{self.controller.effective_template_root()}", foreground=PASS)
                self._refresh_status()
                self._refresh_t2b()
            except UIProjectError as exc:
                effective.configure(text=f"错误 [{exc.code}]：{exc}", foreground=FAIL)

        PathField(row, variable, update_override, "选择外部模板资源目录（高级）").pack(side="left", fill="x", expand=True)

        def clear_override() -> None:
            variable.set("")
            update_override()

        ttk.Button(row, text="清空并使用内置模板", command=clear_override).pack(side="left", padx=(8, 0))
        effective = ttk.Label(body, text="")
        effective.pack(anchor="w", pady=(12, 0))
        update_override()
        ttk.Button(body, text="关闭", command=win.destroy).pack(side="right", pady=(16, 0))

    def _apply(self) -> None:
        try:
            self.controller.apply_changes()
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._log("高级应用：配置校验通过，草稿已成为生效快照。")
        self.status_message.configure(text="高级应用成功；请点击“保存项目”持久化。", foreground=PASS)
        self._refresh_all()

    def _save(self) -> None:
        try:
            path = self.controller.save_project_draft()
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._log(f"保存项目：{path}（原始 Config Excel 未修改）")
        self.status_message.configure(text=f"项目已保存：{path}；原始 Config Excel 未修改。", foreground=PASS)
        self._refresh_all()

    def _import_excel(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(title="导入 Config Excel", filetypes=(("Excel 工作簿", "*.xlsx"),))
        if not path:
            return
        if not self._confirm_leave_current():
            return
        try:
            self.controller.import_excel(Path(path))
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._selected_module = None
        self._show_main()
        self._log(f"导入 Config Excel：{path}（原文件只读，未修改）")
        invalid_roots = self.controller.invalid_roots()
        if invalid_roots:
            detail = "\n".join(f"{name.upper()}: {value or '(未设置)'}" for name, value in invalid_roots.items())
            warning = f"导入成功，但以下 Root 在当前电脑上无效，请重新指定后保存项目：\n{detail}"
            self._log(f"警告：{warning}")
            messagebox.showwarning("项目路径需要修正", warning, parent=self)

    def _new_project(self) -> None:
        name = simpledialog.askstring("新建项目", "项目名称：", parent=self)
        if name is None:
            return
        if not self._confirm_leave_current():
            return
        try:
            self.controller.new_project(name)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._selected_module = None
        self._show_main()
        self._log("新建项目：已创建内部空项目。完整 Schema 编辑将在 UI-2 实现。")

    def _request_close_action(self) -> str:
        if not self.controller.has_unsaved_changes:
            return "discard"
        result = {"value": "cancel"}
        win = tk.Toplevel(self)
        win.title("关闭项目")
        win.geometry("560x190")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        body = ttk.Frame(win, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="当前项目存在未保存修改，是否保存后关闭？", font=(self.ui_font, 11, "bold")).pack(anchor="w")
        ttk.Label(body, text="关闭项目只会清除当前活动项目，不会删除项目目录、Excel、MSI、SPF 或其他输入文件。", foreground=MUTED, wraplength=510).pack(anchor="w", pady=(8, 18))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")

        def choose(value: str) -> None:
            result["value"] = value
            win.destroy()

        ttk.Button(buttons, text="取消", command=lambda: choose("cancel")).pack(side="right")
        ttk.Button(buttons, text="不保存并关闭", command=lambda: choose("discard")).pack(side="right", padx=8)
        ttk.Button(buttons, text="保存并关闭", command=lambda: choose("save"), style="Primary.TButton").pack(side="right")
        win.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        self.wait_window(win)
        return result["value"]

    def _close_current_project(self) -> None:
        action = self._request_close_action()
        if action == "cancel":
            return
        try:
            if not self.controller.close_project(action):
                return
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._selected_module = None
        self._tree_modules.clear()
        self._show_start()

    def _confirm_leave_current(self) -> bool:
        if not self.controller.project:
            return True
        if self.controller.has_unsaved_changes:
            answer = messagebox.askyesnocancel(
                "有未保存修改",
                "当前项目有未保存修改。\n是：验证并保存项目\n否：放弃修改并继续\n取消：返回当前项目",
                parent=self,
            )
            if answer is None:
                return False
            if answer:
                try:
                    self.controller.save_project_draft()
                except UIProjectError as exc:
                    self._show_error(exc)
                    return False
            else:
                self.controller.discard_draft()
        return True

    def _on_close(self) -> None:
        if self._confirm_leave_current():
            self.destroy()

    def _show_error(self, error: UIProjectError) -> None:
        message = f"错误 [{error.code}]：{error}"
        self._log(message)
        if self.controller.project and hasattr(self, "state_label"):
            self._refresh_status()
        if hasattr(self, "status_message"):
            self.status_message.configure(text=message, foreground=FAIL)
        messagebox.showerror("IBIS Automation", message, parent=self)

    def _log(self, message: str) -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def report_callback_exception(self, exc_type, exc_value, traceback) -> None:
        logging.getLogger(LOGGER_NAME).error("UI 回调异常：%s", exc_value, exc_info=(exc_type, exc_value, traceback))
        messagebox.showerror(
            "IBIS Automation",
            f"错误 [UI_CALLBACK_ERROR]：界面操作异常（{exc_value}）\n详细信息已写入 Workspace 日志。",
            parent=self,
        )
