# UI Phase 1.2 阶段测试报告

本报告记录 UI-1.2 分支的本地 Linux 验证基线。Windows 原生结果由同一 Commit 的 GitHub Actions 补充，不能用 Headless 结果替代 GUI Smoke 或人工视觉验收。

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
| Windows EXE Build | 等待 CI | 必须由 `windows-latest` 原生构建 |
| Windows EXE Headless | 等待 CI | 必须对打包后的 EXE 执行 `--check` |
| GUI Smoke Test | 等待 CI | 实际 Tk 窗口自动测试；不等于人工视觉验收 |
| Windows/Linux Compatibility | 等待 CI | 路径中立 Project JSON 逐字节比较 |
| Future Features | PENDING | MSI Merge/Excel 写回（UI-2）、T2B 工作模板/Library（UI-3）、生成/监控（UI-4） |

## 保护检查

以下冻结材料在 UI-1.2 中没有修改：`SPEC.md`、`ACCEPTANCE_TESTS.md`、`PROJECT_STATUS.md`、`inputs/`、`golden/`、`templates/t2b/`、`tests/test_vectors.json`、`tests/run_acceptance.py`。

## Windows 待补证据

分支推送后，Workflow 必须全部完成：Linux source tests、Windows native build and tests、打包 EXE Headless、真实 Tk Window Smoke、Windows/Linux compatibility。最终 Artifact 必须命名为 `IBIS_Automation_Windows_UI1_2` 并包含 EXE、`_internal/`、README、内置模板和 Demo 输入。
