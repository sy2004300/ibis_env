"""Inline Section 4–10 views. Every keystroke belongs to the controller draft."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog
from .configuration_review import append_diagnostics
from .errors import UIProjectError
from .template_selection import effective_template_id

COLUMNS = {
    'simulation_options': [('text', '仿真选项原文')],
    'aliases': [('module', '模块'), ('direction', '方向'), ('original_pin', '原始引脚'), ('alias', '引脚别名')],
    'appends': [('module', '模块'), ('direction', '方向'), ('body', '追加电路正文（保留换行）')],
    'overrides': [('module', '模块'), ('direction', '方向'), ('corner', '工艺角'), ('signal', '信号'), ('value', '覆盖值')],
    'attribute_overrides': [('module', '模块'), ('signal', '信号'), ('attribute', '属性'), ('value', '覆盖值')],
    'msi_mappings': [('module', '模块'), ('file', '来源工作簿'), ('sheet', '来源工作表'), ('column', '引脚名称列')],
}


class InlineRows(ttk.Frame):
    def __init__(self, parent, controller, field, changed):
        super().__init__(parent)
        self.controller, self.field, self.changed = controller, field, changed
        self.variables, self.bodies = [], {}
        self.cells = ttk.Frame(self)
        self.cells.pack(fill='x')
        self.error = ttk.Label(self, foreground='#b42318', wraplength=1100)
        self.error.pack(fill='x')
        ttk.Button(self, text='新增配置行', command=self.add_row).pack(anchor='w')
        if field == 'msi_mappings':
            ttk.Button(self, text='扫描并补充唯一匹配', command=self.auto_map).pack(anchor='w')
        self.details = tk.Text(self, height=5, wrap='none', state='disabled') if field in {'appends', 'overrides', 'attribute_overrides', 'msi_mappings'} else None
        if self.details:
            self.details.pack(fill='x', pady=4)
        self.build(self.rows())

    def rows(self):
        rows = self.controller.active_config[self.field]
        if self.field == 'msi_mappings':
            try:
                report = self.controller.effective_msi_preview()
                existing = {row['module'].casefold() for row in rows}
                rows = [*rows, *[dict(module=r['module'], file=r['source_workbook'], sheet=r['source_sheet'], column=r['column']) for r in report.mappings if r['module'].casefold() not in existing]]
            except Exception:
                pass
        return [{'text': text} for text in rows] if self.field == 'simulation_options' else rows

    def values(self):
        return [{key: (self.bodies[i].get('1.0', 'end-1c') if key == 'body' else var.get()) for key, var in row.items()} for i, row in enumerate(self.variables)]

    def options(self, key, row):
        if key == 'module':
            return [m['name'] for m in self.controller.active_config['modules']]
        if key == 'direction':
            return ['DRV', 'RCV', 'BOTH']
        if key == 'corner':
            return ['MAX', 'TYP', 'MIN', 'ALL']
        if key == 'attribute':
            return ['POWER_DOMAIN']
        if self.field == 'msi_mappings':
            candidates = self.controller.msi_candidates()
            if key == 'file':
                return sorted(set(r['file'] for r in candidates))
            if key == 'sheet':
                return sorted(set(r['sheet'] for r in candidates if not row.get('file') or r['file'] == row['file']))
            if key == 'column':
                return list(dict.fromkeys(c for r in candidates if r['sheet'] == row.get('sheet') for c in r['columns']))
        return []

    def build(self, rows):
        for widget in self.cells.winfo_children():
            widget.destroy()
        self.variables, self.bodies = [], {}
        columns = COLUMNS[self.field]
        for col, (_, label) in enumerate(columns):
            ttk.Label(self.cells, text=label).grid(row=0, column=col, sticky='w')
            self.cells.columnconfigure(col, weight=1)
        for index, row in enumerate(rows):
            variables = {}
            for col, (key, _) in enumerate(columns):
                var = tk.StringVar(value=str(row.get(key, '')))
                variables[key] = var
                if key == 'body':
                    entry = tk.Text(self.cells, height=5, width=65, wrap='none', undo=True)
                    entry.insert('1.0', row.get(key, ''))
                    entry.edit_modified(False)
                    self.bodies[index] = entry
                    entry.bind('<<Modified>>', lambda _, w=entry: self.text_changed(w))
                else:
                    values = self.options(key, row)
                    if values or key in {'module', 'direction', 'corner', 'attribute', 'file', 'sheet', 'column'}:
                        entry = ttk.Combobox(self.cells, textvariable=var, values=values, width=15, state='readonly' if key in {'direction', 'corner', 'attribute'} else 'normal')
                        if self.field == 'msi_mappings':
                            entry.configure(postcommand=lambda w=entry, k=key, i=index: w.configure(values=self.options(k, self.values()[i])))
                    else:
                        entry = ttk.Entry(self.cells, textvariable=var, width=18)
                    var.trace_add('write', lambda *_: self.commit())
                entry.grid(row=index + 1, column=col, sticky='nsew', padx=2, pady=3)
            self.variables.append(variables)
            actions = ttk.Frame(self.cells)
            actions.grid(row=index + 1, column=len(columns), sticky='n')
            ttk.Button(actions, text='删除', width=5, command=lambda i=index: self.delete_row(i)).pack(side='left')
            if self.field == 'simulation_options':
                order = ttk.Spinbox(actions, from_=1, to=len(rows), width=4)
                order.set(index + 1)
                order.pack(side='left')
                ttk.Button(actions, text='移至行', command=lambda i=index, w=order: self.reorder(i, w.get())).pack(side='left')
        self.refresh_details()

    def text_changed(self, widget):
        if widget.edit_modified():
            widget.edit_modified(False)
            self.commit()

    def commit(self):
        rows = self.values()
        self.controller.replace_config_rows(self.field, [row['text'] for row in rows] if self.field == 'simulation_options' else rows)
        missing = [str(i + 1) for i, row in enumerate(rows) if any(not str(v).strip() for v in row.values())]
        self.error.configure(text=f"第 {', '.join(missing)} 行尚未填写完整，保存前请补全" if missing else '')
        self.changed()
        self.refresh_details()

    def add_row(self):
        row = {key: '' for key, _ in COLUMNS[self.field]}
        row.update({k: v for k, v in {'module': self.controller.active_config['modules'][0]['name'] if self.controller.active_config['modules'] else '', 'direction': 'BOTH', 'corner': 'ALL', 'attribute': 'POWER_DOMAIN'}.items() if k in row})
        self.build([*self.values(), row])
        self.commit()

    def delete_row(self, index):
        rows = self.values()
        del rows[index]
        self.build(rows)
        self.commit()

    def reorder(self, index, position):
        try:
            position = int(position) - 1
            rows = self.values()
            if not 0 <= position < len(rows):
                raise ValueError()
            rows.insert(position, rows.pop(index))
            self.build(rows)
            self.commit()
        except ValueError:
            self.error.configure(text='行号必须在现有行范围内')

    def auto_map(self):
        report = self.controller.effective_msi_preview()
        rows = self.values()
        existing = {row['module'] for row in rows}
        rows += [dict(module=r['module'], file=r['source_workbook'], sheet=r['source_sheet'], column=r['column']) for r in report.mappings if r['module'] not in existing]
        self.build(rows)
        self.commit()

    def refresh_details(self):
        if not self.details:
            return
        lines = []
        try:
            if self.field == 'appends':
                for row in self.rows():
                    nodes = []
                    try:
                        nodes = [r['effective_pin'] for r in self.controller.spf_interface_preview(row['module'], 'DRV' if row['direction'] == 'BOTH' else row['direction'])['pins']]
                    except UIProjectError as exc:
                        lines.append(f'节点提示：{exc}')
                    lines.append(f"适用：{row['module']} / {row['direction']}；有效节点：{', '.join(nodes)}\n最终追加内容：\n{row['body']}")
                    lines += [f"{'错误' if level == 'Error' else '警告'}：{msg}" for level, msg in append_diagnostics(row['body'], nodes)]
            else:
                report = self.controller.effective_msi_preview()
                if self.field == 'msi_mappings':
                    lines += [f"{r['module']}：匹配完成；{r['source_workbook']} / {r['source_sheet']} → {r['master_sheet']}" for r in report.mappings]
                else:
                    for row in self.rows():
                        signals = report.signals.get(row['module'], [])
                        signal = next((r for r in signals if r['signal'].casefold() == row['signal'].casefold()), {})
                        if self.field == 'attribute_overrides':
                            lines.append(f"{row['module']} / {row['signal']}：原始供电域={signal.get('original_power_domain', '未找到')}；覆盖={row['value']}；有效={signal.get('effective_power_domain', '待检查')}")
                        else:
                            from ibis_auto.msi import _columns
                            raw = {k: v for k, v in signal.items() if k not in {'signal', 'original_power_domain', 'effective_power_domain', 'source_workbook', 'source_sheet'}}
                            try:
                                header = list(raw)
                                original = raw[header[_columns(header)['default']]]
                            except (KeyError, IndexError):
                                original = '原始表未提供'
                            lines.append(f"{row['module']} / {row['direction']} / {row['corner']} / {row['signal']}：原始={original}；覆盖={row['value']}；该作用域有效值={row['value']}")
                lines += [f"{r['module']}：{r['message']}" for r in report.issues]
        except Exception as exc:
            lines.append(f'待完成配置后检查：{exc}')
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', '\n'.join(lines))
        self.details.configure(state='disabled')


class InlineTemplates(ttk.Frame):
    def __init__(self, parent, controller, changed):
        super().__init__(parent)
        self.controller, self.changed = controller, changed
        self.refresh()

    def refresh(self):
        for widget in self.winfo_children():
            widget.destroy()
        for i, label in enumerate(('模块', '方向', '模板类型', '来源选择', '实际生效路径')):
            ttk.Label(self, text=label).grid(row=0, column=i, sticky='w')
        index = 0
        for module in self.controller.active_config['modules']:
            for direction in (('DRV', 'RCV') if module['generate_type'] == 'BOTH' else (module['generate_type'],)):
                index += 1
                name = module['name']
                ttk.Label(self, text=name).grid(row=index, column=0, sticky='w')
                ttk.Label(self, text=direction).grid(row=index, column=1)
                combo = ttk.Combobox(self, state='readonly', values=[x.template_id for x in self.controller.templates.selectable(direction)], width=20)
                combo.set(effective_template_id(self.controller.active_config, name, direction))
                combo.grid(row=index, column=2, sticky='ew')
                combo.bind('<<ComboboxSelected>>', lambda _, m=name, d=direction, w=combo: self.select_type(m, d, w.get()))
                info = self.controller.template_origin(name, direction)
                source = ttk.Combobox(self, state='readonly', values=('内置母模板', '外部模板', '项目自定义模板'), width=16)
                source.set(info['kind'])
                source.grid(row=index, column=3)
                source.bind('<<ComboboxSelected>>', lambda _, m=name, d=direction, w=source: self.select_source(m, d, w.get()))
                ttk.Label(self, text=info['path'], wraplength=500).grid(row=index, column=4, sticky='w')
        self.columnconfigure(4, weight=1)

    def select_type(self, module, direction, value):
        self.controller.update_template(module, direction, value)
        from .template_selection import definition
        path = self.controller.effective_template_root() / definition(value).filename
        self.controller.set_template_source(module, direction, "外部模板" if self.controller.template_override() else "内置母模板", str(path) if self.controller.template_override() else "")
        self.changed()
        self.refresh()

    def select_source(self, module, direction, kind):
        path = filedialog.askopenfilename(parent=self, title='选择外部 T2B 模板', filetypes=[('T2B 模板', '*.t2b')]) if kind == '外部模板' else ''
        if kind == '外部模板' and not path:
            self.refresh()
            return
        try:
            self.controller.set_template_source(module, direction, kind, path)
            self.changed()
        except UIProjectError as exc:
            from tkinter import messagebox
            messagebox.showerror('模板来源不可用', str(exc), parent=self)
        self.refresh()
