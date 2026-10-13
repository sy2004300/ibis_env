from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ibis_auto.config import validate_overrides
from ibis_auto.model import Config, Corner, ModulePlan

from .errors import ProjectValidationError
from .models import CORNER_NAMES, validate_config_payload
from .template_selection import effective_template_id


def payload_to_core_config(
    payload: dict[str, Any],
    *,
    template_root: Path | None = None,
    template_paths: dict[tuple[str, str], Path] | None = None,
) -> Config:
    """Convert the ProjectStore fact source into the canonical Core Config."""

    candidate = copy.deepcopy(payload)
    validate_config_payload(candidate, check_paths=False)
    roots = {key: Path(str(value)).expanduser().resolve() for key, value in candidate["roots"].items()}
    if template_root is not None:
        roots["template"] = template_root.expanduser().resolve()
    modules = [
        ModulePlan(
            str(row["name"]),
            str(row["generate_type"]).upper(),
            [int(value) for value in row["impedances"]],
            str(row["ibis_io_voltage_domain"]),
            str(row["ibis_vih_voltage_domain"]),
            {name: str(row["tr"][name]) for name in CORNER_NAMES},
            {name: str(row["tf"][name]) for name in CORNER_NAMES},
        )
        for row in candidate["modules"]
    ]
    corners = {
        name: Corner(
            name,
            str(candidate["corners"][name]["process"]).upper(),
            str(candidate["corners"][name]["temperature"]),
            str(candidate["corners"][name]["spf_key"]),
            {str(key): str(value) for key, value in candidate["corners"][name]["voltages"].items()},
            {str(key): str(value) for key, value in candidate["corners"][name]["calibration"].items()},
        )
        for name in CORNER_NAMES
    }
    templates: dict[tuple[str, str], str] = {}
    for module in modules:
        directions = ("DRV", "RCV") if module.generate_type == "BOTH" else (module.generate_type,)
        for direction in directions:
            template_id = effective_template_id(candidate, module.name, direction)
            if not template_id:
                raise ProjectValidationError(
                    "PROJECT_TEMPLATE_MAPPING_MISSING",
                    f"模块 {module.name} {direction} 缺少有效 T2B 模板映射",
                )
            templates[(module.name, direction)] = template_id.split(":", 1)[-1]

    config = Config(
        roots,
        modules,
        corners,
        [str(value) for value in candidate["voltage_order"]],
        [str(value) for value in candidate["simulation_options"]],
        {
            (str(row["module"]), str(row["direction"]).upper(), str(row["original_pin"])): str(row["alias"])
            for row in candidate["aliases"]
        },
        [
            (str(row["module"]), str(row["direction"]).upper(), str(row["body"]))
            for row in candidate["appends"]
        ],
        templates,
        copy.deepcopy(candidate["overrides"]),
        copy.deepcopy(candidate["attribute_overrides"]),
        {
            str(row["module"]): (str(row["file"]), str(row["sheet"]), str(row["column"]))
            for row in candidate["msi_mappings"]
        },
        str(candidate.get("spice_type", "spectre")),
        str(candidate.get("spice_command", "spectre +preset=mx +spice +mt=4")),
        template_paths or {},
    )
    try:
        validate_overrides(config)
    except Exception as exc:
        code = getattr(exc, "code", "PROJECT_OVERRIDE_INVALID")
        raise ProjectValidationError(code, str(exc)) from exc
    return config


def core_semantics(config: Config) -> dict[str, Any]:
    """Path-neutral, order-preserving representation for Excel round-trip tests."""

    return {
        "modules": [
            {
                "name": row.name,
                "generate_type": row.generate_type,
                "impedances": row.impedances,
                "ibis_io_voltage_domain": row.ibis_io_voltage_domain,
                "ibis_vih_voltage_domain": row.ibis_vih_voltage_domain,
                "tr": row.tr,
                "tf": row.tf,
            }
            for row in config.modules
        ],
        "corners": {
            name: {
                "process": row.process,
                "temperature": row.temperature,
                "spf_key": row.spf_key,
                "voltages": row.voltages,
                "calibration": row.calibration,
            }
            for name, row in config.corners.items()
        },
        "voltage_order": config.voltage_order,
        "simulation_options": config.simulation_options,
        "aliases": [(*key, value) for key, value in config.aliases.items()],
        "appends": config.appends,
        "templates": [(*key, value) for key, value in config.templates.items()],
        "overrides": config.overrides,
        "attribute_overrides": config.attribute_overrides,
        "msi_mappings": [(module, *value) for module, value in config.msi_mappings.items()],
    }
