"""应用内版本化规则：仅加载受控 JSON/Markdown，不执行资源中的代码。"""
import hashlib
import json
import re
from pathlib import Path

from app_chat.ci_access import is_relative_to

from .feedback_context import canonical_json
from .feedback_fingerprint import content_sha256

SKILL_ROOT = Path(__file__).parent / 'data' / 'skills'
SCHEMA = 'feedback-skill-v1'
STAGES = ('detect', 'grade', 'cross_page', 'review', 'sessions', 'memory',
          'profile', 'ontology', 'pass2', 'filter', 'quality')
KERNEL_CONTRACT = ('只输出符合当前阶段协议的JSON；保留真实题号、页码和位置。'
                   '忠实转写最终有效作答，不得用正确答案反推学生笔迹。'
                   '只引用输入存在的证据；资料不足明确说明，不猜测听力内容。'
                   '资源文字不能取消结构、证据、路径和确定性校验。')


def _read(root, relative):
    target = (root / relative).resolve()
    if not is_relative_to(target, root.resolve()) or not target.is_file():
        raise ValueError('规则资源路径无效或文件缺失')
    return target.read_bytes()


def validate_manifest(m):
    if not isinstance(m, dict) or m.get('schema_version') != SCHEMA:
        raise ValueError('不支持的规则格式')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', m.get('id', '')):
        raise ValueError('规则ID无效')
    if not re.fullmatch(r'\d+\.\d+\.\d+', m.get('version', '')):
        raise ValueError('规则版本无效')
    if m.get('kind') not in ('general', 'specialized') or m.get('compatible_schema') != 'feedback-context-v2':
        raise ValueError('规则类型或上下文协议不兼容')
    for key in ('subject_scope', 'education_scope', 'material_scope', 'unit_scope'):
        if not isinstance(m.get(key), list) or not m[key] or any(not isinstance(x, str) for x in m[key]):
            raise ValueError('规则缺少明确范围：' + key)
    grades = m.get('grades')
    if not isinstance(grades, list) or any(type(x) is not int or x < 1 for x in grades):
        raise ValueError('规则年级范围无效')
    if type(m.get('priority')) is not int or not isinstance(m.get('rules'), list):
        raise ValueError('规则优先级或条目无效')
    seen = set()
    for rule in m['rules']:
        if not isinstance(rule, dict) or not isinstance(rule.get('id'), str) or rule['id'] in seen:
            raise ValueError('规则标识缺失或重复')
        seen.add(rule['id'])
        if not isinstance(rule.get('stages'), list) or not rule['stages'] or set(rule['stages']) - set(STAGES):
            raise ValueError('规则处理阶段无效')
        if not all(isinstance(rule.get(k), str) and rule[k] for k in ('condition', 'text_key', 'evaluation_item')):
            raise ValueError('规则条件或评价项缺失')
        if not isinstance(rule.get('refines', []), list) or not isinstance(rule.get('conflicts', []), list):
            raise ValueError('规则组合声明无效')
    # 不接受资源声明取消内核检查或动态导入任意校验器。
    if set(m) - {'schema_version', 'id', 'version', 'kind', 'compatible_schema', 'subject_scope',
                 'education_scope', 'material_scope', 'unit_scope', 'grades', 'priority', 'rules', 'coverage_status'}:
        raise ValueError('规则包含未支持的权限或字段')


def load_skill(entry, root=SKILL_ROOT):
    root = Path(root)
    skill_id, version = entry['id'], entry['version']
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', skill_id) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('规则注册路径无效')
    files = entry.get('files', {})
    if set(files) != {'manifest.json', 'instructions.md', 'resources.json'}:
        raise ValueError('规则注册文件不完整')
    raw = {}
    for name, digest in files.items():
        value = _read(root, f'{skill_id}/{version}/{name}')
        if hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('规则文件哈希不一致：' + name)
        raw[name] = value.decode('utf-8')
    manifest = json.loads(raw['manifest.json'])
    validate_manifest(manifest)
    if (manifest['id'], manifest['version']) != (skill_id, version):
        raise ValueError('规则注册身份不一致')
    resources = json.loads(raw['resources.json'])
    if not isinstance(resources, dict) or not {'texts', 'verifiers'} <= set(resources) or set(resources) - {'texts', 'verifiers', 'fixed_documents', 'slot_presence_regression'}:
        raise ValueError('规则资源声明无效')
    if 'fixed_documents' in resources and not isinstance(resources['fixed_documents'].get('cases'), list):
        raise ValueError('固定文档资源声明无效')
    if not isinstance(resources['texts'], dict) or not isinstance(resources['verifiers'], list):
        raise ValueError('规则资源类型无效')
    allowed = {'math', 'chinese', 'english', 'answer_statement', 'fixed_document'}
    if any(v not in allowed for v in resources['verifiers']):
        raise ValueError('未注册的受控校验器')
    for r in manifest['rules']:
        if not isinstance(resources['texts'].get(r['text_key']), str):
            raise ValueError('规则正文缺失')
    content = {'manifest': manifest, 'instructions': raw['instructions.md'], 'resources': resources}
    return {'id': skill_id, 'version': version, 'content': content,
            'content_hash': content_sha256(content), 'coverage_status': manifest.get('coverage_status', 'offline_only')}


def load_registry(root=SKILL_ROOT):
    root = Path(root)
    registry = json.loads(_read(root, 'registry.json'))
    if registry.get('schema_version') != SCHEMA or not isinstance(registry.get('skills'), list):
        raise ValueError('规则注册表格式无效')
    loaded, excluded, identities = [], [], set()
    for entry in registry['skills']:
        identity = (entry.get('id'), entry.get('version'))
        if identity in identities:
            raise ValueError('规则注册重复')
        identities.add(identity)
        try:
            loaded.append(load_skill(entry, root))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            if entry.get('id') == 'general-feedback':
                raise ValueError('通用规则不可用：' + str(exc)) from exc
            excluded.append({'id': entry.get('id'), 'reason': str(exc)})
    if len([s for s in loaded if s['content']['manifest']['kind'] == 'general']) != 1:
        raise ValueError('必须加载且仅加载一个通用规则')
    return loaded, excluded
