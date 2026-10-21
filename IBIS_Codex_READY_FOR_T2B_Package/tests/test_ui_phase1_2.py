from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ibis_ui.controller import ProjectController
from ibis_ui.errors import ProjectStorageError, ProjectValidationError
from ibis_ui.excel_importer import ExcelImporter
from ibis_ui.models import ProjectDocument, validate_config_payload
from ibis_ui.presentation import build_project_overview
from ibis_ui.project_store import ProjectStore
from ibis_ui.runtime import APP_VERSION, ResourceResolver
from ibis_ui.source_preview import preview_models, preview_msi, preview_spf
from ibis_ui.status import ConfigStatus, GenerationStatus, SourceStatus, status_label
from ibis_ui.ui_text import TEXT, TOOLTIPS
from ibis_ui.view import PROJECT_PAGE_ACTIONS, START_PAGE_ACTIONS

from test_ui_phase1_1 import _write_xlsx


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEMO_CONFIG = PACKAGE_ROOT / "inputs" / "config" / "ibis_config.xlsx"
MULTI_MODULE = PACKAGE_ROOT / "tests" / "fixtures" / "multi_module_project.json"
FIXTURE_CATALOG = PACKAGE_ROOT / "tests" / "fixtures" / "ui12_fixture_catalog.json"
MODULE = "demo_phy_io_diff"


class UIPhase12Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = ProjectStore(self.root / "workspace")
        self.resources = ResourceResolver(PACKAGE_ROOT)
        self.controller = ProjectController(self.store, resources=self.resources)

    def test_one_click_save_validates_applies_persists_and_reloads(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG, "一键保存")
        self.controller.update_module(MODULE, "tr.TYP", "33p")
        path = self.controller.save_configuration()

        self.assertTrue(path.is_file())
        self.assertFalse(self.controller.has_unsaved_changes)
        self.assertEqual(self.controller.config_status, ConfigStatus.SAVED)
        reloaded = ProjectController(self.store, resources=self.resources)
        reloaded.load_project(project.project_id)
        self.assertEqual(reloaded.module(MODULE)["tr"]["TYP"], "33p")

    def test_validation_failure_preserves_saved_snapshot_and_draft(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG, "验证回滚")
        self.controller.save_configuration()
        self.controller.update_module(MODULE, "ibis_io_voltage_domain", "UNKNOWN")

        with self.assertRaises(ProjectValidationError):
            self.controller.save_configuration()

        self.assertEqual(self.controller.config_status, ConfigStatus.ERROR)
        self.assertEqual(self.controller.module(MODULE, draft=False)["ibis_io_voltage_domain"], "VDDQ")
        self.assertEqual(self.controller.module(MODULE, draft=True)["ibis_io_voltage_domain"], "UNKNOWN")
        reloaded = ProjectController(self.store, resources=self.resources)
        reloaded.load_project(project.project_id)
        self.assertEqual(reloaded.module(MODULE)["ibis_io_voltage_domain"], "VDDQ")

    def test_storage_failure_preserves_old_snapshot_and_current_draft(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG, "写入回滚")
        self.controller.save_configuration()
        self.controller.update_module(MODULE, "tr.TYP", "44p")
        old_applied = copy.deepcopy(self.controller.project.config)

        with patch.object(self.store, "save", side_effect=ProjectStorageError("PROJECT_SAVE_FAILED", "模拟写入失败")):
            with self.assertRaises(ProjectStorageError):
                self.controller.save_configuration()

        self.assertEqual(self.controller.project.config, old_applied)
        self.assertEqual(self.controller.module(MODULE)["tr"]["TYP"], "44p")
        self.assertTrue(self.controller.is_dirty)
        reloaded = ProjectController(self.store, resources=self.resources)
        reloaded.load_project(project.project_id)
        self.assertEqual(reloaded.module(MODULE)["tr"]["TYP"], "20p")

    def test_original_excel_is_unchanged_by_one_click_save(self) -> None:
        before = DEMO_CONFIG.read_bytes()
        self.controller.import_excel(DEMO_CONFIG)
        self.controller.update_module(MODULE, "tf.MIN", "29p")
        self.controller.save_configuration()
        self.assertEqual(DEMO_CONFIG.read_bytes(), before)

    def test_recent_projects_keep_history_and_report_stale_source(self) -> None:
        first = self.controller.import_excel(DEMO_CONFIG, "项目一")
        first_path = self.controller.save_configuration()
        second_controller = ProjectController(self.store, resources=self.resources)
        second = second_controller.import_excel(DEMO_CONFIG, "项目二")
        second_controller.save_configuration()

        records = self.store.recent_project_records()
        self.assertEqual([item.project_id for item in records[:2]], [second.project_id, first.project_id])
        first_path.unlink()
        stale = next(item for item in self.store.recent_project_records() if item.project_id == first.project_id)
        self.assertFalse(stale.available)
        with self.assertRaisesRegex(ProjectStorageError, "项目不存在"):
            self.controller.load_project(first.project_id)

    def test_remove_recent_keeps_saved_project(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG, "仅移除列表")
        saved = self.controller.save_configuration()
        self.assertTrue(saved.is_file())

        self.controller.remove_recent(project.project_id)

        self.assertTrue(saved.is_file())
        self.assertNotIn(project.project_id, [item.project_id for item in self.store.recent_project_records()])
        reopened = ProjectController(self.store, resources=self.resources)
        reopened.load_project(project.project_id)
        self.assertEqual(reopened.project.name, "仅移除列表")

    def test_delete_project_soft_deletes_only_workspace_project(self) -> None:
        source_before = DEMO_CONFIG.read_bytes()
        project = self.controller.import_excel(DEMO_CONFIG, "软删除项目")
        saved = self.controller.save_configuration()
        project_dir = saved.parent
        self.controller.close_project("discard")

        trash_path = self.controller.delete_project(project.project_id)

        self.assertFalse(project_dir.exists())
        self.assertTrue(trash_path.is_dir())
        self.assertTrue((trash_path / "project.json").is_file())
        self.assertEqual(DEMO_CONFIG.read_bytes(), source_before)
        self.assertNotIn(project.project_id, [item.project_id for item in self.store.recent_project_records()])
        with self.assertRaisesRegex(ProjectStorageError, "项目不存在"):
            self.store.load(project.project_id)

    def test_active_project_cannot_be_deleted(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG, "活动项目")
        self.controller.save_configuration()
        with self.assertRaisesRegex(Exception, "请先关闭项目"):
            self.controller.delete_project(project.project_id)

    def test_active_project_can_be_closed_and_soft_deleted_from_visible_action(self) -> None:
        project = self.controller.import_excel(DEMO_CONFIG, "当前项目删除")
        saved = self.controller.save_configuration()

        trash_path = self.controller.close_and_delete_active_project("discard")

        self.assertIsNone(self.controller.project)
        self.assertFalse(saved.parent.exists())
        self.assertTrue((trash_path / "project.json").is_file())

    def test_never_saved_project_delete_only_closes_transient_project(self) -> None:
        project = self.controller.new_project("未保存项目")

        trash_path = self.controller.close_and_delete_active_project("discard")

        self.assertIsNone(trash_path)
        self.assertIsNone(self.controller.project)
        self.assertFalse(self.store.project_dir(project.project_id).exists())

    def test_import_into_named_project_preserves_name_uuid_and_source_excel(self) -> None:
        source_before = DEMO_CONFIG.read_bytes()
        project = self.controller.new_project("用户自定义项目名")

        imported = self.controller.import_excel(DEMO_CONFIG)

        self.assertEqual(imported.project_id, project.project_id)
        self.assertEqual(imported.name, "用户自定义项目名")
        self.assertEqual(imported.mode, "excel")
        self.assertEqual(imported.source_excel.path, str(DEMO_CONFIG.resolve()))
        self.assertEqual(self.controller.module(MODULE)["tr"]["TYP"], "20p")
        saved = self.controller.save_configuration()
        reloaded = ProjectController(self.store, resources=self.resources)
        reloaded.load_project(project.project_id)
        self.assertEqual(reloaded.project.name, "用户自定义项目名")
        self.assertEqual(reloaded.project.source_excel.path, str(DEMO_CONFIG.resolve()))
        self.assertEqual(DEMO_CONFIG.read_bytes(), source_before)

    def test_corner_voltage_edit_saves_and_reloads_without_modifying_excel(self) -> None:
        source_before = DEMO_CONFIG.read_bytes()
        project = self.controller.import_excel(DEMO_CONFIG, "电压编辑")

        self.controller.update_corner_voltage("VDDQ", "TYP", "0.61")
        self.controller.update_corner_voltage("VDD", "MAX", "0.91")

        self.assertTrue(self.controller.is_dirty)
        self.controller.save_configuration()
        reloaded = ProjectController(self.store, resources=self.resources)
        reloaded.load_project(project.project_id)
        self.assertEqual(reloaded.active_config["corners"]["TYP"]["voltages"]["VDDQ"], "0.61")
        self.assertEqual(reloaded.active_config["corners"]["MAX"]["voltages"]["VDD"], "0.91")
        self.assertEqual(DEMO_CONFIG.read_bytes(), source_before)

    def test_invalid_corner_voltage_is_rejected_when_saving(self) -> None:
        self.controller.import_excel(DEMO_CONFIG, "非法电压")
        self.controller.update_corner_voltage("VDDQ", "MIN", "not-a-number")

        with self.assertRaisesRegex(ProjectValidationError, "电压必须是数字"):
            self.controller.save_configuration()

        self.assertTrue(self.controller.is_dirty)

    def test_recursive_msi_scan_multi_workbook_sheet_and_ambiguity(self) -> None:
        config = json.loads(MULTI_MODULE.read_text(encoding="utf-8"))
        config["modules"] = config["modules"][:2]
        config["templates"] = [row for row in config["templates"] if row["module"] in {"IO_DIFF", "IO_SE"}]
        msi_root = self.root / "msi"
        (msi_root / "nested").mkdir(parents=True)
        header = ["PIN_NAME", "WIDTH", "DIRECTION"]
        _write_xlsx(msi_root / "bundle.xlsx", {"IO_DIFF": [header, ["PAD", "1", "IO"]], "IO_SE": [header, ["PAD", "1", "IO"]]})
        _write_xlsx(msi_root / "MSI_Master.xlsx", {"IO_DIFF": [header, ["PAD", "1", "IO"]]})
        config["roots"]["msi"] = str(msi_root)
        report = preview_msi(config)
        self.assertEqual(len(report.files), 1)
        self.assertEqual(len(report.sheets), 2)
        self.assertEqual([item.status for item in report.modules], ["PASS", "PASS"])

        _write_xlsx(msi_root / "nested" / "IO_DIFF.xlsx", {"misc": [header, ["PAD", "1", "IO"]]})
        ambiguous = preview_msi(config)
        row = next(item for item in ambiguous.modules if item.module == "IO_DIFF")
        self.assertEqual(row.status, "ERROR")
        self.assertIn("无法唯一确定", row.message)

    def test_spf_missing_duplicate_and_pin_mismatch_are_separate_errors(self) -> None:
        config = json.loads(MULTI_MODULE.read_text(encoding="utf-8"))
        config["modules"] = [config["modules"][0]]
        config["templates"] = [row for row in config["templates"] if row["module"] == "IO_DIFF"]
        spf_root = self.root / "spf"
        spf_root.mkdir()
        (spf_root / "IO_DIFF.rcbest.spf").write_text(".subckt IO_DIFF VDD VSS PAD\n.ends IO_DIFF\n", encoding="utf-8")
        (spf_root / "IO_DIFF.typical.spf").write_text(".subckt IO_DIFF VDD VSS PAD EXTRA\n.ends IO_DIFF\n", encoding="utf-8")
        config["roots"]["spf"] = str(spf_root)
        report = preview_spf(config)
        self.assertEqual(next(row for row in report.matches if row.corner == "MIN").status, "ERROR")
        self.assertIn("Pin List 不一致", next(row for row in report.matches if row.corner == "MAX").message)

        (spf_root / "IO_DIFF.typical.copy.spf").write_text(".subckt IO_DIFF VDD VSS PAD\n.ends IO_DIFF\n", encoding="utf-8")
        duplicate = preview_spf(config)
        self.assertIn("匹配到 2 个", next(row for row in duplicate.matches if row.corner == "TYP").message)

    def test_model_root_checks_files_without_claiming_electrical_validation(self) -> None:
        config = json.loads(MULTI_MODULE.read_text(encoding="utf-8"))
        model_root = self.root / "models"
        spectre = model_root / "spectre"
        spectre.mkdir(parents=True)
        for name in ("rbd.lib", "cap.lib"):
            (spectre / name).write_text("synthetic\n", encoding="utf-8")
        config["roots"]["model"] = str(model_root)
        report = preview_models(config)
        self.assertFalse(report.is_complete)
        missing = next(item for item in report.files if item.filename == "mos_var.lib")
        self.assertEqual(missing.status, "ERROR")
        self.assertNotIn("电气", missing.message)

    def test_overview_uses_actual_project_and_input_state(self) -> None:
        project = ExcelImporter().import_project(DEMO_CONFIG)
        config = project.config
        overview = build_project_overview(
            config,
            ConfigStatus.SAVED,
            preview_msi(config),
            preview_spf(config),
            preview_models(config),
        )
        self.assertEqual((overview.io_top_count, overview.branch_count, overview.case_count), (1, 1, 1))
        self.assertTrue(overview.inputs_ready)
        self.assertEqual(overview.current_stage, "模板选择")

        dirty = build_project_overview(config, ConfigStatus.DIRTY, preview_msi(config), preview_spf(config), preview_models(config))
        self.assertEqual(dirty.current_stage, "项目配置编辑")
        self.assertIn("保存项目", dirty.recommended_action)

    def test_status_categories_and_generation_default_are_distinct(self) -> None:
        self.assertEqual(status_label(ConfigStatus.DIRTY), "有未保存修改")
        self.assertEqual(status_label(SourceStatus.MATCHED), "已匹配")
        self.assertEqual(status_label(GenerationStatus.NOT_GENERATED), "未生成")
        self.assertNotEqual(status_label(SourceStatus.MATCHED), status_label(GenerationStatus.PASS))

    def test_chinese_workflow_text_and_tooltips_are_centralized(self) -> None:
        self.assertEqual(TEXT["save_config"], "保存项目")
        self.assertEqual(TEXT["input_files"], "输入文件")
        self.assertIn("不会修改原始 Config Excel", TOOLTIPS["save_config"])
        self.assertEqual(TEXT["back_to_start"], "返回")
        self.assertIn("返回项目首页", TOOLTIPS["back_to_start"])
        self.assertNotIn("Apply", " ".join(TEXT.values()))

    def test_start_and_project_page_actions_have_separate_responsibilities(self) -> None:
        self.assertEqual(START_PAGE_ACTIONS, ("new_project", "open_project"))
        self.assertEqual(
            PROJECT_PAGE_ACTIONS,
            ("import_config", "export_config", "save_config", "delete_project", "advanced", "about"),
        )
        self.assertNotIn("import_config", START_PAGE_ACTIONS)
        self.assertNotIn("new_project", PROJECT_PAGE_ACTIONS)
        self.assertNotIn("open_project", PROJECT_PAGE_ACTIONS)

    def test_fixture_catalog_covers_required_current_scenarios(self) -> None:
        catalog = json.loads(FIXTURE_CATALOG.read_text(encoding="utf-8"))
        identifiers = {item["id"] for item in catalog["derived_scenarios"]}
        self.assertTrue({"dual_module", "multi_ron", "directions", "multi_msi", "multi_sheet", "normal_spf", "error_spf", "config_error", "stale_path"} <= identifiers)
        config = json.loads(MULTI_MODULE.read_text(encoding="utf-8"))
        validate_config_payload(config, check_paths=False)
        self.assertEqual({row["generate_type"] for row in config["modules"]}, {"DRV", "RCV", "BOTH"})

    def test_ui12_version_and_packaging_contract(self) -> None:
        self.assertEqual(APP_VERSION, "0.4.1")
        build_script = (PACKAGE_ROOT / "packaging" / "build_windows.py").read_text(encoding="utf-8")
        workflow = (PACKAGE_ROOT.parent / ".github" / "workflows" / "ibis-windows-package.yml").read_text(encoding="utf-8")
        self.assertIn('OUTPUT_NAME = "IBIS_Automation_Windows_0_4_1"', build_script)
        self.assertIn("codex/ibis-ui-full-workflow", workflow)
        self.assertIn("IBIS_Automation_Windows_0_4_1", workflow)


if __name__ == "__main__":
    unittest.main()
