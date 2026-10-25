# -*- coding: utf-8 -*-
"""文档 → Skill MD、notebook-hub 生成/更新（deepseek-chat）。"""
from __future__ import annotations
import nkcn_public_config as _public_config

import hashlib
import json
import os
import re
import threading
import traceback
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from app_chat import skills_store as store

QUALITY_PROMPT = """图书/文档蒸馏成 Skill的质量总纲。
需要精而不薄、具体、结构化清晰、有洞察的深刻性。
用意识贯穿，少直接贴「红/蓝/紫/绿」「D/M/T层」等标签墙，不要做成标签目录。

【目标】蒸的是能够提取出来「给 Agent 可理解和调用执行」的可复用技能，不是读书笔记，也不是文档摘要。
关键交付物：本质击穿、触发条件、可执行步骤、判断边界等等。禁止空洞复述；禁止把 PreSummary/章节目录改写充数；禁止用「要耐心」类常识占位。

【本质三问】Skill内容中要体现：
① 给谁用 → 定主色表达（可有一辅色）：红=行业专业知识；蓝=可照做步骤与清单；紫=思维模型与判断原则；绿=大白话类通俗易懂的解释。
② 内容里有什么 → 抽三类知识：显性（照着做：定义/概念/步骤）；组织（照着找：骨架/结构/方法）；隐性（想着判：关键信号/例外/分寸）。
③ 怎么组织 → 上·总纲（定位+触发）→ 中·方法（可执行主体）→ 下·边界意识（例外、回滚、关键节点）。健康配比：每层有主导类，另两类做接缝；避免说明书式（只显性）、目录式（只组织）、禅语式（只隐性）。

【除乘加 × DMT】
· 除：抽出 L0→L1→L2 概念簇（这份内容由哪些基础概念构成，如何分层分类）。
· 乘：一句核心运用逻辑 + 可跨内容衔接的语义关键词（建议 5～15 个，可随文档厚度略增减）。
  语义关键词要求：既有整体、又有具体细节，应该具象化、不可发虚，尽可能全面、完整地涵盖本文档内容，且实体概念覆盖尽量齐全；勿空泛堆砌，也不可脱离文档原文依据随意编造。
· 加：包容范围（能容纳哪些变体）+ 回滚条件（前提失效时退回什么安全基线）。
· DMT：立足地基（D）→ 面向场景/读者（M）→ 放眼可衔接的上层框架（T）。是有方向、共存的定位和击穿，而非三者孤立。

【Know What / How / Why】自然写进段落，让使用者/Agent 借助本 Skill 能：说出是什么（概念骨架）→ 会判断何时用并做成事（适用+步骤+边界）→ 懂为何如此并能迁移（原理与设计理由）。

【交付自检】description 的 Use when / NOT for 能命中真实场景且不误触发；文中同时符合上述目标和质量要求；不灌水、不复述目录等等。
"""

DOC_SKILL_SYSTEM = f"""你是 NKCN 文档蒸馏助手。把用户给出的文档材料蒸馏成符合 Agent Skills Spec 的 SKILL.md。
{QUALITY_PROMPT}

篇幅：description 450～900 汉字密度；正文 1500～3500 汉字；全文（含 YAML）硬上限 ≤500 行，超则压缩要点。勿为凑行数灌水或复述目录。

必须严格按以下 Markdown 结构输出（先 YAML frontmatter，再正文）：
---
name: <slug原样保留>
description: >-
  <做什么。Use when …。NOT for …。>
metadata:
  title: "<原文件名>"
  source: document
  source_doc: "<原文件名>"
  doc_role: "<scene_base|notebook_increment>"
  main_four_color: "<主色或空>"
  secondary_four_color: "<辅色或空>"
  dmt_level: "<D|M|T或空>"
  semantic_keywords: ["锚点1", "锚点2"]
  standards: ["Agent Skills Spec", "NKCN"]
  version: "1.0"
---

# <短标题>

## 核心主张
<核心命题；DMT「立足→面向→放眼」视角。>

## 何时用 / 何时不用
<适用场景 + 不适用边界>

## 怎么做（工作流）
<显性步骤为主（可照做）；方法原理为辅（会理解）；关键节点写判断信号（想着判，隐性知识，行业专家级直觉经验）。>

## 关键锚点
<除乘加落点：概念簇要点 + 核心逻辑句 + 5～15 语义关键词（既有整体又有具体细节，具象不发虚，尽量全面完整、实体概念覆盖齐全）及其深入浅出的阐释 + 包容/回滚。>

## 约束与输出期望
<Agent 调用时必须遵守的约束、期望产出形态。>

## 自检（用前过一遍）
<多种角度、全面、深入的自问自检>
"""

HUB_SYSTEM = f"""你是 NKCN 本子 Skill 总入口（notebook-hub）撰写助手。
{QUALITY_PROMPT}

一定要让模型精心生成 description 部分，这是要做总地图的，一定要整体情况和具体路由兼顾，具体说清路由情况、分类的同时，也能分好层，立足面向放眼的 D（7）M（2）T（1）视角要有，不用显式的标记 DMT，有这个意识就可以。

description ≤1024 字符，尽量写满信息密度。
正文 600～1500 汉字，结构：

---
name: notebook-hub
description: >-
  <总地图>
metadata:
  title: "本子 Skill 总入口"
  source: notebook
  version: "1.0"
---

# 本子 Skill 总入口

## 本子里有什么
...

## 怎么路由
...

## 使用原则
...

## 自检
...
"""

_LOCK = threading.Lock()
_INFLIGHT = set()


def _call_deepseek_chat(system: str, user: str, max_tokens: int = 4096) -> str:
    from app_chat.scene_models import resolve_openai_cfg_from_abbr
    cfg = resolve_openai_cfg_from_abbr("deepseek-chat")
    client = OpenAI(
        api_key=cfg.get("api_key") or os.environ.get("DEEPSEEK_API_KEY") or _public_config.secret('DEEPSEEK_API_KEY'),
        base_url=cfg.get("base_url") or "https://api.deepseek.com",
        timeout=120.0,
    )
    model_name = str(cfg.get("model") or "deepseek-chat")
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def _strip_ocr_noise(text: str) -> str:
    """去掉 OCR 版面标记，避免抽样预算被 <|ref|> / det 坐标吃掉。"""
    if not text:
        return ""
    # 整行 OCR 元数据
    text = re.sub(r"^<\|ref\|>.*$", "", text, flags=re.M)
    text = re.sub(r"^<\|det\|>.*$", "", text, flags=re.M)
    # 行内残留
    text = re.sub(r"<\|[^|]+\|>", "", text)
    text = re.sub(r"\[\[\d+[,\s\d]*\]\]", "", text)
    # 折叠过多空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_toc_line(line: str) -> bool:
    """
    目录行判定（用于扫描时跳过，避免把目录点线当成正文标题）。
    必须像「条目 + 领袖符/对齐空白 + 页码」，避免把正文省略号误判成目录。
    """
    s = (line or "").strip()
    if not s or len(s) > 120:
        return False
    # 一行堆多个「第X章」：OCR 目录粘连
    if len(re.findall(r"第\s*[一二三四五六七八九十百千零〇\d]+\s*章", s)) >= 2:
        return True

    has_lead = bool(
        re.search(r"[\.·…．‧・]{2,}\s*\d+\s*$", s)
        or re.search(r"[-—–_]{3,}\s*\d+\s*$", s)
        or re.search(r"\s{2,}\d+\s*$", s)
    )
    if not has_lead:
        return False

    # 还须带目录结构线索，降低「正文……3」类误伤
    struct = re.search(
        r"(?:"
        r"第\s*[一二三四五六七八九十百千零〇\d]+\s*(?:章|节|部分|篇|编|卷)|"
        r"^[一二三四五六七八九十百]+\s*[、．.\s]|"
        r"^\d+\s*[、]|"
        r"^\d+\.\d+|"
        r"^[【\[]\s*[一二三四五六七八九十百\d]+|"
        r"^[（(]\s*[一二三四五六七八九十百\d]+|"
        r"^附录|"
        r"^(?:Chapter|Section|Sec\.?|§)\s*"
        r")",
        s,
        re.I,
    )
    return bool(struct)


def _is_low_value_section_title(title: str) -> bool:
    """字表/参考文献/目录页等：抽样时压配额，避免吃掉正文预算。"""
    t = title or ""
    if re.search(r"字表|常用字|背诵推荐篇目|拼音|笔画", t):
        return True
    if re.search(r"(?:^|\#+\s*)目录\b", t) or t.strip() in ("目录", "## 目录", "# 目录"):
        return True
    if re.search(r"参考文献", t) and len(t) < 40:
        return True
    return False


def _normalize_toc_line(line: str) -> str:
    """目录行 OCR 归一：全角数字/点、第 X 章散字、多余空白。"""
    s = (line or "").strip()
    s = s.translate(str.maketrans("０１２３４５６７８９．　", "0123456789. "))
    # 先合并「部分」，再合并章/节/篇/编/卷（避免「部」半词误伤）
    s = re.sub(
        r"第\s*([一二三四五六七八九十百千零〇\d]+)\s*部分",
        r"第\1部分",
        s,
    )
    s = re.sub(
        r"第\s*([一二三四五六七八九十百千零〇\d]+)\s*(章|节|篇|编|卷)",
        r"第\1\2",
        s,
    )
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# 目录领袖符 + 页码（共用）
_TOC_LEAD_PAGE = re.compile(
    r"(?:[\.·…．‧・]{2,}|[-—–_]{2,}|\s{2,})\s*(\d+)\s*$"
)


def _extract_toc_entries(text: str) -> List[Dict[str, str]]:
    """
    从目录区提取条目。章/节常见 OCR 体例：
      章级: 第X章 / 第 X 章 / Chapter N / 第X部分 / 上编
      节级: 第X节 / Section N / §N / 一、… / 一 标题 / 【一】…
            以及有章时章下的一、二、…
      小节: （一）… / 1.1 标题（有点线页码时）
      其它: 附录 N / 目录块内纯标题+页码
    """
    head = (text or "")[: min(len(text or ""), 45000)]
    # 优先在「目录/CONTENTS」之后取；若无标记则整段 head 扫描（仍要求领袖符+页码）
    toc_mark = re.compile(
        r"^(?:#{0,3}\s*)?(?:目\s*录|CONTENTS?|Table\s+of\s+Contents)\s*$",
        re.I,
    )

    chap_pat = re.compile(
        r"^第\s*([一二三四五六七八九十百千零〇\d]+)\s*(章|节)\s*(.*?)$"
    )
    part_pat = re.compile(
        r"^第\s*([一二三四五六七八九十百千零〇\d]+)\s*(部分|篇|编|卷)\s*(.*?)$"
    )
    volume_pat = re.compile(r"^([上中下])\s*编\s*(.*?)$")
    # 中文大纲：一、 / 一． ；阿拉伯仅顿号 1、
    outline_cn_pat = re.compile(
        r"^([一二三四五六七八九十百]+)[、．]\s*(.*?)$"
    )
    outline_ar_pat = re.compile(r"^(\d+)[、]\s*(.*?)$")
    # 「一 标题」（空格、无顿号）
    outline_space_pat = re.compile(
        r"^([一二三四五六七八九十百]+)\s+([\u4e00-\u9fff].*?)$"
    )
    # 【一】标题
    bracket_pat = re.compile(
        r"^[【\[]\s*([一二三四五六七八九十百\d]+)\s*[】\]]\s*(.*?)$"
    )
    # （一）标题 — 仅中文括号数字，排除习题 (1)
    paren_pat = re.compile(
        r"^[（(]\s*([一二三四五六七八九十百]+)\s*[）)]\s*(.*?)$"
    )
    # Section / Sec. / §
    section_en_pat = re.compile(
        r"^(?:Section|Sec\.?|§)\s*([0-9IVXLC]+)\s*(.*?)$",
        re.I,
    )
    # 1.1 / 2.3.1 节号
    decimal_pat = re.compile(r"^(\d+\.\d+(?:\.\d+)?)\s+(.+)$")
    app_pat = re.compile(r"^附录\s*(\d+)?\s*(.*?)$")
    chapter_en_pat = re.compile(
        r"^(?:Chapter|CHAPTER|Chap\.?)\s*([0-9IVXLC]+)\s*(.*?)$",
        re.I,
    )
    # 仅跳过纯西文 A. 与「1. 」(单层点号+空格，易与正文列表混淆的留给 decimal/outline)
    skip_pat = re.compile(
        r"^(?:"
        r"[A-Za-z]\s*[\.．、]\s+\S|"  # A. / A、
        r"\d+\s*[\.．]\s+(?!\d)"  # 1. xxx 但不是 1.1
        r")"
    )

    lines = head.splitlines()
    # 定位目录块：标记后连续目录行；无标记则全 head
    regions: List[Tuple[int, int]] = []
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        plain = re.sub(r"^#+\s*", "", raw).strip()
        if toc_mark.match(plain):
            j = i + 1
            while j < len(lines):
                t = _normalize_toc_line(re.sub(r"^#+\s*", "", lines[j].strip()))
                if not t:
                    j += 1
                    continue
                # 离开目录：很长且无领袖符的正文行
                if len(t) > 72 and not _TOC_LEAD_PAGE.search(t) and not skip_pat.match(t):
                    if not re.match(r"^(?:附录|第|Chapter)", t, re.I):
                        break
                j += 1
            regions.append((i + 1, j))
            i = j
            continue
        i += 1
    if not regions:
        regions = [(0, len(lines))]

    out: List[Dict[str, str]] = []
    seen = set()

    def _push(kind: str, num: str, title: str, match_title: str, page: str = "") -> None:
        title_c = re.sub(r"\s+", "", title or "")
        match_c = re.sub(r"\s+", "", match_title or title or "")
        if len(title_c) < 2 and kind != "appendix":
            return
        if kind == "outline":
            key = f"outline:{num}、{title_c}"
        elif kind == "section":
            key = f"section:{num}:{title_c}"
        elif kind == "subsection":
            key = f"subsec:{num}:{title_c}"
        elif kind == "chapter":
            key = f"chap:{num}"
        elif kind == "part":
            key = f"part:{num}"
        elif kind == "appendix":
            key = f"app:{num or title_c}"
        else:
            key = f"{kind}:{num}:{title_c}"
        if key in seen:
            return
        seen.add(key)
        out.append({
            "kind": kind,
            "num": num or "",
            "title": title_c,
            "match_title": match_c,
            "page": page or "",
        })

    allow_bare = bool(regions and regions != [(0, len(lines))])

    for start, end in regions:
        for li in range(start, end):
            raw = lines[li].strip()
            if not raw:
                continue
            s = _normalize_toc_line(re.sub(r"^#+\s*", "", raw))
            if not s or skip_pat.match(s):
                continue
            m_lead = _TOC_LEAD_PAGE.search(s)
            if not m_lead:
                continue
            body = s[: m_lead.start()].strip(" \t-—–_.·…．‧・")
            if not body:
                continue

            kind, num, title, match_title = "", "", "", ""

            m = chap_pat.match(body)
            if m:
                unit = m.group(2)
                num = m.group(1)
                title = (m.group(3) or "").strip()
                if unit == "节":
                    kind = "section"
                    match_title = title or f"第{num}节"
                else:
                    kind = "chapter"
                    match_title = title or f"第{num}{unit}"
            if not kind:
                m = part_pat.match(body)
                if m:
                    kind, num = "part", m.group(1)
                    title = (m.group(3) or "").strip()
                    match_title = title or f"第{num}{m.group(2)}"
            if not kind:
                m = volume_pat.match(body)
                if m:
                    kind, num = "part", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = title or f"{num}编"
            if not kind:
                m = chapter_en_pat.match(body)
                if m:
                    kind, num = "chapter", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = title or f"Chapter {num}"
            if not kind:
                m = section_en_pat.match(body)
                if m:
                    kind, num = "section", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = title or f"Section {num}"
            if not kind:
                m = app_pat.match(body)
                if m:
                    kind, num = "appendix", m.group(1) or ""
                    title = (m.group(2) or "").strip()
                    match_title = f"附录{num}{title}" if num else (title or "附录")
            if not kind:
                m = bracket_pat.match(body)
                if m:
                    kind, num = "section", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = title or f"【{num}】"
            if not kind:
                m = paren_pat.match(body)
                if m:
                    # （一）在目录里多为节下小节；有章时作 subsection，无章时当 section
                    kind, num = "subsection", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = f"（{num}）{title}" if title else f"（{num}）"
            if not kind:
                m = decimal_pat.match(body)
                if m:
                    kind, num = "subsection", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = f"{num}{title}"
            if not kind:
                m = outline_cn_pat.match(body)
                if m:
                    kind, num = "outline", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = f"{num}、{title}"
            if not kind:
                m = outline_ar_pat.match(body)
                if m:
                    kind, num = "outline", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = f"{num}、{title}"
            if not kind:
                m = outline_space_pat.match(body)
                if m:
                    kind, num = "outline", m.group(1)
                    title = (m.group(2) or "").strip()
                    match_title = f"{num} {title}"
            if not kind and allow_bare:
                # 目录块内：纯标题 + 领袖符 + 页码（无序号）
                if 4 <= len(re.sub(r"\s+", "", body)) <= 40 and not re.match(
                    r"^[\d一二三四五六七八九十百]+$", body
                ):
                    kind, num, title, match_title = "bare", "", body, body

            if kind:
                _push(kind, num, title, match_title, m_lead.group(1))

    # 若目录里已有「第X章」，则其下的「一、二、」视为节级
    if any(e.get("kind") == "chapter" for e in out):
        for e in out:
            if e.get("kind") == "outline":
                e["kind"] = "section"
            # 无章时 subsection 已是（一）/1.1；有章时保持 subsection，供章内细切
    else:
        # 无章结构：subsection 升为 section（课标（一）等可作切段线索）
        for e in out:
            if e.get("kind") == "subsection":
                e["kind"] = "section"

    return out


def _extract_toc_block_text(text: str, max_chars: int = 2400) -> str:
    """
    抽出目录结构文本，注入 Skill 原文抽样（保证章/节地图进模型）。
    优先原始目录块；否则用解析条目渲染层级。
    """
    entries = _extract_toc_entries(text)
    if len(entries) < 2:
        return ""

    head = (text or "")[: min(len(text or ""), 45000)]
    lines = head.splitlines()
    toc_mark = re.compile(
        r"^(?:#{0,3}\s*)?(?:目\s*录|CONTENTS?|Table\s+of\s+Contents)\s*$",
        re.I,
    )
    skip_pat = re.compile(
        r"^(?:"
        r"[（(]\s*[一二三四五六七八九十百\d]+\s*[）)]|"
        r"\d+\s*[\.．]\s*\d|"
        r"\d+\s*[\.．]\s+\S|"
        r"[A-Za-z]\s*[\.．、]\s+\S"
        r")"
    )
    raw_chunks: List[str] = []
    i = 0
    while i < len(lines):
        plain = re.sub(r"^#+\s*", "", lines[i].strip()).strip()
        if toc_mark.match(plain):
            chunk = [lines[i].rstrip()]
            j = i + 1
            while j < len(lines):
                t = _normalize_toc_line(re.sub(r"^#+\s*", "", lines[j].strip()))
                if not t:
                    j += 1
                    continue
                if len(t) > 72 and not _TOC_LEAD_PAGE.search(t) and not skip_pat.match(t):
                    if not re.match(r"^(?:附录|第|Chapter)", t, re.I):
                        break
                chunk.append(lines[j].rstrip())
                j += 1
            raw_chunks.append("\n".join(chunk).strip())
            i = j
            continue
        i += 1

    if raw_chunks:
        block = "\n\n".join(raw_chunks).strip()
    else:
        # 无「目录」标题时（如直接从第一章条目起）：按解析结果渲染章/节树
        rendered: List[str] = []
        for e in entries:
            kind = e.get("kind") or ""
            num = e.get("num") or ""
            title = e.get("title") or ""
            mt = e.get("match_title") or title
            if kind == "chapter":
                rendered.append(f"第{num}章 {title}".strip())
            elif kind == "part":
                if num in ("上", "中", "下"):
                    rendered.append(f"{num}编 {title}".strip())
                else:
                    rendered.append(f"第{num}部分 {title}".strip())
            elif kind == "section":
                rendered.append(f"  · {mt}")
            elif kind == "subsection":
                rendered.append(f"    · {mt}")
            elif kind == "appendix":
                rendered.append(f"附录{num} {title}".strip() if num else f"附录 {title}".strip())
            elif kind == "outline":
                rendered.append(mt)
            elif kind == "bare":
                rendered.append(mt)
        block = "\n".join(rendered).strip()

    if not block:
        return ""
    if len(block) > max_chars:
        keep = max_chars - 8
        head_n = int(keep * 0.7)
        tail_n = keep - head_n
        block = block[:head_n].rstrip() + "\n……\n" + block[-tail_n:].lstrip()
    return block


def _toc_jie_titles(text: str) -> List[str]:
    """目录中的节级标题，供章内按节抽样对齐。"""
    titles = []
    for e in _extract_toc_entries(text):
        if e.get("kind") not in ("section", "subsection"):
            continue
        t = e.get("title") or ""
        mt = e.get("match_title") or ""
        for cand in (t, mt):
            if not cand:
                continue
            if cand not in titles:
                titles.append(cand)
            bare = re.sub(
                r"^(?:"
                r"第[一二三四五六七八九十百千零〇\d]+节|"
                r"[一二三四五六七八九十百]+\d*[、．.\s]|"
                r"[（(][一二三四五六七八九十百\d]+[）)]|"
                r"[【\[][一二三四五六七八九十百\d]+[】\]]|"
                r"(?:Section|Sec\.?|§)\s*[0-9IVXLC]+|"
                r"\d+(?:\.\d+)+"
                r")",
                "",
                cand,
                flags=re.I,
            )
            bare = bare.strip(" 、．.:：")
            if bare and bare not in titles and len(bare) >= 2:
                titles.append(bare)
    return titles


def _match_jie_heading_line(line: str, *, allow_sub: bool = True) -> Optional[Tuple[str, str]]:
    """
    判断一行是否像「节」标题。
    返回 (tier, title)：tier 为 primary|sub；无法识别则 None。

    覆盖常见体例：
      primary: 第X节 / Section N / §N / 一、… / 【一】… / 一 标题
      sub:     （一）… / 1.1 标题（仅 allow_sub 时）
    """
    raw = (line or "").strip()
    if not raw or len(raw) > 70:
        return None
    if _is_toc_line(raw):
        return None
    s = re.sub(r"^#+\s*", "", raw).strip()
    s = _normalize_toc_line(s)
    if not s or len(s) > 60:
        return None
    # 章/附录/后记不是节
    if re.match(
        r"^(?:第\s*\S+\s*章|附录|参考文献|后记|前言|序言|目录|Chapter\s+)",
        s,
        re.I,
    ):
        return None

    # —— primary ——
    if _is_noise_heading(s):
        return None

    m = re.match(
        r"^第\s*([一二三四五六七八九十百千零〇\d]+)\s*节\s*[：:\s]*(.*)$",
        s,
    )
    if m:
        rest = (m.group(2) or "").strip()
        return "primary", (rest or f"第{m.group(1)}节")[:60]

    m = re.match(
        r"^(?:Section|Sec\.?|§)\s*([0-9IVXLC]+)\s*[：:\s.]*(.*)$",
        s,
        re.I,
    )
    if m:
        rest = (m.group(2) or "").strip()
        return "primary", (rest or f"Section {m.group(1)}")[:60]

    m = re.match(
        r"^[【\[]\s*([一二三四五六七八九十百\d]+)\s*[】\]]\s*(.+)$",
        s,
    )
    if m:
        return "primary", m.group(2).strip()[:60]

    m = re.match(
        r"^([一二三四五六七八九十百]+)[、．.]\s*(.+)$",
        s,
    )
    if m and len(m.group(2).strip()) >= 2:
        return "primary", f"{m.group(1)}、{m.group(2).strip()}"[:60]

    # 「一 标题」无顿号：标题须以汉字开头，避免「一 2」之类
    m = re.match(
        r"^([一二三四五六七八九十百]+)\s+([\u4e00-\u9fff].{0,36})$",
        s,
    )
    if m:
        return "primary", f"{m.group(1)} {m.group(2).strip()}"[:60]

    if not allow_sub:
        return None

    # —— sub（小节，作 primary 不足时的回退）——
    # 仅中文（一）（二）；排除习题 (1)(2)
    m = re.match(
        r"^[（(]\s*([一二三四五六七八九十百]+)\s*[）)]\s*(.+)$",
        s,
    )
    if m and len(m.group(2).strip()) >= 2:
        return "sub", f"（{m.group(1)}）{m.group(2).strip()}"[:60]

    # 1.1 / 2.3 节号（须有小数点分层，排除「1. 选择题」）
    m = re.match(r"^(\d+\.\d+(?:\.\d+)?)\s+([\u4e00-\u9fff].{1,40})$", s)
    if m:
        return "sub", f"{m.group(1)} {m.group(2).strip()}"[:60]

    return None


def _is_noise_heading(clean: str) -> bool:
    """OCR 噪声/习题小标题，不参与顶级切段与目录对齐。"""
    s = (clean or "").strip()
    if not s:
        return True
    # 多章粘连
    if len(re.findall(r"第\s*[一二三四五六七八九十百千零〇\d]+\s*章", s)) >= 2:
        return True
    # 「3. 突出…」「1. 已知」等阿拉伯点号列表（非 1.1 节号）
    if re.match(r"^\d+\.\s+", s) and not re.match(r"^\d+\.\d+", s):
        return True
    # 重复噪声 ## 2. 2. 2. 2.
    if re.search(r"(?:\d+\.\s*){3,}", s):
        return True
    # 习题 (1)(2)
    if re.match(r"^[（(]\s*\d+\s*[）)]", s):
        return True
    # 「一、一、一、」类 OCR 碎屑
    if re.search(r"([一二三四五六七八九十])、\s*\1、\s*\1、", s):
        return True
    # 「目见者见，目见者见，目见者见」类重复碎片
    if re.search(r"(.{2,10})\1\1", s):
        return True
    return False


def _heading_matches_toc_title(heading: str, toc_title: str) -> bool:
    """正文标题与目录条目是否同一节（去空白；剥章节/大纲/附录前缀后再比）。"""
    def _norm(s: str) -> str:
        s = re.sub(r"\s+", "", s or "")
        s = re.sub(r"^#{1,3}", "", s)
        s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        return s

    def _strip_prefix(s: str) -> str:
        s = re.sub(r"^第[一二三四五六七八九十百千零〇\d]+(?:章|节|部分|篇|编|卷)", "", s)
        s = re.sub(r"^[上中下]编", "", s)
        s = re.sub(r"^(?:Chapter|CHAPTER|Chap\.?)[0-9IVXLC]+", "", s, flags=re.I)
        s = re.sub(r"^[一二三四五六七八九十百]+\d*[、．.]", "", s)
        s = re.sub(r"^\d+[、]", "", s)
        s = re.sub(r"^附录\d*", "", s)
        return s

    def _ok_substr(short: str, long_: str) -> bool:
        # 收紧：短串至少 6 字，且占长串 ≥75%，避免「课程内容」「大单元整体学习」误咬长标题
        if len(short) < 6 or short not in long_:
            return False
        return len(short) >= max(6, int(len(long_) * 0.75))

    a, b = _norm(heading), _norm(toc_title)
    if len(a) < 2 or len(b) < 2:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if _ok_substr(short, long_):
        return True
    a2, b2 = _strip_prefix(a), _strip_prefix(b)
    if a2 and b2:
        if a2 == b2:
            return True
        short2, long2 = (a2, b2) if len(a2) <= len(b2) else (b2, a2)
        if _ok_substr(short2, long2):
            return True
    return False


def _outline_num_of(title: str) -> Optional[str]:
    """从标题取出顶级大纲序号「一」「二」…（仅顿号/点号，不含「四 生物进化」空格体）。"""
    s = re.sub(r"^#+\s*", "", (title or "").strip())
    m = re.match(r"^([一二三四五六七八九十百]+)[、．.]", s)
    return m.group(1) if m else None


def _chapter_num_of(title: str) -> Optional[str]:
    s = re.sub(r"^#+\s*", "", (title or "").strip())
    m = re.search(r"第\s*([一二三四五六七八九十百千零〇\d]+)\s*章", s)
    return m.group(1) if m else None


def _find_page_offset(text: str, page: int, min_offset: int = 0) -> int:
    """在 OCR 正文中定位「第 N 页」标记起点；找不到返回 -1。"""
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


def _expand_oversized_toc_sections(
    sections: List[Dict[str, Any]],
    text: str,
) -> List[Dict[str, Any]]:
    """
    「## 目录」段若吞进大量正文（常见于大纲体会议稿），
    按正文里的「## 一、…」标题拆开。
    """
    if not sections:
        return sections
    outline_re = re.compile(
        r"(?m)^(#{1,3}\s+)([一二三四五六七八九十百]+[、．][^\n]{2,60})\s*$"
    )
    out: List[Dict[str, Any]] = []
    for sec in sections:
        title = sec.get("title") or ""
        body = sec.get("text") or ""
        is_toc = bool(
            re.search(r"(?:^|\#+\s*)目录\b", title)
            or title.strip() in ("目录", "## 目录", "# 目录")
        )
        if not is_toc or len(body) < 8000:
            out.append(sec)
            continue
        # 相对整段的命中 → 绝对 offset
        abs_start = int(sec.get("start") or 0)
        hits: List[Tuple[int, str]] = []
        for m in outline_re.finditer(body):
            clean = m.group(2).strip()
            if _is_noise_heading(clean):
                continue
            # 跳过仍像目录点线的行
            line = body[m.start(): body.find("\n", m.start()) if body.find("\n", m.start()) > 0 else m.end()]
            if _is_toc_line(line):
                continue
            hits.append((abs_start + m.start(), f"## {clean}"[:80]))
        if len(hits) < 2:
            out.append(sec)
            continue
        # 目录头（到第一个大纲正文标题）保留为目录段
        first = hits[0][0]
        head_body = text[abs_start:first].strip()
        if head_body:
            out.append({
                "title": title,
                "text": head_body,
                "start": abs_start,
                "end": first,
            })
        for i, (st, lab) in enumerate(hits):
            en = hits[i + 1][0] if i + 1 < len(hits) else int(sec.get("end") or len(text))
            bit = text[st:en].strip()
            if len(bit) < 80:
                continue
            out.append({"title": lab, "text": bit, "start": st, "end": en})
    return out


def _split_doc_into_sections(text: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    按章节/标题/页码切段。返回 (sections, mode)。
    mode: chapter | page | window
    section: {title, text, start, end}
    """
    text = text or ""
    if not text.strip():
        return [], "empty"

    lines = text.splitlines(keepends=True)

    # 强章节：第X章 / 前言|目录|附录|后记 等（排除目录点线正文）
    # 不用匹配所有 ## 小节，否则扫描件书会被切成几百段、预算稀释
    strong_chapter_re = re.compile(
        r"^(?:"
        r"\#{1,3}\s*第\s*[一二三四五六七八九十百千零〇\d]+\s*章\b|"
        r"第\s*[一二三四五六七八九十百千零〇\d]+\s*章\s*[：:\s]?\S|"
        r"\#{1,2}\s*(?:附录|参考文献|后记|序言|前言|绪论|结语|目录)\b|"
        r"(?:附录|参考文献|后记|目录)\s*$|"
        r"(?:Appendix|Chapter)\s+[\dIVXLC]+\b"
        r")",
        re.IGNORECASE,
    )
    # 弱标题：仅一级 #（不含 ##），且不像副标题/破折号书名行
    weak_h1_re = re.compile(r"^#\s+[^#\-\s].{3,60}$")
    md_heading_re = re.compile(r"^#{1,3}\s+(.+)$")
    # 页码：PreSummary 风格 + OCR raw「第 N 页」
    page_re = re.compile(
        r"^(?:"
        r"\[页码：第\s*\d+\s*页\]|"
        r"第\s*\d+\s*页\s*$"
        r")"
    )

    strong_hits: List[Tuple[int, str]] = []
    weak_hits: List[Tuple[int, str]] = []
    page_hits: List[Tuple[int, str]] = []
    # 正文 md 标题候选，供目录补洞（第X章缺号 / 一、大纲体）
    md_heading_cands: List[Tuple[int, str, str]] = []  # offset, clean_title, raw_line
    offset = 0
    for line in lines:
        stripped = line.strip()
        if stripped:
            if page_re.match(stripped):
                page_hits.append((offset, stripped[:40]))
            if not _is_toc_line(stripped):
                mh = md_heading_re.match(stripped)
                if mh and "——" not in stripped:
                    clean = mh.group(1).strip()
                    if 2 <= len(clean) <= 80 and not _is_noise_heading(clean):
                        md_heading_cands.append((offset, clean, stripped[:80]))
                if strong_chapter_re.match(stripped):
                    # 章间短「参考文献」：仅当接近文末才单独立章，否则并入上一章尾巴
                    if re.search(r"参考文献", stripped):
                        if offset < len(text) * 0.85:
                            offset += len(line)
                            continue
                    # 多章粘连目录行
                    if _is_noise_heading(re.sub(r"^#+\s*", "", stripped)):
                        offset += len(line)
                        continue
                    strong_hits.append((offset, stripped[:80]))
                elif weak_h1_re.match(stripped) and "——" not in stripped:
                    # 排除纯书名重复行噪声：太短的书名行可略
                    if weak_hits and weak_hits[-1][1] == stripped[:80]:
                        offset += len(line)
                        continue
                    weak_hits.append((offset, stripped[:80]))
        offset += len(line)

    # 目录补洞：用目录顶级条目对齐正文标题
    # （课标「一、课程性质 …… 1」/ 图书「第X章 标题 ..... N」都走这里）
    # 至少 2 条才启用，避免偶然一行「一、… … 3」误触发切段
    toc_entries = _extract_toc_entries(text)
    if len(toc_entries) >= 2:
        used_offsets = {o for o, _ in strong_hits}

        def _already_covered(entry: Dict[str, str]) -> bool:
            kind = entry.get("kind") or ""
            num = entry.get("num") or ""
            match_title = entry.get("match_title") or entry.get("title") or ""
            for _, t in strong_hits:
                clean_t = re.sub(r"^#+\s*", "", t).strip()
                if kind == "chapter" and num:
                    if _chapter_num_of(clean_t) == num:
                        return True
                if kind == "outline" and num:
                    if _outline_num_of(clean_t) == num:
                        return True
                if match_title and _heading_matches_toc_title(clean_t, match_title):
                    return True
            return False

        if md_heading_cands:
            for entry in toc_entries:
                # 节级不进顶级切段（留给章内按节抽样）；章/部分/附录/顶级大纲才立段
                if entry.get("kind") in ("section", "subsection", "bare"):
                    continue
                # 顶级大纲只认中文「一、二、…」，避免 TOC 子条/噪声
                if entry.get("kind") == "outline":
                    mt0 = entry.get("match_title") or ""
                    if not re.match(r"^[一二三四五六七八九十百]+[、．]", mt0):
                        continue
                match_title = entry.get("match_title") or entry.get("title") or ""
                if not match_title or _already_covered(entry):
                    continue
                for hoff, clean, raw in md_heading_cands:
                    if hoff in used_offsets:
                        continue
                    if _is_noise_heading(clean):
                        continue
                    # 跳过紧贴已有强标题的副标题行
                    if any(abs(hoff - so) < 80 for so in used_offsets):
                        continue
                    # 大纲必须同序号，避免「课程内容」误咬子条
                    if entry.get("kind") == "outline":
                        if _outline_num_of(clean) != (entry.get("num") or ""):
                            continue
                    if entry.get("kind") == "chapter":
                        cn = _chapter_num_of(clean)
                        if cn and cn != (entry.get("num") or ""):
                            continue
                    if not _heading_matches_toc_title(clean, match_title):
                        # 章：允许正文只有「大单元…」标题、无「第X章」字样
                        if entry.get("kind") == "chapter":
                            if not _heading_matches_toc_title(clean, entry.get("title") or ""):
                                continue
                        else:
                            continue
                    if entry["kind"] == "chapter":
                        label = f"## 第{entry['num']}章 {clean}"[:80]
                    elif entry["kind"] == "part":
                        n = entry.get("num") or ""
                        if n in ("上", "中", "下"):
                            label = f"## {n}编 {clean}"[:80]
                        else:
                            label = f"## 第{n}部分 {clean}"[:80]
                    else:
                        label = (raw or f"## {clean}")[:80]
                    strong_hits.append((hoff, label))
                    used_offsets.add(hoff)
                    break
            strong_hits.sort(key=lambda x: x[0])

        # 页码补洞：标题对不上时，用目录页码对齐「第 N 页」（从目录块之后起算）
        toc_mark_off_for_page = next(
            (o for o, t in strong_hits if re.search(r"(?:^|\#+\s*)目录\b", t)),
            0,
        )
        # 目录块本身常占数页，页码锚点至少推到目录标题后；找不到再放宽到目录标题后
        page_min = max(0, toc_mark_off_for_page + 2000) if toc_mark_off_for_page else 0
        for entry in toc_entries:
            if entry.get("kind") not in ("chapter", "outline", "part", "appendix"):
                continue
            if entry.get("kind") == "outline":
                mt0 = entry.get("match_title") or ""
                if not re.match(r"^[一二三四五六七八九十百]+[、．]", mt0):
                    continue
            if _already_covered(entry):
                continue
            try:
                pg = int(entry.get("page") or 0)
            except ValueError:
                pg = 0
            if pg <= 0:
                continue
            poff = _find_page_offset(text, pg, min_offset=page_min)
            if poff < 0 and toc_mark_off_for_page:
                poff = _find_page_offset(
                    text, pg, min_offset=toc_mark_off_for_page + 80
                )
            if poff < 0 or poff in used_offsets:
                continue
            if any(abs(poff - so) < 200 for so in used_offsets):
                continue
            mt = entry.get("match_title") or entry.get("title") or ""
            if entry["kind"] == "chapter":
                label = f"## 第{entry['num']}章 {mt}"[:80]
            elif entry["kind"] == "outline":
                label = f"## {mt}"[:80]
            elif entry["kind"] == "appendix":
                label = f"## {mt}"[:80]
            else:
                label = f"## {mt}"[:80]
            strong_hits.append((poff, label))
            used_offsets.add(poff)
        strong_hits.sort(key=lambda x: x[0])

        # 无「第X章」结构时：目录后的正文「## 一、…」纳入（含 TOC 漏载的四、五）
        # 有章图书不跑，避免章内「四 生物进化」之类升成顶级段
        has_chap_toc = any(e.get("kind") == "chapter" for e in toc_entries)
        if md_heading_cands and not has_chap_toc:
            toc_mark_off = next(
                (o for o, t in strong_hits if re.search(r"(?:^|\#+\s*)目录\b", t)),
                None,
            )
            outline_toc_n = sum(
                1 for e in toc_entries if e.get("kind") == "outline"
            )
            if toc_mark_off is not None or outline_toc_n >= 2:
                covered_nums = {
                    _outline_num_of(re.sub(r"^#+\s*", "", t))
                    for _, t in strong_hits
                    if _outline_num_of(re.sub(r"^#+\s*", "", t))
                }
                outline_by_num = {
                    e.get("num"): e
                    for e in toc_entries
                    if e.get("kind") == "outline" and e.get("num")
                }
                for hoff, clean, raw in md_heading_cands:
                    if hoff in used_offsets or _is_noise_heading(clean):
                        continue
                    if toc_mark_off is not None and hoff <= toc_mark_off:
                        continue
                    on = _outline_num_of(clean)
                    if not on:
                        continue
                    if on in covered_nums:
                        continue
                    # 若 TOC 有该序号，优先要求标题能对上；对不上则跳过该候选
                    ent = outline_by_num.get(on)
                    if ent:
                        mt = ent.get("match_title") or ent.get("title") or ""
                        if mt and not _heading_matches_toc_title(clean, mt):
                            continue
                    if any(abs(hoff - so) < 80 for so in used_offsets):
                        continue
                    # 有 TOC 条目时用目录标准名，避免 OCR 烂标题进段名
                    if ent and (ent.get("match_title") or ent.get("title")):
                        label = f"## {ent.get('match_title') or ent.get('title')}"[:80]
                    else:
                        label = (raw or f"## {clean}")[:80]
                    strong_hits.append((hoff, label))
                    used_offsets.add(hoff)
                    covered_nums.add(on)
                strong_hits.sort(key=lambda x: x[0])

                # 仍缺的 TOC 大纲：①非噪声「## 一、」锚点；②正文出现目录题名
                for on, ent in outline_by_num.items():
                    if on in covered_nums:
                        continue
                    mt = ent.get("match_title") or ent.get("title") or ""
                    placed = False
                    for hoff, clean, raw in md_heading_cands:
                        if hoff in used_offsets or _is_noise_heading(clean):
                            continue
                        if toc_mark_off is not None and hoff <= toc_mark_off:
                            continue
                        if _outline_num_of(clean) != on:
                            continue
                        if any(abs(hoff - so) < 80 for so in used_offsets):
                            continue
                        label = f"## {mt or clean}"[:80]
                        strong_hits.append((hoff, label))
                        used_offsets.add(hoff)
                        covered_nums.add(on)
                        placed = True
                        break
                    if placed or not mt:
                        continue
                    # 目录题名关键词在正文中的首次出现
                    key = re.sub(
                        r"^[一二三四五六七八九十百]+[、．.\s]*",
                        "",
                        re.sub(r"\s+", "", mt),
                    )
                    key = key[:14]
                    if len(key) < 6:
                        continue
                    search_from = (toc_mark_off or 0) + 80
                    pos = (text or "").find(key, search_from)
                    if pos < 0:
                        # 宽松：去标点再找
                        pos = (text or "").find(key[:8], search_from)
                    if pos < 0 or pos in used_offsets:
                        continue
                    if any(abs(pos - so) < 200 for so in used_offsets):
                        continue
                    strong_hits.append((pos, f"## {mt}"[:80]))
                    used_offsets.add(pos)
                    covered_nums.add(on)
                strong_hits.sort(key=lambda x: x[0])

    def _build_from_hits(hits: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
        if not hits:
            return []
        # 文首到第一个标题也要保留（如第一章常以 # 题名出现、无「第一章」字样）
        use_hits = list(hits)
        if use_hits[0][0] > 200:
            use_hits = [(0, "文首/前言或第一章")] + use_hits
        # 丢掉粘连多章/噪声标题行
        use_hits = [
            (o, t) for o, t in use_hits
            if t == "文首/前言或第一章"
            or not _is_noise_heading(re.sub(r"^#+\s*", "", t))
        ]
        if not use_hits:
            return []
        sections = []
        for i, (start, title) in enumerate(use_hits):
            end = use_hits[i + 1][0] if i + 1 < len(use_hits) else len(text)
            body = text[start:end].strip()
            if not body:
                continue
            sections.append({"title": title, "text": body, "start": start, "end": end})
        return sections

    def _cap_sections(sections: List[Dict[str, Any]], max_n: int = 24) -> List[Dict[str, Any]]:
        if len(sections) <= max_n:
            return sections
        # 合并相邻最短段，直到不超过 max_n
        secs = [dict(s) for s in sections]
        while len(secs) > max_n:
            # 找相邻合并后仍合理的最短一对
            best_i = 0
            best_len = len(secs[0]["text"]) + len(secs[1]["text"])
            for i in range(len(secs) - 1):
                pair_len = len(secs[i]["text"]) + len(secs[i + 1]["text"])
                if pair_len < best_len:
                    best_len = pair_len
                    best_i = i
            a, b = secs[best_i], secs[best_i + 1]
            merged = {
                "title": f"{a['title']} + {b['title']}",
                "text": (a["text"] + "\n\n" + b["text"]).strip(),
                "start": a["start"],
                "end": b["end"],
            }
            secs = secs[:best_i] + [merged] + secs[best_i + 2:]
        return secs

    def _build_page_sections() -> List[Dict[str, Any]]:
        page_sections = _build_from_hits(page_hits)
        if len(page_sections) < 3:
            return []
        # 页太多时合并为约 12～16 个页组，保证每组有足够抽样配额
        if len(page_sections) > 20:
            group = max(1, len(page_sections) // 16)
            grouped = []
            for i in range(0, len(page_sections), group):
                chunk = page_sections[i:i + group]
                if not chunk:
                    continue
                grouped.append({
                    "title": f"{chunk[0]['title']}~{chunk[-1]['title']}",
                    "text": "\n\n".join(c["text"] for c in chunk),
                    "start": chunk[0]["start"],
                    "end": chunk[-1]["end"],
                })
            page_sections = grouped
        return _cap_sections(page_sections, 24)

    # 1) 强章节
    chapter_sections = _build_from_hits(strong_hits)
    chapter_sections = [s for s in chapter_sections if len(s["text"]) >= 120] or chapter_sections
    if len(chapter_sections) >= 2:
        chapter_sections = _expand_oversized_toc_sections(chapter_sections, text)
        chapter_sections = _cap_sections(chapter_sections, 24)
        # 伪章节：只切出 2 段且全文很长 → 页码均匀抽样更稳（干部大会 OCR 常见）
        if len(chapter_sections) <= 2 and len(text) > 50000 and len(page_hits) >= 8:
            page_secs = _build_page_sections()
            if len(page_secs) >= 4:
                return page_secs, "page"
        else:
            return chapter_sections, "chapter"

    # 2) 弱一级标题（#）—— 仅当数量适中（2～30）
    weak_sections = _build_from_hits(weak_hits)
    weak_sections = [s for s in weak_sections if len(s["text"]) >= 120] or weak_sections
    if 2 <= len(weak_sections) <= 30:
        weak_sections = _cap_sections(weak_sections, 24)
        if len(weak_sections) <= 2 and len(text) > 50000 and len(page_hits) >= 8:
            page_secs = _build_page_sections()
            if len(page_secs) >= 4:
                return page_secs, "page"
        return weak_sections, "chapter"

    # 3) 页码切分（OCR「第 N 页」或 [页码：第N页]）
    page_sections = _build_page_sections()
    if len(page_sections) >= 3:
        return page_sections, "page"

    # 4) 无结构：等长窗口
    n = max(8, min(16, max(1, len(text) // 4000)))
    win = max(1, (len(text) + n - 1) // n)
    sections = []
    for i in range(n):
        start = i * win
        if start >= len(text):
            break
        end = min(len(text), (i + 1) * win)
        body = text[start:end].strip()
        if not body:
            continue
        sections.append({
            "title": f"窗口{i + 1}/{n}",
            "text": body,
            "start": start,
            "end": end,
        })
    return sections, "window"


def _split_section_by_jie(
    section_text: str,
    jie_titles: Optional[List[str]] = None,
) -> List[Tuple[str, str]]:
    """
    章内按「节」切开，返回 [(节标题, 正文), ...]。
    先试 primary 体例；不足 2 段再回退 （一）/ 1.1 等 sub 体例；
    并与目录节名对齐的 ## 标题合并。
    """
    t = section_text or ""
    if len(t) < 400:
        return []

    def _collect(allow_sub: bool) -> List[Tuple[int, str]]:
        hits: List[Tuple[int, str]] = []
        offset = 0
        for line in t.splitlines(keepends=True):
            stripped = line.strip()
            if stripped:
                matched = _match_jie_heading_line(stripped, allow_sub=allow_sub)
                if matched:
                    _tier, title = matched
                    hits.append((offset, title))
            offset += len(line)

        # 目录节名 ↔ ## 标题（如「教育变革的必要性」）
        if jie_titles:
            for m in re.finditer(
                r"(?m)^(#{1,3}\s+)(?!第\s*\S+\s*章)([^\n]{2,40})\s*$",
                t,
            ):
                clean = m.group(2).strip()
                # 已是显式节行则跳过
                if _match_jie_heading_line(f"## {clean}", allow_sub=True):
                    continue
                if re.search(r"附录|参考文献|后记|目录", clean):
                    continue
                for jt in jie_titles:
                    if _heading_matches_toc_title(clean, jt):
                        hits.append((m.start(), clean[:60]))
                        break
        return hits

    hits = _collect(allow_sub=False)
    # primary 不够时，用（一）/1.1 回退，避免有节结构却抽不到
    if len({h[0] for h in hits}) < 2:
        hits = _collect(allow_sub=True)

    if not hits:
        return []

    hits = sorted(hits, key=lambda x: x[0])
    merged_hits: List[Tuple[int, str]] = []
    for off, title in hits:
        if merged_hits and abs(off - merged_hits[-1][0]) < 40:
            continue
        if merged_hits and merged_hits[-1][1] == title:
            continue
        merged_hits.append((off, title))

    if len(merged_hits) < 2:
        return []

    parts: List[Tuple[str, str]] = []
    for i, (start, title) in enumerate(merged_hits):
        end = merged_hits[i + 1][0] if i + 1 < len(merged_hits) else len(t)
        body = t[start:end].strip()
        if len(body) >= 80:
            parts.append((title, body))
    return parts if len(parts) >= 2 else []


def _sample_within_section(
    section_text: str,
    quota: int,
    jie_titles: Optional[List[str]] = None,
) -> str:
    """
    段内抽样：
    - 若能识别「节」，则尽量每节取一段（保证节覆盖）；
    - 否则回退 段首+中段+段尾。
    """
    t = (section_text or "").strip()
    if not t or quota <= 0:
        return ""
    if len(t) <= quota:
        return t

    jie_parts = _split_section_by_jie(t, jie_titles=jie_titles)
    if len(jie_parts) >= 2:
        # 节太多时均匀抽最多 12 节，头尾必留
        n_j = len(jie_parts)
        if n_j > 12:
            idxs = [0, n_j - 1]
            mid_n = 10
            for k in range(1, mid_n + 1):
                idxs.append(int(k * (n_j - 1) / (mid_n + 1)))
            idxs = sorted(set(idxs))
            jie_parts = [jie_parts[i] for i in idxs]
            n_j = len(jie_parts)

        per = max(140, quota // n_j)
        chunks: List[str] = []
        used = 0
        for title, body in jie_parts:
            room = quota - used - max(0, (n_j - len(chunks) - 1) * 80)
            take = min(per, max(120, room), len(body))
            if take <= 0:
                break
            bit = body[:take]
            cut = bit.rfind("\n\n")
            if cut > take * 0.55:
                bit = bit[:cut]
            block = f"〔{title}〕\n{bit.strip()}"
            chunks.append(block)
            used += len(block) + 8
            if used >= quota:
                break
        out = "\n\n……\n\n".join(chunks)
        if len(out) > quota:
            out = out[:quota]
        return out

    # 回退：三段配额 头 40% / 中 35% / 尾 25%
    head_q = max(80, int(quota * 0.40))
    mid_q = max(60, int(quota * 0.35))
    tail_q = max(40, quota - head_q - mid_q)

    head = t[:head_q]
    cut = head.rfind("\n\n")
    if cut > head_q * 0.6:
        head = head[:cut]

    mid_start = max(0, (len(t) - mid_q) // 2)
    mid = t[mid_start:mid_start + mid_q]
    cut = mid.find("\n\n")
    if 0 < cut < mid_q * 0.4:
        mid = mid[cut + 2:]
    cut = mid.rfind("\n\n")
    if cut > mid_q * 0.6:
        mid = mid[:cut]

    tail = t[-tail_q:]
    cut = tail.find("\n\n")
    if 0 < cut < tail_q * 0.4:
        tail = tail[cut + 2:]

    parts = [p.strip() for p in (head, mid, tail) if p and p.strip()]
    merged = []
    for p in parts:
        if merged and (p in merged[-1] or merged[-1] in p):
            continue
        merged.append(p)
    out = "\n\n……\n\n".join(merged)
    if len(out) > quota:
        out = out[:quota]
    return out


def _stratified_sample_doc_text(raw_text: str, max_chars: int = 28000) -> Tuple[str, Dict[str, Any]]:
    """
    按章/页/窗口均匀抽样原文，返回 (sampled_text, stats)。
    额外：注入完整目录结构；章内尽量按节覆盖。
    """
    raw_before = len(raw_text or "")
    raw_text = _strip_ocr_noise(raw_text or "")
    stats: Dict[str, Any] = {
        "raw_len": raw_before,
        "raw_len_after_ocr_strip": len(raw_text),
        "max_chars": max_chars,
        "mode": "empty",
        "section_count": 0,
        "has_chapter_structure": False,
        "per_section": [],
        "toc_included": False,
        "toc_len": 0,
        "jie_title_count": 0,
    }
    if not raw_text.strip():
        return "", stats

    # 目录结构预算（优先保留章/节地图）
    toc_cap = min(2400, max(600, max_chars // 12))
    toc_block = _extract_toc_block_text(raw_text, max_chars=toc_cap)
    toc_wrap_len = len(f"【文档目录】\n{toc_block}\n\n") if toc_block else 0
    stats["toc_included"] = bool(toc_block)
    stats["toc_len"] = len(toc_block) if toc_block else 0
    jie_titles = _toc_jie_titles(raw_text)
    stats["jie_title_count"] = len(jie_titles)

    content_budget = max_chars - toc_wrap_len
    if content_budget < 2000 and toc_block:
        # 目录过长时再压缩目录，给正文留空间
        toc_cap = min(1200, max_chars // 20)
        toc_block = _extract_toc_block_text(raw_text, max_chars=toc_cap)
        toc_wrap_len = len(f"【文档目录】\n{toc_block}\n\n") if toc_block else 0
        stats["toc_len"] = len(toc_block) if toc_block else 0
        content_budget = max_chars - toc_wrap_len

    if len(raw_text) <= content_budget:
        stats["mode"] = "full"
        stats["section_count"] = 1
        stats["has_chapter_structure"] = False
        sampled = raw_text
        if toc_block and "【文档目录】" not in sampled[:800]:
            # 全文模式也前置目录，避免模型漏看结构（若正文已含目录则不重复）
            has_native_toc = bool(re.search(r"(?m)^(?:#{0,3}\s*)?目录\s*$", sampled[:12000]))
            if not has_native_toc:
                sampled = f"【文档目录】\n{toc_block}\n\n{sampled}"
                if len(sampled) > max_chars:
                    sampled = sampled[:max_chars]
        stats["sampled_len"] = len(sampled)
        stats["note"] = "原文未超预算，全文保留"
        return sampled, stats

    sections, mode = _split_doc_into_sections(raw_text)
    stats["mode"] = mode
    stats["section_count"] = len(sections)
    stats["has_chapter_structure"] = mode == "chapter"
    if not sections:
        sampled = raw_text[:content_budget]
        if toc_block:
            sampled = f"【文档目录】\n{toc_block}\n\n{sampled}"
            if len(sampled) > max_chars:
                sampled = sampled[:max_chars]
        stats["sampled_len"] = len(sampled)
        stats["note"] = "切段失败，回退头截断"
        return sampled, stats

    # 每段配额：均分，设上下限；超长章可略多拿一点（按长度加权后仍封顶）
    n = len(sections)
    total_len = sum(len(s["text"]) for s in sections) or 1
    min_q = 400
    max_q = max(1200, content_budget // max(4, min(n, 12)))
    overhead = n * 60
    budget = max(1000, content_budget - overhead)
    is_low = [_is_low_value_section_title(sec.get("title") or "") for sec in sections]

    quotas: List[int] = []
    for i, sec in enumerate(sections):
        weight = len(sec["text"]) / total_len
        base_q = budget // n
        quota = int(base_q * 0.55 + budget * weight * 0.45)
        quota = max(min_q, min(max_q, quota))
        if is_low[i]:
            quota = min(quota, 600)
        quota = min(quota, max(len(sec["text"]), min_q if not is_low[i] else 600))
        quotas.append(quota)

    assigned = sum(quotas)
    leftover = budget - assigned
    if leftover > 200:
        hi_idxs = [i for i in range(n) if not is_low[i]]
        if hi_idxs:
            hi_total = sum(len(sections[i]["text"]) for i in hi_idxs) or 1
            low_reserve = sum(600 for j in range(n) if is_low[j])
            for i in hi_idxs:
                hi_max = min(len(sections[i]["text"]), max(0, budget - low_reserve))
                room = max(0, hi_max - quotas[i])
                if room <= 0:
                    continue
                extra = int(leftover * len(sections[i]["text"]) / hi_total)
                take = min(room, extra)
                quotas[i] += take
            assigned2 = sum(quotas)
            still = budget - assigned2
            if still > 100:
                for i in sorted(hi_idxs, key=lambda j: len(sections[j]["text"]), reverse=True):
                    if still <= 0:
                        break
                    hi_max = min(len(sections[i]["text"]), max(0, budget - low_reserve))
                    room = max(0, hi_max - quotas[i])
                    take = min(room, still)
                    quotas[i] += take
                    still -= take

    sampled_parts = []
    used = 0
    for i, sec in enumerate(sections):
        quota = quotas[i]
        remain = budget - used
        if i == n - 1:
            if is_low[i]:
                quota = min(quota, 600, max(0, remain))
            else:
                quota = max(quota, min(remain, max(len(sec["text"]), min_q)))
                quota = min(quota, remain)
        else:
            reserve = 0
            for j in range(i + 1, n):
                reserve += 600 if is_low[j] else min_q
            quota = min(quota, max(0, remain - reserve))

        piece = _sample_within_section(sec["text"], quota, jie_titles=jie_titles)
        title = sec.get("title") or f"段{i + 1}"
        block = f"【节选 {i + 1}/{n} · {title}】\n{piece}"
        sampled_parts.append(block)
        used += len(block)
        stats["per_section"].append({
            "i": i + 1,
            "title": title[:60],
            "src_len": len(sec["text"]),
            "quota": quota,
            "got": len(piece),
        })

    sampled = "\n\n".join(sampled_parts)
    if toc_block:
        sampled = f"【文档目录】\n{toc_block}\n\n{sampled}"
    if len(sampled) > max_chars:
        sampled = sampled[:max_chars]
    stats["sampled_len"] = len(sampled)
    stats["budget_used"] = used + toc_wrap_len
    return sampled, stats


def _load_doc_text(usr_name: str, docs_name: str, max_chars: int = 28000) -> str:
    from llm_langchain import util
    file_path = util.construct_file_path(usr_name, docs_name)
    if not os.path.exists(file_path):
        print(f"[Skill] _load_doc_text 文件不存在: {file_path}")
        return ""
    base = os.path.splitext(docs_name)[0]
    ext = os.path.splitext(docs_name)[1][1:] if os.path.splitext(docs_name)[1] else ""
    pre = os.path.join(store.notebook_root(usr_name), "pre_summary", f"{base}_Presummary_{ext}.md")
    chunks = []
    # PreSummary 预算（章节地图）；原文另有 max_chars
    pre_max = 16000

    # 1) PreSummary（若已生成）
    if os.path.isfile(pre):
        with open(pre, "r", encoding="utf-8") as f:
            pre_full = f.read()
        pre_text = pre_full[:pre_max]
        chunks.append("【PreSummary】\n" + pre_text)
        print(
            f"[Skill] 已加载 PreSummary ({len(pre_text)}/{len(pre_full)} chars"
            f"{', 已截断' if len(pre_full) > pre_max else ''}): {pre}"
        )
        # PreSummary 自身是否带章节分隔
        pre_secs = [p for p in re.split(r"\n---\n", pre_full) if p.strip()]
        print(f"[Skill] PreSummary 章节分隔段数(按---): {len(pre_secs)}")
    else:
        print(f"[Skill] 尚无 PreSummary，将仅用原文: {pre}")

    # 2) 原文：扫描件优先 OCR _raw.txt，否则 get_loader 抽文本层
    raw_src = None
    raw_text = ""
    if docs_name.lower().endswith(".pdf"):
        ocr_txt = os.path.join(os.path.dirname(file_path), f"{base}_ocr", f"{base}_raw.txt")
        if os.path.isfile(ocr_txt):
            try:
                with open(ocr_txt, "r", encoding="utf-8") as f:
                    raw_text = f.read()
                if (raw_text or "").strip():
                    raw_src = "ocr"
                    print(f"[Skill] 使用 OCR 原文 ({len(raw_text)} chars): {ocr_txt}")
                else:
                    print(f"[Skill] OCR _raw.txt 为空，回退 PDF 文本层: {ocr_txt}")
            except Exception as e:
                print(f"[Skill] 读取 OCR _raw.txt 失败，回退 PDF 文本层: {e}")
        else:
            print(f"[Skill] 无 OCR _raw.txt: {ocr_txt}")
    if raw_src is None:
        try:
            from llm_langchain.parse_input import get_loader
            docs = get_loader(file_path).load()
            raw_text = "\n".join((d.page_content or "") for d in docs)
            raw_src = "pdf_text" if docs_name.lower().endswith(".pdf") else "txt"
            print(f"[Skill] 使用 {raw_src} 加载原文 ({len(raw_text)} chars): {file_path}")
        except Exception as e:
            print(f"[Skill] 原文加载失败: {e}")
            chunks.append(f"（原文加载失败: {e}）")
            return "\n\n".join(chunks)

    label = "【文档原文摘录·OCR】" if raw_src == "ocr" else "【文档原文摘录】"

    # ---- 旧版：暴力头截断（保留备查，勿删）----
    # chunks.append(f"{label}\n" + (raw_text or "")[:max_chars])
    # if len(raw_text or "") > max_chars:
    #     print(f"[Skill] 原文已截断至 {max_chars} chars（原长 {len(raw_text)}）")
    # return "\n\n".join(chunks)
    # ---- 旧版结束 ----

    # 先剥离 OCR 噪声，再抽 DocStructure（与 PreSummary 同量输入）并尝试按结构组装
    cleaned = _strip_ocr_noise(raw_text or "")
    sampled = ""
    stats: Dict[str, Any] = {}
    used_structure = False
    try:
        from app_chat import doc_structure as ds

        _path, parsed, msg = ds.extract_and_save_doc_structure(
            usr_name, docs_name, cleaned
        )
        print(f"[Skill] DocStructure 结果: {msg} path={_path}")
        if parsed:
            sampled_try, st = ds.assemble_sample_from_structure(
                cleaned, parsed, max_chars=max_chars
            )
            if sampled_try:
                sampled, stats = sampled_try, st
                used_structure = True
                # 补齐与纯解析一致的长度字段
                stats.setdefault("raw_len", len(raw_text or ""))
                stats.setdefault("raw_len_after_ocr_strip", len(cleaned))
                stats.setdefault("max_chars", max_chars)
            else:
                print(
                    f"[Skill] DocStructure 组装未采用，回退纯解析: "
                    f"{st.get('note')}"
                )
    except Exception as e:
        print(f"[Skill] DocStructure 异常，回退纯解析: {e}")
        traceback.print_exc()

    if not used_structure:
        # 新版兜底：按章/页/窗口均匀抽样（段内头+中+尾）
        sampled, stats = _stratified_sample_doc_text(raw_text or "", max_chars=max_chars)

    chunks.append(f"{label}\n" + sampled)

    print(
        f"[Skill] 原文抽样统计: raw_len={stats.get('raw_len')} "
        f"after_ocr_strip={stats.get('raw_len_after_ocr_strip')} "
        f"sampled_len={stats.get('sampled_len')} "
        f"max_chars={max_chars} mode={stats.get('mode')} "
        f"has_chapter_structure={stats.get('has_chapter_structure')} "
        f"section_count={stats.get('section_count')} note={stats.get('note', '')}"
    )
    if stats.get("mode") == "doc_structure":
        print(
            f"[Skill] 使用 DocStructure 组装原文 "
            f"source={stats.get('source')} confidence={stats.get('confidence')} "
            f"page_hit_ratio={stats.get('page_hit_ratio')}"
        )
    elif stats.get("mode") == "chapter":
        print(f"[Skill] 检测到章节结构，共 {stats.get('section_count')} 个章节段，将按章均匀取关键片段")
    elif stats.get("mode") == "page":
        print(f"[Skill] 未稳定识别章节标题，改用页码标记切分，共 {stats.get('section_count')} 页段")
    elif stats.get("mode") == "window":
        print(f"[Skill] 无章节/页码结构，改用等长窗口均分，共 {stats.get('section_count')} 个窗口")
    elif stats.get("mode") == "full":
        print(f"[Skill] 原文未超预算，无需抽样，全文进入材料")

    # 逐段明细（章节多时只打前/后各若干，避免刷屏）
    per = stats.get("per_section") or []
    if per:
        show = per if len(per) <= 12 else (per[:6] + [{"i": "...", "title": f"...省略{len(per) - 12}段...", "src_len": "-", "quota": "-", "got": "-"}] + per[-6:])
        for row in show:
            print(
                f"[Skill]   段#{row.get('i')}: title={row.get('title')!r} "
                f"src_len={row.get('src_len')} quota={row.get('quota')} got={row.get('got')}"
            )

    return "\n\n".join(chunks)


def _resolve_doc_role(usr_name: str, real_name: str, docs_name: str) -> str:
    try:
        from zym.models import UserNotebook
        book = usr_name[len(real_name) + 1:] if usr_name.startswith(real_name + "_") else ""
        nb = UserNotebook.objects.get(username=real_name, bookName=book) if book else None
        scene_name = ""
        if nb:
            from zym.models import scene
            try:
                sc = scene.objects.filter(sid=nb.sid).first()
                scene_name = (sc.sceneDescription if sc else "") or ""
            except Exception:
                pass
        if scene_name:
            from app_chat.cross_document_suggestion import check_if_base_document
            return "scene_base" if check_if_base_document(scene_name, docs_name) else "notebook_increment"
    except Exception:
        pass
    return "notebook_increment"


def _four_color_for_doc(real_name: str, usr_name: str, docs_name: str) -> Dict[str, str]:
    out = {"main_four_color": "", "secondary_four_color": "", "dmt_level": ""}
    try:
        from zym.models import UserNotebook
        book = usr_name[len(real_name) + 1:] if usr_name.startswith(real_name + "_") else ""
        nb = UserNotebook.objects.get(username=real_name, bookName=book)
        data = json.loads(nb.documentFourColorDMT) if nb.documentFourColorDMT else {}
        attrs = data.get(docs_name) or {}
        for k in out:
            out[k] = str(attrs.get(k) or "")
    except Exception:
        pass
    return out


def _extract_skill_md(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:yaml|yml|markdown|md)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    if "---" in raw and not raw.startswith("---"):
        idx = raw.find("---")
        raw = raw[idx:]
    return raw.strip()


def update_document_skill_status(real_name: str, book_name: str, docs_name: str, status) -> None:
    """status: True/False/'pending' """
    try:
        from zym.models import UserNotebook
        nb = UserNotebook.objects.get(username=real_name, bookName=book_name)
        raw = getattr(nb, "documentSkillStatus", "") or ""
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        data[docs_name] = status
        nb.documentSkillStatus = json.dumps(data, ensure_ascii=False)
        nb.save(update_fields=["documentSkillStatus"])
    except Exception as e:
        print(f"[SkillStatus] 更新失败: {e}")


def process_document_skill(real_name: str, usr_name: str, docs_name: str) -> Tuple[bool, Optional[str]]:
    """生成/更新文档对应 Skill；成功返回 (True, skill_name)。"""
    key = f"{usr_name}::{docs_name}"
    with _LOCK:
        if key in _INFLIGHT:
            return False, "already_running"
        _INFLIGHT.add(key)
    book_name = usr_name[len(real_name) + 1:] if usr_name.startswith(real_name + "_") else None
    try:
        if not (docs_name.lower().endswith(".pdf") or docs_name.lower().endswith(".txt")):
            return False, "只支持 PDF/TXT"

        if book_name:
            update_document_skill_status(real_name, book_name, docs_name, "pending")

        slug = store.make_document_slug(docs_name)
        # cache
        from llm_langchain import util as langchain_util
        file_path = langchain_util.construct_file_path(usr_name, docs_name)
        cache_hit = _try_skill_cache(usr_name, docs_name, file_path, slug)
        if cache_hit:
            _register_doc_skill(usr_name, slug, docs_name)
            if book_name:
                update_document_skill_status(real_name, book_name, docs_name, True)
            _schedule_notebook_hub(real_name, usr_name)
            return True, slug

        material = _load_doc_text(usr_name, docs_name)
        print(f"[Skill] 材料组装完毕 docs={docs_name} material_chars={len(material or '')}")
        if not material.strip():
            print(f"[Skill] ❌ 材料为空，无法生成: {docs_name}")
            if book_name:
                update_document_skill_status(real_name, book_name, docs_name, False)
            return False, "无法读取文档内容"

        colors = _four_color_for_doc(real_name, usr_name, docs_name)
        doc_role = _resolve_doc_role(usr_name, real_name, docs_name)
        user_prompt = (
            f"文档名: {docs_name}\n"
            f"slug(name 必须用这个): {slug}\n"
            f"doc_role: {doc_role}\n"
            f"四色DMT: {json.dumps(colors, ensure_ascii=False)}\n\n"
            f"{material}"
        )
        raw = _call_deepseek_chat(DOC_SKILL_SYSTEM, user_prompt)
        md = _extract_skill_md(raw)
        fm, body = store.parse_skill_md(md)
        if not fm:
            # wrap
            fm = {
                "name": slug,
                "description": f"基于文档《{docs_name}》的方法论。Use when 用户提问与该文档主题相关时。NOT for 无关闲聊。",
                "metadata": {
                    "title": docs_name,
                    "source": "document",
                    "source_doc": docs_name,
                    "doc_role": doc_role,
                    **colors,
                    "semantic_keywords": [],
                    "standards": ["Agent Skills Spec", "NKCN"],
                    "version": "1.0",
                },
            }
            body = md
        fm["name"] = slug
        md_meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        md_meta.update({
            "title": docs_name,
            "source": "document",
            "source_doc": docs_name,
            "doc_role": doc_role,
            "main_four_color": colors.get("main_four_color") or md_meta.get("main_four_color") or "",
            "secondary_four_color": colors.get("secondary_four_color") or md_meta.get("secondary_four_color") or "",
            "dmt_level": colors.get("dmt_level") or md_meta.get("dmt_level") or "",
        })
        fm["metadata"] = md_meta
        err = store.validate_frontmatter_minimal(fm)
        if err:
            if book_name:
                update_document_skill_status(real_name, book_name, docs_name, False)
            return False, err
        # 硬上限 ≤500 行：超则截断正文后再写
        content_preview, truncated = store.trim_skill_to_max_lines(fm, body)
        if truncated:
            print(f"[Skill] 生成结果超 500 行，已截断: {docs_name}")
            fm, body = store.parse_skill_md(content_preview)
            fm["name"] = slug
        store.write_skill(usr_name, slug, fm, body)
        _save_skill_cache(docs_name, file_path, store.dump_skill_md(fm, body))
        _register_doc_skill(usr_name, slug, docs_name)
        if book_name:
            update_document_skill_status(real_name, book_name, docs_name, True)
        _schedule_notebook_hub(real_name, usr_name)
        print(f"[Skill] ✅ 文档 Skill 已生成: {slug} <- {docs_name}")
        return True, slug
    except Exception as e:
        traceback.print_exc()
        if book_name:
            update_document_skill_status(real_name, book_name, docs_name, False)
        return False, str(e)[:300]
    finally:
        with _LOCK:
            _INFLIGHT.discard(key)


def _register_doc_skill(usr_name: str, slug: str, docs_name: str) -> None:
    idx = store.load_index(usr_name)
    idx["skills"][slug] = {
        "source": "document",
        "source_doc": docs_name,
        "pack_zip": "",
        "enabled": True,
        "title": docs_name,
    }
    store.save_index(usr_name, idx)


def _cache_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skill_cache")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_key(docs_name: str, file_path: str) -> str:
    size = os.path.getsize(file_path) if os.path.isfile(file_path) else 0
    return hashlib.md5(f"{docs_name}_{size}".encode("utf-8")).hexdigest()[:12]


def _try_skill_cache(usr_name: str, docs_name: str, file_path: str, slug: str) -> bool:
    try:
        h = _cache_key(docs_name, file_path)
        base = os.path.splitext(docs_name)[0]
        path = os.path.join(_cache_dir(), f"{base}_{h}_SKILL.md")
        if not os.path.isfile(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        fm, body = store.parse_skill_md(raw)
        fm["name"] = slug
        md = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        md["source_doc"] = docs_name
        md["title"] = docs_name
        fm["metadata"] = md
        store.write_skill(usr_name, slug, fm, body)
        print(f"[Skill] 🎯 缓存命中: {path}")
        return True
    except Exception:
        return False


def _save_skill_cache(docs_name: str, file_path: str, content: str) -> None:
    try:
        h = _cache_key(docs_name, file_path)
        base = os.path.splitext(docs_name)[0]
        path = os.path.join(_cache_dir(), f"{base}_{h}_SKILL.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"[Skill] 写缓存失败: {e}")


def _schedule_notebook_hub(real_name: str, usr_name: str) -> None:
    t = threading.Thread(target=lambda: update_notebook_hub(real_name, usr_name), daemon=True)
    t.start()


def update_notebook_hub(real_name: str, usr_name: str) -> Tuple[bool, Optional[str]]:
    try:
        idx = store.reconcile_index(usr_name)
        lines = ["【本子当前 Skill 清单】"]
        for name, meta in (idx.get("skills") or {}).items():
            if name == store.NOTEBOOK_HUB_NAME:
                continue
            sk = store.read_skill(usr_name, name)
            desc = ((sk or {}).get("description") or "")[:180]
            lines.append(
                f"- name={name}; source={meta.get('source')}; source_doc={meta.get('source_doc')}; "
                f"pack={meta.get('pack_zip')}; enabled={meta.get('enabled', True)}; desc={desc}"
            )
        for zip_name, pack in (idx.get("packs") or {}).items():
            lines.append(f"- PACK {zip_name}: hub={pack.get('hub')}; members={pack.get('members')}")
        user_prompt = "\n".join(lines) if len(lines) > 1 else "本子尚无文档 Skill 或包；请写一个占位总入口，说明暂无成员。"
        raw = _call_deepseek_chat(HUB_SYSTEM, user_prompt, max_tokens=3072)
        md = _extract_skill_md(raw)
        fm, body = store.parse_skill_md(md)
        if not fm:
            fm = {
                "name": store.NOTEBOOK_HUB_NAME,
                "description": "本子 Skill 总入口。Use when 需要判断该用哪个文档 Skill 或方法论包。NOT for 与本子无关的闲聊。",
                "metadata": {"title": "本子 Skill 总入口", "source": "notebook", "version": "1.0"},
            }
            body = md or "# 本子 Skill 总入口\n\n## 本子里有什么\n（暂无）\n"
        fm["name"] = store.NOTEBOOK_HUB_NAME
        err = store.validate_frontmatter_minimal(fm)
        if err:
            # soft fix description
            fm["description"] = (fm.get("description") or "本子 Skill 总入口。")[:1024]
        store.write_skill(usr_name, store.NOTEBOOK_HUB_NAME, fm, body)
        idx = store.load_index(usr_name)
        idx["skills"][store.NOTEBOOK_HUB_NAME] = {
            "source": "notebook",
            "source_doc": "",
            "pack_zip": "",
            "enabled": True,
            "title": "本子 Skill 总入口",
        }
        idx["notebook_hub"] = store.NOTEBOOK_HUB_NAME
        store.save_index(usr_name, idx)
        print(f"[Skill] ✅ notebook-hub 已更新: {usr_name}")
        return True, None
    except Exception as e:
        traceback.print_exc()
        return False, str(e)[:300]


def spawn_document_skill_async(real_name: str, usr_name: str, docs_name: str) -> None:
    def _run():
        ok, err = process_document_skill(real_name, usr_name, docs_name)
        if not ok:
            print(f"[Skill] ❌ 生成失败 {docs_name}: {err}")
    threading.Thread(target=_run, daemon=True).start()
