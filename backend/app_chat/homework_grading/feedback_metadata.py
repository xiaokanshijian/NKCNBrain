"""filename-dot-v1 的确定性解析。未接入 query/start，不调用模型。"""

import hashlib
import copy
import json
import ntpath
import re
import unicodedata
from pathlib import Path

PARSER_VERSION = 'filename-dot-v1'
FIELD_NAMES = ('education_level', 'grade', 'subject', 'material_type')
UNKNOWN = {'', '未知', '未注明', 'unknown'}
_NUMBERS = {name: index for index, name in enumerate(
    ('', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'))}


def load_aliases():
    with (Path(__file__).parent / 'data' / 'feedback_aliases.json').open(encoding='utf-8') as handle:
        return json.load(handle)


def normalize_text(value):
    if not isinstance(value, str):
        raise ValueError('材料属性必须为文字')
    return unicodedata.normalize('NFKC', value).strip()


def is_unknown(value):
    return value is None or normalize_text(value).casefold() in UNKNOWN


def grade_token(value):
    """只识别文字，不在此处推导学制。返回明确前缀和数字。"""
    text = normalize_text(value)
    match = re.fullmatch(r'(初|高|大)([一二三四五六七八九十]+|\d+)', text)
    prefix = ''
    if match:
        prefix, number = match.groups()
    else:
        match = re.fullmatch(r'([一二三四五六七八九十]+|\d+)年级', text)
        if not match:
            return None
        number = match.group(1)
    number = int(number) if number.isascii() and number.isdigit() else _NUMBERS.get(number)
    if number is None or number < 1:
        return None
    return ({'初': 'junior', '高': 'senior', '大': 'university'}.get(prefix), number)


def normalize_field(field, value, aliases=None):
    aliases = aliases or load_aliases()
    if is_unknown(value):
        return None
    text = normalize_text(value)
    if field == 'grade':
        return text if grade_token(text) else None
    return aliases[field].get(text.casefold(), text if field != 'education_level' else 'other')


def custom_key(name):
    return 'custom:' + hashlib.sha256(normalize_text(name).encode('utf-8')).hexdigest()


def parse_feedback_filename(filename):
    if not isinstance(filename, str):
        raise ValueError('文件名必须为文字')
    aliases = load_aliases()
    basename = ntpath.basename(filename)
    is_pdf = basename.lower().endswith('.pdf')
    stem = basename[:-4] if is_pdf else basename
    text = unicodedata.normalize('NFKC', stem).replace('・', '·').replace('•', '·')
    slots = [part.strip() for part in text.split('·')]
    fields, issues = {}, []
    structured = len(slots) >= 4
    for index, field in enumerate(FIELD_NAMES):
        raw = slots[index] if index < len(slots) and len(slots) > 1 else ''
        value = normalize_field(field, raw, aliases)
        status = 'missing' if is_unknown(raw) else 'declared'
        if field == 'grade' and value is None and status != 'missing':
            status = 'ambiguous'
        # 已登记的其他槽位值出现在本槽，不把它解释成自定义名称。
        elif status != 'missing' and field != 'grade':
            belongs_elsewhere = any(raw.casefold() in aliases[key] for key in
                                   ('education_level', 'subject', 'material_type') if key != field)
            if belongs_elsewhere or grade_token(raw):
                value, status = None, 'ambiguous'
        fields[field] = {'raw': raw, 'value': value, 'status': status}
    # 缺年级引起的连续错位：未知末槽不能被当作自定义品类。
    if fields['grade']['status'] == 'ambiguous' and fields['subject']['status'] == 'ambiguous':
        fields['material_type'].update(value=None, status='ambiguous')
    token = grade_token(fields['grade']['raw'])
    level = fields['education_level']['value']
    if token and token[0] and level not in (None, token[0]):
        fields['grade']['status'] = 'conflict'
        fields['education_level']['status'] = 'conflict'
    for field, item in fields.items():
        if item['status'] != 'declared':
            issues.append({'field': field, 'code': item['status'], 'message': {
                'missing': '材料属性未注明，可补充或保持未知',
                'ambiguous': '槽位含义不明确，请核对学段、年级、学科、品类的顺序',
                'conflict': '学段和年级声明冲突，请核对后修正',
            }[item['status']]})
    if not is_pdf:
        issues.append({'field': 'filename', 'code': 'not_pdf', 'message': '文件名没有PDF后缀'})
    if not structured:
        issues.append({'field': 'filename', 'code': 'unstructured', 'message': '未形成四槽声明，可在材料设置中补充'})
    statuses = {item['status'] for item in fields.values()}
    status = ('invalid' if not is_pdf else 'unstructured' if not structured else
              'conflict' if 'conflict' in statuses else 'ambiguous' if 'ambiguous' in statuses else
              'partial' if 'missing' in statuses else 'parsed')
    return {'parser_version': PARSER_VERSION, 'alias_version': aliases['version'],
            'original_filename': filename, 'basename': basename, 'slots': slots,
            'title': '·'.join(slots[4:]) if structured else stem,
            'parse_status': status, 'fields': fields, 'issues': issues}


def resolve_grade(level, value, *, infer_level=True, school_system=None):
    """六三三映射只用于明确的K12范围；非标准学制保留原说明。"""
    result = {'education_level': level or 'unknown', 'grade_in_level': None,
              'grade_global': None, 'grade_label': value or None, 'grade_status': 'unknown'}
    if is_unknown(value):
        return result
    token = grade_token(value)
    if not token:
        result['grade_status'] = 'unconfirmed'
        return result
    prefix, number = token
    if prefix and level and level != prefix:
        result['grade_status'] = 'conflict'
        return result
    if not level and infer_level:
        level = prefix or ('primary' if number <= 6 else 'junior' if number <= 9 else 'senior' if number <= 12 else None)
        if level:
            result['education_level'] = level
            result['level_inferred'] = True
    if not level:
        return result
    if school_system not in (None, '', '6-3-3'):
        result['grade_status'] = 'unconfirmed'
        return result
    offsets = {'primary': (0, 6), 'junior': (6, 3), 'senior': (9, 3)}
    if level in offsets:
        offset, size = offsets[level]
        local = number if prefix or number <= size else number - offset
        if not 1 <= local <= size:
            result['grade_status'] = 'conflict'
            return result
        result.update(grade_in_level=local, grade_global=offset + local,
                      grade_label=next(k for k, v in _NUMBERS.items() if v == offset + local) + '年级',
                      grade_status='resolved')
    elif level == 'university' and prefix == 'university':
        result.update(grade_in_level=number, grade_status='resolved')
    else:
        result['grade_status'] = 'unconfirmed'
    return result


def resolve_feedback_metadata(filename, overrides=None, reliable_observations=None):
    """observation参数只能由调用者传入已确认可靠的启动前观察。null为锁定未知。"""
    overrides = {} if overrides is None else overrides
    observations = {} if reliable_observations is None else reliable_observations
    allowed = set(FIELD_NAMES) | {'term', 'textbook', 'school_system'}
    for value in (overrides, observations):
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValueError('材料覆盖/观察字段无效')
        for item in value.values():
            if item is not None and not isinstance(item, str):
                raise ValueError('材料属性必须为文字或空值')
    parsed = parse_feedback_filename(filename)
    values, sources, locked, raw_values = {}, {}, [], {}
    for key in sorted(allowed):
        field = parsed['fields'].get(key, {})
        # 冲突声明也必须保留，不能让观察替换后掩盖冲突；最终重新交叉校验。
        if key in overrides:
            raw, source = overrides[key], 'override'
            if is_unknown(raw):
                locked.append(key)
        elif field.get('status') in ('declared', 'conflict'):
            raw, source = field['raw'], 'filename'
        elif field.get('status') != 'ambiguous' and key in observations:
            raw, source = observations[key], 'observation'
        else:
            raw, source = None, 'unknown'
        raw_values[key] = raw
        values[key] = normalize_field(key, raw) if key in FIELD_NAMES else (None if is_unknown(raw) else normalize_text(raw))
        sources[key] = source
    grade = resolve_grade(values['education_level'], raw_values['grade'],
                          infer_level='education_level' not in locked, school_system=values['school_system'])
    if grade.pop('level_inferred', False):
        sources['education_level'] = 'inferred'
    aliases = load_aliases()
    subject = values['subject']
    material = values['material_type']
    known_subject = subject in aliases['subject_names']
    known_material = material in aliases['material_names']
    # 未确认年级、矛盾声明保留原文，不交给范围匹配当有效年级。
    issues = copy.deepcopy(parsed['issues'])
    if grade['grade_status'] in ('conflict', 'unconfirmed'):
        issues.append({'field': 'grade', 'code': grade['grade_status'],
                       'message': '学段年级或学制尚未确认，不使用依赖该范围的规则'})
    return {'parser_version': PARSER_VERSION, 'alias_version': aliases['version'],
            'subject_code': subject if known_subject else 'other' if subject else 'unknown',
            'subject_name': aliases['subject_names'].get(subject, subject),
            'subject_key': subject if known_subject else custom_key(subject) if subject else 'unknown',
            'material_type': material if known_material else 'other' if material else 'unknown',
            'material_name': aliases['material_names'].get(material, material),
            'material_key': material if known_material else custom_key(material) if material else 'unknown',
            **grade, 'term': values['term'], 'textbook': values['textbook'], 'school_system': values['school_system'],
            'metadata_source': sources, 'locked_unknown_fields': sorted(locked),
            'declared_metadata': {'filename': parsed, 'overrides': copy.deepcopy(overrides),
                                  'reliable_observations': copy.deepcopy(observations), 'selected_raw': raw_values},
            'issues': issues}


def resolve_resource_stage(metadata, resource_stages):
    """只返回传入资源中唯一匹配的阶段；不加载课标，不制造S4绑定。

    resource_stages: [{stage_key, education_level, grade_min, grade_max}]
    年级范围为资源明确声明的阶段内年级；只有一个匹配才返回键。
    """
    if metadata.get('grade_status') != 'resolved':
        return None
    grade = metadata.get('grade_in_level')
    if type(grade) is not int:
        return None
    matches = []
    for stage in resource_stages:
        if not isinstance(stage, dict):
            raise ValueError('课程阶段必须为对象')
        low, high = stage.get('grade_min'), stage.get('grade_max')
        if type(low) is not int or type(high) is not int or low > high or not stage.get('stage_key'):
            raise ValueError('课程阶段范围无效')
        if stage.get('education_level') == metadata.get('education_level') and low <= grade <= high:
            matches.append(stage['stage_key'])
    return matches[0] if len(matches) == 1 else None
