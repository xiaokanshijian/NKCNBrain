"""结果展示仅使用对应运行的课程内容；损坏快照不回退最新规则。"""
from .feedback_curriculum import curriculum_entries
from .feedback_runtime_service import restore_feedback_runtime
from .feedback_snapshot_reader import read_feedback_snapshot
from .curriculum import _short_cn_name, label_to_cn_map, label_to_domain_map


def result_basis(root, manifest):
    state = read_feedback_snapshot(root, manifest)
    runtime = None
    names, domains = {}, {}
    if state['snapshot_status'] == 'complete':
        try:
            runtime = restore_feedback_runtime(root)
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
            names, domains = label_to_cn_map(subject), label_to_domain_map(subject)
        state['snapshot_warnings'].append('旧版本知识点名称为兼容映射，未保存当时课程版本')
    return state, runtime, names, domains
