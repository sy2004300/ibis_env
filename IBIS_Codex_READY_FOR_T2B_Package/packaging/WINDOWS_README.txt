IBIS Automation Windows UI-1
============================

运行方式
--------
1. 将整个 IBIS_Automation_Windows_UI1 文件夹完整解压。
2. 双击 IBIS_Automation.exe。
3. 不需要安装 Python，也不要单独移动 EXE；_internal 是运行所需目录。

版本信息
--------
启动页和 About 页面会显示 App Version、Git Commit 与 Platform。
Windows EXE 与 Linux Python 显示相同 Git Commit 时，代表来自同一套源码。

项目与日志目录
--------------
默认 Workspace：%LOCALAPPDATA%\IBIS_Automation\workspace
项目数据：Workspace\projects\<project_id>\project.json
启动及异常日志：Workspace\logs\ibis_automation.log

软件不会要求 EXE 所在目录可写，也不会自动覆盖导入的 Excel。
如项目来自另一台电脑且 MSI/SPF/Model/Template Root 已失效，请在 Config 页面重新指定路径，再点击 Apply Changes。

内置资源
--------
_internal\resources\templates\t2b 中包含只读 T2B 母模板。
_internal\resources\inputs 中仅包含仓库提供的 synthetic Demo Config/MSI/SPF/Model 数据。
可使用内置 Demo Config 进行界面测试：
_internal\resources\inputs\config\ibis_config.xlsx

命令行验收（PowerShell）
-----------------------
Start-Process .\IBIS_Automation.exe -ArgumentList '--check --check-report check.json' -Wait
检查生成的 check.json，其中 status 应为 PASS、mode 应为 HEADLESS。

当前阶段边界
------------
本包是 UI Phase 1。Excel Export/Write Back、T2B Library、Generate、Monitor、真实 T2B、LSF 和 C_comp_view 尚未实现，相关入口会明确禁用。
