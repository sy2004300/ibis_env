"""Real Tk tests. Linux requires DISPLAY/Xvfb; Windows runs on its desktop."""
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
from ibis_ui.editor_dialogs import TemplateEditorDialog

ROOT = Path(__file__).resolve().parents[1]
MODULE = "demo_phy_io_diff"
KEY = (MODULE, "DRV", 30)


@unittest.skipUnless(os.environ.get("DISPLAY") or sys.platform == "win32", "真实 GUI 测试需要 DISPLAY；Headless 不计作 GUI PASS")
class UI041GUIRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = ProjectController(ProjectStore(Path(self.tmp.name) / "workspace"), resources=ResourceResolver(ROOT))
        self.c.import_excel(ROOT / "inputs/config/ibis_config.xlsx")
        self.c.save_project_draft()
        self.view = IBISApplicationView(self.c)
        self.addCleanup(self.view.destroy)
        self.callback_errors = []
        self.view.report_callback_exception = lambda *args: self.callback_errors.append(args)
        self.view.update()

    def pump_until_done(self):
        deadline = time.monotonic() + 30
        while self.view._generation_running and time.monotonic() < deadline:
            self.view.update()
            time.sleep(0.02)
        self.view.update()
        self.assertFalse(self.view._generation_running, "生成仍停留在等待状态")
        self.assertFalse(self.callback_errors, self.callback_errors)

    def test_collapsible_inline_fields_and_case_preview(self):
        v = self.view
        v.notebook.select(v.config_tab)
        section = v._config_sections[1]
        tr = v._module_vars["tr.TYP"]
        tr.set("35p")
        v._module_changed("tr.TYP")
        section.toggle()
        v.update()
        self.assertFalse(section.body.winfo_ismapped())
        section.toggle()
        v.update()
        self.assertEqual(tr.get(), "35p")
        self.assertTrue(section.body.winfo_ismapped())
        voltage = next(row for row in v.voltage_table.variables if row["domain"].get() == "VDDQ")
        voltage["TYP"].set("0.55")
        self.assertEqual(self.c.active_config["corners"]["TYP"]["voltages"]["VDDQ"], "0.55")
        cal = v.calibration_table.variables[0]
        cal["TYP"].set("8'h35")
        self.assertEqual(self.c.active_config["corners"]["TYP"]["calibration"][cal["signal"].get()], "8'h35")
        with patch("ibis_ui.view.SaveReview", wraps=__import__("ibis_ui.review_dialogs", fromlist=["SaveReview"]).SaveReview) as review:
            v.after(100, lambda: next(w for w in v.winfo_children() if w.winfo_class() == "Toplevel").finish(True))
            v._save()
        v.template_panel.refresh()
        self.assertIn("35p", v.template_panel.text.get("1.0", "end"))
        self.assertIn("0.55", v.template_panel.text.get("1.0", "end"))
        self.assertFalse(self.callback_errors)

    def test_actual_generate_button_has_one_terminal_row_and_seven_files(self):
        v = self.view
        self.c.update_module(MODULE, "generate_type", "BOTH")
        self.c.save_project_draft()
        v._refresh_all()
        self.assertEqual(v.results_tree.item(v.results_tree.get_children()[0], "values")[4], "0")
        with patch("ibis_ui.view.messagebox.askyesno", return_value=True):
            v._start_generation([KEY])
            self.pump_until_done()
        rows = v.generation_tree.get_children()
        self.assertEqual(len(rows), 1)
        self.assertEqual(v.generation_tree.item(rows[0], "values")[3], "通过")
        self.assertEqual(len(v.monitor_tree.get_children()), 1)
        self.assertEqual(v.results_tree.item(v.results_tree.get_children()[0], "values")[4], "7")
        self.assertEqual(self.c.project.workflow["working_templates"], {})

    def test_preflight_error_and_worker_exception_leave_no_waiting_rows(self):
        v = self.view
        self.c.workflow_draft["working_templates"][f"{MODULE}|DRV"] = {"path": str(Path(self.tmp.name) / "missing"), "topology": "DIFF"}
        self.c.save_project_draft()
        with patch("ibis_ui.view.messagebox.askyesno", return_value=True):
            v._start_generation([KEY])
            self.pump_until_done()
            self.assertEqual(v.generation_tree.item(v.generation_tree.get_children()[0], "values")[3], "失败")
            with patch.object(self.c, "generate_cases", side_effect=RuntimeError("测试后台异常")):
                v._start_generation([KEY])
                self.pump_until_done()
        self.assertEqual(len(v.generation_tree.get_children()), 1)
        self.assertIn("测试后台异常", v.generation_tree.item(v.generation_tree.get_children()[0], "values")[4])

    def test_edit_template_cancel_and_save_refresh_preview(self):
        v = self.view
        v.template_panel.edit()
        dialogs = [widget for widget in v.template_panel.winfo_children() if isinstance(widget, TemplateEditorDialog)]
        dialog = dialogs[0]
        source = dialog.editor.get("1.0", "end-1c")
        dialog.editor.insert("end", "\n")
        with patch("ibis_ui.editor_dialogs.messagebox.askyesno", return_value=True):
            dialog._cancel()
        self.assertEqual(self.c.workflow_draft["working_templates"], {})
        v.template_panel.edit()
        dialog = next(widget for widget in v.template_panel.winfo_children() if isinstance(widget, TemplateEditorDialog))
        dialog._replace(source.replace("[Source] Akrostar", "[Source] GUI 编辑"))
        dialog._save()
        v.update()
        self.assertTrue(self.c.has_unsaved_changes)  # 0.4.2 template edits join the unified draft.
        self.assertIn("GUI 编辑", v.template_panel.text.get("1.0", "end"))
        self.assertFalse(self.callback_errors)
