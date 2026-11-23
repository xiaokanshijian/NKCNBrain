# encoding=utf-8
"""主体本体语义关键词空间增强 · 源头文档流水线（v3）。

依据：docs/本体语义关键词空间递进/主体本体语义关键词空间增强方案.md
与方案澄清点选结果.json。禁止卡片统计作为权威词源；有源头走本流水线。
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app_chat.semantic_reorganize_pipeline import (
    book_key_issue_path,
    book_kw_attrs_verified_path,
    book_kw_connect_path,
    card_condense_dir,
    card_condense_path,
    write_keyword_attrs_file,
    _write_book_kw_connect,
    FINAL_MARKER,
)

PIPELINE_ID = 'v3_source_document'
# 按文档抽词、按文档定象限：最高同时 4 路。各篇只看自己的材料和本子四象限，互不参照。
V3_DOC_CONCURRENCY = 4

SOURCE_PRIORITY_BLURB = (
    '源头优先序（须遵守）：文档名 > DocStructure > Presummary > Skill >（卡片证据仅局部佐证）。'
    '没有 Presummary 时，材料中的 PreImageSummary 代替 Presummary。'
    '每个词须用本色解释；四色/DMT/三类按本义独立说透，禁止四色混杂补洞。'
)

# admin 可覆盖：环境变量 NKCN_SEMANTIC_V3_MODEL_CHAIN=abbr1,abbr2,...
DEFAULT_MODEL_CHAIN = (
    'claude-opus-5.5',
    'gpt-6-astra',
    'claude-opus-4.8',
    'gemini-3.1-pro-preview',
)


def _user_root(username: str) -> str:
    return os.path.normpath(os.path.join('.', 'received_dir', 'user_raw_file', username))


def intent_memory_path(username: str) -> str:
    d = os.path.join(_user_root(username), 'semantic_intent_memory')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'user_semantic_intent.json')


def load_intent_memory(username: str) -> Dict[str, Any]:
    path = intent_memory_path(username)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_intent_memory(username: str, data: Dict[str, Any]) -> None:
    path = intent_memory_path(username)
    payload = dict(data or {})
    payload['updated_at'] = datetime.now().isoformat(timespec='seconds')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def book_top_keywords_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookTopKeywords.json')


def book_scale_definitions_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookScaleDefinitions.json')


def book_longitude_links_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookLongitudeLinks.json')


def book_quadrant_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookKeywordQuadrants.json')


def book_quadrant_meaning_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookQuadrantMeaning.json')


def book_levels_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookKeywordLevels.json')


def book_thermometer_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookThermometerSpiral.json')


def v3_debug_dir(username: str) -> str:
    d = os.path.join(card_condense_dir(username), 'v3_debug')
    os.makedirs(d, exist_ok=True)
    return d


def model_chain() -> List[str]:
    """降级链：环境变量临时覆盖 > admin「一些系统能力的模型配置」P4 四槽 > 默认（C5）。"""
    raw = (os.environ.get('NKCN_SEMANTIC_V3_MODEL_CHAIN') or '').strip()
    if raw:
        return [x.strip() for x in raw.split(',') if x.strip()]
    try:
        from app_chat.scene_models import get_scene_abbr_chain
        chain = get_scene_abbr_chain(
            [
                'semantic_v3_model_1',
                'semantic_v3_model_2',
                'semantic_v3_model_3',
                'semantic_v3_model_4',
            ],
            list(DEFAULT_MODEL_CHAIN),
        )
        if chain:
            return chain
    except Exception as exc:
        print(f'[semantic_v3] 读取 admin 场景模型链失败，用默认: {exc}', flush=True)
    return list(DEFAULT_MODEL_CHAIN)


JSON_OUTPUT_RULES = (
    '必须只输出一个合法 JSON（对象或数组），禁止 markdown 围栏与多余说明。'
    '字符串值内部禁止使用英文双引号 "；需要引号时一律用中文「」或『』。'
    '不要在字符串里再嵌套未转义的 JSON。'
    '数字字段用数字类型；布尔用 true/false；缺失用 null 或空数组。'
)


def loads_json_loose(text: str) -> Any:
    """解析模型 JSON；加强：围栏剥离、截取、尾逗号、内部控制字符、内嵌引号。"""
    raw = (text or '').strip()
    if not raw:
        raise ValueError('empty json')
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.I)
    raw = re.sub(r'\s*```\s*$', '', raw)
    # 去掉常见前缀废话
    raw = re.sub(r'^(?:输出|结果|如下)[：:]\s*', '', raw.strip())

    candidates: List[str] = []
    for opener, closer in (('{', '}'), ('[', ']')):
        i = raw.find(opener)
        j = raw.rfind(closer)
        if i >= 0 and j > i:
            candidates.append(raw[i : j + 1])
    if not candidates:
        candidates = [raw]

    errors: List[str] = []
    for candidate in candidates:
        for variant in (
            candidate,
            _strip_trailing_commas(candidate),
            _fix_inner_quotes(_strip_trailing_commas(candidate)),
            _escape_ctrl_in_strings(_fix_inner_quotes(_strip_trailing_commas(candidate))),
        ):
            try:
                return json.loads(variant)
            except json.JSONDecodeError as exc:
                errors.append(str(exc))
                continue
    raise ValueError('cannot parse json: ' + (errors[-1] if errors else 'unknown'))


def _strip_trailing_commas(s: str) -> str:
    return re.sub(r',\s*([}\]])', r'\1', s)


def _escape_ctrl_in_strings(s: str) -> str:
    out: List[str] = []
    in_str = False
    escape = False
    for ch in s:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == '\\' and in_str:
            out.append(ch)
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            continue
        if in_str and ch in ('\n', '\r', '\t'):
            out.append('\\n' if ch == '\n' else ('\\r' if ch == '\r' else '\\t'))
            continue
        out.append(ch)
    return ''.join(out)


def _fix_inner_quotes(s: str) -> str:
    """字符串值内部：若 " 后面不像合法结束符，则换成中文引号。"""
    out: List[str] = []
    in_str = False
    escape = False
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if escape:
            out.append(ch)
            escape = False
            i += 1
            continue
        if ch == '\\' and in_str:
            out.append(ch)
            escape = True
            i += 1
            continue
        if ch == '"':
            if not in_str:
                in_str = True
                out.append(ch)
            else:
                # 窥探后续：空白后若是 , } ] : 则视为结束，否则当内部引号
                j = i + 1
                while j < n and s[j] in ' \t\r\n':
                    j += 1
                if j >= n or s[j] in ',}]':
                    in_str = False
                    out.append(ch)
                elif s[j] == ':':
                    # 仅当像 key 结束时才结束——值内部的 "xxx": 极少；保守当作内部
                    in_str = False
                    out.append(ch)
                else:
                    out.append('「')
            i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def call_strong_llm(
    prompt: str,
    *,
    system: str,
    max_tokens: int = 6000,
    timeout_s: float = 240.0,
    track_fn: Optional[Callable] = None,
) -> Tuple[str, str]:
    """按方案降级链调用强模型（流式优先）。"""
    from app_chat.cross_reorganize_skills import _client_for_abbr, _collect_stream_text

    errors: List[str] = []
    for abbr in model_chain():
        try:
            print(f'[semantic_v3] LLM abbr={abbr} stream=1', flush=True)
            client, model_name, create_extra = _client_for_abbr(abbr)
            try:
                client = client.with_options(timeout=float(timeout_s))
            except Exception:
                pass
            kwargs: Dict[str, Any] = {
                'model': model_name,
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': prompt},
                ],
                'max_tokens': int(max_tokens),
                'temperature': 0.25,
                'stream': True,
            }
            kwargs.update(create_extra or {})
            text = _collect_stream_text(client.chat.completions.create(**kwargs))
            text = (text or '').strip()
            if len(text) < 20:
                raise ValueError('输出过短')
            if track_fn:
                try:
                    track_fn('claude')
                except Exception:
                    pass
            print(f'[semantic_v3] LLM ok model={model_name} chars={len(text)}', flush=True)
            return text, model_name
        except Exception as exc:
            errors.append(f'{abbr}:{exc}')
            print(f'[semantic_v3] LLM fail {abbr}: {exc}', flush=True)
            continue
    # 最后兜底 deepseek
    try:
        from app_chat.semantic_reorganize_pipeline import _deepseek_client, DEEPSEEK_FALLBACK
        client = _deepseek_client()
        rsp = client.chat.completions.create(
            model=DEEPSEEK_FALLBACK,
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.25,
        )
        text = (rsp.choices[0].message.content or '').strip()
        if track_fn:
            try:
                track_fn('deepseek')
            except Exception:
                pass
        return text, DEEPSEEK_FALLBACK
    except Exception as exc:
        raise RuntimeError('强模型链全部失败: ' + ' | '.join(errors[:4]) + f' | deepseek:{exc}')


def call_deepseek_llm(
    prompt: str,
    *,
    system: str,
    max_tokens: int = 6000,
    track_fn: Optional[Callable] = None,
) -> Tuple[str, str]:
    """机知判定临时只用 deepseek。提示词与强模型链相同，策略优化后再换回 call_strong_llm。

    deepseek-v4-pro 默认会先写一段推理。推理和正文共用 max_tokens，
    不关掉时正文经常被截成半句，JSON 无法解析。这里与其他 deepseek 调用一样关掉推理。
    """
    from app_chat.semantic_reorganize_pipeline import _deepseek_client, DEEPSEEK_FALLBACK

    client = _deepseek_client()
    last_err: Optional[Exception] = None
    budgets = [int(max_tokens), max(int(max_tokens), 8000)]
    for attempt, budget in enumerate(budgets, start=1):
        try:
            rsp = client.chat.completions.create(
                model=DEEPSEEK_FALLBACK,
                messages=[
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': prompt},
                ],
                max_tokens=budget,
                temperature=0.25,
                extra_body={'thinking': {'type': 'disabled'}},
            )
            choice = rsp.choices[0]
            text = (choice.message.content or '').strip()
            finish = getattr(choice, 'finish_reason', None)
            if len(text) < 20:
                raise ValueError(f'输出过短 finish={finish} chars={len(text)}')
            if finish == 'length':
                raise ValueError(f'输出被截断 finish=length chars={len(text)}')
            if track_fn:
                try:
                    track_fn('deepseek')
                except Exception:
                    pass
            print(
                f'[semantic_v3] LLM ok model={DEEPSEEK_FALLBACK} '
                f'chars={len(text)} finish={finish} attempt={attempt}',
                flush=True,
            )
            return text, DEEPSEEK_FALLBACK
        except Exception as exc:
            last_err = exc
            print(f'[semantic_v3] deepseek attempt={attempt} fail: {exc}', flush=True)
    raise RuntimeError(f'deepseek 机知调用失败: {last_err}')


def call_qwen_aliyun_llm(
    prompt: str,
    *,
    system: str,
    max_tokens: int = 8000,
    track_fn: Optional[Callable] = None,
) -> Tuple[str, str]:
    """按文档定象限。走阿里云兼容接口，模型 qwen3.7-max。关掉思考，避免正文被截断。"""
    from app_chat.homework_grading.llm_clients import _qwen_client

    client = _qwen_client()
    model_name = 'qwen3.7-max'
    last_err: Optional[Exception] = None
    budgets = [int(max_tokens), max(int(max_tokens), 8000)]
    for attempt, budget in enumerate(budgets, start=1):
        try:
            rsp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': prompt},
                ],
                max_tokens=budget,
                temperature=0.25,
                extra_body={'enable_thinking': False},
            )
            choice = rsp.choices[0]
            text = (choice.message.content or '').strip()
            finish = getattr(choice, 'finish_reason', None)
            if len(text) < 20:
                raise ValueError(f'输出过短 finish={finish} chars={len(text)}')
            if finish == 'length':
                raise ValueError(f'输出被截断 finish=length chars={len(text)}')
            if track_fn:
                try:
                    track_fn('qwen')
                except Exception:
                    pass
            print(
                f'[semantic_v3] LLM ok model={model_name} '
                f'chars={len(text)} finish={finish} attempt={attempt}',
                flush=True,
            )
            return text, model_name
        except Exception as exc:
            last_err = exc
            print(f'[semantic_v3] qwen attempt={attempt} fail: {exc}', flush=True)
    raise RuntimeError(f'qwen 文档象限调用失败: {last_err}')


def list_notebook_pdf_basenames(username: str) -> List[str]:
    root = _user_root(username)
    if not os.path.isdir(root):
        return []
    skip = {
        'cardImage', 'pre_summary', 'pre_image_summary', 'doc_structure', 'skills',
        'cardCondense', 'semantic_intent_memory', '_twin', 'keyword_status_history',
    }
    names = []
    for fn in os.listdir(root):
        if fn in skip or fn.startswith('.'):
            continue
        low = fn.lower()
        if low.endswith(('.pdf', '.doc', '.docx', '.ppt', '.pptx', '.txt', '.md')):
            names.append(fn)
    return sorted(names)


def _stem_ext(filename: str) -> Tuple[str, str]:
    base, ext = os.path.splitext(filename)
    return base, (ext[1:] if ext.startswith('.') else ext) or 'pdf'


def _read_text_file(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ''
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def _load_pre_image_summary(root: str, stem: str, ext: str) -> str:
    pdir = os.path.join(root, 'pre_image_summary')
    if not os.path.isdir(pdir):
        return ''
    preferred = [
        os.path.join(pdir, f'{stem}_PreImageSummary_{ext}.md'),
        os.path.join(pdir, f'{stem}_PreImageSummary_pdf.md'),
    ]
    for path in preferred:
        if os.path.isfile(path):
            return _read_text_file(path)
    for name in os.listdir(pdir):
        if not name.startswith(stem) or 'PreImageSummary' not in name or 'Origin' in name:
            continue
        return _read_text_file(os.path.join(pdir, name))
    return ''


def presummary_is_usable(text: str) -> bool:
    """空文本，或“总字数为 0、无法生成摘要”这类空文档说明，都不算有 Presummary。"""
    raw = (text or '').strip()
    if not raw:
        return False
    compact = re.sub(r'\s+', '', raw).replace('０', '0')
    zero = re.search(
        r'(总字数[为是：:]?0字'
        r'|中文0字[，,]?英文0词'
        r'|英文0词[，,]?中文0字'
        r'|文档字数为0'
        r'|文档内容为空'
        r'|原文为空'
        r'|空文档'
        r'|未提供任何可阅读'
        r'|没有可阅读的正文'
        r'|没有任何可读取的文本'
        r'|无任何可分析的正文'
        r'|没有任何(?:可读取的|可分析的)?(?:文字|文本|正文)'
        r'|未包含任何(?:文字|文本|正文)'
        r'|无内容可分析)',
        compact,
    )
    if not zero:
        return True
    refusal = re.search(
        r'(无法生成|不能生成|无法提取|无法按章节|不存在可依据|不存在可供分析'
        r'|无内容可分析|请提供实际文档|建议确认文档是否上传)',
        compact,
    )
    if not refusal:
        return True
    # 同一篇里若已写出实质性内容主体，仍视为有效摘要
    for subject in re.findall(r'内容主体[：:](.{0,48})', raw):
        head = re.sub(r'\s+', '', subject)
        if head and not re.match(r'(无|空|未|没有|不存在|无法)', head):
            return True
    return False


def summary_text_for_analysis(bundle: Dict[str, str]) -> str:
    """有可用 Presummary 就用它；没有，或只是空文档说明，则用 PreImageSummary 整段代替。"""
    ps = bundle.get('presummary') or ''
    if presummary_is_usable(ps):
        return ps.strip()
    pi = (bundle.get('pre_image_summary') or '').strip()
    if not pi:
        return ''
    return '（本文件没有可用的 Presummary，以下用 PreImageSummary 代替）\n' + pi


def load_doc_source_bundle(username: str, filename: str) -> Dict[str, str]:
    """读取单文档 DocStructure / Presummary / PreImageSummary / Skill 文本。"""
    root = _user_root(username)
    stem, ext = _stem_ext(filename)
    bundle = {
        'filename': filename,
        'doc_structure': '',
        'presummary': '',
        'pre_image_summary': '',
        'skill': '',
    }
    ds = os.path.join(root, 'doc_structure', f'{stem}_DocStructure.md')
    if not os.path.isfile(ds):
        # 兼容 INFO 样例命名
        alt = os.path.join(root, 'doc_structure', f'{stem}_DocStructure.md')
        ds = alt if os.path.isfile(alt) else ds
    if os.path.isfile(ds):
        with open(ds, 'r', encoding='utf-8', errors='ignore') as f:
            bundle['doc_structure'] = f.read()

    ps = os.path.join(root, 'pre_summary', f'{stem}_Presummary_{ext}.md')
    if not os.path.isfile(ps):
        # 宽松匹配
        pdir = os.path.join(root, 'pre_summary')
        if os.path.isdir(pdir):
            for n in os.listdir(pdir):
                if n.startswith(stem) and 'Presummary' in n:
                    ps = os.path.join(pdir, n)
                    break
    if os.path.isfile(ps):
        with open(ps, 'r', encoding='utf-8', errors='ignore') as f:
            bundle['presummary'] = f.read()
    bundle['pre_image_summary'] = _load_pre_image_summary(root, stem, ext)

    skills_dir = os.path.join(root, 'skills')
    if os.path.isdir(skills_dir):
        # Skill 目录名常为 slug；用文件名片段模糊匹配 SKILL.md
        needle = re.sub(r'\W+', '', stem).lower()[:24]
        best = ''
        for sub in os.listdir(skills_dir):
            sp = os.path.join(skills_dir, sub, 'SKILL.md')
            if not os.path.isfile(sp):
                continue
            slug = re.sub(r'\W+', '', sub).lower()
            if needle and needle[:12] in slug:
                best = sp
                break
            if not best:
                # 读 frontmatter 看 source 文件名
                try:
                    with open(sp, 'r', encoding='utf-8', errors='ignore') as f:
                        head = f.read(800)
                    if filename in head or stem in head:
                        best = sp
                        break
                except Exception:
                    pass
        if best:
            with open(best, 'r', encoding='utf-8', errors='ignore') as f:
                bundle['skill'] = f.read()
    return bundle


def _source_gaps(bundle: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """返回 (可尝试补齐的缺项, 补不上也不能继续的缺项)。

    能继续的最低条件：有 Presummary 或 PreImageSummary，并且有 DocStructure 或 Skill。
    """
    has_ps = presummary_is_usable(bundle.get('presummary') or '')
    has_pi = bool((bundle.get('pre_image_summary') or '').strip())
    has_ds = bool((bundle.get('doc_structure') or '').strip())
    has_sk = bool((bundle.get('skill') or '').strip())
    backfill_lack: List[str] = []
    hard_lack: List[str] = []
    if not has_ps:
        backfill_lack.append('Presummary')
    if not has_ds:
        backfill_lack.append('DocStructure')
    if not has_sk:
        backfill_lack.append('Skill')
    if not has_ps and not has_pi:
        hard_lack.append('Presummary/PreImageSummary')
    if not has_ds and not has_sk:
        hard_lack.append('DocStructure/Skill')
    return backfill_lack, hard_lack


def assess_source_readiness(username: str) -> Dict[str, Any]:
    """检查能否进入 v3。

    先按缺项补齐。补齐后每份文档只要有摘要（Presummary 或 PreImageSummary）
    且有 DocStructure 或 Skill 之一，就可以梳理。
    仍有文档两条都不满足时 ok=False，不允许只分析已满足的那几份。
    """
    files = list_notebook_pdf_basenames(username)
    if not files:
        return {
            'ok': False,
            'reason': 'no_documents',
            'message': '本子无文档，可走旧卡片语义链路',
            'files': [],
            'missing': [],
            'backfill': [],
            'needs_backfill': False,
            'ready_files': [],
            'used_pre_image': [],
            'total': 0,
            'ready_count': 0,
        }
    missing = []
    backfill = []
    ready = []
    used_pre_image = []
    for fn in files:
        b = load_doc_source_bundle(username, fn)
        backfill_lack, hard_lack = _source_gaps(b)
        if backfill_lack:
            backfill.append({'filename': fn, 'lack': backfill_lack})
        if hard_lack:
            missing.append({'filename': fn, 'lack': hard_lack})
        else:
            ready.append(fn)
            if not presummary_is_usable(b.get('presummary') or '') and (b.get('pre_image_summary') or '').strip():
                used_pre_image.append(fn)
    total = len(files)
    ready_count = len(ready)
    base = {
        'files': files,
        'missing': missing,
        'backfill': backfill,
        'needs_backfill': bool(backfill),
        'ready_files': ready,
        'used_pre_image': used_pre_image,
        'total': total,
        'ready_count': ready_count,
    }
    if missing:
        miss_preview = '；'.join(
            f"{m['filename']}缺{'/'.join(m['lack'])}" for m in missing[:8]
        )
        base.update({
            'ok': False,
            'reason': 'incomplete_sources',
            'message': (
                f'本子共 {total} 份文档，{ready_count} 份可以梳理。'
                '其余文档仍然没有可用摘要（Presummary 或 PreImageSummary），'
                '或者 DocStructure 与 Skill 都没有。'
                '已停止，不会改走旧卡片链路，也不会只分析已可梳理的文档。'
                f'缺项：{miss_preview}'
            ),
        })
        return base
    substitute = ''
    if used_pre_image:
        substitute = f'其中 {len(used_pre_image)} 份 Presummary 缺失或只是空文档说明，用 PreImageSummary 代替。'
    base.update({
        'ok': True,
        'reason': 'ready',
        'message': f'全部 {total} 份文档可以梳理。{substitute}',
    })
    return base


def ensure_all_document_sources(
    username: str,
    *,
    set_job_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """先补 Presummary / DocStructure / Skill。补不上时按最低条件放行。"""
    readiness = assess_source_readiness(username)
    if readiness.get('reason') == 'no_documents':
        return readiness
    if readiness.get('ok') and not readiness.get('needs_backfill'):
        return readiness

    real_name = username.split('_')[0] if '_' in username else username
    book_name = username[len(real_name) + 1 :] if '_' in username else ''
    pending = list(readiness.get('backfill') or [])
    if set_job_fn:
        set_job_fn(
            username,
            phase='source_backfill',
            last_action='补齐文档源头',
            last_action_detail=f'缺 {len(pending)} 份',
            progress_percent=3,
        )

    try:
        from llm_langchain.parse_input import process_document_pre_summary
    except Exception as exc:
        readiness['backfill_error'] = f'无法导入 presummary: {exc}'
        return readiness
    try:
        from app_chat.skill_generate import process_document_skill
    except Exception as exc:
        readiness['backfill_error'] = f'无法导入 skill_generate: {exc}'
        return readiness

    for i, item in enumerate(pending):
        fn = item.get('filename') or ''
        if not fn:
            continue
        if set_job_fn:
            set_job_fn(
                username,
                last_action_detail=fn,
                current_index=i + 1,
                total_cards=len(pending),
            )
        lack = set(item.get('lack') or [])
        try:
            if 'Presummary' in lack:
                ok, err = process_document_pre_summary(real_name, username, fn)
                wrote = ''
                if ok:
                    wrote = (load_doc_source_bundle(username, fn).get('presummary') or '')
                if (not ok) or (not presummary_is_usable(wrote)):
                    print(
                        f'[semantic_v3] backfill PS fail {fn}: {err or "写出的仍是空文档说明，视为没成功"}；'
                        '若有 PreImageSummary 则代替',
                        flush=True,
                    )
            # Skill 生成链路会顺带写 DocStructure。两者有一个即可继续。
            if 'DocStructure' in lack or 'Skill' in lack:
                ok2, err2 = process_document_skill(real_name, username, fn)
                if not ok2:
                    print(
                        f'[semantic_v3] backfill Skill/DS fail {fn}: {err2}；有其一且有摘要即可继续',
                        flush=True,
                    )
        except Exception as exc:
            print(f'[semantic_v3] backfill exception {fn}: {exc}', flush=True)
            traceback.print_exc()

    final = assess_source_readiness(username)
    final['backfill_attempted'] = True
    final['book_name'] = book_name
    return final


def _clip(text: str, n: int) -> str:
    t = (text or '').strip()
    return t if len(t) <= n else t[: n - 20] + '\n…(截断)'


def _intent_attr_follow_blurb(intent: Optional[Dict[str, Any]]) -> str:
    """把用户改属性背后的意图摘要喂给抽词/汇总模型。"""
    if not isinstance(intent, dict) or not intent:
        return ''
    summary = str(intent.get('attr_intent_summary') or '').strip()
    notes = intent.get('attr_intent_notes') if isinstance(intent.get('attr_intent_notes'), list) else []
    locked = intent.get('locked_attr_words') if isinstance(intent.get('locked_attr_words'), list) else []
    chunks: List[str] = []
    if summary:
        chunks.append(f'用户改属性意图摘要：{summary}')
    elif notes:
        chunks.append('用户改属性意图：' + '；'.join(str(x) for x in notes[-8:] if x))
    if locked:
        chunks.append(
            '下列词用户已手改并锁定，属性必须以用户结果为准，不可改回：'
            + '、'.join(str(x) for x in locked[:40] if x)
        )
    if not chunks:
        return ''
    return (
        '【用户属性意图跟随】下次标注四色/DMT/三类时，除锁定词必须照用户结果外，'
        '对其它词也要尽量与下列意图/视角一致（学倾向，不是机械复制）：\n'
        + '\n'.join(chunks)
    )


def _intent_full_follow_blurb(intent: Optional[Dict[str, Any]]) -> str:
    """冲突确认/底栏定义/Top 改选/传文档/钉卡等，下次梳理时喂给模型。"""
    if not isinstance(intent, dict) or not intent:
        return ''
    chunks: List[str] = []
    attr = _intent_attr_follow_blurb(intent)
    if attr:
        chunks.append(attr)

    pref_top = intent.get('preferred_top') if isinstance(intent.get('preferred_top'), dict) else {}
    if pref_top:
        chunks.append('用户 Top 偏好（须优先跟随）：' + json.dumps(pref_top, ensure_ascii=False)[:800])
    top_repl = intent.get('top_replacements') if isinstance(intent.get('top_replacements'), list) else []
    if top_repl:
        recent = top_repl[-12:]
        bits = []
        for r in recent:
            if not isinstance(r, dict):
                continue
            bits.append(
                f"{r.get('tier') or ''}:{r.get('old') or ''}→{r.get('new') or ''}"
            )
        if bits:
            chunks.append('用户曾用备选替换过的 Top 词：' + '；'.join(bits))

    core = str(intent.get('preferred_core_issue') or '').strip()
    if core:
        chunks.append(f'用户偏好核心问题：{core}')
    subs = intent.get('preferred_sub_issues') if isinstance(intent.get('preferred_sub_issues'), list) else []
    if intent.get('sub_issues_user_locked'):
        shown = '、'.join(str(x) for x in subs[:12] if str(x).strip()) or '（用户已清空）'
        chunks.append('用户已亲手增删改子问题，下次必须沿用这份清单，不要另起一套：' + shown)
    elif subs:
        chunks.append('用户偏好子问题：' + '、'.join(str(x) for x in subs[:12] if x))
    edits = intent.get('panel_edit_log') if isinstance(intent.get('panel_edit_log'), list) else []
    if edits:
        bits = []
        for ev in edits[-8:]:
            if not isinstance(ev, dict):
                continue
            action = str(ev.get('action') or '').strip()
            target = str(ev.get('target') or '').strip()
            if action or target:
                bits.append(f'{action}{target}'.strip())
        if bits:
            chunks.append('用户对子问题和刻度说明的最近调整：' + '；'.join(bits))

    scale = intent.get('preferred_scale_definitions')
    if isinstance(scale, dict) and scale:
        chunks.append('用户改过的本子刻度定义：' + json.dumps(scale, ensure_ascii=False)[:1200])
    qdefs = intent.get('preferred_quadrant_definitions')
    if isinstance(qdefs, dict) and any(str(qdefs.get(qid) or '').strip() for qid in ('Q1', 'Q2', 'Q3', 'Q4')):
        chunks.append('用户改过的四象限内涵，下次必须原样保留：' + json.dumps(qdefs, ensure_ascii=False)[:1600])

    confs = intent.get('confirmations') if isinstance(intent.get('confirmations'), list) else []
    if confs:
        bits = []
        for c in confs[-15:]:
            if not isinstance(c, dict):
                continue
            w = str(c.get('word') or '').strip()
            applied = c.get('applied') if isinstance(c.get('applied'), dict) else {}
            choice = str(c.get('choice') or applied.get('option_id') or '').strip()
            hk = applied.get('human_know')
            hk_s = '人知' if hk is True else ('人不知' if hk is False else '')
            if w:
                bits.append(f'{w}:{choice or "确认"}{("|" + hk_s) if hk_s else ""}')
        if bits:
            chunks.append('用户冲突/存疑确认记录：' + '；'.join(bits))

    evs = intent.get('behavior_events') if isinstance(intent.get('behavior_events'), list) else []
    if evs:
        bits = []
        for ev in evs[-20:]:
            if not isinstance(ev, dict):
                continue
            typ = str(ev.get('type') or '').strip()
            if typ == 'upload_document':
                bits.append(f"新传文档:{ev.get('filename') or ''}")
            elif typ == 'pin_card':
                tip = str(ev.get('title') or ev.get('cid') or '').strip()
                ask = '含提问' if (ev.get('has_question') or ev.get('has_user_question')) else ''
                bits.append(f"钉卡:{tip}{('|' + ask) if ask else ''}")
            elif typ:
                bits.append(typ)
        if bits:
            chunks.append(
                '用户近期行为（新传文档/钉卡等，梳理时更注意含提问的钉卡）：'
                + '；'.join(bits)
            )

    if not chunks:
        return ''
    return (
        '【用户意图与行为跟随】下列均为用户已给出的偏好/确认/行为，须认真跟随；'
        '未改过的既有词属性尽量保持，仅对明显需要随意图调整的做适量修正：\n'
        + '\n'.join(chunks)
    )


def extract_keywords_for_document(
    username: str,
    bundle: Dict[str, str],
    *,
    notebook_description: str,
    track_fn: Optional[Callable] = None,
    intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    system = (
        '你是本子主体本体语义关键词分析助手。'
        + JSON_OUTPUT_RULES
    )
    follow = _intent_full_follow_blurb(intent)
    prompt = f"""{SOURCE_PRIORITY_BLURB}
{JSON_OUTPUT_RULES}

本子说明：{_clip(notebook_description, 800)}
{follow}

文档文件名：{bundle.get('filename')}

【DocStructure】
{_clip(bundle.get('doc_structure'), 12000)}

【Presummary】
{_clip(summary_text_for_analysis(bundle), 10000)}

【Skill】（弱候选，须重判）
{_clip(bundle.get('skill'), 8000)}

请提取本子主体本体语义关键词（个数以覆盖完整准确为准，不固定）。
对每个词：结合素材本色解释；给出四色(R/B/P/G)、DMT(D/M/T)、三类知识(trad/org/trib，含义对齐显性/半隐/隐性)。
禁止四色混杂补洞。doubts 仅写具体疑问/冲突点；没有则空数组。
若有用户历史属性改选意图，对新词/未锁定词的属性判断应尽量与这些意图视角一致（不是照搬旧词，而是学其倾向）。
严格按此结构输出（字段名不可改）：
{{
  "keywords": [
    {{
      "word": "短词",
      "analysis": "本色解释",
      "four_color_type": "R",
      "dmt_level": "T",
      "knowledge_type": "trad",
      "doubts": []
    }}
  ]
}}
"""
    raw, model = call_strong_llm(prompt, system=system, track_fn=track_fn)
    safe_fn = re.sub(r'[^\w\u4e00-\u9fff]+', '_', bundle.get('filename') or 'doc')[:80]
    debug_path = os.path.join(v3_debug_dir(username), f'extract_{safe_fn}.txt')
    try:
        with open(debug_path, 'w', encoding='utf-8') as f:
            f.write(raw)
    except Exception:
        pass
    data = loads_json_loose(raw)
    if not isinstance(data, dict):
        data = {'keywords': data if isinstance(data, list) else []}
    kws = data.get('keywords') or []
    cleaned = []
    for item in kws:
        if not isinstance(item, dict):
            continue
        word = str(item.get('word') or item.get('keyword') or '').strip()
        if not word or len(word) > 40:
            continue
        cleaned.append({
            'word': word,
            'analysis': str(item.get('analysis') or '').strip(),
            'four_color_type': str(item.get('four_color_type') or '').strip().upper()[:1],
            'dmt_level': str(item.get('dmt_level') or '').strip().upper()[:1],
            'knowledge_type': str(item.get('knowledge_type') or 'trad').strip().lower(),
            'doubts': item.get('doubts') if isinstance(item.get('doubts'), list) else [],
            'source_file': bundle.get('filename'),
            'model': model,
        })
    return {'filename': bundle.get('filename'), 'keywords': cleaned, 'model': model}


def _stem_filename(fn: str) -> str:
    base = os.path.basename(str(fn or '').strip())
    stem, _ = os.path.splitext(base)
    return stem.strip()


def _notebook_title_blurb(
    notebook_name: str = '',
    scene_name: Optional[str] = None,
    notebook_description: str = '',
) -> str:
    parts = []
    for x in (notebook_name, scene_name):
        s = str(x or '').strip()
        if s and s not in parts:
            parts.append(s)
    desc = str(notebook_description or '').strip()
    if desc:
        parts.append(_clip(desc, 400))
    return ' / '.join(parts) if parts else '（未提供本子名）'


def aggregate_top_and_union(
    per_doc: List[Dict[str, Any]],
    *,
    username: str,
    notebook_description: str,
    intent: Dict[str, Any],
    track_fn: Optional[Callable] = None,
    notebook_name: str = '',
    scene_name: Optional[str] = None,
) -> Dict[str, Any]:
    # 合并同名词：后写覆盖属性但保留来源列表
    union: Dict[str, Dict[str, Any]] = {}
    for block in per_doc:
        for item in block.get('keywords') or []:
            w = item['word']
            prev = union.get(w) or {'sources': [], 'doubts': []}
            sources = list(prev.get('sources') or [])
            if item.get('source_file') and item['source_file'] not in sources:
                sources.append(item['source_file'])
            doubts = list(prev.get('doubts') or []) + list(item.get('doubts') or [])
            entry = dict(item)
            entry['sources'] = sources
            entry['doubts'] = doubts
            union[w] = entry

    pref_top = intent.get('preferred_top') if isinstance(intent.get('preferred_top'), dict) else {}
    follow = _intent_full_follow_blurb(intent)
    source_files = [str(b.get('filename') or '').strip() for b in per_doc if str(b.get('filename') or '').strip()]
    title_blurb = _notebook_title_blurb(notebook_name, scene_name, notebook_description)
    file_stems = [_stem_filename(f) for f in source_files]

    system = '主体本体语义关键词汇总助手。' + JSON_OUTPUT_RULES
    catalog = [{'word': w, **{k: v for k, v in meta.items() if k != 'analysis'}, 'analysis': _clip(meta.get('analysis'), 200)} for w, meta in list(union.items())[:200]]
    prompt = f"""{SOURCE_PRIORITY_BLURB}
{JSON_OUTPUT_RULES}
本子名/场景/说明：{title_blurb}
文档文件名（须用来理解本子目的与各大方面，勿只盯后半迁移词）：{json.dumps(file_stems[:80], ensure_ascii=False)}
用户历史 Top 偏好（若有须优先跟随）：{json.dumps(pref_top, ensure_ascii=False)[:800]}
用户历史核心问题偏好：{json.dumps(intent.get('preferred_core_issue') or '', ensure_ascii=False)[:400]}
用户历史子问题偏好：{json.dumps(intent.get('preferred_sub_issues') or [], ensure_ascii=False)[:800]}
{follow}

候选词（已带属性）：
{json.dumps(catalog, ensure_ascii=False)[:18000]}

请筛选本子 Top1/Top3/Top5/Top10（词必须来自候选，禁止另造权威词；不可是短句）。
另给 core_issue 首选与若干备选；sub_issues 若干。
top_alternatives 的每一档都要给备选短词或复合主体词（非短句）。

目的导向（可泛化，勿写死某一本）：
- 先据本子名与文件名判断本子在比较/迁移/对照哪些大方面；数量接近时视为同级大方面。
- 若存在「先弄清基础域 → 再迁移到应用/洞察域」的语义顺序，Top 与核心问题须两边都有代表，禁止只堆应用侧新词。
- 基础域代表词可略优先于纯迁移口号，但仍须服务本子总目的。

严格结构：
{{
  "top1": ["词"],
  "top3": ["词"],
  "top5": ["词"],
  "top10": ["词"],
  "top_alternatives": {{"top1": ["备选"], "top3": ["备选"], "top5": ["备选"], "top10": ["备选"]}},
  "reasons": {{"top1": "理由", "top3": "理由", "top5": "理由", "top10": "理由"}},
  "core_issue": "首选核心问题一句话",
  "core_issue_alternatives": ["其他可能"],
  "sub_issues": ["子问题"]
}}
"""
    raw, model = call_strong_llm(prompt, system=system, max_tokens=5000, track_fn=track_fn)
    try:
        with open(os.path.join(v3_debug_dir(username), 'aggregate_top.txt'), 'w', encoding='utf-8') as f:
            f.write(raw)
    except Exception:
        pass
    data = loads_json_loose(raw)
    if not isinstance(data, dict):
        data = {}

    def _listify(key, n):
        vals = data.get(key) or []
        if isinstance(vals, str):
            vals = [vals]
        out = []
        for x in vals:
            s = str(x).strip()
            if s and s in union and s not in out:
                out.append(s)
        # 不足时用出现次数多的补
        if len(out) < n:
            ranked = sorted(union.keys(), key=lambda w: (-len(union[w].get('sources') or []), w))
            for w in ranked:
                if w not in out:
                    out.append(w)
                if len(out) >= n:
                    break
        return out[:n]

    top1 = _listify('top1', 1)
    top3 = _listify('top3', 3)
    top5 = _listify('top5', 5)
    top10 = _listify('top10', 10)
    # 应用用户偏好覆盖首选
    if pref_top.get('top1') and pref_top['top1'] in union:
        top1 = [pref_top['top1']]
        if pref_top['top1'] not in top10:
            top10 = [pref_top['top1']] + [x for x in top10 if x != pref_top['top1']]
            top10 = top10[:10]
    for key, n, bucket in (('top3', 3, top3), ('top5', 5, top5), ('top10', 10, top10)):
        pref_list = pref_top.get(key)
        if isinstance(pref_list, list) and pref_list:
            cleaned = [str(x).strip() for x in pref_list if str(x).strip() in union][:n]
            if cleaned:
                if key == 'top3':
                    top3 = cleaned
                elif key == 'top5':
                    top5 = cleaned
                else:
                    top10 = cleaned

    core_issue = str(intent.get('preferred_core_issue') or data.get('core_issue') or '').strip()
    if not core_issue:
        core_issue = str(data.get('core_issue') or '').strip()
    if intent.get('sub_issues_user_locked'):
        raw_subs = intent.get('preferred_sub_issues') if isinstance(intent.get('preferred_sub_issues'), list) else []
        sub_issues = [str(x).strip() for x in raw_subs if str(x).strip()]
    else:
        sub_issues = intent.get('preferred_sub_issues') if isinstance(intent.get('preferred_sub_issues'), list) else None
        if not sub_issues:
            sub_issues = data.get('sub_issues') if isinstance(data.get('sub_issues'), list) else []

    return {
        'union': union,
        'top1': top1,
        'top3': top3,
        'top5': top5,
        'top10': top10,
        'top_alternatives': data.get('top_alternatives') if isinstance(data.get('top_alternatives'), dict) else {},
        'reasons': data.get('reasons') if isinstance(data.get('reasons'), dict) else {},
        'core_issue': core_issue,
        'core_issue_alternatives': data.get('core_issue_alternatives') if isinstance(data.get('core_issue_alternatives'), list) else [],
        'sub_issues': sub_issues,
        'model': model,
    }


def build_scale_definitions(
    *,
    username: str,
    notebook_description: str,
    core_issue: str,
    sub_issues: List[str],
    intent: Dict[str, Any],
    track_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    pref = intent.get('preferred_scale_definitions') if isinstance(intent.get('preferred_scale_definitions'), dict) else {}
    follow = _intent_full_follow_blurb(intent)
    system = '只输出 JSON。' + JSON_OUTPUT_RULES
    prompt = f"""结合本子核心问题与子问题，把本子整体具体化的四色、D/M/T、三类知识含义说清楚（基于通用定义做本子化，勿空话）。
{JSON_OUTPUT_RULES}
本子说明：{_clip(notebook_description, 500)}
核心问题：{core_issue}
子问题：{json.dumps(sub_issues, ensure_ascii=False)[:1200]}
用户历史偏好定义（有则跟随精神；用户改过的条目必须原样保留，只允许补没改过的条目）：{json.dumps(pref, ensure_ascii=False)[:1500]}
{follow}

输出：
{{
  "four_color": {{"R": "...", "B": "...", "P": "...", "G": "..."}},
  "dmt": {{"D": "...", "M": "...", "T": "..."}},
  "knowledge": {{"trad": "传统/显性…", "org": "组织/半隐…", "trib": "部落/隐性…"}},
  "alternatives": {{"four_color": {{}}, "dmt": {{}}, "knowledge": {{}}}}
}}
"""
    raw, model = call_strong_llm(prompt, system=system, max_tokens=3500, track_fn=track_fn)
    try:
        data = loads_json_loose(raw)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if pref:
        # 浅合并用户偏好
        for key in ('four_color', 'dmt', 'knowledge'):
            if isinstance(pref.get(key), dict):
                base = data.get(key) if isinstance(data.get(key), dict) else {}
                base.update({k: v for k, v in pref[key].items() if v})
                data[key] = base
    data['model'] = model
    path = book_scale_definitions_path(username)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def infer_notebook_purpose_skeleton(
    *,
    username: str,
    notebook_name: str,
    scene_name: Optional[str],
    notebook_description: str,
    source_files: List[str],
    top_pack: Dict[str, Any],
    union: Dict[str, Dict[str, Any]],
    track_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """据本子名+文档名推断可泛化的目的骨架：同级大方面、基础→迁移顺序、各柱种子词。"""
    stems = [_stem_filename(f) for f in (source_files or []) if str(f).strip()]
    title_blurb = _notebook_title_blurb(notebook_name, scene_name, notebook_description)
    # 给模型一点词表锚点，避免种子词另造
    anchor_words = sorted(union.keys(), key=lambda w: (-len((union[w] or {}).get('sources') or []), w))[:120]
    system = '本子目的骨架分析助手。只输出 JSON。' + JSON_OUTPUT_RULES
    prompt = f"""{JSON_OUTPUT_RULES}
根据本子名、说明与文档文件名，归纳本子目的骨架（可泛化到任意本子，禁止只服务某一特例）。

本子名/场景/说明：{title_blurb}
文档文件名：{json.dumps(stems[:100], ensure_ascii=False)}
文档份数：{len(stems)}
核心问题：{top_pack.get('core_issue') or ''}
Top10：{json.dumps(top_pack.get('top10') or [], ensure_ascii=False)}
词表锚点（种子词必须尽量选自此表，勿另造）：{json.dumps(anchor_words, ensure_ascii=False)[:6000]}

分析规则：
1) 从本子名与文件名识别 2～4 个「大方面/支柱」pillars；文件名数量接近的主题视为同级大方面。
2) 若语义上存在「先搞清基础域 → 再迁移/对照到应用或洞察域」，则基础域 role=foundation，应用/洞察 role=application，桥接 role=bridge；同级对照用 peer。
3) foundation 在层次上可与 application 同级，但应略优先（先织密基础内部，再桥接迁移）。
4) 每个 pillar 给 4～12 个 seed_terms（必须来自词表锚点），并给 filename_hints（文件名片段即可）。
5) 明确写出若只连应用侧、冷落基础侧会犯的错误。

输出：
{{
  "purpose_one_liner": "本子要做什么",
  "migration_logic": "基础→迁移/对照的一句话；若无迁移则写同级对照",
  "pillars": [
    {{
      "id": "p1",
      "label": "短名",
      "role": "foundation|application|bridge|peer",
      "rank": 1,
      "why": "依据本子名/文件名…",
      "filename_hints": ["文件名片段"],
      "seed_terms": ["词表中的词"]
    }}
  ],
  "link_priorities": ["先…", "再…", "禁止…"]
}}
"""
    raw, model = call_strong_llm(
        prompt, system=system, max_tokens=5000, timeout_s=360.0, track_fn=track_fn,
    )
    try:
        with open(os.path.join(v3_debug_dir(username), 'purpose_skeleton.txt'), 'w', encoding='utf-8') as f:
            f.write(raw or '')
    except Exception:
        pass
    try:
        data = loads_json_loose(raw)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    pillars_in = data.get('pillars') if isinstance(data.get('pillars'), list) else []
    pillars: List[Dict[str, Any]] = []
    for i, p in enumerate(pillars_in[:6]):
        if not isinstance(p, dict):
            continue
        role = str(p.get('role') or 'peer').strip().lower()
        if role not in ('foundation', 'application', 'bridge', 'peer'):
            role = 'peer'
        seeds = []
        for x in (p.get('seed_terms') or []):
            s = str(x).strip()
            if s in union and s not in seeds:
                seeds.append(s)
        hints = [str(x).strip() for x in (p.get('filename_hints') or []) if str(x).strip()]
        label = str(p.get('label') or p.get('id') or f'p{i+1}').strip() or f'p{i+1}'
        try:
            rank = int(p.get('rank') or (i + 1))
        except (TypeError, ValueError):
            rank = i + 1
        pillars.append({
            'id': str(p.get('id') or f'p{i+1}'),
            'label': label,
            'role': role,
            'rank': rank,
            'why': str(p.get('why') or '')[:300],
            'filename_hints': hints[:12],
            'seed_terms': seeds[:12],
        })
    data['pillars'] = pillars
    data['model'] = model
    data['purpose_one_liner'] = str(data.get('purpose_one_liner') or '')[:300]
    data['migration_logic'] = str(data.get('migration_logic') or '')[:400]
    if not isinstance(data.get('link_priorities'), list):
        data['link_priorities'] = []
    return data


def _word_source_stems(meta: Dict[str, Any]) -> List[str]:
    return [_stem_filename(s) for s in (meta.get('sources') or []) if str(s).strip()]


def _pillar_word_buckets(
    union: Dict[str, Dict[str, Any]],
    purpose: Dict[str, Any],
) -> Dict[str, List[str]]:
    """把词粗分到各 pillar：种子命中 > 文件名 hint > 标签子串。"""
    pillars = purpose.get('pillars') if isinstance(purpose.get('pillars'), list) else []
    buckets: Dict[str, List[str]] = {str(p.get('id') or f'p{i}'): [] for i, p in enumerate(pillars)}
    if not pillars:
        return {'all': list(union.keys())}
    seed_owner: Dict[str, str] = {}
    for p in pillars:
        pid = str(p.get('id') or '')
        for s in p.get('seed_terms') or []:
            if s in union:
                seed_owner[s] = pid
    for w, meta in union.items():
        if w in seed_owner:
            buckets[seed_owner[w]].append(w)
            continue
        stems = _word_source_stems(meta)
        stem_blob = ' '.join(stems)
        best_pid = ''
        best_score = 0
        for p in pillars:
            pid = str(p.get('id') or '')
            score = 0
            label = str(p.get('label') or '')
            if label and label in w:
                score += 3
            for h in p.get('filename_hints') or []:
                if h and h in stem_blob:
                    score += 2
            for s in p.get('seed_terms') or []:
                if s and (s in w or w in s):
                    score += 1
            if score > best_score:
                best_score = score
                best_pid = pid
        if best_pid and best_score > 0:
            buckets[best_pid].append(w)
        else:
            # 未归类：暂挂 rank 最小的 foundation/peer，便于后续补线时可见
            prefer = next(
                (str(p.get('id')) for p in sorted(pillars, key=lambda x: int(x.get('rank') or 99))
                 if p.get('role') in ('foundation', 'peer')),
                str(pillars[0].get('id') or 'p1'),
            )
            buckets.setdefault(prefer, []).append(w)
    return buckets


def _balanced_hierarchy_catalog(
    union: Dict[str, Dict[str, Any]],
    top_pack: Dict[str, Any],
    purpose: Dict[str, Any],
    *,
    attr_limit: int = 280,
) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, List[str]]]:
    """均衡抽取各文档源/各支柱词进属性细表；全词名表另给，避免只看见前 180 个。"""
    must: List[str] = []
    for key in ('top1', 'top3', 'top5', 'top10'):
        for w in top_pack.get(key) or []:
            ws = str(w).strip()
            if ws in union and ws not in must:
                must.append(ws)
    for p in purpose.get('pillars') or []:
        if not isinstance(p, dict):
            continue
        for w in p.get('seed_terms') or []:
            if w in union and w not in must:
                must.append(w)

    buckets = _pillar_word_buckets(union, purpose)
    # 按支柱 round-robin，支柱内按来源数排序
    ordered_bucket_ids = []
    pillars = purpose.get('pillars') if isinstance(purpose.get('pillars'), list) else []
    if pillars:
        # foundation/peer 先轮询，再 application/bridge，避免应用侧占满名额
        role_rank = {'foundation': 0, 'peer': 1, 'bridge': 2, 'application': 3}
        pillars_sorted = sorted(
            pillars,
            key=lambda p: (role_rank.get(str(p.get('role')), 9), int(p.get('rank') or 99)),
        )
        ordered_bucket_ids = [str(p.get('id')) for p in pillars_sorted]
    else:
        ordered_bucket_ids = list(buckets.keys())

    per_lists: Dict[str, List[str]] = {}
    for pid in ordered_bucket_ids:
        ws = list(buckets.get(pid) or [])
        ws.sort(key=lambda w: (-len((union.get(w) or {}).get('sources') or []), w))
        per_lists[pid] = ws

    selected: List[str] = []
    selected_set: Set[str] = set()
    for w in must:
        selected.append(w)
        selected_set.add(w)

    idx = 0
    while len(selected) < attr_limit:
        progressed = False
        for pid in ordered_bucket_ids:
            lst = per_lists.get(pid) or []
            if idx < len(lst):
                w = lst[idx]
                if w not in selected_set:
                    selected.append(w)
                    selected_set.add(w)
                    progressed = True
                    if len(selected) >= attr_limit:
                        break
        if not progressed:
            break
        idx += 1

    # 仍不足则按全表补
    if len(selected) < attr_limit:
        for w in sorted(union.keys(), key=lambda x: (-len((union[x] or {}).get('sources') or []), x)):
            if w not in selected_set:
                selected.append(w)
                selected_set.add(w)
            if len(selected) >= attr_limit:
                break

    catalog = [
        {
            'word': w,
            'four_color_type': (union[w] or {}).get('four_color_type'),
            'dmt_level': (union[w] or {}).get('dmt_level'),
            'knowledge_type': (union[w] or {}).get('knowledge_type'),
            'sources': _word_source_stems(union[w] or {})[:3],
        }
        for w in selected
        if w in union
    ]
    all_words = list(union.keys())
    return all_words, catalog, buckets


def _parse_hierarchy_links(raw_links: Any, union: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    links: List[Tuple[str, str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for item in raw_links or []:
        if not isinstance(item, dict):
            continue
        a = str(item.get('parent') or item.get('a') or '').strip()
        b = str(item.get('child') or item.get('b') or '').strip()
        s = str(item.get('strength') or '普通').strip() or '普通'
        if s not in ('强', '强中', '普通'):
            s = '普通'
        if a in union and b in union and a != b and (a, b) not in seen and (b, a) not in seen:
            seen.add((a, b))
            links.append((a, b, s))
    return links


def _link_degree(links: List[Tuple[str, str, str]]) -> Dict[str, int]:
    deg: Dict[str, int] = defaultdict(int)
    for a, b, _ in links:
        deg[a] += 1
        deg[b] += 1
    return deg


_STRENGTH_RANK = {'强': 3, '强中': 2, '普通': 1}
# 模型输出已可读则可跳过重刷：略宽于目标 20/35/45
_ACCEPT_STRONG_RATIO = (0.08, 0.35)
_ACCEPT_MID_RATIO = (0.18, 0.55)
_ACCEPT_NORMAL_RATIO = (0.28, 0.70)
_ACCEPT_STRONG_PER_NODE = 6


def _norm_link_strength(s: Any) -> str:
    t = str(s or '').strip() or '普通'
    return t if t in _STRENGTH_RANK else '普通'


def _hierarchy_links_already_readable(
    links: List[Tuple[str, str, str]],
    *,
    max_degree: int = 8,
    strong_per_node: int = _ACCEPT_STRONG_PER_NODE,
) -> bool:
    """比例、枢纽「强」条数、节点度数都在可接受范围 → 不必后处理。"""
    if not links:
        return True
    n = len(links)
    counts = {'强': 0, '强中': 0, '普通': 0}
    deg: Dict[str, int] = defaultdict(int)
    strong_deg: Dict[str, int] = defaultdict(int)
    for a, b, s in links:
        s = _norm_link_strength(s)
        counts[s] = counts.get(s, 0) + 1
        if a:
            deg[a] += 1
        if b:
            deg[b] += 1
        if s == '强':
            if a:
                strong_deg[a] += 1
            if b:
                strong_deg[b] += 1
    r_strong = counts['强'] / n
    r_mid = counts['强中'] / n
    r_normal = counts['普通'] / n
    if not (_ACCEPT_STRONG_RATIO[0] <= r_strong <= _ACCEPT_STRONG_RATIO[1]):
        return False
    if not (_ACCEPT_MID_RATIO[0] <= r_mid <= _ACCEPT_MID_RATIO[1]):
        return False
    if not (_ACCEPT_NORMAL_RATIO[0] <= r_normal <= _ACCEPT_NORMAL_RATIO[1]):
        return False
    if strong_deg and max(strong_deg.values()) > strong_per_node:
        return False
    if deg and max(deg.values()) > max_degree:
        return False
    return True


def _level_rank(lv: Any) -> int:
    m = re.search(r'L\s*([0-9]+)', str(lv or ''), re.I)
    return int(m.group(1)) if m else 99


def refine_hierarchy_links(
    links: List[Tuple[str, str, str]],
    levels: Optional[Dict[str, str]] = None,
    *,
    max_degree: int = 8,
    strong_ratio: float = 0.20,
    mid_ratio: float = 0.35,
) -> List[Tuple[str, str, str]]:
    """压缩星型过密边 + 重标定强/强中/普通比例，使图可读。

    模型输出已在可接受范围（比例、单点「强」条数、度数）则原样返回，不重刷。
    否则：出边上限优先保跨层/原高强度边；强度配额约 强20% / 强中35% / 普通45%。
    """
    if not links:
        return []
    if _hierarchy_links_already_readable(links, max_degree=max_degree):
        return [(a, b, _norm_link_strength(s)) for a, b, s in links]
    levels = levels or {}

    def edge_score(a: str, b: str, s: str) -> float:
        la, lb = _level_rank(levels.get(a)), _level_rank(levels.get(b))
        span = abs(la - lb)
        # 跨层主干分更高；同层略降
        return _STRENGTH_RANK.get(s, 1) * 10 + span * 3 + (2 if min(la, lb) <= 1 else 0)

    # 去重（无向）
    best: Dict[Tuple[str, str], Tuple[str, str, str, float]] = {}
    for a, b, s in links:
        if not a or not b or a == b:
            continue
        key = (a, b) if a < b else (b, a)
        sc = edge_score(a, b, s)
        prev = best.get(key)
        if prev is None or sc > prev[3]:
            # 保留原方向（a->b 若 a 层级更高/更中心则更像 parent）
            if _level_rank(levels.get(a)) <= _level_rank(levels.get(b)):
                best[key] = (a, b, s, sc)
            else:
                best[key] = (b, a, s, sc)

    scored = sorted(best.values(), key=lambda x: -x[3])

    # 度上限裁剪：先保骨架分高的边；若某点将被孤立则强行保留其最高分边
    kept: List[Tuple[str, str, str, float]] = []
    deg: Dict[str, int] = defaultdict(int)
    covered: Set[str] = set()
    pending = list(scored)
    for a, b, s, sc in pending:
        if deg[a] >= max_degree or deg[b] >= max_degree:
            continue
        kept.append((a, b, s, sc))
        deg[a] += 1
        deg[b] += 1
        covered.add(a)
        covered.add(b)

    all_nodes = {a for a, b, _, _ in scored} | {b for a, b, _, _ in scored}
    orphans = [w for w in all_nodes if w not in covered]
    if orphans:
        by_node: Dict[str, List[Tuple[str, str, str, float]]] = defaultdict(list)
        for item in scored:
            a, b, s, sc = item
            by_node[a].append(item)
            by_node[b].append(item)
        kept_keys = {(a, b) if a < b else (b, a) for a, b, _, _ in kept}
        for w in orphans:
            cands = sorted(by_node.get(w) or [], key=lambda x: -x[3])
            for a, b, s, sc in cands:
                key = (a, b) if a < b else (b, a)
                if key in kept_keys:
                    continue
                # 允许对端略超上限 +1，以救孤立
                if deg[a] > max_degree + 1 or deg[b] > max_degree + 1:
                    continue
                kept.append((a, b, s, sc))
                kept_keys.add(key)
                deg[a] += 1
                deg[b] += 1
                covered.add(a)
                covered.add(b)
                break

    # 强度重标定
    kept_sorted = sorted(kept, key=lambda x: -x[3])
    n = len(kept_sorted)
    n_strong = max(1, int(round(n * strong_ratio))) if n else 0
    n_mid = max(0, int(round(n * mid_ratio))) if n else 0
    # 单点「强」边上限，避免枢纽全粗
    strong_cap_per_node = 3
    strong_deg: Dict[str, int] = defaultdict(int)
    out: List[Tuple[str, str, str]] = []
    strong_left = n_strong
    mid_left = n_mid
    for a, b, _s, _sc in kept_sorted:
        if strong_left > 0 and strong_deg[a] < strong_cap_per_node and strong_deg[b] < strong_cap_per_node:
            out.append((a, b, '强'))
            strong_deg[a] += 1
            strong_deg[b] += 1
            strong_left -= 1
        elif mid_left > 0:
            out.append((a, b, '强中'))
            mid_left -= 1
        else:
            out.append((a, b, '普通'))
    return out


def _fill_underlinked_foundation_links(
    *,
    username: str,
    union: Dict[str, Dict[str, Any]],
    purpose: Dict[str, Any],
    buckets: Dict[str, List[str]],
    levels: Dict[str, str],
    links: List[Tuple[str, str, str]],
    track_fn: Optional[Callable] = None,
) -> Tuple[List[Tuple[str, str, str]], str]:
    """若基础/同级支柱连通明显弱于应用侧，再补一轮只织该侧内部+桥接边。"""
    pillars = purpose.get('pillars') if isinstance(purpose.get('pillars'), list) else []
    if not pillars:
        return links, ''
    deg = _link_degree(links)
    stats = []
    for p in pillars:
        pid = str(p.get('id') or '')
        ws = [w for w in (buckets.get(pid) or []) if w in union]
        if not ws:
            continue
        linked_n = sum(1 for w in ws if deg.get(w, 0) > 0)
        stats.append({
            'id': pid,
            'label': p.get('label'),
            'role': p.get('role'),
            'total': len(ws),
            'linked': linked_n,
            'ratio': linked_n / max(1, len(ws)),
            'seeds': [s for s in (p.get('seed_terms') or []) if s in union][:8],
        })
    if not stats:
        return links, ''

    app_ratios = [s['ratio'] for s in stats if s['role'] == 'application'] or [0.0]
    app_avg = sum(app_ratios) / max(1, len(app_ratios))
    weak = [
        s for s in stats
        if s['role'] in ('foundation', 'peer') and (s['ratio'] < 0.28 or s['ratio'] + 0.15 < app_avg)
    ]
    if not weak:
        return links, ''

    focus_words: List[str] = []
    focus_set: Set[str] = set()
    for s in weak:
        # 种子 + 未连上的词优先
        for w in s['seeds']:
            if w not in focus_set:
                focus_words.append(w)
                focus_set.add(w)
        ws = buckets.get(s['id']) or []
        orphans = [w for w in ws if deg.get(w, 0) == 0]
        linked = [w for w in ws if deg.get(w, 0) > 0]
        for w in orphans[:40] + linked[:12]:
            if w not in focus_set:
                focus_words.append(w)
                focus_set.add(w)
    # 桥接到应用侧少量 hub，避免又变成只补应用
    for p in pillars:
        if p.get('role') != 'application':
            continue
        for w in (p.get('seed_terms') or [])[:4]:
            if w in union and w not in focus_set:
                focus_words.append(w)
                focus_set.add(w)

    if len(focus_words) < 8:
        return links, ''

    system = '只输出 JSON。补全层次关联边。' + JSON_OUTPUT_RULES
    prompt = f"""{JSON_OUTPUT_RULES}
本子目的：{purpose.get('purpose_one_liner') or ''}
迁移逻辑：{purpose.get('migration_logic') or ''}
弱连通支柱（必须优先织密其内部）：{json.dumps(weak, ensure_ascii=False)[:2000]}
已有部分边，请主要补充这些词之间的 parent->child 边（强/强中/普通）。
要求：
1) 先把 foundation/peer 内部构件、机制、层级连起来；
2) 再给少量基础→应用桥接边；
3) 禁止只在应用侧互连；
4) 词必须来自下列词表；
5) 新增边以普通/强中为主，「强」少用；单点邻居尽量 ≤6，同一词「强」边尽量 ≤3。

词：{json.dumps([{'word': w, 'L': levels.get(w, 'L2')} for w in focus_words[:120]], ensure_ascii=False)}

输出：{{"links":[{{"parent":"A","child":"B","strength":"强"}}]}}
"""
    raw, model = call_strong_llm(
        prompt, system=system, max_tokens=12000, timeout_s=480.0, track_fn=track_fn,
    )
    try:
        with open(os.path.join(v3_debug_dir(username), 'hierarchy_fill_links.txt'), 'w', encoding='utf-8') as f:
            f.write(raw or '')
    except Exception:
        pass
    try:
        data = loads_json_loose(raw)
    except Exception:
        data = {}
    extra = _parse_hierarchy_links((data or {}).get('links') if isinstance(data, dict) else [], union)
    if not extra:
        return links, model
    merged = list(links)
    seen = {(a, b) for a, b, _ in merged} | {(b, a) for a, b, _ in merged}
    for a, b, s in extra:
        if (a, b) not in seen and (b, a) not in seen:
            merged.append((a, b, s))
            seen.add((a, b))
    return merged, model


def _promote_foundation_levels(
    levels: Dict[str, str],
    union: Dict[str, Dict[str, Any]],
    top_pack: Dict[str, Any],
    purpose: Dict[str, Any],
) -> None:
    """同级大方面：基础支柱种子可升为 L0/L1，避免只剩应用侧占中心。"""
    for w in top_pack.get('top1') or []:
        if w in union:
            levels[w] = 'L0'
    pillars = purpose.get('pillars') if isinstance(purpose.get('pillars'), list) else []
    l0_now = {w for w, lv in levels.items() if lv == 'L0'}
    for p in sorted(pillars, key=lambda x: int(x.get('rank') or 99)):
        role = p.get('role')
        seeds = [s for s in (p.get('seed_terms') or []) if s in union]
        if not seeds:
            continue
        if role in ('foundation', 'peer'):
            # 至少抬一个种子到 L0（若 L0 未满），其余抬到 L1
            for i, s in enumerate(seeds[:4]):
                cur = levels.get(s, 'L2')
                if i == 0 and len(l0_now) < 5:
                    levels[s] = 'L0'
                    l0_now.add(s)
                elif cur in ('L2', 'L3'):
                    levels[s] = 'L1'
        elif role == 'application':
            # 应用侧保持可见，但不挤掉基础；已有 Top1 即可
            for s in seeds[:2]:
                if levels.get(s, 'L2') in ('L2', 'L3'):
                    levels[s] = 'L1'


def build_hierarchy_with_levels(
    *,
    username: str,
    notebook_description: str,
    union: Dict[str, Dict[str, Any]],
    top_pack: Dict[str, Any],
    track_fn: Optional[Callable] = None,
    notebook_name: str = '',
    scene_name: Optional[str] = None,
    source_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """关联 + 强度 + L：先据本子名/文件名立目的骨架，再均衡覆盖基础与迁移两侧连线。"""
    files = list(source_files or [])
    if not files:
        # 回退：从 union sources 收集
        seen_f: Set[str] = set()
        for meta in union.values():
            for s in meta.get('sources') or []:
                ss = str(s).strip()
                if ss and ss not in seen_f:
                    seen_f.add(ss)
                    files.append(ss)

    purpose = infer_notebook_purpose_skeleton(
        username=username,
        notebook_name=notebook_name,
        scene_name=scene_name,
        notebook_description=notebook_description,
        source_files=files,
        top_pack=top_pack,
        union=union,
        track_fn=track_fn,
    )
    all_words, catalog, buckets = _balanced_hierarchy_catalog(union, top_pack, purpose)
    title_blurb = _notebook_title_blurb(notebook_name, scene_name, notebook_description)
    file_stems = [_stem_filename(f) for f in files]

    system = '主体本体语义关键词层次关联助手。只输出 JSON。' + JSON_OUTPUT_RULES
    prompt = f"""{SOURCE_PRIORITY_BLURB}
{JSON_OUTPUT_RULES}
对本子语义关键词做层次关联分析（L 层级 + parent->child 边 + 强度）。

【本子目的骨架——必须遵守】
本子名/场景/说明：{title_blurb}
文档文件名：{json.dumps(file_stems[:80], ensure_ascii=False)}
目的一句话：{purpose.get('purpose_one_liner') or ''}
迁移/对照逻辑：{purpose.get('migration_logic') or ''}
支柱 pillars：{json.dumps(purpose.get('pillars') or [], ensure_ascii=False)[:5000]}
连线优先级：{json.dumps(purpose.get('link_priorities') or [], ensure_ascii=False)[:1200]}

硬性要求：
1) 每个词一个 L0/L1/L2/L3（文档少可到 L2）；同一词 L 全局唯一。
2) Top1 必须 L0；Top1/3/5/10 都必须在 levels 中。
3) L0 可 1～约 5 个。若存在 foundation 与 application 两个同级大方面：两者都应有 L0 或至少 L0+L1 中心代表；foundation 可略高于/密于 application，但禁止 application 独霸中心、foundation 整片沉到 L2 且无边。
4) 先织密 foundation/peer 内部（构件→机制→层面），再织 bridge，再连到 application；同层可连。
5) 文件名数量接近的主题，连线覆盖也要大致均衡，不能只连后半迁移/洞察词。
6) links 尽量覆盖更多词：目标至少让词表中有实质结构关系的词进网；禁止只给 Top 附近十几条边。
7) 强度只用：强 / 强中 / 普通。DMT 仅作布局导向（越中心越偏 T）。
8) 强度比例务必拉开，尽量贴近：强约20% / 强中约35% / 普通约45%（宜落在 强18～22、强中32～38、普通40～50）。「强」只给主干父子骨架，同层旁支与弱相关一律普通。禁止大半边都标「强」。
9) 单节点直接邻居建议 ≤6：优先清晰主干，不要星型狂连。
10) 同一词标「强」的边建议 ≤3，其余用强中/普通。

Top1={top_pack.get('top1')} Top3={top_pack.get('top3')} Top10={top_pack.get('top10')}
核心问题：{top_pack.get('core_issue')}

全词名表（levels 必须尽量覆盖下列全部词；未细列属性的也要给 L）：
{json.dumps(all_words, ensure_ascii=False)[:12000]}

细属性词（优先在这些词上给出充分 links）：
{json.dumps(catalog, ensure_ascii=False)[:16000]}

输出：
{{
  "levels": {{"词": "L0"}},
  "links": [{{"parent":"A","child":"B","strength":"普通"}}],
  "max_level": "L2",
  "coverage_notes": "简述如何保证基础侧与迁移侧都有层次连线"
}}
"""
    # 步7全量输出可能很长（中转实测可达 2万+ completion tokens、数分钟），先加长超时与 max_tokens 看完整结果
    raw, model = call_strong_llm(
        prompt, system=system, max_tokens=32000, timeout_s=720.0, track_fn=track_fn,
    )
    try:
        with open(os.path.join(v3_debug_dir(username), 'hierarchy_levels.txt'), 'w', encoding='utf-8') as f:
            f.write(raw or '')
    except Exception:
        pass
    try:
        data = loads_json_loose(raw)
    except Exception as exc:
        print(f'[semantic_v3] hierarchy parse fail: {exc}; retry same full prompt', flush=True)
        # 暂不压缩词表：同提示再试一轮（更长等待），便于对照中转站完整输出是否合理
        raw2, model2 = call_strong_llm(
            prompt, system=system, max_tokens=32000, timeout_s=900.0, track_fn=track_fn,
        )
        model = model2 or model
        try:
            with open(os.path.join(v3_debug_dir(username), 'hierarchy_levels_retry.txt'), 'w', encoding='utf-8') as f:
                f.write(raw2 or '')
        except Exception:
            pass
        try:
            data = loads_json_loose(raw2)
        except Exception as exc2:
            print(f'[semantic_v3] hierarchy retry parse fail: {exc2}', flush=True)
            data = {}
    if not isinstance(data, dict):
        data = {}
    levels_raw = data.get('levels') if isinstance(data.get('levels'), dict) else {}
    levels: Dict[str, str] = {}
    for w, lv in levels_raw.items():
        ws = str(w).strip()
        m = re.search(r'L\s*([0-3])', str(lv), re.I)
        if ws in union and m:
            levels[ws] = f'L{m.group(1)}'
    for w in union:
        levels.setdefault(w, 'L2')
    _promote_foundation_levels(levels, union, top_pack, purpose)

    links = _parse_hierarchy_links(data.get('links'), union)
    links, fill_model = _fill_underlinked_foundation_links(
        username=username,
        union=union,
        purpose=purpose,
        buckets=buckets,
        levels=levels,
        links=links,
        track_fn=track_fn,
    )

    # 无边时：按层级弱连接兜底
    if not links and levels:
        by_lv = defaultdict(list)
        for w, lv in levels.items():
            by_lv[lv].append(w)
        for parent in by_lv.get('L0') or []:
            for child in (by_lv.get('L1') or [])[:12]:
                links.append((parent, child, '强中'))

    # 程序兜底：同支柱内，孤立点挂到该支柱已连 hub 或种子
    deg = _link_degree(links)
    seen = {(a, b) for a, b, _ in links} | {(b, a) for a, b, _ in links}
    for p in purpose.get('pillars') or []:
        if not isinstance(p, dict):
            continue
        if p.get('role') not in ('foundation', 'peer', 'bridge'):
            continue
        pid = str(p.get('id') or '')
        ws = [w for w in (buckets.get(pid) or []) if w in union]
        hubs = [w for w in (p.get('seed_terms') or []) if w in union]
        hubs += sorted([w for w in ws if deg.get(w, 0) > 0], key=lambda x: -deg.get(x, 0))
        if not hubs:
            continue
        hub = hubs[0]
        for w in ws:
            if w == hub or deg.get(w, 0) > 0:
                continue
            # 仅挂来源重叠或种子近邻，避免乱连
            w_src = set(_word_source_stems(union.get(w) or {}))
            h_src = set(_word_source_stems(union.get(hub) or {}))
            close = bool(w_src & h_src) or any(
                (s in w or w in s) for s in (p.get('seed_terms') or []) if s
            )
            if not close and deg.get(w, 0) == 0 and w in (p.get('seed_terms') or []):
                close = True
            if close and (hub, w) not in seen:
                links.append((hub, w, '普通'))
                seen.add((hub, w))
                deg[hub] += 1
                deg[w] += 1

    # 可读性：度上限 + 强/强中/普通比例
    links = refine_hierarchy_links(links, levels, max_degree=8, strong_ratio=0.20, mid_ratio=0.35)
    deg = _link_degree(links)

    _write_book_kw_connect(username, links)
    payload = {
        'levels': levels,
        'max_level': data.get('max_level') or 'L3',
        'model': model,
        'fill_model': fill_model or '',
        'purpose_skeleton': {
            'purpose_one_liner': purpose.get('purpose_one_liner'),
            'migration_logic': purpose.get('migration_logic'),
            'pillars': purpose.get('pillars'),
            'link_priorities': purpose.get('link_priorities'),
        },
        'link_count': len(links),
        'linked_node_count': sum(1 for w in union if deg.get(w, 0) > 0),
    }
    with open(book_levels_path(username), 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return {
        'levels': levels,
        'links': links,
        'model': model,
        'purpose_skeleton': purpose,
        'linked_node_count': payload['linked_node_count'],
    }


def build_longitude_links(
    *,
    username: str,
    union: Dict[str, Dict[str, Any]],
    levels: Dict[str, str],
    track_fn: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    system = '只输出 JSON。'
    prompt = f"""梳理「经度感」同色跨层链：每条链尽量含 L0 的一个 T、L1 的一个 M、（若有 L2）一个 M或D、最外层一个 D，且同四色。
不要刻板画经度线；给出节点序列即可。

词：
{json.dumps([{ 'word': w, 'level': levels.get(w), 'four_color_type': union[w].get('four_color_type'), 'dmt_level': union[w].get('dmt_level')} for w in list(union)[:160]], ensure_ascii=False)}

输出：{{"chains":[{{"color":"R","nodes":["词",...]}}]}}
"""
    raw, model = call_strong_llm(
        prompt, system=system, max_tokens=8000, timeout_s=480.0, track_fn=track_fn,
    )
    try:
        with open(os.path.join(v3_debug_dir(username), 'longitude_chains.txt'), 'w', encoding='utf-8') as f:
            f.write(raw or '')
    except Exception:
        pass
    try:
        data = loads_json_loose(raw)
    except Exception:
        data = {}
    chains = []
    for c in (data.get('chains') if isinstance(data, dict) else None) or []:
        if not isinstance(c, dict):
            continue
        nodes = [str(x).strip() for x in (c.get('nodes') or []) if str(x).strip() in union]
        if len(nodes) >= 2:
            chains.append({'color': str(c.get('color') or '').upper()[:1], 'nodes': nodes, 'model': model})
    with open(book_longitude_links_path(username), 'w', encoding='utf-8') as f:
        json.dump({'chains': chains}, f, ensure_ascii=False, indent=2)
    return chains


def _tokenize_text_match_score(word: str, text: str) -> float:
    if not word or not text:
        return 0.0
    t = text.lower()
    w = word.lower()
    if w in t:
        return 1.0 + min(3.0, t.count(w) * 0.2)
    # 部分字符重叠
    hit = sum(1 for ch in w if ch in t)
    return hit / max(3.0, len(w))


_QUADRANT_GENERIC_TEXT = """四象限的通用含义，和机知、人知的关系：
Q1 共识区：机知且人知。材料里站得住，人这边也清楚。
Q2 盲区：机知且人不知。材料里站得住，人这边没掌握或说不清。
Q3 未知区：机不知且人不知。材料里也没把握，人这边也没掌握。
Q4 隐藏区：机不知且人知。人这边清楚，材料里还没立住。
机知只看材料能不能把这个词立住。人知只看人这边有没有清楚表述。"""


def _guide_word_rows(union: Dict[str, Dict[str, Any]], levels: Dict[str, str]) -> List[Dict[str, Any]]:
    """给四象限内涵调用准备词表。优先保留全部词，释义过长时再缩短。"""
    base: List[Dict[str, Any]] = []
    for word, meta in union.items():
        base.append({
            'word': word,
            'level': levels.get(word) or meta.get('level') or '',
            'four_color_type': meta.get('four_color_type') or '',
            'dmt_level': meta.get('dmt_level') or '',
            'knowledge_type': meta.get('knowledge_type') or '',
            'analysis': str(meta.get('analysis') or ''),
        })
    base.sort(key=lambda row: (_parse_level_num(row.get('level')), _zh_sort_key(str(row.get('word') or ''))))
    rows = base
    for clip in (80, 50, 30, 16, 0):
        rows = []
        for row in base:
            item = dict(row)
            item['analysis'] = _clip(row.get('analysis') or '', clip) if clip else ''
            if not item['analysis']:
                item.pop('analysis', None)
            rows.append(item)
        if len(json.dumps(rows, ensure_ascii=False)) <= 140000:
            break
    return rows


def format_quadrant_guide_for_model(meaning: Dict[str, Any]) -> str:
    """压成一段参考，供机知按文档调用时阅读。"""
    if not isinstance(meaning, dict) or not any((meaning.get('definitions') or {}).values()):
        return ''
    members = meaning.get('members') or {}
    blocks = [_QUADRANT_GENERIC_TEXT, '这个本子的四象限内涵、应放入的词、词数比例：']
    for qid in _QUADRANT_IDS:
        words = [str(word) for word in (members.get(qid) or []) if str(word).strip()]
        shown = words[:80]
        more = f'等 {len(words)} 个' if len(words) > len(shown) else f'{len(words)} 个'
        blocks.append(
            f'{qid} {_QUADRANT_NAMES[qid]}：{(meaning.get("definitions") or {}).get(qid) or ""}'
            f'\n应有的词（{more}）：{"、".join(shown)}'
        )
    proportion = meaning.get('proportion') or {}
    if proportion:
        blocks.append(
            '合适比例：' + json.dumps(
                {'proportion': proportion, 'reason': meaning.get('proportion_reason') or ''},
                ensure_ascii=False,
            )
        )
    return _clip('\n'.join(blocks), 7000)


def build_notebook_quadrant_guide(
    *,
    username: str,
    notebook_description: str,
    notebook_name: str,
    top_pack: Dict[str, Any],
    scale: Dict[str, Any],
    union: Dict[str, Dict[str, Any]],
    levels: Dict[str, str],
    source_files: List[str],
    intent: Optional[Dict[str, Any]] = None,
    track_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """机知、人知之前：用尽量完整的本子上下文，写出四象限应有的词、语义和比例。"""
    rows = _guide_word_rows(union, levels)
    scale_brief = {
        'four_color': (scale or {}).get('four_color') or {},
        'dmt': (scale or {}).get('dmt') or {},
        'knowledge': (scale or {}).get('knowledge') or {},
    }
    stems = [_stem_filename(fn) for fn in source_files if fn]
    pref_defs = {}
    if isinstance(intent, dict) and isinstance(intent.get('preferred_quadrant_definitions'), dict):
        for qid in _QUADRANT_IDS:
            text = str(intent['preferred_quadrant_definitions'].get(qid) or '').strip()
            if text:
                pref_defs[qid] = text
    system = '本子四象限内涵助手。只输出 JSON。' + JSON_OUTPUT_RULES
    prompt = f"""{JSON_OUTPUT_RULES}
你在机知、人知判定之前，给这个本子写四象限。下面的词表是本子里的词，请按本子材料把语义覆盖完整。

{_QUADRANT_GENERIC_TEXT}
不要把上面四句原样交回去。每个象限写成这个本子里应容纳的语义：什么样的词、什么样的内容落在这里。贴着核心问题、文档和词的释义，写法要像本子已有的四色、DMT、三类知识刻度那样具体。

词的归属：
1. words 里只写词表中出现过的词。
2. 每个词只进一个象限。
3. 尽量把词表里的词都归进去。拿不准的词不要硬塞。
4. 归类看语义该落在哪一象限，不要为了凑比例搬词。

比例是这个本子合适的词数范围，不是当前计数。四个下限加起来不要超过 1，四个上限加起来不要小于 1。min_ratio、max_ratio 用 0 到 1 的小数。
用户改过的象限内涵（有则该象限的 meaning 必须原样保留，只补没改过的象限）：{json.dumps(pref_defs, ensure_ascii=False)[:2000]}

本子：{_clip(notebook_name, 80)}
本子说明：{_clip(notebook_description, 1200)}
文档：{json.dumps(stems, ensure_ascii=False)}
核心问题：{top_pack.get('core_issue') or ''}
子问题：{json.dumps(top_pack.get('sub_issues') or [], ensure_ascii=False)}
Top10：{json.dumps(top_pack.get('top10') or [], ensure_ascii=False)}
本子刻度：{json.dumps(scale_brief, ensure_ascii=False)}
词表共 {len(rows)} 个：
{json.dumps(rows, ensure_ascii=False)}

输出：
{{
  "definitions": {{
    "Q1": {{"meaning": "这个本子里共识区应容纳的语义", "words": ["词"]}},
    "Q2": {{"meaning": "这个本子里盲区应容纳的语义", "words": ["词"]}},
    "Q3": {{"meaning": "这个本子里未知区应容纳的语义", "words": ["词"]}},
    "Q4": {{"meaning": "这个本子里隐藏区应容纳的语义", "words": ["词"]}}
  }},
  "proportion": {{
    "Q1": {{"min_ratio": 0.2, "max_ratio": 0.4}},
    "Q2": {{"min_ratio": 0.2, "max_ratio": 0.45}},
    "Q3": {{"min_ratio": 0.1, "max_ratio": 0.3}},
    "Q4": {{"min_ratio": 0.05, "max_ratio": 0.2}},
    "reason": "为什么这个本子是这个范围"
  }}
}}
"""
    meaning = {
        'definitions': {qid: '' for qid in _QUADRANT_IDS},
        'members': {qid: [] for qid in _QUADRANT_IDS},
        'proportion': {},
        'proportion_reason': '',
        'model_definitions': '',
        'model_adjust': '',
        'adjustments': [],
        'catalog_size': len(rows),
    }
    print(f'[semantic_v3] quadrant guide catalog={len(rows)} chars={len(prompt)}', flush=True)
    try:
        raw, model_name = call_strong_llm(
            prompt, system=system, max_tokens=32000, timeout_s=600.0, track_fn=track_fn,
        )
        meaning['model_definitions'] = model_name
        try:
            with open(os.path.join(v3_debug_dir(username), 'quadrant_meaning.txt'), 'w', encoding='utf-8') as f:
                f.write(raw)
        except Exception:
            pass
        parsed = loads_json_loose(raw)
        if isinstance(parsed, dict):
            parsed_meaning = _parse_quadrant_meaning(parsed)
            known = set(union)
            members = {}
            for qid in _QUADRANT_IDS:
                members[qid] = [word for word in (parsed_meaning.get('members') or {}).get(qid) or [] if word in known]
            parsed_meaning['members'] = members
            meaning.update(parsed_meaning)
            meaning['model_definitions'] = model_name
    except Exception as exc:
        print(f'[semantic_v3] quadrant guide fail: {exc}', flush=True)
    if pref_defs:
        defs = meaning.get('definitions') if isinstance(meaning.get('definitions'), dict) else {}
        for qid, text in pref_defs.items():
            defs[qid] = text
        meaning['definitions'] = defs
    placed = sum(len(meaning.get('members', {}).get(qid) or []) for qid in _QUADRANT_IDS)
    print(
        f'[semantic_v3] quadrant guide placed={placed}/{len(union)} '
        f'model={meaning.get("model_definitions") or ""}',
        flush=True,
    )
    try:
        with open(book_quadrant_meaning_path(username), 'w', encoding='utf-8') as f:
            json.dump(meaning, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f'[semantic_v3] quadrant guide write fail: {exc}', flush=True)
    return meaning


def score_machine_knowing(
    username: str,
    union: Dict[str, Dict[str, Any]],
    per_doc: List[Dict[str, Any]],
    *,
    track_fn: Optional[Callable] = None,
    set_job_fn: Optional[Callable] = None,
    quadrant_guide: str = '',
) -> Dict[str, Any]:
    """机知：程序匹配 3:7 卡片机器部 + 模型置信 3322，再 3:7。"""
    # 卡片机器部文本
    card_machine_texts: List[str] = []
    cdir = card_condense_dir(username)
    if os.path.isdir(cdir):
        for name in os.listdir(cdir):
            if not name.endswith('.txt') or name.startswith('book'):
                continue
            path = os.path.join(cdir, name)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw = f.read()
            except Exception:
                continue
            # 去掉人主体标记块
            machine = re.sub(
                r'\[\[HUMAN_SUBJECT_START\]\].*?\[\[HUMAN_SUBJECT_END\]\]',
                ' ',
                raw,
                flags=re.S,
            )
            card_machine_texts.append(machine)

    doc_texts: Dict[str, str] = {}
    for block in per_doc:
        fn = block.get('filename') or ''
        b = load_doc_source_bundle(username, fn)
        # C1：文档名也参与程序匹配（优先序最高侧的弱文本证据）
        doc_texts[fn] = '\n'.join([
            fn,
            os.path.splitext(fn)[0],
            b.get('doc_structure') or '',
            summary_text_for_analysis(b),
            b.get('skill') or '',
        ])

    prog_scores: Dict[str, float] = {}
    for w in union:
        ds = sorted((_tokenize_text_match_score(w, txt) for txt in doc_texts.values()), reverse=True)
        cs = sorted((_tokenize_text_match_score(w, txt) for txt in card_machine_texts), reverse=True)
        d3 = sum(ds[:3]) / max(1, min(3, len(ds) or 1)) if ds else 0.0
        c3 = sum(cs[:3]) / max(1, min(3, len(cs) or 1)) if cs else 0.0
        prog_scores[w] = 0.3 * d3 + 0.7 * c3

    # 模型置信：按文档调用（只对源自该文档的词）。一份文档一次，可并发。临时只用 deepseek，提示词不变。
    model_conf: Dict[str, List[float]] = defaultdict(list)
    doubts: Dict[str, List[str]] = defaultdict(list)
    conf_jobs: List[Tuple[str, List[str]]] = []
    for block in per_doc:
        fn = block.get('filename') or ''
        words = [x['word'] for x in block.get('keywords') or [] if x.get('word') in union]
        if words:
            conf_jobs.append((fn, words))

    def _machine_conf_one(fn: str, words: List[str]) -> Tuple[str, Any]:
        b = load_doc_source_bundle(username, fn)
        system = '机知置信评估助手。' + JSON_OUTPUT_RULES
        guide_block = ''
        if quadrant_guide:
            guide_block = f"""
本子四象限参考。判断仍以这一份文档的材料为准：材料里把词立住了，置信可以高；这一份材料里没有，即使参考把它放在共识区或盲区，置信也要低。
{quadrant_guide}

"""
        prompt = f"""根据下列文档材料，判断你对每个词的含义及其四色、DMT、三类是否有足够把握理解清晰。
{JSON_OUTPUT_RULES}
对每个词先短描述，再给 4 项 0-100 置信：word / four_color / dmt / knowledge。
当描述偏不确定或任一项置信 <70 时，必须在 options 给出 2～4 个给人确认的可选项。
每个 option 必须是对象，字段固定：
- id: 短英文或拼音 id
- label: 给人看的中文选项文案
- human_know: true 表示若人选此项则判为人知道；false 表示人不知道/不确定；null 表示只改属性不直接定人知
- preview: 一句话说明选后将确认/改动什么（词义或属性）
- attr_patch: 可选，如 {{"four_color_type":"R"}} 或 {{"dmt_level":"T"}} 或 {{"knowledge_type":"org"}}
{guide_block}
材料：
文档名:{fn}
DocStructure:{_clip(b.get('doc_structure'), 6000)}
Presummary:{_clip(summary_text_for_analysis(b), 5000)}
Skill:{_clip(b.get('skill'), 4000)}

词：{json.dumps(words[:80], ensure_ascii=False)}

输出：
{{"items":[{{"word":"词","desc":"短描述","scores":{{"word":80,"four_color":70,"dmt":60,"knowledge":50}},"options":[{{"id":"o1","label":"…","human_know":true,"preview":"…","attr_patch":{{}}}}]}}]}}
"""
        raw, _model = call_deepseek_llm(prompt, system=system, max_tokens=5000, track_fn=track_fn)
        data = loads_json_loose(raw)
        try:
            safe_fn = re.sub(r'[^\w\u4e00-\u9fff]+', '_', fn)[:60]
            with open(os.path.join(v3_debug_dir(username), f'machine_conf_{safe_fn}.txt'), 'w', encoding='utf-8') as f:
                f.write(raw)
        except Exception:
            pass
        return fn, data

    conf_by_fn: Dict[str, Any] = {}
    if conf_jobs:
        workers = min(V3_DOC_CONCURRENCY, len(conf_jobs))
        done_n = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fut_map = {pool.submit(_machine_conf_one, fn, words): fn for fn, words in conf_jobs}
            for fut in as_completed(fut_map):
                fn = fut_map[fut]
                done_n += 1
                if set_job_fn:
                    set_job_fn(
                        username,
                        last_action='机知模型置信',
                        last_action_detail=f'{done_n}/{len(conf_jobs)} {fn}',
                    )
                try:
                    got_fn, data = fut.result()
                    conf_by_fn[got_fn] = data
                except Exception as exc:
                    print(f'[semantic_v3] machine conf fail {fn}: {exc}', flush=True)
    for fn, _words in conf_jobs:
        data = conf_by_fn.get(fn)
        for item in (data.get('items') if isinstance(data, dict) else None) or []:
            if not isinstance(item, dict):
                continue
            w = str(item.get('word') or '').strip()
            if w not in union:
                continue
            sc = item.get('scores') if isinstance(item.get('scores'), dict) else {}
            try:
                s = (
                    0.3 * float(sc.get('word') or 0)
                    + 0.3 * float(sc.get('four_color') or 0)
                    + 0.2 * float(sc.get('dmt') or 0)
                    + 0.2 * float(sc.get('knowledge') or 0)
                )
            except (TypeError, ValueError):
                s = 0.0
            model_conf[w].append(s)
            for opt in item.get('options') or []:
                if isinstance(opt, dict) and (opt.get('label') or opt.get('id')):
                    doubts[w].append({
                        'id': str(opt.get('id') or '').strip() or f'opt_{len(doubts[w])+1}',
                        'label': str(opt.get('label') or opt.get('id') or '').strip(),
                        'human_know': opt.get('human_know'),
                        'preview': str(opt.get('preview') or '').strip(),
                        'attr_patch': opt.get('attr_patch') if isinstance(opt.get('attr_patch'), dict) else {},
                        'kind': 'attr_or_meaning',
                    })
                elif opt:
                    doubts[w].append({
                        'id': f'text_{len(doubts[w])+1}',
                        'label': str(opt).strip(),
                        'human_know': None,
                        'preview': str(opt).strip(),
                        'attr_patch': {},
                        'kind': 'attr_or_meaning',
                    })

    # 归一化 + 3:7
    def _norm(d: Dict[str, float]) -> Dict[str, float]:
        if not d:
            return {}
        vals = list(d.values())
        lo, hi = min(vals), max(vals)
        if hi <= lo:
            return {k: 0.5 for k in d}
        return {k: (v - lo) / (hi - lo) for k, v in d.items()}

    mc_avg = {w: (sum(v) / len(v) if v else 0.0) for w, v in model_conf.items()}
    for w in union:
        mc_avg.setdefault(w, 0.0)
    np_ = _norm(prog_scores)
    nm = _norm(mc_avg)
    final = {w: 0.3 * np_.get(w, 0) + 0.7 * nm.get(w, 0) for w in union}

    scores_sorted = sorted(final.values())
    # 阈值：约中位偏下，本子固定写入
    thr = scores_sorted[len(scores_sorted) // 3] if scores_sorted else 0.4
    machine_know = {w: final[w] >= thr for w in union}

    return {
        'program_scores': prog_scores,
        'model_scores': mc_avg,
        'final_scores': final,
        'threshold': thr,
        'machine_know': machine_know,
        'doubts': {k: v for k, v in doubts.items() if v},
    }


PENDING_DASHED_CAP = 20  # 图上虚线框待确认上限


_HUMAN_UNCERTAIN_MARKERS = (
    '不确定', '不知道', '不太懂', '不太清楚', '不理解', '疑惑', '疑问',
    '搞不清', '没搞懂', '请问', '？', '?',
)


def _human_word_stance_in_block(blk: str, word: str) -> Optional[str]:
    """
    按词细判：只看该词附近窗口是否带不确定标记。
    返回 'neg' | 'pos' | None(未提及)。
    """
    if not blk or not word:
        return None
    positions: List[int] = []
    start = 0
    while True:
        i = blk.find(word, start)
        if i < 0:
            break
        positions.append(i)
        start = i + max(1, len(word))
    low = blk.lower()
    wlow = word.lower()
    if wlow != word:
        start = 0
        while True:
            i = low.find(wlow, start)
            if i < 0:
                break
            positions.append(i)
            start = i + max(1, len(wlow))
    if not positions:
        return None
    win = max(18, min(48, len(word) * 6))
    saw_neg = False
    for i in positions:
        left = max(0, i - win)
        right = min(len(blk), i + len(word) + win)
        window = blk[left:right]
        if any(m in window for m in _HUMAN_UNCERTAIN_MARKERS):
            saw_neg = True
            break
    return 'neg' if saw_neg else 'pos'


def score_human_knowing(username: str, union: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """从 cardCondense 人主体标记推断人知；①②直接判，③④需确认（非全词虚线）。"""
    human_know: Dict[str, Optional[bool]] = {w: None for w in union}
    need_confirm: Set[str] = set()
    confirm_mode: Dict[str, str] = {}  # verify | direct
    bucket: Dict[str, str] = {}  # known|unknown|unmentioned|conflict
    evidence: Dict[str, List[str]] = defaultdict(list)

    cdir = card_condense_dir(username)
    pos_hits: Dict[str, int] = defaultdict(int)
    neg_hits: Dict[str, int] = defaultdict(int)
    mentioned: Set[str] = set()
    has_any_human_block = False

    if os.path.isdir(cdir):
        for name in os.listdir(cdir):
            if not name.endswith('.txt') or name.startswith('book'):
                continue
            path = os.path.join(cdir, name)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw = f.read()
            except Exception:
                continue
            blocks = re.findall(
                r'\[\[HUMAN_SUBJECT_START\]\](.*?)\[\[HUMAN_SUBJECT_END\]\]',
                raw,
                flags=re.S,
            )
            if not blocks:
                continue
            has_any_human_block = True
            for blk in blocks:
                for w in union:
                    stance = _human_word_stance_in_block(blk, w)
                    if stance is None:
                        continue
                    mentioned.add(w)
                    evidence[w].append(_clip(blk, 120))
                    if stance == 'neg':
                        neg_hits[w] += 1
                    else:
                        pos_hits[w] += 1

    for w in union:
        if not has_any_human_block:
            # 完全无人主体证据：默认「未提及」待确认，但不把全词塞进虚线——由 assign 限流
            bucket[w] = 'unmentioned'
            need_confirm.add(w)
            confirm_mode[w] = 'direct'
            continue
        if w not in mentioned:
            bucket[w] = 'unmentioned'
            need_confirm.add(w)
            confirm_mode[w] = 'direct'
            continue
        if neg_hits[w] > 0 and pos_hits[w] > 0:
            bucket[w] = 'conflict'
            need_confirm.add(w)
            confirm_mode[w] = 'verify'
            continue
        if neg_hits[w] > 0:
            human_know[w] = False
            bucket[w] = 'unknown'
        elif pos_hits[w] > 0:
            human_know[w] = True
            bucket[w] = 'known'
        else:
            bucket[w] = 'unmentioned'
            need_confirm.add(w)
            confirm_mode[w] = 'direct'

    return {
        'human_know': human_know,
        'need_confirm': sorted(need_confirm),
        'confirm_mode': confirm_mode,
        'bucket': bucket,
        'evidence': {k: v[:3] for k, v in evidence.items()},
        'has_any_human_block': has_any_human_block,
    }


def _build_human_confirm_options(machine_know: bool, mode: str) -> List[Dict[str, Any]]:
    """机知→验真知选项；机不知→直问。"""
    if machine_know or mode == 'verify':
        return [
            {
                'id': 'verify_true_know',
                'label': '我能准确说明其含义与关键属性（真知道）',
                'human_know': True,
                'preview': '确认人知道 → 落共识区(机知)或隐藏区(机不知)',
                'attr_patch': {},
                'kind': 'quadrant',
            },
            {
                'id': 'verify_false_know',
                'label': '我说不清/说不准，其实不确定或不知道',
                'human_know': False,
                'preview': '确认人不知道 → 落盲区(机知)或未知区(机不知)',
                'attr_patch': {},
                'kind': 'quadrant',
            },
            {
                'id': 'verify_partial',
                'label': '只知道一部分，关键属性仍模糊',
                'human_know': False,
                'preview': '按人不知道处理，并保留属性可再改',
                'attr_patch': {},
                'kind': 'quadrant',
            },
        ]
    return [
        {
            'id': 'direct_know',
            'label': '我知道这个词（按真实作答）',
            'human_know': True,
            'preview': '机不知+人知 → 隐藏区；默认采信人选',
            'attr_patch': {},
            'kind': 'quadrant',
        },
        {
            'id': 'direct_unknow',
            'label': '我不知道/不确定这个词',
            'human_know': False,
            'preview': '机不知+人不知 → 未知区；默认采信人选',
            'attr_patch': {},
            'kind': 'quadrant',
        },
    ]


def assign_quadrants(
    union: Dict[str, Dict[str, Any]],
    machine: Dict[str, Any],
    human: Dict[str, Any],
) -> Dict[str, Any]:
    """Q1 共识；Q2 盲区；Q3 未知；Q4 隐藏。虚线框 pending 总数封顶 PENDING_DASHED_CAP。"""
    mk = machine.get('machine_know') or {}
    hk = human.get('human_know') or {}
    need = set(human.get('need_confirm') or [])
    modes = human.get('confirm_mode') or {}
    doubts = machine.get('doubts') or {}
    out: Dict[str, Any] = {}

    # 先算全部，再按优先级截断 pending 虚线
    ranked_pending: List[Tuple[float, str]] = []

    for w in union:
        m = bool(mk.get(w))
        h = hk.get(w)
        pending: List[str] = []
        options: List[Dict[str, Any]] = []

        # B 类：抽词 doubts + 机知模型 options
        extract_doubts = union.get(w, {}).get('doubts') or []
        for d in extract_doubts:
            text = str(d).strip()
            if not text:
                continue
            options.append({
                'id': f'extract_{len(options)+1}',
                'label': text,
                'human_know': None,
                'preview': f'确认或消解含义/属性疑问：{text[:80]}',
                'attr_patch': {},
                'kind': 'attr_or_meaning',
            })
        for opt in doubts.get(w) or []:
            if isinstance(opt, dict):
                options.append(opt)
            elif opt:
                options.append({
                    'id': f'm_{len(options)+1}',
                    'label': str(opt),
                    'human_know': None,
                    'preview': str(opt),
                    'attr_patch': {},
                    'kind': 'attr_or_meaning',
                })
        if options:
            pending.append('attr_or_meaning')

        if w in need or h is None:
            pending.append('quadrant')
            mode = modes.get(w) or ('verify' if m else 'direct')
            options = _build_human_confirm_options(m, mode) + options
            if m and h is True:
                quad = 'Q1'
            elif m and (h is False or h is None):
                quad = 'Q2'
            elif (not m) and h is True:
                quad = 'Q4'
                pending.append('human_true_know_uncertain')
            else:
                quad = 'Q3'
        else:
            if h and m:
                quad = 'Q1'
            elif (not h) and m:
                quad = 'Q2'
            elif (not h) and (not m):
                quad = 'Q3'
            else:
                quad = 'Q4'

        score = float((machine.get('final_scores') or {}).get(w) or 0)
        # 优先级：有属性疑问 > 冲突/验真 > 未提及；同分看机知分低优先确认
        pri = 0.0
        if 'attr_or_meaning' in pending:
            pri += 100
        if 'human_true_know_uncertain' in pending or (human.get('bucket') or {}).get(w) == 'conflict':
            pri += 50
        if (human.get('bucket') or {}).get(w) == 'unmentioned':
            pri += 10
        pri += (1.0 - score)
        if pending:
            ranked_pending.append((pri, w))

        out[w] = {
            'quadrant': quad,
            'machine_know': m,
            'human_know': h,
            'pending': pending,
            'pending_options': options,
            'confirm_mode': modes.get(w) or ('verify' if m else 'direct'),
            'machine_score': (machine.get('final_scores') or {}).get(w),
            'human_bucket': (human.get('bucket') or {}).get(w) or '',
        }

    ranked_pending.sort(key=lambda x: -x[0])
    keep = {w for _, w in ranked_pending[:PENDING_DASHED_CAP]}
    for w, entry in out.items():
        if entry.get('pending') and w not in keep:
            # 未进入虚线配额：③未提及默认暂按人不知占位，不虚线；有明确 h 则保留
            if entry.get('human_know') is None:
                m = bool(entry.get('machine_know'))
                entry['human_know'] = False
                entry['quadrant'] = 'Q2' if m else 'Q3'
        entry['pending'] = []
        entry['pending_deferred'] = True
    return out


def _quadrant_choice_options() -> List[Dict[str, Any]]:
    """虚线框给人点的四个象限。点哪一格就落到哪一格。"""
    labels = {
        'Q1': '放到共识：材料立得住，人也清楚',
        'Q2': '放到盲区：材料立得住，人没掌握',
        'Q3': '放到未知：材料没立住，人也没掌握',
        'Q4': '放到隐藏：人清楚，材料还没立住',
    }
    options = []
    for qid in ('Q1', 'Q2', 'Q3', 'Q4'):
        options.append({
            'id': f'quad_{qid}',
            'label': labels[qid],
            'quadrant': qid,
            'human_know': qid in ('Q1', 'Q4'),
            'preview': labels[qid],
            'attr_patch': {},
            'kind': 'quadrant',
        })
    return options


def _chunk_quadrant_bounds(n: int, proportion: Optional[Dict[str, Any]]) -> Dict[str, Tuple[int, int]]:
    """把本子四象限比例换成这一批词允许的个数。上下限按比例取整，并保证加起来能放下这批词。"""
    ids = ('Q1', 'Q2', 'Q3', 'Q4')
    lows: Dict[str, int] = {}
    highs: Dict[str, int] = {}
    for qid in ids:
        band = (proportion or {}).get(qid) if isinstance(proportion, dict) else None
        if not isinstance(band, dict) or band.get('min_ratio') is None or band.get('max_ratio') is None or n <= 0:
            lows[qid] = 0
            highs[qid] = n
            continue
        lo = float(band['min_ratio'])
        hi = float(band['max_ratio'])
        low_n = max(0, int(math.floor(lo * n + 1e-9)))
        high_n = min(n, int(math.ceil(hi * n - 1e-9)))
        if high_n < low_n:
            high_n = low_n
        lows[qid] = low_n
        highs[qid] = high_n
    guard = 0
    while sum(lows.values()) > n and guard < 8:
        qid = max(ids, key=lambda key: lows[key])
        if lows[qid] <= 0:
            break
        lows[qid] -= 1
        guard += 1
    guard = 0
    while sum(highs.values()) < n and guard < 8:
        qid = min(ids, key=lambda key: highs[key])
        if highs[qid] >= n:
            break
        highs[qid] += 1
        guard += 1
    return {qid: (lows[qid], max(lows[qid], highs[qid])) for qid in ids}


def _chunk_bounds_text(bounds: Dict[str, Tuple[int, int]], n: int) -> str:
    bits = [f'{qid} {lo}–{hi} 个' for qid, (lo, hi) in bounds.items()]
    return f'这一批共 {n} 个词。各象限个数必须落在：' + '，'.join(bits) + '。四个数加起来等于这一批的词数。'


def _parsed_doc_items(data: Any, allowed: Set[str]) -> List[Dict[str, Any]]:
    raw_items = None
    if isinstance(data, dict):
        raw_items = data.get('items')
    elif isinstance(data, list):
        raw_items = data
    if not isinstance(raw_items, list):
        return []
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        word = str(item.get('word') or '').strip()
        qid = str(item.get('quadrant') or '').strip().upper()
        if word not in allowed or word in seen or qid not in ('Q1', 'Q2', 'Q3', 'Q4'):
            continue
        seen.add(word)
        out.append(item)
    return out


def _doc_items_in_bounds(items: List[Dict[str, Any]], allowed: Set[str], bounds: Dict[str, Tuple[int, int]]) -> bool:
    if {str(item.get('word') or '').strip() for item in items} != allowed:
        return False
    counts = {qid: 0 for qid in ('Q1', 'Q2', 'Q3', 'Q4')}
    for item in items:
        counts[str(item.get('quadrant') or '').strip().upper()] += 1
    for qid, (lo, hi) in bounds.items():
        if counts.get(qid, 0) < lo or counts.get(qid, 0) > hi:
            return False
    return True


def _running_quadrant_brief(assigned: Dict[str, str]) -> str:
    counts = {qid: 0 for qid in ('Q1', 'Q2', 'Q3', 'Q4')}
    for qid in assigned.values():
        if qid in counts:
            counts[qid] += 1
    total = sum(counts.values())
    if total <= 0:
        return '前面还没有定完象限的词。'
    bits = []
    for qid in ('Q1', 'Q2', 'Q3', 'Q4'):
        n = counts[qid]
        bits.append(f'{qid} {n} 个，占 {round(100.0 * n / total)}%')
    return f'前面已经定完的词共 {total} 个：' + '；'.join(bits)


def _fold_doc_quadrant_votes(
    union: Dict[str, Dict[str, Any]],
    votes: Dict[str, List[str]],
    uncertain_hits: Dict[str, int],
    guide_members: Dict[str, List[str]],
) -> Dict[str, Any]:
    """多篇文档的象限按出现次数取多数；平票留第一次出现的。没进任何文档的词，内涵里点过名的沿用内涵，其余放未知。"""
    member_of: Dict[str, str] = {}
    for qid, words in (guide_members or {}).items():
        if qid not in ('Q1', 'Q2', 'Q3', 'Q4'):
            continue
        for word in words or []:
            text = str(word or '').strip()
            if text and text not in member_of:
                member_of[text] = qid
    out: Dict[str, Any] = {}
    for word in union:
        seq = [qid for qid in (votes.get(word) or []) if qid in ('Q1', 'Q2', 'Q3', 'Q4')]
        source = 'default_unknown'
        quadrant = 'Q3'
        vote_split = False
        uncertain = False
        uncertain_ratio = 0.0
        if seq:
            counts: Dict[str, int] = {}
            for qid in seq:
                counts[qid] = counts.get(qid, 0) + 1
            best = max(counts.values())
            winners = [qid for qid, n in counts.items() if n == best]
            vote_split = len(winners) > 1
            quadrant = seq[0] if vote_split else winners[0]
            hits = int(uncertain_hits.get(word) or 0)
            uncertain_ratio = hits / max(1, len(seq))
            uncertain = vote_split or uncertain_ratio >= 0.5
            source = 'doc_majority'
        elif word in member_of:
            quadrant = member_of[word]
            source = 'guide_member'
        machine_know = quadrant in ('Q1', 'Q2')
        human_know = quadrant in ('Q1', 'Q4')
        out[word] = {
            'quadrant': quadrant,
            'machine_know': machine_know,
            'human_know': human_know,
            'pending': [],
            'pending_options': [],
            'confirm_mode': 'quadrant',
            'machine_score': 0.25 if uncertain or vote_split else 0.8,
            'human_bucket': '',
            'uncertain': uncertain,
            'uncertain_ratio': round(uncertain_ratio, 3),
            'vote_split': vote_split,
            'quadrant_source': source,
            'doc_votes': seq,
        }
    return out


def _cap_dashed_boxes(quadrants: Dict[str, Any]) -> None:
    """图上最多 20 个虚线框。没留下的词保持已定象限，不再改成盲区或未知。"""
    ranked: List[Tuple[float, str]] = []
    for word, entry in quadrants.items():
        if not (entry.get('uncertain') or entry.get('vote_split')):
            continue
        priority = 0.0
        if entry.get('vote_split'):
            priority += 100
        if entry.get('uncertain'):
            priority += 40 + float(entry.get('uncertain_ratio') or 0) * 20
        ranked.append((priority, word))
    ranked.sort(key=lambda item: -item[0])
    keep = {word for _, word in ranked[:PENDING_DASHED_CAP]}
    choices = _quadrant_choice_options()
    for word, entry in quadrants.items():
        if word in keep:
            entry['pending'] = ['quadrant']
            entry['pending_options'] = choices
            entry['pending_deferred'] = False
            entry['pending_faded'] = False
            entry['confirm_mode'] = 'quadrant'
        else:
            was_open = bool(entry.get('uncertain') or entry.get('vote_split'))
            entry['pending'] = []
            entry['pending_options'] = []
            entry['pending_deferred'] = was_open
            entry['pending_faded'] = False


def assign_quadrants_from_documents(
    username: str,
    union: Dict[str, Dict[str, Any]],
    per_doc: List[Dict[str, Any]],
    *,
    quadrant_guide: str = '',
    guide_members: Optional[Dict[str, List[str]]] = None,
    proportion: Optional[Dict[str, Any]] = None,
    track_fn: Optional[Callable] = None,
    set_job_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """第 9 步：一篇文档一次，最多 4 篇同时。各篇按自己的材料和本子四象限定词，互不参照。"""
    jobs: List[Tuple[str, List[str]]] = []
    for block in per_doc:
        fn = str(block.get('filename') or '')
        words = []
        seen_local: Set[str] = set()
        for item in block.get('keywords') or []:
            word = str((item or {}).get('word') or '').strip()
            if word in union and word not in seen_local:
                seen_local.add(word)
                words.append(word)
        if fn and words:
            jobs.append((fn, words))

    votes: Dict[str, List[str]] = defaultdict(list)
    uncertain_hits: Dict[str, int] = defaultdict(int)

    def _apply_items(items: List[Any], allowed: Set[str]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            word = str(item.get('word') or '').strip()
            qid = str(item.get('quadrant') or '').strip().upper()
            if word not in allowed or qid not in ('Q1', 'Q2', 'Q3', 'Q4'):
                continue
            votes[word].append(qid)
            if item.get('uncertain') in (True, 'true', 'True', 1, '1'):
                uncertain_hits[word] += 1

    def _one_doc(fn: str, words: List[str]) -> Tuple[str, List[Tuple[List[Dict[str, Any]], Set[str]]]]:
        bundle = load_doc_source_bundle(username, fn)
        applied: List[Tuple[List[Dict[str, Any]], Set[str]]] = []
        chunks = [words[i:i + 60] for i in range(0, len(words), 60)] or [words]
        for chunk in chunks:
            allowed = set(chunk)
            bounds = _chunk_quadrant_bounds(len(chunk), proportion)
            bound_text = _chunk_bounds_text(bounds, len(chunk))
            brief = []
            for word in chunk:
                analysis = _clip((union.get(word) or {}).get('analysis') or '', 40)
                brief.append({'word': word, 'analysis': analysis} if analysis else {'word': word})
            system = '文档四象限判定助手。个数不在给定范围内的回答作废。' + JSON_OUTPUT_RULES
            material = f"""本子四象限内涵：
{quadrant_guide or '（暂无）'}

文档名:{fn}
DocStructure:{_clip(bundle.get('doc_structure'), 5000)}
Presummary:{_clip(summary_text_for_analysis(bundle), 4000)}
Skill:{_clip(bundle.get('skill'), 3000)}

词：{json.dumps(brief, ensure_ascii=False)}
"""
            prompt = f"""给下面这一批词定象限。{bound_text}
{JSON_OUTPUT_RULES}
个数是硬性条件。四个象限的个数只要有一个不在范围内，这一版就作废，不要交。
先给每个象限放满它的下限，用和该象限内涵最贴的词。剩下的词放进还没到上限的象限。某一格超过上限，就把其中最不贴的词挪走。
每个词恰好一条。材料定不了的词可以写 uncertain 为 true，这条仍计入个数。
交卷前按 quadrant 数一遍，确认落在范围内再输出。

{material}
输出：
{{"items":[{{"word":"词","quadrant":"Q1","uncertain":false,"reason":"一句话"}}]}}
"""
            chosen: List[Dict[str, Any]] = []
            chosen_gap = 10 ** 9
            for attempt in (1, 2):
                raw = ''
                data: Any = {}
                try:
                    raw, _model = call_qwen_aliyun_llm(
                        prompt, system=system, max_tokens=8000, track_fn=track_fn,
                    )
                    data = loads_json_loose(raw)
                except Exception as exc:
                    print(f'[semantic_v3] doc quadrant fail {fn} attempt={attempt}: {exc}', flush=True)
                    data = {}
                try:
                    safe_fn = re.sub(r'[^\w\u4e00-\u9fff]+', '_', fn)[:60]
                    with open(os.path.join(v3_debug_dir(username), f'doc_quadrant_{safe_fn}.txt'), 'a', encoding='utf-8') as f:
                        f.write(raw or '')
                        f.write('\n')
                except Exception:
                    pass
                parsed_items = _parsed_doc_items(data, allowed)
                counts = {qid: 0 for qid in ('Q1', 'Q2', 'Q3', 'Q4')}
                for item in parsed_items:
                    counts[str(item.get('quadrant') or '').strip().upper()] += 1
                gap = abs(len(allowed) - len(parsed_items))
                for qid, (lo, hi) in bounds.items():
                    n = counts.get(qid, 0)
                    if n < lo:
                        gap += lo - n
                    elif n > hi:
                        gap += n - hi
                if parsed_items and gap < chosen_gap:
                    chosen = parsed_items
                    chosen_gap = gap
                if _doc_items_in_bounds(parsed_items, allowed, bounds):
                    print(f'[semantic_v3] doc quadrant in range {fn} attempt={attempt} counts={counts}', flush=True)
                    break
                print(
                    f'[semantic_v3] doc quadrant out of range {fn} attempt={attempt} '
                    f'counts={counts} bounds={bounds} got={len(parsed_items)}/{len(allowed)}',
                    flush=True,
                )
                if attempt == 1:
                    prompt = f"""上一版作废。个数是 {json.dumps(counts, ensure_ascii=False)}，共 {len(parsed_items)}/{len(allowed)} 个词，不在范围内。
{bound_text}
请重排这一批。先满足每个象限的下限，再把剩下的词放进还没到上限的象限。不要把多数词留在同一个象限。
每个词恰好一条。交卷前再数一遍个数。
{JSON_OUTPUT_RULES}

{material}
输出：
{{"items":[{{"word":"词","quadrant":"Q1","uncertain":false,"reason":"一句话"}}]}}
"""
            if chosen:
                applied.append((chosen, allowed))
        return fn, applied

    if jobs:
        workers = min(V3_DOC_CONCURRENCY, len(jobs))
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one_doc, fn, words) for fn, words in jobs]
            for fut in as_completed(futures):
                try:
                    fn, applied = fut.result()
                except Exception as exc:
                    print(f'[semantic_v3] doc quadrant worker fail: {exc}', flush=True)
                    continue
                for chosen, allowed in applied:
                    _apply_items(chosen, allowed)
                done += 1
                if set_job_fn:
                    set_job_fn(
                        username,
                        last_action='按文档定象限',
                        last_action_detail=f'{done}/{len(jobs)} {fn}',
                    )

    quadrants = _fold_doc_quadrant_votes(union, votes, uncertain_hits, guide_members or {})
    _cap_dashed_boxes(quadrants)
    machine_know = {word: bool(entry.get('machine_know')) for word, entry in quadrants.items()}
    final_scores = {word: float(entry.get('machine_score') or 0) for word, entry in quadrants.items()}
    print(
        f'[semantic_v3] doc quadrants counts={_quadrant_counts(quadrants)} '
        f'dashed={sum(1 for entry in quadrants.values() if entry.get("pending"))} '
        f'docs={len(jobs)}',
        flush=True,
    )
    return {
        'quadrants': quadrants,
        'machine': {
            'program_scores': {},
            'model_scores': final_scores,
            'final_scores': final_scores,
            'threshold': 0.5,
            'machine_know': machine_know,
            'doubts': {},
        },
    }


_QUADRANT_IDS = ('Q1', 'Q2', 'Q3', 'Q4')
_QUADRANT_NAMES = {
    'Q1': '共识区',
    'Q2': '盲区',
    'Q3': '未知区',
    'Q4': '隐藏区',
}


def _ratio_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    if number < 0.0 or number > 1.0:
        return None
    return round(number, 3)


def _parse_quadrant_meaning(data: Dict[str, Any]) -> Dict[str, Any]:
    """第一次调用：本子四象限内涵 + 比例范围。"""
    definitions: Dict[str, str] = {}
    raw_defs = data.get('definitions') if isinstance(data.get('definitions'), dict) else data
    for qid in _QUADRANT_IDS:
        block = raw_defs.get(qid) if isinstance(raw_defs, dict) else None
        text = ''
        if isinstance(block, dict):
            text = str(block.get('meaning') or block.get('text') or '').strip()
        elif isinstance(block, str):
            text = block.strip()
        definitions[qid] = text
    proportion: Dict[str, Any] = {}
    raw_prop = data.get('proportion') if isinstance(data.get('proportion'), dict) else {}
    for qid in _QUADRANT_IDS:
        block = raw_prop.get(qid) if isinstance(raw_prop.get(qid), dict) else {}
        lo = _ratio_or_none(block.get('min_ratio') if block else raw_prop.get(f'{qid}_min'))
        hi = _ratio_or_none(block.get('max_ratio') if block else raw_prop.get(f'{qid}_max'))
        if lo is None or hi is None or lo > hi:
            continue
        proportion[qid] = {'min_ratio': lo, 'max_ratio': hi}
    reason = str(raw_prop.get('reason') or data.get('proportion_reason') or '').strip()
    members: Dict[str, List[str]] = {qid: [] for qid in _QUADRANT_IDS}
    seen_words: Set[str] = set()
    for qid in _QUADRANT_IDS:
        block = raw_defs.get(qid) if isinstance(raw_defs, dict) else None
        raw_words = block.get('words') if isinstance(block, dict) else None
        if not isinstance(raw_words, list):
            continue
        for item in raw_words:
            word = str(item or '').strip()
            if not word or word in seen_words:
                continue
            seen_words.add(word)
            members[qid].append(word)
    return {
        'definitions': definitions,
        'members': members,
        'proportion': proportion,
        'proportion_reason': reason,
    }


def _quadrant_counts(quadrants: Dict[str, Any]) -> Dict[str, int]:
    counts = {qid: 0 for qid in _QUADRANT_IDS}
    for entry in quadrants.values():
        qid = str((entry or {}).get('quadrant') or '').strip().upper()
        if qid in counts:
            counts[qid] += 1
    return counts


def _word_rows_for_quadrant_revision(
    union: Dict[str, Dict[str, Any]],
    quadrants: Dict[str, Any],
    machine: Dict[str, Any],
    human: Dict[str, Any],
    levels: Dict[str, str],
) -> List[Dict[str, Any]]:
    bucket = human.get('bucket') or {}
    rows: List[Dict[str, Any]] = []
    for word, meta in union.items():
        entry = quadrants.get(word) or {}
        signal = (human.get('human_know') or {}).get(word)
        rows.append({
            'word': word,
            'quadrant': entry.get('quadrant') or '',
            'machine_know': bool((machine.get('machine_know') or {}).get(word)),
            'human_signal': signal if signal in (True, False) else None,
            'human_bucket': bucket.get(word) or '',
            'four_color_type': meta.get('four_color_type') or '',
            'dmt_level': meta.get('dmt_level') or '',
            'knowledge_type': meta.get('knowledge_type') or '',
            'level': levels.get(word) or '',
            'analysis': _clip(meta.get('analysis') or '', 80),
        })
    return rows


def _sample_rows_by_quadrant(rows: List[Dict[str, Any]], limit: int = 8) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {qid: [] for qid in _QUADRANT_IDS}
    for row in rows:
        qid = str(row.get('quadrant') or '')
        if qid in grouped and len(grouped[qid]) < limit:
            grouped[qid].append(row)
    return grouped


def _rebuild_pending_options(
    word: str,
    union: Dict[str, Dict[str, Any]],
    machine: Dict[str, Any],
    human: Dict[str, Any],
) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """按原来的人知缺口和属性疑问重建可点选项，不改已写好的象限。"""
    mk = bool((machine.get('machine_know') or {}).get(word))
    signal = (human.get('human_know') or {}).get(word)
    need = set(human.get('need_confirm') or [])
    mode = (human.get('confirm_mode') or {}).get(word) or ('verify' if mk else 'direct')
    pending: List[str] = []
    options: List[Dict[str, Any]] = []
    for doubt in (union.get(word) or {}).get('doubts') or []:
        text = str(doubt).strip()
        if not text:
            continue
        options.append({
            'id': f'extract_{len(options)+1}',
            'label': text,
            'human_know': None,
            'preview': f'确认或消解含义/属性疑问：{text[:80]}',
            'attr_patch': {},
            'kind': 'attr_or_meaning',
        })
    for opt in (machine.get('doubts') or {}).get(word) or []:
        if isinstance(opt, dict):
            options.append(opt)
        elif opt:
            options.append({
                'id': f'm_{len(options)+1}',
                'label': str(opt),
                'human_know': None,
                'preview': str(opt),
                'attr_patch': {},
                'kind': 'attr_or_meaning',
            })
    if options:
        pending.append('attr_or_meaning')
    if word in need or signal is None:
        pending.append('quadrant')
        options = _build_human_confirm_options(mk, mode) + options
        if (not mk) and signal is True:
            pending.append('human_true_know_uncertain')
    return pending, options, mode


def _rebalance_pending_boxes(
    quadrants: Dict[str, Any],
    union: Dict[str, Dict[str, Any]],
    machine: Dict[str, Any],
    human: Dict[str, Any],
    adjusted: Set[str],
) -> None:
    """修正象限后重排虚线框：仍只留最需要人确认的 20 个，不把其余词打回占位象限。"""
    bucket = human.get('bucket') or {}
    scores = machine.get('final_scores') or {}
    ranked: List[Tuple[float, str]] = []
    rebuilt: Dict[str, Tuple[List[str], List[Dict[str, Any]], str]] = {}
    for word in quadrants:
        pending, options, mode = _rebuild_pending_options(word, union, machine, human)
        rebuilt[word] = (pending, options, mode)
        if not pending:
            continue
        score = float(scores.get(word) or 0)
        priority = 0.0
        if 'attr_or_meaning' in pending:
            priority += 100
        if 'human_true_know_uncertain' in pending or bucket.get(word) == 'conflict':
            priority += 50
        if bucket.get(word) == 'unmentioned':
            priority += 10
        if word in adjusted and word in set(human.get('need_confirm') or []):
            priority += 15
        priority += (1.0 - score)
        ranked.append((priority, word))
    ranked.sort(key=lambda item: -item[0])
    keep = {word for _, word in ranked[:PENDING_DASHED_CAP]}
    signals = human.get('human_know') or {}
    for word, entry in quadrants.items():
        pending, options, mode = rebuilt.get(word) or ([], [], '')
        entry['pending_options'] = options
        entry['confirm_mode'] = mode or entry.get('confirm_mode') or ''
        signal = signals.get(word)
        entry['human_know'] = signal if signal in (True, False) else None
        if pending and word in keep:
            entry['pending'] = pending
            entry['pending_deferred'] = False
            entry['pending_faded'] = False
        else:
            entry['pending'] = []
            entry['pending_deferred'] = bool(pending)
            entry['pending_faded'] = False


_V3_DISPLAY_COUNT = 200
_REVISION_CATALOG_TARGET = 360
_REVISION_CATALOG_CHAR_BUDGET = 160000
_LINK_STRENGTH_SCORE = {'强': 3, '强中': 2, '普通': 1}


def _zh_sort_key(text: str) -> str:
    try:
        from pypinyin import lazy_pinyin
        return ''.join(lazy_pinyin(str(text or ''))).lower()
    except Exception:
        return str(text or '')


def _parse_level_num(level: Any) -> int:
    matched = re.match(r'^L?(\d+)$', str(level or '').strip().upper())
    return int(matched.group(1)) if matched else 99


def _hierarchy_adjacency(links: Any) -> Dict[str, List[Dict[str, Any]]]:
    adj: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in links or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        left = str(item[0] or '').strip()
        right = str(item[1] or '').strip()
        if not left or not right or left == right:
            continue
        strength = str(item[2] or '普通').strip() if len(item) >= 3 else '普通'
        score = _LINK_STRENGTH_SCORE.get(strength, 1)
        adj[left].append({'other': right, 'score': score})
        adj[right].append({'other': left, 'score': score})
    for word in adj:
        adj[word].sort(key=lambda item: (-item['score'], _zh_sort_key(item['other'])))
    return adj


def _flatten_top_words(top_pack: Dict[str, Any]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for key in ('top1', 'top3', 'top5', 'top10'):
        raw = (top_pack or {}).get(key)
        values = raw if isinstance(raw, list) else ([raw] if str(raw or '').strip() else [])
        for item in values:
            word = str(item or '').strip()
            if word and word not in seen:
                seen.add(word)
                out.append(word)
    return out


def _v3_overflow_budget(max_count: int) -> int:
    if max_count <= 10:
        return 0
    return {30: 4, 50: 5, 100: 10, 150: 15, 200: 18}.get(int(max_count), 0)


def _append_v3_local_hub_overflow(
    selected: List[str],
    pool: List[str],
    pool_set: Set[str],
    adj: Dict[str, List[Dict[str, Any]]],
    level_of,
    max_count: int,
) -> None:
    budget = _v3_overflow_budget(max_count)
    if not budget:
        return
    selected_set = set(selected)
    state = {'added': 0}

    def degree_of(word: str) -> int:
        return len(adj.get(word) or [])

    def strong_hidden(word: str) -> List[Dict[str, Any]]:
        return [
            item for item in (adj.get(word) or [])
            if item['score'] >= 2 and item['other'] in pool_set and item['other'] not in selected_set
        ]

    def attach_score(word: str) -> int:
        best = 0
        for item in adj.get(word) or []:
            if item['score'] >= 2 and item['other'] in selected_set and level_of(item['other']) <= 1:
                best = max(best, item['score'])
        return best

    def chain_score(word: str) -> int:
        names = [item['other'] for item in strong_hidden(word)]
        name_set = set(names)
        count = 0
        for other in names:
            for item in adj.get(other) or []:
                if item['score'] >= 2 and item['other'] in name_set and str(item['other']) > str(other):
                    count += 1
        return count

    def qualifies(word: str) -> bool:
        if not word or word in selected_set or word not in pool_set or level_of(word) < 2:
            return False
        if degree_of(word) < 8:
            return False
        hidden = strong_hidden(word)
        if attach_score(word) > 0:
            return len(hidden) >= 3
        strong_n = sum(1 for item in hidden if item['score'] >= 3)
        return len(hidden) >= 5 or (len(hidden) >= 4 and strong_n >= 1)

    def add_word(word: str) -> None:
        selected.append(word)
        selected_set.add(word)
        state['added'] += 1

    def take_kids(word: str) -> None:
        hidden = strong_hidden(word)
        hidden_set = {item['other'] for item in hidden}

        def kid_key(item: Dict[str, Any]):
            chained = any(
                other['score'] >= 2 and other['other'] in hidden_set
                for other in (adj.get(item['other']) or [])
            )
            return (-item['score'], 0 if chained else 1, _zh_sort_key(item['other']))

        kids = 0
        for item in sorted(hidden, key=kid_key):
            if state['added'] >= budget or kids >= 6 or item['other'] in selected_set:
                continue
            add_word(item['other'])
            kids += 1

    def pull_hubs(only_attached: bool, sort_key) -> None:
        guard = 0
        while state['added'] < budget and guard < 12:
            guard += 1
            rows = [word for word in pool if qualifies(word) and (not only_attached or attach_score(word) > 0)]
            if not rows:
                break
            rows.sort(key=sort_key)
            hub = rows[0]
            add_word(hub)
            take_kids(hub)

    pull_hubs(True, lambda word: (
        -attach_score(word), -chain_score(word), -len(strong_hidden(word)), -degree_of(word), _zh_sort_key(word),
    ))
    pull_hubs(False, lambda word: (
        -chain_score(word), -len(strong_hidden(word)), -degree_of(word), _zh_sort_key(word),
    ))
    if state['added'] >= budget:
        return
    hanging = [
        word for word in selected
        if level_of(word) >= 2 and degree_of(word) >= 8 and len(strong_hidden(word)) >= 3
    ]
    hanging.sort(key=lambda word: (
        -attach_score(word), -chain_score(word), -len(strong_hidden(word)), -degree_of(word),
    ))
    for word in hanging:
        if state['added'] < budget:
            take_kids(word)


def select_v3_display_words(
    pool: List[str],
    *,
    max_count: int,
    levels: Dict[str, str],
    links: Any,
    top_pack: Dict[str, Any],
    quadrants: Dict[str, Any],
    union: Dict[str, Dict[str, Any]],
    core_issue: str,
) -> List[str]:
    """与界面「显示个数」同一套选词：必显、高层枢纽、救孤立、象限补齐，再加少量溢出。"""
    words = [str(word).strip() for word in pool if str(word or '').strip()]
    if not words or max_count <= 0:
        return []
    pool_set = set(words)
    index = {word: pos for pos, word in enumerate(words)}
    tribal = [
        word for word in words
        if (union.get(word) or {}).get('is_tribal')
        or str((union.get(word) or {}).get('knowledge_type') or '') == 'trib'
    ]
    effective_max = max_count + len(tribal)
    if len(words) <= effective_max:
        return words[:effective_max]
    adj = _hierarchy_adjacency(links)
    forced = [word for word in _flatten_top_words(top_pack) if word in pool_set]
    issue = str(core_issue or '').strip()
    head = issue[:min(6, len(issue))] if issue else ''
    core_related = []
    if issue:
        for word in words:
            if word and (word in issue or (head and head in word)):
                core_related.append(word)

    def level_of(word: str) -> int:
        raw = levels.get(word)
        if raw in (None, ''):
            raw = (union.get(word) or {}).get('level')
        return _parse_level_num(raw)

    def quad_of(word: str) -> str:
        qid = str((quadrants.get(word) or {}).get('quadrant') or '').strip().upper()
        return qid if qid in _QUADRANT_IDS else 'Q3'

    def degree_of(word: str) -> int:
        return len(adj.get(word) or [])

    selected: List[str] = []
    selected_set: Set[str] = set()

    def take(word: str) -> bool:
        if not word or word in selected_set or word not in pool_set or len(selected) >= effective_max:
            return False
        selected_set.add(word)
        selected.append(word)
        return True

    for word in forced:
        take(word)
    for word in tribal:
        take(word)
    for word in core_related:
        take(word)

    hubs = [word for word in words if word not in selected_set and level_of(word) <= 1]
    hubs.sort(key=lambda word: (-degree_of(word), level_of(word), index[word]))
    for hub in hubs:
        if len(selected) >= effective_max:
            break
        take(hub)
        neighbors = [item for item in (adj.get(hub) or []) if item['other'] in pool_set and item['other'] not in selected_set]
        budget = max(2, min(6, (effective_max - len(selected)) // 4))
        for item in neighbors[:budget]:
            take(item['other'])

    skeleton = [word for word in words if word not in selected_set]
    skeleton.sort(key=lambda word: (level_of(word), -degree_of(word), index[word]))
    for word in skeleton:
        if len(selected) >= effective_max:
            break
        take(word)
        for item in adj.get(word) or []:
            if item['other'] in pool_set and item['other'] not in selected_set and len(selected) < effective_max:
                take(item['other'])
                break

    guard = 0
    while len(selected) < effective_max and guard < effective_max * 2:
        guard += 1
        isolates = [
            word for word in selected
            if degree_of(word) > 0 and not any(item['other'] in selected_set for item in (adj.get(word) or []))
        ]
        if not isolates:
            break
        pulled = False
        for word in isolates:
            if len(selected) >= effective_max:
                break
            for item in adj.get(word) or []:
                if item['other'] in pool_set and item['other'] not in selected_set and take(item['other']):
                    pulled = True
                    break
            if pulled:
                break
        if not pulled:
            break

    if len(selected) < effective_max:
        quad_count = {qid: 0 for qid in _QUADRANT_IDS}
        for word in selected:
            quad_count[quad_of(word)] = quad_count.get(quad_of(word), 0) + 1
        rest = [word for word in words if word not in selected_set]
        rest.sort(key=lambda word: (
            quad_count.get(quad_of(word), 0),
            0 if degree_of(word) > 0 else 1,
            level_of(word),
            index[word],
        ))
        for word in rest:
            if len(selected) >= effective_max:
                break
            if take(word):
                qid = quad_of(word)
                quad_count[qid] = quad_count.get(qid, 0) + 1

    shown = selected[:effective_max]
    _append_v3_local_hub_overflow(shown, words, pool_set, adj, level_of, max_count)
    return shown


def _proportion_move_hint(
    counts: Dict[str, int],
    proportion: Dict[str, Any],
    total: int,
) -> Tuple[Dict[str, int], int, int, int]:
    """靠近各象限范围边界需要改动的词数，以及允许的偏少、偏多界限。"""
    edges: Dict[str, int] = {}
    deficit = 0
    surplus = 0
    for qid in _QUADRANT_IDS:
        current = int(counts.get(qid) or 0)
        band = (proportion or {}).get(qid) or {}
        low_ratio = band.get('min_ratio')
        high_ratio = band.get('max_ratio')
        if low_ratio is None or high_ratio is None:
            edges[qid] = current
            continue
        low_n = math.ceil(float(low_ratio) * total - 1e-9)
        high_n = math.floor(float(high_ratio) * total + 1e-9)
        if current < low_n:
            edges[qid] = low_n
            deficit += low_n - current
        elif current > high_n:
            edges[qid] = high_n
            surplus += current - high_n
        else:
            edges[qid] = current
    need = max(deficit, surplus)
    if need <= 0:
        return edges, 0, 0, max(6, total // 30)
    low = max(1, int(round(need * 0.75)))
    high = max(low, int(round(need * 1.35)))
    high = min(high, max(low, int(total * 0.25)))
    return edges, need, low, high


def _revision_catalog_rows(
    rows: List[Dict[str, Any]],
    display_words: List[str],
    counts: Dict[str, int],
    edges: Dict[str, int],
) -> List[Dict[str, Any]]:
    """先放进界面显示个数 200 时会画出的词，再按离期望边界的远近补词。"""
    by_word = {str(row.get('word') or ''): row for row in rows}
    ordered: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def add(word: str) -> None:
        if word in by_word and word not in seen:
            seen.add(word)
            ordered.append(by_word[word])

    for word in display_words:
        add(word)
    display_n = len(ordered)
    target = max(display_n, _REVISION_CATALOG_TARGET)
    if len(rows) <= target:
        for row in rows:
            add(str(row.get('word') or ''))
    else:
        groups: Dict[str, List[Dict[str, Any]]] = {qid: [] for qid in _QUADRANT_IDS}
        groups[''] = []
        for row in rows:
            word = str(row.get('word') or '')
            if word in seen:
                continue
            qid = str(row.get('quadrant') or '')
            groups[qid if qid in groups else ''].append(row)
        for qid in list(groups):
            groups[qid].sort(key=lambda row: (
                _parse_level_num(row.get('level')),
                _zh_sort_key(str(row.get('word') or '')),
            ))
        queue = sorted(
            [qid for qid in groups if groups[qid]],
            key=lambda qid: -abs(int(edges.get(qid) or 0) - int(counts.get(qid) or 0)),
        )
        while len(ordered) < target and queue:
            progressed = False
            for qid in list(queue):
                if len(ordered) >= target:
                    break
                if not groups[qid]:
                    queue.remove(qid)
                    continue
                add(str(groups[qid].pop(0).get('word') or ''))
                progressed = True
            if not progressed:
                break
    while len(ordered) > display_n and len(json.dumps(ordered, ensure_ascii=False)) > _REVISION_CATALOG_CHAR_BUDGET:
        ordered.pop()
    return ordered


def _modest_revision_catalog(
    rows: List[Dict[str, Any]],
    members: Dict[str, Any],
    counts: Dict[str, int],
    edges: Dict[str, int],
    quadrants: Dict[str, Any],
    limit: int = 120,
) -> List[Dict[str, Any]]:
    """小幅修正只看三类：和内涵点名不一致的、第 9 步自己标了拿不准的、比例超出范围那一格里的一部分。"""
    by_word = {str(row.get('word') or ''): row for row in rows}
    member_of: Dict[str, str] = {}
    for qid, words in (members or {}).items():
        if qid not in _QUADRANT_IDS:
            continue
        for word in words or []:
            text = str(word or '').strip()
            if text and text not in member_of:
                member_of[text] = qid
    ordered: List[str] = []
    seen: Set[str] = set()

    def add(word: str) -> None:
        if word in by_word and word not in seen and len(ordered) < limit:
            seen.add(word)
            ordered.append(word)

    for word, qid in member_of.items():
        current = str((quadrants.get(word) or {}).get('quadrant') or '')
        if current and current != qid:
            add(word)
    for word, entry in quadrants.items():
        if entry.get('uncertain') or entry.get('vote_split'):
            add(word)
    overweight = [qid for qid in _QUADRANT_IDS if int(counts.get(qid) or 0) > int(edges.get(qid) or 0)]
    for row in rows:
        if str(row.get('quadrant') or '') in overweight:
            add(str(row.get('word') or ''))
    return [by_word[word] for word in ordered]


def revise_quadrants_by_notebook_meaning(
    *,
    username: str,
    notebook_description: str,
    notebook_name: str,
    top_pack: Dict[str, Any],
    scale: Dict[str, Any],
    union: Dict[str, Dict[str, Any]],
    quadrants: Dict[str, Any],
    machine: Dict[str, Any],
    human: Dict[str, Any],
    levels: Dict[str, str],
    source_files: List[str],
    links: Optional[List[Any]] = None,
    prepared_meaning: Optional[Dict[str, Any]] = None,
    track_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """第 10 步之后：两次强模型调用。先写本子四象限内涵和比例，再按它修正词的象限。"""
    rows = _word_rows_for_quadrant_revision(union, quadrants, machine, human, levels)
    counts = _quadrant_counts(quadrants)
    total = max(1, len(quadrants))
    scale_brief = {
        'four_color': (scale or {}).get('four_color') or {},
        'dmt': (scale or {}).get('dmt') or {},
        'knowledge': (scale or {}).get('knowledge') or {},
    }
    stems = [_stem_filename(fn) for fn in source_files if fn]
    system = '本子四象限内涵助手。只输出 JSON。' + JSON_OUTPUT_RULES
    prompt = f"""{JSON_OUTPUT_RULES}
你在给这个本子写四象限的语义内涵，并给出适合这个本子的词数比例范围。
四象限的通用位置是：
Q1 共识区：材料里站得住，人这边的表述也清楚知道。
Q2 盲区：材料里站得住，人这边没掌握或说不清。
Q3 未知区：材料里也没把握，人这边也没掌握。
Q4 隐藏区：人这边清楚，材料里还没立住。
不要把这四句原样交回去。要写成：在这个本子里，什么样的词、什么样的语义内容应该落在这一象限。写法要像本子已经有的四色、DMT、三类知识刻度那样具体，贴着本子的核心问题和材料，不要空话。

比例范围随本子变化。四个下限加起来不要超过 1，四个上限加起来不要小于 1。min_ratio、max_ratio 用 0 到 1 的小数。
当前初步计数只供你看这个本子现在偏在哪里，不要为了把计数改好看而放宽内涵。

本子：{_clip(notebook_name, 80)}
本子说明：{_clip(notebook_description, 800)}
文档：{json.dumps(stems[:80], ensure_ascii=False)}
核心问题：{top_pack.get('core_issue') or ''}
子问题：{json.dumps(top_pack.get('sub_issues') or [], ensure_ascii=False)[:1500]}
Top10：{json.dumps(top_pack.get('top10') or [], ensure_ascii=False)}
本子刻度：{json.dumps(scale_brief, ensure_ascii=False)[:2500]}
当前词数：{json.dumps(counts, ensure_ascii=False)}，共 {len(quadrants)} 个。
各象限抽样（初步结果，含人证不足的占位）：
{json.dumps(_sample_rows_by_quadrant(rows), ensure_ascii=False)[:12000]}

输出：
{{
  "definitions": {{
    "Q1": {{"meaning": "这个本子里共识区应容纳的语义"}},
    "Q2": {{"meaning": "这个本子里盲区应容纳的语义"}},
    "Q3": {{"meaning": "这个本子里未知区应容纳的语义"}},
    "Q4": {{"meaning": "这个本子里隐藏区应容纳的语义"}}
  }},
  "proportion": {{
    "Q1": {{"min_ratio": 0.2, "max_ratio": 0.45}},
    "Q2": {{"min_ratio": 0.15, "max_ratio": 0.4}},
    "Q3": {{"min_ratio": 0.1, "max_ratio": 0.35}},
    "Q4": {{"min_ratio": 0.05, "max_ratio": 0.25}},
    "reason": "为什么这个本子是这个范围"
  }}
}}
"""
    meaning = {
        'definitions': {qid: '' for qid in _QUADRANT_IDS},
        'members': {qid: [] for qid in _QUADRANT_IDS},
        'proportion': {},
        'proportion_reason': '',
        'model_definitions': '',
        'model_adjust': '',
        'adjustments': [],
    }
    use_prepared = isinstance(prepared_meaning, dict) and any((prepared_meaning.get('definitions') or {}).values())
    try:
        if use_prepared:
            meaning.update({
                'definitions': prepared_meaning.get('definitions') or {},
                'members': prepared_meaning.get('members') or {},
                'proportion': prepared_meaning.get('proportion') or {},
                'proportion_reason': prepared_meaning.get('proportion_reason') or '',
                'model_definitions': prepared_meaning.get('model_definitions') or '',
            })
        else:
            raw, model_name = call_strong_llm(prompt, system=system, max_tokens=4000, track_fn=track_fn)
            meaning['model_definitions'] = model_name
            try:
                with open(os.path.join(v3_debug_dir(username), 'quadrant_meaning.txt'), 'w', encoding='utf-8') as f:
                    f.write(raw)
            except Exception:
                pass
            parsed = loads_json_loose(raw)
            if isinstance(parsed, dict):
                meaning.update(_parse_quadrant_meaning(parsed))
                meaning['model_definitions'] = model_name
    except Exception as exc:
        print(f'[semantic_v3] quadrant meaning fail: {exc}', flush=True)
        return {'quadrants': quadrants, 'meaning': meaning}

    if not any(meaning['definitions'].values()):
        print('[semantic_v3] quadrant meaning empty, skip adjust', flush=True)
        return {'quadrants': quadrants, 'meaning': meaning}

    if links is None:
        try:
            from app_chat.semantic_reorganize_pipeline import load_hierarchy_links_from_file
            links = load_hierarchy_links_from_file(username)
        except Exception:
            links = []
    display_words = select_v3_display_words(
        sorted(union.keys()),
        max_count=_V3_DISPLAY_COUNT,
        levels=levels,
        links=links,
        top_pack=top_pack,
        quadrants=quadrants,
        union=union,
        core_issue=str(top_pack.get('core_issue') or ''),
    )
    edges, _need, _move_low, _move_high = _proportion_move_hint(counts, meaning.get('proportion') or {}, total)
    modest_cap = max(6, min(20, max(6, total // 40)))
    catalog = _modest_revision_catalog(rows, meaning.get('members') or {}, counts, edges, quadrants)
    edge_text = '，'.join(
        f'{qid} 约 {edges.get(qid, counts.get(qid, 0))}（现 {counts.get(qid, 0)}）'
        for qid in _QUADRANT_IDS
    )
    print(
        f'[semantic_v3] quadrant revise catalog={len(catalog)} display200={len(display_words)} '
        f'cap={modest_cap}',
        flush=True,
    )
    adjust_system = '本子四象限修正助手。只输出 JSON。' + JSON_OUTPUT_RULES
    adjust_prompt = f"""{JSON_OUTPUT_RULES}
第 9 步已经按每篇文档的材料定过象限。这次只做小幅修正，不要重做一遍。

规则：
1. 只输出需要改象限的词。不改的词不要写。
2. quadrant 只能是 Q1、Q2、Q3、Q4。
3. reason 写一句话：这个词的语义为什么更符合目标象限在本子里的内涵。
4. 最多改 {modest_cap} 个。语义没有明显放错的词不要为了凑比例搬走。
5. 优先改语义和本子内涵明显不符的词。比例可以顺手靠近，全本大致方向是：{edge_text}。不必改到正好等于这些整数。
6. 词表不是全本。词表里没出现的词保持原象限。

本子内涵：
{json.dumps({'definitions': meaning['definitions'], 'proportion': meaning['proportion'], 'proportion_reason': meaning['proportion_reason']}, ensure_ascii=False)[:6000]}
当前计数：{json.dumps(counts, ensure_ascii=False)} / {total}

词表（quadrant 是第 9 步象限）：
{json.dumps(catalog, ensure_ascii=False)}

输出：
{{"adjustments":[{{"word":"词","quadrant":"Q1","reason":"原因"}}]}}
"""
    try:
        raw, model_name = call_strong_llm(
            adjust_prompt, system=adjust_system, max_tokens=32000, timeout_s=600.0, track_fn=track_fn,
        )
        meaning['model_adjust'] = model_name
        try:
            with open(os.path.join(v3_debug_dir(username), 'quadrant_revise.txt'), 'w', encoding='utf-8') as f:
                f.write(raw)
        except Exception:
            pass
        parsed = loads_json_loose(raw)
    except Exception as exc:
        print(f'[semantic_v3] quadrant revise fail: {exc}', flush=True)
        _cap_dashed_boxes(quadrants)
        try:
            with open(book_quadrant_meaning_path(username), 'w', encoding='utf-8') as f:
                json.dump(meaning, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return {'quadrants': quadrants, 'meaning': meaning}

    items = parsed.get('adjustments') if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        items = []
    applied: List[Dict[str, str]] = []
    adjusted: Set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        word = str(item.get('word') or '').strip()
        target = str(item.get('quadrant') or '').strip().upper()
        reason = str(item.get('reason') or '').strip()
        if word not in quadrants or target not in _QUADRANT_IDS:
            continue
        previous = str(quadrants[word].get('quadrant') or '')
        if previous == target:
            continue
        if len(applied) >= modest_cap:
            break
        quadrants[word]['quadrant_before_meaning'] = previous
        quadrants[word]['quadrant'] = target
        quadrants[word]['machine_know'] = target in ('Q1', 'Q2')
        quadrants[word]['human_know'] = target in ('Q1', 'Q4')
        quadrants[word]['quadrant_revise_reason'] = reason
        adjusted.add(word)
        applied.append({'word': word, 'from': previous, 'quadrant': target, 'reason': reason})
    meaning['adjustments'] = applied
    _cap_dashed_boxes(quadrants)
    print(
        f'[semantic_v3] quadrant revise applied={len(applied)} '
        f'counts={_quadrant_counts(quadrants)} dashed='
        f'{sum(1 for entry in quadrants.values() if entry.get("pending"))}',
        flush=True,
    )
    try:
        with open(book_quadrant_meaning_path(username), 'w', encoding='utf-8') as f:
            json.dump(meaning, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f'[semantic_v3] quadrant meaning write fail: {exc}', flush=True)
    return {'quadrants': quadrants, 'meaning': meaning}


def verify_quadrant_assignments(
    *,
    username: str,
    quadrants: Dict[str, Any],
    meaning: Dict[str, Any],
    union: Dict[str, Dict[str, Any]],
    levels: Dict[str, str],
    machine: Dict[str, Any],
    human: Dict[str, Any],
    track_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """核对：只改语义明显放错的词，不为了比例再搬一轮。"""
    rows = _word_rows_for_quadrant_revision(union, quadrants, machine, human, levels)
    counts = _quadrant_counts(quadrants)
    total = max(1, len(quadrants))
    edges, _need, _low, _high = _proportion_move_hint(counts, meaning.get('proportion') or {}, total)
    catalog = _modest_revision_catalog(
        rows, meaning.get('members') or {}, counts, edges, quadrants, limit=80,
    )
    changed = [
        row for row in rows
        if (quadrants.get(row.get('word') or '') or {}).get('quadrant_revise_reason')
    ][:40]
    system = '本子四象限核对助手。只输出 JSON。' + JSON_OUTPUT_RULES
    prompt = f"""{JSON_OUTPUT_RULES}
下面是这个本子已经定好的四象限。请只核对语义是否明显放错。
没有明显放错就输出空列表。不要为了把比例改好看而搬词。最多指出 8 个词。

本子内涵：
{json.dumps({'definitions': meaning.get('definitions') or {}, 'proportion': meaning.get('proportion') or {}, 'proportion_reason': meaning.get('proportion_reason') or ''}, ensure_ascii=False)[:5000]}
当前计数：{json.dumps(counts, ensure_ascii=False)} / {total}
刚被小幅改过的词：{json.dumps(changed, ensure_ascii=False)[:4000]}

待核对的词（quadrant 是目前象限）：
{json.dumps(catalog, ensure_ascii=False)}

输出：
{{"adjustments":[{{"word":"词","quadrant":"Q1","reason":"为什么现在这一格明显放错"}}]}}
"""
    try:
        raw, model_name = call_strong_llm(
            prompt, system=system, max_tokens=8000, timeout_s=600.0, track_fn=track_fn,
        )
    except Exception as exc:
        print(f'[semantic_v3] quadrant verify fail: {exc}', flush=True)
        _cap_dashed_boxes(quadrants)
        return {'quadrants': quadrants, 'meaning': meaning, 'verified': []}
    try:
        with open(os.path.join(v3_debug_dir(username), 'quadrant_verify.txt'), 'w', encoding='utf-8') as f:
            f.write(raw)
    except Exception:
        pass
    try:
        parsed = loads_json_loose(raw)
    except Exception:
        parsed = {}
    items = parsed.get('adjustments') if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        items = []
    applied: List[Dict[str, str]] = []
    for item in items:
        if len(applied) >= 8:
            break
        if not isinstance(item, dict):
            continue
        word = str(item.get('word') or '').strip()
        target = str(item.get('quadrant') or '').strip().upper()
        reason = str(item.get('reason') or '').strip()
        if word not in quadrants or target not in _QUADRANT_IDS:
            continue
        previous = str(quadrants[word].get('quadrant') or '')
        if previous == target:
            continue
        quadrants[word]['quadrant_before_verify'] = previous
        quadrants[word]['quadrant'] = target
        quadrants[word]['machine_know'] = target in ('Q1', 'Q2')
        quadrants[word]['human_know'] = target in ('Q1', 'Q4')
        quadrants[word]['quadrant_verify_reason'] = reason
        applied.append({'word': word, 'from': previous, 'quadrant': target, 'reason': reason})
    meaning['verify_model'] = model_name
    meaning['verified'] = applied
    _cap_dashed_boxes(quadrants)
    print(
        f'[semantic_v3] quadrant verify applied={len(applied)} '
        f'counts={_quadrant_counts(quadrants)} dashed='
        f'{sum(1 for entry in quadrants.values() if entry.get("pending"))}',
        flush=True,
    )
    try:
        with open(book_quadrant_meaning_path(username), 'w', encoding='utf-8') as f:
            json.dump(meaning, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return {'quadrants': quadrants, 'meaning': meaning, 'verified': applied}


def build_thermometer_spiral(
    *,
    username: str,
    notebook_description: str,
    top_pack: Dict[str, Any],
    quadrants: Dict[str, Any],
    track_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    system = '只输出 JSON。'
    qcounts = defaultdict(int)
    for v in quadrants.values():
        qcounts[v.get('quadrant')] += 1
    prompt = f"""评估本子主体体现与本体完整程度（0-100）并给简短理由；再给螺旋提升成型程度一句话。
左=主体贯穿、人的主体认知水准；右=业务本体思维力完整深入。
本子：{_clip(notebook_description, 400)}
核心问题：{top_pack.get('core_issue')}
Top10：{top_pack.get('top10')}
象限计数：{dict(qcounts)}

输出：{{"subject_score":80,"subject_reason":"...","ontology_score":75,"ontology_reason":"...","spiral":"..."}}
"""
    raw, model = call_strong_llm(prompt, system=system, max_tokens=2000, track_fn=track_fn)
    try:
        data = loads_json_loose(raw)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    # 规则校验上下限约两三成：用象限粗调
    try:
        sub = float(data.get('subject_score') or 50)
        ont = float(data.get('ontology_score') or 50)
    except (TypeError, ValueError):
        sub, ont = 50.0, 50.0
    q1 = qcounts.get('Q1', 0)
    total = max(1, sum(qcounts.values()))
    rule_boost = 100.0 * q1 / total
    sub = max(0, min(100, 0.75 * sub + 0.25 * rule_boost))
    ont = max(0, min(100, 0.75 * ont + 0.25 * (100 - 100.0 * qcounts.get('Q3', 0) / total)))
    data['subject_score'] = round(sub, 1)
    data['ontology_score'] = round(ont, 1)
    data['model'] = model
    with open(book_thermometer_path(username), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def ensure_card_condense_human_markers(
    username: str,
    *,
    limit: int = 60,
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
    set_job_fn: Optional[Callable] = None,
) -> int:
    """复用/补齐 cardCondense；缺文件或无人主体标记时仅重跑浓缩（不抽卡词）。"""
    from app_chat.models import Card
    from app_chat.semantic_reorganize_pipeline import condense_card_content

    cards = list(
        Card.objects.filter(username=username)
        .exclude(content__isnull=True)
        .exclude(content='')
        .order_by('-cid')[: max(1, int(limit))]
    )
    done = 0
    for i, card in enumerate(cards):
        if is_running_fn and not is_running_fn(username):
            break
        path = card_condense_path(username, int(card.cid))
        need = True
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw = f.read()
                # 已有标记或正文较长且卡片无明显提问 → 跳过
                if '[[HUMAN_SUBJECT_START]]' in raw:
                    need = False
                elif len(raw.strip()) >= 40 and not re.search(r'[？?]|请问|不知道|不确定', card.content or ''):
                    need = False
            except Exception:
                need = True
        if not need:
            continue
        if set_job_fn:
            set_job_fn(
                username,
                phase='card_condense',
                last_action='卡片浓缩（人主体标记）',
                last_action_detail=f'cid={card.cid}',
                current_index=i + 1,
                total_cards=len(cards),
            )
        try:
            title = (card.contentTitle or card.title or '')[:200]
            text = condense_card_content(
                card.content or '',
                title,
                username=username,
                cid=int(card.cid),
                track_fn=track_fn,
                is_running_fn=is_running_fn,
            )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text or '')
            done += 1
        except Exception as exc:
            print(f'[semantic_v3] cardCondense fail cid={card.cid}: {exc}', flush=True)
    return done


def run_source_v3_pipeline(
    *,
    username: str,
    scene_name: Optional[str],
    notebook_description: str,
    incremental: bool,
    existing_map: Optional[Dict[str, Dict[str, str]]],
    set_job_fn: Callable,
    track_fn: Callable,
    is_running_fn: Callable,
    force_files: Optional[List[str]] = None,
    notebook_name: str = '',
) -> Dict[str, Any]:
    """执行 v3 源头流水线，返回与 v2 run_full_pipeline 相近结构 + 扩展 meta。"""
    intent = load_intent_memory(username)
    readiness = assess_source_readiness(username)
    if not readiness.get('ok'):
        raise RuntimeError(readiness.get('message') or '源头未就绪')
    # 必须使用全部文档；禁止只分析 ready 子集
    files = list(force_files or readiness.get('files') or [])
    if not files:
        raise RuntimeError('无文档可分析')
    if readiness.get('missing'):
        raise RuntimeError(readiness.get('message') or '仍有文档源头不齐，禁止部分分析')

    set_job_fn(
        username,
        running=True,
        phase='card_condense',
        pipeline=PIPELINE_ID,
        last_action='卡片浓缩（人主体标记）',
        last_action_detail='可跳过已有',
    )
    try:
        n_cd = ensure_card_condense_human_markers(
            username,
            limit=60,
            track_fn=track_fn,
            is_running_fn=is_running_fn,
            set_job_fn=set_job_fn,
        )
        print(f'[semantic_v3] cardCondense refreshed={n_cd}', flush=True)
    except Exception as exc:
        print(f'[semantic_v3] cardCondense phase warn: {exc}', flush=True)

    set_job_fn(
        username,
        running=True,
        phase='source_extract',
        pipeline=PIPELINE_ID,
        last_action='按文档提取关键词与属性',
        last_action_detail=f'共 {len(files)} 份文档',
        total_cards=len(files),
        current_index=0,
    )

    per_doc: List[Dict[str, Any]] = []
    extract_failures: List[Dict[str, str]] = []

    def _extract_one(i: int, fn: str):
        if not is_running_fn(username):
            return i, fn, None, '任务已取消'
        bundle = load_doc_source_bundle(username, fn)
        has_summary = bool(summary_text_for_analysis(bundle).strip())
        has_struct = bool((bundle.get('doc_structure') or bundle.get('skill') or '').strip())
        if not has_summary or not has_struct:
            print(f'[semantic_v3] skip thin source {fn}', flush=True)
            return i, fn, None, '源头不够：没有摘要（Presummary/PreImageSummary），或 DocStructure 与 Skill 都没有'
        last_exc: Optional[BaseException] = None
        # 失败再给 2 次重试（共最多 3 次）
        for attempt in range(1, 4):
            if not is_running_fn(username):
                return i, fn, None, '任务已取消'
            try:
                if attempt > 1:
                    set_job_fn(
                        username,
                        last_action=f'抽词重试 {attempt}/3',
                        last_action_detail=fn,
                    )
                block = extract_keywords_for_document(
                    username,
                    bundle,
                    notebook_description=notebook_description,
                    track_fn=track_fn,
                    intent=intent,
                )
                return i, fn, block, None
            except Exception as exc:
                last_exc = exc
                print(f'[semantic_v3] extract fail {fn} attempt={attempt}: {exc}', flush=True)
                traceback.print_exc()
        return i, fn, None, str(last_exc or '未知错误')[:240]

    extract_results = []
    done_n = 0
    progress_lock = threading.Lock()
    workers = min(V3_DOC_CONCURRENCY, max(1, len(files)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_extract_one, i, fn) for i, fn in enumerate(files)]
        for fut in as_completed(futs):
            item = fut.result()
            extract_results.append(item)
            with progress_lock:
                done_n += 1
                done = done_n
            _i, fn, _block, _err = item
            set_job_fn(
                username,
                current_index=done,
                last_action_detail=fn,
                progress_percent=int(5 + 35 * (done / max(1, len(files)))),
            )
    if any(err == '任务已取消' for _i, _fn, _block, err in extract_results):
        raise RuntimeError('任务已取消')
    for _i, fn, block, err in sorted(extract_results, key=lambda x: x[0]):
        if block is not None:
            per_doc.append(block)
        elif err:
            extract_failures.append({'filename': fn, 'error': err[:240]})

    if extract_failures:
        fail_names = '、'.join(x.get('filename') or '' for x in extract_failures[:8])
        set_job_fn(
            username,
            extract_failures=extract_failures,
            last_action_detail=(
                f'有 {len(extract_failures)} 份抽词失败：{fail_names}'
                + ('…' if len(extract_failures) > 8 else '')
            ),
        )
    if not per_doc:
        detail = '；'.join(
            f"{x.get('filename')}: {x.get('error')}" for x in extract_failures[:5]
        )
        raise RuntimeError('未能从任何文档提取关键词' + (f'（{detail}）' if detail else ''))

    set_job_fn(username, phase='aggregate_top', last_action='汇总 Top 与核心问题', progress_percent=42)
    top_pack = aggregate_top_and_union(
        per_doc,
        username=username,
        notebook_description=notebook_description,
        intent=intent,
        track_fn=track_fn,
        notebook_name=notebook_name,
        scene_name=scene_name,
    )
    union = top_pack['union']
    with open(book_top_keywords_path(username), 'w', encoding='utf-8') as f:
        json.dump({k: top_pack[k] for k in (
            'top1', 'top3', 'top5', 'top10', 'top_alternatives', 'reasons',
            'core_issue', 'core_issue_alternatives', 'sub_issues',
        )}, f, ensure_ascii=False, indent=2)

    # 写核心问题文件
    try:
        with open(book_key_issue_path(username), 'w', encoding='utf-8') as f:
            f.write((top_pack.get('core_issue') or '') + '\n')
            for s in top_pack.get('sub_issues') or []:
                f.write(f'- {s}\n')
    except Exception:
        pass

    set_job_fn(username, phase='scale_definitions', last_action='本子刻度具体化', progress_percent=50)
    scale = build_scale_definitions(
        username=username,
        notebook_description=notebook_description,
        core_issue=top_pack.get('core_issue') or '',
        sub_issues=top_pack.get('sub_issues') or [],
        intent=intent,
        track_fn=track_fn,
    )

    set_job_fn(username, phase='hierarchy_levels', last_action='关联强度与 L 层级', progress_percent=60)
    hier = build_hierarchy_with_levels(
        username=username,
        notebook_description=notebook_description,
        union=union,
        top_pack=top_pack,
        track_fn=track_fn,
        notebook_name=notebook_name or (scene_name or ''),
        scene_name=scene_name,
        source_files=files,
    )

    set_job_fn(username, phase='longitude_links', last_action='同色跨层连线', progress_percent=68)
    chains = build_longitude_links(
        username=username, union=union, levels=hier.get('levels') or {}, track_fn=track_fn,
    )

    set_job_fn(username, phase='quadrant_guide', last_action='本子四象限内涵与比例', progress_percent=74)
    quadrant_guide = build_notebook_quadrant_guide(
        username=username,
        notebook_description=notebook_description,
        notebook_name=notebook_name or (scene_name or ''),
        top_pack=top_pack,
        scale=scale,
        union=union,
        levels=hier.get('levels') or {},
        source_files=files,
        intent=intent,
        track_fn=track_fn,
    )
    guide_text = format_quadrant_guide_for_model(quadrant_guide)

    set_job_fn(username, phase='quadrant_machine', last_action='按文档定象限', progress_percent=78)
    doc_assigned = assign_quadrants_from_documents(
        username,
        union,
        per_doc,
        quadrant_guide=guide_text,
        guide_members=(quadrant_guide or {}).get('members') or {},
        proportion=(quadrant_guide or {}).get('proportion') or {},
        track_fn=track_fn,
        set_job_fn=set_job_fn,
    )
    quadrants = doc_assigned.get('quadrants') or {}
    machine = doc_assigned.get('machine') or {}
    human = score_human_knowing(username, union)
    bucket = human.get('bucket') or {}
    for word, entry in quadrants.items():
        entry['human_bucket'] = bucket.get(word) or ''

    set_job_fn(username, phase='quadrant_human', last_action='象限小幅修正', progress_percent=86)
    revision = revise_quadrants_by_notebook_meaning(
        username=username,
        notebook_description=notebook_description,
        notebook_name=notebook_name or (scene_name or ''),
        top_pack=top_pack,
        scale=scale,
        union=union,
        quadrants=quadrants,
        machine=machine,
        human=human,
        levels=hier.get('levels') or {},
        source_files=files,
        links=hier.get('links') or [],
        prepared_meaning=quadrant_guide,
        track_fn=track_fn,
    )
    quadrants = revision.get('quadrants') or quadrants
    quadrant_meaning = revision.get('meaning') or {}
    set_job_fn(username, phase='quadrant_revise', last_action='象限核对', progress_percent=90)
    verified = verify_quadrant_assignments(
        username=username,
        quadrants=quadrants,
        meaning=quadrant_meaning,
        union=union,
        levels=hier.get('levels') or {},
        machine=machine,
        human=human,
        track_fn=track_fn,
    )
    quadrants = verified.get('quadrants') or quadrants
    quadrant_meaning = verified.get('meaning') or quadrant_meaning
    with open(book_quadrant_path(username), 'w', encoding='utf-8') as f:
        json.dump(quadrants, f, ensure_ascii=False, indent=2)

    set_job_fn(username, phase='thermometer', last_action='温度计与螺旋', progress_percent=92)
    thermo = build_thermometer_spiral(
        username=username,
        notebook_description=notebook_description,
        top_pack=top_pack,
        quadrants=quadrants,
        track_fn=track_fn,
    )

    # 属性 map：兼容旧字段 + 扩展
    # 仍在的词：默认视为用户认可，尽量保持原属性；锁定词用用户 after；新词才用本次抽取
    prior_map: Dict[str, Dict[str, Any]] = {
        k: dict(v) for k, v in (existing_map or {}).items() if isinstance(v, dict)
    }
    final_map: Dict[str, Dict[str, Any]] = {}
    locked = set((intent.get('locked_attr_words') or []) if isinstance(intent.get('locked_attr_words'), list) else [])
    locked_after: Dict[str, Dict[str, str]] = {}
    for ed in (intent.get('attr_edits') or []):
        if not isinstance(ed, dict):
            continue
        ww = str(ed.get('word') or '').strip()
        after = ed.get('after') if isinstance(ed.get('after'), dict) else {}
        if ww and after:
            locked_after[ww] = {
                'four_color_type': str(after.get('four_color_type') or '').strip().upper()[:1],
                'dmt_level': str(after.get('dmt_level') or '').strip().upper()[:1],
                'knowledge_type': str(after.get('knowledge_type') or '').strip().lower(),
            }
    for w, meta in union.items():
        prior = dict(prior_map.get(w) or {})
        entry = dict(prior)
        fresh_fc = str(meta.get('four_color_type') or '').strip().upper()[:1]
        fresh_dl = str(meta.get('dmt_level') or '').strip().upper()[:1]
        fresh_kt = str(meta.get('knowledge_type') or 'trad').strip().lower()
        if fresh_fc not in ('R', 'B', 'P', 'G'):
            fresh_fc = ''
        if fresh_dl not in ('D', 'M', 'T'):
            fresh_dl = ''
        if fresh_kt not in ('trad', 'org', 'trib'):
            fresh_kt = 'trad'

        if w in locked:
            user_after = locked_after.get(w) or {}
            if user_after.get('four_color_type') in ('R', 'B', 'P', 'G'):
                entry['four_color_type'] = user_after['four_color_type']
            elif entry.get('four_color_type') not in ('R', 'B', 'P', 'G'):
                entry['four_color_type'] = fresh_fc
            if user_after.get('dmt_level') in ('D', 'M', 'T'):
                entry['dmt_level'] = user_after['dmt_level']
            elif entry.get('dmt_level') not in ('D', 'M', 'T'):
                entry['dmt_level'] = fresh_dl
            if user_after.get('knowledge_type') in ('trad', 'org', 'trib'):
                entry['knowledge_type'] = user_after['knowledge_type']
            elif entry.get('knowledge_type') not in ('trad', 'org', 'trib'):
                entry['knowledge_type'] = fresh_kt
        elif prior:
            # 仍在的旧词：属性尽量保持；仅缺项时用新抽补齐
            if entry.get('four_color_type') not in ('R', 'B', 'P', 'G'):
                entry['four_color_type'] = fresh_fc
            if entry.get('dmt_level') not in ('D', 'M', 'T'):
                entry['dmt_level'] = fresh_dl
            if entry.get('knowledge_type') not in ('trad', 'org', 'trib'):
                entry['knowledge_type'] = fresh_kt
        else:
            entry['four_color_type'] = fresh_fc
            entry['dmt_level'] = fresh_dl
            entry['knowledge_type'] = fresh_kt
        entry['level'] = (hier.get('levels') or {}).get(w) or entry.get('level') or ''
        q = quadrants.get(w) or {}
        entry['quadrant'] = q.get('quadrant') or ''
        if q.get('pending_faded'):
            entry['status'] = 'soft_pending'
            entry['pending_faded'] = True
        else:
            entry['status'] = 'pending' if q.get('pending') else 'confirmed'
            entry['pending_faded'] = False
        entry['analysis'] = _clip(meta.get('analysis') or entry.get('analysis') or '', 500)
        # 直接抽取出来源文档（供前端统计「文档出现频次」）
        srcs = [str(s).strip() for s in (meta.get('sources') or []) if str(s).strip()]
        entry['sources'] = srcs
        final_map[w] = entry

    write_keyword_attrs_file(book_kw_attrs_verified_path(username), list(final_map.keys()), final_map)

    # 各源头文档抽出的词表（供前端对未直接命中的文档做模糊匹配）
    per_doc_keywords: Dict[str, List[str]] = {}
    for block in per_doc:
        fn = str(block.get('filename') or '').strip()
        if not fn:
            continue
        seen_w: set = set()
        words: List[str] = []
        for item in block.get('keywords') or []:
            ww = str((item or {}).get('word') or '').strip()
            if ww and ww not in seen_w:
                seen_w.add(ww)
                words.append(ww)
        per_doc_keywords[fn] = words

    hierarchy_links = [[a, b, s] for a, b, s in (hier.get('links') or [])]
    meta = {
        'pipeline': PIPELINE_ID,
        'last_completed_at': datetime.now().isoformat(timespec='seconds'),
        'last_mode': 'incremental' if incremental else 'full',
        'hierarchy_links': hierarchy_links,
        'longitude_chains': chains,
        'keyword_levels': hier.get('levels') or {},
        'book_top_keywords': {
            'top1': top_pack.get('top1'),
            'top3': top_pack.get('top3'),
            'top5': top_pack.get('top5'),
            'top10': top_pack.get('top10'),
            'top_alternatives': top_pack.get('top_alternatives'),
            'reasons': top_pack.get('reasons'),
        },
        'core_issue': top_pack.get('core_issue'),
        'core_issue_alternatives': top_pack.get('core_issue_alternatives'),
        'sub_issues': top_pack.get('sub_issues'),
        'scale_definitions': scale,
        'quadrant_meaning': quadrant_meaning,
        'quadrants': quadrants,
        'machine_know_threshold': machine.get('threshold'),
        'thermometer': thermo,
        'purpose_skeleton': hier.get('purpose_skeleton') or {},
        'hierarchy_linked_node_count': hier.get('linked_node_count'),
        'book_keywords': sorted(final_map.keys()),
        'per_doc_keywords': per_doc_keywords,
        'book_key_issue_path': book_key_issue_path(username),
        'book_kw_connect_path': book_kw_connect_path(username),
        'source_files': files,
        'extract_failures': extract_failures,
        'sampled': False,
        'reorganize_selected_cids': [],
        'processed_cids': [],
        'notebook_name': notebook_name or (scene_name or ''),
    }

    set_job_fn(
        username,
        progress_percent=98,
        last_action='写入结果',
        extract_failures=extract_failures,
    )
    return {
        'final_map': final_map,
        'meta_partial': meta,
        'newly_processed_cids': [],
        'reorganize_selected_cids': [],
        'keyword_count': len(final_map),
        'hierarchy_links': hierarchy_links,
        'extract_failures': extract_failures,
    }
