from __future__ import annotations

import copy
import logging
import os
import platform
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from .controller import ProjectController
from .editor_dialogs import TableEditorDialog, TemplateEditorDialog
from .errors import UIProjectError
from .logging_utils import LOGGER_NAME
from .presentation import build_project_overview, case_tree_counts, filter_case_tree
from .runtime import app_metadata
from .source_preview import preview_models, preview_msi, preview_spf
from .status import ConfigStatus, GenerationStatus, status_label
from .theme import BACKGROUND, FAIL, MUTED, PANEL, PASS, WARNING, apply_modern_style
from .ui_text import TEXT, TOOLTIPS
from .widgets import PathField, ScrollableFrame, Tooltip


START_PAGE_ACTIONS = ("new_project", "open_project")
PROJECT_PAGE_ACTIONS = ("import_config", "export_config", "save_config", "delete_project", "advanced", "about")


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
        self._case_items: dict[str, tuple[str, str | None, int | None]] = {}
        self._generation_queue: queue.Queue[tuple[str, str, str]] = queue.Queue()
        self._generation_cancel = threading.Event()
        self.smoke_error: str | None = None
        self._content = ttk.Frame(self)
        self._content.pack(fill="both", expand=True)
        self._show_main() if self.controller.project else self._show_start()
        if smoke_test:
            self.after(400, self._run_smoke_test)

    def _run_smoke_test(self) -> None:
        """Exercise the real main window layout before CI auto-closes it."""
        try:
            def button_texts(root: tk.Misc) -> list[str]:
                values: list[str] = []
                for child in root.winfo_children():
                    if isinstance(child, ttk.Button):
                        values.append(str(child.cget("text")))
                    values.extend(button_texts(child))
                return values

            self.update_idletasks()
            if not self.controller.project:
                raise RuntimeError("GUI Smoke 未加载项目")
            if not self.status_message.winfo_ismapped():
                raise RuntimeError("固定底部操作栏不可见")
            if not self.back_to_start_button.winfo_ismapped():
                raise RuntimeError("返回启动首页按钮不可见")
            if not self.delete_project_button.winfo_ismapped():
                raise RuntimeError("删除项目按钮不可见")
            project_buttons = button_texts(self._content)
            if TEXT["new_project"] in project_buttons or TEXT["open_project"] in project_buttons:
                raise RuntimeError("项目内部不应出现新建项目或打开项目按钮")
            if TEXT["import_config"] not in project_buttons:
                raise RuntimeError("项目内部缺少导入 Config Excel 按钮")
            for required in ("导出 Config Excel", "创建工作模板", "生成选中任务", "刷新检查"):
                if required not in project_buttons:
                    raise RuntimeError(f"全流程界面缺少按钮：{required}")
            if not {"VDDQ", "VDD"}.issubset({domain for domain, _corner in self._voltage_vars}):
                raise RuntimeError("参数配置未显示 VDDQ/VDD Corner 电压编辑框")
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
            self.controller.close_project("discard")
            self._show_start()
            self.update_idletasks()
            start_buttons = button_texts(self._content)
            if start_buttons.count(TEXT["new_project"]) != 1 or start_buttons.count(TEXT["open_project"]) != 1:
                raise RuntimeError("项目首页的新建项目/打开项目入口重复或缺失")
            if TEXT["import_config"] in start_buttons:
                raise RuntimeError("项目首页不应出现导入 Config Excel 按钮")
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

        scrolling = ScrollableFrame(self._content)
        scrolling.pack(fill="both", expand=True, padx=16, pady=12)
        panel = scrolling.body
        ttk.Label(panel, text="项目首页", style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text=TEXT.get("app_subtitle", ""), foreground=MUTED).pack(anchor="w", pady=(3, 18))
        card = ttk.LabelFrame(panel, text="开始使用", padding=18, style="Card.TLabelframe")
        card.pack(fill="x", pady=(0, 12))
        ttk.Label(card, text="新建一个软件项目，或从下方最近项目中选择后打开。Config Excel 请进入具体项目后导入。", style="Panel.TLabel").pack(anchor="w")
        actions = ttk.Frame(card, style="Panel.TFrame")
        actions.pack(anchor="w", pady=(14, 0))
        commands = {"new_project": self._new_project, "open_project": self._open_from_start}
        for key in START_PAGE_ACTIONS:
            button = ttk.Button(
                actions,
                text=TEXT[key],
                command=commands[key],
                style="Primary.TButton" if key == "new_project" else "Secondary.TButton",
            )
            button.pack(side="left", padx=(0, 8))
            Tooltip(button, TOOLTIPS[key])

        recent = ttk.LabelFrame(panel, text="最近项目", padding=12, style="Card.TLabelframe")
        recent.pack(fill="both", expand=True, pady=(0, 12))
        ttk.Label(
            recent,
            text="双击项目或选中后点击上方“打开项目”。未选择项目时，“打开项目”可浏览 project.json。",
            style="Panel.TLabel",
            foreground=MUTED,
            wraplength=1050,
        ).pack(anchor="w", pady=(0, 6))
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

        guide = ttk.LabelFrame(panel, text="工程师工作流程", padding=12, style="Card.TLabelframe")
        guide.pack(fill="x")
        ttk.Label(
            guide,
            text="① 新建或打开项目  →  ② 在项目内导入 Config Excel  →  ③ 修改并保存项目  →  ④ 检查输入文件  →  ⑤ 选择 T2B 模板  →  ⑥ 后续阶段生成与查看结果",
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
        self.back_to_start_button = ttk.Button(
            bar,
            text=TEXT["back_to_start"],
            command=self._close_current_project,
            style="Secondary.TButton",
        )
        self.back_to_start_button.pack(side="left", padx=(0, 10))
        Tooltip(self.back_to_start_button, TOOLTIPS["back_to_start"])
        self.project_label = ttk.Label(bar, text="", style="Panel.TLabel", font=(self.ui_font, 11, "bold"))
        self.project_label.pack(side="left")
        self.state_label = ttk.Label(bar, text="", style="StatusSaved.TLabel", background=PANEL)
        self.state_label.pack(side="left", padx=16)
        commands = {
            "import_config": self._import_excel,
            "export_config": self._export_config,
            "save_config": self._save,
            "delete_project": self._delete_current_project,
            "advanced": self._open_advanced_settings,
            "about": self._show_about,
        }
        for key in reversed(PROJECT_PAGE_ACTIONS):
            style = "Primary.TButton" if key == "save_config" else ("Danger.TButton" if key == "delete_project" else "Secondary.TButton")
            button = ttk.Button(bar, text=TEXT[key], command=commands[key], style=style)
            button.pack(side="right", padx=3)
            if key in TOOLTIPS:
                Tooltip(button, TOOLTIPS[key])
            if key == "delete_project":
                self.delete_project_button = button

    def _build_bottom(self) -> None:
        bar = ttk.Frame(self._content, padding=(12, 8), style="Toolbar.TFrame")
        bar.pack(side="bottom", fill="x")
        self.status_message = ttk.Label(bar, text="就绪", style="Panel.TLabel")
        self.status_message.pack(side="left", fill="x", expand=True)
        self.generation_footer = ttk.Label(bar, text="当前生成状态：未生成", style="Panel.TLabel", foreground=MUTED)
        self.generation_footer.pack(side="right")

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
        self.case_tree = ttk.Treeview(holder, columns=("kind", "state"), show="tree headings", selectmode="extended")
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
            text="层级：IO Top → DRV/RCV → Ron\n支持 Ctrl/Shift 多选后生成选中任务",
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
        self.generate_tab = ttk.Frame(self.notebook, padding=8)
        self.results_tab = ttk.Frame(self.notebook, padding=8)
        self.monitor_tab = ttk.Frame(self.notebook, padding=8)
        self.log_tab = ttk.Frame(self.notebook, padding=8)
        for tab, title in (
            (self.home_tab, TEXT["home"]),
            (self.config_tab, TEXT["config"]),
            (self.files_tab, TEXT["input_files"]),
            (self.t2b_tab, TEXT["t2b_templates"]),
            (self.generate_tab, TEXT["generate"]),
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
        config_button = ttk.Button(home_header, text="编辑参数（含 VDDQ/VDD）", command=self._go_config, style="Secondary.TButton")
        config_button.pack(side="right", padx=(0, 8))
        Tooltip(config_button, "打开参数配置，编辑 Voltage Domain、Ron、Tr/Tf 等项目参数。")
        self.overview_text = self._text_with_scrollbars(self.home_tab, wrap="word", readonly=True)
        self._build_config_tab()
        self._build_files_tab()
        self._build_t2b_tab()
        self._build_generation_tab()
        self._build_results_tab()
        self._build_monitor_tab()
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

    def _build_generation_tab(self) -> None:
        toolbar = ttk.Frame(self.generate_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="生成选中任务", command=self._generate_selected, style="Primary.TButton").pack(side="left")
        ttk.Button(toolbar, text="生成全部任务", command=self._generate_all).pack(side="left", padx=6)
        ttk.Button(toolbar, text="取消等待任务", command=self._cancel_generation).pack(side="left")
        ttk.Label(toolbar, text="仅生成 READY_FOR_T2B 文件；不会运行 T2B、LSF 或生成 .ibs/C_comp_view。", foreground=MUTED).pack(side="left", padx=12)
        self.generation_status_label = ttk.Label(self.generate_tab, text="请选择左侧任务后生成。")
        self.generation_status_label.pack(fill="x", pady=(0, 8))
        self.generation_tree = self._tree_with_scrollbars(
            self.generate_tab,
            ("module", "direction", "ron", "status", "message"),
            ("Module", "Direction", "Ron", "状态", "原因 / 输出"),
            (190, 90, 80, 110, 620),
        )

    def _build_results_tab(self) -> None:
        toolbar = ttk.Frame(self.results_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="刷新检查", command=self._refresh_generation_views, style="Primary.TButton").pack(side="left")
        ttk.Button(toolbar, text="查看选中文件", command=self._preview_generated_case).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Golden 行差异", command=self._show_golden_diff).pack(side="left")
        ttk.Button(toolbar, text="重新生成当前 Case", command=self._regenerate_result_case).pack(side="left")
        ttk.Button(toolbar, text="导出生成报告", command=self._export_generation_report).pack(side="right")
        self.results_tree = self._tree_with_scrollbars(
            self.results_tab,
            ("module", "direction", "ron", "status", "files", "validation", "path"),
            ("Module", "Direction", "Ron", "Status", "File Count", "Validation", "Output Path"),
            (180, 85, 70, 120, 85, 260, 480),
        )
        self.results_tree.bind("<Double-1>", lambda _event: self._preview_generated_case())

    def _build_monitor_tab(self) -> None:
        ttk.Label(self.monitor_tab, text="本地 READY_FOR_T2B 任务状态（非 LSF / T2B 仿真任务）", foreground=MUTED).pack(anchor="w", pady=(0, 8))
        self.monitor_tree = self._tree_with_scrollbars(
            self.monitor_tab,
            ("module", "direction", "ron", "status", "progress", "duration", "reason"),
            ("Module", "Direction", "Ron", "状态", "进度", "用时", "原因"),
            (180, 90, 70, 110, 90, 90, 540),
        )

    def _build_config_tab(self) -> None:
        scrolling = ScrollableFrame(self.config_tab)
        scrolling.pack(fill="both", expand=True)
        self.config_scroll = scrolling
        parent = scrolling.body

        ttk.Label(parent, text="Config Section 1～10 共用同一个项目草稿；所有修改最后由顶部“保存项目”统一校验并持久化。", foreground=MUTED).pack(fill="x", pady=(0, 8))
        paths = ttk.LabelFrame(parent, text="第 1 节 — 项目与路径", padding=10, style="Card.TLabelframe")
        paths.pack(fill="x", pady=(0, 8))
        for row, name in enumerate(("model", "msi", "spf")):
            ttk.Label(paths, text=f"{name.upper()} Root", style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            variable = tk.StringVar()
            field = PathField(paths, variable, lambda key=name: self._root_changed(key), f"选择 {name.upper()} Root")
            field.grid(row=row, column=1, sticky="ew", pady=4)
            self._root_vars[name] = variable
        paths.columnconfigure(1, weight=1)
        source = self.controller.project.source_excel if self.controller.project else None
        ttk.Label(paths, text=f"原始 Config（只读）：{source.path if source else '无'}", foreground=MUTED).grid(row=3, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Label(paths, text=f"来源 SHA256：{source.sha256 if source else '无'}", foreground=MUTED).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(
            paths,
            text="T2B 模板通过“T2B 模板”页面进行选择。",
            style="Panel.TLabel",
            foreground=MUTED,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(7, 0))

        summary = ttk.LabelFrame(parent, text="第 3.1 / 3.2 节 — Corner / Voltage（可编辑）", padding=10, style="Card.TLabelframe")
        summary.pack(fill="x", pady=(0, 8))
        ttk.Label(summary, text="参数", style="Panel.TLabel", font=(self.ui_font, 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 5))
        for column, corner in enumerate(("MAX", "TYP", "MIN"), 1):
            ttk.Label(summary, text=corner, style="Panel.TLabel", font=(self.ui_font, 10, "bold")).grid(row=0, column=column, sticky="ew", padx=4, pady=(0, 5))
            summary.columnconfigure(column, weight=1)
        config = self.controller.active_config
        corners = config.get("corners", {})
        self._corner_vars: dict[tuple[str, str], tk.StringVar] = {}
        for row, (label, key) in enumerate((("Process", "process"), ("Temperature", "temperature"), ("SPF Match Key", "spf_key")), 1):
            ttk.Label(summary, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            for column, corner in enumerate(("MAX", "TYP", "MIN"), 1):
                variable = tk.StringVar(value=str(corners.get(corner, {}).get(key, "")))
                entry = ttk.Entry(summary, textvariable=variable)
                entry.grid(row=row, column=column, sticky="ew", padx=4, pady=3)
                entry.bind("<KeyRelease>", lambda _event, item=corner, field=key: self._corner_changed(item, field))
                self._corner_vars[(corner, key)] = variable
        self._voltage_vars: dict[tuple[str, str], tk.StringVar] = {}
        voltage_order = list(config.get("voltage_order", []))
        for row, domain in enumerate(voltage_order, 4):
            ttk.Label(summary, text=f"{domain} Voltage", style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            for column, corner in enumerate(("MAX", "TYP", "MIN"), 1):
                variable = tk.StringVar()
                entry = ttk.Entry(summary, textvariable=variable)
                entry.grid(row=row, column=column, sticky="ew", padx=4, pady=3)
                entry.bind("<KeyRelease>", lambda _event, item=domain, name=corner: self._voltage_changed(item, name))
                self._voltage_vars[(domain, corner)] = variable
        if not voltage_order:
            ttk.Label(summary, text="当前项目尚无 Voltage Domain；可点击下方“编辑 Voltage Domain”。", style="Panel.TLabel", foreground=WARNING).grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        corner_actions = ttk.Frame(summary, style="Panel.TFrame")
        corner_actions.grid(row=5 + len(voltage_order), column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(corner_actions, text="编辑 Voltage Domain", command=self._edit_voltage_domains).pack(side="left")
        ttk.Button(corner_actions, text="编辑 Calibration", command=self._edit_calibrations).pack(side="left", padx=6)
        ttk.Button(corner_actions, text="重新检查 SPF", command=self._refresh_sources).pack(side="left")

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
        module_actions = ttk.Frame(module, style="Panel.TFrame")
        module_actions.grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(module_actions, text="新增 Module", command=self._add_module).pack(side="left")
        ttk.Button(module_actions, text="重命名 Module", command=self._rename_module).pack(side="left", padx=5)
        ttk.Button(module_actions, text="复制 Module", command=self._duplicate_module).pack(side="left")
        ttk.Button(module_actions, text="删除 Module", command=self._delete_module).pack(side="left", padx=5)
        self.module_notice = ttk.Label(
            module,
            text="请选择左侧 IO Top。DRV+RCV 应使用单行生成类型=BOTH；完整第 1–10 节编辑由 UI-2 实现。",
            style="Panel.TLabel",
            foreground=MUTED,
        )
        self.module_notice.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        future = ttk.LabelFrame(parent, text="第 3.3–10 节 — 扩展配置分区", padding=10, style="Card.TLabelframe")
        future.pack(fill="x", pady=(0, 8))
        rows = (
            ("4 Simulation Option", "保持正文与顺序", lambda: self._edit_config_table("simulation_options")),
            ("5 IBIS Pin Mapping", "Original Pin → Alias", lambda: self._edit_config_table("aliases")),
            ("6 CKT Append / Reference", "多行 SPICE Body 原样保存", lambda: self._edit_config_table("appends")),
            ("7 T2B Template Mapping", "跳转到 T2B 模板页", lambda: self.notebook.select(self.t2b_tab)),
            ("8 Signal Override", "保存时检查作用域冲突", lambda: self._edit_config_table("overrides")),
            ("9 MSI Attribute Override", "当前 Core 支持 POWER_DOMAIN", lambda: self._edit_config_table("attribute_overrides")),
            ("10 MSI Mapping", "Workbook / Sheet / PIN_NAME Column", lambda: self._edit_config_table("msi_mappings")),
        )
        for row, (name, state, command) in enumerate(rows):
            ttk.Label(future, text=name, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(future, text=state, style="Panel.TLabel", foreground=MUTED).grid(row=row, column=1, sticky="w", padx=(20, 0), pady=2)
            ttk.Button(future, text="编辑", command=command).grid(row=row, column=2, sticky="e", padx=(20, 0), pady=2)

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

        work_actions = ttk.LabelFrame(self.t2b_tab, text="项目工作模板", padding=8, style="Card.TLabelframe")
        work_actions.pack(fill="x", pady=(0, 8))
        for label, command in (
            ("创建工作模板", self._create_working_template),
            ("编辑工作模板", self._edit_working_template),
            ("另存为用户模板", self._save_template_as),
            ("从用户模板创建", self._create_from_user_template),
            ("恢复母模板", self._restore_builtin_template),
            ("历史版本", self._show_template_history),
            ("全局配置预览", self._preview_global_t2b_config),
        ):
            ttk.Button(work_actions, text=label, command=command).pack(side="left", padx=(0, 5))
        self.working_template_status = ttk.Label(work_actions, text="状态：尚未创建", foreground=MUTED)
        self.working_template_status.pack(side="right")

        preview = ttk.LabelFrame(self.t2b_tab, text="只读 Template Preview", padding=6, style="Card.TLabelframe")
        preview.pack(fill="both", expand=True)
        self.template_text = self._text_with_scrollbars(preview, wrap="none", readonly=True)
        ttk.Label(
            self.t2b_tab,
            text="母模板只读；项目工作模板按 Project ID + Module + Direction 隔离，所有 Ron 共享该方向模板。",
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
        ttk.Button(toolbar, text="MSI Master 预览", command=self._preview_msi_master).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="生成 MSI_Master.xlsx", command=self._merge_msi_master).pack(side="left", padx=(6, 0))
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
        ttk.Button(msi_head, text="MSI 信号详情", command=self._show_msi_signal_details).pack(side="right", padx=3)
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
        ttk.Button(spf_head, text="SPF / CKT 接口预览", command=self._show_spf_interface).pack(side="right", padx=3)
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
        self._refresh_generation_views()

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
        try:
            generation = {row["key"]: row["status"] for row in self.controller.generation_statuses()}
        except UIProjectError:
            generation = {}
        self.tree_summary.configure(text=f"模块 {modules} · Case {cases} · 当前显示 {len(visible)} 个模块")
        self.case_tree.delete(*self.case_tree.get_children())
        self._tree_modules.clear()
        self._case_items.clear()
        first_module_id: str | None = None
        for module_index, module in enumerate(visible):
            module_id = f"module:{module_index}"
            first_module_id = first_module_id or module_id
            self.case_tree.insert("", "end", module_id, text=str(module["module"]), values=("IO Top", "已配置"), open=True)
            self._tree_modules[module_id] = str(module["module"])
            self._case_items[module_id] = (str(module["module"]), None, None)
            for direction_index, direction in enumerate(module["directions"]):
                direction_id = f"{module_id}:direction:{direction_index}"
                self.case_tree.insert(module_id, "end", direction_id, text=str(direction["direction"]), values=("方向", "已配置"), open=True)
                self._tree_modules[direction_id] = str(module["module"])
                self._case_items[direction_id] = (str(module["module"]), str(direction["direction"]), None)
                for ron_index, ron in enumerate(direction["rons"]):
                    case_id = f"{direction_id}:ron:{ron_index}"
                    key = f"{module['module']}/{direction['direction']}/{ron}ohm"
                    self.case_tree.insert(direction_id, "end", case_id, text=f"{ron}Ω", values=("Ron", status_label(generation.get(key, GenerationStatus.NOT_GENERATED))))
                    self._tree_modules[case_id] = str(module["module"])
                    self._case_items[case_id] = (str(module["module"]), str(direction["direction"]), int(ron))
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
        try:
            generation_rows = self.controller.generation_statuses()
        except UIProjectError:
            generation_rows = []
        workflow = project.workflow if project and project.workflow else {}
        working_records = workflow.get("working_templates", {})
        expected_directions = sum(len(row["directions"]) for row in self.controller.case_tree())
        templates_ready = expected_directions > 0 and len(working_records) >= expected_directions
        generated = bool(generation_rows) and any(row["status"] != "NOT_GENERATED" for row in generation_rows)
        checked = generated and all(row["status"] in {"PASS", "UNVALIDATED"} for row in generation_rows if row["status"] != "NOT_GENERATED")
        steps = (
            ("① 导入或新建项目", True, ""),
            ("② 检查输入文件", overview.inputs_ready, ""),
            ("③ 修改并保存项目", self.controller.config_status == ConfigStatus.SAVED, ""),
            ("④ 选择 T2B 模板", True, ""),
            ("⑤ 工作模板有效", templates_ready, ""),
            ("⑥ 生成 READY_FOR_T2B", generated, ""),
            ("⑦ 检查生成文件", checked, ""),
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
            f"  Case：{overview.case_count}",
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
            "阶段边界：本软件只生成并检查 READY_FOR_T2B，不运行真实 T2B、LSF、.ibs 或 C_comp_view。",
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
            corners = config.get("corners", {})
            for (corner, field), variable in self._corner_vars.items():
                variable.set(corners.get(corner, {}).get(field, ""))
            for (domain, corner), variable in self._voltage_vars.items():
                variable.set(corners.get(corner, {}).get("voltages", {}).get(domain, ""))
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
                record = (self.controller.workflow_draft or {}).get("working_templates", {}).get(f"{self._selected_module}|{first_active}")
                if record:
                    self.working_template_status.configure(text=f"状态：已保存 v{record.get('version')} · {str(record.get('content_hash', ''))[:10]}", foreground=PASS)
                else:
                    self.working_template_status.configure(text="状态：尚未创建", foreground=WARNING)
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

    def _selected_direction(self) -> str | None:
        if not self._selected_module:
            return None
        selection = self.case_tree.selection() if hasattr(self, "case_tree") else ()
        if selection:
            direction = self._case_items.get(selection[0], ("", None, None))[1]
            if direction:
                return direction
        generate_type = str(self.controller.module(self._selected_module)["generate_type"]).upper()
        if generate_type in {"DRV", "RCV"}:
            return generate_type
        value = simpledialog.askstring("选择方向", "请输入 DRV 或 RCV：", parent=self)
        value = str(value or "").upper()
        return value if value in {"DRV", "RCV"} else None

    def _create_working_template(self) -> None:
        direction = self._selected_direction()
        if not direction or not self._selected_module:
            return
        try:
            record = self.controller.create_working_template(self._selected_module, direction)
            self._refresh_t2b()
            self._refresh_status()
            self._log(f"创建工作模板：{record['path']}")
        except UIProjectError as exc:
            self._show_error(exc)

    def _edit_working_template(self) -> None:
        direction = self._selected_direction()
        if not direction or not self._selected_module:
            return
        try:
            content = self.controller.read_working_template(self._selected_module, direction)
            service = self.controller.working_template_service()
        except UIProjectError as exc:
            if messagebox.askyesno("尚无工作模板", f"{exc}\n\n现在从母模板创建吗？", parent=self):
                self._create_working_template()
            return
        module = self._selected_module

        def save(text: str) -> None:
            self.controller.save_working_template(module, direction, text)
            self._refresh_status()
            self._refresh_t2b()

        TemplateEditorDialog(self, f"{module} / {direction} 工作模板", content, save, lambda value: service.diff(module, direction, value))

    def _save_template_as(self) -> None:
        direction = self._selected_direction()
        if not direction or not self._selected_module:
            return
        name = simpledialog.askstring("另存为用户模板", "模板显示名称：", parent=self)
        if not name:
            return
        try:
            record = self.controller.working_template_service().save_as_library(self._selected_module, direction, name)
            self._refresh_status()
            messagebox.showinfo("模板已保存", f"用户模板 ID：{record['template_id']}\n{record['path']}", parent=self)
        except UIProjectError as exc:
            self._show_error(exc)

    def _create_from_user_template(self) -> None:
        direction = self._selected_direction()
        if not direction or not self._selected_module:
            return
        library = (self.controller.workflow_draft or {}).get("template_library", {})
        matches = [row for row in library.values() if row.get("direction") == direction]
        if not matches:
            messagebox.showinfo("用户模板库", f"没有可用于 {direction} 的用户模板。", parent=self)
            return
        labels = {f"{row['display_name']} ({row['template_id']})": row["template_id"] for row in matches}
        value = simpledialog.askstring("选择用户模板", "可用模板：\n" + "\n".join(labels) + "\n\n请输入完整 Template ID：", parent=self)
        if not value:
            return
        try:
            self.controller.create_working_template(self._selected_module, direction, value.strip())
            self._refresh_t2b()
            self._refresh_status()
        except UIProjectError as exc:
            self._show_error(exc)

    def _restore_builtin_template(self) -> None:
        direction = self._selected_direction()
        if not direction or not self._selected_module:
            return
        if not messagebox.askyesno("恢复母模板", "将母模板正文保存为新的工作模板版本吗？现有历史不会删除。", parent=self):
            return
        try:
            self.controller.restore_working_template(self._selected_module, direction)
            self._refresh_t2b()
            self._refresh_status()
        except UIProjectError as exc:
            self._show_error(exc)

    def _show_template_history(self) -> None:
        direction = self._selected_direction()
        if not direction or not self._selected_module:
            return
        try:
            rows = self.controller.working_template_service().history(self._selected_module, direction)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        if not rows:
            messagebox.showinfo("历史版本", "当前工作模板尚无历史版本。", parent=self)
            return
        value = simpledialog.askinteger("历史版本", "可用版本：" + ", ".join(f"v{row['version']}" for row in rows) + "\n恢复版本号：", parent=self)
        if value is None:
            return
        try:
            self.controller.restore_working_template(self._selected_module, direction, value)
            self._refresh_t2b()
            self._refresh_status()
        except UIProjectError as exc:
            self._show_error(exc)

    def _preview_global_t2b_config(self) -> None:
        try:
            path = self.controller.effective_template_root() / "_t2b_config.ini"
            content = path.read_text(encoding="utf-8")
        except (UIProjectError, OSError) as exc:
            messagebox.showerror("无法读取全局配置", str(exc), parent=self)
            return
        win = tk.Toplevel(self)
        win.title("_t2b_config.ini（只读）")
        win.geometry("900x600")
        text = tk.Text(win, wrap="none", font=("TkFixedFont", 10))
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

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

    def _show_msi_signal_details(self) -> None:
        if not self._selected_module:
            messagebox.showwarning("未选择 Module", "请先从左侧任务树选择 IO Top。", parent=self)
            return
        try:
            rows = self.controller.msi_signal_details(self._selected_module)
        except Exception as exc:
            messagebox.showerror("MSI 信号详情不可用", str(exc), parent=self)
            return
        win = tk.Toplevel(self)
        win.title(f"MSI 信号详情 — {self._selected_module}")
        win.geometry("1300x700")
        tree = self._tree_with_scrollbars(
            win,
            ("signal", "width", "direction", "pad", "type", "raw", "override", "effective", "ground", "default", "order", "description"),
            ("PIN_NAME", "Width", "Direction", "PAD", "Attribute", "原始 Power Domain", "用户 Override", "Effective", "Ground", "Default", "Row", "Description"),
            (190, 55, 75, 45, 90, 130, 130, 110, 100, 90, 50, 360),
        )
        for row in rows:
            tree.insert("", "end", values=(row["signal"], row["width"], row["direction"], row["pad"], row["attribute_type"], row["power_domain_raw"], row["power_domain_override"], row["power_domain_effective"], row["ground_domain"], row["default_value"], row["row_order"], row["description"]))

    def _show_spf_interface(self) -> None:
        direction = self._selected_direction()
        if not self._selected_module or not direction:
            return
        try:
            preview = self.controller.spf_interface_preview(self._selected_module, direction)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        win = tk.Toplevel(self)
        win.title(f"SPF / CKT 有效接口预览 — {self._selected_module} {direction}")
        win.geometry("900x650")
        ttk.Label(win, text=f"SPF：{preview['path']}\nTOP_SUBCKT：{preview['top_subckt']} · Pin Count：{len(preview['pins'])}", padding=8).pack(fill="x")
        tree = self._tree_with_scrollbars(win, ("order", "original", "effective"), ("Pin Order", "Original Pin", "Effective Pin / Alias"), (100, 300, 300))
        for row in preview["pins"]:
            tree.insert("", "end", values=(row["order"], row["original_pin"], row["effective_pin"]))

    def _preview_msi_master(self) -> None:
        try:
            preview = self.controller.preview_msi_master()
        except UIProjectError as exc:
            self._show_error(exc)
            return
        lines = [f"有效 MSI Sheet：{len(preview.sources)}", f"自动 Mapping：{len(preview.mappings)}"]
        lines.extend(f"- {source.path.name} / {source.sheet} / {source.pin_column} / {source.rows} 行 / {source.sha256[:12]}" for source in preview.sources)
        if preview.ambiguous_modules:
            lines.extend(["", "需要人工选择来源：", *[f"- {name}" for name in preview.ambiguous_modules]])
        if preview.differences:
            lines.extend(["", "现有 Master 与来源差异：", *[f"- {item}" for item in preview.differences]])
        if preview.excluded:
            lines.extend(["", "排除项：", *[f"- {item}" for item in preview.excluded]])
        win = tk.Toplevel(self)
        win.title("MSI Master Merge 预览")
        win.geometry("980x650")
        text = tk.Text(win, wrap="word")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

    def _merge_msi_master(self) -> None:
        try:
            preview = self.controller.preview_msi_master()
            mappings = list(preview.mappings)
            for module in preview.ambiguous_modules:
                options = "\n".join(f"{index}. {source.path.name} / {source.sheet} / {source.pin_column}" for index, source in enumerate(preview.sources, 1))
                choice = simpledialog.askinteger("选择 MSI 来源", f"Module {module} 存在多个或零个自动候选，请选择：\n{options}", minvalue=1, maxvalue=len(preview.sources), parent=self)
                if choice is None:
                    return
                source = preview.sources[choice - 1]
                mappings.append({"module": module, "source_file": str(source.path), "source_sheet": source.sheet, "column": source.pin_column})
            if preview.differences and not messagebox.askyesno("Master 存在编辑", "检测到现有 Master 与来源存在差异。继续合并时将保留受支持的属性编辑，是否继续？", parent=self):
                return
            path = self.controller.merge_msi_master(mappings)
            self._refresh_status()
            self._refresh_sources()
            messagebox.showinfo("MSI Master 已生成", f"{path}\n\n原始 MSI 文件保持只读且 Hash 未变化。", parent=self)
        except UIProjectError as exc:
            self._show_error(exc)

    def _selected_case_keys(self) -> list[tuple[str, str, int]]:
        selected = self.case_tree.selection()
        if not selected:
            return []
        tree = self.controller.case_tree()
        result: set[tuple[str, str, int]] = set()
        for item in selected:
            module, direction, ron = self._case_items.get(item, ("", None, None))
            for module_row in tree:
                if module_row["module"] != module:
                    continue
                for direction_row in module_row["directions"]:
                    if direction is not None and direction_row["direction"] != direction:
                        continue
                    for value in direction_row["rons"]:
                        if ron is None or int(value) == ron:
                            result.add((module, direction_row["direction"], int(value)))
        return sorted(result)

    def _generate_selected(self) -> None:
        keys = self._selected_case_keys()
        if not keys:
            messagebox.showwarning("未选择任务", "请在左侧任务树选择 IO Top、Direction 或 Ron。", parent=self)
            return
        self._start_generation(keys)

    def _generate_all(self) -> None:
        keys = [
            (module["module"], direction["direction"], int(ron))
            for module in self.controller.case_tree()
            for direction in module["directions"]
            for ron in direction["rons"]
        ]
        self._start_generation(keys)

    def _start_generation(self, keys: list[tuple[str, str, int]]) -> None:
        try:
            self.controller.ensure_generate_allowed()
        except UIProjectError as exc:
            self._show_error(exc)
            return
        if not keys:
            messagebox.showwarning("没有 Case", "当前项目没有可生成的 Case。", parent=self)
            return
        if not messagebox.askyesno(
            "生成 READY_FOR_T2B",
            f"将生成 {len(keys)} 个 Case。\n已有结果会先备份后原子替换，未选中 Case 不会被删除。\n\n继续吗？",
            parent=self,
        ):
            return
        self._generation_cancel.clear()
        self.generation_tree.delete(*self.generation_tree.get_children())
        self.monitor_tree.delete(*self.monitor_tree.get_children())
        for index, key in enumerate(keys):
            values = (key[0], key[1], key[2], "等待中", "")
            self.generation_tree.insert("", "end", iid=f"pending:{index}", values=values)
            self.monitor_tree.insert("", "end", iid=f"pending:{index}", values=(key[0], key[1], key[2], "等待中", "0%", "", ""))
        self.generation_status_label.configure(text=f"已排队 {len(keys)} 个 Case。", foreground=WARNING)
        self.notebook.select(self.generate_tab)

        def progress(key: str, status: str, message: str) -> None:
            self._generation_queue.put((key, status, message))

        def worker() -> None:
            try:
                result = self.controller.generate_cases(
                    keys,
                    overwrite_policy="backup",
                    cancel_requested=self._generation_cancel.is_set,
                    progress=progress,
                )
                self._generation_queue.put(("__DONE__", "PASS" if result.ready else "FAIL", "生成任务完成"))
            except Exception as exc:
                self._generation_queue.put(("__DONE__", "FAIL", str(exc)))

        threading.Thread(target=worker, name="ibis-ready-generator", daemon=True).start()
        self.after(100, self._poll_generation)

    def _poll_generation(self) -> None:
        done = False
        final_status = ""
        final_message = ""
        while True:
            try:
                key, state, message = self._generation_queue.get_nowait()
            except queue.Empty:
                break
            if key == "__DONE__":
                done, final_status, final_message = True, state, message
                continue
            module, direction, ron_text = key.split("/")
            ron = ron_text.removesuffix("ohm")
            self.generation_tree.insert("", "end", values=(module, direction, ron, state, message))
            self.monitor_tree.insert("", "end", values=(module, direction, ron, state, "100%" if state not in {"等待中", "生成中"} else "50%", "", message))
            self._log(f"生成任务 {key}：{state} — {message}")
        if done:
            color = PASS if final_status == "PASS" else FAIL
            self.generation_status_label.configure(text=final_message, foreground=color)
            self._refresh_generation_views()
            self._refresh_tree()
            self._refresh_overview()
            self._refresh_status()
            return
        self.after(100, self._poll_generation)

    def _cancel_generation(self) -> None:
        self._generation_cancel.set()
        self.generation_status_label.configure(text="已请求取消；正在执行的单个 Case 将完成隔离清理。", foreground=WARNING)

    def _refresh_generation_views(self) -> None:
        if not hasattr(self, "results_tree"):
            return
        self.results_tree.delete(*self.results_tree.get_children())
        try:
            rows = self.controller.generation_statuses()
        except UIProjectError as exc:
            self.generation_footer.configure(text=f"生成状态不可用：{exc}", foreground=FAIL)
            return
        counts: dict[str, int] = {}
        for index, row in enumerate(rows):
            status = str(row["status"])
            counts[status] = counts.get(status, 0) + 1
            path = Path(str(row.get("output_path", "")))
            file_count = len([item for item in path.iterdir() if item.is_file() and item.name != ".ibis_manifest.json"]) if path.is_dir() else 0
            self.results_tree.insert(
                "", "end", iid=f"result:{index}",
                values=(row["module"], row["direction"], row["ron"], status, file_count, row.get("message", ""), str(path) if str(path) != "." else ""),
                tags=("ERROR" if status == "FAIL" else ("WARNING" if status in {"STALE", "UNVALIDATED", "NOT_GENERATED"} else "PASS"),),
            )
        summary = " · ".join(f"{name} {counts.get(name, 0)}" for name in ("PASS", "UNVALIDATED", "FAIL", "STALE", "NOT_GENERATED"))
        self.generation_footer.configure(text=f"生成状态：{summary}", foreground=FAIL if counts.get("FAIL") else MUTED)

    def _selected_result_key(self) -> tuple[str, str, int] | None:
        selected = self.results_tree.selection()
        if not selected:
            return None
        values = self.results_tree.item(selected[0], "values")
        return (str(values[0]), str(values[1]), int(values[2]))

    def _preview_generated_case(self) -> None:
        selected = self.results_tree.selection()
        if not selected:
            return
        values = self.results_tree.item(selected[0], "values")
        path = Path(str(values[6]))
        if not path.is_dir():
            messagebox.showwarning("Case 不存在", "该 Case 尚无可查看的输出目录。", parent=self)
            return
        files = sorted(item for item in path.iterdir() if item.is_file())
        win = tk.Toplevel(self)
        win.title(f"检查生成文件 — {values[0]} / {values[1]} / {values[2]}Ω")
        win.geometry("1100x720")
        pane = ttk.Panedwindow(win, orient="horizontal")
        pane.pack(fill="both", expand=True)
        left = ttk.Frame(pane, padding=6)
        right = ttk.Frame(pane, padding=6)
        pane.add(left, weight=1)
        pane.add(right, weight=4)
        listing = tk.Listbox(left, exportselection=False)
        listing.pack(fill="both", expand=True)
        preview = tk.Text(right, wrap="none", font=("TkFixedFont", 10))
        ybar = ttk.Scrollbar(right, orient="vertical", command=preview.yview)
        xbar = ttk.Scrollbar(right, orient="horizontal", command=preview.xview)
        preview.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        preview.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        for item in files:
            listing.insert("end", item.name)

        def show(_event=None) -> None:
            choice = listing.curselection()
            if not choice:
                return
            file = files[choice[0]]
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", file.read_text(encoding="utf-8", errors="replace"))
            preview.configure(state="disabled")

        listing.bind("<<ListboxSelect>>", show)
        if files:
            listing.selection_set(0)
            show()

    def _regenerate_result_case(self) -> None:
        key = self._selected_result_key()
        if key:
            self._start_generation([key])

    def _show_golden_diff(self) -> None:
        key = self._selected_result_key()
        if not key:
            messagebox.showwarning("请选择 Case", "请先在结果表中选择一个 Case。", parent=self)
            return
        try:
            content = self.controller.golden_diff(key)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        win = tk.Toplevel(self)
        win.title(f"Golden 行差异 — {key[0]} / {key[1]} / {key[2]}Ω")
        win.geometry("1150x760")
        preview = self._text_with_scrollbars(win, wrap="none")
        preview.insert("1.0", content)
        preview.configure(state="disabled")

    def _export_generation_report(self) -> None:
        from tkinter import filedialog

        directory = filedialog.askdirectory(title="选择生成报告目录")
        if not directory:
            return
        try:
            csv_path, text_path = self.controller.export_generation_summary(Path(directory))
            messagebox.showinfo("报告已导出", f"{csv_path}\n{text_path}", parent=self)
        except UIProjectError as exc:
            self._show_error(exc)

    def _go_home(self) -> None:
        if hasattr(self, "notebook") and hasattr(self, "home_tab"):
            self._refresh_overview()
            self.notebook.select(self.home_tab)

    def _go_config(self) -> None:
        if hasattr(self, "notebook") and hasattr(self, "config_tab"):
            self._refresh_config()
            self.notebook.select(self.config_tab)

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

    def _open_from_start(self) -> None:
        """Use one start-page action for recent projects and browsed JSON."""

        selection = self.start_recent_tree.selection() if hasattr(self, "start_recent_tree") else ()
        if selection and selection[0] != "recent:none":
            self._open_selected_recent(self.start_recent_tree)
            return
        self._browse_project_file()

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

    def _voltage_changed(self, domain: str, corner: str) -> None:
        if self._loading_form:
            return
        try:
            self.controller.update_corner_voltage(domain, corner, self._voltage_vars[(domain, corner)].get())
        except UIProjectError as exc:
            self.status_message.configure(text=f"错误 [{exc.code}]：{exc}", foreground=FAIL)
            return
        self._refresh_status()
        self.status_message.configure(text=f"已修改 {domain} {corner} 电压；点击“保存项目”完成保存。", foreground=WARNING)

    def _corner_changed(self, corner: str, field: str) -> None:
        if self._loading_form:
            return
        try:
            self.controller.update_corner(corner, field, self._corner_vars[(corner, field)].get())
            self._refresh_status()
        except UIProjectError as exc:
            self.status_message.configure(text=f"错误 [{exc.code}]：{exc}", foreground=FAIL)

    def _edit_voltage_domains(self) -> None:
        config = self.controller.active_config
        rows = [
            {"domain": domain, **{corner: config["corners"][corner]["voltages"].get(domain, "") for corner in ("MAX", "TYP", "MIN")}}
            for domain in config["voltage_order"]
        ]
        TableEditorDialog(
            self, "Section 3.2 — Voltage Domain", rows,
            [("domain", "Voltage Domain", None, False), ("MAX", "MAX", None, False), ("TYP", "TYP", None, False), ("MIN", "MIN", None, False)],
            lambda value: (self.controller.set_voltage_domains(value), self.after(0, self._show_main)),
        )

    def _edit_calibrations(self) -> None:
        config = self.controller.active_config
        order: list[str] = []
        for corner in ("MAX", "TYP", "MIN"):
            for signal in config["corners"][corner]["calibration"]:
                if signal not in order:
                    order.append(signal)
        rows = [
            {"signal": signal, **{corner: config["corners"][corner]["calibration"].get(signal, "") for corner in ("MAX", "TYP", "MIN")}}
            for signal in order
        ]
        TableEditorDialog(
            self, "Section 3.3 — Calibration", rows,
            [("signal", "Signal", None, False), ("MAX", "MAX", None, False), ("TYP", "TYP", None, False), ("MIN", "MIN", None, False)],
            lambda value: (self.controller.set_calibrations(value), self._refresh_status()),
        )

    def _edit_config_table(self, field: str) -> None:
        config = self.controller.active_config
        modules = tuple(str(row["name"]) for row in config["modules"])
        pin_choices: list[str] = []
        for module in modules:
            try:
                preview = self.controller.spf_interface_preview(module, "DRV")
                for row in preview["pins"]:
                    if row["original_pin"] not in pin_choices:
                        pin_choices.append(row["original_pin"])
            except UIProjectError:
                continue
        specs = {
            "simulation_options": [("value", "Simulation Option", None, False)],
            "aliases": [("module", "Module", modules, False), ("direction", "Direction", ("DRV", "RCV", "BOTH"), False), ("original_pin", "Original Pin", tuple(pin_choices) or None, False), ("alias", "IBIS Alias", None, False)],
            "appends": [("module", "Module", modules, False), ("direction", "Direction", ("DRV", "RCV", "BOTH"), False), ("body", "SPICE Body", None, True)],
            "overrides": [("module", "Module", modules, False), ("direction", "Direction", ("DRV", "RCV", "BOTH"), False), ("corner", "Corner", ("MAX", "TYP", "MIN", "ALL"), False), ("signal", "Signal", None, False), ("value", "Value", None, False)],
            "attribute_overrides": [("module", "Module", modules, False), ("signal", "Signal", None, False), ("attribute", "Attribute", ("POWER_DOMAIN",), False), ("value", "Value", None, False)],
            "msi_mappings": [("module", "Module", modules, False), ("file", "Workbook", None, False), ("sheet", "Sheet", None, False), ("column", "PIN_NAME Column", None, False)],
        }
        titles = {
            "simulation_options": "Section 4 — Simulation Option", "aliases": "Section 5 — IBIS Pin Mapping",
            "appends": "Section 6 — CKT Append / Reference", "overrides": "Section 8 — Signal Override",
            "attribute_overrides": "Section 9 — MSI Attribute Override", "msi_mappings": "Section 10 — MSI Mapping",
        }
        rows = ([{"value": value} for value in config[field]] if field == "simulation_options" else copy.deepcopy(config[field]))

        def save(value) -> None:
            stored = [row["value"] for row in value] if field == "simulation_options" else value
            self.controller.replace_config_rows(field, stored)
            self._refresh_status()
            self._refresh_tree()

        TableEditorDialog(self, titles[field], rows, specs[field], save)

    def _add_module(self) -> None:
        name = simpledialog.askstring("新增 Module", "Module Name：", parent=self)
        if not name:
            return
        try:
            self.controller.add_module(name)
            self._selected_module = name.strip()
            self._show_main()
        except UIProjectError as exc:
            self._show_error(exc)

    def _rename_module(self) -> None:
        if not self._selected_module:
            return
        value = simpledialog.askstring("重命名 Module", "新的 Module Name：", initialvalue=self._selected_module, parent=self)
        if not value:
            return
        try:
            old = self._selected_module
            self.controller.rename_module(old, value)
            self._selected_module = value.strip()
            self._show_main()
        except UIProjectError as exc:
            self._show_error(exc)

    def _duplicate_module(self) -> None:
        if not self._selected_module:
            return
        value = simpledialog.askstring("复制 Module", "新 Module Name：", initialvalue=f"{self._selected_module}_copy", parent=self)
        if not value:
            return
        try:
            self.controller.duplicate_module(self._selected_module, value)
            self._selected_module = value.strip()
            self._show_main()
        except UIProjectError as exc:
            self._show_error(exc)

    def _delete_module(self) -> None:
        if not self._selected_module:
            return
        references = self.controller.module_references(self._selected_module)
        detail = "\n".join(f"- {name}: {count}" for name, count in references.items()) or "无关联配置"
        if not messagebox.askyesno("删除 Module", f"删除 {self._selected_module} 并清理以下关联吗？\n{detail}", parent=self):
            return
        try:
            self.controller.delete_module(self._selected_module, cascade=True)
            self._selected_module = None
            self._show_main()
        except UIProjectError as exc:
            self._show_error(exc)

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
        ttk.Button(body, text="导出完整项目包", command=self._export_project_package).pack(side="left", pady=(16, 0))
        ttk.Button(body, text="关闭", command=win.destroy).pack(side="right", pady=(16, 0))

    def _export_project_package(self) -> None:
        from tkinter import filedialog

        project = self.controller.project
        path = filedialog.asksaveasfilename(
            title="导出完整项目包", defaultextension=".zip",
            initialfile=f"{project.name if project else 'IBIS_Project'}_Project.zip",
            filetypes=(("ZIP 压缩包", "*.zip"),),
        )
        if not path:
            return
        try:
            result = self.controller.export_project_package(Path(path))
            messagebox.showinfo("项目包已导出", str(result), parent=self)
        except UIProjectError as exc:
            self._show_error(exc)

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

    def _export_config(self) -> None:
        from tkinter import filedialog

        project = self.controller.project
        path = filedialog.asksaveasfilename(
            title="导出 Config Excel",
            defaultextension=".xlsx",
            initialfile=f"{project.name if project else 'ibis_config'}_export.xlsx",
            filetypes=(("Excel 工作簿", "*.xlsx"),),
        )
        if not path:
            return
        try:
            result = self.controller.export_config(Path(path))
        except UIProjectError as exc:
            self._show_error(exc)
            return
        messagebox.showinfo("导出完成", f"Config Excel 已导出并通过 Core 语义回读：\n{result}\n\n原始 Excel 未修改。", parent=self)

    def _import_excel(self) -> None:
        from tkinter import filedialog

        current = self.controller.project
        if current is None:
            messagebox.showinfo("请先新建项目", "请先在项目首页新建或打开一个项目，再在项目内部导入 Config Excel。", parent=self)
            return
        path = filedialog.askopenfilename(title="导入 Config Excel", filetypes=(("Excel 工作簿", "*.xlsx"),))
        if not path:
            return
        if not messagebox.askyesno(
            "导入 Config Excel",
            f"将 Config Excel 导入当前项目“{current.name}”吗？\n\n"
            "项目名称和 Project UUID 会保留；当前项目中的配置草稿将由 Excel 内容更新。\n"
            "原始 Excel 始终只读，不会被软件覆盖。",
            parent=self,
        ):
            return
        current_id = current.project_id
        try:
            project = self.controller.import_excel(Path(path))
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._selected_module = None
        self._show_main()
        self._go_config()
        if project.project_id == current_id:
            result = f"Config Excel 已导入当前项目“{project.name}”；项目名称和 UUID 均已保留，原文件只读且未修改。"
        else:
            result = f"Config Excel 已导入新项目“{project.name}”；原文件只读且未修改。"
        self.status_message.configure(text=result, foreground=PASS)
        self._log(result)
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
        win.title("返回项目首页")
        win.geometry("560x190")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        body = ttk.Frame(win, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="当前项目存在未保存修改，是否保存后返回？", font=(self.ui_font, 11, "bold")).pack(anchor="w")
        ttk.Label(body, text="返回项目首页只会关闭当前项目视图，不会删除项目目录、Excel、MSI、SPF 或其他输入文件。", foreground=MUTED, wraplength=510).pack(anchor="w", pady=(8, 18))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")

        def choose(value: str) -> None:
            result["value"] = value
            win.destroy()

        ttk.Button(buttons, text="取消", command=lambda: choose("cancel")).pack(side="right")
        ttk.Button(buttons, text="不保存并返回", command=lambda: choose("discard")).pack(side="right", padx=8)
        ttk.Button(buttons, text="保存并返回", command=lambda: choose("save"), style="Primary.TButton").pack(side="right")
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

    def _delete_current_project(self) -> None:
        project = self.controller.project
        if project is None:
            return
        if not messagebox.askyesno(
            "删除项目",
            f"确定删除当前项目“{project.name}”吗？\n\n"
            "项目会从 IBIS Automation 工作区移入回收区，可用于恢复。\n"
            "不会删除原始 Config Excel、MSI、SPF、Model 等输入文件。",
            parent=self,
        ):
            return
        action = self._request_close_action()
        if action == "cancel":
            return
        try:
            trash_path = self.controller.close_and_delete_active_project(action)
        except UIProjectError as exc:
            self._show_error(exc)
            return
        if trash_path is None and self.controller.project is not None:
            return
        self._selected_module = None
        self._tree_modules.clear()
        self._show_start()
        if trash_path is None:
            message = f"未保存项目“{project.name}”已关闭；该项目尚无工作区文件，因此没有需要移动的内容。"
        else:
            message = f"项目“{project.name}”已移入软件回收区。\n\n回收位置：\n{trash_path}"
        messagebox.showinfo("项目已删除", message, parent=self)

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
