# IBIS Automation 0.4.1

本版修复 0.4.0 中“缺少工作模板导致生成停止、任务仍显示等待”的故障，简化参数编辑与模板检查。

## 使用流程

1. 打开已有项目或导入 Config Excel。
2. 在参数配置内展开需要的分区。Voltage Domain、Calibration 可以直接修改；Tr/Tf 与 MAX/TYP/MIN 横向排列，明确显示所属模块。
3. 左侧选择 Module / Direction / Ron。T2B 模板页显示当前配置填参后的结果；未保存修改会明确标注，变化行标黄。预览不是上次输出文件。
4. 通常直接保存并生成，无需创建工作模板。只有需要定制模板结构时点击“修改模板”，左侧编辑模板原文、右侧查看同一 Case 的填参结果；“保存模板”会同时保存当前项目配置，“取消”不创建副本。
5. 点击生成选中或全部任务；未保存时提示保存并生成。任务结束后查看每个 Case 的状态、文件和原因。

## 行为与兼容性

- 原有自定义工作模板优先，继续读取 0.4.0 项目 Schema 2；无自定义时直接使用所选母模板。
- 新保存的自定义模板采用版本文件，项目引用随 project.json 原子保存；失败不覆盖旧版本。旧版工作模板路径保持可读。
- 同模块同方向的 Ron 共用模板；不同模块和方向分别保存。
- 预览和实际生成使用 Core 同一个渲染函数。预览只读、不生成 Case；输入不完整时显示具体错误。
- 只检查选中任务所需的模板。未选中的缺失工作模板不再阻塞本次生成。
- 任务事件更新原任务行；输入失败、后台异常、取消均进入终态，不残留等待行。
- 生成期间禁用配置编辑和重复提交；关闭窗口会请求取消并要求等待当前 Case 结束。
- 未生成的空路径文件数为 0；查看文件及 Golden 按钮仅在对应输出可用时启用。
- Golden Diff 与 Core 使用同样的路径归一化，避免本地 Root 导致假差异。
- 取消“上移/下移”按钮，保持原有记录顺序，新行追加。
- 生成仍止于 READY_FOR_T2B；不执行真实 T2B/LSF，不生成 .ibs 或 C_comp_view。

## 验证

新增 Headless 回归覆盖直接使用母模板、DRV/RCV 多 Ron、填参预览与实际输出一致、草稿预览无副作用、未选中模板隔离、错误终态、模板保存回滚、STALE、取消及空路径计数。

新增真实 Tk 回归覆盖折叠后输入保留、Voltage/Calibration 原位编辑、生成按钮单行终态、7 文件输出、缺失模板和后台异常终止、模板取消与保存刷新。Linux 使用 DISPLAY/Xvfb；未配置 DISPLAY 时明确跳过 GUI 测试，不计作 GUI PASS。Windows 原生 Runner 同时执行这些 GUI 回归。

原有 Unit/Template/Robustness、冻结 Acceptance 和 Golden Case 001 继续执行。冻结输入、母模板、Golden 和验收标准保持原样。

## 打包与人工验收

Windows 原生 PyInstaller 输出 `IBIS_Automation_Windows_0_4_1.zip`；解压后双击 `IBIS_Automation.exe`。无需本地 Python。

Linux 入口：`PYTHONPATH=src python3 -m ibis_ui`。

CI 还会验证打包 EXE 的 `--check`：无需工作副本即可生成 Golden Case 001，且填参预览逐字等于写出的 T2B。真实窗口自动 smoke 与 headless 结果分别报告。

仍需用户 Windows 实机确认显示缩放、中文字体、常用工程路径及交互体验。自动窗口测试不能替代人工视觉验收。
