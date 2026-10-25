# -*- coding: utf-8 -*-
"""
NK2026 组本素材 → 每组 Gxx.md 摘录短文生成（与文档交叉梳理卡片完成后衔接）。
产出为四个一级章节（一～四，第四节为相较既有 Gxx 的周际变化）；模型主备顺序见 generate_gxx_markdown_with_fallback（与输入总字数相关）。
"""
from __future__ import annotations
import nkcn_public_config as _public_config

import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from openai import OpenAI

from app_chat.automation_nk2026 import (
    NK2026_CHUCHENGJIA_WEEK_MIN,
    SCENE_BASE_DOC_NAMES,
    collect_nk2026_gxx_input_files,
    infer_week_for_theme_group,
    is_nk2026_ladder_scene,
    nk2026_group_role_line,
    nk2026_matches_b_planning_xml_log_gxx,
    parse_target_ladder_meta,
    read_nk2026_chuchengjia_twin_markdown,
    text_references_course_week_at_least,
    theme_keyword_in_text,
)
from app_chat.views_card_html import _image_layers_text, _is_ladder_fill_image_filename

# 与 views_continuous_image 中 dmxapi Gemini 对齐（可按环境变量覆盖）
_GEMINI_FALLBACK_BASE = os.environ.get("NKCN_DMT_GEMINI_BASE_URL", _public_config.endpoint('NKCN_REVIEW_GATEWAY_V1_URL', 'http://localhost:9999/v1'))
_GEMINI_FALLBACK_KEY = os.environ.get(
    "NKCN_DMT_GEMINI_API_KEY",
    _public_config.secret('NKCN_LLM_DMXAPI_API_KEY'),
)
_GEMINI_FALLBACK_MODEL = os.environ.get("NKCN_DMT_GEMINI_MODEL", "gemini-3.1-pro-preview")

_GROUP_TWIN_JOBS: Dict[str, Dict[str, Any]] = {}
_JOB_LOCK = threading.Lock()

_MAX_CONCURRENT_GROUPS = 3
_MAX_CHARS_DOC_BUNDLE = 45000
_PRIOR_GXX_MAX_CHARS = 14000
_GXX_GENERATED_BY_RE = re.compile(r"\n*<!--\s*generated_by:.*?-->\s*$", re.S | re.I)

# TODO(临时)：仅生成下列组号的 Gxx.md；恢复全量时改为 None
# _GXX_ONLY_GROUP_IDS: Optional[Set[int]] = {3, 7, 17}
_GXX_ONLY_GROUP_IDS: Optional[Set[int]] = None


def _filter_gxx_job_groups(keys: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
    if not _GXX_ONLY_GROUP_IDS:
        return keys
    allowed = {int(g) for g in _GXX_ONLY_GROUP_IDS}
    kept = [pair for pair in keys if int(pair[1]) in allowed]
    skipped = [pair for pair in keys if int(pair[1]) not in allowed]
    if skipped:
        print(
            "[Gxx 临时过滤] 仅生成 G"
            + "/G".join(f"{g:02d}" for g in sorted(allowed))
            + f"；跳过 {len(skipped)} 组: "
            + ", ".join(f"G{g:02d}({t})" for t, g in skipped),
        )
    return kept


def _user_raw_dir(username: str) -> str:
    return os.path.normpath("./received_dir/user_raw_file/" + username.replace("\\", "/"))


def _twin_dir(username: str) -> str:
    d = os.path.join(_user_raw_dir(username), "_twin")
    os.makedirs(d, exist_ok=True)
    return d


def _strip_gxx_generated_footer(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    return _GXX_GENERATED_BY_RE.sub("", text).strip()


def _load_prior_gxx_body(username: str, gid: int) -> Tuple[str, bool]:
    """读取既有 Gxx.md 正文（去掉生成脚注），供本周再生成时作「上周/往期」对比基线。"""
    raw = read_twin_file(username, f"G{int(gid):02d}.md")
    body = _strip_gxx_generated_footer(raw or "")
    if not body:
        return "", False
    if len(body) > _PRIOR_GXX_MAX_CHARS:
        body = body[:_PRIOR_GXX_MAX_CHARS] + "\n…（既有 Gxx 过长，此处截断供对比）"
    return body, True


def _load_claude_46_cfg() -> Dict[str, str]:
    from app_chat.scene_models import get_scene_value, resolve_openai_cfg_from_abbr

    abbr = get_scene_value('gxx_claude', 'claude-sonnet-4.6')
    return resolve_openai_cfg_from_abbr(
        abbr,
        default_model='claude-sonnet-4-6-X',
        default_base=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
        default_key='',
    )


def _gxx_gemini_model() -> str:
    env_val = os.environ.get('NKCN_DMT_GEMINI_MODEL', '').strip()
    if env_val:
        return env_val
    from app_chat.scene_models import get_scene_value
    return get_scene_value('gxx_gemini', _GEMINI_FALLBACK_MODEL)


def _extract_pdf_text_preview(abs_path: str, max_chars: int = 11000) -> str:
    try:
        import fitz

        doc = fitz.open(abs_path)
        parts: List[str] = []
        n = min(doc.page_count, 25)
        for i in range(n):
            parts.append(doc.load_page(i).get_text("text") or "")
            if sum(len(x) for x in parts) >= max_chars:
                break
        doc.close()
        text = "\n".join(parts).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…(截断)"
        return text
    except Exception as e:
        return f"[PDF文本抽取失败: {e}]"


def _read_text_file_preview(abs_path: str, max_chars: int = 11000) -> str:
    try:
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            t = f.read()
        if len(t) > max_chars:
            return t[:max_chars] + "\n…(截断)"
        return t
    except Exception as e:
        return f"[读取失败: {e}]"


def _material_snippet(username: str, file_name: str, *, fulltext: bool = True) -> str:
    """
    从用户目录读取文件做摘录：fulltext=True 时篇幅上限较大，False 时较短（仅供服务端实现，勿写入模型提示）。
    """
    base = _user_raw_dir(username)
    path = os.path.join(base, file_name)
    if not os.path.isfile(path):
        return ""
    ext = os.path.splitext(file_name)[1].lower()
    cap_pdf = 11000 if fulltext else 2800
    cap_txt = 11000 if fulltext else 3600
    if ext == ".pdf":
        return _extract_pdf_text_preview(path, max_chars=cap_pdf)
    if ext in (".txt", ".md", ".csv", ".json"):
        return _read_text_file_preview(path, max_chars=cap_txt)
    return ""


def _gxx_related_bucket(fn: str, theme_kw: str, gid: int, week: Optional[int]) -> Optional[str]:
    """内部归类键：b1/b6/b7/c 或 None（不写入模型提示）。"""
    if fn in SCENE_BASE_DOC_NAMES:
        return "c"
    if "各组除乘加三法则分析填写" in fn:
        return "b6"
    if "智能纪要" in fn and "周教研" in fn:
        return "b1"
    if nk2026_matches_b_planning_xml_log_gxx(fn, theme_kw, gid):
        return "b7"
    return None


def _gxx_rag_query_and_core_keyword(
    bucket: str, theme_kw: str, gid: int, week: Optional[int]
) -> Tuple[str, str]:
    """返回 (检索用语, 核心关键词)，仅用于服务端检索，不暴露给模型。"""
    if bucket == "b1":
        wk = f"W{week} " if week is not None else ""
        q = f"{theme_kw} G{gid:02d}组 {wk}智能纪要 周教研 小组进展 公能 梯子图"
        ck = f"{theme_kw}主题G{gid:02d}组"
        return q, ck
    if bucket == "b6":
        q = f"G{gid:02d}组 除乘加三法则 各组分析 填写 版本"
        ck = f"G{gid:02d}组"
        return q, ck
    if bucket == "c":
        q = f"{theme_kw} 嵌入式课设 实验 课程目标 教研 助教 NK2026 场景预置"
        ck = f"{theme_kw}主题"
        return q, ck
    if bucket == "b7":
        wk = f"W{week} " if week is not None else ""
        q = f"{wk}{theme_kw} G{gid:02d}组 规划表 代码修改 8XML 日志 记录"
        ck = f"{theme_kw}主题G{gid:02d}组"
        return q, ck
    return "", ""


def _flatten_rag_segments(all_segments: Any) -> str:
    if not all_segments:
        return ""
    parts: List[str] = []
    for doc_seg in all_segments:
        if not doc_seg:
            continue
        for seg in doc_seg:
            pc = getattr(seg, "page_content", None) or ""
            if str(pc).strip():
                parts.append(str(pc).strip())
    return "\n\n".join(parts)


def _read_pre_summary_for_doc(username: str, doc_name: str) -> str:
    """读取纲要类 md 并入模型上下文，标签用语保持中性。"""
    if "_" not in username:
        return ""
    real_name = username.split("_")[0]
    book_name = username[len(real_name) + 1 :]
    base = os.path.splitext(doc_name)[0]
    ext = os.path.splitext(doc_name)[1].lstrip(".")
    chunks: List[str] = []
    md_path = (
        f"./received_dir/user_raw_file/{real_name}_{book_name}/pre_summary/"
        f"{base}_Presummary_{ext}.md"
    )
    if os.path.isfile(md_path):
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                t = f.read().strip()
            if t:
                chunks.append(f"【文档 {doc_name}·纲要摘录】\n{t}")
        except Exception as e:
            chunks.append(f"【文档 {doc_name}】纲要读取异常：{e}")
    low = doc_name.lower()
    if low.endswith(".pdf"):
        img_path = (
            f"./received_dir/user_raw_file/{real_name}_{book_name}/pre_image_summary/"
            f"{base}_PreImageSummary_pdf.md"
        )
        if os.path.isfile(img_path):
            try:
                with open(img_path, "r", encoding="utf-8") as f:
                    im = f.read().strip()
                if im:
                    chunks.append(f"【文档 {doc_name}·图文纲要】\n{im}")
            except Exception as e:
                chunks.append(f"【文档 {doc_name}】图文纲要读取异常：{e}")
    return "\n\n".join(chunks)


def _material_snippet_vector_tab(
    username: str,
    fn: str,
    theme_kw: str,
    gid: int,
    week: Optional[int],
    bucket: str,
) -> str:
    """按关键词从库中检索相关片段，并拼接纲要类摘录；实现细节不向模型说明。"""
    from llm_langchain import util as lc_util

    q, ck = _gxx_rag_query_and_core_keyword(bucket, theme_kw, gid, week)
    print(f"[Gxx RAG] file={fn!r} bucket={bucket} core_keyword={ck!r} query_preview={q[:72]!r}…")

    pres = _read_pre_summary_for_doc(username, fn)
    rag_txt = ""
    try:
        segs = lc_util.get_docs_all_split(
            username, [fn], [3], text_for_search=q, core_keyword=ck
        )
        rag_txt = _flatten_rag_segments(segs)
        print(f"[Gxx RAG] file={fn!r} rag_chars={len(rag_txt)} pres_chars={len(pres)}")
    except Exception as e:
        print(f"[Gxx RAG] get_docs_all_split failed file={fn!r}: {e}")

    if not (rag_txt or "").strip():
        rag_txt = _material_snippet(username, fn, fulltext=False)
        print(f"[Gxx RAG] file={fn!r} fallback_disk_short chars={len(rag_txt)}")

    blocks: List[str] = []
    if pres.strip():
        blocks.append(pres.strip())
    if rag_txt.strip():
        blocks.append("【相关摘录】\n" + rag_txt.strip())
    return "\n\n".join(blocks)


def discover_group_keys(file_names: List[str]) -> List[Tuple[str, int]]:
    """返回 [(theme_kw, group_id), ...] 去重排序。"""
    found: Dict[Tuple[str, int], bool] = {}
    for fn in file_names:
        meta = parse_target_ladder_meta(fn)
        if meta:
            found[(meta["theme_kw"], int(meta["group_id"]))] = True
            continue
        m = re.search(r"(?<![A-Za-z])G(\d{1,2})\b", fn, re.I)
        if m:
            gid = int(m.group(1))
            tk = theme_keyword_in_text(fn)
            if tk:
                found[(tk, gid)] = True
    keys = sorted(found.keys(), key=lambda x: (x[0], x[1]))
    return keys


def _call_openai_compatible(
    cfg: Dict[str, str],
    messages: List[Dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: int,
    attempts: int,
) -> Tuple[str, str]:
    last_err = ""
    for i in range(max(1, attempts)):
        try:
            client = OpenAI(
                api_key=cfg.get("api_key") or "",
                base_url=str(cfg.get("base_url") or "").rstrip("/") + "/",
                timeout=timeout,
            )
            rsp = client.chat.completions.create(
                model=cfg.get("model") or "",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = str(rsp.choices[0].message.content or "").strip()
            if text:
                return text, f"{cfg.get('model')} 第{i + 1}次"
            last_err = "empty_output"
        except Exception as e:
            last_err = str(e)
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(last_err or "model_failed")


def generate_gxx_markdown_with_fallback(system_prompt: str, user_prompt: str) -> Tuple[str, str]:
    """
    按输入总字数（system+user）选择主模型与回退顺序：
    - 小于 30000 字：优先 claude-sonnet-4.6（3 次），失败再 Gemini（3 次）。
    - 不小于 30000 字：优先 Gemini（3 次），失败再 Claude（3 次）。
    返回 (markdown, meta_note)。
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    total_chars = len(system_prompt or "") + len(user_prompt or "")
    prefer_claude_first = total_chars < 30000

    gem_cfg = {
        "model": _gxx_gemini_model(),
        "base_url": _GEMINI_FALLBACK_BASE.rstrip("/"),
        "api_key": _GEMINI_FALLBACK_KEY,
    }
    claude_cfg = _load_claude_46_cfg()

    def _attempt(cfg: Dict[str, str], label: str) -> Tuple[str, str]:
        if not (cfg.get("api_key") or "").strip():
            raise RuntimeError(f"{label} 未配置 openai_api_key")
        return _call_openai_compatible(
            cfg,
            messages,
            max_tokens=12888,
            temperature=0.2,
            timeout=600,
            attempts=3,
        )

    primary_label = "claude-sonnet-4.6" if prefer_claude_first else "gemini"
    fallback_label = "gemini" if prefer_claude_first else "claude-sonnet-4.6"
    primary_cfg = claude_cfg if prefer_claude_first else gem_cfg
    fallback_cfg = gem_cfg if prefer_claude_first else claude_cfg

    primary_err: Optional[BaseException] = None
    try:
        text, note = _attempt(primary_cfg, primary_label)
        return text, f"{note} ({primary_label}; input_chars={total_chars})"
    except Exception as e:
        primary_err = e

    try:
        text, note = _attempt(fallback_cfg, fallback_label)
        return text, (
            f"{note} ({fallback_label} fallback after {primary_label}: {primary_err}; "
            f"input_chars={total_chars})"
        )
    except Exception as e2:
        raise RuntimeError(
            f"Gxx 生成失败：{primary_label} 与 {fallback_label} 均不可用。"
            f" primary_err={primary_err!r} fallback_err={e2!r}"
        ) from e2


def _ontology_instructions(*, has_prior_gxx: bool) -> str:
    prior_note = (
        "下方提供了**既有 Gxx.md 全文**，第四节须将其视为**上周/往期周次基线**，与**当周新摘录**对照撰写。"
        if has_prior_gxx
        else "下方**无既有 Gxx.md**；第四节写「首次建档」：仅据当周材料概括阶段性态势，**勿编造**与之前周次的具体对比句。"
    )
    length_note = (
        "**全文总字数（含标题、标点）控制在 1300～1600 字**；第四节约 250～400 字，一、二节仍须保留关键原话。"
        if has_prior_gxx
        else "**全文总字数控制在 1000～1300 字**；第四节约 120～200 字即可。"
    )
    return f"""你必须输出一篇**完整可覆盖落盘**的 Markdown 正文（不要包裹在代码块里），且**只含以下四个一级章节**（## 一、～## 四、），勿增加无关长附录。

{prior_note}

## 一、本组自填与产出（原文为主）
从下方摘录中**尽量全面、完整**提取出**与本组强相关**的**原话/原文**（可带简短来源括号注明文件名或片段位置）。包括但不限于：
- 梯子图填写各区域（组织关/操作关/精进关/目标关四关心得、V1.x和V2.x课程+组织双目标、代码/Issue数&注释/发问数、组员私份/小组公份<五角色都要写>两处心得、除法/乘法/加法三处分析区、蛙鸣·涌现·微创新的一处记录区）已出现的**具体填写原文**，以及哪些区还暂时空白没写；
- 本组「除乘加三法则分析」等**本组填写/分析原文**（偏长要浓缩或略去一些不那么重要的，但是是浓缩不是摘要，尽量不要漏内容）；
- 摘录中本组当周**代码、8XML、日志**等文字，同样**原文录入**（偏长则要浓缩或略去一些不那么重要的，同上）。

## 二、教研与谈话中涉及本组的原话
从摘录中摘录**周教研、Wxx周课后 TA 助教小结**里**点评到本组**的句子原话（无则写「未见相关原话」）；以及**Wxx周激励小组谈话实录**中**本组成员发言原话**与**教师/助教补充点评原话**（无则略）。仍要求**原话为主**。

## 三、本组特点（深入浅出的分析）
做此小组的**情况和特点**分析；若素材足以区分角色，可**细化到角色**（如组长等）；**材料不足或某角色无依据时不得编造**，该角色可简要带过。主要是要分析出此小组的基本特征、情况、特点等，**勿写假设表、开放问题、空泛铺陈等大段空话。**

## 四、相较于之前周次的变化
对照**既有 Gxx（之前周次情况）**与**当周新摘录**，写清周际变化（无既有 Gxx 时按任务说明简写）。建议用短列表或小标题组织，须覆盖（无依据则写「未见」/「无法判断」，禁止编造）：
- **已解决的进步**：之前周次里已暴露过的问题/弱势，本周材料显示已改善或已补齐的（各 1～3 条为宜）；
- **仍存问题**：之前周次就有、本周仍反复出现或仍未闭合的；
- **本周新出现**：分三类简述——**弱势问题**、**常规情况**、**亮点进步**（某类无则写「无」）。

### 篇幅与处理方式（硬性）
- {length_note}
- 第一、二部分若仍偏长：允许**浓缩**——即删去重复、衔接语、非「本组强相关」的边角等不那么重要的内容，**保留信息不丢要点**；**禁止写成「摘要体」**（禁止泛泛改写导致事实原文遗漏）。
- 次要连续段落可用中文省略号「……」表示中间略去，但须在省略之间保留几处足以定位的**原话头中尾**。
- 禁止编造具体姓名、分数、未出现的结论；第四节对比须有**既有 Gxx 或当周摘录**中的依据。
- 若下方「本组角色信息」提供了**固定名单那一行**，则成稿正文中**必须原样包含该行一次**（独立成行，一字不改，含标点与职务名）；放在一级标题 `# Gxx·主题` 的**紧邻下一行**（先于「## 一、」），不得拆散或改写。
- 输出为**整篇替换**的 Gxx.md：一～四节均按**本周最新情况**重写（不是只追加第四节）。
- 注意不要只说“本周”、“上周”这类描述，一定要说“本周Wxx”、“上周Wxx”、“之前周次Wxx”等，否则到了以后容易混淆不清
- 要为此小组建立一个精准独特的小组本体画像，且随版本推进及变化、周次推进及变化、小组之间差异、有无可取长补短学习优秀经验/方法/思路以改善本组缺陷/提升本组的其他小组做法、教师讲的除乘加正本清源内容如何产生对本组实际情况最适配的认知提升帮助（特别是在W13周及之后）...等等，而不断更新、完善、优化、迭代，始终保持精准、独特、动态、鲜活、有生命力。

输出开头请用一级标题一行点明小组，例如：`# G7·车联`（组号与主题与任务一致即可）。"""


def build_prompts_for_group(
    username: str,
    scene_name: str,
    notebook_description: str,
    theme_kw: str,
    gid: int,
    week: Optional[int],
    material: Sequence[Tuple[str, bool]],
    *,
    prior_gxx_md: str = "",
) -> Tuple[str, str]:
    has_prior = bool((prior_gxx_md or "").strip())
    sys_p = (
        "你是 NK2026 课设群组场景下的「小组素材原文摘录员 + 精准独特&动态鲜活的小组特点侧写 + 周际对比侧写」。"
        "任务：依据下方文件名与摘录，为指定小组产出一份**精炼、高密度、精准到位**的 Gxx.md正文。"
        "第一、二部分以**原话原文**为主；第三部分要依据具体材料深入分析；第四节对照既有 Gxx（若有）写周际变化。禁止空话与编造。\n"
        + _ontology_instructions(has_prior_gxx=has_prior)
    )

    def _material_label(fn: str, full: bool) -> str:
        return "完整摘录" if full else "相关摘录"

    if material:
        name_lines = [f"- {fn}  （{_material_label(fn, full)}）" for fn, full in material]
    else:
        name_lines = [
            "(未发现符合规则的素材文件名；请仅凭本子描述与下列可能为空的摘录保守撰写)"
        ]

    role_line = nk2026_group_role_line(gid)
    week_line = (
        f"当前素材推断周次：**W{int(week)}**（第四节「上周」= 下方既有 Gxx 所反映的往期状态，勿与文件名中其它周次混淆）。"
        if week is not None
        else "当前素材推断周次：**未能从文件名解析**（第四节对比时仅依据既有 Gxx 与当周摘录，勿编造周次编号）。"
    )
    lines = [
        f"场景：{scene_name}",
        f"本子描述摘要：{(notebook_description or '')[:1200]}",
        f"对象小组：主题={theme_kw}，组号={gid}（输出文件名逻辑名 G{gid:02d}.md）",
        week_line,
        "",
    ]
    if has_prior:
        lines.extend(
            [
                "### 既有 Gxx.md（上周/往期周次基线，第四节须对照）",
                "以下内容为磁盘上**更新前**的本组 Gxx，生成新的一～四节时：一～三节按**当周摘录及相关情况分析**重写；第四节须相对此基线写变化。",
                "",
                prior_gxx_md.strip(),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "### 既有 Gxx.md",
                "（无：本组首次生成，第四节按提示写「首次建档」即可。）",
                "",
            ]
        )
    if role_line.strip():
        lines.extend(
            [
                "### 本组角色信息（硬性：须写入 Gxx 成稿）",
                "以下一行须在成稿正文中**原样**出现一次：紧跟在一级标题 `# Gxx·主题` 的下一行，先于「## 一、」；不得增删改人名、职务与标点。",
                role_line.strip(),
                "",
            ]
        )
    lines.extend(
        [
            "### 可能与本组相关的文档素材",
            "\n".join(name_lines),
            "",
            "### 各文件摘录内容（无正文的文件此处可能为空）",
        ]
    )
    bundle_chars = 0
    for fn, use_full in material:
        bk = _gxx_related_bucket(fn, theme_kw, gid, week) if not use_full else None
        if use_full and _is_ladder_fill_image_filename(fn):
            pres = _read_pre_summary_for_doc(username, fn)
            vec = _image_layers_text(username, fn, cap=850000, max_seq=160)
            blocks_ladder: List[str] = []
            if pres.strip():
                blocks_ladder.append(pres.strip())
            if vec.strip():
                blocks_ladder.append("【向量库·图片理解全文】\n" + vec.strip())
            snip = "\n\n".join(blocks_ladder)
            if not snip.strip():
                snip = "（该梯子图填写图片暂无向量库图片理解文本，请先完成图片理解入库。）"
        elif use_full:
            snip = _material_snippet(username, fn, fulltext=True)
        elif bk in ("b1", "b6", "b7", "c"):
            snip = _material_snippet_vector_tab(username, fn, theme_kw, gid, week, bk)
        else:
            snip = _material_snippet(username, fn, fulltext=False)
        if not snip:
            continue
        block = f"\n--- 文件: {fn} ---\n{snip}\n"
        if bundle_chars + len(block) > _MAX_CHARS_DOC_BUNDLE:
            lines.append("\n…(摘录总长已达上限，其余文件仅保留文件名列表)\n")
            break
        lines.append(block)
        bundle_chars += len(block)

    lines.append("")
    lines.append("### 输出提醒（务必遵守）")
    if has_prior:
        length_remind = "- 成稿**总字数 1300～1600 汉字**；**## 四、** 须写清：已解决进步 / 仍存问题 / 本周新出现（弱势·常规·亮点）。\n"
    else:
        length_remind = "- 成稿**总字数 1000～1300 汉字**；**## 四、** 按「首次建档」简写。\n"
    remind = [
        length_remind,
        "- 仅允许 **## 一、** **## 二、** **## 三、** **## 四、** 四节正文；勿增加无关的长框架或附录。\n"
        f"- 输出须为**完整正文**（将覆盖写入 G{gid:02d}.md）。",
    ]
    if role_line.strip():
        remind.append(
            "- 已提供「本组角色信息」时：该行必须出现在一级标题正下方（独立一行，与提示中完全一致）。"
        )
    lines.append("\n".join(remind))

    user_p = "\n".join(lines)
    return sys_p, user_p


def _write_twin_file(username: str, gid: int, content: str) -> str:
    d = _twin_dir(username)
    fname = f"G{gid:02d}.md"
    path = os.path.join(d, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def run_group_twin_job(job_id: str, username: str, scene_name: str, notebook_description: str) -> None:
    with _JOB_LOCK:
        job = _GROUP_TWIN_JOBS.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["message"] = "扫描文档…"

    user_path = _user_raw_dir(username)
    if not os.path.isdir(user_path):
        with _JOB_LOCK:
            j = _GROUP_TWIN_JOBS.get(job_id)
            if j:
                j["status"] = "error"
                j["message"] = "用户文档目录不存在"
        return

    file_names = []
    for f in os.listdir(user_path):
        fp = os.path.join(user_path, f)
        if os.path.isdir(fp):
            continue
        if f.endswith("_transFTWYGUHX.pdf"):
            continue
        file_names.append(f)

    keys = _filter_gxx_job_groups(discover_group_keys(file_names))
    with _JOB_LOCK:
        j = _GROUP_TWIN_JOBS.get(job_id)
        if j:
            j["total"] = len(keys)
            j["done"] = 0
            j["groups"] = [f"{t}{g}组" for t, g in keys]
            suffix = (
                f" · 临时仅 {', '.join(f'G{g:02d}' for g in sorted(_GXX_ONLY_GROUP_IDS))}"
                if _GXX_ONLY_GROUP_IDS
                else ""
            )
            j["message"] = f"待生成 {len(keys)} 个小组摘录{suffix}"

    if not keys:
        with _JOB_LOCK:
            j = _GROUP_TWIN_JOBS.get(job_id)
            if j:
                j["status"] = "done"
                j["message"] = "未发现可解析组号的文档，跳过生成"
        return

    errors: List[str] = []

    def one_group(pair: Tuple[str, int]) -> Tuple[str, Optional[str]]:
        theme_kw, gid = pair
        week_guess = infer_week_for_theme_group(file_names, theme_kw, gid)
        material = collect_nk2026_gxx_input_files(file_names, theme_kw, gid, week_guess)
        prior_body, _has_prior = _load_prior_gxx_body(username, gid)
        sys_p, user_p = build_prompts_for_group(
            username,
            scene_name,
            notebook_description,
            theme_kw,
            gid,
            week_guess,
            material,
            prior_gxx_md=prior_body,
        )
        md, note = generate_gxx_markdown_with_fallback(sys_p, user_p)
        if _has_prior:
            note = f"{note}; prior_gxx_chars={len(prior_body)}"
        md = md.strip()
        if not md.startswith("#"):
            md = f"# 小组摘录 · G{gid:02d}（{theme_kw}）\n\n" + md
        path = _write_twin_file(username, gid, md + f"\n\n<!-- generated_by: {note} -->\n")
        return path, None

    with ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_GROUPS) as ex:
        futures = {ex.submit(one_group, pair): pair for pair in keys}
        for fut in as_completed(futures):
            pair = futures[fut]
            try:
                fut.result()
            except Exception as e:
                errors.append(f"{pair}: {e}")
            with _JOB_LOCK:
                j = _GROUP_TWIN_JOBS.get(job_id)
                if j:
                    j["done"] = int(j.get("done") or 0) + 1
                    j["message"] = f"已完成 {j['done']}/{j['total']} · 当前 {pair[0]} G{pair[1]:02d}"

    with _JOB_LOCK:
        j = _GROUP_TWIN_JOBS.get(job_id)
        if j:
            j["status"] = "done" if not errors else "done_with_errors"
            j["errors"] = errors
            j["message"] = (
                "全部完成"
                if not errors
                else f"完成但有 {len(errors)} 组失败"
            )


def start_job(username: str, scene_name: str, notebook_description: str) -> Optional[str]:
    if not is_nk2026_ladder_scene(scene_name):
        return None
    job_id = uuid.uuid4().hex
    with _JOB_LOCK:
        _GROUP_TWIN_JOBS[job_id] = {
            "username": username,
            "scene_name": scene_name,
            "status": "queued",
            "total": 0,
            "done": 0,
            "groups": [],
            "errors": [],
            "message": "排队中",
            "started_at": time.time(),
        }

    th = threading.Thread(
        target=run_group_twin_job,
        args=(job_id, username, scene_name, notebook_description or ""),
        daemon=True,
    )
    th.start()
    return job_id


def get_progress(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOB_LOCK:
        j = _GROUP_TWIN_JOBS.get(job_id)
        if not j:
            return None
        return dict(j)


def list_twin_files(username: str) -> List[Dict[str, str]]:
    d = _twin_dir(username)
    out: List[Dict[str, str]] = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.upper().startswith("G") and fn.lower().endswith(".md"):
            out.append({"name": fn, "path": os.path.join(d, fn)})
    return out


def read_twin_file(username: str, name: str) -> Optional[str]:
    if not re.match(r"^G\d{1,2}\.md$", name, re.I):
        return None
    path = os.path.join(_twin_dir(username), name)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def ladder_fill_group_id_from_filename(filename: str) -> Optional[int]:
    """
    从文件名解析「××组梯子图填写」中的组号数字；不匹配则返回 None。
    例：W10车联2组梯子图填写（上半部分）→ 2
    """
    if not filename or "梯子图填写" not in filename:
        return None
    m = re.search(r"(\d{1,2})\s*组\s*梯子图填写", filename)
    if m:
        return int(m.group(1))
    return None


def collect_gxx_group_ids_for_context(
    file_names: Sequence[str], target_file: Optional[str] = None
) -> List[int]:
    """勾选文档中含梯子图填写则取其组号；另支持 automation 的 target_file。"""
    gids: List[int] = []
    for fn in file_names or []:
        gid = ladder_fill_group_id_from_filename(fn)
        if gid is not None:
            gids.append(gid)
    if target_file:
        gid = ladder_fill_group_id_from_filename(target_file)
        if gid is not None:
            gids.append(gid)
    return sorted(set(gids))


def build_gxx_markdown_context_blocks(
    username: str, group_ids: Sequence[int], max_total_chars: Optional[int] = None
) -> str:
    """将各组已落盘的 Gxx.md 正文拼成一段，注入对话用户消息前缀。

    `group_ids` 来自当前勾选/自动化解析出的组号列表：通常只有 1 个组，则只读入对应一份
    `Gxx.md`；若同次会话涉及多个组，则按组号顺序拼接多份（组与组之间用分隔线）。

    `max_total_chars`：默认 None，表示不截断（产品约定 Gxx 须全文注入）；若传入正整数则保留旧有总长防护（测试或极端多组时用）。
    """
    parts: List[str] = []
    total = 0
    twin_base = _twin_dir(username)
    truncated = False
    for gid in sorted(set(group_ids)):
        name = f"G{int(gid):02d}.md"
        abs_path = os.path.join(twin_base, name)
        content = read_twin_file(username, name)
        if not content or not str(content).strip():
            print(f"[NK2026 Gxx 注入] 跳过 {name}：文件不存在或为空 path={abs_path!r}")
            continue
        raw = str(content).strip()
        raw_len = len(raw)
        header = f"### 小组摘录（{name}）"
        block = f"{header}\n{raw}"
        if max_total_chars is not None and total + len(block) > max_total_chars:
            remain = max_total_chars - total - 80
            if remain > 200:
                block = block[:remain] + "\n…(以下截断)"
                truncated = True
                print(
                    f"[NK2026 Gxx 注入] {name} 磁盘全文约 {raw_len} 字，因上限 max_total_chars={max_total_chars} "
                    f"注入块截断至约 {len(block)} 字 path={abs_path!r}"
                )
                parts.append(block)
            else:
                print(
                    f"[NK2026 Gxx 注入] {name} 磁盘全文约 {raw_len} 字，剩余配额不足已跳过 path={abs_path!r}"
                )
            break
        parts.append(block)
        total += len(block)
        print(
            f"[NK2026 Gxx 注入] 已纳入 {name} 磁盘全文 {raw_len} 字（本块含标题共 {len(block)} 字）path={abs_path!r}"
        )
    out = "\n\n---\n\n".join(parts)
    if out:
        print(
            f"[NK2026 Gxx 注入] 合成前缀总长约 {len(out)} 字，组号={sorted(set(group_ids))!r}，"
            f"twin_dir={twin_base!r}，是否发生截断={truncated}"
        )
    return out


def prepend_nk2026_gxx_context_if_needed(
    username: str,
    scene_name: str,
    file_names: Sequence[str],
    message: str,
    *,
    target_file: Optional[str] = None,
) -> str:
    """
    NK2026 梯子图场景：当勾选文件名含「××组梯子图填写」或 target_file 含该片段时，
    将对应组已生成的 Gxx 摘录文件前置注入用户消息。
    """
    if not is_nk2026_ladder_scene(scene_name):
        return message
    gids = collect_gxx_group_ids_for_context(file_names, target_file)
    if not gids:
        return message
    body = build_gxx_markdown_context_blocks(username, gids)
    if not body:
        print(
            f"[NK2026 Gxx 注入] 解析到组号 {gids!r}，但未读到任何非空 Gxx.md（请检查 "
            f"{_twin_dir(username)!r} 下是否存在 Gxx.md）"
        )
        return message
    prefix = (
        "【与本组相关的摘录】\n"
        "下列内容与当前「××组梯子图填写」同组，回答时请一并参照（若尚未生成则为空）。\n\n"
        f"{body}\n\n"
        "————————————————————\n"
        "【以下为原始提问 / 对话上下文】\n\n"
    )
    return prefix + message


def prepend_nk2026_chuchengjia_context_if_needed(
    username: str,
    scene_name: str,
    message: str,
) -> str:
    """
    NK2026 梯子图场景：用户提问中含 W13 及之后周次时，将 _twin 下正本清源摘录全文前置注入。
    """
    if not is_nk2026_ladder_scene(scene_name):
        return message
    if not text_references_course_week_at_least(message, NK2026_CHUCHENGJIA_WEEK_MIN):
        return message
    body = read_nk2026_chuchengjia_twin_markdown(username)
    if not body:
        return message
    prefix = (
        "【纸联体联除乘加正本清源（W13+ 必读）】\n"
        "下列为本子 _twin 文件夹中的正本清源完整摘录，回答时请作为认知主轴一并参照。\n\n"
        f"{body}\n\n"
        "————————————————————\n"
        "【以下为原始提问 / 对话上下文】\n\n"
    )
    print(f"[NK2026 正本清源 注入] 已注入全文 {len(body)} 字")
    return prefix + message
