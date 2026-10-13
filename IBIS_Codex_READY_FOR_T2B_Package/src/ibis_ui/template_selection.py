from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .errors import ProjectValidationError


AUTO_MODE = "auto"
MANUAL_MODE = "manual"
TOPOLOGIES = ("DIFF", "SE")
DIRECTIONS = ("DRV", "RCV")


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    filename: str
    topology: str
    direction: str
    display_name: str


TEMPLATE_CATALOG = (
    TemplateDefinition("builtin:drv_diff", "drv_diff.t2b", "DIFF", "DRV", "DIFF DRV - Built-in"),
    TemplateDefinition("builtin:rcv_diff", "rcv_diff.t2b", "DIFF", "RCV", "DIFF RCV - Built-in"),
    TemplateDefinition("builtin:drv_se", "drv_se.t2b", "SE", "DRV", "SE DRV - Built-in"),
    TemplateDefinition("builtin:rcv_se", "rcv_se.t2b", "SE", "RCV", "SE RCV - Built-in"),
)
CATALOG_BY_ID = {item.template_id: item for item in TEMPLATE_CATALOG}


_TYPE_ALIASES = {
    "drv_diff": "builtin:drv_diff",
    "io_diff_drv": "builtin:drv_diff",
    "diff_drv": "builtin:drv_diff",
    "rcv_diff": "builtin:rcv_diff",
    "io_diff_rcv": "builtin:rcv_diff",
    "diff_rcv": "builtin:rcv_diff",
    "drv_se": "builtin:drv_se",
    "io_se_drv": "builtin:drv_se",
    "se_drv": "builtin:drv_se",
    "rcv_se": "builtin:rcv_se",
    "io_se_rcv": "builtin:rcv_se",
    "se_rcv": "builtin:rcv_se",
}


def template_id_from_type(value: Any) -> str | None:
    raw = str(value or "").strip().casefold()
    if raw.endswith(".t2b"):
        raw = raw[:-4]
    if raw in CATALOG_BY_ID:
        return raw
    return _TYPE_ALIASES.get(raw)


def definition(template_id: str | None) -> TemplateDefinition | None:
    return CATALOG_BY_ID.get(str(template_id or ""))


def _config_defaults(config: dict[str, Any]) -> dict[tuple[str, str], str]:
    defaults: dict[tuple[str, str], str] = {}
    for row in config.get("templates", []):
        if not isinstance(row, dict):
            continue
        module = str(row.get("module", "")).strip().casefold()
        direction = str(row.get("direction", "")).strip().upper()
        template_id = template_id_from_type(row.get("template_type"))
        if module and direction in DIRECTIONS and template_id:
            defaults[(module, direction)] = template_id
    return defaults


def _infer_topology(module_key: str, defaults: dict[tuple[str, str], str]) -> str:
    topologies = {
        item.topology
        for direction in DIRECTIONS
        if (item := definition(defaults.get((module_key, direction)))) is not None
    }
    return next(iter(topologies)) if len(topologies) == 1 else ""


def _auto_template_id(topology: str, direction: str) -> str | None:
    matches = [
        item.template_id
        for item in TEMPLATE_CATALOG
        if item.topology == topology and item.direction == direction
    ]
    return matches[0] if len(matches) == 1 else None


def _resolve_choice(choice: dict[str, Any], topology: str, direction: str) -> str | None:
    mode = str(choice.get("mode", AUTO_MODE)).casefold()
    if mode == MANUAL_MODE:
        selected = str(choice.get("template_id", ""))
        item = definition(selected)
        return selected if item and item.direction == direction else None
    default_id = str(choice.get("config_default_id", ""))
    default = definition(default_id)
    if default and default.direction == direction:
        return default.template_id
    return _auto_template_id(topology, direction)


def normalized_template_selections(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the module-level UI mapping without changing Config Excel defaults.

    ``templates`` remains the read-only Config Section 7 input. This separate
    structure records the project's current auto/manual decision and the
    resulting stable template ID.
    """

    defaults = _config_defaults(config)
    existing = {
        str(row.get("module", "")).strip().casefold(): row
        for row in config.get("template_selections", [])
        if isinstance(row, dict) and str(row.get("module", "")).strip()
    }
    normalized: list[dict[str, Any]] = []
    for module in config.get("modules", []):
        if not isinstance(module, dict):
            continue
        module_name = str(module.get("name", "")).strip()
        module_key = module_name.casefold()
        previous = existing.get(module_key, {})
        previous_topology = str(previous.get("topology", "")).strip().upper()
        topology = previous_topology or _infer_topology(module_key, defaults)
        row: dict[str, Any] = {"module": module_name, "topology": topology}
        for direction in DIRECTIONS:
            key = f"{direction.casefold()}_template"
            old_choice = previous.get(key, {}) if isinstance(previous.get(key), dict) else {}
            mode = str(old_choice.get("mode", AUTO_MODE)).casefold()
            selected = old_choice.get("template_id")
            choice: dict[str, Any] = {
                "mode": mode,
                "template_id": str(selected).strip() if selected else None,
                "config_default_id": defaults.get((module_key, direction)),
            }
            choice["resolved_template_id"] = _resolve_choice(choice, topology, direction)
            row[key] = choice
        normalized.append(row)
    return normalized


def ensure_template_selections(config: dict[str, Any]) -> dict[str, Any]:
    config["template_selections"] = normalized_template_selections(config)
    return config


def selection_for(config: dict[str, Any], module: str) -> dict[str, Any]:
    module_key = module.casefold()
    for row in normalized_template_selections(config):
        if str(row.get("module", "")).casefold() == module_key:
            return row
    raise ProjectValidationError("PROJECT_MODULE_NOT_FOUND", f"项目中不存在模块：{module}")


def set_template_choice(config: dict[str, Any], module: str, direction: str, template_id: str | None) -> None:
    direction = direction.upper()
    if direction not in DIRECTIONS:
        raise ProjectValidationError("PROJECT_TEMPLATE_DIRECTION_INVALID", f"模板方向非法：{direction}")
    ensure_template_selections(config)
    row = next(
        (item for item in config["template_selections"] if str(item.get("module", "")).casefold() == module.casefold()),
        None,
    )
    if row is None:
        raise ProjectValidationError("PROJECT_MODULE_NOT_FOUND", f"项目中不存在模块：{module}")
    key = f"{direction.casefold()}_template"
    choice = row[key]
    if template_id is None:
        choice["mode"] = AUTO_MODE
        choice["template_id"] = None
    else:
        item = definition(template_id)
        if item is None:
            raise ProjectValidationError("PROJECT_TEMPLATE_ID_INVALID", f"未知 T2B Template ID：{template_id}")
        if item.direction != direction:
            raise ProjectValidationError(
                "PROJECT_TEMPLATE_DIRECTION_MISMATCH",
                f"{direction} 不能使用 {item.display_name}",
            )
        choice["mode"] = MANUAL_MODE
        choice["template_id"] = template_id
    choice["resolved_template_id"] = _resolve_choice(choice, str(row.get("topology", "")), direction)


def effective_template_id(config: dict[str, Any], module: str, direction: str) -> str | None:
    direction = direction.upper()
    row = selection_for(config, module)
    choice = row.get(f"{direction.casefold()}_template", {})
    if not isinstance(choice, dict):
        return None
    return _resolve_choice(choice, str(row.get("topology", "")), direction)


def effective_template_mappings(config: dict[str, Any]) -> list[dict[str, str | None]]:
    """Canonical project choices for the future Generate controller."""

    mappings: list[dict[str, str | None]] = []
    for module in config.get("modules", []):
        if not isinstance(module, dict):
            continue
        name = str(module.get("name", ""))
        generate_type = str(module.get("generate_type", "")).upper()
        directions = DIRECTIONS if generate_type == "BOTH" else (generate_type,)
        row = selection_for(config, name)
        for direction in directions:
            choice = row.get(f"{direction.casefold()}_template", {})
            mappings.append(
                {
                    "module": name,
                    "direction": direction,
                    "mode": str(choice.get("mode", AUTO_MODE)),
                    "template_id": effective_template_id(config, name, direction),
                }
            )
    return mappings


def validate_template_selections(config: dict[str, Any]) -> None:
    rows = normalized_template_selections(config)
    by_module = {str(row.get("module", "")).casefold(): row for row in rows}
    for mapping in config.get("templates", []):
        if not isinstance(mapping, dict):
            continue
        direction = str(mapping.get("direction", "")).upper()
        item = definition(template_id_from_type(mapping.get("template_type")))
        if item is not None and direction in DIRECTIONS and item.direction != direction:
            raise ProjectValidationError(
                "PROJECT_TEMPLATE_DIRECTION_MISMATCH",
                f"模块 {mapping.get('module', '')} {direction} 的 Config Excel 默认模板方向不匹配：{item.display_name}",
            )
    for module in config.get("modules", []):
        if not isinstance(module, dict):
            continue
        name = str(module.get("name", "")).strip()
        row = by_module.get(name.casefold(), {})
        topology = str(row.get("topology", ""))
        if topology and topology not in TOPOLOGIES:
            raise ProjectValidationError("PROJECT_TEMPLATE_TOPOLOGY_INVALID", f"模块 {name} 的 Topology 非法：{topology}")
        generate_type = str(module.get("generate_type", "")).upper()
        directions = DIRECTIONS if generate_type == "BOTH" else (generate_type,)
        for direction in directions:
            choice = row.get(f"{direction.casefold()}_template", {})
            if not isinstance(choice, dict):
                raise ProjectValidationError("PROJECT_TEMPLATE_SELECTION_INVALID", f"模块 {name} {direction} 模板选择格式错误")
            mode = str(choice.get("mode", AUTO_MODE)).casefold()
            if mode not in {AUTO_MODE, MANUAL_MODE}:
                raise ProjectValidationError("PROJECT_TEMPLATE_MODE_INVALID", f"模块 {name} {direction} 模板模式非法：{mode}")
            resolved = _resolve_choice(choice, str(row.get("topology", "")), direction)
            if not resolved:
                raise ProjectValidationError(
                    "PROJECT_TEMPLATE_AUTO_UNRESOLVED",
                    f"模块 {name} {direction} 无法自动匹配 T2B Template，请手工选择",
                )


def merge_manual_selections(source: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """Carry explicit GUI choices into a freshly re-imported Config payload."""

    result = copy.deepcopy(source)
    ensure_template_selections(result)
    old_rows = {
        str(row.get("module", "")).casefold(): row
        for row in normalized_template_selections(previous)
    }
    for row in result["template_selections"]:
        old = old_rows.get(str(row.get("module", "")).casefold())
        if not old:
            continue
        for direction in DIRECTIONS:
            key = f"{direction.casefold()}_template"
            old_choice = old.get(key, {})
            if isinstance(old_choice, dict) and old_choice.get("mode") == MANUAL_MODE:
                row[key]["mode"] = MANUAL_MODE
                row[key]["template_id"] = old_choice.get("template_id")
                row[key]["resolved_template_id"] = _resolve_choice(row[key], str(row.get("topology", "")), direction)
    return result
