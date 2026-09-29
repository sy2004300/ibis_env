#!/usr/bin/env python3
from __future__ import annotations
import argparse, difflib, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "generated" / "demo_phy_io_diff" / "drv" / "30ohm_ibis"
GOLD = ROOT / "golden" / "demo_phy_io_diff" / "drv" / "30ohm_ibis"
MODEL_ROOT = (ROOT / "inputs" / "models").resolve()
SPF_ROOT = (ROOT / "inputs" / "spf").resolve()

FILES = [
    "_t2b_config.ini", "ckt_topology.sp", "component.sp",
    "corner_drv_ron30_max.sp", "corner_drv_ron30_typ.sp", "corner_drv_ron30_min.sp",
    "demo_phy_io_diff_drv_ron30.t2b",
]

def canon(s: str) -> str:
    s = s.replace("\\", "/").replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace(str(MODEL_ROOT).replace("\\", "/"), "{{MODEL_ROOT}}")
    s = s.replace(str(SPF_ROOT).replace("\\", "/"), "{{SPF_ROOT}}")
    return "\n".join(line.rstrip() for line in s.split("\n")).rstrip() + "\n"

def fixture_check() -> list[str]:
    errs=[]
    must = [
        ROOT/"SPEC.md", ROOT/"ACCEPTANCE_TESTS.md", ROOT/"inputs"/"config"/"ibis_config.xlsx",
        ROOT/"inputs"/"msi"/"demo_msi.xlsx",
        ROOT/"templates"/"t2b"/"drv_diff.t2b", ROOT/"templates"/"t2b"/"_t2b_config.ini",
    ]
    for p in must:
        if not p.exists(): errs.append(f"冻结输入缺失：{p.relative_to(ROOT)}")
    for name in ["demo_phy_io_diff.rcbest.spf","demo_phy_io_diff.typical.spf","demo_phy_io_diff.rcworst.spf"]:
        if not (SPF_ROOT/name).exists(): errs.append(f"SPF fixture 缺失：{name}")
    return errs

def run_generator() -> int:
    if (ROOT/"generated").exists():
        shutil.rmtree(ROOT/"generated")
    (ROOT/"generated").mkdir()
    env=os.environ.copy()
    env["PYTHONPATH"] = str(ROOT/"src") + os.pathsep + env.get("PYTHONPATH","")
    cmd=[sys.executable,"-m","ibis_auto","generate",
         "--config",str(ROOT/"inputs"/"config"/"ibis_config.xlsx"),
         "--output",str(ROOT/"generated"),"--non-interactive"]
    print("执行：", " ".join(cmd))
    return subprocess.call(cmd,cwd=ROOT,env=env)

def structural_check() -> list[str]:
    errs=[]
    for f in FILES:
        if not (GEN/f).exists(): errs.append(f"生成文件缺失：{f}")
    if (GEN/"C_comp_view").exists(): errs.append("READY_FOR_T2B 阶段不应生成 C_comp_view")
    if errs: return errs
    typ=(GEN/"corner_drv_ron30_typ.sp").read_text(errors="replace")
    for sig in ["reg_txslice_pd[3]","reg_txslice_pd[2]","reg_txslice_pd[1]","reg_txslice_pd[0]",
                "reg_txslice_pu[3]","reg_txslice_pu[2]","reg_txslice_pu[1]","reg_txslice_pu[0]"]:
        if sig not in typ: errs.append(f"30Ω 控制 bit 缺失：{sig}")
    for sig in ["txzqcal_pd[7]","txzqcal_pd[0]","txzqcal_pu[7]","txzqcal_pu[0]"]:
        if sig not in typ: errs.append(f"Calibration 展开不完整：{sig}")
    if "ipadt 0 dc" in typ or "ipadc 0 dc" in typ:
        errs.append("PAD ipadt/ipadc 不应生成 local voltage source")
    return errs

def golden_check() -> list[str]:
    errs=[]
    for f in FILES:
        gp, ep = GEN/f, GOLD/f
        if not gp.exists() or not ep.exists(): continue
        a=canon(ep.read_text(errors="replace")); b=canon(gp.read_text(errors="replace"))
        if a != b:
            diff="".join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile=f"golden/{f}",tofile=f"generated/{f}"))
            errs.append(f"Golden 不一致：{f}\n{diff[:5000]}")
    return errs

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--fixture-only",action="store_true")
    args=ap.parse_args()
    errs=fixture_check()
    if errs:
        print("FIXTURE FAIL")
        print("\n".join("- "+e for e in errs)); return 2
    print("FIXTURE CHECK：PASS")
    if args.fixture_only: return 0
    rc=run_generator()
    if rc != 0:
        print(f"GENERATOR FAIL：退出码 {rc}"); return rc or 3
    errs=structural_check()
    if errs:
        print("STRUCTURAL FAIL")
        print("\n".join("- "+e for e in errs)); return 4
    print("STRUCTURAL CHECK：PASS")
    errs=golden_check()
    if errs:
        print("GOLDEN FAIL")
        print("\n\n".join(errs)); return 5
    print("GOLDEN CASE 001：PASS")
    print("FINAL：READY_FOR_T2B")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
