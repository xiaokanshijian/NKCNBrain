"""
ci/_context.py — CI 上下文共享模块。

Phase 5.1 / 5.2 迁移：
    - 上下文采集与筛选
    - 检索词抽取与匹配
    - M 层上下文化格式化
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app_chat.ci._utils import _read_text_if_exists
from app_chat.ci_prompts import (
    CI_M_LAYER_CONTEXT_BRIEF_TEMPLATE,
    CI_M_LAYER_CONTEXT_FULL_TEMPLATE,
)


def _load_related_doc_summaries(username: str, selected_file_names: List[str]) -> List[Dict[str, str]]:
    docs: List[Dict[str, str]] = []
    base_user_dir = os.path.join('.', 'received_dir', 'user_raw_file', username)

    for file_name in selected_file_names:
        ext = os.path.splitext(file_name)[1].lower()
        base = os.path.splitext(os.path.basename(file_name))[0]
        ext_no_dot = ext[1:] if ext else ''

        pre_summary_path = os.path.join(base_user_dir, 'pre_summary', f'{base}_Presummary_{ext_no_dot}.md')
        pre_image_summary_path = os.path.join(base_user_dir, 'pre_image_summary', f'{base}_PreImageSummary_pdf.md')

        pre_summary_text = _read_text_if_exists(pre_summary_path, '')
        pre_image_summary_text = _read_text_if_exists(pre_image_summary_path, '')

        if pre_summary_text or pre_image_summary_text:
            docs.append({
                'file_name': file_name,
                'pre_summary': pre_summary_text[:3000],
                'pre_image_summary': pre_image_summary_text[:3000],
            })

    return docs


def _gather_notebook_context(username: str) -> Dict[str, Any]:
    """收集本子级上下文：场景信息 + 全量文档摘要 + 本子内卡片知识。"""
    from app_chat.models import Card
    from app_chat.scene_context_helper import get_scene_info_from_username

    scene_name, sub_scene_name, scene_summary, notebook_description = get_scene_info_from_username(username)

    doc_summaries: List[Dict[str, str]] = []
    base_user_dir = os.path.join('.', 'received_dir', 'user_raw_file', username)
    pre_summary_dir = os.path.join(base_user_dir, 'pre_summary')
    if os.path.isdir(pre_summary_dir):
        for file_name in sorted(os.listdir(pre_summary_dir)):
            if not file_name.endswith('.md'):
                continue
            file_path = os.path.join(pre_summary_dir, file_name)
            text = _read_text_if_exists(file_path, '')
            if text:
                doc_summaries.append({'file_name': file_name, 'summary': text[:3000]})

    card_summaries: List[Dict[str, str]] = []
    try:
        cards = Card.objects.filter(username=username).order_by('-confidence_score', '-cid')[:50]
        for card in cards:
            card_summaries.append({
                'cid': card.cid,
                'title': (card.contentTitle or card.title or '')[:100],
                'keywords': (card.keyWords or '')[:200],
                'preview': (card.content or '')[:300],
                'confidence_score': card.confidence_score,
            })
    except Exception as error:
        print(f'[ci] _gather_notebook_context 卡片查询失败: {error}')

    return {
        'scene_name': scene_name or '',
        'sub_scene_name': sub_scene_name or '',
        'scene_summary': (scene_summary or '')[:600],
        'notebook_description': (notebook_description or '')[:400],
        'doc_summaries': doc_summaries,
        'card_summaries': card_summaries,
    }


def _extract_ci_context_terms(selected_files: Optional[List[str]], notebook_ctx: Dict[str, Any]) -> List[str]:
    """从分析文件名与场景信息中抽取轻量检索词。"""
    terms: List[str] = []
    for file_name in selected_files or []:
        base = os.path.splitext(os.path.basename(file_name))[0].lower()
        for token in re.findall(r'[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}', base):
            if token not in terms:
                terms.append(token)

    scene_text = ' '.join([
        notebook_ctx.get('scene_name', '') or '',
        notebook_ctx.get('sub_scene_name', '') or '',
    ]).lower()
    for token in re.findall(r'[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}', scene_text):
        if token not in terms:
            terms.append(token)
    return terms[:20]


def _text_match_score(text: str, terms: List[str]) -> float:
    if not text or not terms:
        return 0.0
    content = text.lower()
    score = 0.0
    for term in terms:
        if term in content:
            score += 1.0
    return score


def _normalize_doc_key(name: str) -> str:
    """标准化文档名用于精确匹配（忽略扩展名、空白、下划线、中划线）。"""
    base = os.path.splitext(os.path.basename(name or ''))[0].strip().lower()
    return re.sub(r'[\s_\-]+', '', base)


def _extract_source_key_from_presummary_name(name: str) -> str:
    """从 pre_summary 文件名中提取原始文档名 key。"""
    base_name = os.path.basename(name or '')
    match = re.match(r'^(.+?)_Presummary_[^.]+\.md$', base_name, flags=re.IGNORECASE)
    source_name = match.group(1) if match else base_name
    return _normalize_doc_key(source_name)


def _auto_select_context(notebook_ctx: Dict[str, Any], selected_files: Optional[List[str]] = None,
                         max_docs: int = 6, max_cards: int = 12) -> Dict[str, Any]:
    """自动模式：轻量智能召回上下文，避免全量注入。"""
    result = dict(notebook_ctx)
    terms = _extract_ci_context_terms(selected_files, notebook_ctx)

    docs = notebook_ctx.get('doc_summaries', [])
    scored_docs: List[Tuple[float, Dict[str, Any]]] = []
    for doc in docs:
        name = doc.get('file_name', '')
        summary = doc.get('summary', '')
        score = 3.0 * _text_match_score(name, terms) + _text_match_score(summary[:1500], terms)
        scored_docs.append((score, doc))
    scored_docs.sort(key=lambda item: item[0], reverse=True)
    if terms:
        chosen_docs = [doc for score, doc in scored_docs if score > 0][:max_docs]
        if not chosen_docs:
            chosen_docs = [doc for _, doc in scored_docs[:max_docs]]
    else:
        chosen_docs = [doc for _, doc in scored_docs[:max_docs]]
    result['doc_summaries'] = chosen_docs

    cards = notebook_ctx.get('card_summaries', [])
    scored_cards: List[Tuple[float, Dict[str, Any]]] = []
    for card in cards:
        title = card.get('title', '')
        keywords = card.get('keywords', '')
        preview = card.get('preview', '')
        confidence = card.get('confidence_score')
        confidence_score = float(confidence) if isinstance(confidence, (int, float)) and confidence is not None else 0.0
        score = 2.0 * _text_match_score(title, terms) + 2.0 * _text_match_score(keywords, terms) + _text_match_score(preview, terms)
        score += 0.2 * confidence_score
        scored_cards.append((score, card))
    scored_cards.sort(key=lambda item: item[0], reverse=True)
    if terms:
        chosen_cards = [card for score, card in scored_cards if score > 0][:max_cards]
        if not chosen_cards:
            chosen_cards = [card for _, card in scored_cards[:max_cards]]
    else:
        chosen_cards = [card for _, card in scored_cards[:max_cards]]
    result['card_summaries'] = chosen_cards
    return result


def _filter_user_selected_context(notebook_ctx: Dict[str, Any], username: str,
                                  selected_files: Optional[List[str]] = None,
                                  context_docs: Optional[List[str]] = None,
                                  context_card_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """按用户指定筛选上下文（按类型优先），否则自动智能召回。"""
    auto_ctx = _auto_select_context(notebook_ctx, selected_files=selected_files)
    result = dict(notebook_ctx)

    if context_docs:
        selected_keys = set()
        for doc_name in context_docs:
            if not doc_name:
                continue
            selected_keys.add(_normalize_doc_key(doc_name))
            selected_keys.add(_extract_source_key_from_presummary_name(doc_name))

        matched_docs: List[Dict[str, Any]] = []
        for doc in notebook_ctx.get('doc_summaries', []):
            doc_key = _extract_source_key_from_presummary_name(doc.get('file_name', ''))
            if doc_key and doc_key in selected_keys:
                matched_docs.append(doc)
        result['doc_summaries'] = matched_docs
    else:
        result['doc_summaries'] = auto_ctx.get('doc_summaries', [])

    if context_card_ids:
        id_set = {int(item) for item in context_card_ids if str(item).isdigit()}
        from app_chat.models import Card
        try:
            cards = Card.objects.filter(username=username, cid__in=id_set).order_by('-confidence_score', '-cid')
            result['card_summaries'] = [
                {
                    'cid': card.cid,
                    'title': (card.contentTitle or card.title or '')[:100],
                    'keywords': (card.keyWords or '')[:200],
                    # 勾选卡片时：保留原始内容，由后续上下文拼接阶段统一按阈值截断。
                    'preview': (card.content or ''),
                    'confidence_score': card.confidence_score,
                } for card in cards
            ]
        except Exception as error:
            print(f'[ci] _filter_user_selected_context 卡片筛选失败: {error}')
            result['card_summaries'] = auto_ctx.get('card_summaries', [])
    else:
        result['card_summaries'] = auto_ctx.get('card_summaries', [])

    return result


def _format_m_layer_context(notebook_ctx: Dict[str, Any], mode: str = 'full') -> str:
    """将上下文格式化为 M 层 Prompt 可注入的文本段。"""
    if not notebook_ctx:
        return ''

    scene_name = notebook_ctx.get('scene_name', '') or '未指定'
    sub_scene_name = notebook_ctx.get('sub_scene_name', '') or '未指定'
    notebook_description = notebook_ctx.get('notebook_description', '') or '未提供'
    scene_summary = notebook_ctx.get('scene_summary', '') or '未提供'
    doc_summaries = notebook_ctx.get('doc_summaries', [])
    card_summaries = notebook_ctx.get('card_summaries', [])

    has_content = (scene_name != '未指定' or doc_summaries or card_summaries)
    if not has_content:
        return ''

    if mode == 'brief':
        terms = set()
        for card in card_summaries[:15]:
            keywords = card.get('keywords', '')
            for keyword in re.split(r'[,，;；\s]+', keywords):
                keyword = keyword.strip()
                if keyword:
                    terms.add(keyword)
        for doc in doc_summaries[:8]:
            words = doc.get('summary', '')[:120].split()
            terms.update(word for word in words[:8] if len(word) > 1)
        key_terms = '、'.join(list(terms)[:25]) or '无'

        return CI_M_LAYER_CONTEXT_BRIEF_TEMPLATE.format(
            scene_name=scene_name,
            sub_scene_name=sub_scene_name,
            notebook_description=notebook_description[:200],
            key_terms=key_terms[:500],
        )

    doc_lines = []
    total_doc_chars = 0
    for doc in doc_summaries:
        summary = doc.get('summary', '')
        if total_doc_chars + len(summary) > 6000:
            summary = summary[:max(0, 6000 - total_doc_chars)]
        if summary:
            doc_lines.append(f"- **{doc['file_name']}**：{summary}")
            total_doc_chars += len(summary)
        if total_doc_chars >= 6000:
            break
    doc_text = '\n'.join(doc_lines) if doc_lines else '（无导入文档摘要）'

    card_lines = []
    for card in card_summaries[:25]:
        title = card.get('title', '')
        keywords = card.get('keywords', '')
        preview = card.get('preview', '')
        parts = [title]
        if keywords:
            parts.append(f'关键词:{keywords}')
        if preview:
            parts.append(preview)
        card_lines.append(f"- {' | '.join(parts)}")
    card_text = '\n'.join(card_lines) if card_lines else '（无卡片知识）'

    return CI_M_LAYER_CONTEXT_FULL_TEMPLATE.format(
        scene_name=scene_name,
        sub_scene_name=sub_scene_name,
        notebook_description=notebook_description,
        scene_summary=scene_summary,
        doc_summaries=doc_text,
        card_summaries=card_text,
    )