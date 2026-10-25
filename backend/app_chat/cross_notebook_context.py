# -*- coding: utf-8 -*-
"""跨本子任务簇：智能发现关联本子并注入参考文档（问答 RAG 扩展）。"""
from __future__ import annotations
import nkcn_public_config as _public_config

import json
import os
import re
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from django.db.models import Q
from langchain.docstore.document import Document

from app_chat.models import Card
from zym.models import UserNotebook, scene

# ── 常量 ──
MIN_SELECT = 2
MAX_SELECT = 3
SCORE_CLOSE_GAP = 0.06
SCORE_LOW_THRESHOLD = 0.22
SAME_SCENE_BOOST = 0.08
SAME_CLUSTER_BOOST = 0.22
RECENT_ACTIVITY_BOOST = 0.05
RECENT_DAYS = 30

SKIP_DOC_DIRS = frozenset({'cardImage', 'pre_summary', 'pre_image_summary'})
DOC_EXTS = frozenset({'.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.md'})

CITATION_INSTRUCTION = """【引用标注要求（当前本子 + 跨本子参考材料均适用）】
下文参考材料中，每条已标注序号 [1]、[2]、[3] …。同一文档的多段材料共用同一序号（段首均标 [n]）。
回答时必须遵守：
1. 请尽量运用所提供的全部参考材料组织回答：与问题关系密切的素材应多引用、写透；关系稍弱的可简要用到，形成「用得多 / 用得少」的层次，不要只挑一两段而忽略其余已给材料。
2. 直接引用原话时，在相应位置标注序号，例如：……[1]
3. 间接使用（无原话、作为素材形成你自己的观点或理解）也须标注序号，例如：……[2]
4. 回答正文结束后，另起一段输出「参考文档列表」：
   - 只列出你在正文中实际引用过的序号；
   - **同一文档无论对应多少段材料，只写一行**（按文档去重，不要为同一文档重复多行）；
   - 每条格式：[序号] 文档名 | 场景：场景名 | 本子：bookdescription（中文本子描述）
5. 未引用任何参考材料则不必输出该列表。
"""


@dataclass
class NotebookCandidate:
    notebook: UserNotebook
    full_username: str
    scene_name: str
    profile_text: str
    embed_score: float = 0.0
    final_score: float = 0.0
    recent_boost: float = 0.0


@dataclass
class CrossInjectResult:
    segments: List[List[Document]] = field(default_factory=list)
    citation_prefix: str = ''
    ref_meta: List[Dict[str, str]] = field(default_factory=list)
    selected_notebooks: List[str] = field(default_factory=list)


class CitationAllocator:
    """按「文档 + 场景 + 本子」分配引用序号，同一文档多段共用同一 [n]。"""

    def __init__(self, start_index: int = 1):
        self._next = max(1, start_index)
        self._key_to_index: Dict[Tuple[str, str, str], int] = {}

    def _key(self, doc_name: str, scene_name: str, book_desc: str) -> Tuple[str, str, str]:
        return (_normalize_doc_basename(doc_name), scene_name or '未知场景', book_desc or '')

    def allocate(self, doc_name: str, scene_name: str, book_desc: str) -> int:
        key = self._key(doc_name, scene_name, book_desc)
        if key not in self._key_to_index:
            self._key_to_index[key] = self._next
            self._next += 1
        return self._key_to_index[key]

    @property
    def next_index(self) -> int:
        return self._next


def _normalize_doc_basename(name: str) -> str:
    return os.path.basename((name or '').strip()).lower()


def _build_exclude_doc_set(exclude_doc_names: Optional[List[str]]) -> frozenset:
    if not exclude_doc_names:
        return frozenset()
    return frozenset(_normalize_doc_basename(n) for n in exclude_doc_names if n)


def _get_current_notebook_meta(current_username: str) -> Tuple[str, str]:
    author, book = _parse_username(current_username)
    scene_name, book_desc = '', book
    try:
        nb = UserNotebook.objects.filter(username=author, bookName=book).first() if book else None
        if nb:
            scene_name = _scene_name_by_sid(nb.sid)
            book_desc = (nb.bookdescription or nb.bookName or book).strip()
    except Exception:
        pass
    return scene_name or '未知场景', book_desc or book or '当前本子'


def _doc_name_from_segment(segment: Document) -> str:
    src = (segment.metadata or {}).get('source', '')
    if src and src != 'cross_notebook_ref':
        return os.path.basename(src)
    return '未知文档'


def _format_cited_segment(
    ref_index: int,
    page_content: str,
    doc_name: str,
    scene_name: str,
    book_desc: str,
) -> str:
    body = (page_content or '').strip()
    if body.startswith('[') and body[:4].count(']') == 1:
        body = re.sub(r'^\[\d+\]\s*', '', body, count=1)
    return (
        f"[{ref_index}] {body}\n"
        f"（文档：{doc_name} | 场景：{scene_name} | 本子：{book_desc}）"
    )


def apply_citation_to_current_segments(
    segments: List[List[Document]],
    current_username: str,
    start_index: int = 1,
) -> Tuple[List[List[Document]], CitationAllocator]:
    """为当前本子 RAG 片段统一加 [n] 序号（同文档共用序号），返回 (新 segments, 分配器)。"""
    scene_name, book_desc = _get_current_notebook_meta(current_username)
    allocator = CitationAllocator(start_index=start_index)
    out: List[List[Document]] = []

    for doc_group in segments:
        if not doc_group:
            continue
        first_meta = doc_group[0].metadata or {}
        if first_meta.get('source') == 'cross_notebook_ref':
            out.append(doc_group)
            continue

        new_group: List[Document] = []
        for segment in doc_group:
            doc_name = _doc_name_from_segment(segment)
            ref_index = allocator.allocate(doc_name, scene_name, book_desc)
            new_content = _format_cited_segment(
                ref_index, segment.page_content or '', doc_name, scene_name, book_desc
            )
            meta = dict(segment.metadata or {})
            meta['unified_citation'] = True
            meta['citation_index'] = ref_index
            meta['citation_doc_name'] = doc_name
            meta['citation_scene'] = scene_name
            meta['citation_book_desc'] = book_desc
            new_group.append(Document(page_content=new_content, metadata=meta))
        if new_group:
            out.append(new_group)

    return out, allocator


def _parse_username(username: str) -> Tuple[str, str]:
    if '_' in username:
        real, book = username.split('_', 1)
        return real, book
    return username, ''


def _resolve_viewer_real_name(notebook_username: str, origin_real_name: Optional[str] = None) -> str:
    """实际操作者（协作者场景下为 originRealName 中的 realName，而非本子作者）。"""
    if origin_real_name:
        viewer, _ = _parse_username(origin_real_name.strip())
        if viewer:
            return viewer
    viewer, _ = _parse_username(notebook_username)
    return viewer


def _full_username(notebook: UserNotebook) -> str:
    return f"{notebook.username}_{notebook.bookName}"


def _scene_name_by_sid(sid: int) -> str:
    try:
        obj = scene.objects.filter(sid=sid).first()
        return (obj.sceneDescription or '').strip() if obj else ''
    except Exception:
        return ''


def _list_doc_filenames(full_username: str, limit: int = 25) -> List[str]:
    base = os.path.join('.', 'received_dir', 'user_raw_file', full_username)
    if not os.path.isdir(base):
        return []
    names: List[str] = []
    for name in sorted(os.listdir(base)):
        if name in SKIP_DOC_DIRS:
            continue
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in DOC_EXTS:
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return names


def _recent_card_titles(full_username: str, limit: int = 20) -> List[str]:
    try:
        qs = (
            Card.objects.filter(username=full_username)
            .exclude(contentTitle__isnull=True)
            .exclude(contentTitle='')
            .order_by('-datetime')
            .values_list('contentTitle', flat=True)[:limit]
        )
        return [str(t).strip() for t in qs if str(t).strip()]
    except Exception:
        return []


def _recent_activity_boost(full_username: str) -> float:
    try:
        latest = Card.objects.filter(username=full_username).order_by('-datetime').first()
        if not latest or not latest.datetime:
            return 0.0
        from django.utils import timezone
        delta = timezone.now() - latest.datetime
        if delta.days <= RECENT_DAYS:
            return RECENT_ACTIVITY_BOOST * (1.0 - delta.days / RECENT_DAYS)
    except Exception:
        pass
    return 0.0


def _build_profile(notebook: UserNotebook, full_username: str) -> Tuple[str, str]:
    scene_name = _scene_name_by_sid(notebook.sid)
    docs = _list_doc_filenames(full_username)
    titles = _recent_card_titles(full_username)
    parts = [
        f"本子名：{notebook.bookName}",
        f"本子描述：{notebook.bookdescription or ''}",
        f"场景：{scene_name}",
        f"作者：{notebook.username}",
    ]
    if docs:
        parts.append('文档：' + '、'.join(docs[:15]))
    if titles:
        parts.append('卡片标题：' + '、'.join(titles[:12]))
    return scene_name, '\n'.join(parts)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _embed_openai(texts: List[str], is_query: bool = False) -> List[np.ndarray]:
    """使用与 RAG 相同的 OpenAI text-embedding-3-large，避免 jieba 冷启动。"""
    from llm_langchain.parse_input import embeddings

    trimmed = [(t or '')[:2000] for t in texts]
    if not trimmed:
        return []
    try:
        if is_query and len(trimmed) == 1:
            vec = embeddings.embed_query(trimmed[0])
            return [np.array(vec, dtype=np.float32)]
        vecs = embeddings.embed_documents(trimmed)
        return [np.array(v, dtype=np.float32) for v in vecs]
    except Exception as e:
        print(f"[cross_notebook] OpenAI embedding 失败: {e}")
        return []


def _resolve_vector_db_path_readonly(full_username: str) -> Optional[Tuple[str, str]]:
    """返回 (persist_directory, db_type) 或 None（不触发新建库）。"""
    from llm_langchain import parse_input, util

    db_path = util.db_path
    user_db_path = os.path.join(db_path, full_username)
    shared_db_file = os.path.join(db_path, 'chroma.sqlite3')
    user_db_file = os.path.join(user_db_path, 'chroma.sqlite3')
    has_user_db = os.path.exists(user_db_path) and os.path.exists(user_db_file)

    has_shared_data = False
    if os.path.exists(shared_db_file):
        collection_name = util.construct_collection(full_username)
        try:
            collection_exists, has_any_row = parse_input._detect_shared_chroma_collection_fast(
                shared_db_file=shared_db_file,
                collection_name=collection_name,
                timeout_sec=1.0,
            )
            if collection_exists:
                has_shared_data = True if has_any_row is None else bool(has_any_row)
        except Exception as e:
            print(f"[cross_notebook] 共享库探测失败 {full_username}: {e}")

    if has_user_db and has_shared_data:
        return user_db_path, '混合'
    if has_user_db:
        return user_db_path, '独立'
    if has_shared_data:
        return db_path, '共享'
    return None


def _vector_db_exists_readonly(full_username: str) -> bool:
    return _resolve_vector_db_path_readonly(full_username) is not None


def _has_pre_summary(full_username: str) -> bool:
    base = os.path.join('.', 'received_dir', 'user_raw_file', full_username, 'pre_summary')
    if not os.path.isdir(base):
        return False
    return any(name.endswith('.md') for name in os.listdir(base))


def _notebook_has_retrievable_content(full_username: str) -> bool:
    return _vector_db_exists_readonly(full_username) or _has_pre_summary(full_username)


def _should_skip_candidate(nb: UserNotebook, full_username: str, current_book: str = '') -> bool:
    """过滤无效副本、无检索来源的本子。"""
    book = nb.bookName or ''
    if re.search(r'Shared\d+Shared\d+', book, re.I):
        return True
    if current_book and re.match(
        re.escape(current_book) + r'Shared\d*$', book, re.I
    ):
        return True
    if not _list_doc_filenames(full_username, limit=1) and not _recent_card_titles(full_username, limit=1):
        if 'Shared' in book:
            return True
    if not _notebook_has_retrievable_content(full_username):
        return True
    return False


def get_candidate_notebooks(
    viewer_real_name: str,
    current_username: str,
) -> Tuple[List[NotebookCandidate], Optional[int]]:
    _, current_book = _parse_username(current_username)
    author, _ = _parse_username(current_username)

    try:
        qs = UserNotebook.objects.filter(
            Q(username=viewer_real_name) |
            Q(syncUsers__regex=r'(^|,\s*)' + re.escape(viewer_real_name) + r'(\s*,|$)')
        ).defer('context_data')
    except Exception as e:
        print(f"[cross_notebook] 查询候选本子失败: {e}")
        return [], None

    current_sid = None
    try:
        cur_nb = UserNotebook.objects.filter(
            username=author, bookName=current_book
        ).first() if current_book else None
        if cur_nb:
            current_sid = cur_nb.sid
    except Exception:
        pass

    out: List[NotebookCandidate] = []
    seen_full = {current_username}
    for nb in qs:
        full = _full_username(nb)
        if full in seen_full:
            continue
        if _should_skip_candidate(nb, full, current_book=current_book):
            continue
        seen_full.add(full)
        scene_name, profile = _build_profile(nb, full)
        out.append(NotebookCandidate(
            notebook=nb,
            full_username=full,
            scene_name=scene_name,
            profile_text=profile,
        ))
    print(f"[cross_notebook] 候选本子 {len(out)} 个 (viewer={viewer_real_name}, 当前={current_username})")
    return out, current_sid


def _same_cluster_peer_keys(viewer_real_name: str, current_full_username: str) -> set:
    """
    若当前本子属于一个或多个任务簇，返回这些簇内其它本子的 full_username 集合；
    若当前本子未入任何簇（或无任务簇缓存），返回空集 → 跨本保持原自动逻辑。
    """
    viewer = (viewer_real_name or '').strip()
    current = (current_full_username or '').strip()
    if not viewer or not current:
        return set()
    try:
        from app_chat.task_cluster_service import load_task_cluster_result
        payload = load_task_cluster_result(viewer, refresh_card_nums=False)
    except Exception as e:
        print(f"[cross_notebook] 读取任务簇失败: {e}")
        return set()
    if not payload:
        return set()
    peers: set = set()
    in_any = False
    for cl in payload.get('clusters') or []:
        keys = set()
        for k in (cl.get('notebook_keys') or []):
            ks = str(k).strip()
            if ks:
                keys.add(ks)
        for nb in (cl.get('notebooks') or []):
            if isinstance(nb, dict):
                ks = str(nb.get('notebook_key') or nb.get('full_username') or '').strip()
                if ks:
                    keys.add(ks)
        if current in keys:
            in_any = True
            peers |= (keys - {current})
    if in_any:
        print(f"[cross_notebook] 当前本子已入簇，同簇其它本子 {len(peers)} 个")
    return peers if in_any else set()


def _score_candidates(
    candidates: List[NotebookCandidate],
    query_text: str,
    current_sid: Optional[int] = None,
    same_cluster_keys: Optional[set] = None,
) -> None:
    if not query_text.strip() or not candidates:
        return
    q_vecs = _embed_openai([query_text], is_query=True)
    if not q_vecs:
        return
    q_vec = q_vecs[0]
    profiles = [c.profile_text[:1500] for c in candidates]
    p_vecs = _embed_openai(profiles, is_query=False)
    if len(p_vecs) != len(candidates):
        print(f"[cross_notebook] embedding 数量不匹配: {len(p_vecs)} vs {len(candidates)}")
        return
    cluster_keys = same_cluster_keys or set()
    for c, p_vec in zip(candidates, p_vecs):
        c.embed_score = _cosine(q_vec, p_vec)
        c.recent_boost = _recent_activity_boost(c.full_username)
        c.final_score = c.embed_score + c.recent_boost
        if current_sid is not None and c.notebook.sid == current_sid:
            c.final_score += SAME_SCENE_BOOST
        if c.full_username in cluster_keys:
            c.final_score += SAME_CLUSTER_BOOST


def _needs_llm_rerank(ranked: List[NotebookCandidate]) -> bool:
    if len(ranked) < MIN_SELECT:
        return False
    top = ranked[0].final_score
    if top < SCORE_LOW_THRESHOLD:
        return True
    if len(ranked) >= MAX_SELECT:
        gap = ranked[0].final_score - ranked[MAX_SELECT - 1].final_score
        if gap < SCORE_CLOSE_GAP:
            return True
    if len(ranked) >= 2:
        if ranked[0].final_score - ranked[1].final_score < SCORE_CLOSE_GAP * 0.8:
            return True
    return False


def _rank_via_relay(question: str, candidates: List[NotebookCandidate], real_name: str) -> List[int]:
    try:
        import requests
        from app_chat.global_state import GLOBAL_STATE

        model_id = GLOBAL_STATE.user_little_model_id.get(real_name, '3003')
        server_url = (
            _public_config.endpoint('NKCN_SERVICE_8000_URL', 'http://localhost:8000') if str(model_id) == '3007'
            else _public_config.endpoint('NKCN_SERVICE_8000_URL', 'http://localhost:8000')
        )

        lines = []
        for i, c in enumerate(candidates[:10]):
            lines.append(f"{i + 1}. {c.profile_text[:400]}")
        user_prompt = (
            f"用户问题：{question[:500]}\n\n"
            "以下候选本子（仅元数据）。请按与问题的相关度从高到低选出 2 到 3 个最相关的本子编号。\n"
            + '\n'.join(lines)
            + '\n\n只输出 JSON：{"indices":[1,2,3]}，indices 为上述编号（1-based），必须 2 或 3 个。'
        )
        full_input_text = user_prompt.replace('\n', '\\n').replace('```', '')
        request_data = {
            'input_text': full_input_text,
            'user_name': real_name,
            'task_type': 'cross_notebook_rank',
        }
        resp = requests.post(
            f'{server_url}/get_depth_suggestion',
            json=request_data,
            headers={'Content-Type': 'application/json'},
            timeout=25,
        )
        if resp.status_code != 200:
            print(f"[cross_notebook] 小模型中转 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if data.get('error_num', 1) != 0:
            print(f"[cross_notebook] 小模型中转 error: {data.get('message', '')}")
            return []
        raw = (data.get('suggestion') or data.get('result') or data.get('output') or data.get('content') or '').strip()
        if not raw:
            return []
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            m = re.search(r'\{[\s\S]*\}', raw)
            json_str = m.group() if m else raw
        parsed = json.loads(json_str)
        indices = parsed.get('indices') or parsed.get('selected') or []
        out = []
        for x in indices:
            idx = int(x) - 1
            if 0 <= idx < len(candidates):
                out.append(idx)
        if out:
            print(f"[cross_notebook] 小模型重排: {out}")
        return out
    except Exception as e:
        print(f"[cross_notebook] 小模型重排失败: {e}")
        return []


def _rank_via_deepseek(question: str, candidates: List[NotebookCandidate]) -> List[int]:
    try:
        import os
        from openai import OpenAI

        lines = []
        for i, c in enumerate(candidates[:10]):
            lines.append(f"{i + 1}. {c.profile_text[:400]}")
        prompt = (
            f"用户问题：{question[:500]}\n\n候选本子：\n" + '\n'.join(lines)
            + '\n选出最相关的2或3个编号，只输出JSON：{"indices":[1,2,3]}'
        )
        ds_key = os.environ.get('DEEPSEEK_API_KEY') or _public_config.secret('DEEPSEEK_API_KEY')
        client = OpenAI(api_key=ds_key, base_url='https://api.deepseek.com', timeout=20.0)
        resp = client.chat.completions.create(
            model='deepseek-v4-flash',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.3,
            max_tokens=80,
            extra_body={'thinking': {'type': 'disabled'}},
        )
        raw = (resp.choices[0].message.content or '').strip()
        m = re.search(r'\{[\s\S]*\}', raw)
        if not m:
            return []
        parsed = json.loads(m.group())
        indices = parsed.get('indices') or []
        out = []
        for x in indices:
            idx = int(x) - 1
            if 0 <= idx < len(candidates):
                out.append(idx)
        print(f"[cross_notebook] DeepSeek 重排成功: {out}")
        return out
    except Exception as e:
        print(f"[cross_notebook] DeepSeek 重排失败: {e}")
        return []


def select_related_notebooks(
    candidates: List[NotebookCandidate],
    question: str,
    real_name: str,
) -> List[NotebookCandidate]:
    if not candidates:
        return []
    ranked = sorted(candidates, key=lambda c: c.final_score, reverse=True)

    if _needs_llm_rerank(ranked):
        print("[cross_notebook] embedding 分数接近或偏低，启用小模型重排")
        order = _rank_via_relay(question, ranked, real_name)
        if not order:
            print("[cross_notebook] 小模型失败，改用 DeepSeek 重排")
            order = _rank_via_deepseek(question, ranked)
        if order:
            picked = [ranked[i] for i in order[:MAX_SELECT]]
            ranked = picked + [c for j, c in enumerate(ranked) if j not in order[:MAX_SELECT]]

    n_avail = len(ranked)
    n = min(MAX_SELECT, max(MIN_SELECT, n_avail)) if n_avail >= MIN_SELECT else n_avail
    n = max(1, n)
    selected = ranked[:n]

    # 若重排结果含不可检索本子，从后续候选中补齐
    if len(selected) < MIN_SELECT and len(ranked) > len(selected):
        selected_set = {c.full_username for c in selected}
        for c in ranked[len(selected):]:
            if len(selected) >= MIN_SELECT:
                break
            if c.full_username not in selected_set:
                selected.append(c)
                selected_set.add(c.full_username)

    print(
        f"[cross_notebook] 选中 {len(selected)} 个本子: "
        + ', '.join(f"{c.full_username}(score={c.final_score:.3f})" for c in selected)
    )
    return selected


def _candidates_from_full_usernames(
    full_usernames: List[str],
    current_username: str,
) -> List[NotebookCandidate]:
    """将用户勾选的 full_username 解析为候选（排除当前本子与不可检索本子）。"""
    _, current_book = _parse_username(current_username)
    out: List[NotebookCandidate] = []
    seen = set()
    for raw in full_usernames or []:
        full = (raw or '').strip()
        if not full or full == current_username or full in seen:
            continue
        author, book = _parse_username(full)
        if not book:
            continue
        try:
            nb = UserNotebook.objects.filter(username=author, bookName=book).first()
        except Exception:
            nb = None
        if not nb:
            print(f"[cross_notebook] 勾选本子未找到记录: {full}")
            continue
        if _should_skip_candidate(nb, full, current_book=current_book):
            print(f"[cross_notebook] 勾选本子跳过（无检索来源等）: {full}")
            continue
        scene_name, profile = _build_profile(nb, full)
        out.append(NotebookCandidate(
            notebook=nb,
            full_username=full,
            scene_name=scene_name,
            profile_text=profile,
            embed_score=1.0,
            final_score=1.0,
        ))
        seen.add(full)
    print(
        f"[cross_notebook] 用户勾选本子 {len(out)} 个: "
        + ', '.join(c.full_username for c in out)
    )
    return out


def _allocate_char_budgets(scores: List[float]) -> List[int]:
    n = len(scores)
    if n == 0:
        return []
    if n == 1:
        return [2000]
    if n == 2:
        total = 4000
        max_each = 2000
        min_each = 600
    elif n == 3:
        total = 5000
        max_each = 2500
        min_each = 600
    elif n == 4:
        total = 6000
        max_each = 2000
        min_each = 600
    else:
        # 超过 4 个勾选本子：总篇幅封顶并下调单本配额
        total = min(5000, max(2800, n * 550))
        max_each = min(1200, max(450, total // n))
        min_each = 400
    raw = [max(s, 0.01) for s in scores]
    ssum = sum(raw)
    budgets = [int(total * (r / ssum)) for r in raw]
    if n >= 2 and raw[0] > raw[1] * 1.45:
        bonus = int(total * 0.12)
        budgets[0] = min(max_each, budgets[0] + bonus)
        per = bonus // (n - 1)
        for i in range(1, n):
            budgets[i] = max(min_each, budgets[i] - per)
    for i in range(n):
        budgets[i] = min(budgets[i], max_each)
        budgets[i] = max(budgets[i], min_each)
    diff = total - sum(budgets)
    if diff != 0:
        budgets[0] = min(max_each, max(min_each, budgets[0] + diff))
    return budgets


def _get_vector_store_lazy(full_username: str):
    """未 load_user 的关联本子也可读 Chroma（与 RAG 同库）；无库时不创建空库。"""
    from langchain_community.vectorstores import Chroma
    from llm_langchain import global_var, parse_input, util

    try:
        mem = global_var.store_memory.get(full_username) or {}
        vs = mem.get('vector_store')
        if vs is not None:
            return vs
    except Exception:
        pass

    resolved = _resolve_vector_db_path_readonly(full_username)
    if not resolved:
        return None

    actual_db_path, db_type = resolved
    try:
        collection_name = util.construct_collection(full_username)
        vs = Chroma(
            collection_name=collection_name,
            embedding_function=parse_input.embeddings,
            persist_directory=actual_db_path,
        )
        print(f"[cross_notebook] 懒加载向量库 {full_username} ({db_type})")
        return vs
    except Exception as e:
        print(f"[cross_notebook] 向量库不可用 {full_username}: {e}")
        return None


def _pre_summary_doc_name(fname: str) -> str:
    """DeepSeekNSApaper_Presummary_pdf.md -> DeepSeekNSApaper.pdf"""
    if '_Presummary_' in fname:
        stem, rest = fname.split('_Presummary_', 1)
        ext = rest[:-3] if rest.endswith('.md') else rest
        return f"{stem}.{ext}" if ext else stem
    return fname.replace('.md', '')


def _load_pre_summary_chunks(
    full_username: str,
    question: str,
    exclude_doc_names: Optional[List[str]] = None,
    char_budget: int = 2000,
) -> List[Tuple[str, str]]:
    base = os.path.join('.', 'received_dir', 'user_raw_file', full_username, 'pre_summary')
    if not os.path.isdir(base):
        return []
    exclude = _build_exclude_doc_set(exclude_doc_names)
    q_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', question.lower()))
    scored: List[Tuple[float, str, str]] = []
    for fname in os.listdir(base):
        if not fname.endswith('.md'):
            continue
        path = os.path.join(base, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read(2500).strip()
            if not text:
                continue
            doc_name = _pre_summary_doc_name(fname)
            if _normalize_doc_basename(doc_name) in exclude:
                continue
            overlap = sum(1 for t in q_tokens if t in text.lower() or t in fname.lower())
            scored.append((overlap, doc_name, text))
        except Exception:
            continue
    scored.sort(key=lambda x: (-x[0], x[1]))
    out: List[Tuple[str, str]] = []
    used = 0
    for _, doc_name, text in scored:
        remain = char_budget - used
        if remain <= 80:
            break
        piece = text[:remain]
        out.append((doc_name, piece))
        used += len(piece)
    return out


def _fetch_segments_for_notebook(
    full_username: str,
    question: str,
    char_budget: int,
    exclude_doc_names: Optional[List[str]] = None,
) -> List[Tuple[str, str]]:
    """返回 [(doc_name, chunk_text), ...]，在 char_budget 内尽量多取 RAG 片段。"""
    from llm_langchain.util import get_relevant_docs

    exclude = _build_exclude_doc_set(exclude_doc_names)
    doc_names = [
        d for d in _list_doc_filenames(full_username, limit=40)
        if _normalize_doc_basename(d) not in exclude
    ]
    if exclude and len(doc_names) < len(_list_doc_filenames(full_username, limit=40)):
        skipped = [
            d for d in _list_doc_filenames(full_username, limit=40)
            if _normalize_doc_basename(d) in exclude
        ]
        print(f"[cross_notebook] {full_username} 排除与当前本子同名文档: {skipped}")

    chunks: List[Tuple[str, str]] = []

    vector = _get_vector_store_lazy(full_username)
    if vector and doc_names:
        try:
            docs = get_relevant_docs(question, vector, doc_names, full_username, use_tab_enhance=False)
            for seg in docs:
                src = seg.metadata.get('source', '') if seg.metadata else ''
                doc_name = os.path.basename(src) if src else '未知文档'
                if _normalize_doc_basename(doc_name) in exclude:
                    continue
                text = (seg.page_content or '').strip()
                if text and not text.startswith('（本子'):
                    chunks.append((doc_name, text))
        except Exception as e:
            print(f"[cross_notebook] RAG 失败 {full_username}: {e}")

    if not chunks:
        chunks = _load_pre_summary_chunks(
            full_username, question, exclude_doc_names=exclude_doc_names, char_budget=char_budget
        )

    if not chunks:
        return []

    out: List[Tuple[str, str]] = []
    used = 0
    for doc_name, text in chunks:
        remain = char_budget - used
        if remain <= 80:
            break
        piece = text[:remain]
        out.append((doc_name, piece))
        used += len(piece)
    return out


def build_cross_notebook_injection(
    current_username: str,
    question: str,
    core_keyword: Optional[str] = None,
    origin_real_name: Optional[str] = None,
    exclude_doc_names: Optional[List[str]] = None,
    citation_allocator: Optional[CitationAllocator] = None,
    manual_notebook_usernames: Optional[List[str]] = None,
) -> CrossInjectResult:
    result = CrossInjectResult()
    viewer = _resolve_viewer_real_name(current_username, origin_real_name)
    allocator = citation_allocator or CitationAllocator(start_index=1)
    query_text = question
    if core_keyword and str(core_keyword).strip():
        query_text = f"{question}\n{core_keyword}"

    selected: List[NotebookCandidate] = []
    # 钉子勾选仅用于主页整理任务簇，与跨本选本无关（忽略 manual_notebook_usernames）
    candidates, current_sid = get_candidate_notebooks(viewer, current_username)
    if not candidates:
        print("[cross_notebook] 无候选本子，仍注入占位说明")
        ref_i = allocator.allocate('—', '—', '—')
        placeholder = Document(
            page_content=f"[{ref_i}] （暂无其他可关联本子，请主要依据当前本子材料回答）",
            metadata={'source': 'cross_notebook_ref', 'page': 0, 'cross_ref_index': ref_i, 'unified_citation': True},
        )
        result.segments = [[placeholder]]
        result.citation_prefix = CITATION_INSTRUCTION
        result.ref_meta = [{'index': str(ref_i), 'doc_name': '—', 'scene_name': '—', 'book_desc': '—'}]
        return result

    same_cluster_keys = _same_cluster_peer_keys(viewer, current_username)
    _score_candidates(
        candidates,
        query_text,
        current_sid,
        same_cluster_keys=same_cluster_keys,
    )
    selected = select_related_notebooks(candidates, question, viewer)
    if not selected:
        selected = sorted(candidates, key=lambda c: c.final_score, reverse=True)[:MIN_SELECT]

    scores = [c.final_score for c in selected]
    budgets = _allocate_char_budgets(scores)
    content_parts: List[str] = []
    seen_ref_keys: set = set()

    def _record_ref_meta(ref_index: int, doc_name: str, scene_name: str, book_desc: str) -> None:
        key = (_normalize_doc_basename(doc_name), scene_name, book_desc)
        if key in seen_ref_keys:
            return
        seen_ref_keys.add(key)
        result.ref_meta.append({
            'index': str(ref_index),
            'doc_name': doc_name,
            'scene_name': scene_name,
            'book_desc': book_desc,
        })

    for cand, budget in zip(selected, budgets):
        book_desc = cand.notebook.bookdescription or cand.notebook.bookName
        scene = cand.scene_name or '未知场景'
        chunks = _fetch_segments_for_notebook(
            cand.full_username, question, budget, exclude_doc_names=exclude_doc_names
        )
        if not chunks:
            doc_name = f'{cand.notebook.bookName}（元数据摘要）'
            ref_index = allocator.allocate(doc_name, scene, book_desc)
            _record_ref_meta(ref_index, doc_name, scene, book_desc)
            block = (
                f"[{ref_index}] {cand.profile_text[:min(budget, 1200)]}\n"
                f"（文档：{doc_name} | 场景：{scene} | 本子：{book_desc}）"
            )
            content_parts.append(block)
            result.selected_notebooks.append(cand.full_username)
            continue

        for doc_name, chunk_text in chunks:
            ref_index = allocator.allocate(doc_name, scene, book_desc)
            _record_ref_meta(ref_index, doc_name, scene, book_desc)
            block = (
                f"[{ref_index}] {chunk_text}\n"
                f"（文档：{doc_name} | 场景：{scene} | 本子：{book_desc}）"
            )
            content_parts.append(block)
        result.selected_notebooks.append(cand.full_username)

    if not content_parts:
        doc_name = selected[0].notebook.bookName
        scene = selected[0].scene_name or '未知场景'
        book_desc = selected[0].notebook.bookdescription or selected[0].notebook.bookName
        ref_index = allocator.allocate(doc_name, scene, book_desc)
        content_parts.append(
            f"[{ref_index}] （关联本子检索未命中具体文档片段，请参考各本子元数据）\n"
            + selected[0].profile_text[:1500]
        )
        _record_ref_meta(ref_index, doc_name, scene, book_desc)

    cross_doc = Document(
        page_content='【跨本子参考材料】\n\n' + '\n\n'.join(content_parts),
        metadata={'source': 'cross_notebook_ref', 'page': 0, 'unified_citation': True},
    )
    result.segments = [[cross_doc]]
    result.citation_prefix = CITATION_INSTRUCTION
    print(
        f"[cross_notebook] 注入 {len(content_parts)} 段材料 / {len(result.ref_meta)} 个文档序号, "
        f"viewer={viewer}, 本子={result.selected_notebooks}, "
        f"总字符≈{sum(len(p) for p in content_parts)}"
    )
    return result


def append_cross_notebook_segments(
    segments: List[List[Document]],
    current_username: str,
    question: str,
    core_keyword: Optional[str] = None,
    origin_real_name: Optional[str] = None,
    current_file_list: Optional[List[str]] = None,
    manual_notebook_usernames: Optional[List[str]] = None,
) -> Tuple[List[List[Document]], str]:
    try:
        numbered_segments, allocator = apply_citation_to_current_segments(
            segments, current_username, start_index=1
        )
        inj = build_cross_notebook_injection(
            current_username,
            question,
            core_keyword,
            origin_real_name=origin_real_name,
            exclude_doc_names=current_file_list or [],
            citation_allocator=allocator,
            manual_notebook_usernames=manual_notebook_usernames,
        )
        if inj.segments:
            numbered_segments = list(numbered_segments) + inj.segments
        return numbered_segments, inj.citation_prefix
    except Exception as e:
        print(f"[cross_notebook] 注入异常: {e}")
        traceback.print_exc()
        fallback = Document(
            page_content='[1] （跨本子关联处理异常，请依据当前本子材料回答）',
            metadata={'source': 'cross_notebook_ref', 'page': 0, 'unified_citation': True},
        )
        return segments + [[fallback]], CITATION_INSTRUCTION
