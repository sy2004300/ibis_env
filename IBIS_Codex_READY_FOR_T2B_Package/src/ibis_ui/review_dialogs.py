from __future__ import annotations
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import shutil
from pathlib import Path
from .effective_msi import workbook_diff
from .msi_master import file_sha256


def text_view(parent, height=8):
    holder = ttk.Frame(parent)
    holder.pack(fill='both', expand=True)
    text = tk.Text(holder, height=height, wrap='none')
    bar = ttk.Scrollbar(holder, command=text.yview)
    text.configure(yscrollcommand=bar.set)
    bar.pack(side='right', fill='y')
    text.pack(fill='both', expand=True)
    return text


class SaveReview(tk.Toplevel):
    def __init__(self, parent, rows):
        super().__init__(parent)
        self.title('保存前修改差异')
        self.geometry('1050x650')
        self.result = False
        self.transient(parent)
        ttk.Label(self, text='请核对修改。返回修改或取消都会保留当前草稿。').pack(anchor='w', padx=10, pady=10)
        tree = ttk.Treeview(self, columns=('action', 'section', 'scope', 'field', 'old', 'new'), show='headings', height=12)
        for key, label in zip(tree['columns'], ('操作', '配置分区', '模块 / 方向 / 工艺角', '字段', '上次保存值', '新值')):
            tree.heading(key, text=label)
            tree.column(key, width=160)
        tree.pack(fill='both', expand=True)
        details = text_view(self)
        for i, row in enumerate(rows):
            display = lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value if value is not None else '（无）')
            tree.insert('', 'end', iid=str(i), values=(row['action'], row['section'], row['scope'], row['field'], display(row['old']), display(row['new'])))
        def selected(_=None):
            if tree.selection():
                row = rows[int(tree.selection()[0])]
                details.configure(state='normal')
                details.delete('1.0', 'end')
                details.insert('1.0', row['detail'] or f"{row['field']}\n上次保存：{row['old']}\n新值：{row['new']}")
                details.configure(state='disabled')
        tree.bind('<<TreeviewSelect>>', selected)
        buttons = ttk.Frame(self, padding=10)
        buttons.pack(fill='x')
        for label, accept in (('确认保存', True), ('返回修改', False), ('取消', False)):
            ttk.Button(buttons, text=label, command=lambda value=accept: self.finish(value)).pack(side='right', padx=5)
        self.protocol('WM_DELETE_WINDOW', lambda: self.finish(False))
        self.grab_set()

    def finish(self, accept):
        self.result = accept
        self.destroy()


class MasterPreview(tk.Toplevel):
    def __init__(self, parent, controller, changed):
        super().__init__(parent)
        self.controller, self.changed = controller, changed
        self.title('有效 MSI Master 检查与来源追溯')
        self.transient(parent)
        self.grab_set()
        self.geometry('1200x800')
        self.search, self.filter = tk.StringVar(), tk.StringVar(value='全部')
        self.summary = ttk.Label(self, wraplength=1150)
        self.summary.pack(fill='x', padx=10, pady=10)
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        ttk.Label(bar, text='搜索模块 / 信号').pack(side='left')
        ttk.Entry(bar, textvariable=self.search).pack(side='left')
        ttk.Combobox(bar, textvariable=self.filter, values=('全部', '通过', '警告', '错误'), state='readonly', width=8).pack(side='left')
        ttk.Button(bar, text='刷新检查', command=self.refresh).pack(side='left')
        ttk.Button(bar, text='导出本次 Master', command=self.export).pack(side='right')
        ttk.Button(bar, text='查看记录 / 人工修改差异', command=self.history).pack(side='right')
        ttk.Button(bar, text='备份人工版本并恢复自动版本', command=self.restore).pack(side='right')
        self.mapping = ttk.Treeview(self, columns=('module', 'book', 'sheet', 'column', 'source', 'status', 'master', 'changed'), show='headings', height=6)
        for col, label in zip(self.mapping['columns'], ('模块', '来源工作簿', '来源工作表', '引脚名称列', '文件状态', '映射状态', 'Master 工作表', '来源变化')):
            self.mapping.heading(col, text=label)
            self.mapping.column(col, width=130)
        self.mapping.pack(fill='x')
        self.mapping.bind('<<TreeviewSelect>>', self.select)
        self.signals = ttk.Treeview(self, show='headings', height=12)
        y = ttk.Scrollbar(self, orient='vertical', command=self.signals.yview)
        self.signals.configure(yscrollcommand=y.set)
        y.pack(side='right', fill='y')
        self.signals.pack(fill='both', expand=True)
        x = ttk.Scrollbar(self, orient='horizontal', command=self.signals.xview)
        x.pack(fill='x')
        self.signals.configure(xscrollcommand=x.set)
        self.issues = text_view(self, 5)
        self.search.trace_add('write', lambda *_: self.populate())
        self.filter.trace_add('write', lambda *_: self.populate())
        self.refresh()

    def refresh(self):
        self.report = self.controller.effective_msi_preview()
        state = (self.controller.workflow_draft or {}).get('msi_master', {})
        outdated = state.get('fingerprint') != self.report.fingerprint
        master_path = Path(state.get('path', ''))
        manual = master_path.is_file() and file_sha256(master_path) != state.get('sha256')
        outdated = outdated or manual
        errors = len(self.report.errors) + int(manual)
        warnings = sum(r['status'] == 'Warning' for r in self.report.issues)
        self.summary.configure(text=f"模块 {len(self.controller.active_config['modules'])} · 来源工作簿 {len({r['source_workbook'] for r in self.report.mappings})} · 有效工作表 {len(self.report.sheets)} · 映射完成 {len(self.report.mappings)} · 错误 {errors} · 警告 {warnings}\nMaster：{'待更新' if outdated else '与当前配置一致'} · 版本 {state.get('version', '未构建')} · SHA256 {state.get('sha256', '无')}\n生成任务会自动准备 Master；人工属性调整请录入第 9 节，不直接编辑自动工作簿。")
        self.manual = manual
        self.populate()

    def populate(self):
        self.mapping.delete(*self.mapping.get_children())
        search = self.search.get().casefold()
        wanted = {'通过': 'PASS', '警告': 'Warning', '错误': 'Error'}.get(self.filter.get())
        for module in [r['name'] for r in self.controller.active_config['modules']]:
            row = next((r for r in self.report.mappings if r['module'] == module), {})
            issues = [r for r in self.report.issues if r['module'] == module]
            status = 'Error' if any(i['status'] == 'Error' for i in issues) else ('Warning' if issues else 'PASS')
            if wanted and status != wanted:
                continue
            if search and search not in module.casefold() and not any(search in r['signal'].casefold() for r in self.report.signals.get(module, [])):
                continue
            self.mapping.insert('', 'end', iid=module, values=(module, row.get('source_workbook', ''), row.get('source_sheet', ''), row.get('column', ''), '可读' if row else '异常', {'PASS': '通过', 'Warning': '警告', 'Error': '错误'}[status], row.get('master_sheet', ''), '已变化' if row.get('changed') else '无变化'))
        self.issues.configure(state='normal')
        self.issues.delete('1.0', 'end')
        self.issues.insert('1.0', '\n'.join(f"{'错误' if r['status'] == 'Error' else '警告'}：{r['module']} / {r.get('sheet', '')} / {r.get('signal', '')}：{r['message']}" for r in self.report.issues) or '检查通过')
        if getattr(self, 'manual', False):
            self.issues.insert('end', '\n错误：Master 存在人工修改，生成已阻止。请查看差异并选择是否备份后恢复自动版本。')
        self.issues.configure(state='disabled')
        children = self.mapping.get_children()
        if children:
            self.mapping.selection_set(children[0])
        self.select()

    def select(self, _=None):
        self.signals.delete(*self.signals.get_children())
        selected = self.mapping.selection()
        if not selected:
            return
        rows = self.report.signals.get(selected[0], [])
        columns = list(dict.fromkeys(key for row in rows for key in row))
        self.signals.configure(columns=columns)
        labels = {'signal': '信号', 'original_power_domain': '原始供电域', 'effective_power_domain': '有效供电域', 'source_workbook': '来源工作簿', 'source_sheet': '来源工作表'}
        for key in columns:
            self.signals.heading(key, text=labels.get(key, key))  # Actual MSI protocol field names stay intact.
            self.signals.column(key, width=140)
        search = self.search.get().casefold()
        for row in rows:
            if not search or search in selected[0].casefold() or search in row['signal'].casefold():
                self.signals.insert('', 'end', values=[row.get(k, '') for k in columns])

    def history(self):
        state = (self.controller.workflow_draft or {}).get('msi_master', {})
        win = tk.Toplevel(self)
        win.title('Master 版本记录和差异')
        win.geometry('900x600')
        text = text_view(win)
        text.insert('1.0', json.dumps(state, ensure_ascii=False, indent=2))
        path = Path(state.get('path', ''))
        if path.is_file() and file_sha256(path) != state.get('sha256'):
            text.insert('end', '\n人工修改差异：\n' + workbook_diff(path, self.report))
        text.configure(state='disabled')

    def restore(self):
        self.history()
        if messagebox.askyesno('恢复可追溯自动版本', '请先核对差异。确认后将备份现有人工版本，并根据当前草稿重建自动版本；原始 MSI 不变。是否继续？', parent=self):
            try:
                self.controller.prepare_master(restore=True)
                self.changed()
                self.refresh()
            except Exception as exc:
                messagebox.showerror('恢复失败', str(exc), parent=self)

    def export(self):
        state = (self.controller.workflow_draft or {}).get('msi_master', {})
        path = Path(state.get('path', ''))
        if not path.is_file():
            messagebox.showinfo('尚未构建', '当前没有已构建 Master；启动生成任务时会自动构建。', parent=self)
            return
        if file_sha256(path) != state.get('sha256'):
            messagebox.showerror('Master 已变化', '当前文件与已记录 Hash 不一致，请先查看差异。', parent=self)
            return
        target = filedialog.asksaveasfilename(parent=self, initialfile='MSI_Master.xlsx', defaultextension='.xlsx')
        if target:
            resolved = Path(target).resolve()
            protected = {Path(row['source_workbook']).resolve() for row in self.report.mappings}
            if resolved in protected or resolved == path.resolve():
                messagebox.showerror('禁止覆盖输入', '请选择其他位置；原始 MSI 和本次实际使用的 Master 均不可覆盖。', parent=self)
                return
            shutil.copyfile(path, target)
