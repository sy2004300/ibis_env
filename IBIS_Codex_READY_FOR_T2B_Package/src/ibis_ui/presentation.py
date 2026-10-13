from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import build_case_tree
from .source_preview import ModelPreviewReport, MSIPreviewReport, SPFPreviewReport
from .status import ConfigStatus, status_label


def filter_case_tree(tree: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    needle = query.strip().casefold()
    if not needle:
        return tree
    return [item for item in tree if needle in str(item.get("module", "")).casefold()]


def case_tree_counts(tree: list[dict[str, Any]]) -> tuple[int, int]:
    modules = len(tree)
    cases = sum(len(direction.get("rons", [])) for item in tree for direction in item.get("directions", []))
    return modules, cases


@dataclass(frozen=True)
class ProjectOverview:
    io_top_count: int
    branch_count: int
    case_count: int
    msi_matched: int
    msi_total: int
    spf_matched: int
    spf_total: int
    model_files_found: int
    model_files_total: int
    config_status: str
    current_stage: str
    recommended_action: str

    @property
    def inputs_ready(self) -> bool:
        return (
            self.msi_total > 0
            and self.msi_matched == self.msi_total
            and self.spf_total > 0
            and self.spf_matched == self.spf_total
            and self.model_files_total > 0
            and self.model_files_found == self.model_files_total
        )


def build_project_overview(
    config: dict[str, Any],
    config_status: ConfigStatus,
    msi: MSIPreviewReport,
    spf: SPFPreviewReport,
    models: ModelPreviewReport,
) -> ProjectOverview:
    tree = build_case_tree(config)
    modules, cases = case_tree_counts(tree)
    branches = sum(len(item.get("directions", [])) for item in tree)
    msi_matched = sum(item.status == "PASS" for item in msi.modules)
    spf_matched = sum(item.status in {"PASS", "WARNING"} for item in spf.matches)
    model_found = sum(item.status == "FOUND" for item in models.files)
    inputs_ready = (
        bool(msi.modules)
        and msi_matched == len(msi.modules)
        and bool(spf.matches)
        and spf_matched == len(spf.matches)
        and bool(models.files)
        and model_found == len(models.files)
    )
    if config_status == ConfigStatus.ERROR:
        stage = "配置错误"
        action = "根据错误提示修正字段，然后重新点击“保存项目”。"
    elif config_status == ConfigStatus.DIRTY:
        stage = "项目配置编辑"
        action = "检查当前修改，然后点击“保存项目”。"
    elif not inputs_ready:
        stage = "输入来源检查"
        action = "打开“输入文件”，修正 MSI、SPF 或 Model 来源问题。"
    else:
        stage = "模板选择"
        action = "确认 DRV / RCV 使用的 T2B 模板。"
    return ProjectOverview(
        modules,
        branches,
        cases,
        msi_matched,
        len(msi.modules),
        spf_matched,
        len(spf.matches),
        model_found,
        len(models.files),
        status_label(config_status),
        stage,
        action,
    )
