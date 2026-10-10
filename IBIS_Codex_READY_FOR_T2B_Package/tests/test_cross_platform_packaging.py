from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ibis_auto.config import parse_config
from ibis_ui.app import _console_write, headless_check
from ibis_ui.controller import ProjectController
from ibis_ui.errors import ProjectValidationError, ResourceError
from ibis_ui.excel_importer import ExcelImporter
from ibis_ui.logging_utils import LOGGER_NAME, close_file_logging, configure_file_logging
from ibis_ui.project_store import ProjectStore
from ibis_ui.runtime import APP_VERSION, REQUIRED_TEMPLATES, ResourceResolver, app_metadata, default_workspace


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEMO_CONFIG = PACKAGE_ROOT / "inputs" / "config" / "ibis_config.xlsx"


class CrossPlatformRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_default_workspace_is_per_user_on_windows_and_linux(self) -> None:
        windows = default_workspace(
            system="Windows",
            environ={"LOCALAPPDATA": "C:/Users/Tester/AppData/Local"},
            home=Path("C:/Users/Tester"),
        )
        linux = default_workspace(
            system="Linux",
            environ={"XDG_DATA_HOME": "/home/tester/.xdg-data"},
            home=Path("/home/tester"),
        )
        fallback = default_workspace(system="Linux", environ={}, home=Path("/home/tester"))

        self.assertEqual(windows.as_posix(), "C:/Users/Tester/AppData/Local/IBIS_Automation/workspace")
        self.assertEqual(linux, Path("/home/tester/.xdg-data/IBIS_Automation/workspace"))
        self.assertEqual(fallback, Path("/home/tester/.local/share/IBIS_Automation/workspace"))

    def test_project_store_default_uses_runtime_workspace(self) -> None:
        expected = self.root / "user-data" / "workspace"
        with patch("ibis_ui.project_store.default_workspace", return_value=expected):
            store = ProjectStore()
        self.assertEqual(store.workspace, expected.resolve())
        store.ensure_ready()
        self.assertTrue(store.projects_root.is_dir())

    def test_source_resource_resolver_has_templates_and_synthetic_demo(self) -> None:
        resolver = ResourceResolver(PACKAGE_ROOT)
        resolver.validate()
        self.assertEqual(resolver.demo_config, DEMO_CONFIG)
        for filename in REQUIRED_TEMPLATES:
            self.assertTrue((resolver.template_root / filename).is_file())

    def test_missing_packaged_resource_is_structured_error(self) -> None:
        resolver = ResourceResolver(self.root / "incomplete-resources")
        with self.assertRaisesRegex(ResourceError, "软件资源不完整"):
            resolver.validate()

    def test_headless_check_exercises_demo_and_never_creates_gui(self) -> None:
        store = ProjectStore(self.root / "workspace")
        report = headless_check(store, ResourceResolver(PACKAGE_ROOT))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["mode"], "HEADLESS")
        self.assertFalse(report["gui_window_created"])
        self.assertEqual(report["project_schema_version"], 1)
        self.assertEqual(report["demo_modules"], ["demo_phy_io_diff"])

    def test_windowed_executable_does_not_require_console_streams(self) -> None:
        with patch("ibis_ui.app.sys.stdout", None), patch("ibis_ui.app.sys.stderr", None):
            _console_write("headless pass")
            _console_write("headless failure", error=True)

    def test_project_with_foreign_roots_loads_then_blocks_apply_until_repaired(self) -> None:
        store = ProjectStore(self.root / "workspace")
        project = ExcelImporter().import_project(DEMO_CONFIG, "Moved Project")
        project.config["roots"]["msi"] = str(self.root / "old-computer" / "msi")
        store.save(project)

        controller = ProjectController(store)
        controller.load_project(project.project_id)
        self.assertIn("msi", controller.invalid_roots())
        with self.assertRaisesRegex(ProjectValidationError, "MSI Root 不存在"):
            controller.apply_changes()

        controller.update_root("msi", str(PACKAGE_ROOT / "inputs" / "msi"))
        controller.apply_changes()
        self.assertEqual(controller.invalid_roots(), {})

    def test_excel_from_another_machine_imports_with_repairable_stale_root(self) -> None:
        parsed = parse_config(DEMO_CONFIG)
        parsed.roots["model"] = self.root / "old-computer" / "models"
        with patch("ibis_ui.excel_importer.parse_config", return_value=parsed):
            project = ExcelImporter().import_project(DEMO_CONFIG, "Foreign Excel")
        self.assertEqual(project.config["roots"]["model"], str(parsed.roots["model"]))

    def test_log_is_written_under_workspace(self) -> None:
        workspace = self.root / "workspace"
        log_path = configure_file_logging(workspace)
        self.addCleanup(close_file_logging, log_path)
        logging.getLogger(LOGGER_NAME).warning("跨平台日志测试")
        for handler in logging.getLogger(LOGGER_NAME).handlers:
            handler.flush()
        self.assertEqual(log_path, workspace / "logs" / "ibis_automation.log")
        self.assertIn("跨平台日志测试", log_path.read_text(encoding="utf-8"))
        close_file_logging(log_path)

    def test_version_and_packaging_contract(self) -> None:
        metadata = app_metadata()
        self.assertEqual(metadata.version, APP_VERSION)
        self.assertTrue(metadata.git_commit)
        spec = (PACKAGE_ROOT / "packaging" / "IBIS_Automation.spec").read_text(encoding="utf-8")
        self.assertIn("resources/templates/t2b", spec)
        self.assertIn("resources/inputs", spec)
        ignore_rules = (PACKAGE_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dist/", ignore_rules)

    def test_path_neutral_snapshot_contains_stable_config_schema(self) -> None:
        project = ExcelImporter().import_project(DEMO_CONFIG, "Snapshot")
        payload = json.loads(json.dumps(project.config))
        payload["roots"] = {name: f"<{name.upper()}_ROOT>" for name in sorted(payload["roots"])}
        self.assertEqual(payload["modules"][0]["tr"]["TYP"], "20p")
        self.assertEqual(payload["modules"][0]["ibis_io_voltage_domain"], "VDDQ")
        self.assertEqual(payload["corners"]["TYP"]["voltages"]["VDDQ"], "0.5")
        self.assertEqual(payload["roots"]["template"], "<TEMPLATE_ROOT>")


if __name__ == "__main__":
    unittest.main()
