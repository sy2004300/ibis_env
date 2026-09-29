from __future__ import annotations

import re

from .errors import IbisError


def parse_logic(raw: str, module: str, signal: str, width: int) -> str:
    value = (raw or "").strip()
    if not value or value.upper() in {"X", "Z", "-"}:
        raise IbisError("INVALID_LOGIC_VALUE", f"模块 {module} 信号 {signal} 的 Value 非法：{raw!r}", "CASE")
    match = re.fullmatch(r"(\d+)'([bBhH])([0-9a-fA-F_]+)", value)
    if match:
        declared, base, digits = int(match.group(1)), match.group(2).lower(), match.group(3).replace("_", "")
        number = int(digits, 2 if base == "b" else 16)
        bits = f"{number:0{declared}b}"
    elif re.fullmatch(r"0[xX][0-9a-fA-F]+", value): bits = f"{int(value, 16):0{width}b}"
    elif re.fullmatch(r"[01]", value): bits = value
    elif value.isdigit(): bits = f"{int(value):0{width}b}"
    else: raise IbisError("INVALID_LOGIC_VALUE", f"模块 {module} 信号 {signal} 的 Value 非法：{raw!r}", "CASE")
    if len(bits) > width or int(bits, 2) >= 2 ** width:
        raise IbisError("LOGIC_WIDTH_OVERFLOW", f"模块 {module} 信号 {signal} 的 Value 超出 {width} bit：{raw!r}", "CASE")
    return bits.zfill(width)


def impedance_map(text: str) -> dict[int, str]:
    result: dict[int, list[str]] = {}
    for code, ohms in re.findall(r"\b([01]+)\s*:\s*(\d+)\s*ohm\b", text, re.I):
        result.setdefault(int(ohms), []).append(code)
    return {ohms: min(codes, key=lambda code: int(code, 2)) for ohms, codes in result.items()}


def signal_bits(name: str, width: int) -> list[str]:
    match = re.search(r"^(.*?)\[(\d+)\s*:\s*(\d+)\]$", name)
    if not match: return [name]
    base, first, last = match.group(1), int(match.group(2)), int(match.group(3))
    step = -1 if first > last else 1
    bits = [f"{base}[{i}]" for i in range(first, last + step, step)]
    return bits

