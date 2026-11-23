"""可定位的输出错误；证据违规与措辞疑点分别记录，兼容原ValueError调用方。"""
import copy
import json
import re


def coerce_next_steps(steps):
    """将「一、…二、…」整段或其它可拆形式收成 1～2 条字符串，供校验与兜底。"""
    if isinstance(steps, list):
        items = [str(step).strip() for step in steps if isinstance(step, str) and str(step).strip()]
        if 1 <= len(items) <= 2:
            return items
        return items[:2] if items else None
    if not isinstance(steps, str) or not steps.strip():
        return None
    text = steps.strip()
    # 允许「一、…。二、…」同行连写，也允许换行/分号分隔。
    parts = re.split(r'(?:^|[\n；;。])\s*[一二三四五六七八九十\d]+[、.．]\s*', text)
    items = [part.strip().strip('；;。') for part in parts if part and part.strip()]
    if len(items) < 2:
        parts = re.split(r'[\n；;]+', text)
        items = [part.strip().strip('；;。') for part in parts if part and part.strip()]
    if not items and text:
        items = [text]
    items = [item for item in items if item][:2]
    return items or None


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
    prev_by_index = {i: copy.deepcopy(x) for i, x in enumerate(items) if isinstance(x, dict)}
    apply = plan['merge']

    def merge(patch):
        # 优先接受完整 JSON；若仍给 repairs，把「只回了 comment 字符串」还原成完整批语对象。
        if isinstance(patch, dict) and 'repairs' not in patch and isinstance(patch.get('per_question_feedback'), list):
            candidate = copy.deepcopy(previous)
            for key in ('open_material_overview', 'page_feedback_contexts', 'per_question_feedback'):
                if key in patch:
                    candidate[key] = copy.deepcopy(patch[key])
        else:
            candidate = apply(patch)
        values = candidate.get('per_question_feedback')
        if isinstance(values, list):
            fixed = []
            for i, x in enumerate(values):
                if isinstance(x, str) and i in prev_by_index:
                    fixed.append({**copy.deepcopy(prev_by_index[i]), 'comment': x})
                elif isinstance(x, dict):
                    fixed.append(copy.deepcopy(protected.get(x.get('qid_global'), x)))
                else:
                    fixed.append(x)
            present = {x.get('qid_global') for x in fixed if isinstance(x, dict)}
            fixed.extend(copy.deepcopy(x) for qid, x in protected.items() if qid not in present)
            candidate['per_question_feedback'] = fixed
        overview = candidate.get('open_material_overview')
        if isinstance(overview, dict):
            coerced = coerce_next_steps(overview.get('next_steps'))
            if coerced:
                candidate['open_material_overview'] = dict(overview, next_steps=coerced)
        return candidate

    return {
        **plan,
        'merge': merge,
        'prompt': (
            '上次输出未通过校验。请输出与首轮相同结构的完整 JSON 对象（不要只交 repairs 补丁），'
            '必须同时包含：open_material_overview（其中 next_steps 严格为 ["建议一","建议二"] 这种 1～2 条字符串数组，'
            '禁止「一、……二、……」整段字符串）、per_question_feedback（对象数组，覆盖全部输入单元）、'
            'page_feedback_contexts（若首轮有则保留）。'
            '仅修正下列路径指出的问题，其余已通过内容必须原样保留；数组项不得重排。'
            '证据不足时明确待确认，不得删除引用后保留无据结论。\n'
            + json.dumps(error.issues, ensure_ascii=False)
        ),
    }
