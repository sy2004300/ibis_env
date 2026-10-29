from __future__ import annotations
import copy
from .model import CORNERS, directions, parse_rons
from ..errors import ProjectValidationError


def effective_overrides(data, resolved):
    result = []
    for module in data['modules']:
        name = module['name']
        for s in resolved.get('msi',{}).get(name,[]):
            for d in directions(module):
                for c in CORNERS:
                    global_values = [r.get(c,'').strip() for r in data['signals'] if r.get('signal','').casefold()==s['name'].casefold() and r.get(c,'').strip()]
                    local_values = [r.get(c,'').strip() for r in data['overrides'] if r.get('module')==name and r.get('direction')==d and r.get('signal','').casefold()==s['name'].casefold() and r.get(c,'').strip()]
                    value = (local_values or global_values or [''])[0]
                    if value:
                        result.append(dict(module=name,direction=d,corner=c,signal=s['name'],value=value))
    return result


def require_ready(data):
    failures = [r for r in data.get('issues',[]) if r['severity']=='BLOCKING']
    if failures:
        raise ProjectValidationError('VNEXT_BLOCKED', '生成被阻止：\n' + '\n'.join('%s / %s / %s：%s' % (r['module'],r['corner'],r['field'],r['message']) for r in failures))


def to_legacy(data):
    """Convert validated VNext facts to existing Stage 1 canonical parameters."""
    from ..models import empty_config_payload
    result = empty_config_payload()
    resolved = data['resolved']
    result['roots'].update(resolved['roots'])
    result['roots']['template'] = resolved['config_template_root']
    result['simulation_options'] = list(data.get('provenance',{}).get('legacy_simulation_options', ['.option method=gear', '.option runlvl=5']))
    for m in data['modules']:
        result['modules'].append(dict(name=m['name'], generate_type=m['generate_type'], impedances=parse_rons(m['ron']), ibis_io_voltage_domain=m['io_domain'], ibis_vih_voltage_domain=m['vih_domain'], tr={c:data['corners'][c]['tr'] for c in CORNERS}, tf={c:data['corners'][c]['tf'] for c in CORNERS}))
        for d in directions(m):
            result['templates'].append(dict(module=m['name'],direction=d,template_type=d.lower()+'_'+m['topology'].lower()))
    result['voltage_order'] = [r['domain'] for r in data['voltages']]
    for c in CORNERS:
        result['corners'][c].update({key:data['corners'][c][key] for key in ('process','temperature','spf_key')})
        result['corners'][c]['voltages'] = {r['domain']:r[c] for r in data['voltages']}
    for r in data['pins']:
        if r.get('status') not in ('AUTO_MATCH','MANUAL') or not r.get('spf_pin'):
            continue
        pins = resolved['spf'][r['module']]['pins']
        actual = next(p for p in pins if p.casefold()==r['spf_pin'].casefold())
        result['aliases'].append(dict(module=r['module'],direction=r['direction'],original_pin=actual,alias=r['t2b_pin']))
    result['appends'] = [dict(module=r['module'],direction=r['direction'],body=r['body']) for r in data['appends'] if r.get('body','').strip()]
    result['overrides'] = effective_overrides(data,resolved)
    result['msi_mappings'] = [{k:r[k] for k in ('module','file','sheet','column')} for r in data['msi_mappings']]
    # Optional canonical extensions do not affect legacy generation.
    result['stage1_metadata'] = dict(process_sections=resolved['pdk'], model_directories=resolved['model_directories'], controlled_pins={})
    for key, template in resolved['templates'].items():
        module,d = key.split('|')
        controlled = []
        for r in data['pins']:
            if r['module']==module and r['direction']==d:
                controlled.append((r['spf_pin'], '1' if r['kind'].casefold()=='power' else '0'))
        result['stage1_metadata']['controlled_pins'][key] = controlled
    return result


def core_config(data):
    from ..config_adapter import payload_to_core_config
    from pathlib import Path
    legacy = to_legacy(data)
    paths = {tuple(k.split('|')):Path(v['path']) for k,v in data['resolved']['templates'].items()}
    return payload_to_core_config(legacy,template_paths=paths)
