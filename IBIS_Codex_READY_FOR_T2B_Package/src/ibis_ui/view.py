from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from .controller import ProjectController
from .errors import UIProjectError
from .logging_utils import LOGGER_NAME
from .presentation import case_tree_counts, filter_case_tree
from .runtime import app_metadata
from .source_preview import preview_msi, preview_spf
from .theme import BACKGROUND, FAIL, MUTED, PANEL, PASS, WARNING, apply_modern_style
from .widgets import PathField, ScrollableFrame


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
        self.smoke_error: str | None = None
        self._content = ttk.Frame(self)
        self._content.pack(fill="both", expand=True)
        if self.controller.project:
            self._show_main()
        else:
            self._show_start()
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
            if len(self.template_tree.get_children()) != 5:
                raise RuntimeError("T2B 内置模板列表不完整")
            if not self.msi_tree.get_children() or not self.spf_tree.get_children():
                raise RuntimeError("MSI/SPF 只读预览未加载")
        except Exception as exc:
            self.smoke_error = str(exc)
        finally:
            self.destroy()

    def _clear(self) -> None:
        for child in self._content.winfo_children():
            child.destroy()

    def _show_start(self) -> None:
        self._clear()
        panel = ttk.Frame(self._content, padding=44, style="Panel.TFrame")
        panel.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(panel, text="IBIS Automation", style="Title.TLabel", background=PANEL).pack(pady=(0, 8))
        ttk.Label(panel, text="IBIS 自动化配置工具 · UI Phase 1.1", style="Panel.TLabel").pack(pady=(0, 28))
        ttk.Button(panel, text="Import Excel", style="Primary.TButton", command=self._import_excel, width=32).pack(pady=6)
        ttk.Button(panel, text="New Project", command=self._new_project, width=32).pack(pady=6)
        ttk.Button(panel, text="From Library（UI-3 后续阶段）", state="disabled", width=32).pack(pady=6)
        ttk.Label(panel, text="本阶段不会执行 Generate、真实 T2B、LSF 或 C_comp_view。", style="Panel.TLabel", foreground=MUTED).pack(pady=(24, 0))
        ttk.Label(
            panel,
            text=f"Version {self.metadata.version} · Commit {self.metadata.short_commit} · {self.metadata.platform}",
            style="Panel.TLabel",
            foreground=MUTED,
        ).pack(pady=(10, 0))

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
        self.project_label = ttk.Label(bar, text="", style="Panel.TLabel", font=(self.ui_font, 11, "bold"))
        self.project_label.pack(side="left")
        self.state_label = ttk.Label(bar, text="", style="StatusSaved.TLabel", background=PANEL)
        self.state_label.pack(side="left", padx=16)
        ttk.Button(bar, text="Import Excel", command=self._import_excel).pack(side="right", padx=3)
        ttk.Button(bar, text="New Project", command=self._new_project).pack(side="right", padx=3)
        ttk.Button(bar, text="高级设置", command=self._open_advanced_settings).pack(side="right", padx=3)
        ttk.Button(bar, text="Export Excel（UI-2）", state="disabled").pack(side="right", padx=3)
        ttk.Button(bar, text="T2B Library（UI-3）", state="disabled").pack(side="right", padx=3)

    def _build_bottom(self) -> None:
        bar = ttk.Frame(self._content, padding=(12, 8), style="Toolbar.TFrame")
        bar.pack(side="bottom", fill="x")
        self.status_message = ttk.Label(bar, text="就绪", style="Panel.TLabel")
        self.status_message.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="Apply Changes", style="Primary.TButton", command=self._apply).pack(side="right", padx=4)
        ttk.Button(bar, text="Save Project", command=self._save).pack(side="right", padx=4)
        ttk.Button(bar, text="Generate Selected（UI-4）", state="disabled").pack(side="right", padx=4)
        ttk.Button(bar, text="Generate All（UI-4）", state="disabled").pack(side="right", padx=4)

    def _build_tree(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="IO Top / Case Tree", style="Panel.TLabel", font=(self.ui_font, 10, "bold")).pack(anchor="w")
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
        self.case_tree.heading("#0", text="IO Top / Direction / Ron")
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
            text="层级：IO Top → DRV/RCV → Ron\nGenerate 复选将在 UI-4 启用",
            style="Panel.TLabel",
            foreground=MUTED,
        ).pack(anchor="w", pady=(6, 0))

    def _build_tabs(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        self.overview_tab = ttk.Frame(self.notebook, padding=8)
        self.config_tab = ttk.Frame(self.notebook)
        self.t2b_tab = ttk.Frame(self.notebook, padding=8)
        self.files_tab = ttk.Frame(self.notebook, padding=8)
        self.monitor_tab = ttk.Frame(self.notebook, padding=24)
        self.log_tab = ttk.Frame(self.notebook, padding=8)
        self.about_tab = ttk.Frame(self.notebook, padding=16)
        for tab, title in (
            (self.overview_tab, "Overview"),
            (self.config_tab, "Config"),
            (self.t2b_tab, "T2B"),
            (self.files_tab, "Files"),
            (self.monitor_tab, "Monitor"),
            (self.log_tab, "Log"),
            (self.about_tab, "About"),
        ):
            self.notebook.add(tab, text=title)
        self.overview_text = self._text_with_scrollbars(self.overview_tab, wrap="word", readonly=True)
        self._build_config_tab()
        self._build_t2b_tab()
        self._build_files_tab()
        ttk.Label(
            self.monitor_tab,
            text="UI-4 后续阶段：任务状态、Retry Failed 和运行进度尚未实现。\n本页不会假装执行真实 T2B、LSF 或仿真。",
            justify="left",
        ).pack(anchor="nw")
        self.log_text = self._text_with_scrollbars(self.log_tab, wrap="word", readonly=True)
        ttk.Label(self.about_tab, text="IBIS Automation", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.about_tab,
            justify="left",
            text=(
                f"App Version: {self.metadata.version}\n"
                f"Git Commit: {self.metadata.git_commit}\n"
                f"Platform: {self.metadata.platform}\n"
                f"Runtime: {'Windows EXE' if self.metadata.frozen else 'Python Source'}\n"
                f"Workspace: {self.controller.store.workspace}"
            ),
        ).pack(anchor="w", pady=(12, 0))

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

        paths = ttk.LabelFrame(parent, text="Section 1 — Project / Path", padding=10, style="Card.TLabelframe")
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
            text="T2B 母模板由软件内置；外部模板覆盖仅在“高级设置”中配置。",
            style="Panel.TLabel",
            foreground=MUTED,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(7, 0))

        summary = ttk.LabelFrame(parent, text="Section 3.1 / 3.2 — Corner / Voltage（只读预览）", padding=10, style="Card.TLabelframe")
        summary.pack(fill="x", pady=(0, 8))
        summary_holder = ttk.Frame(summary, style="Panel.TFrame")
        summary_holder.pack(fill="x")
        self.corner_summary = ttk.Treeview(summary_holder, columns=("max", "typ", "min"), show="tree headings", height=7)
        self.corner_summary.heading("#0", text="Parameter")
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

        module = ttk.LabelFrame(parent, text="Section 2 — Module / Direction / Ron / T2B 动态参数", padding=10, style="Card.TLabelframe")
        module.pack(fill="x", pady=(0, 8))
        fields = (
            ("name", "Module", "readonly"),
            ("generate_type", "Generate Type", "combo"),
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
            text="请选择左侧 IO Top。DRV+RCV 应使用单行 Generate Type=BOTH；完整 Section 1–10 编辑由 UI-2 实现。",
            style="Panel.TLabel",
            foreground=MUTED,
        )
        self.module_notice.grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))

        future = ttk.LabelFrame(parent, text="Section 3.3–10 — 扩展配置分区", padding=10, style="Card.TLabelframe")
        future.pack(fill="x", pady=(0, 8))
        rows = (
            ("3.3 Calibration", "只读保留；UI-2 编辑"),
            ("3.4 SPF Match", "Files 页提供只读匹配预览"),
            ("4 Simulation Options", "只读保留；UI-2 编辑"),
            ("5 IBIS Pin Mapping", "只读保留；UI-2 编辑"),
            ("6 CKT Append", "只读保留；UI-2 编辑"),
            ("7 T2B Template Mapping", "T2B 页显示当前映射"),
            ("8 Signal Override", "只读保留；UI-2 编辑"),
            ("9 MSI Attribute Override", "只读保留；UI-2 编辑"),
            ("10 MSI Mapping", "Files 页提供只读来源预览"),
        )
        for row, (name, state) in enumerate(rows):
            ttk.Label(future, text=name, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(future, text=state, style="Panel.TLabel", foreground=MUTED).grid(row=row, column=1, sticky="w", padx=(20, 0), pady=2)

    def _build_t2b_tab(self) -> None:
        header = ttk.Frame(self.t2b_tab)
        header.pack(fill="x", pady=(0, 6))
        self.template_root_label = ttk.Label(header, text="")
        self.template_root_label.pack(anchor="w")
        self.template_mapping_label = ttk.Label(header, text="", foreground=MUTED)
        self.template_mapping_label.pack(anchor="w", pady=(2, 0))
        paned = ttk.Panedwindow(self.t2b_tab, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=4)
        self.template_tree = ttk.Treeview(left, columns=("type",), show="headings", selectmode="browse")
        self.template_tree.heading("type", text="内置模板 / 类型")
        self.template_tree.column("type", width=250, stretch=True)
        ybar = ttk.Scrollbar(left, orient="vertical", command=self.template_tree.yview)
        self.template_tree.configure(yscrollcommand=ybar.set)
        self.template_tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.template_tree.bind("<<TreeviewSelect>>", self._template_selected)
        self.template_text = self._text_with_scrollbars(right, wrap="none", readonly=True)
        ttk.Label(
            self.t2b_tab,
            text="当前为软件实际加载的母模板只读视图。独立工作模板、编辑、Case Preview 和历史库将在 UI-3 实现。",
            foreground=MUTED,
        ).pack(fill="x", pady=(6, 0))

    def _build_files_tab(self) -> None:
        toolbar = ttk.Frame(self.files_tab)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="刷新 MSI / SPF 扫描", style="Primary.TButton", command=self._refresh_sources).pack(side="left")
        self.source_summary = ttk.Label(toolbar, text="", foreground=MUTED)
        self.source_summary.pack(side="left", padx=12)
        notebook = ttk.Notebook(self.files_tab)
        notebook.pack(fill="both", expand=True)
        msi_tab = ttk.Frame(notebook, padding=4)
        spf_tab = ttk.Frame(notebook, padding=4)
        notebook.add(msi_tab, text="MSI Sources")
        notebook.add(spf_tab, text="SPF Match")
        self.msi_tree = self._msi_tree_with_scrollbars(msi_tab)
        self.spf_tree = self._tree_with_scrollbars(
            spf_tab,
            ("module", "corner", "status", "top", "pins", "path", "message"),
            ("Module", "Corner", "状态", "TOP_SUBCKT", "Pins", "SPF Path", "说明"),
            (150, 70, 80, 170, 55, 400, 300),
        )

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
        self.project_label.configure(text=f"Project: {project.name}")
        state = self.controller.state_label
        style = "StatusDirty.TLabel" if state == "DIRTY" or "未保存" in state else "StatusSaved.TLabel"
        self.state_label.configure(text=state, style=style, background=PANEL)

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
            self.case_tree.insert("", "end", module_id, text=str(module["module"]), values=("IO Top", "CONFIGURED"), open=True)
            self._tree_modules[module_id] = str(module["module"])
            for direction_index, direction in enumerate(module["directions"]):
                direction_id = f"{module_id}:direction:{direction_index}"
                self.case_tree.insert(module_id, "end", direction_id, text=str(direction["direction"]), values=("Direction", "CONFIGURED"), open=True)
                self._tree_modules[direction_id] = str(module["module"])
                for ron_index, ron in enumerate(direction["rons"]):
                    case_id = f"{direction_id}:ron:{ron_index}"
                    self.case_tree.insert(direction_id, "end", case_id, text=f"{ron}Ω", values=("Ron", "NOT GENERATED"))
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
        lines = [
            f"Project ID: {project.project_id if project else ''}",
            f"Mode: {project.mode if project else ''}",
            f"Source Excel（只读）: {source}",
            "",
            "Roots:",
            *[f"  {name.upper()}: {config.get('roots', {}).get(name, '') or '(未设置)'}" for name in ("model", "msi", "spf")],
            f"  T2B Templates ({template_source}): {template_root}",
            "",
            f"Modules: {len(config.get('modules', []))}",
            f"Voltage Domains: {', '.join(config.get('voltage_order', [])) or '(未设置)'}",
            "",
            "本阶段已实现：滚动配置、主题、多模块树、内置模板只读查看、MSI/SPF 来源预览。",
            "未实现：Excel Export/Write Back（UI-2）、工作模板/历史库（UI-3）、Generate/Monitor（UI-4）。",
        ]
        invalid_roots = self.controller.invalid_roots()
        if invalid_roots:
            lines.extend(["", "警告：以下 Root 在当前电脑上无效，请重新指定后 Apply：", *[f"  {name.upper()}: {value or '(未设置)'}" for name, value in invalid_roots.items()]])
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
            self.status_message.configure(text="警告：Model/MSI/SPF Root 在当前电脑上失效，请重新指定后 Apply Changes。", foreground=WARNING)

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
        self.template_tree.delete(*self.template_tree.get_children())
        try:
            templates = self.controller.templates.list_templates(config)
            source = "外部覆盖" if self.controller.templates.using_override(config) else "软件内置只读资源"
            self.template_root_label.configure(text=f"Template Root：{templates[0].path.parent}（{source}）", foreground=PASS)
            mappings = self.controller.templates.mappings_for(config, self._selected_module)
            mapping_text = "；".join(f"{item.get('direction')} → {item.get('template_type')}" for item in mappings) or "当前模块无 Template Mapping"
            self.template_mapping_label.configure(text=f"{self._selected_module or '未选择模块'}：{mapping_text}")
            for info in templates:
                self.template_tree.insert("", "end", iid=info.filename, values=(f"{info.filename}  ·  {info.template_type}",))
            first = self.template_tree.get_children()
            if first:
                self.template_tree.selection_set(first[0])
                self._template_selected()
        except UIProjectError as exc:
            self.template_root_label.configure(text=f"错误 [{exc.code}]：{exc}", foreground=FAIL)
            self.template_mapping_label.configure(text="请在高级设置中修正或清空外部 Template Root。")
            self._set_readonly_text(self.template_text, f"错误 [{exc.code}]：{exc}")

    def _template_selected(self, _event=None) -> None:
        selection = self.template_tree.selection()
        if not selection:
            return
        try:
            content = self.controller.templates.read(self.controller.active_config, selection[0])
        except UIProjectError as exc:
            content = f"错误 [{exc.code}]：{exc}"
        self._set_readonly_text(self.template_text, content)

    def _refresh_sources(self) -> None:
        config = self.controller.active_config
        self.msi_tree.delete(*self.msi_tree.get_children())
        self.spf_tree.delete(*self.spf_tree.get_children())
        msi = preview_msi(config)
        file_nodes: dict[Path, str] = {}
        for item in msi.sheets:
            file_node = file_nodes.get(item.file)
            if file_node is None:
                file_node = self.msi_tree.insert("", "end", text=item.file.name, values=("", "", "FOUND", str(item.file)), open=True)
                file_nodes[item.file] = file_node
            self.msi_tree.insert(file_node, "end", text="Sheet", values=(item.sheet, ", ".join(item.pin_columns), "ERROR" if item.error else "FOUND", item.error), tags=("ERROR",) if item.error else ())
        for item in msi.modules:
            self.msi_tree.insert("", "end", text=f"Module: {item.module}", values=(item.sheet, item.pin_column, item.status, f"{item.file} {item.message}".strip()), tags=(item.status,))
        spf = preview_spf(config)
        for item in spf.matches:
            self.spf_tree.insert("", "end", values=(item.module, item.corner, item.status, item.top_subckt, item.pin_count or "", item.path, item.message), tags=(item.status,))
        msi_errors = sum(item.status == "ERROR" for item in msi.modules)
        spf_errors = sum(item.status == "ERROR" for item in spf.matches)
        self.source_summary.configure(
            text=f"MSI Excel {len(msi.files)} · MSI Error {msi_errors} · SPF Match {len(spf.matches)} · SPF Error {spf_errors}",
            foreground=FAIL if msi_errors or spf_errors else PASS,
        )

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
        ttk.Label(body, text="外部 T2B Template Root 覆盖", font=(self.ui_font, 10, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="留空时使用软件内置四份母模板。旧项目/Excel 中的路径仍会加载；路径失效时请修正或清空。",
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

        PathField(row, variable, update_override, "选择外部 T2B Template Root").pack(side="left", fill="x", expand=True)

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
        self._log("Apply Changes：配置校验通过，草稿已成为生效快照。")
        self.status_message.configure(text="Apply Changes 成功；请 Save Project 持久化。", foreground=PASS)
        self._refresh_all()

    def _save(self) -> None:
        try:
            path = self.controller.save_project()
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._log(f"Save Project：{path}")
        self.status_message.configure(text=f"项目已保存：{path}", foreground=PASS)
        self._refresh_status()

    def _import_excel(self) -> None:
        if not self._confirm_leave_current():
            return
        from tkinter import filedialog

        path = filedialog.askopenfilename(title="选择 IBIS Config Excel", filetypes=(("Excel Workbook", "*.xlsx"),))
        if not path:
            return
        try:
            self.controller.import_excel(Path(path))
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._selected_module = None
        self._show_main()
        self._log(f"Import Excel：{path}（原文件只读，未修改）")
        invalid_roots = self.controller.invalid_roots()
        if invalid_roots:
            detail = "\n".join(f"{name.upper()}: {value or '(未设置)'}" for name, value in invalid_roots.items())
            warning = f"导入成功，但以下 Root 在当前电脑上无效，请重新指定后 Apply Changes：\n{detail}"
            self._log(f"警告：{warning}")
            messagebox.showwarning("项目路径需要修正", warning, parent=self)

    def _new_project(self) -> None:
        if not self._confirm_leave_current():
            return
        name = simpledialog.askstring("New Project", "项目名称：", parent=self)
        if name is None:
            return
        try:
            self.controller.new_project(name)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._selected_module = None
        self._show_main()
        self._log("New Project：已创建内部空项目。完整 Schema 编辑将在 UI-2 实现。")

    def _confirm_leave_current(self) -> bool:
        if not self.controller.project:
            return True
        if self.controller.is_dirty:
            answer = messagebox.askyesnocancel(
                "未 Apply 的修改",
                "存在尚未 Apply 的修改。\n是：Apply 并保存\n否：丢弃全部未保存修改\n取消：返回项目",
                parent=self,
            )
            if answer is None:
                return False
            if answer:
                try:
                    self.controller.apply_changes()
                    self.controller.save_project()
                except UIProjectError as exc:
                    self._show_error(exc)
                    return False
            else:
                self.controller.discard_draft()
                return True
        if self.controller.has_unsaved_applied_changes:
            answer = messagebox.askyesnocancel("未保存项目", "项目存在尚未保存的生效配置。\n是：保存\n否：不保存\n取消：返回项目", parent=self)
            if answer is None:
                return False
            if answer:
                try:
                    self.controller.save_project()
                except UIProjectError as exc:
                    self._show_error(exc)
                    return False
        return True

    def _on_close(self) -> None:
        if self._confirm_leave_current():
            self.destroy()

    def _show_error(self, error: UIProjectError) -> None:
        message = f"错误 [{error.code}]：{error}"
        self._log(message)
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
