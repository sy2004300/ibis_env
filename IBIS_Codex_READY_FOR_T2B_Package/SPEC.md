# SPEC — IBIS Automation READY_FOR_T2B v1

## 1. 目标与边界

实现一个 UI/CLI 共用底层逻辑的 IBIS Case generator。输入为 Config、MSI、SPF Root、Model Root、T2B Template Root；输出为可直接进入 T2B 运行阶段的独立 Case 目录。

本版本终点：`READY_FOR_T2B`。不启动 T2B。

---

## 2. 输入事实源

### 2.1 SPF

- SPF Top `.SUBCKT` Pin List 是真实电路接口的最终真值。
- 文件名用于定位候选 SPF；真正实例化 cell 名以 SPF 内 Top `.SUBCKT` 为准。
- 文件名 Module 与 Top `.SUBCKT` 不一致：中文 Warning，可继续。
- MAX/TYP/MIN 不从 FF/SS/温度硬推导；通过 Config `SPF Match Key` 独立匹配。
- SPF 集中放在一个 Root 下，generator 建立 SPF Index。
- Corner SP 中引用原 SPF 的绝对路径，不复制 SPF。

### 2.2 MSI

- MSI 可能一个 Workbook 多个 Module Sheet，也可能多个 Workbook。
- 默认一个 Module 最终对应一个有效 MSI Source（Workbook + Sheet + Pin Name Column）。
- Parser 不依赖固定列号，应按 Header 语义/别名解析。
- 正常情况唯一 PIN_NAME；多个候选时不猜，UI/CLI 要求用户选择或显式 Mapping。
- 原 MSI 只读。
- 允许人工覆盖 `Value` 和 `POWER_DOMAIN`。
- 不允许人工覆盖 `Pin Name` / `Width`。

Normalized MSI 至少支持：

`signal_name, width, direction, pad, attribute_type, power_domain, ground_domain, default_value, description, databook_description, row_order`

Bus：同时存在 WIDTH 和 `[N:M]` 时必须一致，否则 Module FAIL。

### 2.3 Config

正式 schema：`inputs/config/ibis_config.xlsx`。

Section：

1. Project / Path
2. Module × Direction × Impedance
3. Corner Definition
   - 3.1 Process / Temperature
   - 3.2 Voltage Domain
   - 3.3 Calibration
   - 3.4 SPF Match
4. Simulation Option
5. IBIS Pin Mapping
6. CKT Append / Reference
7. T2B Template Mapping
8. Signal Override
9. MSI Attribute Override
10. MSI Mapping

Excel merge 仅用于显示。Parser 禁止依赖 merge geometry 或绝对行号，应依赖 Section/Header/内容。

### 2.4 路径

Config 保存默认路径；UI/CLI Runtime Override 优先于 Config Default，但默认不写回。

只有用户明确 `Save as Default` 才写回 Config。

相对路径按项目包/Config 所在工程根解析；真实公司环境可使用绝对路径。

### 2.5 T2B Template Library

固定入口名：

- `drv_se.t2b`
- `drv_diff.t2b`
- `rcv_se.t2b`
- `rcv_diff.t2b`
- `_t2b_config.ini`

Config 第7部分选择 template type。

`Generate Type=BOTH` 时，第2部分表达生成意图，第7部分必须分别有 DRV 和 RCV 映射。

SE/DIFF 仅由 template type 表达，不在 Config 重复保存。

Simulator 不在 Config 保存；唯一事实源为当前 `.t2b` 的 `[Spice type]`。

---

## 3. 错误隔离级别

### 项目级 Error

例如 Config 无法读取、Root 完全不存在、四套模板或 `_t2b_config.ini` 缺失。整个项目停止。

### Module 级 Error

只停止当前 Module，其它 Module 继续。

### Case 级 Error

只停止当前 `Module × Direction × Impedance` Case，其它 Case 继续。

### 用户提示

所有 UI / summary / 主 log 中的 Warning 与 Error 使用中文。内部可保留英文错误码。

---

## 4. MSI Source Discovery

优先级：

1. Config/UI 显式 MSI Mapping
2. Module 与 Workbook/Sheet 标准化名称匹配
3. SPF Top Pin 与候选 MSI Pin List overlap 辅助
4. 仍不唯一：要求用户选择，不允许静默猜测

若一个 Sheet 有多个 PIN_NAME 候选列，要求选择。

UI 中所有需要复现的人工决定最终可以写回 Config；写回前遵守第14节备份规则。

---

## 5. SPF 与接口校验

1. Config Module + SPF Match Key 匹配 MAX/TYP/MIN SPF。
2. 每个 logical corner 必须唯一匹配一个 SPF：0 个或 >1 个均 Module FAIL。
3. 解析 Top `.SUBCKT` 和 Pin List。
4. `SPF Top Pin List` 是接口真值。
5. `MSI有/SPF无`：当前 Module 忽略，可记 INFO。
6. `SPF有/MSI无`：若能由 Voltage Domain / T2B PAD / 明确特殊规则解释，可继续；否则 Module FAIL。

---

## 6. Corner Definition

### Process / Temperature

逻辑 Corner 与 Process 分离。

正常预期：

- MAX = FF
- TYP = TT
- MIN = SS

不满足：中文 Warning，询问 Continue / Abort，不直接 hard fail。

Temperature 不擅自写进 corner SP，由后续 T2B 最终仿真环境处理。

### Voltage Domain

Config 3.2 有什么 domain 就生成什么，不写死 VDD/VDDQ/VSS。

每个 domain 在 `component.sp` 固定生成：

- `<domain>_max`
- `<domain>_typ`
- `<domain>_min`

即使三个值相同也不合并。

### Calibration

Config 3.3 是通用表，不写死 TXZQCAL。

每个 Calibration Signal 必须同时存在于 MSI 和 SPF Top，否则 Module FAIL。

---

## 7. Case Matrix

第2部分 `Generate Type`：

- DRV → DRV
- RCV → RCV
- BOTH → DRV + RCV

仅展开阻抗矩阵中标记 `Y` 的阻抗。

Case Key：`Module × Direction × Impedance`。

输出目录：

`generated/<Module>/<drv|rcv>/<XX>ohm_ibis/`

---

## 8. Template 与 Model Library

根据 `Module + Direction` 找第7部分唯一 template mapping。

读取 `.t2b` 中 `[Spice type]`：当前支持 `spectre` / `hspice`。

Model directory：`Model Root / <SpiceType>`。

固定模型文件：

- `rbd.lib`
- `cap.lib`
- `mos_var.lib`

Process → section：

- FF → `rbd_f`, `cap_f`, `mos_var_ff`
- TT → `rbd_t`, `cap_t`, `mos_var_tt`
- SS → `rbd_s`, `cap_s`, `mos_var_ss`

缺文件：Case FAIL。

---

## 9. Target Impedance

DRV / RCV 均通过：

- `reg_txslice_pu[3:0]`
- `reg_txslice_pd[3:0]`

选择目标阻抗。

分别从 MSI Description/Databook Description 解析各自 impedance map。

同一阻抗多个合法 code：对每组独立取二进制数值最小的 code。

例如：40Ω `{1011,1100}` → `1011`。

`reg_odt` 不参与 target Ron 选择；`reg_odt / odt_en` 默认 MSI Default，除非 Override。

---

## 10. Input Signal / Effective Value

只对 `SPF Top ∩ MSI` 且 Direction 标准化为 Input 的普通 control 默认生成 local source。

Input 接受：`I / i / Input / INPUT / input`。

- Output：默认不生成 local source。
- IO/Inout：不自动当 Input，需要 PAD/T2B/其它明确规则。

工作模式：

- DRV：TXDAT、TXOE 由 T2B 接管。
- RCV：TXDAT=0，TXOE=1。

Value 数据来源包括：MSI Default、Target Impedance、Calibration、工作模式、Config/UI Override。

Config Explicit Override 优先于默认/派生值；但 Override 之间不做隐式优先级。

只要同一个 Module+Signal 的两条 Override 作用域重叠，即报错；完全重复也报错。

支持数值：`0/1`, `N'b...`, `N'h...`, `0x...` 等可确定数字逻辑值。

`X/Z/-/blank/非法文本`：显示 Module、Signal、原始 Value 并 Error，不允许默认为0。

如果需生成高电平但 Power Domain 缺失/未在 Config Voltage Domain 定义：Case FAIL。

若 Signal 最终全0而 Power Domain 缺失：中文 Warning，可继续。

逻辑电平：

- bit 0 → `dc 0`
- bit 1 → `dc <power_domain>_<corner>`

当前版本不使用 GROUND_DOMAIN 生成低电平。

Bus 按声明方向展开；`[N:0]` 用 MSB→LSB；所有 bit 包括 0 bit 都显式生成。

---

## 11. IBIS Pin Mapping / ckt_topology.sp

SPF Top Pin 顺序严格保持。

默认使用原始 SPF Pin Name；仅 Config 第5部分明确配置的 pin 替换为 alias。

真正实例化的 cell name 使用 SPF 内 Top `.SUBCKT`。

SPICE continuation 使用 `+`，禁止用反斜杠续行。

Config 第6部分 CKT Append：

- BOTH → DRV 和 RCV 都生效
- DRV/RCV → 仅对应方向
- 按 Config 原始行顺序追加
- 正文原样复制，不解析、不改写

---

## 12. component.sp

每个 Case 独立生成一份，不共享。

只包含 Config Voltage Domain 参数，不放 Simulation Option。

按 Config domain 行顺序；每个 domain 内固定 MAX→TYP→MIN。

---

## 13. corner SP

文件名固定：

DRV：
- `corner_drv_ronXX_max.sp`
- `corner_drv_ronXX_typ.sp`
- `corner_drv_ronXX_min.sp`

RCV 对应 `corner_rcv_ronXX_*.sp`。

每个 Case 独立生成。

基本内容顺序：

1. `.protect`
2. model library
3. 当前 SPF 绝对路径 `.inc`
4. `.unprotect`
5. Config Simulation Option（逐行原文复制）
6. T2B-controlled 注释 source
7. active power/control source

Simulation Option 默认 Demo：

- `.option method=gear`
- `.option runlvl=5`

T2B-controlled：

- 当前模板声明为 Power/Gnd 的本地 source 注释掉并集中放前面。
- DRV 的 TXDAT/TXOE 也注释并交 T2B。
- IOPADT/IOPADC 等 PAD 只作为 T2B 外部节点，不创建假的 source。

Local Power Pin：`Config Voltage Domain ∩ SPF Top 同名 Pin`。未被 T2B 接管则 active source。

普通 control 输出顺序继承 MSI 原始行顺序。

Source instance：`v + signal_name`，去掉 `[]` 等不适合 instance name 的字符。例如 `reg_txslice_pd[3] → vreg_txslice_pd3`。

---

## 14. Config/UI 写回

MSI 原文件只读。

UI 允许：

- MSI Source Mapping
- Value Override
- Power Domain Override
- Runtime Path Override

不允许直接修改 Pin Name / Width。

点击 Apply Changes：

1. 首次写回前备份原 Config
2. 名称：`ibis_config_bak_YYYYMMDD_HHMMSS.xlsx`
3. 备份失败 → 禁止覆盖原 Config
4. 备份成功 → 一次性写回所有修改
5. 一轮编辑只备份一次

Runtime Path 默认不写回；只有明确 Save as Default 才写回。

---

## 15. Case 最终目录

每个 READY_FOR_T2B Case 包含：

- `_t2b_config.ini`
- `ckt_topology.sp`
- `component.sp`
- 3 个 corner SP
- `<完整Module>_<drv|rcv>_ron<阻抗>.t2b`

`_t2b_config.ini`：模板库全局唯一，每 Case 直接复制，正文不修改。

`C_comp_view`：T2B 运行后输出，READY_FOR_T2B 阶段不得提前生成。

---

## 16. Golden 状态

Golden 可增量补充。

- 有 Golden 且比较通过：PASS
- 无 Golden但结构检查通过：UNVALIDATED
- 有 Golden但不一致/结构错误：FAIL

当前唯一 Golden：

`demo_phy_io_diff / DRV / DIFF / 30Ω / MAX,TYP,MIN`

路径：`golden/demo_phy_io_diff/drv/30ohm_ibis/`

Golden 中 `{{MODEL_ROOT}}`、`{{SPF_ROOT}}` 为比较时的 canonical root token；真实生成文件仍应写实际解析后的路径。

---

## 17. 35-pin Demo

Expanded SPF Pin Count = 35：

- Base 7：VDD/VDDQ/VSS/TXOE/TXDAT/IOPADT/IOPADC
- Target impedance 8：PD[3:0]+PU[3:0]
- Calibration 16：PD[7:0]+PU[7:0]
- FFE 4：reg_txffe[3:0]

Demo Corner：

- MAX：FF, 125°C, VDD 0.825, VDDQ 0.57, VSS 0, CAL 8'h26, SPF key rcbest
- TYP：TT, 25°C, VDD 0.75, VDDQ 0.50, VSS 0, CAL 8'h34, SPF key typical
- MIN：SS, -40°C, VDD 0.6975, VDDQ 0.47, VSS 0, CAL 8'h6A, SPF key rcworst

DRV DIFF alias：

- IOPADT→ipadt
- IOPADC→ipadc
- TXDAT→txdat
- TXOE→txoe
- VDDQ→vddq
- VSS→vss

VDD 不属于 T2B pin，由 corner SP 自己供电。
