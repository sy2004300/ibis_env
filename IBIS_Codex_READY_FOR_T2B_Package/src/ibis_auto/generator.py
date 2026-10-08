from __future__ import annotations

import re
import shutil
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import IbisError
from .model import Config, ModulePlan, Signal
from .values import impedance_map, parse_logic, signal_bits

SECTIONS = {"FF": ("rbd_f", "cap_f", "mos_var_ff"), "TT": ("rbd_t", "cap_t", "mos_var_tt"), "SS": ("rbd_s", "cap_s", "mos_var_ss")}


def _fmt_number(value: str) -> str:
    try: return f"{float(value):g}"
    except ValueError: return value


def _fmt_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _alias(config: Config, module: str, direction: str, pin: str) -> str:
    return config.aliases.get((module, direction, pin), config.aliases.get((module, "BOTH", pin), pin))


def _instance(signal: str) -> str:
    return "v" + re.sub(r"[^A-Za-z0-9_]", "", signal).lower()


def _line(signal: str, bit: str, domain: str, corner: str, commented: bool = False) -> str:
    voltage = "0" if bit == "0" else f"{domain.lower()}_{corner.lower()}"
    return ("*" if commented else "") + f"{_instance(signal)} {signal} 0 dc {voltage}"


def _effective_override(config: Config, module: str, direction: str, corner: str, signal: str) -> str | None:
    for item in config.overrides:
        if item["module"].casefold() != module.casefold() or item["signal"].casefold() != signal.casefold(): continue
        if item["direction"].upper() not in (direction, "BOTH", "ALL", ""): continue
        if item["corner"].upper() not in (corner, "ALL", ""): continue
        return item["value"]
    return None


def validate_module(module: str, signals: list[Signal], pins: list[str], config: Config) -> None:
    expanded = {bit.casefold() for signal in signals for bit in signal_bits(signal.name, signal.width)}
    pinset = {pin.casefold() for pin in pins}
    for signal in config.corners["MAX"].calibration:
        required = {bit.casefold() for bit in signal_bits(signal, abs(int(re.search(r"\[(\d+):(\d+)\]", signal).group(1)) - int(re.search(r"\[(\d+):(\d+)\]", signal).group(2))) + 1)}
        if not required <= expanded or not required <= pinset:
            raise IbisError("CALIBRATION_SIGNAL_MISSING", f"模块 {module} 的 Calibration Signal {signal} 未同时存在于 MSI 和 SPF", "MODULE")
    missing = [pin for pin in pins if pin.casefold() not in expanded and pin not in config.voltage_order]
    if missing: raise IbisError("SPF_PIN_MISSING_IN_MSI", f"模块 {module} 的 SPF Pin 在 MSI 中无法解释：{', '.join(missing)}", "MODULE")


def _component(config: Config) -> str:
    blocks = []
    for domain in config.voltage_order:
        blocks.append("\n".join(f".PARAM {domain.lower()}_{name.lower()}={_fmt_number(config.corners[name].voltages[domain])}" for name in ("MAX", "TYP", "MIN")))
    return "\n\n".join(blocks) + "\n"


def _topology(config: Config, module: str, direction: str, top: str, pins: list[str]) -> str:
    mapped = [_alias(config, module, direction, pin) for pin in pins]
    chunks = [mapped[:9]] + [mapped[i:i + 9] for i in range(9, len(mapped), 9)]
    lines = ["*** netlist_subckt ***", "x1 " + " ".join(chunks[0])]
    lines += ["+ " + " ".join(chunk) for chunk in chunks[1:]]
    lines[-1] += " " + top
    for mod, scope, body in config.appends:
        if mod == module and scope in (direction, "BOTH"): lines.append(body)
    return "\n".join(lines) + "\n"


def _domain_values(config: Config, requested: str, label: str, module: str) -> dict[str, Decimal]:
    if not requested:
        raise IbisError("T2B_FIELD_MISSING", f"模块 {module} 缺少 {label}", "CASE")
    domain = next((name for name in config.voltage_order if name.casefold() == requested.casefold()), None)
    if domain is None:
        raise IbisError("IBIS_VOLTAGE_DOMAIN_INVALID", f"模块 {module} 的 {label} {requested!r} 未在 Voltage Domain 中定义", "CASE")
    values = {}
    for corner_name in ("MAX", "TYP", "MIN"):
        raw = config.corners[corner_name].voltages.get(domain, "")
        if not raw:
            raise IbisError("T2B_FIELD_MISSING", f"模块 {module} 的 {label} 在 {corner_name} 缺少电压值", "CASE")
        try:
            values[corner_name] = Decimal(raw)
        except InvalidOperation as exc:
            raise IbisError("T2B_VALUE_INVALID", f"模块 {module} 的 {label} 在 {corner_name} 电压值非法：{raw!r}", "CASE") from exc
    return values


def _module_corner_values(plan: ModulePlan, attribute: str, label: str) -> dict[str, str]:
    source = getattr(plan, attribute, None)
    if not isinstance(source, dict):
        raise IbisError("T2B_FIELD_MISSING", f"模块 {plan.name} 缺少 {label} Corner 配置", "CASE")
    values = {}
    for corner_name in ("MAX", "TYP", "MIN"):
        value = str(source.get(corner_name, "")).strip()
        if not value:
            raise IbisError("T2B_FIELD_MISSING", f"模块 {plan.name} 缺少 {label} {corner_name}", "CASE")
        values[corner_name] = value
    return values


def _validate_alias_sources(config: Config, module: str, direction: str, pins: list[str]) -> None:
    pinset = {pin.casefold() for pin in pins}
    missing = []
    for (mapped_module, scope, original), _alias_name in config.aliases.items():
        if mapped_module.casefold() != module.casefold() or scope.upper() not in {direction, "BOTH"}:
            continue
        if original.casefold() not in pinset:
            missing.append(original)
    if missing:
        names = ", ".join(dict.fromkeys(missing))
        raise IbisError("IBIS_PIN_SOURCE_MISSING", f"模块 {module} 的 Config Original Pin 不存在于 SPF Top .SUBCKT：{names}", "CASE")


def _template(config: Config, plan: ModulePlan, direction: str, impedance: int, template_type: str, top: str) -> tuple[str, str]:
    path = config.roots["template"] / f"{template_type}.t2b"
    if not path.is_file(): raise IbisError("TEMPLATE_MISSING", f"T2B 模板缺失：{path}")
    text = path.read_text()

    io_values = _domain_values(config, plan.ibis_io_voltage_domain, "IBIS IO Voltage Domain", plan.name)
    vih_values = _domain_values(config, plan.ibis_vih_voltage_domain, "IBIS VIH Voltage Domain", plan.name)
    tr_values = _module_corner_values(plan, "tr", "Tr")
    tf_values = _module_corner_values(plan, "tf", "Tf")
    spice_type = str(config.spice_type).strip()
    spice_command = str(config.spice_command).strip()
    if not spice_type:
        raise IbisError("T2B_FIELD_MISSING", "项目缺少 SPICE_TYPE", "CASE")
    if not spice_command:
        raise IbisError("T2B_FIELD_MISSING", "项目缺少 SPICE_COMMAND", "CASE")

    values = {
        "TOP_SUBCKT": top,
        "RON": str(impedance),
        "DATE_YYYY/MM": date.today().strftime("%Y/%m"),
        "SPICE_TYPE": spice_type,
        "SPICE_COMMAND": spice_command,
        "TEMP_TYP": config.corners["TYP"].temperature, "TEMP_MIN": config.corners["MIN"].temperature, "TEMP_MAX": config.corners["MAX"].temperature,
    }
    for corner_name in ("TYP", "MIN", "MAX"):
        vmeas = io_values[corner_name] / Decimal(4)
        values.update({
            f"VOLT_{corner_name}": _fmt_decimal(io_values[corner_name]),
            f"VIH_{corner_name}": _fmt_decimal(vih_values[corner_name]),
            f"TR_{corner_name}": tr_values[corner_name],
            f"TF_{corner_name}": tf_values[corner_name],
            f"VMEAS_{corner_name}": _fmt_decimal(vmeas),
            f"VINH_{corner_name}": _fmt_decimal(vmeas + Decimal("0.05")),
            f"VINL_{corner_name}": _fmt_decimal(vmeas - Decimal("0.05")),
        })
    for key, value in values.items(): text = text.replace("{{" + key + "}}", value)
    if re.search(r"{{[^}]+}}", text): raise IbisError("TEMPLATE_PLACEHOLDER_UNKNOWN", f"模板存在未解析占位符：{path}", "CASE")
    spice = re.search(r"^\[Spice type\]\s+(\S+)", text, re.M | re.I)
    if not spice or spice.group(1).casefold() not in {"spectre", "hspice"}:
        raise IbisError("SPICE_TYPE_INVALID", f"模板 Spice type 缺失或不支持：{path}", "CASE")
    return text, spice.group(1).casefold()


def _corner(config: Config, module: str, direction: str, impedance: int, corner_name: str, signals: list[Signal], aliases: set[str], spice: str) -> str:
    corner = config.corners[corner_name]
    if corner.process not in SECTIONS: raise IbisError("PROCESS_UNSUPPORTED", f"Corner {corner_name} 的 Process {corner.process} 无模型映射", "CASE")
    model_root = config.roots["model"] / spice
    for filename in ("rbd.lib", "cap.lib", "mos_var.lib"):
        if not (model_root / filename).is_file(): raise IbisError("MODEL_FILE_MISSING", f"模型文件缺失：{model_root / filename}", "CASE")
    sections = SECTIONS[corner.process]
    lines = ["****************", ".protect",
             f".lib '{model_root / 'rbd.lib'}' {sections[0]}", f".lib '{model_root / 'cap.lib'}' {sections[1]}", f".lib '{model_root / 'mos_var.lib'}' {sections[2]}",
             f".inc '{corner.spf}'", ".unprotect", "", *config.simulation_options, "", "*** T2B-controlled pins (local sources disabled) ***"]
    controlled = [("VDDQ", "1"), ("VSS", "0"), ("TXOE", "0"), ("TXDAT", "0")] if direction == "DRV" else []
    by_base = {s.name.casefold(): s for s in signals}
    for pin, bit in controlled:
        signal = by_base.get(pin.casefold()); domain = signal.power_domain if signal else pin
        lines.append(_line(_alias(config, module, direction, pin), bit, domain, corner_name, True))
    lines += ["", "*** active local power ***"]
    controlled_names = {x[0].casefold() for x in controlled}
    for domain in config.voltage_order:
        if domain.casefold() in by_base and domain.casefold() not in controlled_names:
            lines.append(_line(_alias(config, module, direction, domain), "1" if float(corner.voltages[domain]) else "0", domain, corner_name))

    strength = [s for s in signals if s.name.casefold() in {"reg_txslice_pd[3:0]", "reg_txslice_pu[3:0]"}]
    if len(strength) != 2: raise IbisError("TARGET_SIGNALS_MISSING", f"模块 {module} 缺少 PU/PD Target Impedance 信号", "CASE")
    codes = []
    for signal in strength:
        left, right = impedance_map(signal.description), impedance_map(signal.databook_description)
        if left and right and left != right: raise IbisError("MSI_IMPEDANCE_MAP_CONFLICT", f"模块 {module} 信号 {signal.name} 的两个 impedance map 不一致", "CASE")
        mapping = left or right
        if impedance not in mapping: raise IbisError("TARGET_RON_MISSING", f"模块 {module} 信号 {signal.name} 缺少 {impedance}Ω 映射", "CASE")
        codes.append((signal, mapping[impedance]))
    lines += ["", f"*** target impedance: {impedance}ohm; minimum valid code = 4'b{codes[0][1]} ***"]
    for index, (signal, code) in enumerate(codes):
        override = _effective_override(config, module, direction, corner_name, signal.name)
        raw_code = override if override is not None else f"{signal.width}'b{code}"
        bits = parse_logic(raw_code, module, signal.name, signal.width)
        for pin, bit in zip(signal_bits(signal.name, signal.width), bits):
            if bit == "1" and signal.power_domain not in config.voltage_order: raise IbisError("POWER_DOMAIN_MISSING", f"模块 {module} 信号 {signal.name} 为高电平但 Power Domain {signal.power_domain!r} 未定义", "CASE")
            lines.append(_line(pin, bit, signal.power_domain, corner_name))
        if index != len(codes) - 1: lines.append("")

    calibration_names = {name.casefold() for name in corner.calibration}
    previous_calibration = None
    for cal_name, raw in corner.calibration.items():
        signal = next(s for s in signals if s.name.casefold() == cal_name.casefold())
        raw = _effective_override(config, module, direction, corner_name, signal.name) or raw
        bits = parse_logic(raw, module, signal.name, signal.width)
        lines.append("")
        if raw != previous_calibration:
            lines.append(f"*** calibration = {raw} ***")
        for pin, bit in zip(signal_bits(signal.name, signal.width), bits): lines.append(_line(pin, bit, signal.power_domain, corner_name))
        previous_calibration = raw

    ordinary = [s for s in signals if s.direction.casefold() in {"i", "input"} and s.name.casefold() not in controlled_names and s.name.casefold() not in calibration_names and s not in strength and s.attribute_type.casefold() not in {"power", "ground"}]
    for signal in ordinary:
        raw = _effective_override(config, module, direction, corner_name, signal.name)
        raw = signal.default if raw is None else raw
        bits = parse_logic(raw, module, signal.name, signal.width)
        if all(bit == "0" for bit in bits) and signal.power_domain not in config.voltage_order:
            print(f"警告：模块 {module} 信号 {signal.name} 全为 0，但 Power Domain {signal.power_domain!r} 未定义，继续处理")
        if any(bit == "1" for bit in bits) and signal.power_domain not in config.voltage_order:
            raise IbisError("POWER_DOMAIN_MISSING", f"模块 {module} 信号 {signal.name} 为高电平但 Power Domain {signal.power_domain!r} 未定义", "CASE")
        lines += ["", f"*** MSI default {signal.name} = {raw} ***"]
        for pin, bit in zip(signal_bits(signal.name, signal.width), bits): lines.append(_line(pin, bit, signal.power_domain, corner_name))
    return "\n".join(lines) + "\n"


def generate_case(config: Config, output: Path, plan: ModulePlan, direction: str, impedance: int, top: str, pins: list[str], signals: list[Signal]) -> Path:
    module = plan.name
    template_type = config.templates.get((module, direction))
    if not template_type: raise IbisError("TEMPLATE_MAPPING_MISSING", f"模块 {module} {direction} 缺少 T2B Template Mapping", "CASE")
    _validate_alias_sources(config, module, direction, pins)
    rendered, spice = _template(config, plan, direction, impedance, template_type, top)
    case = output / module / direction.lower() / f"{impedance}ohm_ibis"
    case.mkdir(parents=True, exist_ok=True)
    global_config = config.roots["template"] / "_t2b_config.ini"
    if not global_config.is_file(): raise IbisError("TEMPLATE_CONFIG_MISSING", f"全局模板配置缺失：{global_config}")
    shutil.copyfile(global_config, case / "_t2b_config.ini")
    (case / "component.sp").write_text(_component(config))
    (case / "ckt_topology.sp").write_text(_topology(config, module, direction, top, pins))
    (case / f"{module}_{direction.lower()}_ron{impedance}.t2b").write_text(rendered)
    for name in ("MAX", "TYP", "MIN"):
        text = _corner(config, module, direction, impedance, name, signals, set(), spice)
        (case / f"corner_{direction.lower()}_ron{impedance}_{name.lower()}.sp").write_text(text)
    return case
