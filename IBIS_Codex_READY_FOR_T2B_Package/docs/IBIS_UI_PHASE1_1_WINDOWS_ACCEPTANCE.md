# IBIS Automation UI Phase 1.1 — Windows 实机验收清单

适用版本：`0.1.1`。自动化测试能确认数据、资源和窗口创建，但不能替代人工视觉验收。

## 1. 安装与启动

- 解压 `IBIS_Automation_Windows_UI1_1.zip`，确认同一目录内存在 `IBIS_Automation.exe`、`_internal/` 和 `README.txt`。
- 双击 EXE，确认无需安装 Python，窗口标题为 `IBIS Automation 0.1.1 — IBIS 自动化配置工具`。
- About 页确认 App Version、Git Commit、Platform 与本次构建一致。
- 确认 `%LOCALAPPDATA%\IBIS_Automation\workspace\logs\ibis_automation.log` 可创建。

## 2. 显示、字体与窗口缩放

- 在 1366×768 和 1920×1080 分辨率下分别打开、最大化、还原窗口。
- Windows 显示缩放分别检查 100%、125%、150%；中文标签无乱码、无遮挡、无明显字体混用。
- 拖动左右分隔线，确认 Case Tree 和右侧页面都能正常调整宽度。
- 确认顶部项目栏及底部 Apply Changes / Save Project 始终可见。

## 3. Config 滚动

- 导入 Demo Config，进入 Config 页，用滚轮从 Section 1 滚动到 Section 10 预留区。
- 拖动纵向滚动条、横向滚动条；改变窗口尺寸后再次检查。
- 鼠标位于 Corner 表格、左侧任务树和 T2B 文本时分别滚动，确认滚动作用于当前控件，不互相抢占。
- 编辑 `Tr TYP`，滚动离开再返回，确认草稿值仍在且项目状态为 DIRTY。

## 4. 多模块任务树

- 使用包含 IO_DIFF、IO_SE、OUTC、INSE 的测试项目，确认树层级为 `IO Top → DRV/RCV → Ron`。
- 展开/折叠每个模块；搜索 `IO_`、`OUTC` 和不存在的名称。
- 核对模块数和 Case 数摘要。
- 在不同模块间修改不同字段，来回切换，确认草稿不串位、不丢失。
- 同一模块需要 DRV+RCV 时应使用一行 `Generate Type=BOTH`；同名 DRV/RCV 分行应明确报重复模块错误。

## 5. Template、MSI 与 SPF

- Config 普通页面不要求填写 Template Root。
- T2B 页显示四份母模板和 `_t2b_config.ini`，选择每项后能只读查看实际内容。
- 核对当前模块的 DRV/RCV Template Mapping。
- 在高级设置中选择外部 Template Root、清空并恢复内置模板；错误路径必须明确报错。
- MSI Sources 页显示 Excel、Sheet、Pin Name Column 及模块匹配结果；多重匹配不得静默选择。
- SPF Match 页逐模块显示 MAX/TYP/MIN 文件、完整路径、TOP_SUBCKT 和 Pin 数；缺失或重复匹配必须显示中文错误。

## 6. 项目状态与数据保护

- 修改配置后确认 `DIRTY → Apply Changes → APPLIED / 未保存 → Save Project → SAVED`。
- 保存后关闭并重新打开，确认项目和选中模块数据可恢复。
- 未 Apply 时关闭，分别验证取消、丢弃、Apply 并保存三个分支。
- 对导入前后的 Config Excel 计算文件哈希，确认原文件完全不变。

## 7. 阶段边界

- Export Excel、T2B 工作模板编辑/历史库、Generate、Monitor 保持禁用或明确标记后续阶段。
- 不应启动真实 T2B、LSF 或仿真，也不应生成 `C_comp_view`。
