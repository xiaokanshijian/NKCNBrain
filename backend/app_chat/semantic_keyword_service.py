# encoding=utf-8
"""本子级语义关键词重新/迭代梳理服务。"""
from __future__ import annotations
import nkcn_public_config as _public_config

import json
import logging
import os
import random
import re
import threading
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from openai import OpenAI

from app_chat.config.config_manager import config_manager
from app_chat.keyword_utils import (
    KEYWORD_MAX_CN_CHARS,
    is_semantic_keyword_length_valid,
    parse_batch_keyword_attributes,
    split_semantic_keywords_raw,
)
from app_chat.models import Card
from zym.models import UserNotebook, scene

SEMANTIC_EXTRACT_MODEL = os.environ.get('SEMANTIC_KEYWORD_MODEL', 'deepseek-v4-pro')
CLAUDE_ATTR_MODEL = 'claude-sonnet-4.6'
ATTR_BATCH_SIZE = 50
_FINAL_MARKER = '【最终结果如下】'
_SEMANTIC_META_KEY = 'semantic_reorganize'
_SEMANTIC_BACKUP_KEY = 'semantic_reorganize_backup'  # 仅用于清理 context_data 中的历史残留
_SEMANTIC_BACKUP_FILENAME = 'semantic_reorganize_latest.json'
MAX_KEYWORDS_PER_CARD = 8  # 尽量≤6，必要时硬上限 8（与建卡 CARD_KEYWORDS_HARD_CAP 对齐）
SEMANTIC_REORGANIZE_CARD_LIMIT = 150

_LOCK = threading.Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}
_LOG = logging.getLogger(__name__)

REFINE_MAX_ATTEMPTS = 2  # 超长词仅批量凝练，最多 2 轮
MAX_DEEPSEEK_CALLS_PER_CARD = 4  # 1 提取 + 最多 2 批量凝练 + 最多 1 精简

# 课设综合批改语义空间层次示例（写入提取 prompt，引导模型产出质量）
_SEMANTIC_QUALITY_EXAMPLE = """
**语义空间层次性示例（课设综合批改类本子）**：
- 顶层大块：授课、课设、组织……
- 课设下以「除乘加」为主轴，再细分：车联除乘加、纸联除乘加、体联除乘加
- 车联内再细分具体知识：共享单车、共享维护、智能锁、红蓝白包、锁状态回滚、看门狗回滚……
- 纸联内：DMT微版面、NK-cola指令、同学笔记、智能笔盒、设备回滚、看门狗回滚……
- 体联内：五时、三时、健康筛分、精准PSI、智能穿戴表、五时回滚、看门狗回滚……
- 授课、组织等顶层语义同样应有多层细分，形成「有总有分」的语义空间。
"""

_THREE_KNOWLEDGE_BRIEF = """
**三类知识（语义空间应是三类的混合体，简述）**：
1. **传统知识（trad）**：低维显性、可枚举配置的结构性一般知识（字段指标、时间/权限规则、课程/专业基础知识等）。
2. **组织知识（org）**：治理流程、责任分工、协作与分级响应等半显性规则（谁来处理、怎么运转）。
3. **部落知识（trib）**：高维隐性经验诀窍（复合信号判断、成因链追溯、干预有效性预测等），要有具体实在的隐性知识内容，须萃取为**有具体内涵**的词，不可空泛，最好不要“认知协同”这类模糊不清的。
"""


def _job_key(username: str) -> str:
    return username


def _deepseek_client() -> OpenAI:
    api_key = os.environ.get('DEEPSEEK_API_KEY') or _public_config.secret('DEEPSEEK_API_KEY')
    return OpenAI(api_key=api_key, base_url='https://api.deepseek.com', timeout=120.0)


def _claude_client() -> Tuple[OpenAI, str]:
    model_config = config_manager.get_model_config(CLAUDE_ATTR_MODEL)
    cur = model_config.get_config()
    headers = cur.get('default_headers') or {'x-foo': 'true'}
    client = OpenAI(
        api_key=cur.get('openai_api_key'),
        base_url=cur.get('openai_api_base'),
        default_headers=headers,
        timeout=180.0,
    )
    return client, model_config.get_full_name() or cur.get('model_name') or CLAUDE_ATTR_MODEL


def _track_llm_call(username: Optional[str], provider: str, action: str, detail: str = '') -> None:
    msg = f'[semantic_reorganize] {provider} | {action} | {detail}'
    print(msg, flush=True)
    _LOG.info(msg)
    if not username:
        return
    with _LOCK:
        job = _JOBS.setdefault(_job_key(username), {})
        key = f'api_calls_{provider}'
        job[key] = int(job.get(key) or 0) + 1
        job['last_action'] = action
        job['last_action_detail'] = (detail or '')[:300]


def _is_job_running(username: Optional[str]) -> bool:
    if not username:
        return True
    with _LOCK:
        job = _JOBS.get(_job_key(username))
        return bool(job and job.get('running'))


def _load_semantic_meta(notebook: Optional[UserNotebook]) -> Dict[str, Any]:
    if not notebook or not notebook.context_data:
        return {}
    try:
        ctx = json.loads(notebook.context_data)
        return dict(ctx.get(_SEMANTIC_META_KEY) or {})
    except Exception:
        return {}


def _load_notebook_context(notebook: Optional[UserNotebook]) -> Dict[str, Any]:
    if not notebook or not notebook.context_data:
        return {}
    try:
        return dict(json.loads(notebook.context_data))
    except Exception:
        return {}


def _save_notebook_semantic_state(
    notebook: UserNotebook,
    keyword_map: Dict[str, Dict[str, str]],
    meta: Dict[str, Any],
) -> None:
    ctx = _load_notebook_context(notebook)
    ctx[_SEMANTIC_META_KEY] = meta
    notebook.keywordFourColorDMT = json.dumps(keyword_map, ensure_ascii=False)
    notebook.context_data = json.dumps(ctx, ensure_ascii=False)
    notebook.save(update_fields=['keywordFourColorDMT', 'context_data'])


def _keyword_status_history_dir(username: str) -> str:
    path = os.path.join('.', 'received_dir', 'user_raw_file', username, 'keyword_status_history')
    os.makedirs(path, exist_ok=True)
    return path


def _backup_file_path(username: str) -> str:
    return os.path.join(_keyword_status_history_dir(username), _SEMANTIC_BACKUP_FILENAME)


def _purge_legacy_backup_from_context(notebook: UserNotebook) -> None:
    """移除 context_data 中旧版备份字段（若有）。"""
    ctx = _load_notebook_context(notebook)
    if _SEMANTIC_BACKUP_KEY not in ctx:
        return
    ctx.pop(_SEMANTIC_BACKUP_KEY, None)
    notebook.context_data = json.dumps(ctx, ensure_ascii=False)
    notebook.save(update_fields=['context_data'])


def _load_semantic_backup(username: str) -> Optional[Dict[str, Any]]:
    path = _backup_file_path(username)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return dict(data) if isinstance(data, dict) else None
    except Exception as exc:
        print(f'[_load_semantic_backup] 读取失败 {path}: {exc}', flush=True)
        return None


def _create_semantic_backup(
    notebook: UserNotebook,
    username: str,
    mode: str,
) -> Dict[str, Any]:
    from app_chat.semantic_reorganize_pipeline import snapshot_card_condense_files

    cards = Card.objects.filter(username=username).values('cid', 'keyWords')
    backup: Dict[str, Any] = {
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'mode': mode,
        'username': username,
        'card_keywords': {str(c['cid']): c['keyWords'] or '' for c in cards},
        'keywordFourColorDMT': notebook.keywordFourColorDMT or '',
        'semantic_meta': _load_semantic_meta(notebook),
        # 显式快照，便于回退精确恢复（含空目录 {}）
        'card_condense_files': snapshot_card_condense_files(username),
    }
    history_dir = _keyword_status_history_dir(username)
    latest_path = _backup_file_path(username)
    archive_name = f"semantic_reorganize_{backup['created_at'].replace(':', '').replace('-', '')}.json"
    archive_path = os.path.join(history_dir, archive_name)
    for path in (latest_path, archive_path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)
    _purge_legacy_backup_from_context(notebook)
    print(
        f'[_create_semantic_backup] 已写入 {latest_path} '
        f'cardCondense文件数={len(backup.get("card_condense_files") or {})}',
        flush=True,
    )
    return backup


def _build_extraction_prompt(
    card_content: str,
    card_title: str,
    keyword_pool: List[str],
    notebook_description: str = '',
    scene_summary: str = '',
) -> Tuple[str, str]:
    pool_text = '、'.join(keyword_pool) if keyword_pool else '（尚无）'
    system = (
        '你是语义空间构建专家，擅长从知识卡片中提炼有层次、有具体知识含量的中文语义关键词。'
        '关键词用于构成本子的语义空间，需完整、有总有分、可多层细分。'
        '整个语义关键词集合应构成三类知识（传统/组织/部落）的混合体。'
    )
    user = f"""请阅读以下卡片，提炼适合代表该卡片核心语义的**中文关键词**。

**硬性规则**：
1. 数量：优先按篇幅 2～3（较短）或 4～6（较长）；尽量控制在 6 个以内，必要时最多 8 个。
   几个词须在覆盖广度、深度与内容具体性上，基本上能够代表这张卡片（不多不少），宁精勿滥。
2. 每个关键词不超过 {KEYWORD_MAX_CN_CHARS} 个汉字；必须是自然、贴切的**词**，禁止僵硬截断。
   - 错误：「群组综合批」（截断）→ 正确：「群组批改」或「综合批改」
   - 若概念较长，应凝练为核心语义词，而非截断前半段。
3. 优先从「已有备选池」中直接选用完全匹配或语义等价的词；仅当备选池无合适词时才新增。
4. 关键词须有**具体实在的知识内容**（如「共享单车」「看门狗回滚」「DMT微版面」），避免「认知协同」等模糊不清、意义不大的词。
5. 即使是部落知识（高维隐性知识），也须萃取为有**实际内容价值**的具体词，不可模糊笼统。
6. 语义空间要完整、有层次、有总有分；参考下列层次结构示例（按本子实际内容类推，勿照搬无关词）。
7. 只输出关键词，中文逗号分隔，无其他文字。

{_THREE_KNOWLEDGE_BRIEF}

{_SEMANTIC_QUALITY_EXAMPLE}

**已有备选池（前面卡片已分析出的关键词，优先选用）**：
{pool_text}

**本子描述**：{notebook_description or '未提供'}
**场景摘要**：{(scene_summary or '')[:400]}

**卡片标题**：{card_title or '无'}
**卡片正文**：
{(card_content or '')[:12000]}
"""
    return system, user


def _parse_refine_mapping(raw: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for line in (raw or '').splitlines():
        line = line.strip()
        line = re.sub(r'^[\-\*•]+\s*', '', line)
        line = re.sub(r'^\d+[.\、\)]\s+', '', line)
        if '|' not in line:
            continue
        orig, new = [p.strip() for p in line.split('|', 1)]
        if orig and new:
            mapping[orig] = new
    return mapping


def _call_deepseek(
    client: OpenAI,
    system: str,
    user: str,
    temperature: float = 0.3,
    max_tokens: int = 256,
    username: Optional[str] = None,
    action: str = 'deepseek',
    detail: str = '',
) -> str:
    if not _is_job_running(username):
        raise RuntimeError('梳理任务已停止')
    _track_llm_call(username, 'deepseek', action, detail)
    response = client.chat.completions.create(
        model=SEMANTIC_EXTRACT_MODEL,
        messages=[
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={'thinking': {'type': 'disabled'}},
    )
    return (response.choices[0].message.content or '').strip()


def _refine_overlong_keywords_batch(
    client: OpenAI,
    overlong_keywords: List[str],
    card_title: str,
    card_content: str,
    failed_hints: Optional[Dict[str, str]] = None,
    username: Optional[str] = None,
    cid: Optional[int] = None,
) -> Dict[str, str]:
    """批量请模型将超长词自然凝练为 ≤5 汉字。"""
    if not overlong_keywords:
        return {}
    failed_hints = failed_hints or {}
    kw_lines = []
    for kw in overlong_keywords:
        hint = failed_hints.get(kw)
        if hint:
            kw_lines.append(f'- {kw}（上次凝练「{hint}」仍不合规，请重新凝练）')
        else:
            kw_lines.append(f'- {kw}')
    kw_block = '\n'.join(kw_lines)
    system = (
        '你是语义关键词凝练专家。将过长的词自然缩短为不超过 5 个汉字的贴切语义词。'
        '禁止僵硬截断（如「群组综合批改」不能变成「群组综合批」），应选取最能代表含义的核心词。'
        '每个原词都必须给出合规新词，只输出「原词|新词」每行一个，无其他文字。'
    )
    user = f"""请凝练以下超长关键词（每个新词不超过 {KEYWORD_MAX_CN_CHARS} 个汉字）：

{kw_block}

**卡片标题**：{card_title or '无'}
**卡片片段**：
{(card_content or '')[:3000]}"""
    try:
        raw = _call_deepseek(
            client, system, user, temperature=0.3,
            username=username,
            action='凝练超长词(批量)',
            detail=f'cid={cid} 词数={len(overlong_keywords)}',
        )
        return _parse_refine_mapping(raw)
    except Exception as e:
        print(f'[_refine_overlong_keywords_batch] 凝练失败: {e}')
        return {}


def _refine_overlong_keywords(
    client: OpenAI,
    overlong_keywords: List[str],
    card_title: str,
    card_content: str,
    username: Optional[str] = None,
    cid: Optional[int] = None,
    calls_used: Optional[List[int]] = None,
) -> Dict[str, str]:
    """超长词仅批量凝练，最多 2 轮；合规的写入，仍不合规的丢弃。"""
    if not overlong_keywords:
        return {}

    pending = list(dict.fromkeys(overlong_keywords))
    result: Dict[str, str] = {}
    failed_hints: Dict[str, str] = {}

    for _round in range(REFINE_MAX_ATTEMPTS):
        if not pending:
            break
        batch_map = _refine_overlong_keywords_batch(
            client, pending, card_title, card_content,
            failed_hints=failed_hints, username=username, cid=cid,
        )
        if calls_used is not None:
            calls_used[0] += 1
        still_pending: List[str] = []
        for orig in pending:
            candidate = (batch_map.get(orig) or '').strip()
            if candidate and is_semantic_keyword_length_valid(candidate):
                result[orig] = candidate
            else:
                if candidate:
                    failed_hints[orig] = candidate
                still_pending.append(orig)
        pending = still_pending

    if pending:
        print(
            f'[_refine_overlong_keywords] cid={cid} 批量凝练 {REFINE_MAX_ATTEMPTS} 轮后仍不合规，已丢弃: {pending}',
            flush=True,
        )

    return result


def _trim_keywords_to_max(
    client: OpenAI,
    keywords: List[str],
    card_title: str,
    card_content: str,
    username: Optional[str] = None,
    cid: Optional[int] = None,
    max_count: int = MAX_KEYWORDS_PER_CARD,
) -> List[str]:
    """超过 max_count 时调用 DeepSeek 精简一次；仍超出则截断保留前 max_count 个。"""
    if len(keywords) <= max_count:
        return keywords

    kw_text = '，'.join(keywords)
    system = (
        '你是语义关键词精选专家。从给定关键词列表中删去多余项，只保留最有代表性的若干个。'
        f'必须严格输出不超过 {max_count} 个的中文关键词，中文逗号分隔，无其他文字。'
    )
    user = f"""当前关键词共 {len(keywords)} 个，请精简为最多 {max_count} 个。

**删减优先级（先删这类）**：
1. 内容冗余、重复或高度重叠的
2. 不通顺、不像自然语义词的
3. 意义模糊空泛的（如「认知协同」不合适，因为模糊且意义不明；而「认知负荷」「群组协同」可以保留，因为有具体实在的内涵）

**当前关键词**：
{kw_text}

**卡片标题**：{card_title or '无'}
**卡片片段**：
{(card_content or '')[:3000]}

请直接输出精简后的关键词（最多 {max_count} 个，中文逗号分隔）："""
    try:
        raw = _call_deepseek(
            client, system, user, temperature=0.3, max_tokens=256,
            username=username,
            action='精简关键词',
            detail=f'cid={cid} from={len(keywords)} to<={max_count}',
        )
        trimmed: List[str] = []
        for kw in split_semantic_keywords_raw(raw):
            if is_semantic_keyword_length_valid(kw) and kw not in trimmed:
                trimmed.append(kw)
        if not trimmed:
            print(
                f'[semantic_reorganize] cid={cid} 精简无有效结果，截断保留前 {max_count} 个',
                flush=True,
            )
            return keywords[:max_count]
        if len(trimmed) > max_count:
            print(
                f'[semantic_reorganize] cid={cid} 精简后仍 {len(trimmed)} 个，截断保留前 {max_count} 个',
                flush=True,
            )
            return trimmed[:max_count]
        return trimmed
    except Exception as exc:
        print(f'[_trim_keywords_to_max] cid={cid} 失败: {exc}，截断保留前 {max_count} 个', flush=True)
        return keywords[:max_count]


def extract_keywords_for_card(
    card_content: str,
    card_title: str,
    keyword_pool: List[str],
    notebook_description: str = '',
    scene_summary: str = '',
    username: Optional[str] = None,
    cid: Optional[int] = None,
) -> List[str]:
    system, user = _build_extraction_prompt(
        card_content, card_title, keyword_pool, notebook_description, scene_summary,
    )
    client = _deepseek_client()
    if not _is_job_running(username):
        raise RuntimeError('梳理任务已停止')
    _track_llm_call(
        username, 'deepseek', '提取关键词',
        f'cid={cid} title={(card_title or "")[:40]}',
    )
    response = client.chat.completions.create(
        model=SEMANTIC_EXTRACT_MODEL,
        messages=[
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        temperature=0.4,
        max_tokens=512,
        extra_body={'thinking': {'type': 'disabled'}},
    )
    raw = (response.choices[0].message.content or '').strip()
    raw_keywords = split_semantic_keywords_raw(raw)
    print(
        f'[semantic_reorganize] cid={cid} 提取 raw={len(raw_keywords)} 词 overlong待凝练',
        flush=True,
    )

    valid: List[str] = []
    overlong: List[str] = []
    for kw in raw_keywords:
        if is_semantic_keyword_length_valid(kw):
            if kw not in valid:
                valid.append(kw)
        else:
            overlong.append(kw)

    if overlong:
        print(
            f'[semantic_reorganize] cid={cid} 超长词 {len(overlong)} 个: {overlong[:5]}',
            flush=True,
        )
        calls_used = [1]  # 已消耗 1 次提取
        refined_map = _refine_overlong_keywords(
            client, overlong, card_title, card_content,
            username=username, cid=cid, calls_used=calls_used,
        )
        for orig in overlong:
            candidate = refined_map.get(orig, '').strip()
            if candidate and is_semantic_keyword_length_valid(candidate) and candidate not in valid:
                valid.append(candidate)

    if len(valid) > MAX_KEYWORDS_PER_CARD:
        print(
            f'[semantic_reorganize] cid={cid} 共 {len(valid)} 词，超过 {MAX_KEYWORDS_PER_CARD}，发起精简',
            flush=True,
        )
        valid = _trim_keywords_to_max(
            client, valid, card_title, card_content,
            username=username, cid=cid,
        )

    print(
        f'[semantic_reorganize] cid={cid} 最终 {len(valid)} 词: {valid}',
        flush=True,
    )
    return valid


def _attribute_task_instructions() -> str:
    return f"""
请你按照人性化思考协议完成下列任务。

## 任务：为本子语义关键词逐条判定四色、DMT、三类知识

### 一、四色语境类型（语言/语境维度，输出 R/B/P/G）
- **R（红）**：行业领域语言——专业、严谨、权威，指向品质提高；课程概念、基础知识、专业术语、行业规范、学术标准等。
- **B（蓝）**：技术工具语言——目标指向效率提高；可操作的工具、方法、手段、流程优化等。
- **P（紫）**：场景思维语言——逻辑思维性、系统性推演、方法论框架（除乘加·DMT、都江堰化、COT/SOT/TOT/GOT 等思维框架性内容）。
- **G（绿）**：自然语言——基于紫色思维产生的简单而深刻的自然表达，既易懂又有一定深刻性。

### 二、DMT 语义层级（粒度/层次维度，输出 D/M/T）
- **D（Down）**：下层细节、小粒度——具体步骤、基本概念、操作方法、实例、可直接理解的内容等。
- **M（Middle）**：中层、中粒度——连接、组织、分类、比较、结构化过渡等。
- **T（Top）**：顶层框架、大粒度——偏思维性的统领性框架，具有可向下击穿性，能衍生方法与知识等。

### 三、三类知识（知识类型维度，输出 trad/org/trib）——注意与 DMT 不是一回事
**核心定义**：
1. **传统知识 trad**：低维显性知识，可枚举、可配置的结构性一般知识（学生基础数据、课程基础知识、字段指标、时间类与权限规则类等），通常能以文字、书本固化传播。
2. **组织知识 org**：组织在治理、决策流程、责任分工中沉淀的半显性知识（角色责任、协作流程、分级响应、敏感表达规范、干预经验等），明确「谁来处理、怎么运转」。
3. **部落知识 trib**：高维隐性知识，领域专家长期实践积累的经验、直觉、诀窍等（复合信号判断、成因链追溯、干预有效性预测、群体问题识别等），难以完全显性化。

**关键区别**：
- 维度与显性度：trad 低维显性；org 中维半显性；trib 高维隐性。
- 可复制性：trad/org 可复制传播；trib 独特难复制，需深刻萃取利用。
- 应用场景：trad 常规标准化；org 流程协作与分工；trib 复杂非标准化综合推理（如根因诊断、弱关联挖掘）。

**严禁混淆**：三类知识 ≠ DMT。不是说 trad=D、org=M、trib=T。trad/org/trib 各自都可以有 D/M/T；D/M/T 中也分别都可以有 trad/org/trib。

### 四、输出格式
1. 按人性化思考协议完成 thinking / checking（用三反引号包裹并标记 thinking、checking）。
2. 正式结果输出前，**必须先单独一行输出**：{_FINAL_MARKER}
3. 之后每行一个关键词，格式：`关键词|四色|DMT|三类知识`
4. 示例：
共享单车|R|D|trad
都江堰逻辑|P|T|trib
"""


def _build_attribute_batch_prompt(keywords: List[str], notebook_description: str) -> Tuple[str, str]:
    from app_chat.views import system_prompt_claude

    system = system_prompt_claude + _attribute_task_instructions()
    kw_block = '\n'.join(f'- {kw}' for kw in keywords)
    user = f"""本子描述：{notebook_description or '未提供'}

待分析关键词（共 {len(keywords)} 个，请逐条判定四色、DMT、三类知识）：
{kw_block}

请严格按协议思考后，以 {_FINAL_MARKER} 开头输出最终结果。"""
    return system, user


def analyze_keyword_attributes_batch(
    keywords: List[str],
    notebook_description: str = '',
    username: Optional[str] = None,
    batch_index: int = 0,
) -> Dict[str, Dict[str, str]]:
    if not keywords:
        return {}
    if not _is_job_running(username):
        raise RuntimeError('梳理任务已停止')
    client, model_name = _claude_client()
    system, user = _build_attribute_batch_prompt(keywords, notebook_description)
    _track_llm_call(
        username, 'claude', '属性分析(批量)',
        f'batch={batch_index} 词数={len(keywords)}',
    )
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        temperature=0.3,
        max_tokens=8192,
    )
    raw = (response.choices[0].message.content or '').strip()
    parsed = parse_batch_keyword_attributes(raw, keywords, final_marker=_FINAL_MARKER)
    print(
        f'[semantic_reorganize] Claude 批次{batch_index} 解析 {len(parsed)}/{len(keywords)} 词',
        flush=True,
    )
    return parsed


def _load_notebook(username: str, scene_name: Optional[str]) -> Optional[UserNotebook]:
    real_name = username.split('_')[0] if '_' in username else username
    book_name = username[len(real_name) + 1:] if '_' in username and len(username) > len(real_name) + 1 else None
    if not book_name and scene_name:
        try:
            scene_obj = scene.objects.get(sceneDescription=scene_name)
            nb = UserNotebook.objects.filter(username=real_name, sid=scene_obj.sid).first()
            if nb:
                return nb
        except Exception:
            pass
    if book_name:
        try:
            return UserNotebook.objects.get(username=real_name, bookName=book_name)
        except UserNotebook.DoesNotExist:
            pass
    return UserNotebook.objects.filter(username=real_name).first()


def _ordered_cards(username: str) -> List[Card]:
    return list(
        Card.objects.filter(username=username)
        .exclude(content__isnull=True)
        .exclude(content='')
        .order_by('datetime', 'cid')
    )


def _is_deep_card(card: Card) -> bool:
    """深卡：永久卡且具备四色属性。"""
    return '永久' in (card.type or '') and bool((card.four_color_type or '').strip())


def _has_four_color_or_dmt(card: Card) -> bool:
    return bool((card.four_color_type or '').strip()) or bool((card.dmt_level or '').strip())


def _has_rb_color(card: Card) -> bool:
    """红蓝卡标有色（非默认紫）。"""
    color = (card.color or '紫').strip()
    color_sft = (card.colorSFT or '紫').strip()
    return color != '紫' or color_sft != '紫'


def _is_colored_shallow_or_deep(card: Card) -> bool:
    """有色的浅卡或深卡。"""
    if _is_deep_card(card):
        return True
    return _has_rb_color(card) or _has_four_color_or_dmt(card)


def _shallow_deep_scores(card: Card) -> Tuple[float, float]:
    shallow = float(card.score or 0)
    deep_raw = card.scoreSFT
    deep = float(deep_raw) if deep_raw is not None and float(deep_raw) >= 0 else -1.0
    return shallow, deep


def _both_scores_ge_threshold(card: Card, threshold: float = 3.5) -> bool:
    shallow, deep = _shallow_deep_scores(card)
    return shallow >= threshold and deep >= threshold


def _combined_score(card: Card) -> float:
    shallow, deep = _shallow_deep_scores(card)
    if deep < 0:
        return shallow
    return shallow * 0.3 + deep * 0.7


def _card_recency_key(card: Card) -> Tuple[float, int]:
    """时间越近越大；无 datetime 时退化为 cid。"""
    dt = getattr(card, 'datetime', None)
    if dt is not None:
        try:
            return (float(dt.timestamp()), int(card.cid or 0))
        except Exception:
            pass
    return (0.0, int(card.cid or 0))


def _load_v3_disk_extras(username: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """从 cardCondense 旁路 JSON 补齐 v3 展示字段（meta 缺省时）。"""
    extras: Dict[str, Any] = {}
    try:
        from app_chat import semantic_source_v3_pipeline as v3
    except Exception:
        return extras

    def _read_json(path: str) -> Any:
        if not path or not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    if not meta.get('book_top_keywords'):
        data = _read_json(v3.book_top_keywords_path(username))
        if isinstance(data, dict):
            extras['book_top_keywords'] = {
                k: data.get(k)
                for k in ('top1', 'top3', 'top5', 'top10', 'top_alternatives', 'reasons')
            }
            for k in ('core_issue', 'core_issue_alternatives', 'sub_issues'):
                if data.get(k) is not None and k not in meta:
                    extras[k] = data.get(k)
    if not meta.get('scale_definitions'):
        data = _read_json(v3.book_scale_definitions_path(username))
        if isinstance(data, dict):
            extras['scale_definitions'] = data
    if not meta.get('keyword_levels'):
        data = _read_json(v3.book_levels_path(username))
        if isinstance(data, dict) and isinstance(data.get('levels'), dict):
            extras['keyword_levels'] = data['levels']
    if not meta.get('longitude_chains'):
        data = _read_json(v3.book_longitude_links_path(username))
        if isinstance(data, dict) and isinstance(data.get('chains'), list):
            extras['longitude_chains'] = data['chains']
    if not meta.get('quadrants'):
        data = _read_json(v3.book_quadrant_path(username))
        if isinstance(data, dict):
            extras['quadrants'] = data
    if not meta.get('thermometer'):
        data = _read_json(v3.book_thermometer_path(username))
        if isinstance(data, dict):
            extras['thermometer'] = data
    if not meta.get('quadrant_meaning'):
        data = _read_json(v3.book_quadrant_meaning_path(username))
        if isinstance(data, dict):
            extras['quadrant_meaning'] = data
    try:
        extras['intent_memory'] = v3.load_intent_memory(username)
    except Exception:
        pass
    return extras


def semantic_reorganize_meta_for_api(
    notebook: Optional[UserNotebook],
    full_username: Optional[str] = None,
) -> Dict[str, Any]:
    """供前端 KeywordNetworkGraph 使用的梳理元数据。"""
    meta = _load_semantic_meta(notebook)
    if not meta:
        return {}
    processed = meta.get('processed_cids') or []
    card_selection = meta.get('card_selection') or {}
    sampled = bool(
        meta.get('sampled')
        or card_selection.get('sampled')
        or int(card_selection.get('skipped') or 0) > 0
    )
    if not sampled and processed and meta.get('last_completed_at') and full_username:
        total = (
            Card.objects.filter(username=full_username)
            .exclude(content__isnull=True)
            .exclude(content='')
            .count()
        )
        if total > SEMANTIC_REORGANIZE_CARD_LIMIT and len(processed) <= SEMANTIC_REORGANIZE_CARD_LIMIT:
            sampled = True
    hierarchy_links = meta.get('hierarchy_links') or []
    if (not hierarchy_links) and full_username:
        try:
            from app_chat.semantic_reorganize_pipeline import load_hierarchy_links_from_file
            hierarchy_links = load_hierarchy_links_from_file(full_username)
        except Exception:
            hierarchy_links = []
    selected = [int(x) for x in (meta.get('reorganize_selected_cids') or [])]
    # 兼容旧 v2：尚无 selected 字段时，抽样场景下 processed_cids 即选中集
    if (
        not selected
        and meta.get('pipeline') == 'v2_condense_hierarchy'
        and sampled
        and processed
    ):
        selected = [int(x) for x in processed]

    out: Dict[str, Any] = {
        'processed_cids': [int(x) for x in processed],
        'reorganize_selected_cids': selected,
        'sampled': sampled,
        'last_completed_at': meta.get('last_completed_at') or '',
        'last_mode': meta.get('last_mode') or '',
        'hierarchy_links': hierarchy_links,
        'pipeline': meta.get('pipeline') or '',
    }
    # v3 扩展字段透传
    for key in (
        'longitude_chains',
        'keyword_levels',
        'book_top_keywords',
        'core_issue',
        'core_issue_alternatives',
        'sub_issues',
        'scale_definitions',
        'quadrants',
        'quadrant_meaning',
        'machine_know_threshold',
        'thermometer',
        'book_keywords',
        'per_doc_keywords',
        'source_files',
        'extract_failures',
    ):
        if key in meta and meta.get(key) is not None:
            out[key] = meta.get(key)
    if full_username and str(meta.get('pipeline') or '').startswith('v3'):
        extras = _load_v3_disk_extras(full_username, meta)
        for k, v in extras.items():
            if k not in out or out.get(k) in (None, '', {}, []):
                out[k] = v
    return out


def _select_semantic_reorganize_cards(
    cards: List[Card],
    limit: int = SEMANTIC_REORGANIZE_CARD_LIMIT,
) -> Tuple[List[Card], Dict[str, Any]]:
    """
    待分析卡片超过 limit 时按优先级抽样，不全部处理。
    1) 有色的浅/深卡，时间越近越优先；
    2) 浅评、深评均 >=3.5，综合分越高越优先；
    3) 其余随机补足。
    """
    total = len(cards)
    if total <= limit:
        tier1_count = sum(1 for c in cards if _is_colored_shallow_or_deep(c))
        return cards, {
            'total_candidates': total,
            'selected': total,
            'skipped': 0,
            'tier1_colored': tier1_count,
            'tier2_high_score': 0,
            'tier3_random': 0,
            'sampled': False,
        }

    selected: List[Card] = []
    selected_ids: Set[int] = set()

    tier1 = [c for c in cards if _is_colored_shallow_or_deep(c)]
    tier1.sort(key=_card_recency_key, reverse=True)
    for card in tier1:
        if len(selected) >= limit:
            break
        selected.append(card)
        selected_ids.add(card.cid)
    tier1_count = len(selected)

    tier2_count = 0
    if len(selected) < limit:
        tier2_candidates = [
            c for c in cards
            if c.cid not in selected_ids and _both_scores_ge_threshold(c)
        ]
        tier2_candidates.sort(key=_combined_score, reverse=True)
        for card in tier2_candidates:
            if len(selected) >= limit:
                break
            selected.append(card)
            selected_ids.add(card.cid)
            tier2_count += 1

    tier3_count = 0
    if len(selected) < limit:
        remaining = [c for c in cards if c.cid not in selected_ids]
        need = limit - len(selected)
        tier3 = random.sample(remaining, min(need, len(remaining)))
        selected.extend(tier3)
        tier3_count = len(tier3)

    stats = {
        'total_candidates': total,
        'selected': len(selected),
        'skipped': total - len(selected),
        'tier1_colored': tier1_count,
        'tier2_high_score': tier2_count,
        'tier3_random': tier3_count,
        'sampled': True,
    }
    return selected, stats


def _merge_keyword_attrs(
    existing: Dict[str, Dict[str, str]],
    new_attrs: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, str]]:
    merged = dict(existing or {})
    for kw, attrs in (new_attrs or {}).items():
        entry = dict(merged.get(kw) or {})
        entry.update({k: v for k, v in attrs.items() if v})
        merged[kw] = entry
    return merged


_V3_PHASE_PROGRESS = {
    'source_backfill': 4,
    'card_condense': 8,
    'source_extract': None,  # 动态
    'aggregate_top': 42,
    'scale_definitions': 50,
    'hierarchy_levels': 60,
    'longitude_links': 68,
    'quadrant_guide': 74,
    'quadrant_machine': 78,
    'quadrant_human': 86,
    'quadrant_revise': 89,
    'thermometer': 92,
}


def _compute_progress_percent(job: Dict[str, Any]) -> int:
    if not job.get('running'):
        if job.get('phase') == 'completed':
            return 100
        return 0
    # 任务内已显式写入则优先
    explicit = job.get('progress_percent')
    if isinstance(explicit, (int, float)) and explicit > 0:
        return max(1, min(99, int(explicit)))
    phase = job.get('phase')
    if phase == 'preparing':
        return 1
    if phase in _V3_PHASE_PROGRESS:
        if phase == 'source_extract':
            total = job.get('total_cards') or 0
            idx = job.get('current_index') or 0
            if total <= 0:
                return 10
            return min(40, 5 + int(idx / total * 35))
        return int(_V3_PHASE_PROGRESS.get(phase) or 10)
    if phase in ('extract', 'extract_condense'):
        total = job.get('total_cards') or 0
        idx = job.get('current_index') or 0
        if total <= 0:
            return 2
        return min(38, 2 + int(idx / total * 36))
    if phase == 'key_issues_merge':
        return 48
    if phase == 'enrich':
        return 60
    if phase == 'connect':
        return 72
    if phase == 'attributes':
        total_kw = job.get('total_keywords') or 0
        end = job.get('attr_batch_end') or 0
        if total_kw <= 0:
            return 80
        return min(99, 80 + int(end / total_kw * 19))
    return 0


def _phase_label(job: Dict[str, Any]) -> str:
    phase = job.get('phase')
    if phase == 'preparing':
        return '准备中…'
    if phase == 'source_backfill':
        return job.get('last_action') or '补齐全部文档源头…'
    if phase == 'card_condense':
        return job.get('last_action') or '卡片浓缩（人主体标记）…'
    if phase == 'source_extract':
        total = job.get('total_cards') or 0
        idx = job.get('current_index') or 0
        detail = (job.get('last_action_detail') or '').strip()
        base = f'按文档抽词+属性 {idx}/{total}' if total else '按文档抽词+属性'
        return f'{base} - {detail}' if detail else base
    if phase == 'aggregate_top':
        return '汇总本子词表与 Top1/3/5/10…'
    if phase == 'scale_definitions':
        return '本子刻度（四色/DMT/三类）具体化…'
    if phase == 'hierarchy_levels':
        return '关联强度与 L 层级…'
    if phase == 'longitude_links':
        return '同色跨层连线…'
    if phase == 'quadrant_guide':
        return '本子四象限内涵与比例…'
    if phase == 'quadrant_machine':
        return '按文档定象限…'
    if phase == 'quadrant_human':
        return '象限小幅修正…'
    if phase == 'quadrant_revise':
        return '象限核对…'
    if phase == 'thermometer':
        return '温度计与螺旋…'
    if phase in ('extract', 'extract_condense'):
        total = job.get('total_cards') or 0
        idx = job.get('current_index') or 0
        title = (job.get('current_title') or '').strip()
        base = f'抽词+浓缩 {idx}/{total}' if total else '抽词+浓缩'
        return f'{base} - {title}' if title else base
    if phase == 'key_issues_merge':
        return '分析核心问题并合并跨卡同类关键词…'
    if phase == 'enrich':
        return '按本体层次补全必要语义关键词…'
    if phase == 'connect':
        return '分析关键词直接层次连边…'
    if phase == 'attributes':
        end = job.get('attr_batch_end') or 0
        total_kw = job.get('total_keywords') or 0
        action = (job.get('last_action') or '')
        if '核验' in action:
            return f'属性核验 {end}/{total_kw}' if total_kw else '属性核验'
        return f'四色/DMT/三类知识分析 {end}/{total_kw}' if total_kw else '属性分析'
    if phase == 'completed':
        return '已完成'
    if phase == 'error':
        return '失败'
    if job.get('running'):
        return (job.get('last_action') or '准备中…')
    return '空闲'


def get_job_status(username: str, scene_name: Optional[str] = None) -> Dict[str, Any]:
    with _LOCK:
        job = dict(_JOBS.get(_job_key(username)) or {'running': False, 'phase': 'idle'})
    job['progress_percent'] = _compute_progress_percent(job)
    job['phase_label'] = _phase_label(job)
    notebook = _load_notebook(username, scene_name)
    backup = _load_semantic_backup(username)
    job['rollback_available'] = bool(backup) and not job.get('running')
    if backup:
        job['backup_created_at'] = backup.get('created_at')
        job['backup_mode'] = backup.get('mode')
    return job


def rollback_semantic_reorganize(
    username: str,
    scene_name: Optional[str] = None,
) -> Dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(_job_key(username))
        if job and job.get('running'):
            return {'ok': False, 'msg': '梳理任务进行中，无法回退'}

    notebook = _load_notebook(username, scene_name)
    if not notebook:
        return {'ok': False, 'msg': '未找到本子'}
    backup = _load_semantic_backup(username)
    if not backup:
        return {'ok': False, 'msg': '没有可回退的备份（仅支持回退最近一次梳理）'}

    card_keywords = backup.get('card_keywords') or {}
    restored = 0
    for cid_str, kws in card_keywords.items():
        try:
            cid = int(cid_str)
        except (TypeError, ValueError):
            continue
        updated = Card.objects.filter(username=username, cid=cid).update(keyWords=kws)
        restored += updated

    notebook.keywordFourColorDMT = backup.get('keywordFourColorDMT') or ''
    ctx = _load_notebook_context(notebook)
    ctx[_SEMANTIC_META_KEY] = backup.get('semantic_meta') or {}
    notebook.context_data = json.dumps(ctx, ensure_ascii=False)
    notebook.save(update_fields=['keywordFourColorDMT', 'context_data'])

    # 同步恢复 cardCondense（含 bookKeyIssue / bookKWConnect / cid.txt）
    if 'card_condense_files' in backup:
        try:
            from app_chat.semantic_reorganize_pipeline import restore_card_condense_files
            restore_card_condense_files(username, backup.get('card_condense_files') or {})
        except Exception as exc:
            traceback.print_exc()
            print(f'[rollback_semantic_reorganize] 恢复 cardCondense 失败: {exc}', flush=True)

    backup_path = _backup_file_path(username)
    if os.path.isfile(backup_path):
        try:
            os.remove(backup_path)
        except OSError as exc:
            print(f'[rollback_semantic_reorganize] 删除备份文件失败: {exc}', flush=True)
    _purge_legacy_backup_from_context(notebook)

    with _LOCK:
        _JOBS[_job_key(username)] = {
            'running': False,
            'phase': 'idle',
            'rollback_applied_at': datetime.now().isoformat(timespec='seconds'),
        }

    return {
        'ok': True,
        'msg': '已回退到本次梳理前的状态',
        'cards_restored': restored,
    }


def _set_job(username: str, **kwargs) -> None:
    with _LOCK:
        key = _job_key(username)
        job = _JOBS.setdefault(key, {})
        job.update(kwargs)


def _run_v3_reorganize_job(
    username: str,
    scene_name: Optional[str],
    incremental: bool,
) -> None:
    from app_chat.semantic_source_v3_pipeline import PIPELINE_ID, run_source_v3_pipeline

    notebook = _load_notebook(username, scene_name)
    notebook_desc = (notebook.bookdescription if notebook else '') or ''
    notebook_name = ''
    if notebook is not None:
        notebook_name = str(getattr(notebook, 'bookName', '') or '').strip()
    if not notebook_name and scene_name:
        notebook_name = str(scene_name).strip()
    # 全量/迭代都带上旧属性图：仍在的词默认保持原属性（用户未改=认可）
    existing_map: Dict[str, Dict[str, str]] = {}
    if notebook and notebook.keywordFourColorDMT:
        try:
            existing_map = json.loads(notebook.keywordFourColorDMT)
        except Exception:
            existing_map = {}
    print(
        f'[semantic_reorganize] 启动源头流水线 v3 '
        f'mode={"incremental" if incremental else "full"} username={username} '
        f'book={notebook_name or "-"}',
        flush=True,
    )
    result = run_source_v3_pipeline(
        username=username,
        scene_name=scene_name,
        notebook_description=notebook_desc,
        incremental=incremental,
        existing_map=existing_map,
        set_job_fn=_set_job,
        track_fn=_track_llm_call,
        is_running_fn=_is_job_running,
        notebook_name=notebook_name,
    )
    meta_partial = result.get('meta_partial') or {}
    all_cards = _ordered_cards(username)
    meta = dict(meta_partial)
    meta['pipeline'] = PIPELINE_ID
    meta['processed_cids'] = sorted({int(c.cid) for c in all_cards})
    meta['reorganize_selected_cids'] = meta.get('reorganize_selected_cids') or []
    meta['sampled'] = False
    meta['last_mode'] = 'incremental' if incremental else 'full'
    meta['last_completed_at'] = meta.get('last_completed_at') or datetime.now().isoformat(
        timespec='seconds'
    )
    final_map = result.get('final_map') or {}
    extract_failures = result.get('extract_failures') or meta.get('extract_failures') or []
    if notebook:
        _save_notebook_semantic_state(notebook, final_map, meta)
    _set_job(
        username,
        running=False,
        phase='completed',
        pipeline=PIPELINE_ID,
        total_keywords=int(result.get('keyword_count') or len(final_map)),
        cards_processed=0,
        completed_at=meta['last_completed_at'],
        hierarchy_link_count=len(meta.get('hierarchy_links') or []),
        reorganize_selected_count=0,
        progress_percent=100,
        extract_failures=extract_failures,
    )
    print(
        f'[semantic_reorganize] 完成 v3 keywords={result.get("keyword_count")} '
        f'links={len(meta.get("hierarchy_links") or [])} '
        f'extract_failures={len(extract_failures)}',
        flush=True,
    )


def _run_v2_reorganize_job(
    username: str,
    scene_name: Optional[str],
    incremental: bool,
) -> None:
    from app_chat.semantic_reorganize_pipeline import (
        run_full_pipeline,
        select_reorganize_cards,
    )

    notebook = _load_notebook(username, scene_name)
    notebook_desc = (notebook.bookdescription if notebook else '') or ''

    semantic_meta = _load_semantic_meta(notebook)
    processed_cids: Set[int] = set(int(x) for x in (semantic_meta.get('processed_cids') or []))
    prior_selected_cids: List[int] = [
        int(x) for x in (semantic_meta.get('reorganize_selected_cids') or [])
    ]
    if not prior_selected_cids and semantic_meta.get('pipeline') == 'v2_condense_hierarchy':
        prior_selected_cids = sorted(processed_cids)

    existing_map: Dict[str, Dict[str, str]] = {}
    keyword_pool: List[str] = []

    if not incremental:
        existing_map = {}
        keyword_pool = []
        processed_cids = set()
        prior_selected_cids = []
    else:
        if notebook and notebook.keywordFourColorDMT:
            try:
                existing_map = json.loads(notebook.keywordFourColorDMT)
            except Exception:
                existing_map = {}
        if prior_selected_cids:
            from app_chat.semantic_reorganize_pipeline import load_card_rows_by_cids
            prior_rows = load_card_rows_by_cids(username, prior_selected_cids)
            seen_kw: Set[str] = set()
            for row in prior_rows:
                for kw in row.get('keywords') or []:
                    if kw and kw not in seen_kw:
                        seen_kw.add(kw)
                        keyword_pool.append(kw)
            if existing_map:
                existing_map = {k: v for k, v in existing_map.items() if k in seen_kw}
        else:
            keyword_pool = []
            existing_map = {}
        print(
            f'[semantic_reorganize] 迭代备选池仅含历史新梳理词 '
            f'prior_selected={len(prior_selected_cids)} pool={len(keyword_pool)}',
            flush=True,
        )

    preserved_keyword_map: Dict[str, Dict[str, str]] = {}
    if not incremental and notebook and notebook.keywordFourColorDMT:
        try:
            preserved_keyword_map = json.loads(notebook.keywordFourColorDMT)
        except Exception:
            preserved_keyword_map = {}

    all_cards = _ordered_cards(username)
    if incremental:
        candidate_cards = [c for c in all_cards if c.cid not in processed_cids]
    else:
        candidate_cards = all_cards

    cards, selection_stats = select_reorganize_cards(candidate_cards)
    print(
        f'[semantic_reorganize] 启动精进流水线 v2 '
        f'mode={"incremental" if incremental else "full"} '
        f'candidates={selection_stats.get("total_candidates")} '
        f'selected={selection_stats.get("selected")} '
        f'prior_selected={len(prior_selected_cids)} '
        f'initial_pool={len(keyword_pool) if incremental else 0}(full恒为0)',
        flush=True,
    )

    result = run_full_pipeline(
        username=username,
        scene_name=scene_name,
        notebook_description=notebook_desc,
        cards=cards,
        selection_stats=selection_stats,
        incremental=incremental,
        existing_map=existing_map,
        preserved_keyword_map=preserved_keyword_map,
        all_cards=all_cards,
        initial_pool=keyword_pool if incremental else [],
        prior_selected_cids=prior_selected_cids if incremental else [],
        set_job_fn=_set_job,
        track_fn=_track_llm_call,
        is_running_fn=_is_job_running,
        save_state_fn=_save_notebook_semantic_state,
        notebook=notebook,
    )

    newly_processed_cids = result.get('newly_processed_cids') or []
    selected_union = result.get('reorganize_selected_cids') or newly_processed_cids

    if incremental:
        processed_cids.update(newly_processed_cids)
        for c in candidate_cards:
            processed_cids.add(int(c.cid))
    else:
        processed_cids = {int(c.cid) for c in all_cards}

    prev_sampled = bool(semantic_meta.get('sampled')) if incremental else False
    meta_partial = result.get('meta_partial') or {}
    meta = {
        'processed_cids': sorted(processed_cids),
        'reorganize_selected_cids': sorted({int(x) for x in selected_union}),
        'last_completed_at': meta_partial.get('last_completed_at')
        or datetime.now().isoformat(timespec='seconds'),
        'last_mode': 'incremental' if incremental else 'full',
        'sampled': prev_sampled or bool(selection_stats.get('sampled')),
        'card_selection': selection_stats,
        'hierarchy_links': result.get('hierarchy_links') or meta_partial.get('hierarchy_links') or [],
        'pipeline': 'v2_condense_hierarchy',
        'book_key_issue_path': meta_partial.get('book_key_issue_path') or '',
        'book_kw_connect_path': meta_partial.get('book_kw_connect_path') or '',
    }

    final_map = result.get('final_map') or {}
    if notebook:
        _save_notebook_semantic_state(notebook, final_map, meta)

    _set_job(
        username,
        running=False,
        phase='completed',
        total_keywords=int(result.get('keyword_count') or len(final_map)),
        cards_processed=len(newly_processed_cids),
        completed_at=meta['last_completed_at'],
        hierarchy_link_count=len(meta.get('hierarchy_links') or []),
        reorganize_selected_count=len(meta.get('reorganize_selected_cids') or []),
    )
    print(
        f'[semantic_reorganize] 完成 v2 cards={len(newly_processed_cids)} '
        f'selected_union={len(meta.get("reorganize_selected_cids") or [])} '
        f'keywords={result.get("keyword_count")} '
        f'links={len(meta.get("hierarchy_links") or [])}',
        flush=True,
    )


def _run_reorganize_job(
    username: str,
    scene_name: Optional[str],
    incremental: bool,
    *,
    pipeline: str = 'auto',
) -> None:
    try:
        if pipeline == 'v3_source_document':
            _run_v3_reorganize_job(username, scene_name, incremental)
        else:
            _run_v2_reorganize_job(username, scene_name, incremental)
    except Exception as exc:
        traceback.print_exc()
        _set_job(
            username,
            running=False,
            phase='error',
            error=str(exc),
            last_action='失败',
            last_action_detail=str(exc)[:300],
        )
        print(f'[semantic_reorganize] 任务失败 username={username}: {exc}', flush=True)


def start_semantic_reorganize(
    username: str,
    scene_name: Optional[str] = None,
    incremental: bool = False,
    *,
    force_v2: bool = False,
) -> Dict[str, Any]:
    key = _job_key(username)
    with _LOCK:
        job = _JOBS.get(key)
        if job and job.get('running'):
            return {'ok': False, 'msg': '已有梳理任务在运行', 'status': dict(job)}

    notebook = _load_notebook(username, scene_name)
    if not notebook:
        return {'ok': False, 'msg': '未找到本子'}

    from app_chat.semantic_source_v3_pipeline import (
        assess_source_readiness,
        ensure_all_document_sources,
    )

    readiness = assess_source_readiness(username)
    pipeline = 'v2_condense_hierarchy'
    if force_v2:
        pipeline = 'v2_condense_hierarchy'
    elif readiness.get('reason') == 'no_documents':
        # 无文档：旧链路
        pipeline = 'v2_condense_hierarchy'
    elif readiness.get('ok') and not readiness.get('needs_backfill'):
        pipeline = 'v3_source_document'
    else:
        # 有缺项就先补。补不上时：有 PreImageSummary 可代替 Presummary；
        # 有摘要且 DocStructure、Skill 至少有一个，就继续。仍达不到才停止。
        _set_job(
            username,
            running=True,
            phase='source_backfill',
            mode='incremental' if incremental else 'full',
            last_action='补齐全部文档源头',
            last_action_detail=readiness.get('message') or '',
            progress_percent=2,
            error='',
        )
        try:
            readiness = ensure_all_document_sources(username, set_job_fn=_set_job)
        except Exception as exc:
            traceback.print_exc()
            if readiness.get('ok'):
                print(
                    f'[semantic_reorganize] 补齐异常但已有可继续材料，继续梳理: {exc}',
                    flush=True,
                )
            else:
                _set_job(username, running=False, phase='idle', error=str(exc))
                return {
                    'ok': False,
                    'source_incomplete': True,
                    'readiness': readiness,
                    'msg': (
                        f'自动补齐源头失败：{exc}。'
                        '已停止，不会改走旧卡片链路。'
                        '每份文档需要有 Presummary 或 PreImageSummary，并且有 DocStructure 或 Skill。'
                    ),
                }
        if readiness.get('ok'):
            pipeline = 'v3_source_document'
        else:
            _set_job(username, running=False, phase='idle')
            return {
                'ok': False,
                'source_incomplete': True,
                'readiness': readiness,
                'msg': readiness.get('message')
                or (
                    f"本子共 {readiness.get('total') or '?'} 份文档，"
                    f"{readiness.get('ready_count') or 0} 份可以梳理。"
                    '仍有文档没有可用摘要（Presummary 或 PreImageSummary），'
                    '或者 DocStructure 与 Skill 都没有。'
                    '已停止，不会改走旧卡片链路，也不会只分析已可梳理的文档。'
                ),
            }

    mode_label = 'incremental' if incremental else 'full'
    try:
        _create_semantic_backup(notebook, username, mode_label)
    except Exception as exc:
        traceback.print_exc()
        return {'ok': False, 'msg': f'创建回退备份失败: {exc}'}

    _set_job(
        username,
        running=True,
        phase='preparing',
        mode=mode_label,
        pipeline=pipeline,
        current_index=0,
        total_cards=0,
        total_keywords=0,
        keyword_pool_size=0,
        api_calls_deepseek=0,
        api_calls_claude=0,
        last_action='准备中',
        last_action_detail='已创建回退备份，即将开始梳理…',
        error='',
        progress_percent=1,
        started_at=datetime.now().isoformat(timespec='seconds'),
    )
    print(
        f'[semantic_reorganize] 启动 {mode_label} pipeline={pipeline} username={username}',
        flush=True,
    )

    thread = threading.Thread(
        target=_run_reorganize_job,
        args=(username, scene_name, incremental),
        kwargs={'pipeline': pipeline},
        daemon=True,
    )
    thread.start()
    return {
        'ok': True,
        'msg': 'started',
        'mode': 'incremental' if incremental else 'full',
        'pipeline': pipeline,
        'readiness': readiness,
    }


def update_hierarchy_link_strength(
    username: str,
    scene_name: Optional[str],
    *,
    parent: str,
    child: str,
    strength: str,
) -> Dict[str, Any]:
    """手动更新单条层次连边强度，写回 meta + bookKWConnect.txt。"""
    from app_chat.semantic_reorganize_pipeline import (
        DEFAULT_LINK_STRENGTH,
        LINK_STRENGTHS,
        _write_book_kw_connect,
        load_hierarchy_links_from_file,
        normalize_link_strength,
    )

    parent = (parent or '').strip()
    child = (child or '').strip()
    strength_norm = normalize_link_strength(strength) or DEFAULT_LINK_STRENGTH
    if strength_norm not in LINK_STRENGTHS:
        return {'ok': False, 'msg': f'无效强度: {strength}'}
    if not parent or not child or parent == child:
        return {'ok': False, 'msg': 'parent/child 无效'}

    notebook = _load_notebook(username, scene_name)
    if not notebook:
        return {'ok': False, 'msg': '本子不存在'}

    meta = _load_semantic_meta(notebook)
    links_raw = list(meta.get('hierarchy_links') or [])
    if not links_raw:
        links_raw = load_hierarchy_links_from_file(username)

    # 规范化为 [父, 子, 强度]
    normalized: List[List[str]] = []
    for item in links_raw:
        if not item or len(item) < 2:
            continue
        a = str(item[0] or '').strip()
        b = str(item[1] or '').strip()
        if not a or not b or a == b:
            continue
        s = normalize_link_strength(item[2] if len(item) >= 3 else '') or DEFAULT_LINK_STRENGTH
        normalized.append([a, b, s])

    matched_idx = -1
    matched_reverse = False
    for i, (a, b, _s) in enumerate(normalized):
        if a == parent and b == child:
            matched_idx = i
            break
        if a == child and b == parent:
            matched_idx = i
            matched_reverse = True
            break
    if matched_idx < 0:
        return {'ok': False, 'msg': f'未找到连边: {parent}|{child}'}

    if matched_reverse:
        # 保持文件中原有方向，只改强度
        parent_out, child_out = normalized[matched_idx][0], normalized[matched_idx][1]
    else:
        parent_out, child_out = parent, child
    normalized[matched_idx][2] = strength_norm

    triples = [(a, b, s) for a, b, s in normalized]
    _write_book_kw_connect(username, triples)

    new_meta = dict(meta or {})
    new_meta['hierarchy_links'] = [[a, b, s] for a, b, s in triples]
    new_meta['pipeline'] = new_meta.get('pipeline') or 'v2_condense_hierarchy'

    kw_map: Dict[str, Any] = {}
    if notebook.keywordFourColorDMT:
        try:
            kw_map = json.loads(notebook.keywordFourColorDMT)
        except Exception:
            kw_map = {}
    _save_notebook_semantic_state(notebook, kw_map, new_meta)

    return {
        'ok': True,
        'msg': 'ok',
        'parent': parent_out,
        'child': child_out,
        'strength': strength_norm,
        'hierarchy_links': new_meta['hierarchy_links'],
    }


def _derive_attr_edit_intent_hint(before: Dict[str, Any], after: Dict[str, Any], word: str) -> str:
    """从一次属性改动提炼可跟随的意图短句（给人读、也喂给下次模型）。"""
    color_name = {'R': '红/专业业务', 'B': '蓝/工具手段', 'P': '紫/思维框架', 'G': '绿/简单深刻'}
    dmt_name = {'D': 'D/细节', 'M': 'M/中间结构', 'T': 'T/顶层总括'}
    kt_name = {'trad': '传统/显性', 'org': '组织/半隐', 'trib': '部落/隐性'}
    parts: List[str] = []
    bf = str(before.get('four_color_type') or '').upper()[:1]
    af = str(after.get('four_color_type') or '').upper()[:1]
    if af and af != bf:
        parts.append(
            f'把「{word}」四色从{color_name.get(bf, bf or "空")}改为{color_name.get(af, af)}'
            f'——更强调{color_name.get(af, af)}视角'
        )
    bd = str(before.get('dmt_level') or '').upper()[:1]
    ad = str(after.get('dmt_level') or '').upper()[:1]
    if ad and ad != bd:
        parts.append(
            f'把「{word}」DMT从{dmt_name.get(bd, bd or "空")}改为{dmt_name.get(ad, ad)}'
            f'——更按{dmt_name.get(ad, ad)}定位'
        )
    bk = str(before.get('knowledge_type') or '').lower()
    ak = str(after.get('knowledge_type') or '').lower()
    if ak and ak != bk:
        parts.append(
            f'把「{word}」三类知识从{kt_name.get(bk, bk or "空")}改为{kt_name.get(ak, ak)}'
            f'——更按{kt_name.get(ak, ak)}理解'
        )
    if not parts:
        return f'用户确认「{word}」属性为 四色{af or "?"} / DMT{ad or "?"} / {ak or "?"}'
    return '；'.join(parts)


def suggest_semantic_panel_options(
    username: str,
    scene_name: Optional[str],
    *,
    kind: str,
    current: str = '',
    scale_key: str = '',
    item_key: str = '',
    item_name: str = '',
) -> Dict[str, Any]:
    """为子问题增改、刻度说明修改生成可点选说法。不写入偏好。"""
    from app_chat.semantic_source_v3_pipeline import call_strong_llm, loads_json_loose, JSON_OUTPUT_RULES

    kind = str(kind or '').strip()
    if kind not in ('sub_add', 'sub_edit', 'scale_edit', 'quadrant_edit'):
        return {'ok': False, 'msg': '不支持的调整类型', 'options': []}
    notebook = _load_notebook(username, scene_name)
    meta = _load_semantic_meta(notebook) if notebook else {}
    core = str(meta.get('core_issue') or '').strip()
    subs = meta.get('sub_issues') if isinstance(meta.get('sub_issues'), list) else []
    if not subs:
        tops = meta.get('book_top_keywords') if isinstance(meta.get('book_top_keywords'), dict) else {}
        subs = tops.get('sub_issues') if isinstance(tops.get('sub_issues'), list) else []
    subs = [str(x).strip() for x in subs if str(x).strip()]
    scale = meta.get('scale_definitions') if isinstance(meta.get('scale_definitions'), dict) else {}
    block = scale.get(scale_key) if isinstance(scale.get(scale_key), dict) else {}
    siblings = []
    for k, v in block.items():
        if k == item_key or not v:
            continue
        siblings.append(f'{k}：{str(v)[:180]}')
    if kind == 'quadrant_edit':
        pack = meta.get('quadrant_meaning') if isinstance(meta.get('quadrant_meaning'), dict) else {}
        qdefs = pack.get('definitions') if isinstance(pack.get('definitions'), dict) else {}
        qnames = {'Q1': '共识区', 'Q2': '盲区', 'Q3': '未知区', 'Q4': '隐藏区'}
        siblings = []
        current_qid = str(item_key or '').strip().upper()
        for qid, label in qnames.items():
            if qid == current_qid:
                continue
            raw_def = qdefs.get(qid)
            if isinstance(raw_def, dict):
                raw_def = raw_def.get('meaning') or raw_def.get('text') or ''
            text = str(raw_def or '').strip()
            if text:
                siblings.append(f'{label}：{text[:180]}')
    tops = meta.get('book_top_keywords') if isinstance(meta.get('book_top_keywords'), dict) else {}
    top_words = []
    for key in ('top1', 'top3', 'top5', 'top10'):
        raw = tops.get(key)
        if isinstance(raw, list):
            top_words.extend(str(x).strip() for x in raw if str(x).strip())
        elif raw:
            top_words.append(str(raw).strip())
    seen = []
    for w in top_words:
        if w not in seen:
            seen.append(w)
    if kind == 'sub_add':
        task = (
            '补 4 条这个本子还没问到、但现有核心问题、子问题和刻度里站得住的子问题。'
            '每条必须是一句问话，以问号结尾，中间不要用句号。四条角度要分开，不要互相换词。'
        )
        bound = (
            '这是新增，没有原文可改。'
        )
    elif kind == 'sub_edit':
        task = (
            '下面给出的是要修改的原文。请在这句原文上做精修，给出 4 个修改稿。'
            '修改稿必须还是这一问：保留原句里的对象、做法和问法，只把含糊、别扭、不够贴本子的地方收紧。'
            '禁止另起一个新问题，禁止换成另一组对象，禁止整句推倒重写。'
            '每条仍是一句问话，以问号结尾，中间不要用句号。'
        )
        bound = '必须能看出是同一句的修改，而不是另一条子问题。'
    elif kind == 'quadrant_edit':
        task = (
            f'下面给出的是「{item_name or item_key}」这一象限的语义内涵原文。请在原文上做精修，给出 4 个修改稿。'
            '这一象限收哪些语义要留住，已经点到的对象、做法和边界都要留住。'
            '只调整不够准确、不够顺、和本子内容贴得不紧的词句。'
            '禁止改去讲另外一个象限，禁止整段换成另一套语义。'
            '每条是精修后的完整说明，可以有句号。'
        )
        bound = '必须能看出是同一段的修改，而不是替换成另一段。'
    else:
        task = (
            f'下面给出的是「{item_name or item_key}」这条刻度说明的原文。请在原文上做精修，给出 4 个修改稿。'
            '职分不变，段落里已经点到的对象、做法、框架和后半的对应内容都要留住。'
            '只调整不够准确、不够顺、和本子内容贴得不紧的词句。'
            '禁止另写一条新说明，禁止改去讲旁边另一色、另一层或另一类知识。'
            '每条是精修后的完整说明，可以有句号。'
        )
        bound = '必须能看出是同一段的修改，而不是替换成另一段。'
    system = '只输出 JSON。' + JSON_OUTPUT_RULES
    forbid = '' if kind == 'quadrant_edit' else '不要使用四色、DMT、象限、共识区、温度计、螺旋这类内部叫法。\n'
    sibling_label = '同组其它象限内涵' if kind == 'quadrant_edit' else '同组其它刻度说明'
    prompt = f"""{task}
{bound}
{forbid}核心问题：{core or '（暂无）'}
现有子问题：{json.dumps(subs, ensure_ascii=False)[:1600]}
本子里已经靠前的词：{'、'.join(seen[:12]) or '（暂无）'}
要修改的原文：{current or '（新增，尚无原文）'}
{sibling_label}（只作参照，不要写进修改稿去替换原文）：{json.dumps(siblings, ensure_ascii=False)[:1200]}

输出：{{"options":["修改稿1","修改稿2","修改稿3","修改稿4"]}}
"""
    try:
        raw, _model = call_strong_llm(
            prompt,
            system=system,
            max_tokens=4000 if kind in ('scale_edit', 'quadrant_edit') else 1800,
        )
        data = loads_json_loose(raw)
    except Exception as exc:
        return {'ok': False, 'msg': str(exc)[:200], 'options': []}
    if isinstance(data, dict):
        raw_opts = data.get('options')
    elif isinstance(data, list):
        raw_opts = data
    else:
        raw_opts = []
    options = []
    for item in raw_opts or []:
        text = str(item).strip()
        if text and text not in options:
            options.append(text)
        if len(options) >= 4:
            break
    return {'ok': True, 'msg': 'ok', 'options': options}


def save_semantic_intent_preference(
    username: str,
    scene_name: Optional[str],
    *,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    """写入用户意图记忆（Top/核心问题/刻度/锁定属性等），下次梳理跟随；不自动重跑。"""
    from app_chat.semantic_source_v3_pipeline import load_intent_memory, save_intent_memory

    if not username:
        return {'ok': False, 'msg': 'username required'}
    intent = load_intent_memory(username)
    patch = patch if isinstance(patch, dict) else {}

    if isinstance(patch.get('preferred_top'), dict):
        cur = intent.get('preferred_top') if isinstance(intent.get('preferred_top'), dict) else {}
        cur.update({k: v for k, v in patch['preferred_top'].items() if v})
        intent['preferred_top'] = cur
    if patch.get('preferred_core_issue'):
        intent['preferred_core_issue'] = str(patch['preferred_core_issue']).strip()
    if isinstance(patch.get('preferred_sub_issues'), list):
        intent['preferred_sub_issues'] = [str(x).strip() for x in patch['preferred_sub_issues'] if str(x).strip()]
        intent['sub_issues_user_locked'] = True
    if isinstance(patch.get('preferred_scale_definitions'), dict):
        cur = intent.get('preferred_scale_definitions') if isinstance(intent.get('preferred_scale_definitions'), dict) else {}
        for key, val in patch['preferred_scale_definitions'].items():
            if isinstance(val, dict):
                base = cur.get(key) if isinstance(cur.get(key), dict) else {}
                base.update({k: v for k, v in val.items() if v})
                cur[key] = base
            elif val:
                cur[key] = val
        intent['preferred_scale_definitions'] = cur
    if isinstance(patch.get('preferred_quadrant_definitions'), dict):
        cur = intent.get('preferred_quadrant_definitions') if isinstance(intent.get('preferred_quadrant_definitions'), dict) else {}
        for key, val in patch['preferred_quadrant_definitions'].items():
            qid = str(key or '').strip().upper()
            text = str(val or '').strip()
            if qid in ('Q1', 'Q2', 'Q3', 'Q4') and text:
                cur[qid] = text
        intent['preferred_quadrant_definitions'] = cur
    if isinstance(patch.get('locked_attr_words'), list):
        locked = set(intent.get('locked_attr_words') or [])
        locked.update(str(x).strip() for x in patch['locked_attr_words'] if str(x).strip())
        intent['locked_attr_words'] = sorted(locked)
    # 右键改属性：锁结果 + 提炼「背后意图」供下次梳理跟随（不只锁词）
    if isinstance(patch.get('attr_edits'), list):
        edits = list(intent.get('attr_edits') or [])
        notes = list(intent.get('attr_intent_notes') or [])
        for item in patch['attr_edits']:
            if not isinstance(item, dict):
                continue
            word = str(item.get('word') or '').strip()
            before = item.get('before') if isinstance(item.get('before'), dict) else {}
            after = item.get('after') if isinstance(item.get('after'), dict) else {}
            if not word:
                continue
            entry = {
                'word': word,
                'before': {
                    'four_color_type': str(before.get('four_color_type') or '').strip(),
                    'dmt_level': str(before.get('dmt_level') or '').strip(),
                    'knowledge_type': str(before.get('knowledge_type') or '').strip(),
                },
                'after': {
                    'four_color_type': str(after.get('four_color_type') or '').strip(),
                    'dmt_level': str(after.get('dmt_level') or '').strip(),
                    'knowledge_type': str(after.get('knowledge_type') or '').strip(),
                },
                'at': datetime.now().isoformat(timespec='seconds'),
            }
            hint = _derive_attr_edit_intent_hint(entry['before'], entry['after'], word)
            entry['intent_hint'] = hint
            edits.append(entry)
            if hint:
                notes.append(hint)
        intent['attr_edits'] = edits[-100:]
        # 去重保序，最多保留最近 30 条意图说明
        seen_n = set()
        compact_notes = []
        for n in reversed(notes):
            s = str(n).strip()
            if not s or s in seen_n:
                continue
            seen_n.add(s)
            compact_notes.append(s)
            if len(compact_notes) >= 30:
                break
        intent['attr_intent_notes'] = list(reversed(compact_notes))
        intent['attr_intent_summary'] = '；'.join(intent['attr_intent_notes'][-12:])
    if isinstance(patch.get('confirmations'), list):
        hist = list(intent.get('confirmations') or [])
        for item in patch['confirmations']:
            if isinstance(item, dict):
                item = dict(item)
                item['at'] = datetime.now().isoformat(timespec='seconds')
                hist.append(item)
        intent['confirmations'] = hist[-200:]
    # 透传其它显式字段
    for k in ('notes', 'custom_options'):
        if k in patch:
            intent[k] = patch[k]
    # C4：行为记录（新传文档/钉卡/改属性等），下次梳理跟随，不自动重跑
    if isinstance(patch.get('panel_edit'), dict):
        log = list(intent.get('panel_edit_log') or [])
        item = dict(patch['panel_edit'])
        item['at'] = datetime.now().isoformat(timespec='seconds')
        action = str(item.get('action') or '').strip()
        target = str(item.get('target') or '').strip()
        item['action'] = action
        item['target'] = target[:80]
        log.append(item)
        intent['panel_edit_log'] = log[-40:]
    if isinstance(patch.get('behavior_events'), list):
        evs = list(intent.get('behavior_events') or [])
        for ev in patch['behavior_events']:
            if isinstance(ev, dict):
                item = dict(ev)
                item.setdefault('at', datetime.now().isoformat(timespec='seconds'))
                evs.append(item)
        intent['behavior_events'] = evs[-300:]

    save_intent_memory(username, intent)

    # 若改了核心问题/刻度，同步刷新本子 meta 展示字段（不重跑流水线）
    notebook = _load_notebook(username, scene_name)
    if notebook:
        meta = _load_semantic_meta(notebook)
        changed = False
        if patch.get('preferred_core_issue'):
            meta['core_issue'] = intent.get('preferred_core_issue')
            changed = True
        if isinstance(patch.get('preferred_sub_issues'), list):
            meta['sub_issues'] = list(intent.get('preferred_sub_issues') or [])
            tops = meta.get('book_top_keywords') if isinstance(meta.get('book_top_keywords'), dict) else None
            if isinstance(tops, dict):
                tops['sub_issues'] = list(meta['sub_issues'])
            changed = True
        if isinstance(patch.get('preferred_scale_definitions'), dict):
            scale = meta.get('scale_definitions') if isinstance(meta.get('scale_definitions'), dict) else {}
            pref = intent.get('preferred_scale_definitions') or {}
            for key in ('four_color', 'dmt', 'knowledge'):
                if isinstance(pref.get(key), dict):
                    base = scale.get(key) if isinstance(scale.get(key), dict) else {}
                    base.update(pref[key])
                    scale[key] = base
            meta['scale_definitions'] = scale
            changed = True
        if isinstance(patch.get('preferred_quadrant_definitions'), dict):
            pack = meta.get('quadrant_meaning') if isinstance(meta.get('quadrant_meaning'), dict) else {}
            defs = dict(pack.get('definitions') or {}) if isinstance(pack.get('definitions'), dict) else {}
            pref_q = intent.get('preferred_quadrant_definitions') or {}
            for qid in ('Q1', 'Q2', 'Q3', 'Q4'):
                text = str(pref_q.get(qid) or '').strip()
                if text:
                    defs[qid] = text
            pack['definitions'] = defs
            meta['quadrant_meaning'] = pack
            changed = True
            try:
                from app_chat.semantic_source_v3_pipeline import book_quadrant_meaning_path
                with open(book_quadrant_meaning_path(username), 'w', encoding='utf-8') as f:
                    json.dump(pack, f, ensure_ascii=False, indent=2)
            except Exception as exc:
                print(f'[semantic_intent] quadrant meaning write fail: {exc}', flush=True)
        if isinstance(patch.get('preferred_top'), dict):
            tops = meta.get('book_top_keywords') if isinstance(meta.get('book_top_keywords'), dict) else {}
            pref_top = intent.get('preferred_top') or {}
            if pref_top.get('top1'):
                tops['top1'] = [pref_top['top1']]
            meta['book_top_keywords'] = tops
            changed = True
        if changed:
            kw_map: Dict[str, Any] = {}
            if notebook.keywordFourColorDMT:
                try:
                    kw_map = json.loads(notebook.keywordFourColorDMT)
                except Exception:
                    kw_map = {}
            _save_notebook_semantic_state(notebook, kw_map, meta)

    return {'ok': True, 'msg': 'ok', 'intent': intent}


def confirm_semantic_pending(
    username: str,
    scene_name: Optional[str],
    *,
    word: str,
    choice: str,
    custom_text: str = '',
    preview_applied: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """确认存疑/冲突选项：更新象限或属性，写入记忆；不自动重跑。"""
    from app_chat.semantic_source_v3_pipeline import (
        book_quadrant_path,
        load_intent_memory,
        save_intent_memory,
    )

    word = (word or '').strip()
    choice = (choice or '').strip()
    if not username or not word:
        return {'ok': False, 'msg': 'username/word required'}

    notebook = _load_notebook(username, scene_name)
    if not notebook:
        return {'ok': False, 'msg': '本子不存在'}

    kw_map: Dict[str, Any] = {}
    if notebook.keywordFourColorDMT:
        try:
            kw_map = json.loads(notebook.keywordFourColorDMT)
        except Exception:
            kw_map = {}
    entry = dict(kw_map.get(word) or {})
    meta = _load_semantic_meta(notebook)
    quads = meta.get('quadrants') if isinstance(meta.get('quadrants'), dict) else {}
    q = dict(quads.get(word) or {})

    applied: Dict[str, Any] = {'word': word, 'choice': choice}
    # 优先按结构化 option id / human_know 字段解析（禁止靠中文子串猜）
    opt_matched: Optional[Dict[str, Any]] = None
    for opt in (q.get('pending_options') or []):
        if not isinstance(opt, dict):
            continue
        oid = str(opt.get('id') or '').strip()
        label = str(opt.get('label') or '').strip()
        if choice and (choice == oid or choice == label or choice == f"{oid}:{label}"):
            opt_matched = opt
            break
    if opt_matched is None and isinstance(preview_applied, dict) and preview_applied.get('option_id'):
        for opt in (q.get('pending_options') or []):
            if isinstance(opt, dict) and str(opt.get('id')) == str(preview_applied.get('option_id')):
                opt_matched = opt
                break

    if opt_matched is not None:
        hk = opt_matched.get('human_know')
        applied['option_id'] = opt_matched.get('id')
        applied['preview'] = opt_matched.get('preview') or ''
        patch = opt_matched.get('attr_patch') if isinstance(opt_matched.get('attr_patch'), dict) else {}
        for k in ('four_color_type', 'dmt_level', 'knowledge_type'):
            if patch.get(k):
                entry[k] = patch[k]
                applied[k] = patch[k]
        direct_q = str(opt_matched.get('quadrant') or '').strip().upper()
        if direct_q in ('Q1', 'Q2', 'Q3', 'Q4'):
            q['quadrant'] = direct_q
            q['machine_know'] = direct_q in ('Q1', 'Q2')
            q['human_know'] = direct_q in ('Q1', 'Q4')
            applied['human_know'] = q['human_know']
            applied['quadrant'] = direct_q
            q['pending'] = [
                p for p in (q.get('pending') or [])
                if p not in ('quadrant', 'human_true_know_uncertain')
            ]
            q['pending_faded'] = False
        elif hk is True:
            q['human_know'] = True
            mk = bool(q.get('machine_know'))
            q['quadrant'] = 'Q1' if mk else 'Q4'
            applied['human_know'] = True
            applied['quadrant'] = q['quadrant']
            # A 类：机不知 + 人选知道 → 虚线保留但淡化示疑
            if not mk:
                q['pending'] = [p for p in (q.get('pending') or []) if p != 'quadrant']
                if 'human_true_know_uncertain' not in q['pending']:
                    q['pending'].append('human_true_know_uncertain')
                q['pending_faded'] = True
                applied['pending_faded'] = True
            else:
                q['pending'] = [
                    p for p in (q.get('pending') or [])
                    if p not in ('quadrant', 'human_true_know_uncertain')
                ]
                q['pending_faded'] = False
        elif hk is False:
            q['human_know'] = False
            mk = bool(q.get('machine_know'))
            q['quadrant'] = 'Q2' if mk else 'Q3'
            applied['human_know'] = False
            applied['quadrant'] = q['quadrant']
            q['pending'] = [p for p in (q.get('pending') or []) if p not in ('quadrant', 'human_true_know_uncertain')]
            q['pending_faded'] = False
        else:
            q['pending'] = [p for p in (q.get('pending') or []) if p != 'attr_or_meaning']
        entry['quadrant'] = q.get('quadrant') or entry.get('quadrant') or ''
        if q.get('pending_faded'):
            entry['status'] = 'soft_pending'
            entry['pending_faded'] = True
        else:
            entry['status'] = 'confirmed' if not q.get('pending') else 'pending'
            entry['pending_faded'] = False
    elif choice.startswith('attr:') or choice in ('R', 'B', 'P', 'G', 'D', 'M', 'T', 'trad', 'org', 'trib'):
        val = choice.split(':', 1)[-1] if ':' in choice else choice
        if val in ('R', 'B', 'P', 'G'):
            entry['four_color_type'] = val
            applied['four_color_type'] = val
        elif val in ('D', 'M', 'T'):
            entry['dmt_level'] = val
            applied['dmt_level'] = val
        elif val in ('trad', 'org', 'trib'):
            entry['knowledge_type'] = val
            applied['knowledge_type'] = val
        q['pending'] = [p for p in (q.get('pending') or []) if p != 'attr_or_meaning']
        entry['status'] = 'confirmed' if not q.get('pending') else 'pending'
    elif custom_text:
        applied['custom_text'] = custom_text.strip()
        q['pending'] = []
        entry['status'] = 'confirmed'
        entry['analysis'] = ((entry.get('analysis') or '') + f' | 用户确认：{custom_text.strip()}')[:500]
    else:
        q['pending'] = []
        entry['status'] = 'confirmed'
        if custom_text:
            applied['custom_text'] = custom_text.strip()

    if isinstance(preview_applied, dict):
        applied['preview'] = preview_applied

    quads[word] = q
    meta['quadrants'] = quads
    kw_map[word] = entry
    _save_notebook_semantic_state(notebook, kw_map, meta)
    try:
        with open(book_quadrant_path(username), 'w', encoding='utf-8') as f:
            json.dump(quads, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    intent = load_intent_memory(username)
    hist = list(intent.get('confirmations') or [])
    hist.append({
        'word': word,
        'choice': choice,
        'custom_text': custom_text or '',
        'applied': applied,
        'at': datetime.now().isoformat(timespec='seconds'),
    })
    intent['confirmations'] = hist[-200:]
    # 手改属性锁定
    if any(k in applied for k in ('four_color_type', 'dmt_level', 'knowledge_type')):
        locked = set(intent.get('locked_attr_words') or [])
        locked.add(word)
        intent['locked_attr_words'] = sorted(locked)
    save_intent_memory(username, intent)

    return {
        'ok': True,
        'msg': 'ok',
        'applied': applied,
        'quadrant': q,
        'keyword': entry,
    }


def _keyword_surface_sim(a: str, b: str) -> float:
    aa = (a or '').strip().lower()
    bb = (b or '').strip().lower()
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    if aa in bb or bb in aa:
        return min(len(aa), len(bb)) / max(len(aa), len(bb))
    sa, sb = set(aa), set(bb)
    return len(sa & sb) / max(len(sa | sb), 1)


def _rename_keyword_in_notebook_state(
    kw_map: Dict[str, Any],
    meta: Dict[str, Any],
    old: str,
    new: str,
) -> None:
    """把节点词 old 改名为 new：属性、层次边、L、象限、Top 列表一并替换。"""
    if not old or not new or old == new:
        return
    old_entry = dict(kw_map.get(old) or {})
    new_entry = dict(kw_map.get(new) or {})
    merged = dict(old_entry)
    # 新词若已有属性则保留其非空字段，其余从旧词继承
    for k, v in new_entry.items():
        if v not in (None, '', [], {}):
            merged[k] = v
    for k in ('four_color_type', 'dmt_level', 'knowledge_type', 'analysis', 'level', 'quadrant', 'sources'):
        if (not merged.get(k)) and old_entry.get(k):
            merged[k] = old_entry.get(k)
    kw_map[new] = merged
    if old in kw_map and old != new:
        del kw_map[old]

    def _swap(s: Any) -> Any:
        return new if str(s) == old else s

    links = meta.get('hierarchy_links') if isinstance(meta.get('hierarchy_links'), list) else []
    new_links = []
    for link in links:
        if isinstance(link, (list, tuple)) and len(link) >= 2:
            row = list(link)
            row[0] = _swap(row[0])
            row[1] = _swap(row[1])
            new_links.append(row)
        else:
            new_links.append(link)
    meta['hierarchy_links'] = new_links

    levels = meta.get('keyword_levels') if isinstance(meta.get('keyword_levels'), dict) else {}
    if old in levels:
        levels[new] = levels.pop(old)
    meta['keyword_levels'] = levels

    quads = meta.get('quadrants') if isinstance(meta.get('quadrants'), dict) else {}
    if old in quads:
        quads[new] = quads.pop(old)
    meta['quadrants'] = quads

    chains = meta.get('longitude_chains') if isinstance(meta.get('longitude_chains'), list) else []
    new_chains = []
    for chain in chains:
        if isinstance(chain, list):
            new_chains.append([_swap(x) for x in chain])
        else:
            new_chains.append(chain)
    meta['longitude_chains'] = new_chains

    book_kw = meta.get('book_keywords') if isinstance(meta.get('book_keywords'), list) else []
    meta['book_keywords'] = sorted({new if str(x) == old else str(x) for x in book_kw if str(x).strip()})

    tops = meta.get('book_top_keywords') if isinstance(meta.get('book_top_keywords'), dict) else {}
    for key in ('top1', 'top3', 'top5', 'top10'):
        raw = tops.get(key)
        arr = list(raw) if isinstance(raw, list) else ([raw] if raw else [])
        tops[key] = [new if str(x) == old else x for x in arr]
    alts = tops.get('top_alternatives') if isinstance(tops.get('top_alternatives'), dict) else {}
    for key, raw in list(alts.items()):
        if isinstance(raw, list):
            alts[key] = [new if str(x) == old else x for x in raw]
    tops['top_alternatives'] = alts
    meta['book_top_keywords'] = tops


def apply_top_alternative_replace(
    username: str,
    scene_name: Optional[str],
    *,
    tier: str,
    alt_word: str,
    replace_word: str = '',
) -> Dict[str, Any]:
    """
    点选 Top1/3/5/10 备选：由用户指定该档中要被替换的现有词，换成备选表述，
    并同步属性图、层次边、L、象限与前端所需 meta。
    """
    from app_chat.semantic_source_v3_pipeline import load_intent_memory, save_intent_memory, book_quadrant_path

    tier = str(tier or '').strip()
    alt_word = str(alt_word or '').strip()
    replace_word = str(replace_word or '').strip()
    if not username or tier not in ('top1', 'top3', 'top5', 'top10') or not alt_word:
        return {'ok': False, 'msg': 'username/tier/alt_word required'}
    if not replace_word:
        return {'ok': False, 'msg': '请指定要替换的该档现有词 replace_word'}

    notebook = _load_notebook(username, scene_name)
    if not notebook:
        return {'ok': False, 'msg': '本子不存在'}

    kw_map: Dict[str, Any] = {}
    if notebook.keywordFourColorDMT:
        try:
            kw_map = json.loads(notebook.keywordFourColorDMT)
        except Exception:
            kw_map = {}
    meta = _load_semantic_meta(notebook)
    tops = meta.get('book_top_keywords') if isinstance(meta.get('book_top_keywords'), dict) else {}
    raw = tops.get(tier)
    current = [str(x).strip() for x in (raw if isinstance(raw, list) else ([raw] if raw else [])) if str(x).strip()]
    if not current:
        # 兜底：从 book_keywords 取前 n
        n = {'top1': 1, 'top3': 3, 'top5': 5, 'top10': 10}[tier]
        current = [str(x).strip() for x in (meta.get('book_keywords') or []) if str(x).strip()][:n]

    if replace_word not in current:
        return {
            'ok': False,
            'msg': f'「{replace_word}」不在当前 {tier} 列表中',
            'top_list': current,
        }

    if alt_word == replace_word or alt_word in current:
        # 备选已是该档词：仅调整顺序（提到该档相关位置），不改名
        current = [alt_word if x == replace_word else x for x in current]
        # 去重保序
        seen = set()
        deduped = []
        for x in current:
            if x in seen:
                continue
            seen.add(x)
            deduped.append(x)
        current = deduped
        replaced_old = replace_word
    else:
        replaced_old = replace_word
        current = [alt_word if x == replaced_old else x for x in current]
        n = {'top1': 1, 'top3': 3, 'top5': 5, 'top10': 10}[tier]
        current = current[:n]
        _rename_keyword_in_notebook_state(kw_map, meta, replaced_old, alt_word)

    tops = meta.get('book_top_keywords') if isinstance(meta.get('book_top_keywords'), dict) else {}
    tops[tier] = current
    # top1 同步进 top10 首位
    if tier == 'top1' and current:
        t10 = [str(x).strip() for x in (tops.get('top10') or []) if str(x).strip()]
        tops['top10'] = [current[0]] + [x for x in t10 if x != current[0]]
        tops['top10'] = tops['top10'][:10]
        tops['top1'] = [current[0]]
    meta['book_top_keywords'] = tops
    _save_notebook_semantic_state(notebook, kw_map, meta)
    try:
        quads = meta.get('quadrants') if isinstance(meta.get('quadrants'), dict) else {}
        with open(book_quadrant_path(username), 'w', encoding='utf-8') as f:
            json.dump(quads, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    intent = load_intent_memory(username)
    pref = intent.get('preferred_top') if isinstance(intent.get('preferred_top'), dict) else {}
    pref[tier] = list(current)
    if tier == 'top1' and current:
        pref['top1'] = current[0]
    intent['preferred_top'] = pref
    repl = list(intent.get('top_replacements') or [])
    repl.append({
        'tier': tier,
        'old': replaced_old,
        'new': alt_word,
        'at': datetime.now().isoformat(timespec='seconds'),
    })
    intent['top_replacements'] = repl[-100:]
    save_intent_memory(username, intent)

    return {
        'ok': True,
        'msg': 'ok',
        'tier': tier,
        'old': replaced_old,
        'new': alt_word,
        'top_list': current,
        'book_top_keywords': tops,
        'keyword_map': kw_map,
        'hierarchy_links': meta.get('hierarchy_links') or [],
        'keyword_levels': meta.get('keyword_levels') or {},
        'quadrants': meta.get('quadrants') or {},
        'book_keywords': meta.get('book_keywords') or [],
    }
