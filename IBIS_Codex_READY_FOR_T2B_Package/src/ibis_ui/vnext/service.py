"""VNext orchestration; all generation still uses the existing Stage 1 engine."""
from __future__ import annotations
import copy
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from ibis_auto.service import generate_from_config, expand_case_keys
from ibis_auto.generator import render_t2b
from ..errors import ProjectValidationError
from ..models import utc_now
from .scan import precheck, hash_file, fingerprint
from .adapter import core_config, require_ready
from .model import payload, directions, parse_rons
from .excel import write


def atomic_json(path, value):
    from ..generation_service import _atomic_json
    _atomic_json(path, value)


def writable_project(store, project):
    root = store.project_dir(project.project_id).resolve()
    workspace = store.workspace.resolve()
    if workspace not in root.parents:
        raise ProjectValidationError('WORKSPACE_ESCAPE', '项目目录通过链接指向工作区以外，请重新指定 Workspace')
    data = project.config['vnext']
    sources = [Path(p).expanduser().resolve() for p in data['sources'].values() if p]
    if project.source_excel:
        sources.append(Path(project.source_excel.path).resolve())
    for source in sources:
        if source.is_dir() and (source == root or source in root.parents):
            raise ProjectValidationError('WORKSPACE_IN_SOURCE', '项目输出目录位于原始输入目录中，请使用独立 Workspace：' + str(source))
    for name in ('config', 'logs', 'READY_FOR_T2B'):
        child = (root / name).resolve()
        if root not in child.parents:
            raise ProjectValidationError('WORKSPACE_ESCAPE', '项目输出子目录指向工作区以外：' + name)
    return root


def archive_import(store, project, source):
    root = writable_project(store, project)
    target = root / 'config' / 'imports' / hash_file(source) / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(str(source), str(target))
    if hash_file(source) != hash_file(target):
        raise ProjectValidationError('IMPORT_CHANGED', '导入副本与原文件不一致，请重新导入')


def save_checked(store, project):
    root = writable_project(store, project)
    data = project.config['vnext']
    # ProjectStore is the authoritative atomic snapshot; these are reproducible views.
    path = store.save(project)
    target = root / 'config' / 'Config_Generated.xlsx'
    if project.source_excel and target.resolve() == Path(project.source_excel.path).resolve():
        target = root / 'config' / 'Config_Current.xlsx'
    write(data, target)
    atomic_json(root / 'logs' / 'precheck.json', dict(checked_at=utc_now(), issues=data['issues']))
    return path


def source_hashes(data):
    paths = set()
    for row in data['resolved']['spf'].values():
        paths.update(row['files'].values())
    paths.update(r['file'] for r in data['msi_mappings'] if r.get('file'))
    paths.update(r['path'] for r in data['resolved']['templates'].values())
    for directory in data['resolved'].get('model_directories', {}).values():
        paths.update(str(Path(directory) / name) for name in ('rbd.lib', 'cap.lib', 'mos_var.lib'))
    paths.add(str(Path(data['resolved']['config_template_root']) / '_t2b_config.ini'))
    return {p: hash_file(p) for p in sorted(paths)}


def semantic_hash(data):
    return fingerprint({k: v for k, v in data.items() if k not in ('issues', 'resolved', 'provenance')})


def generate(store, resources, project, **kwargs):
    # Recheck on every backend call. A saved Excel status is never authority.
    checked = precheck(project.config['vnext'], resources.template_root)
    require_ready(checked)
    config = core_config(checked)
    root = writable_project(store, project)
    output = root / 'READY_FOR_T2B'
    hashes = source_hashes(checked)
    # Store copies of the selected small inputs for traceability. SPICE .lib
    # references still point to the verified original library, preserving its includes.
    for source, digest in hashes.items():
        source_path = Path(source)
        if source_path.suffix.lower() == '.lib':
            continue
        target = root / 'config' / 'sources' / digest / source_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(str(source_path), str(target))
        if hash_file(target) != digest:
            raise ProjectValidationError('SOURCE_COPY_CHANGED', '项目输入副本已改变：' + str(target))
    # Source hashes are checked immediately before and after the engine call.
    if source_hashes(checked) != hashes:
        raise ProjectValidationError('SOURCE_CHANGED', '准备输入期间来源文件发生变化，请重新检查')
    result = generate_from_config(config, output, golden_root=None, **kwargs)
    if source_hashes(checked) != hashes:
        for row in result.cases:
            row.status, row.message = 'FAIL', '生成期间来源文件变化，本次输出不可用于仿真，请重新检查生成'
        result.ready = False
    workflow = project.workflow or {}
    generation = workflow.setdefault('generation', {})
    records = generation.setdefault('cases', {})
    for row in result.cases:
        record = asdict(row)
        record['output_path'] = record.pop('path')
        record['input_hashes'] = hashes
        record['config_hash'] = semantic_hash(checked)
        record['output_files'] = {}
        if record['output_path'] and Path(record['output_path']).is_dir():
            record['output_files'] = {str(p): hash_file(p) for p in Path(record['output_path']).iterdir() if p.is_file()}
        records[row.key] = record
    generation.update(output_root=str(output), tasks=[asdict(r) for r in result.cases])
    project.workflow = workflow
    project.config = payload(checked)
    project.updated_at = utc_now()
    atomic_json(root / 'logs' / 'generation.json', dict(generated_at=utc_now(), ready=result.ready, cases=[asdict(r) for r in result.cases], input_hashes=hashes, config=checked))
    save_checked(store, project)
    return result


def statuses(project):
    data = project.config['vnext']
    records = (project.workflow or {}).get('generation', {}).get('cases', {})
    result = []
    for module in data['modules']:
        try:
            rons = parse_rons(module.get('ron', ''))
        except ValueError:
            continue
        for d in directions(module):
            for ron in rons:
                key = '%s/%s/%sohm' % (module['name'], d, ron)
                row = copy.deepcopy(records.get(key, dict(status='NOT_GENERATED', message='尚未生成')))
                row.update(key=key, module=module['name'], direction=d, ron=ron)
                if row.get('config_hash') and row['config_hash'] != semantic_hash(data):
                    row.update(status='STALE', message='配置已修改，请重新生成')
                for field, status, message in [('input_hashes','STALE','来源文件已变化'), ('output_files','FAIL','生成文件缺失或被修改')]:
                    for path, expected in row.get(field, {}).items():
                        if not Path(path).is_file() or hash_file(path) != expected:
                            row.update(status=status, message=message)
                            break
                result.append(row)
    return result


def preview(data, key):
    require_ready(data)
    config = core_config(data)
    if key not in expand_case_keys(config):
        raise ProjectValidationError('PREVIEW_CASE', '请选择有效的模块、方向和 Ron')
    module, direction, ron = key
    plan = next(p for p in config.modules if p.name == module)
    source = Path(data['resolved']['templates'][module + '|' + direction]['path'])
    return render_t2b(config, plan, direction, ron, data['resolved']['spf'][module]['top'], source.read_text(encoding='utf-8'))[0]
