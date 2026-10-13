from __future__ import annotations


TEXT = {
    "app_subtitle": "IBIS 自动化配置工具 · UI 阶段 1.2.1 验收修订",
    "home": "项目首页",
    "back_to_start": "← 返回启动首页",
    "new_project": "新建项目",
    "import_config": "导入 Config Excel",
    "open_project": "打开项目",
    "remove_recent": "从列表移除",
    "delete_project": "删除项目",
    "close_project": "关闭项目",
    "save_config": "保存项目",
    "input_check": "输入检查",
    "config": "参数配置",
    "input_files": "输入文件",
    "t2b_templates": "T2B 模板",
    "results": "生成结果",
    "monitor": "任务监控",
    "log": "运行日志",
    "about": "关于软件",
    "advanced": "高级设置",
}


TOOLTIPS = {
    "new_project": "新建项目：创建一个不依赖 Excel 的项目入口。",
    "import_config": "导入 Config Excel：只读加载工作簿，不会覆盖原文件。",
    "open_project": "打开项目：从可读的项目列表中选择已经保存的软件项目。",
    "remove_recent": "仅从最近项目列表移除，不删除项目文件或任何输入文件。",
    "delete_project": "将软件工作区中的项目移入回收区，不删除原始 Config Excel、MSI、SPF 或 Model。",
    "close_project": "关闭当前项目并返回启动首页，不会删除任何项目或输入文件。",
    "save_config": "检查并保存当前软件项目中的修改，不会修改原始 Config Excel。",
    "input_check": "输入检查：重新扫描并检查 MSI、SPF 和 Model 来源。",
    "home": "返回项目首页：保留当前项目和未保存的编辑草稿。",
    "back_to_start": "关闭当前项目并返回启动首页；如有未保存修改会先询问。",
}
