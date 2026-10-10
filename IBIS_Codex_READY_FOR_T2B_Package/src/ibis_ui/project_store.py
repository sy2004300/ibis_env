from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from uuid import UUID

from .errors import ProjectStorageError, ProjectValidationError
from .models import ProjectDocument
from .runtime import default_workspace


class ProjectStore:
    """Atomic, project-id-scoped persistence for applied project snapshots."""

    def __init__(self, workspace: Path | None = None):
        self.workspace = (workspace or default_workspace()).expanduser().resolve()
        self.projects_root = self.workspace / "projects"
        self.state_path = self.workspace / "ui_state.json"

    def ensure_ready(self) -> None:
        """Create and verify the user-writable workspace before the UI starts."""
        try:
            self.projects_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.workspace, delete=False) as stream:
                probe = Path(stream.name)
                stream.write("IBIS Automation workspace check\n")
            probe.unlink()
        except OSError as exc:
            if "probe" in locals():
                probe.unlink(missing_ok=True)
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
                temporary.unlink(missing_ok=True)
            raise ProjectStorageError("PROJECT_SAVE_FAILED", f"项目保存失败：{path}（{exc}）") from exc

    def save(self, project: ProjectDocument) -> Path:
        # Round-trip validation catches malformed documents before they replace a valid snapshot.
        validated = ProjectDocument.from_dict(project.to_dict())
        path = self.project_path(validated.project_id)
        self._atomic_json_write(path, validated.to_dict())
        self._atomic_json_write(self.state_path, {"schema_version": 1, "recent_project_id": validated.project_id})
        return path

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

    def recent_project_id(self) -> str | None:
        if not self.state_path.is_file():
            return None
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            value = payload.get("recent_project_id")
            return str(value) if value else None
        except (OSError, json.JSONDecodeError):
            return None

    def load_recent(self) -> ProjectDocument | None:
        project_id = self.recent_project_id()
        if not project_id:
            return None
        try:
            return self.load(project_id)
        except (ProjectStorageError, ProjectValidationError):
            return None
