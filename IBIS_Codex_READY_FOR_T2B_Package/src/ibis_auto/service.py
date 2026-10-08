from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import parse_config, validate_overrides
from .errors import IbisError
from .generator import generate_case, validate_module
from .msi import discover
from .spf import match_corners
from .validator import validate_case


@dataclass
class CaseResult:
    key: str
    status: str
    message: str = ""


@dataclass
class GenerationResult:
    ready: bool
    cases: list[CaseResult]


def generate(config_path: Path, output: Path, root_overrides: dict[str, Path] | None = None, non_interactive: bool = False) -> GenerationResult:
    config = parse_config(config_path.resolve(), root_overrides)
    for key in ("model", "msi", "spf", "template"):
        if not config.roots[key].is_dir(): raise IbisError("ROOT_MISSING", f"项目 Root 不存在：{config.roots[key]}")
    for filename in ("drv_se.t2b", "drv_diff.t2b", "rcv_se.t2b", "rcv_diff.t2b", "_t2b_config.ini"):
        if not (config.roots["template"] / filename).is_file():
            raise IbisError("TEMPLATE_LIBRARY_INCOMPLETE", f"模板库文件缺失：{filename}")
    unusual = [(name, corner.process) for name, corner in config.corners.items() if corner.process != {"MAX": "FF", "TYP": "TT", "MIN": "SS"}[name]]
    if unusual:
        detail = ", ".join(f"{name}={process}" for name, process in unusual)
        print(f"警告：Process/Corner 非常规关系（{detail}）")
        if not non_interactive and input("是否继续？[y/N] ").strip().casefold() not in {"y", "yes"}:
            raise IbisError("PROCESS_ABORTED", "用户终止非常规 Process/Corner 配置")
    results = []
    output.mkdir(parents=True, exist_ok=True)
    for plan in config.modules:
        if plan.generate_type not in {"DRV", "RCV", "BOTH"}:
            error = IbisError("GENERATE_TYPE_INVALID", f"模块 {plan.name} 的 Generate Type 非法：{plan.generate_type!r}", "MODULE")
            for impedance in plan.impedances or [0]:
                results.append(CaseResult(f"{plan.name}/{plan.generate_type or 'UNKNOWN'}/{impedance}ohm", "FAIL", f"[{error.code}] {error}"))
            print(f"错误 [{error.code}]：{error}")
            continue
        try:
            validate_overrides(config, plan.name)
            signals = discover(config, plan.name)
            top, pins = match_corners(config.roots["spf"], plan.name, config.corners)
            validate_module(plan.name, signals, pins, config)
        except IbisError as exc:
            directions = ["DRV", "RCV"] if plan.generate_type == "BOTH" else [plan.generate_type]
            for direction in directions:
                for impedance in plan.impedances: results.append(CaseResult(f"{plan.name}/{direction}/{impedance}ohm", "FAIL", f"[{exc.code}] {exc}"))
            print(f"错误 [{exc.code}]：{exc}")
            continue
        directions = ["DRV", "RCV"] if plan.generate_type == "BOTH" else [plan.generate_type]
        for direction in directions:
            for impedance in plan.impedances:
                key = f"{plan.name}/{direction}/{impedance}ohm"
                try:
                    case = generate_case(config, output, plan, direction, impedance, top, pins, signals)
                    golden = config_path.resolve().parents[2] / "golden" / plan.name / direction.lower() / f"{impedance}ohm_ibis"
                    status, validation = validate_case(case, golden, config.roots["model"], config.roots["spf"])
                    results.append(CaseResult(key, status, f"{validation}；{case}"))
                except IbisError as exc:
                    shutil.rmtree(output / plan.name / direction.lower() / f"{impedance}ohm_ibis", ignore_errors=True)
                    results.append(CaseResult(key, "FAIL", f"[{exc.code}] {exc}"))
                    print(f"错误 [{exc.code}]：{exc}")
    return GenerationResult(bool(results) and all(r.status != "FAIL" for r in results), results)
