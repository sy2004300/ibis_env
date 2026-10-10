from __future__ import annotations

import platform
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Iterable


BLUE = "#1677ff"
BLUE_DARK = "#0f5ec7"
BLUE_SOFT = "#eaf3ff"
BACKGROUND = "#f6f8fb"
PANEL = "#ffffff"
BORDER = "#d9e0ea"
TEXT = "#1f2937"
MUTED = "#667085"
PASS = "#18a957"
WARNING = "#f28c28"
FAIL = "#e5484d"


FONT_CANDIDATES = {
    "Windows": ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Segoe UI"),
    "Darwin": ("PingFang SC", "Hiragino Sans GB", "Helvetica Neue"),
    "Linux": ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "DejaVu Sans"),
}


def choose_ui_font(available: Iterable[str], system: str | None = None) -> str:
    """Choose an installed Chinese-capable font without making it a dependency."""
    installed = {str(name).casefold(): str(name) for name in available}
    system_name = system or platform.system()
    candidates = FONT_CANDIDATES.get(system_name, FONT_CANDIDATES["Linux"])
    for candidate in candidates:
        actual = installed.get(candidate.casefold())
        if actual:
            return actual
    return "TkDefaultFont"


def configure_process_dpi_awareness(system: str | None = None) -> None:
    """Best-effort Windows DPI awareness; never prevents startup."""
    if (system or platform.system()) != "Windows":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def apply_modern_style(root: tk.Misc) -> str:
    """Apply the V10.4-inspired blue/white theme and return the selected font."""
    try:
        root.configure(background=BACKGROUND)
    except tk.TclError:
        pass
    try:
        available = tkfont.families(root)
    except tk.TclError:
        available = ()
    family = choose_ui_font(available)
    for named_font in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(named_font, root=root).configure(family=family, size=10)
        except tk.TclError:
            pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", font=(family, 10))
    style.configure("TFrame", background=BACKGROUND)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Toolbar.TFrame", background=PANEL)
    style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=(family, 13, "bold"), foreground=TEXT)
    style.configure("StatusSaved.TLabel", foreground=PASS, font=(family, 10, "bold"))
    style.configure("StatusDirty.TLabel", foreground=WARNING, font=(family, 10, "bold"))
    style.configure("StatusError.TLabel", foreground=FAIL, font=(family, 10, "bold"))
    style.configure("Card.TLabelframe", background=PANEL, bordercolor=BORDER, relief="solid")
    style.configure("Card.TLabelframe.Label", background=PANEL, foreground=TEXT, font=(family, 10, "bold"))
    style.configure("TButton", padding=(10, 6))
    style.configure("Primary.TButton", background=BLUE, foreground="white", bordercolor=BLUE)
    style.map(
        "Primary.TButton",
        background=[("active", BLUE_DARK), ("pressed", BLUE_DARK), ("disabled", "#a8cfff")],
        foreground=[("disabled", "#f7faff")],
    )
    style.configure("Secondary.TButton", background=PANEL, foreground=TEXT, bordercolor=BORDER)
    style.configure("Treeview", rowheight=28, background=PANEL, fieldbackground=PANEL, foreground=TEXT)
    style.configure("Treeview.Heading", background="#eef3f8", foreground=TEXT, font=(family, 9, "bold"), padding=(6, 5))
    style.map("Treeview", background=[("selected", "#dcecff")], foreground=[("selected", TEXT)])
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 8))
    style.map("TNotebook.Tab", background=[("selected", BLUE_SOFT)], foreground=[("selected", BLUE_DARK)])
    style.configure("Vertical.TScrollbar", arrowsize=14)
    style.configure("Horizontal.TScrollbar", arrowsize=14)
    return family
