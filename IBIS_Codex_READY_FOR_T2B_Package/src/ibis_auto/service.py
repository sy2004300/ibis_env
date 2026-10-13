from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .config import parse_config, validate_overrides
from .errors import IbisError
from .generator import generate_case, validate_module
from .model import Config, ModulePlan
from .msi import discover
from .spf import match_corners
from .validator import validate_case


@dataclass
class CaseResult:
    key: str
    status: str
    message: str = ""
    path: str = ""


@dataclass
class GenerationResult:
    ready: bool
    cases: list[CaseResult]


CaseKey = tuple[str, str, int]
ProgressCallback = Callable[[str, str, str], None]


def _directions(plan: ModulePlan) -> tuple[str, ...]:
    return ("DRV", "RCV") if plan.generate_type == "BOTH" else (plan.generate_type,)


def expand_case_keys(config: Config) -> list[CaseKey]:
    return [
        (plan.name, direction, impedance)
        for plan in config.modules
        for direction in _directions(plan)
        for impedance in plan.impedances
    ]


def _validate_project(config: Config, require_full_library: bool) -> None:
    for key in ("model", "msi", "spf", "template"):
        if key not in config.roots or not config.roots[key].is_dir():
            raise IbisError("ROOT_MISSING", f"项目 Root 不存在：{config.roots.get(key, '')}")
    required = ["_t2b_config.ini"]
    if require_full_library:
        required += ["drv_se.t2b", "drv_diff.t2b", "rcv_se.t2b", "rcv_diff.t2b"]
    for filename in required:
        if not (config.roots["template"] / filename).is_file():
            raise IbisError("TEMPLATE_LIBRARY_INCOMPLETE", f"模板库文件缺失：{filename}")
    for path in config.template_paths.values():
        if not path.is_file():
            raise IbisError("TEMPLATE_MISSING", f"项目工作模板缺失：{path}")


def _check_process(config: Config, non_interactive: bool) -> None:
    unusual = [
        (name, corner.process)
        for name, corner in config.corners.items()
        if corner.process != {"MAX": "FF", "TYP": "TT", "MIN": "SS"}[name]
    ]
    if not unusual:
        return
    detail = ", ".join(f"{name}={process}" for name, process in unusual)
    print(f"警告：Process/Corner 非常规关系（{detail}）")
    if not non_interactive and input("是否继续？[y/N] ").strip().casefold() not in {"y", "yes"}:
        raise IbisError("PROCESS_ABORTED", "用户终止非常规 Process/Corner 配置")


def _case_key(plan: ModulePlan, direction: str, impedance: int) -> str:
    return f"{plan.name}/{direction}/{impedance}ohm"


def _commit_case(staged: Path, target: Path, overwrite_policy: str) -> Path | None:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, target)
        return None
    if overwrite_policy in {"cancel", "keep"}:
        return target
    if overwrite_policy != "backup":
        raise IbisError("OVERWRITE_POLICY_INVALID", f"输出覆盖策略非法：{overwrite_policy}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup = target.with_name(f"{target.name}.backup_{stamp}")
    os.replace(target, backup)
    try:
        os.replace(staged, target)
    except OSError:
        os.replace(backup, target)
        raise
    return backup


def generate_from_config(
    config: Config,
    output: Path,
    *,
    selected: Iterable[CaseKey] | None = None,
    golden_root: Path | None = None,
    non_interactive: bool = True,
    overwrite_policy: str = "backup",
    cancel_requested: Callable[[], bool] | None = None,
    progress: ProgressCallback | None = None,
    require_full_library: bool = False,
) -> GenerationResult:
    """Generate selected cases from canonical Config using isolated staging dirs."""

    _validate_project(config, require_full_library)
    _check_process(config, non_interactive)
    all_keys = expand_case_keys(config)
    selected_set = set(selected) if selected is not None else set(all_keys)
    unknown = selected_set - set(all_keys)
    if unknown:
        raise IbisError("CASE_SELECTION_INVALID", f"选择了不存在的 Case：{sorted(unknown)!r}")
    if not selected_set:
        raise IbisError("CASE_SELECTION_EMPTY", "至少选择一个 READY_FOR_T2B Case")
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    staging_root = output / ".staging"
    staging_root.mkdir(exist_ok=True)
    results: list[CaseResult] = []

    for plan in config.modules:
        plan_keys = {(plan.name, direction, impedance) for direction in _directions(plan) for impedance in plan.impedances}
        wanted = plan_keys & selected_set
        if not wanted:
            continue
        if plan.generate_type not in {"DRV", "RCV", "BOTH"}:
            error = IbisError("GENERATE_TYPE_INVALID", f"模块 {plan.name} 的 Generate Type 非法：{plan.generate_type!r}", "MODULE")
            for _module, direction, impedance in sorted(wanted):
                results.append(CaseResult(_case_key(plan, direction, impedance), "FAIL", f"[{error.code}] {error}"))
            continue
        try:
            validate_overrides(config, plan.name)
            signals = discover(config, plan.name)
            top, pins = match_corners(config.roots["spf"], plan.name, config.corners)
            validate_module(plan.name, signals, pins, config)
        except IbisError as exc:
            for _module, direction, impedance in sorted(wanted):
                results.append(CaseResult(_case_key(plan, direction, impedance), "FAIL", f"[{exc.code}] {exc}"))
                if progress:
                    progress(_case_key(plan, direction, impedance), "FAIL", str(exc))
            continue

        for direction in _directions(plan):
            for impedance in plan.impedances:
                tuple_key = (plan.name, direction, impedance)
                if tuple_key not in selected_set:
                    continue
                key = _case_key(plan, direction, impedance)
                if cancel_requested and cancel_requested():
                    results.append(CaseResult(key, "已取消", "用户取消尚未执行的任务"))
                    if progress:
                        progress(key, "已取消", "用户取消")
                    continue
                if progress:
                    progress(key, "生成中", "正在生成 staging Case")
                stage = Path(tempfile.mkdtemp(prefix=f"{plan.name}_{direction}_{impedance}_", dir=staging_root))
                target = output / plan.name / direction.lower() / f"{impedance}ohm_ibis"
                try:
                    staged_case = generate_case(config, stage, plan, direction, impedance, top, pins, signals)
                    golden = golden_root / plan.name / direction.lower() / f"{impedance}ohm_ibis" if golden_root else None
                    structural_status, structural_validation = validate_case(staged_case, None, config.roots["model"], config.roots["spf"])
                    if structural_status == "FAIL":
                        raise IbisError("CASE_VALIDATION_FAILED", structural_validation, "CASE")
                    status, validation = validate_case(staged_case, golden, config.roots["model"], config.roots["spf"])
                    existing = _commit_case(staged_case, target, overwrite_policy)
                    if existing == target and overwrite_policy in {"keep", "cancel"}:
                        result = CaseResult(key, "已取消" if overwrite_policy == "cancel" else "保留旧结果", "目标目录已存在，未覆盖", str(target))
                    else:
                        result = CaseResult(key, status, f"{validation}；{target}", str(target))
                    results.append(result)
                    if progress:
                        progress(key, result.status, result.message)
                except (IbisError, OSError) as exc:
                    code = getattr(exc, "code", "CASE_COMMIT_FAILED")
                    message = f"[{code}] {exc}"
                    results.append(CaseResult(key, "FAIL", message, str(target)))
                    if progress:
                        progress(key, "FAIL", message)
                finally:
                    shutil.rmtree(stage, ignore_errors=True)
    try:
        staging_root.rmdir()
    except OSError:
        pass
    complete = bool(results) and all(row.status in {"PASS", "UNVALIDATED"} for row in results)
    return GenerationResult(complete, results)


def generate(
    config_path: Path,
    output: Path,
    root_overrides: dict[str, Path] | None = None,
    non_interactive: bool = False,
) -> GenerationResult:
    config_path = config_path.resolve()
    config = parse_config(config_path, root_overrides)
    return generate_from_config(
        config,
        output,
        golden_root=config_path.parents[2] / "golden",
        non_interactive=non_interactive,
        overwrite_policy="backup",
        require_full_library=True,
    )
