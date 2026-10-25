# -*- coding: utf-8 -*-
"""建卡语义关键词统一抽取：admin「P4 · 语义梳理」可切 kimi / kimi-k3 / claude-sonnet-5 / claude-opus-4.8 / deepseek-v4-flash。
Claude 调用失败时重试 1 次，仍失败则降级 deepseek-v4-pro（thinking 关闭）。
"""
from __future__ import annotations
import nkcn_public_config as _public_config

from typing import List, Optional, Sequence, Tuple

from openai import OpenAI

from app_chat.keyword_utils import (
    SEMANTIC_KEYWORDS_FINAL_MARKER,
    build_keyword_extraction_instruction,
    find_rejected_semantic_keywords,
    has_final_marker,
    keyword_count_bounds_for_content,
    parse_final_semantic_keywords,
    split_semantic_keywords_raw,
)

SCENE_SLOT_KEY = 'card_semantic_keywords'
DEFAULT_SLOT_ABBR = 'kimi'
CLAUDE_FALLBACK_ABBR = 'deepseek-v4-pro'
_CLAUDE_MAX_TOKENS = 8192
_KIMI_MAX_TOKENS = 4096
_KIMI_K3_MAX_TOKENS = 8192
_DEEPSEEK_MAX_TOKENS = 8192


def _slot_abbr() -> str:
    from app_chat.scene_models import get_scene_value
    return str(get_scene_value(SCENE_SLOT_KEY, DEFAULT_SLOT_ABBR) or DEFAULT_SLOT_ABBR).strip()


def _is_claude(abbr: str) -> bool:
    return str(abbr or '').strip().lower().startswith('claude')


def _is_deepseek_v4(abbr: str, model_name: str = '') -> bool:
    """deepseek-v4-flash / deepseek-v4-pro：官方 API，需关闭 thinking。"""
    for name in (abbr or '', model_name or ''):
        n = str(name).strip().lower()
        if n.startswith('deepseek-v4-flash') or n.startswith('deepseek-v4-pro'):
            return True
    return False


def _is_moonshot_fixed_sampling(abbr: str, model_name: str = '') -> bool:
    """kimi-k3 等：temperature 仅允许 1，勿传随意 top_p/penalty。"""
    for name in (abbr or '', model_name or ''):
        n = str(name).strip().lower()
        if n == 'kimi-k3' or n.startswith('kimi-k3'):
            return True
        if n == 'kimi-k2.7-code' or n.startswith('kimi-k2.7'):
            return True
    return False


def _build_user_prompt(
    content: str,
    *,
    key_topics: Optional[Sequence[str]] = None,
    notebook_description: str = '',
    min_keywords: int,
    preferred_max: int,
    hard_cap: int,
) -> str:
    parts: List[str] = []
    nb = (notebook_description or '').strip()
    if nb:
        parts.append(
            f'【本子背景】本卡片属于本子（bookdescription）：{nb}\n'
            '请结合本子主题理解卡片在本子中的定位，再提炼语义关键词。'
        )
    topics = [str(t).strip() for t in (key_topics or []) if str(t).strip()]
    if topics:
        parts.append(f'已有的关键词备选集合：{", ".join(topics)}')
    parts.append(
        f'请按工作流程完成提炼：'
        f'（A）理解通透并标出具体内容主体/手段周边/语义段/D·M·T比重/作者深层意图 → '
        f'（B）第一版关键词 → '
        f'（C）checking：先审理解（主题是否被误判为场景、深刻是否被误当成更抽象）；'
        f'再做一眼可读自检、语义段覆盖自检与 D/M/T 缺层检查，决定增/删/改/换序，最后逐词规范审核 → '
        f'（D）第二版为最终，先输出 {SEMANTIC_KEYWORDS_FINAL_MARKER}。\n'
        f'数量以合适为准（可参考 {min_keywords}～{preferred_max}，最好不超 {preferred_max}），'
        f'不要纠结凑数；硬上限 {hard_cap}。'
        f'须覆盖各语义段，勿整段遗漏；优先保证具体内容主体可读，禁止整盘发虚的过程/机制壳。\n'
        f'需要你总结语义关键词的文本：\n{content}'
    )
    return '\n\n'.join(parts)


def _call_kimi(system_prompt: str, user_prompt: str) -> str:
    """沿用现有 moonshot kimi_api 路径（kimi-k3）。"""
    import kimi_api
    from llm_langchain import global_var

    full_prompt = f'{system_prompt}\n\n{user_prompt}'
    prev_max = None
    try:
        prev_max = global_var.kimiConfig.get('max_tokens')
        global_var.kimiConfig['max_tokens'] = max(int(prev_max or 0), _KIMI_MAX_TOKENS)
    except Exception:
        prev_max = None
    try:
        rsp = kimi_api.make_requests(full_prompt, None, False, 0.8)
        raw = (rsp.choices[0].message.content or '').strip()
    finally:
        if prev_max is not None:
            try:
                global_var.kimiConfig['max_tokens'] = prev_max
            except Exception:
                pass
    return raw


def _call_openai_compat(
    abbr: str,
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = _CLAUDE_MAX_TOKENS,
) -> str:
    from app_chat.scene_models import resolve_openai_cfg_from_abbr
    from app_chat.config.config_manager import config_manager

    cfg = resolve_openai_cfg_from_abbr(abbr)
    headers = {'x-foo': 'true'}
    temperature = 0.7
    model_name = str(cfg.get('model') or abbr)
    try:
        mc = config_manager.get_model_config(abbr)
        if mc:
            cur = mc.get_config() or {}
            if cur.get('default_headers'):
                headers = cur.get('default_headers')
            if cur.get('temperature') is not None:
                temperature = float(cur.get('temperature'))
            if cur.get('max_tokens'):
                max_tokens = max(int(cur.get('max_tokens')), max_tokens)
            if cur.get('model_name'):
                model_name = str(cur.get('model_name'))
    except Exception:
        pass

    client = OpenAI(
        api_key=cfg.get('api_key'),
        base_url=cfg.get('base_url'),
        default_headers=headers,
        timeout=180.0,
    )
    create_kwargs = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': max_tokens,
    }
    if _is_moonshot_fixed_sampling(abbr, model_name):
        # kimi-k3：仅 temperature=1，省略 top_p / penalty / n，避免 400
        create_kwargs['temperature'] = 1.0
        create_kwargs['max_tokens'] = max(max_tokens, _KIMI_K3_MAX_TOKENS)
        print(
            f'[card_keyword_extract] {abbr}/{model_name} 固定采样：temperature=1.0（已省略 top_p/penalty）',
            flush=True,
        )
    elif _is_deepseek_v4(abbr, model_name):
        # deepseek-v4-flash / pro：关闭 API thinking，避免 content 被推理占空
        import os
        create_kwargs['temperature'] = 0.6
        create_kwargs['max_tokens'] = max(max_tokens, _DEEPSEEK_MAX_TOKENS)
        create_kwargs['extra_body'] = {'thinking': {'type': 'disabled'}}
        if not str(create_kwargs['model']).startswith('deepseek-v4'):
            create_kwargs['model'] = abbr
        ds_key = (os.environ.get('DEEPSEEK_API_KEY') or '').strip()
        if not ds_key:
            ds_key = str(cfg.get('api_key') or '').strip()
            if ds_key.startswith('env:'):
                ds_key = (os.environ.get(ds_key[4:]) or '').strip()
        if not ds_key:
            # 与 views / semantic_keyword_service 等同项目回退
            ds_key = _public_config.secret('DEEPSEEK_API_KEY')
        client = OpenAI(
            api_key=ds_key,
            base_url='https://api.deepseek.com',
            timeout=180.0,
        )
        print(
            f'[card_keyword_extract] {abbr}/{create_kwargs["model"]}：temperature=0.6, thinking=disabled',
            flush=True,
        )
    else:
        create_kwargs['temperature'] = temperature

    rsp = client.chat.completions.create(**create_kwargs)
    msg = rsp.choices[0].message
    content = (getattr(msg, 'content', None) or '').strip()
    if content:
        return content
    reasoning = (getattr(msg, 'reasoning_content', None) or '').strip()
    return reasoning


def _system_prompt_for_slot(abbr: str, task_instruction: str) -> str:
    if _is_claude(abbr):
        from app_chat.views import system_prompt_claude
        return (
            f'{system_prompt_claude}\n\n'
            '请你按照如上人性化思考协议的要求，思考并完成任务'
            '（先 thinking，再 checking；可按需要再补充思考），'
            '再给出最终正文结果。\n'
            '特别注意：prompt 中有【强制对齐示范】多份样例（含样例5体联公能批改、样例6都江堰三级筛分）。'
            'checking 时必须对照：一眼是否读得出具体内容；主题/专名是否居前；'
            'D/M/T 是否约 5:3:2 且三层齐全；是否犯了样例5/6同类「发虚占位」错误；'
            '先审理解，再对关键词做增/删/改/换序。\n\n'
            f'{task_instruction}'
        )
    return task_instruction


def _invoke_model(abbr: str, system_prompt: str, user_prompt: str) -> str:
    if abbr.lower() in ('kimi', 'moonshot', 'kimi-legacy'):
        return _call_kimi(system_prompt, user_prompt)
    return _call_openai_compat(abbr, system_prompt, user_prompt)


def _validate_claude_keyword_extract_raw(raw: str, *, hard_cap: int) -> str:
    """
    Claude 抽词输出验收：
    1) 必须含 [FINAL]（或兼容旧标记）
    2) 仅解析 FINAL 后的词表
    3) 任一词 ≥10 个汉字（字母/数字不计），或含 ` → 整批失败
    返回归一化后的逗号分隔关键词串。
    """
    if not has_final_marker(raw):
        raise RuntimeError(f'输出缺少最终标记 {SEMANTIC_KEYWORDS_FINAL_MARKER}')
    key_words = parse_final_semantic_keywords(raw, max_count=hard_cap, require_marker=True)
    kws = split_semantic_keywords_raw(key_words)
    if not kws:
        raise RuntimeError('[FINAL] 后未解析到任何语义关键词')
    bad = find_rejected_semantic_keywords(kws)
    if bad:
        preview = '、'.join(bad[:5])
        more = f'等共{len(bad)}个' if len(bad) > 5 else ''
        raise RuntimeError(
            f'关键词不合格（≥10汉字或含`）：{preview}{more}'
        )
    return key_words


def _invoke_with_claude_retry_fallback(
    abbr: str,
    task_instruction: str,
    user_prompt: str,
    *,
    hard_cap: int = 10,
) -> Tuple[str, str]:
    """
    Claude：失败重试 1 次（含缺 FINAL / 脏词）；仍失败则降级 deepseek-v4-pro（不开 thinking）。
    返回 (实际使用的 abbr, raw 文本)。
    """
    system_prompt = _system_prompt_for_slot(abbr, task_instruction)
    if not _is_claude(abbr):
        raw = _invoke_model(abbr, system_prompt, user_prompt)
        # 非 Claude 也尽量按同一验收（缺标记时 parse 仍可回退，但脏词仍拦）
        if has_final_marker(raw):
            _validate_claude_keyword_extract_raw(raw, hard_cap=hard_cap)
        else:
            kws = split_semantic_keywords_raw(
                parse_final_semantic_keywords(raw, max_count=hard_cap)
            )
            bad = find_rejected_semantic_keywords(kws)
            if bad:
                raise RuntimeError(
                    f'关键词不合格（≥10汉字或含`）：{"、".join(bad[:5])}'
                )
        return abbr, raw

    last_err: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            print(
                f'[card_keyword_extract] Claude 调用 attempt={attempt}/2 abbr={abbr}',
                flush=True,
            )
            raw = _invoke_model(abbr, system_prompt, user_prompt)
            if not (raw or '').strip():
                raise RuntimeError('Claude 返回空内容')
            _validate_claude_keyword_extract_raw(raw, hard_cap=hard_cap)
            return abbr, raw
        except Exception as e:
            last_err = e
            print(
                f'[card_keyword_extract] Claude 调用失败 attempt={attempt}/2 abbr={abbr}: {e}',
                flush=True,
            )

    fallback = CLAUDE_FALLBACK_ABBR
    print(
        f'[card_keyword_extract] Claude 两次失败，降级 {fallback}（thinking=disabled）；'
        f'last_err={last_err}',
        flush=True,
    )
    fb_system = _system_prompt_for_slot(fallback, task_instruction)
    raw = _invoke_model(fallback, fb_system, user_prompt)
    if not (raw or '').strip():
        raise RuntimeError(f'{fallback} 降级返回空内容；Claude 错误={last_err}')
    # 降级仍做同一验收，避免脏词入库
    _validate_claude_keyword_extract_raw(raw, hard_cap=hard_cap)
    return fallback, raw


def extract_card_semantic_keywords(
    content: str,
    *,
    key_topics: Optional[Sequence[str]] = None,
    notebook_description: str = '',
    with_candidates: Optional[bool] = None,
    username: Optional[str] = None,
    scene_name: Optional[str] = None,
) -> str:
    """
    抽取建卡语义关键词（逗号分隔字符串）。
    - 模型由 admin 槽位 card_semantic_keywords 决定
    - Claude 失败重试 1 次，仍失败降级 deepseek-v4-pro（thinking 关闭）
    - 完整打印模型输出，便于排查理解细节
    - 解析 [FINAL] 后的列表；硬上限随正文字数（≤3000→10，>3000→15，>4000→20）
    - Claude：缺 [FINAL]、或词≥10汉字（字母数字不计）/含` → 视为调用失败并重试
    """
    text = content or ''
    if not str(text).strip():
        return ''

    nb = (notebook_description or '').strip()
    if not nb and (username or scene_name):
        try:
            from app_chat.scene_context_helper import get_notebook_description
            nb = get_notebook_description(username or '', scene_name) or ''
        except Exception as e:
            print(f'[card_keyword_extract] 获取本子描述失败: {e}', flush=True)

    min_kw, preferred_max, hard_cap = keyword_count_bounds_for_content(text)
    topics = list(key_topics or [])
    use_candidates = with_candidates if with_candidates is not None else bool(topics)

    task_instruction = build_keyword_extraction_instruction(
        preferred_max,
        with_candidates=use_candidates,
        min_keywords=min_kw,
        hard_cap=hard_cap,
    )
    user_prompt = _build_user_prompt(
        text,
        key_topics=topics,
        notebook_description=nb,
        min_keywords=min_kw,
        preferred_max=preferred_max,
        hard_cap=hard_cap,
    )

    abbr = _slot_abbr()

    print(
        f'[card_keyword_extract] slot={abbr} chars={len(text)} '
        f'bounds={min_kw}~{preferred_max}(hard≤{hard_cap}) '
        f'notebook_desc_len={len(nb)} candidates={len(topics)}',
        flush=True,
    )

    try:
        used_abbr, raw = _invoke_with_claude_retry_fallback(
            abbr, task_instruction, user_prompt, hard_cap=hard_cap,
        )
    except Exception as e:
        print(f'[card_keyword_extract] 调用失败 abbr={abbr}: {e}', flush=True)
        raise

    print(
        f'[card_keyword_extract] ===== 模型完整输出 begin (abbr={used_abbr}) =====\n'
        f'{raw}\n'
        f'[card_keyword_extract] ===== 模型完整输出 end =====',
        flush=True,
    )

    key_words = parse_final_semantic_keywords(raw, max_count=hard_cap, require_marker=True)
    print(f'[card_keyword_extract] 解析结果: {key_words}', flush=True)
    return key_words
