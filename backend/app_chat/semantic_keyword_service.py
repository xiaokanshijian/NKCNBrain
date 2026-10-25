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
    return {
        'processed_cids': [int(x) for x in processed],
        'reorganize_selected_cids': selected,
        'sampled': sampled,
        'last_completed_at': meta.get('last_completed_at') or '',
        'last_mode': meta.get('last_mode') or '',
        'hierarchy_links': hierarchy_links,
        'pipeline': meta.get('pipeline') or '',
    }


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


def _compute_progress_percent(job: Dict[str, Any]) -> int:
    if not job.get('running'):
        if job.get('phase') == 'completed':
            return 100
        return 0
    phase = job.get('phase')
    if phase == 'preparing':
        return 1
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
        return '准备中…'
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


def _run_reorganize_job(
    username: str,
    scene_name: Optional[str],
    incremental: bool,
) -> None:
    try:
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
        # 兼容旧 meta：无 reorganize_selected_cids 时，用 processed_cids 作为已梳理选中集
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
            # 迭代备选池：只用来自「此前新梳理选中卡」的关键词，绝不混入未梳理旧卡旧词
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
                # 属性库也裁到新语义空间，避免旧词属性残留参与合并
                if existing_map:
                    existing_map = {k: v for k, v in existing_map.items() if k in seen_kw}
            else:
                # 尚无 v2 选中集：备选池保持空，从零按新流程长
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
            # 重新梳理：备选池从空开始；迭代：仅历史新梳理词
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
            # 覆盖集：旧覆盖 ∪ 本轮实际处理；选中集：历史已梳理 ∪ 本轮
            processed_cids.update(newly_processed_cids)
            # 本轮候选中未抽中的也不再反复迭代（与全量覆盖语义一致）
            for c in candidate_cards:
                processed_cids.add(int(c.cid))
        else:
            # 全量：覆盖集=当前本子全部卡，避免迭代去啃未抽样旧卡冲掉全书结果
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
) -> Dict[str, Any]:
    key = _job_key(username)
    with _LOCK:
        job = _JOBS.get(key)
        if job and job.get('running'):
            return {'ok': False, 'msg': '已有梳理任务在运行', 'status': dict(job)}

    notebook = _load_notebook(username, scene_name)
    if not notebook:
        return {'ok': False, 'msg': '未找到本子'}
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
        current_index=0,
        total_cards=0,
        total_keywords=0,
        keyword_pool_size=0,
        api_calls_deepseek=0,
        api_calls_claude=0,
        last_action='准备中',
        last_action_detail='已创建回退备份，即将开始梳理…',
        error='',
        started_at=datetime.now().isoformat(timespec='seconds'),
    )
    print(f'[semantic_reorganize] 启动 {mode_label} username={username}', flush=True)

    thread = threading.Thread(
        target=_run_reorganize_job,
        args=(username, scene_name, incremental),
        daemon=True,
    )
    thread.start()
    return {'ok': True, 'msg': 'started', 'mode': 'incremental' if incremental else 'full'}


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
