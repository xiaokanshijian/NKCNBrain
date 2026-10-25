# -*- coding: utf-8 -*-
"""
文档结构抽取（DeepSeek）→ 落盘 DocStructure.md → 指导 Skill 原文分层抽样。

失败或解析失败时由调用方回退到纯规则抽样（_stratified_sample_doc_text）。
输入量与 PreSummary 对齐。
"""
from __future__ import annotations
import nkcn_public_config as _public_config

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from app_chat import skills_store as store

# 与 parse_input.process_document_pre_summary 保持一致
_CONTEXT_MAX_TOKENS = 131072
_COMPLETION_MAX_TOKENS = 8192  # 结构 MAP 可能较长
_RESERVED_TOKENS = 6500
_CHARS_PER_TOKEN = 1.50
_SAFETY_FACTOR = 0.90

DOC_STRUCTURE_SYSTEM = """你是文档结构抽取助手。根据用户给出的文档全文（可能含 OCR「第 N 页」标记），输出**唯一**一份 Markdown，严格按下述格式，禁止 JSON，禁止代码围栏，禁止前言后语。

# DOC_STRUCTURE v1
source: toc | semantic
confidence: high | mid | low

## MAP
- L1 | <章/一级标题> | p<起>-p<止>
  - L2 | <节/二级标题> | p<起>-p<止>
    - L3 | <小节/三级标题> | p<起>-p<止>

## NOTES
- <可选：目录缺失、OCR 粘连、页码不确定等一句说明>

规则：
1. 若原文有**明确目录/Contents**，source 必须为 toc，MAP **严格按目录层级**抽取，不得把章内小节升成 L1。最多三级：章 L1 / 节 L2 / 小节 L3；目录若有更深层级，合并进 L3，不要输出 L4。
2. 若没有明确目录，source 为 semantic：按语义与篇幅自行划分层次，可只做 L1，或 L1+L2，或 L1+L2+L3；不要过度切碎。
3. 页码必须对齐文中「第 N 页」或目录点线页码；区间写作 p12-p18；单页可写 p12-p12。不确定时仍给出最合理估计，并在 NOTES 说明。
4. L1 至少 1 条；长文优先保证全书主要部分都有 L1 覆盖（含附录/后记若目录有）。
5. 标题保持原文用语，可轻微清理空格，不要杜撰章节名。
"""

_MAP_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)-\s*L(?P<level>[123])\s*\|\s*(?P<title>.+?)\s*\|\s*"
    r"p\s*(?P<p0>\d+)\s*(?:-\s*p\s*(?P<p1>\d+))?\s*$",
    re.I,
)


def presummary_max_content_chars() -> int:
    tokens_budget = max(
        0, _CONTEXT_MAX_TOKENS - _COMPLETION_MAX_TOKENS - _RESERVED_TOKENS
    )
    return int(tokens_budget * _CHARS_PER_TOKEN * _SAFETY_FACTOR)


def truncate_like_presummary(text: str) -> str:
    """与 PreSummary 相同的尽量长截断策略。"""
    text = text or ""
    max_len = presummary_max_content_chars()
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_para = truncated.rfind("\n\n")
    if last_para > max_len * 0.85:
        return text[:last_para]
    return truncated


def _call_deepseek_structure(system: str, user: str) -> str:
    from app_chat.scene_models import resolve_openai_cfg_from_abbr

    cfg = resolve_openai_cfg_from_abbr("deepseek-chat")
    client = OpenAI(
        api_key=cfg.get("api_key")
        or os.environ.get("DEEPSEEK_API_KEY")
        or _public_config.secret('DEEPSEEK_API_KEY'),
        base_url=cfg.get("base_url") or "https://api.deepseek.com",
        timeout=300.0,
    )
    model_name = str(cfg.get("model") or "deepseek-chat")
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=_COMPLETION_MAX_TOKENS,
    )
    return (resp.choices[0].message.content or "").strip()


def _normalize_structure_md(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:markdown|md)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"(?im)^#\s*DOC_STRUCTURE\b", raw)
    if m:
        raw = raw[m.start():]
    return raw.strip()


def parse_doc_structure_md(md: str) -> Optional[Dict[str, Any]]:
    """
    解析 DocStructure.md。
    成功返回 {source, confidence, nodes, map_text, notes, raw_md}；失败 None。
    """
    md = _normalize_structure_md(md)
    if not re.search(r"(?im)^#\s*DOC_STRUCTURE\b", md):
        return None

    source_m = re.search(r"(?im)^source:\s*(toc|semantic)\s*$", md)
    conf_m = re.search(r"(?im)^confidence:\s*(high|mid|low)\s*$", md)
    if not source_m:
        return None
    source = source_m.group(1).lower()
    confidence = (conf_m.group(1).lower() if conf_m else "mid")

    map_m = re.search(r"(?im)^##\s*MAP\s*$", md)
    if not map_m:
        return None
    rest = md[map_m.end():]
    notes_m = re.search(r"(?im)^##\s*NOTES\s*$", rest)
    map_body = rest[: notes_m.start()] if notes_m else rest
    notes = rest[notes_m.end():].strip() if notes_m else ""

    nodes: List[Dict[str, Any]] = []
    for line in map_body.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = _MAP_LINE_RE.match(line.rstrip())
        if not m:
            continue
        level = int(m.group("level"))
        title = (m.group("title") or "").strip()
        p0 = int(m.group("p0"))
        p1 = int(m.group("p1") or m.group("p0"))
        if p1 < p0:
            p0, p1 = p1, p0
        if not title or p0 <= 0:
            continue
        nodes.append({
            "level": level,
            "title": title[:120],
            "p0": p0,
            "p1": p1,
        })

    if len(nodes) < 1:
        return None
    if not any(n["level"] == 1 for n in nodes):
        for n in nodes:
            n["level"] = max(1, n["level"] - 1)

    map_text = "\n".join(
        f"{'  ' * (n['level'] - 1)}- L{n['level']} | {n['title']} | p{n['p0']}-p{n['p1']}"
        for n in nodes
    )
    return {
        "source": source,
        "confidence": confidence,
        "nodes": nodes,
        "map_text": map_text,
        "notes": notes,
        "raw_md": md,
    }


def find_page_offset(text: str, page: int, min_offset: int = 0) -> int:
    if page <= 0:
        return -1
    pat = re.compile(
        rf"(?:^|\n)\s*(?:\[页码：)?第\s*{page}\s*页\s*(?:\])?\s*(?:\n|$)",
    )
    for m in pat.finditer(text or ""):
        off = m.start() + (1 if m.group(0).startswith("\n") else 0)
        if off >= min_offset:
            return off
    return -1


def slice_by_page_range(text: str, p0: int, p1: int) -> str:
    """按起止页从 OCR 正文切片；找不到起始页码则返回空串。"""
    text = text or ""
    start = find_page_offset(text, p0)
    if start < 0:
        return ""
    end = find_page_offset(text, p1 + 1, min_offset=start + 1)
    if end < 0:
        end = len(text)
    return text[start:end].strip()


def _l1_groups(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for n in nodes:
        if n["level"] == 1:
            cur = {"node": n, "children": []}
            groups.append(cur)
        elif cur is not None:
            cur["children"].append(n)
    if not groups and nodes:
        groups = [{"node": nodes[0], "children": nodes[1:]}]
    return groups


_OUTLINE_L2_RE = re.compile(
    r"^(?:"
    r"[一二三四五六七八九十百]+[、．.]|"
    r"[（(]\s*[一二三四五六七八九十百]+|"
    r"\d+[、]"
    r")"
)


def _is_outline_sampling_title(title: str) -> bool:
    """目录大纲式标题：一、 / （一） / 1、 …"""
    return bool(_OUTLINE_L2_RE.match((title or "").strip()))


def _split_l2_blocks(
    children: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """把 L1 下扁平 children 收成 [{node: L2, children: L3...}, ...]。"""
    blocks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for c in children or []:
        lv = int(c.get("level") or 0)
        if lv == 2:
            cur = {"node": c, "children": []}
            blocks.append(cur)
        elif cur is not None and lv >= 3:
            cur["children"].append(c)
    return blocks


def _promote_outline_l2_groups(
    groups: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    仅 1 个 L1、其下 ≥2 个「一、二、…」式 L2 时：
    把这些 L2 提升为抽样用的 L1（MAP 原文不变，仅组装切段）。
    解决干部大会把书名当唯一 L1、大纲全挤在 L2 的问题。
    """
    if len(groups) != 1:
        return groups, False
    blocks = _split_l2_blocks(groups[0].get("children") or [])
    if len(blocks) < 2:
        return groups, False
    outline_blocks = [
        b for b in blocks
        if _is_outline_sampling_title((b["node"].get("title") or ""))
    ]
    use = outline_blocks if len(outline_blocks) >= 2 else blocks
    if len(use) < 2:
        return groups, False
    return use, True


def assemble_sample_from_structure(
    raw_text: str,
    parsed: Dict[str, Any],
    max_chars: int = 28000,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    按 DocStructure 组装原文抽样。
    成功返回 (sampled, stats)；页码对不上或内容过少返回 (None, stats) 供回退。
    """
    from app_chat.skill_generate import (
        _is_low_value_section_title,
        _sample_within_section,
    )

    stats: Dict[str, Any] = {
        "mode": "doc_structure",
        "source": parsed.get("source"),
        "confidence": parsed.get("confidence"),
        "section_count": 0,
        "has_chapter_structure": True,
        "per_section": [],
        "toc_included": True,
        "toc_len": 0,
        "jie_title_count": 0,
        "note": "",
        "page_hit_ratio": 0.0,
        "promoted_outline_l2": False,
    }
    text = raw_text or ""
    groups = _l1_groups(parsed.get("nodes") or [])
    if not groups:
        stats["note"] = "无 L1 节点"
        return None, stats

    groups, promoted = _promote_outline_l2_groups(groups)
    stats["promoted_outline_l2"] = promoted

    map_block = parsed.get("map_text") or ""
    struct_wrap = f"【文档结构】\nsource: {parsed.get('source')}\n{map_block}\n\n"
    stats["toc_len"] = len(map_block)
    content_budget = max(2000, max_chars - len(struct_wrap))
    # 目标吃满约 90%～94% 正文预算
    fill_target = int(content_budget * 0.92)

    # 未超预算：结构地图 + 全文（仍保留结构指引）
    if len(text) <= content_budget:
        sampled = struct_wrap + text
        if len(sampled) > max_chars:
            sampled = sampled[:max_chars]
        stats["section_count"] = len(groups)
        stats["sampled_len"] = len(sampled)
        stats["page_hit_ratio"] = 1.0
        stats["note"] = (
            f"DocStructure({parsed.get('source')}) 全文+结构图 "
            f"L1={len(groups)}"
            + (" promoted_outline_l2" if promoted else "")
        )
        return sampled, stats

    hits = 0
    bodies: List[Tuple[str, str, List[Dict[str, Any]]]] = []
    for g in groups:
        n = g["node"]
        body = slice_by_page_range(text, n["p0"], n["p1"])
        if body:
            hits += 1
        bodies.append((n["title"], body, g["children"]))
    ratio = hits / max(1, len(groups))
    stats["page_hit_ratio"] = round(ratio, 3)
    if ratio < 0.4 or hits == 0:
        stats["note"] = f"页码对齐失败 hit={hits}/{len(groups)}"
        return None, stats

    usable = [(t, b, ch) for t, b, ch in bodies if b]
    if not usable:
        stats["note"] = "所有 L1 切片为空"
        return None, stats

    stats["section_count"] = len(usable)
    n = len(usable)
    lengths = [len(b) for _, b, _ in usable]
    total_len = sum(lengths) or 1

    # 按篇幅加权配额，整体对准 fill_target
    weights: List[float] = []
    for title, body, _ch in usable:
        w = float(max(len(body), 1))
        if _is_low_value_section_title(title):
            w = min(w, 1200.0)
        weights.append(w)
    sum_w = sum(weights) or 1.0

    quotas: List[int] = []
    if n == 1:
        quotas = [min(len(usable[0][1]), fill_target)]
    else:
        for title, body, w in zip(
            [u[0] for u in usable],
            [u[1] for u in usable],
            weights,
        ):
            q = int(fill_target * (w / sum_w))
            if _is_low_value_section_title(title):
                q = min(q, 700)
            # 单段上限放宽，避免长文预算吃不满
            q = max(500, min(q, len(body), int(content_budget * 0.62)))
            quotas.append(q)

        sum_q = sum(quotas) or 1
        if sum_q > fill_target:
            quotas = [
                max(400, int(q * fill_target / sum_q)) for q in quotas
            ]
        elif sum_q < fill_target * 0.88:
            # 仍偏短：把剩余预算按「正文还有空」的段补齐
            leftover = fill_target - sum_q
            room_idxs = [
                i for i, ((_, body, _), q) in enumerate(zip(usable, quotas))
                if len(body) > q + 80 and not _is_low_value_section_title(usable[i][0])
            ]
            while leftover > 100 and room_idxs:
                add_each = max(50, leftover // len(room_idxs))
                new_room = []
                for i in room_idxs:
                    body_len = len(usable[i][1])
                    grow = min(add_each, body_len - quotas[i], leftover)
                    if grow <= 0:
                        continue
                    quotas[i] += grow
                    leftover -= grow
                    if body_len > quotas[i] + 80:
                        new_room.append(i)
                if not new_room:
                    break
                room_idxs = new_room

    pieces: List[str] = []
    used = 0
    for i, ((title, body, children), quota) in enumerate(zip(usable, quotas), 1):
        room = content_budget - used
        take = min(quota, room)
        if take < 200:
            break
        jie_titles = [c["title"] for c in children if c.get("level") == 2]
        # 提升后的 L1 原是 L2，其子为 L3；抽样时 L3 当节标题
        if not jie_titles and children:
            jie_titles = [c["title"] for c in children if c.get("level") >= 3]
        # 用整段正文 + 节标题做段内抽样，比按子节点页切片更易吃满配额
        sampled_body = _sample_within_section(
            body, take, jie_titles=jie_titles or None
        )

        block = f"【节选 {i}/{n} · {title}】\n{sampled_body}".strip()
        pieces.append(block)
        used += len(block) + 8
        stats["per_section"].append({
            "i": i,
            "title": f"L1 {title}"[:80],
            "src_len": len(body),
            "quota": take,
            "got": len(sampled_body),
        })
        if used >= content_budget:
            break

    # 仍明显未满：把剩余预算补给还有正文余量的段
    if pieces and used < fill_target * 0.85:
        leftover = fill_target - used
        for idx, ((title, body, children), row) in enumerate(
            zip(usable[: len(pieces)], stats["per_section"])
        ):
            if leftover < 200:
                break
            got = int(row.get("got") or 0)
            if len(body) <= got + 100:
                continue
            extra = min(leftover, len(body) - got, max(400, leftover // 2))
            new_take = got + extra
            jie_titles = [c["title"] for c in children if c.get("level") == 2]
            if not jie_titles and children:
                jie_titles = [
                    c["title"] for c in children if c.get("level") >= 3
                ]
            new_body = _sample_within_section(
                body, new_take, jie_titles=jie_titles or None
            )
            if len(new_body) <= got + 50:
                continue
            delta = len(new_body) - got
            pieces[idx] = (
                f"【节选 {idx + 1}/{n} · {title}】\n{new_body}".strip()
            )
            row["quota"] = new_take
            row["got"] = len(new_body)
            used += delta
            leftover -= delta

    if not pieces:
        stats["note"] = "组装结果为空"
        return None, stats

    sampled = struct_wrap + "\n\n".join(pieces)
    if len(sampled) > max_chars:
        sampled = sampled[:max_chars]
    if len(sampled) < min(1500, max_chars // 4) and len(text) > max_chars:
        stats["note"] = f"组装过短 sampled={len(sampled)}"
        return None, stats

    stats["sampled_len"] = len(sampled)
    stats["note"] = (
        f"DocStructure({parsed.get('source')}/{parsed.get('confidence')}) "
        f"L1={len(usable)} page_hit={hits}/{len(groups)}"
        + (" promoted_outline_l2" if promoted else "")
    )
    return sampled, stats


def extract_and_save_doc_structure(
    usr_name: str,
    docs_name: str,
    raw_text: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
    """
    调用 DeepSeek 抽取结构并落盘。
    返回 (md_path|None, parsed|None, message)。
    """
    path = store.doc_structure_path(usr_name, docs_name)
    content = truncate_like_presummary(raw_text or "")
    if not content.strip():
        return None, None, "原文为空"

    user_prompt = (
        "请根据下列文档全文抽取 DOC_STRUCTURE（严格按系统格式输出）。\n\n"
        f"文档名: {docs_name}\n\n"
        f"{content}"
    )
    print(
        f"[DocStructure] 开始抽取 docs={docs_name} "
        f"input_chars={len(content)} max≈{presummary_max_content_chars()} → {path}"
    )
    try:
        raw_out = _call_deepseek_structure(DOC_STRUCTURE_SYSTEM, user_prompt)
    except Exception as e:
        print(f"[DocStructure] 调用失败: {e}")
        return None, None, f"调用失败: {e}"

    md = _normalize_structure_md(raw_out)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md if md else (raw_out or ""))
        print(f"[DocStructure] 已落盘 ({len(md)} chars): {path}")
    except Exception as e:
        print(f"[DocStructure] 落盘失败: {e}")
        return None, None, f"落盘失败: {e}"

    parsed = parse_doc_structure_md(md)
    if not parsed:
        print("[DocStructure] 解析失败，将回退纯规则抽样")
        return path, None, "解析失败"
    print(
        f"[DocStructure] 解析成功 source={parsed['source']} "
        f"confidence={parsed['confidence']} nodes={len(parsed['nodes'])}"
    )
    return path, parsed, "ok"
