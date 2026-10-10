from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from .errors import ResourceError


APP_NAME = "IBIS Automation"
APP_VERSION = "0.1.0-ui1"
APP_DATA_DIRECTORY = "IBIS_Automation"
REQUIRED_TEMPLATES = (
    "_t2b_config.ini",
    "drv_se.t2b",
    "drv_diff.t2b",
    "rcv_se.t2b",
    "rcv_diff.t2b",
)


def default_workspace(
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return a per-user writable workspace without relying on the install directory."""
    system_name = system or platform.system()
    variables = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    if system_name == "Windows":
        local_app_data = variables.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else user_home / "AppData" / "Local"
    elif system_name == "Darwin":
        base = user_home / "Library" / "Application Support"
    else:
        xdg_data_home = variables.get("XDG_DATA_HOME")
        base = Path(xdg_data_home).expanduser() if xdg_data_home else user_home / ".local" / "share"
    return base / APP_DATA_DIRECTORY / "workspace"


def _source_package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Locate immutable bundled resources in source and PyInstaller executions."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve() / "resources"
    return _source_package_root()


@dataclass(frozen=True)
class ResourceResolver:
    root: Path

    @classmethod
    def current(cls) -> ResourceResolver:
        return cls(resource_root())

    @property
    def template_root(self) -> Path:
        return self.root / "templates" / "t2b"

    @property
    def demo_config(self) -> Path:
        return self.root / "inputs" / "config" / "ibis_config.xlsx"

    @property
    def demo_inputs_root(self) -> Path:
        return self.root / "inputs"

    @property
    def build_info_path(self) -> Path:
        return self.root / "build_info.json"

    def missing_required_files(self) -> list[Path]:
        required = [self.template_root / name for name in REQUIRED_TEMPLATES]
        required.append(self.demo_config)
        return [path for path in required if not path.is_file()]

    def validate(self) -> None:
        missing = self.missing_required_files()
        if missing:
            names = "、".join(str(path) for path in missing)
            raise ResourceError("RESOURCE_MISSING", f"软件资源不完整，请重新下载或解压安装包：{names}")


def _bundled_commit(resolver: ResourceResolver) -> str | None:
    try:
        payload = json.loads(resolver.build_info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = str(payload.get("git_commit", "")).strip()
    return value or None


def _source_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_source_package_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


@dataclass(frozen=True)
class AppMetadata:
    version: str
    git_commit: str
    platform: str
    frozen: bool

    @property
    def short_commit(self) -> str:
        return self.git_commit[:12] if self.git_commit != "unknown" else self.git_commit


@lru_cache(maxsize=1)
def app_metadata() -> AppMetadata:
    resolver = ResourceResolver.current()
    frozen = bool(getattr(sys, "frozen", False))
    environment_commit = os.environ.get("IBIS_BUILD_COMMIT", "").strip()
    if frozen:
        commit = _bundled_commit(resolver) or environment_commit or "unknown"
    else:
        commit = environment_commit or _source_commit() or "unknown"
    return AppMetadata(
        version=APP_VERSION,
        git_commit=commit,
        platform=platform.system() or sys.platform,
        frozen=frozen,
    )
