"""VNext configuration page inside the existing Tk application (no second UI)."""
from __future__ import annotations
import copy
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from ..widgets import ScrollableFrame
from ..errors import UIProjectError
from .excel import TABLES
from .model import CORNERS, SOURCES, directions, parse_rons

LABELS = {'modules':'模块计划', 'corners':'全局 Corner / Tr / Tf', 'voltages':'电压值（需填写）', 'signals':'全局信号默认值（可留空）', 'pins':'IBIS Pin 映射（仅 T2B [Pin]）', 'appends':'追加电路（可留空）', 'overrides':'模块信号覆盖（空白继承）', 'msi_mappings':'MSI 来源映射'}
COLUMNS = {key: columns for key, (_, columns) in TABLES.items()}
COLUMNS.update(corners=[('parameter','参数')]+[(c,c) for c in CORNERS], voltages=[('domain','Domain')]+[(c,c) for c in CORNERS], signals=[('signal','Signal')]+[(c,c) for c in CORNERS])
CORNER_FIELDS = [('process','Process'), ('temperature','Temperature (°C)'), ('tr','Tr'), ('tf','Tf'), ('spf_key','SPF Match Key')]


class TableEditor(ttk.Frame):
    def __init__(self, parent, panel, section):
        super().__init__(parent)
        self.panel, self.section = panel, section
        self.columns = COLUMNS[section]
        self.editor = None
        self.tree = ttk.Treeview(self, columns=[k for k, _ in self.columns], show='headings', height=4)
        for key, title in self.columns:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=135 if key not in ('file','body') else 270, minwidth=70)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.columnconfigure(0, weight=1)
        self.tree.bind('<Double-1>', self.edit_click)
        self.tree.bind('<Return>', lambda e: self.edit_selected())
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky='w')
        ttk.Label(bar, text='双击单元格编辑；回车确认').pack(side='left', padx=4)
        if section not in ('corners','pins','msi_mappings'):
            ttk.Button(bar, text='新增行', command=self.add).pack(side='left')
        if section != 'corners':
            ttk.Button(bar, text='删除选中行', command=self.delete).pack(side='left')
        if section in ('pins','msi_mappings'):
            ttk.Button(bar, text='核对后确认映射', command=self.confirm).pack(side='left')

    def rows(self):
        if self.section == 'corners':
            return [dict(parameter=label, **{c:self.panel.data['corners'][c][key] for c in CORNERS}) for key,label in CORNER_FIELDS]
        return self.panel.data[self.section]

    def refresh(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        rows = self.rows()
        self.tree.configure(height=max(2, min(7, len(rows))))
        for i, row in enumerate(rows):
            self.tree.insert('', 'end', iid=str(i), values=[row.get(k,'') for k,_ in self.columns])
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])

    def add(self):
        self.panel.flush()
        self.panel.data[self.section].append({k:'' for k,_ in self.columns})
        self.panel.changed()
        self.refresh()
        self.edit_cell(len(self.rows())-1, self.columns[0][0])

    def delete(self):
        selected = self.tree.selection()
        if selected:
            self.panel.flush()
            del self.panel.data[self.section][int(selected[0])]
            self.panel.changed()

    def confirm(self):
        self.panel.flush()
        for index in self.tree.selection():
            row = self.rows()[int(index)]
            row['status'] = 'MANUAL'
            row['fingerprint'] = row.get('current_fingerprint','')
        self.panel.changed()

    def edit_click(self, event):
        row, col = self.tree.identify_row(event.y), self.tree.identify_column(event.x)
        if row and col and col != '#0':
            self.edit_cell(int(row), self.columns[int(col[1:])-1][0])

    def edit_selected(self):
        if self.tree.selection():
            self.edit_cell(int(self.tree.selection()[0]), self.columns[0][0])

    def edit_cell(self, index, field):
        if self.section == 'corners' and field == 'parameter':
            return
        if self.section in ('pins','msi_mappings') and field in ('module','direction','t2b_pin','status'):
            return
        self.panel.flush()
        self.tree.see(str(index))
        self.update_idletasks()
        box = self.tree.bbox(str(index), field)
        if not box:
            return
        row = self.rows()[index]
        value = str(row.get(field,''))
        if field == 'body':
            window = tk.Toplevel(self)
            window.title('编辑追加 SPICE（空白表示不追加）')
            widget = tk.Text(window, width=90, height=16)
            widget.pack(fill='both', expand=True)
            widget.insert('1.0',value)
            def commit():
                self.set_value(index,field,widget.get('1.0','end-1c'))
                window.destroy()
            ttk.Button(window,text='应用',command=commit).pack()
            window.transient(self.winfo_toplevel())
            window.grab_set()
            return
        options = self.panel.options(self.section,index,field)
        var = tk.StringVar(value=value)
        widget = ttk.Combobox(self.tree,textvariable=var,values=options) if options else ttk.Entry(self.tree,textvariable=var)
        widget.place(x=box[0],y=box[1],width=max(box[2],90),height=box[3])
        self.editor = (widget,var,index,field,value)
        widget.bind('<Return>',lambda e:self.flush())
        widget.bind('<FocusOut>',lambda e:self.flush())
        widget.bind('<<ComboboxSelected>>',lambda e:self.flush())
        widget.bind('<Escape>',lambda e:self.cancel())
        widget.focus_set()
        widget.selection_range(0,'end')

    def cancel(self):
        if self.editor:
            widget = self.editor[0]
            self.editor = None
            widget.destroy()

    def flush(self):
        if not self.editor:
            return
        widget,var,index,field,old = self.editor
        value = var.get()
        self.editor = None
        widget.destroy()
        if value != old:
            self.set_value(index,field,value)

    def set_value(self,index,field,value):
        if self.section == 'corners':
            self.panel.data['corners'][field][CORNER_FIELDS[index][0]] = value.strip()
        else:
            row = self.panel.data[self.section][index]
            row[field] = value if field=='body' else value.strip()
            if self.section in ('pins','msi_mappings'):
                row.update(status='MANUAL',fingerprint='')
        self.panel.changed()
        self.refresh()


class VNextPanel(ttk.Frame):
    def __init__(self,parent,controller,host):
        super().__init__(parent)
        self.controller,self.host = controller,host
        self.data = copy.deepcopy(controller.active_config['vnext'])
        self.pending = None
        self.busy = False
        self.events = queue.Queue()
        self.editors, self.sections, self.source_vars, self.source_entries = {}, {}, {}, {}
        header = ttk.Frame(self,padding=6)
        header.pack(fill='x')
        self.summary = ttk.Label(header,text='自动检查中…')
        self.summary.pack(side='left',fill='x',expand=True)
        self.generate_button = ttk.Button(header,text='Generate T2B',command=self.generate)
        self.generate_button.pack(side='right')
        ttk.Button(header,text='重新检查',command=self.check).pack(side='right',padx=6)
        layout = ttk.Panedwindow(self,orient='horizontal')
        layout.pack(fill='both',expand=True)
        left = ttk.Frame(layout,width=220)
        right = ttk.Frame(layout)
        layout.add(left,weight=1)
        layout.add(right,weight=4)
        ttk.Label(left,text='IO Top → DRV / RCV → Ron').pack(anchor='w',padx=5)
        self.task_tree = ttk.Treeview(left,show='tree',selectmode='browse')
        self.task_tree.pack(fill='both',expand=True)
        self.task_tree.column('#0',width=210)
        self.task_tree.bind('<<TreeviewSelect>>',self.task_selected)
        self.task_keys = {}
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill='both',expand=True)
        self.config = ScrollableFrame(self.notebook)
        self.notebook.add(self.config,text='参数与映射')
        issue_frame = ttk.Frame(self.notebook)
        self.notebook.add(issue_frame,text='待填写 / 待修正')
        self.issue_tree = self.make_tree(issue_frame, ['severity','code','module','direction','corner','field','location','message'], ['级别','类别','模块','方向','Corner','字段','文件 / Sheet','原因'])
        self.issue_tree.column('message',width=400)
        self.issue_tree.column('location',width=300)
        self.issue_tree.bind('<<TreeviewSelect>>',self.locate_issue)
        # A compact issue list is also always visible above the editor.
        self.issue_link = ttk.Button(self.config.body,text='查看待修正项',command=lambda:self.notebook.select(issue_frame))
        self.issue_link.pack(fill='x',pady=(0,8))
        sources = self.section('sources','输入来源（目录或文件；T2B 留空使用内置）')
        for index,(label,key) in enumerate(SOURCES.items()):
            ttk.Label(sources,text=label).grid(row=index,column=0,sticky='w')
            var = tk.StringVar(value=self.data['sources'][key])
            entry = ttk.Entry(sources,textvariable=var)
            entry.grid(row=index,column=1,sticky='ew',padx=4,pady=3)
            entry.bind('<FocusOut>',lambda e,k=key:self.source_changed(k))
            entry.bind('<Return>',lambda e,k=key:self.source_changed(k))
            self.source_vars[key],self.source_entries[key] = var,entry
            ttk.Button(sources,text='目录…',command=lambda k=key:self.browse(k,True)).grid(row=index,column=2)
            ttk.Button(sources,text='文件…',command=lambda k=key:self.browse(k,False)).grid(row=index,column=3)
        sources.columnconfigure(1,weight=1)
        for key in ('modules','corners','voltages','signals','pins','appends','overrides','msi_mappings'):
            body = self.section(key,LABELS[key])
            editor = TableEditor(body,self,key)
            editor.pack(fill='both',expand=True)
            self.editors[key] = editor
        preview_frame = ttk.Frame(self.notebook)
        self.notebook.add(preview_frame,text='填参 T2B 预览')
        self.case_choice = ttk.Combobox(preview_frame,state='readonly')
        self.case_choice.pack(fill='x')
        self.case_choice.bind('<<ComboboxSelected>>',lambda e:self.show_preview())
        self.preview_text = self.textbox(preview_frame)
        results_frame = ttk.Frame(self.notebook)
        self.notebook.add(results_frame,text='生成结果')
        self.results = self.make_tree(results_frame,['key','status','message','output_path'],['Case','状态','原因','输出目录'])
        self.results.bind('<Double-1>',self.open_result)
        ttk.Label(results_frame,text='双击已生成的 Case 查看文件；仅准备 Stage 1 环境，不执行真实仿真。').pack()
        logs = ttk.Frame(self.notebook)
        self.notebook.add(logs,text='运行日志')
        self.log_text = self.textbox(logs)
        self.refresh()

    @staticmethod
    def textbox(parent):
        frame = ttk.Frame(parent)
        frame.pack(fill='both',expand=True)
        text = tk.Text(frame,wrap='none',state='disabled')
        text.grid(row=0,column=0,sticky='nsew')
        for orient,row,col,command in [('vertical',0,1,text.yview),('horizontal',1,0,text.xview)]:
            bar = ttk.Scrollbar(frame,orient=orient,command=command)
            bar.grid(row=row,column=col,sticky='ns' if orient=='vertical' else 'ew')
            text.configure(**{('yscrollcommand' if orient=='vertical' else 'xscrollcommand'):bar.set})
        frame.columnconfigure(0,weight=1)
        frame.rowconfigure(0,weight=1)
        return text

    @staticmethod
    def make_tree(parent,columns,headings):
        frame = ttk.Frame(parent)
        frame.pack(fill='both',expand=True)
        tree = ttk.Treeview(frame,columns=columns,show='headings')
        for key,label in zip(columns,headings):
            tree.heading(key,text=label)
            tree.column(key,width=130)
        tree.grid(row=0,column=0,sticky='nsew')
        for orient,row,col,command in [('vertical',0,1,tree.yview),('horizontal',1,0,tree.xview)]:
            bar = ttk.Scrollbar(frame,orient=orient,command=command)
            bar.grid(row=row,column=col,sticky='ns' if orient=='vertical' else 'ew')
            tree.configure(**{('yscrollcommand' if orient=='vertical' else 'xscrollcommand'):bar.set})
        frame.columnconfigure(0,weight=1)
        frame.rowconfigure(0,weight=1)
        return tree

    def section(self,key,title):
        frame = ttk.Frame(self.config.body)
        frame.pack(fill='x',pady=5)
        body = ttk.Frame(frame,padding=6)
        def toggle():
            if body.winfo_manager():
                body.pack_forget()
                button.configure(text='▶ '+title)
            else:
                body.pack(fill='x')
                button.configure(text='▼ '+title)
        button = ttk.Button(frame,text='▼ '+title,command=toggle)
        button.pack(fill='x')
        body.pack(fill='x')
        self.sections[key] = (frame,body,button,title)
        return body

    def options(self,section,index,field):
        data = self.data
        if section=='corners':
            key = CORNER_FIELDS[index][0]
            return ['FF','FS','SF','SS','TT'] if key=='process' else (['125','25','-40'] if key=='temperature' else [])
        row = data[section][index]
        if field=='generate_type': return ['DRV','RCV','BOTH']
        if field=='topology': return ['SE','DIFF']
        if field in ('io_domain','vih_domain'): return [r['domain'] for r in data['voltages']]
        if field=='direction': return ['DRV','RCV']
        if field=='module': return [r['name'] for r in data['modules']]
        if field=='spf_pin': return data['resolved'].get('spf',{}).get(row['module'],{}).get('pins',[])
        if field=='signal':
            if section=='signals':
                return sorted({s['name'] for signals in data['resolved'].get('msi',{}).values() for s in signals})
            return [s['name'] for s in data['resolved'].get('msi',{}).get(row.get('module',''),[])]
        candidates = data['resolved'].get('candidates',[])
        if field=='file': return list(dict.fromkeys(r['file'] for r in candidates))
        if field=='sheet': return list(dict.fromkeys(r['sheet'] for r in candidates if r['file']==row.get('file')))
        if field=='column': return list(dict.fromkeys(h for r in candidates if r['file']==row.get('file') and r['sheet']==row.get('sheet') for h in r['headers']))
        return []

    def source_changed(self,key):
        value = self.source_vars[key].get().strip()
        if value != self.data['sources'].get(key):
            self.data['sources'][key] = value
            self.changed()

    def browse(self,key,directory):
        selected = filedialog.askdirectory(parent=self,title='选择来源目录') if directory else filedialog.askopenfilename(parent=self,title='选择来源文件')
        if selected:
            self.source_vars[key].set(selected)
            self.source_changed(key)

    def flush(self):
        for editor in self.editors.values():
            editor.flush()
        for key in self.source_vars:
            self.source_changed(key)

    def changed(self):
        from .model import payload
        self.controller.draft = payload(self.data)
        self.generate_button.configure(state='disabled')
        self.host._refresh_status()
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(650,self.check)

    def check(self):
        self.flush()
        if self.pending:
            self.after_cancel(self.pending)
            self.pending = None
        try:
            self.data = self.controller.recheck_vnext(self.data)
            self.refresh()
            self.host._refresh_status()
        except Exception as exc:
            self.generate_button.configure(state='disabled')
            self.summary.configure(text='检查失败：'+str(exc))
            self.log('检查失败：'+str(exc))

    def refresh(self):
        self.data = copy.deepcopy(self.controller.active_config['vnext'])
        for key,var in self.source_vars.items():
            var.set(self.data['sources'].get(key,''))
        for editor in self.editors.values(): editor.refresh()
        issues = self.data.get('issues',[])
        count = sum(r['severity']=='BLOCKING' for r in issues)
        message = '阻断 %d 项 / 警告 %d 项；未完成配置也可导出 Excel。' % (count,len(issues)-count)
        self.summary.configure(text=message)
        self.issue_link.configure(text=message+' 点击定位待修正项')
        self.generate_button.configure(state='disabled' if count or self.busy else 'normal')
        self.issue_tree.delete(*self.issue_tree.get_children())
        for i,row in enumerate(issues):
            self.issue_tree.insert('','end',iid=str(i),values=[('阻断' if row[k]=='BLOCKING' else '警告') if k=='severity' else row.get(k,'') for k in ('severity','code','module','direction','corner','field','location','message')])
        self.case_keys = []
        for module in self.data['modules']:
            try: rons = parse_rons(module.get('ron',''))
            except ValueError: continue
            self.case_keys.extend((module['name'],d,r) for d in directions(module) for r in rons)
        self.task_tree.delete(*self.task_tree.get_children())
        self.task_keys = {}
        for module in self.data['modules']:
            parent = self.task_tree.insert('','end',text=module.get('name') or '待填写模块',open=True)
            for d in directions(module):
                child = self.task_tree.insert(parent,'end',text=d,open=True)
                for key in self.case_keys:
                    if key[:2] == (module['name'],d):
                        item = self.task_tree.insert(child,'end',text=str(key[2])+'Ω')
                        self.task_keys[item] = key
        self.case_choice.configure(values=['%s / %s / %sΩ'%key for key in self.case_keys])
        if self.case_keys and self.case_choice.current() < 0: self.case_choice.current(0)
        self.results.delete(*self.results.get_children())
        for row in self.controller.generation_statuses():
            self.results.insert('','end',values=[row.get(k,'') for k in ('key','status','message','output_path')])
        self.show_preview()

    def task_selected(self,event=None):
        selection = self.task_tree.selection()
        if selection and selection[0] in self.task_keys:
            key = self.task_keys[selection[0]]
            self.case_choice.current(self.case_keys.index(key))
            self.show_preview()
            self.notebook.select(2)

    def locate_issue(self,event=None):
        selected = self.issue_tree.selection()
        if not selected: return
        issue = self.data['issues'][int(selected[0])]
        key = issue['section']
        if key not in self.sections: return
        frame,body,button,title = self.sections[key]
        body.pack(fill='x')
        button.configure(text='▼ '+title)
        self.notebook.select(self.config)
        self.update_idletasks()
        self.config.canvas.yview_moveto(frame.winfo_y()/max(1,self.config.body.winfo_height()))
        if key=='sources':
            entry = self.source_entries.get(issue['field'])
            if entry: entry.focus_set()
            return
        editor = self.editors[key]
        index = issue.get('row',0)
        if key=='corners':
            index = next((i for i,(field,_) in enumerate(CORNER_FIELDS) if field==issue['field']),0)
            field = issue.get('corner') or 'MAX'
        else: field = issue.get('field') or editor.columns[0][0]
        if index < len(editor.rows()):
            editor.tree.selection_set(str(index))
            if field in [k for k,_ in editor.columns]: editor.edit_cell(index,field)

    def show_preview(self):
        index = self.case_choice.current()
        text = '请选择有效 Case。'
        if 0 <= index < len(self.case_keys):
            try:
                from .service import preview
                text = preview(self.data,self.case_keys[index])
            except Exception as exc:
                text = '配置尚未通过检查，不能显示有效填参结果。\n'+str(exc)
        self.set_text(self.preview_text,text)

    @staticmethod
    def set_text(widget,text):
        widget.configure(state='normal')
        widget.delete('1.0','end')
        widget.insert('1.0',text)
        widget.configure(state='disabled')

    def log(self,message):
        self.log_text.configure(state='normal')
        self.log_text.insert('end',message+'\n')
        self.log_text.configure(state='disabled')

    def generate(self):
        if self.busy: return
        self.check()
        if any(r['severity']=='BLOCKING' for r in self.data['issues']):
            messagebox.showwarning('尚不能生成','请先修正阻断项；当前配置仍可导出 Excel。',parent=self)
            return
        try:
            self.controller.save_configuration()
        except Exception as exc:
            messagebox.showerror('保存失败',str(exc),parent=self)
            return
        self.busy = self.host._generation_running = True
        self.generate_button.configure(state='disabled')
        # Generate from a snapshot. Block edits/navigation until completion to
        # avoid a worker overwriting a newer draft or another active project.
        self.cancel_event = threading.Event()
        self.progress_window = tk.Toplevel(self)
        self.progress_window.title('正在生成 Stage 1 文件')
        self.progress_window.transient(self.host)
        ttk.Label(self.progress_window,text='正在检查并生成，请等待当前 Case 完成。',padding=20).pack()
        ttk.Button(self.progress_window,text='取消后续任务',command=self.cancel_event.set).pack(pady=10)
        self.progress_window.protocol('WM_DELETE_WINDOW',self.cancel_event.set)
        self.progress_window.grab_set()
        def work():
            try:
                result = self.controller.generate_cases(cancel_requested=self.cancel_event.is_set, progress=lambda key,status,msg:self.events.put(('progress',key+' '+status+' '+msg)))
                self.events.put(('done',result))
            except Exception as exc:
                self.events.put(('error',exc))
        threading.Thread(target=work,daemon=True).start()
        self.after(100,self.poll)

    def poll(self):
        finished = False
        while not self.events.empty():
            kind,value = self.events.get()
            if kind=='progress': self.log(value)
            else:
                finished = True
                self.busy = self.host._generation_running = False
                self.progress_window.grab_release()
                self.progress_window.destroy()
                self.controller.draft = self.controller.project.clone_config()
                self.refresh()
                self.host._refresh_status()
                if kind=='error':
                    self.log('生成失败：'+str(value))
                    messagebox.showerror('生成失败',str(value),parent=self)
                else:
                    self.notebook.select(3)
                    self.log('READY_FOR_T2B '+('已准备；结构通过，无对应 Golden 的 Case 标记 UNVALIDATED' if value.ready else '未完成，请查看错误原因'))
        if not finished: self.after(100,self.poll)

    def open_result(self,event=None):
        selected = self.results.selection()
        if not selected: return
        values = self.results.item(selected[0],'values')
        directory = Path(values[3]) if len(values)>3 and values[3] else None
        if not directory or not directory.is_dir():
            messagebox.showinfo('尚无输出','该 Case 尚未成功生成。',parent=self)
            return
        window = tk.Toplevel(self)
        window.title('生成文件：'+str(directory))
        window.geometry('1000x650')
        combo = ttk.Combobox(window,state='readonly',values=[p.name for p in sorted(directory.iterdir()) if p.is_file()])
        combo.pack(fill='x')
        text = self.textbox(window)
        combo.bind('<<ComboboxSelected>>',lambda e:self.set_text(text,(directory/combo.get()).read_text(encoding='utf-8',errors='replace')))
        if combo['values']:
            combo.current(0)
            combo.event_generate('<<ComboboxSelected>>')

    def destroy(self):
        if self.pending:
            self.after_cancel(self.pending)
            self.pending = None
        super().destroy()
