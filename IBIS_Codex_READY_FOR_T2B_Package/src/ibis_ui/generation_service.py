from __future__ import annotations

import csv
import difflib
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from ibis_auto.service import CaseKey, GenerationResult, expand_case_keys, generate_from_config
from ibis_auto.validator import validate_case

from .config_adapter import payload_to_core_config
from .errors import ProjectStorageError, ProjectValidationError
from .models import ProjectDocument, utc_now
from .project_store import ProjectStore
from .runtime import APP_VERSION, ResourceResolver, app_metadata
from .working_templates import WorkingTemplateService


CORE_FILE_COUNT = 7


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary:
            temporary.unlink(missing_ok=True)
        raise ProjectStorageError("GENERATION_MANIFEST_SAVE_FAILED", f"生成 Manifest 保存失败：{path}（{exc}）") from exc


def _module(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(row for row in payload["modules"] if str(row["name"]) == name)


def _case_projection(payload: dict[str, Any], key: CaseKey) -> dict[str, Any]:
    module, direction, impedance = key
    module_key = module.casefold()
    return {
        "module": _module(payload, module), "direction": direction, "impedance": impedance,
        "corners": payload["corners"], "voltage_order": payload["voltage_order"],
        "simulation_options": payload["simulation_options"],
        "spice_type": payload.get("spice_type"), "spice_command": payload.get("spice_command"),
        "aliases": [row for row in payload["aliases"] if str(row.get("module", "")).casefold() == module_key and str(row.get("direction", "")).upper() in {direction, "BOTH"}],
        "appends": [row for row in payload["appends"] if str(row.get("module", "")).casefold() == module_key and str(row.get("direction", "")).upper() in {direction, "BOTH"}],
        "overrides": [row for row in payload["overrides"] if str(row.get("module", "")).casefold() == module_key and str(row.get("direction", "")).upper() in {direction, "BOTH", "ALL", ""}],
        "attribute_overrides": [row for row in payload["attribute_overrides"] if str(row.get("module", "")).casefold() == module_key],
        "msi_mappings": [row for row in payload["msi_mappings"] if str(row.get("module", "")).casefold() == module_key],
    }


def _input_files(payload: dict[str, Any], key: CaseKey) -> list[Path]:
    module, _direction, _impedance = key
    roots = {name: Path(str(value)) for name, value in payload["roots"].items()}
    files: list[Path] = []
    mappings = [row for row in payload["msi_mappings"] if str(row.get("module", "")).casefold() == module.casefold()]
    if mappings:
        files.extend(roots["msi"] / str(row["file"]) for row in mappings)
    elif roots["msi"].is_dir():
        files.extend(sorted(roots["msi"].rglob("*.xlsx")))
    keys = {str(payload["corners"][name]["spf_key"]).casefold() for name in ("MAX", "TYP", "MIN")}
    if roots["spf"].is_dir():
        files.extend(
            path for path in sorted(roots["spf"].rglob("*.spf"))
            if module.casefold() in path.name.casefold() and any(item in path.name.casefold() for item in keys)
        )
    spice = str(payload.get("spice_type", "spectre")).casefold()
    files.extend(roots["model"] / spice / name for name in ("rbd.lib", "cap.lib", "mos_var.lib"))
    return list(dict.fromkeys(path.resolve() for path in files if path.is_file()))


def case_fingerprint(payload: dict[str, Any], key: CaseKey, template_path: Path) -> dict[str, Any]:
    inputs = {str(path): _sha256(path) for path in _input_files(payload, key)}
    return {
        "config_hash": _json_hash(_case_projection(payload, key)),
        "template_hash": _sha256(template_path),
        "input_hashes": inputs,
        "combined_hash": _json_hash({"config": _case_projection(payload, key), "template": _sha256(template_path), "inputs": inputs}),
    }


class ProjectGenerationService:
    def __init__(self, store: ProjectStore, resources: ResourceResolver):
        self.store = store
        self.resources = resources

    def _template_service(self, project: ProjectDocument, workflow: dict[str, Any], template_root: Path) -> WorkingTemplateService:
        return WorkingTemplateService(self.store.project_dir(project.project_id), template_root, project.project_id, workflow)

    def output_root(self, project: ProjectDocument, workflow: dict[str, Any]) -> Path:
        raw = str(workflow.setdefault("generation", {}).get("output_root", "")).strip()
        return Path(raw).expanduser().resolve() if raw else self.store.project_dir(project.project_id) / "generated"

    def generate(
        self,
        project: ProjectDocument,
        *,
        selected: Iterable[CaseKey] | None = None,
        overwrite_policy: str = "backup",
        cancel_requested: Callable[[], bool] | None = None,
        progress: Callable[[str, str, str], None] | None = None,
    ) -> GenerationResult:
        workflow = project.workflow or {}
        template_override = str(project.config.get("roots", {}).get("template", "")).strip()
        template_root = Path(template_override).resolve() if template_override else self.resources.template_root
        template_service = self._template_service(project, workflow, template_root)
        template_paths = template_service.generation_paths(project.config)
        config = payload_to_core_config(project.config, template_root=template_root, template_paths=template_paths)
        selected_keys = list(selected) if selected is not None else expand_case_keys(config)
        output = self.output_root(project, workflow)
        golden_root = self.resources.golden_root
        result = generate_from_config(
            config, output, selected=selected_keys,
            golden_root=golden_root if golden_root.is_dir() else None,
            overwrite_policy=overwrite_policy, cancel_requested=cancel_requested, progress=progress,
        )
        records = workflow.setdefault("generation", {}).setdefault("cases", {})
        manifests = self.store.project_dir(project.project_id) / "manifests"
        by_string = {f"{module}/{direction}/{ron}ohm": (module, direction, ron) for module, direction, ron in selected_keys}
        for row in result.cases:
            key = by_string.get(row.key)
            record = {
                "key": row.key, "status": row.status, "message": row.message,
                "output_path": row.path, "updated_at": utc_now(),
            }
            if key and row.status in {"PASS", "UNVALIDATED", "FAIL"} and row.path and Path(row.path).is_dir():
                template = template_paths[(key[0], key[1])]
                fingerprint = case_fingerprint(project.config, key, template)
                case_path = Path(row.path)
                output_files = {path.name: _sha256(path) for path in sorted(case_path.iterdir()) if path.is_file()}
                manifest = {
                    "project_id": project.project_id, "module": key[0], "direction": key[1], "ron": key[2],
                    "generator_version": APP_VERSION, "git_commit": app_metadata().git_commit,
                    **fingerprint, "output_files": output_files, "generated_at": utc_now(),
                    "validation_status": row.status, "validation_message": row.message,
                }
                manifest_path = manifests / f"{key[0]}__{key[1].lower()}__{key[2]}ohm.json"
                _atomic_json(manifest_path, manifest)
                record["manifest_path"] = str(manifest_path)
                record["fingerprint"] = fingerprint["combined_hash"]
            records[row.key] = record
        workflow["generation"]["output_root"] = str(output)
        workflow["generation"]["tasks"] = [asdict(row) for row in result.cases]
        project.workflow = workflow
        project.updated_at = utc_now()
        self.store.save(project)
        return result

    def case_statuses(self, project: ProjectDocument) -> list[dict[str, Any]]:
        workflow = project.workflow or {}
        records = workflow.get("generation", {}).get("cases", {})
        template_override = str(project.config.get("roots", {}).get("template", "")).strip()
        template_root = Path(template_override).resolve() if template_override else self.resources.template_root
        templates = self._template_service(project, workflow, template_root)
        paths = {}
        try:
            paths = templates.generation_paths(project.config)
        except (ProjectValidationError, ProjectStorageError):
            pass
        config = payload_to_core_config(project.config, template_root=template_root, template_paths=paths) if paths else None
        all_keys = expand_case_keys(config) if config else [
            (str(module["name"]), direction, int(ron))
            for module in project.config.get("modules", [])
            for direction in (("DRV", "RCV") if str(module["generate_type"]).upper() == "BOTH" else (str(module["generate_type"]).upper(),))
            for ron in module["impedances"]
        ]
        statuses: list[dict[str, Any]] = []
        for key in all_keys:
            string_key = f"{key[0]}/{key[1]}/{key[2]}ohm"
            record = dict(records.get(string_key, {}))
            if not record:
                statuses.append({"key": string_key, "module": key[0], "direction": key[1], "ron": key[2], "status": "NOT_GENERATED", "message": "尚未生成"})
                continue
            status = str(record.get("status", "FAIL"))
            manifest_path = Path(str(record.get("manifest_path", "")))
            template_key = (key[0], key[1])
            if status in {"PASS", "UNVALIDATED"} and template_key in paths and manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    current = case_fingerprint(project.config, key, paths[template_key])
                    if current["combined_hash"] != manifest.get("combined_hash"):
                        status = "STALE"
                        record["message"] = "Config、模板或关键输入已发生变化"
                except (OSError, json.JSONDecodeError):
                    status = "FAIL"
                    record["message"] = "生成 Manifest 无法读取"
            statuses.append({**record, "key": string_key, "module": key[0], "direction": key[1], "ron": key[2], "status": status})
        return statuses

    def validate_existing_case(self, project: ProjectDocument, key: CaseKey) -> tuple[str, str]:
        workflow = project.workflow or {}
        output = self.output_root(project, workflow) / key[0] / key[1].lower() / f"{key[2]}ohm_ibis"
        if not output.is_dir():
            return "FAIL", "Case 输出目录不存在"
        config = payload_to_core_config(project.config, template_root=self.resources.template_root)
        golden = self.resources.golden_root / key[0] / key[1].lower() / f"{key[2]}ohm_ibis"
        return validate_case(output, golden if golden.is_dir() else None, config.roots["model"], config.roots["spf"])

    def golden_diff(self, project: ProjectDocument, key: CaseKey) -> str:
        """Return a real unified line diff for the selected reference case."""
        workflow = project.workflow or {}
        generated = self.output_root(project, workflow) / key[0] / key[1].lower() / f"{key[2]}ohm_ibis"
        golden = self.resources.golden_root / key[0] / key[1].lower() / f"{key[2]}ohm_ibis"
        if not generated.is_dir():
            raise ProjectValidationError("GENERATED_CASE_MISSING", "所选 Case 尚未生成，无法比较 Golden。")
        if not golden.is_dir():
            raise ProjectValidationError("GOLDEN_CASE_MISSING", "所选 Case 没有冻结 Golden；只能执行结构检查。")
        names = sorted(
            {path.name for path in generated.iterdir() if path.is_file()}
            | {path.name for path in golden.iterdir() if path.is_file()}
        )
        sections: list[str] = []
        for name in names:
            actual_path = generated / name
            expected_path = golden / name
            actual = actual_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if actual_path.is_file() else []
            expected = expected_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if expected_path.is_file() else []
            diff = list(difflib.unified_diff(expected, actual, fromfile=f"Golden/{name}", tofile=f"Generated/{name}"))
            if diff:
                sections.extend(diff)
        return "".join(sections) if sections else "Golden 比较 PASS：所有文件逐行一致。\n"

    def export_summary(self, project: ProjectDocument, csv_path: Path, text_path: Path) -> tuple[Path, Path]:
        rows = self.case_statuses(project)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Module", "Direction", "Ron", "Status", "Output Path", "Reason"])
            for row in rows:
                writer.writerow([row["module"], row["direction"], row["ron"], row["status"], row.get("output_path", ""), row.get("message", "")])
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        lines = [f"Total Cases: {len(rows)}", *[f"{name}: {counts.get(name, 0)}" for name in ("PASS", "UNVALIDATED", "FAIL", "STALE", "NOT_GENERATED")], ""]
        lines.extend(f"{row['key']} | {row['status']} | {row.get('output_path', '')} | {row.get('message', '')}" for row in rows)
        text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return csv_path, text_path
