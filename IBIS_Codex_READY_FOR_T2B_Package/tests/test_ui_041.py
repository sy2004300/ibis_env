from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ibis_ui.controller import ProjectController
from ibis_ui.errors import ProjectStorageError, ProjectValidationError
from ibis_ui.project_store import ProjectStore
from ibis_ui.runtime import ResourceResolver
from ibis_ui.task_state import ACTIVE_STATES, GenerationTasks, output_file_count

ROOT = Path(__file__).resolve().parents[1]
MODULE = "demo_phy_io_diff"
KEY = (MODULE, "DRV", 30)


class UI041RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ProjectStore(Path(self.tmp.name) / "workspace")
        self.controller = ProjectController(self.store, resources=ResourceResolver(ROOT))
        self.controller.import_excel(ROOT / "inputs/config/ibis_config.xlsx", "新版回归")
        self.controller.save_project_draft()

    def test_direct_templates_all_directions_and_preview_equal_output(self):
        c = self.controller
        c.update_module(MODULE, "generate_type", "BOTH")
        c.update_module(MODULE, "impedances", [30, 40])
        c.save_project_draft()
        previews = {(MODULE, direction, ron): c.preview_t2b((MODULE, direction, ron)) for direction in ("DRV", "RCV") for ron in (30, 40)}
        result = c.generate_cases()
        self.assertTrue(result.ready, [row.message for row in result.cases])
        self.assertEqual(len(result.cases), 4)
        self.assertEqual(c.project.workflow["working_templates"], {})
        for row in result.cases:
            module, direction, ron = row.key.split("/")
            key = module, direction, int(ron[:-3])
            path = next(Path(row.path).glob("*.t2b"))
            self.assertEqual(path.read_text(encoding="utf-8"), previews[key])
            self.assertEqual(output_file_count(row.path), 7)
        self.assertIn("PASS", c.golden_diff(KEY))

    def test_selected_drv_ignores_unselected_missing_rcv_customization(self):
        c = self.controller
        c.update_module(MODULE, "generate_type", "BOTH")
        c.workflow_draft["working_templates"][f"{MODULE}|RCV"] = {
            "path": str(Path(self.tmp.name) / "missing.t2b"), "topology": "DIFF",
        }
        c.save_project_draft()
        result = c.generate_cases([KEY])
        self.assertTrue(result.ready)
        self.assertEqual(len(result.cases), 1)

    def test_preflight_failure_becomes_terminal_and_persists(self):
        c = self.controller
        c.workflow_draft["working_templates"][f"{MODULE}|DRV"] = {
            "path": str(Path(self.tmp.name) / "missing.t2b"), "topology": "DIFF",
        }
        c.save_project_draft()
        tasks = GenerationTasks([KEY])
        result = c.generate_cases([KEY], progress=tasks.update)
        tasks.finish("FAIL", "结束")
        self.assertFalse(result.ready)
        self.assertTrue(all(row["status"] == "FAIL" for row in tasks.rows.values()))
        c.load_project(c.project.project_id)
        row = c.generation_statuses()[0]
        self.assertEqual(row["status"], "FAIL")
        self.assertIn("模板", row["message"])
        self.assertEqual(output_file_count(row["output_path"]), 0)

    def test_preview_follows_draft_without_writing_files(self):
        c = self.controller
        original = c.preview_t2b(KEY)
        c.update_module(MODULE, "tr.TYP", "33p")
        draft_preview = c.preview_t2b(KEY)
        self.assertNotEqual(original, draft_preview)
        self.assertIn("33p", draft_preview)
        self.assertTrue(c.has_unsaved_changes)
        project_dir = self.store.project_dir(c.project.project_id)
        self.assertFalse((project_dir / "templates").exists())
        self.assertFalse((project_dir / "generated").exists())
        c.discard_draft()
        self.assertEqual(c.preview_t2b(KEY), original)

    def test_custom_template_save_reload_and_stale(self):
        c = self.controller
        self.assertTrue(c.generate_cases([KEY]).ready)
        source = c.template_source(MODULE, "DRV")
        c.save_template_and_project(MODULE, "DRV", source.replace("[Source] Akrostar", "[Source] 中文模板"))
        self.assertFalse(c.has_unsaved_changes)
        self.assertEqual(c.generation_statuses()[0]["status"], "STALE")
        c.load_project(c.project.project_id)
        preview = c.preview_t2b(KEY)
        self.assertIn("中文模板", preview)
        result = c.generate_cases([KEY])
        self.assertEqual(result.cases[0].status, "FAIL")  # Deliberate Golden difference.
        self.assertEqual(next(Path(result.cases[0].path).glob("*.t2b")).read_text(encoding="utf-8"), preview)
        self.assertIn("[Source] Akrostar", (ROOT / "templates/t2b/drv_diff.t2b").read_text())

    def test_template_failed_save_preserves_saved_reference(self):
        c = self.controller
        source = c.template_source(MODULE, "DRV")
        c.save_template_and_project(MODULE, "DRV", source)
        before = copy.deepcopy(c.project.to_dict())
        with patch.object(self.store, "save", side_effect=ProjectStorageError("DISK_FULL", "磁盘空间不足")):
            with self.assertRaises(ProjectStorageError):
                c.save_template_and_project(MODULE, "DRV", source.replace("[Source] Akrostar", "[Source] Changed"))
        self.assertEqual(c.project.to_dict(), before)
        c.load_project(c.project.project_id)
        self.assertEqual(c.template_source(MODULE, "DRV"), source)

    def test_invalid_inline_edits_block_save_without_losing_snapshot(self):
        c = self.controller
        before = c.project.to_dict()
        c.pending_edit_errors["voltage"] = "Voltage Domain 名称重复"
        self.assertTrue(c.has_unsaved_changes)
        with self.assertRaises(ProjectValidationError):
            c.save_project_draft()
        self.assertEqual(before, c.project.to_dict())
        c.discard_draft()
        self.assertFalse(c.has_unsaved_changes)

    def test_task_events_update_in_place_and_exception_finishes_pending(self):
        tasks = GenerationTasks([KEY, (MODULE, "DRV", 40)])
        key = f"{MODULE}/DRV/30ohm"
        tasks.update(key, "检查输入", "检查模板")
        tasks.update(key, "生成中", "生成中")
        tasks.update(key, "PASS", "完成")
        tasks.finish("FAIL", "后台异常")
        self.assertEqual(len(tasks.rows), 2)
        self.assertEqual(tasks.rows[key]["status"], "PASS")
        self.assertFalse(any(row["status"] in ACTIVE_STATES for row in tasks.rows.values()))
        self.assertIn("后台异常", tasks.rows[f"{MODULE}/DRV/40ohm"]["message"])

    def test_empty_output_never_counts_working_directory(self):
        self.assertEqual(output_file_count(""), 0)
        self.assertEqual(output_file_count("."), 0)
        self.assertEqual(output_file_count("  "), 0)

    def test_cancelled_tasks_terminal_without_case_files(self):
        tasks = GenerationTasks([KEY])
        result = self.controller.generate_cases([KEY], cancel_requested=lambda: True, progress=tasks.update)
        self.assertEqual(result.cases[0].status, "已取消")
        self.assertFalse(any(row["status"] in ACTIVE_STATES for row in tasks.rows.values()))
