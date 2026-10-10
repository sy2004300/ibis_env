# IBIS Codex READY_FOR_T2B Package

这是用于让 Codex **从零实现 IBIS READY_FOR_T2B 自动化生成器，并自行运行验收、迭代修复** 的冻结输入包。

## 当前边界

本包覆盖：

`环境初始化 → MSI/SPF/Config 解析 → Canonical Model → Case 展开 → 文件生成 → 结构检查 → READY_FOR_T2B`

暂不覆盖：

- 真正启动 T2B
- LSF/bsub 调度
- `C_comp_view` / `.ibs` 运行后结果
- ANA/IBIS 仿真校验

## Codex 最先阅读

1. `MASTER_PROMPT.md`
2. `AGENTS.md`
3. `SPEC.md`
4. `ACCEPTANCE_TESTS.md`
5. `PROJECT_STATUS.md`

## 核心输入

- `inputs/config/ibis_config.xlsx`：最终版 Config Schema + Demo Case
- `inputs/msi/demo_msi.xlsx`：Synthetic MSI，多 Sheet，可测试 MSI Catalog
- `inputs/spf/*.spf`：三套最小合法 synthetic SPF
- `inputs/models/`：仅用于文件存在性 precheck 的 synthetic model placeholders
- `templates/t2b/`：四套固定入口 T2B template + 全局 `_t2b_config.ini`

## Golden

当前只有一套已确认 Golden：

`golden/demo_phy_io_diff/drv/30ohm_ibis/`

对应：`demo_phy_io_diff + DRV + DIFF + 30Ω + MAX/TYP/MIN`。

其它模板/Case 当前应标记 `UNVALIDATED`，不是错误。

## 重要约束

Codex 可以创建/修改实现代码，但不得为了让测试通过而修改：

- `SPEC.md`
- `ACCEPTANCE_TESTS.md`
- `golden/`
- `inputs/`
- `templates/t2b/`

若发现这些冻结输入之间存在矛盾，应输出 `SPEC_CONFLICT`，而不是擅自修改标准答案。

## IBIS Automation UI（Phase 1）

UI-1 在 `src/ibis_ui/` 中提供 Linux Tkinter 桌面框架，并复用现有
`ibis_auto.config.parse_config` 解析 Config Excel。项目状态由相互独立的
Model、Controller、View 管理，Headless 测试不会创建 Tk 窗口。

启动图形界面：

```bash
PYTHONPATH=src python -m ibis_ui
```

在没有 `DISPLAY` 的环境检查模块和项目存储初始化：

```bash
PYTHONPATH=src python -m ibis_ui --check
```

ProjectStore 默认使用 `workspace/projects/<project_id>/project.json`。每个项目使用
UUID 作为目录名，项目文件的 `schema_version` 当前为 `1`；写入采用同目录临时文件
加原子替换。导入的 Excel 仅作为只读来源，项目文件记录其绝对路径和 SHA-256，
UI 修改只进入内部项目配置，绝不会回写原始工作簿。

本阶段已实现 Import Excel、New Project 空项目入口、Case Tree、Section 2 常用字段编辑、
`DIRTY → Apply Changes → Save Project`、项目重载及最近项目恢复。New Project 的完整
Schema 编辑与 Excel Export 属于 UI-2，T2B Library 属于 UI-3，Generate、Files、Monitor
属于 UI-4；界面中的对应入口均明确标记并禁用，本阶段不会执行真实 T2B、LSF 或
`C_comp_view`。
