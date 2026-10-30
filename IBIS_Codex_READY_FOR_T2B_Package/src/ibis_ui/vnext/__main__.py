"""Headless entry, sharing importer, precheck, store and generation with Tk UI."""
from __future__ import annotations
import argparse
from pathlib import Path
from ..controller import ProjectController
from ..project_store import ProjectStore
from ..errors import UIProjectError


def main():
    parser = argparse.ArgumentParser(description='VNext 配置预处理与 Stage 1 生成')
    parser.add_argument('command', choices=('preprocess', 'generate'))
    parser.add_argument('--input', type=Path, required=True, help='极简 Input 或完整 Config Excel')
    parser.add_argument('--workspace', type=Path, required=True, help='所有自动输出的项目工作区')
    parser.add_argument('--output', type=Path, help='可选另存完整 Excel（即使配置不完整）')
    args = parser.parse_args()
    try:
        controller = ProjectController(ProjectStore(args.workspace))
        project = controller.import_excel(args.input)
        if 'vnext' not in project.config:
            parser.error('此入口用于 VNext 格式；旧版 Config 请使用原有 ibis_auto 入口')
        path = controller.save_configuration()
        if args.output:
            controller.export_config(args.output)
        data = controller.active_config['vnext']
        for issue in data['issues']:
            print('%s [%s] %s/%s/%s %s：%s' % (issue['severity'], issue['code'], issue['module'], issue['direction'], issue['corner'], issue['field'], issue['message']))
        print('项目已保存：%s' % path)
        if args.command == 'generate':
            result = controller.generate_cases()
            for row in result.cases:
                print('%s %s：%s' % (row.key, row.status, row.message))
            return 0 if result.ready else 1
        print('预处理完成；阻断项 %d；配置可以导出。' % sum(r['severity']=='BLOCKING' for r in data['issues']))
        return 0
    except (UIProjectError, OSError, ValueError) as exc:
        print('错误 [%s]：%s' % (getattr(exc, 'code', 'VNEXT_ERROR'), exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
