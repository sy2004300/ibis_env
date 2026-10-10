from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ibis_ui.app import main as ui_main
from ibis_ui.controller import ProjectController
from ibis_ui.errors import ProjectStateError, ProjectStorageError, ProjectValidationError
from ibis_ui.models import PROJECT_SCHEMA_VERSION
from ibis_ui.project_store import ProjectStore


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEMO_CONFIG = PACKAGE_ROOT / "inputs" / "config" / "ibis_config.xlsx"
MODULE = "demo_phy_io_diff"


class UIPhase1ProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name) / "workspace"
        self.store = ProjectStore(self.workspace)
        self.controller = ProjectController(self.store)

    def test_import_excel_loads_demo_without_modifying_source(self) -> None:
        before = DEMO_CONFIG.read_bytes()

        project = self.controller.import_excel(DEMO_CONFIG, "Imported Demo")

        self.assertEqual(DEMO_CONFIG.read_bytes(), before)
        self.assertEqual(project.mode, "excel")
        self.assertEqual(project.source_excel.path, str(DEMO_CONFIG.resolve()))
        module = self.controller.module(MODULE)
        self.assertEqual(module["generate_type"], "DRV")
        self.assertEqual(module["impedances"], [30])
        self.assertEqual(module["ibis_io_voltage_domain"], "VDDQ")
        self.assertEqual(module["ibis_vih_voltage_domain"], "VDD")
        self.assertEqual(module["tr"], {"MAX": "20p", "TYP": "20p", "MIN": "20p"})
        self.assertEqual(module["tf"], {"MAX": "20p", "TYP": "20p", "MIN": "20p"})
        self.assertEqual(project.config["corners"]["TYP"]["temperature"], "25")
        self.assertEqual(project.config["corners"]["TYP"]["voltages"]["VDDQ"], "0.5")

    def test_dirty_apply_save_reload_and_source_immutability(self) -> None:
        source_before = DEMO_CONFIG.read_bytes()
        project = self.controller.import_excel(DEMO_CONFIG)
        project_id = project.project_id

        self.controller.update_module(MODULE, "tr.TYP", "25p")
        self.assertTrue(self.controller.is_dirty)
        self.assertEqual(self.controller.module(MODULE, draft=False)["tr"]["TYP"], "20p")
        with self.assertRaisesRegex(ProjectStateError, "尚未 Apply"):
            self.controller.save_project()

        self.controller.apply_changes()
        self.assertFalse(self.controller.is_dirty)
        self.assertTrue(self.controller.has_unsaved_applied_changes)
        saved_path = self.controller.save_project()
        self.assertTrue(saved_path.is_file())
        self.assertEqual(DEMO_CONFIG.read_bytes(), source_before)

        reloaded = ProjectController(self.store)
        reloaded.load_project(project_id)
        self.assertEqual(reloaded.module(MODULE)["tr"]["TYP"], "25p")
        self.assertFalse(reloaded.is_dirty)
        self.assertEqual(DEMO_CONFIG.read_bytes(), source_before)

        payload = json.loads(saved_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(payload["source_excel"]["path"], str(DEMO_CONFIG.resolve()))

    def test_failed_apply_preserves_applied_snapshot(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG)
        self.controller.save_project()
        self.controller.update_module(MODULE, "ibis_io_voltage_domain", "UNKNOWN")

        with self.assertRaisesRegex(ProjectValidationError, "Voltage Domain"):
            self.controller.apply_changes()

        self.assertEqual(self.controller.module(MODULE, draft=False)["ibis_io_voltage_domain"], "VDDQ")
        self.assertTrue(self.controller.is_dirty)
        reloaded = ProjectController(self.store)
        reloaded.load_project(project.project_id)
        self.assertEqual(reloaded.module(MODULE)["ibis_io_voltage_domain"], "VDDQ")

    def test_invalid_path_is_reported_and_guard_tracks_draft(self) -> None:
        self.controller.import_excel(DEMO_CONFIG)
        self.controller.update_root("model", str(self.workspace / "missing-model-root"))
        self.assertEqual(
            self.controller.guard_message(),
            "存在尚未 Apply 的修改，请选择 Apply 并保存、丢弃或取消。",
        )
        with self.assertRaisesRegex(ProjectValidationError, "MODEL Root 不存在"):
            self.controller.apply_changes()
        self.controller.discard_draft()
        self.assertFalse(self.controller.is_dirty)
        self.assertIn("尚未保存", self.controller.guard_message())

    def test_projects_are_isolated_even_with_same_name(self) -> None:
        first = self.controller.import_excel(DEMO_CONFIG, "Same Name")
        self.controller.save_project()

        second_controller = ProjectController(self.store)
        second = second_controller.import_excel(DEMO_CONFIG, "Same Name")
        second_controller.update_module(MODULE, "tr.TYP", "31p")
        second_controller.apply_changes()
        second_controller.save_project()

        self.assertNotEqual(first.project_id, second.project_id)
        first_reloaded = ProjectController(self.store)
        first_reloaded.load_project(first.project_id)
        self.assertEqual(first_reloaded.module(MODULE)["tr"]["TYP"], "20p")
        self.assertEqual(second_controller.module(MODULE)["tr"]["TYP"], "31p")

    def test_project_id_cannot_escape_workspace(self) -> None:
        with self.assertRaisesRegex(ProjectStorageError, "项目 ID 非法"):
            self.store.load("../../outside")

    def test_new_project_save_and_recent_restore(self) -> None:
        created = self.controller.new_project("Empty UI Project")
        self.assertEqual(created.mode, "ui")
        self.assertEqual(created.config["modules"], [])
        self.controller.save_project()

        restored = ProjectController(self.store)
        recent = restored.load_recent()
        self.assertIsNotNone(recent)
        self.assertEqual(recent.project_id, created.project_id)
        self.assertEqual(restored.state_label, "SAVED")

    def test_case_tree_and_future_generate_guard(self) -> None:
        self.controller.import_excel(DEMO_CONFIG)
        self.assertEqual(
            self.controller.case_tree(),
            [{"module": MODULE, "directions": [{"direction": "DRV", "rons": [30]}]}],
        )
        with self.assertRaisesRegex(ProjectStateError, "UI-4"):
            self.controller.ensure_generate_allowed()

        self.controller.update_module(MODULE, "tr.TYP", "21p")
        with self.assertRaisesRegex(ProjectStateError, "禁止 Generate"):
            self.controller.ensure_generate_allowed()

    def test_headless_check_does_not_require_display(self) -> None:
        from ibis_ui.view import IBISApplicationView

        self.assertTrue(issubclass(IBISApplicationView, object))
        self.assertEqual(ui_main(["--check", "--workspace", str(self.workspace)]), 0)

    def test_exit_guard_cancel_and_discard_without_tk_root(self) -> None:
        from ibis_ui.view import IBISApplicationView

        self.controller.import_excel(DEMO_CONFIG)
        self.controller.update_module(MODULE, "tr.TYP", "22p")
        view = IBISApplicationView.__new__(IBISApplicationView)
        view.controller = self.controller

        with patch("ibis_ui.view.messagebox.askyesnocancel", return_value=None):
            self.assertFalse(view._confirm_leave_current())
        self.assertTrue(self.controller.is_dirty)

        with patch("ibis_ui.view.messagebox.askyesnocancel", return_value=False):
            self.assertTrue(view._confirm_leave_current())
        self.assertFalse(self.controller.is_dirty)
        self.assertEqual(self.controller.module(MODULE)["tr"]["TYP"], "20p")


if __name__ == "__main__":
    unittest.main()
