"""学习阶段（session）切分与 session memory 构建。

nkcn 自有实现，按 yq/连续图片批改 2026-06-01 追加修正改写：
- session 是篇次/课时级时序单位，不再把低层栏目拆成独立 session；
- 低层栏目进入 ``submodules``；
- 新产物只写闭区间 ``page_start`` / ``page_end``，读取旧产物时兼容 ``page_range``。
"""

from __future__ import annotations

from .feedback_runtime import stamp_feedback
from .feedback_verification import validate_page


import datetime
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app_chat.homework_grading.memory import aggregate_pages
from app_chat.homework_grading.utils import parse_page_num, safe_json_dump, safe_json_load, sorted_json_pages

logger = logging.getLogger(__name__)

TEMPORAL_ASSUMPTION = (
    'session order_index ascending == chronological practice order '
    '(holds within a single PDF homework)'
)
PAGE_FIELD_CONVENTION = 'page_start/page_end are inclusive 1-based page numbers.'
SESSION_GRANULARITY = 'lesson_or_practice_episode; low-level exercise columns are submodules'

LOW_LEVEL_MODULE_PATTERNS: Dict[str, List[str]] = {
    'math': [
        '基础过关营', '探究益智营', '素养提升营', '实践体验营',
        '拓展提升营', '探究益智题',
    ],
    'chinese': [
        '课堂轻松练习', '随堂轻松练习', '课后提升作业',
        '轻松练习', '提升作业',
    ],
    'english': [
        '听力训练', '读写训练', '听说训练',
        '轻松启航', '能力提升', '综合实践',
        '律动听说', '快乐听力', '首字大写',
    ],
}

# Back-compat name for older local callers.
MODULE_PATTERNS = LOW_LEVEL_MODULE_PATTERNS

_OCR_CONFUSIONS: Dict[str, str] = {
    '酒': '课',
    '语堂': '课堂',
    '满堂': '课堂',
    '通堂': '课堂',
    '课轻': '课堂轻',
}
_PAGE_BREAK_RE = re.compile(r'<div[^>]*page-break-after[^>]*>\s*</div>', re.IGNORECASE)
_HEADER_LINE_RE = re.compile(r'^\s*#{1,6}\s+')
_HEADER_PREFIX_RE = re.compile(r'^[#\s]+')
_NOISE_RE = re.compile(r'[#\s\\*?？]')
_QUESTION_HEADER_RE = re.compile(r'^([一二三四五六七八九十]+|[0-9]+)[、.．]\s*')
_CJK_RE = re.compile(r'[\u4e00-\u9fff]')

_CONF_LLM_ADJUDICATED = 0.9
_CONF_RULE_ONLY = 0.82
_CONF_RULE_AFTER_LLM_FAIL = 0.68
_KP_ACCURACY_DELTA = 0.15


def session_page_bounds(session: Dict[str, Any]) -> Tuple[int, int]:
    """Return inclusive (page_start, page_end), accepting legacy half-open page_range."""
    if session.get('page_start') is not None and session.get('page_end') is not None:
        return int(session['page_start']), int(session['page_end'])
    page_range = session.get('page_range') or []
    if len(page_range) >= 2:
        return int(page_range[0]), int(page_range[1]) - 1
    pages = session.get('pages') or []
    if pages:
        values = [int(p) for p in pages]
        return min(values), max(values)
    raise ValueError('session missing page_start/page_end')


def _apply_ocr_confusions(text: str) -> str:
    for src, dst in _OCR_CONFUSIONS.items():
        if src in text:
            text = text.replace(src, dst)
    return text


def _norm(text: str) -> str:
    return _apply_ocr_confusions(_NOISE_RE.sub('', str(text or '')))


def _clean_header(line: str) -> str:
    text = _HEADER_PREFIX_RE.sub('', line).strip()
    return re.sub(r'\s+', ' ', text).strip()


def _split_ocr_pages(md_text: str) -> List[str]:
    chunks = _PAGE_BREAK_RE.split(md_text)
    if chunks and not chunks[-1].strip():
        chunks = chunks[:-1]
    return chunks


def _dedupe_keep_order(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set = set()
    for value in values:
        value = str(value or '').strip()
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _coerce_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return _dedupe_keep_order([str(v).strip() for v in value if str(v).strip()])
    text = str(value).strip()
    return [text] if text else []


def _canonical_low_level_title(title: str, subject: str) -> Optional[str]:
    norm = _norm(title)
    for pattern in LOW_LEVEL_MODULE_PATTERNS.get(subject, []):
        if _norm(pattern) in norm:
            return pattern
    return None


def _is_question_like_header(title: str) -> bool:
    stripped = title.strip()
    norm = _norm(stripped)
    if _QUESTION_HEADER_RE.match(stripped):
        return True
    if stripped.startswith((
        '根据要求', '根据课文', '阅读下面', '下列', '一、', '二、', '三、',
        '四、', '五、', '六、', '七、', '八、', '九、',
    )):
        return True
    return norm in {'填空', '解决问题', '探索规律', '选择', '选一选'}


def _high_level_title_score(title: str, subject: str) -> int:
    stripped = title.strip()
    norm = _norm(stripped)
    if not stripped or _canonical_low_level_title(stripped, subject):
        return 0
    if _is_question_like_header(stripped):
        return 0
    if '我学会了吗' in norm:
        return 100
    if subject == 'math':
        if re.search(r'第[一二三四五六七八九十\d]+课时', norm):
            return 95
        if re.match(r'^[一二三四五六七八九十\d]+单元', norm):
            return 85
        if len(norm) >= 5 and _CJK_RE.search(stripped):
            return 60
        return 0
    if subject == 'chinese':
        if '语文园地' in norm:
            return 95
        if re.match(r'^\d+\s*\\?\*?\s*[\u4e00-\u9fff]', stripped):
            return 90
        if re.match(r'^第[一二三四五六七八九十\d]+单元', norm):
            return 70
        return 0
    if subject == 'english':
        if re.search(r'\bUnit\s*\d+', stripped, re.IGNORECASE):
            return 100
        if re.search(r'\bPart\s*\d+', stripped, re.IGNORECASE):
            return 95
    return 0


def _extract_page_features(pages: List[str], subject: str) -> List[Dict[str, Any]]:
    features: List[Dict[str, Any]] = []
    for page_idx, page_md in enumerate(pages, start=1):
        headers: List[str] = []
        submodules: List[str] = []
        candidates: List[Dict[str, Any]] = []
        for line_idx, line in enumerate(page_md.splitlines()):
            if not _HEADER_LINE_RE.match(line):
                continue
            title = _clean_header(line)
            if not title:
                continue
            headers.append(title)
            low_title = _canonical_low_level_title(title, subject)
            if low_title:
                submodules.append(low_title)
                continue
            score = _high_level_title_score(title, subject)
            if score:
                candidates.append({
                    'title': title,
                    'score': score,
                    'line_index': line_idx,
                    'evidence': title[:80],
                })
        best = max(candidates, key=lambda c: (c['score'], c['line_index'])) if candidates else None
        features.append({
            'page': page_idx,
            'headers': headers[:12],
            'session_anchor': best['title'] if best else None,
            'anchor_score': best['score'] if best else 0,
            'submodules': _dedupe_keep_order(submodules),
            'evidence': best['evidence'] if best else '',
        })
    return features


def _fallback_start_title(page_features: List[Dict[str, Any]], sample_id: str, subject: str) -> str:
    first = page_features[0] if page_features else {}
    for header in first.get('headers', []) or []:
        if not _canonical_low_level_title(header, subject) and not _is_question_like_header(header):
            return header
    return f'{sample_id} 起始篇次'


def _submodules_for_range(page_features: List[Dict[str, Any]], start: int, end: int) -> List[str]:
    values: List[str] = []
    for feature in page_features[start - 1:end]:
        values.extend(feature.get('submodules', []) or [])
    return _dedupe_keep_order(values)


def _build_sessions_rule(
    page_features: List[Dict[str, Any]],
    subject: str,
    total_pages: int,
    sample_id: str,
) -> List[Dict[str, Any]]:
    anchors: List[Dict[str, Any]] = []
    for feature in page_features:
        title = feature.get('session_anchor')
        if not title:
            continue
        page = int(feature['page'])
        if anchors and anchors[-1]['start_page'] == page:
            continue
        anchors.append({
            'start_page': page,
            'session_title': title,
            'evidence': feature.get('evidence') or title,
            'boundary_reason': 'high_level_header',
        })

    if not anchors or anchors[0]['start_page'] != 1:
        anchors.insert(0, {
            'start_page': 1,
            'session_title': _fallback_start_title(page_features, sample_id, subject),
            'evidence': 'document_start',
            'boundary_reason': 'document_start_without_high_level_anchor',
        })

    sessions: List[Dict[str, Any]] = []
    for i, anchor in enumerate(anchors):
        start = int(anchor['start_page'])
        next_start = int(anchors[i + 1]['start_page']) if i + 1 < len(anchors) else total_pages + 1
        if next_start <= start:
            continue
        end = next_start - 1
        title = str(anchor['session_title']).strip() or f'Session {i + 1}'
        sessions.append({
            'session_index': i + 1,
            'page_start': start,
            'page_end': end,
            'session_title': title,
            'unit_title': title,
            'module_title': title,
            'submodules': _submodules_for_range(page_features, start, end),
            'boundary_signal': anchor['boundary_reason'],
            'boundary_reason': anchor['boundary_reason'],
            'split_source': 'rule',
            'confidence': _CONF_RULE_ONLY,
            'evidence': str(anchor.get('evidence', ''))[:120],
        })
    _validate_session_ranges(sessions, total_pages)
    return sessions


def _validate_session_ranges(sessions: List[Dict[str, Any]], total_pages: int) -> None:
    if total_pages <= 0:
        raise ValueError('total_pages must be positive')
    if not sessions:
        raise ValueError('session list is empty')
    expected_start = 1
    for idx, session in enumerate(sessions, start=1):
        try:
            start = int(session['page_start'])
            end = int(session['page_end'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'session {idx} missing/non-integer page_start/page_end') from exc
        if start != expected_start:
            raise ValueError(f'session ranges must be contiguous: expected p{expected_start}, got p{start}')
        if end < start:
            raise ValueError(f'session {idx} has empty or reversed page_start/page_end')
        if end > total_pages:
            raise ValueError(f'session {idx} exceeds total_pages={total_pages}')
        expected_start = end + 1
    if expected_start != total_pages + 1:
        raise ValueError(f'session ranges end at p{expected_start - 1}, expected p{total_pages}')


def _enrich_sessions_with_features(
    sessions: List[Dict[str, Any]],
    page_features: List[Dict[str, Any]],
    split_source: str,
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for session in sessions:
        s = dict(session)
        start, end = int(s['page_start']), int(s['page_end'])
        title = s.get('session_title') or s.get('module_title') or s.get('unit_title') or f'Session {len(enriched) + 1}'
        submodules = _dedupe_keep_order(
            _coerce_str_list(s.get('submodules')) + _submodules_for_range(page_features, start, end)
        )
        s['session_title'] = str(title).strip()
        s['unit_title'] = str(title).strip()
        s['module_title'] = str(title).strip()
        s['submodules'] = submodules
        s['split_source'] = split_source
        s.setdefault('boundary_signal', split_source)
        s.setdefault('boundary_reason', split_source)
        s.setdefault('evidence', str(title).strip()[:120])
        enriched.append(s)
    return enriched


def _finalize_sessions(sessions: List[Dict[str, Any]], sample_id: str, total_pages: int) -> List[Dict[str, Any]]:
    _validate_session_ranges(sessions, total_pages)
    out: List[Dict[str, Any]] = []
    for idx, session in enumerate(sessions, start=1):
        s = dict(session)
        s['session_index'] = idx
        s['order_index'] = idx
        s['session_id'] = s.get('session_id') or f'{sample_id}_s{idx:02d}'
        s['session_title'] = s.get('session_title') or s.get('module_title') or s.get('unit_title') or f'Session {idx}'
        s['module_title'] = s['session_title']
        s['unit_title'] = s.get('unit_title') or s['session_title']
        # New schema writes no page_range/pages/page_span.
        for legacy_key in ('page_range', 'pages', 'page_span'):
            s.pop(legacy_key, None)
        out.append(s)
    return out


def _extract_json_payload(text: str) -> Any:
    text = (text or '').strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(1))


def _items_from_payload(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ('sessions', 'modules', 'items'):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_llm_sessions(items: List[Dict[str, Any]], total_pages: int) -> List[Dict[str, Any]]:
    sessions: List[Dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        try:
            start = int(item.get('start_page', item.get('page_start')))
            end = int(item.get('end_page', item.get('page_end')))
        except (TypeError, ValueError):
            continue
        title = item.get('session_title') or item.get('module_title') or item.get('unit_title') or f'Session {idx}'
        try:
            confidence = float(item.get('confidence', _CONF_LLM_ADJUDICATED))
        except (TypeError, ValueError):
            confidence = _CONF_LLM_ADJUDICATED
        sessions.append({
            'session_index': idx,
            'page_start': start,
            'page_end': end,
            'session_title': str(title).strip() or f'Session {idx}',
            'unit_title': str(title).strip() or f'Session {idx}',
            'module_title': str(title).strip() or f'Session {idx}',
            'submodules': _coerce_str_list(item.get('submodules')),
            'boundary_signal': 'llm_adjudicated',
            'boundary_reason': str(item.get('boundary_reason', 'llm_adjudicated')).strip(),
            'split_source': 'llm',
            'confidence': max(0.0, min(1.0, confidence)),
            'evidence': str(item.get('evidence', '')).strip()[:120],
        })
    _validate_session_ranges(sessions, total_pages)
    return sessions


def _llm_adjudicate_sessions(
    sample_id: str,
    subject: str,
    page_features: List[Dict[str, Any]],
    rule_sessions: List[Dict[str, Any]],
    total_pages: int,
*, feedback_runtime=None) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    try:
        from app_chat.homework_grading.llm_clients import _deepseek_client, homework_deepseek_model
        client = _deepseek_client()
        from .feedback_model import runtime_client
        client = runtime_client(client, feedback_runtime, "deepseek")
    except Exception as exc:
        return None, f'DeepSeek client unavailable: {exc}'

    system = (
        '你是中小学作业 OCR 篇次切分助手。'
        'session 表示学生连续完成的一次篇次/课时/单元检测，而不是栏目。'
        '基础过关营、探究益智营、素养提升营、实践体验营、听力训练、读写训练、'
        '课堂轻松练习、课后提升作业等低层栏目必须合并进 submodules，禁止单独切成 session。'
        '返回 JSON object，形如 {"sessions":[{"session_title":str,'
        '"start_page":int,"end_page":int,"submodules":[str],'
        '"evidence":str,"boundary_reason":str,"confidence":number}]}。'
        'start_page/end_page 是 1-based 闭区间；sessions 必须从第1页连续覆盖到最后1页，'
        '无空洞、无重叠、按页码升序。只返回 JSON。'
    )
    if feedback_runtime is not None:
        from .feedback_prompts import context_block, stage_instructions
        system = system.replace('中小学作业', '学生材料') + context_block(feedback_runtime) + stage_instructions(feedback_runtime, 'sessions')
    payload = {
        'sample_id': sample_id,
        'subject': subject,
        'total_pages': total_pages,
        'page_features': page_features,
        'rule_candidates': [
            {
                'start_page': s['page_start'],
                'end_page': s['page_end'],
                'session_title': s.get('session_title'),
                'submodules': s.get('submodules', []),
                'evidence': s.get('evidence', ''),
            }
            for s in rule_sessions
        ],
    }
    try:
        resp = client.chat.completions.create(
            model=homework_deepseek_model(),
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
            extra_body={'thinking': {'type': 'disabled'}},
            response_format={'type': 'json_object'},
            max_tokens=4000,
        )
        data = _extract_json_payload((resp.choices[0].message.content or '').strip())
        sessions = _normalize_llm_sessions(_items_from_payload(data), total_pages)
        sessions = _enrich_sessions_with_features(sessions, page_features, 'llm')
        _validate_session_ranges(sessions, total_pages)
        return sessions, None
    except Exception as exc:
        return None, str(exc)


def _resolve_sessions(
    sample_id: str,
    subject: str,
    page_features: List[Dict[str, Any]],
    rule_sessions: List[Dict[str, Any]],
    total_pages: int,
    use_llm: bool,
*, feedback_runtime=None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    sessions: Optional[List[Dict[str, Any]]] = None
    fallback_reason: Optional[str] = None
    if use_llm:
        sessions, fallback_reason = _llm_adjudicate_sessions(sample_id, subject, page_features, rule_sessions, total_pages, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    llm_used = sessions is not None
    fallback_used = False
    if sessions is None:
        fallback_used = bool(use_llm)
        source = 'rule_fallback' if fallback_used else 'rule'
        confidence = _CONF_RULE_AFTER_LLM_FAIL if fallback_used else _CONF_RULE_ONLY
        sessions = []
        for rule_session in rule_sessions:
            s = dict(rule_session)
            s['split_source'] = source
            s['confidence'] = min(float(s.get('confidence', confidence)), confidence)
            if fallback_used:
                s['boundary_reason'] = f'rule fallback after LLM unavailable/invalid: {fallback_reason}'[:160]
            sessions.append(s)
        sessions = _enrich_sessions_with_features(sessions, page_features, source)
    sessions = _finalize_sessions(sessions, sample_id, total_pages)
    return sessions, {
        'granularity': SESSION_GRANULARITY,
        'channels': ['rule', 'llm'] if use_llm else ['rule'],
        'llm_triggered': bool(use_llm),
        'llm_used': llm_used,
        'trigger_reason': 'default_adjudication' if use_llm else None,
        'fallback_used': fallback_used,
        'fallback_reason': fallback_reason if fallback_used else None,
        'rule_candidate_count': len(rule_sessions),
    }


def _find_ocr_markdown(pdf_path: str) -> Optional[str]:
    if not pdf_path or not os.path.exists(pdf_path):
        return None
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    directory = os.path.dirname(pdf_path)
    for candidate in [
        os.path.join(directory, f'{base}_ocr', f'{base}_ocr.md'),
        os.path.join(directory, f'{base}_ocr.md'),
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


def _count_clean_pages(clean_dir: str) -> int:
    if not os.path.isdir(clean_dir):
        return 0
    return len([f for f in os.listdir(clean_dir) if f.lower().endswith('.png')])


def build_pre_pass1_session_map(
    subject: str,
    sample_id: str,
    pdf_path: str,
    clean_dir: str,
    report_dir: str,
    use_llm: bool = True,
*, feedback_runtime=None) -> Optional[str]:
    """Pass1 前构建篇次/课时级 session map 并落盘。"""
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    out_path = os.path.join(report_dir, f'{subject}_{sample_id}_sessions.json')
    total_pages = _count_clean_pages(clean_dir)
    ocr_md_path = _find_ocr_markdown(pdf_path)
    pages: List[str] = []
    if ocr_md_path:
        try:
            with open(ocr_md_path, encoding='utf-8') as f:
                pages = _split_ocr_pages(f.read())
        except Exception as exc:
            logger.warning('[session-map] OCR markdown 读取失败：%s', exc)
            pages = []
    if not total_pages:
        total_pages = len(pages)
    if total_pages <= 0:
        return None
    if len(pages) < total_pages:
        pages = pages + [''] * (total_pages - len(pages))
    elif len(pages) > total_pages:
        pages = pages[:total_pages]

    page_features = _extract_page_features(pages, subject)
    try:
        rule_sessions = _build_sessions_rule(page_features, subject, total_pages, sample_id)
        sessions, split_summary = _resolve_sessions(sample_id, subject, page_features, rule_sessions, total_pages, use_llm=use_llm, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    except Exception as exc:
        logger.warning('[session-map] 切分失败，回退整篇作业：%s', exc)
        title = _fallback_start_title(page_features, sample_id, subject)
        sessions = _finalize_sessions([{
            'session_index': 1,
            'page_start': 1,
            'page_end': total_pages,
            'session_title': title,
            'unit_title': title,
            'module_title': title,
            'submodules': _submodules_for_range(page_features, 1, total_pages),
            'boundary_signal': 'fallback',
            'boundary_reason': str(exc)[:160],
            'split_source': 'fallback',
            'confidence': 0.5,
        }], sample_id, total_pages)
        split_summary = {
            'granularity': SESSION_GRANULARITY,
            'channels': ['rule'],
            'ocr_md_used': bool(ocr_md_path),
            'llm_triggered': False,
            'llm_used': False,
            'fallback_used': True,
            'fallback_reason': str(exc)[:160],
            'rule_candidate_count': 0,
        }
    split_summary['ocr_md_used'] = bool(ocr_md_path)

    doc = {
        'subject': subject,
        'sample_id': sample_id,
        'total_pages': total_pages,
        'session_count': len(sessions),
        'extracted_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'temporal_assumption': TEMPORAL_ASSUMPTION,
        'page_field_convention': PAGE_FIELD_CONVENTION,
        'session_granularity': SESSION_GRANULARITY,
        'split_summary': split_summary,
        'sessions': sessions,
    }
    try:
        os.makedirs(report_dir, exist_ok=True)
        safe_json_dump(out_path, stamp_feedback(doc, feedback_runtime, 'sessions'))
        logger.info('[session-map] 落盘 %s（%d sessions）', out_path, len(sessions))
        return out_path
    except Exception as exc:
        logger.warning('[session-map] 落盘失败：%s', exc)
        return None


def _normalize_session_entry(session: Dict[str, Any], idx: int, sample_id: str = 'session') -> Dict[str, Any]:
    start, end = session_page_bounds(session)
    title = session.get('session_title') or session.get('module_title') or session.get('unit_title') or f'Session {idx}'
    return {
        'session_id': session.get('session_id') or f'{sample_id}_s{idx:02d}',
        'session_index': int(session.get('session_index') or idx),
        'order_index': int(session.get('order_index') or session.get('session_index') or idx),
        'page_start': start,
        'page_end': end,
        'session_title': title,
        'unit_title': session.get('unit_title') or title,
        'module_title': session.get('module_title') or title,
        'submodules': _coerce_str_list(session.get('submodules')),
        'split_source': session.get('split_source', ''),
        'confidence': session.get('confidence'),
    }


def _match_module(text: str, subject: str) -> Optional[str]:
    norm = _norm(text)
    return next((p for p in LOW_LEVEL_MODULE_PATTERNS.get(subject, []) if _norm(p) in norm), None)


def _extract_page_title(page_data: Dict[str, Any], subject: str) -> Optional[str]:
    header = page_data.get('page_header') or ''
    if header and _high_level_title_score(header, subject):
        return str(header).strip()
    texts: List[str] = []
    boundary = page_data.get('boundary') or {}
    for key in ('description_prev', 'description_next'):
        if boundary.get(key):
            texts.append(str(boundary[key]))
    for text in texts:
        if _high_level_title_score(text, subject):
            return text.strip()
    return None


def _extract_page_submodules(page_data: Dict[str, Any], subject: str) -> List[str]:
    texts: List[str] = []
    if page_data.get('page_header'):
        texts.append(str(page_data['page_header']))
    boundary = page_data.get('boundary') or {}
    texts.extend(str(boundary.get(k) or '') for k in ('description_prev', 'description_next'))
    for q in page_data.get('questions') or []:
        texts.append(str(q.get('stem_excerpt') or ''))
    return _dedupe_keep_order([hit for text in texts if (hit := _match_module(text, subject))])


def split_sessions(pass1_dir: str, subject: str = 'unknown', sessions_json_path: Optional[str] = None, *, feedback_runtime=None) -> List[Dict[str, Any]]:
    """Load prebuilt session map, or build a conservative legacy fallback from Pass1 JSON."""
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if feedback_runtime is not None and sessions_json_path and os.path.exists(sessions_json_path):
        existing = safe_json_load(sessions_json_path)
        if existing.get('feedback_execution', {}).get('config_fingerprint') != feedback_runtime.fingerprint:
            raise ValueError('篇目数据与当前运行配置不一致')
    if sessions_json_path and os.path.exists(sessions_json_path):
        try:
            doc = safe_json_load(sessions_json_path)
            sessions = doc.get('sessions') or []
            if sessions:
                sample_id = doc.get('sample_id') or 'session'
                return [_normalize_session_entry(s, idx + 1, sample_id) for idx, s in enumerate(sessions)]
        except Exception as exc:
            logger.warning('[split_sessions] 读取预建 session map 失败：%s，回退 Pass1 扫描', exc)

    page_files = sorted_json_pages(pass1_dir)
    if not page_files:
        return []
    pages: List[Dict[str, Any]] = []
    for pf in page_files:
        data = safe_json_load(pf)
        page_num = data.get('page') or parse_page_num(os.path.basename(pf))
        pages.append({
            'page': int(page_num),
            'title': _extract_page_title(data, subject),
            'submodules': _extract_page_submodules(data, subject),
        })
    pages.sort(key=lambda p: p['page'])
    anchors = [{'start_page': p['page'], 'title': p['title']} for p in pages if p.get('title')]
    if not anchors or anchors[0]['start_page'] != pages[0]['page']:
        anchors.insert(0, {'start_page': pages[0]['page'], 'title': '整篇作业'})
    last_page = pages[-1]['page']
    out: List[Dict[str, Any]] = []
    for i, anchor in enumerate(anchors):
        start = int(anchor['start_page'])
        next_start = int(anchors[i + 1]['start_page']) if i + 1 < len(anchors) else last_page + 1
        end = max(start, next_start - 1)
        submodules: List[str] = []
        for page in pages:
            if start <= page['page'] <= end:
                submodules.extend(page.get('submodules') or [])
        idx = i + 1
        title = anchor.get('title') or ('未命名篇目' if feedback_runtime is not None else f'Session {idx}')
        out.append({
            'session_id': f'session_{idx:02d}',
            'session_index': idx,
            'order_index': idx,
            'page_start': start,
            'page_end': end,
            'session_title': title,
            'unit_title': title,
            'module_title': title,
            'submodules': _dedupe_keep_order(submodules),
        })
    return out


def _kp_accuracy_map(memory_body: Dict[str, Any]) -> Dict[str, float]:
    return {
        item['point']: item.get('correct_rate', 1 - item.get('error_rate', 0))
        for item in memory_body.get('knowledge_point_frequency', [])
    }


def _compute_kp_trend(current: Dict[str, Any], prior: Optional[Dict[str, Any]]) -> Dict[str, str]:
    cur_acc = _kp_accuracy_map(current)
    if not prior:
        return {kp: 'new' for kp in cur_acc}
    prior_acc = _kp_accuracy_map(prior)
    trend: Dict[str, str] = {}
    for kp, acc in cur_acc.items():
        if kp not in prior_acc:
            trend[kp] = 'new'
            continue
        delta = acc - prior_acc[kp]
        if delta >= _KP_ACCURACY_DELTA:
            trend[kp] = 'improving'
        elif delta <= -_KP_ACCURACY_DELTA:
            trend[kp] = 'worsening'
        else:
            trend[kp] = 'stable'
    return trend


def _compute_erase_candidates(
    current: Dict[str, Any],
    prior: Optional[Dict[str, Any]],
    prior_session_index: Optional[int],
) -> List[Dict[str, Any]]:
    if not prior or prior_session_index is None:
        return []
    cur_kps = {item['point'] for item in current.get('knowledge_point_frequency', [])}
    out = []
    for kp, level in (prior.get('kp_importance') or {}).items():
        if level == 'LOW' and kp not in cur_kps:
            out.append({
                'knowledge_point': kp,
                'last_seen_session_index': prior_session_index,
                'reason': 'LOW importance, not observed in current session',
            })
    return out


def build_session_memory(
    subject: str,
    sample_id: str,
    session: Dict[str, Any],
    all_page_files: List[str],
    prior_memory: Optional[Dict[str, Any]] = None,
*, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    start, end = session_page_bounds(session)
    page_files = [p for p in all_page_files if start <= parse_page_num(os.path.basename(p)) <= end]
    body = aggregate_pages(page_files, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    session_title = session.get('session_title') or session.get('module_title') or session.get('unit_title') or ''
    body.update({
        'session_id': session['session_id'],
        'session_index': session['session_index'],
        'page_start': start,
        'page_end': end,
        'session_title': session_title,
        'unit_title': session.get('unit_title', session_title),
        'module_title': session.get('module_title', session_title),
        'submodules': session.get('submodules', []),
    })
    body['kp_trend'] = _compute_kp_trend(body, prior_memory)
    body['erase_candidates'] = _compute_erase_candidates(
        body, prior_memory, prior_memory.get('session_index') if prior_memory else None,
    )
    return stamp_feedback({'subject': subject, 'sample_id': sample_id, **body}, feedback_runtime, 'sessions')


def save_session_memory(memory: Dict[str, Any], report_dir: str, subject: str, sample_id: str, *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    path = os.path.join(report_dir, f"{subject}_{sample_id}_s{memory['session_index']:02d}_memory.json")
    safe_json_dump(path, stamp_feedback(memory, feedback_runtime, 'sessions'))
    return path


def build_all_session_memories(
    pass1_dir: str,
    report_dir: str,
    subject: str,
    sample_id: str,
    sessions_json_path: Optional[str] = None,
*, feedback_runtime=None) -> List[Dict[str, Any]]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    sessions = split_sessions(pass1_dir, subject, sessions_json_path=sessions_json_path, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    all_page_files = sorted_json_pages(pass1_dir)
    memories: List[Dict[str, Any]] = []
    prior: Optional[Dict[str, Any]] = None
    for session in sessions:
        mem = build_session_memory(subject, sample_id, session, all_page_files, prior_memory=prior, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        save_session_memory(mem, report_dir, subject, sample_id, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        memories.append(mem)
        prior = mem
    return memories
