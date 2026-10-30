from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from ._compat37 import unlink_missing_ok
from .errors import ProjectStorageError, ProjectValidationError
from .models import ProjectDocument
from .runtime import default_workspace


@dataclass(frozen=True)
class RecentProjectRecord:
    project_id: str
    name: str
    last_opened: str
    path: Path
    available: bool
    source_excel: str
    updated_at: str
    status: str


class ProjectStore:
    """Atomic, project-id-scoped persistence for applied project snapshots."""

    def __init__(self, workspace: Path | None = None):
        self.workspace = (workspace or default_workspace()).expanduser().resolve()
        self.projects_root = self.workspace / "projects"
        self.trash_root = self.workspace / "trash"
        self.state_path = self.workspace / "ui_state.json"

    def ensure_ready(self) -> None:
        """Create and verify the user-writable workspace before the UI starts."""
        try:
            self.projects_root.mkdir(parents=True, exist_ok=True)
            self.trash_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.workspace, delete=False) as stream:
                probe = Path(stream.name)
                stream.write("IBIS Automation workspace check\n")
            probe.unlink()
        except OSError as exc:
            if "probe" in locals():
                unlink_missing_ok(probe)
            raise ProjectStorageError(
                "WORKSPACE_NOT_WRITABLE",
                f"项目 Workspace 不可写，请使用 --workspace 指定其他目录：{self.workspace}（{exc}）",
            ) from exc

    @staticmethod
    def _validated_project_id(project_id: str) -> str:
        try:
            return str(UUID(str(project_id)))
        except (TypeError, ValueError) as exc:
            raise ProjectStorageError("PROJECT_ID_INVALID", f"项目 ID 非法：{project_id!r}") from exc

    def project_dir(self, project_id: str) -> Path:
        return self.projects_root / self._validated_project_id(project_id)

    def project_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"

    @staticmethod
    def _atomic_json_write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except (OSError, TypeError, ValueError) as exc:
            if "temporary" in locals():
                unlink_missing_ok(temporary)
            raise ProjectStorageError("PROJECT_SAVE_FAILED", f"项目保存失败：{path}（{exc}）") from exc

    def save(self, project: ProjectDocument) -> Path:
        # Round-trip validation catches malformed documents before they replace a valid snapshot.
        validated = ProjectDocument.from_dict(project.to_dict())
        path = self.project_path(validated.project_id)
        # Recent-project metadata is written first. If the project commit then
        # fails, the previous project.json remains intact and the UI can show
        # the premature history entry as unavailable instead of reporting a
        # failed save after project data was already replaced.
        self.remember_recent(validated)
        self._atomic_json_write(path, validated.to_dict())
        return path

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"schema_version": 2, "recent_projects": []}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 2, "recent_projects": []}
        return payload if isinstance(payload, dict) else {"schema_version": 2, "recent_projects": []}

    def remember_recent(self, project: ProjectDocument) -> None:
        state = self._read_state()
        rows = state.get("recent_projects", [])
        if not isinstance(rows, list):
            rows = []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        updated = [
            {
                "project_id": project.project_id,
                "name": project.name,
                "last_opened": now,
                "source_excel": project.source_excel.path if project.source_excel else "无（UI 新建）",
                "updated_at": project.updated_at,
            },
            *[
                item
                for item in rows
                if isinstance(item, dict) and str(item.get("project_id", "")) != project.project_id
            ],
        ][:10]
        self._atomic_json_write(
            self.state_path,
            {
                "schema_version": 2,
                "recent_project_id": project.project_id,
                "recent_projects": updated,
            },
        )

    def recent_project_records(self) -> list[RecentProjectRecord]:
        state = self._read_state()
        rows = state.get("recent_projects", [])
        if not isinstance(rows, list):
            rows = []
        if not rows and state.get("recent_project_id"):
            rows = [{"project_id": state["recent_project_id"], "name": "最近项目", "last_opened": ""}]
        records: list[RecentProjectRecord] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                project_id = self._validated_project_id(str(item.get("project_id", "")))
            except ProjectStorageError:
                continue
            path = self.project_path(project_id)
            source_excel = str(item.get("source_excel", ""))
            updated_at = str(item.get("updated_at", ""))
            project_name = str(item.get("name", "")).strip() or "未命名项目"
            if path.is_file():
                try:
                    project_payload = json.loads(path.read_text(encoding="utf-8"))
                    project_name = str(project_payload.get("name", project_name)).strip() or project_name
                    updated_at = str(project_payload.get("updated_at", updated_at))
                    source = project_payload.get("source_excel")
                    if isinstance(source, dict):
                        source_excel = str(source.get("path", source_excel))
                    elif not source_excel:
                        source_excel = "无（UI 新建）"
                except (OSError, json.JSONDecodeError):
                    pass
            records.append(
                RecentProjectRecord(
                    project_id,
                    project_name,
                    str(item.get("last_opened", "")),
                    path,
                    path.is_file(),
                    source_excel or "未知",
                    updated_at,
                    "已保存" if path.is_file() else "项目文件不存在",
                )
            )
        return records

    def remove_recent(self, project_id: str) -> None:
        validated = self._validated_project_id(project_id)
        state = self._read_state()
        rows = state.get("recent_projects", [])
        remaining = [
            item
            for item in rows
            if isinstance(item, dict) and str(item.get("project_id", "")) != validated
        ] if isinstance(rows, list) else []
        recent_id = state.get("recent_project_id")
        if str(recent_id or "") == validated:
            recent_id = remaining[0].get("project_id") if remaining else None
        self._atomic_json_write(
            self.state_path,
            {"schema_version": 2, "recent_project_id": recent_id, "recent_projects": remaining},
        )

    def delete_project(self, project_id: str) -> Path:
        """Soft-delete a managed project without touching external input files."""

        validated = self._validated_project_id(project_id)
        source = self.project_dir(validated)
        if not source.is_dir():
            raise ProjectStorageError("PROJECT_NOT_FOUND", f"项目不存在：{validated}")

        self.trash_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.trash_root / f"{validated}_{stamp}"
        suffix = 1
        while target.exists():
            target = self.trash_root / f"{validated}_{stamp}_{suffix}"
            suffix += 1
        try:
            os.replace(source, target)
        except OSError as exc:
            raise ProjectStorageError(
                "PROJECT_DELETE_FAILED",
                f"项目删除失败：{source}（{exc}）",
            ) from exc

        # Project data is intentionally retained under workspace/trash for
        # recovery. Only the recent-project index is removed.
        self.remove_recent(validated)
        return target

    def load(self, project_id: str) -> ProjectDocument:
        path = self.project_path(project_id)
        if not path.is_file():
            raise ProjectStorageError("PROJECT_NOT_FOUND", f"项目不存在：{project_id}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            project = ProjectDocument.from_dict(payload)
        except (OSError, json.JSONDecodeError, ProjectValidationError) as exc:
            if isinstance(exc, ProjectValidationError):
                raise
            raise ProjectStorageError("PROJECT_READ_FAILED", f"项目文件无法读取：{path}（{exc}）") from exc
        if project.project_id != project_id:
            raise ProjectStorageError("PROJECT_ID_MISMATCH", f"项目目录与内部 ID 不一致：{project_id}")
        return project

    def load_file(self, path: Path) -> ProjectDocument:
        source = path.expanduser().resolve()
        if not source.is_file():
            raise ProjectStorageError("PROJECT_NOT_FOUND", f"项目配置文件不存在：{source}")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
            return ProjectDocument.from_dict(payload)
        except ProjectValidationError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectStorageError("PROJECT_READ_FAILED", f"项目配置文件无法读取：{source}（{exc}）") from exc

    def recent_project_id(self) -> str | None:
        payload = self._read_state()
        value = payload.get("recent_project_id")
        return str(value) if value else None

    def load_recent(self) -> ProjectDocument | None:
        project_id = self.recent_project_id()
        if not project_id:
            return None
        try:
            return self.load(project_id)
        except (ProjectStorageError, ProjectValidationError):
            return None
