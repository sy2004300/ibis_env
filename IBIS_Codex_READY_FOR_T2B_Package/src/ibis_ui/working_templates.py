from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ProjectStorageError, ProjectValidationError
from .template_selection import definition, effective_template_id, selection_for


PLACEHOLDER_PATTERN = re.compile(r"{{([A-Z0-9_/]+)}}")
SUPPORTED_PLACEHOLDERS = {
    "TOP_SUBCKT", "RON", "DATE_YYYY/MM", "SPICE_TYPE", "SPICE_COMMAND",
    "TEMP_TYP", "TEMP_MIN", "TEMP_MAX", "VOLT_TYP", "VOLT_MIN", "VOLT_MAX",
    "VIH_TYP", "VIH_MIN", "VIH_MAX", "TR_TYP", "TR_MIN", "TR_MAX",
    "TF_TYP", "TF_MIN", "TF_MAX", "VMEAS_TYP", "VMEAS_MIN", "VMEAS_MAX",
    "VINH_TYP", "VINH_MIN", "VINH_MAX", "VINL_TYP", "VINL_MIN", "VINL_MAX",
}
REQUIRED_SECTIONS = ("[IBIS Ver]", "[Spice type]", "[Temperature Range]", "[Voltage Range]", "[Pin]", "[Model file]", "[ExtSpiceCmd]")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "template"


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary:
            temporary.unlink(missing_ok=True)
        raise ProjectStorageError("WORKING_TEMPLATE_SAVE_FAILED", f"工作模板保存失败：{path}（{exc}）") from exc


@dataclass(frozen=True)
class TemplateValidation:
    valid: bool
    errors: tuple[str, ...]
    placeholders: tuple[str, ...]
    spice_type_expression: str


def validate_template_text(text: str, direction: str, topology: str) -> TemplateValidation:
    errors: list[str] = []
    if not text.strip():
        errors.append("模板正文为空")
    for section in REQUIRED_SECTIONS:
        if section.casefold() not in text.casefold():
            errors.append(f"缺少关键 Section：{section}")
    placeholders = tuple(sorted(set(PLACEHOLDER_PATTERN.findall(text))))
    unknown = sorted(set(placeholders) - SUPPORTED_PLACEHOLDERS)
    if unknown:
        errors.append(f"存在未知占位符：{', '.join(unknown)}")
    if "TOP_SUBCKT" not in placeholders or "RON" not in placeholders:
        errors.append("模板必须保留 {{TOP_SUBCKT}} 和 {{RON}} 动态占位符")
    spice = re.search(r"^\[Spice type\]\s+(.+?)\s*$", text, re.I | re.M)
    spice_expression = spice.group(1).strip() if spice else ""
    if spice_expression not in {"{{SPICE_TYPE}}", "spectre", "Spectre", "hspice", "HSPICE"}:
        errors.append(f"[Spice type] 无效：{spice_expression or '(空)'}")
    direction = direction.upper()
    if f"corner_{direction.casefold()}_ron{{{{RON}}}}" not in text:
        errors.append(f"模板与 {direction} 方向不兼容：Model file 未引用对应 Corner")
    topology = topology.upper()
    has_diff = "[Diff pin]" in text
    if topology == "DIFF" and not has_diff:
        errors.append("DIFF 模板缺少 [Diff pin]")
    if topology == "SE" and has_diff:
        errors.append("SE 模板不应包含 [Diff pin]")
    return TemplateValidation(not errors, tuple(errors), placeholders, spice_expression)


class WorkingTemplateService:
    def __init__(self, project_dir: Path, builtin_root: Path, project_id: str, workflow: dict[str, Any]):
        self.project_dir = project_dir
        self.builtin_root = builtin_root
        self.project_id = project_id
        self.workflow = workflow
        self.records = workflow.setdefault("working_templates", {})
        self.library = workflow.setdefault("template_library", {})

    @staticmethod
    def key(module: str, direction: str) -> str:
        return f"{module}|{direction.upper()}"

    def _path(self, module: str, direction: str) -> Path:
        return self.project_dir / "templates" / "working" / _safe(module) / f"{direction.casefold()}.t2b"

    def create(self, config: dict[str, Any], module: str, direction: str, source_template_id: str | None = None) -> dict[str, Any]:
        direction = direction.upper()
        selection = selection_for(config, module)
        topology = str(selection.get("topology", "")).upper()
        template_id = source_template_id or effective_template_id(config, module, direction)
        item = definition(template_id)
        if item is None:
            custom = self.library.get(str(template_id))
            if not custom:
                raise ProjectValidationError("WORKING_TEMPLATE_SOURCE_INVALID", f"工作模板来源不存在：{template_id}")
            source = Path(custom["path"])
        else:
            if item.direction != direction or item.topology != topology:
                raise ProjectValidationError("WORKING_TEMPLATE_SOURCE_MISMATCH", f"模板 {item.display_name} 与 {direction}/{topology} 不兼容")
            source = self.builtin_root / item.filename
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProjectStorageError("WORKING_TEMPLATE_SOURCE_READ_FAILED", f"无法读取模板来源：{source}（{exc}）") from exc
        return self.save(config, module, direction, text, source_template_id=template_id, display_name=f"{module} {direction} 工作模板")

    def save(
        self,
        config: dict[str, Any],
        module: str,
        direction: str,
        text: str,
        *,
        source_template_id: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        direction = direction.upper()
        topology = str(selection_for(config, module).get("topology", "")).upper()
        validation = validate_template_text(text, direction, topology)
        if not validation.valid:
            raise ProjectValidationError("WORKING_TEMPLATE_INVALID", "；".join(validation.errors))
        key = self.key(module, direction)
        previous = self.records.get(key, {})
        version = int(previous.get("version", 0)) + 1
        created_at = str(previous.get("created_at", "")) or _now()
        history = self.project_dir / "templates" / "history" / _safe(module) / direction.casefold() / f"v{version:04d}.t2b"
        _atomic_text(history, text)
        record = {
            "template_id": str(previous.get("template_id") or f"project:{self.project_id}:{_safe(module)}:{direction.casefold()}"),
            "display_name": display_name or str(previous.get("display_name") or f"{module} {direction} 工作模板"),
            "module": module, "direction": direction, "topology": topology,
            "created_at": created_at, "modified_at": _now(), "content_hash": _hash(text),
            "source_template_id": source_template_id or previous.get("source_template_id") or effective_template_id(config, module, direction),
            "version": version, "path": str(history), "history_path": str(history),
            "validation": "PASS",
        }
        self.records[key] = record
        return record

    def read(self, module: str, direction: str) -> str:
        record = self.records.get(self.key(module, direction))
        if not record:
            raise ProjectValidationError("WORKING_TEMPLATE_MISSING", f"模块 {module} {direction} 尚未创建工作模板")
        path = Path(record["path"])
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProjectStorageError("WORKING_TEMPLATE_READ_FAILED", f"工作模板无法读取：{path}（{exc}）") from exc

    def history(self, module: str, direction: str) -> list[dict[str, Any]]:
        record = self.records.get(self.key(module, direction), {})
        maximum = int(record.get("version", 0))
        root = self.project_dir / "templates" / "history" / _safe(module) / direction.casefold()
        result = []
        for version in range(1, maximum + 1):
            path = root / f"v{version:04d}.t2b"
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                result.append({"version": version, "path": str(path), "content_hash": _hash(text)})
        return result

    def restore(self, config: dict[str, Any], module: str, direction: str, version: int) -> dict[str, Any]:
        match = next((row for row in self.history(module, direction) if row["version"] == version), None)
        if not match:
            raise ProjectValidationError("WORKING_TEMPLATE_VERSION_MISSING", f"工作模板历史版本不存在：v{version}")
        return self.save(config, module, direction, Path(match["path"]).read_text(encoding="utf-8"))

    def restore_builtin(self, config: dict[str, Any], module: str, direction: str) -> dict[str, Any]:
        return self.create(config, module, direction, effective_template_id(config, module, direction))

    def save_as_library(self, module: str, direction: str, display_name: str) -> dict[str, Any]:
        text = self.read(module, direction)
        working = self.records[self.key(module, direction)]
        digest = _hash(text)
        template_id = f"user:{digest[:16]}"
        path = self.project_dir / "templates" / "library" / f"{_safe(display_name)}_{digest[:8]}.t2b"
        if not path.exists():
            _atomic_text(path, text)
        record = {
            "template_id": template_id, "display_name": display_name,
            "direction": direction.upper(), "topology": working["topology"],
            "created_at": _now(), "modified_at": _now(), "content_hash": digest,
            "source_template_id": working["template_id"], "version": 1, "path": str(path),
        }
        self.library[template_id] = record
        return record

    def diff(self, module: str, direction: str, candidate: str) -> str:
        current = self.read(module, direction)
        return "".join(difflib.unified_diff(current.splitlines(True), candidate.splitlines(True), fromfile="已保存", tofile="当前编辑"))

    def resolve_path(self, config: dict[str, Any], module: str, direction: str, *, validate: bool = True) -> Path:
        """Use an existing project customization, otherwise read the selected source."""
        record = self.records.get(self.key(module, direction))
        item = definition(effective_template_id(config, module, direction))
        explicit = self.workflow.get("template_sources", {}).get(self.key(module, direction), {})
        kind = explicit.get("kind")
        if kind == "外部模板" and explicit.get("path"):
            path = Path(explicit["path"])
            topology = item.topology if item else str(selection_for(config, module).get("topology", ""))
        elif kind == "内置母模板" and item:
            from .runtime import ResourceResolver
            path = ResourceResolver.current().template_root / item.filename
            topology = item.topology
        elif record and kind in {None, "项目自定义模板"}:
            path = Path(record["path"])
            topology = str(record["topology"])
        elif item:
            path = self.builtin_root / item.filename
            topology = item.topology
        else:
            raise ProjectValidationError("TEMPLATE_MAPPING_MISSING", f"模块 {module} {direction} 无法匹配模板，请检查模板选择。")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProjectStorageError("TEMPLATE_READ_FAILED", f"模块 {module} {direction} 模板无法读取：{path}（{exc}）") from exc
        validation = validate_template_text(text, direction, topology)
        if validate and not validation.valid:
            raise ProjectValidationError("WORKING_TEMPLATE_INVALID", f"{module} {direction}：" + "；".join(validation.errors))
        return path

    def generation_paths(self, config: dict[str, Any], selected=None) -> dict[tuple[str, str], Path]:
        result: dict[tuple[str, str], Path] = {}
        wanted = {(key[0], key[1]) for key in selected} if selected is not None else None
        for module in config.get("modules", []):
            name = str(module["name"])
            directions = ("DRV", "RCV") if str(module["generate_type"]).upper() == "BOTH" else (str(module["generate_type"]).upper(),)
            for direction in directions:
                if wanted is None or (name, direction) in wanted:
                    result[(name, direction)] = self.resolve_path(config, name, direction)
        return result
