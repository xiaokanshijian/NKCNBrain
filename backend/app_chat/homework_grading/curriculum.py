"""课程标准课标树加载器（nkcn 自有，数据位于本包 data/curriculum/）。

改编自 yq v2.0 prompts.py / hallucination_filter.py / profile_builder.py 中
分散的课标加载逻辑，统一收口于此，供 llm.py、hallucination_filter.py、profile.py 复用。
"""

from __future__ import annotations

import json
import os
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


def domains_of(subject: str, stage: Optional[int] = None) -> List[str]:
    tree = load_curriculum_tree(subject)
    seen: Set[str] = set()
    out: List[str] = []
    for _stage, domain_name, _kp in iter_curriculum_kps(tree, stage=stage):
        if domain_name and domain_name not in seen:
            seen.add(domain_name)
            out.append(domain_name)
    return out
