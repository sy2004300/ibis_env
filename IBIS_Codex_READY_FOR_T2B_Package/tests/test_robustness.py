from __future__ import annotations

import contextlib
import copy
import io
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from ibis_auto.errors import IbisError
from ibis_auto.ooxml import read_workbook
from ibis_auto.service import generate

ROOT = Path(__file__).resolve().parents[1]


def write_xlsx(path: Path, sheets: dict[str, list[list[str]]]) -> None:
    """Write the small inline-string XLSX fixtures used by integration tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_entries, relationships = [], []
    with zipfile.ZipFile(path, "w") as archive:
        for number, (name, rows) in enumerate(sheets.items(), 1):
            sheet_entries.append(f'<sheet name="{escape(name)}" sheetId="{number}" r:id="rId{number}"/>')
            relationships.append(f'<Relationship Id="rId{number}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{number}.xml"/>')
            xml_rows = []
            for row_number, row in enumerate(rows, 1):
                cells = []
                for column, value in enumerate(row):
                    if value is None: value = ""
                    letters, n = "", column + 1
                    while n: n, rem = divmod(n - 1, 26); letters = chr(65 + rem) + letters
                    cells.append(f'<c r="{letters}{row_number}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>')
                xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
            archive.writestr(f"xl/worksheets/sheet{number}.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + "</sheetData></worksheet>")
        archive.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + "".join(sheet_entries) + "</sheets></workbook>")
        archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(relationships) + "</Relationships>")
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/></Types>')


class Fixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "inputs", self.root / "inputs")
        shutil.copytree(ROOT / "templates", self.root / "templates")
        self.config_path = self.root / "inputs/config/ibis_config.xlsx"
        self.msi_path = self.root / "inputs/msi/demo_msi.xlsx"
        self.config = read_workbook(self.config_path)["IBIS_Config"]
        self.msi = read_workbook(self.msi_path)
        self.output = self.root / "generated"

    def close(self): self.temp.cleanup()
    def save_config(self): write_xlsx(self.config_path, {"IBIS_Config": self.config})
    def save_msi(self): write_xlsx(self.msi_path, self.msi)
    def row(self, rows, first): return next(row for row in rows if row and row[0] == first)
    def insert_before(self, rows, marker, row): rows.insert(next(i for i, item in enumerate(rows) if item and item[0].startswith(marker)), row)
    def run(self, **kwargs):
        self.save_config(); self.save_msi()
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream): result = generate(self.config_path, self.output, non_interactive=True, **kwargs)
        return result, stream.getvalue()
    def case(self): return self.output / "demo_phy_io_diff/drv/30ohm_ibis"
    def corner(self, name="typ"): return (self.case() / f"corner_drv_ron30_{name}.sp").read_text()
    def signal(self, name): return self.row(self.msi["demo_phy_io_diff"], name)


class RobustnessTests(unittest.TestCase):
    def setUp(self): self.fx = Fixture()
    def tearDown(self): self.fx.close()

    def assert_project_error(self, code):
        with self.assertRaises(IbisError) as caught: self.fx.run()
        self.assertEqual(caught.exception.code, code)

    def assert_case_error(self, code):
        result, _ = self.fx.run(); self.assertFalse(result.ready)
        self.assertTrue(any(r.status == "FAIL" and f"[{code}]" in r.message for r in result.cases), result.cases)

    def test_01_config_unreadable(self):
        self.fx.config_path.write_text("not an xlsx")
        with self.assertRaises(IbisError) as caught: generate(self.fx.config_path, self.fx.output, non_interactive=True)
        self.assertEqual(caught.exception.code, "CONFIG_READ_ERROR")

    def test_02_required_root_missing(self):
        self.fx.row(self.fx.config, "SPF Root")[1] = "./missing"; self.assert_project_error("ROOT_MISSING")

    def test_03_required_template_missing(self):
        (self.fx.root / "templates/t2b/rcv_se.t2b").unlink(); self.assert_project_error("TEMPLATE_LIBRARY_INCOMPLETE")

    def test_04_t2b_config_missing(self):
        (self.fx.root / "templates/t2b/_t2b_config.ini").unlink(); self.assert_project_error("TEMPLATE_LIBRARY_INCOMPLETE")

    def test_05_generate_type_invalid(self):
        self.fx.row(self.fx.config, "demo_phy_io_diff")[1] = "BAD"; self.assert_case_error("GENERATE_TYPE_INVALID")

    def test_06_msi_source_not_unique(self):
        write_xlsx(self.fx.root / "inputs/msi/second.xlsx", {"demo_phy_io_diff": self.fx.msi["demo_phy_io_diff"]}); self.assert_case_error("MSI_SOURCE_AMBIGUOUS")

    def test_07_multiple_pin_columns(self):
        rows = self.fx.msi["demo_phy_io_diff"]; rows[0].append("Pin Name")
        for row in rows[1:]: row.append(row[0] if row else "")
        self.assert_case_error("MSI_PIN_COLUMN_AMBIGUOUS")

    def test_08_bus_width_conflict(self):
        self.fx.signal("reg_txffe[3:0]")[1] = "3"; self.assert_case_error("MSI_BUS_WIDTH_CONFLICT")

    def test_09_spf_not_found(self):
        self.fx.row(self.fx.config, "SPF Match Key")[1] = "absent"; self.assert_case_error("SPF_NOT_FOUND")

    def test_10_spf_ambiguous(self):
        source = self.fx.root / "inputs/spf/demo_phy_io_diff.rcbest.spf"; shutil.copy(source, source.with_name("demo_phy_io_diff.rcbest.copy.spf")); self.assert_case_error("SPF_AMBIGUOUS")

    def test_11_spf_top_name_warning_and_cell(self):
        for path in (self.fx.root / "inputs/spf").glob("*.spf"):
            path.write_text(path.read_text().replace("demo_phy_io_diff", "actual_top"))
        result, output = self.fx.run(); self.assertTrue(result.ready); self.assertIn("警告", output); self.assertTrue(self.fx.corner())
        self.assertTrue((self.fx.case() / "ckt_topology.sp").read_text().rstrip().endswith("actual_top"))

    def test_12_calibration_missing(self):
        self.fx.msi["demo_phy_io_diff"] = [r for r in self.fx.msi["demo_phy_io_diff"] if not r or r[0] != "txzqcal_pd[7:0]"]; self.assert_case_error("CALIBRATION_SIGNAL_MISSING")

    def _override(self, direction="DRV", corner="ALL", value="0"):
        self.fx.insert_before(self.fx.config, "9.", ["demo_phy_io_diff", direction, corner, "reg_txffe[3:0]", value])

    def test_13_override_exact_duplicate(self): self._override(); self._override(); self.assert_case_error("OVERRIDE_SCOPE_CONFLICT")
    def test_14_override_overlap(self): self._override("BOTH", "ALL"); self._override("DRV", "TYP"); self.assert_case_error("OVERRIDE_SCOPE_CONFLICT")

    def test_15_atypical_process_warns_and_continues(self):
        self.fx.row(self.fx.config, "Process")[1:4] = ["TT", "TT", "SS"]
        result, output = self.fx.run(); self.assertTrue(result.ready); self.assertIn("警告：Process/Corner 非常规关系", output)

    def test_16_target_impedance_missing(self):
        for name in ("reg_txslice_pd[3:0]", "reg_txslice_pu[3:0]"):
            row = self.fx.signal(name); row[8] = row[8].replace("1111: 30ohm", "1111: 31ohm"); row[9] = row[9].replace("1111: 30ohm", "1111: 31ohm")
        self.assert_case_error("TARGET_RON_MISSING")

    def test_17_minimum_code_selected_independently(self):
        for name in ("reg_txslice_pd[3:0]", "reg_txslice_pu[3:0]"):
            row = self.fx.signal(name); row[8] += "\n1110: 30ohm"; row[9] += "\n1110: 30ohm"
        result, _ = self.fx.run(); self.assertTrue(result.ready); self.assertIn("4'b1110", self.fx.corner())

    def test_18_pu_pd_maps_are_independent(self):
        pu = self.fx.signal("reg_txslice_pu[3:0]"); pu[8] += "\n1110: 30ohm"; pu[9] += "\n1110: 30ohm"
        result, _ = self.fx.run(); self.assertTrue(result.ready); text = self.fx.corner()
        self.assertIn("vreg_txslice_pd0 reg_txslice_pd[0] 0 dc vdd_typ", text)
        self.assertIn("vreg_txslice_pu0 reg_txslice_pu[0] 0 dc 0", text)

    def _invalid_default(self, value): self.fx.signal("reg_txffe[3:0]")[7] = value; self.assert_case_error("INVALID_LOGIC_VALUE")
    def test_19_default_x(self): self._invalid_default("X")
    def test_20_default_z(self): self._invalid_default("Z")
    def test_21_default_dash(self): self._invalid_default("-")
    def test_22_default_blank(self): self._invalid_default("")
    def test_23_default_unparseable(self): self._invalid_default("nonsense")

    def test_24_logic_one_missing_domain(self):
        row = self.fx.signal("reg_txffe[3:0]"); row[5] = ""; row[7] = "4'b0001"; self.assert_case_error("POWER_DOMAIN_MISSING")

    def test_25_logic_one_unknown_domain(self):
        row = self.fx.signal("reg_txffe[3:0]"); row[5] = "VUNKNOWN"; row[7] = "4'b0001"; self.assert_case_error("POWER_DOMAIN_MISSING")

    def test_26_all_zero_missing_domain_warns(self):
        self.fx.signal("reg_txffe[3:0]")[5] = ""; result, output = self.fx.run(); self.assertTrue(result.ready); self.assertIn("警告", output)

    def test_27_output_has_no_local_source(self):
        self.fx.signal("reg_txffe[3:0]")[2] = "Output"; result, _ = self.fx.run(); self.assertTrue(result.ready); self.assertNotIn("vreg_txffe", self.fx.corner())

    def test_28_io_has_no_local_source(self):
        self.fx.signal("reg_txffe[3:0]")[2] = "Inout"; result, _ = self.fx.run(); self.assertTrue(result.ready); self.assertNotIn("vreg_txffe", self.fx.corner())

    def test_29_bus_expands_msb_to_lsb(self):
        self.fx.run(); text = self.fx.corner(); positions = [text.index(f"reg_txffe{i}") for i in (3, 2, 1, 0)]; self.assertEqual(positions, sorted(positions))

    def test_30_zero_bit_is_explicit(self): self.fx.run(); self.assertIn("reg_txffe[0]", self.fx.corner())
    def test_31_logic_zero_is_dc_zero(self): self.fx.run(); self.assertIn("reg_txffe[0] 0 dc 0", self.fx.corner())

    def test_32_logic_one_uses_corner_domain(self):
        self.fx.signal("reg_txffe[3:0]")[7] = "4'b0001"; self.fx.run(); self.assertIn("reg_txffe[0] 0 dc vdd_typ", self.fx.corner())

    def test_33_model_library_missing(self):
        (self.fx.root / "inputs/models/spectre/rbd.lib").unlink(); self.assert_case_error("MODEL_FILE_MISSING")

    def test_34_spice_type_unsupported(self):
        path = self.fx.root / "templates/t2b/drv_diff.t2b"; path.write_text(path.read_text().replace("[Spice type]  spectre", "[Spice type]  xyce")); self.assert_case_error("SPICE_TYPE_INVALID")

    def test_35_topology_preserves_spf_order(self):
        self.fx.run(); topology = (self.fx.case() / "ckt_topology.sp").read_text(); self.assertLess(topology.index("VDD"), topology.index("vddq")); self.assertLess(topology.index("txoe"), topology.index("txdat"))

    def test_36_only_explicit_aliases_change(self):
        self.fx.run(); topology = (self.fx.case() / "ckt_topology.sp").read_text(); self.assertIn("ipadt ipadc", topology); self.assertIn("reg_txffe[3]", topology)

    def _append(self, scope, body): self.fx.insert_before(self.fx.config, "7.", ["demo_phy_io_diff", scope, body])
    def test_37_append_scope(self):
        self._append("RCV", "* rcv only"); self._append("BOTH", "* both"); self.fx.run(); text = (self.fx.case() / "ckt_topology.sp").read_text(); self.assertNotIn("rcv only", text); self.assertIn("* both", text)

    def test_38_append_order(self):
        self._append("DRV", "* first"); self._append("DRV", "* second"); self.fx.run(); text = (self.fx.case() / "ckt_topology.sp").read_text(); self.assertLess(text.index("* first"), text.index("* second"))

    def test_39_component_has_all_corner_values(self):
        self.fx.run(); text = (self.fx.case() / "component.sp").read_text()
        for domain in ("vdd", "vddq", "vss"):
            for corner in ("max", "typ", "min"): self.assertIn(f".PARAM {domain}_{corner}=", text)

    def test_40_t2b_controlled_sources_commented(self):
        self.fx.run(); text = self.fx.corner(); self.assertIn("*vvddq", text); self.assertIn("*vvss", text); self.assertIn("*vtxoe", text); self.assertIn("*vtxdat", text)

    def test_41_pads_have_no_fake_source(self):
        self.fx.run(); text = self.fx.corner(); self.assertNotIn("vipadt", text); self.assertNotIn("vipadc", text)

    def test_42_temperature_not_in_corner(self):
        self.fx.run(); text = self.fx.corner(); self.assertNotIn("25", text); self.assertNotIn("temperature", text.casefold())

    def test_43_case_error_isolation(self):
        module = self.fx.row(self.fx.config, "demo_phy_io_diff"); module[2] = "Y"; module[3] = "Y"
        pu = self.fx.signal("reg_txslice_pu[3:0]")
        for column in (8, 9):
            pu[column] = pu[column].replace("1101: 34ohm", "1101: 35ohm").replace("1110: 34ohm", "1110: 35ohm")
        result, _ = self.fx.run(); statuses = {r.key: r.status for r in result.cases}; self.assertEqual(statuses["demo_phy_io_diff/DRV/30ohm"], "UNVALIDATED"); self.assertEqual(statuses["demo_phy_io_diff/DRV/34ohm"], "FAIL")

    def test_44_module_error_isolation(self):
        # A second bad module must not prevent the original module from completing.
        self.fx.insert_before(self.fx.config, "3.", ["bad_module", "DRV", "Y"])
        result, _ = self.fx.run(); statuses = {r.key: r.status for r in result.cases}; self.assertEqual(statuses["demo_phy_io_diff/DRV/30ohm"], "UNVALIDATED"); self.assertEqual(statuses["bad_module/DRV/30ohm"], "FAIL")

    def test_45_project_error_stops_project(self):
        (self.fx.root / "templates/t2b/drv_diff.t2b").unlink()
        with self.assertRaises(IbisError) as caught: self.fx.run()
        self.assertEqual(caught.exception.level, "PROJECT"); self.assertFalse(self.fx.output.exists())
