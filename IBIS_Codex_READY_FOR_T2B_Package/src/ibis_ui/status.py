from __future__ import annotations

from enum import Enum


class ConfigStatus(str, Enum):
    UNMODIFIED = "UNMODIFIED"
    DIRTY = "DIRTY"
    SAVED = "SAVED"
    ERROR = "ERROR"


class SourceStatus(str, Enum):
    UNSCANNED = "UNSCANNED"
    FOUND = "FOUND"
    MATCHED = "MATCHED"
    MATCH_FAILED = "MATCH_FAILED"


class GenerationStatus(str, Enum):
    NOT_GENERATED = "NOT_GENERATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASS = "PASS"
    UNVALIDATED = "UNVALIDATED"
    FAIL = "FAIL"
    STALE = "STALE"
    CANCELLED = "CANCELLED"


STATUS_LABELS = {
    ConfigStatus.UNMODIFIED.value: "未修改",
    ConfigStatus.DIRTY.value: "有未保存修改",
    ConfigStatus.SAVED.value: "已保存",
    ConfigStatus.ERROR.value: "配置错误",
    SourceStatus.UNSCANNED.value: "未扫描",
    SourceStatus.FOUND.value: "已发现",
    SourceStatus.MATCHED.value: "已匹配",
    SourceStatus.MATCH_FAILED.value: "匹配失败",
    GenerationStatus.NOT_GENERATED.value: "未生成",
    GenerationStatus.QUEUED.value: "等待中",
    GenerationStatus.RUNNING.value: "生成中",
    GenerationStatus.PASS.value: "通过",
    GenerationStatus.UNVALIDATED.value: "未验证",
    GenerationStatus.FAIL.value: "失败",
    GenerationStatus.STALE.value: "已过期",
    GenerationStatus.CANCELLED.value: "已取消",
    "PASS": "通过",
    "WARNING": "警告",
    "ERROR": "错误",
    "CONFIGURED": "已配置",
    "NO_PROJECT": "未打开项目",
}


def status_label(value: str | Enum) -> str:
    key = value.value if isinstance(value, Enum) else str(value)
    return STATUS_LABELS.get(key, key)
