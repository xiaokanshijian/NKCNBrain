# -*- coding: utf-8 -*-
"""跨本子任务簇：用户本子语义聚类（主页「任务簇型」视图）。"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Count, Q
from openai import OpenAI

from app_chat.models import Card
from zym.models import UserNotebook, scene

_META_DIR = os.path.join('.', 'received_dir', 'task_cluster_meta')
_SKIP_DOC_DIRS = frozenset({'cardImage', 'pre_summary', 'pre_image_summary'})
_DOC_EXTS = frozenset({'.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.md'})
_COLORED_CARD_LIMIT = 20
_BATCH_CLUSTER_THRESHOLD = 50
_BATCH_CLUSTER_SIZE = 40
_BATCH_MAX_WORKERS = 3
_DOC_SHOW_MAX = 15
_CARD_SHOW_MAX = 15
_GEMINI_MAX_TOKENS = 18888
_CLAUDE_MAX_TOKENS = 32768
_GEMINI_DEFAULT = 'gemini-3.1-pro-preview'
_OPUS_DEFAULT = 'claude-opus-4.8'

_running_lock = threading.Lock()
_running_users: set = set()

SYSTEM_PROMPT = """你是 NKCN 本子任务簇分析助手。根据用户多个学习/工作本子的元数据，识别哪些本子围绕同一任务簇（同一课设、同一项目、同一主题工作流等）强相关。

重要原则：
1. 同一场景下的本子不一定属于同一任务簇；不同场景的本子也可能属于同一任务簇。
2. 只有「较强任务关联」才应聚为一簇（例如：飞书TA答疑、精进种子、梯子图批改等课设相关本子）。
3. 关联弱的本子放入 unclustered，不要强行合并。
4. 只输出 JSON，不要 markdown 代码块外的任何文字。"""

USER_PROMPT_TEMPLATE = """请分析以下用户的 {count} 个本子，按任务簇聚类。

每个本子字段说明：
- notebook_key: 唯一标识（作者_英文名）
- bookdescription: 中文本子名
- scene_name: 所属场景
- role: author=我是作者，collaborator=我是组本协作者
- last_used: 最后使用时间
- documents: 文档文件名列表
- colored_card_titles: 有色浅卡标题（红蓝卡标非紫）

输出必须是合法 JSON，格式严格如下：
{{
  "clusters": [
    {{
      "cluster_id": "c1",
      "cluster_name": "任务簇中文名（简短）",
      "summary": "为何这些本子属于同一任务簇（1-3句）",
      "notebook_keys": ["作者1_本子A", "作者2_本子B"]
    }}
  ],
  "unclustered": [
    {{
      "notebook_key": "作者_本子",
      "reason": "为何单独成簇或不入簇"
    }}
  ]
}}

要求：
- 每个 notebook_key 必须恰好出现在 clusters 某一项的 notebook_keys 中，或出现在 unclustered 中，不可遗漏、不可重复。
- clusters 至少 1 项（若全部强相关可只有 1 簇）；允许 unclustered 为空。
- notebook_keys 使用输入中的 notebook_key 原样。
{compact_hint}
本子列表：
{payload}
"""

COMPACT_OUTPUT_HINT = """
- 输出 JSON 必须完整闭合、可解析；cluster_name/summary/reason 可适度简短以控制篇幅，但不可截断 JSON。"""

MERGE_PROMPT_TEMPLATE = """以下是同一用户多批任务簇分析结果，请合并语义相同或高度重叠的簇，输出覆盖全部 {count} 个 notebook_key 的最终 JSON。

规则与单批相同：每个 notebook_key 恰好出现一次；同场景未必同簇；跨场景可同簇。
{compact_hint}
全部 notebook_key 列表（必须全部覆盖）：
{all_keys}

各批结果：
{batch_payload}

只输出合法 JSON，格式：
{{
  "clusters": [{{"cluster_id":"c1","cluster_name":"...","summary":"...","notebook_keys":[]}}],
  "unclustered": [{{"notebook_key":"...","reason":"..."}}]
}}
"""


INCREMENTAL_SYSTEM_PROMPT = """你是 NKCN 任务簇增量分析助手。用户已完成一次完整聚类，现仅对「新增且最近使用过的本子」做归属判断。

重要原则：
1. 禁止修改、删除或挪动已有簇内本子；不得从已有簇中移除本子。
2. 可将增量本子加入已有簇（并酌情更新该簇 summary），或新建簇，或归入 unclustered。
3. 同一场景下的本子不一定属于同一任务簇；只有较强任务关联才应聚为一簇。
4. 只输出 JSON，不要 markdown 代码块外的任何文字。"""

INCREMENTAL_USER_PROMPT_TEMPLATE = """已有任务簇（请勿改动其已有本子归属，仅可将下方增量本子加入其中并酌情更新 summary）：
{existing_clusters}

待判定的 {count} 个增量本子（均不在上次分析结果中，且最近使用时间晚于上次分析时间 {analyzed_at}）：
{payload}

对每个增量 notebook_key，三选一：
1. join_existing：归入已有簇 cluster_id，可选 updated_summary 更新该簇一句话描述
2. new_clusters：与现有簇都不够强关联时新建簇
3. unclustered：关联弱则不入簇

输出合法 JSON，格式：
{{
  "join_existing": [
    {{"cluster_id": "c1", "notebook_keys": ["key1"], "updated_summary": "可选"}}
  ],
  "new_clusters": [
    {{"cluster_name": "...", "summary": "...", "notebook_keys": ["key2"]}}
  ],
  "unclustered": [
    {{"notebook_key": "key3", "reason": "..."}}
  ]
}}

要求：
- 每个增量 notebook_key 恰好出现一次；cluster_id 必须来自上方已有簇。
- notebook_keys 使用输入中的 notebook_key 原样。
{compact_hint}
"""


def _progress_path(viewer: str) -> str:
    safe = re.sub(r'[^\w\-.]', '_', viewer or 'unknown')
    return os.path.join(_META_DIR, f'{safe}_progress.json')


def _set_progress(
    viewer: str,
    *,
    percent: int,
    message: str,
    running: bool = True,
    done: bool = False,
    error_num: int = 0,
    msg: str = '',
) -> None:
    os.makedirs(_META_DIR, exist_ok=True)
    payload = {
        'viewer': viewer,
        'percent': max(0, min(100, int(percent))),
        'message': message,
        'running': running,
        'done': done,
        'error_num': error_num,
        'msg': msg,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(_progress_path(viewer), 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def get_task_cluster_progress(viewer_real_name: str) -> Dict[str, Any]:
    viewer = (viewer_real_name or '').strip()
    path = _progress_path(viewer)
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                data['error_num'] = int(data.get('error_num') or 0)
                return data
        except Exception as e:
            print(f'[task_cluster] 读取进度失败: {e}')
    with _running_lock:
        running = viewer in _running_users
    return {
        'viewer': viewer,
        'percent': 0,
        'message': '等待开始' if not running else '分析中',
        'running': running,
        'done': not running,
        'error_num': 0,
        'msg': '',
    }


def is_task_cluster_running(viewer_real_name: str) -> bool:
    with _running_lock:
        return (viewer_real_name or '').strip() in _running_users


def start_task_cluster_analyze_async(
    viewer_real_name: str,
    *,
    force: bool = False,
    mode: str = 'full',
) -> Dict[str, Any]:
    viewer = (viewer_real_name or '').strip()
    if not viewer:
        return {'error_num': 1, 'msg': '缺少用户名'}

    analyze_mode = (mode or 'full').strip().lower()
    if analyze_mode not in ('full', 'incremental'):
        analyze_mode = 'full'

    if analyze_mode == 'incremental':
        cached = load_task_cluster_result(viewer)
        if not cached or cached.get('clusters') is None:
            return {'error_num': 1, 'msg': '无历史分析结果，请先进行完整分析'}
        incremental = _find_incremental_notebooks(viewer, cached)
        if not incremental:
            result = dict(cached)
            result['from_cache'] = True
            result['error_num'] = 0
            result['processed'] = True
            result['incremental_skipped'] = True
            result['started'] = False
            result['running'] = False
            result['msg'] = '没有需要增量分析的本子（无新增或最近使用在上次分析之后的本子）'
            return result
    elif not force:
        cached = load_task_cluster_result(viewer)
        if cached and cached.get('clusters') is not None:
            cached = dict(cached)
            cached['from_cache'] = True
            cached['error_num'] = 0
            cached['processed'] = True
            cached['started'] = False
            cached['running'] = False
            return cached

    with _running_lock:
        if viewer in _running_users:
            prog = get_task_cluster_progress(viewer)
            prog['started'] = False
            prog['running'] = True
            prog['error_num'] = 0
            prog['msg'] = '分析进行中'
            return prog
        _running_users.add(viewer)

    def _job() -> None:
        try:
            label = '增量分析' if analyze_mode == 'incremental' else '任务簇分析'
            _set_progress(viewer, percent=1, message=f'正在启动{label}…', running=True, done=False)
            result = analyze_task_clusters(viewer, force=force, mode=analyze_mode)
            if int(result.get('error_num') or 0) != 0:
                _set_progress(
                    viewer,
                    percent=0,
                    message=result.get('msg') or '分析失败',
                    running=False,
                    done=True,
                    error_num=1,
                    msg=result.get('msg') or '分析失败',
                )
            else:
                _set_progress(viewer, percent=100, message='分析完成', running=False, done=True)
        except Exception as e:
            print(f'[task_cluster] 异步分析异常: {e}')
            traceback.print_exc()
            _set_progress(
                viewer,
                percent=0,
                message=str(e),
                running=False,
                done=True,
                error_num=1,
                msg=str(e),
            )
        finally:
            with _running_lock:
                _running_users.discard(viewer)

    threading.Thread(target=_job, daemon=True).start()
    _set_progress(viewer, percent=2, message='已提交分析任务…', running=True, done=False)
    return {'error_num': 0, 'started': True, 'running': True, 'msg': '已开始分析'}


def _meta_path(viewer: str) -> str:
    safe = re.sub(r'[^\w\-.]', '_', viewer or 'unknown')
    return os.path.join(_META_DIR, f'{safe}.json')


def _scene_name_by_sid(sid: int) -> str:
    try:
        obj = scene.objects.filter(sid=sid).first()
        return (obj.sceneDescription or '').strip() if obj else ''
    except Exception:
        return ''


def _format_book_id(book_id: str) -> str:
    raw = str(book_id or '').strip()
    if not raw:
        return '未知'
    try:
        num = int(raw)
        if num > 1_000_000_000_000:
            num = num / 1000.0
        return datetime.fromtimestamp(num).strftime('%Y年%m月%d日 %H:%M')
    except Exception:
        return raw


def _list_doc_filenames(full_username: str, limit: int = 50) -> List[str]:
    base = os.path.join('.', 'received_dir', 'user_raw_file', full_username)
    if not os.path.isdir(base):
        return []
    names: List[str] = []
    for name in sorted(os.listdir(base)):
        if name in _SKIP_DOC_DIRS:
            continue
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in _DOC_EXTS:
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return names


def _colored_shallow_card_titles(full_username: str, limit: int = _COLORED_CARD_LIMIT) -> List[str]:
    try:
        qs = (
            Card.objects.filter(username=full_username)
            .exclude(contentTitle__isnull=True)
            .exclude(contentTitle='')
            .order_by('-datetime')
        )
        out: List[str] = []
        for card in qs[: limit * 3]:
            color = (card.color or '紫').strip()
            color_sft = (card.colorSFT or '紫').strip()
            four = (card.four_color_type or '').strip()
            if color == '紫' and color_sft == '紫' and not four:
                continue
            title = str(card.contentTitle or '').strip()
            if title and title not in out:
                out.append(title)
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def _card_count_for_notebook(full_username: str) -> int:
    try:
        return Card.objects.filter(username=full_username).count()
    except Exception:
        return 0


def _batch_card_counts(notebook_keys: List[str]) -> Dict[str, int]:
    """一次 SQL 批量统计多个本子的页数，避免 N 次 count 查询。"""
    keys = list({str(k).strip() for k in notebook_keys if str(k).strip()})
    if not keys:
        return {}
    try:
        rows = (
            Card.objects.filter(username__in=keys)
            .values('username')
            .annotate(count=Count('cid'))
        )
        return {row['username']: int(row['count']) for row in rows}
    except Exception as e:
        print(f'[task_cluster] 批量统计页数失败: {e}')
        return {}


def _collect_all_known_keys_from_payload(payload: Dict[str, Any]) -> set:
    known: set = set()
    for cl in payload.get('clusters') or []:
        for k in cl.get('notebook_keys') or []:
            key = str(k).strip()
            if key:
                known.add(key)
        for nb in cl.get('notebooks') or []:
            key = str(nb.get('notebook_key') or nb.get('full_username') or '').strip()
            if key:
                known.add(key)
    for item in payload.get('unclustered') or []:
        key = str(item.get('notebook_key') or '').strip()
        if key:
            known.add(key)
        nb = item.get('notebook')
        if isinstance(nb, dict):
            key = str(nb.get('notebook_key') or nb.get('full_username') or '').strip()
            if key:
                known.add(key)
    return known


def _parse_analyzed_at_ts(analyzed_at: str) -> float:
    text = str(analyzed_at or '').strip()
    if not text:
        return 0.0
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y年%m月%d日 %H:%M'):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except Exception:
            continue
    return 0.0


def _find_incremental_notebooks(
    viewer_real_name: str,
    cached_payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """上次分析后新增、且最近使用时间晚于 analyzed_at 的本子。"""
    analyzed_ts = _parse_analyzed_at_ts(cached_payload.get('analyzed_at') or '')
    known_keys = _collect_all_known_keys_from_payload(cached_payload)
    incremental: List[Dict[str, Any]] = []
    for nb in get_accessible_notebooks(viewer_real_name):
        key = str(nb.get('notebook_key') or '').strip()
        if not key or key in known_keys:
            continue
        if _notebook_recency_ts(nb) > analyzed_ts:
            incremental.append(nb)
    return incremental


def _summarize_existing_clusters_for_incremental(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    for cl in payload.get('clusters') or []:
        cid = cl.get('cluster_id') or ''
        name = cl.get('cluster_name') or ''
        summary = cl.get('summary') or ''
        keys = _notebook_keys_in_cluster(cl)
        lines.append(
            f'- [{cid}] {name}: summary={summary}; '
            f'已有本子={json.dumps(keys, ensure_ascii=False)}'
        )
    return '\n'.join(lines) if lines else '（无已有簇）'


def _build_incremental_prompt(
    cached_payload: Dict[str, Any],
    incremental_notebooks: List[Dict[str, Any]],
) -> str:
    count = len(incremental_notebooks)
    return INCREMENTAL_USER_PROMPT_TEMPLATE.format(
        existing_clusters=_summarize_existing_clusters_for_incremental(cached_payload),
        count=count,
        analyzed_at=cached_payload.get('analyzed_at') or '未知',
        compact_hint=_compact_hint(count),
        payload=_build_llm_payload(incremental_notebooks),
    )


def _apply_incremental_to_payload(
    viewer: str,
    payload: Dict[str, Any],
    incremental_notebooks: List[Dict[str, Any]],
    parsed: Dict[str, Any],
) -> Dict[str, Any]:
    nb_map = {nb['notebook_key']: nb for nb in incremental_notebooks}
    inc_keys = set(nb_map.keys())
    assigned: set = set()
    out = copy.deepcopy(payload)

    cluster_by_id = {
        str(cl.get('cluster_id') or '').strip(): cl
        for cl in (out.get('clusters') or [])
        if str(cl.get('cluster_id') or '').strip()
    }

    for item in parsed.get('join_existing') or []:
        cid = str(item.get('cluster_id') or '').strip()
        cl = cluster_by_id.get(cid)
        if not cl:
            continue
        keys_in_cluster = set(_notebook_keys_in_cluster(cl))
        for k in item.get('notebook_keys') or []:
            key = str(k).strip()
            if key not in nb_map:
                continue
            assigned.add(key)
            if key not in keys_in_cluster:
                cl.setdefault('notebook_keys', []).append(key)
                cl.setdefault('notebooks', []).append(nb_map[key])
                keys_in_cluster.add(key)
        updated_summary = (item.get('updated_summary') or '').strip()
        if updated_summary:
            cl['summary'] = updated_summary

    base_ts = int(datetime.now().timestamp())
    for idx, item in enumerate(parsed.get('new_clusters') or [], 1):
        keys = [str(k).strip() for k in (item.get('notebook_keys') or []) if str(k).strip()]
        items: List[Dict[str, Any]] = []
        valid_keys: List[str] = []
        for key in keys:
            if key in nb_map:
                assigned.add(key)
                valid_keys.append(key)
                items.append(nb_map[key])
        if not valid_keys:
            continue
        new_cluster = {
            'cluster_id': f'i{base_ts}_{idx}',
            'cluster_name': (item.get('cluster_name') or f'新任务簇{idx}').strip(),
            'summary': (item.get('summary') or '').strip(),
            'notebook_keys': valid_keys,
            'notebooks': items,
        }
        out.setdefault('clusters', []).append(new_cluster)
        cluster_by_id[new_cluster['cluster_id']] = new_cluster

    for item in parsed.get('unclustered') or []:
        key = str(item.get('notebook_key') or '').strip()
        if key in nb_map:
            assigned.add(key)
            out.setdefault('unclustered', []).append({
                'notebook_key': key,
                'reason': (item.get('reason') or '').strip(),
                'notebook': nb_map[key],
            })

    missing = inc_keys - assigned
    for key in sorted(missing):
        out.setdefault('unclustered', []).append({
            'notebook_key': key,
            'reason': '增量分析未覆盖，自动归入未强关联',
            'notebook': nb_map[key],
        })

    out['analyzed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    out['notebook_count'] = len(get_accessible_notebooks(viewer))
    counts = _batch_card_counts(_collect_notebook_keys_from_payload(out))
    _apply_card_counts(out, counts)
    return out


def _collect_notebook_keys_from_payload(payload: Dict[str, Any]) -> List[str]:
    keys: List[str] = []
    for cl in payload.get('clusters') or []:
        for nb in cl.get('notebooks') or []:
            key = str(nb.get('notebook_key') or nb.get('full_username') or '').strip()
            if key:
                keys.append(key)
    for item in payload.get('unclustered') or []:
        nb = item.get('notebook')
        if isinstance(nb, dict):
            key = str(nb.get('notebook_key') or nb.get('full_username') or '').strip()
            if key:
                keys.append(key)
    return keys


def _apply_card_counts(payload: Dict[str, Any], counts: Dict[str, int]) -> None:
    for cl in payload.get('clusters') or []:
        for nb in cl.get('notebooks') or []:
            key = str(nb.get('notebook_key') or nb.get('full_username') or '').strip()
            if key:
                nb['cardNum'] = counts.get(key, 0)
    for item in payload.get('unclustered') or []:
        nb = item.get('notebook')
        if isinstance(nb, dict):
            key = str(nb.get('notebook_key') or nb.get('full_username') or '').strip()
            if key:
                nb['cardNum'] = counts.get(key, 0)


def get_accessible_notebooks(viewer_real_name: str) -> List[Dict[str, Any]]:
    """用户为作者或组本协作者可访问的全部本子。"""
    viewer = (viewer_real_name or '').strip()
    if not viewer:
        return []
    try:
        qs = UserNotebook.objects.filter(
            Q(username=viewer) |
            Q(writer=viewer) |
            Q(syncUsers__regex=r'(^|,\s*)' + re.escape(viewer) + r'(\s*,|$)')
        ).defer('context_data')
    except Exception as e:
        print(f'[task_cluster] 查询本子失败: {e}')
        return []

    seen_keys = set()
    out: List[Dict[str, Any]] = []
    skipped_writer = 0
    skipped_scene = 0
    skipped_shared_copy = 0
    for nb in qs:
        full = f'{nb.username}_{nb.bookName}'
        if full in seen_keys:
            continue
        seen_keys.add(full)

        writer = (nb.writer or '').strip()
        if not writer:
            skipped_writer += 1
            print(f'[task_cluster] 跳过 writer 为空: {full}')
            continue

        scene_name = (_scene_name_by_sid(nb.sid) or '').strip()
        if not scene_name:
            skipped_scene += 1
            print(f'[task_cluster] 跳过 sid={nb.sid} 无对应场景: {full}')
            continue

        username = (nb.username or '').strip()
        sync_users_raw = (nb.syncUsers or '').strip()
        if username != writer and writer == viewer and not sync_users_raw:
            skipped_shared_copy += 1
            print(
                f'[task_cluster] 跳过分享副本(username={username}, writer={writer}, 非组本): {full}'
            )
            continue

        sync_list = [u.strip() for u in sync_users_raw.split(',') if u.strip()]
        if writer == viewer or (nb.username or '').strip() == viewer:
            viewer_role = 'author'
        elif viewer in sync_list:
            viewer_role = 'collaborator'
        else:
            viewer_role = 'other'
        out.append({
            'notebook_key': full,
            'full_username': full,
            'bookName': nb.bookName,
            'title': nb.bookName,
            'bookdescription': (nb.bookdescription or nb.bookName or '').strip(),
            'description': (nb.bookdescription or nb.bookName or '').strip(),
            'scene_name': scene_name,
            'sid': nb.sid,
            'writer': writer,
            'username': nb.username,
            'role': viewer_role,
            'last_used': _format_book_id(nb.bookId),
            'bookId': nb.bookId,
            'id': nb.bookId,
            'syncUsers': nb.syncUsers or '',
            'isShared': int(getattr(nb, 'isShared', 0) or 0),
            'documents': _list_doc_filenames(full),
            'colored_card_titles': _colored_shallow_card_titles(full),
            'cardNum': _card_count_for_notebook(full),
        })
    out.sort(key=lambda x: (x.get('scene_name', ''), x.get('bookdescription', '')))
    print(
        f'[task_cluster] 用户 {viewer} 可分析本子 {len(out)} 个'
        f'（跳过 writer 空 {skipped_writer}，sid 无场景 {skipped_scene}，'
        f'分享副本 {skipped_shared_copy}）'
    )
    return out


def _format_list_field(items: List[str], show_max: int, label: str) -> Tuple[str, str]:
    """适度展示长列表：前列全展示 + 显式注明未列出数量（非暴力截断）。"""
    vals = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not vals:
        return f'（无{label}）', ''
    if len(vals) <= show_max:
        return '、'.join(vals), ''
    shown = '、'.join(vals[:show_max])
    extra_line = (
        f'   {label}_另有={len(vals) - show_max}项未列出'
        f'（完整共{len(vals)}项，已展示前{show_max}项）'
    )
    return shown, extra_line


def _build_llm_payload(notebooks: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for i, nb in enumerate(notebooks, 1):
        docs, docs_extra = _format_list_field(nb.get('documents') or [], _DOC_SHOW_MAX, 'documents')
        titles, titles_extra = _format_list_field(
            nb.get('colored_card_titles') or [], _CARD_SHOW_MAX, 'colored_card_titles'
        )
        block = (
            f'{i}. notebook_key={nb["notebook_key"]}\n'
            f'   bookdescription={nb["bookdescription"]}\n'
            f'   scene_name={nb["scene_name"]}\n'
            f'   role={nb["role"]}\n'
            f'   writer={nb["writer"]}\n'
            f'   last_used={nb["last_used"]}\n'
            f'   documents={docs}\n'
            f'   colored_card_titles={titles}'
        )
        if docs_extra:
            block += f'\n{docs_extra}'
        if titles_extra:
            block += f'\n{titles_extra}'
        lines.append(block)
    return '\n\n'.join(lines)


def _compact_hint(notebook_count: int) -> str:
    return COMPACT_OUTPUT_HINT if notebook_count > 30 else ''


def _max_tokens_for_count(notebook_count: int, *, is_gemini: bool) -> int:
    estimated = 3000 + notebook_count * 140
    cap = _GEMINI_MAX_TOKENS if is_gemini else _CLAUDE_MAX_TOKENS
    return min(cap, max(8192, estimated))


def _build_user_prompt(notebooks: List[Dict[str, Any]]) -> str:
    count = len(notebooks)
    return USER_PROMPT_TEMPLATE.format(
        count=count,
        compact_hint=_compact_hint(count),
        payload=_build_llm_payload(notebooks),
    )


def _primary_slot_abbr() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('task_cluster_semantic', _GEMINI_DEFAULT)


def _alternate_slot_abbr(primary: str) -> str:
    p = str(primary or '').strip().lower()
    if p.startswith('gemini'):
        return _OPUS_DEFAULT
    return _GEMINI_DEFAULT


def _resolve_model_slot(abbr: str) -> Tuple[Dict[str, str], str, bool]:
    from app_chat.scene_models import _dmxapi_default_cfg, resolve_openai_cfg_from_abbr

    slot = str(abbr or '').strip()
    is_gemini = slot.startswith('gemini')
    if is_gemini:
        cfg = _dmxapi_default_cfg(slot)
    else:
        cfg = resolve_openai_cfg_from_abbr(slot)
    return cfg, slot, is_gemini


def _extract_completion_text(rsp: Any) -> str:
    choices = getattr(rsp, 'choices', None) or []
    if not choices:
        return ''
    msg = choices[0].message
    for attr in ('content', 'reasoning_content'):
        val = getattr(msg, attr, None)
        if val:
            text = str(val).strip()
            if text:
                return text
    try:
        dumped = msg.model_dump() if hasattr(msg, 'model_dump') else {}
        for key in ('content', 'reasoning_content'):
            val = dumped.get(key)
            if val:
                text = str(val).strip()
                if text:
                    return text
    except Exception:
        pass
    return ''


def _finish_reason_of(rsp: Any) -> str:
    try:
        choices = getattr(rsp, 'choices', None) or []
        if choices:
            return str(getattr(choices[0], 'finish_reason', '') or '')
    except Exception:
        pass
    return ''


def _strip_json_fence(raw: str) -> str:
    clean = (raw or '').strip()
    if not clean.startswith('```'):
        return clean
    lines = clean.splitlines()
    if lines and lines[0].strip().startswith('```'):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith('```'):
        lines = lines[:-1]
    return '\n'.join(lines).strip()


def _extract_first_json_object(raw: str) -> Optional[str]:
    text = _strip_json_fence(raw)
    start = text.find('{')
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def _extract_json(text: str) -> Dict[str, Any]:
    raw = (text or '').strip()
    if not raw:
        raise ValueError('模型返回空文本，无法解析 JSON')
    errors: List[Exception] = []
    for candidate in (raw, _strip_json_fence(raw)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            errors.append(e)
    fenced = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', raw)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError as e:
            errors.append(e)
    blob = _extract_first_json_object(raw)
    if blob:
        try:
            return json.loads(blob)
        except json.JSONDecodeError as e:
            errors.append(e)
    detail = str(errors[-1]) if errors else 'unknown'
    raise ValueError(f'JSON 解析失败: {detail}')


def _repair_json_via_llm(
    client: OpenAI,
    *,
    model: str,
    broken_text: str,
    notebook_count: int,
    is_gemini: bool,
    max_tokens: int,
) -> str:
    repair_prompt = (
        '以下 JSON 不完整或被截断。请补全为合法 JSON，覆盖全部 notebook_key，'
        '只输出 JSON，不要 markdown：\n'
        f'{broken_text[-12000:]}'
    )
    rsp = _create_chat_completion(
        client,
        model=model,
        messages=[{'role': 'user', 'content': repair_prompt}],
        max_tokens=max_tokens,
        temperature=0.0,
        use_json_mode=is_gemini,
    )
    text = _extract_completion_text(rsp)
    finish = _finish_reason_of(rsp)
    print(f'[task_cluster] JSON 修复返回长度 {len(text)} finish_reason={finish}')
    return text


def _create_chat_completion(
    client: OpenAI,
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
    use_json_mode: bool,
) -> Any:
    kwargs: Dict[str, Any] = {
        'model': model,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }
    if use_json_mode:
        kwargs['response_format'] = {'type': 'json_object'}
    try:
        return client.chat.completions.create(**kwargs)
    except Exception:
        if use_json_mode:
            kwargs.pop('response_format', None)
            return client.chat.completions.create(**kwargs)
        raise


def _call_llm_with_slot(
    user_prompt: str,
    *,
    notebook_count: int,
    slot_abbr: str,
    system_prompt: str = SYSTEM_PROMPT,
) -> Tuple[str, str, str]:
    cfg, model_label, is_gemini = _resolve_model_slot(slot_abbr)
    max_tokens = _max_tokens_for_count(notebook_count, is_gemini=is_gemini)
    client = OpenAI(
        api_key=cfg['api_key'],
        base_url=str(cfg['base_url']).rstrip('/') + '/',
        timeout=300.0,
    )
    messages: List[Dict[str, str]] = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]

    last_error = ''
    for attempt in range(2):
        attempt_messages = messages
        if is_gemini and attempt == 1:
            attempt_messages = [{
                'role': 'user',
                'content': f'{system_prompt}\n\n{user_prompt}',
            }]
        try:
            rsp = _create_chat_completion(
                client,
                model=cfg['model'],
                messages=attempt_messages,
                max_tokens=max_tokens,
                temperature=0.2,
                use_json_mode=is_gemini,
            )
        except Exception as e:
            last_error = str(e)
            print(f'[task_cluster] 模型 {model_label} 调用失败: {e}')
            continue

        text = _extract_completion_text(rsp)
        finish = _finish_reason_of(rsp)
        if text:
            return text, model_label, finish
        last_error = f'empty_model_output finish_reason={finish}'
        print(f'[task_cluster] 模型 {model_label} 返回空 finish_reason={finish}')

    raise RuntimeError(last_error or f'{model_label} 调用失败')


def _call_llm_once(
    user_prompt: str,
    *,
    notebook_count: int,
    system_prompt: str = SYSTEM_PROMPT,
) -> Tuple[str, str, str]:
    """主模型失败则切换 gemini <-> claude-opus-4.8。"""
    primary = _primary_slot_abbr()
    alternate = _alternate_slot_abbr(primary)
    errors: List[str] = []

    for slot in (primary, alternate):
        try:
            text, label, finish = _call_llm_with_slot(
                user_prompt,
                notebook_count=notebook_count,
                slot_abbr=slot,
                system_prompt=system_prompt,
            )
            if text:
                if slot != primary:
                    print(f'[task_cluster] 主模型 {primary} 未成功，已切换 {slot}')
                return text, label, finish
        except Exception as e:
            errors.append(f'{slot}: {e}')
            print(f'[task_cluster] 模型 {slot} 失败: {e}')

    raise RuntimeError('; '.join(errors) or 'all_models_failed')


def _parse_llm_json_response(
    raw_text: str,
    *,
    notebook_count: int,
    model_label: str,
    finish_reason: str,
    user_prompt: str = '',
) -> Dict[str, Any]:
    try:
        return _extract_json(raw_text)
    except (ValueError, json.JSONDecodeError) as first_err:
        print(
            f'[task_cluster] JSON 解析失败(len={len(raw_text)}, '
            f'finish_reason={finish_reason}): {first_err}'
        )

    primary = _primary_slot_abbr()
    alternate = _alternate_slot_abbr(primary)
    repair_slots = [primary, alternate]

    for slot in repair_slots:
        cfg, label, is_gemini = _resolve_model_slot(slot)
        client = OpenAI(
            api_key=cfg['api_key'],
            base_url=str(cfg['base_url']).rstrip('/') + '/',
            timeout=300.0,
        )
        max_tokens = _max_tokens_for_count(notebook_count, is_gemini=is_gemini)
        repaired = _repair_json_via_llm(
            client,
            model=cfg['model'],
            broken_text=raw_text,
            notebook_count=notebook_count,
            is_gemini=is_gemini,
            max_tokens=max_tokens,
        )
        if repaired:
            try:
                return _extract_json(repaired)
            except (ValueError, json.JSONDecodeError) as repair_err:
                print(f'[task_cluster] {label} JSON 修复后仍失败: {repair_err}')

        retry_prompt = (
            '上次输出 JSON 不完整。请重新输出完整合法 JSON，'
            f'必须覆盖全部 {notebook_count} 个 notebook_key。\n'
            f'截断片段：\n{raw_text[-6000:]}'
        )
        if user_prompt:
            retry_prompt = f'{user_prompt}\n\n{retry_prompt}'
        try:
            text, _, _ = _call_llm_with_slot(
                retry_prompt,
                notebook_count=notebook_count,
                slot_abbr=slot,
            )
            if text:
                return _extract_json(text)
        except Exception as e:
            print(f'[task_cluster] {label} 重生成 JSON 失败: {e}')

    raise ValueError(f'JSON 解析与修复均失败: {first_err}')


def _call_llm(user_prompt: str, *, notebook_count: int) -> Tuple[str, str]:
    text, model_label, _finish = _call_llm_once(user_prompt, notebook_count=notebook_count)
    return text, model_label


def _summarize_batch_for_merge(parsed: Dict[str, Any], batch_no: int) -> str:
    lines = [f'--- 第{batch_no}批 ---']
    for cl in parsed.get('clusters') or []:
        keys = cl.get('notebook_keys') or []
        lines.append(
            f'簇 {cl.get("cluster_name")}: keys={json.dumps(keys, ensure_ascii=False)}; '
            f'summary={cl.get("summary", "")}'
        )
    for item in parsed.get('unclustered') or []:
        lines.append(
            f'未聚类 {item.get("notebook_key")}: {item.get("reason", "")}'
        )
    return '\n'.join(lines)


def _cluster_one_batch(
    batch_idx: int,
    batch: List[Dict[str, Any]],
    total_batches: int,
    viewer: str,
) -> Tuple[int, str, str]:
    prompt = _build_user_prompt(batch)
    raw_text, model_label, finish = _call_llm_once(prompt, notebook_count=len(batch))
    print(
        f'[task_cluster] 第{batch_idx}/{total_batches}批 模型 {model_label} '
        f'返回长度 {len(raw_text)} finish_reason={finish}'
    )
    parsed = _parse_llm_json_response(
        raw_text,
        notebook_count=len(batch),
        model_label=model_label,
        finish_reason=finish,
        user_prompt=prompt,
    )
    summary = _summarize_batch_for_merge(parsed, batch_idx)
    pct = 10 + int(55 * batch_idx / max(total_batches, 1))
    _set_progress(
        viewer,
        percent=pct,
        message=f'第 {batch_idx}/{total_batches} 批聚类完成',
        running=True,
        done=False,
    )
    return batch_idx, summary, model_label


def _cluster_notebooks_batched(
    notebooks: List[Dict[str, Any]],
    viewer: str,
) -> Tuple[Dict[str, Any], str]:
    batches = [
        notebooks[i:i + _BATCH_CLUSTER_SIZE]
        for i in range(0, len(notebooks), _BATCH_CLUSTER_SIZE)
    ]
    total_batches = len(batches)
    print(
        f'[task_cluster] 大批量分 {total_batches} 批处理，'
        f'每批最多 {_BATCH_CLUSTER_SIZE} 本，并发 {_BATCH_MAX_WORKERS}'
    )
    _set_progress(
        viewer,
        percent=8,
        message=f'共 {len(notebooks)} 本，分 {total_batches} 批并行聚类…',
        running=True,
        done=False,
    )

    ordered_summaries: List[Optional[str]] = [None] * total_batches
    model_label = _primary_slot_abbr()

    with ThreadPoolExecutor(max_workers=_BATCH_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_cluster_one_batch, idx, batch, total_batches, viewer): idx
            for idx, batch in enumerate(batches, 1)
        }
        for future in as_completed(futures):
            batch_idx, summary, used_model = future.result()
            ordered_summaries[batch_idx - 1] = summary
            model_label = used_model

    batch_summaries = [s for s in ordered_summaries if s]

    _set_progress(viewer, percent=72, message='各批聚类完成，正在合并任务簇…', running=True, done=False)
    all_keys = '\n'.join(f'- {nb["notebook_key"]}' for nb in notebooks)
    merge_prompt = MERGE_PROMPT_TEMPLATE.format(
        count=len(notebooks),
        compact_hint=_compact_hint(len(notebooks)),
        all_keys=all_keys,
        batch_payload='\n\n'.join(batch_summaries),
    )
    raw_text, model_label, finish = _call_llm_once(
        merge_prompt,
        notebook_count=len(notebooks),
        system_prompt='你是任务簇合并助手。合并多批聚类结果，输出单一完整 JSON。',
    )
    print(
        f'[task_cluster] 合并阶段 模型 {model_label} 返回长度 {len(raw_text)} '
        f'finish_reason={finish}'
    )
    _set_progress(viewer, percent=88, message='合并结果解析中…', running=True, done=False)
    parsed = _parse_llm_json_response(
        raw_text,
        notebook_count=len(notebooks),
        model_label=model_label,
        finish_reason=finish,
        user_prompt=merge_prompt,
    )
    return parsed, model_label


def _enrich_clusters(
    parsed: Dict[str, Any],
    notebooks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    nb_map = {nb['notebook_key']: nb for nb in notebooks}
    all_keys = set(nb_map.keys())
    used: set = set()

    clusters_out: List[Dict[str, Any]] = []
    for idx, cl in enumerate(parsed.get('clusters') or [], 1):
        keys = [str(k).strip() for k in (cl.get('notebook_keys') or []) if str(k).strip()]
        items = []
        for k in keys:
            if k in nb_map:
                items.append(nb_map[k])
                used.add(k)
        clusters_out.append({
            'cluster_id': cl.get('cluster_id') or f'c{idx}',
            'cluster_name': (cl.get('cluster_name') or f'任务簇{idx}').strip(),
            'summary': (cl.get('summary') or '').strip(),
            'notebook_keys': keys,
            'notebooks': items,
        })

    unclustered_out: List[Dict[str, Any]] = []
    for item in parsed.get('unclustered') or []:
        k = str(item.get('notebook_key') or '').strip()
        if k in nb_map:
            unclustered_out.append({
                'notebook_key': k,
                'reason': (item.get('reason') or '').strip(),
                'notebook': nb_map[k],
            })
            used.add(k)

    missing = all_keys - used
    for k in sorted(missing):
        unclustered_out.append({
            'notebook_key': k,
            'reason': '模型输出未覆盖，自动归入未聚类',
            'notebook': nb_map[k],
        })

    return {
        'clusters': clusters_out,
        'unclustered': unclustered_out,
    }


def refresh_cluster_card_nums(payload: Dict[str, Any]) -> Dict[str, Any]:
    """读取缓存时刷新页数，避免旧结果 cardNum 为 0。"""
    if not isinstance(payload, dict):
        return payload
    counts = _batch_card_counts(_collect_notebook_keys_from_payload(payload))
    _apply_card_counts(payload, counts)
    return payload


def _read_task_cluster_payload_raw(viewer_real_name: str) -> Optional[Dict[str, Any]]:
    path = _meta_path(viewer_real_name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f'[task_cluster] 读取缓存失败: {e}')
        return None


def _notebook_recency_ts(nb: Dict[str, Any]) -> float:
    """本子最近使用时间戳，越大越近。优先 bookId。"""
    if not isinstance(nb, dict):
        return 0.0
    raw = nb.get('bookId')
    if raw is not None and str(raw).strip():
        try:
            num = float(str(raw).strip())
            if num > 1_000_000_000_000:
                num = num / 1000.0
            return num
        except Exception:
            pass
    last_used = str(nb.get('last_used') or '').strip()
    if last_used and last_used != '未知':
        for fmt in ('%Y年%m月%d日 %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(last_used, fmt).timestamp()
            except Exception:
                continue
    return 0.0


def _cluster_max_recency(cluster: Dict[str, Any]) -> float:
    nbs = cluster.get('notebooks') or []
    if not nbs:
        return 0.0
    return max(_notebook_recency_ts(nb) for nb in nbs)


def sort_clusters_by_recency(payload: Dict[str, Any]) -> Dict[str, Any]:
    """按簇内最近使用时间最晚的本子排序，越近越靠前。"""
    if not isinstance(payload, dict):
        return payload
    clusters = list(payload.get('clusters') or [])
    clusters.sort(key=_cluster_max_recency, reverse=True)
    payload['clusters'] = clusters
    return payload


def load_task_cluster_result(
    viewer_real_name: str,
    *,
    refresh_card_nums: bool = True,
) -> Optional[Dict[str, Any]]:
    data = _read_task_cluster_payload_raw(viewer_real_name)
    if not data:
        return None
    if refresh_card_nums:
        data = refresh_cluster_card_nums(data)
    return sort_clusters_by_recency(data)


def save_task_cluster_result(viewer_real_name: str, payload: Dict[str, Any]) -> None:
    os.makedirs(_META_DIR, exist_ok=True)
    sort_clusters_by_recency(payload)
    path = _meta_path(viewer_real_name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def analyze_task_clusters(
    viewer_real_name: str,
    *,
    force: bool = False,
    mode: str = 'full',
) -> Dict[str, Any]:
    viewer = (viewer_real_name or '').strip()
    if not viewer:
        return {'error_num': 1, 'msg': '缺少用户名'}

    analyze_mode = (mode or 'full').strip().lower()
    if analyze_mode not in ('full', 'incremental'):
        analyze_mode = 'full'

    if analyze_mode == 'incremental':
        return _analyze_task_clusters_incremental(viewer)

    if not force:
        cached = load_task_cluster_result(viewer)
        if cached and cached.get('clusters') is not None:
            cached = dict(cached)
            cached['from_cache'] = True
            cached['error_num'] = 0
            cached['processed'] = True
            return cached

    notebooks = get_accessible_notebooks(viewer)
    if not notebooks:
        payload = {
            'version': 1,
            'viewer': viewer,
            'analyzed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'model': '',
            'notebook_count': 0,
            'clusters': [],
            'unclustered': [],
            'error_num': 0,
            'msg': '没有可分析的本子',
        }
        save_task_cluster_result(viewer, payload)
        return payload

    if len(notebooks) == 1:
        nb = notebooks[0]
        payload = {
            'version': 1,
            'viewer': viewer,
            'analyzed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'model': 'rule',
            'notebook_count': 1,
            'clusters': [{
                'cluster_id': 'c1',
                'cluster_name': nb['bookdescription'] or '唯一本子',
                'summary': '仅有一个本子，自动成簇',
                'notebook_keys': [nb['notebook_key']],
                'notebooks': [nb],
            }],
            'unclustered': [],
            'error_num': 0,
        }
        save_task_cluster_result(viewer, payload)
        return payload

    try:
        n = len(notebooks)
        _set_progress(viewer, percent=5, message=f'已汇总 {n} 个本子，准备聚类…', running=True, done=False)
        if n > _BATCH_CLUSTER_THRESHOLD:
            parsed, model_label = _cluster_notebooks_batched(notebooks, viewer)
        else:
            user_prompt = _build_user_prompt(notebooks)
            _set_progress(viewer, percent=12, message='正在调用语义梳理模型…', running=True, done=False)
            raw_text, model_label, finish = _call_llm_once(user_prompt, notebook_count=n)
            print(
                f'[task_cluster] 模型 {model_label} 返回长度 {len(raw_text)} '
                f'finish_reason={finish}'
            )
            _set_progress(viewer, percent=70, message='模型返回完成，正在解析结果…', running=True, done=False)
            parsed = _parse_llm_json_response(
                raw_text,
                notebook_count=n,
                model_label=model_label,
                finish_reason=finish,
                user_prompt=user_prompt,
            )
        _set_progress(viewer, percent=92, message='正在整理任务簇视图数据…', running=True, done=False)
        enriched = _enrich_clusters(parsed, notebooks)
        payload = {
            'version': 1,
            'viewer': viewer,
            'analyzed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'model': model_label,
            'notebook_count': len(notebooks),
            **enriched,
            'error_num': 0,
        }
        save_task_cluster_result(viewer, payload)
        print(
            f'[task_cluster] 完成 viewer={viewer} '
            f'clusters={len(payload["clusters"])} unclustered={len(payload["unclustered"])}'
        )
        return payload
    except Exception as e:
        print(f'[task_cluster] 分析失败: {e}')
        traceback.print_exc()
        return {
            'error_num': 1,
            'msg': str(e),
            'viewer': viewer,
        }


def _analyze_task_clusters_incremental(viewer: str) -> Dict[str, Any]:
    cached = load_task_cluster_result(viewer, refresh_card_nums=True)
    if not cached or cached.get('clusters') is None:
        return {'error_num': 1, 'msg': '无历史分析结果，请先进行完整分析'}

    incremental = _find_incremental_notebooks(viewer, cached)
    if not incremental:
        result = dict(cached)
        result['error_num'] = 0
        result['processed'] = True
        result['from_cache'] = True
        result['incremental_skipped'] = True
        result['msg'] = '没有需要增量分析的本子（无新增或最近使用在上次分析之后的本子）'
        return result

    try:
        n = len(incremental)
        _set_progress(
            viewer,
            percent=8,
            message=f'发现 {n} 个增量本子，准备归属判断…',
            running=True,
            done=False,
        )
        user_prompt = _build_incremental_prompt(cached, incremental)
        _set_progress(viewer, percent=15, message='正在调用语义梳理模型（增量）…', running=True, done=False)
        raw_text, model_label, finish = _call_llm_once(
            user_prompt,
            notebook_count=n,
            system_prompt=INCREMENTAL_SYSTEM_PROMPT,
        )
        print(
            f'[task_cluster] 增量分析 模型 {model_label} 返回长度 {len(raw_text)} '
            f'finish_reason={finish}'
        )
        _set_progress(viewer, percent=75, message='增量结果解析中…', running=True, done=False)
        parsed = _parse_llm_json_response(
            raw_text,
            notebook_count=n,
            model_label=model_label,
            finish_reason=finish,
            user_prompt=user_prompt,
        )
        _set_progress(viewer, percent=90, message='正在合并增量归属…', running=True, done=False)
        merged = _apply_incremental_to_payload(viewer, cached, incremental, parsed)
        merged['model'] = model_label
        merged['error_num'] = 0
        merged['processed'] = True
        merged['incremental'] = True
        save_task_cluster_result(viewer, merged)
        print(
            f'[task_cluster] 增量完成 viewer={viewer} '
            f'新增处理={n} clusters={len(merged.get("clusters") or [])}'
        )
        return merged
    except Exception as e:
        print(f'[task_cluster] 增量分析失败: {e}')
        traceback.print_exc()
        return {
            'error_num': 1,
            'msg': str(e),
            'viewer': viewer,
        }


def update_cluster_meta(
    viewer_real_name: str,
    cluster_id: str,
    *,
    cluster_name: Optional[str] = None,
    summary: Optional[str] = None,
) -> Dict[str, Any]:
    viewer = (viewer_real_name or '').strip()
    cid = (cluster_id or '').strip()
    if not viewer or not cid:
        return {'error_num': 1, 'msg': '缺少用户名或任务簇 ID'}
    payload = load_task_cluster_result(viewer, refresh_card_nums=False)
    if not payload:
        return {'error_num': 1, 'msg': '无任务簇缓存，请先分析'}
    found = False
    for cl in payload.get('clusters') or []:
        if cl.get('cluster_id') == cid:
            if cluster_name is not None:
                cl['cluster_name'] = (cluster_name or '').strip()
            if summary is not None:
                cl['summary'] = (summary or '').strip()
            found = True
            break
    if not found:
        return {'error_num': 1, 'msg': '未找到任务簇'}
    payload['manually_edited'] = True
    save_task_cluster_result(viewer, payload)
    result = dict(payload)
    result['error_num'] = 0
    result['processed'] = True
    return result


def _find_notebook_obj_in_payload(payload: Dict[str, Any], nb_key: str) -> Optional[Dict[str, Any]]:
    key = (nb_key or '').strip()
    if not key:
        return None
    for cl in payload.get('clusters') or []:
        for nb in cl.get('notebooks') or []:
            if str(nb.get('notebook_key') or '').strip() == key:
                return nb
    for item in payload.get('unclustered') or []:
        if str(item.get('notebook_key') or '').strip() == key:
            nb = item.get('notebook')
            if isinstance(nb, dict):
                return nb
    return None


def _notebook_keys_in_cluster(cl: Dict[str, Any]) -> List[str]:
    keys = [str(k).strip() for k in (cl.get('notebook_keys') or []) if str(k).strip()]
    if keys:
        return keys
    return [
        str(nb.get('notebook_key') or '').strip()
        for nb in (cl.get('notebooks') or [])
        if str(nb.get('notebook_key') or '').strip()
    ]


def _resolve_or_build_notebook_obj(viewer: str, payload: Dict[str, Any], nb_key: str) -> Optional[Dict[str, Any]]:
    """从任务簇缓存或用户本子列表解析 notebook 对象（支持复制入簇）。
    nb_key 既可能是 username_bookName，也可能是钉子勾选用的 writer_bookName。
    """
    found = _find_notebook_obj_in_payload(payload, nb_key)
    if found:
        return found
    try:
        notebooks = get_accessible_notebooks(viewer)
    except Exception as e:
        print(f'[task_cluster] 解析本子失败 {nb_key}: {e}')
        return None
    for nb in notebooks or []:
        key = str(nb.get('notebook_key') or '').strip()
        if key == nb_key:
            return nb
        writer_key = f"{(nb.get('writer') or '').strip()}_{(nb.get('bookName') or nb.get('title') or '').strip()}"
        if writer_key == nb_key:
            return nb
    return None


def adjust_notebook_cluster(
    viewer_real_name: str,
    notebook_key: str,
    action: str,
    *,
    target_cluster_id: Optional[str] = None,
    new_cluster_name: Optional[str] = None,
    new_cluster_summary: Optional[str] = None,
) -> Dict[str, Any]:
    viewer = (viewer_real_name or '').strip()
    nb_key = (notebook_key or '').strip()
    act = (action or '').strip().lower()
    if not viewer or not nb_key:
        return {'error_num': 1, 'msg': '缺少用户名或本子标识'}
    payload = load_task_cluster_result(viewer, refresh_card_nums=False)
    if not payload:
        return {'error_num': 1, 'msg': '无任务簇缓存，请先分析或新增任务簇'}

    # —— 复制加入指定簇（不离开其它簇）——
    if act == 'add':
        target_id = (target_cluster_id or '').strip()
        if not target_id:
            return {'error_num': 1, 'msg': '缺少目标簇 ID'}
        target = None
        for cl in payload.get('clusters') or []:
            if cl.get('cluster_id') == target_id:
                target = cl
                break
        if not target:
            return {'error_num': 1, 'msg': '未找到目标任务簇'}
        nb_obj = _resolve_or_build_notebook_obj(viewer, payload, nb_key)
        if not nb_obj:
            return {'error_num': 1, 'msg': f'未找到本子 {nb_key}'}
        # 统一用缓存标准 notebook_key（username_bookName），避免钉子 writer_bookName 分叉
        canon_key = str(nb_obj.get('notebook_key') or nb_key).strip()
        nb_obj = dict(nb_obj)
        nb_obj['notebook_key'] = canon_key
        keys = target.setdefault('notebook_keys', [])
        if canon_key not in [str(k).strip() for k in keys]:
            keys.append(canon_key)
        notebooks = target.setdefault('notebooks', [])
        if not any(str(nb.get('notebook_key') or '').strip() == canon_key for nb in notebooks):
            notebooks.append(nb_obj)
        # 已入任一簇后，从「未强关联」区移除
        payload['unclustered'] = [
            item for item in (payload.get('unclustered') or [])
            if str(item.get('notebook_key') or '').strip() != canon_key
        ]
        payload['manually_edited'] = True
        save_task_cluster_result(viewer, payload)
        result = dict(payload)
        result['error_num'] = 0
        result['processed'] = True
        return result

    # —— 仅从指定簇移除（可仍留在其它簇）——
    if act == 'remove_from_cluster':
        source_id = (target_cluster_id or '').strip()
        if not source_id:
            return {'error_num': 1, 'msg': '缺少源簇 ID'}
        nb_obj = None
        removed = False
        for cl in payload.get('clusters') or []:
            if cl.get('cluster_id') != source_id:
                continue
            kept_nbs: List[Dict[str, Any]] = []
            for nb in cl.get('notebooks') or []:
                key = str(nb.get('notebook_key') or '').strip()
                if key == nb_key:
                    nb_obj = nb
                    removed = True
                else:
                    kept_nbs.append(nb)
            cl['notebooks'] = kept_nbs
            cl['notebook_keys'] = [
                k for k in (cl.get('notebook_keys') or []) if str(k).strip() != nb_key
            ]
        if not removed:
            return {'error_num': 1, 'msg': '该本子不在此任务簇中'}
        still_in_cluster = False
        for cl in payload.get('clusters') or []:
            if nb_key in _notebook_keys_in_cluster(cl):
                still_in_cluster = True
                break
        if not still_in_cluster:
            if not nb_obj:
                nb_obj = _resolve_or_build_notebook_obj(viewer, payload, nb_key)
            if nb_obj:
                already = any(
                    str(item.get('notebook_key') or '').strip() == nb_key
                    for item in (payload.get('unclustered') or [])
                )
                if not already:
                    payload.setdefault('unclustered', []).append({
                        'notebook_key': nb_key,
                        'reason': '手动调整：从此簇移除后暂无其它簇',
                        'notebook': nb_obj,
                    })
        payload['manually_edited'] = True
        save_task_cluster_result(viewer, payload)
        result = dict(payload)
        result['error_num'] = 0
        result['processed'] = True
        return result

    # —— 兼容旧 action：移动语义（先脱离所有簇再放入一处）——
    nb_obj = None
    for cl in payload.get('clusters') or []:
        kept_nbs: List[Dict[str, Any]] = []
        for nb in cl.get('notebooks') or []:
            key = str(nb.get('notebook_key') or '').strip()
            if key == nb_key:
                nb_obj = nb
            else:
                kept_nbs.append(nb)
        cl['notebooks'] = kept_nbs
        cl['notebook_keys'] = [
            k for k in (cl.get('notebook_keys') or []) if str(k).strip() != nb_key
        ]

    new_unclustered: List[Dict[str, Any]] = []
    for item in payload.get('unclustered') or []:
        if str(item.get('notebook_key') or '').strip() == nb_key:
            nb_obj = item.get('notebook') or nb_obj
        else:
            new_unclustered.append(item)
    payload['unclustered'] = new_unclustered

    if not nb_obj:
        nb_obj = _resolve_or_build_notebook_obj(viewer, payload, nb_key)
    if not nb_obj:
        return {'error_num': 1, 'msg': f'未找到本子 {nb_key}'}

    if act == 'unclustered':
        payload['unclustered'].append({
            'notebook_key': nb_key,
            'reason': '手动调整：不入簇',
            'notebook': nb_obj,
        })
    elif act == 'move':
        target_id = (target_cluster_id or '').strip()
        if not target_id:
            return {'error_num': 1, 'msg': '缺少目标簇 ID'}
        target = None
        for cl in payload.get('clusters') or []:
            if cl.get('cluster_id') == target_id:
                target = cl
                break
        if not target:
            return {'error_num': 1, 'msg': '未找到目标任务簇'}
        target.setdefault('notebooks', []).append(nb_obj)
        keys = target.setdefault('notebook_keys', [])
        if nb_key not in keys:
            keys.append(nb_key)
    elif act == 'new':
        name = (new_cluster_name or '').strip()
        summary = (new_cluster_summary or '').strip()
        if not name:
            return {'error_num': 1, 'msg': '新簇名称不能为空'}
        if not summary:
            return {'error_num': 1, 'msg': '新簇需要一句话描述'}
        new_id = f'm{int(time.time() * 1000)}'
        payload.setdefault('clusters', []).append({
            'cluster_id': new_id,
            'cluster_name': name,
            'summary': summary,
            'notebook_keys': [nb_key],
            'notebooks': [nb_obj],
        })
    else:
        return {'error_num': 1, 'msg': f'未知操作 {action}'}

    # 允许空簇保留（用户可仅新增分类、稍后再移入本子）
    payload['manually_edited'] = True
    save_task_cluster_result(viewer, payload)
    result = dict(payload)
    result['error_num'] = 0
    result['processed'] = True
    return result


def create_empty_cluster(
    viewer_real_name: str,
    *,
    cluster_name: str,
    summary: str,
) -> Dict[str, Any]:
    """仅新增空任务簇，不移入本子。"""
    viewer = (viewer_real_name or '').strip()
    name = (cluster_name or '').strip()
    desc = (summary or '').strip()
    if not viewer:
        return {'error_num': 1, 'msg': '缺少用户名'}
    if not name:
        return {'error_num': 1, 'msg': '新簇名称不能为空'}
    if not desc:
        return {'error_num': 1, 'msg': '新簇需要一句话描述'}
    payload = load_task_cluster_result(viewer, refresh_card_nums=False)
    if not payload:
        return {'error_num': 1, 'msg': '无任务簇缓存，请先分析'}
    new_id = f'm{int(time.time() * 1000)}'
    payload.setdefault('clusters', []).append({
        'cluster_id': new_id,
        'cluster_name': name,
        'summary': desc,
        'notebook_keys': [],
        'notebooks': [],
    })
    payload['manually_edited'] = True
    save_task_cluster_result(viewer, payload)
    result = dict(payload)
    result['error_num'] = 0
    result['processed'] = True
    return result


def delete_cluster(viewer_real_name: str, cluster_id: str) -> Dict[str, Any]:
    """删除任务簇分类；其中本子迁入未强关联入簇，不删本子数据。"""
    viewer = (viewer_real_name or '').strip()
    cid = (cluster_id or '').strip()
    if not viewer or not cid:
        return {'error_num': 1, 'msg': '缺少用户名或任务簇 ID'}
    payload = load_task_cluster_result(viewer, refresh_card_nums=False)
    if not payload:
        return {'error_num': 1, 'msg': '无任务簇缓存，请先分析'}

    removed: Optional[Dict[str, Any]] = None
    kept: List[Dict[str, Any]] = []
    for cl in payload.get('clusters') or []:
        if cl.get('cluster_id') == cid:
            removed = cl
        else:
            kept.append(cl)
    if not removed:
        return {'error_num': 1, 'msg': '未找到任务簇'}

    payload['clusters'] = kept
    unclustered = list(payload.get('unclustered') or [])
    existing_keys = {
        str(item.get('notebook_key') or '').strip()
        for item in unclustered
    }
    for nb in removed.get('notebooks') or []:
        nb_key = str(nb.get('notebook_key') or '').strip()
        if not nb_key or nb_key in existing_keys:
            continue
        unclustered.append({
            'notebook_key': nb_key,
            'reason': '任务簇已删除，待重新入簇',
            'notebook': nb,
        })
        existing_keys.add(nb_key)
    payload['unclustered'] = unclustered
    payload['manually_edited'] = True
    save_task_cluster_result(viewer, payload)
    result = dict(payload)
    result['error_num'] = 0
    result['processed'] = True
    return result


def get_task_cluster_status(viewer_real_name: str) -> Dict[str, Any]:
    cached = _read_task_cluster_payload_raw(viewer_real_name)
    if cached:
        return {
            'error_num': 0,
            'processed': True,
            'analyzed_at': cached.get('analyzed_at', ''),
            'model': cached.get('model', ''),
            'notebook_count': cached.get('notebook_count', 0),
            'cluster_count': len(cached.get('clusters') or []),
        }
    return {
        'error_num': 0,
        'processed': False,
        'analyzed_at': '',
        'model': '',
        'notebook_count': 0,
        'cluster_count': 0,
    }
