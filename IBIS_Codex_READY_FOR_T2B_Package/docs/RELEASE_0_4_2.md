# IBIS Automation 0.4.2 验收版

基于 `codex/ibis-ui-0-4-1` 的 `b73c6ae`，开发分支 `codex/ibis-ui-0-4-2`。
保留项目 UUID、Schema 2 和原始 Config / MSI 只读约束，未修改 Core 生成规则、冻结输入、母模板或 Golden。
本版本等待人工验收，不自动合并 main。任务原文见 `UI_0_4_2_TASK.md`。

## 配置编辑与保存

- 第 4 节：原位逐行编辑 SPICE Option，保留文本和顺序；用目标行号调整顺序。
- 第 5 节：原位编辑模块、方向、原始引脚、别名；检查空值、重叠作用域重复别名与可确认的 SPF 引脚引用。
- 第 6 节：原位多行正文编辑，保留换行；显示适用模块/方向、有效节点、最终追加正文。确定的重复实例报错；扩展语法和无法确认的内部节点只警告。
- 第 7 节：模板类型、来源和实际路径直接展示。支持内置、外部和现有项目自定义模板；与 T2B 填参预览使用同一个解析器。
- 第 8 节：信号值覆盖的模块/方向/工艺角/信号/值直接编辑，显示原始默认值及该作用域有效值；沿用 Core 冲突校验并检查信号引用和位宽。
- 第 9 节：仅支持 POWER_DOMAIN，显示原始、覆盖和有效供电域。
- 第 10 节：展示自动候选或显式映射；可直接选择工作簿、工作表及引脚名称列，支持多工作簿/多工作表。
- 所有编辑进入草稿；模板编辑器的“保存模板”也先进入草稿，最后用顶部“保存项目”统一保存。
- 保存前对比磁盘中的最后成功版本，包含新增/删除、模块/方向/工艺角和多行正文差异。确认后原子保存；返回修改或取消不丢草稿。
- 离开项目、导入、打开、新建、退出继续使用保存/放弃/取消保护。无修改时不弹空白差异窗口。

## MSI Master 单一数据链路

原始 MSI → 原始工作簿/工作表映射 → 有效 Master → 构建检查 → Generator 读取生成输入快照 → Case 检查 → 保存追溯记录。

1. 生成前自动扫描、解析并检查每个模块的唯一来源。缺失工作表、列、重复信号、无效位宽、冲突属性或无效信号引用会阻止生成。
2. POWER_DOMAIN 覆盖写入有效 Master 的语义列；原始值可从来源及原始 Hash 追溯。
3. 按方向/工艺角生效的信号覆盖保留在 `_Case_Overrides` 工作表，由同一个 Core 在对应 Case 应用，不改全局默认值。
4. 来源路径、工作表、列、Hash 及有效工作表映射记录在 `_Source_Info` 和 `source_manifest.json`；属性覆盖单独记录。
5. 相同输入复用已有快照。输入或映射变化会构建新版本，旧版本保留。
6. Generator 的 MSI Root 指向输出目录中的 Master 快照；测试捕获实际传入 Core 的配置并验证路径和 Hash，避免“生成后另建一份检查表”。
7. 每个 Case 的独立版本 Manifest 记录实际 Master 路径/Hash、模板快照、原始输入 Hash、项目配置和有效配置快照、输出文件 Hash、检查结果。
8. 失败和取消不会把旧输出重新标成这次成功；前次成功 Manifest 和文件保留。无 Golden 的 Case 保持 UNVALIDATED。

目录示例：

```text
项目目录/
  project.json
  msi/versions/<输入指纹>/MSI_Master.xlsx
  msi/manual_backups/<人工版本Hash>/MSI_Master.xlsx
  manifests/<模块>__<方向>__<Ron>_<时间>.json
  generated/
    _inputs/<Master文件Hash>/MSI_Master.xlsx
    _inputs/<Master文件Hash>/source_manifest.json
    _inputs/templates/<模板Hash>/<模板文件>
    <模块>/<方向>/<Ron>ohm_ibis/  # 原有七文件结构保持不变
```

Master 放在带 Hash 的目录以保留多次生成记录，避免根目录“最新 Master”覆盖旧 Case 的依据。

## 人工修改边界

本版不支持将任意手工编辑的 Master 当作可信输入自动合并。检测到人工编辑会阻止生成并展示差异。
用户可在“预览有效 MSI”查看版本和差异，明确确认后备份人工文件、恢复可追溯自动版本。
正式供电域调整应通过第 9 节保存；Case 信号覆盖通过第 8 节保存。原始 MSI 始终不回写。
旧版手动合并项目的来源记录可恢复为原始映射；缺失追溯记录时要求重新指定，不猜测、不回退旧数据。

## 自动化验证

本地实际执行：

```bash
DISPLAY=:91 PYTHONPATH=src python -m unittest discover -s tests -v
python tests/run_acceptance.py
PYTHONPATH=src python -m ibis_ui --check --workspace /tmp/ibis-042-check
DISPLAY=:91 PYTHONPATH=src python -m ibis_ui --smoke-test --workspace /tmp/ibis-042-smoke
```

- 164 项测试 PASS，包括新增 19 项数据层/集成测试和 7 项 GUI 测试。
- 共 11 项真实 Tk GUI 测试 PASS（Linux Xvfb）；Headless 与 GUI 结果分别记录。
- Unit / Template / Robustness、Structural、Golden Case 001、Acceptance、READY_FOR_T2B PASS。
- `--check` 验证填参预览与实际输出相同，以及输出 Master 的真实路径/Hash。
- 新测试覆盖原位增删编辑、SPICE 顺序和正文保真、别名/信号覆盖校验、单/多工作簿及工作表、属性与 Case 覆盖区分、自动构建、变化失效、人工保护、旧项目迁移、实际 DRV/RCV 生成、取消和失败不破坏旧数据、外部模板同步、输出篡改检测。
- GUI 测试实际创建窗口、编辑控件、操作保存差异窗口、切换页面、搜索筛选 Master、启动生成，不以模块导入替代。

GitHub Actions 在同一提交运行 Windows 原生测试、PyInstaller onedir、EXE `--check`、真实窗口 Smoke Test、Linux 回归及跨平台数据比较。跨平台比较含有效 Master 工作表语义和来源标识，排除本地路径和时间等环境差异。最终构建状态和产物下载链接在 PR / 交付消息提供。

## 主要变更文件

| 文件 | 目的 |
| --- | --- |
| `src/ibis_ui/effective_msi.py` | 有效 MSI 解析、校验、版本构建、人工保护及输出快照 |
| `src/ibis_ui/configuration_review.py` | 保存差异、引脚和保守 SPICE 检查 |
| `src/ibis_ui/inline_sections.py` | 第 4～10 节原位编辑 |
| `src/ibis_ui/review_dialogs.py` | 保存差异窗口和结构化 Master 预览 |
| `controller.py` | 草稿校验、模板来源、Master 查询和准备接口 |
| `generation_service.py` | 正式使用 Master 输入、模板快照、版本 Manifest 与文件检查 |
| `view.py`, `template_panel.py`, `editor_dialogs.py` | UI 接入、中文提示及统一保存流程 |
| `working_templates.py` | 内置/外部/自定义来源统一解析 |
| `app.py`, `runtime.py`, `ui_text.py`, `pyproject.toml` | 安装自检与 0.4.2 版本信息 |
| `tests/test_ui_042.py`, `tests/test_ui_042_gui.py` | 数据链路、异常、真实 GUI 回归 |
| `tests/test_ui_041_gui.py` | 更新统一草稿保存交互的原有 GUI 回归 |
| `tests/test_ui_phase1_*.py` | 更新版本与产物名称断言，保留原业务测试 |
| `packaging/*`, `.github/workflows/ibis-windows-package.yml` | 原生 Windows 包和跨平台 Master 语义比较 |

## 运行与验收边界

Windows 完整解压 `IBIS_Automation_Windows_0_4_2.zip` 后双击 `IBIS_Automation.exe`，保留 `_internal`。
Linux 在项目包目录运行 `PYTHONPATH=src python3 -m ibis_ui`。两者共用源码。

仍需用户在本地 Windows 验收显示缩放、字体、实际工程文件及工作流程；CI 窗口测试不等于人工视觉验收。
SPICE 检查不是完整解析器，不替代仿真器语法校验。本版未运行真实 T2B、LSF，也不生成 `.ibs` 或 `C_comp_view`。
