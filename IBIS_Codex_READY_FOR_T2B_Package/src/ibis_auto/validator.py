from __future__ import annotations

from pathlib import Path


def _canonical(text: str, model_root: Path, spf_root: Path) -> str:
    text = text.replace("\\", "/").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(str(model_root).replace("\\", "/"), "{{MODEL_ROOT}}")
    text = text.replace(str(spf_root).replace("\\", "/"), "{{SPF_ROOT}}")
    return "\n".join(line.rstrip() for line in text.split("\n")).rstrip() + "\n"


def validate_case(case: Path, golden: Path | None, model_root: Path, spf_root: Path) -> tuple[str, str]:
    required = {"_t2b_config.ini", "ckt_topology.sp", "component.sp"}
    required.update(path.name for path in case.glob("corner_*.sp"))
    required.update(path.name for path in case.glob("*.t2b"))
    if len(list(case.glob("corner_*.sp"))) != 3 or len(list(case.glob("*.t2b"))) != 1:
        return "FAIL", "Case 文件数量不完整"
    if not required <= {path.name for path in case.iterdir()} or (case / "C_comp_view").exists():
        return "FAIL", "Case 结构检查失败"
    if golden is None or not golden.is_dir():
        return "UNVALIDATED", "结构检查通过，但没有 Golden"
    for expected in golden.iterdir():
        actual = case / expected.name
        if not actual.is_file(): return "FAIL", f"Golden 文件缺失：{expected.name}"
        if _canonical(actual.read_text(errors="replace"), model_root, spf_root) != _canonical(expected.read_text(errors="replace"), model_root, spf_root):
            return "FAIL", f"Golden 不一致：{expected.name}"
    return "PASS", "Golden 比较通过"

