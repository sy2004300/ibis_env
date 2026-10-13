from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .errors import ProjectStateError, ProjectValidationError, ResourceError
from .excel_importer import ExcelImporter
from .models import EXTERNAL_ROOT_NAMES, ProjectDocument, build_case_tree, empty_config_payload, utc_now, validate_config_payload
from .project_store import ProjectStore
from .runtime import ResourceResolver
from .status import ConfigStatus
from .template_service import TemplateResourceService
from .template_selection import merge_manual_selections, selection_for, set_template_choice


class ProjectController:
    """Headless UI-1 state machine: Draft -> Apply -> Save -> Reload."""

    def __init__(
        self,
        store: ProjectStore,
        importer: ExcelImporter | None = None,
        resources: ResourceResolver | None = None,
    ):
        self.store = store
        self.importer = importer or ExcelImporter()
        self.resources = resources or ResourceResolver.current()
        self.templates = TemplateResourceService(self.resources)
        self.project: ProjectDocument | None = None
        self.draft: dict[str, Any] | None = None
        self.has_unsaved_applied_changes = False
        self.validation_error: str | None = None

    def _activate(self, project: ProjectDocument, unsaved: bool) -> ProjectDocument:
        self.project = project
        self.draft = project.clone_config()
        self.has_unsaved_applied_changes = unsaved
        self.validation_error = None
        return project

    def import_excel(self, path: Path, project_name: str | None = None) -> ProjectDocument:
        imported = self.importer.import_project(path, project_name)
        current = self.project
        # The normal UI action imports Config into the project that is already
        # open.  Its user-assigned identity must not silently become the Excel
        # filename (or a new UUID).  Supplying project_name explicitly keeps
        # the importer API's create-a-new-project behavior for automation and
        # tests that intentionally create separate projects.
        if current is not None and project_name is None:
            imported.project_id = current.project_id
            imported.name = current.name
            imported.created_at = current.created_at
            imported.config = merge_manual_selections(imported.config, self.draft or current.config)
        return self._activate(imported, unsaved=True)

    def new_project(self, name: str) -> ProjectDocument:
        return self._activate(ProjectDocument.create(name, "ui", empty_config_payload()), unsaved=True)

    def load_project(self, project_id: str) -> ProjectDocument:
        project = self.store.load(project_id)
        self.store.remember_recent(project)
        return self._activate(project, unsaved=False)

    def open_project_file(self, path: Path) -> ProjectDocument:
        project = self.store.load_file(path)
        # Advanced browsing may select a JSON outside the managed workspace.
        # Copy the validated snapshot into ProjectStore without touching the
        # selected source file, so the readable project selector can reopen it.
        self.store.save(project)
        return self._activate(project, unsaved=False)

    def load_recent(self) -> ProjectDocument | None:
        project = self.store.load_recent()
        return self._activate(project, unsaved=False) if project else None

    def close_project(self, disposition: str = "cancel") -> bool:
        """Clear only the active project; persisted files and recent history remain."""

        if self.project is None:
            return True
        if self.has_unsaved_changes:
            if disposition == "cancel":
                return False
            if disposition == "save":
                self.save_configuration()
            elif disposition != "discard":
                raise ProjectStateError("PROJECT_CLOSE_ACTION_INVALID", f"关闭项目操作非法：{disposition}")
        self.project = None
        self.draft = None
        self.has_unsaved_applied_changes = False
        self.validation_error = None
        return True

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

    @property
    def config_status(self) -> ConfigStatus | None:
        if self.project is None:
            return None
        if self.validation_error:
            return ConfigStatus.ERROR
        if self.is_dirty or self.has_unsaved_applied_changes:
            return ConfigStatus.DIRTY
        return ConfigStatus.SAVED

    @property
    def has_unsaved_changes(self) -> bool:
        return self.is_dirty or self.has_unsaved_applied_changes

    def module(self, name: str, draft: bool = True) -> dict[str, Any]:
        project, working = self._require_active()
        config = working if draft else project.config
        for module in config.get("modules", []):
            if module.get("name") == name:
                return module
        raise ProjectValidationError("PROJECT_MODULE_NOT_FOUND", f"项目中不存在模块：{name}")

    def update_module(self, name: str, field: str, value: Any) -> None:
        self.validation_error = None
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

    def update_corner_voltage(self, domain: str, corner: str, value: Any) -> None:
        """Update one project-local Voltage Domain value in the draft."""

        self.validation_error = None
        _project, draft = self._require_active()
        domain_name = str(domain).strip()
        corner_name = str(corner).strip().upper()
        if domain_name not in draft.get("voltage_order", []):
            raise ProjectValidationError(
                "PROJECT_VOLTAGE_DOMAIN_INVALID",
                f"Voltage Domain 未定义：{domain_name}",
            )
        if corner_name not in {"MAX", "TYP", "MIN"}:
            raise ProjectValidationError("PROJECT_CORNER_INVALID", f"Corner 非法：{corner_name}")
        draft["corners"][corner_name]["voltages"][domain_name] = str(value).strip()

    def template_selection(self, module: str) -> dict[str, Any]:
        _project, draft = self._require_active()
        return selection_for(draft, module)

    def update_template(self, module: str, direction: str, template_id: str | None) -> None:
        self.validation_error = None
        _project, draft = self._require_active()
        set_template_choice(draft, module, direction, template_id)

    def update_root(self, name: str, value: str) -> None:
        self.validation_error = None
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
            if name in EXTERNAL_ROOT_NAMES and (not str(value).strip() or not Path(str(value)).is_dir())
        }

    def effective_template_root(self, draft: bool = True) -> Path:
        project, working = self._require_active()
        config = working if draft else project.config
        return self.templates.effective_root(config)

    def template_override(self) -> str:
        _project, draft = self._require_active()
        return str(draft.get("roots", {}).get("template", ""))

    def apply_changes(self) -> None:
        project, draft = self._require_active()
        try:
            validate_config_payload(draft, check_paths=True)
            self.templates.effective_root(draft)
        except (ProjectValidationError, ResourceError) as exc:
            self.validation_error = str(exc)
            raise
        project.config = copy.deepcopy(draft)
        project.updated_at = utc_now()
        self.draft = project.clone_config()
        self.has_unsaved_applied_changes = True
        self.validation_error = None

    def discard_draft(self) -> None:
        project, _draft = self._require_active()
        self.draft = project.clone_config()
        self.validation_error = None

    def save_project(self) -> Path:
        project, _draft = self._require_active()
        if self.is_dirty:
            raise ProjectStateError("PROJECT_DIRTY", "存在尚未 Apply 的修改；请先 Apply Changes 或丢弃草稿")
        path = self.store.save(project)
        self.has_unsaved_applied_changes = False
        return path

    def save_configuration(self) -> Path:
        """Validate, apply and persist the current draft as one user operation.

        The active snapshot and draft are mutated only after ProjectStore has
        completed its atomic write. Validation or storage failures therefore
        preserve both the previous applied snapshot and the user's draft.
        """
        project, draft = self._require_active()
        candidate = copy.deepcopy(draft)
        try:
            validate_config_payload(candidate, check_paths=True)
            self.templates.effective_root(candidate)
        except (ProjectValidationError, ResourceError) as exc:
            self.validation_error = str(exc)
            raise
        staged = copy.deepcopy(project)
        staged.config = candidate
        staged.updated_at = utc_now()
        path = self.store.save(staged)
        self.project = staged
        self.draft = staged.clone_config()
        self.has_unsaved_applied_changes = False
        self.validation_error = None
        return path

    def save_project_draft(self) -> Path:
        """Public UI action: validate, apply and atomically save the project."""

        return self.save_configuration()

    def recent_projects(self):
        return self.store.recent_project_records()

    def remove_recent(self, project_id: str) -> None:
        self.store.remove_recent(project_id)

    def delete_project(self, project_id: str) -> Path:
        """Soft-delete a saved project after it is no longer active."""

        if self.project is not None and self.project.project_id == project_id:
            raise ProjectStateError(
                "PROJECT_DELETE_ACTIVE",
                "当前项目正在打开，请先关闭项目，再从项目首页删除。",
            )
        return self.store.delete_project(project_id)

    def close_and_delete_active_project(self, disposition: str = "cancel") -> Path | None:
        """Close and soft-delete the active managed project as one UI flow."""

        project, _draft = self._require_active()
        project_id = project.project_id
        if not self.close_project(disposition):
            return None
        # A newly-created project may never have been saved.  In that case
        # closing it is the complete delete operation; there is no managed
        # directory (and no external input) to move into the trash.
        if not self.store.project_dir(project_id).is_dir():
            return None
        return self.delete_project(project_id)

    def leave_warning(self) -> str | None:
        if self.has_unsaved_changes:
            return "当前项目有未保存修改。请选择保存项目、放弃修改或取消。"
        return None

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
