from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ResourceError
from .runtime import REQUIRED_TEMPLATES, ResourceResolver
from .template_selection import TEMPLATE_CATALOG, definition, effective_template_id, selection_for


TEMPLATE_TYPES = {
    "drv_se.t2b": "DRV / 单端",
    "drv_diff.t2b": "DRV / 差分",
    "rcv_se.t2b": "RCV / 单端",
    "rcv_diff.t2b": "RCV / 差分",
    "_t2b_config.ini": "全局 T2B 配置",
}


@dataclass(frozen=True)
class TemplateInfo:
    filename: str
    template_type: str
    path: Path


class TemplateResourceService:
    """Resolve built-in templates while preserving explicit legacy overrides."""

    def __init__(self, resolver: ResourceResolver | None = None):
        self.resolver = resolver or ResourceResolver.current()

    def effective_root(self, config: dict[str, Any]) -> Path:
        raw = str(config.get("roots", {}).get("template", "")).strip()
        if raw:
            override = Path(raw).expanduser()
            if not override.is_dir():
                raise ResourceError("TEMPLATE_OVERRIDE_INVALID", f"外部 T2B Template Root 不存在：{override}")
            root = override.resolve()
        else:
            root = self.resolver.template_root
        missing = [name for name in REQUIRED_TEMPLATES if not (root / name).is_file()]
        if missing:
            raise ResourceError(
                "TEMPLATE_RESOURCE_INCOMPLETE",
                f"T2B 模板资源不完整：{root}（缺少 {', '.join(missing)}）",
            )
        return root

    def using_override(self, config: dict[str, Any]) -> bool:
        return bool(str(config.get("roots", {}).get("template", "")).strip())

    def list_templates(self, config: dict[str, Any]) -> list[TemplateInfo]:
        root = self.effective_root(config)
        return [TemplateInfo(name, TEMPLATE_TYPES[name], root / name) for name in REQUIRED_TEMPLATES]

    def read(self, config: dict[str, Any], filename: str) -> str:
        if filename not in REQUIRED_TEMPLATES:
            raise ResourceError("TEMPLATE_RESOURCE_UNKNOWN", f"未知内置模板：{filename}")
        path = self.effective_root(config) / filename
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ResourceError("TEMPLATE_RESOURCE_READ_FAILED", f"无法读取 T2B 模板：{path}（{exc}）") from exc

    def path_for_id(self, config: dict[str, Any], template_id: str) -> Path:
        item = definition(template_id)
        if item is None:
            raise ResourceError("TEMPLATE_RESOURCE_UNKNOWN", f"未知 T2B Template ID：{template_id}")
        return self.effective_root(config) / item.filename

    def read_id(self, config: dict[str, Any], template_id: str) -> str:
        item = definition(template_id)
        if item is None:
            raise ResourceError("TEMPLATE_RESOURCE_UNKNOWN", f"未知 T2B Template ID：{template_id}")
        return self.read(config, item.filename)

    def selection_summary(self, config: dict[str, Any], module: str, direction: str) -> dict[str, Any]:
        row = selection_for(config, module)
        direction = direction.upper()
        choice = row[f"{direction.casefold()}_template"]
        template_id = effective_template_id(config, module, direction)
        item = definition(template_id)
        source = "项目手动选择" if choice.get("mode") == "manual" else (
            "Config Excel 默认值" if choice.get("config_default_id") == template_id else "软件自动匹配"
        )
        return {
            "module": module,
            "topology": row.get("topology", ""),
            "direction": direction,
            "mode": choice.get("mode", "auto"),
            "template_id": template_id,
            "display_name": item.display_name if item else "无法自动匹配",
            "filename": item.filename if item else "",
            "source": source if item else "未配置 / Error",
            "path": self.path_for_id(config, template_id) if item else None,
        }

    @staticmethod
    def selectable(direction: str):
        direction = direction.upper()
        return [item for item in TEMPLATE_CATALOG if item.direction == direction]

    @staticmethod
    def mappings_for(config: dict[str, Any], module: str | None = None) -> list[dict[str, str]]:
        rows = [item for item in config.get("templates", []) if isinstance(item, dict)]
        if module is None:
            return rows
        return [item for item in rows if str(item.get("module", "")).casefold() == module.casefold()]
