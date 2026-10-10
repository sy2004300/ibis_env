# IBIS Automation — UI SPEC V1.0

> 状态：需求基线 / 待 UI 实现；日期：2026-10-10  
> 仓库：`sy2004300/ibis_env` · `main`  
> 代码根目录：`IBIS_Codex_READY_FOR_T2B_Package/`  
> 本文汇总已确认的产品需求；带“实现建议”的技术细节是推荐方案，而非已实现功能。

## 0. 产品定位与边界

目标是一个 **Linux 可运行的 Python Tkinter 桌面应用**，为 IBIS READY_FOR_T2B 生成器提供：项目配置管理、Excel 双向导入导出、T2B 独立编辑及历史模板版本库、Case 选择生成、文件预览、状态监控及中文错误定位。UI 应以减少工程师重复填写为目标。

**当前可执行工作边界**：配置读取/校验 → MSI/SPF 发现 → Canonical Model → Case Matrix → `_t2b_config.ini`、`component.sp`、`ckt_topology.sp`、三角 `corner_*.sp`、`.t2b` → 结构/Golden 检查 → READY_FOR_T2B。

**未来扩展，不在 UI V1.0 完成范围**：启动真实 T2B、LSF/bsub、C_comp_view、ANA/IBIS 眼图/脉冲/SNR 验证、IBIS merge、Word/PDF。界面不得将 READY_FOR_T2B 标记为“已完成仿真”。

**现存系统基线（2026-10-10 查看 main）**：
- `src/ibis_auto/config.py::parse_config(path, root_overrides)`：读取既有 `.xlsx` 并生成 `Config` 对象。
- `src/ibis_auto/ooxml.py::read_workbook()`：只读 OOXML，尚无 Excel 导出/写回。
- `src/ibis_auto/service.py::generate(config_path, output, root_overrides, non_interactive)`：仍以 Excel 文件路径为调用入口，返回 `GenerationResult`；不提供逐 Case 进度回调。
- `src/ibis_auto/generator.py`：模板当前通过 `config.roots['template'] / f'{template_type}.t2b'` 读取，动态令牌使用 `{{TOP_SUBCKT}}`、`{{RON}}` 等；不得让 UI 另写一份渲染规则。
- `src/ibis_auto/model.py`：已有 `Config / ModulePlan / Corner / Signal` 等对象。
- `templates/t2b/`：四份母模板和 `_t2b_config.ini`。
- 当前只有 `demo_phy_io_diff / DRV / DIFF / 30Ω` 一组 Reference Golden。

**冻结资产保护**：遵守仓库 `AGENTS.md`，未经明确授权不得修改 `SPEC.md`、`ACCEPTANCE_TESTS.md`、`PROJECT_STATUS.md`、`inputs/**`、`golden/**`、`templates/t2b/**`、`tests/test_vectors.json`、`tests/run_acceptance.py`。不能通过更改 Golden/原始输入制造测试 PASS。

## 1. 统一数据原则

### 1.1 两种配置模式

- **Excel Mode**：导入已有 `ibis_config.xlsx`，映射到 UI 内部项目配置，编辑/校验后保存项目、导出 Excel 或直接 Generate。
- **UI Mode**：无 Excel 时，从空项目或历史项目模板包创建，在 UI 中填入全部必需参数；支持导出一份标准 Config Excel，也支持直接 Generate。
- 两种模式进入相同的主界面，使用同一配置 Schema、验证器、Case Generator。
- 任何模式下都不要求先导出 Excel 才能 Generate。V1 可在临时隔离目录中生成合法的临时 `.xlsx` 作为现有 Core 的适配输入；用户不应感知或手工维护临时文件。后续可重构出 `generate_from_config`，但必须保留现有 CLI/Golden 的输出语义。

### 1.2 单一生效数据源

- **当前项目内部配置**是该次 Generate 的唯一生效数据源。
- Excel 是可选的输入/输出载体；历史模板库是复制初始化来源；都不得隐式覆盖已确认的内部配置。
- 所有修改先进入内存草稿，标记 `DIRTY`。点击 **Apply Changes** 执行模型校验，成功后更新当前项目的生效快照；**Save Project** 将生效快照持久化至软件 workspace。
- 存在尚未 Apply 的草稿时，Generate 必须阻止或要求先 Apply / 明确舍弃草稿；不得悄悄使用旧配置。
- 关闭界面、切换项目、再次 Import 时，如有草稿必须提示保存/丢弃/取消。`Save Project` 不应绕过验证；需要保留未通过验证的编辑草稿时只能保存为独立的 Recovery Draft，不得作为生效快照。
- **Write Back to Excel** 是明确动作，原始 Excel 默认只读，写回前备份一次（同一编辑 session 首次写回前），采用临时文件 + 原子替换，失败时保留原文件。

### 1.3 Config 参数与 T2B 的关系

- 已有 Config Section 2 明确提供 Module/Generate Type/阻抗/`IBIS IO Voltage Domain`/`IBIS VIH Voltage Domain`/`Tr MAX|TYP|MIN`/`Tf MAX|TYP|MIN`，这些字段按模块行独立管理；不要引入另一套默认值覆盖体系。
- Corner/Voltage/Calibration/SPF 匹配/Pin Mapping/MSI/CKT Append 等仍由既有 Config 语义维护。
- T2B 界面完整展示所有字段。**属于 Config 的共享字段**在 UI 中编辑时映射到相应 Config 字段并进入同一草稿，不单独保存一份冲突值；仅 T2B 自身字段（例如 nPoints、Spice command、Rload、Sim time 等）保存于模块工作模板。
- Template 的动态令牌，例如 `{{RON}}`、`{{TOP_SUBCKT}}`、`{{MODEL...}}` 的实际键名必须以现有 `T2B_TEMPLATE_RULES.md` 和 renderer 为准；UI 不新增第二套 `${RON}` 渲染语法。
- 自由文本编辑保留完整文本能力；保存前检查关键令牌、块结构、`[Pin]`↔`[Model]` 引用及 T2B 类型一致性。如果编辑试图直接硬编码属于 Config 的动态字段，UI 应提示其数据归属并引导在 Config 参数中修改；不得静默让 Config/T2B 分叉。
- Case Preview 展示某个指定 Ron 下**完整展开但尚未落盘**的最终 `.t2b`，可对比所有动态替换。

## 2. 工作区与目录（建议实现）

```
IBIS_Codex_READY_FOR_T2B_Package/
├── src/ibis_auto/                     # 现有 Core；必要时增量适配
├── src/ibis_ui/                       # 新增 Tkinter UI、ViewModel、Controller
├── templates/t2b/                    # 既有四份只读母模板 + _t2b_config.ini
├── workspace/                        # 软件管理的可写数据（默认；可在设置中调整）
│   ├── projects/
│   │   └── <project_id>/
│   │       ├── project.json          # 生效配置和元数据（引用/相对路径策略）
│   │       ├── templates/<io_top>/<drv|rcv>.t2b
│   │       ├── backups/              # 项目配置版本/备份
│   │       └── logs/
│   └── template_library/
│       └── <package_id>/
│           ├── manifest.json         # 版本、兼容性、校验和、模块映射信息
│           └── templates/<io_top>/<drv|rcv>.t2b
└── generated/<io_top>/<drv|rcv>/<N>ohm_ibis>/   # 既有结构，不变
```

- `project_id` 必须是稳定的**内部 ID**，不能只用文件夹名、当前 Config 路径或产品名来识别项目；同名项目不误覆盖。
- 存储目录可以在软件安装/脚本目录下的可写 `workspace/`，满足用户“放在软件内部”的要求；若安装目录只读，允许改到用户自定义可写数据目录。
- 路径迁移：相对路径优先配合项目 Root；绝对模型/MSI/SPF 路径要有“重新定位 Root”的入口，不能承诺跨服务器无需修改环境路径。
- 模板库与当前工作模板分离；历史归档只读，读取时复制；四份母模板只读。
- 生成目录及临时目录不得存入归档模板包；备份和测试工件也不应进入 git。
- 目录示例为建议，实施时需评估与当前项目树/打包路径的兼容性，不要求在首轮全部建好。

## 3. 启动及主界面

### 3.1 三种启动入口

1. **Import Excel**：导入已存在的 Config。
2. **New Project**：不依赖 Excel，在 UI 中填完整配置。
3. **From Library**：从历史项目模板包建立当前项目，可随后导入新的 Excel 参数。

启动后恢复上一次有效项目路径、选中 IO Top、筛选器和窗口布局；不可悄悄恢复未经 Apply 的配置草稿为生效值。

### 3.2 主界面布局

```
┌───────────────────────────────────────────────────────────────────────┐
│ Project: LPDDR6_V2  [DIRTY / SAVED]   Import Excel | Save | Export   │
├───────────────────────┬───────────────────────────────────────────────┤
│ Case Tree（带复选框）  │  [Overview] [Config] [T2B] [Files] [Monitor] │
│ □ IO Top A            │  状态摘要: MSI/SPF/Template/Errors/Warnings   │
│   □ DRV               │  Basic / MSI / Voltage / Timing / Mapping     │
│     □ 30Ω  STALE      │  / CKT / Simulation Options / Signal Override │
│     □ 34Ω             │                                               │
│   □ RCV               │  T2B: 完整文本编辑 + 选择 Ron 的 Case Preview    │
│ □ IO Top B            │                                               │
├───────────────────────┴───────────────────────────────────────────────┤
│ Status / Log: 当前 Stage、运行进度、中文错误、原始 Log / Search       │
├───────────────────────────────────────────────────────────────────────┤
│ Apply Changes  | Generate Selected | Generate All | Retry Failed   │
└───────────────────────────────────────────────────────────────────────┘
```

- 树层级：`IO Top → DRV/RCV → Ron`，模块、方向和单 Case 支持多选/部分选中状态。
- 右侧：上方状态摘要 + 下方分区表单；完整的模块 T2B 单独 Tab，文件预览、Monitor、Log 也是独立功能。
- 中文界面；技术关键字和文件路径保留英文原文。
- 参数选择器优先复用 Excel 下拉的枚举定义（如 DRV/RCV/BOTH、MAX/TYP/MIN、模板类型）。

## 4. Excel 导入、编辑、导出

### 4.1 初次导入
- UI 调用现有 `parse_config` 校验并转换为内部配置对象；要保留字段来源坐标（Sheet、行、列）用于回写、错误定位。
- 保留原始文件的副本或内容基线、原路径和摘要；**导入本身不修改原文件**。
- 结构、Excel 格式、必需字段缺失等错误用中文展示，并允许定位源 Sheet/Cell。

### 4.2 二次导入（差异合并）
- 当当前项目已存在，Import 新 Excel 时比较**当前内部生效快照**与新 Excel 解析结果。
- 以 `(Section, Module, Direction, Corner, Signal, Field)` 等语义主键匹配，不能只比单元格坐标或字段名。
- 变更项表格列出：模块/方向/Corner、字段、当前值、新值、勾选框；支持全选/反选/分组筛选。
- 新增/删除的模块、阻抗、映射行及根路径变更单独提示；删除不得静默执行。
- 确认后仅合并选中项到草稿，按 Apply→Validate 生效；受影响 Case 标记 STALE。

### 4.3 导出
- **Export As Excel**：在导入源的副本上进行最小变更，尽可能保持原始 Sheet、样式、公式、合并、数据验证、其它 Sheet 不变；不得先转换为 pandas 再重建导致版式丢失。对无法无损保留的特殊特性（宏、外链、图表、复杂名称管理器）做检测/告警，绝不无提示破坏。
- **Write Back to Original Excel**：显式按钮+确认，先自动备份；只对被允许的配置区域写入，确保其他工作表与非目标单元格不变。
- **Export Standard Config**：UI 新建项目使用软件版本化的标准 Config schema 生成新文件；测试要求导出的 Excel 可被现有 `parse_config` 无损解析（语义往返），且不修改仓库冻结 demo `inputs`。
- Excel 的“模板库版本”下拉可由 UI 向**导出文件**写数据验证+隐藏选项页；无需强行改变既有 `inputs/config/ibis_config.xlsx`；旧版 Config 不含此字段时默认 BASE。
- Excel 引用历史模板时应保存稳定的 `package_id`/版本标识，不只保存显示名；库未找到该版本时明确提示“引用缺失”，不能静默改用母模板。

## 5. 模块 T2B 工作模板

- 四份母模板提供初始结构：`drv_se.t2b`、`rcv_se.t2b`、`drv_diff.t2b`、`rcv_diff.t2b`。
- **首次加载 IO Top**：自动按 Config 中的方向和模板类型复制生成 IO Top 独立 `.t2b` 工作模板；没有启用的方向无需生成。
- **后续加载**：若模块工作模板存在，绝不自动覆盖。上游 Config 或母模板变化时，显示 STALE、差异预览，用户明确选择 Refresh Auto Fields 或 Reset From Base；Reset 是高风险操作，确认后备份。
- **同一模块同一方向**：全部 Ron 共用一份模块工作模板；`{{RON}}`、`{{TOP_SUBCKT}}` 等动态变量按 Case 在渲染时展开，不要求人工维护 8 份 T2B。
- 完整文本可编辑，支持撤销/重做、搜索、文件差异、恢复；保存前校验并保持动态变量占位语法与已有模板一致。
- **Config 共享字段**的改动必须反馈到统一项目配置草稿；模型名、实际 SPF `.SUBCKT` 及 Pin Mapping 不能在模板文本中不经校验任意脱离权威来源。
- 手工改模块模板后，相关生成 Case 标记 STALE，但不自动覆盖 `generated/`；点击 Regenerate Selected / All 并确认覆盖后才落盘。

## 6. 历史模板库（T2B Library）

### 6.1 数据单元
- 模板库的基本单元是**项目版本模板包**，如 `LPDDR6_V1`，包含该次选择的多个模块的 DRV/RCV T2B 工作模板及关联的元数据（module、direction、SE/DIFF 模板类型、来源、版本、备注、时间、校验和）。
- 默认保存全部模块，但也允许选择性归档模块；不可因为单个模块不完整就强制等待全项目完工。
- 历史包保存后只读；要改变应创建新包或新版本（如 LPDDR6_V1.1），不覆盖已归档版本。
- `Save to Library` 不应自动复制 MSI/SPF/模型库大文件或 generated 仿真结果；模板之外的配置片段如确需继承，须在 manifest 中明确范围。

### 6.2 引用、复用及模块改名
- `From Library` 可以一次导入项目模板包，也可以选取其中某个模块、某个方向。
- 名称一致时预填匹配建议；名称不一致时允许显式指定映射：例如 V1 `io_dff` → V2 `io_diff`。
- 复用历史模板时 **copy-on-import**：新项目获得独立工作副本，不影响历史包。
- 所有绑定 V1 项目身份的动态字段在 V2 重新求值：`TOP_SUBCKT` 来源为 V2 实际 SPF `.SUBCKT`；当前 Ron、Corner 文件、Model Name、文件路径、Pin Map、电压、Tr/Tf 使用 V2 的内部配置。严禁直接携带 V1 已展开的值。
- 导入时检查方向（DRV/RCV）、SE/DIFF 类型和必需动态令牌。不同类型拒绝或需要明确转换，不能只凭名字相似自动继承。
- 若目标 IO Top 已有人工修改工作模板，先显示差异/冲突，让用户选择，禁止默默覆盖。
- 模板库记录稳定包 ID 与内容 SHA-256，可导出/导入版本包，以便迁移服务器和离线共享；重复包或损坏包明确报错。

## 7. Generate、监控和结果管理

### 7.1 任务选择
- 树形复选框选择整个 IO Top、DRV/RCV、部分 Ron；支持 Generate Selected / Generate All / Retry Failed / Regenerate Selected。
- 只针对有启用且有效的 Case 创建任务，避免无谓空任务。
- 含 STALE 或现有输出目录的任务需展示覆盖预览（任务数量+文件路径）并确认。

### 7.2 错误隔离
- 全局 Config/Root 无法解析：项目级失败，本轮终止。
- 单个 IO Top 的 MSI/SPF/Pin Mapping 错误：只隔离受影响 IO Top，不影响其他模块。
- 单 Case 错误：只隔离当前 Case，其他独立任务继续。
- 失败任务有中文结构化摘要及原始 traceback/log，包含来源文件/字段/信号和建议检查项。

### 7.3 状态定义
- UI 编辑态：`CLEAN / DIRTY / INVALID`。
- 生成态：`QUEUED / RUNNING / PASS / UNVALIDATED / FAIL / STALE / CANCELLED`；其中 `PASS` 代表已有 Golden 且比较通过，**无 Golden 仅结构检查通过必须是 UNVALIDATED**。
- “READY_FOR_T2B”只表示生成文件满足当前校验边界，无真实 T2B 仿真含义。
- 监控表显示 Total、Running、PASS、UNVALIDATED、FAIL、Remaining；支持筛选、定位、复制错误、打开目录、重提失败。
- 为 UI 增加逐 Case 进度事件接口，Tkinter 主线程仅处理队列消息，禁止在主线程跑阻塞生成；是否真并行要遵循现有 Core 的数据依赖，不因 UI 假造并行。

### 7.4 生成文件浏览
- 选中 Case 后展示输出树，预览 `.ini/.sp/.t2b/.log` 文本，搜索、复制、行号；默认只读。
- 能在配置的外部工具中打开（如 gvim、VSCode 或系统默认），不能假设 Windows 桌面可调用 Linux gvim。
- 对 UI 外部修改的 generated 文件以摘要或 mtime+hash 检测 `MODIFIED`，再生成时提示覆盖风险。
- 推荐新一轮生成到 staging 目录、结构校验通过后原子地替换对应 Case，失败则保留原来的有效 Case；这是需要 Core 增量实现的新机制，不可误认为已存在。

## 8. UI 按钮语义

| 功能 | 行为 |
|---|---|
| Import Excel | 导入首次 Excel，或对已存在项目先比较差异 |
| New Project | 使用标准 Schema 和四份母模板新建 |
| From Library | 引入模板包并建立当前项目独立副本 |
| Apply Changes | 校验草稿并更新生效配置，受影响 Case 标记 STALE |
| Save Project | 将已 Apply 的内部配置和模块工作模板持久化 |
| Export As Excel | 基于源文件副本导出，不修改源文件 |
| Export Standard Config | 从 UI 内部项目生成标准 Config 文件 |
| Write Back | 提示确认并备份后写入来源 Excel |
| Save to Library | 归档全部或选定模块的工作模板为只读版本 |
| Generate Selected / All | 使用内部生效快照调用现有 Core 执行 READY_FOR_T2B |
| Refresh Template | 预览受影响动态字段并明确确认更新 |
| Reset Template | 高风险完整重建，备份并确认 |
| Retry Failed | 对失败任务重新执行，保留独立任务日志 |

## 9. Core 集成策略

1. 先建立 `ProjectStore`（内部 Schema/序列化）、`ExcelImporter/Exporter`、`TemplateLibrary` 和 `UIController`。这些服务与 Tkinter 窗口完全解耦，可做无界面单元测试。
2. 优先利用已有 `Config/ModulePlan/Corner`，引入仅 UI 层需要的持久化元数据，避免把 UI 组件类型塞进 Core dataclass。
3. 现有 CLI 的 `service.generate(config_path, ...)` 必须保留原调用和结果行为。可增内部 Adapter，通过临时标准 Config 或新增 `generate_from_config(config, ...)` 复用同一生成器。
4. 模块模板路由应是显式输入到 renderer，例如优先某个 `(project, module, direction)` 工作模板，缺失时选择母模板。不得创建两套 render 算法，也不得要求每个 Case 一套模板目录。
5. 服务层追加进度 callback / 结构化错误上报，UI 不直接解析 print/grep 字符串充当稳定接口。
6. 将项目的 staging / 原子替换机制独立封装，保证中断/校验失败时原结果不被破坏。
7. 无论 UI 状态如何，Acceptance 仍必须由既有 Core 校验得出，禁止在 UI 根据文件存在就显示 PASS。

## 10. 分阶段实施计划（推荐）

### Phase UI-1：框架 + 配置持久化（下一轮 Codex）
- 建 `src/ibis_ui/`、Tkinter UI 骨架、启动页三入口和主窗口布局。
- 新增 `ProjectStore` + 标准内部 Schema/序列化、最近项目恢复、DIRTY/Apply/Save 基础状态机。
- **真实接入“Import Excel → 当前项目配置预览/编辑 → Apply → Save Project → 重新打开”**。
- New Project 建立有效空项目模板，允许手工填字段；尚未实现全 Schema 编辑时必须清晰标明限制。
- 不执行真实 Generate，不改变 generator 模板解析、冻结输入、Golden。
- 让 UI 可在无图形显示的 CI 环境进行逻辑测试（Tkinter 实窗测试允许有 display 时执行，headless 只测 ViewModel/Service）。

### Phase UI-2：Excel 全量双向读写
- 覆盖现有 Section 1–10 的全部关键可编辑项、原始单元格定位、二次 Import diff/merge。
- Export Standard Config、Export As（格式保留）、显式 Write Back（备份）。
- 往返/冲突/源文件不被改写测试。

### Phase UI-3：模块模板编辑 + T2B Library
- 四份母模板自动初始化模块工作模板、完整文本编辑、动态令牌检查、Case Preview、STALE/Refresh/Reset。
- Save/Load Library、版本清单、模块名映射、Excel Library 版本选择。
- 模板独立性、只读版本及跨项目复用测试。

### Phase UI-4：Generate/Monitor 和验收
- Service/Controller 桥接、复选框生成、逐 Case 状态、错误隔离、文件预览、选择性重生成、覆盖保护。
- 真实运行现有 demo，验证 Golden Case 001 和全部旧测试没有回归。

## 11. 验收清单

**UI-1 必须通过：**
1. Python ≥3.10；软件可启动（在有 GUI display 的 Linux）；主窗口具备启动三入口、IO Top/DRV/RCV/Ron 树、分区编辑页及导航。
2. 导入 `inputs/config/ibis_config.xlsx` 后正确显示现有 `ModulePlan`、Voltage Domain、Corner、Ron 等字段；不修改导入源。
3. UI 修改 Section 2 的某模块 `Tr TYP`，Apply 后内部快照变化；Save Project 后重启再读取保持一致，源 Excel 不变。
4. 草稿未 Apply 时禁止悄悄 Generate 或以旧配置保存；退出/切换提示。
5. 同名 IO Top 不同 project_id 不共享编辑值。
6. headless 单元测试可运行，缺少 DISPLAY 时不导致整个测试集失败。
7. `python tests/run_acceptance.py`、既有 unit/template/robustness 测试全部仍 PASS；Golden Case 001 完全不变。

**后续阶段最终必须通过：**
8. 标准 Excel 语义往返无损；源文件导入/导出能最大限度保留 Sheet、样式、合并、公式和下拉。
9. 二次导入显示字段粒度 diff，只有勾选项被合并；模块删除需显式确认。
10. LPDDR6_V1 历史模板 `io_dff` 可映射复用到 V2 `io_diff`；V2 `TOP_SUBCKT` 来自新 SPF，V1 模板不可变。
11. 不同 Ron 共用模块 T2B，预览不同 Ron 能正确替换动态字段，Template 修改后相关 Case 变 STALE。
12. Case 重新生成前明确确认覆盖；失败不丢失上一版有效结果；单模块失败不拖垮其他模块。
13. PASS / UNVALIDATED / FAIL 区分严格与现有 Validator 一致；READY_FOR_T2B 不能冒称真实仿真完成。

## 12. 非目标及已知风险

- 不应在 UI V1 阶段启动真实 T2B/LSF 或生成 C_comp_view。
- 不应把 Excel 外观当作 Canonical Model，也不应令模板库成为第二份共享参数真相。
- `ooxml.py` 为只读解析器，Excel 写入需要新的经过验证的实现；不能默认所有 OOXML 高级特性都可完全保留。
- `service.generate` 目前直接创建/覆盖 Case，发生异常时甚至会删除该 Case 目录；正式 UI 的安全重生成需要引入 staging 事务流程。
- `READY_FOR_T2B` 的通过条件与 Goldens 数量有限，不能将全部 UNVALIDATED 解释为所有 T2B 模板已经通过实际仿真。
- UI 要支持大规模模块/Case，避免在 Tkinter 主线程耗时扫描 MSI/SPF 或同步写 Excel。

**版本结束条件**：需求文档冻结后按 Phase UI-1 至 UI-4 分 PR 实施、每次合并保留旧基线测试通过。所有新文件的路径和 Schema 版本信息需在 README 中明确说明。
