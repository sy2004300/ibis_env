from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable


FieldSpec = tuple[str, str, tuple[str, ...] | None, bool]


class TableEditorDialog(tk.Toplevel):
    """Small ordered table editor used by Config Sections 3-10."""

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        rows: list[dict[str, Any]],
        fields: list[FieldSpec],
        save: Callable[[list[dict[str, str]]], None],
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry("980x560")
        self.transient(parent)
        self.grab_set()
        self.rows = copy.deepcopy(rows)
        self.fields = fields
        self.save_callback = save
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(0, 8))
        holder = ttk.Frame(body)
        holder.pack(fill="both", expand=True)
        columns = tuple(field[0] for field in fields)
        self.tree = ttk.Treeview(holder, columns=columns, show="headings", selectmode="browse")
        for key, label, _choices, _multiline in fields:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=max(110, 780 // max(1, len(fields))), stretch=True)
        ybar = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(holder, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _event: self._edit())
        toolbar = ttk.Frame(body)
        toolbar.pack(fill="x", pady=(8, 0))
        for label, command in (("新增", self._add), ("编辑", self._edit), ("删除", self._delete)):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(toolbar, text="应用到项目草稿", command=self._save, style="Primary.TButton").pack(side="right", padx=(0, 8))
        self._refresh()

    def _refresh(self, selected: int | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(index), values=tuple(str(row.get(field[0], "")) for field in self.fields))
        if selected is not None and 0 <= selected < len(self.rows):
            self.tree.selection_set(str(selected))

    def _selected(self) -> int | None:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def _edit_row(self, initial: dict[str, Any]) -> dict[str, str] | None:
        win = tk.Toplevel(self)
        win.title("编辑行")
        win.geometry("720x520" if any(field[3] for field in self.fields) else "640x420")
        win.transient(self)
        win.grab_set()
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        widgets: dict[str, tuple[tk.Widget, tk.StringVar | None]] = {}
        for row_index, (key, label, choices, multiline) in enumerate(self.fields):
            ttk.Label(body, text=label).grid(row=row_index, column=0, sticky="nw", padx=(0, 8), pady=4)
            value = str(initial.get(key, ""))
            if multiline:
                widget = tk.Text(body, height=8, wrap="none")
                widget.insert("1.0", value)
                widget.grid(row=row_index, column=1, sticky="nsew", pady=4)
                widgets[key] = (widget, None)
                body.rowconfigure(row_index, weight=1)
            else:
                variable = tk.StringVar(value=value)
                widget = ttk.Combobox(body, textvariable=variable, values=choices, state="readonly") if choices else ttk.Entry(body, textvariable=variable)
                widget.grid(row=row_index, column=1, sticky="ew", pady=4)
                widgets[key] = (widget, variable)
        body.columnconfigure(1, weight=1)
        result: dict[str, str] | None = None

        def accept() -> None:
            nonlocal result
            result = {}
            for key, (widget, variable) in widgets.items():
                result[key] = widget.get("1.0", "end-1c") if isinstance(widget, tk.Text) else str(variable.get())
            win.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=len(self.fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="确定", command=accept, style="Primary.TButton").pack(side="right", padx=(0, 8))
        self.wait_window(win)
        return result

    def _add(self) -> None:
        row = self._edit_row({})
        if row is not None:
            self.rows.append(row)
            self._refresh(len(self.rows) - 1)

    def _edit(self) -> None:
        index = self._selected()
        if index is None:
            return
        row = self._edit_row(self.rows[index])
        if row is not None:
            self.rows[index] = row
            self._refresh(index)

    def _delete(self) -> None:
        index = self._selected()
        if index is not None and messagebox.askyesno("删除行", "确定删除选中行吗？", parent=self):
            self.rows.pop(index)
            self._refresh(min(index, len(self.rows) - 1))

    def _save(self) -> None:
        try:
            self.save_callback(copy.deepcopy(self.rows))
        except Exception as exc:
            messagebox.showerror("配置无效", str(exc), parent=self)
            return
        self.destroy()


class TemplateEditorDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, text: str, save: Callable[[str], None], diff: Callable[[str], str], preview=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("1100x720")
        self.transient(parent)
        self.grab_set()
        self.save_callback = save
        self.diff_callback = diff
        self.original = text
        self.preview_callback = preview
        self.preview_after = None
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        toolbar = ttk.Frame(self, padding=(8, 8))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="左侧编辑模板原文；右侧为填参预览。保存模板先加入项目草稿；请使用顶部“保存项目”核对差异并持久化。").pack(side="left")
        ttk.Button(toolbar, text="取消", command=self._cancel).pack(side="right", padx=5)
        ttk.Button(toolbar, text="保存模板", command=self._save, style="Primary.TButton").pack(side="right")
        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True)
        holder = ttk.Frame(pane)
        pane.add(holder, weight=1)
        if preview:
            right = ttk.Frame(pane)
            pane.add(right, weight=1)
            self.preview_text = tk.Text(right, wrap="none", font=("TkFixedFont", 10), state="disabled")
            yscroll = ttk.Scrollbar(right, orient="vertical", command=self.preview_text.yview)
            xscroll = ttk.Scrollbar(right, orient="horizontal", command=self.preview_text.xview)
            self.preview_text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
            self.preview_text.grid(row=0, column=0, sticky="nsew")
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll.grid(row=1, column=0, sticky="ew")
            right.rowconfigure(0, weight=1)
            right.columnconfigure(0, weight=1)
        self.lines = tk.Text(holder, width=6, padx=4, takefocus=0, state="disabled", background="#f0f0f0")
        self.editor = tk.Text(holder, wrap="none", undo=True, font=("TkFixedFont", 10))
        ybar = ttk.Scrollbar(holder, orient="vertical", command=self._scroll)
        xbar = ttk.Scrollbar(holder, orient="horizontal", command=self.editor.xview)
        self.editor.configure(yscrollcommand=lambda first, last: (ybar.set(first, last), self._sync_lines(first)))
        self.editor.grid(row=0, column=1, sticky="nsew")
        self.lines.grid(row=0, column=0, sticky="ns")
        ybar.grid(row=0, column=2, sticky="ns")
        xbar.grid(row=1, column=1, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(1, weight=1)
        self.editor.tag_configure("placeholder", foreground="#005bbb", background="#e7f1ff")
        self.editor.bind("<KeyRelease>", lambda _event: self._decorate())
        self._replace(text)
        self.editor.bind("<Control-f>", lambda _: self._find())

    def _update_preview(self):
        self.preview_after = None
        if not self.preview_callback:
            return
        try:
            value = self.preview_callback(self.editor.get("1.0", "end-1c"))
        except Exception as exc:
            value = f"预览错误：{exc}"
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", value)
        self.preview_text.configure(state="disabled")

    def _cancel(self):
        if self.editor.get("1.0", "end-1c") != self.original:
            if not messagebox.askyesno("放弃模板修改", "模板尚未保存，是否放弃本次修改？", parent=self):
                return
        self.destroy()

    def destroy(self):
        if self.preview_after:
            self.after_cancel(self.preview_after)
            self.preview_after = None
        super().destroy()

    def _scroll(self, *args) -> None:
        self.editor.yview(*args)
        self.lines.yview(*args)

    def _sync_lines(self, first: str) -> None:
        self.lines.yview_moveto(float(first))

    def _replace(self, value: str) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", value)
        self._decorate()

    def _decorate(self) -> None:
        if self.preview_after:
            self.after_cancel(self.preview_after)
        self.preview_after = self.after(300, self._update_preview)
        count = int(self.editor.index("end-1c").split(".")[0])
        self.lines.configure(state="normal")
        self.lines.delete("1.0", "end")
        self.lines.insert("1.0", "\n".join(str(index) for index in range(1, count + 1)))
        self.lines.configure(state="disabled")
        self.editor.tag_remove("placeholder", "1.0", "end")
        start = "1.0"
        while True:
            found = self.editor.search(r"\{\{[A-Z0-9_/]+\}\}", start, "end", regexp=True)
            if not found:
                break
            end = f"{found}+{len(self.editor.get(found, found + ' lineend').split('}}', 1)[0]) + 2}c"
            self.editor.tag_add("placeholder", found, end)
            start = end

    def _find(self) -> None:
        value = simpledialog.askstring("查找", "查找内容：", parent=self)
        if not value:
            return
        found = self.editor.search(value, self.editor.index("insert"), "end", nocase=True)
        if not found:
            found = self.editor.search(value, "1.0", "end", nocase=True)
        if found:
            end = f"{found}+{len(value)}c"
            self.editor.tag_remove("sel", "1.0", "end")
            self.editor.tag_add("sel", found, end)
            self.editor.mark_set("insert", end)
            self.editor.see(found)

    def _diff(self) -> None:
        diff = self.diff_callback(self.editor.get("1.0", "end-1c")) or "没有差异。"
        win = tk.Toplevel(self)
        win.title("工作模板差异")
        win.geometry("900x600")
        text = tk.Text(win, wrap="none", font=("TkFixedFont", 10))
        text.insert("1.0", diff)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

    def _save(self) -> None:
        try:
            self.save_callback(self.editor.get("1.0", "end-1c"))
        except Exception as exc:
            messagebox.showerror("模板保存失败", str(exc), parent=self)
            return
        self.destroy()
