# -*- coding: utf-8 -*-
"""需加强核实位置：核验「有误」时可点短句预生成。

- 批改报告完成后，按「需核实」所属页，用与逐页批改相同的页图调视觉模型预生成；
- 模型失败/超时/解析失败时用规则兜底；
- 迭代更新后：若该页已有模型成功结果则跳过，规则兜底页再试模型。
"""
from __future__ import annotations

import json
import os
import re
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app_chat.homework_grading.utils import (
    image_to_data_uri,
    safe_json_dump,
    safe_json_load,
)

SUGGEST_FILE = 'verify_suggestions.json'
_ROLES = ('layout', 'understanding', 'grading')
_ROLE_CN = {
    'layout': '无损版面',
    'understanding': '无损理解',
    'grading': '三区批改',
}
def _suggest_path(paths: Dict[str, str]) -> str:
    return os.path.join(paths.get('base') or paths.get('root') or '', SUGGEST_FILE)


def load_suggestions(paths: Dict[str, str]) -> Dict[str, Any]:
    path = _suggest_path(paths)
    data = safe_json_load(path) if os.path.isfile(path) else None
    if not isinstance(data, dict):
        data = {'schema_version': 1, 'pages': {}, 'items': {}, 'updated_at': ''}
    if not isinstance(data.get('pages'), dict):
        data['pages'] = {}
    if not isinstance(data.get('items'), dict):
        data['items'] = {}
    return data


def save_suggestions(paths: Dict[str, str], data: Dict[str, Any]) -> None:
    data = dict(data or {})
    data['schema_version'] = 1
    data['updated_at'] = datetime.now().isoformat(timespec='seconds')
    safe_json_dump(_suggest_path(paths), data)


def suggestions_for_html(paths: Dict[str, str]) -> Dict[str, Any]:
    """供解释精要 HTML 内嵌：qid → {layout,understanding,grading,source}。"""
    data = load_suggestions(paths)
    out: Dict[str, Any] = {}
    for qid, item in (data.get('items') or {}).items():
        if not isinstance(item, dict):
            continue
        out[str(qid)] = {
            'source': item.get('source') or 'rule',
            'layout': list(item.get('layout') or [])[:3],
            'understanding': list(item.get('understanding') or [])[:3],
            'grading': list(item.get('grading') or [])[:3],
        }
    return out


def _clip_phrase(text: Any, lo: int = 12, hi: int = 28) -> str:
    """清洗可点短句。prompt 仍引导约 lo～hi 字；程序层不因超长截断。"""
    _ = (lo, hi)  # 与 prompt「约 12～28 字」对齐的文档参数，不做硬截断
    s = re.sub(r'\s+', '', str(text or '').strip())
    s = re.sub(r'^[·\-—,\s]+|[·\-—,\s]+$', '', s)
    if not s:
        return ''
    # 去掉内部变量名与白灰黑等对普通用户的黑话
    s = re.sub(
        r'(layout_confidence|understanding_confidence|grading_confidence|'
        r'recognition_confidence|uncertain_reason|error_type|qid_global|bbox|'
        r'白灰黑|深灰区|中灰区|浅灰区|白区|灰区|黑区)',
        '',
        s,
        flags=re.I,
    )
    s = re.sub(r'[（(]\s*[）)]', '', s)
    s = re.sub(r'^[·\-—,\s]+|[·\-—,\s]+$', '', s)
    return s


def _normalize_phrases(raw: Any) -> List[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen = set()
    for item in raw:
        phrase = _clip_phrase(item)
        if len(phrase) < 6:
            continue
        if phrase in seen:
            continue
        seen.add(phrase)
        out.append(phrase)
        if len(out) >= 3:
            break
    return out


def _confidence_plain(conf: Any = None) -> str:
    """用户可见用语：只用「把握高低 + 数字」，不用白/灰/黑区。"""
    from app_chat.homework_grading.confidence_zones import clamp_confidence
    n = clamp_confidence(conf)
    if n is None:
        return '把握一般'
    if n < 40:
        return f'把握很低（{n}）'
    if n < 70:
        return f'把握偏低（{n}）'
    return f'把握约{n}'


def _shade_label_for_model(shade: Any, conf: Any = None) -> str:
    """仅作模型输入：白/灰/黑区 + 数字；禁止写进用户可见短句。"""
    from app_chat.homework_grading.confidence_zones import (
        SHADE_DISPLAY,
        clamp_confidence,
        gray_shade,
    )
    key = str(shade or '').strip()
    if not key and conf is not None:
        key = gray_shade(conf, mode='grading')
    _cn = {
        'white': '白区',
        'gray_deep': '深灰区',
        'gray_mid': '中灰区',
        'gray_light': '浅灰区',
        'black': '黑区',
        'gray': '灰区',
    }
    label = SHADE_DISPLAY.get(key) or _cn.get(key) or '灰区'
    n = clamp_confidence(conf)
    if n is None:
        return label
    return f'{label}（{n}）'


def _item_has_llm(store: Dict[str, Any], qid_global: str) -> bool:
    item = (store.get('items') or {}).get(qid_global)
    if not isinstance(item, dict) or item.get('source') != 'llm':
        return False
    for role in _ROLES:
        phrases = item.get(role)
        if not isinstance(phrases, list) or len(phrases) < 2:
            return False
    return True


def need_verify_missing_llm(
    paths: Dict[str, str],
    manifest: Optional[Dict[str, Any]] = None,
    trust: Optional[Dict[str, Any]] = None,
) -> bool:
    """当前需核实题/条中，是否还有尚未拿到模型可点短句的项。"""
    manifest = manifest if isinstance(manifest, dict) else safe_json_load(paths.get('manifest') or '') or {}
    subject = str(manifest.get('subject') or 'chinese')
    material_type = 'homework'
    fctx = manifest.get('feedback_context') if isinstance(manifest.get('feedback_context'), dict) else {}
    if fctx.get('material_type'):
        material_type = str(fctx.get('material_type') or material_type)
    gc = manifest.get('grading_config') if isinstance(manifest.get('grading_config'), dict) else {}
    assigned = None
    if gc.get('assigned_pages'):
        try:
            assigned = [int(p) for p in gc['assigned_pages']]
        except (TypeError, ValueError):
            assigned = None
    if trust is None:
        try:
            from app_chat.homework_grading.wgb_trust import build_wgb_trust_summary
            trust = build_wgb_trust_summary(
                paths.get('pass1_json') or '',
                subject,
                material_type=material_type,
                assigned_pages=assigned,
            ) or {}
        except Exception:
            trust = {}
    by_page, _unit_word = _need_verify_by_page(trust if isinstance(trust, dict) else {})
    if not by_page:
        return False
    store = load_suggestions(paths)
    for page_num, units in by_page.items():
        for u in units:
            qid = str(u.get('qid') or '').strip()
            if not qid:
                continue
            if not _item_has_llm(store, f'p{page_num}:{qid}'):
                return True
    return False


def _verdict_cn(verdict: Any) -> str:
    v = str(verdict or '').strip().lower()
    return {
        'correct': '判对',
        'wrong': '判错',
        'partial': '部分对',
        'uncertain': '待确认',
    }.get(v, v or '未判定')


def _user_safe_text(value: Any, limit: int = 36) -> str:
    """供模型输入/规则拼句的清洗。limit=0 表示不截断。"""
    text = re.sub(r'\s+', ' ', str(value or '').strip())
    text = re.sub(
        r'(layout_confidence|understanding_confidence|grading_confidence|'
        r'recognition_confidence|uncertain_reason|error_type|model_|json)',
        '',
        text,
        flags=re.I,
    ).strip(' ，,;；')
    if limit and len(text) > limit:
        text = text[:limit].rstrip('，,;；') + '…'
    return text


def build_rule_suggestions_for_question(
    question: Dict[str, Any],
    trust_unit: Optional[Dict[str, Any]] = None,
    *,
    subject: str = 'chinese',
) -> Dict[str, List[str]]:
    """规则兜底：用已有字段拼「哪里误认/误判」短句。"""
    from app_chat.homework_grading.confidence_zones import (
        clamp_confidence,
        combined_recognition_understanding_confidence,
        gray_shade,
    )

    qid = str(question.get('id') or '').strip() or '?'
    parent = _user_safe_text(
        question.get('parent_group_id') or question.get('parent_stem_excerpt') or '',
        0,
    )
    stem = _user_safe_text(question.get('stem_excerpt') or '', 0)
    printed = _user_safe_text(
        question.get('printed_text_marked')
        or question.get('printed_text')
        or question.get('layout_text')
        or '',
        0,
    )
    handwritten = _user_safe_text(
        question.get('handwritten_text_marked')
        or question.get('student_answer')
        or '',
        0,
    )
    understanding = _user_safe_text(question.get('understanding') or '', 0)
    comment = _user_safe_text(question.get('comment') or question.get('feedback') or '', 0)
    uncertain = _user_safe_text(question.get('uncertain_reason') or '', 0)
    error_type = _user_safe_text(question.get('error_type') or '', 0)
    verdict = _verdict_cn(question.get('verdict'))

    lc = clamp_confidence(question.get('layout_confidence'))
    rc = clamp_confidence(question.get('recognition_confidence'))
    uc = clamp_confidence(question.get('understanding_confidence'))
    gc = clamp_confidence(question.get('grading_confidence'))
    und_combined = combined_recognition_understanding_confidence(question)

    layout_shade = (trust_unit or {}).get('layout_shade') or gray_shade(lc, mode='layout', subject=subject)
    und_shade = (trust_unit or {}).get('understanding_shade') or gray_shade(
        und_combined if und_combined is not None else uc, mode='understanding', subject=subject
    )
    grade_shade = (trust_unit or {}).get('grading_shade') or gray_shade(gc, mode='grading', subject=subject)
    black_roles = list((trust_unit or {}).get('black_roles') or [])
    cross_title = _user_safe_text((trust_unit or {}).get('cross_title') or '', 0)
    verify_reason = ''
    if black_roles:
        verify_reason = '、'.join(_ROLE_CN.get(r, r).replace('无损', '').replace('三区', '') for r in black_roles) + '把握偏低'
    elif cross_title:
        verify_reason = cross_title

    layout: List[str] = []
    understanding_list: List[str] = []
    grading: List[str] = []

    # —— 版面：印刷识别相关 ——
    if 'layout' in black_roles or layout_shade == 'black':
        layout.append(f'题号{qid}框选偏移或漏框')
    if printed:
        layout.append(f'印刷题干误读成「{printed}」')
    elif stem:
        layout.append(f'版面题干截取不准（{stem}）')
    if parent:
        layout.append(f'所属大题「{parent}」边界划错')
    if lc is not None and lc < 70:
        layout.append(f'版面{_confidence_plain(lc)}需复核')
    if not layout:
        layout.append(f'第{qid}题印刷排版识别有偏差')
        layout.append('题号或作答区定位不准')

    # —— 理解：手写识别 + 题意理解 ——
    if 'understanding' in black_roles or und_shade == 'black':
        understanding_list.append('手写作答识别可能认错字')
    if handwritten:
        understanding_list.append(f'手写答案误认成「{handwritten}」')
    if understanding:
        understanding_list.append(f'题意理解偏差：{understanding}')
    if uncertain:
        understanding_list.append(f'存疑点：{uncertain}')
    if rc is not None and rc < 70:
        understanding_list.append(f'手写识别{_confidence_plain(rc)}')
    if uc is not None and uc < 70:
        understanding_list.append(f'理解{_confidence_plain(uc)}')
    if not understanding_list:
        understanding_list.append('手写内容与印刷题干对不齐')
        understanding_list.append('理解步骤可能误判学生意图')

    # —— 批改：对错与批语 ——
    if 'grading' in black_roles or grade_shade == 'black':
        grading.append(f'对错判定不稳（现为{verdict}）')
    if error_type:
        grading.append(f'错误类型可能标错：{error_type}')
    if comment:
        grading.append(f'批语依据不足：{comment}')
    if verdict in ('判对', '判错', '部分对', '待确认'):
        grading.append(f'批改结果「{verdict}」需对照原卷')
    if gc is not None and gc < 70:
        grading.append(f'批改{_confidence_plain(gc)}')
    if verify_reason:
        grading.append(f'因{verify_reason}建议重核')
    if not grading:
        grading.append(f'批改结论「{verdict}」可能有误')
        grading.append('得分点或扣分依据不准确')

    return {
        'layout': _normalize_phrases(layout)[:3] or ['版面题号或框选可能有误', '印刷内容识别不准确'],
        'understanding': _normalize_phrases(understanding_list)[:3] or ['手写识别可能认错', '题意理解可能有偏差'],
        'grading': _normalize_phrases(grading)[:3] or ['对错判定可能不准', '批语与原卷不完全相符'],
    }


def _parse_page_llm_payload(raw: Any, expected_qids: List[str]) -> Dict[str, Dict[str, List[str]]]:
    """解析模型输出为 qid_local → {layout,understanding,grading}。"""
    data = raw
    if isinstance(raw, str):
        from app_chat.homework_grading.llm_clients import _loads_json_with_retry_text
        data = _loads_json_with_retry_text(raw)
    if not isinstance(data, dict):
        raise ValueError('模型输出不是对象')

    # 允许 {items:[...]} 或 {qid:{...}} 或 {questions:{qid:{...}}}
    bucket = data.get('items') or data.get('questions') or data.get('by_qid') or data
    if isinstance(bucket, list):
        mapped: Dict[str, Any] = {}
        for row in bucket:
            if not isinstance(row, dict):
                continue
            key = str(row.get('id') or row.get('qid') or row.get('qid_local') or '').strip()
            if key:
                mapped[key] = row
        bucket = mapped
    if not isinstance(bucket, dict):
        raise ValueError('模型输出缺少题目映射')

    out: Dict[str, Dict[str, List[str]]] = {}
    for qid in expected_qids:
        row = bucket.get(qid) or bucket.get(f'p:{qid}') or bucket.get(str(qid))
        if not isinstance(row, dict):
            # 模糊：只比尾部
            for k, v in bucket.items():
                if str(k).endswith(str(qid)) and isinstance(v, dict):
                    row = v
                    break
        if not isinstance(row, dict):
            raise ValueError(f'缺少题 {qid} 的建议')
        item = {
            'layout': _normalize_phrases(row.get('layout')),
            'understanding': _normalize_phrases(row.get('understanding')),
            'grading': _normalize_phrases(row.get('grading')),
        }
        for role in _ROLES:
            if len(item[role]) < 2:
                raise ValueError(f'题 {qid} 的 {role} 建议不足 2 条')
        out[qid] = item
    return out


def _build_llm_user_text(
    page_num: int,
    units: List[Dict[str, Any]],
    questions_by_id: Dict[str, Dict[str, Any]],
    *,
    unit_word: str = '题',
) -> str:
    lines = [
        f'这是第 {page_num} 页原卷图像。请只针对下列「需加强核实」的{unit_word}/条目写可点短句。',
        '站位：你在帮老师做核验勾选——老师对照原卷时最想点选的是「模型在这道题上具体误认/误判了什么」。',
        '务必先看图中该题/条目的真实版面（题号、印刷题干、选项/空位、作答区、手写笔迹、邻近题边界），'
        '再对照下方识别与批改摘要，找出对该题内容本身最容易出的差错，而不是空泛套话。',
        '要求：',
        '1) 每个位置三个步骤各给 2～3 条短句，每条约 12～28 字（尽量贴合该长度；内容具体优先于硬凑字数）；',
        '2) 每条都要能落到「这道题的某处内容」：可点出误读了哪段印刷、误认了哪处手写、错判了哪个得分点；',
        '3) 优先写视觉模型/批改模型对本题最可能犯的错：形近字、漏读条件、选项串题、框线切错、'
        '把旁题答案并进来、把涂改当终答、把半对判满对/满错、批语与卷面不符等；',
        '4) 用普通老师能懂的业务用语，禁止程序变量名或内部黑话；'
        '输入里的「白区/灰区/黑区」仅供你推断，输出短句中禁止出现这些词；',
        '5) 版面侧重印刷题干/题号/框选/选项排布；理解侧重手写识别与题意；批改侧重对错与批语；',
        '6) 误判往往更多出在理解与批改，版面也可能有但不要二极管；',
        '7) 只输出严格 JSON，不要 markdown。格式：',
        '{"题号或条目号":{"layout":["…","…"],"understanding":["…","…"],"grading":["…","…"]}, ...}',
        '',
        f'本页需核实位置（共 {len(units)} 处）：',
    ]
    for u in units:
        qid = str(u.get('qid') or '').strip()
        q = questions_by_id.get(qid) or {}
        roles_cn = str(u.get('black_roles_cn') or '').strip()
        reason = str(u.get('cross_title') or '').strip()
        if roles_cn:
            reason = (reason + '；' if reason else '') + f'黑区在{roles_cn}'
        lines.append(
            f'- {u.get("label") or qid}（编号 {qid}）· 核实原因：{reason or "需加强核实"}'
        )
        lines.append(
            f'  版面把握：{_shade_label_for_model(u.get("layout_shade"), q.get("layout_confidence"))}；'
            f'理解把握：{_shade_label_for_model(u.get("understanding_shade"), q.get("understanding_confidence"))}；'
            f'批改把握：{_shade_label_for_model(u.get("grading_shade"), q.get("grading_confidence"))}'
        )
        if q.get('parent_group_id') or q.get('parent_stem_excerpt'):
            lines.append(
                f'  所属大题：{_user_safe_text(q.get("parent_group_id") or q.get("parent_stem_excerpt"), 120)}'
            )
        if q.get('stem_excerpt'):
            lines.append(f'  题干摘要：{_user_safe_text(q.get("stem_excerpt"), 160)}')
        printed = q.get('printed_text_marked') or q.get('printed_text')
        if printed:
            lines.append(f'  印刷识别：{_user_safe_text(printed, 220)}')
        handwritten_marked = q.get('handwritten_text_marked')
        student_answer = q.get('student_answer')
        if handwritten_marked:
            lines.append(f'  手写识别（含笔色标记）：{_user_safe_text(handwritten_marked, 220)}')
            # 标记版去掉标签后应等于纯转写；若另有 student_answer 且不同，一并给出
            plain = _user_safe_text(student_answer, 220) if student_answer else ''
            marked_plain = _user_safe_text(
                re.sub(r'<[^>]+>', '', str(handwritten_marked or '')), 220
            )
            if plain and plain != marked_plain:
                lines.append(f'  手写纯转写：{plain}')
        elif student_answer:
            lines.append(f'  手写/作答识别：{_user_safe_text(student_answer, 220)}')
        if q.get('understanding'):
            lines.append(f'  理解：{_user_safe_text(q.get("understanding"), 160)}')
        lines.append(
            f'  批改结果：{_verdict_cn(q.get("verdict"))}；'
            f'错误类型：{_user_safe_text(q.get("error_type"), 80) or "无"}；'
            f'存疑：{_user_safe_text(q.get("uncertain_reason"), 120) or "无"}'
        )
        if q.get('comment') or q.get('feedback'):
            lines.append(f'  批语：{_user_safe_text(q.get("comment") or q.get("feedback"), 160)}')
        lines.append(
            '  （请对照原卷图中本题实际印刷与手写，写出老师核验时最想勾选的具体误认/误判点）'
        )
    return '\n'.join(lines)


def generate_page_suggestions_llm(
    image_path: str,
    page_num: int,
    units: List[Dict[str, Any]],
    questions_by_id: Dict[str, Dict[str, Any]],
    *,
    unit_word: str = '题',
    feedback_runtime=None,
) -> Dict[str, Dict[str, List[str]]]:
    """对单页调视觉模型；成功返回 local_qid→三步短句。失败抛异常由上层兜底。"""
    from app_chat.homework_grading.llm_clients import (
        _call_qwen_json,
        _loads_json_with_retry_text,
    )

    if not image_path or not os.path.isfile(image_path):
        raise FileNotFoundError(f'页图不存在: {image_path}')
    expected = [str(u.get('qid') or '').strip() for u in units if str(u.get('qid') or '').strip()]
    if not expected:
        raise ValueError('本页无待核实题号')

    system = (
        '你是协助老师核验作业批改的助手。对照原卷页图与批改摘要，'
        '为每个需加强核实的题/条目写出三步骤「可点选项」：老师最可能想勾选的具体误认/误判点。'
        '必须结合该题在图上的版面实况（印刷文字、选项/空位、作答区、手写、邻近边界），'
        '优先写模型识别/理解/批改对本题内容最容易出错之处，避免空泛套话。'
        '输入中的白区/灰区/黑区是把握分区，仅供推断；'
        '输出短句须让普通老师能懂，禁止写出白区/灰区/黑区/白灰黑及程序变量名。'
        '只输出 JSON 对象，键为题号/条目号。'
    )
    user_text = _build_llm_user_text(
        page_num, units, questions_by_id, unit_word=unit_word,
    )
    messages = [
        {'role': 'system', 'content': system},
        {
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}},
                {'type': 'text', 'text': user_text},
            ],
        },
    ]
    extra_body = {'enable_thinking': False}
    resp = _call_qwen_json(
        messages,
        extra_body,
        # 须落在 feedback_runtime.qwen_call_policy.allowed_temperatures（含 0.1）
        temperature=0.1,
        **({'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {}),
    )
    content = ''
    try:
        content = resp.choices[0].message.content or ''
    except Exception:
        content = str(resp or '')
    parsed = _loads_json_with_retry_text(content)
    return _parse_page_llm_payload(parsed, expected)


def _load_pass2_comments(paths: Dict[str, str], manifest: Dict[str, Any]) -> Dict[str, str]:
    """Pass1 题上常无 comment；批语在 Pass2 per_question_feedback。"""
    try:
        from app_chat.homework_grading.result_cards import _named_json, _sample_id
    except Exception:
        return {}
    subject = str(manifest.get('subject') or 'chinese')
    analysis_id = str(manifest.get('analysis_id') or '')
    sample_id = _sample_id(analysis_id) if analysis_id else ''
    if not sample_id:
        return {}
    report = _named_json(paths.get('pass2_report') or '', subject, sample_id, '_report.json')
    if not isinstance(report, dict):
        return {}
    out: Dict[str, str] = {}
    for item in report.get('per_question_feedback') or []:
        if not isinstance(item, dict):
            continue
        qid_global = str(item.get('qid_global') or '').strip()
        comment = str(item.get('comment') or '').strip()
        if qid_global and comment:
            out[qid_global] = comment
        # 也按本地题号索引，便于页内合并
        local = ''
        m = re.match(r'^p\d+:(.+)$', qid_global, re.I)
        if m:
            local = m.group(1).strip()
        if local and comment and local not in out:
            out[local] = comment
    return out


def _load_page_questions(
    paths: Dict[str, str],
    page: Dict[str, Any],
    *,
    pass2_comments: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    from app_chat.homework_grading.staged_pipeline import _question_json_path

    official = _question_json_path(paths['pass1_json'], page['clean_abs_path'])
    data = safe_json_load(official) if os.path.isfile(official) else {}
    qs = data.get('questions') if isinstance(data, dict) else None
    out: Dict[str, Dict[str, Any]] = {}
    page_num = page.get('page')
    comments = pass2_comments or {}
    if isinstance(qs, list):
        for q in qs:
            if not isinstance(q, dict) or q.get('id') is None:
                continue
            qid = str(q.get('id')).strip()
            row = dict(q)
            if not row.get('comment') and not row.get('feedback'):
                qid_global = f'p{page_num}:{qid}' if page_num is not None else ''
                c = comments.get(qid_global) or comments.get(qid) or ''
                if c:
                    row['comment'] = c
            out[qid] = row
    return out


def _page_image_path(page: Dict[str, Any]) -> str:
    from app_chat.homework_grading.fixed_sample_crossout import MODEL_IMAGE_PATH_KEY
    path = page.get(MODEL_IMAGE_PATH_KEY) or page.get('clean_abs_path') or ''
    return str(path)


def _need_verify_by_page(
    trust: Dict[str, Any],
) -> Tuple[Dict[int, List[Dict[str, Any]]], str]:
    need = trust.get('need_verify') if isinstance(trust, dict) else None
    if not isinstance(need, list):
        need = []
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for u in need:
        if not isinstance(u, dict):
            continue
        try:
            page = int(u.get('page') if u.get('page') is not None else str(u.get('qid_global') or '').split(':')[0].lstrip('pP'))
        except Exception:
            m = re.match(r'^p(\d+):', str(u.get('qid_global') or ''), re.I)
            if not m:
                continue
            page = int(m.group(1))
        qid = str(u.get('qid') or '').strip()
        if not qid:
            m2 = re.match(r'^p\d+:(.+)$', str(u.get('qid_global') or ''), re.I)
            qid = m2.group(1).strip() if m2 else ''
        if not qid:
            continue
        row = dict(u)
        row['qid'] = qid
        row['page'] = page
        by_page.setdefault(page, []).append(row)
    return by_page, str((trust or {}).get('unit_word') or '题')


def generate_verify_suggestions(
    paths: Dict[str, str],
    manifest: Optional[Dict[str, Any]] = None,
    *,
    feedback_runtime=None,
    prefer_keep_llm: bool = False,
    trust: Optional[Dict[str, Any]] = None,
    progress_cb: Optional[Any] = None,
) -> Dict[str, Any]:
    """批改/核验迭代报告完成后调用：为需核实页预生成可点短句。

    prefer_keep_llm=False（完整批改收尾）：对需核实项全部重调模型。
    prefer_keep_llm=True（核验后局部迭代）：
    - 页内当前需核实题均已有模型成功结果 → 整页跳过；
    - 否则仅对尚无模型结果的题调模型，已有模型结果的题原样保留。

    progress_cb(optional): callable(dict) 如
      {page_index, pages_total, page_num, phase, msg, progress}
    """
    manifest = manifest if isinstance(manifest, dict) else safe_json_load(paths.get('manifest') or '') or {}
    subject = str(manifest.get('subject') or 'chinese')
    material_type = 'homework'
    fctx = manifest.get('feedback_context') if isinstance(manifest.get('feedback_context'), dict) else {}
    if fctx.get('material_type'):
        material_type = str(fctx.get('material_type') or material_type)
    gc = manifest.get('grading_config') if isinstance(manifest.get('grading_config'), dict) else {}
    assigned = None
    if gc.get('assigned_pages'):
        try:
            assigned = [int(p) for p in gc['assigned_pages']]
        except (TypeError, ValueError):
            assigned = None

    if trust is None:
        from app_chat.homework_grading.wgb_trust import build_wgb_trust_summary
        trust = build_wgb_trust_summary(
            paths.get('pass1_json') or '',
            subject,
            material_type=material_type,
            assigned_pages=assigned,
        ) or {}

    by_page, unit_word = _need_verify_by_page(trust)
    store = load_suggestions(paths)
    if not by_page:
        # 清空无核实项时仍保留文件结构
        store['pages'] = {}
        store['items'] = {}
        save_suggestions(paths, store)
        return store

    from app_chat.homework_grading.staged_pipeline import load_homework_clean_pages
    pages = load_homework_clean_pages(paths)
    page_map = {int(p['page']): p for p in pages if p.get('page') is not None}
    pass2_comments = _load_pass2_comments(paths, manifest)

    page_items = sorted(by_page.items())
    pages_total = len(page_items)

    def _emit_progress(page_index: int, page_num: int, *, msg: str, progress: Optional[int] = None) -> None:
        if not callable(progress_cb):
            return
        # 手动沉淀进度条区间约 20–55
        pct = progress
        if pct is None and pages_total > 0:
            pct = 20 + int(35 * page_index / pages_total)
        try:
            progress_cb({
                'phase': 'verify_suggest',
                'page_index': page_index,
                'pages_total': pages_total,
                'page_num': page_num,
                'progress': max(20, min(55, int(pct or 20))),
                'msg': msg,
            })
        except Exception:
            pass

    for page_index, (page_num, units) in enumerate(page_items, start=1):
        page_key = str(page_num)
        existing_page = (store.get('pages') or {}).get(page_key) or {}
        qids = [str(u.get('qid') or '').strip() for u in units if str(u.get('qid') or '').strip()]
        qid_globals = [f'p{page_num}:{qid}' for qid in qids]
        trust_by_qid = {str(u.get('qid')): u for u in units}
        _emit_progress(
            page_index,
            page_num,
            msg=f'生成核验可点短句：第{page_index}页/需核验共{pages_total}页（原卷第{page_num}页）',
        )

        keep_llm: set = set()
        need_units: List[Dict[str, Any]] = []
        if prefer_keep_llm:
            for u in units:
                qid = str(u.get('qid') or '').strip()
                if not qid:
                    continue
                if _item_has_llm(store, f'p{page_num}:{qid}'):
                    keep_llm.add(qid)
                else:
                    need_units.append(u)
            if qids and not need_units:
                # 当前需核实题全部已有模型结果 → 整页跳过
                store.setdefault('pages', {})[page_key] = dict(existing_page) or {
                    'source': 'llm',
                    'generated_at': datetime.now().isoformat(timespec='seconds'),
                }
                store['pages'][page_key]['source'] = 'llm'
                store['pages'][page_key]['qids'] = qid_globals
                continue
        else:
            need_units = [u for u in units if str(u.get('qid') or '').strip()]

        page = page_map.get(page_num)
        questions_by_id = (
            _load_page_questions(paths, page, pass2_comments=pass2_comments) if page else {}
        )
        llm_ok = False
        llm_map: Dict[str, Dict[str, List[str]]] = {}
        if page and need_units:
            image_path = _page_image_path(page)
            try:
                llm_map = generate_page_suggestions_llm(
                    image_path,
                    page_num,
                    need_units,
                    questions_by_id,
                    unit_word=unit_word,
                    feedback_runtime=feedback_runtime,
                )
                llm_ok = True
            except Exception:
                traceback.print_exc()
                llm_ok = False
                llm_map = {}

        now = datetime.now().isoformat(timespec='seconds')
        store.setdefault('pages', {})[page_key] = {
            'source': 'rule',
            'generated_at': now,
            'qids': qid_globals,
        }
        for qid in qids:
            qid_global = f'p{page_num}:{qid}'
            if prefer_keep_llm and qid in keep_llm:
                # 已有模型结果：原样保留
                continue
            q = questions_by_id.get(qid) or {'id': qid}
            if llm_ok and qid in llm_map:
                phrases = llm_map[qid]
                item_source = 'llm'
            else:
                phrases = build_rule_suggestions_for_question(
                    q, trust_by_qid.get(qid), subject=subject,
                )
                item_source = 'rule'
            store.setdefault('items', {})[qid_global] = {
                'qid_global': qid_global,
                'page': page_num,
                'qid': qid,
                'source': item_source,
                'layout': phrases.get('layout') or [],
                'understanding': phrases.get('understanding') or [],
                'grading': phrases.get('grading') or [],
                'generated_at': now,
            }
        page_items = [store['items'].get(f'p{page_num}:{qid}') for qid in qids]
        if page_items and all((it or {}).get('source') == 'llm' for it in page_items):
            store['pages'][page_key]['source'] = 'llm'
        else:
            store['pages'][page_key]['source'] = 'rule'

    # 只保留当前仍需核实的题/页
    keep = {f'p{page_num}:{u.get("qid")}' for page_num, units in by_page.items() for u in units}
    store['items'] = {k: v for k, v in (store.get('items') or {}).items() if k in keep}
    store['pages'] = {
        str(page_num): (store.get('pages') or {}).get(str(page_num))
        for page_num in by_page
        if (store.get('pages') or {}).get(str(page_num))
    }
    save_suggestions(paths, store)
    return store
