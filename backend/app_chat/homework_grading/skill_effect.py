"""本子 Skill 作用档：整次批改只判 1 次。小模型优先，失败 deepseek 兜底。"""
import json
import re
from typing import Any, Dict, List, Optional

from .yangqian_debug import debug_log

LEVELS = ('低', '中', '高')
_LEVEL_RE = re.compile(r'(档\s*[=:：]\s*|作用\s*[=:：]\s*|level\s*[=:：]\s*)?(低|中|高)')


def _parse_level(raw: str) -> Optional[Dict[str, str]]:
    text = str(raw or '').strip()
    if not text or '失败' in text[:20]:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            level = str(data.get('档') or data.get('level') or data.get('作用') or '').strip()
            if level in LEVELS:
                return {'level': level, 'reason': str(data.get('理由') or data.get('reason') or '')[:160],
                        'source': 'json'}
    except Exception:
        pass
    m = _LEVEL_RE.search(text)
    if not m:
        return None
    return {'level': m.group(2), 'reason': text.replace(m.group(0), '').strip()[:160], 'source': 'text'}


def _payload(card_text: str, skill_titles: List[str]) -> str:
    titles = '、'.join(skill_titles) or '（未列出方法名，按正文判断）'
    body = (card_text or '')[:6000]
    return (
        '判断下面这份批改结果卡里，本子教学方法是否真正贯穿（不是贴方法原文、不是堆方法名词）。\n'
        '对照：有页上事实、能判断所处环节或方法主线、下一步学生能做、有边界；删掉方法词后仍像人话算更深。\n'
        f'本轮方法（对照用）：{titles}\n'
        '只输出一行：档=低 或 档=中 或 档=高，可再附一句理由。\n'
        '低：几乎看不到方法，或只剩方法词。\n'
        '中：有方法视角但不完整（缺事实或缺下一步）。\n'
        '高：贯穿且达到能用（事实、判断、下一步齐全）。\n\n'
        '【结果卡正文】\n' + body
    )


def _small_model(username: str, payload: str) -> str:
    from llm_langchain.get_rel_que import get_depth_suggestion
    return get_depth_suggestion(payload, username or 'grading', 'notebook_skill_effect') or ''


def _deepseek(payload: str, feedback_runtime=None) -> str:
    from .llm_clients import _deepseek_client, homework_deepseek_model
    from .feedback_model import runtime_client
    client = _deepseek_client()
    client = runtime_client(client, feedback_runtime, 'deepseek')
    resp = client.chat.completions.create(
        model=homework_deepseek_model(),
        messages=[
            {'role': 'system', 'content': '你只判断教学方法在批改结果中的贯穿程度。只输出 档=低|中|高 和一句理由。'},
            {'role': 'user', 'content': payload},
        ],
        temperature=0.2,
        max_tokens=200,
    )
    return (resp.choices[0].message.content or '').strip()


def judge_notebook_skill_effect(
    *,
    username: str,
    card_text: str,
    skill_titles: Optional[List[str]] = None,
    feedback_runtime=None,
) -> Dict[str, Any]:
    titles = [str(x) for x in (skill_titles or []) if x]
    payload = _payload(card_text, titles)
    raw = ''
    source = ''
    try:
        raw = _small_model(username, payload)
        parsed = _parse_level(raw)
        if parsed:
            parsed['source'] = 'peft'
            parsed['raw'] = raw[:400]
            debug_log(f'[skill_effect] 小模型命中 档={parsed["level"]} titles={titles}')
            return parsed
        source = 'peft_unparsed'
        debug_log(f'[skill_effect] 小模型未解析 raw={str(raw)[:120]} titles={titles}')
    except Exception as exc:
        raw = str(exc)
        source = 'peft_error'
        debug_log(f'[skill_effect] 小模型失败: {exc} titles={titles}')
    try:
        ds = _deepseek(payload, feedback_runtime)
        parsed = _parse_level(ds)
        if parsed:
            parsed['source'] = 'deepseek'
            parsed['raw'] = ds[:400]
            debug_log(f'[skill_effect] deepseek 兜底命中 档={parsed["level"]} titles={titles}')
            return parsed
        debug_log(f'[skill_effect] deepseek 未解析 raw={str(ds)[:120]} titles={titles}')
        return {'level': '', 'reason': '解析失败', 'source': 'deepseek_unparsed', 'raw': (ds or raw)[:400]}
    except Exception as exc:
        debug_log(f'[skill_effect] deepseek 兜底失败: {exc} titles={titles}')
        return {'level': '', 'reason': str(exc)[:160], 'source': source or 'failed', 'raw': raw[:400]}
