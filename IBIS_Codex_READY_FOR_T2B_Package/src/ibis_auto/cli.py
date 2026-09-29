from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import IbisError
from .service import generate


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ibis_auto", description="IBIS READY_FOR_T2B 自动生成器")
    commands = root.add_subparsers(dest="command", required=True)
    command = commands.add_parser("generate", help="生成 READY_FOR_T2B Case")
    command.add_argument("--config", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--non-interactive", action="store_true")
    for option in ("model", "msi", "spf", "template"):
        command.add_argument(f"--{option}-root", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    overrides = {name: getattr(args, f"{name}_root").resolve() for name in ("model", "msi", "spf", "template") if getattr(args, f"{name}_root")}
    try:
        result = generate(args.config, args.output.resolve(), overrides, args.non_interactive)
    except IbisError as exc:
        print(f"项目错误 [{exc.code}]：{exc}", file=sys.stderr)
        print("项目状态：FAIL", file=sys.stderr)
        return 2
    for case in result.cases:
        suffix = f" — {case.message}" if case.message else ""
        print(f"Case {case.key}：{case.status}{suffix}")
    print(f"项目状态：{'READY_FOR_T2B' if result.ready else 'FAIL'}")
    return 0 if result.ready else 1

