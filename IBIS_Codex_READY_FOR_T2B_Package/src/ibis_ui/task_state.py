"""Headless task state shared by the generator window and its regression tests."""
from __future__ import annotations

import time
from pathlib import Path


ACTIVE_STATES = {"等待中", "检查输入", "生成中"}


def output_file_count(raw_path: str) -> int:
    if not raw_path.strip():
        return 0
    path = Path(raw_path)
    if not path.is_absolute() or not path.is_dir():
        return 0
    try:
        return sum(item.is_file() for item in path.iterdir() if item.name != ".ibis_manifest.json")
    except OSError:
        return 0


class GenerationTasks:
    def __init__(self, keys):
        now = time.monotonic()
        self.rows = {
            f"{module}/{direction}/{ron}ohm": {
                "module": module, "direction": direction, "ron": ron,
                "status": "等待中", "message": "", "started": now,
                "updated": now, "elapsed": 0.0,
            }
            for module, direction, ron in keys
        }

    def update(self, key: str, status: str, message: str) -> None:
        if key not in self.rows:
            return
        row = self.rows[key]
        now = time.monotonic()
        row.update(status=status, message=message, updated=now, elapsed=now - row["started"])

    def finish(self, status: str, message: str) -> None:
        for key, row in self.rows.items():
            if row["status"] in ACTIVE_STATES:
                self.update(key, "已取消" if status == "已取消" else "FAIL", message or "任务提前结束，未收到完成结果")
