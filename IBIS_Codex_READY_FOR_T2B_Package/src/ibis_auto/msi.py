from __future__ import annotations

import re
from pathlib import Path

from .errors import IbisError
from .model import Config, Signal
from .ooxml import read_workbook

ALIASES = {
    "signal_name": {"pinname", "name"}, "width": {"width"},
    "direction": {"directiontype", "io", "direction"}, "pad": {"pad"},
    "attribute_type": {"attributertype", "attributetype"},
    "power_domain": {"powerdomain"}, "ground_domain": {"grounddomain"},
    "default": {"defaultvalue", "defaultvaluephyreset", "defaultvaluepoweroff"},
    "description": {"description", "descriptioninternal", "signalsdescription"},
    "databook_description": {"databookdescription", "descriptionexternal"},
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold().lstrip("*"))


def _module_norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _columns(header: list[str], explicit: str = "") -> dict[str, int]:
    result = {}
    for field, aliases in ALIASES.items():
        found = [i for i, value in enumerate(header) if _norm(value) in aliases]
        if field == "signal_name" and explicit:
            found = [i for i, value in enumerate(header) if value.casefold() == explicit.casefold()]
        if len(found) > 1 and field == "signal_name":
            raise IbisError("MSI_PIN_COLUMN_AMBIGUOUS", "MSI 存在多个 PIN_NAME 候选列，必须显式选择", "MODULE")
        if found: result[field] = found[0]
    for required in ("signal_name", "width", "direction"):
        if required not in result:
            raise IbisError("MSI_COLUMN_MISSING", f"MSI 缺少字段：{required}", "MODULE")
    return result


def discover(config: Config, module: str) -> list[Signal]:
    root = config.roots["msi"]
    if not root.is_dir():
        raise IbisError("MSI_ROOT_MISSING", f"MSI Root 不存在：{root}")
    mapping = config.msi_mappings.get(module)
    candidates = []
    files = [root / mapping[0]] if mapping else sorted(root.glob("*.xlsx"))
    for path in files:
        try: sheets = read_workbook(path)
        except Exception as exc: raise IbisError("MSI_READ_ERROR", f"MSI 无法读取：{path}（{exc}）", "MODULE") from exc
        for sheet, rows in sheets.items():
            if not rows: continue
            if mapping and sheet != mapping[1]: continue
            if mapping or _module_norm(module) in {_module_norm(path.stem), _module_norm(sheet)}:
                candidates.append((path, sheet, rows, mapping[2] if mapping else ""))
    if len(candidates) != 1:
        raise IbisError("MSI_SOURCE_AMBIGUOUS", f"模块 {module} 的 MSI Source 数量为 {len(candidates)}，无法唯一确定", "MODULE")
    _, _, rows, explicit = candidates[0]
    cols = _columns(rows[0], explicit)
    signals = []
    for order, row in enumerate(rows[1:]):
        get = lambda key: row[cols[key]].strip() if key in cols and cols[key] < len(row) else ""
        name = get("signal_name")
        if not name: continue
        width_raw = get("width") or "1"
        try: width = int(float(width_raw))
        except ValueError: raise IbisError("MSI_WIDTH_INVALID", f"模块 {module} 信号 {name} 的 WIDTH 非法：{width_raw}", "MODULE")
        match = re.search(r"\[(\d+)\s*:\s*(\d+)\]", name)
        if match and abs(int(match.group(1)) - int(match.group(2))) + 1 != width:
            raise IbisError("MSI_BUS_WIDTH_CONFLICT", f"模块 {module} 信号 {name} 的 WIDTH={width} 与声明范围冲突", "MODULE")
        signals.append(Signal(name, width, get("direction"), get("pad").upper() == "Y", get("attribute_type"), get("power_domain"), get("ground_domain"), get("default"), get("description"), get("databook_description"), order))
    # Attribute override is deliberately limited by the specification.
    by_name = {s.name.casefold(): s for s in signals}
    for override in config.attribute_overrides:
        if override["module"].casefold() != module.casefold(): continue
        if override["attribute"].upper() != "POWER_DOMAIN":
            raise IbisError("MSI_ATTRIBUTE_OVERRIDE_INVALID", f"模块 {module} 不允许覆盖属性 {override['attribute']}", "MODULE")
        signal = by_name.get(override["signal"].casefold())
        if not signal: raise IbisError("MSI_OVERRIDE_SIGNAL_MISSING", f"模块 {module} 的 MSI 不含信号 {override['signal']}", "MODULE")
        signal.power_domain = override["value"]
    return signals

