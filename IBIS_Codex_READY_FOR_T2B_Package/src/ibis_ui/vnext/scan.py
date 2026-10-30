"""Read-only source discovery and precheck. No output or input mutation here."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from ibis_auto.msi import _columns, discover
from ibis_auto.ooxml import read_workbook
from ibis_auto.spf import parse as parse_spf
from ibis_auto.values import parse_logic, impedance_map, signal_bits
from ..configuration_review import append_diagnostics
from ..working_templates import validate_template_text
from .model import VERSION, CORNERS, directions, parse_rons, validate_shape

STRENGTH = {'reg_txslice_pd[3:0]', 'reg_txslice_pu[3:0]'}


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def template_pins(text):
    mode, pins, links, diff = '', [], [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(('|', '*', '#', ';')):
            continue
        header = re.match(r'^\[([^]]+)\]', line)
        if header:
            mode = header.group(1).casefold()
            continue
        parts = line.split()
        if mode == 'pin':
            if parts[0] == '->':
                links.extend(parts[1:])
            elif len(parts) >= 4:
                pins.append(dict(name=parts[0], kind=parts[3] if parts[3].casefold() in ('power', 'gnd', 'dummy') else 'model'))
            else:
                raise ValueError('[Pin] 行格式不完整：' + line)
        elif mode == 'diff pin':
            if len(parts) < 2:
                raise ValueError('[Diff pin] 行格式不完整')
            diff.append(parts[:2])
    names = [p['name'].casefold() for p in pins]
    if not names or len(names) != len(set(names)):
        raise ValueError('模板 [Pin] 为空或包含重复 Pin')
    if any(p.casefold() not in names for pair in diff for p in pair) or any(p.casefold() not in names for p in links):
        raise ValueError('[Diff pin] 或 -> 引用了未定义的 [Pin]')
    return pins, links, diff


def resolve_source(raw, kind, builtin):
    if not raw:
        if kind == 'template':
            return Path(builtin).resolve(), None
        raise ValueError('必需来源尚未填写')
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise ValueError('来源不存在：' + str(path))
    if path.is_dir():
        return path, None
    extension = {'model': '.lib', 'msi': '.xlsx', 'spf': '.spf', 'template': '.t2b'}[kind]
    if path.suffix.casefold() != extension:
        raise ValueError('文件类型错误，要求目录或 ' + extension)
    if kind == 'model' and not all((path.parent / name).is_file() for name in ('rbd.lib','cap.lib','mos_var.lib')):
        raise ValueError('单个 .lib 无法安全推导完整模型库，请指定模型根目录')
    return path.parent, path


def msi_candidates(root, anchor=None):
    candidates = []
    files = [anchor] if anchor else sorted(root.rglob('*.xlsx'))
    for file in files:
        if file.name.startswith('~$') or file.name.casefold() == 'msi_master.xlsx':
            continue
        try:
            sheets = read_workbook(file)
        except Exception:
            continue
        for sheet, rows in sheets.items():
            if not rows or sheet.startswith('_'):
                continue
            header = rows[0]
            norm = lambda s: re.sub('[^a-z0-9]', '', s.casefold())
            columns = [h for h in header if norm(h) in ('pinname', 'name')]
            if not columns:
                continue
            candidates.append(dict(file=str(file.resolve()), sheet=sheet, columns=columns, headers=header))
    return candidates


def precheck(original, builtin):
    validate_shape(original)
    data = copy.deepcopy(original)
    data['schema_version'] = VERSION
    issues, resolved, roots, anchors = [], dict(spf={}, msi={}, templates={}, pdk={}, candidates=[]), {}, {}
    def issue(code, message, section='sources', row=0, field='', module='', direction='', corner='', location='', severity='BLOCKING'):
        issues.append(dict(severity=severity, code=code, message=str(message), section=section, row=row, field=field, module=module, direction=direction, corner=corner, location=str(location)))
    for kind in ('model', 'msi', 'spf', 'template'):
        try:
            roots[kind], anchors[kind] = resolve_source(data['sources'].get(kind, ''), kind, builtin)
        except Exception as exc:
            issue('SOURCE_INVALID', exc, field=kind)
    resolved['roots'] = {key: str(value) for key, value in roots.items()}
    resolved['config_template_root'] = str(Path(builtin).resolve())
    if not (Path(builtin) / '_t2b_config.ini').is_file():
        issue('TEMPLATE_CONFIG', '软件资源缺少 _t2b_config.ini', field='template')
    resolved['anchors'] = {key: str(value) if value else '' for key, value in anchors.items()}
    if data['provenance'].get('notice'):
        issue('IMPORT_NOTICE', data['provenance']['notice'], severity='WARNING')
    if not data['modules']:
        issue('MODULE_MISSING', '请至少填写一个模块', 'modules', field='name')
    for c in CORNERS:
        row = data['corners'][c]
        for field in ('process', 'temperature', 'tr', 'tf', 'spf_key'):
            value = row.get(field, '').strip()
            valid = bool(value)
            if field == 'process':
                valid = value.upper() in ('FF','FS','SF','SS','TT')
            elif field == 'temperature':
                valid = value in ('125', '25', '-40')
            elif field in ('tr', 'tf'):
                match = re.fullmatch(r'(\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+|[fpnumk]s?|s)?', value)
                valid = bool(match) and float(match.group(1)) > 0
            if not valid:
                issue('CORNER_INVALID', '必填项缺失或格式不合法', 'corners', CORNERS.index(c), field, corner=c)
    candidates = msi_candidates(roots['msi'], anchors['msi']) if 'msi' in roots else []
    resolved['candidates'] = candidates
    names = [m.get('name', '').casefold() for m in data['modules']]
    plans = {(d, m.get('topology', '')) for m in data['modules'] for d in directions(m)}
    domains = list(dict.fromkeys(r.get('domain', '') for r in data['voltages'] if r.get('domain')))
    def domain(value):
        if value and value.casefold() not in {d.casefold() for d in domains}:
            domains.append(value)
    newpins, newmsi = [], []
    oldpins = {(r.get('module'), r.get('direction'), r.get('t2b_pin')): r for r in data['pins']}
    if len(oldpins) != len(data['pins']):
        issue('PIN_DUPLICATE', '同一模块/方向的 T2B Pin 重复', 'pins')
    for index, module in enumerate(data['modules']):
        name = module.get('name', '')
        for field in ('name', 'generate_type', 'topology', 'ron'):
            value = module.get(field, '')
            valid = bool(value)
            if field == 'name':
                valid = bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', value)) and names.count(value.casefold()) == 1
            elif field == 'generate_type':
                valid = value in ('DRV', 'RCV', 'BOTH')
            elif field == 'topology':
                valid = value in ('SE', 'DIFF')
            elif field == 'ron':
                try:
                    module['rons'] = parse_rons(value)
                except ValueError:
                    valid = False
            if not valid:
                issue('MODULE_INVALID', '必填项缺失、重复或格式不合法', 'modules', index, field, name)
        spfs, pins, tops, hashes = {}, None, [], {}
        if 'spf' in roots:
            for c in CORNERS:
                key = data['corners'][c].get('spf_key', '')
                matches = [p for p in roots['spf'].rglob('*.spf') if name and key and name.casefold() in p.name.casefold() and key.casefold() in p.name.casefold()]
                if len(matches) != 1:
                    issue('SPF_MATCH', 'SPF 匹配数量为 %d，要求唯一；请调整匹配关键字' % len(matches), 'corners', CORNERS.index(c), 'spf_key', name, corner=c, location=roots['spf'])
                    continue
                path = matches[0].resolve()
                try:
                    top, current = parse_spf(path)
                    if pins is not None and pins != current:
                        issue('SPF_INTERFACE', '各 Corner 的完整 Pin 数量或顺序不一致', 'corners', CORNERS.index(c), 'spf_key', name, corner=c, location=path)
                    pins = current if pins is None else pins
                    tops.append(top)
                    spfs[c] = str(path)
                    hashes[str(path)] = hash_file(path)
                except Exception as exc:
                    issue('SPF_PARSE', exc, 'corners', field='spf_key', module=name, corner=c, location=path)
            if len(set(spfs.values())) != len(spfs):
                issue('SPF_REUSED', '三个 Corner 必须对应三个独立 SPF 文件', 'corners', module=name, field='spf_key')
            if len(set(tops)) > 1:
                issue('SPF_TOP', '各 Corner 的 Top .SUBCKT 名称不一致，不能使用单一拓扑', 'corners', module=name, field='spf_key')
        resolved['spf'][name] = dict(top=tops[0] if tops else '', pins=pins or [], files=spfs, hashes=hashes)
        signals = []
        mapped = next((copy.deepcopy(r) for r in data['msi_mappings'] if r.get('module') == name), dict(module=name, file='', sheet='', column='', status='UNRESOLVED'))
        if sum(r.get('module') == name for r in data['msi_mappings']) > 1:
            issue('MSI_DUPLICATE', '同一模块只能有一个 MSI 映射', 'msi_mappings', len(newmsi), 'file', name)
        if not mapped.get('file') and not mapped.get('sheet'):
            matches = [r for r in candidates if name.casefold() in (Path(r['file']).stem.casefold(), r['sheet'].casefold())]
            if len(matches) == 1 and len(matches[0]['columns']) == 1:
                mapped.update(file=matches[0]['file'], sheet=matches[0]['sheet'], column=matches[0]['columns'][0], status='AUTO_MATCH')
        try:
            if not all(mapped.get(k) for k in ('file', 'sheet', 'column')):
                raise ValueError('MSI 来源未唯一确定，请从候选工作簿/工作表/列选择')
            file = Path(mapped['file'])
            if not file.is_absolute() and 'msi' in roots:
                file = roots['msi'] / file
            file = file.resolve()
            allowed = [r for r in candidates if r['file'] == str(file) and r['sheet'] == mapped['sheet']]
            if not allowed:
                raise ValueError('所选工作簿/工作表不在当前 MSI Source 的有效范围内')
            rows = read_workbook(file).get(mapped['sheet'], [])
            cols = _columns(rows[0], mapped['column'])
            seen = set()
            for row in rows[1:]:
                signal = row[cols['signal_name']] if len(row) > cols['signal_name'] else ''
                if not signal:
                    continue
                if signal.casefold() in seen:
                    raise ValueError('MSI 重复信号：' + signal)
                seen.add(signal.casefold())
                width = row[cols['width']] if len(row) > cols['width'] else ''
                if not re.fullmatch(r'[1-9]\d*(?:\.0+)?', width):
                    raise ValueError('信号 %s 的 WIDTH 非法：%s' % (signal, width))
            current_fp = fingerprint([str(file), hash_file(file), mapped['sheet'], mapped['column']])
            if mapped.get('fingerprint') and mapped['fingerprint'] != current_fp:
                mapped['status'] = 'STALE'
            mapped['current_fingerprint'] = current_fp
            if not mapped.get('fingerprint'):
                mapped['fingerprint'] = current_fp
            if mapped.get('status') not in ('MANUAL', 'AUTO_MATCH', 'STALE'):
                issue('MSI_UNCONFIRMED', 'MSI 选择尚未确认', 'msi_mappings', len(newmsi), 'status', name)
            if mapped.get('status') == 'STALE':
                issue('MSI_STALE', 'MSI 来源已变化，保留旧选择，请核对后重新确认', 'msi_mappings', len(newmsi), 'status', name, location=str(file) + '/' + mapped['sheet'])
            namespace = SimpleNamespace(roots={'msi': file.parent}, msi_mappings={name: (str(file), mapped['sheet'], mapped['column'])}, attribute_overrides=[])
            signals = discover(namespace, name)
            for signal in signals:
                bits = signal_bits(signal.name, signal.width)
                if len(bits) != signal.width:
                    raise ValueError('MSI 信号范围与 WIDTH 不一致：' + signal.name)
            mapped['file'] = str(file)
            for s in signals:
                domain(s.power_domain)
                domain(s.ground_domain)
        except Exception as exc:
            issue('MSI_MAPPING', exc, 'msi_mappings', len(newmsi), 'file', name, location=mapped.get('file', '') + '/' + mapped.get('sheet', ''))
        newmsi.append(mapped)
        resolved['msi'][name] = [asdict(s) for s in signals]
        for d in directions(module):
            key = name + '|' + d
            if 'template' not in roots:
                continue
            path = anchors['template'] or roots['template'] / ('%s_%s.t2b' % (d.lower(), module.get('topology','').lower()))
            if anchors['template'] and len(plans) != 1:
                issue('TEMPLATE_SCOPE', '单个 T2B 文件不能覆盖多个方向或拓扑，请指定模板目录', 'sources', field='template', module=name, direction=d)
                continue
            try:
                raw = path.read_text(encoding='utf-8')
                validation = validate_template_text(raw, d, module.get('topology', ''))
                if not validation.valid:
                    raise ValueError('；'.join(validation.errors))
                tpins, links, diff = template_pins(raw)
                spice = re.search(r'^\[Spice type\]\s+(.+)', raw, re.M | re.I).group(1).strip()
                spice = 'spectre' if spice == '{{SPICE_TYPE}}' else spice.casefold()
                command = re.search(r'^\[Spice command\]\s+(.+)', raw, re.M | re.I)
                command = command.group(1).strip() if command else ''
                if command == '{{SPICE_COMMAND}}':
                    command = 'spectre +preset=mx +spice +mt=4' if spice == 'spectre' else 'hspice'
                resolved['templates'][key] = dict(path=str(path.resolve()), pins=tpins, links=links, spice=spice, command=command, sha256=hash_file(path))
                for t in tpins:
                    if t['kind'].casefold() in ('power', 'gnd'):
                        actual = next((s.name for s in signals if s.name.casefold() == t['name'].casefold()), t['name'])
                        domain(actual)
                power_candidates = [s.name for s in signals if any(t['kind'].casefold() == 'power' and t['name'].casefold() == s.name.casefold() for t in tpins)]
                for field in ('io_domain', 'vih_domain'):
                    if not module.get(field) and len(power_candidates) == 1:
                        module[field] = power_candidates[0]
                pin_fp = fingerprint([hashes, str(path.resolve()), hash_file(path), mapped.get('current_fingerprint', '')])
                used = set()
                for t in tpins:
                    row = copy.deepcopy(oldpins.get((name, d, t['name']), dict(module=name, direction=d, t2b_pin=t['name'], spf_pin='', status='UNRESOLVED')))
                    row['kind'] = t['kind']
                    if not row.get('spf_pin'):
                        matching = [p for p in pins or [] if p.casefold() == t['name'].casefold()]
                        if len(matching) == 1:
                            row.update(spf_pin=matching[0], status='AUTO_MATCH')
                    if row.get('fingerprint') and row['fingerprint'] != pin_fp and row.get('status') in ('MANUAL', 'STALE'):
                        row['status'] = 'STALE'
                    row['current_fingerprint'] = pin_fp
                    if not row.get('fingerprint') or row.get('status') == 'AUTO_MATCH':
                        row['fingerprint'] = pin_fp
                    message = ''
                    if not re.fullmatch(r'[\x21-\x7e]{1,5}', t['name']):
                        message = 'IBIS 对外 Pin 必须为不超过 5 个 ASCII 可见字符'
                    elif not row.get('spf_pin'):
                        message = '仅允许同名自动匹配；请选择实际 SPF Pin 并确认'
                    elif row['spf_pin'].casefold() not in {p.casefold() for p in pins or []}:
                        message = '原 SPF Pin 已不存在，请重新选择'
                        row['status'] = 'STALE'
                    elif row['spf_pin'].casefold() in used:
                        message = '同一方向多个 IBIS Pin 映射到了同一个 SPF Pin'
                    elif row.get('status') == 'AUTO_MATCH' and row['spf_pin'].casefold() != t['name'].casefold():
                        message = '不同名 Pin 必须人工确认，不能标记为自动匹配'
                    elif row.get('status') not in ('AUTO_MATCH', 'MANUAL'):
                        message = '映射待确认或来源变化，请核对后重新确认'
                    if not message and t['kind'].casefold() in ('power','gnd'):
                        signal = next((s for s in signals if s.name.casefold()==row['spf_pin'].casefold()), None)
                        expected = 'power' if t['kind'].casefold()=='power' else 'ground'
                        if signal is None or signal.attribute_type.casefold() != expected:
                            message = 'T2B Power/Gnd 必须对应 MSI 中类型一致的电源/地 Pin'
                    if not message and row['spf_pin'].casefold() in {bit.casefold() for s in signals if s.name.casefold() in STRENGTH for bit in signal_bits(s.name,s.width)}:
                        message = 'IBIS Pin 不得接管 Ron 阻抗控制信号'
                    if message:
                        issue('IBIS_PIN_MAPPING', message, 'pins', len(newpins), 'spf_pin', name, d, location=str(path))
                    used.add(row.get('spf_pin', '').casefold())
                    newpins.append(row)
                mappings = {r.get('spf_pin','').casefold(): r['t2b_pin'] for r in newpins if r['module']==name and r['direction']==d and r.get('spf_pin')}
                connected = [mappings.get(pin.casefold(),pin).casefold() for pin in (pins or [])]
                if len(connected) != len(set(connected)):
                    issue('PIN_NODE_COLLISION', '映射后连接节点重复，可能短接未映射 SPF Pin；请检查映射', 'pins', field='spf_pin', module=name, direction=d)
            except Exception as exc:
                issue('TEMPLATE_INVALID', exc, 'sources', field='template', module=name, direction=d, location=path)
        for field in ('io_domain','vih_domain'):
            domain(module.get(field, ''))
            if not module.get(field):
                issue('DOMAIN_UNRESOLVED', '电压域无法唯一确定，请人工选择', 'modules', index, field, name)
        if signals and pins:
            expanded = {p.casefold() for s in signals for p in signal_bits(s.name, s.width)}
            missing = [p for p in pins if p.casefold() not in expanded and p.casefold() not in {v.casefold() for v in domains}]
            if missing:
                issue('SPF_MSI_INTERFACE', 'SPF Pin 缺少 MSI 定义：' + ', '.join(missing), 'msi_mappings', len(newmsi)-1, 'file', name)
        strength = [s for s in signals if s.name.casefold() in STRENGTH]
        if len(strength) != 2:
            issue('RON_SIGNALS', 'MSI 缺少 PU/PD 阻抗控制信号', 'modules', index, 'ron', name)
        for s in strength:
            a, b = impedance_map(s.description), impedance_map(s.databook_description)
            if a and b and a != b:
                issue('RON_CODE_CONFLICT', '两个 MSI 阻抗映射说明冲突：' + s.name, 'modules', index, 'ron', name)
            for ron in module.get('rons', []):
                if ron in (a or b):
                    try:
                        parse_logic(str(s.width) + "'b" + (a or b)[ron], name, s.name, s.width)
                    except Exception as exc:
                        issue('RON_CODE_INVALID', exc, 'modules', index, 'ron', name)
                if ron not in (a or b):
                    issue('RON_CODE_MISSING', '%s 缺少 %sΩ 的实际 code' % (s.name, ron), 'modules', index, 'ron', name)
    # Never silently discard a saved manual mapping when a module or template
    # disappears. Keep it visible for explicit correction/deletion.
    for old in data['pins']:
        identity = (old.get('module'), old.get('direction'), old.get('t2b_pin'))
        if not any((r.get('module'),r.get('direction'),r.get('t2b_pin'))==identity for r in newpins):
            retained = copy.deepcopy(old)
            retained['status'] = 'STALE'
            issue('PIN_ORPHAN', '原映射的模块/方向/模板 Pin 不再存在；请核对后删除或修正来源', 'pins',len(newpins),'spf_pin',old.get('module',''),old.get('direction',''))
            newpins.append(retained)
    for old in data['msi_mappings']:
        if not any(r.get('module')==old.get('module') for r in newmsi):
            retained = copy.deepcopy(old)
            retained['status'] = 'STALE'
            issue('MSI_ORPHAN', '原 MSI 映射的模块已不存在，请核对后删除', 'msi_mappings',len(newmsi),'file',old.get('module',''))
            newmsi.append(retained)
    # Invalid duplicate rows must remain visible across automatic rechecks;
    # otherwise a second scan could silently drop the conflict and allow Generate.
    for field, target, keys in [('pins',newpins,('module','direction','t2b_pin')), ('msi_mappings',newmsi,('module',))]:
        groups = {}
        for row in data[field]:
            identity = tuple(row.get(k,'') for k in keys)
            groups.setdefault(identity,[]).append(row)
        for rows in groups.values():
            if len(rows)>1:
                extras = rows[:-1] if field=='pins' else rows[1:]
                target.extend(copy.deepcopy(extras))
    data['pins'], data['msi_mappings'] = newpins, newmsi
    for d in domains:
        if not any(r.get('domain', '').casefold() == d.casefold() for r in data['voltages']):
            data['voltages'].append(dict(domain=d, source='T2B/MSI', **{c: '' for c in CORNERS}))
    check_values(data, resolved, issue)
    check_models(data, resolved, roots, issue)
    # At most one optional starter row per actual plan, never phantom modules.
    for field in ('appends','overrides'):
        for module in data['modules']:
            for d in directions(module):
                if not any(r.get('module') == module['name'] and r.get('direction') == d for r in data[field]):
                    row = dict(module=module['name'], direction=d)
                    row.update({'body': ''} if field == 'appends' else dict(signal='', **{c: '' for c in CORNERS}))
                    data[field].append(row)
    data['resolved'], data['issues'] = resolved, issues
    if not any(r['severity']=='BLOCKING' for r in issues):
        try:
            from .adapter import core_config
            from ibis_auto.generator import validate_module, render_t2b
            config = core_config(data)
            for plan in config.modules:
                signals = discover(config, plan.name)
                validate_module(plan.name, signals, resolved['spf'][plan.name]['pins'], config)
                for d in directions(next(m for m in data['modules'] if m['name']==plan.name)):
                    source = Path(resolved['templates'][plan.name+'|'+d]['path'])
                    render_t2b(config, plan, d, plan.impedances[0], resolved['spf'][plan.name]['top'], source.read_text(encoding='utf-8'))
        except Exception as exc:
            issue('CORE_PRECHECK', exc, 'modules', field='name')
    return data


def check_models(data, resolved, roots, issue):
    if 'model' not in roots:
        return
    for spice in set(t['spice'] for t in resolved['templates'].values()):
        candidates = [p for p in (roots['model'], roots['model']/spice) if all((p/n).is_file() for n in ('rbd.lib','cap.lib','mos_var.lib'))]
        if len(candidates) != 1:
            issue('MODEL_LIBRARY', '模型目录必须唯一包含 rbd.lib、cap.lib、mos_var.lib', field='model', location=roots['model'])
            continue
        directory = candidates[0]
        resolved.setdefault('model_directories', {})[spice] = str(directory)
        for c in CORNERS:
            process = data['corners'][c].get('process','').upper()
            sections = []
            for filename in ('rbd.lib','cap.lib','mos_var.lib'):
                file = directory/filename
                text = file.read_text(encoding='utf-8', errors='replace')
                actual = re.findall(r'^\s*(?:\.lib|section)\s+([A-Za-z_][\w.-]*)\s*(?:$|[;*])', text, re.I|re.M)
                suffixes = {'FF': ('f','ff'), 'TT': ('t','tt'), 'SS': ('s','ss'), 'FS': ('fs',), 'SF': ('sf',)}.get(process, ())
                matches = list(dict.fromkeys(name for name in actual if name.casefold() in suffixes or any(name.casefold() == file.stem.casefold()+'_'+suffix for suffix in suffixes)))
                if len(matches) != 1:
                    issue('PDK_SECTION', 'Process %s 的真实 section 数量为 %d，请检查模型库；不臆造 section' % (process,len(matches)), 'corners', CORNERS.index(c), 'process', corner=c, location=file)
                else:
                    sections.append(matches[0])
            if len(sections) == 3:
                resolved['pdk'][spice+':'+process] = sections


def check_values(data, resolved, issue):
    names = [r.get('domain','').casefold() for r in data['voltages']]
    for i, row in enumerate(data['voltages']):
        if not re.fullmatch(r'[A-Za-z_][\w]*', row.get('domain','')) or names.count(row.get('domain','').casefold()) != 1:
            issue('VOLTAGE_DOMAIN', '供电域名称缺失、不合法或重复', 'voltages', i, 'domain')
        for c in CORNERS:
            try:
                value = Decimal(row.get(c,''))
                if not value.is_finite() or value < 0:
                    raise ValueError()
            except (ValueError, InvalidOperation):
                issue('VOLTAGE_MISSING', '实际电压必须由工程师填写为有限非负数；软件不会编造', 'voltages', i, c, corner=c)
    modules = {m['name']: m for m in data['modules']}
    for field in ('signals', 'overrides'):
        seen = set()
        for i, row in enumerate(data[field]):
            signal = row.get('signal','').strip()
            if not signal and not any(row.get(c,'').strip() for c in CORNERS):
                continue
            targets = list(modules) if field == 'signals' else [row.get('module','')]
            count = 0
            for module in targets:
                found = next((s for s in resolved['msi'].get(module,[]) if s['name'].casefold() == signal.casefold()), None)
                if not found:
                    if field == 'overrides':
                        issue('SIGNAL_MISSING', 'MSI 中不存在此信号', field, i, 'signal', module)
                    continue
                count += 1
                for c in CORNERS:
                    value = row.get(c,'').strip()
                    if not value:
                        continue
                    direction = row.get('direction', 'BOTH')
                    if field == 'overrides' and direction not in directions(modules.get(module, {})):
                        issue('OVERRIDE_SCOPE', '覆盖方向不在模块生成计划内', field,i,'direction',module)
                    for d in (directions(modules[module]) if field == 'signals' else (direction,)):
                        key = (module,d,c,signal.casefold())
                        if key in seen:
                            issue('SIGNAL_CONFLICT', '同一作用域存在重复覆盖',field,i,c,module,d,c)
                        seen.add(key)
                    try:
                        if signal.casefold() in STRENGTH:
                            raise ValueError('普通信号覆盖不得修改 Ron→Code 阻抗控制信号')
                        from .logic_codes import canonical_value
                        canonical_value(row,c,found['width'])
                    except Exception as exc:
                        issue('SIGNAL_VALUE', exc,field,i,c,module,corner=c)
            if not count:
                issue('SIGNAL_MISSING', '没有模块的 MSI 定义此信号',field,i,'signal')
    for i, row in enumerate(data['appends']):
        if not row.get('body','').strip():
            continue
        name, d = row.get('module',''), row.get('direction','')
        if name not in modules or d not in directions(modules.get(name,{})):
            issue('APPEND_SCOPE','追加电路作用域不存在','appends',i,'module',name,d)
    for module in modules:
        for d in directions(modules[module]):
            body = '\n'.join(r.get('body','') for r in data['appends'] if r.get('module')==module and r.get('direction')==d)
            original = resolved['spf'].get(module,{}).get('pins',[])
            aliases = {r.get('spf_pin','').casefold():r['t2b_pin'] for r in data['pins']
                       if r.get('module')==module and r.get('direction')==d
                       and r.get('status') in ('AUTO_MATCH','MANUAL') and r.get('spf_pin')}
            effective_pins = [aliases.get(pin.casefold(),pin) for pin in original]
            for level,msg in append_diagnostics(body,effective_pins):
                issue('APPEND_SYNTAX',msg,'appends',field='body',module=module,direction=d,severity='BLOCKING' if level=='Error' else 'WARNING')
    # Validate effective inherited values, not just non-empty override cells.
    from .adapter import effective_overrides
    overrides = effective_overrides(data, resolved, tolerate_invalid=True)
    for module, signals in resolved['msi'].items():
        for signal in signals:
            power = signal['power_domain']
            if power and power.casefold() not in names:
                issue('MSI_POWER_DOMAIN','MSI POWER_DOMAIN 未定义；请修正原 MSI 或供电域表','msi_mappings',module=module,field='file')
            if signal['direction'].casefold() not in ('input','i','output','o','io','inout','power','ground',''):
                issue('MSI_DIRECTION','MSI 方向不合法：'+signal['name'],'msi_mappings',module=module,field='file')
            if signal['direction'].casefold() not in ('input','i') or signal['name'].casefold() in STRENGTH or signal['attribute_type'].casefold() in ('power','ground'):
                continue
            for d in directions(modules[module]):
                controlled = [p['name'].casefold() for p in resolved['templates'].get(module+'|'+d,{}).get('pins',[])]
                mapped = [p.get('spf_pin','').casefold() for p in data['pins'] if p['module']==module and p['direction']==d and p['t2b_pin'].casefold() in controlled]
                if signal['name'].casefold() in mapped:
                    if any(r['module']==module and r['direction']==d and r['signal'].casefold()==signal['name'].casefold() for r in overrides):
                        issue('T2B_SIGNAL_CONTROL','此信号由 T2B 接管，不能用普通信号覆盖','overrides',module=module,direction=d,field='signal')
                    continue
                for c in CORNERS:
                    raw = next((r['value'] for r in overrides if r['module']==module and r['direction']==d and r['corner']==c and r['signal'].casefold()==signal['name'].casefold()),signal['default'])
                    try:
                        bits = parse_logic(raw,module,signal['name'],signal['width'])
                        if '1' in bits and power.casefold() not in names:
                            raise ValueError('高电平信号缺少有效 POWER_DOMAIN：'+signal['name'])
                    except Exception as exc:
                        issue('MSI_EFFECTIVE_VALUE',exc,'overrides',module=module,direction=d,corner=c,field='signal')
