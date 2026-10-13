# IBIS Automation UI Phase 1.2 设计说明

## 1. 范围

UI-1.2 将 UI-1.1 的参数页调整为工程师工作流入口，不改变 Core Engine、Project Schema、Config Schema、T2B renderer 或 READY_FOR_T2B 验收语义。

本阶段实现项目首页、统一中文操作、单入口保存、输入来源摘要、最近项目和正式测试规划。Excel 双向写回与 MSI Merge 属于 UI-2；T2B 工作模板和历史库属于 UI-3；生成、结果和监控属于 UI-4。

## 2. 页面和导航

打开项目后的内部页签顺序：

1. 项目总览
2. 参数配置
3. 输入文件
4. T2B 模板
5. 生成结果
6. 任务监控
7. 运行日志

应用级“项目首页”和项目内部页面职责分离：

- 项目首页只展示一次“新建项目”和“打开项目”，不提供 Config Excel 导入。“打开项目”同时负责打开选中的最近项目；未选择最近项目时允许浏览 `project.json`。
- 项目内部不展示“新建项目”或“打开项目”。顶部提供“返回”、导入 Config Excel、保存项目、删除项目、高级设置和关于软件。
- “返回”关闭当前项目视图并回到项目首页；有未保存修改时必须选择保存并返回、不保存并返回或取消。
- Config Excel 只能导入当前项目。导入保留用户设置的项目名称、Project UUID 和创建时间，更新内部配置且不回写原始 Excel。

项目内部的“项目总览”根据当前 Project、输入扫描报告和保存状态计算 IO Top、DRV/RCV 分支、Case、MSI、SPF、Model、当前阶段及推荐下一步。“编辑参数（含 VDDQ/VDD）”提供明确的参数页入口。

“参数配置”的 Corner / Voltage 表允许修改现有 Voltage Domain（包括 VDDQ、VDD、VSS）的 MAX/TYP/MIN 值。修改进入 Project Draft，经“保存项目”验证并写入 ProjectStore；Process、Temperature 和 Voltage Domain 名称仍保持只读。Section 1–10 的其余全量编辑继续属于 UI-2。

## 3. 状态模型

内部状态保持英文枚举，界面通过统一映射显示中文：

- 配置：`UNMODIFIED / DIRTY / SAVED / ERROR`
- 输入来源：`UNSCANNED / FOUND / MATCHED / MATCH_FAILED`
- 生成：`NOT_GENERATED / QUEUED / RUNNING / PASS / UNVALIDATED / FAIL / STALE / CANCELLED`

MSI/SPF 匹配只属于输入来源状态。UI-1.2 不开放生成，因此 Case 一律显示“未生成”，不会把“已匹配”错误显示为“通过”。

## 4. 保存事务

普通界面只暴露“保存配置”。Controller 内部仍保持 Draft、Validate、Apply、Save 的职责边界：

1. 深拷贝当前草稿为候选配置。
2. 对候选配置执行 Schema、Root 和模板资源验证。
3. 创建独立 staged `ProjectDocument`，不修改当前生效快照。
4. `ProjectStore` 使用临时文件、`fsync` 和原子替换写入 `project.json`。
5. 写入成功后才用 staged snapshot 替换 Controller 的生效项目并清除 DIRTY。

验证或存储失败时，旧生效快照不变、当前 UI 草稿不丢失、原始 Config Excel 不被写入。旧的 `apply_changes()` 和 `save_project()` API 保留给兼容测试及高级开发流程，普通 UI 不展示 Apply 按钮。

## 5. 输入文件页面

### MSI 信号表

默认表只展示 `IO Top → MSI 文件 → Sheet → PIN_NAME Column` 映射。摘要展示 Root、Excel、Sheet、IO Top 和成功/失败数。“查看扫描详情”单独展示原始 Excel/Sheet，不再与 Module Mapping 混排。扫描支持 Root 下递归多 Excel 和单 Excel 多 Sheet，歧义不猜测。

### SPF 网表

按 IO Top 和 MAX/TYP/MIN 展示文件、TOP_SUBCKT、Pin 数量及匹配状态。缺失、重复和各 Corner Pin List 不一致均显示匹配失败。

### Model Library

按当前 SPICE 类型检查 `rbd.lib`、`cap.lib`、`mos_var.lib` 是否存在。此检查不运行仿真，不显示“电气模型验证通过”。

所有来源扫描均为只读，不修改 MSI、SPF、Model 或 Config Excel。

## 6. 最近项目

`ui_state.json` schema 升级为兼容旧 `recent_project_id` 的最近项目列表，最多保留十条。每条记录使用稳定 `project_id`，显示项目名、最近使用时间、配置路径和可用状态。路径失效时保留记录并提供中文错误，不导致软件启动崩溃。

## 7. 跨平台和打包

Windows EXE 与 Linux Python 共用 `src/ibis_ui/` 和 `src/ibis_auto/`。路径由 `pathlib` 处理；内置资源继续通过 `ResourceResolver` 解析。Windows 包名为 `IBIS_Automation_Windows_UI1_2`，版本为 `0.1.2`。

## 8. 不在本阶段实现

- Config Section 1–10 全量编辑、Excel Export/Write Back、MSI Master Merge
- 可编辑模块 T2B 工作模板、Case Preview、历史模板库
- Generate Selected/All、真实 T2B、LSF、任务监控、C_comp_view

未开放页面只说明阶段边界，不执行模拟操作，也不返回虚假 PASS。
