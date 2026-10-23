"""Review and conservative validation of the common project draft."""
from __future__ import annotations
import difflib
import re
from .errors import ProjectValidationError

SECTIONS = {'roots': '第 1 节 路径', 'modules': '第 2 节 模块', 'corners': '第 3 节 工艺角', 'voltage_order': '第 3 节 供电域', 'simulation_options': '第 4 节 仿真选项', 'aliases': '第 5 节 引脚映射', 'appends': '第 6 节 电路追加', 'templates': '第 7 节 模板映射', 'template_selections': '第 7 节 模板映射', 'overrides': '第 8 节 信号值覆盖', 'attribute_overrides': '第 9 节 属性覆盖', 'msi_mappings': '第 10 节 MSI 映射', 'working_templates': '模板正文', 'template_sources': '模板来源'}


def changes(before, after, path=(), context=''):
    result = []
    if before == after:
        return result
    if isinstance(before, dict) and isinstance(after, dict):
        scope = ' / '.join(str(after.get(k, before.get(k, ''))) for k in ('module', 'direction', 'corner') if after.get(k, before.get(k))) or context
        for key in dict.fromkeys([*before, *after]):
            result += changes(before.get(key), after.get(key), (*path, str(key)), scope)
    elif isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            result += changes(before[index] if index < len(before) else None, after[index] if index < len(after) else None, (*path, f'第 {index + 1} 行'), context)
    else:
        value = after if isinstance(after, dict) else before
        if isinstance(value, dict):
            context = ' / '.join(str(value[k]) for k in ('module', 'direction', 'corner') if k in value) or context
        section = next((SECTIONS[key] for key in path if key in SECTIONS), '项目设置')
        detail = ''
        if isinstance(before, str) and isinstance(after, str) and ('\n' in before or '\n' in after):
            detail = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='保存前', tofile='草稿'))
        result.append(dict(section=section, scope=context, field=' / '.join(path), old=before, new=after, action='新增' if before is None else ('删除' if after is None else '修改'), detail=detail))
    return result


def append_diagnostics(body, known_nodes=()):
    """Check only unambiguous primitive records; leave full SPICE parsing to tools."""
    messages, instances = [], set()
    scope = "global"
    conditional = False
    for index, line in enumerate(body.splitlines(), 1):
        stripped = line.strip()
        if stripped.casefold().startswith('.subckt '):
            scope = stripped.casefold()
        elif stripped.casefold().startswith('.ends'):
            scope = 'global'
        elif stripped.casefold().startswith(('.if', '.else')):
            conditional = True
        if not stripped or stripped.startswith(('*', '+', '.')):
            continue
        parts = stripped.split()
        name = parts[0].casefold()
        if (scope, name) in instances:
            messages.append(('Warning' if conditional else 'Error', f'第 {index} 行实例名重复：{parts[0]}'))
        instances.add((scope, name))
        if name[:1] in {'r', 'c', 'l', 'v', 'i'}:
            if len(parts) < 4:
                messages.append(('Warning', f'第 {index} 行元件字段较少，请检查语法：{stripped}'))
            elif known_nodes:
                unknown = [node for node in parts[1:3] if node.casefold() not in {str(n).casefold() for n in known_nodes} | {'0', 'gnd'}]
                if unknown:
                    messages.append(('Warning', f"第 {index} 行包含内部或未确认节点：{', '.join(unknown)}"))
        else:
            messages.append(('Warning', f'第 {index} 行采用扩展语法，仅保留原文，请人工检查'))
    return messages


def validate_tables(payload, pin_provider=None):
    aliases = payload['aliases']
    for i, row in enumerate(aliases):
        if any(c.isspace() for c in row['alias']):
            raise ProjectValidationError('PIN_ALIAS_INVALID', '引脚别名不能包含空白字符')
        for other in aliases[:i]:
            overlap = row['direction'].upper() == other['direction'].upper() or 'BOTH' in {row['direction'].upper(), other['direction'].upper()}
            if row['module'].casefold() == other['module'].casefold() and overlap and (row['alias'].casefold() == other['alias'].casefold() or row['original_pin'].casefold() == other['original_pin'].casefold()):
                raise ProjectValidationError('PIN_ALIAS_DUPLICATE', f"模块 {row['module']} 存在重叠作用域的重复引脚或别名：{row['alias']}")
        if pin_provider:
            pins = pin_provider(row['module'], 'DRV' if row['direction'].upper() == 'BOTH' else row['direction'].upper())
            if pins and row['original_pin'].casefold() not in {pin.casefold() for pin in pins}:
                raise ProjectValidationError('PIN_ALIAS_REFERENCE_INVALID', f"模块 {row['module']} 的原始引脚不存在：{row['original_pin']}")
    for module in payload['modules']:
        for direction in ('DRV', 'RCV'):
            body = '\n'.join(row['body'] for row in payload['appends'] if row['module'].casefold() == module['name'].casefold() and row['direction'].upper() in {direction, 'BOTH'})
            errors = [message for level, message in append_diagnostics(body) if level == 'Error']
            if errors:
                raise ProjectValidationError('CKT_APPEND_DUPLICATE', '；'.join(errors))
    seen = set()
    for row in payload['attribute_overrides']:
        key = (row['module'].casefold(), row['signal'].casefold(), row['attribute'].upper())
        if key in seen:
            raise ProjectValidationError('MSI_ATTRIBUTE_CONFLICT', f"模块 {row['module']} 信号 {row['signal']} 的属性覆盖重复")
        seen.add(key)
