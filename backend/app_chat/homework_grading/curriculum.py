"""课程标准课标树加载器（nkcn 自有，数据位于本包 data/curriculum/）。

改编自 yq v2.0 prompts.py / hallucination_filter.py / profile_builder.py 中
分散的课标加载逻辑，统一收口于此，供 llm.py、hallucination_filter.py、profile.py 复用。
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
_CURRICULUM_DIR = os.path.join(_DATA_DIR, 'curriculum')


@lru_cache(maxsize=8)
def load_curriculum_tree(subject: str) -> Dict[str, Any]:
    path = os.path.join(_CURRICULUM_DIR, f'{subject}_curriculum.json')
    if not os.path.exists(path):
        return {'domains': []}
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)


def iter_curriculum_kps(
    tree: Dict[str, Any],
    stage: Optional[int] = None,
) -> Iterator[Tuple[Optional[int], str, Dict[str, Any]]]:
    """Iterate ``(stage, domain_name, kp)`` over both yq v2.5 and legacy trees."""
    stages = tree.get('stages')
    if isinstance(stages, list):
        for stage_entry in stages:
            stage_num = stage_entry.get('stage')
            if stage is not None and stage_num != stage:
                continue
            for domain in stage_entry.get('domains', []) or []:
                domain_name = domain.get('name', '')
                for kp in domain.get('knowledge_points', []) or []:
                    yield stage_num, domain_name, kp
        return

    for domain in tree.get('domains', []) or []:
        domain_name = domain.get('name', '')
        for kp in domain.get('knowledge_points', []) or []:
            yield None, domain_name, kp


def load_curriculum_labels(subject: str, stage: Optional[int] = None) -> List[str]:
    tree = load_curriculum_tree(subject)
    return [
        kp['label']
        for _stage, _domain, kp in iter_curriculum_kps(tree, stage=stage)
        if kp.get('label')
    ]


def load_curriculum_entries(subject: str, stage: Optional[int] = None) -> List[Dict[str, Any]]:
    tree = load_curriculum_tree(subject)
    entries: List[Dict[str, Any]] = []
    for stage_num, domain_name, kp in iter_curriculum_kps(tree, stage=stage):
        if kp.get('id') and kp.get('label'):
            entries.append({
                'id': kp['id'],
                'label': kp['label'],
                'domain': domain_name,
                'stage': stage_num,
                'grade_band': kp.get('grade_band', ''),
                'description': kp.get('description', ''),
                'cognitive_level': kp.get('cognitive_level', ''),
            })
    return entries


def curriculum_index(subject: str, stage: Optional[int] = None) -> Tuple[Set[str], Set[str], List[str]]:
    """返回 (curriculum_ids, curriculum_labels, all_descriptions)。"""
    ids: Set[str] = set()
    labels: Set[str] = set()
    descriptions: List[str] = []
    for entry in load_curriculum_entries(subject, stage=stage):
        ids.add(entry['id'])
        labels.add(entry['label'])
        if entry['description']:
            descriptions.append(entry['description'])
    return ids, labels, descriptions


def label_to_id_map(subject: str, stage: Optional[int] = None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for entry in load_curriculum_entries(subject, stage=stage):
        out.setdefault(entry['label'], entry['id'])
    return out


def label_to_domain_map(subject: str, stage: Optional[int] = None) -> Dict[str, str]:
    """label → 课标领域名（用于知识点掌握度按领域聚合）。"""
    return {entry['label']: entry['domain'] for entry in load_curriculum_entries(subject, stage=stage)}


def _short_cn_name(description: str, label: str) -> str:
    """从课标中文描述派生简短知识点名称，缺失时回退英文 label。"""
    text = (description or '').strip()
    if not text:
        return label
    for sep in ('，', '。', '；', '：', '、', ',', '.', ';'):
        idx = text.find(sep)
        if idx > 0:
            return text[:idx].strip()
    return text


@lru_cache(maxsize=8)
def _load_label_mapping(subject: str) -> Dict[str, str]:
    """加载英译中术语映射表（{subject}_curriculum_label_mapping.json）。"""
    path = os.path.join(_DATA_DIR, f'{subject}_curriculum_label_mapping.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


@lru_cache(maxsize=8)
def label_to_cn_map(subject: str) -> Dict[str, str]:
    """label → 简短中文知识点名（用于前端展示，避免出现英文术语）。
    优先查映射表，次用 description 派生，最后回退英文 label。
    """
    mapping = _load_label_mapping(subject)
    out: Dict[str, str] = {}
    for entry in load_curriculum_entries(subject):
        lbl = entry['label']
        if lbl in mapping:
            out.setdefault(lbl, mapping[lbl])
        else:
            out.setdefault(lbl, _short_cn_name(entry.get('description', ''), lbl))
    for lbl, cn in mapping.items():
        out.setdefault(lbl, cn)
    return out


def label_to_cn(subject: str, label: str) -> str:
    """单个 label → 中文名，未命中时原样返回。"""
    if not label:
        return ''
    return label_to_cn_map(subject).get(label, label)


@lru_cache(maxsize=8)
def id_to_entry_map(subject: str) -> Dict[str, Dict[str, Any]]:
    """课标 id（如 MA_S2_038）→ 条目。"""
    return {entry['id']: entry for entry in load_curriculum_entries(subject) if entry.get('id')}


def id_to_cn(subject: str, curriculum_id: str) -> str:
    """课标 id → 给人看的中文知识点名；未命中返回空串。"""
    entry = id_to_entry_map(subject).get(str(curriculum_id or '').strip())
    if not entry:
        return ''
    mapped = label_to_cn(subject, entry.get('label') or '')
    if mapped and mapped != entry.get('label'):
        return mapped
    return _short_cn_name(entry.get('description') or '', entry.get('label') or '')


_CURRICULUM_ID_RE = re.compile(r'^[A-Z]{2}_S\d+_\d+$')
# 模型有时把课标白名单整行写进 knowledge_point，如：
# EN_S2_040 [expressing_feelings, 掌握, 写作]
# EN_S2_021 [tense_usage, 理解, 语音] 理解一般现在时…
# 用户可见：去掉课标码即可；[label, 认知, 领域] 与后面中文说明都可保留。
_CURRICULUM_LINE_RE = re.compile(
    r'^(?P<id>[A-Z]{2}_S\d+_\d+)'
    r'(?:\s*(?P<meta>\[[^\]]*\]))?'
    r'(?:\s+(?P<desc>.+))?$'
)
_CURRICULUM_ID_ANYWHERE_RE = re.compile(r'\b([A-Z]{2}_S\d+_\d+)\b')


def strip_curriculum_codes(text: str) -> str:
    """只去掉课标码（如 EN_S2_040）；保留 [label, 认知, 领域] 与中文说明。"""
    raw = str(text or '').strip()
    if not raw:
        return ''
    m = _CURRICULUM_LINE_RE.match(raw)
    if m:
        meta = (m.group('meta') or '').strip()
        desc = (m.group('desc') or '').strip()
        parts = [p for p in (meta, desc) if p]
        if parts:
            return ' '.join(parts)
        # 仅有课标码：用中文短名兜底（调用方需传入 subject 时走 humanize）
        return ''
    cleaned = _CURRICULUM_ID_ANYWHERE_RE.sub('', raw)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(' ·|-')
    return cleaned


# 兼容旧名
def strip_curriculum_jargon(text: str) -> str:
    return strip_curriculum_codes(text)


def humanize_knowledge_point(subject: str, value: str) -> str:
    """展示用知识点名：去掉课标码；保留可读的 [label, 认知, 领域] 与中文说明。

    全学科通用（math / chinese / english）。
    """
    text = str(value or '').strip()
    if not text or text in ('no_observed',):
        return ''
    # 整行：EN_S2_021 [tense_usage, 理解, 语音] 理解一般现在时…
    line = _CURRICULUM_LINE_RE.match(text)
    if line:
        meta = (line.group('meta') or '').strip()
        desc = (line.group('desc') or '').strip()
        parts = [p for p in (meta, desc) if p]
        if parts:
            return ' '.join(parts)
        # 只有课标码时，换成中文短名，避免界面露码
        return id_to_cn(subject, line.group('id')) or ''
    if _CURRICULUM_ID_RE.match(text):
        return id_to_cn(subject, text) or ''
    # 句中夹带课标码：只剥码，其余原样
    if _CURRICULUM_ID_ANYWHERE_RE.search(text):
        stripped = strip_curriculum_codes(text)
        return stripped or text
    # 纯英文 label：有中文映射则用映射，便于单独出现时也好读
    cn = label_to_cn(subject, text)
    if cn and cn != text:
        return cn
    if re.fullmatch(r'[A-Za-z0-9_]+', text):
        return id_to_cn(subject, text) or text
    return text


def domains_of(subject: str, stage: Optional[int] = None) -> List[str]:
    tree = load_curriculum_tree(subject)
    seen: Set[str] = set()
    out: List[str] = []
    for _stage, domain_name, _kp in iter_curriculum_kps(tree, stage=stage):
        if domain_name and domain_name not in seen:
            seen.add(domain_name)
            out.append(domain_name)
    return out
