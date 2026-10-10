from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ibis_auto.ooxml import read_workbook
from ibis_auto.spf import parse as parse_spf


def _module_norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _header_norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold().lstrip("*"))


PIN_NAME_ALIASES = {"pinname", "name"}


@dataclass(frozen=True)
class MSISheetPreview:
    file: Path
    sheet: str
    pin_columns: tuple[str, ...]
    error: str = ""


@dataclass(frozen=True)
class MSIModulePreview:
    module: str
    status: str
    file: str = ""
    sheet: str = ""
    pin_column: str = ""
    message: str = ""


@dataclass(frozen=True)
class MSIPreviewReport:
    root: Path
    files: tuple[Path, ...]
    sheets: tuple[MSISheetPreview, ...]
    modules: tuple[MSIModulePreview, ...]


@dataclass(frozen=True)
class SPFCornerPreview:
    module: str
    corner: str
    status: str
    path: str = ""
    top_subckt: str = ""
    pin_count: int = 0
    message: str = ""


@dataclass(frozen=True)
class SPFPreviewReport:
    root: Path
    matches: tuple[SPFCornerPreview, ...]


def _mapping_by_module(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        str(item.get("module", "")).casefold(): item
        for item in config.get("msi_mappings", [])
        if isinstance(item, dict) and str(item.get("module", "")).strip()
    }


def preview_msi(config: dict[str, Any]) -> MSIPreviewReport:
    root = Path(str(config.get("roots", {}).get("msi", ""))).expanduser()
    files = tuple(sorted(root.glob("*.xlsx"))) if root.is_dir() else ()
    sheets: list[MSISheetPreview] = []
    for path in files:
        try:
            workbook = read_workbook(path)
        except Exception as exc:
            sheets.append(MSISheetPreview(path.resolve(), "", (), f"无法读取：{exc}"))
            continue
        if not workbook:
            sheets.append(MSISheetPreview(path.resolve(), "", (), "工作簿没有可读取的 Sheet"))
            continue
        for sheet_name, rows in workbook.items():
            header = rows[0] if rows else []
            pin_columns = tuple(value for value in header if _header_norm(value) in PIN_NAME_ALIASES)
            sheets.append(MSISheetPreview(path.resolve(), sheet_name, pin_columns))

    mappings = _mapping_by_module(config)
    module_results: list[MSIModulePreview] = []
    for module_row in config.get("modules", []):
        module = str(module_row.get("name", ""))
        mapping = mappings.get(module.casefold())
        if mapping:
            file_name = str(mapping.get("file", ""))
            sheet_name = str(mapping.get("sheet", ""))
            column_name = str(mapping.get("column", ""))
            candidates = [item for item in sheets if item.file.name.casefold() == file_name.casefold() and item.sheet.casefold() == sheet_name.casefold()]
            if len(candidates) != 1:
                module_results.append(MSIModulePreview(module, "ERROR", file_name, sheet_name, column_name, "Config MSI Mapping 找不到唯一 File/Sheet"))
                continue
            selected = candidates[0]
            if selected.error:
                module_results.append(MSIModulePreview(module, "ERROR", file_name, sheet_name, column_name, selected.error))
                continue
            if column_name and column_name.casefold() not in {name.casefold() for name in selected.pin_columns}:
                module_results.append(MSIModulePreview(module, "ERROR", file_name, sheet_name, column_name, "Pin Name Column 不存在或不是有效 PIN_NAME 列"))
                continue
            if not column_name and len(selected.pin_columns) != 1:
                module_results.append(MSIModulePreview(module, "ERROR", file_name, sheet_name, "", f"PIN_NAME 候选列数量为 {len(selected.pin_columns)}，无法唯一确定"))
                continue
            module_results.append(MSIModulePreview(module, "PASS", selected.file.name, selected.sheet, column_name or selected.pin_columns[0], "使用 Config MSI Mapping"))
            continue

        normalized = _module_norm(module)
        candidates = [
            item
            for item in sheets
            if not item.error and normalized in {_module_norm(item.file.stem), _module_norm(item.sheet)}
        ]
        if len(candidates) != 1:
            module_results.append(MSIModulePreview(module, "ERROR", message=f"MSI Source 数量为 {len(candidates)}，无法唯一确定"))
            continue
        selected = candidates[0]
        if len(selected.pin_columns) != 1:
            module_results.append(MSIModulePreview(module, "ERROR", selected.file.name, selected.sheet, message=f"PIN_NAME 候选列数量为 {len(selected.pin_columns)}，必须显式 Mapping"))
            continue
        module_results.append(MSIModulePreview(module, "PASS", selected.file.name, selected.sheet, selected.pin_columns[0], "按 Module/File/Sheet 名称唯一匹配"))
    return MSIPreviewReport(root.resolve() if root.exists() else root, files, tuple(sheets), tuple(module_results))


def preview_spf(config: dict[str, Any]) -> SPFPreviewReport:
    root = Path(str(config.get("roots", {}).get("spf", ""))).expanduser()
    spf_files = tuple(sorted(root.rglob("*.spf"))) if root.is_dir() else ()
    results: list[SPFCornerPreview] = []
    for module_row in config.get("modules", []):
        module = str(module_row.get("name", ""))
        module_pin_lists: dict[str, tuple[str, ...]] = {}
        module_indexes: list[int] = []
        for corner_name in ("MAX", "TYP", "MIN"):
            corner = config.get("corners", {}).get(corner_name, {})
            match_key = str(corner.get("spf_key", "")).strip()
            matches = [path for path in spf_files if module.casefold() in path.name.casefold() and match_key.casefold() in path.name.casefold()] if match_key else []
            module_indexes.append(len(results))
            if not match_key:
                results.append(SPFCornerPreview(module, corner_name, "ERROR", message="SPF Match Key 为空"))
                continue
            if len(matches) != 1:
                results.append(SPFCornerPreview(module, corner_name, "ERROR", message=f"匹配到 {len(matches)} 个 SPF（要求唯一）"))
                continue
            path = matches[0].resolve()
            try:
                top_subckt, pins = parse_spf(path)
            except Exception as exc:
                results.append(SPFCornerPreview(module, corner_name, "ERROR", str(path), message=f"SPF 解析失败：{exc}"))
                continue
            module_pin_lists[corner_name] = tuple(pins)
            status = "PASS" if module.casefold() == top_subckt.casefold() else "WARNING"
            message = "" if status == "PASS" else f"文件名 Module 与 TOP_SUBCKT {top_subckt} 不一致"
            results.append(SPFCornerPreview(module, corner_name, status, str(path), top_subckt, len(pins), message))
        if len(module_pin_lists) > 1 and len(set(module_pin_lists.values())) != 1:
            for index in module_indexes:
                current = results[index]
                if current.path:
                    results[index] = SPFCornerPreview(
                        current.module,
                        current.corner,
                        "ERROR",
                        current.path,
                        current.top_subckt,
                        current.pin_count,
                        "同一模块各 Corner 的 SPF Top Pin List 不一致",
                    )
    return SPFPreviewReport(root.resolve() if root.exists() else root, tuple(results))
