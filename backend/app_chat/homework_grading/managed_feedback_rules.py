"""可管理的批改业务规则；固定协议、校验器和历史快照仍由 Skill 包负责。"""
import copy
import datetime
import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path

from app_chat.ci.file_io import FileLock, atomic_json

from .feedback_context import LEVEL_NAMES
from .feedback_fingerprint import content_sha256
from .feedback_metadata import load_aliases
from .feedback_skills import STAGES
from .feedback_capabilities import load_capability_registry
from .yangqian_debug import debug_log


SCHEMA = 'managed-feedback-rules-v1'
RULES_PATH = Path(__file__).parent / 'data' / 'managed_feedback_rules.json'
HISTORY_CAP = 50
HISTORY_REASONS = {
    'save': '保存前',
    'restore_factory': '恢复出厂前',
    'restore_all': '整包恢复前',
    'rollback': '回滚前',
    'delete': '删除前',
}
USAGE_STAGES = {
    'layout': ('detect',),
    'understanding': ('grade', 'cross_page', 'review'),
    'grading': ('pass2',),
}
USAGE_NAMES = {'layout': '版面', 'understanding': '理解', 'grading': '批改'}
ID_PATTERN = re.compile(r'[a-z0-9][a-z0-9-]{2,79}')
K12_GRADE_LIMITS = {'primary': 6, 'junior': 3, 'senior': 3}


OWNERSHIP_ITEMS = [
    {'name': '普通连续图片 M/T/D/R 提示', 'usage': '连续图片理解与复现',
     'source': 'app_chat/ci_prompts.py、views_continuous_image.py', 'owner': '连续图片理解／复现模块',
     'maintenance': '源码维护', 'status': '在用；本页只读登记'},
    {'name': '旧 DMT 提示', 'usage': '旧版 DMT 处理', 'source': 'app_chat/dmt_prompts.py',
     'owner': 'DMT 相关功能', 'maintenance': '源码维护', 'status': '历史兼容'},
    {'name': '文档总结与主题增强', 'usage': '文档加工',
     'source': 'llm_langchain/enhanced_prompts.py、prompt_enhancement_config.py',
     'owner': '文档加工模块', 'maintenance': '源码维护', 'status': '与梁依枫工作对接'},
    {'name': '文档／用户提示导入', 'usage': '导入普通提示文字',
     'source': 'app_chat/views.py:prompt_upload、utils.py:read_prompt_from_file、llm_langchain/parse_input.py:set_user_prompt',
     'owner': '首页提示词导入／解析模块', 'maintenance': '首页已有入口', 'status': '不等同 Skill 包导入'},
    {'name': '场景模型与模型提示设置', 'usage': '模型参数及场景调用',
     'source': 'app_chat/scene_models.py、core/model_handler.py、core/construct.py',
     'owner': '模型与场景模块', 'maintenance': '管理页现有模型区域', 'status': '在用'},
    {'name': '关键词与语义梳理', 'usage': '关键词和语义网络',
     'source': 'semantic_keyword_service.py、semantic_reorganize_pipeline.py、card_keyword_extract.py',
     'owner': '关键词／语义网络模块', 'maintenance': '对应业务入口', 'status': '梁依枫相关工作'},
    {'name': '本子记忆', 'usage': '本子长短记忆',
     'source': 'notebook_memory.py、memory_tier_consolidation.py', 'owner': '本子记忆模块',
     'maintenance': '源码及既有入口', 'status': '本周不重构'},
    {'name': '任务簇与分组孪生体', 'usage': '任务组织与分组分析',
     'source': 'task_cluster_service.py、group_twin_gxx.py', 'owner': '各自业务模块',
     'maintenance': '对应业务入口', 'status': '本页只读登记'},
    {'name': '卡片图文与图像', 'usage': '卡片内容及图像处理',
     'source': 'views_card_html.py、views_card_image.py、card_value_filter.py', 'owner': '卡片模块',
     'maintenance': '卡片相关入口', 'status': '不与批改规则混用'},
    {'name': '其他场景提示', 'usage': '问答及专项场景',
     'source': 'socratic_probe.py、views_feishu_ta_qa.py、views_seed_gongsheng.py、bodyhealth_edge_views.py',
     'owner': '对应问答／场景模块', 'maintenance': '源码维护', 'status': '需按实际调用逐项核对'},
]


def _rules_path(path=None):
    return Path(path) if path is not None else RULES_PATH


def _lock_path(path):
    digest = hashlib.sha256(str(Path(path).resolve()).encode('utf-8')).hexdigest()
    return Path(tempfile.gettempdir()) / ('nkcn-feedback-rules-' + digest + '.lock')


def _string_list(value, field, *, allowed=None):
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError(field + '必须为数组且不超过20项')
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 80:
            raise ValueError(field + '包含无效值')
        item = item.strip()
        if allowed is not None and item not in allowed:
            raise ValueError(field + '包含未支持的值：' + item)
        if item in result:
            raise ValueError(field + '不能包含重复值')
        result.append(item)
    return result


def _source_rules(skills):
    result = {}
    for skill in skills:
        manifest = skill['content']['manifest']
        for rule in manifest['rules']:
            if rule['id'] in result:
                raise ValueError('原规则标识重复：' + rule['id'])
            result[rule['id']] = {
                'skill_id': skill['id'], 'version': skill['version'],
                'rule': copy.deepcopy(rule),
                'body': skill['content']['resources']['texts'][rule['text_key']],
                'scope': {
                    'education_levels': [] if '*' in manifest['education_scope'] else manifest['education_scope'],
                    'grades': manifest['grades'],
                    'subjects': [] if '*' in manifest['subject_scope'] else manifest['subject_scope'],
                    'material_types': [] if '*' in manifest['material_scope'] else manifest['material_scope'],
                },
            }
    return result


def usages_for_stages(stages):
    usages = []
    if 'detect' in stages:
        usages.append('layout')
    if set(stages) & {'grade', 'cross_page', 'review', 'sessions', 'memory', 'profile', 'ontology'}:
        usages.append('understanding')
    if set(stages) & {'pass2', 'filter', 'quality'}:
        usages.append('grading')
    return usages


def stages_for_usages(usages):
    result = []
    for usage in usages:
        for stage in USAGE_STAGES[usage]:
            if stage not in result:
                result.append(stage)
    return result


def _validate_rule(rule, source_rules):
    if not isinstance(rule, dict):
        raise ValueError('规则条目必须为对象')
    rule_id = rule.get('id')
    if not isinstance(rule_id, str) or not rule_id or len(rule_id) > 120:
        raise ValueError('规则ID无效')
    for field, maximum in (('name', 120), ('body', 20000)):
        value = rule.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(field + '不能为空或过长')
    if type(rule.get('built_in')) is not bool or type(rule.get('enabled', True)) is not bool:
        raise ValueError('规则来源状态无效')
    levels = _string_list(rule.get('education_levels'), 'education_levels', allowed=set(LEVEL_NAMES) - {'unknown'})
    aliases = load_aliases()
    subjects = _string_list(rule.get('subjects'), 'subjects', allowed=set(aliases['subject_names']))
    materials = _string_list(rule.get('material_types'), 'material_types', allowed=set(aliases['material_names']))
    usages = _string_list(rule.get('usages'), 'usages', allowed=set(USAGE_STAGES))
    if not usages:
        raise ValueError('usages至少选择一项')
    grades = rule.get('grades')
    if (not isinstance(grades, list) or len(grades) > 20
            or any(type(value) is not int or not 1 <= value <= 20 for value in grades)
            or len(grades) != len(set(grades))):
        raise ValueError('grades必须为1至20的不重复整数数组')
    if len(levels) > 1:
        raise ValueError('一条规则只能选择一个学段；跨学段请分别建立规则')
    if grades and len(levels) != 1:
        raise ValueError('选择年级前必须先选择一个学段')
    if grades and levels[0] in K12_GRADE_LIMITS and max(grades) > K12_GRADE_LIMITS[levels[0]]:
        raise ValueError('年级必须使用所选学段内的年级数字')
    source = rule.get('source')
    if not isinstance(source, dict) or source.get('kind') not in ('builtin', 'managed'):
        raise ValueError('规则来源无效')
    stages = rule.get('stages')
    if not isinstance(stages, list) or not stages or set(stages) - set(STAGES):
        raise ValueError('规则执行阶段无效')
    for field in ('condition', 'evaluation_item'):
        if not isinstance(rule.get(field), str) or not rule[field]:
            raise ValueError('规则内部字段无效：' + field)
    for field in ('refines', 'conflicts'):
        if not isinstance(rule.get(field, []), list) or any(not isinstance(value, str) for value in rule.get(field, [])):
            raise ValueError('规则组合字段无效：' + field)
    if rule['built_in']:
        original = source_rules.get(rule_id)
        if original is None or source.get('kind') != 'builtin':
            raise ValueError('内置规则来源不存在：' + rule_id)
        expected_source = {'kind': 'builtin', 'skill_id': original['skill_id'], 'version': original['version'],
                           'rule_id': rule_id, 'text_key': original['rule']['text_key']}
        if any(source.get(key) != value for key, value in expected_source.items()):
            raise ValueError('内置规则来源被修改：' + rule_id)
        original_rule = original['rule']
        for field in ('stages', 'condition', 'evaluation_item', 'refines', 'conflicts'):
            if rule.get(field, []) != original_rule.get(field, []):
                raise ValueError('内置规则执行条件被修改：' + rule_id)
        if ({'education_levels': levels, 'grades': grades, 'subjects': subjects,
             'material_types': materials} != original['scope']
                or usages != usages_for_stages(stages)):
            raise ValueError('内置规则适用范围或用途被修改：' + rule_id)
    else:
        if (not ID_PATTERN.fullmatch(rule_id) or source.get('kind') != 'managed'
                or rule['condition'] != 'always'):
            raise ValueError('管理页新增规则只能使用固定匹配条件')
        if stages != stages_for_usages(usages):
            raise ValueError('管理页新增规则用途与执行阶段不一致')
    return rule


def validate_document(document, *, source_skills=None):
    if not isinstance(document, dict) or document.get('schema_version') != SCHEMA:
        raise ValueError('不支持的受管规则格式')
    rules = document.get('rules')
    if not isinstance(rules, list):
        raise ValueError('受管规则清单必须为数组')
    source_skills = load_capability_registry()[0] if source_skills is None else source_skills
    source_rules = _source_rules(source_skills)
    seen = set()
    for rule in rules:
        _validate_rule(rule, source_rules)
        if rule['id'] in seen:
            raise ValueError('受管规则ID重复：' + rule['id'])
        seen.add(rule['id'])
    missing = set(source_rules) - {rule['id'] for rule in rules if rule.get('built_in')}
    if missing:
        raise ValueError('受管规则缺少内置条目：' + '、'.join(sorted(missing)))
    return document


def load_document(path=None, *, source_skills=None):
    target = _rules_path(path)
    try:
        document = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('受管规则文件无法读取：' + str(exc)) from exc
    return validate_document(document, source_skills=source_skills)


def _public_rule(rule):
    return {key: copy.deepcopy(rule[key]) for key in (
        'id', 'name', 'education_levels', 'grades', 'subjects', 'material_types',
        'usages', 'body', 'source', 'built_in')}


def list_rules(path=None):
    document = load_document(path)
    return [_public_rule(rule) for rule in document['rules'] if rule.get('enabled', True)]


def rule_options():
    aliases = load_aliases()
    return {
        'education_levels': [{'value': key, 'label': value} for key, value in LEVEL_NAMES.items() if key != 'unknown'],
        'subjects': [{'value': key, 'label': value} for key, value in aliases['subject_names'].items()],
        'material_types': [{'value': key, 'label': value} for key, value in aliases['material_names'].items()],
        'usages': [{'value': key, 'label': value} for key, value in USAGE_NAMES.items()],
        'grades': list(range(1, 21)),
    }


def _write_update(mutator, path=None):
    target = _rules_path(path)
    with FileLock(_lock_path(target), timeout=10):
        document = load_document(target)
        result = mutator(document)
        validate_document(document)
        atomic_json(target, document)
    return result


def _ensure_history(document):
    history = document.get('history')
    if not isinstance(history, dict):
        document['history'] = {}
        return document['history']
    return history


def _push_history(document, rule, reason):
    if not isinstance(rule, dict) or not rule.get('id'):
        return
    history = _ensure_history(document)
    rid = rule['id']
    entries = history.get(rid)
    if not isinstance(entries, list):
        entries = []
    entries.append({
        'history_id': uuid.uuid4().hex,
        'saved_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'reason': reason if reason in HISTORY_REASONS else 'save',
        'rule': _public_rule(rule),
    })
    history[rid] = entries[-HISTORY_CAP:]
    debug_log(
        f'[feedback_rules] 写入历史 reason={reason} id={rid} history_id={entries[-1]["history_id"]} '
        f'name={rule.get("name")} 条数={len(entries)}'
    )


def _history_entry_public(entry):
    rule = entry.get('rule') if isinstance(entry, dict) else {}
    body = str((rule or {}).get('body') or '')
    return {
        'history_id': entry.get('history_id'),
        'saved_at': entry.get('saved_at'),
        'reason': entry.get('reason'),
        'reason_label': HISTORY_REASONS.get(entry.get('reason'), '保存前'),
        'name': (rule or {}).get('name') or '',
        'body_preview': body[:180],
        'body': body,
    }


def list_rule_history(rule_id, path=None):
    if not isinstance(rule_id, str) or not rule_id or len(rule_id) > 120:
        raise ValueError('规则ID无效')
    document = load_document(path)
    entries = (_ensure_history(document).get(rule_id) or [])
    if not isinstance(entries, list):
        return []
    return [_history_entry_public(item) for item in reversed(entries) if isinstance(item, dict)]


def _apply_snapshot(existing, snap, source_rules):
    if existing.get('built_in'):
        existing['name'] = snap['name']
        existing['body'] = snap['body']
    else:
        for key in ('name', 'education_levels', 'grades', 'subjects', 'material_types', 'usages', 'body'):
            if key in snap:
                existing[key] = copy.deepcopy(snap[key])
        existing['stages'] = stages_for_usages(existing['usages'])
    return _validate_rule(existing, source_rules)


def rollback_rule(rule_id, history_id, path=None):
    if not isinstance(rule_id, str) or not rule_id or len(rule_id) > 120:
        raise ValueError('规则ID无效')
    if not isinstance(history_id, str) or not history_id or len(history_id) > 80:
        raise ValueError('历史版本ID无效')

    def mutate(document):
        entries = _ensure_history(document).get(rule_id) or []
        item = next((entry for entry in entries if isinstance(entry, dict) and entry.get('history_id') == history_id), None)
        if item is None:
            raise ValueError('找不到该历史版本')
        snap = item.get('rule')
        if not isinstance(snap, dict):
            raise ValueError('历史版本内容无效')
        source_rules = _source_rules(load_capability_registry()[0])
        existing = next((rule for rule in document['rules'] if rule['id'] == rule_id), None)
        if existing is not None:
            _push_history(document, existing, 'rollback')
            existing['enabled'] = True
            return _public_rule(_apply_snapshot(existing, snap, source_rules))
        if snap.get('built_in'):
            raise ValueError('内置细则不能借历史版本重建')
        _string_list(snap.get('usages') or [], 'usages', allowed=set(USAGE_STAGES))
        rule = copy.deepcopy(snap)
        rule.update(
            id=rule_id, built_in=False, enabled=True,
            stages=stages_for_usages(rule['usages']), condition='always',
            evaluation_item='managed:' + rule_id, refines=[], conflicts=[],
            source={'kind': 'managed', 'label': '管理页新增'},
        )
        document['rules'].append(rule)
        return _public_rule(_validate_rule(rule, source_rules))

    return _write_update(mutate, path)


def save_rule(payload, path=None):
    if not isinstance(payload, dict):
        raise ValueError('规则数据必须为对象')
    allowed = {'id', 'name', 'education_levels', 'grades', 'subjects', 'material_types', 'usages', 'body'}
    if set(payload) - allowed:
        raise ValueError('规则包含未支持字段')

    def mutate(document):
        rule_id = payload.get('id')
        if rule_id:
            existing = next((rule for rule in document['rules'] if rule['id'] == rule_id and rule.get('enabled', True)), None)
            if existing is None:
                raise ValueError('规则不存在')
            editable = {'name', 'body'} if existing['built_in'] else allowed - {'id'}
            if set(payload) - {'id'} - editable:
                raise ValueError('内置规则只允许修改名称和正文')
            if any(key in payload and payload[key] != existing.get(key) for key in editable):
                _push_history(document, existing, 'save')
            for key in editable:
                if key in payload:
                    existing[key] = copy.deepcopy(payload[key])
            if not existing['built_in']:
                existing['stages'] = stages_for_usages(existing['usages'])
            return _public_rule(_validate_rule(existing, _source_rules(load_capability_registry()[0])))
        required = allowed - {'id'}
        if set(payload) != required:
            raise ValueError('新增规则字段不完整')
        _string_list(payload['usages'], 'usages', allowed=set(USAGE_STAGES))
        new_id = 'managed-' + uuid.uuid4().hex
        rule = copy.deepcopy(payload)
        rule.update(id=new_id, built_in=False, enabled=True,
                    stages=stages_for_usages(rule['usages']), condition='always',
                    evaluation_item='managed:' + new_id, refines=[], conflicts=[],
                    source={'kind': 'managed', 'label': '管理页新增'})
        document['rules'].append(rule)
        return _public_rule(_validate_rule(rule, _source_rules(load_capability_registry()[0])))

    return _write_update(mutate, path)


def restore_rule_body(rule_id, path=None):
    if not isinstance(rule_id, str) or not rule_id or len(rule_id) > 120:
        raise ValueError('规则ID无效')

    def mutate(document):
        index = next((index for index, rule in enumerate(document['rules'])
                      if rule['id'] == rule_id and rule.get('enabled', True)), None)
        if index is None:
            raise ValueError('规则不存在')
        rule = document['rules'][index]
        if not rule.get('built_in'):
            raise ValueError('仅内置细则可恢复出厂正文')
        _push_history(document, rule, 'restore_factory')
        factory = _source_rules(load_capability_registry()[0]).get(rule_id)
        if factory is None:
            raise ValueError('找不到出厂正文：' + rule_id)
        rule['body'] = factory['body']
        return _public_rule(_validate_rule(rule, _source_rules(load_capability_registry()[0])))

    return _write_update(mutate, path)


def compose_skill_md_preview(rules, *, title=None):
    rules = list(rules or [])
    title = str(title or '').strip() or '作业批改内部细则'
    groups = {'layout': [], 'understanding': [], 'grading': []}
    for rule in rules:
        usages = rule.get('usages') or []
        bucket = usages[0] if usages and usages[0] in groups else 'understanding'
        groups[bucket].append(rule)
    claims = [rule for rule in rules if re.search(r'主张|原则|规范|总则', str(rule.get('name') or ''))]
    lines = [
        '---',
        'name: homework-grading-skill',
        'description: 批改内部细则。按材料学段、学科、品类自动套用；内置项不可关闭。Use when 作业、试卷、作文或笔记需要版面识别、理解或批改条文。NOT for 本子教学方法包，也不可改动判分协议底座。',
        'metadata:',
        f'  title: "{title}"',
        '  source: managed_feedback_rules',
        '  standards:',
        '  - Agent Skills Spec',
        '  - NKCN',
        '---',
        '',
        f'# {title}',
        '',
        '## 核心主张',
        '',
    ]
    if claims:
        for rule in claims:
            lines.append(f'### {rule.get("name")}')
            lines.append(str(rule.get('body') or '').strip())
            lines.append('')
    else:
        lines.append('先依据原页可见事实，再评价、再给下一步。专项规则优先于本子方法，不得改对错判定。各用途的具体主张见下方怎么做。')
        lines.append('')
    lines.extend([
        '## 何时用 / 何时不用',
        '',
        '**用在这些场景**：当前范围内的作业、试卷、作文、笔记批改；版面识别、理解作答、整篇诊断与批语组织。',
        '',
        '**不用在这些场景**：改对错判定或可核对的标准答案；关闭内置细则；把本子教学方法写进对错判定；协议底座（字段结构）不在此页修改。',
        '',
        '**与相邻能力的区分**：本子 Skill 是教学方法，启动时可勾选。这里是批改准确率底座，命中材料后自动套用。',
        '',
        '## 怎么做（工作流）',
        '',
    ])
    for usage, heading in (('layout', '版面'), ('understanding', '理解'), ('grading', '批改')):
        lines.extend([f'### {heading}', ''])
        if not groups[usage]:
            lines.append('（当前筛选下无此用途细则）')
            lines.append('')
            continue
        for rule in groups[usage]:
            lines.append(f'#### {rule.get("name")}')
            lines.append(str(rule.get('body') or '').strip())
            lines.append('')
    lines.extend([
        '## 约束与输出期望',
        '',
        '专项规则优先于本子方法；不得改对错判定与可核对的标准答案。解释链用白话三问；作业/试卷单题短评不套三问。改正文只影响此后新开批改，历史批改仍用当时快照。',
        '',
    ])
    return '\n'.join(lines).strip() + '\n'


def restore_builtin_bodies(path=None):
    def mutate(document):
        source_rules = _source_rules(load_capability_registry()[0])
        restored = []
        for rule in document['rules']:
            if not rule.get('built_in'):
                continue
            factory = source_rules.get(rule['id'])
            if factory is None:
                continue
            if rule.get('body') != factory['body']:
                _push_history(document, rule, 'restore_all')
                rule['body'] = factory['body']
                restored.append(rule['id'])
        return {'restored': restored, 'count': len(restored)}

    return _write_update(mutate, path)


def delete_rule(rule_id, path=None):
    if not isinstance(rule_id, str) or not rule_id or len(rule_id) > 120:
        raise ValueError('规则ID无效')

    def mutate(document):
        index = next((index for index, rule in enumerate(document['rules'])
                      if rule['id'] == rule_id and rule.get('enabled', True)), None)
        if index is None:
            raise ValueError('规则不存在')
        if document['rules'][index]['built_in']:
            raise ValueError('内置细则不能删除或关闭，只能编辑正文或恢复出厂')
        _push_history(document, document['rules'][index], 'delete')
        document['rules'].pop(index)
        return {'id': rule_id}

    return _write_update(mutate, path)


def _matches(rule, metadata):
    checks = (
        ('education_levels', metadata.get('education_level')),
        ('subjects', metadata.get('subject_code')),
        ('material_types', metadata.get('material_type')),
    )
    if any(rule[field] and value not in rule[field] for field, value in checks):
        return False
    if rule['grades'] and (metadata.get('grade_status') != 'resolved'
                           or metadata.get('grade_in_level') not in rule['grades']):
        return False
    return True


def bind_managed_rules(metadata, selected_skills, path=None):
    """清除新运行中的旧正文，仅把本材料命中的受管正文放入通用快照。"""
    document = load_document(path)
    selected = copy.deepcopy(selected_skills)
    general = None
    for skill in selected:
        manifest = skill['content']['manifest']
        manifest['rules'] = []
        skill['content']['resources']['texts'] = {}
        if manifest['kind'] == 'general':
            general = skill
    if general is None:
        raise ValueError('缺少通用规则载体')
    matched = []
    for item in document['rules']:
        if not item.get('enabled', True) or not _matches(item, metadata):
            continue
        text_key = 'managed:' + item['id']
        general['content']['manifest']['rules'].append({
            'id': item['id'], 'stages': copy.deepcopy(item['stages']),
            'condition': item['condition'], 'text_key': text_key,
            'evaluation_item': item['evaluation_item'],
            'refines': copy.deepcopy(item.get('refines', [])),
            'conflicts': copy.deepcopy(item.get('conflicts', [])),
        })
        general['content']['resources']['texts'][text_key] = item['body']
        matched.append(item['id'])
    for skill in selected:
        skill['content_hash'] = content_sha256(skill['content'])
    return selected, matched
