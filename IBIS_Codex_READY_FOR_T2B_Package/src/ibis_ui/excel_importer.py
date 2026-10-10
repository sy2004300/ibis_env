from __future__ import annotations

import hashlib
from pathlib import Path

from ibis_auto.config import parse_config
from ibis_auto.errors import IbisError

from .errors import ExcelImportError, ProjectValidationError
from .models import ProjectDocument, SourceExcel, core_config_to_payload, validate_config_payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ExcelImporter:
    """Read an existing Config workbook without ever writing to it."""

    def import_project(self, path: Path, project_name: str | None = None) -> ProjectDocument:
        source = path.expanduser().resolve()
        if not source.is_file():
            raise ExcelImportError("EXCEL_SOURCE_MISSING", f"Config Excel 不存在：{source}")
        if source.suffix.casefold() != ".xlsx":
            raise ExcelImportError("EXCEL_SOURCE_TYPE_INVALID", f"仅支持 .xlsx Config：{source}")
        before = file_sha256(source)
        try:
            config = parse_config(source)
        except IbisError as exc:
            raise ExcelImportError(exc.code, f"导入 Config 失败：{exc}") from exc
        after = file_sha256(source)
        if before != after:
            raise ExcelImportError("EXCEL_SOURCE_MUTATED", f"导入过程中原始 Excel 被意外修改：{source}")
        payload = core_config_to_payload(config)
        try:
            validate_config_payload(payload, check_paths=True)
        except ProjectValidationError as exc:
            raise ExcelImportError(exc.code, f"导入 Config 校验失败：{exc}") from exc
        return ProjectDocument.create(
            project_name or source.stem,
            "excel",
            payload,
            SourceExcel(str(source), before),
        )
