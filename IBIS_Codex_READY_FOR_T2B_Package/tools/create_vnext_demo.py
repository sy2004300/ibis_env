#!/usr/bin/env python3
"""Create only synthetic VNext inputs under an explicitly selected directory."""
from __future__ import print_function
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from vnext_fixture import fixture, confirmed, input_book
from ibis_ui.vnext.excel import write


def main():
    parser = argparse.ArgumentParser(description='创建 VNext 合成演示数据，不是实际 PDK')
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.expanduser().resolve() / 'vnext-synthetic-demo'
    if root.exists():
        parser.error('演示目录已存在，为避免覆盖，请选择其他 Workspace：' + str(root))
    root.mkdir(parents=True)
    data = fixture(root, se=True)
    source = input_book(data, root / 'Config_Input.xlsx')
    generated = write(confirmed(data), root / 'Config_Generated.xlsx')
    print('仅限合成演示，库文件不包含真实器件模型。')
    print('极简输入（导入后需人工确认 ipadt/ipadc/ipad）：' + str(source))
    print('已填写映射的完整演示配置：' + str(generated))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
