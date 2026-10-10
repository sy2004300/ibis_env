from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ibis_auto.model import Config

from .errors import ProjectValidationError


PROJECT_SCHEMA_VERSION = 1
CORNER_NAMES = ("MAX", "TYP", "MIN")
ROOT_NAMES = ("model", "msi", "spf", "template")
EXTERNAL_ROOT_NAMES = ("model", "msi", "spf")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_config_payload() -> dict[str, Any]:
    return {
        "roots": {name: "" for name in ROOT_NAMES},
        "modules": [],
        "corners": {
            name: {
                "name": name,
                "process": "",
                "temperature": "",
                "spf_key": "",
                "voltages": {},
                "calibration": {},
            }
            for name in CORNER_NAMES
        },
        "voltage_order": [],
        "simulation_options": [],
        "aliases": [],
        "appends": [],
        "templates": [],
        "overrides": [],
        "attribute_overrides": [],
        "msi_mappings": [],
        "spice_type": "spectre",
        "spice_command": "spectre +preset=mx +spice +mt=4",
    }


def core_config_to_payload(config: Config) -> dict[str, Any]:
    return {
        "roots": {name: str(path) for name, path in config.roots.items()},
        "modules": [
            {
                "name": plan.name,
                "generate_type": plan.generate_type,
                "impedances": list(plan.impedances),
                "ibis_io_voltage_domain": plan.ibis_io_voltage_domain,
                "ibis_vih_voltage_domain": plan.ibis_vih_voltage_domain,
                "tr": dict(plan.tr),
                "tf": dict(plan.tf),
            }
            for plan in config.modules
        ],
        "corners": {
            name: {
                "name": corner.name,
                "process": corner.process,
                "temperature": corner.temperature,
                "spf_key": corner.spf_key,
                "voltages": dict(corner.voltages),
                "calibration": dict(corner.calibration),
            }
            for name, corner in config.corners.items()
        },
        "voltage_order": list(config.voltage_order),
        "simulation_options": list(config.simulation_options),
        "aliases": [
            {"module": module, "direction": direction, "original_pin": pin, "alias": alias}
            for (module, direction, pin), alias in config.aliases.items()
        ],
        "appends": [
            {"module": module, "direction": direction, "body": body}
            for module, direction, body in config.appends
        ],
        "templates": [
            {"module": module, "direction": direction, "template_type": template_type}
            for (module, direction), template_type in config.templates.items()
        ],
        "overrides": copy.deepcopy(config.overrides),
        "attribute_overrides": copy.deepcopy(config.attribute_overrides),
        "msi_mappings": [
            {"module": module, "file": value[0], "sheet": value[1], "column": value[2]}
            for module, value in config.msi_mappings.items()
        ],
        "spice_type": config.spice_type,
        "spice_command": config.spice_command,
    }


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectValidationError("PROJECT_SCHEMA_INVALID", f"项目配置字段 {label} 格式错误")
    return value


def validate_config_payload(payload: dict[str, Any], check_paths: bool = False) -> None:
    payload = _require_mapping(payload, "config")
    roots = _require_mapping(payload.get("roots"), "roots")
    modules = payload.get("modules")
    corners = _require_mapping(payload.get("corners"), "corners")
    voltage_order = payload.get("voltage_order")
    if not isinstance(modules, list) or not isinstance(voltage_order, list):
        raise ProjectValidationError("PROJECT_SCHEMA_INVALID", "项目 Modules 或 Voltage Domain 格式错误")

    for name in CORNER_NAMES:
        corner = _require_mapping(corners.get(name), f"Corner {name}")
        _require_mapping(corner.get("voltages"), f"Corner {name} Voltage")
        _require_mapping(corner.get("calibration"), f"Corner {name} Calibration")

    if modules:
        for root_name in EXTERNAL_ROOT_NAMES:
            raw = str(roots.get(root_name, "")).strip()
            if not raw:
                raise ProjectValidationError("PROJECT_ROOT_MISSING", f"项目缺少 {root_name.upper()} Root")
            if check_paths and not Path(raw).is_dir():
                raise ProjectValidationError("PROJECT_ROOT_INVALID", f"项目 {root_name.upper()} Root 不存在：{raw}")
        template_override = str(roots.get("template", "")).strip()
        if check_paths and template_override and not Path(template_override).is_dir():
            raise ProjectValidationError(
                "PROJECT_TEMPLATE_OVERRIDE_INVALID",
                f"外部 T2B Template Root 不存在：{template_override}；请修正或清空以使用软件内置模板",
            )

    known_domains = {str(name).casefold() for name in voltage_order}
    seen_modules: set[str] = set()
    template_keys = {
        (str(item.get("module", "")).casefold(), str(item.get("direction", "")).upper())
        for item in payload.get("templates", [])
        if isinstance(item, dict)
    }
    for module in modules:
        module = _require_mapping(module, "Module")
        name = str(module.get("name", "")).strip()
        if not name:
            raise ProjectValidationError("PROJECT_MODULE_INVALID", "模块名称不能为空")
        normalized = name.casefold()
        if normalized in seen_modules:
            raise ProjectValidationError("PROJECT_MODULE_DUPLICATE", f"模块名称重复：{name}")
        seen_modules.add(normalized)

        generate_type = str(module.get("generate_type", "")).upper()
        if generate_type not in {"DRV", "RCV", "BOTH"}:
            raise ProjectValidationError("PROJECT_GENERATE_TYPE_INVALID", f"模块 {name} 的 Generate Type 非法：{generate_type!r}")
        impedances = module.get("impedances")
        if not isinstance(impedances, list) or any(not isinstance(value, int) or value <= 0 for value in impedances):
            raise ProjectValidationError("PROJECT_IMPEDANCE_INVALID", f"模块 {name} 的 Ron 列表必须是正整数")
        if len(impedances) != len(set(impedances)):
            raise ProjectValidationError("PROJECT_IMPEDANCE_DUPLICATE", f"模块 {name} 的 Ron 存在重复值")

        for field, label in (
            ("ibis_io_voltage_domain", "IBIS IO Voltage Domain"),
            ("ibis_vih_voltage_domain", "IBIS VIH Voltage Domain"),
        ):
            value = str(module.get(field, "")).strip()
            if not value or value.casefold() not in known_domains:
                raise ProjectValidationError("PROJECT_VOLTAGE_DOMAIN_INVALID", f"模块 {name} 的 {label} 未在 Voltage Domain 中定义：{value!r}")
        for field, label in (("tr", "Tr"), ("tf", "Tf")):
            values = _require_mapping(module.get(field), f"模块 {name} {label}")
            for corner_name in CORNER_NAMES:
                if not str(values.get(corner_name, "")).strip():
                    raise ProjectValidationError("PROJECT_TIMING_MISSING", f"模块 {name} 缺少 {label} {corner_name}")

        directions = ("DRV", "RCV") if generate_type == "BOTH" else (generate_type,)
        for direction in directions:
            if (normalized, direction) not in template_keys:
                raise ProjectValidationError("PROJECT_TEMPLATE_MAPPING_MISSING", f"模块 {name} {direction} 缺少 T2B Template Mapping")


@dataclass
class SourceExcel:
    path: str
    sha256: str
    sheet: str = "IBIS_Config"

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256, "sheet": self.sheet}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceExcel:
        return cls(str(data["path"]), str(data["sha256"]), str(data.get("sheet", "IBIS_Config")))


@dataclass
class ProjectDocument:
    project_id: str
    name: str
    mode: str
    config: dict[str, Any]
    created_at: str
    updated_at: str
    source_excel: SourceExcel | None = None
    schema_version: int = PROJECT_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        name: str,
        mode: str,
        config: dict[str, Any] | None = None,
        source_excel: SourceExcel | None = None,
    ) -> ProjectDocument:
        project_name = name.strip()
        if not project_name:
            raise ProjectValidationError("PROJECT_NAME_MISSING", "项目名称不能为空")
        if mode not in {"excel", "ui"}:
            raise ProjectValidationError("PROJECT_MODE_INVALID", f"项目模式非法：{mode}")
        now = utc_now()
        payload = copy.deepcopy(config if config is not None else empty_config_payload())
        validate_config_payload(payload, check_paths=False)
        return cls(str(uuid4()), project_name, mode, payload, now, now, source_excel)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "name": self.name,
            "mode": self.mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_excel": self.source_excel.to_dict() if self.source_excel else None,
            "config": copy.deepcopy(self.config),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectDocument:
        if data.get("schema_version") != PROJECT_SCHEMA_VERSION:
            raise ProjectValidationError("PROJECT_SCHEMA_VERSION_UNSUPPORTED", f"不支持的项目 Schema 版本：{data.get('schema_version')!r}")
        try:
            project_id = str(UUID(str(data["project_id"])))
            name = str(data["name"])
            mode = str(data["mode"])
            config = copy.deepcopy(data["config"])
            created_at = str(data["created_at"])
            updated_at = str(data["updated_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectValidationError("PROJECT_SCHEMA_INVALID", f"项目文件格式错误：{exc}") from exc
        if mode not in {"excel", "ui"} or not name.strip():
            raise ProjectValidationError("PROJECT_SCHEMA_INVALID", "项目名称或模式非法")
        validate_config_payload(config, check_paths=False)
        source = data.get("source_excel")
        try:
            source_excel = SourceExcel.from_dict(source) if source else None
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectValidationError("PROJECT_SCHEMA_INVALID", f"项目 Excel 来源格式错误：{exc}") from exc
        return cls(project_id, name, mode, config, created_at, updated_at, source_excel)

    def clone_config(self) -> dict[str, Any]:
        return copy.deepcopy(self.config)


def build_case_tree(config: dict[str, Any]) -> list[dict[str, Any]]:
    tree = []
    for module in config.get("modules", []):
        generate_type = str(module.get("generate_type", "")).upper()
        directions = ["DRV", "RCV"] if generate_type == "BOTH" else ([generate_type] if generate_type else [])
        tree.append({
            "module": module.get("name", ""),
            "directions": [
                {"direction": direction, "rons": list(module.get("impedances", []))}
                for direction in directions
            ],
        })
    return tree
