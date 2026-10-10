from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

from .theme import BACKGROUND


def wheel_scroll_units(delta: int, num: int = 0) -> int:
    """Normalize Windows/macOS MouseWheel and Linux Button-4/5 events."""
    if num == 4:
        return -3
    if num == 5:
        return 3
    if delta == 0:
        return 0
    magnitude = max(1, abs(delta) // 120)
    return -magnitude if delta > 0 else magnitude


class ScrollableFrame(ttk.Frame):
    """Reusable vertical form viewport with pointer-routed mouse-wheel support."""

    def __init__(self, parent: tk.Misc, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=BACKGROUND)
        self.vertical = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vertical.set, xscrollcommand=self.horizontal.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical.grid(row=0, column=1, sticky="ns")
        self.horizontal.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.body = ttk.Frame(self.canvas, padding=(10, 8))
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._sync_scrollregion, add="+")
        self.canvas.bind("<Configure>", self._sync_width, add="+")
        self._bind_wheel_tree(self.body)
        self._bind_wheel_tree(self.canvas)

    def _sync_scrollregion(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event) -> None:
        requested = self.body.winfo_reqwidth()
        self.canvas.itemconfigure(self._window, width=max(event.width, requested))

    def _bind_wheel_tree(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_wheel, add="+")
        widget.bind("<Shift-MouseWheel>", self._on_shift_wheel, add="+")
        widget.bind("<Button-4>", self._on_wheel, add="+")
        widget.bind("<Button-5>", self._on_wheel, add="+")
        widget.bind("<Map>", lambda _event, item=widget: self._bind_children(item), add="+")

    def _bind_children(self, widget: tk.Misc) -> None:
        for child in widget.winfo_children():
            self._bind_wheel_tree(child)
            self._bind_children(child)

    def _on_wheel(self, event):
        if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Treeview, tk.Canvas)) and event.widget is not self.canvas:
            return None
        units = wheel_scroll_units(getattr(event, "delta", 0), getattr(event, "num", 0))
        if units:
            self.canvas.yview_scroll(units, "units")
            return "break"
        return None

    def _on_shift_wheel(self, event):
        if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Treeview, tk.Canvas)) and event.widget is not self.canvas:
            return None
        units = wheel_scroll_units(getattr(event, "delta", 0), getattr(event, "num", 0))
        if units:
            self.canvas.xview_scroll(units, "units")
            return "break"
        return None


class PathField(ttk.Frame):
    """Entry + Browse folder control used consistently for project roots."""

    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.StringVar,
        on_change: Callable[[], None],
        browse_title: str,
    ):
        super().__init__(parent, style="Panel.TFrame")
        self.variable = variable
        self.on_change = on_change
        self.browse_title = browse_title
        self.entry = ttk.Entry(self, textvariable=variable)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<FocusOut>", lambda _event: self.on_change())
        self.entry.bind("<Return>", lambda _event: self.on_change())
        ttk.Button(self, text="浏览…", command=self._browse).pack(side="left", padx=(6, 0))

    def _browse(self) -> None:
        raw = self.variable.get().strip()
        initial = raw if raw and Path(raw).is_dir() else None
        selected = filedialog.askdirectory(parent=self.winfo_toplevel(), title=self.browse_title, initialdir=initial)
        if selected:
            self.variable.set(selected)
            self.on_change()
