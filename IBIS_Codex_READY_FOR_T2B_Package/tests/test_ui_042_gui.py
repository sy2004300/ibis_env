"""Real Tk event-loop checks; no DISPLAY means explicit skip, never GUI PASS."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from ibis_ui.controller import ProjectController
from ibis_ui.project_store import ProjectStore
from ibis_ui.runtime import ResourceResolver
from ibis_ui.view import IBISApplicationView
from ibis_ui.review_dialogs import SaveReview, MasterPreview

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'demo_phy_io_diff'


@unittest.skipUnless(os.environ.get('DISPLAY') or sys.platform == 'win32', '真实 GUI 测试需要图形显示环境')
class UI042GUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = ProjectController(ProjectStore(Path(self.tmp.name)), resources=ResourceResolver(ROOT))
        self.c.import_excel(ROOT / 'inputs/config/ibis_config.xlsx')
        self.c.save_project_draft()
        self.v = IBISApplicationView(self.c)
        self.addCleanup(self.v.destroy)
        self.errors = []
        self.v.report_callback_exception = lambda *args: self.errors.append(args)
        self.v.update()

    def answer_review(self, accept):
        def answer():
            dialog = next((w for w in self.v.winfo_children() if isinstance(w, SaveReview)), None)
            if dialog:
                self.review_shown = True
                dialog.finish(accept)
            else:
                self.v.after(20, answer)
        self.review_shown = False
        self.v.after(20, answer)

    def test_all_sections_inline_add_edit_delete_and_fold_preserve(self):
        self.v.notebook.select(self.v.config_tab)
        for field in ('simulation_options', 'aliases', 'appends', 'overrides', 'attribute_overrides', 'msi_mappings'):
            widget = self.v.inline_sections[field]
            count = len(widget.variables)
            widget.add_row()
            self.assertEqual(len(self.c.active_config[field]), count + 1)
            widget.delete_row(count)
            self.assertEqual(len(self.c.active_config[field]), count)
        widget = self.v.inline_sections['simulation_options']
        widget.variables[0]['text'].set('.option custom=123')
        section = next(s for s in self.v._config_sections if '第 4 节' in s.title)
        section.toggle()
        section.toggle()
        self.v.notebook.select(self.v.t2b_tab)
        self.v.update()
        self.v.notebook.select(self.v.config_tab)
        self.v.update()
        self.assertEqual(widget.variables[0]['text'].get(), '.option custom=123')
        self.assertEqual(self.c.active_config['simulation_options'][0], '.option custom=123')
        self.assertFalse(self.errors, self.errors)

    def test_cancel_diff_preserves_draft_and_confirm_persists(self):
        widget = self.v.inline_sections['simulation_options']
        widget.variables[0]['text'].set('.option method=trap')
        self.answer_review(False)
        self.assertFalse(self.v._save_with_review())
        self.assertTrue(self.review_shown)
        self.assertTrue(self.c.has_unsaved_changes)
        self.assertEqual(self.c.project.config['simulation_options'][0], '.option method=gear')
        self.answer_review(True)
        self.assertTrue(self.v._save_with_review())
        self.assertEqual(self.c.project.config['simulation_options'][0], '.option method=trap')
        with patch('ibis_ui.view.SaveReview', side_effect=AssertionError('无修改不弹窗')):
            self.assertTrue(self.v._save_with_review())

    def test_body_text_preserved_and_order_control(self):
        options = self.v.inline_sections['simulation_options']
        old = list(self.c.active_config['simulation_options'])
        options.reorder(0, 2)
        self.assertEqual(self.c.active_config['simulation_options'], old[::-1])
        appends = self.v.inline_sections['appends']
        appends.add_row()
        i = len(appends.variables) - 1
        body = '* exact spaces\nRtest  VDD 0 1k\n'
        appends.bodies[i].insert('1.0', body)
        self.v.update()
        self.assertEqual(self.c.active_config['appends'][i]['body'], body)
        self.assertFalse(self.errors, self.errors)

    def test_template_source_shared_between_inline_and_preview(self):
        source = self.c.template_source(MODULE, 'DRV')
        path = Path(self.tmp.name) / 'external.t2b'
        path.write_text(source.replace('[Source] Akrostar', '[Source] Shared'), encoding='utf-8')
        widget = self.v.inline_sections['templates']
        with patch('ibis_ui.inline_sections.filedialog.askopenfilename', return_value=str(path)):
            widget.select_source(MODULE, 'DRV', '外部模板')
        self.v.notebook.select(self.v.t2b_tab)
        self.v.update()
        self.assertIn('Shared', self.v.template_panel.text.get('1.0', 'end'))
        self.assertIn(str(path.resolve()), self.v.template_panel.source_label.cget('text'))
        self.assertTrue(self.c.has_unsaved_changes)
        self.assertFalse(self.errors, self.errors)

    def test_master_preview_search_filter_actual_signal_fields(self):
        dialog = MasterPreview(self.v, self.c, self.v._sections_changed)
        self.addCleanup(dialog.destroy)
        self.v.update()
        self.assertEqual(len(dialog.mapping.get_children()), 1)
        dialog.search.set('reg_txffe')
        self.v.update()
        self.assertEqual(len(dialog.signals.get_children()), 1)
        dialog.filter.set('错误')
        self.v.update()
        self.assertEqual(len(dialog.mapping.get_children()), 0)
        dialog.filter.set('全部')
        dialog.search.set('')
        self.v.update()
        self.assertGreater(len(dialog.signals.get_children()), 1)
        self.assertFalse(self.errors, self.errors)

    def test_generate_automatically_prepares_master(self):
        self.assertFalse(self.c.project.workflow['msi_master']['path'])
        with patch('ibis_ui.view.messagebox.askyesno', return_value=True):
            self.v._start_generation([(MODULE, 'DRV', 30)])
        deadline = time.monotonic() + 20
        while self.v._generation_running and time.monotonic() < deadline:
            self.v.update()
            time.sleep(.01)
        self.assertFalse(self.v._generation_running)
        self.assertTrue(Path(self.c.project.workflow['msi_master']['path']).is_file())
        self.assertEqual(self.v.generation_tree.item(self.v.generation_tree.get_children()[0], 'values')[3], '通过')
        self.assertFalse(self.errors, self.errors)

    def test_navigation_cancel_keeps_draft(self):
        self.v.inline_sections['simulation_options'].variables[0]['text'].set('.option new=1')
        with patch('ibis_ui.view.messagebox.askyesnocancel', return_value=None):
            self.assertFalse(self.v._confirm_leave_current())
        self.assertTrue(self.c.has_unsaved_changes)
        with patch('ibis_ui.view.messagebox.askyesnocancel', return_value=True):
            self.answer_review(False)
            self.assertFalse(self.v._confirm_leave_current())
        self.assertEqual(self.c.active_config['simulation_options'][0], '.option new=1')
