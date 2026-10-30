from __future__ import annotations
import copy
import re
from ..errors import ProjectValidationError

VERSION = 2
CORNERS = ('MAX', 'TYP', 'MIN')
STATES = ('AUTO_MATCH', 'MANUAL', 'UNRESOLVED', 'STALE')
SOURCES = {'Model Source': 'model', 'MSI Source': 'msi', 'SPF Source': 'spf', 'T2B Source': 'template'}


def empty():
    return dict(schema_version=VERSION, sources={key: '' for key in SOURCES.values()}, modules=[],
                corners={c: {f: '' for f in ('process', 'temperature', 'tr', 'tf', 'spf_key')} for c in CORNERS},
                voltages=[], signals=[], pins=[], appends=[], overrides=[], msi_mappings=[],
                provenance={}, resolved={}, issues=[])


def validate_shape(data):
    if not isinstance(data, dict) or data.get('schema_version') not in (1, VERSION):
        raise ProjectValidationError('VNEXT_SCHEMA', '不支持的 VNext 配置版本')
    for key in ('sources', 'corners', 'provenance'):
        if not isinstance(data.get(key), dict):
            raise ProjectValidationError('VNEXT_SCHEMA', '配置字段格式错误：' + key)
    for key in ('modules', 'voltages', 'signals', 'pins', 'appends', 'overrides', 'msi_mappings'):
        if not isinstance(data.get(key), list) or any(not isinstance(r, dict) for r in data[key]):
            raise ProjectValidationError('VNEXT_SCHEMA', '配置表格式错误：' + key)
    # Incomplete values are intentionally valid storage/export data.


def parse_rons(raw):
    pieces = re.split(r'[,，;；、\s]+', str(raw).strip())
    if not pieces or pieces == ['']:
        raise ValueError('Ron 必须填写正整数列表，例如 30,34,40')
    if any(not p.isdigit() or int(p) <= 0 for p in pieces):
        raise ValueError('Ron 只允许正整数，以逗号、分号或空格分隔')
    return list(dict.fromkeys(int(p) for p in pieces))


def directions(module):
    value = module.get('generate_type', '').upper()
    return ('DRV', 'RCV') if value == 'BOTH' else ((value,) if value in ('DRV', 'RCV') else ())


def payload(data):
    """Storage facade for the existing project/tree; generator uses adapter only."""
    from ..models import empty_config_payload
    result = empty_config_payload()
    result['vnext'] = copy.deepcopy(data)
    result['roots'].update(data['sources'])
    for row in data['modules']:
        try:
            rons = parse_rons(row.get('ron', ''))
        except ValueError:
            rons = []
        result['modules'].append(dict(name=row.get('name', ''), generate_type=row.get('generate_type', ''),
            impedances=rons, ibis_io_voltage_domain=row.get('io_domain', ''), ibis_vih_voltage_domain=row.get('vih_domain', ''),
            tr={c: data['corners'][c].get('tr', '') for c in CORNERS}, tf={c: data['corners'][c].get('tf', '') for c in CORNERS}))
    for c in CORNERS:
        result['corners'][c].update({f: data['corners'][c].get(f, '') for f in ('process', 'temperature', 'spf_key')})
        result['corners'][c]['voltages'] = {r.get('domain', ''): r.get(c, '') for r in data['voltages'] if r.get('domain')}
    result['voltage_order'] = [r['domain'] for r in data['voltages'] if r.get('domain')]
    return result
