# MSI Master Merge 方案 A 技术规范

## 1. 目标和边界

本规范冻结 UI-2 的 MSI Merge 契约。UI-1.2 只提供只读扫描和映射预览，不生成 `MSI_Master.xlsx`。

Config Excel 与 MSI Master 是两个独立事实源：Config 保存模块、DRV/RCV、Ron、Corner、Voltage、模板映射和唯一 MSI 来源映射；`MSI_Master.xlsx` 保存合并后的信号表、来源追踪和 Module → Master Sheet 关系。原始 MSI Excel 与原始 Config Excel始终只读。

## 2. 数据模型

### 2.1 SourceWorkbook

- `source_id`：基于规范化绝对路径、文件 SHA-256 和导入批次的稳定 ID
- `path`：原始路径，仅用于本地定位
- `filename`
- `sha256`
- `size`
- `mtime`
- `imported_at`

### 2.2 SourceSheet

- `source_id`
- `original_sheet`
- `header_signature`
- `content_sha256`
- `pin_name_columns`
- `row_count`
- `is_valid_msi`
- `validation_errors`

### 2.3 MasterSheet

- `master_sheet_id`
- `master_sheet_name`
- `module`
- `source_id`
- `original_sheet`
- `source_content_sha256`
- `master_content_sha256`
- `user_modified`
- `revision`

### 2.4 ModuleMapping

- `module`
- `master_sheet_id`
- `pin_name_column`
- `match_method`
- `match_score`
- `confirmed_by_user`

Config Section 10 的 MSI Mapping 与 `ModuleMapping` 必须表示同一决定。实现时由一个应用服务同时更新项目草稿和 Master manifest，不允许产生第二套互相矛盾的映射。

## 3. 扫描与识别

1. 递归发现 `.xlsx`，忽略 Excel 临时文件 `~$*`。
2. 明确排除当前项目的 `MSI_Master.xlsx` 及 manifest 标记过的 Master，防止反复合并。
3. 一个 Workbook 的每个 Sheet 独立识别。
4. 按现有 MSI Header 别名和 PIN_NAME 唯一性判断有效 MSI Sheet，不依赖固定列号。
5. 非 MSI Sheet保留在扫描报告中，但默认不进入 Merge 候选。
6. 扫描阶段只读，记录合并前每个源文件 SHA-256；完成后再次核对，Hash 变化则中止。

## 4. Sheet 命名

Excel Sheet 名必须满足：最长 31 个字符，不包含 `: \\ / ? * [ ]`，不能为空，不能以单引号形成非法边界，名称比较不区分大小写。

命名优先级：

1. 已确认并仍合法的历史 Master Sheet 名。
2. 唯一且合法的原始 Sheet 名。
3. 规范化后的 Module 名。
4. 截断后的基础名加稳定短 Hash，例如 `very_long_module_name_ab12cd`。

规范化不会静默覆盖。发生名称碰撞时，预览中显示冲突来源；只有用户确认后才能使用稳定后缀生成不同名称。重跑相同输入必须得到相同名称。

## 5. 冲突处理

- 同名 Sheet、内容 Hash 相同：标记为重复候选；默认复用一份，但必须保留全部来源追踪。
- 同名 Sheet、内容不同：`NAME_CONTENT_CONFLICT`，禁止覆盖，要求选择、重命名或分别保留。
- 同 Module 多候选：`MODULE_SOURCE_AMBIGUOUS`，不得按扫描顺序猜测。
- 同候选多个 PIN_NAME：`PIN_COLUMN_AMBIGUOUS`，要求用户选择。
- Master 已人工修改且来源更新：生成三方 Diff（旧来源、当前 Master、新来源），不得静默刷新。
- Config Mapping 与 Master Mapping 不一致：阻止保存并要求解决冲突。

## 6. 智能匹配优先级

1. 已确认且来源仍有效的 Project/Config 显式 Mapping。
2. Module 与原始 Sheet 规范化名称精确匹配。
3. Module 与 Workbook stem 规范化名称精确匹配。
4. SPF Top Pin 与 MSI Pin List overlap，仅作为候选评分辅助。
5. 仍非唯一时进入人工映射，不自动选择最高扫描顺序。

每个自动决定必须记录 `match_method`、分数、候选集和确认状态，以便 UI 显示和复现。

## 7. 预览、编辑和保存

Merge 分为 Scan、Plan、Preview、Commit 四步。Preview 展示新增、复用、重命名、冲突、忽略和 Mapping 变化。用户确认后写入项目 Workspace 内 staging 文件：

1. 写入完整临时 Workbook 和 manifest。
2. 重新读取临时文件并验证 Sheet、Header、行数、Hash 和 Mapping。
3. 对已有 Master 建立同 session 一次性备份。
4. 使用原子替换提交 Master 与 manifest；任一步失败保留旧 Master。

Excel 写入失败、磁盘空间不足、目标被占用或进程中断均不得损坏已有 Master。保存成功后才更新项目的 MSI Mapping 草稿。原始 Config Excel 不自动回写。

## 8. 重新扫描和幂等性

重新扫描先比较 Source Hash、Master revision 和用户修改标记：

- 输入与规则不变：Merge plan 为空，输出语义和 Sheet 命名不变。
- 新增来源：只增加候选，不覆盖既有人工修改。
- 删除/移动来源：映射标记失效，保留 Master 内容并要求重新定位或确认删除。
- 来源内容变化：显示 Diff；用户选择保留 Master、采用新来源或逐项合并。
- Master 本身不得再次被扫描为原始来源。

## 9. Core 兼容

Core 的 MSI 行解析、Header 别名、Width/Direction/Default/Power Domain 语义保持不变。UI-2 通过明确的 Workbook + Sheet + PIN_NAME Column Mapping 将 Master Sheet 交给现有 Parser。Core 不读取 UI 控件状态，也不引入第二套信号归一化算法。

## 10. 异常代码

- `MSI_SOURCE_READ_FAILED`
- `MSI_SOURCE_CHANGED_DURING_MERGE`
- `MSI_SHEET_INVALID`
- `MSI_SHEET_NAME_INVALID`
- `MSI_SHEET_NAME_CONFLICT`
- `MSI_MODULE_SOURCE_AMBIGUOUS`
- `MSI_PIN_COLUMN_AMBIGUOUS`
- `MSI_MASTER_USER_CONFLICT`
- `MSI_MAPPING_CONFLICT`
- `MSI_MASTER_SAVE_FAILED`
- `MSI_MASTER_RECOVERY_REQUIRED`

用户可见信息使用中文并包含来源文件、Sheet、Module、失败阶段和恢复建议。

## 11. UI-2 实施清单

- [ ] Source/Sheet/Master/Mapping dataclass 与版本化 manifest
- [ ] 只读递归扫描、源 Hash 和 Master 排除规则
- [ ] Merge plan、命名器、冲突分类和稳定 ID
- [ ] Merge Preview 与人工 Mapping
- [ ] Master 编辑、Diff、重新扫描和三方冲突
- [ ] staging、备份、原子提交和中断恢复
- [ ] Config Mapping 单一事实源适配
- [ ] Excel 格式与 Core Parser 语义往返测试
- [ ] 所有第 12 节测试由 PENDING 转为实际 PASS/FAIL

## 12. 验收测试

正式用例包括：一个 Excel/一个 Sheet、一个 Excel/多 Sheet、多 Excel/单 Sheet、多 Excel/多 Sheet、同名相同数据、同名不同数据、不合法名称、超过 31 字符、有效与非 MSI 混合、Module 同名/异名、多候选、重新导入、Master 人工修改、保存失败、中断恢复、重复 Merge 幂等、Source_Info 追溯、Master/Config Mapping 一致性、原始 MSI Hash 不变。

这些用例在 UI-1.2 统一标记 `PENDING (UI-2)`，不得计入当前功能 PASS。
