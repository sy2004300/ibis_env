from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .controller import ProjectController
from .errors import UIProjectError


PHASE_LABELS = {
    "T2B": "UI-3 后续阶段：模块工作模板、完整文本编辑和 Case Preview 尚未实现。",
    "Files": "UI-4 后续阶段：生成文件浏览将在 Generate 集成后实现。",
    "Monitor": "UI-4 后续阶段：任务状态、Retry Failed 和运行进度尚未实现。",
}


class IBISApplicationView(tk.Tk):
    """Tkinter shell. All project-state decisions live in ProjectController."""

    def __init__(self, controller: ProjectController, smoke_test: bool = False):
        super().__init__()
        self.controller = controller
        self.title("IBIS Automation — UI Phase 1")
        self.geometry("1180x760")
        self.minsize(960, 640)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tree_modules: dict[str, str] = {}
        self._selected_module: str | None = None
        self._loading_form = False
        self._module_vars: dict[str, tk.StringVar] = {}
        self._root_vars: dict[str, tk.StringVar] = {}
        self._content = ttk.Frame(self)
        self._content.pack(fill="both", expand=True)
        if self.controller.project:
            self._show_main()
        else:
            self._show_start()
        if smoke_test:
            self.after(150, self.destroy)

    def _clear(self) -> None:
        for child in self._content.winfo_children():
            child.destroy()

    def _show_start(self) -> None:
        self._clear()
        panel = ttk.Frame(self._content, padding=40)
        panel.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(panel, text="IBIS Automation", font=("TkDefaultFont", 22, "bold")).pack(pady=(0, 8))
        ttk.Label(panel, text="UI Phase 1 — 项目配置管理", font=("TkDefaultFont", 12)).pack(pady=(0, 28))
        ttk.Button(panel, text="Import Excel", command=self._import_excel, width=32).pack(pady=6)
        ttk.Button(panel, text="New Project", command=self._new_project, width=32).pack(pady=6)
        ttk.Button(panel, text="From Library（UI-3 后续阶段）", state="disabled", width=32).pack(pady=6)
        ttk.Label(panel, text="本阶段不会执行 Generate、真实 T2B、LSF 或 C_comp_view。", foreground="#555555").pack(pady=(24, 0))

    def _show_main(self) -> None:
        self._clear()
        self._build_topbar()
        body = ttk.Panedwindow(self._content, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        left = ttk.Frame(body, padding=4)
        right = ttk.Frame(body, padding=4)
        body.add(left, weight=1)
        body.add(right, weight=4)
        self._build_tree(left)
        self._build_tabs(right)
        self._build_bottom()
        self._refresh_all()

    def _build_topbar(self) -> None:
        bar = ttk.Frame(self._content, padding=(10, 8))
        bar.pack(fill="x")
        self.project_label = ttk.Label(bar, text="", font=("TkDefaultFont", 11, "bold"))
        self.project_label.pack(side="left")
        self.state_label = ttk.Label(bar, text="")
        self.state_label.pack(side="left", padx=16)
        ttk.Button(bar, text="Import Excel", command=self._import_excel).pack(side="right", padx=3)
        ttk.Button(bar, text="New Project", command=self._new_project).pack(side="right", padx=3)
        ttk.Button(bar, text="Export Excel（UI-2）", state="disabled").pack(side="right", padx=3)
        ttk.Button(bar, text="T2B Library（UI-3）", state="disabled").pack(side="right", padx=3)

    def _build_tree(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Case Tree", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(0, 4))
        self.case_tree = ttk.Treeview(parent, show="tree", selectmode="browse")
        self.case_tree.pack(fill="both", expand=True)
        self.case_tree.bind("<<TreeviewSelect>>", self._tree_selected)
        ttk.Label(parent, text="IO Top → DRV/RCV → Ron\n复选与 Generate 将在 UI-4 启用", foreground="#555555").pack(anchor="w", pady=6)

    def _build_tabs(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        self.overview_tab = ttk.Frame(self.notebook, padding=10)
        self.config_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.overview_tab, text="Overview")
        self.notebook.add(self.config_tab, text="Config")
        self.overview_text = tk.Text(self.overview_tab, wrap="word", state="disabled", height=20)
        self.overview_text.pack(fill="both", expand=True)
        self._build_config_tab()
        for name in ("T2B", "Files", "Monitor"):
            tab = ttk.Frame(self.notebook, padding=24)
            ttk.Label(tab, text=PHASE_LABELS[name], wraplength=680, justify="left").pack(anchor="nw")
            self.notebook.add(tab, text=name)
        self.log_tab = ttk.Frame(self.notebook, padding=8)
        self.log_text = tk.Text(self.log_tab, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True)
        self.notebook.add(self.log_tab, text="Log")

    def _build_config_tab(self) -> None:
        paths = ttk.LabelFrame(self.config_tab, text="Project / Path", padding=8)
        paths.pack(fill="x", pady=(0, 8))
        for row, name in enumerate(("model", "msi", "spf", "template")):
            ttk.Label(paths, text=f"{name.upper()} Root").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            variable = tk.StringVar()
            entry = ttk.Entry(paths, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            entry.bind("<FocusOut>", lambda _event, key=name: self._root_changed(key))
            entry.bind("<Return>", lambda _event, key=name: self._root_changed(key))
            self._root_vars[name] = variable
        paths.columnconfigure(1, weight=1)

        summary = ttk.LabelFrame(self.config_tab, text="Corner / Voltage（只读摘要）", padding=8)
        summary.pack(fill="x", pady=(0, 8))
        self.corner_summary = ttk.Treeview(summary, columns=("max", "typ", "min"), show="tree headings", height=6)
        self.corner_summary.heading("#0", text="Parameter")
        for name in ("max", "typ", "min"):
            self.corner_summary.heading(name, text=name.upper())
            self.corner_summary.column(name, width=100, anchor="center")
        self.corner_summary.column("#0", width=180)
        self.corner_summary.pack(fill="x")

        module = ttk.LabelFrame(self.config_tab, text="Section 2 — Module 配置", padding=8)
        module.pack(fill="both", expand=True)
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
            ttk.Label(module, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            variable = tk.StringVar()
            if kind == "combo":
                widget = ttk.Combobox(module, textvariable=variable, values=("DRV", "RCV", "BOTH"), state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda _event, field=key: self._module_changed(field))
            elif kind == "domain":
                widget = ttk.Combobox(module, textvariable=variable, state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda _event, field=key: self._module_changed(field))
            else:
                widget = ttk.Entry(module, textvariable=variable, state="readonly" if kind == "readonly" else "normal")
                if kind != "readonly":
                    widget.bind("<KeyRelease>", lambda _event, field=key: self._module_changed(field))
            widget.grid(row=row, column=1, sticky="ew", pady=2)
            self._module_vars[key] = variable
            self._module_widgets[key] = (widget, kind)
            if kind == "domain":
                setattr(widget, "_ibis_domain_widget", True)
        module.columnconfigure(1, weight=1)
        self.module_notice = ttk.Label(module, text="请选择左侧 IO Top。UI-1 仅编辑 Section 2；完整 Schema 编辑将在 UI-2 实现。", foreground="#555555")
        self.module_notice.grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_bottom(self) -> None:
        bar = ttk.Frame(self._content, padding=(10, 7))
        bar.pack(fill="x")
        self.status_message = ttk.Label(bar, text="就绪")
        self.status_message.pack(side="left")
        ttk.Button(bar, text="Apply Changes", command=self._apply).pack(side="right", padx=4)
        ttk.Button(bar, text="Save Project", command=self._save).pack(side="right", padx=4)
        ttk.Button(bar, text="Generate Selected（UI-4）", state="disabled").pack(side="right", padx=4)
        ttk.Button(bar, text="Generate All（UI-4）", state="disabled").pack(side="right", padx=4)

    def _refresh_all(self) -> None:
        self._refresh_status()
        self._refresh_tree()
        self._refresh_overview()
        self._refresh_config()

    def _refresh_status(self) -> None:
        project = self.controller.project
        if not project:
            return
        self.project_label.configure(text=f"Project: {project.name}")
        state = self.controller.state_label
        color = "#a33b00" if state == "DIRTY" else ("#7a5d00" if "未保存" in state else "#176b2c")
        self.state_label.configure(text=state, foreground=color)

    def _refresh_tree(self) -> None:
        self.case_tree.delete(*self.case_tree.get_children())
        self._tree_modules.clear()
        first_module_id: str | None = None
        for module_index, module in enumerate(self.controller.case_tree()):
            module_id = f"module:{module_index}"
            first_module_id = first_module_id or module_id
            self.case_tree.insert("", "end", module_id, text=str(module["module"]), open=True)
            self._tree_modules[module_id] = str(module["module"])
            for direction_index, direction in enumerate(module["directions"]):
                direction_id = f"{module_id}:direction:{direction_index}"
                self.case_tree.insert(module_id, "end", direction_id, text=str(direction["direction"]), open=True)
                self._tree_modules[direction_id] = str(module["module"])
                for ron_index, ron in enumerate(direction["rons"]):
                    case_id = f"{direction_id}:ron:{ron_index}"
                    self.case_tree.insert(direction_id, "end", case_id, text=f"{ron}Ω  NOT GENERATED")
                    self._tree_modules[case_id] = str(module["module"])
        if not self._selected_module and first_module_id:
            self._selected_module = self._tree_modules[first_module_id]
        if self._selected_module:
            target = next((item for item, name in self._tree_modules.items() if name == self._selected_module and item.count(":") == 1), None)
            if target:
                self.case_tree.selection_set(target)
                self.case_tree.focus(target)

    def _refresh_overview(self) -> None:
        project = self.controller.project
        config = self.controller.active_config
        source = project.source_excel.path if project and project.source_excel else "无（UI Mode）"
        lines = [
            f"Project ID: {project.project_id if project else ''}",
            f"Mode: {project.mode if project else ''}",
            f"Source Excel（只读）: {source}",
            "",
            "Roots:",
            *[f"  {name.upper()}: {value or '(未设置)'}" for name, value in config.get("roots", {}).items()],
            "",
            f"Modules: {len(config.get('modules', []))}",
            f"Voltage Domains: {', '.join(config.get('voltage_order', [])) or '(未设置)'}",
            "",
            "本阶段已实现：Import / New Project / Draft / Apply / Save / Reload。",
            "未实现：Excel Export/Write Back（UI-2）、T2B Library（UI-3）、Generate/Monitor（UI-4）。",
        ]
        self.overview_text.configure(state="normal")
        self.overview_text.delete("1.0", "end")
        self.overview_text.insert("1.0", "\n".join(lines))
        self.overview_text.configure(state="disabled")

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

    def _tree_selected(self, _event=None) -> None:
        selection = self.case_tree.selection()
        if not selection:
            return
        module = self._tree_modules.get(selection[0])
        if not module:
            return
        self._selected_module = module
        self._loading_form = True
        try:
            self._load_module_form(module)
        finally:
            self._loading_form = False

    def _module_changed(self, field: str) -> None:
        if self._loading_form or not self._selected_module:
            return
        try:
            self.controller.update_module(self._selected_module, field, self._module_vars[field].get())
        except UIProjectError as exc:
            self.status_message.configure(text=f"错误 [{exc.code}]：{exc}")
            return
        self._refresh_status()
        if field in {"generate_type", "impedances"}:
            self._refresh_tree()

    def _root_changed(self, name: str) -> None:
        if self._loading_form:
            return
        try:
            self.controller.update_root(name, self._root_vars[name].get())
            self._refresh_status()
        except UIProjectError as exc:
            self._show_error(exc)

    def _apply(self) -> None:
        try:
            self.controller.apply_changes()
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._log("Apply Changes：配置校验通过，草稿已成为生效快照。")
        self.status_message.configure(text="Apply Changes 成功；请 Save Project 持久化。")
        self._refresh_all()

    def _save(self) -> None:
        try:
            path = self.controller.save_project()
        except UIProjectError as exc:
            self._show_error(exc)
            return
        self._log(f"Save Project：{path}")
        self.status_message.configure(text=f"项目已保存：{path}")
        self._refresh_status()

    def _import_excel(self) -> None:
        if not self._confirm_leave_current():
            return
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
            self.status_message.configure(text=message)
        messagebox.showerror("IBIS Automation", message, parent=self)

    def _log(self, message: str) -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
