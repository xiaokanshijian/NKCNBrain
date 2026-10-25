"""结果展示仅使用对应运行的课程内容；损坏快照不回退最新规则。"""
from .feedback_curriculum import curriculum_entries
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from .feedback_snapshot_reader import read_feedback_snapshot
from .curriculum import _short_cn_name, id_to_cn, label_to_cn_map, label_to_domain_map, load_curriculum_entries


def result_basis(root, manifest):
    state = read_feedback_snapshot(root, manifest)
    runtime = None
    names, domains = {}, {}
    if state['snapshot_status'] == 'complete':
        try:
            # 展示只读取已校验快照，不组合现行执行规则或初始化模型。
            contents = {}
            from .feedback_snapshot_reader import SNAPSHOT_FILES
            for kind, name in SNAPSHOT_FILES.items():
                raw = (Path(root) / name).read_bytes()
                if hashlib.sha256(raw).hexdigest() != manifest['feedback_snapshot']['files'][name]:
                    raise ValueError('读取期间快照发生变化')
                value = json.loads(raw)
                contents[kind] = value if kind == 'context' else value['data']
            context = contents.pop('context')
            runtime = SimpleNamespace(context=context, dependencies={**contents, **manifest['feedback_execution']},
                                      fingerprint=state['config_fingerprint'])
            labels = runtime.dependencies['retrieval'].get('display_names', {}).get(
                runtime.context['subject_code'], {})
            for entry in curriculum_entries(runtime):
                name = labels.get(entry['label']) or _short_cn_name(entry.get('description', ''), entry['label'])
                # 冻结课标既提供稳定编号，也保留旧英文标签；两者指向同一知识点。
                for key in (entry['id'], entry['label']):
                    names[key] = name
                    domains[key] = entry['domain']
        except (ValueError, OSError, KeyError, TypeError):
            state.update(snapshot_status='invalid', feedback_context=None,
                         snapshot_warnings=['运行依据无法完整恢复，仅保留原结果展示'])
            runtime = None
            names, domains = {}, {}
    elif state['snapshot_status'] == 'legacy_missing':
        subject = manifest.get('subject') or 'unknown'
        if subject in ('math', 'chinese', 'english'):
            names, domains = dict(label_to_cn_map(subject)), dict(label_to_domain_map(subject))
            # 全学科：课标码与英文 label 都映射到同一中文名，避免界面露出 EN_S2_040 等
            for entry in load_curriculum_entries(subject):
                cid = entry.get('id') or ''
                label = entry.get('label') or ''
                cn = names.get(label) or id_to_cn(subject, cid) or _short_cn_name(
                    entry.get('description', ''), label
                )
                if cid and cn:
                    names[cid] = cn
                    domains[cid] = entry.get('domain') or domains.get(label, '')
        state['snapshot_warnings'].append('旧版本知识点名称为兼容映射，未保存当时课程版本')
    return state, runtime, names, domains
