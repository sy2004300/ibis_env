"""Read-only filled T2B preview. Never writes a case or creates a working copy."""
from __future__ import annotations

from ibis_auto.generator import render_t2b
from ibis_auto.spf import match_corners
from ibis_auto.errors import IbisError

from .config_adapter import payload_to_core_config
from .errors import ProjectValidationError
from .working_templates import validate_template_text
from .template_selection import definition, effective_template_id


def render_preview(config_payload, template_root, template_service, key, text=None):
    module, direction, ron = key
    try:
        config = payload_to_core_config(config_payload, template_root=template_root)
        plan = next((item for item in config.modules if item.name == module), None)
        if plan is None or ron not in plan.impedances or direction not in (
            ("DRV", "RCV") if plan.generate_type == "BOTH" else (plan.generate_type,)
        ):
            raise ProjectValidationError("PREVIEW_CASE_INVALID", f"请选择有效的模块、方向和 Ron：{key}")
        path = template_service.resolve_path(config_payload, module, direction, validate=text is None)
        source = text if text is not None else path.read_text(encoding="utf-8")
        if text is not None:
            record = template_service.records.get(template_service.key(module, direction))
            item = definition(effective_template_id(config_payload, module, direction))
            topology = record["topology"] if record else item.topology
            validation = validate_template_text(text, direction, topology)
            if not validation.valid:
                raise ProjectValidationError("TEMPLATE_EDIT_INVALID", "；".join(validation.errors))
        top, _pins = match_corners(config.roots["spf"], module, config.corners)
        rendered, _spice = render_t2b(config, plan, direction, ron, top, source)
        return rendered
    except (IbisError, OSError, ValueError) as exc:
        raise ProjectValidationError(getattr(exc, "code", "T2B_PREVIEW_INVALID"), f"无法预览 {module}/{direction}/{ron}Ω：{exc}") from exc
