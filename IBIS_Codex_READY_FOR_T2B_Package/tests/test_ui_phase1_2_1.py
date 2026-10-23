from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ibis_ui.app import main as ui_main
from ibis_ui.controller import ProjectController
from ibis_ui.errors import ProjectStorageError, ProjectValidationError
from ibis_ui.models import ProjectDocument, validate_config_payload
from ibis_ui.project_store import ProjectStore
from ibis_ui.runtime import APP_VERSION, ResourceResolver
from ibis_ui.template_selection import (
    effective_template_mappings,
    effective_template_id,
    ensure_template_selections,
    selection_for,
)
from ibis_ui.ui_text import TEXT, TOOLTIPS


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEMO_CONFIG = PACKAGE_ROOT / "inputs" / "config" / "ibis_config.xlsx"
MULTI_MODULE = PACKAGE_ROOT / "tests" / "fixtures" / "multi_module_project.json"
MODULE = "demo_phy_io_diff"


class UIPhase121Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = ProjectStore(self.root / "workspace")
        self.resources = ResourceResolver(PACKAGE_ROOT)
        self.controller = ProjectController(self.store, resources=self.resources)

    def _load_multi(self) -> ProjectDocument:
        config = json.loads(MULTI_MODULE.read_text(encoding="utf-8"))
        for name in ("model", "msi", "spf"):
            root = self.root / name
            root.mkdir(exist_ok=True)
            config["roots"][name] = str(root)
        project = ProjectDocument.create("多模块模板", "ui", config)
        self.store.save(project)
        self.controller.load_project(project.project_id)
        return project

    def test_start_import_close_and_reopen_from_readable_recent_record(self) -> None:
        self.assertIsNone(self.controller.project)
        before = hashlib.sha256(DEMO_CONFIG.read_bytes()).hexdigest()
        project = self.controller.import_excel(DEMO_CONFIG, "Config 导入项目")
        self.controller.save_project_draft()

        record = self.controller.recent_projects()[0]
        self.assertEqual(record.name, "Config 导入项目")
        self.assertEqual(record.source_excel, str(DEMO_CONFIG.resolve()))
        self.assertEqual(record.status, "已保存")
        self.assertNotIn(project.project_id, record.name)

        self.assertTrue(self.controller.close_project())
        self.assertIsNone(self.controller.project)
        reopened = self.controller.load_project(project.project_id)
        self.assertEqual(reopened.name, "Config 导入项目")
        self.assertEqual(before, hashlib.sha256(DEMO_CONFIG.read_bytes()).hexdigest())

    def test_normal_application_start_does_not_auto_open_recent_project(self) -> None:
        recent = self.controller.import_excel(DEMO_CONFIG, "不应自动打开")
        self.controller.save_project_draft()
        captured: dict[str, object] = {}

        def fake_view(controller, smoke_test=False):
            captured["project"] = controller.project
            view = MagicMock()
            view.smoke_error = None
            return view

        with patch("ibis_ui.view.IBISApplicationView", side_effect=fake_view), patch("ibis_ui.app.configure_process_dpi_awareness"):
            self.assertEqual(ui_main(["--workspace", str(self.store.workspace)]), 0)
        self.assertIsNone(captured["project"])
        self.assertEqual(self.store.load(recent.project_id).name, "不应自动打开")

    def test_close_project_dirty_save_discard_cancel(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG, "关闭保护")
        self.controller.save_project_draft()
        self.controller.update_module(MODULE, "tr.TYP", "31p")
        self.assertFalse(self.controller.close_project("cancel"))
        self.assertIsNotNone(self.controller.project)

        self.assertTrue(self.controller.close_project("discard"))
        discarded = ProjectController(self.store, resources=self.resources)
        discarded.load_project(project.project_id)
        self.assertEqual(discarded.module(MODULE)["tr"]["TYP"], "20p")

        discarded.update_module(MODULE, "tr.TYP", "32p")
        self.assertTrue(discarded.close_project("save"))
        saved = ProjectController(self.store, resources=self.resources)
        saved.load_project(project.project_id)
        self.assertEqual(saved.module(MODULE)["tr"]["TYP"], "32p")

    def test_recent_missing_project_is_reported_and_removable(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG, "失效项目")
        project_path = self.controller.save_project_draft()
        project_path.unlink()
        record = self.controller.recent_projects()[0]
        self.assertFalse(record.available)
        self.assertEqual(record.status, "项目文件不存在")
        with self.assertRaises(ProjectStorageError):
            self.controller.load_project(project.project_id)
        self.controller.remove_recent(project.project_id)
        self.assertEqual(self.controller.recent_projects(), [])

    def test_auto_mapping_covers_diff_and_se_drv_rcv_both(self) -> None:
        self._load_multi()
        expected = {
            ("IO_DIFF", "DRV"): "builtin:drv_diff",
            ("IO_DIFF", "RCV"): "builtin:rcv_diff",
            ("IO_SE", "DRV"): "builtin:drv_se",
            ("IO_SE", "RCV"): "builtin:rcv_se",
            ("OUTC", "DRV"): "builtin:drv_se",
            ("INSE", "RCV"): "builtin:rcv_se",
        }
        for key, template_id in expected.items():
            self.assertEqual(effective_template_id(self.controller.active_config, *key), template_id)
        mappings = effective_template_mappings(self.controller.active_config)
        self.assertEqual(len(mappings), 6)
        self.assertTrue(all(item["template_id"] for item in mappings))
        self.assertEqual(selection_for(self.controller.active_config, "IO_DIFF")["topology"], "DIFF")
        self.assertEqual(selection_for(self.controller.active_config, "IO_SE")["topology"], "SE")

    def test_auto_uses_explicit_metadata_not_module_name(self) -> None:
        config = json.loads(MULTI_MODULE.read_text(encoding="utf-8"))
        config["modules"][0]["name"] = "misleading_se_name"
        for row in config["templates"]:
            if row["module"] == "IO_DIFF":
                row["module"] = "misleading_se_name"
        ensure_template_selections(config)
        self.assertEqual(selection_for(config, "misleading_se_name")["topology"], "DIFF")
        self.assertEqual(effective_template_id(config, "misleading_se_name", "DRV"), "builtin:drv_diff")

    def test_generate_type_switch_preserves_hidden_direction_choices(self) -> None:
        self._load_multi()
        self.controller.update_template("IO_DIFF", "DRV", "builtin:drv_se")
        self.controller.update_template("IO_DIFF", "RCV", "builtin:rcv_se")
        for generate_type in ("DRV", "BOTH", "RCV", "BOTH"):
            self.controller.update_module("IO_DIFF", "generate_type", generate_type)
        row = self.controller.template_selection("IO_DIFF")
        self.assertEqual(row["drv_template"]["template_id"], "builtin:drv_se")
        self.assertEqual(row["rcv_template"]["template_id"], "builtin:rcv_se")

    def test_manual_auto_save_reload_and_module_isolation(self) -> None:
        project = self._load_multi()
        self.controller.update_template("IO_DIFF", "DRV", "builtin:drv_se")
        self.controller.update_template("IO_DIFF", "RCV", "builtin:rcv_se")
        self.assertTrue(self.controller.is_dirty)
        self.controller.save_project_draft()

        reloaded = ProjectController(self.store, resources=self.resources)
        reloaded.load_project(project.project_id)
        diff = reloaded.template_selection("IO_DIFF")
        se = reloaded.template_selection("IO_SE")
        self.assertEqual(diff["drv_template"]["mode"], "manual")
        self.assertEqual(diff["drv_template"]["template_id"], "builtin:drv_se")
        self.assertEqual(diff["rcv_template"]["template_id"], "builtin:rcv_se")
        self.assertEqual(se["drv_template"]["mode"], "auto")

        reloaded.update_template("IO_DIFF", "DRV", None)
        self.assertEqual(reloaded.template_selection("IO_DIFF")["drv_template"]["mode"], "auto")
        self.assertEqual(effective_template_id(reloaded.active_config, "IO_DIFF", "DRV"), "builtin:drv_diff")

    def test_config_default_then_manual_priority_and_reimport_preserves_manual(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG)
        choice = self.controller.template_selection(MODULE)["drv_template"]
        self.assertEqual(choice["mode"], "auto")
        self.assertIsNone(choice["template_id"])
        self.assertEqual(choice["config_default_id"], "builtin:drv_diff")
        self.assertEqual(choice["resolved_template_id"], "builtin:drv_diff")

        self.controller.update_template(MODULE, "DRV", "builtin:drv_se")
        self.controller.save_project_draft()
        reimported = self.controller.import_excel(DEMO_CONFIG)
        self.assertEqual(reimported.project_id, project.project_id)
        after = self.controller.template_selection(MODULE)["drv_template"]
        self.assertEqual(after["mode"], "manual")
        self.assertEqual(after["template_id"], "builtin:drv_se")
        self.assertEqual(after["config_default_id"], "builtin:drv_diff")

    def test_unresolved_auto_is_validation_error_not_pass(self) -> None:
        config = json.loads(MULTI_MODULE.read_text(encoding="utf-8"))
        config["modules"] = [copy.deepcopy(config["modules"][0])]
        config["templates"] = []
        config["template_selections"] = []
        with self.assertRaisesRegex(ProjectValidationError, "无法自动匹配"):
            validate_config_payload(config, check_paths=False)

    def test_invalid_persisted_template_mode_is_not_silently_coerced(self) -> None:
        config = json.loads(MULTI_MODULE.read_text(encoding="utf-8"))
        ensure_template_selections(config)
        config["template_selections"][0]["drv_template"]["mode"] = "unexpected"
        with self.assertRaisesRegex(ProjectValidationError, "模板模式非法"):
            validate_config_payload(config, check_paths=False)

    def test_failed_template_validation_does_not_replace_saved_project(self) -> None:
        project = self._load_multi()
        self.controller.save_project_draft()
        self.controller.active_config["template_selections"][0]["drv_template"] = {
            "mode": "manual",
            "template_id": "unknown",
        }
        with self.assertRaises(ProjectValidationError):
            self.controller.save_project_draft()
        reloaded = ProjectController(self.store, resources=self.resources)
        reloaded.load_project(project.project_id)
        self.assertEqual(effective_template_id(reloaded.active_config, "IO_DIFF", "DRV"), "builtin:drv_diff")

    def test_project_json_schema_is_path_neutral_and_persists_stable_ids(self) -> None:
        project = self._load_multi()
        self.controller.update_template("IO_DIFF", "DRV", "builtin:drv_se")
        path = self.controller.save_project_draft()
        payload = json.loads(path.read_text(encoding="utf-8"))
        row = next(item for item in payload["config"]["template_selections"] if item["module"] == "IO_DIFF")
        self.assertEqual(row["drv_template"]["mode"], "manual")
        self.assertEqual(row["drv_template"]["template_id"], "builtin:drv_se")
        self.assertNotIn("DIFF DRV - Built-in", json.dumps(row, ensure_ascii=False))
        self.assertEqual(ProjectDocument.from_dict(payload).project_id, project.project_id)

    def test_ui121_copy_and_packaging_contract(self) -> None:
        self.assertEqual(APP_VERSION, "0.4.2")
        self.assertEqual(TEXT["import_config"], "导入 Config Excel")
        self.assertEqual(TEXT["save_config"], "保存项目")
        self.assertEqual(TEXT["close_project"], "返回")
        self.assertEqual(TOOLTIPS["save_config"], "检查并保存当前软件项目中的修改，不会修改原始 Config Excel。")
        workflow = (PACKAGE_ROOT.parent / ".github" / "workflows" / "ibis-windows-package.yml").read_text(encoding="utf-8")
        self.assertIn("codex/ibis-ui-full-workflow", workflow)
        self.assertIn("IBIS_Automation_Windows_0_4_2", workflow)


if __name__ == "__main__":
    unittest.main()
