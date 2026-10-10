from __future__ import annotations

import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ibis_ui.controller import ProjectController
from ibis_ui.errors import ProjectValidationError, ResourceError
from ibis_ui.models import ProjectDocument, build_case_tree, validate_config_payload
from ibis_ui.presentation import case_tree_counts, filter_case_tree
from ibis_ui.project_store import ProjectStore
from ibis_ui.runtime import APP_VERSION, REQUIRED_TEMPLATES, ResourceResolver
from ibis_ui.source_preview import preview_msi, preview_spf
from ibis_ui.template_service import TemplateResourceService
from ibis_ui.theme import choose_ui_font
from ibis_ui.widgets import wheel_scroll_units


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "multi_module_project.json"


def _column_name(index: int) -> str:
    result = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _write_xlsx(path: Path, sheets: dict[str, list[list[str]]]) -> None:
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    sheet_xml: list[tuple[str, str]] = []
    workbook_rows = []
    relationship_rows = []
    override_rows = []
    for sheet_index, (name, rows) in enumerate(sheets.items(), 1):
        workbook_rows.append(f'<sheet name="{name}" sheetId="{sheet_index}" r:id="rId{sheet_index}"/>')
        relationship_rows.append(
            f'<Relationship Id="rId{sheet_index}" Type="{rel}/worksheet" Target="worksheets/sheet{sheet_index}.xml"/>'
        )
        override_rows.append(
            f'<Override PartName="/xl/worksheets/sheet{sheet_index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        xml_rows = []
        for row_index, row in enumerate(rows, 1):
            cells = []
            for column_index, value in enumerate(row):
                ref = f"{_column_name(column_index)}{row_index}"
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
            xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        sheet_xml.append(
            (f"xl/worksheets/sheet{sheet_index}.xml", f'<worksheet xmlns="{main}"><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
        )
    workbook = f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>{"".join(workbook_rows)}</sheets></workbook>'
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(relationship_rows)
        + "</Relationships>"
    )
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(override_rows)
        + "</Types>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        for filename, payload in sheet_xml:
            archive.writestr(filename, payload)


class UIPhase11Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_multi_module_fixture_tree_search_counts_and_switch_isolation(self) -> None:
        validate_config_payload(self.config, check_paths=False)
        tree = build_case_tree(self.config)
        self.assertEqual(case_tree_counts(tree), (4, 9))
        self.assertEqual([item["module"] for item in filter_case_tree(tree, "io_")], ["IO_DIFF", "IO_SE"])

        project = ProjectDocument.create("Multi Module", "ui", self.config)
        store = ProjectStore(self.root / "workspace")
        store.save(project)
        controller = ProjectController(store, resources=ResourceResolver(PACKAGE_ROOT))
        controller.load_project(project.project_id)
        controller.update_module("IO_DIFF", "tr.TYP", "31p")
        controller.update_module("IO_SE", "tf.TYP", "42p")
        self.assertEqual(controller.module("IO_DIFF")["tr"]["TYP"], "31p")
        self.assertEqual(controller.module("IO_DIFF")["tf"]["TYP"], "20p")
        self.assertEqual(controller.module("IO_SE")["tr"]["TYP"], "19p")
        self.assertEqual(controller.module("IO_SE")["tf"]["TYP"], "42p")

    def test_separate_duplicate_drv_rcv_rows_are_rejected_not_skipped(self) -> None:
        duplicate = copy.deepcopy(self.config)
        duplicate["modules"] = [copy.deepcopy(duplicate["modules"][0]), copy.deepcopy(duplicate["modules"][0])]
        duplicate["modules"][0]["generate_type"] = "DRV"
        duplicate["modules"][1]["generate_type"] = "RCV"
        with self.assertRaisesRegex(ProjectValidationError, "模块名称重复"):
            validate_config_payload(duplicate, check_paths=False)

    def test_template_root_is_optional_and_built_in_templates_are_visible(self) -> None:
        for name in ("model", "msi", "spf"):
            path = self.root / name
            path.mkdir()
            self.config["roots"][name] = str(path)
        self.config["roots"]["template"] = ""
        validate_config_payload(self.config, check_paths=True)
        service = TemplateResourceService(ResourceResolver(PACKAGE_ROOT))
        items = service.list_templates(self.config)
        self.assertEqual(tuple(item.filename for item in items), REQUIRED_TEMPLATES)
        self.assertIn("[Model]", service.read(self.config, "drv_diff.t2b"))

        self.config["roots"]["template"] = str(self.root / "missing-template-root")
        with self.assertRaisesRegex(ResourceError, "外部 T2B Template Root 不存在"):
            service.effective_root(self.config)

    def test_msi_multiple_files_and_sheets_preview_is_strict_and_read_only(self) -> None:
        msi_root = self.root / "msi"
        msi_root.mkdir()
        header = ["*PIN_NAME", "WIDTH", "DIRECTION"]
        first = msi_root / "io_diff.xlsx"
        second = msi_root / "mixed.xlsx"
        _write_xlsx(first, {"IO_DIFF": [header, ["PAD", "1", "IO"]]})
        _write_xlsx(
            second,
            {
                "IO_SE": [header, ["PAD", "1", "IO"]],
                "OUTC": [header, ["PAD", "1", "O"]],
                "INSE": [header, ["PAD", "1", "I"]],
            },
        )
        before = {path: path.read_bytes() for path in (first, second)}
        self.config["roots"]["msi"] = str(msi_root)
        report = preview_msi(self.config)
        self.assertEqual(len(report.files), 2)
        self.assertEqual(len(report.sheets), 4)
        self.assertEqual([item.status for item in report.modules], ["PASS"] * 4)
        self.assertEqual({item.sheet for item in report.modules}, {"IO_DIFF", "IO_SE", "OUTC", "INSE"})
        self.assertEqual(before, {path: path.read_bytes() for path in (first, second)})

    def test_msi_ambiguous_pin_columns_are_reported(self) -> None:
        msi_root = self.root / "msi"
        msi_root.mkdir()
        _write_xlsx(msi_root / "io_diff.xlsx", {"IO_DIFF": [["PIN_NAME", "Name", "WIDTH", "DIRECTION"], ["PAD", "PAD", "1", "IO"]]})
        self.config["modules"] = [self.config["modules"][0]]
        self.config["roots"]["msi"] = str(msi_root)
        report = preview_msi(self.config)
        self.assertEqual(report.modules[0].status, "ERROR")
        self.assertIn("候选列数量为 2", report.modules[0].message)

    def test_spf_max_typ_min_preview_and_ambiguity(self) -> None:
        spf_root = self.root / "spf"
        spf_root.mkdir()
        for module in ("IO_DIFF", "IO_SE", "OUTC", "INSE"):
            for key in ("rcbest", "typical", "rcworst"):
                (spf_root / f"{module}.{key}.spf").write_text(f".subckt {module} VDD VSS PAD\n.ends {module}\n", encoding="utf-8")
        self.config["roots"]["spf"] = str(spf_root)
        report = preview_spf(self.config)
        self.assertEqual(len(report.matches), 12)
        self.assertTrue(all(item.status == "PASS" for item in report.matches))
        self.assertTrue(all(item.pin_count == 3 for item in report.matches))

        (spf_root / "IO_DIFF.typical.duplicate.spf").write_text(".subckt IO_DIFF VDD VSS PAD\n.ends IO_DIFF\n", encoding="utf-8")
        duplicate = preview_spf(self.config)
        item = next(row for row in duplicate.matches if row.module == "IO_DIFF" and row.corner == "TYP")
        self.assertEqual(item.status, "ERROR")
        self.assertIn("匹配到 2 个", item.message)

    def test_font_fallback_and_wheel_normalization(self) -> None:
        self.assertEqual(choose_ui_font(["Arial", "Microsoft YaHei UI"], "Windows"), "Microsoft YaHei UI")
        self.assertEqual(choose_ui_font(["DejaVu Sans"], "Linux"), "DejaVu Sans")
        self.assertEqual(choose_ui_font([], "Windows"), "TkDefaultFont")
        self.assertEqual(wheel_scroll_units(120), -1)
        self.assertEqual(wheel_scroll_units(-240), 2)
        self.assertEqual(wheel_scroll_units(0, 4), -3)
        self.assertEqual(wheel_scroll_units(0, 5), 3)

    def test_ui11_version_and_windows_artifact_contract(self) -> None:
        self.assertEqual(APP_VERSION, "0.1.1")
        build_script = (PACKAGE_ROOT / "packaging" / "build_windows.py").read_text(encoding="utf-8")
        readme = (PACKAGE_ROOT / "packaging" / "WINDOWS_README.txt").read_text(encoding="utf-8")
        self.assertIn('OUTPUT_NAME = "IBIS_Automation_Windows_UI1_1"', build_script)
        self.assertIn("IBIS_Automation_Windows_UI1_1", readme)


if __name__ == "__main__":
    unittest.main()
