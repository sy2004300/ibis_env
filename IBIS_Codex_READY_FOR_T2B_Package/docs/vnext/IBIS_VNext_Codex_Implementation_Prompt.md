# Codex 执行任务：IBIS Automation VNext — 极简 Excel 双格式导入 + 自动预处理 + UI 补全 + 安全生成

> 这是**实施任务**，不是调研或设计提案。请结合一起上传的 `IBIS_Config_Input_Final.xlsx` 与 `IBIS_Config_Generated_Example_Final.xlsx`，完成软件、配置解析、导出、验证、测试和文档的端到端更新。生成的 Excel 示例是**布局/行为示意**，不是来自真实 SPF/MSI/T2B 的扫描结果。**Excel 文件与本 Prompt 同时作为输入，以下条款是行为要求；当示例值与真实输入文件冲突时，以真实输入为准并提示用户。**

## 0. 项目、环境和原则

- 仓库：`sy2004300/ibis_env`。以已在公司 Linux 上验证能启动的 `codex/ibis-ui-0-4-2-python37` 分支及现有 Stage 1 实现为基线。**先核对仓库当前分支和代码，再修改，禁止直接覆盖现有可用实现。**
- 运行环境：CentOS 7、Python 3.7.8、Tkinter；保持这套环境兼容性。不要引入需要较新 glibc/Python 的依赖，Python 3.7 不支持的语法不允许使用；若使用 openpyxl，注意与 Python 3.7 匹配（既有环境采用 3.0.10）。保留已经修复过的 Tk 命名字体兼容性。
- 工作范围：**Stage 1 IBIS/T2B 环境准备及 `READY_FOR_T2B` 生成**。不要更改 Stage 2 IBIS Merge 的命名/合并逻辑，也不要在 Stage 1 擅自把 SPF 顶层 `.SUBCKT` 重命名为短名称。
- 一切软件自动写入输出至项目 Workspace（优先 MSDV 指定目录），**不污染 SPF/MSI/Model/T2B 原始输入目录，不在 trunk/sim 下生成软链接**。
- 关键理念：**用户填最少信息 → Import Excel 自动识别类型和预处理 → UI 显示缺失/错误并允许修正 → 任何时候可 Export Excel → 检查通过后才允许 Generate T2B。** 不增加不必要的主操作按钮/向导。

## 1. 必须支持的两种 Excel 格式

### 1.1 极简输入 `IBIS_Config_Input_Final.xlsx`

这份文件有 3 个 Sheet：

1. `Input`：**唯一正式输入 Sheet**，包含源路径、模块、Corner、可选 Voltage 与 Global Signal。
2. `Demo`：用户参考示例，**不得参与任何生产数据解析**。
3. `填写说明`：说明文档，**不得参与生产数据解析**。

必须按标题、字段名和有效数据区解析，而非依赖之前 0.4.2 的旧 Section 编号、固定行位置或旧 Ron 阻值列布局。`Input` 中的结构按附件读取：

- `01 Input Sources`：`Model Source`、`MSI Source`、`SPF Source`、`T2B Source`。
- `02 Module Configuration`：`Module (SPF 匹配名)`、`Generate Type`、`Topology`、`IO Domain`、`VIH Domain`、`Ron (Ω)`。
- `03 Corner Configuration`：`Process`、`Temperature (°C)`、`Tr`、`Tf`、`SPF Match Key`，每项 MAX/TYP/MIN。
- `04 Optional Voltage Values`：`Domain | MAX | TYP | MIN`。
- `05 Optional Global Signal Defaults`：`Signal | MAX | TYP | MIN`。

必须识别 `30,34,40` 形式的**单元格 Ron 列表**（空格及常见分隔符合理兼容，检查正整数、去重和 MSI 阻抗 code）；不是旧版每阻值一个 Y/N 列。只预留 3 个 Module 行、2 个 Voltage 行、2 个 Global Signal 行是**视觉限制而非容量限制**：用户插入新行应能正常读取，不能写死容量。不要自动生成大片空白行。

### 1.2 完整配置 `Config_Generated.xlsx`

附件 `IBIS_Config_Generated_Example_Final.xlsx` 的 `Generated Demo` 是输出形态**演示**。正式实现应生成可保存、可导入、可作为实际生成依据的完整配置（命名可以为 `Config_Generated.xlsx`），包含有效的：

- Resolved Sources，Module Plans、Corner/Power/Signal。
- IBIS Pin Mapping。
- Optional CKT Append。
- Module Signal Override。
- MSI Mapping。
- 字段来源、检查结果和必要的人工确认状态。

**完整表不是可读但无法解析的展示报表**：必须能把人工修改的值重新导入并真正用于 Stage 1 生成。完整表未填写完时也允许保存，保存空值及状态，不允许伪造已完成结果。解析器应跳过说明/示例行、空占位行、非法空 Case。重新导出尽量保持表格紧凑，**只有标题行/字段表头着色，普通数据行白底，全部表格内部细实线**；不要铺几十行占位。

### 1.3 统一导入行为

UI 使用**同一个 `Import Excel` 按钮**同时支持上述两种格式，按工作簿结构/内部版本标记检测，**不靠文件名**判断。当前 Input 模板已存在、可能无版本标记，应能兼容识别；新导出的完整表建议加入版本元数据。

- 导入极简 Input：**自动进行预处理**，不要求再点击单独的 Preprocess 按钮。
- 导入完整 Config：读回人工确认配置，检查源文件变化并保留仍有效的用户值，再重新验证。
- 允许打开已有项目恢复上一次完整配置；不同项目配置完全隔离。
- 可选兼容旧 0.4.2 Config：如果实现，必须显式提示转换、绝不默默覆写旧文件；不要为此牺牲本次主要功能。

## 2. UI：以最简单的三个核心操作为主

在现有 Tkinter UI 中实现（不是新建第二套工具）：

1. **Import Excel**：选择 Input 或完整表 → 解析 → 扫描 MSI/SPF/T2B → 自动填充可确定项 → 检查 → 展示缺失/错误清单。
2. **Export Excel**：任何时候都可导出当前**完整配置**，包括 AUTO_MATCH、MANUAL、UNRESOLVED、STALE 状态和未填写字段；用于离线 Excel 编辑后重新导入。
3. **Generate T2B**：**只有所有阻断性检查通过才启用/真正执行**；点击时还须做一次服务器端/核心层 Precheck（不能仅相信 UI 按钮状态），调用已有 Stage 1 Generator 生成 `READY_FOR_T2B`。

无需独立的 Preprocess、Refresh、Precheck 作为三个强制主按钮。**导入和 UI 修改后自动进行必要的检查**；如有必要，详细面板中可有“重新扫描/重新检查”次级操作。首次可 New Project、之后 Open Project，工作区保存原始输入副本、完整配置、检查报告、日志和 Stage 1 输出。

UI 必须有清晰的**待填写/待修正列表**：错误类别、Module、Direction、Corner、字段名、文件/Sheet、为何阻断；点击或选择问题能定位到对应字段，允许在 UI 中填写/下拉修改。支持导出后在 Excel 编辑再导入。区分 `ERROR/BLOCKING` 与非阻断 `WARNING`；**有空白不代表一定错误**。例如 CKT Append、Signal Override 留空是正常情况，而必需 Pin 映射、电压值缺失则阻断正式生成。

状态建议：`AUTO_MATCH`、`MANUAL`、`UNRESOLVED`、`STALE`。**不能只根据非空判断通过**，必须检查来源、值合法性和跨文件一致性。若导入完整表后源文件变化，保留旧人工结果并验证；失效则 STALE，必须重新确认才允许生成。不得静默覆盖确认值。

## 3. 输入与自动补齐的具体规则

### 3.1 Source / 文件目录防呆

- `Model Source`：允许指定模型根目录；若输入具体 `.lib`，只可在目录结构**唯一且安全**推导完整库文件集时解析到模型根，否则明确报错；检查真实 `rbd.lib`、`cap.lib`、`mos_var.lib` 和 PDK `.lib` section。
- `MSI Source`：目录或单 `.xlsx`，目录可递归查找；忽略生成的 MSI Master 和不相关/临时文件；避免把同名 Sheet 误选。
- `SPF Source`：目录或单 `.spf` 文件作**定位锚点**。即使输入单文件也必须确定 MAX/TYP/MIN 三个独立文件；没有找到全套时报告待修正，不把一份 SPF 误用于三个 Corner。
- `T2B Source`：目录或一个可唯一匹配实际计划的 `.t2b`，留空使用项目内置四套模板（`drv_se` / `drv_diff` / `rcv_se` / `rcv_diff`）。对 BOTH 或多拓扑项目，单模板不能偷偷覆盖所有方向。
- 所有路径先验证真实文件类型、存在性及作用范围，显示规范化路径，不得把文件路径当目录传给 `rglob` 等目录 API。

### 3.2 Module 与模板

- Section 2 中 `Generate Type = DRV / RCV / BOTH`，`Topology = SE / DIFF`。两者组合自动推导模板；BOTH 按 DRV 和 RCV 展开。
- IO/VIH Domain 缺失时可以从 T2B/MSI 获得候选，只有无歧义且规则确定时预填，否则留空提示；不能随便把所有模块写成 VDDQ。
- **彻底取消独立模板 Mapping 表和模块级 Tr/Tf Override**。Tr/Tf 只能在 Corner 表定义全局 MAX/TYP/MIN。

### 3.3 Corner、Voltage、Signal

- Process 下拉 `FF/FS/SF/SS/TT`，Temperature 下拉 `125/25/-40`；Process 的 FS/SF PDK lib 映射需从真实库验证，不允许臆造 section 名。
- Global Tr/Tf 每个 Corner 必须有效；`SPF Match Key` 用于唯一定位每模块 MAX/TYP/MIN SPF。
- Voltage Domain 名称尽可能由 T2B `[Pin]` 的 `Power/Gnd`、MSI `POWER_DOMAIN/GROUND_DOMAIN`、模块 IO/VIH Domain 汇总预填；**不得自动编造实际 MAX/TYP/MIN 电压**。输入表已给的电压要保留并校验，缺必需电压阻断生成。MSI 属性本身不允许在 Config 覆盖，若错误要求用户修正原 MSI。
- Global Signal Defaults 只处理用户实际填写的信号，允许空表；不再硬编码 `Calibration` 类别。Signal 值支持标准 Verilog `8'h4C`、`8'b01001100`、`8'd76`、可控简写 `0x4C`、`0b01001100`、`76`；要检查解析歧义、位宽和信号有效性，空白表示继承已有值。不同模块 MSI Signal 集合不同不能假设所有模块都存在同一个全局信号。
- **删除 Excel Simulation Options 部分**：用户已决定后续不填 Option。不得误删 T2B 原有 `[Spice command]`、已有必要 SPICE 配置及生成器能力。

### 3.4 IBIS Pin Mapping（核心，严格执行）

**只针对实际所选 T2B 的 `[Pin]` 中 IBIS Pin 映射。不展开 SPF 里其余配置、校准、Ron 等非 IBIS Pin。**

- 解析所选 T2B `[Pin]` 定义，正确识别 `Power/Gnd/dummy/model`、续行 `->` 及差分 `[Diff pin]`，不要把 `->` 或 model 名误作 Pin。
- 解析 SPF TOP `.SUBCKT` **完整且有序的 Pin List**；验证每个 Corner 的 Pin 列表一致性。
- 仅当 `T2B Pin` 与 `SPF Pin` **名称相同（忽略大小写）**时自动填入 SPF Pin；不能按相似度“猜”。例如 `txoe` ↔ `txoe` 自动；`ipadt` ↔ `IOPADT` **不同名**（多了字母 o）→ **SPF Pin 保持空白，用户从 SPF 原始 Pin 下拉选择**；`ipadc` ↔ `IOPADC` 同理。
- 用户手工选择后记 `MANUAL`，检查 Pin 真实存在、同一作用域映射不冲突、符合本项目 IBIS 对外 Pin 名 **不超过 5 个 ASCII 字符**的约束。
- 生成 `ckt_topology.sp` 时：**先按 SPF `.SUBCKT` 的所有 Pin 原始顺序与个数生成 `x1` 连接列表，然后只在用户确认的 IBIS Pin 对应位置替换节点名称，非 IBIS Pin 原封不动保留，不能删/重排。**
- 示例：SPF 顶层 `.SUBCKT top vddq vss txoe txdat IOPADT IOPADC reg_cal_pd[0]`；用户确认 T2B `ipadt` 对应 SPF `IOPADT`，`ipadc` 对应 `IOPADC`；输出应为 `x1 vddq vss txoe txdat ipadt ipadc reg_cal_pd[0] top`，其中非 IBIS 控制 Pin 保留。
- 当前 0.4.2 使用 `config.aliases` 映射 SPF Pin，需确保新格式方向正确，并且不再假设旧 Excel Alias 在 G 列。

### 3.5 CKT Append

- 根据 Module + Generate Type 自动创建**少量** Module/Direction 行；`SPICE Body` 默认空，**无内容即不追加任何 SPICE**，不应要求填 Enabled。可按需增加多条附加语句，检查基本有效性及重复实例名。

### 3.6 Module Signal Override

- 自动依据 Module/Direction 创建**少量**空行；Signal 从 MSI 选择，MAX/TYP/MIN 独立覆盖，空格子表示继承 Global Signal 或 MSI 默认。
- 处理位宽、进制、Corner/Direction 作用域冲突，不允许普通 Override 意外破坏 Ron→Code 的已有阻抗控制路径。

### 3.7 MSI Mapping

- 根据输入 Module + MSI Source 尝试唯一匹配 Workbook/Sheet，优先复用合法且经过确认的 Mapping；自动发现 `PIN_NAME`/`NAME`、`WIDTH`、`DIRECTION` 列。
- 零匹配或多匹配时留空、列出候选让用户选；名字相似、Pin 相似只能作建议不能自动确认。保存所选 Workbook/Sheet/列名，重新加载仍然可用。
- **取消 MSI Attribute Override**，不得为方便自动化而偷偷改 MSI `POWER_DOMAIN`。

## 4. 数据结构、保存和项目工作目录

- 将 UI、扫描/预处理、Excel 读写、Precheck、Stage 1 Generator 分离；**一套核心逻辑同时供 GUI 和 CLI/Agent 调用**。可新增 CLI `preprocess --input ... --output ...`，但 GUI 导入时应自动触发，无须用户手动操作该命令。
- 设计有版本号的内部 Config Schema（Input/Generated 两种入口进入统一 Model）；不要直接把某份 Excel 工作表当核心数据模型。
- Generated Excel 的状态/来源/人工确认需要可持久化；保留必要源文件路径与文件指纹（如 hash/size/mtime 的组合）用于重导入后的 STALE 检测，避免把单纯重命名成旧文件就误当有效。
- 打开已有项目应加载保存的完整 Config；更新输入不会悄悄清空已确认的映射；若源文件变化使值失效则明确提示、阻止生成。
- 对可导出的完整表，保持当前约定的视觉标准：**标题/字段表头可以着色，普通数据行白底，全表细实线，少预留行，用户插入行后仍能解析**。
- 原始文件只读，输出全部集中在项目 Workspace 内（如 `config/`、`logs/`、`READY_FOR_T2B/`），不要碰原始数据目录。

## 5. 阻断条件与验收用例（必须写自动化测试）

### 必须阻断正式 Generate T2B 的情形

1. 必填 Source/Module/Generate Type/Topology/Ron/Corner 配置缺失或格式错误。
2. 目标 MAX/TYP/MIN SPF 找不到、匹配多份，或三角 Top Pin List 不一致。
3. 模板缺失、模板作用方向/拓扑不匹配，或 `[Pin]` 有未映射的必需 Pin。
4. MSI 找不到、Sheet/信号列歧义、信号/位宽/POWER_DOMAIN 不合法、与实际电压配置冲突。
5. 关键 Tr/Tf/Process lib section/Voltage 值缺失、非法或未验证。
6. 映射冲突、覆盖冲突、陈旧人工映射 STALE，或其他会改变仿真结果的错误。

### 必须允许 Export Excel 的情形

- 上述任何未解决项存在时，**仍可导出包含待补充项的完整 Config**，以便用户 Excel 离线补充后再次 Import；导出前不应强制所有项通过。
- CKT Append 与 Signal Override 全空是**正常配置，不是阻断项**。

### 必做测试

1. Input 与 Generated 两种 Excel 通过**同一个 Import Excel**正确识别；Generated 完整表的人工修改重导入后在生成逻辑中真正生效；Demo/填写说明绝不参与生产解析。
2. `BOTH × DIFF`、`DRV × SE` 等自动模板选择正确； Ron 单元格 `30,34,40` 解析正确；插入额外模块、Voltage、Signal 行也正确。
3. T2B `ipadt` 对 SPF `IOPADT` 必须 UNRESOLVED、`txoe` 对 `txoe` AUTO_MATCH；手选后检查 CKT `x1` 全部 Pin 顺序、数量严格不变，只替换指定 IBIS 节点。
4. T2B+MSI 电源域名称自动预填；未提供电压数值则 BLOCKED，补值后通过；绝不编造任何 Corner 电压。
5. 缺少/歧义 MSI Sheet、三个 SPF Corner 文件或 PDK Section 时，GUI 给出定位清楚的问题清单。
6. 未通过检查时，**Export Excel 成功但 Generate T2B 被禁用且核心执行入口拒绝**；补齐后启用并生成 READY_FOR_T2B。
7. 完整 Config 再次导入不丢人工修改；变更源 SPF/T2B/MSI 后对受影响映射进行 STALE 检查。
8. 不产生多余空 Module、CKT Append 或 Override；导出 XLSX 不出现大面积颜色与大量空白预留行。
9. Stage 1 旧有 `.lib/.inc`、Corner SP、`component.sp`、T2B 变量、MSI Ron→Code、仿真生成链路不回归。
10. CentOS 7 / Python 3.7.8 下 Tkinter UI 能启动；至少执行与 Python 3.7 兼容的单元测试、xlsx 读写回环和基础生成 Fixture。

## 6. 交付和执行要求

- 一次性完成真实实现，不要只输出建议、Prompt、伪代码、空壳按钮或只能展示不能回读的 Excel。
- 提交/说明改动文件及差异：Config Schema/Parser、Preprocess、UI、Import/Export、Precheck、Generator、测试、README、演示输入和示例输出。
- 说明从 UI 新建项目、Import Input、修正缺项、Export、重新 Import Generated、最终 Generate T2B 的实际操作步骤。
- 保持既有 UI 0.4.2 可用能力与命令入口，明确兼容方案；不对真实项目硬编码假电压、假模型库 section、假 MSI 目标阻抗码。
- 输出实际测试结果（成功/失败/未能在当前平台验证）和剩余限制。若真实 PDK/SPF/MSI 不在仓库中，必须使用最小**合成 Fixture** 跑通上述关键测试，不得因此放弃实现。
- 如实现过程中出现真正不可由附件或现有代码判断的硬阻塞，请集中列出少量需要工程师确认的问题；其他部分继续完成，不要用随意假设掩盖问题。

**优先级最高的验收标准：两类 Excel 都能直接 Import；导入后自动预处理和显示待填写；Export 随时可用；Generate 严格受有效性检查约束；CKT 完整 Pin 不丢失；原 Stage 1 不回归。**
