from __future__ import annotations

import copy
import zipfile
from pathlib import Path
from typing import Any

from .errors import ProjectStateError, ProjectValidationError, ResourceError
from .config_adapter import payload_to_core_config
from ibis_auto.msi import discover as discover_msi
from ibis_auto.spf import parse as parse_spf
from .excel_exporter import export_config_excel, verify_export_round_trip
from .excel_importer import ExcelImporter
from .generation_service import ProjectGenerationService
from .models import EXTERNAL_ROOT_NAMES, ProjectDocument, build_case_tree, empty_config_payload, empty_workflow_payload, utc_now, validate_config_payload
from .msi_master import MASTER_FILENAME, MergePreview, merge_msi_master, preview_merge
from .project_store import ProjectStore
from .runtime import ResourceResolver
from .status import ConfigStatus
from .template_service import TemplateResourceService
from .template_selection import ensure_template_selections, merge_manual_selections, selection_for, set_template_choice
from .working_templates import WorkingTemplateService
from .template_preview import render_preview
from .configuration_review import changes, validate_tables
from . import effective_msi


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
        self.workflow_draft: dict[str, Any] | None = None
        self.has_unsaved_applied_changes = False
        self.validation_error: str | None = None
        self.pending_edit_errors: dict[str, str] = {}

    def _activate(self, project: ProjectDocument, unsaved: bool) -> ProjectDocument:
        self.pending_edit_errors.clear()
        self.project = project
        self.draft = project.clone_config()
        self.workflow_draft = copy.deepcopy(project.workflow or empty_workflow_payload())
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
            imported.workflow = copy.deepcopy(self.workflow_draft or current.workflow or empty_workflow_payload())
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
        self.workflow_draft = None
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
        return bool(
            self.project
            and self.draft is not None
            and (
                self.draft != self.project.config
                or self.workflow_draft != (self.project.workflow or empty_workflow_payload())
                or self.pending_edit_errors
            )
        )

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

    def add_module(self, name: str, generate_type: str = "DRV", impedances: list[int] | None = None) -> None:
        _project, draft = self._require_active()
        clean = str(name).strip()
        if not clean:
            raise ProjectValidationError("PROJECT_MODULE_INVALID", "模块名称不能为空")
        if any(str(row.get("name", "")).casefold() == clean.casefold() for row in draft["modules"]):
            raise ProjectValidationError("PROJECT_MODULE_DUPLICATE", f"模块名称重复：{clean}")
        domains = list(draft.get("voltage_order", []))
        io_domain = next((item for item in domains if item.casefold() == "vddq"), domains[0] if domains else "")
        vih_domain = next((item for item in domains if item.casefold() == "vdd"), io_domain)
        draft["modules"].append({
            "name": clean,
            "generate_type": str(generate_type).upper(),
            "impedances": list(impedances or [30]),
            "ibis_io_voltage_domain": io_domain,
            "ibis_vih_voltage_domain": vih_domain,
            "tr": {corner: "20p" for corner in ("MAX", "TYP", "MIN")},
            "tf": {corner: "20p" for corner in ("MAX", "TYP", "MIN")},
        })
        ensure_template_selections(draft)

    def module_references(self, name: str) -> dict[str, int]:
        _project, draft = self._require_active()
        key = name.casefold()
        fields = {
            "Pin Mapping": "aliases", "CKT Append": "appends", "T2B Mapping": "templates",
            "Signal Override": "overrides", "MSI Attribute Override": "attribute_overrides",
            "MSI Mapping": "msi_mappings",
        }
        result: dict[str, int] = {}
        for label, field in fields.items():
            count = sum(str(row.get("module", "")).casefold() == key for row in draft.get(field, []))
            if count:
                result[label] = count
        return result

    def rename_module(self, old_name: str, new_name: str) -> None:
        _project, draft = self._require_active()
        clean = str(new_name).strip()
        if not clean:
            raise ProjectValidationError("PROJECT_MODULE_INVALID", "模块名称不能为空")
        if old_name.casefold() != clean.casefold() and any(
            str(row.get("name", "")).casefold() == clean.casefold() for row in draft["modules"]
        ):
            raise ProjectValidationError("PROJECT_MODULE_DUPLICATE", f"模块名称重复：{clean}")
        self.module(old_name)["name"] = clean
        for field in ("aliases", "appends", "templates", "overrides", "attribute_overrides", "msi_mappings", "template_selections"):
            for row in draft.get(field, []):
                if str(row.get("module", "")).casefold() == old_name.casefold():
                    row["module"] = clean
        for field in ("working_templates", "template_sources", "template_baselines"):
            working = (self.workflow_draft or {}).get(field, {})
            for key in list(working):
                if key.split("|", 1)[0].casefold() == old_name.casefold():
                    working[f"{clean}|{key.split('|', 1)[1]}"] = working.pop(key)

    def duplicate_module(self, name: str, new_name: str) -> None:
        _project, draft = self._require_active()
        source = copy.deepcopy(self.module(name))
        self.add_module(new_name, source["generate_type"], source["impedances"])
        target = self.module(new_name)
        target.update({key: copy.deepcopy(value) for key, value in source.items() if key != "name"})
        for field in ("aliases", "appends", "templates", "overrides", "attribute_overrides", "msi_mappings"):
            additions = []
            for row in draft.get(field, []):
                if str(row.get("module", "")).casefold() == name.casefold():
                    cloned = copy.deepcopy(row)
                    cloned["module"] = new_name
                    additions.append(cloned)
            draft[field].extend(additions)
        ensure_template_selections(draft)

    def delete_module(self, name: str, cascade: bool = False) -> dict[str, int]:
        _project, draft = self._require_active()
        references = self.module_references(name)
        if references and not cascade:
            detail = "、".join(f"{label} {count} 项" for label, count in references.items())
            raise ProjectValidationError("PROJECT_MODULE_REFERENCED", f"模块 {name} 仍被引用：{detail}")
        before = len(draft["modules"])
        draft["modules"] = [row for row in draft["modules"] if str(row.get("name", "")).casefold() != name.casefold()]
        if len(draft["modules"]) == before:
            raise ProjectValidationError("PROJECT_MODULE_NOT_FOUND", f"项目中不存在模块：{name}")
        for field in ("aliases", "appends", "templates", "overrides", "attribute_overrides", "msi_mappings", "template_selections"):
            draft[field] = [row for row in draft.get(field, []) if str(row.get("module", "")).casefold() != name.casefold()]
        for field in ("working_templates", "template_sources", "template_baselines"):
            working = (self.workflow_draft or {}).get(field, {})
            for key in list(working):
                if key.split("|", 1)[0].casefold() == name.casefold():
                    del working[key]
        return references

    def update_corner(self, corner: str, field: str, value: Any) -> None:
        _project, draft = self._require_active()
        corner = str(corner).upper()
        if corner not in {"MAX", "TYP", "MIN"} or field not in {"process", "temperature", "spf_key"}:
            raise ProjectValidationError("PROJECT_CORNER_INVALID", f"Corner 字段非法：{corner}.{field}")
        draft["corners"][corner][field] = str(value)

    def set_voltage_domains(self, rows: list[dict[str, Any]]) -> None:
        _project, draft = self._require_active()
        names = [str(row.get("domain", "")).strip() for row in rows]
        if any(not name for name in names) or len({name.casefold() for name in names}) != len(names):
            raise ProjectValidationError("PROJECT_VOLTAGE_DOMAIN_INVALID", "Voltage Domain 不能为空或重复")
        referenced = {
            str(module.get(field, "")).casefold()
            for module in draft["modules"]
            for field in ("ibis_io_voltage_domain", "ibis_vih_voltage_domain")
        }
        missing = referenced - {name.casefold() for name in names}
        if missing:
            raise ProjectValidationError("PROJECT_VOLTAGE_DOMAIN_REFERENCED", f"仍被模块引用的 Voltage Domain 不能删除：{', '.join(sorted(missing))}")
        draft["voltage_order"] = names
        for corner in ("MAX", "TYP", "MIN"):
            draft["corners"][corner]["voltages"] = {
                name: str(row.get(corner, "")).strip() for name, row in zip(names, rows)
            }

    def set_calibrations(self, rows: list[dict[str, Any]]) -> None:
        _project, draft = self._require_active()
        names = [str(row.get("signal", "")).strip() for row in rows]
        if any(not name for name in names) or len({name.casefold() for name in names}) != len(names):
            raise ProjectValidationError("PROJECT_CALIBRATION_INVALID", "Calibration Signal 不能为空或重复")
        for corner in ("MAX", "TYP", "MIN"):
            draft["corners"][corner]["calibration"] = {
                name: str(row.get(corner, "")) for name, row in zip(names, rows)
            }

    def replace_config_rows(self, field: str, rows: list[Any]) -> None:
        _project, draft = self._require_active()
        allowed = {"simulation_options", "aliases", "appends", "overrides", "attribute_overrides", "msi_mappings"}
        if field not in allowed:
            raise ProjectValidationError("PROJECT_FIELD_UNSUPPORTED", f"不支持替换 Config 字段：{field}")
        if field == "attribute_overrides" and any(str(row.get("attribute", "")).upper() != "POWER_DOMAIN" for row in rows):
            raise ProjectValidationError("MSI_ATTRIBUTE_OVERRIDE_INVALID", "当前 Core 仅支持 POWER_DOMAIN Override")
        draft[field] = copy.deepcopy(rows)

    def export_config(self, target: Path) -> Path:
        _project, draft = self._require_active()
        validate_config_payload(draft, check_paths=False)
        path = export_config_excel(draft, target)
        verify_export_round_trip(draft, path)
        return path

    def msi_signal_details(self, module: str) -> list[dict[str, Any]]:
        _project, draft = self._require_active()
        template_root = self.effective_template_root()
        raw_payload = copy.deepcopy(draft)
        raw_payload["attribute_overrides"] = []
        raw_signals = discover_msi(payload_to_core_config(raw_payload, template_root=template_root), module)
        effective_signals = discover_msi(payload_to_core_config(draft, template_root=template_root), module)
        effective_by_name = {row.name.casefold(): row for row in effective_signals}
        overrides = {
            (str(row["signal"]).casefold(), str(row["attribute"]).upper()): str(row["value"])
            for row in draft["attribute_overrides"]
            if str(row["module"]).casefold() == module.casefold()
        }
        result = []
        for signal in raw_signals:
            effective = effective_by_name[signal.name.casefold()]
            result.append({
                "signal": signal.name, "width": signal.width, "direction": signal.direction,
                "pad": "Y" if signal.pad else "N", "attribute_type": signal.attribute_type,
                "power_domain_raw": signal.power_domain,
                "power_domain_override": overrides.get((signal.name.casefold(), "POWER_DOMAIN"), ""),
                "power_domain_effective": effective.power_domain,
                "ground_domain": signal.ground_domain, "default_value": signal.default,
                "description": signal.description, "databook_description": signal.databook_description,
                "row_order": signal.row_order,
            })
        return result

    def spf_interface_preview(self, module: str, direction: str) -> dict[str, Any]:
        _project, draft = self._require_active()
        corner = draft["corners"]["TYP"]
        root = Path(str(draft["roots"]["spf"]))
        matches = [
            path for path in root.rglob("*.spf")
            if module.casefold() in path.name.casefold() and str(corner["spf_key"]).casefold() in path.name.casefold()
        ]
        if len(matches) != 1:
            raise ProjectValidationError("SPF_SOURCE_AMBIGUOUS", f"模块 {module} TYP SPF 匹配数量为 {len(matches)}")
        top, pins = parse_spf(matches[0])
        aliases = {
            str(row["original_pin"]).casefold(): str(row["alias"])
            for row in draft["aliases"]
            if str(row["module"]).casefold() == module.casefold() and str(row["direction"]).upper() in {direction.upper(), "BOTH"}
        }
        return {
            "module": module, "corner": "TYP", "path": str(matches[0].resolve()),
            "top_subckt": top, "pins": [
                {"order": index + 1, "original_pin": pin, "effective_pin": aliases.get(pin.casefold(), pin)}
                for index, pin in enumerate(pins)
            ],
        }

    def preview_msi_master(self) -> MergePreview:
        project, draft = self._require_active()
        workflow = self.workflow_draft or empty_workflow_payload()
        source_root = str(workflow.get("msi_master", {}).get("source_root", "")).strip()
        root = Path(source_root or str(draft["roots"].get("msi", ""))).expanduser().resolve()
        master = self.store.project_dir(project.project_id) / "msi" / MASTER_FILENAME
        return preview_merge(root, [str(row["name"]) for row in draft["modules"]], master)

    def merge_msi_master(self, explicit_mappings: list[dict[str, str]] | None = None) -> Path:
        project, draft = self._require_active()
        workflow = self.workflow_draft or empty_workflow_payload()
        state = workflow.setdefault("msi_master", {})
        source_root = str(state.get("source_root", "")).strip()
        root = Path(source_root or str(draft["roots"].get("msi", ""))).expanduser().resolve()
        target = self.store.project_dir(project.project_id) / "msi" / MASTER_FILENAME
        preview = preview_merge(root, [str(row["name"]) for row in draft["modules"]], target)
        path, mappings, sources = merge_msi_master(preview, target, explicit_mappings=explicit_mappings)
        state.update({
            "path": str(path), "source_root": str(root), "sources": sources,
            "mappings": mappings, "last_merge_at": utc_now(),
        })
        draft["roots"]["msi"] = str(path.parent)
        draft["msi_mappings"] = copy.deepcopy(mappings)
        self.workflow_draft = workflow
        return path

    def working_template_service(self) -> WorkingTemplateService:
        project, _draft = self._require_active()
        if self.workflow_draft is None:
            self.workflow_draft = empty_workflow_payload()
        return WorkingTemplateService(
            self.store.project_dir(project.project_id),
            self.effective_template_root(),
            project.project_id,
            self.workflow_draft,
        )

    def create_working_template(self, module: str, direction: str, source_template_id: str | None = None) -> dict[str, Any]:
        return self.working_template_service().create(self.active_config, module, direction, source_template_id)

    def read_working_template(self, module: str, direction: str) -> str:
        return self.working_template_service().read(module, direction)

    def template_source(self, module: str, direction: str) -> str:
        return self.working_template_service().resolve_path(self.active_config, module, direction, validate=False).read_text(encoding="utf-8")

    def preview_t2b(self, key: tuple[str, str, int], text: str | None = None) -> str:
        return render_preview(self.active_config, self.effective_template_root(), self.working_template_service(), key, text)

    def save_template_and_project(self, module: str, direction: str, text: str) -> Path:
        """Commit the template reference with the project; failed writes keep the draft."""
        previous = copy.deepcopy(self.workflow_draft)
        try:
            self.save_working_template(module, direction, text)
            return self.save_project_draft()
        except Exception:
            self.workflow_draft = previous
            raise

    def save_working_template(self, module: str, direction: str, text: str) -> dict[str, Any]:
        record = self.working_template_service().save(self.active_config, module, direction, text)
        self.workflow_draft.setdefault("template_sources", {})[f"{module}|{direction}"] = {"kind": "项目自定义模板", "path": record["path"]}
        return record

    def restore_working_template(self, module: str, direction: str, version: int | None = None) -> dict[str, Any]:
        service = self.working_template_service()
        if version is None:
            return service.restore_builtin(self.active_config, module, direction)
        return service.restore(self.active_config, module, direction, version)

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

    def set_template_source(self, module, direction, kind, path=""):
        key = f"{module}|{direction}"
        sources = self.workflow_draft.setdefault("template_sources", {})
        if kind == "项目自定义模板" and key not in self.workflow_draft.get("working_templates", {}):
            raise ProjectValidationError("TEMPLATE_CUSTOM_MISSING", "该模块尚无项目自定义模板，请先在 T2B 页面修改模板并保存到草稿")
        previous = copy.deepcopy(sources)
        sources[key] = {"kind": kind, "path": str(Path(path).resolve()) if path else ""}
        try:
            self.working_template_service().resolve_path(self.active_config, module, direction)
        except Exception:
            self.workflow_draft["template_sources"] = previous
            raise

    def template_origin(self, module, direction):
        key = f"{module}|{direction}"
        source = self.workflow_draft.get("template_sources", {}).get(key)
        custom = self.workflow_draft.get("working_templates", {}).get(key)
        kind = source["kind"] if source else ("项目自定义模板" if custom else ("外部模板" if self.template_override() else "内置母模板"))
        try:
            path = self.working_template_service().resolve_path(self.active_config, module, direction, validate=False)
            import hashlib
            current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception as exc:
            return dict(kind=kind, path=str(exc), changed=False)
        saved_sources = (self.project.workflow or {}).get("template_baselines", {})
        saved_hash = saved_sources.get(key, {}).get("sha256")
        return dict(kind=kind, path=str(path), changed=bool(saved_hash and current_hash != saved_hash), sha256=current_hash)

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
        self.check_pending_edits()
        try:
            validate_config_payload(draft, check_paths=True)
            template_root = self.templates.effective_root(draft)
            payload_to_core_config(draft, template_root=template_root)
            self.validate_extended(draft)
        except (ProjectValidationError, ResourceError) as exc:
            self.validation_error = str(exc)
            raise
        project.config = copy.deepcopy(draft)
        project.workflow = copy.deepcopy(self.workflow_draft or empty_workflow_payload())
        project.updated_at = utc_now()
        self.draft = project.clone_config()
        self.has_unsaved_applied_changes = True
        self.validation_error = None

    def discard_draft(self) -> None:
        self.pending_edit_errors.clear()
        project, _draft = self._require_active()
        self.draft = project.clone_config()
        self.workflow_draft = copy.deepcopy(project.workflow or empty_workflow_payload())
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
        self.check_pending_edits()
        candidate = copy.deepcopy(draft)
        try:
            validate_config_payload(candidate, check_paths=True)
            template_root = self.templates.effective_root(candidate)
            payload_to_core_config(candidate, template_root=template_root)
            self.validate_extended(candidate)
        except (ProjectValidationError, ResourceError) as exc:
            self.validation_error = str(exc)
            raise
        staged = copy.deepcopy(project)
        staged.config = candidate
        staged.workflow = copy.deepcopy(self.workflow_draft or empty_workflow_payload())
        for module in candidate["modules"]:
            for direction in (("DRV", "RCV") if module["generate_type"] == "BOTH" else (module["generate_type"],)):
                origin = self.template_origin(module["name"], direction)
                if origin.get("sha256"):
                    key = f"{module['name']}|{direction}"
                    staged.workflow.setdefault("template_baselines", {})[key] = origin
        staged.updated_at = utc_now()
        path = self.store.save(staged)
        self.project = staged
        self.draft = staged.clone_config()
        self.workflow_draft = copy.deepcopy(staged.workflow)
        self.has_unsaved_applied_changes = False
        self.validation_error = None
        return path

    def validate_extended(self, payload):
        def pins(module, direction):
            try:
                return [row["original_pin"] for row in self.spf_interface_preview(module, direction)["pins"]]
            except ProjectValidationError:
                return []  # Missing external roots remain diagnosed by input checking.
        validate_tables(payload, pins)
        # Validate explicit mappings and overrides, including cross-section references.
        if payload["msi_mappings"] or payload["overrides"] or payload["attribute_overrides"]:
            effective_msi.inspect(payload, self.workflow_draft or {}).require_valid()

    def review_changes(self):
        project, draft = self._require_active()
        self.check_pending_edits()
        validate_config_payload(draft, check_paths=True)
        payload_to_core_config(draft, template_root=self.effective_template_root())
        self.validate_extended(draft)
        path = self.store.project_dir(project.project_id) / "project.json"
        before = self.store.load_file(path) if path.is_file() else None
        baseline = before.to_dict() if before else {}
        current = project.to_dict()
        current["config"] = copy.deepcopy(draft)
        current["workflow"] = copy.deepcopy(self.workflow_draft)
        for field in ("created_at", "updated_at"):
            baseline.pop(field, None)
            current.pop(field, None)
        return changes(baseline, current)

    def effective_msi_preview(self):
        return effective_msi.inspect(self.active_config, self.workflow_draft or {})

    def prepare_master(self, restore=False):
        project, draft = self._require_active()
        effective, path, manifest = effective_msi.prepare(draft, self.workflow_draft, self.store.project_dir(project.project_id), restore=restore)
        return path

    def msi_candidates(self):
        return effective_msi.candidates(effective_msi.source_payload(self.active_config, self.workflow_draft or {}))

    def check_pending_edits(self) -> None:
        if self.pending_edit_errors:
            raise ProjectValidationError("PROJECT_INLINE_INVALID", "；".join(self.pending_edit_errors.values()))

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
            raise ProjectStateError("PROJECT_DIRTY", "存在未保存的修改，请保存项目后生成")
        if self.has_unsaved_applied_changes:
            raise ProjectStateError("PROJECT_NOT_SAVED", "项目存在尚未保存的配置，生成前请先保存项目")
        if self.project is None:
            raise ProjectStateError("PROJECT_NOT_OPEN", "当前没有打开的项目")

    def generation_service(self) -> ProjectGenerationService:
        return ProjectGenerationService(self.store, self.resources)

    def generate_cases(
        self,
        selected=None,
        *,
        overwrite_policy: str = "backup",
        cancel_requested=None,
        progress=None,
    ):
        self.ensure_generate_allowed()
        project, _draft = self._require_active()
        result = self.generation_service().generate(
            project,
            selected=selected,
            overwrite_policy=overwrite_policy,
            cancel_requested=cancel_requested,
            progress=progress,
        )
        self.workflow_draft = copy.deepcopy(project.workflow or empty_workflow_payload())
        return result

    def generation_statuses(self) -> list[dict[str, Any]]:
        project, _draft = self._require_active()
        return self.generation_service().case_statuses(project)

    def golden_diff(self, key: tuple[str, str, int]) -> str:
        project, _draft = self._require_active()
        return self.generation_service().golden_diff(project, key)

    def export_generation_summary(self, directory: Path) -> tuple[Path, Path]:
        project, _draft = self._require_active()
        directory = directory.expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return self.generation_service().export_summary(
            project,
            directory / "generation_summary.csv",
            directory / "generation_summary.txt",
        )

    def export_project_package(self, target: Path) -> Path:
        self.ensure_generate_allowed()
        project, _draft = self._require_active()
        root = self.store.project_dir(project.project_id)
        target = target.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(root.rglob("*")):
                    if path.is_file() and "generated" not in path.relative_to(root).parts:
                        archive.write(path, Path(project.project_id) / path.relative_to(root))
        except OSError as exc:
            raise ProjectStateError("PROJECT_PACKAGE_EXPORT_FAILED", f"完整项目包导出失败：{target}（{exc}）") from exc
        return target
