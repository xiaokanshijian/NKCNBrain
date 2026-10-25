"""可定位的输出错误；证据违规与措辞疑点分别记录，兼容原ValueError调用方。"""
import copy
import json


class TextConstraintError(ValueError):
    def __init__(self, message, findings):
        super().__init__(message)
        self.findings = findings


def issue(error, path, *, qid=None, code='invalid_evidence'):
    findings = getattr(error, 'findings', [])
    if hasattr(error, 'issues'):
        findings = [finding for entry in error.issues for finding in entry.get('findings', [])]
    return {'path': path, 'qid_global': qid, 'code': code,
            'kind': 'wording' if findings and all(x['kind'] == 'ambiguous' for x in findings) else 'evidence',
            'message': str(error), 'findings': findings}


class ValidationIssues(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('；'.join(f"{x['path']}: {x['message']}" for x in issues))


def raise_issues(issues):
    if issues:
        raise ValidationIssues(issues)


def _parts(path):
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('修复字段路径无效')
    return [x.replace('~1', '/').replace('~0', '~') for x in path[1:].split('/')]


def _read(document, path):
    try:
        for part in _parts(path):
            document = document[int(part)] if isinstance(document, list) else document[part]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError('修复返回缺少字段：' + path) from exc
    return copy.deepcopy(document)


def _write(document, path, value):
    parts = _parts(path)
    node = document
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(parts[-1])] = copy.deepcopy(value)
    else:
        node[parts[-1]] = copy.deepcopy(value)


def field_repair_plan(previous, error, *, allow_zone_removal=False):
    """只接受校验器允许的原字段路径，完整返回也只取出待修字段。"""
    if not isinstance(previous, dict) or not isinstance(error, ValidationIssues):
        return None
    paths = sorted({x['path'] for x in error.issues}, key=lambda x: (len(_parts(x)), x))
    if '/' in paths:
        return None
    paths = [p for p in paths if not any(p.startswith(parent + '/') for parent in paths if parent != p)]
    frozen = copy.deepcopy(previous)

    def merge(patch):
        candidate = copy.deepcopy(frozen)
        changes = patch.get('repairs')
        if changes is not None:
            if not isinstance(changes, list) or any(not isinstance(x, dict) for x in changes):
                raise ValueError('repairs必须为路径与value对象数组')
            by_path = {}
            for change in changes:
                path = change.get('path')
                if path not in paths or path in by_path or 'value' not in change:
                    raise ValueError('修复返回包含未授权、重复或缺失的字段')
                by_path[path] = change['value']
            if set(by_path) != set(paths):
                raise ValueError('修复返回未覆盖全部待修字段')
        else:
            by_path = {}
            for path in paths:
                parts = _parts(path)
                # 兼容完整响应中明确撤回无效分区项；只允许删除已被校验器拒绝的项。
                if (allow_zone_removal and len(parts) == 3 and parts[0] == 'zones'
                        and parts[2].isdigit() and _read(patch, '/' + '/'.join(parts[:2])) == []):
                    by_path[path] = None
                else:
                    by_path[path] = _read(patch, path)
        removals = []
        for path, value in by_path.items():
            parts = _parts(path)
            if (allow_zone_removal and value is None and len(parts) == 3
                    and parts[0] == 'zones' and parts[2].isdigit()):
                removals.append((parts[1], int(parts[2])))
            else:
                _write(candidate, path, value)
        for bucket, index in sorted(removals, reverse=True):
            del candidate['zones'][bucket][index]
        return candidate

    return {'merge': merge, 'paths': paths, 'prompt': (
        '只修正下列路径，其他内容已经通过校验，必须保持不变。输出JSON：'
        '{"repairs":[{"path":"原路径","value":"修正后的完整字段值"}]}。'
        '数组项位置对应上次返回，不得重排。证据不足时明确待确认，不得删除引用后保留无据结论。\n'
        + json.dumps(error.issues, ensure_ascii=False))}


def ontology_repair_plan(previous, error):
    plan = field_repair_plan(previous, error, allow_zone_removal=True)
    if plan:
        plan['prompt'] += '\n无法支持的分区项可用value:null明确撤回，仅限列出的无效项。'
    return plan


def feedback_repair_plan(previous, error):
    plan = field_repair_plan(previous, error)
    if not plan:
        return None
    items = previous.get('per_question_feedback')
    if not isinstance(items, list):
        return plan
    bad = {int(x['path'].split('/')[2]) for x in error.issues
           if x['path'].startswith('/per_question_feedback/') and x['path'].split('/')[2].isdigit()}
    protected = {x['qid_global']: copy.deepcopy(x) for i, x in enumerate(items)
                 if i not in bad and isinstance(x, dict) and isinstance(x.get('qid_global'), str)}
    apply = plan['merge']

    def merge(patch):
        candidate = apply(patch)
        values = candidate.get('per_question_feedback')
        if isinstance(values, list):
            candidate['per_question_feedback'] = [copy.deepcopy(protected.get(x.get('qid_global'), x))
                if isinstance(x, dict) else x for x in values]
            present = {x.get('qid_global') for x in values if isinstance(x, dict)}
            candidate['per_question_feedback'] += [copy.deepcopy(x) for qid, x in protected.items() if qid not in present]
        return candidate

    return {**plan, 'merge': merge}
