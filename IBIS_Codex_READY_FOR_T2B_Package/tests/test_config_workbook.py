from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class ConfigWorkbookTests(unittest.TestCase):
    def test_dropdowns_are_scoped_to_their_own_data_sections(self):
        path = ROOT / "inputs/config/ibis_config.xlsx"
        with zipfile.ZipFile(path) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

        validations = sheet.find(f"{{{MAIN}}}dataValidations")
        self.assertIsNotNone(validations)
        actual = {
            (item.attrib["sqref"], item.findtext(f"{{{MAIN}}}formula1"))
            for item in validations
        }
        expected = {
            ("B11:B12", '"DRV,RCV,BOTH"'),
            ("B42:B48", '"DRV,RCV,BOTH"'),
            ("B51:B54", '"DRV,RCV,BOTH"'),
            ("B57:B59", '"DRV,RCV"'),
            ("C57:C59", '"drv_se,drv_diff,rcv_se,rcv_diff"'),
            ("B62:B67", '"DRV,RCV,BOTH"'),
            ("C62:C67", '"MAX,TYP,MIN,ALL"'),
            ("C70:C74", '"POWER_DOMAIN"'),
        }
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
