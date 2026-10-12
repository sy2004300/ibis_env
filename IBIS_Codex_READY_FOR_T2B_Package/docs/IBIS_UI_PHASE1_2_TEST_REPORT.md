# UI Phase 1.2 阶段测试报告

本报告记录 UI-1.2 分支的 Linux 与 Windows 自动验证。Windows Headless 和 GUI Smoke 是不同检查；自动 GUI Smoke 不能替代人工视觉验收。

| 项目 | 结果 | 证据 |
|---|---|---|
| Unit / Template / Robustness / UI | PASS | `python -m unittest discover -s tests -p "test_*.py" -v`，95 tests |
| UI-1.2 新增测试 | PASS | 13 tests：一键保存、回滚、最近项目、MSI/SPF/Model、首页状态、中文状态和打包契约 |
| MSI/SPF Tests | PASS | 多 Excel、多 Sheet、自动匹配、歧义、Corner 缺失、重复、Pin List 不一致 |
| Core Acceptance | PASS | `python tests/run_acceptance.py` |
| Structural Check | PASS | Acceptance 实际输出 |
| Golden Case 001 | PASS | Golden 比较通过 |
| READY_FOR_T2B | PASS | Acceptance 最终状态 |
| Linux Headless | PASS | 版本 0.1.2、内置模板、Demo Config/MSI/SPF 初始化 |
| Windows EXE Build | PASS | GitHub Actions `windows-latest` 原生 PyInstaller onedir 构建 |
| Windows EXE Headless | PASS | 打包后的 EXE 执行 `--check`，资源和 Commit 校验通过 |
| GUI Smoke Test | PASS | 实际创建 Tk 窗口并验证首页、中文导航、滚动、模板和 MSI/SPF/Model 预览后自动关闭；不是人工视觉验收 |
| Windows/Linux Compatibility | PASS | 路径中立 Project JSON 逐字节一致 |
| Future Features | PENDING | MSI Merge/Excel 写回（UI-2）、T2B 工作模板/Library（UI-3）、生成/监控（UI-4） |

## 保护检查

以下冻结材料在 UI-1.2 中没有修改：`SPEC.md`、`ACCEPTANCE_TESTS.md`、`PROJECT_STATUS.md`、`inputs/`、`golden/`、`templates/t2b/`、`tests/test_vectors.json`、`tests/run_acceptance.py`。

## Windows 构建证据

GitHub Actions Run `38226479569` 已完成 Linux source tests、Windows native build and tests、打包 EXE Headless、真实 Tk Window Smoke 和 Windows/Linux compatibility。Artifact `IBIS_Automation_Windows_UI1_2`（ID `11736728074`，12.2 MB）包含 EXE、`_internal/`、README、内置模板和 Demo 输入；SHA-256 digest 为 `9f72c2631186c0cedaa985ce7cf46a555fe2c2dd03dd94156823718945a92445`。
