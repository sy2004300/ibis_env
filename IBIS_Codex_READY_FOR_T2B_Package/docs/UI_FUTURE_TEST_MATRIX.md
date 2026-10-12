# UI-2 / UI-3 / UI-4 正式测试矩阵

状态说明：`PASS` 表示当前代码已执行通过；`PENDING` 表示对应阶段尚未实现，不计入 UI-1.2 PASS。

## UI-2：Excel 与 MSI Master

| ID | 场景 | 关键断言 | UI-1.2 状态 |
|---|---|---|---|
| MSI-M01 | 一个 Excel / 一个 Sheet | 生成一份可追溯 Master Sheet | PENDING |
| MSI-M02 | 一个 Excel / 多 Sheet | 所有有效 Sheet 独立进入预览 | PENDING |
| MSI-M03 | 多 Excel / 单 Sheet | 来源 Workbook 均保留 | PENDING |
| MSI-M04 | 多 Excel / 多 Sheet | Module Mapping 唯一且可复现 | PENDING |
| MSI-M05 | 同名 Sheet / 相同数据 | 去重但保留全部来源 | PENDING |
| MSI-M06 | 同名 Sheet / 不同数据 | 阻止静默覆盖 | PENDING |
| MSI-M07 | 不合法 Sheet 名 | 稳定规范化并展示变更 | PENDING |
| MSI-M08 | 名称超过 31 字符 | 截断加稳定 Hash | PENDING |
| MSI-M09 | 有效/非 MSI Sheet 混合 | 仅有效 Sheet 默认入选 | PENDING |
| MSI-M10 | Module 与 Sheet 同名 | 精确自动匹配 | PENDING |
| MSI-M11 | Module 与 Sheet 异名 | 进入人工映射 | PENDING |
| MSI-M12 | 一个 Module 多候选 | 不猜测，保存前阻止 | PENDING |
| MSI-M13 | 重新导入 MSI | 显示新增/删除/变化 Diff | PENDING |
| MSI-M14 | Master 已人工修改 | 三方冲突，不静默覆盖 | PENDING |
| MSI-M15 | Master 保存失败 | 旧 Master 完整可恢复 | PENDING |
| MSI-M16 | Merge 中断恢复 | staging 可清理/恢复 | PENDING |
| MSI-M17 | 重复执行 | 输出语义幂等 | PENDING |
| MSI-M18 | Source_Info | 路径、Sheet、Hash 可追溯 | PENDING |
| MSI-M19 | Master/Config Mapping | 单一映射保持一致 | PENDING |
| MSI-M20 | 原始 MSI Hash | Merge 前后完全一致 | PENDING |
| XLS-01 | Export Standard Config | Core Parser 语义往返 | PENDING |
| XLS-02 | Export As | 非目标 Sheet/样式尽量保持 | PENDING |
| XLS-03 | Write Back | 明确确认、备份、原子替换 | PENDING |

## UI-3：T2B 工作模板与 Library

| ID | 场景 | 关键断言 | UI-1.2 状态 |
|---|---|---|---|
| T2B-01 | 四份母模板 | 类型和必需令牌完整 | PENDING |
| T2B-02 | 模块独立工作模板 | 项目/模块之间不串改 | PENDING |
| T2B-03 | DRV/RCV 隔离 | 两方向内容独立 | PENDING |
| T2B-04 | 多 Ron | 共用模块模板，按 Case 动态展开 | PENDING |
| T2B-05 | 完整文本编辑 | Undo/Redo/Search/结构校验 | PENDING |
| T2B-06 | Case Preview | 完整展开但不落盘 | PENDING |
| T2B-07 | 历史归档 | 只读、版本、校验和 | PENDING |
| T2B-08 | Library 版本管理 | 不覆盖旧版本 | PENDING |
| T2B-09 | 项目模块改名映射 | 显式映射且重新求值动态字段 | PENDING |
| T2B-10 | V1 → V2 继承 | V1 不变，V2 使用新 SPF/Config | PENDING |
| T2B-11 | Config 共享参数 | 不产生第二份冲突真相 | PENDING |

## UI-4：生成、结果和监控

| ID | 场景 | 关键断言 | UI-1.2 状态 |
|---|---|---|---|
| GEN-01 | Generate Selected | 只创建选中有效 Case | PENDING |
| GEN-02 | Generate All | 所有有效 Case 进入任务 | PENDING |
| GEN-03 | Case 隔离 | 单 Case 失败不影响其它 Case | PENDING |
| GEN-04 | Golden PASS | 只对真实 Golden 一致显示 PASS | PENDING |
| GEN-05 | UNVALIDATED | 无 Golden 的结构通过不冒充 PASS | PENDING |
| GEN-06 | FAIL | 显示结构化中文错误 | PENDING |
| GEN-07 | STALE | 上游变化使相关 Case 过期 | PENDING |
| GEN-08 | 覆盖保护 | 显示范围并确认，失败保留旧结果 | PENDING |
| GEN-09 | 文件预览 | 只读浏览、搜索、复制完整路径 | PENDING |
| GEN-10 | 失败重试 | 仅重提失败任务 | PENDING |
| GEN-11 | 进度显示 | 事件与实际任务一致 | PENDING |
| GEN-12 | 取消/异常 | 状态可恢复，不阻塞 Tk 主线程 | PENDING |

## 当前自动化基线

UI-1.2 当前自动测试覆盖 Project 创建、Config 导入、多模块、模块编辑隔离、一键保存、重载、保存失败回滚、未保存保护、MSI 多 Excel/多 Sheet/歧义、SPF Corner/缺失/重复/Pin 不一致、Model 文件存在性、内置模板、跨平台 JSON、原始 Excel 不变。未来功能只有矩阵和 Fixture 设计，均不计为 PASS。
