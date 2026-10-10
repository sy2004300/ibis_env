# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path


project_root = Path(SPECPATH).resolve().parent
build_info = Path(os.environ["IBIS_BUILD_INFO_FILE"]).resolve()

datas = [
    (str(project_root / "templates" / "t2b"), "resources/templates/t2b"),
    (str(project_root / "inputs"), "resources/inputs"),
    (str(build_info), "resources"),
]

analysis = Analysis(
    [str(project_root / "packaging" / "ibis_automation_entry.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="IBIS_Automation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="IBIS_Automation",
)
