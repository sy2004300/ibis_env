from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
from pathlib import Path
from typing import Any

from .controller import ProjectController
from .errors import ResourceError, UIProjectError
from .excel_importer import ExcelImporter
from .logging_utils import close_file_logging, configure_file_logging, logger
from .project_store import ProjectStore
from .runtime import ResourceResolver, app_metadata


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ibis-ui", description="IBIS Automation Tkinter UI（Phase 1）")
    result.add_argument("--workspace", type=Path, help="项目数据 Workspace；默认使用当前系统的用户数据目录")
    result.add_argument("--check", action="store_true", help="执行不创建窗口的安装、资源和 Config 初始化检查")
    result.add_argument("--check-report", type=Path, help="将 --check 结果写入 JSON，供打包验收使用")
    result.add_argument("--smoke-test", action="store_true", help="创建真实 Tk 窗口并自动关闭，用于 GUI 冒烟测试")
    return result


def _write_report(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _console_write(message: str, error: bool = False) -> None:
    """Write only when a console stream exists (PyInstaller windowed sets it to None)."""
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        try:
            print(message, file=stream)
        except (OSError, UnicodeError):
            return


def headless_check(store: ProjectStore, resolver: ResourceResolver) -> dict[str, Any]:
    """Exercise packaged resources and data services without creating a Tk root."""
    store.ensure_ready()
    resolver.validate()
    project = ExcelImporter().import_project(resolver.demo_config, "Bundled Demo Check")
    invalid_roots = {
        name: value
        for name, value in project.config["roots"].items()
        if not Path(str(value)).is_dir()
    }
    if invalid_roots:
        detail = "、".join(f"{name}={value}" for name, value in invalid_roots.items())
        raise ResourceError("BUNDLED_DEMO_ROOT_INVALID", f"内置 Demo 的资源路径无效：{detail}")
    metadata = app_metadata()
    return {
        "status": "PASS",
        "mode": "HEADLESS",
        "gui_window_created": False,
        "app_version": metadata.version,
        "git_commit": metadata.git_commit,
        "platform": metadata.platform,
        "frozen": metadata.frozen,
        "workspace": str(store.workspace),
        "resource_root": str(resolver.root),
        "template_files": sorted(path.name for path in resolver.template_root.iterdir() if path.is_file()),
        "demo_modules": [module["name"] for module in project.config["modules"]],
        "project_schema_version": project.schema_version,
    }


def _show_startup_error(message: str) -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        from tkinter import messagebox

        messagebox.showerror("IBIS Automation 启动失败", message, parent=root)
        root.destroy()
    except Exception:
        return


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = ProjectStore(args.workspace)
    resolver = ResourceResolver.current()
    log_path: Path | None = None
    try:
        store.ensure_ready()
        log_path = configure_file_logging(store.workspace)
        metadata = app_metadata()
        logger().info(
            "启动 %s；commit=%s；platform=%s；frozen=%s；workspace=%s",
            metadata.version,
            metadata.git_commit,
            metadata.platform,
            metadata.frozen,
            store.workspace,
        )
        if args.check:
            report = headless_check(store, resolver)
            _write_report(args.check_report, report)
            message = f"IBIS Automation Headless 检查通过（Workspace：{store.workspace}）"
            logger().info(message)
            _console_write(message)
            return 0

        resolver.validate()
        controller = ProjectController(store)
        controller.load_recent()
        from .view import IBISApplicationView

        view = IBISApplicationView(controller, smoke_test=args.smoke_test)
        view.mainloop()
        logger().info("IBIS Automation 正常退出")
        return 0
    except tk.TclError as exc:
        message = f"错误 [GUI_DISPLAY_UNAVAILABLE]：无法启动 Tkinter 图形界面（{exc}）"
        if log_path:
            logger().exception(message)
        _console_write(message, error=True)
        _console_write("可使用 --check 在 Headless 环境验证数据层。", error=True)
        _write_report(args.check_report, {"status": "FAIL", "code": "GUI_DISPLAY_UNAVAILABLE", "message": message})
        return 2
    except UIProjectError as exc:
        message = f"错误 [{exc.code}]：{exc}"
        if log_path:
            logger().exception(message)
        _console_write(message, error=True)
        _write_report(args.check_report, {"status": "FAIL", "code": exc.code, "message": str(exc)})
        if not args.check:
            _show_startup_error(f"{message}\n\n日志：{log_path or '无法创建日志'}")
        return 2
    except Exception as exc:  # pragma: no cover - last-resort packaged startup protection
        message = f"错误 [UNEXPECTED_STARTUP_ERROR]：软件启动异常（{exc}）"
        if log_path:
            logger().exception(message)
        _console_write(message, error=True)
        _write_report(args.check_report, {"status": "FAIL", "code": "UNEXPECTED_STARTUP_ERROR", "message": str(exc)})
        if not args.check:
            _show_startup_error(f"{message}\n\n日志：{log_path or '无法创建日志'}")
        return 3
    finally:
        if log_path:
            close_file_logging(log_path)
