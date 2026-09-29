"""Small, dependency-free, read-only OOXML table reader."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _column(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group()
    result = 0
    for char in letters:
        result = result * 26 + ord(char) - 64
    return result - 1


def read_workbook(path: Path) -> dict[str, list[list[str]]]:
    """Return workbook sheets as dense string rows without mutating the file."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"无法读取 Excel：{path}（{exc}）") from exc
    with archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in item.iter(f"{{{MAIN}}}t")) for item in root]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in relationships}
        result = {}
        for sheet in workbook.find(f"{{{MAIN}}}sheets"):
            target = targets[sheet.attrib[f"{{{REL}}}id"]].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            xml = ET.fromstring(archive.read(target))
            rows: list[list[str]] = []
            for row in xml.findall(f".//{{{MAIN}}}sheetData/{{{MAIN}}}row"):
                values: dict[int, str] = {}
                for cell in row.findall(f"{{{MAIN}}}c"):
                    kind = cell.attrib.get("t")
                    value_node = cell.find(f"{{{MAIN}}}v")
                    value = "" if value_node is None else (value_node.text or "")
                    if kind == "s" and value:
                        value = shared[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(f"{{{MAIN}}}t"))
                    values[_column(cell.attrib["r"])] = value
                if values:
                    dense = [""] * (max(values) + 1)
                    for index, value in values.items():
                        dense[index] = value.strip()
                    rows.append(dense)
            result[sheet.attrib["name"]] = rows
        return result

