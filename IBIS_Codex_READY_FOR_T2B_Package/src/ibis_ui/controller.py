from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .errors import ProjectStateError, ProjectValidationError
from .excel_importer import ExcelImporter
from .models import ProjectDocument, build_case_tree, empty_config_payload, utc_now, validate_config_payload
from .project_store import ProjectStore


class ProjectController:
    """Headless UI-1 state machine: Draft -> Apply -> Save -> Reload."""

    def __init__(self, store: ProjectStore, importer: ExcelImporter | None = None):
        self.store = store
        self.importer = importer or ExcelImporter()
        self.project: ProjectDocument | None = None
        self.draft: dict[str, Any] | None = None
        self.has_unsaved_applied_changes = False

    def _activate(self, project: ProjectDocument, unsaved: bool) -> ProjectDocument:
        self.project = project
        self.draft = project.clone_config()
        self.has_unsaved_applied_changes = unsaved
        return project

    def import_excel(self, path: Path, project_name: str | None = None) -> ProjectDocument:
        return self._activate(self.importer.import_project(path, project_name), unsaved=True)

    def new_project(self, name: str) -> ProjectDocument:
        return self._activate(ProjectDocument.create(name, "ui", empty_config_payload()), unsaved=True)

    def load_project(self, project_id: str) -> ProjectDocument:
        return self._activate(self.store.load(project_id), unsaved=False)

    def load_recent(self) -> ProjectDocument | None:
        project = self.store.load_recent()
        return self._activate(project, unsaved=False) if project else None

    def _require_active(self) -> tuple[ProjectDocument, dict[str, Any]]:
        if self.project is None or self.draft is None:
            raise ProjectStateError("PROJECT_NOT_OPEN", "当前没有打开的项目")
        return self.project, self.draft

    @property
    def active_config(self) -> dict[str, Any]:
        """Return the working configuration for read-only view rendering."""
        _project, draft = self._require_active()
        return draft

    @property
    def is_dirty(self) -> bool:
        return bool(self.project and self.draft is not None and self.draft != self.project.config)

    @property
    def state_label(self) -> str:
        if self.project is None:
            return "NO PROJECT"
        if self.is_dirty:
            return "DIRTY"
        return "APPLIED / 未保存" if self.has_unsaved_applied_changes else "SAVED"

    def module(self, name: str, draft: bool = True) -> dict[str, Any]:
        project, working = self._require_active()
        config = working if draft else project.config
        for module in config.get("modules", []):
            if module.get("name") == name:
                return module
        raise ProjectValidationError("PROJECT_MODULE_NOT_FOUND", f"项目中不存在模块：{name}")

    def update_module(self, name: str, field: str, value: Any) -> None:
        module = self.module(name, draft=True)
        if field in {"generate_type", "ibis_io_voltage_domain", "ibis_vih_voltage_domain"}:
            module[field] = str(value).strip().upper() if field == "generate_type" else str(value).strip()
            return
        if field == "impedances":
            if isinstance(value, str):
                try:
                    parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
                except ValueError as exc:
                    raise ProjectValidationError("PROJECT_IMPEDANCE_INVALID", f"Ron 必须是逗号分隔的整数：{value!r}") from exc
            else:
                parsed = [int(item) for item in value]
            module[field] = parsed
            return
        parts = field.split(".")
        if len(parts) == 2 and parts[0] in {"tr", "tf"} and parts[1] in {"MAX", "TYP", "MIN"}:
            module[parts[0]][parts[1]] = str(value).strip()
            return
        raise ProjectValidationError("PROJECT_FIELD_UNSUPPORTED", f"UI-1 不支持编辑字段：{field}")

    def update_root(self, name: str, value: str) -> None:
        _project, draft = self._require_active()
        if name not in {"model", "msi", "spf", "template"}:
            raise ProjectValidationError("PROJECT_FIELD_UNSUPPORTED", f"未知 Root：{name}")
        draft["roots"][name] = str(Path(value).expanduser().resolve()) if value.strip() else ""

    def invalid_roots(self, draft: bool = True) -> dict[str, str]:
        project, working = self._require_active()
        config = working if draft else project.config
        if not config.get("modules"):
            return {}
        return {
            name: str(value)
            for name, value in config.get("roots", {}).items()
            if not str(value).strip() or not Path(str(value)).is_dir()
        }

    def apply_changes(self) -> None:
        project, draft = self._require_active()
        validate_config_payload(draft, check_paths=True)
        project.config = copy.deepcopy(draft)
        project.updated_at = utc_now()
        self.draft = project.clone_config()
        self.has_unsaved_applied_changes = True

    def discard_draft(self) -> None:
        project, _draft = self._require_active()
        self.draft = project.clone_config()

    def save_project(self) -> Path:
        project, _draft = self._require_active()
        if self.is_dirty:
            raise ProjectStateError("PROJECT_DIRTY", "存在尚未 Apply 的修改；请先 Apply Changes 或丢弃草稿")
        path = self.store.save(project)
        self.has_unsaved_applied_changes = False
        return path

    def case_tree(self) -> list[dict[str, Any]]:
        _project, draft = self._require_active()
        return build_case_tree(draft)

    def guard_message(self) -> str | None:
        if self.is_dirty:
            return "存在尚未 Apply 的修改，请选择 Apply 并保存、丢弃或取消。"
        if self.has_unsaved_applied_changes:
            return "项目存在尚未保存的已生效配置，请选择保存、丢弃或取消。"
        return None

    def ensure_generate_allowed(self) -> None:
        if self.is_dirty:
            raise ProjectStateError("PROJECT_DIRTY", "存在尚未 Apply 的修改，禁止 Generate")
        raise ProjectStateError("FEATURE_NOT_IMPLEMENTED", "Generate 将在 UI-4 实现，本阶段不会执行生成")
