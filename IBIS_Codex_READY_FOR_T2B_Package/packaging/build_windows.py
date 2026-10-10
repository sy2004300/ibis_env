from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = PROJECT_ROOT / "build" / "windows-package"
PYINSTALLER_DIST = BUILD_ROOT / "pyinstaller-dist"
PYINSTALLER_WORK = BUILD_ROOT / "pyinstaller-work"
PACKAGE_INPUT = BUILD_ROOT / "package-input"
DIST_ROOT = PROJECT_ROOT / "dist"
OUTPUT_NAME = "IBIS_Automation_Windows_UI1"
OUTPUT_DIRECTORY = DIST_ROOT / OUTPUT_NAME
OUTPUT_ARCHIVE = DIST_ROOT / f"{OUTPUT_NAME}.zip"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build the native Windows UI-1 onedir package")
    result.add_argument("--commit", required=True, help="Git commit embedded in the EXE About page")
    return result


def _remove_build_output(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _assert_package() -> None:
    required = [
        OUTPUT_DIRECTORY / "IBIS_Automation.exe",
        OUTPUT_DIRECTORY / "_internal",
        OUTPUT_DIRECTORY / "README.txt",
        OUTPUT_DIRECTORY / "_internal" / "resources" / "build_info.json",
        OUTPUT_DIRECTORY / "_internal" / "resources" / "inputs" / "config" / "ibis_config.xlsx",
    ]
    required.extend(
        OUTPUT_DIRECTORY / "_internal" / "resources" / "templates" / "t2b" / filename
        for filename in ("_t2b_config.ini", "drv_se.t2b", "drv_diff.t2b", "rcv_se.t2b", "rcv_diff.t2b")
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Windows 打包资源缺失：" + "、".join(str(path) for path in missing))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if os.name != "nt":
        print("错误：Windows EXE 必须在 Windows 原生环境构建，禁止使用普通 Linux PyInstaller 冒充。", file=sys.stderr)
        return 2

    commit = args.commit.strip()
    if not commit:
        print("错误：Git Commit 不能为空。", file=sys.stderr)
        return 2

    _remove_build_output(BUILD_ROOT)
    _remove_build_output(OUTPUT_DIRECTORY)
    OUTPUT_ARCHIVE.unlink(missing_ok=True)
    PACKAGE_INPUT.mkdir(parents=True, exist_ok=True)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)

    build_info = PACKAGE_INPUT / "build_info.json"
    build_info.write_text(
        json.dumps({"app_version": "0.1.0-ui1", "git_commit": commit}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["IBIS_BUILD_INFO_FILE"] = str(build_info)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(PYINSTALLER_DIST),
            "--workpath",
            str(PYINSTALLER_WORK),
            str(PROJECT_ROOT / "packaging" / "IBIS_Automation.spec"),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )

    shutil.copytree(PYINSTALLER_DIST / "IBIS_Automation", OUTPUT_DIRECTORY)
    shutil.copy2(PROJECT_ROOT / "packaging" / "WINDOWS_README.txt", OUTPUT_DIRECTORY / "README.txt")
    _assert_package()
    shutil.make_archive(str(DIST_ROOT / OUTPUT_NAME), "zip", root_dir=DIST_ROOT, base_dir=OUTPUT_NAME)
    if not OUTPUT_ARCHIVE.is_file() or OUTPUT_ARCHIVE.stat().st_size == 0:
        raise RuntimeError(f"Windows ZIP 未生成：{OUTPUT_ARCHIVE}")
    print(f"Windows package: {OUTPUT_DIRECTORY}")
    print(f"Windows archive: {OUTPUT_ARCHIVE} ({OUTPUT_ARCHIVE.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
