# -*- coding: utf-8 -*-
"""批改配置卡：解析 / 校验 / 按文件名解析已布置页与篇次。"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from app_chat.models import Card

CONFIG_MARKER = "【批改配置卡】"
MATERIAL_SEP = "——材料——"
_IDENT_RE = re.compile(r"^材料标识[：:]\s*(.+?)\s*$")
_DESC_RE = re.compile(r"^材料说明[：:]\s*(.*)$")
_ORDER_HDR_RE = re.compile(r"^布置次序[：:]\s*$")
_BATCH_RE = re.compile(r"^第\s*(\d+)\s*次[：:]\s*(.*)$")


def is_grading_config_content(content: str) -> bool:
    return CONFIG_MARKER in (content or "")


def parse_page_list(text: str) -> List[int]:
    """解析如 1-3,7,10 → [1,2,3,7,10]，保序去重。"""
    text = (text or "").strip()
    if not text:
        return []
    out: List[int] = []
    seen: Set[int] = set()
    for part in re.split(r"[,，、\s]+", text):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[-–—~～]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            for p in range(a, b + 1):
                if p not in seen and p > 0:
                    seen.add(p)
                    out.append(p)
            continue
        if part.isdigit():
            p = int(part)
            if p > 0 and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def parse_grading_config(content: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    解析配置卡。成功返回 (data, [])；失败返回 (None, errors)。
    data = { materials: [ {filename, description, batches:[{k, pages}], assigned_pages, page_to_batch} ] }
    """
    errors: List[str] = []
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if CONFIG_MARKER not in text:
        return None, ["缺少固定标题【批改配置卡】"]

    # 按材料块切分
    parts = re.split(r"\n\s*" + re.escape(MATERIAL_SEP) + r"\s*\n", text)
    # 第一段是标题区，其后为材料
    material_chunks = parts[1:] if len(parts) > 1 else []
    if not material_chunks:
        # 兼容：标题后直接跟材料字段（少写了一个分隔行）
        after = text.split(CONFIG_MARKER, 1)[-1].strip()
        if "材料标识" in after:
            material_chunks = [after]
        else:
            return None, ["至少需要一块「——材料——」"]

    materials: List[Dict[str, Any]] = []
    seen_files: Set[str] = set()

    for idx, chunk in enumerate(material_chunks, start=1):
        lines = [ln.rstrip() for ln in chunk.strip().split("\n")]
        filename = ""
        description = ""
        batches: List[Dict[str, Any]] = []
        in_order = False
        page_owner: Dict[int, int] = {}
        dup_pages: List[int] = []

        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            m = _IDENT_RE.match(s)
            if m:
                filename = m.group(1).strip()
                continue
            m = _DESC_RE.match(s)
            if m:
                description = m.group(1).strip()
                continue
            if _ORDER_HDR_RE.match(s) or s.startswith("布置次序"):
                in_order = True
                continue
            m = _BATCH_RE.match(s)
            if m:
                in_order = True
                k = int(m.group(1))
                pages = parse_page_list(m.group(2))
                if not pages:
                    errors.append(f"材料{idx}「第{k}次」页码列表为空或无效")
                    continue
                for p in pages:
                    if p in page_owner:
                        dup_pages.append(p)
                    else:
                        page_owner[p] = k
                # 同页多次：只保留第一次
                keep = [p for p in pages if page_owner.get(p) == k]
                batches.append({"k": k, "pages": keep})
                continue
            if in_order and (s.startswith("第") or "次" in s):
                errors.append(f"材料{idx}布置行无法解析: {s[:40]}")

        if not filename or filename.startswith("（") or filename.startswith("("):
            errors.append(f"材料{idx}缺少有效「材料标识」文件名")
            continue
        if filename in seen_files:
            # 同卡重复文件名：以第一次为准，跳过后续
            continue
        seen_files.add(filename)
        if not batches:
            errors.append(f"材料「{filename}」至少需要一次有效布置")
            continue
        batches.sort(key=lambda b: b["k"])
        assigned: List[int] = []
        for b in batches:
            for p in b["pages"]:
                if p not in assigned:
                    assigned.append(p)
        if dup_pages:
            errors.append(
                f"材料「{filename}」页码重复写入多次布置（以第一次为准）: "
                + ",".join(str(p) for p in sorted(set(dup_pages)))
            )
        materials.append({
            "filename": filename,
            "description": description,
            "batches": batches,
            "assigned_pages": assigned,
            "page_to_batch": dict(page_owner),
        })

    if errors and not materials:
        return None, errors
    if not materials:
        return None, errors or ["未解析到任何有效材料块"]
    # 有重复页警告时仍允许生成（以第一次为准），但若有致命错误则失败
    fatal = [e for e in errors if "重复写入" not in e]
    if fatal:
        return None, errors
    return {"materials": materials, "warnings": [e for e in errors if "重复写入" in e]}, []


def validate_grading_config_for_create(
    content: str,
    notebook_filenames: List[str],
) -> Tuple[bool, List[str]]:
    """建卡前校验：模板 + 每个材料标识须在本子文件中完全同名。"""
    data, errors = parse_grading_config(content)
    if errors or not data:
        return False, errors or ["批改配置卡解析失败"]
    files = set(notebook_filenames or [])
    missing = []
    for mat in data["materials"]:
        if mat["filename"] not in files:
            missing.append(mat["filename"])
    if missing:
        return False, [
            "以下材料标识在本子导入区找不到完全同名文件：" + "；".join(missing)
        ]
    return True, data.get("warnings") or []


def validate_template_preset(kind: str, content: str) -> Tuple[bool, List[str]]:
    """预选项模板结构校验。"""
    text = content or ""
    if kind == "grading_config":
        data, errors = parse_grading_config(text)
        if errors or not data:
            return False, errors or ["批改配置卡模板结构不完整"]
        return True, []
    if kind == "todo":
        if not re.search(r"^\s*\d+\.\s*\S+", text, re.M):
            return False, ["TODO清单卡须至少有一条「1. …」形式的清单项"]
        return True, []
    if kind == "directory":
        first = (text.strip().split("\n")[0] if text.strip() else "").strip()
        if not first.endswith("目录"):
            return False, ["目录卡第一行须以「目录」结尾，例如「××论文目录」"]
        if not re.search(r"^[一二三四五六七八九十百]+[、.]", text, re.M) and not re.search(
            r"^\d+\.", text, re.M
        ):
            return False, ["目录卡须有「一、章名」或「1.节名」层级"]
        return True, []
    return True, []


def find_latest_grading_config_card(username: str) -> Optional[Card]:
    cards = (
        Card.objects.filter(username=username)
        .order_by("-datetime")
        .only("cid", "content", "datetime", "contentTitle")
    )
    for card in cards:
        if is_grading_config_content(card.content or ""):
            data, errors = parse_grading_config(card.content or "")
            if data and not errors:
                return card
            # 有 warnings 的 data 也可
            if data:
                return card
    return None


def resolve_material_for_filename(
    username: str,
    filename: str,
) -> Optional[Dict[str, Any]]:
    """
    无匹配 → None（调用方必须保持现网零影响）。
    有匹配 → 材料块 dict + 元信息。
    """
    if not username or not filename:
        return None
    card = find_latest_grading_config_card(username)
    if not card:
        return None
    data, _ = parse_grading_config(card.content or "")
    if not data:
        return None
    for mat in data["materials"]:
        if mat["filename"] == filename:
            out = dict(mat)
            out["config_card_id"] = card.cid
            return out
    return None


def build_session_map_from_config(
    material: Dict[str, Any],
    *,
    subject: str,
    sample_id: str,
    total_pages: int,
) -> Dict[str, Any]:
    """用配置卡第k次合成 sessions.json 结构（仅覆盖已布置页）。"""
    sessions: List[Dict[str, Any]] = []
    for i, batch in enumerate(material.get("batches") or [], start=1):
        pages = [p for p in batch.get("pages") or [] if 1 <= int(p) <= total_pages]
        if not pages:
            continue
        start, end = min(pages), max(pages)
        title = f"第{batch.get('k', i)}次布置"
        sessions.append({
            "session_index": i,
            "order_index": i,
            "session_id": f"{sample_id}_s{i:02d}",
            "page_start": start,
            "page_end": end,
            "pages": pages,  # 显式页列表（可非连续）；下游 session_page_bounds 用起止，Pass1 靠 scope
            "session_title": title,
            "unit_title": title,
            "module_title": title,
            "submodules": [],
            "boundary_signal": "grading_config_card",
            "boundary_reason": f"批改配置卡第{batch.get('k', i)}次",
            "split_source": "grading_config_card",
            "confidence": 1.0,
        })
    assigned = sorted({int(p) for p in (material.get("assigned_pages") or []) if 1 <= int(p) <= total_pages})
    unassigned = [p for p in range(1, total_pages + 1) if p not in set(assigned)]
    return {
        "subject": subject,
        "sample_id": sample_id,
        "total_pages": total_pages,
        "session_count": len(sessions),
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "session_granularity": "grading_config_batch",
        "split_source": "grading_config_card",
        "grading_config": {
            "filename": material.get("filename"),
            "config_card_id": material.get("config_card_id"),
            "assigned_pages": assigned,
            "unassigned_pages": unassigned,
            "description": material.get("description") or "",
        },
        "sessions": sessions,
    }


def list_notebook_filenames(username: str) -> List[str]:
    root = os.path.normpath(f"./received_dir/user_raw_file/{username}")
    if not os.path.isdir(root):
        return []
    skip = {
        "cardImage", "pre_summary", "pre_image_summary", "_twin", "cardCondense",
        "pre_tribal_knowledge", "skills", "_socratic_meta", "continuous_image_dmt",
        "doc_structure",
    }
    out = []
    for fn in os.listdir(root):
        if fn.startswith(".") or fn in skip:
            continue
        full = os.path.join(root, fn)
        if os.path.isfile(full):
            out.append(fn)
    return out
