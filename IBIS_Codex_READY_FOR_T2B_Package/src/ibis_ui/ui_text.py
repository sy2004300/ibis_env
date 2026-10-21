from __future__ import annotations


TEXT = {
    "app_subtitle": "IBIS 自动化配置工具 · 全流程 0.4.2",
    "home": "项目总览",
    "back_to_start": "返回",
    "new_project": "新建项目",
    "import_config": "导入 Config Excel",
    "open_project": "打开项目",
    "remove_recent": "从列表移除",
    "delete_project": "删除项目",
    "close_project": "返回",
    "save_config": "保存项目",
    "export_config": "导出 Config Excel",
    "input_check": "输入检查",
    "config": "参数配置",
    "input_files": "输入文件",
    "t2b_templates": "T2B 模板",
    "generate": "生成 READY_FOR_T2B",
    "results": "检查生成文件",
    "monitor": "任务监控",
    "log": "运行日志",
    "about": "关于软件",
    "advanced": "高级设置",
}


TOOLTIPS = {
    "new_project": "新建项目：创建一个不依赖 Excel 的项目入口。",
    "import_config": "导入 Config Excel 到当前项目：保留项目名称和 UUID，不会覆盖原 Excel。",
    "open_project": "打开项目：打开选中的最近项目；未选择时可浏览 project.json。",
    "remove_recent": "仅从最近项目列表移除，不删除项目文件或任何输入文件。",
    "delete_project": "将软件工作区中的项目移入回收区，不删除原始 Config Excel、MSI、SPF 或 Model。",
    "close_project": "返回项目首页；如有未保存修改会先询问是否保存。",
    "save_config": "检查并保存当前软件项目中的修改，不会修改原始 Config Excel。",
    "export_config": "将当前 ProjectStore 的 Section 1～10 另存为新的 Config Excel。",
    "input_check": "输入检查：重新扫描并检查 MSI、SPF 和 Model 来源。",
    "home": "查看当前项目总览。",
    "back_to_start": "返回项目首页；如有未保存修改会先询问是否保存。",
}
