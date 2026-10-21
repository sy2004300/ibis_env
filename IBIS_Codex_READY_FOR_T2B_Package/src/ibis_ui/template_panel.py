from __future__ import annotations

import difflib
import tkinter as tk
from tkinter import messagebox, ttk

from .config_widgets import CollapsibleSection
from .editor_dialogs import TemplateEditorDialog
from .errors import UIProjectError


class TemplatePanel(ttk.Frame):
    """Case-oriented rendered preview; template editing is an optional action."""
    def __init__(self, parent, controller, changed):
        super().__init__(parent)
        self.controller = controller
        self.changed = changed
        self.module = None
        self.previous = None
        self.direction = tk.StringVar()
        self.ron = tk.StringVar()
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.module_label = ttk.Label(top, text="请选择模块")
        self.module_label.pack(side="left", padx=5)
        ttk.Label(top, text="方向").pack(side="left")
        self.direction_combo = ttk.Combobox(top, textvariable=self.direction, state="readonly", width=7)
        self.direction_combo.pack(side="left", padx=5)
        ttk.Label(top, text="Ron (Ω)").pack(side="left")
        self.ron_combo = ttk.Combobox(top, textvariable=self.ron, state="readonly", width=8)
        self.ron_combo.pack(side="left", padx=5)
        self.edit_button = ttk.Button(top, text="修改模板", command=self.edit)
        self.edit_button.pack(side="right")
        self.direction_combo.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        self.ron_combo.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        self.source_label = ttk.Label(self, foreground="#667085")
        self.source_label.pack(fill="x", pady=5)
        self.state_label = ttk.Label(self, wraplength=900)
        self.state_label.pack(fill="x", pady=5)
        self.advanced = CollapsibleSection(self, "模板来源（高级）", {"模板来源（高级）": False})
        self.advanced.pack(fill="x", pady=4)
        self.source = tk.StringVar()
        self.source_combo = ttk.Combobox(self.advanced.body, textvariable=self.source, state="readonly")
        self.source_combo.pack(fill="x")
        self.source_combo.bind("<<ComboboxSelected>>", self.change_source)
        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True)
        self.text = tk.Text(holder, wrap="none", font=("TkFixedFont", 10), state="disabled")
        ybar = ttk.Scrollbar(holder, orient="vertical", command=self.text.yview)
        xbar = ttk.Scrollbar(holder, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.text.tag_configure("changed", background="#fff2c6")
        ttk.Label(self, text="这里是当前配置填参预览，不代表已经生成文件。修改电压、Tr/Tf 请到“参数配置”；同模块同方向的 Ron 共用模板。", wraplength=900).pack(fill="x", pady=5)

    def set_case(self, module, direction=None, ron=None):
        if module != self.module:
            self.previous = None
        self.module = module
        if module is None:
            self.refresh()
            return
        item = self.controller.module(module)
        directions = ("DRV", "RCV") if item["generate_type"] == "BOTH" else (item["generate_type"],)
        rons = tuple(str(value) for value in item["impedances"])
        self.direction_combo.configure(values=directions)
        self.ron_combo.configure(values=rons)
        self.direction.set(direction if direction in directions else (self.direction.get() if self.direction.get() in directions else directions[0]))
        self.ron.set(str(ron) if str(ron) in rons else (self.ron.get() if self.ron.get() in rons else (rons[0] if rons else "")))
        self.refresh()

    def key(self):
        return (self.module, self.direction.get(), int(self.ron.get()))

    def refresh(self):
        if not self.winfo_exists():
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.edit_button.configure(state="disabled")
        if not self.module or not self.controller.project:
            self.text.insert("1.0", "请从左侧选择一个模块或 Case。")
            self.text.configure(state="disabled")
            return
        self.module_label.configure(text=f"当前模块：{self.module}")
        direction = self.direction.get()
        record = (self.controller.workflow_draft or {}).get("working_templates", {}).get(f"{self.module}|{direction}")
        self.choices = {"自动匹配": None}
        self.choices.update({item.display_name: item.template_id for item in self.controller.templates.selectable(direction)})
        self.source_combo.configure(values=tuple(self.choices))
        choice = self.controller.template_selection(self.module)[f"{direction.lower()}_template"]
        self.source.set(next((label for label, value in self.choices.items() if value == choice.get("template_id")), "自动匹配") if choice["mode"] == "manual" else "自动匹配")
        try:
            self.controller.check_pending_edits()
            path = self.controller.working_template_service().resolve_path(self.controller.active_config, self.module, direction, validate=False)
            self.source_label.configure(text=f"使用模板：{'项目自定义 v' + str(record['version']) if record else '直接使用母模板'} · {path.name}")
            self.edit_button.configure(state="normal")
            key = self.key()
            rendered = self.controller.preview_t2b(key)
            self.text.insert("1.0", rendered)
            if self.previous and self.previous[0] == key and self.previous[1] != rendered:
                old_lines, new_lines = self.previous[1].splitlines(), rendered.splitlines()
                for tag, _a, _b, start, end in difflib.SequenceMatcher(a=old_lines, b=new_lines).get_opcodes():
                    if tag in {"replace", "insert"}:
                        self.text.tag_add("changed", f"{start + 1}.0", f"{end + 1}.0")
            self.previous = (key, rendered)
            draft = self.controller.has_unsaved_changes
            self.state_label.configure(text="当前配置预览：包含未保存修改（变化行以黄色标注）" if draft else "当前已保存配置预览：可直接生成", foreground="#b54708" if draft else "#067647")
        except (UIProjectError, ValueError, OSError) as exc:
            self.previous = None
            self.text.insert("1.0", f"无法显示填参结果：{exc}\n\n请检查“参数配置”和“输入文件”中的对应字段。")
            self.state_label.configure(text="预览不可用：输入尚未完整或存在错误", foreground="#b42318")
        finally:
            self.text.configure(state="disabled")

    def change_source(self, _event=None):
        direction = self.direction.get()
        key = f"{self.module}|{direction}"
        records = (self.controller.workflow_draft or {}).get("working_templates", {})
        if key in records and not messagebox.askyesno("更换模板来源", "当前使用项目自定义模板。更换来源后将使用新模板，历史文件保留。是否继续？", parent=self):
            self.refresh()
            return
        self.controller.update_template(self.module, direction, self.choices[self.source.get()])
        records.pop(key, None)
        self.changed()
        self.refresh()

    def edit(self):
        module, direction, ron = self.key()
        try:
            source = self.controller.template_source(module, direction)
        except UIProjectError as exc:
            messagebox.showerror("模板不可用", str(exc), parent=self)
            return

        def save(value):
            self.controller.save_template_and_project(module, direction, value)
            self.changed()
            self.refresh()

        TemplateEditorDialog(
            self, f"修改模板 — {module} / {direction}（该方向所有 Ron 共用）",
            source, save,
            lambda value: "".join(difflib.unified_diff(source.splitlines(True), value.splitlines(True))),
            preview=lambda value: self.controller.preview_t2b((module, direction, ron), value),
        )
