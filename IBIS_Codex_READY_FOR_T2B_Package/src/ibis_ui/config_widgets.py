from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class CollapsibleSection(ttk.Frame):
    """Keep children alive when collapsed, including uncommitted entry text."""
    def __init__(self, parent, title, states=None):
        super().__init__(parent)
        self.title = title
        self.states = states if states is not None else {}
        self.expanded = self.states.get(title, True)
        self.toggle_button = ttk.Button(self, command=self.toggle)
        self.toggle_button.pack(fill="x")
        self.body = ttk.Frame(self, padding=10, style="Panel.TFrame")
        self._display()

    def _display(self):
        self.toggle_button.configure(text=("▼ " if self.expanded else "▶ ") + self.title)
        if self.expanded:
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()
        self.states[self.title] = self.expanded

    def toggle(self):
        self.expanded = not self.expanded
        self._display()


class InlineCornerTable(ttk.Frame):
    """Editable name / MAX / TYP / MIN rows, with no separate edit dialog."""
    def __init__(self, parent, name_key, label, rows, change):
        super().__init__(parent, style="Panel.TFrame")
        self.name_key = name_key
        self.change = change
        self.variables = []
        self.cells = ttk.Frame(self, style="Panel.TFrame")
        self.cells.pack(fill="x")
        self.error = ttk.Label(self, foreground="#b42318", wraplength=800)
        self.error.pack(fill="x")
        ttk.Button(self, text=f"新增 {label}", command=self.add_row).pack(anchor="w")
        self.label = label
        self._build(rows)

    def values(self):
        return [{key: var.get() for key, var in row.items()} for row in self.variables]

    def _build(self, rows):
        for widget in self.cells.winfo_children():
            widget.destroy()
        self.variables = []
        keys = (self.name_key, "MAX", "TYP", "MIN")
        for col, name in enumerate((self.label, "MAX", "TYP", "MIN")):
            ttk.Label(self.cells, text=name).grid(row=0, column=col, sticky="w", padx=3)
            self.cells.columnconfigure(col, weight=1)
        for index, value in enumerate(rows):
            variables = {}
            for col, key in enumerate(keys):
                var = tk.StringVar(value=str(value.get(key, "")))
                variables[key] = var
                ttk.Entry(self.cells, textvariable=var).grid(row=index + 1, column=col, sticky="ew", padx=3, pady=2)
                var.trace_add("write", lambda *_: self._changed())
            self.variables.append(variables)
            ttk.Button(self.cells, text="删除", command=lambda i=index: self.delete_row(i)).grid(row=index + 1, column=4, padx=3)

    def _changed(self):
        error = self.change(self.values())
        self.error.configure(text=error or "")
        return not error

    def add_row(self):
        self._build([*self.values(), {self.name_key: "", "MAX": "", "TYP": "", "MIN": ""}])
        self._changed()

    def delete_row(self, index):
        rows = self.values()
        candidate = rows[:index] + rows[index + 1:]
        error = self.change(candidate)
        if error:
            self.error.configure(text=error)
            # Revalidate what remains visible; a rejected deletion is not a draft edit.
            self.change(rows)
        else:
            self._build(candidate)
            self.error.configure(text="")
