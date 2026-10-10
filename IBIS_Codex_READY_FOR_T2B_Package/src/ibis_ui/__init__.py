"""IBIS Automation Tkinter UI and headless project services."""

from .controller import ProjectController
from .project_store import ProjectStore
from .runtime import APP_VERSION

__all__ = ["APP_VERSION", "ProjectController", "ProjectStore"]
__version__ = APP_VERSION
