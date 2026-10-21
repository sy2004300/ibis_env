# IBIS Automation UI 0.4.2 — 配置编辑、MSI Master 与生成流程优化

## 一、任务目标

请基于 GitHub 仓库 `sy2004300/ibis_env` 当前最新开发分支 `codex/ibis-ui-0-4-1` 继续开发，不要退回旧版 UI-1.2，也不要直接基于过时的 `main` 覆盖当前开发成果。

建议新建独立分支 `codex/ibis-ui-0-4-2`，具体命名可根据仓库现状调整。

本次目标是完善 UI 0.4.1 的配置编辑、MSI Master 数据链路、T2B 配置展示、生成前检查和自动化测试。

**重要约束：**

1. 开始前必须检查最新分支的真实代码、测试结果和工作区状态。
2. 不要仅修改 UI 文案而忽略底层数据、配置保存及生成逻辑。
3. 不要破坏现有项目存储、稳定 UUID、原始 Config Excel 只读、T2B 模板选择、生成状态管理和文件检查功能。
4. 所有按钮、标题、提示、弹窗、表格列名和错误信息统一使用简体中文。SPICE 语法、信号名、协议字段及文件名等技术内容保留原文。
5. 不要擅自删除现有功能或改变已有字段的业务含义。
6. 所有修改必须配套自动化测试，不能仅以 Python 模块导入成功或 Windows EXE 构建成功作为验收。
7. 完成后提交代码、推送开发分支，并在权限允许时创建 PR；不要自动合并到 `main`。

## 二、OPT-01：Section 4～10 改为原位展示和编辑

### 2.1 当前问题

参数配置页面中，Section 4～10 目前主要展示简短说明和“编辑”按钮。用户必须打开额外窗口才能查看和修改实际内容，不利于检查配置，也不符合 Section 1～3 的交互方式。

### 2.2 修改要求

保留 Config Section 1～10 的现有数据结构和 Core 接口，但改造 Section 4～10 的展示层。

要求：

- 展开后直接显示实际配置内容。
- 可以在页面中直接新增、修改和删除配置。
- 所有修改先进入项目 Draft，不得绕过现有数据模型直接修改已保存的项目。
- 对无效输入提供中文错误提示。
- 修改后明确显示“有未保存修改”。
- 重新进入页面、切换模块或切换标签时，不得无故丢失 Draft。
- Section 7 与 T2B 模板页面使用同一份模板映射数据，不允许两个页面各自维护互相冲突的状态。

### 2.3 各 Section 的展示方式

**Section 4 — Simulation Option**

采用多行列表，每一行代表一条 SPICE Option。

字段：
- Option 原文
- 行号或顺序
- 删除操作

支持新增、编辑、删除、调整顺序。保留原有 Option 文本和排列顺序，不得在保存时擅自改写技术语法。

**Section 5 — IBIS Pin Mapping**

使用可直接编辑的表格：

- Module
- Direction
- Original Pin
- Alias

支持新增、修改和删除映射。显示有效映射，并检查明显的重复 Alias、空值和不合法映射。

不得将 Pin Alias 与 MSI 信号 Default Value 混为一谈。

**Section 6 — CKT Append / Reference**

采用多行 SPICE 文本编辑器，直接展示实际 Body 内容。

支持：
- 查看和编辑完整的多行文本。
- 保留换行、顺序和原始语法。
- 明确显示当前 Module 和 Direction 的适用范围。
- 显示有效节点列表或可供选择的节点提示。
- 提供基本语法、节点引用和重复实例名检查。

不要尝试用简单正则表达式完整解析所有合法 SPICE 语法。无法可靠判断的内容应给出 Warning，而不是误报为确定的错误。

提供最终追加内容预览，便于用户检查实际生成的 `ckt_topology.sp`。

**Section 7 — T2B Template Mapping**

直接显示：

- Module
- Direction
- 当前模板类型
- 实际模板来源
- 模板文件路径或内置资源标识

通过下拉框选择可用模板。

支持内置母模板、外部模板和项目自定义模板。当前有效模板必须与 T2B 页面一致。

用户切换模板后，应立即更新 T2B 页面和预览状态；如果有未保存修改，必须保留或明确提示。

**Section 8 — Signal Value Override**

将现有功能名称改为：

`信号值覆盖（Signal Value Override）`

表格字段：

- Module
- Direction
- Corner
- Signal
- Value
- 删除操作

该功能用于在指定 Module、Direction 和 Corner 下覆盖信号值，不是用来修正错误的 MSI 映射。

要求：
- 保留现有的作用域和冲突检查逻辑。
- 显示原始值、覆盖值和最终有效值。
- 检查重复、冲突和无效信号引用。
- 不得将按 Corner 生效的不同值错误合并为 Master 中的一个固定 Default Value。

**Section 9 — MSI Attribute Override**

将现有名称改为：

`MSI 属性覆盖（当前支持供电域）`

当前 Core 实际支持的属性为 `POWER_DOMAIN`，不得在 UI 中暗示已经支持所有 MSI 属性。

字段：

- Module
- Signal
- Attribute
- Original Value
- Override Value
- Effective Value

对于 `POWER_DOMAIN`，显示原始供电域、覆盖后的供电域和最终有效供电域。

如果未来要支持更多属性，必须同步实现 Core、数据校验、Master 生成和回归测试，不能只增加下拉选项。

**Section 10 — MSI Mapping**

直接展示：

- Module
- 来源 Workbook
- 来源 Sheet
- PIN_NAME Column
- 匹配状态
- 来源路径

支持直接选择和修改 Workbook、Sheet 及 Pin Name 列。

同时兼容：
1. 一个 Excel 中包含多个 Module Sheet。
2. 多个 Excel 文件分别包含不同 Module。
3. 一个目录下存在多个 MSI Excel，软件自动扫描并建立候选映射。
4. 用户手动调整自动匹配结果。

映射变更后必须更新有效 MSI 和 Master 的待更新状态。

原始 MSI Excel 始终只读，不得将合并结果写回原始文件。

## 三、OPT-02：保存机制与修改差异预览

### 3.1 统一保存流程

所有 Section 1～10、模板映射和 MSI Mapping 修改都进入同一套 Draft / Apply / Save 管理机制。

用户点击“保存项目”时：

1. 检查是否存在未完成编辑的输入框。
2. 校验整个配置，而不只是当前 Section。
3. 计算 Draft 与最后保存版本的差异。
4. 弹出中文修改差异窗口。
5. 用户确认后，原子化保存项目。
6. 保存成功后刷新项目状态、有效配置和页面展示。

如果存在错误，禁止覆盖最后一次成功保存的数据。

### 3.2 差异窗口

必须真实展示修改前后的值，例如：

- Section 名称
- Module / Direction / Corner
- 字段名称
- 原始值
- 新值

对于新增和删除的行，也必须明确标记。

对于长文本，例如 CKT Append，应展示新增、删除和修改的具体文本行。

窗口至少提供：

- 确认保存
- 返回修改
- 取消

没有任何修改时，不要弹出空白差异窗口。

### 3.3 未保存修改保护

以下操作必须检查未保存修改：

- 返回项目首页
- 打开其他项目
- 新建项目
- 导入 Config Excel
- 退出程序

允许用户选择保存、放弃修改或取消操作。

任何情况下都不得静默丢弃用户的修改。

## 四、OPT-03：明确 T2B 模板来源

当前测试模板中出现了 `Synthetic QA`、`Synthetic QA Labs` 等测试数据。这些属于合成 Demo 元数据，不是 T2B 特殊语法，也不应误认为正式项目要求。

请在 T2B 页面清楚展示：

- 内置母模板
- 外部模板
- 项目自定义模板
- 实际生效模板路径
- 当前模板是否有未保存修改

对于外部模板被修改的情况，应提示用户当前使用的是外部版本。

内置模板与外部模板之间切换时，必须重新计算预览，防止页面展示的模板来源与实际生成来源不一致。

不得将合成测试元数据自动替换到正式项目模板中。

## 五、OPT-04：重新设计 MSI Master 数据链路

这是本次修改最重要的架构要求。

### 5.1 统一定义

**MSI_Master.xlsx 是由原始 MSI Excel 经过模块映射、数据合并和适用的属性调整后形成的有效 MSI。它既是正式生成输入源，也是生成结果检查和数据追溯的基准。**

不能再把“用于生成的 Master”和“用于检查的 Master”设计成两套相互独立、可能内容不一致的数据。

### 5.2 正确的数据流

原始 MSI Excel
→ Workbook / Sheet / Module Mapping
→ 合并并生成有效 MSI Master
→ 检查有效 Master
→ Generator 读取本次实际使用的 Master
→ 生成对应 Case
→ 对生成结果进行结构和语义检查
→ 将本次使用的 Master 随生成结果一起保存。

MSI Master 必须在生成任务开始前生成或确认完成。

禁止先用一种 MSI 数据生成 Case，之后再生成另一份不一致的 Master 作为检查依据。

### 5.3 原始 MSI 与 Master 的关系

原始 MSI Excel：

- 始终只读。
- 作为原始数据和来源追溯依据。
- 不得被软件自动覆盖。

MSI Master：

- 是映射后的有效 MSI。
- 是 Generator 正式使用的 MSI 输入源。
- 也是后续检查、追溯和问题定位的依据。
- 必须记录来源 Workbook、Sheet、原始文件标识和必要的 Hash 信息。
- 必须能够追溯每个有效 Sheet 来自哪份原始 MSI。

### 5.4 属性覆盖与信号值覆盖必须区分

Section 9 的 `POWER_DOMAIN` Override 属于 MSI 属性调整。有效属性应反映到 Master 的语义数据中，同时保留原始值与覆盖记录。

Section 8 的 Signal Value Override 可能按 Direction、Corner 产生不同的最终值。这些值属于 Case 级规则，不能简单覆盖 Master 中一个全局 Default Value。

对于 Case 级 Override，应在 Master 中保留必要的来源追溯信息，或通过独立的 Manifest / Sheet 记录规则；Generator 在生成对应 Case 时应用正确的最终值。

### 5.5 Master 更新与人工修改保护

自动更新 Master 时必须比较：

- 原始 MSI 是否变化。
- Mapping 是否变化。
- 属性覆盖是否变化。
- Master 内容是否被人工修改。

不得无条件覆盖人工维护的内容。

如果 Master 已被人工修改且重新合并可能覆盖这些修改，必须提示用户并展示差异，允许确认、取消或恢复到可追溯的自动生成版本。

应明确区分自动生成内容和人工维护内容，并避免两者相互覆盖。

如果当前架构无法可靠支持 Master 人工编辑，应先明确实现边界，不要伪装成已经支持。

### 5.6 生成结果目录

建议采用以下结构，具体位置以当前生成架构为准：

generated/
├── _inputs/
│   ├── MSI_Master.xlsx
│   └── source_manifest.json
├── phy_lane0_diff/
├── phy_cmd_se/
├── phy_strobe_diff/
└── phy_data_se/

其中 `MSI_Master.xlsx` 必须是本次实际使用的版本，而不是重新扫描后生成的另一份不一致文件。

若同一项目需要多次生成，应保留足够的版本和 Hash 信息，以便确认每个 Case 对应哪一次 Master。

不要在没有必要时重复生成多份内容相同的 Master。

## 六、OPT-05：取消手动生成 Master 的必选步骤

当前 UI 不应再要求用户为了开始生成流程，先手动寻找并点击“生成 MSI_Master.xlsx”。

请调整为：

1. 导入或新建项目。
2. 自动扫描并建立 MSI Mapping 候选。
3. 用户检查或修改 Mapping。
4. 用户启动生成任务。
5. 软件自动构建或确认有效 MSI Master。
6. 完成 Master 检查后，才允许正式生成 Case。
7. 生成结束后将本次实际使用的 Master 保存到输出目录。

可以保留高级页面中的“预览 Master”“重新生成 Master”等操作，但这些不应成为日常生成的强制手工步骤。

如果映射缺失、信号定义冲突或有效 Master 无法生成，必须在开始生成前明确报错。

不得使用旧 Master 静默生成，也不得在 Master 构建失败时回退到未经确认的原始 MSI 数据。

## 七、OPT-06：MSI Master 预览界面详细化

目前的文本式摘要不足以满足工程检查需求。

请将 Master 预览改为结构化表格。

### 7.1 顶部摘要

显示：

- Module 数量
- 原始 Workbook 数量
- 有效 Sheet 数量
- Mapping 完成数
- 错误数和 Warning 数
- Master 是否过期
- Master 当前版本 / Hash 标识

### 7.2 来源映射表

每行对应一个 Module 或一条实际映射关系。

列包括：

- Module
- 来源 Workbook
- 来源 Sheet
- PIN_NAME Column
- 原始文件状态
- Mapping 状态
- 有效 Master Sheet
- 来源文件变化状态

点击某一行可查看具体 Sheet 内容。

### 7.3 有效 MSI 信号表

展示当前选中 Module 的有效信号数据，包括实际存在的字段：

- PIN_NAME
- WIDTH
- DIRECTION
- POWER_DOMAIN
- DEFAULT_VALUE
- 其他已支持且实际存在的 MSI 属性
- 原始值
- Override 后的有效值
- 来源 Workbook / Sheet

不要为了界面完整而伪造原始 MSI 中不存在的字段。

### 7.4 检查结果

至少覆盖：

- 缺失 Module Mapping
- Sheet 不存在
- Pin Name 列不存在
- 重复信号
- Width 无效
- 缺失必需字段
- 属性覆盖冲突
- 来源文件已变化
- Master 与当前有效配置不一致

对每个问题提供可定位的 Module、Sheet 和 Signal。

### 7.5 交互

支持：

- 搜索 Module / Signal
- 筛选 PASS / Warning / Error
- 展开查看具体信号
- 查看原始值与有效值差异
- 查看 Master 生成记录
- 导出或打开本次 Master

手动 Mapping 的修改必须通过项目统一的 Draft / Save 流程保存，不允许预览界面绕过项目数据模型。

## 八、生成结果与检查链路

本次优化不能只完成参数编辑和 Master 展示，还必须保证后续生成流程真实使用有效数据。

请验证以下链路：

Config Section 1～10
→ MSI Mapping
→ 有效 MSI Master
→ T2B 模板选择
→ T2B 填参预览
→ 生成选中 Case / 生成全部 Case
→ 输出文件检查
→ Master 来源追溯。

必须验证：

1. 修改 Tr/Tf、Voltage Domain、Calibration 后，预览和生成结果同步变化。
2. 修改 Simulation Option 后，生成文件中的 Option 正确更新。
3. 修改 Pin Alias 后，生成的连接关系符合映射。
4. 修改 CKT Append 后，生成的 `ckt_topology.sp` 包含正确的附加内容。
5. 修改 T2B Template Mapping 后，实际生成使用选定模板。
6. 修改 Signal Override 后，只有适用的 Direction / Corner 使用对应值。
7. 修改 POWER_DOMAIN 后，有效 Master、生成结果和检查记录一致。
8. 修改 MSI Mapping 后，Master 重新构建，生成器不得继续使用旧 Master。
9. 生成完成后，输出目录中的 Master 与生成时实际使用的 Master 一致。
10. 如果生成中途失败，必须记录失败原因，不得把部分输出伪装成完整成功结果。

没有冻结 Golden 的合成 Demo，只能标记为 `UNVALIDATED` 或实际结构检查结果，不得擅自标记为 Golden PASS。

## 九、自动化测试要求

在现有测试架构上补充测试，不得只新增不执行的测试代码。

### 9.1 单元测试

覆盖：

- Section 4～10 的 Draft 更新。
- 多行 Option 保存及顺序保留。
- Pin Alias 新增、删除、重复和无效引用。
- CKT Append 文本保真与基本检查。
- T2B Mapping 与模板解析一致性。
- Signal Override 的作用域和冲突检查。
- POWER_DOMAIN Override 的有效值。
- 多 Workbook / 多 Sheet MSI Mapping。
- Master 自动构建、更新和来源追溯。
- Master 人工修改保护。
- Master Hash 与版本记录。
- 保存前 Diff 的正确性。

### 9.2 集成测试

必须覆盖：

1. 从原始 MSI 构建 Master。
2. 从 Master 生成至少一个 DRV Case。
3. 从 Master 生成至少一个 RCV Case。
4. 验证 Corner SP 中的信号值。
5. 验证 T2B 参数替换。
6. 验证 CKT Append 的实际输出。
7. 修改 Mapping 后重新生成。
8. 验证输出 Master 与生成输入一致。
9. 验证源文件变化后触发正确的失效或重新生成逻辑。
10. 验证失败和取消操作不会破坏最后一次成功保存的配置。

### 9.3 GUI 自动化测试

使用仓库现有的 GUI 测试方案，覆盖：

- Section 4～10 原位展开。
- 字段编辑、增加和删除。
- 保存前差异弹窗。
- 取消保存后保留 Draft。
- 切换页面后修改仍然存在。
- 修改 T2B Mapping 后预览同步更新。
- Master 预览搜索和筛选。
- 生成任务启动前自动准备 Master。
- 未保存修改保护。

如果环境无法运行真实图形界面测试，必须如实记录未执行项，不得以 Headless 测试代替真实 GUI 验收。

### 9.4 Windows 打包

如果仓库已有 Windows EXE 打包工作流，继续使用现有工作流。

必须确保 EXE 与 Linux Python 版本使用相同的 Core 生成逻辑、配置语义和数据模型。平台差异只能存在于 UI、文件路径和打包层，不得造成两套不同的 Master 或生成逻辑。

## 十、完成标准与交付

完成后提供：

1. 新分支名称和最终 Commit SHA。
2. 修改文件清单及每项修改的目的。
3. Section 4～10 原位编辑完成情况。
4. MSI Master 构建、生成输入和检查基准的完整流程说明。
5. Master 人工修改保护和来源追溯机制。
6. 新增及执行的测试清单和真实测试结果。
7. GUI 自动化测试结果。
8. Windows EXE 构建结果及产物位置。
9. 未完成项、已知限制和风险。
10. PR 链接（若成功创建）。

必须保证现有功能没有因为本次重构而回退。

完成后先停在独立开发分支，等待人工验收；不得自动合并到 `main`。

**最终验收原则：同一次生成任务中，MSI_Master.xlsx 是映射后的有效 MSI，也是 Generator 实际读取的数据源和生成结果检查基准；所有结果均可追溯到原始 MSI、Mapping、模板和项目配置。**