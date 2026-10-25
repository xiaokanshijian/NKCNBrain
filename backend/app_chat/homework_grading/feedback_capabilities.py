"""新运行能力目录：仅范围、规则身份和确定性资源，不读取退役说明正文。"""
import copy
import json
from pathlib import Path

from .feedback_fingerprint import content_sha256
from .feedback_skills import validate_manifest

SCHEMA = 'feedback-capabilities-v1'
CAPABILITIES_PATH = Path(__file__).parent / 'data' / 'feedback_capabilities.json'
VERIFIERS = {'math', 'chinese', 'english', 'answer_statement', 'fixed_document'}


def load_capability_registry(path=None):
    document = json.loads(Path(path or CAPABILITIES_PATH).read_text(encoding='utf-8'))
    if (not isinstance(document, dict) or document.get('schema_version') != SCHEMA
            or set(document) != {'schema_version', 'capabilities'}
            or not isinstance(document['capabilities'], list)):
        raise ValueError('不支持的批改能力目录格式')
    result, identities = [], set()
    for item in document['capabilities']:
        if not isinstance(item, dict) or set(item) != {'manifest', 'resources'}:
            raise ValueError('批改能力条目格式无效')
        manifest, resources = copy.deepcopy(item['manifest']), copy.deepcopy(item['resources'])
        validate_manifest(manifest)
        identity = (manifest['id'], manifest['version'])
        if identity in identities:
            raise ValueError('批改能力身份重复')
        identities.add(identity)
        if (not isinstance(resources, dict) or set(resources) - {'verifiers', 'fixed_documents', 'slot_presence_regression'}
                or not isinstance(resources.get('verifiers'), list)
                or any(v not in VERIFIERS for v in resources['verifiers'])):
            raise ValueError('批改能力包含未注册的资源或校验器')
        if 'fixed_documents' in resources and (not isinstance(resources['fixed_documents'], dict)
                or not isinstance(resources['fixed_documents'].get('cases'), list)):
            raise ValueError('固定文档资源声明无效')
        # 空正文仅用于组合规则身份和冲突；正常启动随后绑定受管正文。
        resources['texts'] = {rule['text_key']: '' for rule in manifest['rules']}
        content = {'resource_schema': SCHEMA, 'manifest': manifest, 'resources': resources, 'instructions': ''}
        result.append({'id': manifest['id'], 'version': manifest['version'], 'content': content,
                       'content_hash': content_sha256(content),
                       'coverage_status': manifest.get('coverage_status', 'offline_only')})
    if sum(s['content']['manifest']['kind'] == 'general' for s in result) != 1:
        raise ValueError('批改能力目录必须包含唯一通用能力')
    return result, []
