"""Shared read-only, two-pane Case file preview for legacy and VNext UI."""
from __future__ import annotations
import os
import platform
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox


def file_order(path):
    name = path.name.casefold()
    group = 0 if name == 'ckt_topology.sp' else 1 if name == 'component.sp' else 2 if name.startswith('corner_') and path.suffix.casefold() == '.sp' else 3 if path.suffix.casefold() == '.t2b' else 4
    return group, name


def open_directory(path):
    path = Path(path).resolve()
    if not path.is_dir():
        raise OSError('输出目录不存在：' + str(path))
    if platform.system() == 'Windows':
        os.startfile(str(path))
    else:
        subprocess.Popen(['open' if platform.system() == 'Darwin' else 'xdg-open', str(path)])


class CaseFilePreview(tk.Toplevel):
    def __init__(self, parent, directory, title='检查生成文件'):
        super().__init__(parent)
        self.directory = Path(directory).resolve()
        self.title(title)
        self.geometry('1100x720')
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill='x')
        ttk.Label(toolbar, text=str(self.directory)).pack(side='left', fill='x', expand=True)
        ttk.Button(toolbar, text='打开输出文件夹', command=self.open_folder).pack(side='right')
        pane = ttk.Panedwindow(self, orient='horizontal')
        pane.pack(fill='both', expand=True)
        left, right = ttk.Frame(pane, padding=6), ttk.Frame(pane, padding=6)
        pane.add(left, weight=1)
        pane.add(right, weight=4)
        self.listing = tk.Listbox(left, exportselection=False, width=32)
        self.listing.grid(row=0, column=0, sticky='nsew')
        self.preview = tk.Text(right, wrap='none', font='TkFixedFont', state='disabled', exportselection=False)
        self.preview.grid(row=0, column=0, sticky='nsew')
        for frame, widget in ((left, self.listing), (right, self.preview)):
            ybar = ttk.Scrollbar(frame, orient='vertical', command=widget.yview)
            xbar = ttk.Scrollbar(frame, orient='horizontal', command=widget.xview)
            widget.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            ybar.grid(row=0, column=1, sticky='ns')
            xbar.grid(row=1, column=0, sticky='ew')
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
        self.preview.bind('<Control-a>', self.select_all)
        self.preview.bind('<Control-A>', self.select_all)
        self.preview.bind('<Control-c>', self.copy_selection)
        self.preview.bind('<Control-C>', self.copy_selection)
        self.files = sorted((p for p in self.directory.iterdir() if p.is_file()), key=file_order)
        for path in self.files:
            self.listing.insert('end', path.name)
        self.listing.bind('<<ListboxSelect>>', self.show_file)
        if self.files:
            self.listing.selection_set(0)
            self.show_file()

    def show_file(self, event=None):
        selected = self.listing.curselection()
        if not selected:
            return
        try:
            # No strip/reflow: keep whitespace and original line breaks.
            with self.files[selected[0]].open('r', encoding='utf-8', errors='replace', newline='') as stream:
                text = stream.read()
        except OSError as exc:
            text = '文件无法读取：' + str(exc)
        self.preview.configure(state='normal')
        self.preview.delete('1.0', 'end')
        self.preview.insert('1.0', text)
        self.preview.configure(state='disabled')
        self.preview.xview_moveto(0)
        self.preview.yview_moveto(0)

    def select_all(self, event=None):
        self.preview.tag_add('sel', '1.0', 'end-1c')
        return 'break'

    def copy_selection(self, event=None):
        try:
            text = self.preview.get('sel.first', 'sel.last')
        except tk.TclError:
            return 'break'
        self.clipboard_clear()
        self.clipboard_append(text)
        return 'break'

    def open_folder(self):
        try:
            open_directory(self.directory)
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showwarning('无法打开输出文件夹', '请手动打开：%s\n%s' % (self.directory, exc), parent=self)
