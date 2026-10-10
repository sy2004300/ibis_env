from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path

from .controller import ProjectController
from .project_store import ProjectStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ibis-ui", description="IBIS Automation Tkinter UI（Phase 1）")
    result.add_argument("--workspace", type=Path, help="项目数据 workspace；默认位于软件目录下")
    result.add_argument("--check", action="store_true", help="仅执行无 DISPLAY 的模块/存储初始化检查")
    result.add_argument("--smoke-test", action="store_true", help="在可用 DISPLAY 上创建并自动关闭真实窗口")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = ProjectStore(args.workspace)
    controller = ProjectController(store)
    if args.check:
        print(f"IBIS UI Phase 1：模块导入与 ProjectStore 初始化成功（{store.workspace}）")
        return 0
    controller.load_recent()
    try:
        from .view import IBISApplicationView

        view = IBISApplicationView(controller, smoke_test=args.smoke_test)
    except tk.TclError as exc:
        print(f"错误 [GUI_DISPLAY_UNAVAILABLE]：无法启动 Tkinter 图形界面（{exc}）", file=sys.stderr)
        print("可使用 --check 在 Headless 环境验证数据层。", file=sys.stderr)
        return 2
    view.mainloop()
    return 0
