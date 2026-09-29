from __future__ import annotations

import re
from pathlib import Path

from .errors import IbisError


def parse(path: Path) -> tuple[str, list[str]]:
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"\s*\.subckt\s+(\S+)\s*(.*)", line, re.I)
        if not match: continue
        payload = match.group(2)
        j = i + 1
        while j < len(lines) and re.match(r"\s*\+", lines[j]):
            payload += " " + re.sub(r"^\s*\+\s*", "", lines[j]); j += 1
        return match.group(1), payload.split()
    raise IbisError("SPF_SUBCKT_MISSING", f"SPF 缺少 Top .SUBCKT：{path}", "MODULE")


def match_corners(root: Path, module: str, corners) -> tuple[str, list[str]]:
    if not root.is_dir(): raise IbisError("SPF_ROOT_MISSING", f"SPF Root 不存在：{root}")
    top = None; pins = None
    for corner in corners.values():
        matches = [p for p in root.rglob("*.spf") if module.casefold() in p.name.casefold() and corner.spf_key.casefold() in p.name.casefold()]
        if not matches:
            raise IbisError("SPF_NOT_FOUND", f"模块 {module} Corner {corner.name} 未找到 SPF", "MODULE")
        if len(matches) > 1:
            raise IbisError("SPF_AMBIGUOUS", f"模块 {module} Corner {corner.name} 匹配到 {len(matches)} 个 SPF（要求唯一）", "MODULE")
        corner.spf = matches[0].resolve()
        current_top, current_pins = parse(matches[0])
        if module.casefold() != current_top.casefold():
            print(f"警告：模块 {module} 的 SPF 文件名与 Top .SUBCKT {current_top} 不一致，继续处理")
        if pins is not None and current_pins != pins:
            raise IbisError("SPF_INTERFACE_MISMATCH", f"模块 {module} 各 Corner 的 SPF Top Pin List 不一致", "MODULE")
        top, pins = current_top, current_pins
    return top, pins
