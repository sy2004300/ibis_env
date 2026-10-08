from __future__ import annotations

import re
from pathlib import Path

from .errors import IbisError
from .model import Config, Corner, ModulePlan
from .ooxml import read_workbook


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


def _resolve(config_path: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    # Config paths describe the project package rather than the config directory.
    for base in [config_path.parent, *config_path.parents]:
        candidate = (base / path).resolve()
        if candidate.exists():
            return candidate
    return (config_path.parent / path).resolve()


def parse_config(path: Path, root_overrides: dict[str, Path] | None = None) -> Config:
    if not path.is_file():
        raise IbisError("CONFIG_READ_ERROR", f"配置文件无法读取：{path}")
    try:
        sheets = read_workbook(path)
    except Exception as exc:
        raise IbisError("CONFIG_READ_ERROR", f"配置文件无法读取：{path}（{exc}）") from exc
    if not sheets:
        raise IbisError("CONFIG_EMPTY", "配置文件没有工作表")
    rows = next(iter(sheets.values()))
    section_rows = {re.sub(r"（.*", "", _cell(row, 0)).strip(): i for i, row in enumerate(rows) if re.match(r"^\d+(?:\.\d+)?\.", _cell(row, 0))}

    def section(prefix: str) -> tuple[int, int]:
        starts = [(name, i) for name, i in section_rows.items() if name.startswith(prefix)]
        if not starts:
            raise IbisError("CONFIG_SECTION_MISSING", f"配置缺少 Section {prefix}")
        start = starts[0][1]
        end = min((i for i in section_rows.values() if i > start), default=len(rows))
        return start, end

    start, end = section("1.")
    raw_roots = {_cell(r, 0): _cell(r, 1) for r in rows[start + 1:end] if _cell(r, 0) and _cell(r, 1)}
    root_names = {"Model Root": "model", "MSI Root": "msi", "SPF Root": "spf", "T2B Template Root": "template"}
    roots = {short: _resolve(path, raw_roots.get(label, "")) for label, short in root_names.items()}
    roots.update(root_overrides or {})

    start, end = section("2.")
    header = rows[start + 1]
    header_indexes = {
        re.sub(r"\s+", " ", _cell(header, i)).casefold(): i
        for i in range(len(header))
        if _cell(header, i)
    }
    required_headers = [
        "Module",
        "Generate Type",
        "IBIS IO Voltage Domain",
        "IBIS VIH Voltage Domain",
        "Tr MAX",
        "Tr TYP",
        "Tr MIN",
        "Tf MAX",
        "Tf TYP",
        "Tf MIN",
    ]
    missing_headers = [name for name in required_headers if name.casefold() not in header_indexes]
    if missing_headers:
        raise IbisError("CONFIG_HEADER_MISSING", f"配置 Section 2 缺少列：{', '.join(missing_headers)}")

    def module_column(name: str) -> int:
        return header_indexes[name.casefold()]

    impedance_columns = []
    for i, name in enumerate(header):
        match = re.fullmatch(r"\s*(\d+)\s*(?:Ω|ohm)\s*", name, re.I)
        if match:
            impedance_columns.append((i, int(match.group(1))))

    modules = []
    for row in rows[start + 2:end]:
        module = _cell(row, module_column("Module"))
        if not module:
            continue
        impedances = [value for i, value in impedance_columns if _cell(row, i).upper() == "Y"]
        modules.append(ModulePlan(
            module,
            _cell(row, module_column("Generate Type")).upper(),
            impedances,
            _cell(row, module_column("IBIS IO Voltage Domain")),
            _cell(row, module_column("IBIS VIH Voltage Domain")),
            {corner: _cell(row, module_column(f"Tr {corner}")) for corner in ("MAX", "TYP", "MIN")},
            {corner: _cell(row, module_column(f"Tf {corner}")) for corner in ("MAX", "TYP", "MIN")},
        ))

    corners = {name: Corner(name, "", "", "") for name in ("MAX", "TYP", "MIN")}
    start, end = section("3.1")
    for row in rows[start + 1:end]:
        if _cell(row, 0) == "Process":
            for i, name in enumerate(corners, 1): corners[name].process = _cell(row, i).upper()
        elif _cell(row, 0) == "Temperature":
            for i, name in enumerate(corners, 1): corners[name].temperature = _cell(row, i)
    start, end = section("3.2")
    voltage_order = []
    for row in rows[start + 2:end]:
        domain = _cell(row, 0)
        if domain:
            voltage_order.append(domain)
            for i, name in enumerate(corners, 1): corners[name].voltages[domain] = _cell(row, i)
    start, end = section("3.3")
    for row in rows[start + 2:end]:
        signal = _cell(row, 0)
        if signal:
            for i, name in enumerate(corners, 1): corners[name].calibration[signal] = _cell(row, i)
    start, end = section("3.4")
    for row in rows[start + 1:end]:
        if _cell(row, 0) == "SPF Match Key":
            for i, name in enumerate(corners, 1): corners[name].spf_key = _cell(row, i)

    start, end = section("4.")
    options = [_cell(r, 0) for r in rows[start + 2:end] if _cell(r, 0)]
    start, end = section("5.")
    aliases = {(_cell(r, 0), _cell(r, 1).upper(), _cell(r, 2)): _cell(r, 6) for r in rows[start + 2:end] if _cell(r, 0)}
    start, end = section("6.")
    appends = [(_cell(r, 0), _cell(r, 1).upper(), _cell(r, 2)) for r in rows[start + 2:end] if _cell(r, 0) and _cell(r, 2)]
    start, end = section("7.")
    templates = {(_cell(r, 0), _cell(r, 1).upper()): _cell(r, 2) for r in rows[start + 2:end] if _cell(r, 0)}

    def dict_rows(prefix: str, fields: list[str]) -> list[dict[str, str]]:
        s, e = section(prefix)
        return [{field: _cell(row, i) for i, field in enumerate(fields)} for row in rows[s + 2:e] if _cell(row, 0)]

    overrides = dict_rows("8.", ["module", "direction", "corner", "signal", "value"])
    attrs = dict_rows("9.", ["module", "signal", "attribute", "value"])
    mappings = {r["module"]: (r["file"], r["sheet"], r["column"]) for r in dict_rows("10.", ["module", "file", "sheet", "column"])}
    return Config(roots, modules, corners, voltage_order, options, aliases, appends, templates, overrides, attrs, mappings)


def validate_overrides(config: Config, module: str | None = None) -> None:
    selected = [item for item in config.overrides if module is None or item["module"].casefold() == module.casefold()]
    for i, left in enumerate(selected):
        for right in selected[i + 1:]:
            if left["module"].casefold() != right["module"].casefold() or left["signal"].casefold() != right["signal"].casefold():
                continue
            directions = lambda x: {"DRV", "RCV"} if x in ("BOTH", "ALL", "") else {x}
            corners = lambda x: {"MAX", "TYP", "MIN"} if x in ("ALL", "") else {x}
            if directions(left["direction"].upper()) & directions(right["direction"].upper()) and corners(left["corner"].upper()) & corners(right["corner"].upper()):
                raise IbisError("OVERRIDE_SCOPE_CONFLICT", f"模块 {left['module']} 信号 {left['signal']} 的 Override 作用域重叠", "MODULE")
