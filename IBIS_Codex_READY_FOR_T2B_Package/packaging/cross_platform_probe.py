from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibis_ui.excel_importer import ExcelImporter  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Write a path-neutral UI project snapshot")
    result.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    source = PROJECT_ROOT / "inputs" / "config" / "ibis_config.xlsx"
    project = ExcelImporter().import_project(source, "Cross Platform Probe")
    config = copy.deepcopy(project.config)
    config["roots"] = {name: f"<{name.upper()}_ROOT>" for name in sorted(config["roots"])}
    payload = {
        "project_schema_version": project.schema_version,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "config": config,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
