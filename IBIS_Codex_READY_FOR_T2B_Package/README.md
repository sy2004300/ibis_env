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

## IBIS Automation UI（Phase 1.1）

UI-1.1 在 `src/ibis_ui/` 中提供 Windows/Linux Tkinter 桌面框架，并复用现有
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

ProjectStore 默认使用当前用户的可写数据目录，不依赖源码或 EXE 安装位置：

- Windows：`%LOCALAPPDATA%/IBIS_Automation/workspace/`
- Linux：`~/.local/share/IBIS_Automation/workspace/`（设置 `XDG_DATA_HOME` 时遵循该目录）

项目存储在 `projects/<project_id>/project.json`。每个项目使用 UUID 作为目录名，项目文件的
`schema_version` 当前为 `1`；写入采用同目录临时文件加原子替换。导入的 Excel 仅作为只读
来源，项目文件记录其绝对路径和 SHA-256，UI 修改只进入内部项目配置，绝不会回写原始工作簿。
启动及异常日志位于 `<workspace>/logs/ibis_automation.log`。

本阶段已实现 Import Excel、New Project 空项目入口、可搜索多模块 Case Tree、可滚动 Config
分区、Section 2 常用字段编辑、内置 T2B 母模板只读查看、MSI 多文件/多 Sheet 来源预览、
SPF MAX/TYP/MIN 匹配预览，以及 `DIRTY → Apply Changes → Save Project`、项目重载及最近项目
恢复。New Project 的完整 Schema 编辑与 Excel Export 属于 UI-2；T2B 工作模板编辑及历史库
属于 UI-3；Generate/Monitor 属于 UI-4。未实现入口均明确标记，本阶段不会执行真实 T2B、
LSF 或 `C_comp_view`。Windows 人工检查步骤见
[`docs/IBIS_UI_PHASE1_1_WINDOWS_ACCEPTANCE.md`](docs/IBIS_UI_PHASE1_1_WINDOWS_ACCEPTANCE.md)。

## Windows EXE 打包

Windows 和 Linux 使用同一套 `src/ibis_ui/` 与 `src/ibis_auto/` 源码。Windows EXE 是
PyInstaller `onedir` 产物，不存在独立的 Windows UI 实现。About 页面会显示 App Version、
Git Commit 和 Platform，可用 Commit 判断两个平台是否属于同一版本。

原生 Windows 构建由 `.github/workflows/ibis-windows-package.yml` 在 `windows-latest` 上执行。
Workflow 会运行 Windows 测试、Core Acceptance、PyInstaller 构建、打包后 EXE Headless 检查、
真实 Tk 窗口自动关闭 Smoke Test，并上传 `IBIS_Automation_Windows_UI1_1.zip` Artifact。Linux job
运行相同测试；两个平台另外输出去除本地路径后的项目 JSON，并进行逐字节一致性比较。

本地 Windows 构建命令：

```powershell
python -m pip install -r packaging/requirements-build.txt
python packaging/build_windows.py --commit <当前完整 Git SHA>
```

产物结构：

```text
dist/IBIS_Automation_Windows_UI1_1/
├── IBIS_Automation.exe
├── _internal/
└── README.txt
```

最终 ZIP 为 `dist/IBIS_Automation_Windows_UI1_1.zip`。`build/`、`dist/` 和 EXE/ZIP 产物不会提交
到 Git。软件自带只读资源位于 `_internal/resources/`；项目 Workspace 始终位于用户数据目录，
也可通过 `--workspace` 显式覆盖。若跨电脑项目的 MSI/SPF/Model Root 失效，UI 会打开项目并
提示重新指定路径，Apply 在路径修复前保持阻止状态。T2B 母模板默认由 Resource Resolver 从
源码或 EXE 内置资源加载；历史外部 Template Root 仍兼容，并可在“高级设置”中修正或清空。
